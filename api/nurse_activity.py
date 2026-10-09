from __future__ import annotations

import logging
from datetime import date, datetime,timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from sql.people_models import Nurse, Patient,NurseLoginCode
from sql.nurse_activity_models import (
    NurseActivityLog,
    NurseActionType,
    NurseTestType,
    NurseMessageType,
)
from schema.nurse_activity import (
    NurseActivityLogCreate,
    NurseActivityLogResponse,
)

from fastapi import Body, Query
from fastapi.responses import Response
from sqlalchemy import func
from datetime import datetime as dt

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/nurse-activity", tags=["护士操作日志"])


# ============ 你的同步 get_db ============
# 假设项目里的写法是：
# from db.session import get_db
# 这里保持你原有的导入方式即可
from sql.start import get_db   # ← 按你项目实际路径调整


def _parse_date(v: Optional[str]) -> Optional[date]:
    if not v:
        return None
    try:
        return date.fromisoformat(v)
    except ValueError:
        return None


def _parse_datetime(v: Optional[str]) -> Optional[datetime]:
    if not v:
        return None
    try:
        # 兼容带 Z 的 ISO
        return datetime.fromisoformat(v.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _to_int(v) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


@router.post(
    "/log",
    response_model=NurseActivityLogResponse,
    summary="插入护士操作日志",
)
def log_nurse_activity(
    payload: NurseActivityLogCreate,
    db: Session = Depends(get_db),
):
    """
    前端埋点统一入口。
    失败不抛异常阻塞前端（返回 success=False），只写日志。
    """
    # 1. 校验 action_type
    try:
        action_type = NurseActionType(payload.action_type)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"无效的 action_type: {payload.action_type}",
        )

    # 2. 校验 nurse_id
    nurse_id = _to_int(payload.nurse_id)
    if not nurse_id:
        raise HTTPException(status_code=400, detail="nurse_id 无效")

    # 3. 护士是否存在（避免脏数据；失败也不阻塞前端使用）
    nurse_exists = (
        db.query(Nurse.nurse_id).filter(Nurse.nurse_id == nurse_id).first()
    )
    if not nurse_exists:
        logger.warning("nurse_activity: nurse_id=%s 不存在，跳过记录", nurse_id)
        return NurseActivityLogResponse(success=False, message="护士不存在")

    # 4. patient_id 校验（可空）
    patient_id = _to_int(payload.patient_id)
    if patient_id:
        patient_exists = (
            db.query(Patient.patient_id)
            .filter(Patient.patient_id == patient_id)
            .first()
        )
        if not patient_exists:
            # 病人不存在时，把 patient_id 置空，仍然记录操作
            patient_id = None

    # 5. test_type 校验
    test_type: Optional[NurseTestType] = None
    if payload.test_type:
        try:
            test_type = NurseTestType(payload.test_type)
        except ValueError:
            test_type = None

    # 6. message_type 校验
    message_type: Optional[NurseMessageType] = None
    if payload.message_type:
        try:
            message_type = NurseMessageType(payload.message_type)
        except ValueError:
            message_type = None

    # 7. content 长度保护（避免超长文本撑爆 TEXT）
    content = payload.content
    if content and len(content) > 20000:
        content = content[:20000]

    # 8. 写库
    try:
        row = NurseActivityLog(
            nurse_id=nurse_id,
            action_type=action_type,
            patient_id=patient_id,
            room_uuid=payload.room_uuid,
            target_date=_parse_date(payload.target_date),
            record_id=_to_int(payload.record_id),
            test_type=test_type,
            message_uuid=payload.message_uuid,
            content=content,
            message_type=message_type,
            chat_mode=payload.chat_mode,
            extra_data=payload.metadata,
            client_ts=_parse_datetime(payload.client_ts),
        )
        db.add(row)
        db.commit()
        db.refresh(row)

        return NurseActivityLogResponse(
            success=True, message="记录成功", id=row.id
        )

    except Exception as e:
        db.rollback()
        logger.exception("nurse_activity 写入失败: %s", e)
        # 埋点失败不阻塞前端，返回 200 + success=False
        return NurseActivityLogResponse(success=False, message="记录失败")


