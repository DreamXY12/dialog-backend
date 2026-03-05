import jwt
from config import get_parameter

# 解码JWT令牌
def decode_token(token):
    SECRET_KEY = get_parameter("web","secrete_key") or "your-secret-key-here-change-in-production"
    ALGORITHM = "HS256"
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except Exception as e:
        print(f"解码失败: {e}")
        return None

# 测试令牌
token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwidXNlcl90eXBlIjoicGF0aWVudCIsImZ1bGxfbmFtZSI6IuW8oOS4iSIsImV4cCI6MTc3MTQyNDc1Mn0.N20kqWGcz2ouIwPcDKYGWJ0LIJE"

if __name__ == "__main__":
    print("解码令牌...")
    payload = decode_token(token)
    print(f"令牌内容: {payload}")
    if payload:
        print(f"用户ID: {payload.get('sub')}")
        print(f"用户类型: {payload.get('user_type')}")
        print(f"用户名: {payload.get('full_name')}")
