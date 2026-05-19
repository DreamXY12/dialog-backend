from fastapi import FastAPI
from api.api import api_router
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from config import get_parameter

from api.chat_server import sio
import socketio

PASSWORD = get_parameter("rdb", "password")

app = FastAPI()
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

