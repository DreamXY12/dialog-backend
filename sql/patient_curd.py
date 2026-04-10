# 病人相关的SQL操作

from sql.people_models import PatientAIDialogHistory
from sqlalchemy.orm import Session
from sql.people_models import Patient,Gender,SmokingStatus,DrinkingFrequency, FamilyHistory
from typing import Optional

from sqlalchemy import select
from datetime import datetime,timedelta
from sqlalchemy import text
import logging
import json

logger = logging.getLogger(__name__)


# 通过序号找患者，因为在创建患者时就把信息塞到token里面去了
def get_patient_by_id(db: Session, patient_id: int):
    return db.query(Patient).filter(Patient.patient_id == patient_id).first()

def get_patient_full_name(db: Session, patient_id: int) -> str|None:
    patient = get_patient_by_id(db, patient_id)
    if patient:
        return str(patient.full_name)
    return None

def get_patient_by_phone(db: Session, phone: str) -> Patient | None:
    """按手机号查询患者（核心函数）"""
    return db.query(Patient).filter(Patient.phone == phone).first()

def update_patient_record(db: Session, patient_id: int, update_data: dict):
    """更新患者信息（移除护士关联逻辑，仅处理患者基础信息）"""
    patient = get_patient_by_id(db, patient_id)
    if not patient:
        return None

    # 遍历更新字段（仅处理患者基础信息，移除护士相关逻辑）
    for key, value in update_data.items():
        if value is None or not hasattr(patient, key):
            continue

        try:
            # 1. 枚举字段转换（严格匹配模型枚举类）
            if key == "sex":
                patient.sex = Gender(value)
            elif key == "family_history":
                patient.family_history = FamilyHistory(value)
            elif key == "smoking_status":
                patient.smoking_status = SmokingStatus(value)
            elif key == "drinking_history":
                patient.drinking_history = DrinkingFrequency(value)
            # 2. 普通字段直接赋值（身高/体重/出生日期等）
            else:
                setattr(patient, key, value)

        except ValueError as e:
            # 枚举值不匹配时的友好提示
            print(f"字段 {key} 值 {value} 无效: {e}")
            continue
        except Exception as e:
            print(f"设置字段 {key} 出错: {e}")
            continue

    try:
        db.commit()
        db.refresh(patient)  # 恢复refresh，新模型枚举转换无问题
        return patient
    except Exception as e:
        db.rollback()
        print(f"更新患者记录失败: {str(e)}")
        return None

def get_ai_dialog_by_session_key(
        db: Session,
        session_key: str
) -> Optional[PatientAIDialogHistory]:
    """
    根据session_key获取AI对话记录
    """
    try:
        stmt = select(PatientAIDialogHistory).where(
            PatientAIDialogHistory.session_key == session_key
        )
        result = db.execute(stmt)
        return result.scalar()
    except Exception as e:
        print(f"Error fetching AI dialog by session key {session_key}: {e}")
        return None

def create_ai_dialog(
        db: Session,
        patient_phone: str,
        session_key: str,
        prompts: Optional[dict] = None,
        ai_model: Optional[str] = None,
        title: Optional[str] = None
) -> Optional[PatientAIDialogHistory]:
    """
    创建新的AI对话记录
    通常在用户开始与AI对话时调用
    """
    try:
        # 检查患者是否存在
        patient = get_patient_by_phone(db, patient_phone)
        if not patient:
            print(f"Patient with phone {patient_phone} not found")
            return None

        # 检查是否已存在相同session_key的对话
        existing_dialog = get_ai_dialog_by_session_key(db, session_key)
        if existing_dialog:
            print(f"Dialog with session_key {session_key} already exists")
            return existing_dialog

        # 计算消息数量
        message_count = 0
        if prompts and 'messages' in prompts:
            message_count = len(prompts['messages'])

        # 创建新的对话记录
        new_dialog = PatientAIDialogHistory(
            patient_phone=patient_phone,
            session_key=session_key,
            ai_model=ai_model or "default",  # 默认值
            title=title or f"与AI的对话 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            prompts=prompts,
            message_count=message_count,
            last_message_time=datetime.now()  # 设置最后消息时间为当前时间
        )

        db.add(new_dialog)
        db.commit()
        db.refresh(new_dialog)
        return new_dialog

    except Exception as e:
        db.rollback()
        print(f"Error creating AI dialog: {e}")
        return None

