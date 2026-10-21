# 护士查看患者 AI 对话总结日志模型
from __future__ import annotations

from datetime import datetime, date

from sqlalchemy import (
    BigInteger, Integer, String, DateTime, Date, Text,
    Index, ForeignKey, func
)
from sqlalchemy.orm import Mapped, mapped_column

from .people_models import Base


class NurseAiSummaryLog(Base):
    """
    护士查看患者 AI 对话总结记录表
    每次护士点开"AI 总结"（含缓存命中）都会写一条
    """
    __tablename__ = "nurse_ai_summary_log"

    __table_args__ = (
        Index("idx_nas_patient_time", "patient_id", "create_time"),
        Index("idx_nas_nurse_time", "nurse_id", "create_time"),
        {
            "comment": "护士查看患者 AI 对话总结记录表",
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
        },
    )

    id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True, comment="主键ID"
    )

    # ---------- 患者 ----------
    patient_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("patient.patient_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        comment="患者ID",
    )
    patient_name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="患者姓名（快照，防止改名后追溯困难）"
    )

    # ---------- 护士 ----------
    nurse_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("nurse.nurse_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        comment="护士ID",
    )
    nurse_name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="护士姓名（快照）"
    )

    # ---------- 总结范围 ----------
    start_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="总结起始日期"
    )
    end_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="总结结束日期"
    )
    message_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="本次统计到的对话条数（作为分母）"
    )

    # ---------- 总结内容 ----------
    summary_content: Mapped[str] = mapped_column(
        Text, nullable=False, comment="AI 生成的总结内容"
    )
    from_cache: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0,
        comment="是否命中缓存：0=实时生成，1=缓存命中",
    )

    # ---------- 记录时间 ----------
    create_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=func.now(),
        nullable=False,
        comment="记录时间",
    )

    def __repr__(self):
        return (
            f"<NurseAiSummaryLog(id={self.id}, patient_id={self.patient_id}, "
            f"nurse_id={self.nurse_id}, {self.start_date}~{self.end_date})>"
        )