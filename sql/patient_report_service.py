from datetime import date
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from sql.people_models import Message,ChatRoom  # 你的模型
from utility.word_cloud import generate_multilang_word_cloud
from fastapi import HTTPException  # 增加异常处理

def get_patient_daily_chat_report(
    db: Session,
    room_uuid: str,        # 前端传的是 room_uuid（修改点）
    patient_id: int,
    report_date: date = None
):
    """
    【最终版】根据 room_uuid + patient_id 获取病人每日对话报告
    自动通过 room_uuid 找到 room_id
    只统计病人自己发的消息
    """
    if not report_date:
        report_date = date.today()

    # ===================== 关键步骤：通过 room_uuid 获取 room_id =====================
    chat_room = db.query(ChatRoom).filter(
        ChatRoom.room_uuid == room_uuid
    ).first()

    # 房间不存在直接抛友好提示
    if not chat_room:
        raise HTTPException(status_code=404, detail="聊天室不存在")

    # 拿到真正的 room_id
    room_id = chat_room.room_id


    # ===================== 只查询【当前病人】在【当前房间】发的消息 =====================
    messages = db.query(Message).filter(
        Message.room_id == room_id,
        func.date(Message.create_time) == report_date,
        Message.message_type == "text",
        Message.sender_type == "patient",  # 只看病人
        Message.sender_id == patient_id    # 只看当前病人
    ).all()

    # 提取内容
    contents = [msg.content for msg in messages if msg.content]
    chat_count = len(messages)

    # 多语言词云
    top_topics = generate_multilang_word_cloud(contents)

    return {
        "room_uuid": room_uuid,
        "room_id": room_id,
        "patient_id": patient_id,
        "report_date": report_date.isoformat(),
        "patient_chat_count": chat_count,
        "has_patient_chat_today": chat_count > 0,
        "top_topics": top_topics

        # 你后面要加的 健康数据、检测记录 我也可以帮你加进来
    }