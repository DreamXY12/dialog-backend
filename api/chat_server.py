import socketio
import uuid
import time
import asyncio
import aiohttp
import json

# 改成
from redis.asyncio import Redis
from sqlalchemy.orm import Session
from yaml import emit

from sql.start import get_db
from sql.people_models import Message, ConversationSession, ChatRoom, NurseWorkShift
from sql.people_models import SenderType, SessionStatus, SessionType
from sql.nurse_curd import  unassign_patient_from_specific_nurse_by_phone
from typing import Optional, Dict, List
from datetime import datetime
from sql.chat_histoty_curd import get_room_uuid_by_id
from sql.patient_curd import get_nurse
from sql.nurse_curd import get_patient_ids_by_nurse
import httpx
import urllib3
from sqlalchemy.exc import SQLAlchemyError, PendingRollbackError

import logging
# 配置日志（非常重要）
logger = logging.getLogger(__name__)


urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from sql.chat_histoty_curd import (
    get_or_create_patient_chat_room,
    get_nurse_patient_chat_room,
    get_chat_room_by_uuid,
    get_or_create_message,
    update_message_read_status
)

# =========================
# AI 全局配置 稳定版
# =========================
AI_BASE_URL = "https://agent.dialog.polyusn.com"
SESSION_TIMEOUT_HOURS = 4

# =========================
# 生产环境：Redis 连接 (AWS 可用)
# =========================
redis: Redis = None

REDIS_ONLINE_USER = "chat:online_user"
REDIS_USER_ROLE = "chat:user_role"
REDIS_SID_TO_USER = "chat:sid_to_user"
REDIS_ROOM_INFO = "chat:room_info"
REDIS_AI_REPLY_LOCK = "chat:ai_replying"

async def init_redis_once():
    global redis
    if redis is not None:
        return
    redis = Redis.from_url(
        "redis://localhost:6379/0",
        encoding="utf-8",
        decode_responses=True
    )
    await redis.ping()
    print("✅ Redis 已连接（全局仅一次）")

    # ✅ 服务器启动 → 清空所有在线状态（确保重启后清空）
    await redis.delete(REDIS_ONLINE_USER)
    await redis.delete(REDIS_USER_ROLE)
    await redis.delete(REDIS_SID_TO_USER)


# =========================
# Socket.IO 服务
# =========================
allowed_origins = [
    "http://localhost:5173",
    "https://dialog.polyusn.com"
]

sio = socketio.AsyncServer(
    cors_allowed_origins=allowed_origins,
    async_mode="asgi",
    cors_credentials=True,
    allow_headers=["*"],
    max_http_buffer_size=1e8,
)

# =========================
# AI 工具方法
# =========================
async def ai_public_chat(message: str, session_id: str = None, room_uuid: str = None):
    payload = {"message": message.strip()}
    if session_id:
        payload["session_id"] = session_id

    try:
        async with httpx.AsyncClient(verify=False, timeout=30.0) as client:
            res = await client.post(f"{AI_BASE_URL}/api/public/chat", json=payload)
        return res.status_code, res.json()
    except Exception as e:
        print(f"AI 请求失败: {str(e)}")
        await sio.emit("receive_message", {
            "room_uuid": room_uuid,
            "user_id": "ai",
            "role": "ai",
            "content": "AI 服务异常，请稍后重试",
            "streaming": False
        }, room=room_uuid)
        return -1, {}

# =========================
# 房间操作（Redis 稳定版）
# =========================
async def get_room(room_uuid: str) -> dict:
    data = await redis.hget(REDIS_ROOM_INFO, room_uuid)
    return json.loads(data) if data else {}

async def save_room(room_uuid: str, data: dict):
    await redis.hset(REDIS_ROOM_INFO, room_uuid, json.dumps(data))

async def del_room(room_uuid: str):
    await redis.hdel(REDIS_ROOM_INFO, room_uuid)