def get_or_create_ai_dialog(
        db: Session,
        patient_phone: str,
        session_key: str,
        ai_model: Optional[str] = None,
        initial_message: Optional[str] = None
) -> Optional[PatientAIDialogHistory]:
    """
       获取或创建AI对话记录
       如果对话已存在，返回现有对话；否则创建新对话
       """
    # 先尝试获取现有对话
    existing_dialog = get_ai_dialog_by_session_key(db, session_key)

    if existing_dialog:
        return existing_dialog  # 直接返回现有对话，不做修改

    # 如果不存在，创建新对话
    prompts = None
    if initial_message:
        prompts = {
            'messages': [{
                'role': 'user',
                'content': initial_message,
                'timestamp': datetime.now().isoformat()
            }]
        }

    return create_ai_dialog(
        db=db,
        patient_phone=patient_phone,
        session_key=session_key,
        prompts=prompts,
        ai_model=ai_model,
        title=f"对话 {datetime.now().strftime('%m-%d %H:%M')}"
    )

def get_ai_dialogs_by_patient_and_date_range(
        db: Session,
        patient_phone: str,
        start_date: datetime,
        end_date: datetime
) -> list[PatientAIDialogHistory]:
    """
    根据病人登录码和时间范围获取AI对话记录
    使用MySQL 8.0+ JSON函数，基于消息时间戳筛选

    参数：
    - patient_login_code: 病人登录码
    - start_date: 开始时间
    - end_date: 结束时间

    返回：在指定时间范围内有消息的所有对话
    """
    try:
        # 确保日期范围是合理的
        if start_date > end_date:
            start_date, end_date = end_date, start_date

        # 使用MySQL 8.0+的JSON_TABLE函数进行高效查询
        sql = """
              WITH filtered_dialogs AS (SELECT DISTINCT h.* \
                                        FROM patient_ai_dialog_history h, \
                                             JSON_TABLE( \
                                                     h.prompts, \
                                                     '$.messages[*]' COLUMNS (
                    msg_time DATETIME PATH '$.timestamp'
                ) \
                                             ) AS msgs \
                                        WHERE h.patient_phone = :patient_phone \
                                          AND h.prompts IS NOT NULL \
                                          AND JSON_LENGTH(h.prompts, '$.messages') > 0 \
                                          AND msgs.msg_time IS NOT NULL \
                                          AND msgs.msg_time BETWEEN :start_date AND :end_date)
              SELECT * \
              FROM filtered_dialogs
              ORDER BY create_time DESC \
              """

        result = db.execute(
            text(sql),
            {
                'patient_phone': patient_phone,
                'start_date': start_date,
                'end_date': end_date
            }
        )

        # 将结果映射到模型
        dialogs = []
        for row in result:
            dialog = PatientAIDialogHistory(
                history_id=row[0],
                patient_phone=row[1],
                session_key=row[2],
                ai_model=row[3],
                title=row[4],
                prompts=json.loads(row[5]) if row[5] else None,
                message_count=row[6],
                last_message_time=row[7],
                create_time=row[8],
                update_time=row[9]
            )
            dialogs.append(dialog)

        logger.info(
            f"Found {len(dialogs)} dialogs for patient {patient_phone} between {start_date} and {end_date}")
        return dialogs

    except Exception as e:
        logger.error(f"Error fetching AI dialogs for patient {patient_phone} in date range: {e}")
        return []

def get_ai_dialogs_by_patient_login_code(
        db: Session,
        patient_phone: str
) -> list[PatientAIDialogHistory]:
    """
    根据病人登录码获取所有AI对话记录，按创建时间由近到远排序
    """
    try:
        stmt = (
            select(PatientAIDialogHistory)
            .where(PatientAIDialogHistory.patient_phone == patient_phone)
            .order_by(PatientAIDialogHistory.create_time.desc())
        )
        result = db.execute(stmt)
        return result.scalars().all()
    except Exception as e:
        # 记录错误日志
        print(f"Error fetching AI dialogs for patient {patient_phone}: {e}")
        return []

