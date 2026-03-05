import requests
import json

# 测试血糖管理API
base_url = "http://localhost:8000/api/v1"

# 测试添加血糖记录
def test_add_blood_glucose():
    url = f"{base_url}/users/patients/me/blood-glucose"
    headers = {
        "Content-Type": "application/json",
        # 这里需要一个有效的token，暂时使用假token进行测试
        "Authorization": "Bearer test_token"
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
        "Authorization": "Bearer test_token"
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
