from fastapi import APIRouter
from api import auth,register,sms_router,patients,nurses,case,robot,feedback,chat_history,CKD_server,AI_server,risk_server

api_router = APIRouter(prefix="/api/v1")

# api_router.include_router(users.router)
# api_router.include_router(user.router)
# api_router.include_router(session.router)
# api_router.include_router(newmessages.router)
# api_router.include_router(wechat_message.router)
api_router.include_router(case.router)
api_router.include_router(auth.router)
api_router.include_router(register.router)
api_router.include_router(sms_router.router)
api_router.include_router(patients.router)
api_router.include_router(nurses.router)
api_router.include_router(robot.router)
api_router.include_router(feedback.router)
api_router.include_router(chat_history.router)
api_router.include_router(CKD_server.router)
api_router.include_router(AI_server.router)
api_router.include_router(risk_server.router)
# api_router.include_router(nurse.router)
# api_router.include_router(patient.router)


      