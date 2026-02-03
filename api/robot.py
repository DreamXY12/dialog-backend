import logging
from twilio.rest import Client
from fastapi import Request, APIRouter, HTTPException
from core.translate import to_other_language, user_input_to_internal_language, get_fixed_field_translation
from core.translate import get_fixed_response_translation
from core.translate import normalize_alcohol, normalize_yes_no, extract_local_context
from sql.cache_database import r, store_message, get_chat_history
from sql.start import get_db
import sql.crud as crud
from api.user import sign_up, CreateUser
from api.session import response_from_llm
from sql.models import Session, Query
from sql import models
from typing import Annotated
from fastapi import Depends
from sqlalchemy.orm import Session as Connection
import re
from datetime import datetime, timedelta
import uuid
from sql.login_crud import get_or_create_ai_dialog
from sql.login_crud import get_ai_dialogs_by_patient_and_date_range,get_ai_dialogs_by_patient_login_code
from sql.login_crud import update_ai_dialog_with_message,update_ai_dialog_with_message_simple,get_conversation_statistics_enhanced
from sql.models import Session as OldSession
from sql.login_crud import get_filtered_messages_from_dialogs,get_message_timeline,search_messages_by_keyword,get_ai_dialogs_by_patient_and_day
from config import get_parameter
from enum import Enum
from datetime import date

from sql.login_crud import get_patient_by_login_code

"""現在是把用戶登錄的login_code當作原來的phone_number，時間緊急，就先這樣"""

router = APIRouter(prefix='/robot', tags=["robot"])

