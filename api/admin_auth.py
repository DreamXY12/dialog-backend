from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from sql.start import get_db
from sql.admin_crud import (
    get_admin_by_username, create_admin, list_admins,
    get_admin_by_id, update_admin_password, delete_admin,
    update_last_login
)
from utility.dependencies import get_current_admin, get_current_super_admin
from utility.fun_tool import create_access_token
from sql.admin_models import Admin

router = APIRouter(prefix="/polyu/dialog/admin", tags=["admin"])


# ---------- Pydantic 请求/响应模型 ----------
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    admin_id: int
    role: str
    username: str


class AdminCreateRequest(BaseModel):
    username: str
    password: str  # 明文，长度≤10
    role: str = "operator"  # super / operator


class AdminUpdatePasswordRequest(BaseModel):
    password: str


class AdminResponse(BaseModel):
    id: int
    username: str
    role: str
    last_login: Optional[datetime]
    created_at: datetime
    updated_at: datetime


# ---------- 登录接口 ----------
@router.post("/login", response_model=LoginResponse)
def admin_login(request: LoginRequest, db: Session = Depends(get_db)):
    admin = get_admin_by_username(db, request.username)
    if not admin or admin.password != request.password:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )
    # 更新最后登录时间
    update_last_login(db, admin.id)

    # 生成 JWT，载荷包含 admin_id
    access_token = create_access_token(data={"sub": str(admin.id)})
    return LoginResponse(
        access_token=access_token,
        admin_id=admin.id,
        role=admin.role.value,
        username=admin.username
    )


# ---------- 获取当前管理员信息 ----------
@router.get("/me", response_model=AdminResponse)
def get_me(current_admin: Admin = Depends(get_current_admin)):
    return current_admin


# ---------- 创建管理员（仅 super） ----------
@router.post("/admins", response_model=AdminResponse, dependencies=[Depends(get_current_super_admin)])
def create_new_admin(request: AdminCreateRequest, db: Session = Depends(get_db)):
    # 检查用户名是否已存在
    if get_admin_by_username(db, request.username):
        raise HTTPException(status_code=400, detail="用户名已存在")
    if len(request.password) > 10:
        raise HTTPException(status_code=400, detail="密码长度不能超过10位")
    # 验证角色
    if request.role not in ["super", "operator"]:
        raise HTTPException(status_code=400, detail="角色必须是 super 或 operator")
    new_admin = create_admin(db, request.username, request.password, request.role)
    return new_admin


# ---------- 获取管理员列表（分页，仅 super） ----------
@router.get("/admins", response_model=dict)
def get_admin_list(
        page: int = 1,
        size: int = 20,
        _: Admin = Depends(get_current_super_admin),
        db: Session = Depends(get_db)
):
    admins, total = list_admins(db, page, size)
    return {
        "total": total,
        "page": page,
        "size": size,
        "data": admins
    }


# ---------- 获取单个管理员详情（含密码，仅 super） ----------
@router.get("/admins/{admin_id}", response_model=dict)
def get_admin_detail(
        admin_id: int,
        _: Admin = Depends(get_current_super_admin),
        db: Session = Depends(get_db)
):
    admin = get_admin_by_id(db, admin_id)
    if not admin:
        raise HTTPException(status_code=404, detail="管理员不存在")
    return {
        "id": admin.id,
        "username": admin.username,
        "password": admin.password,  # 明文，方便查看
        "role": admin.role.value,
        "last_login": admin.last_login,
        "created_at": admin.created_at,
        "updated_at": admin.updated_at
    }


# ---------- 更新密码（仅 super） ----------
@router.put("/admins/{admin_id}/password")
def update_admin_pwd(
        admin_id: int,
        request: AdminUpdatePasswordRequest,
        _: Admin = Depends(get_current_super_admin),
        db: Session = Depends(get_db)
):
    if len(request.password) > 10:
        raise HTTPException(status_code=400, detail="密码长度不能超过10位")
    admin = update_admin_password(db, admin_id, request.password)
    if not admin:
        raise HTTPException(status_code=404, detail="管理员不存在")
    return {"message": "密码更新成功"}


# ---------- 删除管理员（仅 super） ----------
@router.delete("/admins/{admin_id}")
def delete_admin_route(
        admin_id: int,
        current_admin: Admin = Depends(get_current_super_admin),
        db: Session = Depends(get_db)
):
    # 不允许删除自己
    if admin_id == current_admin.id:
        raise HTTPException(status_code=400, detail="不能删除自己")
    success = delete_admin(db, admin_id)
    if not success:
        raise HTTPException(status_code=404, detail="管理员不存在")
    return {"message": "管理员已删除"}