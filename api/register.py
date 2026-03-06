# 用与患者与病人的注册

from __future__ import annotations
from datetime import timedelta, datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field

# 核心配置：Token有效期3天（全局定义）
ACCESS_TOKEN_EXPIRE_DAYS = 3
ACCESS_TOKEN_EXPIRE_MINUTES = ACCESS_TOKEN_EXPIRE_DAYS * 24 * 60  # 4320分钟

# 导入公共依赖
from sql.start import get_db
from sql.people_models import Nurse, Patient  # 导入护士/患者模型
from utility.fun_tool import create_access_token  # JWT生成函数
from sql.verify_code_curd import verify_verification_code  # 验证码验证函数

# 统一路由（可拆分前缀，也可共用根路由）
router = APIRouter(tags=["auth/register"])  # 统一标签，便于文档区分

# ---------------------------
# 1. 通用模型（核心：统一Token响应+公共请求体）
# ---------------------------
class BaseRegisterRequest(BaseModel):
    """通用注册请求体（护士/患者共用基础字段）"""
    phone: str = Field(..., description="带区号的手机号，如+85212345678")
    verify_code: str = Field(..., min_length=6, max_length=6, description="6位短信验证码")
    first_name: str = Field(..., description="姓氏")
    last_name: str = Field(..., description="名字")
    phone_area_code: Optional[str] = Field(None, description="手机号区号，如+852/+86")

class PatientRegisterRequest(BaseRegisterRequest):
    """患者注册请求体（扩展专属字段）"""
    assigned_nurse_phone: Optional[str] = Field(None, description="负责护士手机号，默认空")

class NurseRegisterRequest(BaseRegisterRequest):
    """护士注册请求体（无扩展字段，直接继承通用体）"""
    pass

class CommonTokenResponse(BaseModel):
    """通用Token响应模型（兼容护士/患者角色）"""
    access_token: str
    token_type: str = "bearer"
    user_type: str  # 动态值："patient" / "nurse"
    user_id: int    # 动态值：patient_id / nurse_id
    first_name: str
    last_name: str
    phone: str
    is_first_login: bool = True
    # 可选：扩展字段（按需添加）
    full_name: str = Field(None, description="完整姓名（姓+名）")
    class Config:
        from_attributes = True

# ---------------------------
# 2. 批量分配请求体（保留护士原有逻辑）
# ---------------------------
class BatchAssignRequest(BaseModel):
    patient_login_codes: List[str]

# ---------------------------
# 3. 核心业务函数（分角色实现）
# ---------------------------
# -------- 患者相关函数 --------
def create_patient_record(
    db: Session,
    phone: str,
    first_name: str,
    last_name: str,
    phone_area_code: Optional[str] = None,
    assigned_nurse_phone: Optional[str] = None
):
    """创建患者记录"""
    # 检查手机号是否已注册
    existing_patient = db.query(Patient).filter(Patient.phone == phone).first()
    if existing_patient:
        return None

    new_patient = Patient(
        phone=phone,
        phone_area_code=phone_area_code,
        first_name=first_name,
        last_name=last_name,
        assigned_nurse_phone=assigned_nurse_phone,
        create_time=datetime.now(),
        update_time=datetime.now()
    )
    db.add(new_patient)
    db.commit()
    db.refresh(new_patient)
    return new_patient

# -------- 护士相关函数 --------
def get_nurse_by_id(db: Session, nurse_id: int):
    """保留原有护士查询函数"""
    return db.query(Nurse).filter(Nurse.nurse_id == nurse_id).first()

def get_all_nurses(db: Session, skip: int = 0, limit: int = 100):
    """保留原有护士查询函数"""
    return db.query(Nurse).offset(skip).limit(limit).all()

def create_nurse_record(
    db: Session,
    phone: str,
    first_name: str,
    last_name: str,
    phone_area_code: Optional[str] = None
):
    """创建护士记录"""
    # 检查手机号是否已注册
    existing_nurse = db.query(Nurse).filter(Nurse.phone == phone).first()
    if existing_nurse:
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
# 4. 注册路由（分角色，统一前缀）
# ---------------------------
@router.post("/patients/register", response_model=CommonTokenResponse, tags=["auth/register/patient"])
async def register_patient(
    request: PatientRegisterRequest,
    db: Session = Depends(get_db)
):
    """患者注册接口"""
    try:
        # 1. 验证验证码
        verify_success = verify_verification_code(
            db=db,
            phone=request.phone,
            code=request.verify_code,
            role="patient",
            mode="register"
        )
        if not verify_success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="验证码错误、已过期或已使用"
            )

        # 2. 创建患者记录
        patient = create_patient_record(
            db=db,
            phone=request.phone,
            first_name=request.first_name,
            last_name=request.last_name,
            phone_area_code=request.phone_area_code,
            assigned_nurse_phone=request.assigned_nurse_phone
        )
        if not patient:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="注册失败，该手机号已注册"
            )

        # 3. 生成Token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={
                "sub": str(patient.patient_id),
                "user_type": "patient",
                "phone": patient.phone
            },
            expires_delta=access_token_expires
        )

        # 4. 返回通用Token响应
        return CommonTokenResponse(
            access_token=access_token,
            user_type="patient",
            user_id=patient.patient_id,
            first_name=patient.first_name,
            last_name=patient.last_name,
            phone=patient.phone,
            full_name=f"{patient.first_name}{patient.last_name}"  # 可选：拼接完整姓名
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"患者注册失败: {str(e)}"
        )

@router.post("/nurses/register", response_model=CommonTokenResponse, tags=["auth/register/nurse"])
async def register_nurse(
    request: NurseRegisterRequest,
    db: Session = Depends(get_db)
):
    """护士注册接口"""
    try:
        # 1. 验证验证码
        verify_success = verify_verification_code(
            db=db,
            phone=request.phone,
            code=request.verify_code,
            role="nurse",
            mode="register"
        )
        if not verify_success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="验证码错误、已过期或已使用"
            )

        # 2. 创建护士记录
        nurse = create_nurse_record(
            db=db,
            phone=request.phone,
            first_name=request.first_name,
            last_name=request.last_name,
            phone_area_code=request.phone_area_code
        )
        if not nurse:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="注册失败，该手机号已注册"
            )

        # 3. 生成Token
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        access_token = create_access_token(
            data={
                "sub": str(nurse.nurse_id),
                "user_type": "nurse",
                "phone": nurse.phone
            },
            expires_delta=access_token_expires
        )

        # 4. 返回通用Token响应
        return CommonTokenResponse(
            access_token=access_token,
            user_type="nurse",
            user_id=nurse.nurse_id,
            first_name=nurse.first_name,
            last_name=nurse.last_name,
            phone=nurse.phone,
            full_name=f"{nurse.first_name}{nurse.last_name}"  # 可选：拼接完整姓名
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"护士注册失败: {str(e)}"
        )
