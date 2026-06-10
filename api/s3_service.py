import boto3
import uuid
from datetime import datetime
from botocore.config import Config

class S3Service:
    def __init__(self):
        self.bucket = "dialog-patient-food-image"
        self.region = "ap-southeast-1"
        self.client = boto3.client(
            "s3",
            region_name=self.region,
            config=Config(signature_version="s3v4")
        )

    def generate_key(self, patient_id: int, now: datetime, ext: str):
        date_str = now.strftime("%Y-%m-%d")
        uid = uuid.uuid4().hex[:8]
        filename = f"{now.strftime('%Y-%m-%d_%H-%M-%S')}_{uid}.{ext}"
        return f"DialogImages/{patient_id}/{date_str}/{filename}"

    def upload(self, s3_key: str, file_bytes: bytes, content_type: str):
        self.client.put_object(
            Bucket=self.bucket,
            Key=s3_key,
            Body=file_bytes,
            ContentType=content_type,
            ACL="private"
        )

    def get_presigned_url(self, s3_key: str, expires=3600):
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": s3_key},
            ExpiresIn=expires
        )

s3_service = S3Service()