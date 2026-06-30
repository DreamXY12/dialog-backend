from __future__ import annotations
from datetime import timedelta, datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel, Field
import pytz
tz = pytz.timezone("Asia/Hong_Kong")

# 你原有的配置
ACCESS_TOKEN_EXPIRE_DAYS = 7
ACCESS_TOKEN_EXPIRE_MINUTES = ACCESS_TOKEN_EXPIRE_DAYS * 24 * 60

# 导入你的项目依赖
from sql.start import get_db
from sql.people_models import Nurse, Patient, PatientLoginCode, NurseLoginCode
from utility.fun_tool import create_access_token

# 路由
router = APIRouter(tags=["auth/register-4code"])

# ---------------------------
# 1. 請求體：移除長度限制 + 繁體描述
# ---------------------------
class BaseRegisterRequest(BaseModel):
    phone: str = Field(..., description="帶區號的手機號")
    login_code: str = Field(..., description="登入密碼")  # 已移除長度限制
    first_name: str = Field(..., description="姓氏")
    last_name: str = Field(..., description="名字")
    phone_area_code: Optional[str] = Field(None, description="手機號區號")

class PatientRegisterRequest(BaseRegisterRequest):
    assigned_nurse_id: Optional[int] = Field(None, description="負責護士ID")

class NurseRegisterRequest(BaseRegisterRequest):
    pass

# ---------------------------
# 2. 響應模型
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
# 3. 工具函數：明文驗證（無加密）
# ---------------------------
def verify_plain_login_code(
    db: Session,
    phone: str,
    plain_code: str,
    role: str
):
    """
    驗證前端傳入的登入密碼是否存在且未綁定使用者
    註冊時必須校驗！
    """
    # 直接明文查詢，無加密
    if role == "patient":
        record = db.query(PatientLoginCode).filter(
            PatientLoginCode.login_code_hash == plain_code,
            PatientLoginCode.patient_id == None
        ).first()
    else:
        record = db.query(NurseLoginCode).filter(
            NurseLoginCode.login_code_hash == plain_code,
            NurseLoginCode.nurse_id == None
        ).first()

    if not record:
        # 遍歷未綁定的記錄，明文比對
        if role == "patient":
            all_records = db.query(PatientLoginCode).filter(PatientLoginCode.patient_id == None).all()
        else:
            all_records = db.query(NurseLoginCode).filter(NurseLoginCode.nurse_id == None).all()

        for r in all_records:
            if r.login_code_hash == plain_code:
                return r

        raise HTTPException(status_code=400, detail="登入密碼無效或已被使用")
    return record

# ---------------------------
# 4. 建立使用者函數
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
        create_time=datetime.now(tz),
        update_time=datetime.now(tz)
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
        create_time=datetime.now(tz=tz),
        update_time=datetime.now(tz=tz)
    )
    db.add(new_nurse)
    db.commit()
    db.refresh(new_nurse)
    return new_nurse

# ---------------------------
# 6. 病患註冊
# ---------------------------
@router.post("/patients/register-by-code", response_model=CommonTokenResponse)
async def register_patient(
    request: PatientRegisterRequest,
    db: Session = Depends(get_db)
):
    try:
        # 1. 校驗手機號未註冊
        existing = db.query(Patient).filter(Patient.phone == request.phone).first()
        if existing:
            raise HTTPException(status_code=400, detail="手機號已註冊")

        # 2. 校驗登入密碼有效且未綁定
        code_record = verify_plain_login_code(
            db=db,
            phone=request.phone,
            plain_code=request.login_code,
            role="patient"
        )

        # 3. 建立病患
        patient = create_patient_record(
            db=db,
            phone=request.phone,
            first_name=request.first_name,
            last_name=request.last_name,
            phone_area_code=request.phone_area_code,
            assigned_nurse_id=request.assigned_nurse_id
        )
        if not patient:
            raise HTTPException(status_code=400, detail="註冊失敗")

        # 4. 綁定登入密碼到病患
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
        raise HTTPException(status_code=500, detail=f"註冊失敗：{str(e)}")

# ---------------------------
# 7. 護士註冊
# ---------------------------
@router.post("/nurses/register-by-code", response_model=CommonTokenResponse)
async def register_nurse(
    request: NurseRegisterRequest,
    db: Session = Depends(get_db)
):
    try:
        # 1. 校驗手機號
        existing = db.query(Nurse).filter(Nurse.phone == request.phone).first()
        if existing:
            raise HTTPException(status_code=400, detail="手機號已註冊")

        # 2. 校驗登入密碼
        code_record = verify_plain_login_code(
            db=db,
            phone=request.phone,
            plain_code=request.login_code,
            role="nurse"
        )

        # 3. 建立護士
        nurse = create_nurse_record(
            db=db,
            phone=request.phone,
            first_name=request.first_name,
            last_name=request.last_name,
            phone_area_code=request.phone_area_code
        )
        if not nurse:
            raise HTTPException(status_code=400, detail="註冊失敗")

        # 4. 綁定登入密碼
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
        raise HTTPException(status_code=500, detail=f"註冊失敗：{str(e)}")