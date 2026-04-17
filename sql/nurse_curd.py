# 护士相关的sql操作
import datetime

from sqlalchemy.orm import Session
from sql.people_models import Nurse, Patient,NurseWorkShift
from typing import Optional,Dict, Any,List
from sql.chat_histoty_curd import get_room_uuid_by_id
from sqlalchemy.exc import SQLAlchemyError  # 导入异常类

def get_nurse_by_phone(db: Session, phone: str) -> Nurse | None:
    """按手机号查询护士（适配新模型）"""
    return db.query(Nurse).filter(Nurse.phone == phone).first()


def get_nurse_by_id(db: Session, nurse_id: int) -> Optional[Nurse]:
    """
    按照护士ID获取护士的基本信息

    Args:
        db: 数据库会话对象
        nurse_id: 护士ID（主键）

    Returns:
        Optional[Nurse]: 找到返回Nurse对象，未找到/参数非法返回None
    """
    # 1. 参数校验：确保nurse_id是合法整数（防御性编程）
    if not isinstance(nurse_id, int) or nurse_id <= 0:
        return None

    try:
        # 2. 显式通过主键字段查询（比get()更通用、可读性更高）
        return db.query(Nurse).filter(Nurse.nurse_id == nurse_id).first()
    except Exception as e:
        # 3. 异常捕获：避免数据库层面的意外报错导致程序崩溃
        print(f"查询护士信息失败（ID: {nurse_id}）：{str(e)}")  # 建议替换为日志库（如logging）
        return None

def get_nurse_full_name(db:Session, nurse_id: int) -> str | None:
    nurse = get_nurse_by_id(db, nurse_id)
    if nurse:
        return nurse.full_name
    return None


def get_nurse_id_by_phone(db: Session, phone: str) -> Optional[int]:
    """
    按手机号查询护士ID（适配新模型）

    Args:
        db: 数据库会话对象
        phone: 护士手机号（带区号，如+85212345678）

    Returns:
        Optional[int]: 找到则返回护士ID，未找到返回None
    """
    # 查询护士记录并仅获取nurse_id字段（性能优化）
    nurse_id = db.query(Nurse.nurse_id).filter(Nurse.phone == phone).scalar()
    return nurse_id

# 原方法：get_patients_without_nurse_paginated_by_login_codes
# def get_patients_without_nurse_paginated_by_phone(db: Session, page: int, page_size: int, search: str = None):
#     # 修改查询条件：使用 phone 而非 login_code
#     query = db.query(Patient).filter(Patient.assigned_nurse_phone.is_(None))
#     if search:
#         query = query.filter(
#             (Patient.phone.contains(search)) |
#             (Patient.full_name.contains(search))
#         )
#     # 分页逻辑不变
#     total = query.count()
#     patients = query.offset((page-1)*page_size).limit(page_size).all()
#     return {
#         "patients": patients,
#         "pagination": {"page": page, "page_size": page_size, "total_count": total}
#     }

def get_patients_without_nurse_paginated_by_phone(
        db: Session,
        page: int,
        page_size: int,
        search: str = None
) -> Dict:
    """
    查询未分配护士的患者（分页），支持手机号/姓名模糊搜索
    适配Patient表字段变更：assigned_nurse_phone → assigned_nurse_id

    Args:
        db: 数据库会话对象
        page: 当前页码（从1开始）
        page_size: 每页条数
        search: 搜索关键词（匹配手机号/姓名）

    Returns:
        包含患者列表和分页信息的字典
    """
    # 🔴 修改1：过滤条件从assigned_nurse_phone改为assigned_nurse_id
    query = db.query(Patient).filter(Patient.assigned_nurse_id.is_(None))

    # 🔴 修改2：修复full_name计算属性无法用于SQL查询的问题
    # 改用first_name + last_name拼接匹配（兼容数据库查询）
    if search:
        # 构建姓名拼接的模糊查询（适配不同数据库，这里以MySQL为例）
        name_search = f"%{search}%"
        phone_search = f"%{search}%"

        query = query.filter(
            Patient.phone.like(phone_search) |  # 手机号模糊匹配
            # 姓名组合模糊匹配（支持搜索姓氏/名字/全名）
            (Patient.first_name + " " + Patient.last_name).like(name_search)
        )

    # 分页逻辑保持不变
    total = query.count()
    patients = query.offset((page - 1) * page_size).limit(page_size).all()

    return {
        "patients": patients,
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total_count": total
        }
    }

