#用于患者页面的后端操作
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Dict, Any
from sql.start import get_db
from sql.login_crud import get_patient_by_login_code, get_nurse_by_id,get_nurse_by_login_code
from datetime import date

# 后端前缀
router = APIRouter(prefix="/patient", tags=["patient"])


@router.get("/profile")
async def get_patient_profile(
        login_code: str = Query(..., description="登录码"),
        db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    获取病人完整资料
    通过登录码和密码验证身份
    """
    # 验证用户身份
    user = get_patient_by_login_code(db, login_code)
    if not user or not hasattr(user, 'patient_id'):
        raise HTTPException(status_code=401, detail="登录码或密码错误")

    patient = user

    # 计算年龄
    age = None
    if patient.date_of_birth:
        today = date.today()
        age = today.year - patient.date_of_birth.year
        if (today.month, today.day) < (patient.date_of_birth.month, patient.date_of_birth.day):
            age -= 1

    # 计算BMI
    bmi = None
    if patient.height and patient.weight:
        bmi = round(float(patient.weight) / ((float(patient.height) / 100) ** 2), 1)

    # 获取护士信息
    nurse_info = None
    if patient.assigned_nurse_id:
        nurse = get_nurse_by_login_code(db, patient.assigned_nurse_id)
        if nurse:
            nurse_info = {
                "nurse_id": nurse.nurse_id,
                "first_name": nurse.first_name,
                "last_name": nurse.last_name,
                "full_name": f"{nurse.first_name}{nurse.last_name}"
            }

    # 构建响应
    response = {
        "patient": {
            "patient_id": patient.patient_id,
            "first_name": patient.first_name,
            "last_name": patient.last_name,
            "full_name": f"{patient.first_name}{patient.last_name}",
            "date_of_birth": patient.date_of_birth.isoformat() if patient.date_of_birth else None,
            "age": age,
            "sex": patient.sex,
            "family_history": patient.family_history,
            "smoking_status": patient.smoking_status,
            "drinking_history": patient.drinking_history,
            "height": float(patient.height) if patient.height else None,
            "weight": float(patient.weight) if patient.weight else None,
            "bmi": bmi
        },
        "nurse": nurse_info
    }

    return response

