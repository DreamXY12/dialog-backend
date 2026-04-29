# 忽略 SSL 不安全警告（测试环境专用）
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from fastapi import APIRouter
from fastapi import HTTPException
import requests  # 用来发 POST 请求第三方后端
import boto3

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
async def ckd_predict():
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
        "creat": 67.42,
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
        # ==========================================
        # 你向后端发送 POST 请求（核心代码）
        # ==========================================
        response = requests.post(
            url=third_party_url,
            json=simulation_data,  # 前端传什么，你就转发什么
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
        ckd_result = response.json()

        # ==========================================
        # 自动生成图片可访问URL（关键！）
        # ==========================================
        bucket = ckd_result.get("bucket")
        key = ckd_result.get("key")
        if bucket and key:
            ckd_result["image_url"] = generate_s3_presigned_url(bucket, key)

        # 返回给前端
        return ckd_result

    # ==========================================
    # 全局网络错误处理（全部覆盖）
    # ==========================================
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


