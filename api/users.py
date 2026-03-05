from fastapi import APIRouter, Depends, HTTPException, status, Header
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime,timedelta

from api.auth import create_access_token, SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES

from sql.start import get_db
from sql.login_models import Patient, Nurse
from sql.login_models import Gender, FamilyHistory, SmokingStatus, DrinkingFrequency
from sql.schemas import PatientCreate, PatientUpdate, PatientResponse,TokenResponse
from api.auth import (
    get_password_hash, mark_login_code_as_used, get_login_code,
    decode_token, oauth2_scheme
)
import logging
logging.basicConfig(
    level=logging.INFO,
    filename='dev.log',
    filemode='a',
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

from sql.schemas import FirstLoginUpdate

router = APIRouter(prefix="/users", tags=["users"])

# 患者相关函数
def get_patient_by_id(db: Session, patient_id: int):
    return db.query(Patient).filter(Patient.patient_id == patient_id).first()

def get_nurse_by_id(db: Session, nurse_id: int):
    return db.query(Nurse).filter(Nurse.nurse_id == nurse_id).first()


def get_all_patients(db: Session, skip: int = 0, limit: int = 100):
    return db.query(Patient).offset(skip).limit(limit).all()


def get_patients_by_nurse(db: Session, nurse_id: int):
    return db.query(Patient).filter(Patient.assigned_nurse_id == nurse_id).all()


def create_patient_record(db: Session, login_code: str, first_name: str, last_name: str, password: str,
                          assigned_nurse_id: Optional[int] = None):
    # 检查登录码是否可用
    login_code_obj = get_login_code(db, login_code)
    if not login_code_obj or login_code_obj.is_used:
        return None

    # 如果指定了护士，检查护士是否存在
    if assigned_nurse_id:
        nurse = db.query(Nurse).filter(Nurse.nurse_id == assigned_nurse_id).first()
        if not nurse:
            return None

    # 计算年龄
    def calculate_age(date_of_birth):
        if not date_of_birth:
            return None
        today = datetime.now().date()
        age = today.year - date_of_birth.year
        if (today.month, today.day) < (date_of_birth.month, date_of_birth.day):
            age -= 1
        return age

    # get_password_hash(password)每次用这个总会报错，说生成的密码超过72位了，就先存储原码了
    # 创建患者
    patient = Patient(
        login_code=login_code,
        first_name=first_name,
        last_name=last_name,
        hashed_password=password,
        assigned_nurse_id=assigned_nurse_id
    )

    db.add(patient)
    db.commit()
    db.refresh(patient)

    # 标记登录码为已使用
    mark_login_code_as_used(db, login_code, "patient")

    return patient


def update_patient_record(db: Session, patient_id: int, update_data: dict):
    """更新患者信息（增强版）"""

    patient = get_patient_by_id(db, patient_id)
    if not patient:
        return None

    # 处理枚举字段转换
    for key, value in update_data.items():
        if value is not None and hasattr(patient, key):
            try:
                # 特殊处理枚举字段
                if key == "sex":
                    # 确保值匹配枚举
                    if value in ["Female", "Male", "Prefer not to tell"]:
                        setattr(patient, key, Gender(value))
                    else:
                        # 尝试自动转换
                        if value.upper() in ["FEMALE", "F", "女"]:
                            setattr(patient, key, Gender.Female)
                        elif value.upper() in ["MALE", "M", "男"]:
                            setattr(patient, key, Gender.Male)
                        elif value.upper() in ["PREFER_NOT_TO_TELL", "UNKNOWN", "未知"]:
                            setattr(patient, key, Gender.PREFER_NOT_TO_TELL)
                        else:
                            print(f"警告: 无法识别的性别值: {value}")
                            continue

                elif key == "family_history":
                    if value in ["Yes", "No", "Unknown"]:
                        setattr(patient, key, FamilyHistory(value))
                    elif value == "yes":
                        setattr(patient, key, FamilyHistory.YES)
                    elif value == "no":
                        setattr(patient, key, FamilyHistory.NO)
                    elif value in ["Prefer not to tell", "unknown", "UNKNOWN"]:
                        setattr(patient, key, FamilyHistory.UNKNOWN)
                    else:
                        print(f"警告: 无法识别的家族病史值: {value}")
                        continue

                elif key == "smoking_status":
                    if value in ["Yes", "No","Prefer not to tell"]:
                        setattr(patient, key, SmokingStatus(value))
                    elif value.upper() in ["YES", "Y", "是", "吸烟"]:
                        setattr(patient, key, SmokingStatus.YES)
                    elif value.upper() in ["NO", "N", "否", "不吸烟"]:
                        setattr(patient, key, SmokingStatus.NO)
                    else:
                        print(f"警告: 无法识别的吸烟状态值: {value}")
                        continue

                elif key == "drinking_history":
                    if value in ["Never", "Rarely", "Occasionally", "Frequently", "Daily"]:
                        setattr(patient, key, DrinkingFrequency(value))
                    else:
                        print(f"警告: 无法识别的饮酒频率值: {value}")
                        continue

                else:
                    # 非枚举字段直接设置
                    setattr(patient, key, value)

            except Exception as e:
                print(f"设置字段 {key} 时出错: {e}")
                continue

    # 如果指定了护士，检查护士是否存在
    if 'assigned_nurse_id' in update_data and update_data['assigned_nurse_id'] is not None:
        if update_data['assigned_nurse_id'] == 0:  # 设置为空
            patient.assigned_nurse_id = None
        else:
            nurse = get_nurse_by_id(db, update_data['assigned_nurse_id'])
            if not nurse:
                return None
            patient.assigned_nurse_id = update_data['assigned_nurse_id']

    # 确保 update_time 会被更新
    from datetime import datetime
    patient.update_time = datetime.utcnow()

    try:
        db.commit()
        # 注意：移除refresh调用，因为枚举转换可能导致问题
        # db.refresh(patient)
        return patient
    except Exception as e:
        db.rollback()
        print(f"更新患者记录失败: {str(e)}")
        return None


# 修改注册接口，返回TokenResponse而不是PatientResponse
@router.post("/patients/register", response_model=TokenResponse)
async def register_patient(
        request: PatientCreate,
        db: Session = Depends(get_db)
):
    """注册患者并自动登录"""
    try:
        # 1. 创建患者记录
        patient = create_patient_record(
            db,
            request.login_code,
            request.first_name,
            request.last_name,
            request.password,
            request.assigned_nurse_id
        )

        if not patient:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="注册失败，登录码无效或已被使用"
            )

        # 2. 刷新对象以获取数据库生成的字段
        db.refresh(patient)

        # 3. 创建访问令牌
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={
                "sub": str(patient.patient_id),  # 使用患者ID
                "user_type": "patient",  # 用户类型
                "login_code": patient.login_code
            },
            expires_delta=access_token_expires
        )

        # 4. 返回token响应
        return TokenResponse(
            access_token=access_token,
            token_type="bearer",
            user_type="patient",
            user_id=patient.patient_id,
            first_name=patient.first_name,
            last_name=patient.last_name,
            login_code=patient.login_code
        )

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"注册失败: {str(e)}"
        )

