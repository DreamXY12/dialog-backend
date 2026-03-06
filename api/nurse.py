from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from fastapi import Query

from sql.start import get_db
from sql.login_models import Nurse
from sql.schemas import NurseCreate, NurseResponse
#from api.auth import get_password_hash, mark_login_code_as_used, get_login_code
import sql.login_crud as login_curd
import re  # 正则表达式模块

from typing import List
from pydantic import BaseModel

class BatchAssignRequest(BaseModel):
    patient_login_codes: List[str]

router = APIRouter(prefix="/nurses", tags=["nurses"])


# 护士相关函数
def get_nurse_by_id(db: Session, nurse_id: int):
    return db.query(Nurse).filter(Nurse.nurse_id == nurse_id).first()


def get_all_nurses(db: Session, skip: int = 0, limit: int = 100):
    return db.query(Nurse).offset(skip).limit(limit).all()


def create_nurse_record(db: Session, login_code: str, first_name: str, last_name: str, password: str):
    # 检查登录码是否可用
    #login_code_obj = get_login_code(db, login_code)
    login_code_obj = ""
    if not login_code_obj or login_code_obj.is_used:
        return None

    #这里也是一样的
    # 创建护士
    nurse = Nurse(
        login_code=login_code,
        first_name=first_name,
        last_name=last_name,
        hashed_password=password
    )

    db.add(nurse)
    db.commit()
    db.refresh(nurse)

    # 标记登录码为已使用
    #mark_login_code_as_used(db, login_code, "nurse")

    return nurse


# 路由
@router.post("/register", response_model=NurseResponse)
async def register_nurse(
        request: NurseCreate,
        db: Session = Depends(get_db)
):
    """注册护士"""
    try:
        nurse = create_nurse_record(
            db,
            request.login_code,
            request.first_name,
            request.last_name,
            request.password
        )

        if not nurse:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="注册失败，登录码无效或已被使用"
            )

        # 刷新对象
        db.refresh(nurse)

        return NurseResponse(
            nurse_id= nurse.nurse_id,
            login_code=nurse.login_code,
            first_name=nurse.first_name,
            last_name=nurse.last_name,
            full_name=nurse.first_name+nurse.last_name
        )
    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"注册失败: {str(e)}"
        )


@router.get("/", response_model=List[NurseResponse])
async def get_nurses(
        skip: int = 0,
        limit: int = 100,
        db: Session = Depends(get_db)
):
    """获取所有护士"""
    return get_all_nurses(db, skip, limit)


@router.get("/{nurse_id}", response_model=NurseResponse)
async def get_nurse(nurse_id: int, db: Session = Depends(get_db)):
    """获取护士信息"""
    nurse = get_nurse_by_id(db, nurse_id)
    if not nurse:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="护士不存在"
        )
    return nurse


# ==================== 新增的三个端点 ====================

@router.get("/{nurse_login_code}/unassigned-patients")
async def get_unassigned_patients_for_nurse(
        nurse_login_code: str,
        page: int = Query(1, ge=1, description="页码，从1开始"),
        page_size: int = Query(20, ge=1, le=100, description="每页记录数"),
        db: Session = Depends(get_db)
):
    """
    获取该护士可以分配的未分配患者
    """
    # 护士验证在数据库操作函数中已经完成
    result = login_curd.get_patients_without_nurse_paginated_by_login_codes(db, page, page_size)

    # 获取护士信息用于返回
    nurse = db.query(Nurse).filter(Nurse.login_code == nurse_login_code).first()
    nurse_name = nurse.full_name if nurse else None

    return {
        "success": True,
        "nurse_login_code": nurse_login_code,
        "nurse_name": nurse_name,
        "data": {
            "patients": result["patients"],
            "pagination": result["pagination"]
        }
    }


