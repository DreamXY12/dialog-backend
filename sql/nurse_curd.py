# 护士相关的sql操作
from sqlalchemy.orm import Session
from sql.people_models import Nurse, Patient
from typing import Optional,Dict, Any

def get_nurse_by_phone(db: Session, phone: str) -> Nurse | None:
    """按手机号查询护士（适配新模型）"""
    return db.query(Nurse).filter(Nurse.phone == phone).first()

# 原方法：get_patients_without_nurse_paginated_by_login_codes
def get_patients_without_nurse_paginated_by_phone(db: Session, page: int, page_size: int, search: str = None):
    # 修改查询条件：使用 phone 而非 login_code
    query = db.query(Patient).filter(Patient.assigned_nurse_phone.is_(None))
    if search:
        query = query.filter(
            (Patient.phone.contains(search)) |
            (Patient.full_name.contains(search))
        )
    # 分页逻辑不变
    total = query.count()
    patients = query.offset((page-1)*page_size).limit(page_size).all()
    return {
        "patients": patients,
        "pagination": {"page": page, "page_size": page_size, "total_count": total}
    }

# 原方法：assign_patient_to_nurse_by_login_code
def assign_patient_to_nurse_by_phone(db: Session, patient_phone: str, nurse_phone: str):
    # 1. 查询护士是否存在
    nurse = db.query(Nurse).filter(Nurse.phone == nurse_phone).first()
    if not nurse:
        return None
    # 2. 查询患者是否存在且未分配
    patient = db.query(Patient).filter(
        Patient.phone == patient_phone,
        Patient.assigned_nurse_phone.is_(None)
    ).first()
    if not patient:
        return None
    # 3. 分配患者
    patient.assigned_nurse_phone = nurse_phone
    patient.assigned_nurse_id = nurse.id
    db.commit()
    db.refresh(patient)
    return patient

# 其他方法同步修改：
# unassign_patient_from_specific_nurse_by_login_code → unassign_patient_from_specific_nurse_by_phone
# get_patients_by_nurse_paginated → 内部使用 nurse_phone 查询

def unassign_patient_from_specific_nurse_by_phone(
        db: Session,
        patient_phone: str,
        nurse_phone: str
) -> Optional[Patient]:
    """
    解除指定护士对指定患者的管理权限（按手机号）
    适配你提供的 Patient/Nurse 模型结构

    Args:
        db: 数据库会话对象
        patient_phone: 患者手机号（带区号，如+85212345678）
        nurse_phone: 护士手机号（带区号，如+85212345678）

    Returns:
        解除分配后的 Patient 对象 | None（失败时）
    """
    try:
        # 1. 验证护士是否存在（匹配 Nurse 模型的 phone 字段）
        nurse = db.query(Nurse).filter(Nurse.phone == nurse_phone).first()
        if not nurse:
            # 护士手机号不存在
            return None

        # 2. 验证患者是否存在，且当前归属该护士（匹配 Patient 模型的字段）
        # 核心条件：患者手机号匹配 + 关联的护士手机号匹配
        patient = db.query(Patient).filter(
            Patient.phone == patient_phone,  # 匹配患者手机号
            Patient.assigned_nurse_phone == nurse_phone  # 匹配当前分配的护士手机号
        ).first()

        # 3. 患者不存在 或 不归该护士管理 → 返回 None
        if not patient:
            return None

        # 4. 解除分配（清空关联字段，匹配你的 Patient 模型定义）
        patient.assigned_nurse_phone = None  # 清空关联的护士手机号
        # 注：你的 Patient 模型中未定义 assigned_nurse_id，仅需清空 assigned_nurse_phone

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


def get_patients_by_nurse_paginated(
        db: Session,
        nurse_phone: str,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None
) -> Dict[str, Any]:
    """
    分页获取指定护士管理的所有患者
    适配你提供的 Patient 模型结构

    Args:
        db: 数据库会话对象
        nurse_phone: 护士手机号（带区号）
        page: 页码（默认1）
        page_size: 每页条数（默认20）
        search: 搜索关键词（可选，匹配姓名/手机号）

    Returns:
        包含分页数据的字典，格式：
        {
            "patients": [患者列表],
            "pagination": {
                "page": 当前页,
                "page_size": 每页条数,
                "total_count": 总条数,
                "total_pages": 总页数
            }
        }
    """
    try:
        # 1. 构建基础查询：筛选归属该护士的患者
        query = db.query(Patient).filter(Patient.assigned_nurse_phone == nurse_phone)

        # 2. 搜索条件（匹配姓名/手机号）
        if search and search.strip():
            search_term = f"%{search.strip()}%"
            query = query.filter(
                (Patient.phone.ilike(search_term)) |  # 手机号模糊匹配
                (Patient.first_name.ilike(search_term)) |  # 姓氏模糊匹配
                (Patient.last_name.ilike(search_term))  # 名字模糊匹配
            )

        # 3. 计算总条数和总页数
        total_count = query.count()
        total_pages = (total_count + page_size - 1) // page_size  # 向上取整

        # 4. 分页查询（注意：SQLAlchemy offset 从0开始）
        offset = (page - 1) * page_size
        patients = query.order_by(Patient.create_time.desc()).offset(offset).limit(page_size).all()

        # 5. 格式化患者数据（适配前端返回格式）
        formatted_patients = []
        for patient in patients:
            # 计算BMI（复用模型中的bmi计算属性）
            bmi = patient.bmi if hasattr(patient, 'bmi') else None

            # 计算年龄（复用模型中的age计算属性）
            age = patient.age if hasattr(patient, 'age') else None

            formatted_patients.append({
                "patient_id": patient.patient_id,
                "phone": patient.phone,
                "first_name": patient.first_name,
                "last_name": patient.last_name,
                "full_name": patient.full_name,  # 复用模型中的full_name属性
                "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
                "age": age,
                "sex": patient.sex.value if patient.sex else None,  # 枚举值转字符串
                "family_history": patient.family_history.value if patient.family_history else None,
                "smoking_status": patient.smoking_status.value if patient.smoking_status else None,
                "drinking_history": patient.drinking_history.value if patient.drinking_history else None,
                "height": float(patient.height) if patient.height else None,
                "weight": float(patient.weight) if patient.weight else None,
                "bmi": bmi,
                "assigned_nurse_phone": patient.assigned_nurse_phone,
                "create_time": patient.create_time.isoformat() if patient.create_time else None,
                "update_time": patient.update_time.isoformat() if patient.update_time else None
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
        print(f"获取护士患者列表失败: {str(e)}")  # 替换为日志记录
        # 返回空数据，避免接口报错
        return {
            "patients": [],
            "pagination": {
                "page": page,
                "page_size": page_size,
                "total_count": 0,
                "total_pages": 0
            }
        }