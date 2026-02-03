from sqlalchemy import select, update, desc, func
from sqlalchemy.orm import Session as Connection
from typing import Optional, List,cast
from sql.login_models import LoginCode, Nurse, Patient
import random
from passlib.context import CryptContext
from sqlalchemy.sql.expression import func
from datetime import datetime, timedelta
from sqlalchemy import and_
from sql.login_models import PatientAIDialogHistory
from sql.schemas import AIDialogHistoryCreate


# 密码哈希
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

'''密码相关'''


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """获取密码哈希"""
    return pwd_context.hash(password)


'''登录码操作'''


def generate_unique_login_code(db: Connection, max_attempts: int = 100) -> str:
    """生成唯一的4位登录码"""
    attempts = 0

    while attempts < max_attempts:
        code = f"{random.randint(1000, 9999)}"

        # 检查代码是否已存在
        existing = db.query(LoginCode).filter(LoginCode.code == code).first()
        if not existing:
            return code

        attempts += 1

    # 如果无法生成唯一的4位代码，尝试生成5位
    for _ in range(max_attempts):
        code = f"{random.randint(10000, 99999)}"
        existing = db.query(LoginCode).filter(LoginCode.code == code).first()
        if not existing:
            return code

    raise RuntimeError("无法生成唯一的登录码")


def create_login_code(db: Connection, user_type: Optional[str] = None) -> LoginCode:
    """创建新的登录码"""
    code = generate_unique_login_code(db)

    login_code = LoginCode(
        code=code,
        user_type=user_type,
        is_used=False
    )

    db.add(login_code)
    try:
        db.commit()
        return login_code
    except Exception as e:
        db.rollback()
        raise e


def get_login_code_by_code(db: Connection, code: str) -> Optional[LoginCode]:
    """通过代码获取登录码"""
    return db.query(LoginCode).filter(LoginCode.code == code).first()


def mark_login_code_as_used(db: Connection, code: str, user_type: str) -> bool:
    """标记登录码为已使用"""
    login_code = get_login_code_by_code(db, code)
    if not login_code or login_code.is_used:
        return False

    login_code.is_used = True
    login_code.user_type = user_type
    login_code.used_at = func.now()

    try:
        db.commit()
        return True
    except Exception as e:
        db.rollback()
        return False


'''护士操作'''


def get_nurse_by_login_code(db: Connection, login_code: str) -> Optional[Nurse]:
    """通过登录码获取护士"""
    return db.query(Nurse).filter(Nurse.login_code == login_code).first()


def get_nurse_by_id(db: Connection, nurse_id: int) -> Optional[Nurse]:
    """通过ID获取护士"""
    return db.query(Nurse).filter(Nurse.nurse_id == nurse_id).first()


def get_all_nurses(db: Connection, skip: int = 0, limit: int = 100) -> List[Nurse]:
    """获取所有护士"""
    stmt = select(Nurse).offset(skip).limit(limit)
    result = db.execute(stmt).scalars().all()
    return list(result)
    return db.query(Nurse).offset(skip).limit(limit).all()


def create_nurse(db: Connection, login_code: str, first_name: str, last_name: str, password: str) -> Optional[Nurse]:
    """创建护士"""
    # 检查登录码是否可用
    login_code_obj = get_login_code_by_code(db, login_code)
    if not login_code_obj or login_code_obj.is_used:
        return None

    # 创建护士
    nurse = Nurse(
        login_code=login_code,
        first_name=first_name,
        last_name=last_name,
        hashed_password=get_password_hash(password)
    )

    db.add(nurse)
    try:
        db.commit()
        # 标记登录码为已使用
        mark_login_code_as_used(db, login_code, "nurse")
        return nurse
    except Exception as e:
        db.rollback()
        raise e


'''患者操作'''


def get_patient_by_login_code(db: Connection, login_code: str) -> Optional[Patient]:
    """通过登录码获取患者"""
    return db.query(Patient).filter(Patient.login_code == login_code).first()


def verify_patient_assigned_to_nurse_by_login_code(db: Connection, patient_login_code: str, nurse_login_code: str) -> \
Optional[Patient]:
    """
    通过登录码验证患者是否确实被指定护士管理

    参数:
    - db: 数据库连接
    - patient_login_code: 患者登录码
    - nurse_login_code: 护士登录码

    返回: 如果验证通过返回患者对象，否则返回None
    """
    try:
        patient = db.query(Patient).filter(
            Patient.login_code == patient_login_code,
            Patient.assigned_nurse_id == nurse_login_code
        ).first()

        return patient
    except Exception as e:
        print(f"Error verifying patient assignment by login code: {e}")
        return None


