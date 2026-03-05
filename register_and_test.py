import requests
import json

# 注册患者并测试血糖管理API
base_url = "http://localhost:8000/api/v1"

# 1. 注册患者
def register_patient():
    url = f"{base_url}/users/patients/register"
    data = {
        "login_code": "1181",
        "first_name": "测试",
        "last_name": "患者",
        "password": "123456"
    }
    
    try:
        response = requests.post(url, json=data)
        print(f"注册患者 - 状态码: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"注册成功: {data}")
            return data.get("access_token")
        else:
            print(f"注册失败: {response.json()}")
            return None
    except Exception as e:
        print(f"注册失败: {e}")
        return None

# 2. 测试添加血糖记录
def test_add_blood_glucose(token):
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

# 3. 测试获取血糖记录
def test_get_blood_glucose(token):
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
    print("注册患者并测试血糖管理API...")
    print("=" * 50)
    
    # 注册患者
    token = register_patient()
    
    if token:
        print("-" * 50)
        # 测试添加血糖记录
        test_add_blood_glucose(token)
        print("-" * 50)
        # 测试获取血糖记录
        test_get_blood_glucose(token)
    
    print("=" * 50)
