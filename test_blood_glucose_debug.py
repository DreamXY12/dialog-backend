import requests
import json

# 测试添加血糖记录
base_url = "http://localhost:8000/api/v1"
token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwidXNlcl90eXBlIjoicGF0aWVudCIsImxvZ2luX2NvZGUiOiI1NzkwIiwiZXhwIjoxNzczMTI2NDk1fQ.zML4cJ8bWnoe16MsEUgW9kLXC8gTCgcWYQy-vxK8X6k"

# 测试添加血糖记录
def test_add_blood_glucose():
    url = f"{base_url}/users/patients/me/blood-glucose"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    data = {
        "value": 6.2,
        "period": "餐后",
        "time": "2026-03-03T12:00:00"
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        print(f"添加血糖记录 - 状态码: {response.status_code}")
        print(f"响应内容: {response.json()}")
    except Exception as e:
        print(f"测试失败: {e}")

if __name__ == "__main__":
    print("测试添加血糖记录...")
    test_add_blood_glucose()
