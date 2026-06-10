from pydantic import BaseModel
from datetime import datetime

# 前端传参用
class FoodImageRequest(BaseModel):
    patient_id: int  # 前端传这个 id

class FoodImageResponse(BaseModel):
    id: int
    image_url: str
    upload_timestamp: datetime

    class Config:
        orm_mode = True