# def assign_patient_to_nurse_by_phone(db: Session, patient_phone: str, nurse_phone: str):
#     # 临时开启自动提交（绕过事务管理）
#     db.autocommit = True
#
#     try:
#         nurse = db.query(Nurse).filter(Nurse.phone == nurse_phone).first()
#         if not nurse:
#             return None
#
#         patient = db.query(Patient).filter(
#             Patient.phone == patient_phone,
#             Patient.assigned_nurse_phone.is_(None)
#         ).first()
#         if not patient:
#             return None
#
#         patient.assigned_nurse_phone = nurse_phone
#         # 自动提交，无需手动 commit
#         db.refresh(patient)
#         return patient
#     except Exception as e:
#         print(f"分配失败：{e}")
#         return None
#     finally:
#         # 恢复原有配置（可选）
#         db.autocommit = False
#         db.close()

def assign_patient_to_nurse_by_phone(
        db: Session,
        patient_phone: str,
        nurse_phone: str
) -> Optional[Patient]:
    """
    根据手机号为患者分配护士（适配字段变更：assigned_nurse_id）

    Args:
        db: 数据库会话对象
        patient_phone: 患者手机号
        nurse_phone: 护士手机号

    Returns:
        Optional[Patient]: 分配成功返回患者对象，失败返回None
    """
    # 🔴 移除不规范的autocommit修改，推荐使用事务上下文
    try:
        # 1. 查询护士（获取nurse_id）
        nurse = db.query(Nurse).filter(Nurse.phone == nurse_phone).first()
        if not nurse:
            print(f"分配失败：未找到手机号为{nurse_phone}的护士")
            return None

        # 2. 查询未分配护士的患者（过滤条件改为assigned_nurse_id）
        patient = db.query(Patient).filter(
            Patient.phone == patient_phone,
            Patient.assigned_nurse_id.is_(None)  # 🔴 修改1：字段替换
        ).first()
        if not patient:
            print(f"分配失败：未找到手机号为{patient_phone}的未分配护士患者")
            return None

        # 3. 分配护士（赋值nurse_id而非手机号）
        patient.assigned_nurse_id = nurse.nurse_id  # 🔴 修改2：赋值ID而非手机号
        db.commit()  # 🔴 显式提交事务（替代autocommit）
        db.refresh(patient)  # 刷新对象获取最新数据
        return patient

    except Exception as e:
        db.rollback()  # 🔴 异常时回滚事务
        print(f"分配失败：{str(e)}")
        return None
    finally:
        # 🔴 移除不必要的db.close()（会话应由调用方管理）
        pass

# 其他方法同步修改：
# unassign_patient_from_specific_nurse_by_login_code → unassign_patient_from_specific_nurse_by_phone
# get_patients_by_nurse_paginated → 内部使用 nurse_phone 查询

