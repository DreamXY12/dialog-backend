from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc, and_
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel
from sqlalchemy import desc
from sql.common_model import Feedback

from sql.start import get_db
from sql.people_models import (
    Patient, Nurse, ChatRoom, ConversationSession,
    Message, PatientLoginCode, NurseWorkShift
)
from sql.chat_histoty_curd import get_chat_room_by_uuid

# 导入 Redis 客户端（复用 chat_socket 中的实例）
from api import chat_server
import asyncio

router = APIRouter(prefix="/polyu/dialog/admin", tags=["admin"])

# ---------- 响应模型（可选，用于 swagger 文档） ----------
class OnlineUserResponse(BaseModel):
    user_id: str
    role: str

class NurseInfo(BaseModel):
    nurse_id: int
    phone: str
    full_name: str
    is_online: bool
    patient_count: int
    work_start: Optional[str]
    work_end: Optional[str]
    is_working_now: bool

class PatientInfo(BaseModel):
    patient_id: int
    phone: str
    full_name: str
    is_online: bool
    last_login: Optional[datetime]
    assigned_nurse_id: Optional[int]
    assigned_nurse_name: Optional[str]

class MessageResponse(BaseModel):
    message_uuid: str
    sender_type: str
    sender_id: int
    content: str
    create_time: datetime
    chat_mode: str

class RoomInfo(BaseModel):
    room_uuid: str
    patient_id: int
    nurse_id: Optional[int]
    current_session_uuid: Optional[str]
    current_session_number: Optional[int]
    last_activity_time: Optional[datetime]

# ---------- 辅助函数 ----------
async def get_online_users() -> dict:
    """获取所有在线用户的 user_id -> role 映射"""
    online = {}
    all_users = await chat_server.redis.hgetall(chat_server.REDIS_ONLINE_USER)  # {user_id: sid}
    for uid, _ in all_users.items():
        role = await chat_server.redis.hget(f"chat:user_role", uid)  # 注意：key 与代码一致
        online[uid] = role or "unknown"
    return online

# ---------- 接口实现 ----------
@router.get("/online-users", response_model=List[OnlineUserResponse])
async def list_online_users():
    """获取当前所有在线用户（护士 + 患者）"""
    online = await get_online_users()
    return [{"user_id": uid, "role": role} for uid, role in online.items()]

