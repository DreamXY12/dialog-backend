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

# 登录码模型 + 加密
from sql.people_models import PatientLoginCode, NurseLoginCode
import bcrypt

# ---------------------------
# 配置
# ---------------------------
router = APIRouter(prefix="/auth-code", tags=["authentication-4code"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth-code/login")

# ---------------------------
# 登录请求体
# ---------------------------
class LoginRequest(BaseModel):
    phone: str = Field(..., description="带区号的手机号，如+85212345678")
    phone_area_code: Optional[str] = Field(None, description="手机号区号，如+852/+86")
    login_code: str = Field(..., min_length=4, max_length=4, description="4位数字登录码")
    user_type: str = Field(..., pattern="^(patient|nurse)$", description="用户类型：patient/nurse")

# ---------------------------
# 登录码验证工具函数
# ---------------------------
def verify_code(plain_code: str, hashed_code: str) -> bool:
    """验证 4 位登录码是否正确（明文 vs 哈希）"""
    try:
        return bcrypt.checkpw(plain_code.encode("utf-8"), hashed_code.encode("utf-8"))
    except Exception:
        return False

def authenticate_user_login_code(
    db: Session,
    user_id: int,
    user_type: str,
    plain_login_code: str
) -> bool:
    """验证用户登录码是否正确"""
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

        return verify_code(plain_login_code, record.login_code_hash)
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
    """用户登录（手机号 + 4位永久登录码）"""
    try:
        # 1. 查询用户是否存在
        user = get_user_by_phone(db, request.phone, request.user_type)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"{request.user_type} 用户不存在，请先注册"
            )

        # 2. 获取用户ID
        user_id = user.patient_id if request.user_type == "patient" else user.nurse_id

        # 3. 验证登录码
        if not authenticate_user_login_code(db, user_id, request.user_type, request.login_code):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="登錄碼錯誤"
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

        # 5. 护士登录 → 自动创建排班
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
            full_name=full_name
        )

    except HTTPException:
        raise
    except Exception as e:
        # 仅业务异常回滚，查询异常无需回滚
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"登录失败: {str(e)}"
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
            detail="无效的令牌"
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
    return {"message": "4位码登录测试链接正常"}