# def unassign_patient_from_specific_nurse_by_phone(
#         db: Session,
#         patient_phone: str,
#         nurse_phone: str
# ) -> Optional[Patient]:
#     """
#     解除指定护士对指定患者的管理权限（按手机号）
#     适配你提供的 Patient/Nurse 模型结构
#
#     Args:
#         db: 数据库会话对象
#         patient_phone: 患者手机号（带区号，如+85212345678）
#         nurse_phone: 护士手机号（带区号，如+85212345678）
#
#     Returns:
#         解除分配后的 Patient 对象 | None（失败时）
#     """
#     try:
#         # 1. 验证护士是否存在（匹配 Nurse 模型的 phone 字段）
#         nurse = db.query(Nurse).filter(Nurse.phone == nurse_phone).first()
#         if not nurse:
#             # 护士手机号不存在
#             return None
#
#         # 2. 验证患者是否存在，且当前归属该护士（匹配 Patient 模型的字段）
#         # 核心条件：患者手机号匹配 + 关联的护士手机号匹配
#         patient = db.query(Patient).filter(
#             Patient.phone == patient_phone,  # 匹配患者手机号
#             Patient.assigned_nurse_phone == nurse_phone  # 匹配当前分配的护士手机号
#         ).first()
#
#         # 3. 患者不存在 或 不归该护士管理 → 返回 None
#         if not patient:
#             return None
#
#         # 4. 解除分配（清空关联字段，匹配你的 Patient 模型定义）
#         patient.assigned_nurse_phone = None  # 清空关联的护士手机号
#         # 注：你的 Patient 模型中未定义 assigned_nurse_id，仅需清空 assigned_nurse_phone
#
#         # 5. 提交事务并刷新患者数据
#         db.commit()
#         db.refresh(patient)
#
#         # 6. 返回解除分配后的患者对象
#         return patient
#
#     except Exception as e:
#         # 异常时回滚事务，避免数据不一致
#         db.rollback()
#         print(f"解除患者分配失败: {str(e)}")  # 可替换为日志记录
#         return None

def unassign_patient_from_specific_nurse_by_phone(
        db: Session,
        patient_phone: str,
        nurse_phone: str
) -> Optional[Patient]:
    """
    解除指定护士对指定患者的管理权限（按手机号）
    适配字段变更：Patient.assigned_nurse_id 关联 Nurse.nurse_id

    Args:
        db: 数据库会话对象
        patient_phone: 患者手机号（带区号，如+85212345678）
        nurse_phone: 护士手机号（带区号，如+85212345678）

    Returns:
        解除分配后的 Patient 对象 | None（失败时）
    """
    try:
        # 1. 验证护士是否存在，获取护士ID
        nurse = db.query(Nurse).filter(Nurse.phone == nurse_phone).first()
        if not nurse:
            print(f"解除分配失败：未找到手机号为{nurse_phone}的护士")
            return None

        # 2. 验证患者是否存在，且当前归属该护士（核心修改：匹配assigned_nurse_id）
        patient = db.query(Patient).filter(
            Patient.phone == patient_phone,
            Patient.assigned_nurse_id == nurse.nurse_id  # 🔴 修改1：匹配护士ID而非手机号
        ).first()

        # 3. 患者不存在 或 不归该护士管理 → 返回 None
        if not patient:
            print(f"解除分配失败：患者{patient_phone}不存在，或不归护士{nurse_phone}管理")
            return None

        # 4. 解除分配（清空关联字段）
        patient.assigned_nurse_id = None  # 🔴 修改2：清空护士ID而非手机号

        # 5. 提交事务并刷新患者数据
        db.commit()
        db.refresh(patient)

        # 6. 返回解除分配后的患者对象
        return patient

    except Exception as e:
        # 异常时回滚事务，避免数据不一致
        db.rollback()
        print(f"解除患者分配失败: {str(e)}")  # 可替换为日志记录
        return None