def update_ai_dialog_with_message(
        db: Session,
        session_key: str,
        user_message: str,
        ai_response: str,
        ai_model: Optional[str] = None
) -> Optional[PatientAIDialogHistory]:
    """
    更新AI对话记录，添加新的消息对
    修复版：确保每次都能正确添加
    """
    try:
        dialog = get_ai_dialog_by_session_key(db, session_key)
        if not dialog:
            print(f"ERROR: Dialog with session_key {session_key} not found")
            return None

        print(f"DEBUG: Found dialog {session_key}, current message_count: {dialog.message_count}")

        # 获取或初始化prompts
        prompts = dialog.prompts
        if prompts is None:
            prompts = {'messages': []}
            print(f"DEBUG: Initialized empty prompts for {session_key}")

        # 确保messages存在
        if 'messages' not in prompts:
            prompts['messages'] = []
            print(f"DEBUG: Initialized messages array for {session_key}")

        messages = prompts['messages']
        print(f"DEBUG: Current messages count: {len(messages)}")

        # 打印最后一条消息（如果有）
        if messages:
            last_msg = messages[-1]
            print(f"DEBUG: Last message: role={last_msg.get('role')}, content={last_msg.get('content')[:50]}...")

        # 总是添加用户消息
        print(f"DEBUG: Adding user message: {user_message[:50]}...")
        messages.append({
            'role': 'user',
            'content': user_message,
            'timestamp': datetime.now().isoformat()
        })

        # 添加AI回复
        print(f"DEBUG: Adding AI response: {ai_response[:50]}...")
        messages.append({
            'role': 'assistant',
            'content': ai_response,
            'model': ai_model or dialog.ai_model or "default",
            'timestamp': datetime.now().isoformat()
        })

        # 更新对话记录
        dialog.prompts = prompts
        dialog.message_count = len(messages)
        dialog.last_message_time = datetime.now()

        print(f"DEBUG: After update - message_count: {dialog.message_count}")

        # 自动更新标题
        if dialog.message_count >= 4 and dialog.title and "对话" in dialog.title:
            # 尝试从用户消息生成更有意义的标题
            user_messages = [msg for msg in messages if msg.get('role') == 'user']
            if user_messages:
                first_user_msg = user_messages[0].get('content', '')[:30]
                if first_user_msg:
                    dialog.title = f"{first_user_msg}..."
                    print(f"DEBUG: Updated title to: {dialog.title}")

        db.commit()
        db.refresh(dialog)

        print(f"SUCCESS: Updated dialog {session_key}, now has {dialog.message_count} messages")
        return dialog

    except Exception as e:
        db.rollback()
        print(f"ERROR updating AI dialog {session_key}: {e}")
        import traceback
        traceback.print_exc()
        return None

def update_ai_dialog_with_message_simple(
        db: Session,
        session_key: str,
        user_message: str,
        ai_response: str,
        ai_model: Optional[str] = None
) -> Optional[PatientAIDialogHistory]:
    """
    最简单的方案：在Python中处理，然后更新
    """
    try:
        dialog = get_ai_dialog_by_session_key(db, session_key)
        if not dialog:
            print(f"Dialog {session_key} not found")
            return None

        print(f"Updating dialog {session_key}, current message_count: {dialog.message_count}")

        # 获取当前prompts
        prompts = dialog.prompts or {'messages': []}
        print("没有更新前的prompts:",prompts)

        # 获取当前prompts的副本
        if dialog.prompts:
            # 创建深拷贝，确保是新对象
            import copy
            prompts = copy.deepcopy(dialog.prompts)
        else:
            prompts = {'messages': []}

        # 确保messages存在
        # if 'messages' not in prompts:
        #     prompts['messages'] = []

        # 添加新消息
        prompts['messages'].append({
            'role': 'user',
            'content': user_message,
            'timestamp': datetime.now().isoformat()
        })

        prompts['messages'].append({
            'role': 'assistant',
            'content': ai_response,
            'model': ai_model or dialog.ai_model or "default",
            'timestamp': datetime.now().isoformat()
        })

        # 打印验证
        print(f"After adding, messages count: {len(prompts['messages'])}")
        print("更新后的prompts:", prompts)

        # 更新对象
        dialog.prompts = prompts
        dialog.message_count = len(prompts['messages'])
        dialog.last_message_time = datetime.now()

        # 尝试直接赋值，看看SQLAlchemy是否检测到变化
        from sqlalchemy import inspect
        inspector = inspect(dialog)
        if inspector.modified:
            print(f"SQLAlchemy detected changes: {inspector.modified}")
        else:
            print("WARNING: SQLAlchemy did not detect changes, forcing...")
            # 强制标记为已修改
            from sqlalchemy.orm.attributes import flag_modified
            flag_modified(dialog, "prompts")
        print(f"Has changes: {inspector.modified}")

        # 提交
        db.commit()
        print("Commit successful")

        # 刷新
        db.refresh(dialog)
        print(f"After refresh, message_count: {dialog.message_count}")

        return dialog

    except Exception as e:
        db.rollback()
        print(f"Error in simple update: {e}")
        import traceback
        traceback.print_exc()
        return None