@router.get("/patients", response_model=List[PatientResponse])
async def get_patients(
        skip: int = 0,
        limit: int = 100,
        db: Session = Depends(get_db)
):
    """获取所有患者"""
    return get_all_patients(db, skip, limit)

@router.get("/patients/{patient_id}", response_model=PatientResponse)
async def get_patient(patient_id: int, db: Session = Depends(get_db)):
    """获取患者信息"""
    patient = get_patient_by_id(db, patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="患者不存在"
        )
    return patient

@router.put("/patients/{patient_id}", response_model=PatientResponse)
async def update_patient(
        patient_id: int,
        update_data: PatientUpdate,
        db: Session = Depends(get_db)
):
    """更新患者信息"""
    try:
        # 转换枚举值为字符串
        update_dict = {}
        for key, value in update_data.dict().items():
            if value is not None:
                if hasattr(value, 'value'):  # 如果是枚举
                    update_dict[key] = value.value
                else:
                    update_dict[key] = value

        patient = update_patient_record(db, patient_id, update_dict)
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="更新失败，护士不存在或数据无效"
            )

        return patient
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"更新失败: {str(e)}"
        )


@router.get("/nurses/{nurse_id}/patients", response_model=List[PatientResponse])
async def get_nurse_patients(nurse_id: int, db: Session = Depends(get_db)):
    """获取护士负责的患者"""
    nurse = db.query(Nurse).filter(Nurse.nurse_id == nurse_id).first()
    if not nurse:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="护士不存在"
        )
    return get_patients_by_nurse(db, nurse_id)


