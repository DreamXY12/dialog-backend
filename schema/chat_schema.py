# schemas/chat.py
from pydantic import BaseModel
from typing import Optional, List

class SessionInfo(BaseModel):
    session_uuid: str
    session_number: int
    status: str
    start_time: Optional[str]
    message_count: int
    session_type: str
    nurse_shift_info: Optional[dict] = None

    class Config:
        from_attributes = True


class MessageDetail(BaseModel):
    message_uuid: str
    session_uuid: str
    sender_type: str
    sender_id: int
    content: Optional[str]
    message_type: str = "text"
    file_url: Optional[str] = None
    is_read: bool = False
    read_time: Optional[str] = None
    read_by_user_id: Optional[int] = None
    read_by_role: Optional[str] = None
    chat_mode: str = "AI"
    create_time: str

    class Config:
        from_attributes = True


class MessageListResponse(BaseModel):
    session_uuid: str
    total_count: int
    page: int
    page_size: int
    total_pages: int
    messages: List[MessageDetail]


class ActiveSessionResponse(BaseModel):
    session_uuid: str
    session_number: int
    status: str
    start_time: Optional[str]
    message_count: int
    session_type: str
    nurse_shift_info: Optional[dict] = None


class UnreadCountResponse(BaseModel):
    unread_count: int
    room_id: int
    session_uuid: Optional[str] = None