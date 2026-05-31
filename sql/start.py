from sqlalchemy import create_engine
from sqlalchemy import URL, JSON
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from typing import Any
import json
from config import get_parameter

USERNAME = get_parameter("rdb", "username") or "root"
PASSWORD = get_parameter("rdb", "password") or "MariaDB2026!"
HOST = get_parameter("rdb", "host") or "localhost"
DATABASE = get_parameter("rdb", "database") or "dialog"

# 新增：isLocalDev 如果值为1则是本地测试，为0则到了服务器端
ISLOCALDEV = get_parameter("dev", "isLocalDev")
if ISLOCALDEV=="1":
    #这里只用修改HOST就行了，其余都不变
    HOST="diabetes-rds.cteaa20ag0h1.ap-southeast-1.rds.amazonaws.com"
    
    
# 使用直接的连接字符串格式，确保认证插件被正确指定
SQLALCHEMY_DATABASE_URL = f"mysql+mysqlconnector://{USERNAME}:{PASSWORD}@{HOST}/{DATABASE}?auth_plugin=caching_sha2_password"


engine = create_engine(SQLALCHEMY_DATABASE_URL, echo=False,pool_size=100)

# ==============================
# 🔥 关键：在这里加 时区设置（强制东八区，解决数据库时间差8小时）
# ==============================
from sqlalchemy import event

@event.listens_for(engine, "connect")
def set_mysql_timezone(conn, connection_record):
    """
    强制 MySQL 连接使用东八区时间（香港/上海时间）
    这样 create_time / update_time 自动正确，不再差8小时
    """
    cursor = conn.cursor()
    cursor.execute("SET time_zone = '+08:00';")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


class Base(DeclarativeBase):
    type_annotation_map = {
        dict[str, Any]: JSON
    }

