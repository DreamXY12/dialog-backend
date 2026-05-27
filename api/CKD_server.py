# 忽略 SSL 不安全警告（测试环境专用）
import datetime

import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from fastapi import HTTPException
import requests  # 用来发 POST 请求第三方后端
import boto3
from pydantic import BaseModel
from sql.start import get_db
from sql.ckd_curd import (
   create_patient_ckd_prediction,
    get_all_ckd_by_patient_and_date,
   get_ckd_by_date_range_paginated

)

from sqlalchemy.exc import SQLAlchemyError  # 数据库相关异常（如果用到SQLAlchemy）

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from datetime import date

# ==========================
# 1. 定义和前端完全对齐的请求体模型
# ==========================
class CKDPredictRequest(BaseModel):
    patient_id: int
    model_type: str
    horizon: str
    age: int
    sex: str
    bmi: float
    hba1c: float
    tc: float
    ldl: float
    hdl: float
    k: float
    creat: float
    use_insulin: bool
    stroke: bool
    smoke: bool
    anti_ht: bool
    angio: bool
    other_dm: bool
    whr: float
    fpg: float
    sbp: float
    dbp: float
    foot_prob: bool
    eye_prob: bool

dialog_ai_url="https://agent.dialog.polyusn.com"

# ==========================
# 1. 生成 S3 预签名 URL（自动用你本地 AWS 配置）
# ==========================
def generate_s3_presigned_url(bucket: str, key: str, expires_in: int = 3600):
    try:
        s3 = boto3.client("s3", region_name="ap-southeast-1")
        return s3.generate_presigned_url(
            ClientMethod="get_object",
            Params={"Bucket": bucket, "Key": key},
            ExpiresIn=expires_in,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"S3签名失败：{str(e)}")

router = APIRouter(tags=["ckd_predict"])

# ==========================
# 你对外提供的 POST 接口
# 前端调用你：/ai/ckd_predict
# 你内部调用：第三方后端 /ai/ckd_predict
# ==========================
@router.post("/ai/ckd_predict")
async def ckd_predict(req: CKDPredictRequest):
    """
    前端 → 你的FastAPI → 第三方后端
    自动处理错误 + 自动生成图片签名URL
    """

    # 先用模拟数据，到时候直接填就行了
    simulation_data = {
        "model_type": "Full",
        "horizon": "5",
        "age": 46,
        "sex": "Female",
        "bmi": 29.0,
        "hba1c": 27.3,
        "tc": 4.76,
        "ldl": 2.79,
        "hdl": 1.29,
        "k": 4.24,
        "creat": 120,
        "use_insulin": False,
        "stroke": False,
        "smoke": True,
        "anti_ht": False,
        "angio": False,
        "other_dm": False,
        "whr": 0.951,
        "fpg": 4.887,
        "sbp": 146.0,
        "dbp": 95.0,
        "foot_prob": False,
        "eye_prob": False,
      }
    third_party_url = dialog_ai_url + "/ai/ckd_predict"

    try:
        # 直接把前端传入的参数转 json 转发，不再写死模拟数据
        payload = req.model_dump(exclude_none=True)

        response = requests.post(
            url=third_party_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=20,
            verify=False
        )

        # 状态码错误处理
        if response.status_code == 400:
            raise HTTPException(status_code=400, detail="请求参数错误")
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="接口不存在")
        if response.status_code >= 500:
            raise HTTPException(status_code=503, detail="第三方服务暂时不可用")

        ckd_result = response.json()


        # 生成图片预签名地址
        bucket = ckd_result.get("bucket")
        key = ckd_result.get("key")
        if bucket and key:
            ckd_result["image_url"] = generate_s3_presigned_url(bucket, key)

        # 如果沒有錯誤就保存到數據庫
        try:
            record = create_patient_ckd_prediction(db=next(get_db()), patient_id=payload["patient_id"],age=payload["age"],sex=payload["sex"],bmi=payload["bmi"],
                                          whr=payload["whr"],hba1c=payload["hba1c"],tc=payload["tc"],ldl=payload["ldl"],hdl=payload["hdl"],
                                          k=payload["k"],creat=payload["creat"],fpg=payload["fpg"],sbp=payload["sbp"],dbp=payload["dbp"],
                                          use_insulin=payload["use_insulin"],stroke=payload["stroke"],smoke=payload["smoke"],anti_ht=payload["anti_ht"],
                                          angio=payload["angio"],other_dm = payload["other_dm"],foot_prob=payload["foot_prob"],eye_prob=payload["eye_prob"],
                                          test_date=date.today(),model_type=payload["model_type"],risk_group=ckd_result["risk_group"],
                                          risk_2y_percent=ckd_result["risk_2y_percent"],risk_5y_percent=ckd_result["risk_5y_percent"],
                                          population_percentile=ckd_result["population_percentile"],image_url=ckd_result["image_url"]
                                          )
        # 捕获 payload/ckd_result 缺少 key 的错误
        except KeyError as e:
            print(f"错误：缺少必要的字段 -> {str(e)}")
            # 你可以在这里返回错误响应、记录日志等

        # 捕获数据库操作异常（如果使用SQLAlchemy）
        except SQLAlchemyError as e:
            print(f"数据库操作失败：{str(e)}")

        # 捕获函数内部抛出的所有其他异常
        except Exception as e:
            print(f"创建CKD预测记录失败：{str(e)}")

        return ckd_result

    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="请求第三方接口超时")
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="无法连接第三方服务")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器错误：{str(e)}")

