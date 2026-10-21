# -*- coding: utf-8 -*-
"""
患者对话 AI 总结服务
- 独立于 chat_server，不依赖 socket 初始化
- 自带 Redis 缓存（1 小时）
- 条数超限直接返回，不调 AI
"""
from __future__ import annotations

import re
import json
import logging
from datetime import date, datetime, time as dt_time
from typing import Optional

import httpx
from redis.asyncio import Redis
from sqlalchemy import func
from sqlalchemy.orm import Session

from sql.people_models import ChatRoom, Message, SenderType,Patient,Nurse
from sql.nurse_ai_summary_models import NurseAiSummaryLog

logger = logging.getLogger(__name__)

# ==================== 配置 ====================
AI_BASE_URL = "https://agent.dialog.polyusn.com"   # 与 chat_server 保持一致
AI_SUMMARY_TIMEOUT = 50.0                          # 后端调 AI 超时（秒）
MESSAGE_COUNT_LIMIT = 150                          # 条数上限
CACHE_TTL_SECONDS = 3600                           # Redis 缓存 1 小时
CACHE_KEY_PREFIX = "ai_summary:v3:patient"

# 独立 Redis 连接（懒加载）
_summary_redis: Optional[Redis] = None


async def _get_redis() -> Redis:
    global _summary_redis
    if _summary_redis is None:
        _summary_redis = Redis.from_url(
            "redis://localhost:6379/0",
            encoding="utf-8",
            decode_responses=True,
        )
    return _summary_redis


# ==================== Prompt 构造 ====================
_ROLE_LABEL = {
    SenderType.PATIENT: "患者",
    SenderType.AI: "AI",
    SenderType.NURSE: "护士",
}


def _build_prompt(messages, start_date: str, end_date: str) -> str:
    lines = [
        f"以下是患者 {start_date} 至 {end_date} 期间与 AI 助手的对话记录，每条消息前有编号：",
        "",
    ]
    for idx, msg in enumerate(messages, 1):
        content = (msg.content or "").strip()
        if not content:
            continue
        role = _ROLE_LABEL.get(msg.sender_type, "系统")
        ts = msg.create_time.strftime("%Y-%m-%d %H:%M") if msg.create_time else ""
        lines.append(f"[#{idx}][{ts}] {role}：{content}")

    total = len(messages)
    lines.extend([
        "",
        "请从护士视角总结这段对话，用 2-4 条要点，严格按以下格式输出：",
        "",
        "1. <一句话结论，不超过25字> | refs: [1, 3, 5]",
        "2. <一句话结论> | refs: [7]",
        "",
        "要求：",
        f"- refs 必须从上面的编号（1-{total}）中选择，不要编造",
        "- 每条要点选 1-3 条最能支撑它的消息编号",
        "- 只输出要点，不要加'根据以上'之类的开头",
    ])
    return "\n".join(lines)


# ==================== 调 AI ====================
async def _call_ai_summary(prompt: str) -> Optional[str]:
    """
    一次调用，不重试。stopped / needs_input 等任何 state 只要 message 有内容就返回。
    """
    if not prompt.strip():
        return None

    try:
        async with httpx.AsyncClient(verify=False, timeout=AI_SUMMARY_TIMEOUT) as client:
            res = await client.post(
                f"{AI_BASE_URL}/api/public/chat",
                json={"message": prompt, "session_id": None},
            )
    except httpx.TimeoutException:
        logger.error("AI summary 超时")
        return None
    except Exception as e:
        logger.error(f"AI summary 请求异常: {e}")
        return None

    if res.status_code != 200:
        logger.error(f"AI summary HTTP {res.status_code}: {res.text[:200]}")
        return None

    try:
        data = res.json()
    except Exception as e:
        logger.error(f"AI summary JSON 解析失败: {e}")
        return None

    text = (data.get("message") or "").strip()
    return text or None

# 容忍：句号、空格、全角冒号、全角方括号
_POINT_PATTERN = re.compile(
    r'^\s*\d+\s*[.．、]\s*(.+?)\s*[|｜]\s*refs\s*[:：]\s*[\[［]?([\d,\s，]+)[\]］]?',
    re.MULTILINE,
)


def _parse_summary_with_refs(raw_text: str, messages: list) -> dict:
    """
    解析 AI 输出：
      1. 患者关心血糖 | refs: [1, 3, 5]
    → {"points": [{"text": "...", "message_uuids": [...]}], "raw": "原文"}
    解析失败时 points 为空，前端 fallback 到 raw。
    """
    points = []
    for match in _POINT_PATTERN.finditer(raw_text or ""):
        text = (match.group(1) or "").strip().rstrip("。.．，,")
        refs_str = match.group(2) or ""

        ref_nums = [int(x) for x in re.findall(r"\d+", refs_str)]
        uuids = []
        for n in ref_nums:
            idx = n - 1
            if 0 <= idx < len(messages):
                uuids.append(messages[idx].message_uuid)

        if text and uuids:
            points.append({"text": text, "message_uuids": uuids})

    return {"points": points, "raw": raw_text or ""}