def get_conversation_statistics_enhanced(
        db: Session,
        patient_phone: str,
        start_date: datetime,
        end_date: datetime
) -> dict:
    """
    获取增强的对话统计数据
    """
    try:
        sql = """
              WITH conversation_stats AS (SELECT h.history_id, \
                                                 h.session_key, \
                                                 h.title, \
                                                 h.create_time, \
                                                 h.message_count                                              as total_messages_in_dialog, \
                                                 COUNT(msgs.msg_data)                                         as messages_in_range, \
                                                 MIN(msgs.msg_time)                                           as first_msg_time, \
                                                 MAX(msgs.msg_time)                                           as last_msg_time, \
                                                 SUM(CASE WHEN msgs.msg_role = 'user' THEN 1 ELSE 0 END)      as user_messages, \
                                                 SUM(CASE WHEN msgs.msg_role = 'assistant' THEN 1 ELSE 0 END) as ai_messages \
                                          FROM patient_ai_dialog_history h \
                                                   LEFT JOIN JSON_TABLE( \
                                                  h.prompts, \
                                                  '$.messages[*]' COLUMNS (
                    msg_time DATETIME PATH '$.timestamp',
                    msg_role VARCHAR(20) PATH '$.role',
                    msg_data JSON PATH '$'
                ) \
                                                             ) AS msgs ON msgs.msg_time BETWEEN :start_date AND :end_date \
                                          WHERE h.patient_phone = :patient_phone \
                                            AND h.prompts IS NOT NULL \
                                          GROUP BY h.history_id, h.session_key, h.title, h.create_time, h.message_count \
                                          HAVING COUNT(msgs.msg_data) > 0),
                   summary_stats AS (SELECT COUNT(DISTINCT history_id) as total_dialogs, \
                                            SUM(messages_in_range)     as total_messages, \
                                            SUM(user_messages)         as total_user_messages, \
                                            SUM(ai_messages)           as total_ai_messages, \
                                            MIN(first_msg_time)        as overall_first_msg, \
                                            MAX(last_msg_time)         as overall_last_msg \
                                     FROM conversation_stats)
              SELECT * \
              FROM summary_stats \
              """

        result = db.execute(
            text(sql),
            {
                'patient_phone': patient_phone,
                'start_date': start_date,
                'end_date': end_date
            }
        ).fetchone()

        if result:
            total_dialogs, total_messages, user_msgs, ai_msgs, first_msg, last_msg = result

            return {
                'patient_phone': patient_phone,
                'date_range': {
                    'start': start_date.isoformat(),
                    'end': end_date.isoformat()
                },
                'statistics': {
                    'total_dialogs': total_dialogs or 0,
                    'total_messages': total_messages or 0,
                    'user_messages': user_msgs or 0,
                    'ai_messages': ai_msgs or 0,
                    'message_ratio': round(user_msgs / ai_msgs, 2) if ai_msgs > 0 else 0,
                    'first_message_time': first_msg.isoformat() if first_msg else None,
                    'last_message_time': last_msg.isoformat() if last_msg else None
                }
            }

        return {
            'patient_phone': patient_phone,
            'date_range': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'statistics': {
                'total_dialogs': 0,
                'total_messages': 0,
                'user_messages': 0,
                'ai_messages': 0,
                'message_ratio': 0,
                'first_message_time': None,
                'last_message_time': None
            }
        }

    except Exception as e:
        logger.error(f"Error getting enhanced statistics: {e}")
        return {
            'patient_phone': patient_phone,
            'error': str(e)
        }