@router.get("/ckd/health")
async def ckd_health():
    try:
        # ==========================================
        # 你向后端发送 POST 请求（核心代码）
        # ==========================================
        third_party_url=dialog_ai_url + "/ckd/health"
        response = requests.get(
            url=third_party_url,
            headers={"Content-Type": "application/json"},
            timeout=20,  # 超时20秒
            verify=False  # 测试环境忽略证书错误（正式环境可删掉）
        )

        # ==========================================
        # 错误处理：第三方接口返回非200
        # ==========================================
        if response.status_code == 400:
            raise HTTPException(status_code=400, detail="请求参数错误")
        if response.status_code == 404:
            raise HTTPException(status_code=404, detail="接口不存在")
        if response.status_code >= 500:
            raise HTTPException(status_code=503, detail="第三方服务暂时不可用")

        # 获取第三方返回结果
        ckd_health_result = response.json()

        # 返回给前端
        return ckd_health_result

    # ==========================================
    # 全局网络错误处理（全部覆盖）
    # ==========================================
    except requests.exceptions.Timeout:
        raise HTTPException(status_code=504, detail="请求第三方接口超时")
    except requests.exceptions.ConnectionError:
        raise HTTPException(status_code=503, detail="无法连接第三方服务")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"服务器错误：{str(e)}")


# 1. 获取【某一天】所有 CKD 记录
@router.get("/ckd/records/day")
def get_ckd_day_records(
    patient_id: int,
    date_str: str = Query(..., description="格式：2025-11-21"),
    db: Session = Depends(get_db)
):
    query_date = date.fromisoformat(date_str)
    records = get_all_ckd_by_patient_and_date(db, patient_id, query_date)
    return {"code": 200, "data": records}

# 2. 获取【时间段】CKD 记录
@router.get("/ckd/records/range")
def get_ckd_range_records(
    patient_id: int,
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    page: int = Query(1),
    page_size: int = Query(5),
    db: Session = Depends(get_db)
):
    start = date.fromisoformat(start_date) if start_date else None
    end = date.fromisoformat(end_date) if end_date else None

    total,result = get_ckd_by_date_range_paginated(
        db=db,
        patient_id=patient_id,
        start_date=start,
        end_date=end,
        page=page,
        page_size=page_size
    )

    return {
        "code": 200,
        "data": result,
        "total": total,
        "page": page,
        "page_size": page_size
    }