def assign_patient_to_nurse_by_login_code(db: Connection, patient_login_code: str, nurse_login_code: str) -> Optional[
    Patient]:
    """
    通过登录码将患者分配给护士

    参数:
    - db: 数据库连接
    - patient_login_code: 患者登录码
    - nurse_login_code: 护士登录码

    返回: 更新后的患者对象，失败返回None
    """
    try:
        # 获取患者
        patient = get_patient_by_login_code(db, patient_login_code)
        if not patient:
            print(f"Patient with login_code {patient_login_code} not found")
            return None

        # 如果已经是这个护士的患者，直接返回
        if patient.assigned_nurse_id == nurse_login_code:
            return patient

        # 检查护士是否存在
        nurse = db.query(Nurse).filter(Nurse.login_code == nurse_login_code).first()
        if not nurse:
            print(f"Nurse with login_code {nurse_login_code} not found")
            return None

        # 更新患者的护士分配
        patient.assigned_nurse_id = nurse_login_code

        try:
            db.commit()
            db.refresh(patient)
            return patient
        except Exception as e:
            db.rollback()
            print(f"Error assigning patient to nurse by login code: {e}")
            return None

    except Exception as e:
        print(f"Error in assign_patient_to_nurse_by_login_code: {e}")
        return None


def unassign_patient_from_specific_nurse_by_login_code(db: Connection, patient_login_code: str,
                                                       nurse_login_code: str) -> Optional[Patient]:
    """
    通过登录码解除患者与特定护士的分配关系

    参数:
    - db: 数据库连接
    - patient_login_code: 患者登录码
    - nurse_login_code: 护士登录码

    返回: 更新后的患者对象，失败返回None
    """
    try:
        # 先验证患者是否属于这个护士
        patient = verify_patient_assigned_to_nurse_by_login_code(db, patient_login_code, nurse_login_code)
        if not patient:
            print(f"Patient {patient_login_code} is not assigned to nurse {nurse_login_code}")
            return None

        # 解除分配
        patient.assigned_nurse_id = None

        try:
            db.commit()
            db.refresh(patient)
            return patient
        except Exception as e:
            db.rollback()
            print(f"Error unassigning patient from specific nurse by login code: {e}")
            return None

    except Exception as e:
        print(f"Error in unassign_patient_from_specific_nurse_by_login_code: {e}")
        return None


def unassign_patient_from_nurse_by_login_code(db: Connection, patient_login_code: str) -> Optional[Patient]:
    """
    通过登录码解除患者与护士的分配关系（不验证具体护士）

    参数:
    - db: 数据库连接
    - patient_login_code: 患者登录码

    返回: 更新后的患者对象，失败返回None
    """
    try:
        # 获取患者
        patient = get_patient_by_login_code(db, patient_login_code)
        if not patient:
            print(f"Patient with login_code {patient_login_code} not found")
            return None

        # 如果患者本来就没有分配护士，直接返回
        if not patient.assigned_nurse_id:
            return patient

        # 解除分配
        patient.assigned_nurse_id = None

        try:
            db.commit()
            db.refresh(patient)
            return patient
        except Exception as e:
            db.rollback()
            print(f"Error unassigning patient from nurse by login code: {e}")
            return None

    except Exception as e:
        print(f"Error in unassign_patient_from_nurse_by_login_code: {e}")
        return None


def get_patients_without_nurse_paginated_by_login_codes(
        db: Connection,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None
) -> dict:
    """
    分页获取没有分配护士的患者（包含登录码信息），支持搜索
    """
    try:
        # 计算偏移量
        skip = (page - 1) * page_size

        # 获取患者数据
        if search:
            patients = get_patients_without_nurse_by_search(db, search, skip, page_size)
            total_count = get_patients_without_nurse_by_search_count(db, search)
        else:
            patients = get_patients_without_nurse(db, skip, page_size)
            total_count = get_patients_without_nurse_count(db)

        # 转换为响应格式
        patients_data = []
        for patient in patients:
            # 计算年龄
            age = None
            if patient.date_of_birth:
                from datetime import date
                today = date.today()
                age = today.year - patient.date_of_birth.year
                if (today.month, today.day) < (patient.date_of_birth.month, patient.date_of_birth.day):
                    age -= 1

            # 计算BMI
            bmi = None
            if patient.height and patient.weight and patient.height > 0:
                height_m = patient.height / 100
                bmi = patient.weight / (height_m * height_m)
                bmi = round(bmi, 2)

            patients_data.append({
                "patient_id": patient.patient_id,
                "login_code": patient.login_code,
                "first_name": patient.first_name,
                "last_name": patient.last_name,
                "full_name": patient.full_name,
                "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
                "age": age,
                "sex": patient.sex,
                "family_history": patient.family_history,
                "smoking_status": patient.smoking_status,
                "drinking_history": patient.drinking_history,
                "height": float(patient.height) if patient.height else None,
                "weight": float(patient.weight) if patient.weight else None,
                "bmi": bmi,
                "assigned_nurse_id": patient.assigned_nurse_id,
                "create_time": patient.create_time.isoformat() if patient.create_time else None,
                "update_time": patient.update_time.isoformat() if patient.update_time else None
            })

        return {
            "patients": patients_data,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": (total_count + page_size - 1) // page_size if total_count > 0 else 0
            }
        }
    except Exception as e:
        print(f"Error in get_patients_without_nurse_paginated_by_login_codes: {e}")
        return {
            "patients": [],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_count": 0,
                "total_pages": 0
            }
        }


