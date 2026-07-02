from sqlalchemy import create_engine
from sqlalchemy import URL, JSON
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from typing import Any
import json
from config import get_parameter
import logging

import logging

# 为连接池监控创建专用 logger
pool_logger = logging.getLogger("pool_monitor")
pool_logger.setLevel(logging.DEBUG)

# 创建文件 handler
fh = logging.FileHandler("pool_monitor.log")
fh.setLevel(logging.DEBUG)
fh.setFormatter(logging.Formatter('%(asctime)s - %(message)s'))
pool_logger.addHandler(fh)

# 阻止日志向上传播到根 logger（否则可能会重复输出到 dev.log）
pool_logger.propagate = False

USERNAME = get_parameter("rdb", "username") or "root"
PASSWORD = get_parameter("rdb", "password") or "MariaDB2026!"
HOST = get_parameter("rdb", "host") or "localhost"
DATABASE = get_parameter("rdb", "database") or "dialog"

# 新增：isLocalDev 如果值为1则是本地测试，为0则到了服务器端
ISLOCALDEV = get_parameter("dev", "isLocalDev")
if ISLOCALDEV=="0":
    #这里只用修改HOST就行了，其余都不变
    HOST="diabetes-rds.cteaa20ag0h1.ap-southeast-1.rds.amazonaws.com"
    
# 使用直接的连接字符串格式，确保认证插件被正确指定
SQLALCHEMY_DATABASE_URL = f"mysql+mysqlconnector://{USERNAME}:{PASSWORD}@{HOST}/{DATABASE}?auth_plugin=caching_sha2_password"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    echo=False,
    pool_size=30,
    max_overflow=20,
    pool_recycle=1800,      # 空闲连接超过30分钟自动回收
    pool_pre_ping=True,     # 每次从池中取连接前先 ping 一下
    pool_timeout=20         # 等待连接的超时时间（秒）
)
pool = engine.pool
# ==============================
# 🔥 关键：在这里加 时区设置（强制东八区，解决数据库时间差8小时）
# ==============================
from sqlalchemy import event
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.pool.base import _ConnectionRecord
# 监听连接借出事件
# 以下代码用于测试
# @event.listens_for(pool, "checkout")
# def on_checkout(dbapi_connection, connection_record, connection_proxy):
#     print("Type of connection_record:", type(connection_record))
#     print("Has 'pool'?", hasattr(connection_record, "pool"))
#     print("Dir of connection_record:", [x for x in dir(connection_record) if not x.startswith('_')])
#     # 如果确实没有 pool，就打印全部属性看看它到底是什么
#     if not hasattr(connection_record, "pool"):
#         print("Full dir:", dir(connection_record))
#
# @event.listens_for(pool, "checkin")
# def on_checkin(dbapi_connection, connection_record):
#     print("Type of connection_record:", type(connection_record))
#     print("Has 'pool'?", hasattr(connection_record, "pool"))
def safe_int(attr_or_method):
    """如果可调用就调用它，否则直接返回值。兼容方法和属性。"""
    return attr_or_method() if callable(attr_or_method) else attr_or_method

def log_pool_state(event_name, dbapi_conn):
    size = safe_int(pool.size)
    checkedout = safe_int(pool.checkedout)
    idle = size - checkedout
    overflow = safe_int(pool.overflow) if hasattr(pool, 'overflow') else 'N/A'
    pool_logger.debug(
        f"连接{event_name} ({hex(id(dbapi_conn))})，池状态: "
        f"空闲={idle}，已借出={checkedout}，总计={size}"
    )

@event.listens_for(pool, "checkout")
def on_checkout(dbapi_connection, connection_record, connection_proxy):
    log_pool_state("借出", dbapi_connection)

@event.listens_for(pool, "checkin")
def on_checkin(dbapi_connection, connection_record):
    log_pool_state("归还", dbapi_connection)

# @event.listens_for(engine, "connect") 没作用
# def set_mysql_timezone(conn, connection_record):
#     """
#     强制 MySQL 连接使用东八区时间（香港/上海时间）
#     这样 create_time / update_time 自动正确，不再差8小时
#     """
#     cursor = conn.cursor()
#     cursor.execute("SET time_zone = '+08:00';")
#     cursor.close()

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

