# 后端接口，用于响应前端调用路径

from fastapi import APIRouter, Depends, status,HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from sql.start import get_db
from core.sms_code import send_verification_code

router = APIRouter(prefix="/sms", tags=["sms-verification"])

# 请求体模型
class SendCodeRequest(BaseModel):
    phone: str = Field(..., description="带国际区号的已验证手机号（如+85212345678）")
    role: str = Field(..., pattern="^(patient|nurse)$", description="用户角色：patient/nurse")
    mode: str = Field(..., pattern="^(login|register)$", description="用途：login/register")
    mock: bool = Field(False, description="是否模拟发送（测试用，无需AWS）")

# 发送验证码接口
@router.post("/send-code", status_code=status.HTTP_200_OK)
async def send_code(
    request: SendCodeRequest,
    db: Session = Depends(get_db)
):
    """发送验证码（AWS SNS沙盒模式）"""
    try:
        result = send_verification_code(
            db=db,
            phone=request.phone,
            role=request.role,
            mode=request.mode
        )
        return result
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"發送驗證碼失敗：{str(e)}"
        )