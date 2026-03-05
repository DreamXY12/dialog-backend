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
DEBUG = get_parameter("dev", "debug") == "1"

if DEBUG:# 第68行的注释说明了问
    USERNAME="root"
    HOST="localhost"
    DATABASE = "dialog"
    PASSWORD="MariaDB2026!"
    
    
# 使用直接的连接字符串格式，确保认证插件被正确指定
SQLALCHEMY_DATABASE_URL = f"mysql+mysqlconnector://{USERNAME}:{PASSWORD}@{HOST}/{DATABASE}?auth_plugin=caching_sha2_password"


engine = create_engine(SQLALCHEMY_DATABASE_URL, echo=False,pool_size=100)

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