# 依赖函数：获取当前患者信息
def get_current_patient_info(
        token: str = Depends(oauth2_scheme),
        db: Session = Depends(get_db)
) -> dict:
    """获取当前患者信息作为依赖"""
    payload = decode_token(token)
    if not payload or payload.get("user_type") != "patient":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的令牌或权限不足"
        )

    patient_id = int(payload.get("sub"))
    patient = get_patient_by_id(db, patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="患者不存在"
        )

    return {
        "login_code": patient.login_code,
        "patient_id": patient.patient_id,
        "full_name": patient.full_name
    }

# 当前用户信息
@router.get("/me/patient", response_model=PatientResponse)
async def get_current_patient(
        current_user: dict = Depends(get_current_patient_info),
        db: Session = Depends(get_db)
):
    """获取当前患者信息"""
    patient = get_patient_by_id(db, current_user["patient_id"])
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="患者不存在"
        )

    return patient


@router.get("/me/nurse", response_model=dict)
async def get_current_nurse(
        token: str = Depends(oauth2_scheme),
        db: Session = Depends(get_db)
):
    """获取当前护士信息"""
    payload = decode_token(token)
    if not payload or payload.get("user_type") != "nurse":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的令牌或权限不足"
        )

    nurse_id = int(payload.get("sub"))
    nurse = db.query(Nurse).filter(Nurse.nurse_id == nurse_id).first()
    if not nurse:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="护士不存在"
        )

    return {
        "nurse_id": nurse.nurse_id,
        "login_code": nurse.login_code,
        "first_name": nurse.first_name,
        "last_name": nurse.last_name,
        "full_name": f"{nurse.first_name}{nurse.last_name}",
        "create_time": nurse.create_time
    }


# @router.put("/patients/{patient_id}/first-login", response_model=PatientResponse)
# async def update_patient_first_login(
#         patient_id: int,
#         update_data: dict,
#         db: Session = Depends(get_db)
# ):
#     """患者首次登录更新个人信息"""
#     try:
#         # 验证必填字段
#         required_fields = ["height", "weight"]
#         for field in required_fields:
#             if field not in update_data or not update_data[field]:
#                 raise HTTPException(
#                     status_code=status.HTTP_400_BAD_REQUEST,
#                     detail=f"必填字段缺失: {field}"
#                 )
#
#         # 获取患者
#         patient = get_patient_by_id(db, patient_id)
#         if not patient:
#             raise HTTPException(
#                 status_code=status.HTTP_404_NOT_FOUND,
#                 detail="患者不存在"
#             )
#
#         # 处理特殊字段
#         update_dict = {}
#         for key, value in update_data.items():
#             if value is not None and value != '':
#                 if key == "sex":
#                     if value in ["Female", "Male", "Prefer not to tell"]:
#                         update_dict[key] = Gender(value)
#                 elif key == "family_history":
#                     if value in ["yes", "no", "Prefer not to tell"]:
#                         # 注意：前端传的是 "yes"/"no"，但数据库期望 "Yes"/"No"
#                         if value == "yes":
#                             update_dict[key] = FamilyHistory.YES
#                         elif value == "no":
#                             update_dict[key] = FamilyHistory.NO
#                         else:
#                             update_dict[key] = FamilyHistory.UNKNOWN
#                 elif key == "smoking":
#                     if value in ["Yes", "No"]:
#                         update_dict[key] = SmokingStatus(value)
#                 elif key == "drinking":
#                     if value in ["Never", "Rarely", "Occasionally", "Frequently", "Daily"]:
#                         update_dict[key] = DrinkingFrequency(value)
#                 elif key in ["height", "weight"]:
#                     try:
#                         update_dict[key] = float(value)
#                     except (ValueError, TypeError):
#                         raise HTTPException(
#                             status_code=status.HTTP_400_BAD_REQUEST,
#                             detail=f"字段 {key} 必须是数字"
#                         )
#                 elif key == "age":
#                     try:
#                         # 将年龄转换为出生日期
#                         from datetime import date
#                         current_year = date.today().year
#                         birth_year = current_year - int(value)
#                         update_dict["date_of_birth"] = date(birth_year, 1, 1)  # 假设生日为1月1日
#                     except (ValueError, TypeError):
#                         raise HTTPException(
#                             status_code=status.HTTP_400_BAD_REQUEST,
#                             detail="年龄必须是有效的数字"
#                         )
#
#         # 更新患者信息
#         patient = update_patient_record(db, patient_id, update_dict)
#         if not patient:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="更新失败"
#             )
#
#         return patient
#     except ValueError as e:
#         db.rollback()
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail=f"数据格式错误: {str(e)}"
#         )
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail=f"更新失败: {str(e)}"
#         )


