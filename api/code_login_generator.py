from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional

# 你的数据库依赖
from sql.start import get_db

# 导入你的模型 + 查询函数
from sql.people_models import Patient, Nurse
from sql.patient_curd import get_patient_by_phone    # 你提供的
from sql.nurse_curd import get_nurse_by_phone        # 你提供的

# 导入登录码模型
from sql.people_models import PatientLoginCode, NurseLoginCode

# 工具
import random
import bcrypt

# ---------------------------
# 路由配置（和你短信接口一模一样）
# ---------------------------
router = APIRouter(prefix="/login-code", tags=["login-code-generator"])

# ---------------------------
# 请求体（和短信接口完全一致）
# ---------------------------
class LoginCodeRequest(BaseModel):
    phone: str = Field(..., description="带国际区号的手机号（如+85212345678）")
    role: str = Field(..., pattern="^(patient|nurse)$", description="用户角色：patient/nurse")
    mode: str = Field(..., pattern="^(login|register|reset)$", description="用途：register / reset")

# ---------------------------
# 工具函数（4位码生成 + 加密）
# ---------------------------
def generate_4digit_code() -> str:
    return f"{random.randint(0, 9999):04d}"

def hash_code(plain_code: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plain_code.encode("utf-8"), salt).decode("utf-8")

# ---------------------------
# 核心：生成唯一不重复的登录码（你要的：先查再插）
# ---------------------------
def generate_unique_login_code(db: Session) -> str:
    while True:
        code = generate_4digit_code()
        code_hash = hash_code(code)

        # 全局不重复
        patient_exists = db.query(PatientLoginCode).filter(PatientLoginCode.login_code_hash == code_hash).first()
        nurse_exists = db.query(NurseLoginCode).filter(NurseLoginCode.login_code_hash == code_hash).first()

        if not patient_exists and not nurse_exists:
            return code

# ---------------------------
# 主接口：获取/重置 4位登录码
# ---------------------------
@router.post("/generate", status_code=status.HTTP_200_OK)
async def generate_login_code(
    request: LoginCodeRequest,
    db: Session = Depends(get_db)
):
    phone = request.phone
    role = request.role
    mode = request.mode

    try:
        # ==============================================
        # 1. 注册模式：必须确保【手机号未注册】才能生成码
        # ==============================================
        if mode == "register":
            if role == "patient":
                exists = get_patient_by_phone(db, phone)
                if exists:
                    raise HTTPException(status_code=400, detail="患者手机号已注册，请直接登录")
            else:
                exists = get_nurse_by_phone(db, phone)
                if exists:
                    raise HTTPException(status_code=400, detail="护士手机号已注册，请直接登录")

        # ==============================================
        # 2. 重置模式：必须确保【手机号已注册】才能重置
        # ==============================================
        elif mode == "reset":
            if role == "patient":
                user = get_patient_by_phone(db, phone)
                if not user:
                    raise HTTPException(status_code=400, detail="患者手机号未注册")
                user_id = user.patient_id
            else:
                user = get_nurse_by_phone(db, phone)
                if not user:
                    raise HTTPException(status_code=400, detail="护士手机号未注册")
                user_id = user.nurse_id

        # ==============================================
        # 3. 生成唯一 4 位码
        # ==============================================
        plain_code = generate_unique_login_code(db)
        code_hash = hash_code(plain_code)

        # ==============================================
        # 4. 保存 or 更新 登录码
        # ==============================================
        if role == "patient":
            # 注册模式
            if mode == "register":
                code_record = PatientLoginCode(
                    patient_id=None,  # 注册时还没有patient_id，留空 → 注册时再补上
                    login_code_hash=code_hash,
                    is_active=True
                )
                db.add(code_record)
                db.commit()
                return {
                    "login_code": plain_code,
                    "message": "患者登录码生成成功"
                }

            # 重置模式
            elif mode == "reset":
                record = db.query(PatientLoginCode).filter(PatientLoginCode.patient_id == user_id).first()
                if not record:
                    raise HTTPException(status_code=404, detail="未找到该患者的登录码")
                record.login_code_hash = code_hash
                db.commit()
                return {
                    "login_code": plain_code,
                    "message": "患者登录码重置成功"
                }

        else:  # nurse
            if mode == "register":
                code_record = NurseLoginCode(
                    nurse_id=None,
                    login_code_hash=code_hash,
                    is_active=True
                )
                db.add(code_record)
                db.commit()
                return {
                    "login_code": plain_code,
                    "message": "护士登录码生成成功"
                }

            elif mode == "reset":
                record = db.query(NurseLoginCode).filter(NurseLoginCode.nurse_id == user_id).first()
                if not record:
                    raise HTTPException(status_code=404, detail="未找到该护士的登录码")
                record.login_code_hash = code_hash
                db.commit()
                return {
                    "login_code": plain_code,
                    "message": "护士登录码重置成功"
                }

        return {"message": "操作成功", "login_code": plain_code}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"生成登录码失败：{str(e)}"
        )