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
        remark: str | None = None,
        eat_time: str | None = None
    ):
        ext = filename.split(".")[-1].lower()
        if ext not in ["jpg", "jpeg", "png", "webp"]:
            raise Exception("不支持的图片格式")

        if eat_time:
            now = datetime.strptime(eat_time, "%Y-%m-%d %H:%M:%S")
        else:
            now = datetime.now()
        # S3 key 仍然使用 now（来自 eat_time 或当前时间）
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