# =========================
# 辅助函数
# =========================
def get_current_active_session(room_id: str, db: Session) -> Optional[ConversationSession]:
    return db.query(ConversationSession).filter(
        ConversationSession.room_id == int(room_id),
        ConversationSession.session_status == SessionStatus.ACTIVE
    ).order_by(ConversationSession.start_time.desc()).first()

async def create_new_session(room_id: str, user_id: str, role: str, db: Session, ai_session_id: str = None) -> ConversationSession:
    room = db.query(ChatRoom).filter(ChatRoom.room_id == int(room_id)).first()
    session_count = db.query(ConversationSession).filter(
        ConversationSession.room_id == int(room_id)
    ).count()
    session_number = session_count + 1

    nurse_shift_id = None
    session_type = SessionType.AI_ONLY

    if room and room.nurse_id and room.current_shift_id:
        shift = db.query(NurseWorkShift).filter(
            NurseWorkShift.shift_id == room.current_shift_id
        ).first()
        if shift and shift.is_working_hours:
            nurse_shift_id = shift.shift_id
            session_type = SessionType.NURSE_ASSISTED

    new_session = ConversationSession(
        room_id=int(room_id),
        session_uuid=ai_session_id,
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

def role_to_sender_type(role: str) -> str:
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

async def get_patient_nurse_id(patient_id: str, db) -> str:
    chat_room = get_room_uuid_by_id(db, patient_id=int(patient_id))
    return str(chat_room["nurse_id"]) if chat_room and chat_room["nurse_id"] else ""

async def get_nurse_patient_ids(nurse_id: str, db) -> List[str]:
    chat_rooms = get_room_uuid_by_id(db, nurse_id=int(nurse_id))
    return [str(cr["patient_id"]) for cr in chat_rooms] if chat_rooms else []

# =========================
# 安全异步任务（不崩溃）
# =========================
async def safe_task(coro):
    try:
        await coro
    except Exception as e:
        print(f"[任务异常] {e}")

# =========================
# 连接
# =========================
@sio.event
async def connect(sid, environ, auth):
    if not auth:
        return


    await init_redis_once()
    user_id = str(auth.get("user_id"))
    role = auth.get("role")
    if not user_id or not role or role not in ["nurse", "patient"]:
        return

    await redis.hset(REDIS_ONLINE_USER, user_id, sid)
    await redis.hset(REDIS_USER_ROLE, user_id, role)
    await redis.hset(REDIS_SID_TO_USER, sid, user_id)
    print(f"{role} {user_id} 上线")

    if role == "patient":
        await get_nurse_online_status(sid, auth)
    elif role == "nurse":
        await get_patients_online_status(sid, auth)
    try:
        db: Session = next(get_db())

        await broadcast_online_status(user_id, role, online=True, db=db)
    finally:
        db.close()

@sio.event
async def disconnect(sid):
    user_id = await redis.hget(REDIS_SID_TO_USER, sid)
    if not user_id:
        return

    role = await redis.hget(REDIS_USER_ROLE, user_id)
    await redis.hdel(REDIS_ONLINE_USER, user_id)
    await redis.hdel(REDIS_USER_ROLE, user_id)
    await redis.hdel(REDIS_SID_TO_USER, sid)

    for room_uuid in await redis.hkeys(REDIS_ROOM_INFO):
        room = await get_room(room_uuid)
        if room.get("nurse_sid") == sid:
            room["nurse_sid"] = None
            room["nurse_id"] = None
            room["ai_enabled"] = True
            room["abort_ai"] = False
            await save_room(room_uuid, room)

    print(f"{role} {user_id} 下线")

    db: Session = next(get_db())
    try:
        await broadcast_online_status(user_id, role, online=False, db=db)
    finally:
        db.close()

# =========================
# 加入房间
# =========================
@sio.event
async def join_room(sid, data):
    user_id = data["user_id"]
    role = data["role"]
    target_patient_id = data.get("target_patient_id")
    db: Session = next(get_db())

    try:
        if role == "patient":
            patient_id = int(user_id)
            chat_room, _ = get_or_create_patient_chat_room(db, patient_id)
            room_uuid = chat_room.room_uuid

            room = await get_room(room_uuid)
            if not room:
                room = {
                    "patient_sid": sid, "patient_id": patient_id,
                    "nurse_sid": None, "nurse_id": None,
                    "ai_enabled": True, "abort_ai": False, "ai_session_id": None
                }
            else:
                room["patient_sid"] = sid
                room["patient_id"] = patient_id

            await save_room(room_uuid, room)

        elif role == "nurse":
            if not target_patient_id:
                raise Exception("护士必须指定病人ID")
            nurse_id = int(user_id)
            patient_id = int(target_patient_id)
            chat_room = get_nurse_patient_chat_room(db, nurse_id, patient_id, verify_assignment=True)
            room_uuid = chat_room.room_uuid

            room = await get_room(room_uuid)
            if not room:
                room = {
                    "patient_sid": None, "patient_id": patient_id,
                    "nurse_sid": sid, "nurse_id": nurse_id,
                    "ai_enabled": True, "abort_ai": False, "ai_session_id": None
                }
            else:
                room["nurse_sid"] = sid
                room["nurse_id"] = nurse_id

            await save_room(room_uuid, room)

        await sio.enter_room(sid, room_uuid)
        await sio.emit("room_joined", {
            "room_uuid": room_uuid, "role": role, "user_id": user_id, "success": True
        }, room=room_uuid)

    except Exception as e:
        await sio.emit("join_error", {"error": str(e)}, to=sid)
    finally:
        db.close()

@sio.event
async def get_patients_online_status(sid, data):
    """
    护士页面：获取【自己绑定的所有病人】，并标注在线状态
    病人来源 = 数据库绑定列表
    在线状态 = Redis 真实在线
    """
    nurse_id = data.get("user_id")
    if not nurse_id:
        return

    db: Session = next(get_db())
    try:
        # ✅ 从数据库获取【该护士绑定的所有病人】（必须全部显示）
        patient_ids = await get_nurse_patient_ids(str(nurse_id), db)
        online_list = []

        for pid in patient_ids:
            pid_str = str(pid)
            # ✅ 逐个判断 Redis 是否在线
            is_online = await redis.hexists(REDIS_ONLINE_USER, pid_str)
            online_list.append({
                "user_id": pid_str,
                "online": is_online
            })

        # 推送给护士
        await sio.emit("patients_online", online_list, to=sid)
    finally:
        db.close()

@sio.event
async def get_nurse_online_status(sid, data):
    """
    病人页面加载 → 获取自己护士的在线状态
    前端：emitNurseIsOnline
    """
    patient_id = data.get("user_id")
    if not patient_id:
        return

    db: Session = next(get_db())
    try:
        nurse_id = await get_patient_nurse_id(patient_id, db)
        if not nurse_id:
            await sio.emit("nurse_online", {"nurse_online": False}, to=sid)
            return

        is_online = await redis.hexists(REDIS_ONLINE_USER, nurse_id)
        await sio.emit("nurse_online", {"nurse_online": is_online}, to=sid)
    finally:
        db.close()

# =========================
# 发送消息 & AI 回复
# =========================
@sio.event
async def send_message(sid, data):
    room_uuid = data.get("room_uuid")
    role = data["role"]
    if not room_uuid:
        return

    lock_key = f"{REDIS_AI_REPLY_LOCK}:{room_uuid}"
    if await redis.exists(lock_key):
        return

    # 每次都拿全新的 DB 会话，不要复用
    db: Session = next(get_db())

    try:
        chat_room = get_chat_room_by_uuid(db, room_uuid)
        if not chat_room:
            return

        sender_id = int(data["user_id"])
        active_session = get_current_active_session(str(chat_room.room_id), db)
        room = await get_room(room_uuid)
        current_ai_session_id = room.get("ai_session_id")

        if not active_session:
            status, ai_data = await ai_public_chat(message=data["content"], room_uuid=room_uuid)
            if status == 200 and "session_id" in ai_data:
                current_ai_session_id = ai_data["session_id"]
                room["ai_session_id"] = current_ai_session_id
                await save_room(room_uuid, room)
            active_session = await create_new_session(
                room_id=str(chat_room.room_id), user_id=str(sender_id), role=role, db=db,
                ai_session_id=current_ai_session_id
            )

        message, _ = get_or_create_message(
            db=db,
            session_uuid=str(active_session.session_uuid),
            sender_type=role_to_sender_type(role),
            sender_id=sender_id,
            content=data["content"],
            chat_mode=data.get("chatMode", "AI"),
            temp_id=data.get("temp_id"),
            room_id=chat_room.room_id,
        )

        chat_room.last_activity_time = datetime.now()
        db.commit()

        msg = {
            "message_uuid": message.message_uuid,
            "room_uuid": room_uuid,
            "user_id": data["user_id"],
            "role": role,
            "content": data["content"],
            "timestamp": int(time.time() * 1000),
            "streaming": False,
            "chatMode": data.get("chatMode", "AI"),
            "temp_id": data.get("temp_id"),
            "from_name": data.get("from_name")
        }
        await sio.emit("receive_message", msg, room=room_uuid)

        if role == "patient" and room.get("ai_enabled", True) and data.get("chatMode") != "nurseType":
            task = asyncio.create_task(safe_task(
                handle_ai_reply(room_uuid, msg, current_ai_session_id)
            ))

    # 🔥 关键 1：专门捕获 SQLAlchemy 事务错误
    except PendingRollbackError as e:
        print(f"\n=====================================")
        print(f"❌ PendingRollbackError 事务失效")
        print(f"📜 错误信息：{str(e)}")
        print(f"🔴 异常类型：{type(e).__name__}")
        print(f"🚽 房间 UUID：{room_uuid}")
        print(f"=====================================\n")

        msg = {
            "message_uuid": (uuid.uuid4()),
            "room_uuid": room_uuid,
            "user_id": data["user_id"],
            "role": role,
            "content": "抱歉，當前出了點網絡問題，請刷新頁面稍後重試",
            "timestamp": int(time.time() * 1000),
            "streaming": False,
            "chatMode": data.get("chatMode", "AI"),
            "temp_id": data.get("temp_id"),
            "from_name": data.get("from_name")
        }
        await sio.emit("receive_message", msg, room=room_uuid)

        db.rollback()
        db.invalidate()  # 关键修复
        # 强制回滚 + 失效连接（根治脏事务）
        db.rollback()
        db.invalidate()  # 最重要的修复
        print("🔥 已修复失效事务：强制回滚并重置连接")

    # 🔥 关键 2：捕获所有数据库错误
    except SQLAlchemyError as e:
        db.rollback()
        print(f"数据库异常：{str(e)}")

    # 其他异常
    except Exception as e:
        db.rollback()
        print(f"未知异常：{str(e)}")

    # 🔥 关键 3：无论如何都彻底清理会话
    finally:
        db.rollback()  # 兜底回滚，防止残留事务
        db.close()
        db = None  # 释放引用

async def handle_ai_reply(room_uuid, user_msg, ai_session_id):
    lock_key = f"{REDIS_AI_REPLY_LOCK}:{room_uuid}"
    await redis.set(lock_key, "1", ex=15)

    db: Session = next(get_db())
    try:
        room = await get_room(room_uuid)
        if room.get("abort_ai"):
            return

        # 1. 获取房间信息
        chat_room = get_chat_room_by_uuid(db, room_uuid)
        if not chat_room:
            return

        # 2. 请求 AI Agent
        status, ai_data = await ai_public_chat(
            message=user_msg["content"],
            session_id=ai_session_id,
            room_uuid=room_uuid
        )
        if status != 200:
            return

        # ===================== 读取 AI 返回核心字段 =====================
        ai_state = ai_data.get("state", "").strip()
        ai_text = ai_data.get("message", "").strip()
        new_session_id = ai_data.get("session_id")
        # =================================================================

        # 更新 session_id
        if room.get("ai_session_id") != new_session_id:
            if new_session_id:
                room["ai_session_id"] = new_session_id
                await save_room(room_uuid, room)

        # ---------------------------------------------------------------------
        # ✅ 关键：所有 state 都必须返回消息给前端
        # ---------------------------------------------------------------------
        reply_text = ""

        if ai_state == "stopped":
            reply_text = ai_text if ai_text else "AI 目前無法繼續回答，建議您轉由護士人工協助。您可以直接輸入'轉人工'，或者點擊下方緊急聯係護士按鈕。"

        elif ai_state == "needs_input":
            reply_text = ai_text if ai_text else "請您補充相關資料，我才能繼續為您評估。"

        elif ai_state == "urgent":
            reply_text = ai_text if ai_text else "偵測到健康風險，建議您盡快諮詢醫護人員。您可以直接輸入'轉人工'，或者點擊下方緊急聯係護士按鈕。"

        elif ai_state == "in_progress":
            reply_text = ai_text if ai_text else "處理中，請稍後..."

        elif ai_state == "completed":
            reply_text = ai_text if ai_text else "本次諮詢已完成。"

        else:
            reply_text = ai_text if ai_text else "感謝您的提問，我已記錄您的問題。"

        # ---------------------------------------------------------------------
        # 3. 获取会话
        # ---------------------------------------------------------------------
        active_session = get_current_active_session(str(chat_room.room_id), db)
        if not active_session:
            return

        # ---------------------------------------------------------------------
        # 4. 存入数据库（所有状态都存）
        # ---------------------------------------------------------------------
        get_or_create_message(
            db=db,
            session_uuid=str(active_session.session_uuid),
            sender_type="ai",
            sender_id=0,
            content=reply_text,
            chat_mode="AI",
            temp_id=None,
            room_id=chat_room.room_id,
        )

        # ---------------------------------------------------------------------
        # 5. 推送给前端（一定会发）
        # ---------------------------------------------------------------------
        msg_id = str(uuid.uuid4())
        ai_msg = {
            "message_uuid": msg_id,
            "room_uuid": room_uuid,
            "user_id": "ai",
            "role": "ai",
            "content": reply_text,
            "streaming": False,
            "chatMode": "AI",
            "state": ai_state
        }
        await sio.emit("receive_message", ai_msg, room=room_uuid)

    finally:
        await redis.delete(lock_key)
        db.commit()
        db.close()

# =========================
# 其他事件（已稳定化）
# =========================
@sio.event
async def nurse_takeover(sid, data):
    room_id = data["room_id"]
    active = data["active"]
    room = await get_room(room_id)
    if room:
        room["ai_enabled"] = not active
        room["abort_ai"] = active
        await save_room(room_id, room)
    await sio.emit("nurse_takeover", {"active": active}, room=room_id)

@sio.event
async def mark_message_read(sid, data):
    db: Session = next(get_db())
    try:
        update_message_read_status(db, data["message_uuid"], int(data["reader_id"]), data["reader_role"])
    finally:
        db.close()

async def broadcast_online_status(user_id: str, role: str, online: bool, db):
    data = {"user_id": user_id, "role": role, "online": online}
    if role == "patient":
        nid = await get_patient_nurse_id(user_id, db)
        if nid and await redis.hexists(REDIS_ONLINE_USER, nid):
            await sio.emit("user_online_status", data, to=await redis.hget(REDIS_ONLINE_USER, nid))
    else:
        pids = await get_nurse_patient_ids(user_id, db)
        for pid in pids:
            if await redis.hexists(REDIS_ONLINE_USER, pid):
                await sio.emit("user_online_status", data, to=await redis.hget(REDIS_ONLINE_USER, pid))

# 廣播當前聊天室的聊天狀態
# --- 带完整错误处理的 socket 事件 ---
@sio.event
async def sync_chat_mode_broadcast(sid, data):
    db: Session = None
    try:
        # 1. 校验入参
        if not data.get("room_uuid"):
            logger.warning(f"客户端 {sid} 缺少 room_uuid 参数")
            await sio.emit("error", {"msg": "缺少房间ID"}, to=sid)
            return

        # 2. 获取数据库连接
        db = next(get_db())

        # 3. 获取房间
        room = await get_room(data["room_uuid"])
        if not room:
            logger.warning(f"房间不存在: {data['room_uuid']}")
            await sio.emit("error", {"msg": "房间不存在"}, to=sid)
            return

        # 4. 构造数据
        emit_data = {
            "chatMode": data["chatMode"],
            "isStreamAbort": False,
            "isTyping": True
        }

        # 5. 特殊模式处理
        if emit_data["chatMode"] == "nurseType":
            emit_data["isStreamAbort"] = True
            emit_data["isTyping"] = False

        # 6. 广播消息
        await sio.emit("sync_chat_mode", emit_data, room=data["room_uuid"])
        logger.info(f"房间 {data['room_uuid']} 同步聊天模式成功")

    except KeyError as e:
        # 缺少字段错误
        logger.error(f"数据格式错误，缺少字段: {str(e)}")
        await sio.emit("error", {"msg": f"数据格式错误：{str(e)}"}, to=sid)

    except Exception as e:
        # 全局兜底错误（不会让服务崩溃）
        logger.error(f"sync_chat_mode_broadcast 执行失败: {str(e)}", exc_info=True)
        await sio.emit("error", {"msg": "服务器同步聊天模式失败"}, to=sid)

    finally:
        # 无论成功失败，确保数据库关闭
        if db:
            db.close()

# 只有護士才會離開房間，病人除了斷開鏈接，否則一直會在房間内
@sio.event
async def leave_room(sid, data):
    room_uuid = data["room_uuid"]
    if room_uuid:
        await get_room(room_uuid)
        await sio.emit("nurse_leave",room=room_uuid)

#護士如果更新了上下班時間，就給對應的病人通告
@sio.event
async def nurse_work_time_update(sid,data):
    nurse_id = data.get("nurse_id")
    if nurse_id:
        db = next(get_db())
        pids = await get_nurse_patient_ids(nurse_id, db)
        # 如果病人在綫就實時推送護士已經修改了工作時間
        for pid in pids:
            if await redis.hexists(REDIS_ONLINE_USER, pid):
                await sio.emit("nurse_work_time_changed", data, to=await redis.hget(REDIS_ONLINE_USER, pid))

# 護士分配病人事件,這是一對一通知的，不是對護士名下的所有人通知
@sio.event
async def add_new_patients(sid,data):
    nurse_id = data.get("nurse_id")
    send_data={"nurse_id": nurse_id,"is_add":True}
    for patient_id in data["patient_ids"]: #病人的id,是個數組，因爲可能會添加多個病人
        if await redis.hexists(REDIS_ONLINE_USER,patient_id ):
            # 如果對應的分配病人在綫則通知否則就不通知已經被分配了
            await sio.emit("patient_add",send_data,to=await redis.hget(REDIS_ONLINE_USER,patient_id))

@sio.event
async def remove_patient(sid,data):
    nurse_phone = data.get("nurse_phone")
    patient_phone = data.get("patient_phone")
    patient_id = data.get("patient_id")
    if nurse_phone and patient_phone:

        db = next(get_db())
        patient = unassign_patient_from_specific_nurse_by_phone(db, nurse_phone, patient_phone)
        if not patient:
            send_data = {"is_remove":True}
            # 在线就直接通知不在线就通知不到
            await sio.emit("patient_remove",data,to=await redis.hget(REDIS_ONLINE_USER,patient_id))
