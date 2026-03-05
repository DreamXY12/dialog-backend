from api.auth import get_password_hash, create_access_token
from sql.start import get_db
from sql.login_models import Patient, LoginCode
from datetime import timedelta

# 测试创建患者和生成令牌
def test_create_patient_and_token():
    db = next(get_db())
    try:
        # 检查是否有可用的登录码
        login_code = db.query(LoginCode).filter(LoginCode.is_used == False).first()
        if not login_code:
            print("没有可用的登录码，请先生成登录码")
            return
        
        # 创建患者
        patient = Patient(
            login_code=login_code.code,
            first_name="测试",
            last_name="患者",
            hashed_password=get_password_hash("123456")
        )
        db.add(patient)
        db.commit()
        db.refresh(patient)
        
        # 标记登录码为已使用
        login_code.is_used = True
        login_code.user_type = "patient"
        db.commit()
        
        print(f"创建患者成功: ID={patient.patient_id}, 登录码={patient.login_code}")
        
        # 生成令牌
        access_token = create_access_token(
            data={
                "sub": str(patient.patient_id),
                "user_type": "patient",
                "login_code": patient.login_code
            },
            expires_delta=timedelta(minutes=60)
        )
        
        print(f"生成令牌: {access_token}")
        print(f"使用此令牌测试血糖管理API")
        
    except Exception as e:
        print(f"创建患者失败: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    print("测试创建患者和生成令牌...")
    test_create_patient_and_token()