def get_patient_by_id(db: Connection, patient_id: int) -> Optional[Patient]:
    """通过ID获取患者"""
    return db.query(Patient).filter(Patient.patient_id == patient_id).first()


def get_all_patients(db: Connection, skip: int = 0, limit: int = 100) -> List[Patient]:
    """获取所有患者"""
    stmt = select(Patient).offset(skip).limit(limit)
    result = db.execute(stmt).scalars().all()
    return list(result)


def get_patients_by_nurse(db: Connection, nurse_login_code: str) -> List[Patient]:
    """获取指定护士的患者 - 改为通过护士login_code查询"""
    stmt = select(Patient).where(Patient.assigned_nurse_id == nurse_login_code)
    result = db.execute(stmt).scalars().all()
    return list(result)


def create_patient(db: Connection, login_code: str, first_name: str, last_name: str, password: str,
                   assigned_nurse_id: Optional[str] = None) -> Optional[Patient]:
    """创建患者 - 修改护士ID参数类型"""
    # 检查登录码是否可用
    login_code_obj = get_login_code_by_code(db, login_code)
    if not login_code_obj or login_code_obj.is_used:
        return None

    # 如果指定了护士，检查护士是否存在
    if assigned_nurse_id:
        # 改为通过护士login_code查询
        nurse = db.query(Nurse).filter(Nurse.login_code == assigned_nurse_id).first()
        if not nurse:
            return None

    # 创建患者
    patient = Patient(
        login_code=login_code,
        first_name=first_name,
        last_name=last_name,
        hashed_password=get_password_hash(password),
        assigned_nurse_id=assigned_nurse_id
    )

    db.add(patient)
    try:
        db.commit()
        # 标记登录码为已使用
        mark_login_code_as_used(db, login_code, "patient")
        return patient
    except Exception as e:
        db.rollback()
        raise e


def update_patient(db: Connection, patient_id: int, **kwargs) -> Optional[Patient]:
    """更新患者信息 - 修改护士检查逻辑"""
    patient = get_patient_by_id(db, patient_id)
    if not patient:
        return None

    # 如果指定了护士，检查护士是否存在
    if 'assigned_nurse_id' in kwargs and kwargs['assigned_nurse_id'] is not None:
        nurse_login_code = kwargs['assigned_nurse_id']
        if nurse_login_code == "":  # 设置为空
            patient.assigned_nurse_id = None
        else:
            # 改为通过护士login_code查询
            nurse = db.query(Nurse).filter(Nurse.login_code == nurse_login_code).first()
            if not nurse:
                return None
            patient.assigned_nurse_id = nurse_login_code
        kwargs.pop('assigned_nurse_id')

    # 更新其他字段
    for key, value in kwargs.items():
        if hasattr(patient, key) and value is not None:
            setattr(patient, key, value)

    try:
        db.commit()
        return patient
    except Exception as e:
        db.rollback()
        raise e

'''认证操作'''


def authenticate_user(db: Connection, login_code: str, password: str) -> Optional[object]:
    """认证用户，先尝试患者，再尝试护士"""
    # 尝试患者
    patient = get_patient_by_login_code(db, login_code)
    if patient and verify_password(password, patient.hashed_password):
        return patient

    # 尝试护士
    nurse = get_nurse_by_login_code(db, login_code)
    if nurse and verify_password(password, nurse.hashed_password):
        return nurse

    return None




# 在文件末尾添加以下函数
def get_ai_dialogs_by_patient_login_code(
        db: Connection,
        patient_login_code: str
) -> list[PatientAIDialogHistory]:
    """
    根据病人登录码获取所有AI对话记录，按创建时间由近到远排序
    """
    try:
        stmt = (
            select(PatientAIDialogHistory)
            .where(PatientAIDialogHistory.patient_login_code == patient_login_code)
            .order_by(PatientAIDialogHistory.create_time.desc())
        )
        result = db.execute(stmt)
        return result.scalars().all()
    except Exception as e:
        # 记录错误日志
        print(f"Error fetching AI dialogs for patient {patient_login_code}: {e}")
        return []


from sqlalchemy import text
from datetime import datetime, timedelta
import json
import logging

logger = logging.getLogger(__name__)


def get_ai_dialogs_by_patient_and_date_range(
        db: Connection,
        patient_login_code: str,
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
                                        WHERE h.patient_login_code = :patient_code \
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
                'patient_code': patient_login_code,
                'start_date': start_date,
                'end_date': end_date
            }
        )

        # 将结果映射到模型
        dialogs = []
        for row in result:
            dialog = PatientAIDialogHistory(
                history_id=row[0],
                patient_login_code=row[1],
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
            f"Found {len(dialogs)} dialogs for patient {patient_login_code} between {start_date} and {end_date}")
        return dialogs

    except Exception as e:
        logger.error(f"Error fetching AI dialogs for patient {patient_login_code} in date range: {e}")
        return []