def _log_summary(
    db: Session,
    patient_id: int,
    patient_name: str,
    nurse_id: int,
    nurse_name: str,
    start_date: date,
    end_date: date,
    message_count: int,
    summary_content: str,
    from_cache: bool,
) -> None:
    """写日志失败不影响主流程"""
    try:
        row = NurseAiSummaryLog(
            patient_id=patient_id,
            patient_name=patient_name,
            nurse_id=nurse_id,
            nurse_name=nurse_name,
            start_date=start_date,
            end_date=end_date,
            message_count=message_count,
            summary_content=summary_content,
            from_cache=1 if from_cache else 0,
        )
        db.add(row)
        db.commit()
    except Exception as e:
        db.rollback()
        logger.warning(f"AI summary 日志写入失败（忽略）: {e}")

# ==================== 主入口 ====================
async def get_patient_ai_summary(
    db: Session,
    patient_id: int,
    start_date: date,
    end_date: date,
    nurse_id: int,
) -> dict:
    """
    返回:
      {
        "status": "ok" | "empty" | "too_many" | "error",
        "summary": str | None,
        "message_count": int,
        "from_cache": bool,     # 可选
      }
    """

    # 0. 查患者和护士姓名（用于日志快照）
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        return {"status": "empty", "summary": None, "message_count": 0}
    patient_name = patient.full_name or f"Patient#{patient_id}"

    nurse = db.query(Nurse).filter(Nurse.nurse_id == nurse_id).first()
    nurse_name = (nurse.full_name if nurse else "") or f"Nurse#{nurse_id}"

    # 1. 找房间
    chat_room = db.query(ChatRoom).filter(ChatRoom.patient_id == patient_id).first()
    if not chat_room:
        return {"status": "empty", "summary": None, "message_count": 0}

    room_id = chat_room.room_id
    start_dt = datetime.combine(start_date, dt_time.min)
    end_dt = datetime.combine(end_date, dt_time.max)

    # 2. 只统计条数（不查内容，快）
    count = (
        db.query(func.count(Message.message_id))
        .filter(
            Message.room_id == room_id,
            Message.create_time >= start_dt,
            Message.create_time <= end_dt,
            Message.sender_type != SenderType.SYSTEM,
        )
        .scalar()
        or 0
    )

    # 2. 只统计条数
    count = (
            db.query(func.count(Message.message_id))
            .filter(
                Message.room_id == room_id,
                Message.create_time >= start_dt,
                Message.create_time <= end_dt,
                Message.sender_type != SenderType.SYSTEM,
            )
            .scalar()
            or 0
    )

    if count == 0:
        return {
            "status": "empty", "points": [], "raw": "",
            "message_count": 0, "truncated": False,
        }

    truncated = count > MESSAGE_COUNT_LIMIT

    # 3. 查缓存（JSON 格式，带 points）
    cache_key = f"{CACHE_KEY_PREFIX}:{patient_id}:{start_date.isoformat()}:{end_date.isoformat()}"
    try:
        r = await _get_redis()
        cached_raw = await r.get(cache_key)
        if cached_raw:
            cached_obj = json.loads(cached_raw)
            cached_points = cached_obj.get("points", [])
            cached_summary_text = cached_obj.get("raw", "")
            if cached_points or cached_summary_text:
                _log_summary(
                    db=db, patient_id=patient_id, patient_name=patient_name,
                    nurse_id=nurse_id, nurse_name=nurse_name,
                    start_date=start_date, end_date=end_date,
                    message_count=cached_obj.get("total_count", count),
                    summary_content=cached_summary_text,
                    from_cache=True,
                )
                return {
                    "status": "ok",
                    "points": cached_points,
                    "raw": cached_summary_text,
                    "message_count": cached_obj.get("total_count", count),
                    "truncated": cached_obj.get("truncated", truncated),
                    "from_cache": True,
                }
    except Exception as e:
        logger.warning(f"AI summary Redis 读取失败（忽略）: {e}")

    # 4. 查内容：超限时取时间最晚的 150 条
    messages = (
        db.query(Message)
        .filter(
            Message.room_id == room_id,
            Message.create_time >= start_dt,
            Message.create_time <= end_dt,
            Message.sender_type != SenderType.SYSTEM,
        )
        .order_by(Message.create_time.desc())
        .limit(MESSAGE_COUNT_LIMIT)
        .all()
    )
    messages.reverse()  # 翻转成时间正序

    # 5. 拼 prompt + 调 AI
    prompt = _build_prompt(messages, start_date.isoformat(), end_date.isoformat())
    raw_text = await _call_ai_summary(prompt)

    if not raw_text:
        return {
            "status": "error", "points": [], "raw": "",
            "message_count": count, "truncated": truncated,
        }

    # 6. 解析成结构化要点
    parsed = _parse_summary_with_refs(raw_text, messages)

    # 7. 写缓存（JSON 格式）
    try:
        r = await _get_redis()
        cache_obj = {
            "points": parsed["points"],
            "raw": parsed["raw"],
            "total_count": count,
            "truncated": truncated,
        }
        await r.setex(cache_key, CACHE_TTL_SECONDS, json.dumps(cache_obj, ensure_ascii=False))
    except Exception as e:
        logger.warning(f"AI summary Redis 写入失败（忽略）: {e}")

    # 8. 写日志
    _log_summary(
        db=db, patient_id=patient_id, patient_name=patient_name,
        nurse_id=nurse_id, nurse_name=nurse_name,
        start_date=start_date, end_date=end_date,
        message_count=count, summary_content=parsed["raw"],
        from_cache=False,
    )

    return {
        "status": "ok",
        "points": parsed["points"],
        "raw": parsed["raw"],
        "message_count": count,
        "truncated": truncated,
        "from_cache": False,
    }