from sql.start import get_db
from sql.login_models import Patient

# 检查患者是否存在
def check_patient_exists():
    db = next(get_db())
    try:
        # 检查ID为1的患者
        patient = db.query(Patient).filter(Patient.patient_id == 1).first()
        if patient:
            print(f"患者存在: ID={patient.patient_id}, 登录码={patient.login_code}, 姓名={patient.first_name}{patient.last_name}")
        else:
            print("患者不存在 (ID=1)")
        
        # 检查所有患者
        patients = db.query(Patient).all()
        print(f"\n所有患者:")
        for p in patients:
            print(f"ID={p.patient_id}, 登录码={p.login_code}, 姓名={p.first_name}{p.last_name}")
    finally:
        db.close()

if __name__ == "__main__":
    print("检查患者记录...")
    check_patient_exists()
