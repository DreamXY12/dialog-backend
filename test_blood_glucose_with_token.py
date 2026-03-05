import requests
import json

# 测试血糖管理API
base_url = "http://localhost:8000/api/v1"
token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwidXNlcl90eXBlIjoicGF0aWVudCIsImZ1bGxfbmFtZSI6IuW8oOS4iSIsImV4cCI6MTc3MTQyNDc1Mn0.N20kqWGcz2ouIwPcDKYGWJ0LIJE"

# 测试添加血糖记录
def test_add_blood_glucose():
    url = f"{base_url}/users/patients/me/blood-glucose"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    data = {
        "value": 5.6,
        "period": "空腹",
        "time": "2026-03-03T10:00:00"
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        print(f"添加血糖记录 - 状态码: {response.status_code}")
        print(f"响应内容: {response.json()}")
    except Exception as e:
        print(f"测试失败: {e}")

# 测试获取血糖记录
def test_get_blood_glucose():
    url = f"{base_url}/users/patients/me/blood-glucose"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    try:
        response = requests.get(url, headers=headers)
        print(f"获取血糖记录 - 状态码: {response.status_code}")
        print(f"响应内容: {response.json()}")
    except Exception as e:
        print(f"测试失败: {e}")

if __name__ == "__main__":
    print("测试血糖管理API...")
    print("=" * 50)
    test_add_blood_glucose()
    print("-" * 50)
    test_get_blood_glucose()
    print("=" * 50)
