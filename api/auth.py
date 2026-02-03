from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from datetime import timedelta
from typing import Optional
import os
from jose import JWTError, jwt
from passlib.context import CryptContext

from sql.start import get_db
from sql.login_models import LoginCode, Nurse, Patient
from sql.schemas import LoginRequest, TokenResponse, LoginCodeResponse, CheckCodeResponse, UserType
import random
from config import get_parameter

router = APIRouter(prefix="/auth", tags=["authentication"])
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")

# 配置
SECRET_KEY = get_parameter("web","secrete_key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60*24*7

# 密码哈希
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# 工具函数
def verify_password(plain_password: str, hashed_password: str) -> bool:
    return plain_password == hashed_password
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    from datetime import datetime, timedelta
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


# 登录码相关函数
def generate_unique_login_code(db: Session, max_attempts: int = 100) -> str:
    attempts = 0

    while attempts < max_attempts:
        code = f"{random.randint(1000, 9999)}"

        existing = db.query(LoginCode).filter(LoginCode.code == code).first()
        if not existing:
            return code

        attempts += 1

    for _ in range(max_attempts):
        code = f"{random.randint(10000, 99999)}"
        existing = db.query(LoginCode).filter(LoginCode.code == code).first()
        if not existing:
            return code

    raise RuntimeError("无法生成唯一的登录码")


def get_login_code(db: Session, code: str):
    return db.query(LoginCode).filter(LoginCode.code == code).first()


def mark_login_code_as_used(db: Session, code: str, user_type: str) -> bool:
    from datetime import datetime
    login_code = get_login_code(db, code)
    if not login_code or login_code.is_used:
        return False

    login_code.is_used = True
    login_code.user_type = user_type
    login_code.used_at = datetime.utcnow()

    try:
        db.commit()
        return True
    except Exception:
        db.rollback()
        return False


# 用户认证函数
def get_patient_by_login_code(db: Session, login_code: str):
    return db.query(Patient).filter(Patient.login_code == login_code).first()


def get_nurse_by_login_code(db: Session, login_code: str):
    return db.query(Nurse).filter(Nurse.login_code == login_code).first()


def authenticate_user(db: Session, login_code: str, password: str):
    # 尝试患者
    patient = get_patient_by_login_code(db, login_code)
    if patient and verify_password(password, patient.hashed_password):
        return patient, UserType.PATIENT

    # 尝试护士
    nurse = get_nurse_by_login_code(db, login_code)
    if nurse and verify_password(password, nurse.hashed_password):
        return nurse, UserType.NURSE

    return None, None

# 测试用，get方法
@router.get("/login1")
async def login1():
    print("测试链接")

# 路由post方法
@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: Session = Depends(get_db)):
    print("进入登陆主函数")
    """用户登录"""
    user, user_type = authenticate_user(db, request.login_code, request.password)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="登录码或密码错误"
        )

    # 创建访问令牌
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    if user_type == UserType.PATIENT:
        user_id = user.patient_id
        full_name = f"{user.first_name}{user.last_name}"
    else:  # UserType.NURSE
        user_id = user.nurse_id
        full_name = f"{user.first_name}{user.last_name}"

    access_token = create_access_token(
        data={
            "sub": str(user_id),
            "user_type": user_type.value,
            "full_name": full_name
        },
        expires_delta=access_token_expires
    )

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        login_code=request.login_code,
        user_id=user_id,
        first_name=user.first_name,
        last_name=user.last_name,
        user_type=str(user_type.value)
    )


@router.post("/generate-code", response_model=LoginCodeResponse)
async def generate_login_code(
        user_type: Optional[str] = None,
        db: Session = Depends(get_db)
):
    """生成登录码"""
    try:
        from datetime import datetime
        code = generate_unique_login_code(db)

        login_code = LoginCode(
            code=code,
            user_type=user_type,
            is_used=False
        )

        db.add(login_code)
        db.commit()
        db.refresh(login_code)

        return LoginCodeResponse(
            login_code=code,
            message="登录码生成成功",
            created_at=login_code.create_time
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"生成登录码失败: {str(e)}"
        )


@router.get("/check-code/{code}", response_model=CheckCodeResponse)
async def check_login_code(code: str, db: Session = Depends(get_db)):
    """检查登录码状态"""
    if not code or len(code) != 4 or not code.isdigit():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="登录码必须是4位数字"
        )

    login_code = get_login_code(db, code)

    if not login_code:
        return CheckCodeResponse(
            code=code,
            is_available=False,
            is_used=False,
            exists=False
        )

    return CheckCodeResponse(
        code=code,
        is_available=not login_code.is_used,
        is_used=login_code.is_used,
        exists=True
    )


@router.get("/verify-token")
async def verify_token(token: str = Depends(oauth2_scheme)):
    """验证令牌有效性"""
    payload = decode_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的令牌"
        )

    return {"valid": True, "user_id": payload.get("sub"), "user_type": payload.get("user_type")}