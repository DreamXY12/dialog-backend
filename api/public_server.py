# api/public_server.py
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, datetime, timedelta
from typing import Optional
from sql.start import get_db
from sql.people_models import Patient, Case, Message, FoodImage
from sql.ckd_model import PatientCkdRiskRecord  # 保留但不使用，保持与原接口一致（只查Case）

router = APIRouter(prefix="/public", tags=["对外接口"])


def remove_area_code(full_phone: str | None, area_code: str | None) -> str:
    """从完整手机号开头移除区号（复制自 admin_monitor）"""
    if not full_phone or not area_code:
        return full_phone if full_phone else ""
    if full_phone.startswith(area_code):
        return full_phone[len(area_code):]
    return full_phone


def get_patient_stats(db: Session, patient: Patient, target_date: Optional[date] = None):
    """
    获取患者的监控统计数据。
    若 target_date 为 None，返回从账号创建到今天的完整统计（与原 detail 接口一致）；
    若指定日期，只返回该日的统计。
    """
    if target_date is None:
        # ----- 完整统计（同原 detail） -----
        account_create_date = patient.create_time.date()
        today = date.today()
        total_duration_days = (today - account_create_date).days + 1
        if total_duration_days <= 0:
            total_duration_days = 1

        # AI 对话按日分组
        ai_rows = (
            db.query(func.date(Message.create_time).label("d"), func.count(1).label("c"))
            .filter(Message.sender_id == patient.patient_id)
            .group_by(func.date(Message.create_time))
            .all()
        )
        ai_dict = {row.d: row.c for row in ai_rows}
        ai_dates = set(ai_dict.keys())

        # 风险预测按日分组（根据 has_diabetes 选择表）
        if patient.has_diabetes == "Yes":
            risk_rows = (
                db.query(func.date(PatientCkdRiskRecord.create_time).label("d"), func.count(1).label("c"))
                .filter(PatientCkdRiskRecord.patient_id == patient.patient_id)
                .group_by(func.date(PatientCkdRiskRecord.create_time))
                .all()
            )
        else:
            risk_rows = (
                db.query(func.date(Case.create_time).label("d"), func.count(1).label("c"))
                .filter(Case.user_id == patient.patient_id)
                .group_by(func.date(Case.create_time))
                .all()
            )
        risk_dict = {row.d: row.c for row in risk_rows}
        risk_dates = set(risk_dict.keys())

        # 食物图片按日分组
        food_rows = (
            db.query(func.date(FoodImage.upload_timestamp).label("d"), func.count(1).label("c"))
            .filter(FoodImage.patient_id == patient.patient_id)
            .group_by(func.date(FoodImage.upload_timestamp))
            .all()
        )
        food_dict = {row.d: row.c for row in food_rows}
        food_dates = set(food_dict.keys())

        # 生成每日明细
        daily_list = []
        cur = account_create_date
        while cur <= today:
            daily_list.append({
                "date": cur.isoformat(), # 时间
                "ai_chat_count": ai_dict.get(cur, 0), # 当天对话总数，只统计用户发送的消息，没有统计AI的
                "risk_predict_count": risk_dict.get(cur, 0), # 当天使用风险预测的次数
                "food_upload_count": food_dict.get(cur, 0),  # 当天使用食物图片上传的次数
            })
            cur += timedelta(days=1)

        total_ai = len(ai_dates)
        total_risk = len(risk_dates)
        total_food = len(food_dates)

        return {
            "subject_code": patient.subject_code,  # 用户编号
            "full_name": f"{patient.first_name} {patient.last_name}", # 用户全名
            "phone": remove_area_code(patient.phone, patient.phone_area_code),# 用户电话
            "user_create_date":patient.create_time.date().isoformat(), # 用户账号创建的时间，格式YYYY-MM-DD
            "has_diabetes": patient.has_diabetes,# 是否有糖尿病，值为Yes或No，字符串
            "total_ai_chat_days": total_ai,  # 总的AI对话活跃天数，这个是统计用户当天发了消息，如果没有发消息就不会统计
            "total_risk_predict_days": total_risk, # 用的使用风险预测的天数，没有使用的天数不做统计
            "total_food_upload_days": total_food, # 使用图片上传功能的天数，没有使用就不做统计
            "daily_data_list": daily_list,  # 所有的信息
        }

    else:
        # ----- 单日统计 -----
        ai_count = (
            db.query(func.count(Message.message_id))
            .filter(
                Message.sender_id == patient.patient_id,
                func.date(Message.create_time) == target_date,
            )
            .scalar()
            or 0
        )

        if patient.has_diabetes == "Yes":
            risk_count = (
                    db.query(func.count(PatientCkdRiskRecord.id))
                    .filter(
                        PatientCkdRiskRecord.patient_id == patient.patient_id,
                        func.date(PatientCkdRiskRecord.create_time) == target_date,
                    )
                    .scalar()
                    or 0
            )
        else:
            risk_count = (
                    db.query(func.count(Case.case_id))
                    .filter(
                        Case.user_id == patient.patient_id,
                        func.date(Case.create_time) == target_date,
                    )
                    .scalar()
                    or 0
            )

        food_count = (
            db.query(func.count(FoodImage.id))
            .filter(
                FoodImage.patient_id == patient.patient_id,
                func.date(FoodImage.upload_timestamp) == target_date,
            )
            .scalar()
            or 0
        )

        return {
            "subject_code": patient.subject_code,
            "full_name": f"{patient.first_name} {patient.last_name}",
            "phone": remove_area_code(patient.phone, patient.phone_area_code),
            "user_create_date":patient.create_time.date().isoformat(), # 用户账号创建的时间，格式YYYY-MM-DD
            "has_diabetes": patient.has_diabetes,
            "query_date": target_date,
            "daily_data": {
                "ai_chat_count": ai_count,
                "risk_predict_count": risk_count,
                "food_upload_count": food_count,
            },
        }


@router.get("/user/detail")
def get_patient_monitor_detail_public(
    phone: str = Query(..., description="8位纯电话号码（不含区号）"),
    date_str: Optional[str] = Query(None, description="可选日期，格式 YYYY-MM-DD，不传则返回全部"),
    db: Session = Depends(get_db),
):
    """
    对外接口：通过电话号码查询患者监控统计。
    - 若未提供 date_str，返回从账号创建至今的完整统计（与原 /detail/{patient_id} 一致）。
    - 若提供 date_str，只返回该日的统计。
    """
    # 1. 根据电话号码查找患者（只允许正式受试者）
    patients = db.query(Patient).filter(Patient.official_subject_sql_filter()).all()
    target_patient = None
    for p in patients:
        if remove_area_code(p.phone, p.phone_area_code) == phone:
            target_patient = p
            break

    if not target_patient:
        raise HTTPException(status_code=404, detail="未找到该电话号码对应的正式患者")

    # 2. 解析日期（若有）
    target_date = None
    if date_str:
        try:
            target_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式错误，应为 YYYY-MM-DD")

    # 3. 获取统计数据
    stats = get_patient_stats(db, target_patient, target_date)
    return stats