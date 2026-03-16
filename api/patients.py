# 病人的相关操作，网页端对应的后端操作
from fastapi import APIRouter, Depends, HTTPException, status, Header,Query
import logging
from pydantic import BaseModel, Field
from typing import Optional,Dict,Any
from sql.start import get_db
from utility.fun_tool import decode_token
from api.auth import oauth2_scheme
from sqlalchemy.orm import Session
from sql.people_models import Gender, FamilyHistory, SmokingStatus, DrinkingFrequency
from sql.patient_curd import get_patient_by_id,update_patient_record
from datetime import date, datetime
from sql.nurse_curd import get_nurse_by_id
from sql.patient_curd import get_patient_by_phone
from sql.people_models import Patient,BloodGlucoseRecord

# 后端前缀
router = APIRouter(prefix="/patients", tags=["patient"])

logger = logging.getLogger(__name__)

# 更新患者体重
class PatientWeightUpdate(BaseModel):
    """更新体重的请求体模型（匹配你的代码风格）"""
    weight: float = Field(..., gt=0, le=500, description="体重（公斤），范围0-500")

    class Config:
        schema_extra = {
            "example": {
                "weight": 65.5
            }
        }

# 严格匹配前端传参的请求体模型（移除所有护士相关字段）
class FirstLoginUpdate(BaseModel):
    height: float = Field(..., gt=0, le=250, description="身高（厘米），范围0-250")
    weight: float = Field(..., gt=0, le=500, description="体重（公斤），范围0-500")
    age: int = Field(..., gt=0, le=120, description="年龄，范围1-120")
    sex: Optional[str] = None
    family_history: Optional[str] = None
    smoking: Optional[str] = None
    drinking: Optional[str] = None

    class Config:
        schema_extra = {
            "example": {
                "height": 175.5,
                "weight": 65.0,
                "age": 30,
                "sex": "Female",
                "family_history": "No",
                "smoking": "No",
                "drinking": "Never"
            }
        }

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
        "patient_phone": patient.phone,
        "patient_id": patient.patient_id,
        "full_name": patient.full_name
    }


@router.put("/me/first-login")
async def update_current_patient_first_login(
        update_data: FirstLoginUpdate,
        token: str = Depends(oauth2_scheme),
        db: Session = Depends(get_db)
):
    """当前患者首次登录更新个人信息（仅支持前端传递的字段，移除护士关联逻辑）"""
    logger.info(f"接收首次登录请求: {update_data.dict()}")

    # 验证令牌
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

    # 构建更新字典（仅处理前端传递的字段）
    update_dict = {}

    # 1. 性别字段（严格匹配枚举值）
    if update_data.sex:
        valid_sex = [e.value for e in Gender]
        if update_data.sex in valid_sex:
            update_dict["sex"] = update_data.sex
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的性别选项，仅支持：{valid_sex}"
            )

    # 2. 家族病史（严格匹配枚举值）
    if update_data.family_history:
        valid_fh = [e.value for e in FamilyHistory]
        if update_data.family_history in valid_fh:
            update_dict["family_history"] = update_data.family_history
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的家族病史选项，仅支持：{valid_fh}"
            )

    # 3. 吸烟状态（补充Prefer not to tell选项）
    if update_data.smoking:
        valid_smoking = [e.value for e in SmokingStatus]
        if update_data.smoking in valid_smoking:
            update_dict["smoking_status"] = update_data.smoking
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的吸烟选项，仅支持：{valid_smoking}"
            )

    # 4. 饮酒频率（严格匹配枚举值）
    if update_data.drinking:
        valid_drinking = [e.value for e in DrinkingFrequency]
        if update_data.drinking in valid_drinking:
            update_dict["drinking_history"] = update_data.drinking
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"无效的饮酒频率选项，仅支持：{valid_drinking}"
            )

    # 5. 身高体重（已通过Pydantic校验，直接赋值）
    update_dict["height"] = float(update_data.height)
    update_dict["weight"] = float(update_data.weight)

    # 6. 年龄转出生日期（优化边界：避免未来日期）
    current_year = date.today().year
    birth_year = current_year - update_data.age
    # 防止年龄过大导致出生年份为负数
    if birth_year < 1900:
        birth_year = 1900
    update_dict["date_of_birth"] = date(birth_year, 1, 1)

    logger.info(f"更新参数: {update_dict}")

    # 调用更新函数
    patient = update_patient_record(db, patient_id, update_dict)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="更新失败"
        )

    logger.info(f"更新成功: patient_id={patient.patient_id}")

    # 返回序列化结果（移除所有护士相关字段）
    return {
        "patient_id": patient.patient_id,
        "phone": patient.phone,  # 替换原login_code（新模型无login_code）
        "first_name": patient.first_name,
        "last_name": patient.last_name,
        "height": float(patient.height) if patient.height else None,
        "weight": float(patient.weight) if patient.weight else None,
        "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
        "sex": patient.sex.value if patient.sex else None,  # 枚举值转字符串
        "family_history": patient.family_history.value if patient.family_history else None,
        "smoking_status": patient.smoking_status.value if patient.smoking_status else None,
        "drinking_history": patient.drinking_history.value if patient.drinking_history else None,
        "full_name": patient.full_name,
        "age": patient.age,
        "bmi": patient.bmi
    }

