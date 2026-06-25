from fastapi import APIRouter, UploadFile, File, Depends, HTTPException,Query
from sqlalchemy.orm import Session
from sql.start import get_db
from api.food_service import food_service
from schema.food_image import FoodImageResponse
from typing import List
from fastapi import Form

router = APIRouter(prefix="/patients/me/food-images", tags=["Food Images"])

# ------------------------------
# 上传：前端传 patient_id
# ------------------------------
@router.post("/send_food_image", response_model=FoodImageResponse)
async def upload(
    patient_id: int = Query(...),  # 直接从前端获取
    file: UploadFile = File(...),
    eat_time: str | None = Form(None),
    remark: str | None = Form(None),
    db: Session = Depends(get_db)
):
    try:
        return await food_service.upload(
            db=db,
            patient_id=patient_id,  # 用前端传的
            file_bytes=await file.read(),
            filename=file.filename,
            eat_time=eat_time,
            remark=remark,
            content_type=file.content_type
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


# ------------------------------
# 查询列表：前端传 patient_id
# ------------------------------
@router.get("/get_food_image", response_model=List[FoodImageResponse])
async def get_list(
    patient_id: int = Query(...),  # 直接从前端获取
    db: Session = Depends(get_db)
):
    return await food_service.get_list(db, patient_id)