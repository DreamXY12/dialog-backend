from fastapi import FastAPI

from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from config import get_parameter

from api.chat_server import sio,init_redis_once
import socketio
from api.api import api_router

PASSWORD = get_parameter("rdb", "password")

from contextlib import asynccontextmanager
# ===== 定义 lifespan 上下文管理器 =====
@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时执行
    await init_redis_once()
    print("✅ FastAPI 启动完成，Redis 已就绪")
    yield
    # 关闭时执行（如果需要清理资源，可以在这里添加）
    # 例如：关闭 Redis 连接等
    # await redis.close()
    print("🛑 FastAPI 正在关闭...")

app = FastAPI(lifespan=lifespan)


origins = ["http://localhost:5173","https://dialog.polyusn.com"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

socket_app = socketio.ASGIApp(sio)
app.mount("/socket.io", socket_app)

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)

