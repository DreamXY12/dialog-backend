# chat_history.py
from datetime import datetime, date,timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc, func,asc
from sql.nurse_curd import get_nurse_full_name
from sql.patient_curd import get_patient_full_name

# 假设你已经有了这些导入
from sql.start import get_db
from sql.people_models import (
    ChatRoom, ConversationSession, Message, NurseWorkShift,
    Nurse, SessionStatus
)
from schema.chat_schema import (
    MessageListResponse,
    ActiveSessionResponse, UnreadCountResponse
)

from sql.chat_histoty_curd import (
    get_chat_room_by_uuid,
    get_active_session_by_room_id,
    get_or_create_patient_chat_room
)

router = APIRouter(tags=["chat-history"])


# ==================== 辅助函数 ====================
def get_current_active_session(room_uuid: str, db: Session) -> Optional[ConversationSession]:
    """获取房间的当前活跃会话"""

    result = db.query(ChatRoom).filter(ChatRoom.room_uuid == room_uuid).one_or_none()
    room_id = result.room_id

    return db.query(ConversationSession).filter(
        ConversationSession.room_id == room_id,
        ConversationSession.session_status == SessionStatus.ACTIVE
    ).order_by(desc(ConversationSession.start_time)).first()


def get_nurse_today_shift(nurse_id: int, db: Session) -> Optional[NurseWorkShift]:
    """获取护士今天的班次"""
    today = date.today()
    return db.query(NurseWorkShift).filter(
        NurseWorkShift.nurse_id == nurse_id,
        NurseWorkShift.work_date == today,
        NurseWorkShift.status.in_(['scheduled', 'active'])
    ).first()


def is_nurse_in_working_hours(nurse_id: int, db: Session) -> bool:
    """检查护士当前是否在工作时间段内"""
    shift = get_nurse_today_shift(nurse_id, db)
    if not shift:
        return False

    now = datetime.now().time()
    return shift.work_start_time <= now <= shift.work_end_time


# ==================== API接口 ====================
@router.get("/rooms/{room_uuid}/active-session")
async def get_active_session_by_uuid(
        room_uuid: str,
        db: Session = Depends(get_db)
):
    """通过room_uuid获取活跃会话"""
    # 1. 获取聊天室
    chat_room = get_chat_room_by_uuid(db, room_uuid)
    if not chat_room:
        raise HTTPException(status_code=404, detail="聊天室不存在")

    # 2. 获取活跃会话
    active_session, created = get_active_session_by_room_id(db, chat_room.room_id)

    if not active_session:
        raise HTTPException(status_code=404, detail="无法获取活跃会话")

    # 3. 构建响应
    return {
        "room_uuid": room_uuid,
        "room_id": chat_room.room_id,
        "session_uuid": active_session.session_uuid,
        "session_number": active_session.session_number,
        "status": active_session.session_status.value,
        "start_time": active_session.start_time.isoformat() if active_session.start_time else None,
        "message_count": active_session.message_count,
        "session_type": active_session.session_type.value,
        "patient_id": chat_room.patient_id,
        "nurse_id": chat_room.nurse_id
    }


@router.get("/patients/{patient_id}/chat-room-uuid")
async def get_patient_chat_room_uuid(
        patient_id: int,
        db: Session = Depends(get_db)
):
    """获取病人的聊天室UUID"""
    chat_room, created = get_or_create_patient_chat_room(db, patient_id)

    if not chat_room:
        raise HTTPException(status_code=404, detail="无法获取聊天室")

    return {
        "room_uuid": chat_room.room_uuid,
        "room_id": chat_room.room_id,
        "patient_id": chat_room.patient_id,
        "nurse_id": chat_room.nurse_id,
        "created": created
    }