# def get_patients_by_nurse_paginated(
#         db: Session,
#         nurse_phone: str,
#         page: int = 1,
#         page_size: int = 20,
#         search: Optional[str] = None
# ) -> Dict[str, Any]:
#     """
#     分页获取指定护士管理的所有患者
#     适配你提供的 Patient 模型结构
#
#     Args:
#         db: 数据库会话对象
#         nurse_phone: 护士手机号（带区号）
#         page: 页码（默认1）
#         page_size: 每页条数（默认20）
#         search: 搜索关键词（可选，匹配姓名/手机号）
#
#     Returns:
#         包含分页数据的字典，格式：
#         {
#             "patients": [患者列表],
#             "pagination": {
#                 "page": 当前页,
#                 "page_size": 每页条数,
#                 "total_count": 总条数,
#                 "total_pages": 总页数
#             }
#         }
#     """
#     try:
#         # 1. 构建基础查询：筛选归属该护士的患者
#         query = db.query(Patient).filter(Patient.assigned_nurse_phone == nurse_phone)
#
#         # 2. 搜索条件（匹配姓名/手机号）
#         if search and search.strip():
#             search_term = f"%{search.strip()}%"
#             query = query.filter(
#                 (Patient.phone.ilike(search_term)) |  # 手机号模糊匹配
#                 (Patient.first_name.ilike(search_term)) |  # 姓氏模糊匹配
#                 (Patient.last_name.ilike(search_term))  # 名字模糊匹配
#             )
#
#         # 3. 计算总条数和总页数
#         total_count = query.count()
#         total_pages = (total_count + page_size - 1) // page_size  # 向上取整
#
#         # 4. 分页查询（注意：SQLAlchemy offset 从0开始）
#         offset = (page - 1) * page_size
#         patients = query.order_by(Patient.create_time.desc()).offset(offset).limit(page_size).all()
#
#         # 5. 格式化患者数据（适配前端返回格式）
#         formatted_patients = []
#         for patient in patients:
#             # 计算BMI（复用模型中的bmi计算属性）
#             bmi = patient.bmi if hasattr(patient, 'bmi') else None
#
#             # 计算年龄（复用模型中的age计算属性）
#             age = patient.age if hasattr(patient, 'age') else None
#
#             formatted_patients.append({
#                 "patient_id": patient.patient_id,
#                 "phone": patient.phone,
#                 "first_name": patient.first_name,
#                 "last_name": patient.last_name,
#                 "full_name": patient.full_name,  # 复用模型中的full_name属性
#                 "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
#                 "age": age,
#                 "sex": patient.sex.value if patient.sex else None,  # 枚举值转字符串
#                 "family_history": patient.family_history.value if patient.family_history else None,
#                 "smoking_status": patient.smoking_status.value if patient.smoking_status else None,
#                 "drinking_history": patient.drinking_history.value if patient.drinking_history else None,
#                 "height": float(patient.height) if patient.height else None,
#                 "weight": float(patient.weight) if patient.weight else None,
#                 "bmi": bmi,
#                 "assigned_nurse_phone": patient.assigned_nurse_phone,
#                 "create_time": patient.create_time.isoformat() if patient.create_time else None,
#                 "update_time": patient.update_time.isoformat() if patient.update_time else None
#             })
#
#         # 6. 组装返回结果
#         return {
#             "patients": formatted_patients,
#             "pagination": {
#                 "page": page,
#                 "page_size": page_size,
#                 "total_count": total_count,
#                 "total_pages": total_pages
#             }
#         }
#
#     except Exception as e:
#         print(f"获取护士患者列表失败: {str(e)}")  # 替换为日志记录
#         # 返回空数据，避免接口报错
#         return {
#             "patients": [],
#             "pagination": {
#                 "page": page,
#                 "page_size": page_size,
#                 "total_count": 0,
#                 "total_pages": 0
#             }
#         }

def get_patient_ids_by_nurse(
    db: Session,
    nurse_id: int
) -> List[int]:
    """
    根据护士 nurse_id，获取该护士已分配的所有患者 patient_id 列表
    返回：List[patient_id]
    """
    try:
        # 直接查询该护士分配的所有患者，只取 patient_id
        patient_ids = (
            db.query(Patient.patient_id)
            .filter(Patient.assigned_nurse_id == nurse_id)
            .all()
        )
        # 把 [(1,), (2,)] 转成 [1, 2]
        return [pid[0] for pid in patient_ids]

    except Exception as e:
        print(f"获取护士患者ID失败: {str(e)}")
        return []