# 在 router 中定义接口
@router.put("/patients/me/first-login")
async def update_current_patient_first_login(
        update_data: FirstLoginUpdate,
        token: str = Depends(oauth2_scheme),
        db: Session = Depends(get_db)
):
    """当前患者首次登录更新个人信息"""
    #try: 先别try了，一直报错浪费时间
    # 验证令牌
    logger.info(f"接收首次登录请求: {update_data.dict()}")

    payload = decode_token(token)
    if not payload or payload.get("user_type") != "patient":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的令牌或权限不足"
        )

    patient_id = int(payload.get("sub"))
    logger.info(f"患者ID: {patient_id}")

    # 获取患者
    patient = get_patient_by_id(db, patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="患者不存在"
        )

    # 验证必填字段
    if update_data.height is None or update_data.weight is None or update_data.age is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="身高、体重、年龄为必填项"
        )

    # 处理特殊字段转换
    update_dict = {}

    # 1. 处理性别
    if update_data.sex:
        if update_data.sex in ["Female", "Male", "Prefer not to tell"]:
            update_dict["sex"] = update_data.sex
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的性别选项"
            )

    # 2. 处理家族病史
    if update_data.family_history:
        if update_data.family_history == "Yes":
            update_dict["family_history"] = "Yes"  # 转为数据库期望的大写形式
        elif update_data.family_history == "No":
            update_dict["family_history"] = "No"
        elif update_data.family_history == "Unknown":
            update_dict["family_history"] = "Unknown"  # 数据库是Unknown
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的家族病史选项"
            )

    # 3. 处理吸烟
    if update_data.smoking:
        if update_data.smoking in ["Yes", "No"]:
            update_dict["smoking_status"] = update_data.smoking
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的吸烟选项"
            )

    # 4. 处理饮酒
    if update_data.drinking:
        if update_data.drinking in ["Never", "Rarely", "Occasionally", "Frequently", "Daily"]:
            update_dict["drinking_history"] = update_data.drinking
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的饮酒频率选项"
            )

    # 5. 处理身高体重
    update_dict["height"] = float(update_data.height)
    update_dict["weight"] = float(update_data.weight)

    # 6. 将年龄转换为出生日期
    from datetime import date
    current_year = date.today().year
    birth_year = current_year - update_data.age
    # 假设生日为1月1日
    update_dict["date_of_birth"] = date(birth_year, 1, 1)

    # 7. 标记首次登录完成
    # 如果您的Patient模型中有first_login_completed字段，取消注释下面这行
    # update_dict["first_login_completed"] = True

    logger.info(f"更新参数: {update_dict}")

    # 调用现有的更新函数
    patient = update_patient_record(db, patient_id, update_dict)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="更新失败"
        )

    logger.info(f"更新成功: patient_id={patient.patient_id}")
    # 返回一个简单的字典，而不是 patient 对象，以避免序列化问题
    return {
        "patient_id": patient.patient_id,
        "login_code": patient.login_code,
        "first_name": patient.first_name,
        "last_name": patient.last_name,
        "height": float(patient.height) if patient.height else None,
        "weight": float(patient.weight) if patient.weight else None,
        "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
        "sex": patient.sex,
        "family_history": patient.family_history,
        "smoking_status": patient.smoking_status,
        "drinking_history": patient.drinking_history,
        "assigned_nurse_id": patient.assigned_nurse_id,
        "full_name": patient.full_name,
        "age": patient.age,
        "bmi": patient.bmi
    }

    # except HTTPException:
    #     raise
    # except Exception as e:
    #     db.rollback()
    #     logger.error(f"首次登录更新失败: {str(e)}", exc_info=True)
    #     raise HTTPException(
    #         status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    #         detail=f"服务器内部错误: {str(e)}"
    #     )


# ==================== 血糖记录相关 API ====================
from sql.login_models import BloodGlucoseRecord


