# 忽略 SSL 不安全警告（测试环境专用）
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from fastapi import APIRouter
from fastapi import HTTPException
import requests  # 用来发 POST 请求第三方后端
from pydantic import BaseModel
from urllib3 import disable_warnings
from sql.start import get_db
from typing_extensions import Annotated
from sqlalchemy.orm import Session as Connection
from datetime import datetime
from sql.people_models import Case
from sql.crud import upsert_patient_score
from sql.risk_crud import (
    get_diabetes_records_by_user_and_date,
    get_diabetes_by_date_range_paginated

)
from datetime import date
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

router = APIRouter()

disable_warnings()

# 跟前端对齐的请求体结构
class LabData(BaseModel):
    fastingGlucose: float | None = None
    HBA1C: float | None = None
    cholesHDL: float | None = None
    triglyceride: float | None = None
    # 👇 下面这 4 个是新增补齐的
    choles: float | None = None  # 总胆固醇
    cholesLDL_1: float | None = None  # 低密度
    creatinine: float | None = None  # 肌酐
    potassiumSerumOrPlasma: float | None = None  # 血钾

class RiskPredictRequest(BaseModel):
    user_id: int
    lab_data: LabData
    time_spec: int
    labtest_date: str

AI_BASE_URL="https://agent.dialog.polyusn.com"

# 糖尿病前期风险预测
@router.post("/ai/risk_predict")
async def ai_risk_predict(
    req: RiskPredictRequest,
    db: Annotated[Connection, Depends(get_db)]
):
    try:
        payload = req.model_dump(exclude_none=True)
        res = requests.post(
            url=f"{AI_BASE_URL}/ai/risk_predict",
            json=payload,
            timeout=30,
            verify=False
        )

        if not res.ok:
            raise HTTPException(status_code=res.status_code, detail=res.text)

        outdata = res.json()

        # 统一风险等级
        if outdata["analysis_result"] == "medium":
            analysis_result = "medium risk"
        elif outdata["analysis_result"] == "high":
            analysis_result = "high risk"
        else:
            analysis_result = "low risk"

        score = outdata["score"]

        # ==============================
        # 👇 这里补齐 8 个字段，全部传入
        # ==============================
        upsert_patient_score(
            conn=db,
            user_id=payload["user_id"],
            hba1c=payload["lab_data"]["HBA1C"],
            fasting_glucose=payload["lab_data"]["fastingGlucose"],
            hdl_cholesterol=payload["lab_data"]["cholesHDL"],
            triglyceride=payload["lab_data"]["triglyceride"],

            # 新增 4 个字段
            total_cholesterol=payload["lab_data"].get("choles"),
            ldl_cholesterol=payload["lab_data"].get("cholesLDL_1"),
            creatinine=payload["lab_data"].get("creatinine"),
            potassium=payload["lab_data"].get("potassiumSerumOrPlasma"),

            time_spec=5,
            test_date=datetime.strptime(payload['labtest_date'], '%Y-%m-%d').date(),
            new_score=score,
            analysis_result=analysis_result
        )

        return outdata

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"糖尿病风险预测失败：{str(e)}")

# 1. 获取【某一天】所有糖尿病记录
@router.get("/diabetes/records/day")
def get_diabetes_day_records(
    user_id: int,
    date_str: str = Query(..., description="格式：2025-11-21"),
    db: Session = Depends(get_db)
):
    query_date = date.fromisoformat(date_str)
    records = get_diabetes_records_by_user_and_date(db, user_id, query_date)
    return {"code": 200, "data": records}

# 2. 获取【时间段】糖尿病记录
@router.get("/diabetes/records/range")
def get_diabetes_range_records(
    user_id: int,
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    page: int = Query(1),
    page_size: int = Query(5),
    db: Session = Depends(get_db)
):
    start = date.fromisoformat(start_date) if start_date else None
    end = date.fromisoformat(end_date) if end_date else None

    total,result = get_diabetes_by_date_range_paginated(
        db=db,
        user_id=user_id,
        start_date=start,
        end_date=end,
        page=page,
        page_size=page_size
    )

    return {
        "code": 200,
        "data": result,
        "total":total,
        "page": page,
        "page_size": page_size
    }