# 工具模块
from datetime import timedelta, datetime
from typing import Optional
from jose import  jwt,JWTError
from config import get_parameter
import time

# JWT配置（固定值，生产环境建议移到环境变量）
SECRET_KEY = get_parameter("web","secrete_key") or "your-secret-key-here-change-in-production"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_DAYS = 14
ACCESS_TOKEN_EXPIRE_MINUTES = ACCESS_TOKEN_EXPIRE_DAYS * 24 * 60  # 14天
#ACCESS_TOKEN_EXPIRE_MINUTES = 0.5 # 测试用

# ---------------------------
# 核心工具函数（适配手机号登录）
# ---------------------------
def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """生成JWT Token（有效期3天）"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now() + expires_delta
    else:
        expire = datetime.now() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_token(token: str, verify_exp: bool = False) -> Optional[dict]:
    try:
        if verify_exp:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        else:
            # 忽略过期验证，只校验签名
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM], options={"verify_exp": False})
        # exp_ts = payload["exp"]
        #
        # print(f"\nexp时间戳(秒): {exp_ts}")
        # print(f"过期UTC时间: {datetime.utcfromtimestamp(exp_ts)}")
        # print(f"过期本地时间: {datetime.fromtimestamp(exp_ts)}")
        #
        # now_ts = int(time.time())
        # print(f"当前时间戳: {now_ts}")
        # print(f"是否过期:{now_ts > exp_ts}")
        return payload
    except JWTError:
        return None