@router.post("/patients/me/blood-glucose", response_model=dict)
async def add_blood_glucose_record(
    record: dict,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_patient_info)
):
    """添加血糖记录"""
    try:
        logger.info(f"接收到添加血糖记录请求: {record}")
        logger.info(f"当前用户信息: {current_user}")
        
        # 验证必填字段
        if 'value' not in record or record['value'] is None:
            logger.error("血糖值不能为空")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="血糖值不能为空"
            )
        
        if 'period' not in record or record['period'] is None:
            logger.error("测量时段不能为空")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="测量时段不能为空"
            )
        
        # 验证血糖值格式
        try:
            glucose_value = float(record['value'])
            logger.info(f"验证血糖值: {glucose_value}")
        except (ValueError, TypeError):
            logger.error(f"血糖值格式错误: {record['value']}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="血糖值必须是数字"
            )
        
        # 验证测量时段
        valid_periods = ['空腹', '餐前', '餐后', '睡前']
        if record['period'] not in valid_periods:
            logger.error(f"测量时段无效: {record['period']}")
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"测量时段必须是以下之一: {', '.join(valid_periods)}"
            )
        
        # 处理时间字段
        recorded_at = record.get('time')
        if isinstance(recorded_at, str):
            try:
                from datetime import datetime
                recorded_at = datetime.fromisoformat(recorded_at)
                logger.info(f"解析时间成功: {recorded_at}")
            except Exception as e:
                logger.error(f"时间格式错误: {e}")
                recorded_at = datetime.now()
                logger.info(f"使用当前时间: {recorded_at}")
        elif recorded_at is None:
            from datetime import datetime
            recorded_at = datetime.now()
            logger.info(f"使用当前时间: {recorded_at}")
        
        logger.info(f"准备创建血糖记录: patient_login_code={current_user['login_code']}, value={glucose_value}, period={record['period']}, recorded_at={recorded_at}")
        
        new_record = BloodGlucoseRecord(
            patient_login_code=current_user['login_code'],
            value=glucose_value,
            period=record['period'],
            recorded_at=recorded_at
        )
        
        logger.info(f"创建BloodGlucoseRecord对象成功")
        
        db.add(new_record)
        logger.info("添加到数据库会话")
        
        db.commit()
        logger.info("数据库提交成功")
        
        db.refresh(new_record)
        logger.info(f"刷新对象成功: id={new_record.id}")
        
        logger.info(f"血糖记录添加成功: id={new_record.id}, value={new_record.value}")
        
        return {
            "success": True,
            "message": "血糖记录添加成功",
            "data": {
                "id": new_record.id,
                "value": float(new_record.value),
                "period": new_record.period,
                "recorded_at": new_record.recorded_at.isoformat()
            }
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"添加血糖记录失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="添加血糖记录失败"
        )


@router.get("/patients/me/blood-glucose", response_model=dict)
async def get_blood_glucose_records(
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_patient_info)
):
    """获取血糖记录列表"""
    try:
        records = db.query(BloodGlucoseRecord).filter(
            BloodGlucoseRecord.patient_login_code == current_user['login_code']
        ).order_by(
            BloodGlucoseRecord.recorded_at.desc()
        ).limit(limit).offset(offset).all()
        
        total = db.query(BloodGlucoseRecord).filter(
            BloodGlucoseRecord.patient_login_code == current_user['login_code']
        ).count()
        
        return {
            "success": True,
            "data": {
                "records": [
                    {
                        "id": record.id,
                        "value": float(record.value),
                        "period": record.period,
                        "recorded_at": record.recorded_at.isoformat()
                    }
                    for record in records
                ],
                "total": total,
                "limit": limit,
                "offset": offset
            }
        }
    except Exception as e:
        logger.error(f"获取血糖记录失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取血糖记录失败"
        )


@router.get("/patients/me/blood-glucose/latest", response_model=dict)
async def get_latest_blood_glucose(
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_patient_info)
):
    """获取最新血糖记录"""
    try:
        record = db.query(BloodGlucoseRecord).filter(
            BloodGlucoseRecord.patient_login_code == current_user['login_code']
        ).order_by(
            BloodGlucoseRecord.recorded_at.desc()
        ).first()
        
        if record:
            return {
                "success": True,
                "data": {
                    "id": record.id,
                    "value": float(record.value),
                    "period": record.period,
                    "recorded_at": record.recorded_at.isoformat()
                }
            }
        else:
            return {
                "success": True,
                "data": None
            }
    except Exception as e:
        logger.error(f"获取最新血糖记录失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="获取最新血糖记录失败"
        )


@router.delete("/patients/me/blood-glucose/{record_id}", response_model=dict)
async def delete_blood_glucose_record(
    record_id: int,
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_patient_info)
):
    """删除血糖记录"""
    try:
        record = db.query(BloodGlucoseRecord).filter(
            BloodGlucoseRecord.id == record_id,
            BloodGlucoseRecord.patient_login_code == current_user['login_code']
        ).first()
        
        if not record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="血糖记录不存在"
            )
        
        db.delete(record)
        db.commit()
        
        return {
            "success": True,
            "message": "血糖记录删除成功"
        }
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"删除血糖记录失败: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="删除血糖记录失败"
        )
