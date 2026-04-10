import requests
from typing_extensions import Annotated
from sqlalchemy.orm import Session as Connection
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, Body, Query

from sql.start import get_db
from sql.cache_database import r
from sql.models import Invitation
from api.api import api_router

from sql.crud import create_user, init_models
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import os
import binascii
from contextlib import asynccontextmanager
from config import get_parameter

from api.chat_server import sio
import socketio

PASSWORD = get_parameter("rdb", "password")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # load the resources
    init_models()
    yield

app = FastAPI()
origins = ["https://dialog.polyusn.com"]
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

@app.patch("/clean", description="clean and create table, it is for development only")
async def clean(
    admin_key: Annotated[str, Body]
):
    '''
    clean and create table, it is for development only.
    '''
    if admin_key == PASSWORD:
        r.flushdb()
        init_models()
        return {"message": "database has been cleaned"}
    else:
        raise HTTPException(401, detail="please enter the admin key for the operation")

@app.post("/add", description="add the invitation code, it is exclusive to admin")
async def add(
    admin_key: Annotated[str, Body],
    tag: Annotated[str, Body],
    db: Annotated[Connection, Depends(get_db)]
):
    '''
    generate the key and write to database
    '''
    if admin_key == PASSWORD:
        invitation_code = binascii.b2a_hex(os.urandom(16)).decode('ascii')
        db_ic = Invitation()
        db_ic.code = invitation_code
        db_ic.tag = tag
        db.add(db_ic)
        try:
            db.commit()
        except Exception as e:
            print(e)
            db.rollback()
            raise e
        
        return {"generated_key": invitation_code}
    else:
        raise HTTPException(401, detail="please enter the admin key for the operation")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000)