logging.basicConfig(
    level=logging.INFO,
    filename='dev.log',
    filemode='a',
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def extract(request: Request):
    """提取请求数据"""
    json_data = await request.json()
    return {
        "prompt": json_data.get("prompt"),
        "login_code": json_data.get("login_code"),
        "user_info": json_data.get("user_info"),
    }

#设置字典，从前端获取表单信息然后存入
def set_user_profile(login_code: str, data: dict, ttl: int = 1800):
    if not data:
        return

    key = f"user:{login_code}:profile"

    mapping = {
        str(k): str(v)
        for k, v in data.items()
        if v is not None
    }

    logger.info(f"[Redis] HMSET {key} {mapping}")

    r.hmset(key, mapping)   # ✅ Redis 3.0 完美支持
    r.expire(key, ttl)

@router.post("/")
async def reply(request: Request, db: Annotated[Connection, Depends(get_db)]):
    """处理微信消息"""
    try:
        data = await extract(request)
        question = data["prompt"]
        phone_number = data["login_code"]
        user_info=data["user_info"]
        if user_info is not None:
            set_user_profile(phone_number, user_info)

        logger.info(f"Received message from {phone_number}: {question}")

        # 检查用户是否已注册
        user = get_patient_by_login_code(db,phone_number)
        if user is not None:
            # 已注册用户，处理正常对话
            logger.info(f"User {phone_number} is already registered")
            return await handle_registered_user(user, phone_number, question, db)

    except Exception as e:
        logger.error(f"Error in reply handler: {e}")
        return send_message(phone_number, "對不起，處理您的請求時發生錯誤。請再試一次。", "system")

# 1 代表需要翻译，0代表本身就是繁体中文
def send_message(to_login_code, body_text, role, is_fixed=0,is_register=0):
    """发送微信消息"""
    yue_body_text = ""
    try:
        print(f"DEBUG: Sending message to {to_login_code}: {body_text}")
        if is_fixed == 1:
            yue_body_text = to_other_language(body_text, "yue")
        elif is_fixed == 0:  # 本来就已经设置成了繁体中文
            yue_body_text = body_text

        store_message(to_login_code, (role, body_text))
        logger.info(f"Message sent to {to_login_code}: {yue_body_text}")
        return {"code": 200, "data": {"message": yue_body_text, "role": role, "to_loginCode": to_login_code}, "error_info": "","success": 1}
    except Exception as e:
        logger.error(f"Error sending message to {to_login_code}: {e}")
        print(f"Error sending message to {to_login_code}: {e}")
        return {"code": -1, "data": {"message": "接收消息失敗，請稍後重試", "role": role, "to_number": to_login_code,"success": 0},
                "error_info": str(e),"is_register":is_register}

async def handle_registered_user(user, login_code, question, db):
    """处理已注册用户的对话"""
    try:
        # 获取或创建会话
        session = crud.get_latest_session(db, user_id=user.patient_id)

        if session is None or session.create_time < datetime.utcnow() - timedelta(minutes=30):
            session_key = str(uuid.uuid4())
            db_session = Session(session_key=session_key, user_id=user.patient_id, status=True)
            session = crud.create_session(db, db_session)

        # ====== 关键修改：为同一患者使用固定的AI对话session_key ======
        # 使用患者的login_code作为AI对话的唯一标识
        ai_session_key = f"ai_dialog_{login_code}"

        # 1. 获取或创建AI对话

        ai_dialog = get_or_create_ai_dialog(
            db=db,
            patient_login_code=login_code,
            session_key=ai_session_key,
            ai_model="gpt-4"
        )

        if not ai_dialog:
            print(f"Failed to get or create AI dialog for {ai_session_key}")

        # 创建查询
        q = models.Query(session_key=session.session_key, enquiry=question)
        q = crud.create_query(db, q)

        # 获取LLM响应
        chat_response = response_from_llm(q, session, db, login_code)
        ai_response_text = chat_response["response"]

        # 2. 更新AI对话记录
        if ai_dialog:
            updated = update_ai_dialog_with_message_simple(
                db=db,
                session_key=ai_session_key,
                user_message=question,
                ai_response=ai_response_text,
                ai_model="gpt-4"
            )

            if updated:
                print(f"Dialog updated: {updated.session_key}, messages: {updated.message_count}")
            else:
                print(f"Failed to update dialog {ai_session_key}")

        # 发送响应
        return send_message(login_code, ai_response_text, "ai", 1)

    except Exception as e:
        print(f"Error in handle_registered_user for {login_code}: {e}")
        return send_message(login_code, "對不起，處理您的訊息時發生錯誤。", "system")


# 在robot.py中添加
from datetime import datetime, timedelta
from fastapi import Query
from typing import Optional
import json


# 添加新的API端点来查询AI对话历史
@router.get("/ai-dialogs/{patient_login_code}")
def get_patient_ai_dialogs_endpoint(
        patient_login_code: str,
        db: Annotated[Connection, Depends(get_db)],
        include_messages: bool = Query(False, description="是否包含完整的消息内容"),
        skip: int = Query(0, ge=0, description="跳过记录数"),
        limit: int = Query(100, ge=1, le=1000, description="限制记录数"),

):
    """获取患者的AI对话历史记录"""
    try:
        # 获取所有对话
        dialogs = get_ai_dialogs_by_patient_login_code(db, patient_login_code)

        # 计算总数
        total = len(dialogs)

        # 应用分页
        if skip < total:
            end_index = min(skip + limit, total)
            paginated_dialogs = dialogs[skip:end_index]
        else:
            paginated_dialogs = []

        # 处理响应数据
        response_data = []
        for dialog in paginated_dialogs:
            dialog_info = {
                "history_id": dialog.history_id,
                "patient_login_code": dialog.patient_login_code,
                "session_key": dialog.session_key,
                "title": dialog.title,
                "ai_model": dialog.ai_model,
                "message_count": dialog.message_count,
                "last_message_time": dialog.last_message_time.isoformat() if dialog.last_message_time else None,
                "create_time": dialog.create_time.isoformat() if dialog.create_time else None,
                "update_time": dialog.update_time.isoformat() if dialog.update_time else None
            }

            # 如果请求包含消息，添加消息预览
            if include_messages and dialog.prompts and 'messages' in dialog.prompts:
                messages = dialog.prompts.get('messages', [])
                dialog_info["total_messages"] = len(messages)

                # 添加前几条消息作为预览
                preview_messages = []
                for msg in messages[:5]:  # 只显示前5条作为预览
                    preview_messages.append({
                        "role": msg.get('role'),
                        "content_preview": msg.get('content', '')[:100] + "..." if len(
                            msg.get('content', '')) > 100 else msg.get('content', ''),
                        "timestamp": msg.get('timestamp')
                    })
                dialog_info["message_preview"] = preview_messages

                # 统计用户和AI消息数量
                user_count = sum(1 for msg in messages if msg.get('role') == 'user')
                ai_count = sum(1 for msg in messages if msg.get('role') == 'assistant')
                dialog_info["user_message_count"] = user_count
                dialog_info["ai_message_count"] = ai_count
            else:
                # 如果不包含完整消息，只添加统计信息
                if dialog.prompts and 'messages' in dialog.prompts:
                    messages = dialog.prompts.get('messages', [])
                    user_count = sum(1 for msg in messages if msg.get('role') == 'user')
                    ai_count = sum(1 for msg in messages if msg.get('role') == 'assistant')
                    dialog_info["user_message_count"] = user_count
                    dialog_info["ai_message_count"] = ai_count

            response_data.append(dialog_info)

        return {
            "code": 200,
            "data": response_data,
            "pagination": {
                "skip": skip,
                "limit": limit,
                "total": total,
                "has_more": (skip + limit) < total
            },
            "summary": {
                "patient_login_code": patient_login_code,
                "total_dialogs": total,
                "total_messages": sum(d.message_count for d in dialogs),
                "earliest_conversation": dialogs[-1].create_time.isoformat() if dialogs else None,
                "latest_conversation": dialogs[0].create_time.isoformat() if dialogs else None
            }
        }

    except Exception as e:
        logger.error(f"Error getting AI dialogs for {patient_login_code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ai-dialogs/{patient_login_code}/date-range")
def get_patient_ai_dialogs_by_date_range_endpoint(
        patient_login_code: str,
        db: Annotated[Connection, Depends(get_db)],
        start_date: datetime = Query(..., description="开始时间，格式: 2024-01-01T00:00:00"),
        end_date: datetime = Query(..., description="结束时间，格式: 2024-01-31T23:59:59"),
        include_context: bool = Query(True, description="是否包含上下文消息"),
        filter_type: str = Query("message_time",
                                 description="过滤类型: message_time(消息时间) 或 dialog_time(对话时间)"),
        detailed: bool = Query(False, description="是否返回详细消息"),

):
    """根据时间范围获取患者的AI对话历史记录"""
    try:
        # 确保日期范围合理
        if start_date > end_date:
            start_date, end_date = end_date, start_date

        if filter_type == "dialog_time":
            # 基于对话创建时间过滤
            dialogs = get_ai_dialogs_by_patient_and_date_range(
                db, patient_login_code, start_date, end_date
            )

            response_data = []
            for dialog in dialogs:
                dialog_info = {
                    "history_id": dialog.history_id,
                    "session_key": dialog.session_key,
                    "title": dialog.title,
                    "ai_model": dialog.ai_model,
                    "message_count": dialog.message_count,
                    "last_message_time": dialog.last_message_time.isoformat() if dialog.last_message_time else None,
                    "create_time": dialog.create_time.isoformat() if dialog.create_time else None,
                    "in_date_range": True
                }

                # 如果需要详细消息
                if detailed and dialog.prompts and 'messages' in dialog.prompts:
                    messages = dialog.prompts.get('messages', [])
                    dialog_info["messages"] = []

                    for msg in messages:
                        msg_time_str = msg.get('timestamp')
                        in_range = False

                        if msg_time_str:
                            try:
                                msg_time = datetime.fromisoformat(msg_time_str.replace('Z', '+00:00'))
                                in_range = start_date <= msg_time <= end_date
                            except (ValueError, TypeError):
                                pass

                        dialog_info["messages"].append({
                            "message": msg,
                            "in_date_range": in_range
                        })

                response_data.append(dialog_info)

            # 获取统计信息
            stats = get_conversation_statistics_enhanced(
                db, patient_login_code, start_date, end_date
            )

            return {
                "code": 200,
                "data": response_data,
                "total": len(response_data),
                "filter_type": filter_type,
                "date_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                },
                "statistics": stats.get('statistics', {}) if isinstance(stats, dict) else stats
            }

        else:  # 默认使用 message_time
            # 基于消息时间过滤
            filtered_data = get_filtered_messages_from_dialogs(
                db, patient_login_code, start_date, end_date, include_context
            )

            # 获取统计信息
            stats = get_conversation_statistics_enhanced(
                db, patient_login_code, start_date, end_date
            )

            return {
                "code": 200,
                "data": filtered_data,
                "total": len(filtered_data),
                "filter_type": filter_type,
                "date_range": {
                    "start": start_date.isoformat(),
                    "end": end_date.isoformat()
                },
                "statistics": stats.get('statistics', {}) if isinstance(stats, dict) else stats,
                "summary": {
                    "total_dialogs_with_messages": len(filtered_data),
                    "total_filtered_messages": sum(d.get('total_filtered', 0) for d in filtered_data)
                }
            }

    except Exception as e:
        logger.error(f"Error getting AI dialogs for {patient_login_code} in date range: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ai-dialogs/{patient_login_code}/statistics")
def get_patient_ai_dialogs_statistics(
        db: Annotated[Connection, Depends(get_db)],
        patient_login_code: str,
        start_date: Optional[datetime] = Query(None, description="开始时间"),
        end_date: Optional[datetime] = Query(None, description="结束时间"),

):
    """获取患者AI对话的详细统计信息"""
    try:

        # 如果没有提供日期范围，使用默认范围（最近30天）
        if not start_date or not end_date:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=30)

        # 获取基础统计
        all_dialogs = get_ai_dialogs_by_patient_login_code(db, patient_login_code)
        total_dialogs = len(all_dialogs)
        total_messages = sum(d.message_count for d in all_dialogs)

        # 获取时间范围内的增强统计
        range_stats = get_conversation_statistics_enhanced(
            db, patient_login_code, start_date, end_date
        )

        # 获取时间线数据
        timeline = get_message_timeline(
            db, patient_login_code, start_date, end_date, group_by='day'
        )

        return {
            "code": 200,
            "patient_login_code": patient_login_code,
            "date_range": {
                "start": start_date.isoformat(),
                "end": end_date.isoformat()
            },
            "overall_statistics": {
                "total_dialogs": total_dialogs,
                "total_messages": total_messages,
                "avg_messages_per_dialog": round(total_messages / total_dialogs, 2) if total_dialogs > 0 else 0,
                "earliest_conversation": all_dialogs[-1].create_time.isoformat() if all_dialogs else None,
                "latest_conversation": all_dialogs[0].create_time.isoformat() if all_dialogs else None
            },
            "range_statistics": range_stats.get('statistics', {}) if isinstance(range_stats, dict) else range_stats,
            "timeline": timeline
        }

    except Exception as e:
        logger.error(f"Error getting statistics for {patient_login_code}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/ai-dialogs/{patient_login_code}/search")
