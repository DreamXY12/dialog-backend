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
    # 新增可选参数
    account_type: Optional[str] = None

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
# 主接口：获取/重置 4位登录码（已改造支持护士账号类型）
# ---------------------------
@router.post("/generate", status_code=status.HTTP_200_OK)
async def generate_login_code(
    request: LoginCodeRequest,
    db: Session = Depends(get_db)
):
    phone = request.phone
    role = request.role
    mode = request.mode
    account_type = request.account_type

    try:
        # 仅护士注册时校验account_type，其余场景清空忽略
        if mode == "register" and role == "nurse":
            if not account_type or account_type not in ("official", "test"):
                raise HTTPException(
                    status_code=400,
                    detail="护士注册必须指定账号类型(official/test)"
                )
        else:
            account_type = None

        # 1. 注册模式：手机号不能已存在
        if mode == "register":
            if role == "patient":
                exists = get_patient_by_phone(db, phone)
                if exists:
                    raise HTTPException(status_code=400, detail="病患手機號已註冊，請直接登入")
            else:
                exists = get_nurse_by_phone(db, phone)
                if exists:
                    raise HTTPException(status_code=400, detail="護士手機號已註冊，請直接登入")

        # 2. 重置模式：手机号必须已注册
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

        # 3. 生成4位唯一登录码
        plain_code = generate_unique_login_code(db)

        # 4. 新增/更新登录码记录
        if role == "patient":
            if mode == "register":
                code_record = PatientLoginCode(
                    patient_id=None,
                    login_code_hash=plain_code,
                    is_active=True
                )
                db.add(code_record)
                db.commit()
                return {
                    "login_code": plain_code,
                    "message": "病患登錄碼生成成功"
                }
            elif mode == "reset":
                record = db.query(PatientLoginCode).filter(PatientLoginCode.patient_id == user_id).first()
                if not record:
                    raise HTTPException(status_code=404, detail="未找到該病患的登錄碼")
                record.login_code_hash = plain_code
                db.commit()
                return {
                    "login_code": plain_code,
                    "message": "病患登錄碼重置成功"
                }
        else:
            # 护士逻辑
            if mode == "register":
                # 存入临时账号类型
                code_record = NurseLoginCode(
                    nurse_id=None,
                    login_code_hash=plain_code,
                    is_active=True,
                    temp_account_type=account_type
                )
                db.add(code_record)
                db.commit()
                return {
                    "login_code": plain_code,
                    "message": f"護士登錄碼生成成功，账号类型：{account_type}"
                }
            elif mode == "reset":
                record = db.query(NurseLoginCode).filter(NurseLoginCode.nurse_id == user_id).first()
                if not record:
                    raise HTTPException(status_code=404, detail="未找到該護士的登錄碼")
                record.login_code_hash = plain_code
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