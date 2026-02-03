from fastapi import APIRouter
from api import user, case, session, newmessages,wechat_message,auth,nurse,users,robot
from api.endpoints import patient

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(user.router)
api_router.include_router(case.router)
api_router.include_router(session.router)
api_router.include_router(newmessages.router)
api_router.include_router(wechat_message.router)
api_router.include_router(auth.router)
api_router.include_router(nurse.router)
api_router.include_router(users.router)
api_router.include_router(patient.router)
api_router.include_router(robot.router)
      