from datetime import datetime
from sqlalchemy.orm import Session
from sql.people_models import FoodImage
from api.s3_service import s3_service

class FoodService:
    async def upload(
        self,
        db: Session,
        patient_id: int,
        file_bytes: bytes,
        filename: str,
        content_type: str,
        remark: str,
        eat_time:str
    ):
        ext = filename.split(".")[-1].lower()
        if ext not in ["jpg", "jpeg", "png", "webp"]:
            raise Exception("不支持的图片格式")

        if eat_time:
            # 把前端字符串转为 datetime 对象
            now = datetime.strptime(eat_time, "%Y-%m-%d %H:%M:%S")
        else:
            now = datetime.now()
        s3_key = s3_service.generate_key(patient_id, now, ext)
        s3_service.upload(s3_key, file_bytes, content_type)

        food_image = FoodImage(
            patient_id=patient_id,
            s3_key=s3_key,
            remark=remark,
            upload_timestamp=now
        )

        db.add(food_image)
        db.commit()
        db.refresh(food_image)

        # 上传成功后返回临时预览URL
        food_image.image_url = s3_service.get_presigned_url(s3_key)
        return food_image

    async def get_list(self, db: Session, patient_id: int):
        images = db.query(FoodImage)\
            .filter(FoodImage.patient_id == patient_id)\
            .order_by(FoodImage.upload_timestamp.desc())\
            .limit(6)\
            .all()

        # 重点：每张图片实时生成新URL
        result = []
        for img in images:
            result.append({
                "id": img.id,
                "image_url": s3_service.get_presigned_url(img.s3_key),
                "upload_timestamp": img.upload_timestamp
            })
        return result

food_service = FoodService()