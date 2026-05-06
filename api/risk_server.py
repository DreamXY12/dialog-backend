# 忽略 SSL 不安全警告（测试环境专用）
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from fastapi import APIRouter
from fastapi import HTTPException
import requests  # 用来发 POST 请求第三方后端
from pydantic import BaseModel
from urllib3 import disable_warnings

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
async def ai_risk_predict(req: RiskPredictRequest):
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
        return res.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"糖尿病风险预测失败：{str(e)}")