@router.post("/{nurse_login_code}/assign-patient/{patient_login_code}")
async def assign_patient_to_nurse(
        nurse_login_code: str,
        patient_login_code: str,
        db: Session = Depends(get_db)
):
    """
    分配患者给护士
    """
    # 验证患者登录码格式
    if not re.match(r'^\d{4}$', patient_login_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="患者登录码必须是4位数字"
        )

    # 使用数据库操作函数，护士验证在函数内部完成
    patient = login_curd.assign_patient_to_nurse_by_login_code(db, patient_login_code, nurse_login_code)

    if not patient:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"分配失败，患者登录码 {patient_login_code} 或护士登录码 {nurse_login_code} 不存在，或患者已被分配"
        )

    return {
        "success": True,
        "message": f"成功将患者 {patient_login_code} 分配给护士 {nurse_login_code}",
        "data": {
            "patient": {
                "patient_id": patient.patient_id,
                "patient_login_code": patient.login_code,
                "full_name": patient.full_name,
                "assigned_nurse_id": patient.assigned_nurse_id
            }
        }
    }


@router.delete("/{nurse_login_code}/unassign-patient/{patient_login_code}")
async def unassign_patient_from_nurse(
        nurse_login_code: str,
        patient_login_code: str,
        db: Session = Depends(get_db)
):
    """
    护士解除患者分配
    """
    # 验证患者登录码格式
    if not re.match(r'^\d{4}$', patient_login_code):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="患者登录码必须是4位数字"
        )

    # 使用数据库操作函数，护士验证在函数内部完成
    patient = login_curd.unassign_patient_from_specific_nurse_by_login_code(db, patient_login_code, nurse_login_code)

    if not patient:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"解除分配失败，患者登录码 {patient_login_code} 不是护士 {nurse_login_code} 负责的患者"
        )

    return {
        "success": True,
        "message": f"已成功解除护士 {nurse_login_code} 对患者 {patient_login_code} 的管理",
        "data": {
            "patient": {
                "patient_id": patient.patient_id,
                "patient_login_code": patient.login_code,
                "full_name": patient.full_name,
                "assigned_nurse_id": patient.assigned_nurse_id
            }
        }
    }

@router.get("/{nurse_login_code}/patients")
async def get_nurse_patients(
        nurse_login_code: str,
        page: int = Query(1, ge=1, description="页码，从1开始"),
        page_size: int = Query(20, ge=1, le=100, description="每页记录数"),
        db: Session = Depends(get_db)
):
    """
    获取护士管理的所有患者
    """
    try:
        result = login_curd.get_patients_by_nurse_paginated(db, nurse_login_code, page, page_size)

        return {
            "success": True,
            "nurse_login_code": nurse_login_code,
            "data": result
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"获取患者失败: {str(e)}"
        )

@router.get("/{nurse_login_code}/unassigned-patients")
async def get_unassigned_patients_for_nurse(
    nurse_login_code: str,
    page: int = Query(1, ge=1, description="页码，从1开始"),
    page_size: int = Query(20, ge=1, le=100, description="每页记录数"),
    search: str = Query(None, description="搜索关键词"),
    db: Session = Depends(get_db)
):
    """
    获取该护士可以分配的未分配患者
    """
    try:
        result = login_curd.get_patients_without_nurse_paginated_by_login_codes(
            db, page, page_size, search
        )

        return {
            "success": True,
            "nurse_login_code": nurse_login_code,
            "data": result
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"获取未分配患者失败: {str(e)}"
        )


@router.post("/{nurse_login_code}/batch-assign")
async def batch_assign_patients_to_nurse(
        nurse_login_code: str,
        request: BatchAssignRequest,
        db: Session = Depends(get_db)
):
    """
    批量分配患者给护士
    """
    try:
        results = {
            "success": [],
            "failed": []
        }
        assigned_count = 0
        failed_count = 0

        for patient_login_code in request.patient_login_codes:
            # 验证患者登录码格式
            if not re.match(r'^\d{4}$', patient_login_code):
                results["failed"].append({
                    "patient_login_code": patient_login_code,
                    "reason": "登录码格式错误"
                })
                failed_count += 1
                continue

            # 尝试分配
            patient = login_curd.assign_patient_to_nurse_by_login_code(db, patient_login_code, nurse_login_code)

            if patient:
                results["success"].append({
                    "patient_id": patient.patient_id,
                    "login_code": patient.login_code,
                    "full_name": patient.full_name
                })
                assigned_count += 1
            else:
                results["failed"].append({
                    "patient_login_code": patient_login_code,
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