@router.get("/me/profile")
async def get_patient_profile(
        phone: str = Query(..., description="患者登录手机号（带区号，如+85212345678）"),
        db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    获取病人完整资料
    通过手机号验证身份（替代原登录码）
    """
    # 1. 验证参数合法性
    if not phone or len(phone.strip()) == 0:
        raise HTTPException(
            status_code=400,
            detail="手机号不能为空"
        )

    # 2. 根据手机号查询患者信息（替换原login_code查询）
    patient = get_patient_by_phone(db, phone.strip())
    if not patient or not isinstance(patient, Patient):
        raise HTTPException(
            status_code=401,
            detail="手机号错误或患者不存在"
        )
    logger.info(f"患者{phone}请求个人资料，ID: {patient.patient_id}")

    # 3. 计算年龄（保留原逻辑）
    age = None
    if patient.date_of_birth:
        today = date.today()
        age = today.year - patient.date_of_birth.year
        # 未到生日则年龄减1
        if (today.month, today.day) < (patient.date_of_birth.month, patient.date_of_birth.day):
            age -= 1

    # 4. 计算BMI（保留原逻辑，增加零值校验）
    bmi = None
    if patient.height and patient.weight and float(patient.height) > 0:
        height_m = float(patient.height) / 100
        bmi = round(float(patient.weight) / (height_m ** 2), 1)

    # 5. 获取护士信息（适配新模型：按手机号查询）
    nurse_info = None
    if patient.assigned_nurse_id:
        nurse = get_nurse_by_id(db, patient.assigned_nurse_id)
        if nurse:
            nurse_info = {
                "nurse_id": nurse.nurse_id,
                "phone": nurse.phone,  # 补充护士手机号
                "first_name": nurse.first_name,
                "last_name": nurse.last_name,
                "full_name": f"{nurse.first_name}{nurse.last_name}"
            }

    # 6. 构建响应（适配新模型，优化枚举字段返回）
    response = {
        "patient": {
            "patient_id": patient.patient_id,
            "phone": patient.phone,  # 返回患者手机号（替代原login_code）
            "phone_area_code":patient.phone_area_code,
            "first_name": patient.first_name,
            "last_name": patient.last_name,
            "full_name": f"{patient.first_name}{patient.last_name}",
            "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
            "age": age,
            # 枚举字段转为字符串（避免序列化问题）
            "sex": patient.sex.value if patient.sex else None,
            "family_history": patient.family_history.value if patient.family_history else None,
            "smoking_status": patient.smoking_status.value if patient.smoking_status else None,
            "drinking_history": patient.drinking_history.value if patient.drinking_history else None,
            "height": float(patient.height) if patient.height else None,
            "weight": float(patient.weight) if patient.weight else None,
            "bmi": bmi,
            "assigned_nurse_id": patient.assigned_nurse_id  # 补充护士ID
        },
        "nurse": nurse_info
    }

    return response

@router.put("/me/weight")
async def update_patient_weight(
        weight_data: PatientWeightUpdate,
        token: str = Depends(oauth2_scheme),
        db: Session = Depends(get_db)
):
    """
    当前患者更新体重信息
    通过token验证身份，仅更新体重字段
    """
    logger.info(f"接收体重更新请求: {weight_data.dict()}")

    # 1. 验证令牌（复用你现有逻辑）
    payload = decode_token(token)
    if not payload or payload.get("user_type") != "patient":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的令牌或权限不足"
        )

    patient_id = int(payload.get("sub"))
    logger.info(f"患者ID {patient_id} 请求更新体重")

    # 2. 查询患者是否存在
    patient = get_patient_by_id(db, patient_id)
    if not patient:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="患者不存在"
        )

    # 3. 构建更新字典（仅体重字段）
    update_dict = {
        "weight": float(weight_data.weight)
    }

    # 4. 调用现有更新函数（复用你已有的update_patient_record）
    updated_patient = update_patient_record(db, patient_id, update_dict)
    if not updated_patient:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="体重更新失败"
        )

    logger.info(f"患者ID {patient_id} 体重更新成功: {weight_data.weight}kg")

    # 5. 返回更新结果（保持和你现有接口一致的响应格式）
    return {
        "patient_id": updated_patient.patient_id,
        "phone": updated_patient.phone,
        "full_name": updated_patient.full_name,
        "weight": float(updated_patient.weight) if updated_patient.weight else None,
        "bmi": updated_patient.bmi,  # 自动返回更新后的BMI
        "message": "体重更新成功"
    }

# ========== 单独获取体重接口（方便前端查询） ==========
@router.get("/me/weight")
async def get_patient_weight(
        phone: str = Query(..., description="患者登录手机号（带区号，如+85212345678）"),
        db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    获取患者当前体重信息
    通过手机号验证身份
    """
    # 1. 验证参数
    if not phone or len(phone.strip()) == 0:
        raise HTTPException(
            status_code=400,
            detail="手机号不能为空"
        )

    # 2. 查询患者
    patient = get_patient_by_phone(db, phone.strip())
    if not patient:
        raise HTTPException(
            status_code=404,
            detail="患者不存在"
        )

    # 3. 返回体重信息
    return {
        "patient_id": patient.patient_id,
        "phone": patient.phone,
        "full_name": patient.full_name,
        "weight": float(patient.weight) if patient.weight else None,
        "bmi": patient.bmi,
        "message": "获取体重信息成功"
    }

#========血糖记录相关=========#
@router.post("/me/blood-glucose", response_model=dict)
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

        logger.info(
            f"准备创建血糖记录: patient_login_code={current_user['patient_phone']}, value={glucose_value}, period={record['period']}, recorded_at={recorded_at}")

        new_record = BloodGlucoseRecord(
            patient_phone=current_user['patient_phone'],
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


@router.get("/me/blood-glucose", response_model=dict)
async def get_blood_glucose_records(
        limit: int = 20,
        offset: int = 0,
        db: Session = Depends(get_db),
        current_user: dict = Depends(get_current_patient_info)
):
    """获取血糖记录列表"""
    try:
        records = db.query(BloodGlucoseRecord).filter(
            BloodGlucoseRecord.patient_phone == current_user['patient_phone']
        ).order_by(
            BloodGlucoseRecord.recorded_at.desc()
        ).limit(limit).offset(offset).all()

        total = db.query(BloodGlucoseRecord).filter(
            BloodGlucoseRecord.patient_phone == current_user['patient_phone']
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


@router.get("/me/blood-glucose/latest", response_model=dict)
async def get_latest_blood_glucose(
        db: Session = Depends(get_db),
        current_user: dict = Depends(get_current_patient_info)
):
    """获取最新血糖记录"""
    try:
        record = db.query(BloodGlucoseRecord).filter(
            BloodGlucoseRecord.patient_phone == current_user['patient_phone']
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


@router.delete("/me/blood-glucose/{record_id}", response_model=dict)
async def delete_blood_glucose_record(
        record_id: int,
        db: Session = Depends(get_db),
        current_user: dict = Depends(get_current_patient_info)
):
    """删除血糖记录"""
    try:
        record = db.query(BloodGlucoseRecord).filter(
            BloodGlucoseRecord.id == record_id,
            BloodGlucoseRecord.patient_phone == current_user['patient_phone']
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