#这是按照会话来分类的，可以留着，万一之后得区分对话呢？
@router.get("/sessions/{session_uuid}/messages", response_model=MessageListResponse)
async def get_session_messages(
    session_uuid: str,
    order: str = Query("desc", description="排序方式: asc-正序, desc-倒序"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(50, ge=1, le=100, description="每页数量"),
    days_limit: int = Query(3, ge=1, description="限制天数，0表示不限制"),
    reader_id: int = Query(..., description="请求者ID"),
    reader_role: str = Query(..., description="请求者角色", regex="^(patient|nurse)$"),
    db: Session = Depends(get_db)
):
    """
    获取会话的消息列表（适配独立已读模型）
    - 根据 reader_id / reader_role 动态返回 is_read
    - 支持正序(asc)和倒序(desc)排列
    - 支持限制获取天数内的消息
    """
    try:
        # 验证会话是否存在
        session = db.query(ConversationSession).filter(
            ConversationSession.session_uuid == session_uuid
        ).first()

        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")

        # 构建基础查询
        query = db.query(Message).filter(
            Message.session_uuid == session_uuid
        )

        # 如果设置了天数限制，只获取指定天数内的消息
        if days_limit > 0:
            cutoff_date = datetime.now() - timedelta(days=days_limit)
            query = query.filter(Message.create_time >= cutoff_date)

        # 计算总数
        total_count = query.count()

        # 按创建时间倒序查询
        query = query.order_by(desc(Message.create_time))

        # 分页
        offset = (page - 1) * page_size
        messages = query.offset(offset).limit(page_size).all()

        # 如果前端要求正序，反转列表
        if order.lower() == "asc":
            messages = messages[::-1]

        # 构建响应
        message_list = []
        for msg in messages:
            # 动态计算 is_read
            if reader_role == "nurse":
                msg_is_read = msg.nurse_read
            else:
                msg_is_read = msg.patient_read

            message_data = {
                "message_uuid": msg.message_uuid,
                "session_uuid": msg.session_uuid,
                "room_id": msg.room_id,  # 新增返回房间ID
                "sender_type": msg.sender_type.value,
                "sender_id": msg.sender_id,
                "content": msg.content,
                "message_type": msg.message_type.value if msg.message_type else "text",
                "file_url": msg.file_url,
                "is_read": msg_is_read,          # 动态，每个用户独立
                "patient_read": msg.patient_read, # 可选，便于调试
                "nurse_read": msg.nurse_read,     # 可选，便于调试
                "chat_mode": msg.chat_mode.value if msg.chat_mode else "AI",
                "create_time": msg.create_time.isoformat() if msg.create_time else None
            }
            message_list.append(message_data)

        return {
            "session_uuid": session_uuid,
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size,
            "messages": message_list,
            "order": order,
            "days_limit": days_limit
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取消息失败: {str(e)}")


@router.post("/messages/{message_uuid}/read")
async def mark_message_as_read(
    message_uuid: str,
    reader_id: int = Query(..., description="阅读者ID"),
    reader_role: str = Query(..., description="阅读者角色", regex="^(patient|nurse)$"),
    db: Session = Depends(get_db)
):
    """
    标记消息为已读（独立已读模型）
    - 护士阅读：更新 nurse_read = 1
    - 患者阅读：更新 patient_read = 1
    """
    try:
        message = db.query(Message).filter(Message.message_uuid == message_uuid).first()
        if not message:
            raise HTTPException(status_code=404, detail="消息不存在")

        # 按角色更新对应字段
        if reader_role == "nurse":
            message.nurse_read = True
        elif reader_role == "patient":
            message.patient_read = True
        else:
            raise HTTPException(status_code=400, detail="无效的阅读者角色")

        db.commit()

        return {
            "success": True,
            "message": "消息已标记为已读",
            "message_uuid": message_uuid,
            "reader_role": reader_role,
            "read_time": datetime.now().isoformat()  # 可选择记录时间，但表内无持久化字段，这里仅返回临时时间
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"标记已读失败: {str(e)}")


@router.get("/rooms/{room_uuid}/unread-count", response_model=UnreadCountResponse)
async def get_unread_message_count(
    room_uuid: str,
    user_id: int = Query(..., description="用户ID"),
    user_role: str = Query(..., description="用户角色", regex="^(patient|nurse)$"),
    db: Session = Depends(get_db)
):
    """
    获取房间的未读消息数（独立已读模型）
    - 根据 user_role 读取 nurse_read 或 patient_read
    - 仅统计当前活跃会话中对方/系统的未读消息
    """
    try:
        # 获取当前活跃会话（你原有的函数）
        active_session = get_current_active_session(room_uuid, db)
        if not active_session:
            return {"unread_count": 0, "room_id": room_uuid}

        # 根据用户角色确定统计哪些发送者
        if user_role == "patient":
            target_sender_types = ["nurse", "system", "ai"]
            read_column = Message.patient_read
        elif user_role == "nurse":
            target_sender_types = ["patient", "system", "ai"]
            read_column = Message.nurse_read
        else:
            return {"unread_count": 0, "room_id": room_uuid}

        # 计算未读消息数
        unread_count = db.query(func.count(Message.message_id)).join(
            ConversationSession,
            Message.session_uuid == ConversationSession.session_uuid
        ).filter(
            # 限定当前活跃会话
            Message.session_uuid == active_session.session_uuid,
            # 使用独立已读字段：未读即 read_column == False
            read_column == False,
            # 只统计目标发送者
            Message.sender_type.in_(target_sender_types),
            # 排除自己发送的消息
            Message.sender_id != user_id
        ).scalar()

        return {
            "unread_count": unread_count or 0,
            "room_uuid": room_uuid,
            "session_uuid": active_session.session_uuid
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取未读数失败: {str(e)}")


@router.get("/rooms/{room_id}/sessions")
async def get_room_sessions(
        room_id: int,
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=50, description="每页数量"),
        db: Session = Depends(get_db)
):
    """
    获取房间的历史会话列表
    - 按开始时间倒序排列
    """
    try:
        # 验证房间是否存在
        room = db.query(ChatRoom).filter(ChatRoom.room_id == room_id).first()
        if not room:
            raise HTTPException(status_code=404, detail="房间不存在")

        # 计算总数
        total_count = db.query(ConversationSession).filter(
            ConversationSession.room_id == room_id
        ).count()

        # 分页查询会话
        offset = (page - 1) * page_size
        sessions = db.query(ConversationSession).filter(
            ConversationSession.room_id == room_id
        ).order_by(desc(ConversationSession.start_time)).offset(offset).limit(page_size).all()

        # 构建响应
        session_list = []
        for session in sessions:
            session_data = {
                "session_uuid": session.session_uuid,
                "session_number": session.session_number,
                "session_type": session.session_type.value,
                "status": session.session_status.value,
                "start_time": session.start_time.isoformat() if session.start_time else None,
                "end_time": session.end_time.isoformat() if session.end_time else None,
                "message_count": session.message_count,
                "auto_end_reason": session.auto_end_reason.value if session.auto_end_reason else None
            }

            # 添加护士信息
            if session.nurse_shift_id:
                shift = db.query(NurseWorkShift).filter(
                    NurseWorkShift.shift_id == session.nurse_shift_id
                ).first()
                if shift and shift.nurse:
                    session_data["nurse_info"] = {
                        "nurse_id": shift.nurse_id,
                        "nurse_name": shift.nurse.full_name
                    }

            session_list.append(session_data)

        return {
            "room_id": room_id,
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": (total_count + page_size - 1) // page_size,
            "sessions": session_list
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取会话列表失败: {str(e)}")


@router.post("/sessions/{session_uuid}/end")
async def end_session(
        session_uuid: str,
        reason: str = Query(..., description="结束原因",
                            regex="^(manual_end|nurse_shift_end|inactivity_timeout|day_end)$"),
        db: Session = Depends(get_db)
):
    """
    手动结束会话
    """
    try:
        session = db.query(ConversationSession).filter(
            ConversationSession.session_uuid == session_uuid
        ).first()

        if not session:
            raise HTTPException(status_code=404, detail="会话不存在")

        if session.session_status == SessionStatus.COMPLETED:
            raise HTTPException(status_code=400, detail="会话已结束")

        # 更新会话状态
        session.session_status = SessionStatus.COMPLETED
        session.end_time = datetime.utcnow()
        session.auto_end_reason = reason

        # 如果关联了护士班次，更新班次统计
        if session.nurse_shift_id:
            shift = db.query(NurseWorkShift).filter(
                NurseWorkShift.shift_id == session.nurse_shift_id
            ).first()
            if shift and shift.current_session_count > 0:
                shift.current_session_count -= 1

        db.commit()

        return {
            "success": True,
            "message": "会话已结束",
            "session_uuid": session_uuid,
            "end_time": session.end_time.isoformat(),
            "reason": reason
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"结束会话失败: {str(e)}")


@router.get("/nurses/{nurse_id}/current-shift")
async def get_nurse_current_shift(
        nurse_id: int,
        db: Session = Depends(get_db)
):
    """
    获取护士当前的班次信息
    """
    try:
        nurse = db.query(Nurse).filter(Nurse.nurse_id == nurse_id).first()
        if not nurse:
            raise HTTPException(status_code=404, detail="护士不存在")

        today = date.today()
        shift = db.query(NurseWorkShift).filter(
            NurseWorkShift.nurse_id == nurse_id,
            NurseWorkShift.work_date == today
        ).order_by(desc(NurseWorkShift.create_time)).first()

        if not shift:
            return {
                "has_shift": False,
                "message": "今天没有排班"
            }

        now = datetime.now().time()
        is_working = shift.work_start_time <= now <= shift.work_end_time

        return {
            "has_shift": True,
            "shift_uuid": shift.shift_uuid,
            "work_date": shift.work_date.isoformat(),
            "work_start_time": shift.work_start_time.isoformat()[:5],  # HH:MM格式
            "work_end_time": shift.work_end_time.isoformat()[:5],
            "status": shift.status.value,
            "is_working_hours": is_working,
            "current_session_count": shift.current_session_count,
            "total_session_count": shift.total_session_count,
            "total_message_count": shift.total_message_count
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取班次信息失败: {str(e)}")


@router.post("/nurses/{nurse_id}/create-daily-shift")
async def create_daily_shift_for_nurse(
        nurse_id: int,
        work_start_time: str = Query("09:00", description="工作时间开始，格式: HH:MM"),
        work_end_time: str = Query("18:00", description="工作时间结束，格式: HH:MM"),
        db: Session = Depends(get_db)
):
    """
    为护士创建今日班次
    """
    try:
        nurse = db.query(Nurse).filter(Nurse.nurse_id == nurse_id).first()
        if not nurse:
            raise HTTPException(status_code=404, detail="护士不存在")

        today = date.today()

        # 检查是否已有今天的班次
        existing = db.query(NurseWorkShift).filter(
            NurseWorkShift.nurse_id == nurse_id,
            NurseWorkShift.work_date == today
        ).first()

        if existing:
            return {
                "success": True,
                "message": "今日班次已存在",
                "shift_uuid": existing.shift_uuid
            }

        # 解析时间
        try:
            start_time_obj = datetime.strptime(work_start_time, "%H:%M").time()
            end_time_obj = datetime.strptime(work_end_time, "%H:%M").time()
        except ValueError:
            raise HTTPException(status_code=400, detail="时间格式错误，请使用HH:MM格式")

        # 创建新班次
        new_shift = NurseWorkShift(
            nurse_id=nurse_id,
            work_date=today,
            work_start_time=start_time_obj,
            work_end_time=end_time_obj,
            status="scheduled"
        )

        db.add(new_shift)
        db.commit()
        db.refresh(new_shift)

        return {
            "success": True,
            "message": "班次创建成功",
            "shift_uuid": new_shift.shift_uuid,
            "work_date": new_shift.work_date.isoformat(),
            "work_start_time": new_shift.work_start_time.isoformat()[:5],
            "work_end_time": new_shift.work_end_time.isoformat()[:5]
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"创建班次失败: {str(e)}")


# ==================== 定时任务相关 ====================
@router.post("/tasks/end-expired-sessions")
async def end_expired_sessions(db: Session = Depends(get_db)):
    """
    结束过期的会话（供定时任务调用）
    - 超时30分钟无消息的会话
    - 昨天的活跃会话
    """
    try:
        now = datetime.utcnow()
        results = {
            "timeout_sessions": 0,
            "yesterday_sessions": 0,
            "shift_end_sessions": 0
        }

        # 1. 结束超时会话（30分钟无消息）
        timeout_threshold = now - timedelta(minutes=30)
        timeout_sessions = db.query(ConversationSession).filter(
            ConversationSession.session_status == SessionStatus.ACTIVE,
            ConversationSession.last_message_time < timeout_threshold
        ).all()

        for session in timeout_sessions:
            session.session_status = SessionStatus.COMPLETED
            session.end_time = now
            session.auto_end_reason = "inactivity_timeout"
            results["timeout_sessions"] += 1

        # 2. 结束昨天的活跃会话
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_sessions = db.query(ConversationSession).filter(
            ConversationSession.session_status == SessionStatus.ACTIVE,
            ConversationSession.start_time < today_start
        ).all()

        for session in yesterday_sessions:
            session.session_status = SessionStatus.COMPLETED
            session.end_time = now
            session.auto_end_reason = "day_end"
            results["yesterday_sessions"] += 1

        # 3. 检查护士班次是否结束，结束相关会话
        yesterday = today_start - timedelta(days=1)
        completed_shifts = db.query(NurseWorkShift).filter(
            NurseWorkShift.status == "completed",
            NurseWorkShift.work_date >= yesterday.date()
        ).all()

        for shift in completed_shifts:
            # 查找此班次的活跃会话
            shift_sessions = db.query(ConversationSession).filter(
                ConversationSession.nurse_shift_id == shift.shift_id,
                ConversationSession.session_status == SessionStatus.ACTIVE
            ).all()

            for session in shift_sessions:
                session.session_status = SessionStatus.COMPLETED
                session.end_time = now
                session.auto_end_reason = "nurse_shift_end"
                results["shift_end_sessions"] += 1

        db.commit()

        return {
            "success": True,
            "message": "过期会话清理完成",
            "results": results,
            "timestamp": now.isoformat()
        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"清理过期会话失败: {str(e)}")

@router.get("/rooms/{room_uuid}/all-messages", response_model=MessageListResponse)
async def get_room_all_messages(
    room_uuid: str,
    order: str = Query("asc", description="排序方式: asc-正序, desc-倒序"),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=200),
    days_limit: int = Query(3, ge=0),
    reader_id: int = Query(..., description="请求者ID"),
    reader_role: str = Query(..., description="请求者角色", regex="^(patient|nurse)$"),
    db: Session = Depends(get_db)
):
    """
    跨会话获取房间历史消息（独立已读模型）
    - 需要 reader_id/reader_role 动态计算 is_read
    - 消息顺序：旧 → 新（适合聊天渲染）
    """
    try:
        # 1. 获取房间
        chat_room = get_chat_room_by_uuid(db, room_uuid)
        if not chat_room:
            raise HTTPException(status_code=404, detail="聊天室不存在")

        room_id = chat_room.room_id

        # 2. 关联查询：该房间下所有会话的消息
        query = db.query(Message).join(
            ConversationSession,
            ConversationSession.session_uuid == Message.session_uuid
        ).filter(
            ConversationSession.room_id == room_id
        )

        # 3. 天数限制
        if days_limit > 0:
            cutoff_date = datetime.now() - timedelta(days=days_limit)
            query = query.filter(Message.create_time >= cutoff_date)

        total_count = query.count()

        # 4. 取最新 page_size 条（创建时间倒序）
        messages = query.order_by(desc(Message.create_time)).limit(page_size).all()

        # 5. 反转：旧消息在前，新消息在后
        messages = messages[::-1]

        # 6. 动态 is_read
        is_nurse = reader_role == "nurse"

        message_list = []
        for msg in messages:
            is_read = msg.nurse_read if is_nurse else msg.patient_read

            message_list.append({
                "message_uuid": msg.message_uuid,
                "session_uuid": msg.session_uuid,
                "room_id": msg.room_id,                     # 新增
                "sender_id": msg.sender_id,
                "sender_type": msg.sender_type.value,
                "content": msg.content,
                "chat_mode": msg.chat_mode.value if msg.chat_mode else "AI",
                "is_read": is_read,                         # 动态计算
                "create_time": msg.create_time.isoformat() if msg.create_time else None,
                "message_type": msg.message_type.value if msg.message_type else "text",
                "file_url": msg.file_url,
            })

        return {
            "session_uuid": "",          # 房间维度的请求无特定会话，返回空或房间uuid均可
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": 1,            # 可扩展
            "messages": message_list
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取房间消息失败: {str(e)}")

@router.get("/rooms/{room_uuid}/recently-messages", response_model=MessageListResponse)
async def get_room_recently_messages(
    room_uuid: str,
    order: str = Query("asc", description="排序方式: asc-正序, desc-倒序"),
    page: int = Query(1, ge=1),
    page_size: int = Query(120, ge=1, le=200),
    reader_id: int = Query(..., description="请求者ID"),
    reader_role: str = Query(..., description="请求者角色", regex="^(patient|nurse)$"),
    db: Session = Depends(get_db)
):
    """
    获取房间最新120条历史消息（跨会话，独立已读）
    - 需要 reader_id / reader_role 动态计算 is_read
    - 顺序：旧→新，前端直接渲染
    """
    try:
        # 1. 获取房间
        chat_room = get_chat_room_by_uuid(db, room_uuid)
        if not chat_room:
            raise HTTPException(status_code=404, detail="聊天室不存在")

        room_id = chat_room.room_id

        # 2. 查询该房间下所有会话的消息
        query = db.query(Message).join(
            ConversationSession,
            ConversationSession.session_uuid == Message.session_uuid
        ).filter(
            ConversationSession.room_id == room_id
        )

        total_count = query.count()

        # 3. 取最新 page_size 条（倒序）
        messages = query.order_by(desc(Message.create_time)).limit(page_size).all()

        # 4. 反转 → 旧→新
        messages = messages[::-1]

        # 5. 动态 is_read（按角色）
        is_nurse = reader_role == "nurse"

        message_list = []
        for msg in messages:
            # 计算发送者名称
            if msg.sender_type.value == "patient":
                from_name = get_patient_full_name(db, int(msg.sender_id))
            elif msg.sender_type.value == "nurse":
                from_name = get_nurse_full_name(db, int(msg.sender_id))
            elif msg.sender_type.value == "ai":
                from_name = "糖尿病AI助手"
            elif msg.sender_type.value == "system":
                from_name = "系统"
            else:
                from_name = "未知"

            # 动态已读
            is_read = msg.nurse_read if is_nurse else msg.patient_read

            message_list.append({
                "message_uuid": msg.message_uuid,
                "session_uuid": msg.session_uuid,
                "room_id": msg.room_id,                # 新增
                "sender_id": msg.sender_id,
                "sender_type": msg.sender_type.value,
                "role": msg.sender_type.value,
                "from_name": from_name,
                "content": msg.content,
                "chat_mode": msg.chat_mode.value if msg.chat_mode else "AI",
                "is_read": is_read,                    # 动态
                "create_time": msg.create_time.isoformat() if msg.create_time else None,
                "message_type": msg.message_type.value if msg.message_type else "text",
                "file_url": msg.file_url,
            })

        return {
            "session_uuid": "",
            "total_count": total_count,
            "page": page,
            "page_size": page_size,
            "total_pages": 1,
            "messages": message_list
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取房间消息失败: {str(e)}")