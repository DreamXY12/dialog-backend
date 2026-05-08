# AI 的数据库相关操作

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

# 导入你的模型
from sql.people_models import ChatRoom
from sql.people_models import ConversationSession
from typing import Optional


def delete_patient_current_session_and_clear(
    db: Session,
    patient_id: int
) -> bool:
    """
    根据 patient_id 删除当前会话，并清空 ChatRoom 的 current_session_uuid
    事务保证：删会话 + 清空字段 要么都成功，要么都失败

    Args:
        db: SQLAlchemy 数据库会话
        patient_id: 患者ID

    Returns:
        bool: 操作成功返回 True，无数据/失败返回 False
    """
    try:
        # 1. 根据 patient_id 查询 ChatRoom 记录
        chat_room = db.query(ChatRoom).filter(
            ChatRoom.patient_id == patient_id
        ).first()

        # 无聊天室记录 → 直接返回True
        if not chat_room:
            print(f"[操作] 患者 {patient_id} 无对应聊天室")
            return True

        # 获取当前会话 UUID
        session_uuid = chat_room.current_session_uuid

        # 没有 current_session_uuid → 无需删除，直接返回
        if not session_uuid:
            #print(f"[操作] 患者 {patient_id} 无当前活跃会话，无需删除")
            return True

        # 2. 根据 session_uuid 删除 ConversationSession 记录
        del_count = db.query(ConversationSession).filter(
            ConversationSession.session_uuid == session_uuid
        ).delete()

        #print(f"[删除] 成功删除会话记录：{del_count} 条 (session_uuid={session_uuid})")

        # 3. 将 ChatRoom 的 current_session_uuid 置为空
        chat_room.current_session_uuid = None

        # 4. 提交事务
        db.commit()
        #print(f"[更新] 成功清空患者 {patient_id} 的 current_session_uuid")
        return True

    except SQLAlchemyError as e:
        # 异常回滚
        db.rollback()
        print(f"[错误] 删除会话 & 清空字段失败：{str(e)}")
        return False

def update_chat_room_current_session_uuid_by_patient(
    db: Session,
    patient_id: int,
    current_session_uuid: Optional[str]
) -> bool:
    """
    根据 patient_id 更新聊天室当前活跃会话 UUID
    修复：Result.rowcount 报错问题
    """
    try:
        # 1. 先查询是否存在该患者的聊天室（安全写法）
        chat_room = db.query(ChatRoom).filter(
            ChatRoom.patient_id == patient_id
        ).first()

        if not chat_room:
            return False  # 无数据

        # 2. 更新字段
        chat_room.current_session_uuid = current_session_uuid

        # 3. 提交
        db.commit()
        db.refresh(chat_room)
        return True

    except SQLAlchemyError as e:
        db.rollback()
        print(f"更新失败：{str(e)}")
        return False