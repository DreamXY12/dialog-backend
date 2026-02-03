# app/api/endpoints/chat.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from websocket.chat_manager import manager
from schemas.chat import WebSocketMessage, MessageCreate
from crud import chat as chat_crud
from database import get_db
from sqlalchemy.orm import Session
import json
import uuid
import asyncio
from datetime import datetime

router = APIRouter()

@router.websocket("/ws/chat/{user_login}")
async def websocket_endpoint(
        websocket: WebSocket,
        user_login: str,
        token: str = None  # 可以通过query参数传递token
):
    """WebSocket连接端点"""
    # 这里可以添加认证逻辑
    # if not verify_token(token):
    #     await websocket.close(code=1008)
    #     return

    await manager.connect(websocket, user_login)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message_data = json.loads(data)
                ws_message = WebSocketMessage(**message_data)

                # 处理不同类型的消息
                if ws_message.type == "message":
                    await handle_message(ws_message, user_login)
                elif ws_message.type == "typing":
                    await handle_typing(ws_message, user_login)
                elif ws_message.type == "read":
                    await handle_read(ws_message, user_login)
                elif ws_message.type == "join":
                    await handle_join(ws_message, user_login)

            except json.JSONDecodeError:
                error_msg = WebSocketMessage(
                    type="error",
                    data={"error": "无效的JSON格式"},
                    message_id=None
                )
                await websocket.send_json(error_msg.to_dict())
            except Exception as e:
                error_msg = WebSocketMessage(
                    type="error",
                    data={"error": str(e)},
                    message_id=None
                )
                await websocket.send_json(error_msg.to_dict())

    except WebSocketDisconnect:
        manager.disconnect(user_login)
    except Exception as e:
        print(f"WebSocket错误: {e}")
        manager.disconnect(user_login)


async def handle_message(ws_message: WebSocketMessage, sender_id: str):
    """处理聊天消息"""
    data = ws_message.data
    room_id = data.get("room_id")
    receiver_id = data.get("receiver_id")
    content = data.get("content")

    if not all([room_id, receiver_id, content]):
        return

    # 1. 保存到数据库
    message_create = MessageCreate(
        sender_id=sender_id,
        receiver_id=receiver_id,
        room_id=room_id,
        content=content,
        message_type=data.get("message_type", "text")
    )

    # 这里需要异步保存到数据库
    # saved_message = await chat_crud.create_message(message_create)

    # 2. 构建响应消息
    response_message = WebSocketMessage(
        type="message",
        data={
            "sender_id": sender_id,
            "receiver_id": receiver_id,
            "room_id": room_id,
            "content": content,
            "message_type": data.get("message_type", "text"),
            "timestamp": datetime.utcnow().isoformat(),
            "message_id": ws_message.message_id or str(uuid.uuid4())
        },
        message_id=ws_message.message_id
    )

    # 3. 发送给接收者
    await manager.send_personal_message(response_message.to_dict(), receiver_id)

    # 4. 广播给房间内的其他人（如果需要）
    await manager.broadcast_to_room(
        response_message.to_dict(),
        room_id,
        exclude_user=sender_id
    )


async def handle_typing(ws_message: WebSocketMessage, sender_id: str):
    """处理正在输入状态"""
    data = ws_message.data
    room_id = data.get("room_id")
    receiver_id = data.get("receiver_id")

    typing_message = WebSocketMessage(
        type="typing",
        data={
            "sender_id": sender_id,
            "room_id": room_id,
            "is_typing": data.get("is_typing", True)
        }
    )

    if receiver_id:
        await manager.send_personal_message(typing_message.to_dict(), receiver_id)


async def handle_read(ws_message: WebSocketMessage, sender_id: str):
    """处理已读回执"""
    data = ws_message.data
    message_ids = data.get("message_ids", [])
    room_id = data.get("room_id")

    # 更新数据库中的消息状态
    # await chat_crud.mark_messages_as_read(message_ids, sender_id)

    read_message = WebSocketMessage(
        type="read",
        data={
            "reader_id": sender_id,
            "message_ids": message_ids,
            "room_id": room_id,
            "read_at": datetime.utcnow().isoformat()
        }
    )

    # 通知发送者消息已被阅读
    # 这里需要根据message_ids找到原始发送者
    # await manager.send_personal_message(read_message.to_dict(), original_sender_id)


async def handle_join(ws_message: WebSocketMessage, user_id: str):
    """处理加入房间"""
    data = ws_message.data
    room_id = data.get("room_id")

    if room_id:
        await manager.join_room(user_id, room_id)

        join_message = WebSocketMessage(
            type="join",
            data={
                "user_id": user_id,
                "room_id": room_id,
                "timestamp": datetime.utcnow().isoformat()
            }
        )

        await manager.broadcast_to_room(
            join_message.to_dict(),
            room_id,
            exclude_user=user_id
        )