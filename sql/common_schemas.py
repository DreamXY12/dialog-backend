from pydantic import BaseModel
from typing import Optional, List

# 反馈用的请求
class FeedbackCreate(BaseModel):
    rating: int
    type: str
    content: str
    attachments: Optional[List[str]] = None

    role: str
    phone: str
    ai_context: Optional[str] = None
