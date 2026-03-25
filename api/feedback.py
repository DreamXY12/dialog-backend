from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sql.common_model import Feedback
from sql.common_schemas import FeedbackCreate
import json
from sql.start import get_db

router = APIRouter(tags=["feedback"])

@router.post("/feedback")
def create_feedback(data: FeedbackCreate, db: Session = Depends(get_db)):
    feedback = Feedback(
        rating=data.rating,
        type=data.type,
        content=data.content,
        attachments=json.dumps(data.attachments) if data.attachments else None,
        role=data.role,
        phone=data.phone,
        ai_context=data.ai_context
    )

    db.add(feedback)
    db.commit()
    db.refresh(feedback)

    return {"msg": "success"}