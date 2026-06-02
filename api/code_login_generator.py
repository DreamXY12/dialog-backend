from fastapi import APIRouter, Depends, status, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional

# 你的数据库依赖
from sql.start import get_db

# 导入你的模型 + 查询函数
from sql.people_models import Patient, Nurse
from sql.patient_curd import get_patient_by_phone
from sql.nurse_curd import get_nurse_by_phone

# 导入登录码模型
from sql.people_models import PatientLoginCode, NurseLoginCode

# 工具
import random

# ---------------------------
# 路由配置
# ---------------------------
router = APIRouter(prefix="/login-code", tags=["login-code-generator"])

# ---------------------------
# 请求体
# ---------------------------
class LoginCodeRequest(BaseModel):
    phone: str = Field(..., description="帶國際區號的手機號（如+85212345678）")
    role: str = Field(..., pattern="^(patient|nurse)$", description="使用者角色：patient/nurse")
    mode: str = Field(..., pattern="^(login|register|reset)$", description="用途：register / reset")

# ---------------------------
# 工具函数（4位码生成，移除加密）
# ---------------------------
def generate_4digit_code() -> str:
    return f"{random.randint(0, 9999):04d}"

# ---------------------------
# 核心：生成唯一不重复的登录码（明文）
# ---------------------------
def generate_unique_login_code(db: Session) -> str:
    while True:
        code = generate_4digit_code()

        # 全局不重复（直接比对明文）
        patient_exists = db.query(PatientLoginCode).filter(PatientLoginCode.login_code_hash == code).first()
        nurse_exists = db.query(NurseLoginCode).filter(NurseLoginCode.login_code_hash == code).first()

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
        # 1. 註冊模式：必須確保【手機號未註冊】才能生成碼
        # ==============================================
        if mode == "register":
            if role == "patient":
                exists = get_patient_by_phone(db, phone)
                if exists:
                    raise HTTPException(status_code=400, detail="病患手機號已註冊，請直接登入")
            else:
                exists = get_nurse_by_phone(db, phone)
                if exists:
                    raise HTTPException(status_code=400, detail="護士手機號已註冊，請直接登入")

        # ==============================================
        # 2. 重置模式：必須確保【手機號已註冊】才能重置
        # ==============================================
        elif mode == "reset":
            if role == "patient":
                user = get_patient_by_phone(db, phone)
                if not user:
                    raise HTTPException(status_code=400, detail="病患手機號未註冊")
                user_id = user.patient_id
            else:
                user = get_nurse_by_phone(db, phone)
                if not user:
                    raise HTTPException(status_code=400, detail="護士手機號未註冊")
                user_id = user.nurse_id

        # ==============================================
        # 3. 生成唯一 4 位碼
        # ==============================================
        plain_code = generate_unique_login_code(db)

        # ==============================================
        # 4. 保存 or 更新 登錄碼（直接存明文）
        # ==============================================
        if role == "patient":
            # 註冊模式
            if mode == "register":
                code_record = PatientLoginCode(
                    patient_id=None,
                    login_code_hash=plain_code,  # 直接存明文
                    is_active=True
                )
                db.add(code_record)
                db.commit()
                return {
                    "login_code": plain_code,
                    "message": "病患登錄碼生成成功"
                }

            # 重置模式
            elif mode == "reset":
                record = db.query(PatientLoginCode).filter(PatientLoginCode.patient_id == user_id).first()
                if not record:
                    raise HTTPException(status_code=404, detail="未找到該病患的登錄碼")
                record.login_code_hash = plain_code  # 直接存明文
                db.commit()
                return {
                    "login_code": plain_code,
                    "message": "病患登錄碼重置成功"
                }

        else:  # nurse
            if mode == "register":
                code_record = NurseLoginCode(
                    nurse_id=None,
                    login_code_hash=plain_code,  # 直接存明文
                    is_active=True
                )
                db.add(code_record)
                db.commit()
                return {
                    "login_code": plain_code,
                    "message": "護士登錄碼生成成功"
                }

            elif mode == "reset":
                record = db.query(NurseLoginCode).filter(NurseLoginCode.nurse_id == user_id).first()
                if not record:
                    raise HTTPException(status_code=404, detail="未找到該護士的登錄碼")
                record.login_code_hash = plain_code  # 直接存明文
                db.commit()
                return {
                    "login_code": plain_code,
                    "message": "護士登錄碼重置成功"
                }

        return {"message": "操作成功", "login_code": plain_code}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"生成登錄碼失敗：{str(e)}"
        )