from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import timedelta, datetime, time
from pydantic import BaseModel, Field
from typing import Optional

# 你的项目依赖
from sql.start import get_db
from sql.common_curd import get_user_by_phone
from api.register import CommonTokenResponse
from utility.fun_tool import create_access_token, decode_token, ACCESS_TOKEN_EXPIRE_MINUTES
from sql.nurse_curd import add_nurse_work_time,get_nurse_by_id
from sql.patient_curd import get_patient_by_id

# 登录码模型
from sql.people_models import PatientLoginCode, NurseLoginCode

# ---------------------------
# 配置
# ---------------------------
router = APIRouter(prefix="/auth-code", tags=["authentication-4code"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth-code/login")

# ---------------------------
# 登录请求体（移除长度限制）
# ---------------------------
class LoginRequest(BaseModel):
    phone: str = Field(..., description="帶區號的手機號，如+85212345678")
    phone_area_code: Optional[str] = Field(None, description="手機號區號，如+852/+86")
    login_code: str = Field(..., description="登入密碼")  # 移除 min_length / max_length
    user_type: str = Field(..., pattern="^(patient|nurse)$", description="使用者類型：patient/nurse")

# ---------------------------
# 登录码验证工具函数（明文对比）
# ---------------------------
def authenticate_user_login_code(
    db: Session,
    user_id: int,
    user_type: str,
    plain_login_code: str
) -> bool:
    """驗證使用者登入密碼是否正確（明文直接比對）"""
    try:
        if user_type == "patient":
            record = db.query(PatientLoginCode).filter(
                PatientLoginCode.patient_id == user_id,
                PatientLoginCode.is_active == True
            ).first()
        else:
            record = db.query(NurseLoginCode).filter(
                NurseLoginCode.nurse_id == user_id,
                NurseLoginCode.is_active == True
            ).first()

        if not record:
            return False

        # 直接明文比對
        return record.login_code_hash == plain_login_code
    except Exception:
        return False

# ---------------------------
# 核心登录接口
# ---------------------------
@router.post("/login", response_model=CommonTokenResponse)
async def login(
    request: LoginRequest,
    db: Session = Depends(get_db)
):
    """使用者登入（手機號 + 登入密碼）"""
    try:
        # 1. 查詢使用者是否存在
        user = get_user_by_phone(db, request.phone, request.user_type)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"{request.user_type} 使用者不存在，請先註冊"
            )

        # 2. 獲取使用者ID
        user_id = user.patient_id if request.user_type == "patient" else user.nurse_id

        # 设置生日
        date_of_birth=user.date_of_birth if request.user_type == "patient" else ""

        # 3. 驗證登入密碼
        if not authenticate_user_login_code(db, user_id, request.user_type, request.login_code):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="登入密碼錯誤"
            )

        # 4. 生成 Token
        full_name = f"{user.first_name}{user.last_name}"
        access_token = create_access_token(
            data={
                "sub": str(user_id),
                "user_type": request.user_type,
                "phone": request.phone,
                "full_name": full_name
            },
            expires_delta=timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        )

        # 5. 護士登入 → 自動創建排班
        if request.user_type == "nurse":
            work_start = time(hour=9, minute=0, second=0)
            work_end = time(hour=18, minute=0, second=0)
            add_nurse_work_time(db, user_id, work_start, work_end)

        # 6. 返回
        return CommonTokenResponse(
            access_token=access_token,
            token_type="bearer",
            user_type=request.user_type,
            user_id=user_id,
            first_name=str(user.first_name),
            last_name=str(user.last_name),
            phone=request.phone,
            phone_area_code=request.phone_area_code,
            is_first_login=False,
            full_name=full_name,
            date_of_birth=str(date_of_birth)
        )

    except HTTPException:
        raise
    except Exception as e:
        # 僅業務異常回滾，查詢異常無需回滾
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"登入失敗: {str(e)}"
        )

# ---------------------------
# 验证 Token
# ---------------------------
@router.get("/verify-token")
async def verify_token(token: str = Depends(oauth2_scheme)):
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="無效的令牌"
        )

    return {
        "valid": True,
        "user_id": payload.get("sub"),
        "user_type": payload.get("user_type"),
        "phone": payload.get("phone"),
        "expire_at": payload.get("exp")
    }

@router.get("/login1")
async def login1():
    return {"message": "登入密碼測試連結正常"}