def get_patients_by_nurse_paginated(
        db: Session,
        nurse_phone: str,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None
) -> Dict[str, Any]:
    """
    分页获取指定护士管理的所有患者
    适配字段变更：Patient.assigned_nurse_id 关联 Nurse.nurse_id
    修复：每个患者返回独立的room_uuid
    """
    try:
        # 1. 查询护士信息，获取nurse_id
        nurse = db.query(Nurse).filter(Nurse.phone == nurse_phone).first()
        if not nurse:
            return {
                "patients": [],
                "pagination": {
                    "page": page,
                    "page_size": page_size,
                    "total_count": 0,
                    "total_pages": 0
                }
            }

        # 2. 筛选该护士管理的患者
        query = db.query(Patient).filter(Patient.assigned_nurse_id == nurse.nurse_id)

        # 3. 搜索条件（匹配姓名/手机号）
        if search and search.strip():
            search_term = f"%{search.strip()}%"
            query = query.filter(
                (Patient.phone.ilike(search_term)) |
                (Patient.first_name.ilike(search_term)) |
                (Patient.last_name.ilike(search_term))
            )

        # 4. 计算分页参数
        total_count = query.count()
        total_pages = (total_count + page_size - 1) // page_size
        offset = (page - 1) * page_size
        patients = query.order_by(Patient.create_time.desc()).offset(offset).limit(page_size).all()

        # 5. 格式化患者数据（核心：循环内为每个患者单独获取room_uuid）
        formatted_patients = []
        for patient in patients:
            # 计算BMI和年龄
            bmi = patient.bmi if hasattr(patient, 'bmi') else None
            age = patient.age if hasattr(patient, 'age') else None

            # 🔥 修复1：移到循环内 + 传当前患者的patient_id（实例属性）
            # 🔥 修复2：增加空值判断，避免报错
            room_info = get_room_uuid_by_id(db, patient_id=patient.patient_id)
            current_room_uuid = room_info["room_uuid"] if (room_info and "room_uuid" in room_info) else None

            formatted_patients.append({
                "patient_id": patient.patient_id,
                "phone": patient.phone,
                "first_name": patient.first_name,
                "last_name": patient.last_name,
                "full_name": patient.full_name,
                "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
                "age": age,
                "sex": patient.sex.value if patient.sex else None,
                "family_history": patient.family_history.value if patient.family_history else None,
                "smoking_status": patient.smoking_status.value if patient.smoking_status else None,
                "drinking_history": patient.drinking_history.value if patient.drinking_history else None,
                "height": float(patient.height) if patient.height else None,
                "weight": float(patient.weight) if patient.weight else None,
                "bmi": bmi,
                "assigned_nurse_id": patient.assigned_nurse_id,
                "assigned_nurse_name": nurse.full_name,
                "assigned_nurse_phone": nurse.phone,
                "create_time": patient.create_time.isoformat() if patient.create_time else None,
                "update_time": patient.update_time.isoformat() if patient.update_time else None,
                # 🔥 修复3：赋值当前患者的独立room_uuid
                "room_uuid": current_room_uuid
            })

        # 6. 组装返回结果
        return {
            "patients": formatted_patients,
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_count": total_count,
                "total_pages": total_pages
            }
        }

    except Exception as e:
        print(f"获取护士患者列表失败: {str(e)}")
        return {
            "patients": [],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_count": 0,
                "total_pages": 0
            }
        }

def add_nurse_work_time(db: Session,nurse_id:int,start_time:datetime.time,end_time:datetime.time):
    # 1. 获取当前日期（UTC时间，若需香港本地时间需做时区转换，见下方备注）
    today = datetime.date.today()

    # 3. 查询当日该护士是否已存在排班记录（防重复插入）
    existing_shift = db.query(NurseWorkShift).filter(
        NurseWorkShift.nurse_id == nurse_id,
        NurseWorkShift.work_date == today
    ).first()
    # 4. 不存在则插入新记录，字段均用默认值（status默认scheduled，统计字段默认0）
    if not existing_shift:
        new_shift = NurseWorkShift(
            nurse_id=nurse_id,
            work_date=today,
            work_start_time=start_time,
            work_end_time=end_time
            # 其余字段：shift_uuid(数据库自动生成)、status(默认scheduled)、统计字段(默认0) 无需手动传
        )
        db.add(new_shift)
        db.commit()
        db.refresh(new_shift)  # 刷新获取自动生成的shift_uuid/shift_id


