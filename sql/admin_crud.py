from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional, List, Tuple
from .admin_models import Admin, AdminRole
from datetime import datetime

def get_admin_by_username(db: Session, username: str) -> Optional[Admin]:
    """根据用户名查询管理员"""
    return db.query(Admin).filter(Admin.username == username).first()

def get_admin_by_id(db: Session, admin_id: int) -> Optional[Admin]:
    return db.query(Admin).filter(Admin.id == admin_id).first()

def create_admin(db: Session, username: str, password: str, role: str = "operator") -> Admin:
    """创建新管理员（明文密码）"""
    new_admin = Admin(
        username=username,
        password=password,
        role=AdminRole(role)  # 确保枚举值正确
    )
    db.add(new_admin)
    db.commit()
    db.refresh(new_admin)
    return new_admin

def update_admin_password(db: Session, admin_id: int, new_password: str) -> Optional[Admin]:
    admin = get_admin_by_id(db, admin_id)
    if admin:
        admin.password = new_password
        db.commit()
        db.refresh(admin)
    return admin

def delete_admin(db: Session, admin_id: int) -> bool:
    admin = get_admin_by_id(db, admin_id)
    if admin:
        db.delete(admin)
        db.commit()
        return True
    return False

def list_admins(db: Session, page: int = 1, size: int = 20) -> Tuple[List[Admin], int]:
    """分页获取管理员列表"""
    offset = (page - 1) * size
    query = db.query(Admin)
    total = query.count()
    admins = query.order_by(desc(Admin.created_at)).offset(offset).limit(size).all()
    return admins, total

def update_last_login(db: Session, admin_id: int):
    """更新最后登录时间"""
    admin = get_admin_by_id(db, admin_id)
    if admin:
        admin.last_login = datetime.now()  # 需导入 datetime
        db.commit()
        return admin
    return None