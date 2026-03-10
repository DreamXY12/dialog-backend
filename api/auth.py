from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import timedelta
from passlib.context import CryptContext

# 导入核心依赖（适配新结构）
from sql.start import get_db
from sql.common_curd import get_user_by_phone
from api.register import CommonTokenResponse  # 复用通用Token响应模型
from sql.verify_code_curd import verify_verification_code  # 验证码验证函数
from pydantic import BaseModel,Field
from utility.fun_tool import create_access_token,decode_token,ACCESS_TOKEN_EXPIRE_MINUTES
from typing import Optional

# ---------------------------
# 1. 配置（移除配置文件依赖，直接定义3天有效期）
# ---------------------------
router = APIRouter(prefix="/auth", tags=["authentication"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# 密码上下文（保留但不再使用，如需兼容旧密码可保留）
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ---------------------------
# 2. 定义登录请求体（手机号+验证码+角色）
# ---------------------------
class LoginRequest(BaseModel):
    """登录请求体（替换原登录码+密码）"""
    phone: str = Field(..., description="带区号的手机号，如+85212345678")
    phone_area_code: Optional[str] = Field(None, description="手机号区号，如+852/+86")
    verify_code: str = Field(..., min_length=6, max_length=6, description="6位短信验证码")
    user_type: str = Field(..., pattern="^(patient|nurse)$", description="用户类型：patient/nurse")

# ---------------------------
# 4. 核心登录接口（手机号+验证码）
# ---------------------------
@router.post("/login", response_model=CommonTokenResponse)
async def login(
    request: LoginRequest,
    db: Session = Depends(get_db)
):
    """用户登录（手机号+验证码）- 重新生成3天有效期Token"""
    try:
        # Step 1: 验证短信验证码（核心）
        verify_success = verify_verification_code(
            db=db,
            phone=request.phone,
            code=request.verify_code,
            role=request.user_type,
            mode="login"  # 验证码用途为登录
        )
        if not verify_success:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="验证码错误、已过期或已使用"
            )

        # Step 2: 查询用户是否存在
        user = get_user_by_phone(db, request.phone, request.user_type)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"{request.user_type}用户不存在，请先注册"
            )

        # Step 3: 生成新的3天有效期Token（关键：登录时重新生成）
        access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        # 拼接完整姓名
        full_name = f"{user.first_name}{user.last_name}"
        # 生成Token（载荷包含核心用户信息）
        access_token = create_access_token(
            data={
                "sub": str(user.patient_id) if request.user_type == "patient" else str(user.nurse_id),
                "user_type": request.user_type,
                "phone": request.phone,
                "full_name": full_name
            },
            expires_delta=access_token_expires
        )

        if request.user_type == "patient":
            request_user_id = int(user.patient_id)
        else:
            request_user_id = int(user.nurse_id)
        # Step 4: 返回通用Token响应（和注册接口格式一致）
        return CommonTokenResponse(
            access_token=access_token,
            token_type="bearer",
            user_type=request.user_type,
            user_id=request_user_id,
            first_name=str(user.first_name),
            last_name=str(user.last_name),
            phone=request.phone,  # 替换原login_code字段
            phone_area_code=request.phone_area_code,
            is_first_login=False,  # 登录时标记为非首次
            full_name=f"{user.first_name}{user.last_name}"
        )

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"登录失败: {str(e)}"
        )

# ---------------------------
# 5. 保留/适配辅助接口
# ---------------------------
@router.get("/login1")
async def login1():
    """测试接口（保留）"""
    print("测试链接")
    return {"message": "测试链接正常"}

@router.get("/verify-token")
async def verify_token(token: str = Depends(oauth2_scheme)):
    """验证Token有效性（适配新Token格式）"""
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
