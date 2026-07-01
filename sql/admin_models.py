from sqlalchemy import Column, Integer, String, DateTime, Enum
from sqlalchemy.sql import func
from sql.start import Base
import enum

class AdminRole(str, enum.Enum):
    SUPER = "super"
    OPERATOR = "operator"

class Admin(Base):
    __tablename__ = "admin"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="管理员ID")
    username = Column(String(50), unique=True, nullable=False, comment="登录账号")
    password = Column(String(10), nullable=False, comment="明文密码（字母+数字）")
    role = Column(Enum(AdminRole,values_callable=lambda e: [i.value for i in e]), nullable=False, default= AdminRole.OPERATOR, comment="角色")
    last_login = Column(DateTime, nullable=True, comment="最后登录时间")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")