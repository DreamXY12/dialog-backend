# 查找历史聊天相关的curd
# sql_curd.py
from typing import Optional, Tuple, Dict, Any
from sqlalchemy.orm import Session
from datetime import datetime
import uuid

from sql.people_models import (
    ChatRoom, ConversationSession, Message,
    Patient, Nurse, NurseWorkShift
)
from sql.people_models import SessionStatus, SessionType,RoomStatus


# 在 sql_curd.py 文件中添加以下函数
def is_nurse_in_working_hours(
        nurse_id: int,
        db: Session
) -> bool:
    """
    检查护士当前是否在工作时间内

    Args:
        nurse_id: 护士ID
        db: 数据库会话

    Returns:
        bool: 是否在工作时间内
    """
    try:
        from datetime import datetime, date, time

        now = datetime.now()
        today = now.date()
        current_time = now.time()

        # 1. 查找护士今天的班次
        shift = db.query(NurseWorkShift).filter(
            NurseWorkShift.nurse_id == nurse_id,
            NurseWorkShift.work_date == today,
            NurseWorkShift.status.in_(['scheduled', 'active'])  # 排班中或活跃中
        ).first()

        if not shift:
            return False  # 今天没有排班

        # 2. 检查当前时间是否在工作时间段内
        in_working_hours = shift.work_start_time <= current_time <= shift.work_end_time

        # 3. 自动更新班次状态
        if in_working_hours and shift.status == 'scheduled':
            # 进入工作时间，激活班次
            shift.status = 'active'
            db.commit()
        elif not in_working_hours and shift.status == 'active':
            # 超过工作时间，结束班次
            shift.status = 'completed'
            db.commit()

        return in_working_hours

    except Exception as e:
        print(f"检查护士工作时间失败: {str(e)}")
        return False


def get_or_create_patient_chat_room(
        db: Session,
        patient_id: int,
        create_if_not_exists: bool = True
) -> Tuple[Optional[ChatRoom], bool]:
    """
    通过病人ID获取或创建聊天室

    Args:
        db: 数据库会话
        patient_id: 病人ID
        create_if_not_exists: 如果不存在是否创建

    Returns:
        Tuple[Optional[ChatRoom], bool]: (聊天室对象, 是否新创建的)
    """
    try:
        # 1. 验证病人是否存在
        patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
        if not patient:
            return None, False

        # 2. 查找聊天室
        chat_room = db.query(ChatRoom).filter(
            ChatRoom.patient_id == patient_id
        ).first()

        created = False

        if not chat_room and create_if_not_exists:
            # 3. 创建新聊天室
            chat_room = ChatRoom(
                patient_id=patient_id,
                nurse_id=patient.assigned_nurse_id,  # 如果有分配的护士
                room_status=RoomStatus.ACTIVE,
                last_activity_time=datetime.now(),
                create_time=datetime.now()
            )
            db.add(chat_room)
            db.commit()
            db.refresh(chat_room)
            created = True

            print(f"为病人{patient_id}创建新聊天室: room_id={chat_room.room_id}, room_uuid={chat_room.room_uuid}")

        return chat_room, created

    except Exception as e:
        db.rollback()
        print(f"获取/创建病人聊天室失败: {str(e)}")
        return None, False


def get_nurse_patient_chat_room(
        db: Session,
        nurse_id: int,
        patient_id: int,
        verify_assignment: bool = True
) -> Optional[ChatRoom]:
    """
    通过护士ID和病人ID获取聊天室（验证分配关系）

    Args:
        db: 数据库会话
        nurse_id: 护士ID
        patient_id: 病人ID
        verify_assignment: 是否验证护士-病人分配关系

    Returns:
        Optional[ChatRoom]: 聊天室对象，如果无权限或不存在返回None
    """
    try:
        # 1. 验证分配关系
        if verify_assignment:
            patient = db.query(Patient).filter(
                Patient.patient_id == patient_id,
                Patient.assigned_nurse_id == nurse_id
            ).first()

            if not patient:
                print(f"护士{nurse_id}未被分配照顾病人{patient_id}")
                return None

        # 2. 获取聊天室
        chat_room = db.query(ChatRoom).filter(
            ChatRoom.patient_id == patient_id
        ).first()

        if not chat_room:
            print(f"病人{patient_id}的聊天室不存在")
            return None

        # 3. 确保聊天室的nurse_id正确（如果之前没有设置）
        if not chat_room.nurse_id:
            chat_room.nurse_id = nurse_id
            db.commit()
            db.refresh(chat_room)

        return chat_room

    except Exception as e:
        db.rollback()
        print(f"获取护士病人聊天室失败: {str(e)}")
        return None


