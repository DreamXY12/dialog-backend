# 护士操作行为日志模型
from __future__ import annotations

import enum
from datetime import datetime, date
from typing import Optional, Any, Dict

from sqlalchemy import (
    BigInteger, Integer, String, DateTime, Date, Text,
    Index, ForeignKey, Enum, func
)
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

# 复用 people_models.py 里的 Base
from .people_models import Base
from sqlalchemy.types import Date as SqlDate


# ---------------------------
# 枚举：护士操作类型
# ---------------------------
class NurseActionType(str, enum.Enum):
    ADD_PATIENT = "add_patient"                  # 添加病人
    VIEW_CHAT_HISTORY = "view_chat_history"      # 查看某病人某天的对话历史
    VIEW_TEST_HISTORY = "view_test_history"      # 查看某病人的检测记录详情
    SEND_CHAT_MESSAGE = "send_chat_message"      # 在聊天室发送消息
    VIEW_DAILY_REPORT = "view_daily_report"      # 查看某病人某天的每日报告
    OPEN_CHAT_ROOM = "open_chat_room"            # 护士进入聊天室



class NurseTestType(str, enum.Enum):
    """检测记录类型"""
    DIABETES = "diabetes"
    CKD = "CKD"


class NurseMessageType(str, enum.Enum):
    """护士发送的消息类型"""
    TEXT = "text"
    FILE = "file"
    VOICE = "voice"


# ---------------------------
# 护士操作行为日志表
# ---------------------------
class NurseActivityLog(Base):
    """
    护士操作行为日志表
    用于记录：添加病人 / 查看对话历史 / 查看检测记录 / 聊天室发消息 / 查看每日报告
    """
    __tablename__ = "nurse_activity_log"

    __table_args__ = (
        # 常用查询：按护士 + 时间
        Index("idx_nurse_time", "nurse_id", "create_time"),
        # 常用查询：按患者 + 操作类型 + 时间
        Index("idx_patient_action", "patient_id", "action_type", "create_time"),
        # 常用查询：按操作类型 + 时间（统计某个功能的整体使用频率）
        Index("idx_action_time", "action_type", "create_time"),
        {
            "comment": "护士操作行为日志表",
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
        },
    )

    # 主键
    id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment="主键ID"
    )

    # 护士
    nurse_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("nurse.nurse_id", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        comment="护士ID（外键关联nurse表）"
    )

    # 操作类型
    action_type: Mapped[NurseActionType] = mapped_column(
        Enum(NurseActionType, values_callable=lambda e: [i.value for i in e]),
        nullable=False,
        comment="操作类型：add_patient / view_chat_history / view_test_history / send_chat_message / view_daily_report"
    )

    # 患者 & 聊天室
    patient_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey("patient.patient_id", ondelete="SET NULL", onupdate="CASCADE"),
        nullable=True,
        comment="患者ID（外键关联patient表）"
    )
    room_uuid: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
        comment="聊天室UUID（聊天相关操作时记录）"
    )

    # 日期类操作
    target_date: Mapped[Optional[date]] = mapped_column(
        SqlDate,
        nullable=True,
        comment="操作针对的日期（查看对话历史/每日报告时的日期）"
    )

    # 检测记录相关
    record_id: Mapped[Optional[int]] = mapped_column(
        BigInteger,
        nullable=True,
        comment="检测记录ID（查看检测记录详情时记录）"
    )
    test_type: Mapped[Optional[NurseTestType]] = mapped_column(
        Enum(NurseTestType, values_callable=lambda e: [i.value for i in e]),
        nullable=True,
        comment="检测类型：diabetes=糖尿病 / CKD=肾病"
    )

    # 聊天消息相关
    message_uuid: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
        comment="消息UUID（发送消息时记录）"
    )
    content: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="护士发送的消息内容（仅 send_chat_message 时记录）"
    )
    message_type: Mapped[Optional[NurseMessageType]] = mapped_column(
        Enum(NurseMessageType, values_callable=lambda e: [i.value for i in e]),
        nullable=True,
        comment="消息类型：text / file / voice"
    )
    chat_mode: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="发送消息时的聊天模式：AI / assist / nurseType"
    )

    # 附加信息（注意：SQLAlchemy 里 metadata 是保留属性，所以属性名用 extra_data，列名仍叫 metadata）
    extra_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(
        "metadata",
        JSON,
        nullable=True,
        comment="额外信息（JSON，例如添加病人的 patient_ids、文件信息等）"
    )

    # 客户端时间（前端上报的 ISO 时间）
    client_ts: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
        comment="客户端上报时间"
    )

    # 服务端记录时间
    create_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=func.now(),
        nullable=False,
        comment="服务端记录时间"
    )

    def __repr__(self):
        return (
            f"<NurseActivityLog(id={self.id}, nurse_id={self.nurse_id}, "
            f"action_type={self.action_type}, patient_id={self.patient_id})>"
        )