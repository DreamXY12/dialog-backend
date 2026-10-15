from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class PatientLinkClickCreate(BaseModel):
    patient_id: int
    link_url: str
    message_uuid: Optional[str] = None
    room_uuid: Optional[str] = None
    chat_mode: Optional[str] = None
    user_agent: Optional[str] = None


class PatientLinkClickResponse(BaseModel):
    success: bool
    message: str
    id: Optional[int] = None