def get_chat_room_by_uuid(
        db: Session,
        room_uuid: str
) -> Optional[ChatRoom]:
    """
    通过room_uuid获取聊天室

    Args:
        db: 数据库会话
        room_uuid: 聊天室UUID

    Returns:
        Optional[ChatRoom]: 聊天室对象
    """
    try:
        return db.query(ChatRoom).filter(
            ChatRoom.room_uuid == room_uuid
        ).first()
    except Exception as e:
        print(f"通过UUID获取聊天室失败: {str(e)}")
        return None


def get_active_session_by_room_id(
        db: Session,
        room_id: int,
        create_if_not_exists: bool = True
) -> Tuple[Optional[ConversationSession], bool]:
    """
    通过房间ID获取当前活跃会话

    Args:
        db: 数据库会话
        room_id: 聊天室ID
        create_if_not_exists: 如果不存在是否创建

    Returns:
        Tuple[Optional[ConversationSession], bool]: (会话对象, 是否新创建的)
    """
    try:
        # 1. 获取聊天室信息
        chat_room = db.query(ChatRoom).filter(ChatRoom.room_id == room_id).first()
        if not chat_room:
            return None, False

        # 2. 查找活跃会话
        active_session = db.query(ConversationSession).filter(
            ConversationSession.room_id == room_id,
            ConversationSession.session_status == SessionStatus.ACTIVE
        ).order_by(ConversationSession.start_time.desc()).first()

        created = False

        if not active_session and create_if_not_exists:
            # 3. 创建新会话
            session_number = db.query(ConversationSession).filter(
                ConversationSession.room_id == room_id
            ).count() + 1

            # 判断会话类型
            session_type = SessionType.AI_ONLY
            if chat_room.nurse_id:
                # 检查护士是否在工作时间
                if is_nurse_in_working_hours(chat_room.nurse_id, db):
                    session_type = SessionType.NURSE_ASSISTED

            active_session = ConversationSession(
                room_id=room_id,
                session_number=session_number,
                session_type=session_type,
                session_status=SessionStatus.ACTIVE,
                start_time=datetime.utcnow(),
                # 如果有护士班次，可以关联
                nurse_shift_id=None  # 这里可以根据业务逻辑设置
            )
            db.add(active_session)
            db.commit()
            db.refresh(active_session)
            created = True

            # 更新聊天室的当前会话UUID
            chat_room.current_session_uuid = active_session.session_uuid
            db.commit()

            print(f"为房间{room_id}创建新会话: session_uuid={active_session.session_uuid}")

        return active_session, created

    except Exception as e:
        db.rollback()
        print(f"获取/创建活跃会话失败: {str(e)}")
        return None, False


