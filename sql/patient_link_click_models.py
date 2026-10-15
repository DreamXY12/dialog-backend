# 患者外链点击日志模型
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Integer, String, DateTime, Text,
    Index, ForeignKey, func
)
from sqlalchemy.orm import Mapped, mapped_column

from .people_models import Base


class PatientLinkClickLog(Base):
    """
    患者外链点击日志
    只统计"点击"这一次行为（CPC 模式），不追踪跳转后的后续行为
    """
    __tablename__ = "patient_link_click_log"

    __table_args__ = (
        Index("idx_plc_patient_time", "patient_id", "create_time"),
        Index("idx_plc_domain_time", "link_domain", "create_time"),
        Index("idx_plc_message", "message_uuid"),
        {
            "comment": "患者外链点击日志表",
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
        },
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="主键ID"
    )

    patient_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("patient.patient_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        comment="患者ID",
    )

    # 关联到具体哪条消息、哪个房间（方便追溯上下文）
    message_uuid: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, comment="消息UUID（从哪条消息点出去的）"
    )
    room_uuid: Mapped[Optional[str]] = mapped_column(
        String(36), nullable=True, comment="聊天室UUID"
    )

    # 链接本身
    link_url: Mapped[str] = mapped_column(
        Text, nullable=False, comment="完整链接"
    )
    link_domain: Mapped[str] = mapped_column(
        String(255), nullable=False, comment="链接域名（用于快速筛选 DHC 等特定域名）"
    )

    # 上下文
    chat_mode: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="点击时的聊天模式：AI/assist/nurseType"
    )

    # 环境（排查用，可空）
    user_agent: Mapped[Optional[str]] = mapped_column(
        String(500), nullable=True, comment="UA（可选，移动端/桌面端分析用）"
    )

    create_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=func.now(),
        nullable=False,
        comment="点击时间",
    )

    def __repr__(self):
        return (
            f"<PatientLinkClickLog(id={self.id}, patient_id={self.patient_id}, "
            f"domain={self.link_domain})>"
        )