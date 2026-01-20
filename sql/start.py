from sqlalchemy import create_engine
from sqlalchemy import URL, JSON
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from typing import Any
import json
from config import get_parameter

USERNAME = get_parameter("rdb", "username")
PASSWORD = get_parameter("rdb", "password")
HOST = get_parameter("rdb", "host")
DATABASE = get_parameter("rdb", "database")
DEBUG = get_parameter("dev", "debug") == "1"

if DEBUG:
    USERNAME="root"
    HOST="localhost"
    DATABASE = "dialog"
    PASSWORD="lw08zs28"
    
    
SQLALCHEMY_DATABASE_URL = URL.create(
    "mysql+mysqlconnector",
    username=USERNAME,
    password=PASSWORD,
    host=HOST,
    database=DATABASE
)


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