def search_patient_ai_dialogs(
        patient_login_code: str,
        db: Annotated[Connection, Depends(get_db)],
        start_date: Optional[datetime] = Query(None, description="开始时间"),
        end_date: Optional[datetime] = Query(None, description="结束时间"),
):
    """获取患者的AI对话消息（支持时间范围过滤）"""
    try:
        # 调用修改后的函数（已移除keyword参数）
        messages = search_messages_by_keyword(
            db=db,
            patient_login_code=patient_login_code,
            start_date=start_date,
            end_date=end_date,
        )

        # 按对话分组，便于前端展示
        conversations = {}
        for msg in messages:
            dialog_id = msg.get('dialog_id')
            if dialog_id not in conversations:
                conversations[dialog_id] = {
                    'conversation_id': dialog_id,
                    'session_key': msg.get('session_key'),
                    'title': msg.get('title'),
                    'create_time': msg.get('create_time'),
                    'messages': []
                }
            conversations[dialog_id]['messages'].append({
                'content': msg.get('message', {}).get('content', ''),
                'role': msg.get('message', {}).get('role'),
                'timestamp': msg.get('timestamp'),
                'model': msg.get('message', {}).get('model')
            })

        # 转换为列表并按时间排序
        conversation_list = list(conversations.values())
        conversation_list.sort(key=lambda x: x['create_time'] or '', reverse=True)

        # 统计信息
        total_messages = len(messages)
        total_conversations = len(conversation_list)

        # 按角色统计
        user_messages = [msg for msg in messages if msg.get('message', {}).get('role') == 'user']
        ai_messages = [msg for msg in messages if msg.get('message', {}).get('role') == 'assistant']

        return {
            "code": 200,
            "message": "查询成功",
            "data": {
                "patient_login_code": patient_login_code,
                "search_criteria": {
                    "date_range": {
                        "start": start_date.isoformat() if start_date else None,
                        "end": end_date.isoformat() if end_date else None
                    },
                    "time_filter_applied": start_date is not None or end_date is not None
                },
                "statistics": {
                    "total_conversations": total_conversations,
                    "total_messages": total_messages,
                    "user_messages": len(user_messages),
                    "ai_messages": len(ai_messages),
                    "earliest_message": messages[-1].get('timestamp') if messages else None,
                    "latest_message": messages[0].get('timestamp') if messages else None
                },
                "conversations": conversation_list,
                "raw_messages": messages  # 保留原始消息格式，便于不同用途
            }
        }

    except Exception as e:
        logger.error(f"Error searching dialogs for {patient_login_code}: {e}")
        return {
            "code": 500,
            "message": f"查询失败: {str(e)}",
            "data": None
        }