@router.get("/nurses", summary="护士列表（下拉用）")
def list_nurses_for_filter(db: Session = Depends(get_db)):
    rows = (
        db.query(Nurse.nurse_id, Nurse.first_name, Nurse.last_name, Nurse.phone)
        .order_by(Nurse.nurse_id.asc())
        .all()
    )
    return [
        {
            "nurse_id": nid,
            "full_name": f"{fn} {ln}",
            "phone": phone,
        }
        for nid, fn, ln, phone in rows
    ]

def _apply_filters(q, nurse_id, patient_id, action_type, start_date, end_date):
    if nurse_id:
        q = q.filter(NurseActivityLog.nurse_id == nurse_id)
    if patient_id:
        q = q.filter(NurseActivityLog.patient_id == patient_id)
    if action_type:
        try:
            q = q.filter(NurseActivityLog.action_type == NurseActionType(action_type))
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效 action_type: {action_type}")
    if start_date:
        q = q.filter(NurseActivityLog.create_time >= dt.fromisoformat(f"{start_date}T00:00:00"))
    if end_date:
        q = q.filter(NurseActivityLog.create_time <= dt.fromisoformat(f"{end_date}T23:59:59"))
    return q


@router.get("/list", summary="分页查询护士操作日志")
def list_nurse_activity(
    nurse_id: int = Query(None),
    patient_id: int = Query(None),
    action_type: str = Query(None),
    start_date: str = Query(None),
    end_date: str = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    q = (
        db.query(
            NurseActivityLog,
            Nurse.first_name.label("nurse_first_name"),
            Nurse.last_name.label("nurse_last_name"),
            Nurse.phone.label("nurse_phone"),
            NurseLoginCode.update_time.label("nurse_last_login"),
            Patient.first_name.label("patient_first_name"),
            Patient.last_name.label("patient_last_name"),
            Patient.subject_code.label("patient_subject_code"),
        )
        .outerjoin(Nurse, NurseActivityLog.nurse_id == Nurse.nurse_id)
        .outerjoin(NurseLoginCode, Nurse.nurse_id == NurseLoginCode.nurse_id)
        .outerjoin(Patient, NurseActivityLog.patient_id == Patient.patient_id)
    )
    q = _apply_filters(q, nurse_id, patient_id, action_type, start_date, end_date)

    total = q.count()
    rows = (
        q.order_by(NurseActivityLog.create_time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    items = []
    for log, n_fn, n_ln, n_phone, n_last_login, p_fn, p_ln, p_code in rows:
        items.append({
            "id": log.id,
            "nurse_id": log.nurse_id,
            "nurse_name": f"{n_fn or ''} {n_ln or ''}".strip(),
            "nurse_phone": n_phone,
            "nurse_last_login": n_last_login.isoformat() if n_last_login else None,
            "patient_id": log.patient_id,
            "patient_name": f"{p_fn or ''} {p_ln or ''}".strip() if log.patient_id else "",
            "patient_subject_code": p_code,
            "action_type": log.action_type.value if log.action_type else None,
            "room_uuid": log.room_uuid,
            "target_date": log.target_date.isoformat() if log.target_date else None,
            "record_id": log.record_id,
            "test_type": log.test_type.value if log.test_type else None,
            "message_uuid": log.message_uuid,
            "content": log.content,
            "message_type": log.message_type.value if log.message_type else None,
            "chat_mode": log.chat_mode,
            "extra_data": log.extra_data,
            "client_ts": log.client_ts.isoformat() if log.client_ts else None,
            "create_time": log.create_time.isoformat() if log.create_time else None,
        })

    return {"total": total, "page": page, "page_size": page_size, "items": items}

@router.get("/stats", summary="护士操作日志统计")
def stats_nurse_activity(
    nurse_id: int = Query(None),
    start_date: str = Query(None),
    end_date: str = Query(None),
    db: Session = Depends(get_db),
):
    # 复用 _apply_filters 中的时间/护士条件
    filters = []
    if nurse_id:
        filters.append(NurseActivityLog.nurse_id == nurse_id)
    if start_date:
        filters.append(NurseActivityLog.create_time >= dt.fromisoformat(f"{start_date}T00:00:00"))
    if end_date:
        filters.append(NurseActivityLog.create_time <= dt.fromisoformat(f"{end_date}T23:59:59"))

    total = db.query(func.count(NurseActivityLog.id)).filter(*filters).scalar() or 0

    by_action_rows = (
        db.query(
            NurseActivityLog.action_type,
            func.count(NurseActivityLog.id).label("cnt"),
        )
        .filter(*filters)
        .group_by(NurseActivityLog.action_type)
        .all()
    )

    by_nurse_rows = (
        db.query(
            NurseActivityLog.nurse_id,
            Nurse.first_name,
            Nurse.last_name,
            func.count(NurseActivityLog.id).label("cnt"),
        )
        .outerjoin(Nurse, NurseActivityLog.nurse_id == Nurse.nurse_id)
        .filter(*filters)
        .group_by(NurseActivityLog.nurse_id, Nurse.first_name, Nurse.last_name)
        .order_by(func.count(NurseActivityLog.id).desc())
        .all()
    )

    by_date_rows = (
        db.query(
            func.date(NurseActivityLog.create_time).label("d"),
            func.count(NurseActivityLog.id).label("cnt"),
        )
        .filter(*filters)
        .group_by(func.date(NurseActivityLog.create_time))
        .order_by(func.date(NurseActivityLog.create_time).desc())
        .all()
    )

    return {
        "total": total,
        "by_action_type": [
            {"action_type": a.value if a else None, "count": c}
            for a, c in by_action_rows
        ],
        "by_nurse": [
            {
                "nurse_id": nid,
                "nurse_name": f"{fn or ''} {ln or ''}".strip(),
                "count": c,
            }
            for nid, fn, ln, c in by_nurse_rows
        ],
        "by_date": [
            {"date": d.isoformat() if hasattr(d, "isoformat") else str(d), "count": c}
            for d, c in by_date_rows
        ],
    }

@router.post("/export", summary="导出护士操作日志（制表符分隔，txt 文件）")
def export_nurse_activity(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    start_date = payload.get("start_date")
    end_date = payload.get("end_date")
    nurse_ids = payload.get("nurse_ids") or None
    action_types = payload.get("action_types") or None

    q = (
        db.query(NurseActivityLog, Nurse, NurseLoginCode, Patient)
        .outerjoin(Nurse, NurseActivityLog.nurse_id == Nurse.nurse_id)
        .outerjoin(NurseLoginCode, Nurse.nurse_id == NurseLoginCode.nurse_id)
        .outerjoin(Patient, NurseActivityLog.patient_id == Patient.patient_id)
        .order_by(NurseActivityLog.create_time.asc())
    )
    if start_date:
        q = q.filter(NurseActivityLog.create_time >= dt.fromisoformat(f"{start_date}T00:00:00"))
    if end_date:
        q = q.filter(NurseActivityLog.create_time <= dt.fromisoformat(f"{end_date}T23:59:59"))
    if nurse_ids:
        q = q.filter(NurseActivityLog.nurse_id.in_(nurse_ids))
    if action_types:
        try:
            enum_list = [NurseActionType(a) for a in action_types]
            q = q.filter(NurseActivityLog.action_type.in_(enum_list))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=f"无效 action_types: {e}")

    rows = q.all()

    def clean(v) -> str:
        """清理单元格内容，避免破坏制表符结构"""
        if v is None:
            return ""
        return str(v).replace("\t", " ").replace("\r", " ").replace("\n", " ").strip()

    lines = []
    lines.append("\t".join([
        "记录ID", "护士ID", "护士姓名", "护士手机号", "最后登录时间",
        "患者ID", "患者姓名", "受试者编号",
        "操作类型", "目标日期", "房间UUID", "检测记录ID", "检测类型",
        "消息UUID", "消息类型", "聊天模式", "消息内容",
        "客户端时间", "服务端时间",
    ]))

    for log, nurse, login_code, patient in rows:
        nurse_name = f"{nurse.first_name} {nurse.last_name}".strip() if nurse else ""
        nurse_phone = nurse.phone if nurse else ""
        last_login = (
            login_code.update_time.strftime("%Y-%m-%d %H:%M:%S")
            if login_code and login_code.update_time else ""
        )
        patient_name = (
            f"{patient.first_name} {patient.last_name}".strip() if patient else ""
        )
        subject_code = patient.subject_code if patient and patient.subject_code else ""

        lines.append("\t".join([
            clean(log.id),
            clean(log.nurse_id),
            clean(nurse_name),
            clean(nurse_phone),
            clean(last_login),
            clean(log.patient_id),
            clean(patient_name),
            clean(subject_code),
            clean(log.action_type.value if log.action_type else ""),
            clean(log.target_date.isoformat() if log.target_date else ""),
            clean(log.room_uuid),
            clean(log.record_id),
            clean(log.test_type.value if log.test_type else ""),
            clean(log.message_uuid),
            clean(log.message_type.value if log.message_type else ""),
            clean(log.chat_mode),
            clean(log.content),
            clean(log.client_ts.strftime("%Y-%m-%d %H:%M:%S") if log.client_ts else ""),
            clean(log.create_time.strftime("%Y-%m-%d %H:%M:%S") if log.create_time else ""),
        ]))

    content_bytes = "\n".join(lines).encode("utf-8-sig")
    filename = f"nurse_activity_{start_date or 'all'}_{end_date or 'all'}.txt"

    return Response(
        content=content_bytes,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

# 汇总导出的表头顺序（与前端展示、CSV 顺序一致）
SUMMARY_ACTION_ORDER = [
    ("add_patient",       "添加病人"),
    ("view_chat_history", "查看对话历史"),
    ("view_test_history", "查看检测记录"),
    ("open_chat_room",    "打开聊天室"),
    ("send_chat_message", "发送聊天消息"),
    ("view_daily_report", "查看每日报告"),
]


@router.post("/export-summary", summary="导出护士操作汇总（制表符分隔，txt 文件）")
def export_nurse_activity_summary(
    payload: dict = Body(...),
    db: Session = Depends(get_db),
):
    """
    导出格式：每个护士一行。
    - 前半部分：过去一周（end_date-7 ~ end_date-1，不含当天）各操作类型次数 + 过去一周总数
    - 后半部分：导出时间段内各操作类型次数 + 时间段总次数
    制表符分隔，直接粘贴 Excel 可对齐。
    """
    start_date = payload.get("start_date")
    end_date = payload.get("end_date")
    nurse_ids = payload.get("nurse_ids") or None

    # ---------- 1. 时间段内聚合 ----------
    time_filters = []
    if start_date:
        time_filters.append(
            NurseActivityLog.create_time >= dt.fromisoformat(f"{start_date}T00:00:00")
        )
    if end_date:
        time_filters.append(
            NurseActivityLog.create_time <= dt.fromisoformat(f"{end_date}T23:59:59")
        )

    q = (
        db.query(
            NurseActivityLog.nurse_id,
            NurseActivityLog.action_type,
            func.count(NurseActivityLog.id).label("cnt"),
        )
        .filter(*time_filters)
    )
    if nurse_ids:
        q = q.filter(NurseActivityLog.nurse_id.in_(nurse_ids))
    q = q.group_by(NurseActivityLog.nurse_id, NurseActivityLog.action_type)
    rows = q.all()

    nurse_stats: dict[int, dict[str, int]] = {}
    for nid, action_type, cnt in rows:
        key = action_type.value if action_type else "unknown"
        nurse_stats.setdefault(nid, {})[key] = cnt

    # ---------- 2. 过去一周聚合（按护士 + 操作类型） ----------
    if end_date:
        base_date = date.fromisoformat(end_date)
    else:
        base_date = date.today()

    week_end_date = base_date - timedelta(days=1)
    week_start_date = week_end_date - timedelta(days=6)

    week_q = (
        db.query(
            NurseActivityLog.nurse_id,
            NurseActivityLog.action_type,
            func.count(NurseActivityLog.id).label("cnt"),
        )
        .filter(
            NurseActivityLog.create_time >= dt.fromisoformat(
                f"{week_start_date.isoformat()}T00:00:00"
            ),
            NurseActivityLog.create_time <= dt.fromisoformat(
                f"{week_end_date.isoformat()}T23:59:59"
            ),
        )
    )
    if nurse_ids:
        week_q = week_q.filter(NurseActivityLog.nurse_id.in_(nurse_ids))
    week_q = week_q.group_by(NurseActivityLog.nurse_id, NurseActivityLog.action_type)
    week_rows = week_q.all()

    week_stats: dict[int, dict[str, int]] = {}
    for nid, action_type, cnt in week_rows:
        key = action_type.value if action_type else "unknown"
        week_stats.setdefault(nid, {})[key] = cnt

    # ---------- 3. 组装表头 ----------
    week_tag = f"(过去一周 {week_start_date}~{week_end_date})"

    header = (
        ["护士ID", "护士姓名", "护士手机号", "最后登录时间"]
        # 过去一周，各操作类型
        + [f"{label}{week_tag}" for _, label in SUMMARY_ACTION_ORDER]
        + [f"总操作次数{week_tag}"]
        # 时间段内，各操作类型
        + [label for _, label in SUMMARY_ACTION_ORDER]
        + ["总操作次数"]
    )

    lines = ["\t".join(header)]

    # ---------- 4. 无数据时，只输出表头 ----------
    if not nurse_stats and not week_stats:
        content_bytes = "\n".join(lines).encode("utf-8-sig")
        filename = f"nurse_activity_summary_{start_date or 'all'}_{end_date or 'all'}.txt"
        return Response(
            content=content_bytes,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    # ---------- 5. 护士基础信息 + 最后登录时间 ----------
    all_nurse_ids = set(nurse_stats.keys()) | set(week_stats.keys())
    nurse_rows = (
        db.query(Nurse, NurseLoginCode)
        .outerjoin(NurseLoginCode, Nurse.nurse_id == NurseLoginCode.nurse_id)
        .filter(Nurse.nurse_id.in_(all_nurse_ids))
        .all()
    )

    # ---------- 6. 组装每行数据 ----------
    table_rows = []
    for nurse, login_code in nurse_rows:
        stats = nurse_stats.get(nurse.nurse_id, {})
        counts = [stats.get(key, 0) for key, _ in SUMMARY_ACTION_ORDER]
        total = sum(counts)

        w_stats = week_stats.get(nurse.nurse_id, {})
        week_counts = [w_stats.get(key, 0) for key, _ in SUMMARY_ACTION_ORDER]
        week_total = sum(week_counts)

        last_login = (
            login_code.update_time.strftime("%Y-%m-%d %H:%M:%S")
            if login_code and login_code.update_time else ""
        )

        table_rows.append([
            nurse.nurse_id,
            f"{nurse.first_name} {nurse.last_name}".strip(),
            nurse.phone,
            last_login,
            *week_counts,      # 过去一周各操作
            week_total,        # 过去一周总数
            *counts,           # 时间段各操作
            total,             # 时间段总数
        ])

    # ---------- 7. 按时间段总操作次数倒序（最后一列） ----------
    table_rows.sort(key=lambda r: r[-1], reverse=True)

    for r in table_rows:
        lines.append("\t".join(str(x) for x in r))

    content_bytes = "\n".join(lines).encode("utf-8-sig")
    filename = f"nurse_activity_summary_{start_date or 'all'}_{end_date or 'all'}.txt"
    return Response(
        content=content_bytes,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )