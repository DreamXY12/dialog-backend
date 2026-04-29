# 忽略 SSL 不安全警告（测试环境专用）
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from fastapi import APIRouter
from fastapi import HTTPException
import requests  # 用来发 POST 请求第三方后端

router = APIRouter()

AI_BASE_URL="https://agent.dialog.polyusn.com"

# 糖尿病前期风险预测
@router.post("/ai/risk_predict")
async def ai_risk_predict():
    test_data={
        "user_id": 123,
        "lab_data": {
            "fastingGlucose": 5.9,
            "HBA1C": 5.8,
            "cholesHDL": 1.1,
            "triglyceride": 1.6
        },
        "time_spec": 5,
        "labtest_date": "2026-04-17"
    }
    try:
        res = requests.post(
            url=f"{AI_BASE_URL}/ai/risk_predict",
            json=test_data,
            timeout=30,
            verify=False
        )
        if not res.ok:
            raise HTTPException(status_code=res.status_code, detail=res.text)
        return res.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"糖尿病风险预测失败：{str(e)}")