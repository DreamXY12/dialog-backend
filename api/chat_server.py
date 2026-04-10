import socketio
from fastapi import FastAPI
import uuid
import time
import asyncio
from sqlalchemy.orm import Session
# 导入数据模型
from sql.start import get_db
from sql.people_models import Message, ConversationSession, ChatRoom, NurseWorkShift
from sql.people_models import SenderType, ChatMode, SessionStatus, SessionType
from typing import Optional
from datetime import datetime
from typing import Dict,List
from sql.chat_histoty_curd import get_room_uuid_by_id

from sql.chat_histoty_curd import (
    get_or_create_patient_chat_room,
    get_nurse_patient_chat_room,
    get_active_session_by_room_id,
    get_chat_room_by_uuid,
    get_or_create_message,
    update_message_read_status
)

# =========================
# 会话超时配置（可灵活修改）
# =========================
SESSION_TIMEOUT_HOURS = 4  # 会话超时时间：小时

# 1. 创建 Socket.IO 异步服务
sio = socketio.AsyncServer(
    cors_allowed_origins="https://dialog.polyusn.com",        # 允许所有来源
    async_mode="asgi",
    cors_credentials=True,
    allow_headers=["*"],             # 允许所有头
    supports_credentials=True,       # 关键：允许跨域凭证
    max_http_buffer_size=1e8,
)

# 在线用户
online_users = {}  # user_id -> sid
# 维护用户角色映射 {user_id:role} (护士/患者)
user_roles:Dict[str,str]={}
# 房间信息
rooms = {}
# room_id -> {
#   "patient": None,
#   "nurse": None,
#   "ai_enabled": True,
#   "ai_task": None,    # 新增：保存当前AI流式任务
#   "abort_ai": False   # 新增：AI终止开关
# }

HUMAN_ROLES = ["patient", "nurse"]

# =========================
# 辅助函数
# =========================
def get_current_active_session(room_id: str, db: Session) -> Optional[ConversationSession]:
    """获取房间的当前活跃会话（自动处理超时）"""
    # 1. 查询当前活跃会话
    session = db.query(ConversationSession).filter(
        ConversationSession.room_id == int(room_id),
        ConversationSession.session_status == SessionStatus.ACTIVE
    ).order_by(ConversationSession.start_time.desc()).first()

    # 2. 如果没有会话 → 返回空
    if not session:
        return None

    # 3. 检查是否超时
    if check_session_timeout(session):
        # 超时：关闭旧会话
        close_expired_session(session, db)
        print(f"会话已超时({SESSION_TIMEOUT_HOURS}小时)，已自动关闭: {session.session_uuid}")
        return None

    # 4. 没超时 → 返回原会话
    return session

async def create_new_session(room_id: str, user_id: str, role: str, db: Session) -> ConversationSession:
    """创建新会话"""
    # 获取房间信息
    room = db.query(ChatRoom).filter(ChatRoom.room_id == int(room_id)).first()
    if not room:
        # 如果房间不存在，创建临时会话
        session_number = 1
    else:
        # 计算会话序号
        session_count = db.query(ConversationSession).filter(
            ConversationSession.room_id == int(room_id)
        ).count()
        session_number = session_count + 1

        # 检查护士是否在工作时间
        nurse_shift_id = None
        session_type = SessionType.AI_ONLY

        if room.nurse_id and room.current_shift_id:
            shift = db.query(NurseWorkShift).filter(
                NurseWorkShift.shift_id == room.current_shift_id
            ).first()
            if shift and shift.is_working_hours:
                nurse_shift_id = shift.shift_id
                session_type = SessionType.NURSE_ASSISTED

    # 创建新会话
    new_session = ConversationSession(
        room_id=int(room_id),
        session_number=session_number,
        session_type=session_type,
        session_status=SessionStatus.ACTIVE,
        start_time=datetime.now(),
        nurse_shift_id=nurse_shift_id
    )

    db.add(new_session)
    db.commit()
    db.refresh(new_session)

    return new_session

