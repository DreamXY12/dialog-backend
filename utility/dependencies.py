from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import JWTError
from sqlalchemy.orm import Session
from sql.start import get_db
from sql.admin_crud import get_admin_by_id
from utility.fun_tool import decode_token  # 假设你的 decode_token 在 fun_tool.py
from sql.admin_models import Admin

security = HTTPBearer()


async def get_current_admin(
        credentials: HTTPAuthorizationCredentials = Depends(security),
        db: Session = Depends(get_db)
):
    """验证 Token，返回当前管理员对象"""
    token = credentials.credentials
    payload = decode_token(token)  # 返回 dict 或 None
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效或过期的 Token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    admin_id = payload.get("sub")  # 我们生成时用 "sub" 存放 admin_id
    if not admin_id:
        raise HTTPException(status_code=401, detail="无效 Token 载荷")

    admin = get_admin_by_id(db, int(admin_id))
    if not admin:
        raise HTTPException(status_code=401, detail="管理员不存在或已删除")

    return admin


async def get_current_super_admin(current_admin: Admin = Depends(get_current_admin)):
    """仅超级管理员可访问"""
    if current_admin.role != "super":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要超级管理员权限"
        )
    return current_admin