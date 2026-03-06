# 病人相关的SQL操作

from sqlalchemy.orm import Session
from sql.people_models import Patient,Gender,SmokingStatus,DrinkingFrequency, FamilyHistory

# 通过序号找患者，因为在创建患者时就把信息塞到token里面去了
def get_patient_by_id(db: Session, patient_id: int):
    return db.query(Patient).filter(Patient.patient_id == patient_id).first()

def get_patient_by_phone(db: Session, phone: str) -> Patient | None:
    """按手机号查询患者（核心函数）"""
    return db.query(Patient).filter(Patient.phone == phone).first()

def update_patient_record(db: Session, patient_id: int, update_data: dict):
    """更新患者信息（移除护士关联逻辑，仅处理患者基础信息）"""
    patient = get_patient_by_id(db, patient_id)
    if not patient:
        return None

    # 遍历更新字段（仅处理患者基础信息，移除护士相关逻辑）
    for key, value in update_data.items():
        if value is None or not hasattr(patient, key):
            continue

        try:
            # 1. 枚举字段转换（严格匹配模型枚举类）
            if key == "sex":
                patient.sex = Gender(value)
            elif key == "family_history":
                patient.family_history = FamilyHistory(value)
            elif key == "smoking_status":
                patient.smoking_status = SmokingStatus(value)
            elif key == "drinking_history":
                patient.drinking_history = DrinkingFrequency(value)
            # 2. 普通字段直接赋值（身高/体重/出生日期等）
            else:
                setattr(patient, key, value)

        except ValueError as e:
            # 枚举值不匹配时的友好提示
            print(f"字段 {key} 值 {value} 无效: {e}")
            continue
        except Exception as e:
            print(f"设置字段 {key} 出错: {e}")
            continue

    try:
        db.commit()
        db.refresh(patient)  # 恢复refresh，新模型枚举转换无问题
        return patient
    except Exception as e:
        db.rollback()
        print(f"更新患者记录失败: {str(e)}")
        return None