def check_session_timeout(session: ConversationSession) -> bool:
    """
    检查会话是否超时
    返回 True = 已超时，需要创建新会话
    """
    if not session or not session.start_time:
        return True

    # 计算超时时间
    timeout_seconds = SESSION_TIMEOUT_HOURS * 3600
    elapsed = (datetime.now() - session.start_time).total_seconds()
    return elapsed > timeout_seconds


def close_expired_session(session: ConversationSession, db: Session):
    """关闭超时的会话"""
    if not session:
        return
    session.session_status = SessionStatus.COMPLETED  # 标记结束
    session.end_time = datetime.now()
    db.commit()

def role_to_sender_type(role: str) -> str:
    """前端role转换为数据库sender_type"""
    if role == "patient":
        return "patient"
    elif role == "nurse":
        return "nurse"
    elif role == "ai":
        return "ai"
    elif role == "system":
        return "system"
    else:
        return "system"

# 工具函数1：根据患者ID查询对应护士ID（从数据库ChatRoom/Patient表查，复用你现有curd）
async def get_patient_nurse_id(patient_id: str, db) -> str:
    """获取患者分配的护士ID，无则返回空"""
    chat_room = get_room_uuid_by_id(db, patient_id=int(patient_id))
    return str(chat_room["nurse_id"]) if chat_room and chat_room["nurse_id"] else ""

# 工具函数2：根据护士ID查询关联的所有患者ID（复用你现有curd）
async def get_nurse_patient_ids(nurse_id: str, db) -> List[str]:
    """获取护士关联的所有患者ID列表"""
    chat_rooms = get_room_uuid_by_id(db, nurse_id=int(nurse_id))
    return [str(cr["patient_id"]) for cr in chat_rooms] if chat_rooms else []

# =========================
# ✅ 连接
# =========================
@sio.event
async def connect(sid, environ, auth):
    if not auth:
        return  # 无认证拒绝连接
    user_id = str(auth.get("user_id"))
    role = auth.get("role")
    if not user_id or not role or role not in ["nurse", "patient"]:
        return  # 无ID/角色/角色错误拒绝连接

    # 记录在线用户+角色
    online_users[user_id] = sid
    user_roles[user_id] = role
    print(f"{role} {user_id} 上线，SID: {sid}")

    # 获取数据库会话，触发上线广播
    db: Session = next(get_db())
    await broadcast_online_status(user_id, role, online=True, db=db)
    db.close()

@sio.event
async def join_room(sid, data):
    user_id = data["user_id"]
    role = data["role"]
    target_patient_id = data.get("target_patient_id")

    db: Session = next(get_db())
    try:
        if role == "patient":
            # 病人：获取或创建自己的聊天室
            patient_id = int(user_id)
            chat_room, created = get_or_create_patient_chat_room(db, patient_id)

            if not chat_room:
                raise Exception("无法获取或创建聊天室")

            room_uuid = chat_room.room_uuid

            # 记录病人socket连接
            if room_uuid not in rooms:
                rooms[room_uuid] = {
                    "patient_sid": sid,
                    "patient_id": patient_id,
                    "nurse_sid": None,
                    "nurse_id": None,
                    "ai_enabled": True,
                    "ai_task": None,
                    "abort_ai": False
                }
            else:
                rooms[room_uuid]["patient_sid"] = sid
                rooms[room_uuid]["patient_id"] = patient_id

        elif role == "nurse":
            if not target_patient_id:
                raise Exception("护士必须指定病人ID")

            nurse_id = int(user_id)
            patient_id = int(target_patient_id)

            # 获取护士-病人聊天室（会自动验证分配关系）
            chat_room = get_nurse_patient_chat_room(
                db, nurse_id, patient_id, verify_assignment=True
            )

            if not chat_room:
                raise Exception("您未被分配照顾此病人")

            room_uuid = chat_room.room_uuid

            # 记录护士socket连接
            if room_uuid not in rooms:
                rooms[room_uuid] = {
                    "patient_sid": None,
                    "patient_id": patient_id,
                    "nurse_sid": sid,
                    "nurse_id": nurse_id,
                    "ai_enabled": True,
                    "ai_task": None,
                    "abort_ai": False
                }
            else:
                rooms[room_uuid]["nurse_sid"] = sid
                rooms[room_uuid]["nurse_id"] = nurse_id

        else:
            raise Exception(f"未知角色: {role}")

        # 获取或创建活跃会话
        # 先检查超时 → 再获取/创建
        active_session = get_current_active_session(str(chat_room.room_id), db)
        if not active_session:
            active_session = await create_new_session(str(chat_room.room_id), user_id, role, db)

        # 加入Socket房间
        await sio.enter_room(sid, room_uuid)
        print(
            f"{role} {user_id} 加入房间 {room_uuid} (session: {active_session.session_uuid if active_session else '无'})")

        # 发送房间加入成功事件
        await sio.emit("room_joined", {
            "room_uuid": room_uuid,
            "session_uuid": active_session.session_uuid if active_session else None,
            "role": role,
            "user_id": user_id,
            "success": True
        }, room=sid)

        # 如果护士加入，通知房间内的其他人
        if role == "nurse":
            await sio.emit("nurse_enter", {
                "nurse_id": nurse_id,
                "patient_id": patient_id,
                "room_uuid": room_uuid
            }, room=room_uuid)

    except Exception as e:
        print(f"加入房间失败: {str(e)}")
        await sio.emit("join_error", {
            "error": str(e),
            "success": False
        }, room=sid)
    finally:
        db.close()

