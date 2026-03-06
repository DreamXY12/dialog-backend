# 护士和病人共有的SQL操作

from sqlalchemy.orm import Session
from typing import Union
from sql.people_models import Nurse, Patient

def get_user_by_phone(db: Session, phone: str, user_type: str) -> Union[Patient, Nurse, None]:
    """根据手机号+角色查询用户"""
    if user_type == "patient":
        return db.query(Patient).filter(Patient.phone == phone).first()
    elif user_type == "nurse":
        return db.query(Nurse).filter(Nurse.phone == phone).first()
    return None