def update_nurse_today_work_time(
        db: Session,
        nurse_id: int,
        new_start_time: datetime.time | None = None,
        new_end_time: datetime.time | None = None
):
    """
    更新护士当日的工作时间段
    :param db: 数据库会话
    :param nurse_id: 护士ID
    :param new_start_time: 新的上班时间（可选，不传则不更新）
    :param new_end_time: 新的下班时间（可选，不传则不更新）
    :return: 更新后的NurseWorkShift对象 | None（无记录/未更新）
    """
    # 1. 空值校验：至少传一个时间参数，避免无意义更新
    if new_start_time is None and new_end_time is None:
        return None

    # 2. 获取当日日期（和原新增函数一致，新加坡UTC+8，与香港日期无偏差）
    today = datetime.date.today()

    # 3. 查询当日该护士的排班记录
    existing_shift = db.query(NurseWorkShift).filter(
        NurseWorkShift.nurse_id == nurse_id,
        NurseWorkShift.work_date == today
    ).first()

    # 4. 存在则更新时间，按需赋值（传啥更啥）
    if existing_shift:
        if new_start_time is not None:
            existing_shift.work_start_time = new_start_time
        if new_end_time is not None:
            existing_shift.work_end_time = new_end_time
        # 数据库已配置update_time ON UPDATE，无需手动赋值，提交即可
        db.commit()
        db.refresh(existing_shift)  # 刷新返回最新数据
        return existing_shift
    # 无当日班次记录则返回None
    return None


def update_nurse_appoint_work_time(
        db: Session,
        nurse_id: int,
        work_date: datetime.date,
        new_start_time: datetime.time | None = None,
        new_end_time: datetime.time | None = None
):
    """
    更新护士指定日期的工作时间段（支持任意日期，灵活扩展）
    :param db: 数据库会话
    :param nurse_id: 护士ID
    :param work_date: 要更新的班次日期（如date(2025,10,1)）
    :param new_start_time: 新的上班时间（可选，不传则不更新）
    :param new_end_time: 新的下班时间（可选，不传则不更新）
    :return: 更新后的NurseWorkShift对象 | None（无记录/未更新）
    """
    # 1. 空值校验：至少传一个时间参数
    if new_start_time is None and new_end_time is None:
        return None

    # 2. 查询指定日期该护士的排班记录
    existing_shift = db.query(NurseWorkShift).filter(
        NurseWorkShift.nurse_id == nurse_id,
        NurseWorkShift.work_date == work_date
    ).first()

    # 3. 存在则更新时间
    if existing_shift:
        if new_start_time is not None:
            existing_shift.work_start_time = new_start_time
        if new_end_time is not None:
            existing_shift.work_end_time = new_end_time
        db.commit()
        db.refresh(existing_shift)
        return existing_shift
    # 无指定日期班次记录则返回None
    return None

def get_nurse_today_work_time_curd(db: Session,nurse_id: int):
    # 查询当日排班记录
    today = datetime.date.today()
    shift = db.query(NurseWorkShift).filter(
        NurseWorkShift.nurse_id == nurse_id,
        NurseWorkShift.work_date == today
    ).first()
    # 无记录则自动创建（调用你写的新增函数，默认香港长白班）
    if not shift:
        add_nurse_work_time(
            db=db,
            nurse_id=nurse_id,
            start_time=datetime.time(hour=9, minute=0),
            end_time=datetime.time(hour=18, minute=0)
        )
        shift = db.query(NurseWorkShift).filter(
            NurseWorkShift.nurse_id == nurse_id,
            NurseWorkShift.work_date == today
        ).first()
    return shift