# =========================
# ✅ 护士接管（真正停止AI）
# =========================
@sio.event
async def nurse_takeover(sid, data):
    room_id = data["room_id"]
    active = data["active"]

    if room_id in rooms:
        rooms[room_id]["ai_enabled"] = not active
        rooms[room_id]["abort_ai"] = active  # 接管=打开终止开关

        # 终止正在运行的AI任务
        if rooms[room_id]["ai_task"]:
            rooms[room_id]["ai_task"].cancel()

    await sio.emit("nurse_takeover", {"active": active}, room=room_id)
    print(f"房间 {room_id} AI已终止")

@sio.event
async def send_message(sid, data):
    room_uuid = data.get("room_uuid")
    role = data["role"]

    if not room_uuid:
        await sio.emit("error", {"error": "缺少room_uuid"}, room=sid)
        return

    db: Session = next(get_db())

    try:
        # 1. 获取聊天室
        chat_room = get_chat_room_by_uuid(db, room_uuid)
        if not chat_room:
            raise Exception("聊天室不存在")

        # 2. 验证发送者权限
        sender_id = int(data["user_id"])

        if role == "patient":
            if sender_id != chat_room.patient_id:
                raise Exception("无权限在此房间发送消息")
        elif role == "nurse":
            if sender_id != chat_room.nurse_id:
                raise Exception("无权限在此房间发送消息")

        # 3. 获取活跃会话
        # 3. 检查会话超时，自动创建新会话
        active_session = get_current_active_session(str(chat_room.room_id), db)
        if not active_session:
            active_session = await create_new_session(str(chat_room.room_id), str(sender_id), role, db)

        # 4. 保存消息到数据库
        message, created = get_or_create_message(
            db=db,
            session_uuid=str(active_session.session_uuid),
            sender_type=role_to_sender_type(role),
            sender_id=sender_id,
            content=data["content"],
            chat_mode=data.get("chatMode", "AI"),
            temp_id=data.get("temp_id")
        )

        if not message:
            raise Exception("保存消息失败")

        # 5. 更新聊天室最后活动时间
        chat_room.last_activity_time = datetime.now()
        db.commit()

        # 6. 构建广播消息
        msg = {
            "message_uuid": message.message_uuid,
            "message_id": message.message_uuid,
            "session_uuid": active_session.session_uuid,
            "room_uuid": room_uuid,
            "user_id": data["user_id"],
            "role": role,
            "from_name": data.get("from_name", role),
            "content": data["content"],
            "timestamp": int(time.time() * 1000),
            "streaming": False,
            "temp_id": data.get("temp_id"),
            "chatMode": data.get("chatMode", "AI"),
            "is_read": False,
            "create_time": message.create_time.isoformat() if message.create_time else None
        }

        await sio.emit("receive_message", msg, room=room_uuid)

        # 7. AI回复（如果是病人发送且AI启用）
        if (role == "patient" and
                rooms.get(room_uuid, {}).get("ai_enabled", True) and
                data.get("chatMode")!="nurseType"):  # 只有在没有护士时才AI回复
            task = asyncio.create_task(handle_ai_reply(room_uuid, msg, db))
            rooms[room_uuid]["ai_task"] = task

    except Exception as e:
        print(f"发送消息失败: {str(e)}")
        await sio.emit("error", {"error": f"发送失败: {str(e)}"}, room=sid)
    finally:
        db.close()

