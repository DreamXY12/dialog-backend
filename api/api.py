from fastapi import APIRouter
from api import user, case, session, newmessages,wechat_message

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(user.router)
api_router.include_router(case.router)
api_router.include_router(session.router)
api_router.include_router(newmessages.router)
api_router.include_router(wechat_message.router)
      