@router.get("/nurses", response_model=List[NurseInfo])
async def list_nurses(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """分页获取护士列表，含在线状态、患者数量、工作时段"""
    offset = (page - 1) * size
    nurses = db.query(Nurse).offset(offset).limit(size).all()
    online_map = await get_online_users()

    result = []
    for nurse in nurses:
        nurse_id = str(nurse.nurse_id)
        # 患者数量
        patient_count = db.query(Patient).filter(Patient.assigned_nurse_id == nurse.nurse_id).count()
        # 工作时段（取当天有效的一条，简化：取第一条）
        shift = db.query(NurseWorkShift).filter(
            NurseWorkShift.nurse_id == nurse.nurse_id,
            NurseWorkShift.work_date == datetime.now().date()
        ).first()
        work_start = shift.work_start_time.strftime("%H:%M") if shift and shift.work_start_time else None
        work_end = shift.work_end_time.strftime("%H:%M") if shift and shift.work_end_time else None
        # 是否在值班（假设 working_hours 字段）
        is_working_now = shift.is_working_hours if shift else False

        result.append({
            "nurse_id": nurse.nurse_id,
            "phone": nurse.phone,
            "full_name": nurse.full_name,
            "is_online": nurse_id in online_map,
            "patient_count": patient_count,
            "work_start": work_start,
            "work_end": work_end,
            "is_working_now": is_working_now,
        })
    return result

@router.get("/patients", response_model=List[PatientInfo])
async def list_patients(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """分页获取患者列表，含在线状态、最后登录时间、负责护士"""
    offset = (page - 1) * size
    patients = db.query(Patient).offset(offset).limit(size).all()
    online_map = await get_online_users()
    # 预查询最后登录时间（从 PatientLoginCode）
    login_codes = {
        pc.patient_id: pc.update_time
        for pc in db.query(PatientLoginCode).filter(PatientLoginCode.patient_id.in_([p.patient_id for p in patients])).all()
    }

    result = []
    for patient in patients:
        pid = str(patient.patient_id)
        nurse_name = None
        if patient.assigned_nurse_id:
            nurse = db.query(Nurse).filter(Nurse.nurse_id == patient.assigned_nurse_id).first()
            nurse_name = nurse.full_name if nurse else None

        result.append({
            "patient_id": patient.patient_id,
            "phone": patient.phone,
            "full_name": patient.full_name,
            "is_online": pid in online_map,
            "last_login": login_codes.get(patient.patient_id),
            "assigned_nurse_id": patient.assigned_nurse_id,
            "assigned_nurse_name": nurse_name,
        })
    return result

@router.get("/patients/{patient_id}/messages", response_model=List[MessageResponse])
async def get_patient_messages(
    patient_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """分页获取指定患者的聊天消息（按时间倒序）"""
    # 先找到该患者的所有房间
    rooms = db.query(ChatRoom).filter(ChatRoom.patient_id == patient_id).all()
    if not rooms:
        return []
    room_ids = [r.room_id for r in rooms]
    # 获取消息
    offset = (page - 1) * size
    messages = (
        db.query(Message)
        .filter(Message.room_id.in_(room_ids))
        .order_by(desc(Message.create_time))
        .offset(offset)
        .limit(size)
        .all()
    )
    return [
        {
            "message_uuid": m.message_uuid,
            "sender_type": m.sender_type,
            "sender_id": m.sender_id,
            "content": m.content,
            "create_time": m.create_time,
            "chat_mode": m.chat_mode,
        }
        for m in messages
    ]

@router.get("/rooms", response_model=List[RoomInfo])
async def list_rooms(
    db: Session = Depends(get_db)
):
    """列出所有聊天房间，含当前活跃会话信息"""
    rooms = db.query(ChatRoom).all()
    result = []
    for room in rooms:
        # 获取当前活跃会话（如果有）
        active_session = (
            db.query(ConversationSession)
            .filter(
                ConversationSession.room_id == room.room_id,
                ConversationSession.session_status == "active"
            )
            .order_by(desc(ConversationSession.start_time))
            .first()
        )
        result.append({
            "room_uuid": room.room_uuid,
            "patient_id": room.patient_id,
            "nurse_id": room.nurse_id,
            "current_session_uuid": active_session.session_uuid if active_session else None,
            "current_session_number": active_session.session_number if active_session else None,
            "last_activity_time": room.last_activity_time,
        })
    return result

@router.get("/nurses/{nurse_id}/patients", response_model=List[PatientInfo])
async def get_nurse_patients(
    nurse_id: int,
    db: Session = Depends(get_db)
):
    """获取指定护士负责的所有患者（含在线状态）"""
    patients = db.query(Patient).filter(Patient.assigned_nurse_id == nurse_id).all()
    online_map = await get_online_users()
    login_codes = {
        pc.patient_id: pc.update_time
        for pc in db.query(PatientLoginCode).filter(PatientLoginCode.patient_id.in_([p.patient_id for p in patients])).all()
    }
    result = []
    for p in patients:
        result.append({
            "patient_id": p.patient_id,
            "phone": p.phone,
            "full_name": p.full_name,
            "is_online": str(p.patient_id) in online_map,
            "last_login": login_codes.get(p.patient_id),
            "assigned_nurse_id": p.assigned_nurse_id,
            "assigned_nurse_name": None,  # 可忽略或查询
        })
    return result

@router.get("/feedbacks", response_model=dict)
async def get_feedbacks(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    获取用户反馈列表（分页）
    - 按创建时间倒序
    - 返回总条数、当前页数据
    """
    offset = (page - 1) * size
    total = db.query(Feedback).count()
    feedbacks = (
        db.query(Feedback)
        .order_by(desc(Feedback.create_time))
        .offset(offset)
        .limit(size)
        .all()
    )
    return {
        "total": total,
        "page": page,
        "size": size,
        "data": [
            {
                "id": f.id,
                "rating": f.rating,
                "type": f.type,
                "content": f.content,
                "attachments": f.attachments,      # 原样返回 JSON 字符串
                "role": f.role,
                "phone": f.phone,
                "ai_context": f.ai_context,
                "create_time": f.create_time.isoformat() if f.create_time else None,
            }
            for f in feedbacks
        ]
    }


@router.get("/feedbacks/{feedback_id}/user")
async def get_feedback_user(
        feedback_id: int,
        db: Session = Depends(get_db)
):
    """
    根据反馈ID获取对应的用户信息（姓名、电话、角色）
    仅在管理员点击查看详情时调用
    """
    feedback = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="反馈不存在")

    name = None
    if feedback.role == "nurse":
        nurse = db.query(Nurse).filter(Nurse.phone == feedback.phone).first()
        if nurse:
            name = nurse.full_name
    elif feedback.role == "patient":
        patient = db.query(Patient).filter(Patient.phone == feedback.phone).first()
        if patient:
            name = patient.full_name

    return {
        "phone": feedback.phone,
        "role": feedback.role,
        "name": name
    }