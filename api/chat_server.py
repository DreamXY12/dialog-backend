import socketio
from fastapi import FastAPI
import uuid
import time
import asyncio

# 1. 创建 Socket.IO 异步服务
sio = socketio.AsyncServer(
    cors_allowed_origins="*",
    async_mode="asgi",
    cors_credentials=True,
    allow_origin=None
)

# 在线用户
online_users = {}  # user_id -> sid

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
# ✅ 连接
# =========================
@sio.event
async def connect(sid, environ, auth):
    if not auth:
        return
    user_id = auth.get("user_id")
    role = auth.get("role")
    if user_id:
        online_users[user_id] = sid
        print(f"{role} {user_id} 上线")

# =========================
# ✅ 加入房间
# =========================
@sio.event
async def join_room(sid, data):
    user_id = data["user_id"]
    room_id = data["room_id"]
    role = data["role"]

    await sio.enter_room(sid, room_id)

    if room_id not in rooms:
        rooms[room_id] = {
            "patient": None,
            "nurse": None,
            "ai_enabled": True,
            "ai_task": None,       # 保存AI任务
            "abort_ai": False      # 终止开关
        }

    if role == "patient":
        rooms[room_id]["patient"] = user_id
    elif role == "nurse":
        rooms[room_id]["nurse"] = user_id
        await sio.emit("nurse_enter", {"active": True}, room=room_id)

    print(f"{user_id} 加入 {room_id}")

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

# =========================
# ✅ 发送消息
# =========================
@sio.event
async def send_message(sid, data):
    room_id = data["room_id"]
    role = data["role"]
    chatMode = data.get("chatMode")

    # 模式控制AI开关
    if chatMode is not None:
        if chatMode == "nurseType" or chatMode == "one-to-one":
            rooms[room_id]["ai_enabled"] = False
            rooms[room_id]["abort_ai"] = True  # 终止AI
            if rooms[room_id]["ai_task"]:
                rooms[room_id]["ai_task"].cancel()
        else:
            rooms[room_id]["ai_enabled"] = True
            rooms[room_id]["abort_ai"] = False

    msg = {
        "message_id": str(uuid.uuid4()),
        "room_id": room_id,
        "user_id": data["user_id"],
        "role": role,
        "from_name": data["from_name"],
        "content": data["content"],
        "phone": data.get("phone") if role in HUMAN_ROLES else None,
        "timestamp": int(time.time() * 1000),
        "streaming": False,
        "temp_id": data["temp_id"]
    }

    await sio.emit("receive_message", msg, room=room_id)

    # AI 回复
    if role == "patient" and rooms[room_id]["ai_enabled"]:
        # 保存任务，方便后面取消
        task = asyncio.create_task(handle_ai_reply(room_id, msg))
        rooms[room_id]["ai_task"] = task

# =========================
# ✅ AI流式回复（支持终止）
# =========================
async def handle_ai_reply(room_id, user_msg):
    ai_msg_id = str(uuid.uuid4())
    full_text = f"AI回覆：{user_msg['content']}，這是一個流式輸出示例。"
    current_text = ""

    for char in full_text:
        # ======================
        # 核心：检测终止开关
        # ======================
        if room_id in rooms and rooms[room_id]["abort_ai"]:
            print(f"房间 {room_id} AI流式已终止")
            # 发送结束消息
            ai_msg = {
                "message_id": ai_msg_id,
                "room_id": room_id,
                "user_id": "ai",
                "role": "ai",
                "content": current_text,
                "from_name": "糖尿病AI助手",
                "timestamp": int(time.time() * 1000),
                "streaming": False  # 强制结束
            }
            await sio.emit("receive_message", ai_msg, room=room_id)
            return  # 退出循环，彻底停止

        current_text += char
        ai_msg = {
            "message_id": ai_msg_id,
            "room_id": room_id,
            "user_id": "ai",
            "role": "ai",
            "content": current_text,
            "from_name": "糖尿病AI助手",
            "timestamp": int(time.time() * 1000),
            "streaming": True,
            "temp_id": user_msg["temp_id"]
        }

        await sio.emit("receive_message", ai_msg, room=room_id)
        await asyncio.sleep(0.05)

    # 正常结束
    ai_msg["streaming"] = False
    await sio.emit("receive_message", ai_msg, room=room_id)

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
    for uid, s in list(online_users.items()):
        if s == sid:
            del online_users[uid]
            break

# =========================
# ✅ 新增：转发多端聊天状态同步广播（核心解决患者端不同步问题）
# =========================
@sio.event
async def sync_chat_mode_broadcast(sid, data):
    room_id = data.get("room_id")
    if room_id and room_id in rooms:
        # 转发状态到当前房间所有客户端（患者+护士）
        await sio.emit("sync_chat_mode", data, room=room_id)