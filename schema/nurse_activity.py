from __future__ import annotations

from datetime import date, datetime
from typing import Any, Dict, Optional, Union

from pydantic import BaseModel, Field, field_validator


class NurseActivityLogCreate(BaseModel):
    """前端上报的护士操作日志"""

    action_type: str = Field(..., description="操作类型")
    nurse_id: Union[int, str] = Field(..., description="护士ID")
    patient_id: Optional[Union[int, str]] = Field(None, description="患者ID")
    room_uuid: Optional[str] = Field(None, description="聊天室UUID")
    target_date: Optional[str] = Field(None, description="目标日期 YYYY-MM-DD")
    record_id: Optional[Union[int, str]] = Field(None, description="检测记录ID")
    test_type: Optional[str] = Field(None, description="diabetes / CKD")
    message_uuid: Optional[str] = Field(None, description="消息UUID")
    content: Optional[str] = Field(None, description="护士发送的消息内容")
    message_type: Optional[str] = Field(None, description="text / file / voice")
    chat_mode: Optional[str] = Field(None, description="AI / assist / nurseType")
    metadata: Optional[Dict[str, Any]] = Field(None, description="额外信息")
    client_ts: Optional[str] = Field(None, description="客户端ISO时间")

    @field_validator("target_date")
    @classmethod
    def _validate_target_date(cls, v):
        if v in (None, ""):
            return None
        try:
            date.fromisoformat(v)
        except ValueError:
            raise ValueError("target_date 必须是 YYYY-MM-DD 格式")
        return v


class NurseActivityLogResponse(BaseModel):
    success: bool
    message: str
    id: Optional[int] = None