def get_or_create_message(
    db: Session,
    room_id: int,               # 🔥 新增：聊天室ID
    session_uuid: str,
    sender_type: str,
    sender_id: int,
    content: str,
    chat_mode: str = "AI",
    temp_id: Optional[str] = None
) -> Tuple[Optional[Message], bool]:
    """
    创建消息记录（适配新 Message 模型）

    Args:
        db: 数据库会话
        room_id: 聊天室ID（必填）
        session_uuid: 会话UUID
        sender_type: 发送者类型
        sender_id: 发送者ID
        content: 消息内容
        chat_mode: 聊天模式
        temp_id: 临时ID（用于更新已存在的临时消息）

    Returns:
        Tuple[Optional[Message], bool]: (消息对象, 是否新创建的)
    """
    try:

        # 如果有temp_id，尝试查找（加上 room_id 防误匹配）
        if temp_id:
            message = db.query(Message).filter(
                Message.room_id == room_id,          # 只在本房间查找
                Message.session_uuid == session_uuid,
                Message.content.like(f"%{temp_id}%")
            ).first()

            if message:
                # 更新现有消息
                message.content = content
                message.chat_mode = chat_mode       # 枚举赋值，可自动转换
                db.commit()
                return message, False

        # 创建新消息
        message_uuid = str(uuid.uuid4())
        message = Message(
            message_uuid=message_uuid,
            room_id=room_id,                        # 必填
            session_uuid=session_uuid,
            sender_type=sender_type,                # 枚举值，直接给字符串也可以，SQLAlchemy会自动转
            sender_id=sender_id,
            content=content,
            chat_mode=chat_mode,
            # patient_read / nurse_read 默认 False，无需显式设置
            create_time=datetime.now()
        )
        db.add(message)

        # 更新会话的消息计数
        session = db.query(ConversationSession).filter(
            ConversationSession.session_uuid == session_uuid
        ).first()
        if session:
            session.message_count += 1
            session.last_message_time = datetime.utcnow()

        db.commit()
        db.refresh(message)

        return message, True

    except Exception as e:
        db.rollback()
        print(f"创建消息失败: {str(e)}")
        return None, False


def update_message_read_status(
        db: Session,
        message_uuid: str,
        reader_id: int,
        reader_role: str
) -> bool:
    """
    更新消息已读状态（独立已读模型）
    - 护士阅读 → nurse_read = True
    - 患者阅读 → patient_read = True
    """
    try:
        message = db.query(Message).filter(Message.message_uuid == message_uuid).first()
        if not message:
            return False

        if reader_role == "nurse":
            message.nurse_read = True
            print("护士已看，标记已读")
        elif reader_role == "patient":
            message.patient_read = True
            print("病人已看，标记已读")
        else:
            return False

        db.commit()
        return True

    except Exception as e:
        db.rollback()
        print(f"更新消息已读状态失败: {str(e)}")
        return False


def get_unread_messages_count(
        db: Session,
        room_id: int,
        user_id: int,
        user_role: str
) -> int:
    """
    获取未读消息数量（独立已读模型）

    Args:
        db: 数据库会话
        room_id: 房间ID
        user_id: 用户ID
        user_role: 用户角色 (patient / nurse)

    Returns:
        int: 未读消息数量
    """
    try:
        from sqlalchemy import func

        # 获取当前活跃会话
        active_session = get_active_session_by_room_id(db, room_id, False)[0]
        if not active_session:
            return 0

        # 根据用户角色确定对方类型和已读字段
        if user_role == "patient":
            target_sender_types = ["nurse", "ai", "system"]   # 包含 AI 和系统（可按需去掉 system）
            read_column = Message.patient_read
        elif user_role == "nurse":
            target_sender_types = ["patient", "ai", "system"]
            read_column = Message.nurse_read
        else:
            return 0

        # 计算未读消息数
        count = db.query(func.count(Message.message_id)).filter(
            Message.room_id == room_id,
            Message.session_uuid == active_session.session_uuid,
            read_column == False,                              # 尚未被当前角色读取
            Message.sender_type.in_(target_sender_types),
            Message.sender_id != user_id                      # 排除自己发送的消息
        ).scalar()

        return count or 0

    except Exception as e:
        print(f"获取未读消息数失败: {str(e)}")
        return 0


