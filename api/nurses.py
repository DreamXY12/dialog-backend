from fastapi import APIRouter, HTTPException, Query, Path, Depends,status
from pydantic import BaseModel
from typing import List, Optional
from sql.people_models import Nurse
import re
from sqlalchemy.orm import Session
from sql.start import get_db
from sql.nurse_curd import  get_patients_without_nurse_paginated_by_phone,assign_patient_to_nurse_by_phone
from sql.nurse_curd import unassign_patient_from_specific_nurse_by_phone,get_patients_by_nurse_paginated

# 初始化路由
router = APIRouter(prefix="/nurses", tags=["nurses"])

# -------------------------- 请求模型定义 --------------------------
class BatchAssignRequest(BaseModel):
    """批量分配请求模型（替换为手机号）"""
    patient_phones: List[str]  # 替换 patient_login_codes

# -------------------------- 核心接口实现 --------------------------
@router.get("/{nurse_phone}/unassigned-patients")
async def get_unassigned_patients_for_nurse(
    nurse_phone: str = Path(..., description="护士手机号"),
    page: int = Query(1, ge=1, description="页码，从1开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页记录数"),
    search: str = Query(None, description="搜索关键词"),
    db: Session = Depends(get_db)
):
    """
    获取该护士可以分配的未分配患者（替换为手机号）
    """
    try:
        # 调用curd层（需同步修改为按手机号查询）
        result = get_patients_without_nurse_paginated_by_phone(
            db, page, page_size, search
        )

        # 获取护士信息
        nurse = db.query(Nurse).filter(Nurse.phone == nurse_phone).first()  # 替换 login_code 为 phone
        nurse_name = nurse.full_name if nurse else None

        return {
            "success": True,
            "nurse_phone": nurse_phone,  # 替换 nurse_login_code
            "nurse_name": nurse_name,
            "data": result
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"获取未分配患者失败: {str(e)}"
        )


@router.post("/{nurse_phone}/assign-patient/{patient_phone}")
async def assign_patient_to_nurse(
    nurse_phone: str = Path(..., description="护士手机号"),
    patient_phone: str = Path(..., description="患者手机号"),
    db: Session = Depends(get_db)
):
    """
    分配患者给护士（替换为手机号）
    """
    # 验证手机号格式（可根据实际需求调整正则）
    if not re.match(r'^1[3-9]\d{9}$', patient_phone):  # 匹配中国大陆手机号
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="患者手机号格式错误（需为11位有效手机号）"
        )

    # 调用curd层（需同步修改为按手机号分配）
    patient = assign_patient_to_nurse_by_phone(db, patient_phone, nurse_phone)

    if not patient:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"分配失败，患者手机号 {patient_phone} 或护士手机号 {nurse_phone} 不存在，或患者已被分配"
        )

    return {
        "success": True,
        "message": f"成功将患者 {patient_phone} 分配给护士 {nurse_phone}",
        "data": {
            "patient": {
                "patient_id": patient.patient_id,
                "patient_phone": patient.phone,  # 替换 patient_login_code
                "full_name": patient.full_name,
                "assigned_nurse_id": patient.assigned_nurse_id
            }
        }
    }


@router.delete("/{nurse_phone}/unassign-patient/{patient_phone}")
async def unassign_patient_from_nurse(
    nurse_phone: str = Path(..., description="护士手机号"),
    patient_phone: str = Path(..., description="患者手机号"),
    db: Session = Depends(get_db)
):
    """
    护士解除患者分配（替换为手机号）
    """
    # 验证手机号格式
    if not re.match(r'^1[3-9]\d{9}$', patient_phone):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="患者手机号格式错误（需为11位有效手机号）"
        )

    # 调用curd层（需同步修改为按手机号解除分配）
    patient = unassign_patient_from_specific_nurse_by_phone(db, patient_phone, nurse_phone)

    if not patient:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"解除分配失败，患者手机号 {patient_phone} 不是护士 {nurse_phone} 负责的患者"
        )

    return {
        "success": True,
        "message": f"已成功解除护士 {nurse_phone} 对患者 {patient_phone} 的管理",
        "data": {
            "patient": {
                "patient_id": patient.patient_id,
                "patient_phone": patient.phone,  # 替换 patient_login_code
                "full_name": patient.full_name,
                "assigned_nurse_id": patient.assigned_nurse_id
            }
        }
    }


@router.get("/{nurse_phone}/patients")
async def get_nurse_patients(
    nurse_phone: str = Path(..., description="护士手机号"),
    page: int = Query(1, ge=1, description="页码，从1开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页记录数"),
    db: Session = Depends(get_db)
):
    """
    获取护士管理的所有患者（替换为手机号）
    """
    try:
        # 调用curd层（需同步修改为按护士手机号查询）
        result = get_patients_by_nurse_paginated(db, nurse_phone, page, page_size)

        return {
            "success": True,
            "nurse_phone": nurse_phone,  # 替换 nurse_login_code
            "data": result
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"获取患者失败: {str(e)}"
        )


@router.post("/{nurse_phone}/batch-assign")
async def batch_assign_patients_to_nurse(
    nurse_phone: str = Path(..., description="护士手机号"),
    request: BatchAssignRequest = ...,  # 使用新的请求模型（patient_phones）
    db: Session = Depends(get_db)
):
    """
    批量分配患者给护士（替换为手机号）
    """
    try:
        results = {
            "success": [],
            "failed": []
        }
        assigned_count = 0
        failed_count = 0

        for patient_phone in request.patient_phones:  # 替换 patient_login_codes
            # 验证手机号格式
            if not re.match(r'^1[3-9]\d{9}$', patient_phone):
                results["failed"].append({
                    "patient_phone": patient_phone,  # 替换 patient_login_code
                    "reason": "手机号格式错误"
                })
                failed_count += 1
                continue

            # 尝试分配（调用修改后的curd方法）
            patient = assign_patient_to_nurse_by_phone(db, patient_phone, nurse_phone)

            if patient:
                results["success"].append({
                    "patient_id": patient.patient_id,
                    "phone": patient.phone,  # 替换 login_code
                    "full_name": patient.full_name
                })
                assigned_count += 1
            else:
                results["failed"].append({
                    "patient_phone": patient_phone,  # 替换 patient_login_code
                    "reason": "患者或护士不存在，或患者已被分配"
                })
                failed_count += 1

        return {
            "success": assigned_count > 0,  # 只要有成功的就返回True
            "message": f"成功分配 {assigned_count} 位患者，{failed_count} 位失败",
            "data": {
                "assigned_count": assigned_count,
                "failed_count": failed_count,
                "results": results
            }
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"批量分配失败: {str(e)}"
        )