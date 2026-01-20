'''
@author: george 
@email: george6.lu@polyu.edu.hk
@date: 16 May 2023
@description: test api that is available for development only, it provide series of tools for cleaning database.
'''

from fastapi import Request, Query, APIRouter, Security, File, UploadFile
from sql.crud import init_models
from fastapi import Request, Query, APIRouter
from typing import Optional, List, Union
from typing_extensions import Annotated

from fastapi import Depends
from core.auth import get_current_session

router = APIRouter(prefix='/test')



# @router.patch("/clean/", description="clean and create table, it is for development only")
# async def clean():
#     '''
#     clean and create table, it is for development only.
#     '''
#     await init_models()


# @router.get("/session/", response_model=None)
# async def read_users_me(
#     current_session: Annotated[Session, Depends(get_current_session)]
# ):
#     return current_session