def get_ai_dialogs_by_patient_and_day(
        db: Connection,
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


def get_filtered_messages_from_dialogs(
        db: Connection,
        patient_login_code: str,
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
            db, patient_login_code, start_date, end_date
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


def get_conversation_statistics_by_date_range_sql(
        db: Connection,
        patient_login_code: str,
        start_date: datetime,
        end_date: datetime
) -> dict:
    """
    使用SQL直接统计时间范围内的对话情况
    更高效，减少数据传输
    """
    try:
        sql = """
              SELECT COUNT(DISTINCT h.history_id) as total_dialogs, \
                     COUNT(msgs.msg_data)         as total_messages, DATE (msgs.msg_time) as message_date, HOUR (msgs.msg_time) as message_hour, msgs.msg_role, COUNT (*) as count_per_hour
              FROM patient_ai_dialog_history h, JSON_TABLE(
                  h.prompts, '$.messages[*]' COLUMNS (
                  msg_time DATETIME PATH '$.timestamp', msg_role VARCHAR (20) PATH '$.role', msg_data JSON PATH '$'
                  )
                  ) AS msgs
              WHERE h.patient_login_code = :patient_code
                AND h.prompts IS NOT NULL
                AND msgs.msg_time IS NOT NULL
                AND msgs.msg_time BETWEEN :start_date \
                AND :end_date
              GROUP BY DATE (msgs.msg_time), HOUR (msgs.msg_time), msgs.msg_role
              ORDER BY message_date, message_hour \
              """

        result = db.execute(
            text(sql),
            {
                'patient_code': patient_login_code,
                'start_date': start_date,
                'end_date': end_date
            }
        )

        stats = {
            'patient_login_code': patient_login_code,
            'date_range': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'total_dialogs': 0,
            'total_messages': 0,
            'messages_by_date': {},
            'messages_by_hour': {},
            'user_messages': 0,
            'ai_messages': 0,
            'detailed_stats': []
        }

        for row in result:
            total_dialogs, total_msgs, msg_date, msg_hour, msg_role, count = row

            if msg_date:
                date_key = msg_date.isoformat() if hasattr(msg_date, 'isoformat') else str(msg_date)
                stats['messages_by_date'][date_key] = stats['messages_by_date'].get(date_key, 0) + count

            if msg_hour is not None:
                hour_key = f"{int(msg_hour):02d}:00"
                stats['messages_by_hour'][hour_key] = stats['messages_by_hour'].get(hour_key, 0) + count

            if msg_role == 'user':
                stats['user_messages'] += count
            elif msg_role == 'assistant':
                stats['ai_messages'] += count

            stats['detailed_stats'].append({
                'date': date_key if msg_date else None,
                'hour': msg_hour,
                'role': msg_role,
                'count': count
            })

        # 汇总总数
        stats['total_messages'] = sum(row[5] for row in result) if result.rowcount > 0 else 0

        # 获取唯一的对话数
        count_sql = """
                    SELECT COUNT(DISTINCT h.history_id)
                    FROM patient_ai_dialog_history h,
                         JSON_TABLE(
                                 h.prompts,
                                 '$.messages[*]' COLUMNS (
                msg_time DATETIME PATH '$.timestamp'
            )
                         ) AS msgs
                    WHERE h.patient_login_code = :patient_code
                      AND msgs.msg_time BETWEEN :start_date AND :end_date \
                    """

        count_result = db.execute(
            text(count_sql),
            {
                'patient_code': patient_login_code,
                'start_date': start_date,
                'end_date': end_date
            }
        ).scalar()

        stats['total_dialogs'] = count_result or 0

        # 计算最活跃的时间段
        if stats['messages_by_hour']:
            most_active = max(stats['messages_by_hour'].items(), key=lambda x: x[1])
            stats['most_active_hour'] = {
                'hour': most_active[0],
                'count': most_active[1]
            }

        if stats['messages_by_date']:
            most_active_date = max(stats['messages_by_date'].items(), key=lambda x: x[1])
            stats['most_active_date'] = {
                'date': most_active_date[0],
                'count': most_active_date[1]
            }

        return stats

    except Exception as e:
        logger.error(f"Error getting conversation statistics via SQL: {e}")
        # 回退到Python版本
        return get_conversation_statistics_by_date_range_python(db, patient_login_code, start_date, end_date)


def get_conversation_statistics_by_date_range_python(
        db: Connection,
        patient_login_code: str,
        start_date: datetime,
        end_date: datetime
) -> dict:
    """
    Python版本的统计函数，作为SQL版本的备选
    """
    try:
        # 先获取所有符合条件的消息
        dialogs = get_ai_dialogs_by_patient_and_date_range(
            db, patient_login_code, start_date, end_date
        )

        stats = {
            'patient_login_code': patient_login_code,
            'date_range': {
                'start': start_date.isoformat(),
                'end': end_date.isoformat()
            },
            'total_dialogs': len(dialogs),
            'total_messages': 0,
            'messages_by_date': {},
            'messages_by_hour': {},
            'user_messages': 0,
            'ai_messages': 0
        }

        for dialog in dialogs:
            if not dialog.prompts or 'messages' not in dialog.prompts:
                continue

            for message in dialog.prompts.get('messages', []):
                msg_time_str = message.get('timestamp')
                if not msg_time_str:
                    continue

                try:
                    msg_time = datetime.fromisoformat(msg_time_str.replace('Z', '+00:00'))

                    if start_date <= msg_time <= end_date:
                        stats['total_messages'] += 1

                        if message.get('role') == 'user':
                            stats['user_messages'] += 1
                        elif message.get('role') == 'assistant':
                            stats['ai_messages'] += 1

                        date_key = msg_time.date().isoformat()
                        stats['messages_by_date'][date_key] = stats['messages_by_date'].get(date_key, 0) + 1

                        hour_key = f"{msg_time.hour:02d}:00"
                        stats['messages_by_hour'][hour_key] = stats['messages_by_hour'].get(hour_key, 0) + 1

                except (ValueError, TypeError):
                    continue

        return stats

    except Exception as e:
        logger.error(f"Error in Python statistics: {e}")
        return {
            'patient_login_code': patient_login_code,
            'error': str(e)
        }

#终极版本
def search_messages_by_keyword(
        db: Connection,
        patient_login_code: str,
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
              WHERE h.patient_login_code = :patient_code
                AND h.prompts IS NOT NULL \
              """

        params = {'patient_code': patient_login_code}

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

        logger.info(f"Found {len(search_results)} messages for patient {patient_login_code}")
        return search_results

    except Exception as e:
        logger.error(f"Error getting messages: {e}")
        return []


def get_message_timeline(
        db: Connection,
        patient_login_code: str,
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
            WHERE h.patient_login_code = :patient_code
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
                'patient_code': patient_login_code,
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

        logger.info(f"Generated timeline with {len(timeline)} data points for patient {patient_login_code}")
        return timeline

    except Exception as e:
        logger.error(f"Error getting message timeline: {e}")
        return []


def get_conversation_statistics_enhanced(
        db: Connection,
        patient_login_code: str,
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
                                          WHERE h.patient_login_code = :patient_code \
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
                'patient_code': patient_login_code,
                'start_date': start_date,
                'end_date': end_date
            }
        ).fetchone()

        if result:
            total_dialogs, total_messages, user_msgs, ai_msgs, first_msg, last_msg = result

            return {
                'patient_login_code': patient_login_code,
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
            'patient_login_code': patient_login_code,
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
            'patient_login_code': patient_login_code,
            'error': str(e)
        }


def search_messages_with_pagination(
        db: Connection,
        patient_login_code: str,
        keyword: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        page: int = 1,
        page_size: int = 20
) -> dict:
    """
    分页搜索消息
    """
    try:
        # 计算偏移量
        offset = (page - 1) * page_size

        # 计数查询
        count_sql = """
                    SELECT COUNT(*) as total
                    FROM patient_ai_dialog_history h,
                         JSON_TABLE(
                                 h.prompts,
                                 '$.messages[*]' COLUMNS (
                msg_time DATETIME PATH '$.timestamp',
                msg_content TEXT PATH '$.content',
                msg_data JSON PATH '$'
            )
                         ) AS msgs
                    WHERE h.patient_login_code = :patient_code
                      AND h.prompts IS NOT NULL
                      AND msgs.msg_content LIKE :keyword \
                    """

        count_params = {
            'patient_code': patient_login_code,
            'keyword': f'%{keyword}%'
        }

        if start_date:
            count_sql += " AND msgs.msg_time >= :start_date"
            count_params['start_date'] = start_date

        if end_date:
            count_sql += " AND msgs.msg_time <= :end_date"
            count_params['end_date'] = end_date

        count_result = db.execute(text(count_sql), count_params).scalar()
        total_count = count_result or 0

        # 如果总数大于0，获取数据
        if total_count > 0:
            data_sql = """
                       SELECT h.history_id, \
                              h.session_key, \
                              h.title, \
                              msgs.msg_data as message, \
                              msgs.msg_time
                       FROM patient_ai_dialog_history h,
                            JSON_TABLE(
                                    h.prompts,
                                    '$.messages[*]' COLUMNS (
                    msg_time DATETIME PATH '$.timestamp',
                    msg_content TEXT PATH '$.content',
                    msg_data JSON PATH '$'
                )
                            ) AS msgs
                       WHERE h.patient_login_code = :patient_code
                         AND h.prompts IS NOT NULL
                         AND msgs.msg_content LIKE :keyword \
                       """

            data_params = {
                'patient_code': patient_login_code,
                'keyword': f'%{keyword}%',
                'limit': page_size,
                'offset': offset
            }

            if start_date:
                data_sql += " AND msgs.msg_time >= :start_date"
                data_params['start_date'] = start_date

            if end_date:
                data_sql += " AND msgs.msg_time <= :end_date"
                data_params['end_date'] = end_date

            data_sql += " ORDER BY msgs.msg_time DESC LIMIT :limit OFFSET :offset"

            result = db.execute(text(data_sql), data_params)

            search_results = []
            for row in result:
                history_id, session_key, title, message_data, msg_time = row

                # 解析消息
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
                    'message': message,
                    'timestamp': msg_time.isoformat() if msg_time else None
                })
        else:
            search_results = []

        return {
            'patient_login_code': patient_login_code,
            'keyword': keyword,
            'date_range': {
                'start': start_date.isoformat() if start_date else None,
                'end': end_date.isoformat() if end_date else None
            },
            'pagination': {
                'page': page,
                'page_size': page_size,
                'total_count': total_count,
                'total_pages': (total_count + page_size - 1) // page_size if total_count > 0 else 0
            },
            'results': search_results
        }

    except Exception as e:
        logger.error(f"Error in paginated search: {e}")
        return {
            'patient_login_code': patient_login_code,
            'error': str(e)
        }

def create_ai_dialog_history(
        db: Connection,
        dialog_data: AIDialogHistoryCreate
) -> Optional[PatientAIDialogHistory]:
    """
    创建新的AI对话历史记录
    """
    try:
        # 检查患者是否存在
        patient = get_patient_by_login_code(db, dialog_data.patient_login_code)
        if not patient:
            return None

        # 创建对话记录
        dialog_history = PatientAIDialogHistory(
            patient_login_code=dialog_data.patient_login_code,
            session_key=dialog_data.session_key,
            ai_model=dialog_data.ai_model,
            title=dialog_data.title,
            prompts=dialog_data.prompts,
            message_count=dialog_data.message_count,
            last_message_time=dialog_data.last_message_time
        )

        db.add(dialog_history)
        db.commit()
        db.refresh(dialog_history)
        return dialog_history

    except Exception as e:
        db.rollback()
        print(f"Error creating AI dialog history: {e}")
        return None


def get_ai_dialog_by_session_key(
        db: Connection,
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


# 在login_crud.py的AI对话相关函数区域添加以下函数

def create_ai_dialog(
        db: Connection,
        patient_login_code: str,
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
        patient = get_patient_by_login_code(db, patient_login_code)
        if not patient:
            print(f"Patient with login_code {patient_login_code} not found")
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
            patient_login_code=patient_login_code,
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


def update_ai_dialog_with_message_simple(
        db: Connection,
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

def update_ai_dialog_with_message(
        db: Connection,
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

def get_or_create_ai_dialog(
        db: Connection,
        patient_login_code: str,
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
        patient_login_code=patient_login_code,
        session_key=session_key,
        prompts=prompts,
        ai_model=ai_model,
        title=f"对话 {datetime.now().strftime('%m-%d %H:%M')}"
    )


def get_patients_without_nurse(db: Connection, skip: int = 0, limit: int = 100) -> List[Patient]:
    """
    获取所有没有分配护士的患者

    参数:
    - db: 数据库连接
    - skip: 跳过记录数
    - limit: 限制记录数

    返回: 患者列表
    """
    try:
        stmt = select(Patient).where(
            Patient.assigned_nurse_id.is_(None)  # 注意这里用is_而不是==
        ).offset(skip).limit(limit)

        result = db.execute(stmt).scalars().all()
        return list(result)
    except Exception as e:
        print(f"Error getting patients without nurse: {e}")
        return []


def get_patients_without_nurse_count(db: Connection) -> int:
    """
    获取没有分配护士的患者总数

    参数:
    - db: 数据库连接

    返回: 患者总数
    """
    try:
        count = db.query(Patient).filter(
            Patient.assigned_nurse_id.is_(None)
        ).count()
        return count
    except Exception as e:
        print(f"Error counting patients without nurse: {e}")
        return 0


def get_patients_without_nurse_paginated(db: Connection, page: int = 1, page_size: int = 20) -> dict:
    """
    分页获取没有分配护士的患者

    参数:
    - db: 数据库连接
    - page: 页码 (从1开始)
    - page_size: 每页大小

    返回: 包含患者列表和分页信息的字典
    """
    try:
        # 计算偏移量
        skip = (page - 1) * page_size

        # 获取患者数据
        patients = get_patients_without_nurse(db, skip, page_size)

        # 获取总数
        total_count = get_patients_without_nurse_count(db)

        # 转换为响应格式
        patients_data = []
        for patient in patients:
            patients_data.append({
                "patient_id": patient.patient_id,
                "login_code": patient.login_code,
                "first_name": patient.first_name,
                "last_name": patient.last_name,
                "full_name": patient.full_name,
                "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
                "age": patient.age,
                "sex": patient.sex,
                "height": float(patient.height) if patient.height else None,
                "weight": float(patient.weight) if patient.weight else None,
                "bmi": patient.bmi,
                "create_time": patient.create_time.isoformat() if patient.create_time else None
            })

        return {
            "patients": patients_data,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": (total_count + page_size - 1) // page_size if total_count > 0 else 0
            }
        }
    except Exception as e:
        print(f"Error in paginated patients without nurse: {e}")
        return {
            "patients": [],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_count": 0,
                "total_pages": 0
            }
        }


def assign_patient_to_nurse(db: Connection, patient_id: int, nurse_login_code: str) -> Optional[Patient]:
    """
    将患者分配给护士

    参数:
    - db: 数据库连接
    - patient_id: 患者ID
    - nurse_login_code: 护士登录码

    返回: 更新后的患者对象，失败返回None
    """
    try:
        # 获取患者
        patient = get_patient_by_id(db, patient_id)
        if not patient:
            print(f"Patient with id {patient_id} not found")
            return None

        # 如果已经是这个护士的患者，直接返回
        if patient.assigned_nurse_id == nurse_login_code:
            return patient

        # 检查护士是否存在
        nurse = db.query(Nurse).filter(Nurse.login_code == nurse_login_code).first()
        if not nurse:
            print(f"Nurse with login_code {nurse_login_code} not found")
            return None

        # 更新患者的护士分配
        patient.assigned_nurse_id = nurse_login_code

        try:
            db.commit()
            db.refresh(patient)
            return patient
        except Exception as e:
            db.rollback()
            print(f"Error assigning patient to nurse: {e}")
            return None

    except Exception as e:
        print(f"Error in assign_patient_to_nurse: {e}")
        return None


def unassign_patient_from_nurse(db: Connection, patient_id: int) -> Optional[Patient]:
    """
    解除患者与护士的分配关系

    参数:
    - db: 数据库连接
    - patient_id: 患者ID

    返回: 更新后的患者对象，失败返回None
    """
    try:
        # 获取患者
        patient = get_patient_by_id(db, patient_id)
        if not patient:
            print(f"Patient with id {patient_id} not found")
            return None

        # 如果患者本来就没有分配护士，直接返回
        if not patient.assigned_nurse_id:
            return patient

        # 解除分配
        patient.assigned_nurse_id = None

        try:
            db.commit()
            db.refresh(patient)
            return patient
        except Exception as e:
            db.rollback()
            print(f"Error unassigning patient from nurse: {e}")
            return None

    except Exception as e:
        print(f"Error in unassign_patient_from_nurse: {e}")
        return None


def search_patients_without_nurse(db: Connection, search_term: str) -> List[Patient]:
    """
    搜索没有分配护士的患者
    可以按姓名、登录码搜索

    参数:
    - db: 数据库连接
    - search_term: 搜索关键词

    返回: 符合条件的患者列表
    """
    try:
        # 构建搜索条件
        search_pattern = f"%{search_term}%"

        stmt = select(Patient).where(
            Patient.assigned_nurse_id.is_(None),
            (
                    (Patient.first_name.like(search_pattern)) |
                    (Patient.last_name.like(search_pattern)) |
                    (Patient.login_code.like(search_pattern))
            )
        )

        result = db.execute(stmt).scalars().all()
        return list(result)
    except Exception as e:
        print(f"Error searching patients without nurse: {e}")
        return []


def get_patient_assignment_status(db: Connection, patient_id: int) -> dict:
    """
    获取患者的分配状态信息

    参数:
    - db: 数据库连接
    - patient_id: 患者ID

    返回: 包含分配状态信息的字典
    """
    try:
        patient = get_patient_by_id(db, patient_id)
        if not patient:
            return {
                "has_error": True,
                "error": f"Patient with id {patient_id} not found"
            }

        nurse_info = None
        if patient.assigned_nurse_id:
            nurse = db.query(Nurse).filter(Nurse.login_code == patient.assigned_nurse_id).first()
            if nurse:
                nurse_info = {
                    "nurse_login_code": nurse.login_code,
                    "first_name": nurse.first_name,
                    "last_name": nurse.last_name,
                    "full_name": nurse.full_name
                }

        return {
            "has_error": False,
            "patient_id": patient.patient_id,
            "login_code": patient.login_code,
            "full_name": patient.full_name,
            "is_assigned": patient.assigned_nurse_id is not None,
            "assigned_nurse": nurse_info,
            "assigned_nurse_id": patient.assigned_nurse_id
        }
    except Exception as e:
        print(f"Error getting patient assignment status: {e}")
        return {
            "has_error": True,
            "error": str(e)
        }


def batch_assign_patients_to_nurse(db: Connection, patient_ids: List[int], nurse_login_code: str) -> dict:
    """
    批量将患者分配给护士

    参数:
    - db: 数据库连接
    - patient_ids: 患者ID列表
    - nurse_login_code: 护士登录码

    返回: 包含操作结果的字典
    """
    try:
        # 检查护士是否存在
        nurse = db.query(Nurse).filter(Nurse.login_code == nurse_login_code).first()
        if not nurse:
            return {
                "success": False,
                "error": f"Nurse with login_code {nurse_login_code} not found"
            }

        results = {
            "success": [],
            "failed": [],
            "total": len(patient_ids)
        }

        for patient_id in patient_ids:
            patient = get_patient_by_id(db, patient_id)
            if not patient:
                results["failed"].append({
                    "patient_id": patient_id,
                    "reason": "患者不存在"
                })
                continue

            # 更新分配
            try:
                patient.assigned_nurse_id = nurse_login_code
                db.commit()
                results["success"].append({
                    "patient_id": patient_id,
                    "login_code": patient.login_code,
                    "full_name": patient.full_name
                })
            except Exception as e:
                db.rollback()
                results["failed"].append({
                    "patient_id": patient_id,
                    "reason": f"数据库错误: {str(e)}"
                })

        return {
            "success": True,
            "results": results,
            "summary": {
                "assigned_count": len(results["success"]),
                "failed_count": len(results["failed"])
            }
        }

    except Exception as e:
        db.rollback()
        print(f"Error in batch_assign_patients_to_nurse: {e}")
        return {
            "success": False,
            "error": str(e)
        }


# 在 login_curd.py 文件中，添加到合适的位置

def get_patients_by_nurse_paginated(
        db: Connection,
        nurse_login_code: str,
        page: int = 1,
        page_size: int = 20
) -> dict:
    """
    分页获取护士管理的患者
    """
    try:
        # 验证护士是否存在
        nurse = get_nurse_by_login_code(db, nurse_login_code)
        if not nurse:
            raise ValueError(f"护士登录码 {nurse_login_code} 不存在")

        # 计算偏移量
        skip = (page - 1) * page_size

        # 查询护士管理的患者
        stmt = (
            select(Patient)
            .where(Patient.assigned_nurse_id == nurse_login_code)
            .order_by(desc(Patient.create_time))
            .offset(skip)
            .limit(page_size)
        )

        result = db.execute(stmt)
        patients = result.scalars().all()

        # 获取总数
        count_stmt = (
            select(func.count())
            .select_from(Patient)
            .where(Patient.assigned_nurse_id == nurse_login_code)
        )
        total_count = db.execute(count_stmt).scalar() or 0

        # 转换为响应格式
        patients_data = []
        for patient in patients:
            # 计算年龄
            age = None
            if patient.date_of_birth:
                from datetime import date
                today = date.today()
                age = today.year - patient.date_of_birth.year
                if (today.month, today.day) < (patient.date_of_birth.month, patient.date_of_birth.day):
                    age -= 1

            # 计算BMI
            bmi = None
            if patient.height and patient.weight and patient.height > 0:
                height_m = patient.height / 100
                bmi = patient.weight / (height_m * height_m)
                bmi = round(bmi, 2)

            patients_data.append({
                "patient_id": patient.patient_id,
                "login_code": patient.login_code,
                "first_name": patient.first_name,
                "last_name": patient.last_name,
                "full_name": patient.full_name,
                "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
                "age": age,
                "sex": patient.sex,
                "family_history": patient.family_history,
                "smoking_status": patient.smoking_status,
                "drinking_history": patient.drinking_history,
                "height": float(patient.height) if patient.height else None,
                "weight": float(patient.weight) if patient.weight else None,
                "bmi": bmi,
                "assigned_nurse_id": patient.assigned_nurse_id,
                "create_time": patient.create_time.isoformat() if patient.create_time else None,
                "update_time": patient.update_time.isoformat() if patient.update_time else None
            })

        return {
            "patients": patients_data,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": (total_count + page_size - 1) // page_size if total_count > 0 else 0
            }
        }
    except Exception as e:
        print(f"Error in get_patients_by_nurse_paginated: {e}")
        return {
            "patients": [],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_count": 0,
                "total_pages": 0
            }
        }


def get_patients_without_nurse(db: Connection, skip: int = 0, limit: int = 100) -> List[Patient]:
    """
    获取没有分配护士的患者
    """
    try:
        stmt = (
            select(Patient)
            .where(Patient.assigned_nurse_id.is_(None))
            .order_by(desc(Patient.create_time))
            .offset(skip)
            .limit(limit)
        )
        result = db.execute(stmt)
        return list(result.scalars().all())
    except Exception as e:
        print(f"Error getting patients without nurse: {e}")
        return []

def get_patients_without_nurse_by_search(db: Connection, search: str, skip: int = 0, limit: int = 100) -> List[Patient]:
    """
    通过搜索条件获取没有分配护士的患者
    """
    try:
        stmt = (
            select(Patient)
            .where(
                Patient.assigned_nurse_id.is_(None),
                (Patient.login_code.ilike(f"%{search}%") |
                 Patient.full_name.ilike(f"%{search}%") |
                 Patient.first_name.ilike(f"%{search}%") |
                 Patient.last_name.ilike(f"%{search}%"))
            )
            .order_by(desc(Patient.create_time))
            .offset(skip)
            .limit(limit)
        )
        result = db.execute(stmt)
        return list(result.scalars().all())
    except Exception as e:
        print(f"Error searching patients without nurse: {e}")
        return []


def get_patients_without_nurse_by_search_count(db: Connection, search: str) -> int:
    """
    通过搜索条件获取没有分配护士的患者总数
    """
    try:
        stmt = (
            select(func.count())
            .select_from(Patient)
            .where(
                Patient.assigned_nurse_id.is_(None),
                (Patient.login_code.ilike(f"%{search}%") |
                 Patient.full_name.ilike(f"%{search}%") |
                 Patient.first_name.ilike(f"%{search}%") |
                 Patient.last_name.ilike(f"%{search}%"))
            )
        )
        return db.execute(stmt).scalar() or 0
    except Exception as e:
        print(f"Error getting patients without nurse search count: {e}")
        return 0