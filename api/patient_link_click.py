from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from sql.start import get_db
from sql.people_models import Patient
from sql.patient_link_click_models import PatientLinkClickLog
from schema.patient_link_click import (
    PatientLinkClickCreate,
    PatientLinkClickResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/patient-link-click", tags=["患者外链点击日志"])

# 若只想统计特定域名（比如 DHC），在这里加白名单；
# 留空表示记录所有外链点击。
TRACKED_DOMAINS_WHITELIST: list[str] = [
    # "dhc.com.hk",
    # "www.dhc.net",
]


def _extract_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        return (parsed.netloc or "").lower()
    except Exception:
        return ""


def _to_int(v) -> Optional[int]:
    if v is None or v == "":
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


@router.post(
    "/log",
    response_model=PatientLinkClickResponse,
    summary="记录患者点击外链一次",
)
def log_patient_link_click(
    payload: PatientLinkClickCreate,
    db: Session = Depends(get_db),
):
    """
    前端每次点击外链调用一次。
    失败不阻塞前端跳转（返回 200 + success=False）。
    """
    patient_id = _to_int(payload.patient_id)
    if not patient_id:
        raise HTTPException(status_code=400, detail="patient_id 无效")

    if not payload.link_url:
        raise HTTPException(status_code=400, detail="link_url 不能为空")

    domain = _extract_domain(payload.link_url)
    if not domain:
        raise HTTPException(status_code=400, detail="无法解析链接域名")

    # 域名白名单过滤（若配置了白名单）
    if TRACKED_DOMAINS_WHITELIST:
        if not any(domain.endswith(d) for d in TRACKED_DOMAINS_WHITELIST):
            # 不在白名单内的链接点击，不记录，直接返回成功
            return PatientLinkClickResponse(
                success=True, message="不在追踪范围内，已忽略"
            )

    # 患者是否存在（不存在也不阻塞，只记日志）
    patient_exists = db.query(Patient.patient_id).filter(
        Patient.patient_id == patient_id
    ).first()
    if not patient_exists:
        logger.warning(
            "patient_link_click: patient_id=%s 不存在，跳过记录", patient_id
        )
        return PatientLinkClickResponse(success=False, message="患者不存在")

    try:
        row = PatientLinkClickLog(
            patient_id=patient_id,
            message_uuid=payload.message_uuid,
            room_uuid=payload.room_uuid,
            link_url=payload.link_url,
            link_domain=domain,
            chat_mode=payload.chat_mode,
            user_agent=payload.user_agent,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return PatientLinkClickResponse(success=True, message="记录成功", id=row.id)
    except Exception as e:
        db.rollback()
        logger.exception("patient_link_click 写入失败: %s", e)
        return PatientLinkClickResponse(success=False, message="记录失败")


@router.get("/stats", summary="按域名统计点击次数")
def stats_link_click(
    patient_id: Optional[int] = Query(None),
    start_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    end_date: Optional[str] = Query(None, description="YYYY-MM-DD"),
    db: Session = Depends(get_db),
):
    """
    汇总用：每个域名被点了多少次。
    前端 admin 页面可以拿这个展示。
    """
    from datetime import datetime as dt

    filters = []
    if patient_id:
        filters.append(PatientLinkClickLog.patient_id == patient_id)
    if start_date:
        filters.append(
            PatientLinkClickLog.create_time >= dt.fromisoformat(f"{start_date}T00:00:00")
        )
    if end_date:
        filters.append(
            PatientLinkClickLog.create_time <= dt.fromisoformat(f"{end_date}T23:59:59")
        )

    total = db.query(func.count(PatientLinkClickLog.id)).filter(*filters).scalar() or 0

    by_domain = (
        db.query(
            PatientLinkClickLog.link_domain,
            func.count(PatientLinkClickLog.id).label("cnt"),
        )
        .filter(*filters)
        .group_by(PatientLinkClickLog.link_domain)
        .order_by(func.count(PatientLinkClickLog.id).desc())
        .all()
    )

    return {
        "total": total,
        "by_domain": [{"domain": d, "count": c} for d, c in by_domain],
    }