async def handle_ai_reply(room_uuid, user_msg, db: Session = None):
    ai_msg_id = str(uuid.uuid4())
    full_text = f"AI回覆：{user_msg['content']}，這是一個流式輸出示例。"
    current_text = ""

    # 获取或创建数据库会话
    if not db:
        db = next(get_db())

    try:
        for i, char in enumerate(full_text):
            # 检测终止开关
            if room_uuid in rooms and rooms[room_uuid].get("abort_ai", False):
                print(f"房间 {room_uuid} AI流式已终止")
                # 发送结束消息
                ai_msg = {
                    "message_id": ai_msg_id,
                    "room_uuid": room_uuid,
                    "user_id": "ai",
                    "role": "ai",
                    "content": current_text,
                    "from_name": "糖尿病AI助手",
                    "timestamp": int(time.time() * 1000),
                    "streaming": False
                }
                await sio.emit("receive_message", ai_msg, room=room_uuid)
                return

            current_text += char

            # 如果是第一个字符，创建数据库记录
            if i == 0 and "session_uuid" in user_msg:
                message, _ = get_or_create_message(
                    db=db,
                    session_uuid=user_msg["session_uuid"],
                    sender_type="ai",
                    sender_id=0,
                    content=current_text,
                    chat_mode=user_msg.get("chatMode", "AI")
                )

                if message:
                    ai_msg_id = message.message_uuid

            ai_msg = {
                "message_uuid": ai_msg_id,
                "message_id": ai_msg_id,
                "session_uuid": user_msg.get("session_uuid", ""),
                "room_uuid": room_uuid,
                "user_id": "ai",
                "role": "ai",
                "content": current_text,
                "from_name": "糖尿病AI助手",
                "timestamp": int(time.time() * 1000),
                "streaming": i < len(full_text) - 1,
                "temp_id": user_msg.get("temp_id"),
                "chatMode": user_msg.get("chatMode", "AI"),
                "is_read": True,
                "create_time": datetime.now().isoformat()
            }

            await sio.emit("receive_message", ai_msg, room=room_uuid)
            await asyncio.sleep(0.05)

        # 正常结束，更新消息内容
        if "session_uuid" in user_msg and ai_msg_id:
            # 重新获取消息并更新
            message = db.query(Message).filter(
                Message.message_uuid == ai_msg_id
            ).first()
            if message:
                message.content = current_text
                db.commit()

        # 发送最终消息
        ai_msg["streaming"] = False
        await sio.emit("receive_message", ai_msg, room=room_uuid)

    except Exception as e:
        print(f"AI回复保存失败: {str(e)}")
    finally:
        if db:
            db.close()

# =========================
# ✅ 离开房间
# =========================
@sio.event
async def leave_room(sid, data):
    user_id = data["user_id"]
    room_id = data["room_id"]
    role = data["role"]

    await sio.leave_room(sid, room_id)

    if role == "nurse" and room_id in rooms:
        rooms[room_id]["nurse"] = None
        rooms[room_id]["ai_enabled"] = True
        rooms[room_id]["abort_ai"] = False  # 重置终止开关
        await sio.emit("nurse_leave", {"active": False}, room=room_id)

    print(f"{user_id} 离开 {room_id}")

# =========================
# ✅ 断开
# =========================
@sio.event
async def disconnect(sid):
    # 找到当前sid对应的user_id和role
    user_id = None
    role = None
    for uid, s in online_users.items():
        if s == sid:
            user_id = uid
            role = user_roles.get(uid)
            break
    if not user_id or not role:
        return

    # 移除在线记录
    del online_users[user_id]
    if user_id in user_roles:
        del user_roles[user_id]
    print(f"{role} {user_id} 下线，SID: {sid}")

    # 获取数据库会话，触发下线广播
    db: Session = next(get_db())
    await broadcast_online_status(user_id, role, online=False, db=db)
    db.close()

