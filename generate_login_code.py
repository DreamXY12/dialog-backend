from sql.start import get_db
from sql.login_models import LoginCode
from datetime import datetime
import random

# 生成登录码
def generate_login_code():
    db = next(get_db())
    try:
        # 生成4位数字登录码
        while True:
            code = f"{random.randint(1000, 9999)}"
            # 检查是否已存在
            existing = db.query(LoginCode).filter(LoginCode.code == code).first()
            if not existing:
                break
        
        # 创建登录码记录
        login_code = LoginCode(
            code=code,
            is_used=False,
            user_type="patient"
        )
        db.add(login_code)
        db.commit()
        db.refresh(login_code)
        
        print(f"生成登录码成功: {code}")
        return code
    except Exception as e:
        print(f"生成登录码失败: {e}")
        db.rollback()
        return None
    finally:
        db.close()

if __name__ == "__main__":
    print("生成登录码...")
    generate_login_code()
