from __future__ import annotations
from datetime import timedelta, datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel, Field

# 你原有的配置
ACCESS_TOKEN_EXPIRE_DAYS = 3
ACCESS_TOKEN_EXPIRE_MINUTES = ACCESS_TOKEN_EXPIRE_DAYS * 24 * 60

# 导入你的项目依赖
from sql.start import get_db
from sql.people_models import Nurse, Patient, PatientLoginCode, NurseLoginCode
from utility.fun_tool import create_access_token
import bcrypt

# 路由
router = APIRouter(tags=["auth/register-4code"])

# ---------------------------
# 1. 请求体：增加 login_code（前端传入）
# ---------------------------
class BaseRegisterRequest(BaseModel):
    phone: str = Field(..., description="带区号的手机号")
    login_code: str = Field(..., min_length=4, max_length=4, description="4位数字登录码")  # 新增
    first_name: str = Field(..., description="姓氏")
    last_name: str = Field(..., description="名字")
    phone_area_code: Optional[str] = Field(None, description="手机号区号")

class PatientRegisterRequest(BaseRegisterRequest):
    assigned_nurse_id: Optional[int] = Field(None, description="负责护士ID")

class NurseRegisterRequest(BaseRegisterRequest):
    pass

# ---------------------------
# 2. 响应模型（不变）
# ---------------------------
class CommonTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user_type: str
    user_id: int
    first_name: str
    last_name: str
    phone: str
    phone_area_code: Optional[str] = None
    full_name: str
    login_code: str
    is_first_login: bool = True

    class Config:
        from_attributes = True

# ---------------------------
# 3. 工具函数：验证登录码是否有效（未绑定）
# ---------------------------
def verify_plain_login_code(
    db: Session,
    phone: str,
    plain_code: str,
    role: str
):
    """
    验证前端传入的4位登录码是否存在且未绑定用户
    注册时必须校验！
    """
    code_hash = bcrypt.hashpw(plain_code.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    # 这里用查询已存在的hash
    if role == "patient":
        record = db.query(PatientLoginCode).filter(
            PatientLoginCode.login_code_hash == code_hash,
            PatientLoginCode.patient_id == None  # 未绑定用户
        ).first()
    else:
        record = db.query(NurseLoginCode).filter(
            NurseLoginCode.login_code_hash == code_hash,
            NurseLoginCode.nurse_id == None
        ).first()

    if not record:
        # 暴力匹配所有未绑定的码
        if role == "patient":
            all_records = db.query(PatientLoginCode).filter(PatientLoginCode.patient_id == None).all()
        else:
            all_records = db.query(NurseLoginCode).filter(NurseLoginCode.nurse_id == None).all()

        for r in all_records:
            if bcrypt.checkpw(plain_code.encode(), r.login_code_hash.encode()):
                return r

        raise HTTPException(status_code=400, detail="登录码无效或已被使用")
    return record

# ---------------------------
# 4. 原有创建用户函数（完全不变）
# ---------------------------
def create_patient_record(db: Session, phone: str, first_name: str, last_name: str, phone_area_code: Optional[str] = None, assigned_nurse_id: Optional[int] = None):
    existing = db.query(Patient).filter(Patient.phone == phone).first()
    if existing:
        return None
    new_patient = Patient(
        phone=phone,
        phone_area_code=phone_area_code,
        first_name=first_name,
        last_name=last_name,
        assigned_nurse_id=assigned_nurse_id,
        create_time=datetime.now(),
        update_time=datetime.now()
    )
    db.add(new_patient)
    db.commit()
    db.refresh(new_patient)
    return new_patient

def create_nurse_record(db: Session, phone: str, first_name: str, last_name: str, phone_area_code: Optional[str] = None):
    existing = db.query(Nurse).filter(Nurse.phone == phone).first()
    if existing:
        return None
    new_nurse = Nurse(
        phone=phone,
        phone_area_code=phone_area_code,
        first_name=first_name,
        last_name=last_name,
        create_time=datetime.now(),
        update_time=datetime.now()
    )
    db.add(new_nurse)
    db.commit()
    db.refresh(new_nurse)
    return new_nurse

# ---------------------------
# 6. 患者注册（仅绑定，不生成）
# ---------------------------
@router.post("/patients/register-by-code", response_model=CommonTokenResponse)
async def register_patient(
    request: PatientRegisterRequest,
    db: Session = Depends(get_db)
):
    try:
        # 1. 校验手机号未注册
        existing = db.query(Patient).filter(Patient.phone == request.phone).first()
        if existing:
            raise HTTPException(status_code=400, detail="手机号已注册")

        # 2. 校验登录码有效且未绑定
        code_record = verify_plain_login_code(
            db=db,
            phone=request.phone,
            plain_code=request.login_code,
            role="patient"
        )

        # 3. 创建患者
        patient = create_patient_record(
            db=db,
            phone=request.phone,
            first_name=request.first_name,
            last_name=request.last_name,
            phone_area_code=request.phone_area_code,
            assigned_nurse_id=request.assigned_nurse_id
        )
        if not patient:
            raise HTTPException(status_code=400, detail="注册失败")

        # 4. 绑定登录码到患者（核心！）
        code_record.patient_id = patient.patient_id
        db.commit()

        # 5. 生成Token
        access_token = create_access_token(
            data={
                "sub": str(patient.patient_id),
                "user_type": "patient",
                "phone": patient.phone
            },
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )

        return CommonTokenResponse(
            access_token=access_token,
            user_type="patient",
            user_id=patient.patient_id,
            first_name=patient.first_name,
            last_name=patient.last_name,
            phone=patient.phone,
            phone_area_code=patient.phone_area_code,
            full_name=f"{patient.first_name}{patient.last_name}",
            login_code=request.login_code
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"注册失败：{str(e)}")

# ---------------------------
# 7. 护士注册（仅绑定，不生成）
# ---------------------------
@router.post("/nurses/register-by-code", response_model=CommonTokenResponse)
async def register_nurse(
    request: NurseRegisterRequest,
    db: Session = Depends(get_db)
):
    try:
        # 1. 校验手机号
        existing = db.query(Nurse).filter(Nurse.phone == request.phone).first()
        if existing:
            raise HTTPException(status_code=400, detail="手机号已注册")

        # 2. 校验登录码
        code_record = verify_plain_login_code(
            db=db,
            phone=request.phone,
            plain_code=request.login_code,
            role="nurse"
        )

        # 3. 创建护士
        nurse = create_nurse_record(
            db=db,
            phone=request.phone,
            first_name=request.first_name,
            last_name=request.last_name,
            phone_area_code=request.phone_area_code
        )
        if not nurse:
            raise HTTPException(status_code=400, detail="注册失败")

        # 4. 绑定登录码
        code_record.nurse_id = nurse.nurse_id
        db.commit()

        # 5. 生成Token
        access_token = create_access_token(
            data={
                "sub": str(nurse.nurse_id),
                "user_type": "nurse",
                "phone": nurse.phone
            },
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )

        return CommonTokenResponse(
            access_token=access_token,
            user_type="nurse",
            user_id=nurse.nurse_id,
            first_name=nurse.first_name,
            last_name=nurse.last_name,
            phone=nurse.phone,
            phone_area_code=nurse.phone_area_code,
            full_name=f"{nurse.first_name}{nurse.last_name}",
            login_code=request.login_code
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"注册失败：{str(e)}")