# =========================
# ✅ 新增：转发多端聊天状态同步广播（核心解决患者端不同步问题）
# =========================
@sio.event
async def sync_chat_mode_broadcast(sid, data):
    room_id = data.get("room_uuid")
    if room_id and room_id in rooms:
        # 转发状态到当前房间所有客户端（患者+护士）
        await sio.emit("sync_chat_mode", data, room=room_id)

@sio.event
async def mark_message_read(sid, data):
    """标记消息为已读"""
    room_uuid = data.get("room_uuid")
    message_uuid = data.get("message_uuid")
    reader_id = data.get("reader_id")
    reader_role = data.get("reader_role")

    if not all([room_uuid, message_uuid, reader_id, reader_role]):
        return

    db: Session = next(get_db())

    try:
        # 更新已读状态
        success = update_message_read_status(
            db, message_uuid, int(reader_id), reader_role
        )

        if success:
            # 广播已读状态更新
            await sio.emit("message_read_update", {
                "message_uuid": message_uuid,
                "is_read": True,
                "read_by_user_id": reader_id,
                "read_by_role": reader_role,
                "read_time": datetime.now().isoformat()
            }, room=room_uuid)

    except Exception as e:
        print(f"标记已读失败: {str(e)}")
    finally:
        db.close()


@sio.event
async def send_system_message(sid, data):
    """发送系统消息"""
    room_id = data["room_id"]
    content = data["content"]

    # 获取数据库会话
    db: Session = next(get_db())

    try:
        # 获取当前活跃会话
        active_session = get_current_active_session(room_id, db)
        if not active_session:
            return

        # 创建系统消息记录
        message_uuid = str(uuid.uuid4())
        db_message = Message(
            message_uuid=message_uuid,
            session_uuid=active_session.session_uuid,
            sender_type=SenderType.SYSTEM,
            sender_id=-1,  # 系统固定ID
            content=content,
            chat_mode="AI",
            create_time=datetime.now()
        )
        db.add(db_message)

        # 更新会话统计
        active_session.message_count += 1
        active_session.last_message_time = datetime.now()

        db.commit()

        # 广播系统消息
        await sio.emit("receive_message", {
            "message_uuid": message_uuid,
            "message_id": message_uuid,
            "session_uuid": active_session.session_uuid,
            "room_id": room_id,
            "user_id": "system",
            "role": "system",
            "content": content,
            "timestamp": int(time.time() * 1000),
            "chatMode": "AI",
            "is_read": True
        }, room=room_id)

    except Exception as e:
        db.rollback()
        print(f"发送系统消息失败: {str(e)}")
    finally:
        db.close()

# 核心广播函数：向目标用户推送上下线通知
async def broadcast_online_status(user_id: str, role: str, online: bool, db):
    """
    广播上下线状态
    :param user_id: 上下线用户ID
    :param role: 上下线用户角色（nurse/patient）
    :param online: 在线状态（True/False）
    :param db: 数据库会话
    """
    # 构造通知数据
    notify_data = {
        "user_id": user_id,
        "role": role,
        "online": online,
        "timestamp": datetime.now().isoformat()  # 时间戳防重复
    }
    # 场景1：患者上下线 → 推送给**该患者的专属护士**
    if role == "patient":
        nurse_id = await get_patient_nurse_id(user_id, db)
        if nurse_id and nurse_id in online_users:  # 护士在线才推送
            await sio.emit(
                "user_online_status",  # 前端监听的事件名
                notify_data,
                to=online_users[nurse_id]  # 推送给对应护士的sid
            )
    # 场景2：护士上下线 → 推送给**该护士的所有关联患者**
    elif role == "nurse":
        patient_ids = await get_nurse_patient_ids(user_id, db)
        for p_id in patient_ids:
            if p_id in online_users:  # 患者在线才推送
                await sio.emit(
                    "user_online_status",
                    notify_data,
                    to=online_users[p_id]
                )