def get_chat_room_info(
        db: Session,
        room_id: Optional[int] = None,
        room_uuid: Optional[str] = None,
        patient_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """
    获取聊天室详细信息

    Args:
        db: 数据库会话
        room_id: 房间ID（可选）
        room_uuid: 房间UUID（可选）
        patient_id: 病人ID（可选）

    Returns:
        Optional[Dict]: 聊天室信息字典
    """
    try:
        query = db.query(ChatRoom)

        if room_id:
            query = query.filter(ChatRoom.room_id == room_id)
        elif room_uuid:
            query = query.filter(ChatRoom.room_uuid == room_uuid)
        elif patient_id:
            query = query.filter(ChatRoom.patient_id == patient_id)
        else:
            return None

        chat_room = query.first()
        if not chat_room:
            return None

        # 获取病人信息
        patient = db.query(Patient).filter(
            Patient.patient_id == chat_room.patient_id
        ).first()

        # 获取护士信息
        nurse = None
        if chat_room.nurse_id:
            nurse = db.query(Nurse).filter(Nurse.nurse_id == chat_room.nurse_id).first()

        # 获取活跃会话
        active_session = get_active_session_by_room_id(db, chat_room.room_id, False)[0]

        # 获取未读消息数
        unread_patient = get_unread_messages_count(db, chat_room.room_id, chat_room.patient_id, "patient")
        unread_nurse = 0
        if chat_room.nurse_id:
            unread_nurse = get_unread_messages_count(db, chat_room.room_id, chat_room.nurse_id, "nurse")

        return {
            "room_id": chat_room.room_id,
            "room_uuid": chat_room.room_uuid,
            "patient_id": chat_room.patient_id,
            "patient_name": f"{patient.first_name} {patient.last_name}" if patient else None,
            "patient_phone": patient.phone if patient else None,
            "nurse_id": chat_room.nurse_id,
            "nurse_name": f"{nurse.first_name} {nurse.last_name}" if nurse else None,
            "room_status": chat_room.room_status,
            "last_activity_time": chat_room.last_activity_time,
            "current_session_uuid": chat_room.current_session_uuid,
            "active_session": {
                "session_uuid": active_session.session_uuid if active_session else None,
                "session_number": active_session.session_number if active_session else None,
                "message_count": active_session.message_count if active_session else 0
            },
            "unread_counts": {
                "patient": unread_patient,
                "nurse": unread_nurse
            },
            "create_time": chat_room.create_time
        }

    except Exception as e:
        print(f"获取聊天室信息失败: {str(e)}")
        return None


def get_room_uuid_by_id(
        db: Session,
        patient_id: Optional[int] = None,
        nurse_id: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """
    通过患者ID / 护士ID获取聊天室UUID（room_uuid）
    - 传patient_id：返回该患者唯一的聊天室信息（一对一）
    - 传nurse_id：返回该护士关联的所有患者聊天室列表（一对多）
    - 两个参数不能同时为空
    Args:
        db: 数据库会话
        patient_id: 患者ID（可选）
        nurse_id: 护士ID（可选）
    Returns:
        传patient_id → dict(room_id, room_uuid, nurse_id) | None
        传nurse_id → list[dict(room_id, room_uuid, patient_id)] | None
    """
    try:
        # 校验参数：至少传一个ID
        if not patient_id and not nurse_id:
            print("错误：必须传入patient_id或nurse_id")
            return None

        query = db.query(ChatRoom)
        # 按患者ID查询（一对一，患者唯一对应一个聊天室）
        if patient_id:
            chat_room = query.filter(ChatRoom.patient_id == patient_id).first()
            if not chat_room:
                print(f"患者{patient_id}未创建聊天室")
                return None
            return {
                "room_id": chat_room.room_id,
                "room_uuid": chat_room.room_uuid,
                "nurse_id": chat_room.nurse_id  # 关联的护士ID
            }

        # 按护士ID查询（一对多，护士对应多个患者聊天室）
        if nurse_id:
            chat_rooms = query.filter(
                ChatRoom.nurse_id == nurse_id,
                ChatRoom.room_status == RoomStatus.ACTIVE  # 只查活跃的聊天室
            ).all()
            if not chat_rooms:
                print(f"护士{nurse_id}暂无关联的患者聊天室")
                return []
            return [
                {
                    "room_id": cr.room_id,
                    "room_uuid": cr.room_uuid,
                    "patient_id": cr.patient_id  # 关联的患者ID
                }
                for cr in chat_rooms
            ]

    except Exception as e:
        print(f"通过ID获取room_uuid失败: {str(e)}")
        return None