def get_filtered_messages_from_dialogs(
        db: Session,
        patient_phone: str,
        start_date: datetime,
        end_date: datetime,
        include_context: bool = True
) -> list[dict]:
    """
    获取对话中在时间范围内的消息，可选包含上下文

    参数：
    - include_context: 是否包含时间范围前后的一条消息作为上下文

    返回格式：
    [
        {
            "dialog_id": 123,
            "session_key": "xxx",
            "title": "对话标题",
            "filtered_messages": [
                {
                    "message": {...},
                    "timestamp": "2024-01-15T10:00:00",
                    "in_range": true,
                    "context_before": {...},  # 可选
                    "context_after": {...}    # 可选
                }
            ]
        }
    ]
    """
    try:
        # 先获取符合条件的对话
        dialogs = get_ai_dialogs_by_patient_and_date_range(
            db, patient_phone, start_date, end_date
        )

        if not dialogs:
            return []

        result = []

        for dialog in dialogs:
            if not dialog.prompts or 'messages' not in dialog.prompts:
                continue

            messages = dialog.prompts.get('messages', [])
            filtered_messages_in_dialog = []

            for i, message in enumerate(messages):
                msg_time_str = message.get('timestamp')
                if not msg_time_str:
                    continue

                try:
                    msg_time = datetime.fromisoformat(msg_time_str.replace('Z', '+00:00'))

                    if start_date <= msg_time <= end_date:
                        filtered_msg = {
                            "message": message,
                            "timestamp": msg_time_str,
                            "in_range": True,
                            "message_index": i
                        }

                        # 添加上下文
                        if include_context:
                            if i > 0:
                                prev_msg = messages[i - 1]
                                filtered_msg["context_before"] = {
                                    "message": prev_msg,
                                    "timestamp": prev_msg.get('timestamp'),
                                    "type": "context"
                                }

                            if i < len(messages) - 1:
                                next_msg = messages[i + 1]
                                filtered_msg["context_after"] = {
                                    "message": next_msg,
                                    "timestamp": next_msg.get('timestamp'),
                                    "type": "context"
                                }

                        filtered_messages_in_dialog.append(filtered_msg)

                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to parse timestamp {msg_time_str}: {e}")
                    continue

            if filtered_messages_in_dialog:
                result.append({
                    "dialog_id": dialog.history_id,
                    "session_key": dialog.session_key,
                    "title": dialog.title,
                    "create_time": dialog.create_time.isoformat() if dialog.create_time else None,
                    "last_message_time": dialog.last_message_time.isoformat() if dialog.last_message_time else None,
                    "message_count": dialog.message_count,
                    "filtered_messages": filtered_messages_in_dialog,
                    "total_filtered": len(filtered_messages_in_dialog)
                })

        return result

    except Exception as e:
        logger.error(f"Error getting filtered messages: {e}")
        return []