def get_validated_date(date_str: str) -> date:
    """验证日期字符串并返回 date 对象"""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail="日期格式无效，应为 YYYY-MM-DD"
        )

@router.get("/ai-dialogs/{patient_login_code}/date/{date_str}")
def get_patient_ai_dialogs_by_date(
        db: Annotated[Connection, Depends(get_db)],
        patient_login_code: str,
        date_str: str ,
        detailed: bool = Query(False, description="是否返回详细消息"),

):
    """获取患者指定日期的AI对话记录"""
    try:
        # 解析日期
        query_date = datetime.strptime(date_str, "%Y-%m-%d")

        # 获取当天的对话
        dialogs = get_ai_dialogs_by_patient_and_day(db, patient_login_code, query_date)

        # 获取统计信息
        start_of_day = query_date.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1) - timedelta(seconds=1)

        stats = get_conversation_statistics_enhanced(
            db, patient_login_code, start_of_day, end_of_day
        )

        response_data = []
        for dialog in dialogs:
            dialog_info = {
                "history_id": dialog.history_id,
                "session_key": dialog.session_key,
                "title": dialog.title,
                "ai_model": dialog.ai_model,
                "message_count": dialog.message_count,
                "last_message_time": dialog.last_message_time.isoformat() if dialog.last_message_time else None,
                "create_time": dialog.create_time.isoformat() if dialog.create_time else None
            }

            # 如果需要详细消息
            if detailed and dialog.prompts and 'messages' in dialog.prompts:
                messages = dialog.prompts.get('messages', [])
                dialog_info["messages"] = []

                for msg in messages:
                    msg_time_str = msg.get('timestamp')
                    is_today = False

                    if msg_time_str:
                        try:
                            msg_time = datetime.fromisoformat(msg_time_str.replace('Z', '+00:00'))
                            is_today = (msg_time.date() == query_date.date())
                        except (ValueError, TypeError):
                            pass

                    dialog_info["messages"].append({
                        "message": msg,
                        "is_today": is_today
                    })

            response_data.append(dialog_info)

        return {
            "code": 200,
            "date": date_str,
            "data": response_data,
            "total": len(response_data),
            "statistics": stats.get('statistics', {}) if isinstance(stats, dict) else stats
        }

    except ValueError:
        raise HTTPException(status_code=400, detail="日期格式错误，请使用YYYY-MM-DD格式")
    except Exception as e:
        logger.error(f"Error getting dialogs for {patient_login_code} on {date_str}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# @router.get("/ai-dialogs/detail/{history_id}")
# def get_ai_dialog_detail(
#         history_id: int,
#         db: Annotated[Connection, Depends(get_db)]
# ):
#     """获取AI对话的详细信息"""
#     try:
#
#         dialog = get_ai_dialog_by_id(db, history_id)
#         if not dialog:
#             raise HTTPException(status_code=404, detail="对话记录不存在")
#
#         # 构建详细响应
#         response = {
#             "history_id": dialog.history_id,
#             "patient_login_code": dialog.patient_login_code,
#             "session_key": dialog.session_key,
#             "title": dialog.title,
#             "ai_model": dialog.ai_model,
#             "message_count": dialog.message_count,
#             "last_message_time": dialog.last_message_time.isoformat() if dialog.last_message_time else None,
#             "create_time": dialog.create_time.isoformat() if dialog.create_time else None,
#             "update_time": dialog.update_time.isoformat() if dialog.update_time else None
#         }
#
#         # 添加消息内容
#         if dialog.prompts and 'messages' in dialog.prompts:
#             messages = dialog.prompts.get('messages', [])
#             response["messages"] = messages
#
#             # 添加消息统计
#             user_messages = [msg for msg in messages if msg.get('role') == 'user']
#             ai_messages = [msg for msg in messages if msg.get('role') == 'assistant']
#
#             response["message_statistics"] = {
#                 "total": len(messages),
#                 "user_messages": len(user_messages),
#                 "ai_messages": len(ai_messages),
#                 "user_first_message": user_messages[0].get('content', '') if user_messages else None,
#                 "user_last_message": user_messages[-1].get('content', '') if user_messages else None
#             }
#
#         return {
#             "code": 200,
#             "data": response
#         }
#
#     except HTTPException:
#         raise
#     except Exception as e:
#         logger.error(f"Error getting dialog detail {history_id}: {e}")
#         raise HTTPException(status_code=500, detail=str(e))


# 辅助函数，用于在需要时批量迁移现有对话
def migrate_existing_dialogs_to_ai_history(db: Connection):
    """
    将现有的session对话迁移到AI对话历史表中
    这是一个一次性迁移函数
    """
    try:

        # 获取所有已有的session
        old_sessions = db.query(OldSession).all()

        migrated_count = 0

        for old_session in old_sessions:
            # 获取这个session的所有查询
            queries = crud.get_queries_by_session(db, old_session.session_key)

            if not queries or len(queries) == 0:
                continue

            # 获取用户信息
            user = get_patient_by_login_code(db, str(old_session.user_id))
            if not user:
                continue

            # 为这个session创建AI对话记录
            ai_session_key = f"ai_migrated_{old_session.session_key}"

            # 按顺序处理每个查询
            for query in queries:
                if query.enquiry and query.response:
                    # 获取或创建AI对话
                    ai_dialog = get_or_create_ai_dialog(
                        db=db,
                        patient_login_code=user.login_code,
                        session_key=ai_session_key,
                        ai_model="gpt-3.5",  # 假设是旧模型
                        initial_message=query.enquiry
                    )

                    if ai_dialog:
                        # 更新对话
                        update_ai_dialog_with_message(
                            db=db,
                            session_key=ai_session_key,
                            user_message=query.enquiry,
                            ai_response=query.response,
                            ai_model="gpt-3.5"
                        )

                        migrated_count += 1
                        logger.info(f"Migrated query {query.query_id} to AI dialog history")

        logger.info(f"Migration completed: {migrated_count} queries migrated to AI dialog history")
        return migrated_count

    except Exception as e:
        logger.error(f"Error migrating existing dialogs: {e}")
        return 0