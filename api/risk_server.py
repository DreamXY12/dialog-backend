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
from fastapi import  Depends
from sqlalchemy.orm import Session as Connection
from datetime import datetime
from sql.people_models import Case
from sql.crud import upsert_patient_score

router = APIRouter()

disable_warnings()

# 跟前端对齐的请求体结构
class LabData(BaseModel):
    fastingGlucose: float | None = None
    HBA1C: float | None = None
    cholesHDL: float | None = None
    triglyceride: float | None = None

class RiskPredictRequest(BaseModel):
    user_id: int
    lab_data: LabData
    time_spec: int
    labtest_date: str

AI_BASE_URL="https://agent.dialog.polyusn.com"

# 糖尿病前期风险预测
@router.post("/ai/risk_predict")
async def ai_risk_predict(req: RiskPredictRequest,db:Annotated[Connection, Depends(get_db)]):
    try:
        # 修复：用 model_dump() 转字典，不要用 model_dump_json()
        payload = req.model_dump(exclude_none=True)
        res = requests.post(
            url=f"{AI_BASE_URL}/ai/risk_predict",
            json=payload,   # 传字典 ✅
            timeout=30,
            verify=False
        )
        if not res.ok:
            raise HTTPException(status_code=res.status_code, detail=res.text)
        else:
            data = dict()
            outdata = res.json()
            if outdata["analysis_result"] == "medium":
                data["analysis_result"] = "medium risk"
            elif outdata["analysis_result"] == "high":
                data["analysis_result"] = "high risk"
            else:
                data["analysis_result"] = "low risk"
            data["score"] = outdata["score"]
            upsert_patient_score(db,payload["user_id"],payload["lab_data"]["HBA1C"],payload["lab_data"]["fastingGlucose"],payload["lab_data"]["cholesHDL"],payload["lab_data"]["triglyceride"],
                                 5,datetime.strptime(payload['labtest_date'], '%Y-%m-%d').date(),outdata["score"],data["analysis_result"])
            # data["user_id"]=payload["user_id"]
            # data["hba1c"]=payload["lab_data"]["HBA1C"]
            # data["fasting_glucose"]=payload["lab_data"]["fastingGlucose"]
            # data["hdl_cholesterol"]=payload["lab_data"]["cholesHDL"]
            # data["total_cholesterol"]=None
            # data["ldl_cholesterol"]=None
            # data["creatinine"]=None
            # data["triglyceride"]=payload["lab_data"]["triglyceride"]
            # data["potassium"]=None
            # data["time_spec"]=5
            # data["test_date"]= datetime.strptime(payload["lab_data"]['labtest_date'], '%Y-%m-%d').date()
            #
            # data["score"]=outdata["score"]
            #
            # temp_case = Case(**data, user_id=payload["user_id"])


        return outdata
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"糖尿病风险预测失败：{str(e)}")