def get_message_timeline(
        db: Session,
        patient_phone: str,
        start_date: datetime,
        end_date: datetime,
        group_by: str = 'day'  # 'day', 'hour', 'week', 'month'
) -> list[dict]:
    """
    获取消息时间线统计
    修正版：处理可能的空值和优化分组
    """
    try:
        # 验证group_by参数
        valid_groups = ['hour', 'day', 'week', 'month']
        if group_by not in valid_groups:
            group_by = 'day'
            logger.warning(f"Invalid group_by '{group_by}', defaulting to 'day'")

        # 根据分组类型设置SQL
        if group_by == 'hour':
            group_sql = "DATE_FORMAT(msgs.msg_time, '%Y-%m-%d %H:00')"
            label_format = '%Y-%m-%d %H:00'
        elif group_by == 'week':
            group_sql = "DATE_FORMAT(msgs.msg_time, '%Y-%u')"
            label_format = '%Y-W%U'
        elif group_by == 'month':
            group_sql = "DATE_FORMAT(msgs.msg_time, '%Y-%m')"
            label_format = '%Y-%m'
        else:  # day
            group_sql = "DATE(msgs.msg_time)"
            label_format = '%Y-%m-%d'

        sql = f"""
        WITH message_data AS (
            SELECT 
                msgs.msg_time,
                msgs.msg_role
            FROM patient_ai_dialog_history h,
            JSON_TABLE(
                h.prompts,
                '$.messages[*]' COLUMNS (
                    msg_time DATETIME PATH '$.timestamp',
                    msg_role VARCHAR(20) PATH '$.role'
                )
            ) AS msgs
            WHERE h.patient_phone = :patient_phone
            AND h.prompts IS NOT NULL
            AND JSON_TYPE(h.prompts) = 'OBJECT'
            AND JSON_CONTAINS_PATH(h.prompts, 'one', '$.messages')
            AND msgs.msg_time IS NOT NULL
            AND msgs.msg_time BETWEEN :start_date AND :end_date
        )
        SELECT 
            {group_sql} as time_period,
            msg_role,
            COUNT(*) as message_count
        FROM message_data
        WHERE msg_time IS NOT NULL
        GROUP BY {group_sql}, msg_role
        ORDER BY time_period
        """

        result = db.execute(
            text(sql),
            {
                'patient_phone': patient_phone,
                'start_date': start_date,
                'end_date': end_date
            }
        )

        timeline = []
        for row in result:
            time_period, role, count = row

            # 确保时间格式统一
            if time_period:
                if group_by == 'week' and isinstance(time_period, str):
                    # 处理周格式
                    year_week = time_period.split('-')
                    if len(year_week) == 2:
                        year, week = year_week
                        time_period = f"{year}-W{int(week):02d}"

            timeline.append({
                'time_period': str(time_period) if time_period else None,
                'role': role,
                'count': count
            })

        logger.info(f"Generated timeline with {len(timeline)} data points for patient {patient_phone}")
        return timeline

    except Exception as e:
        logger.error(f"Error getting message timeline: {e}")
        return []

def search_messages_by_keyword(
        db: Session,
        patient_phone: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
) -> list[dict]:
    """
    在指定时间范围内获取所有消息
    修改：移除了keyword参数，改为获取所有消息
    """
    try:
        # 基础SQL
        sql = """
              SELECT h.history_id, \
                     h.session_key, \
                     h.title, \
                     h.create_time, \
                     msgs.msg_data as message, \
                     msgs.msg_time
              FROM ai_dialog_history h,
                   JSON_TABLE(
                           h.prompts,
                           '$.messages[*]' COLUMNS (
                msg_time DATETIME PATH '$.timestamp',
                msg_role VARCHAR(20) PATH '$.role',
                msg_content TEXT PATH '$.content',
                msg_data JSON PATH '$'
            )
                   ) AS msgs
              WHERE h.patient_phone = :patient_phone
                AND h.prompts IS NOT NULL \
              """

        params = {'patient_phone': patient_phone}

        # 添加时间范围条件
        if start_date:
            sql += " AND msgs.msg_time >= :start_date"
            params['start_date'] = start_date

        if end_date:
            sql += " AND msgs.msg_time <= :end_date"
            params['end_date'] = end_date

        sql += " ORDER BY msgs.msg_time DESC"

        result = db.execute(text(sql), params)

        search_results = []
        for row in result:
            history_id, session_key, title, create_time, message_data, msg_time = row

            # 解析消息数据
            message = None
            if message_data:
                try:
                    if isinstance(message_data, str):
                        message = json.loads(message_data)
                    else:
                        message = message_data
                except (json.JSONDecodeError, TypeError):
                    message = {"error": "Failed to parse message data"}

            search_results.append({
                'dialog_id': history_id,
                'session_key': session_key,
                'title': title,
                'create_time': create_time.isoformat() if create_time else None,
                'message': message,
                'timestamp': msg_time.isoformat() if msg_time else None
            })

        logger.info(f"Found {len(search_results)} messages for patient {patient_phone}")
        return search_results

    except Exception as e:
        logger.error(f"Error getting messages: {e}")
        return []

def get_ai_dialogs_by_patient_and_day(
        db: Session,
        patient_login_code: str,
        query_date: datetime
) -> list[PatientAIDialogHistory]:
    """
    根据病人登录码和具体日期获取当天的AI对话记录
    使用MySQL 8.0+ JSON函数优化查询
    """
    start_of_day = query_date.replace(hour=0, minute=0, second=0, microsecond=0)
    end_of_day = start_of_day + timedelta(days=1) - timedelta(seconds=1)

    return get_ai_dialogs_by_patient_and_date_range(
        db, patient_login_code, start_of_day, end_of_day
    )