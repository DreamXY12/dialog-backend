from api.auth import get_password_hash

# 测试密码加密
password = "123456"
hashed_password = get_password_hash(password)
print(f"原始密码: {password}")
print(f"加密结果: {hashed_password}")
print(f"加密结果长度: {len(hashed_password)}")