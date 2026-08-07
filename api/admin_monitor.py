from fastapi import APIRouter, Depends, Query,HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, case
from typing import List
from datetime import date, datetime
from sql.start import get_db
from sql.people_models import (
    Patient,
    Case,
    FoodImage,
    ChatRoom,
    Message
)
from schema.admin_monitor import (
    PatientMonitorDetail,
    PatientDailyStat,
    PatientSimpleItem,
    PatientMonitorListResp
)
# 这里引入你的管理员权限依赖，示例：from core.deps import admin_required
# from core.deps import admin_required

router = APIRouter(prefix="/admin/patient-monitor", tags=["管理员-患者数据监控"])


@router.get("/patient-list", response_model=PatientMonitorListResp)
def get_patient_simple_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    # _ = Depends(admin_required)
):
    """获取患者简易下拉列表，用于监控面板选择患者"""
    offset = (page - 1) * page_size
    stmt_total = select(func.count(Patient.patient_id))
    total = db.scalar(stmt_total) or 0

    stmt_items = (
        select(Patient.patient_id, Patient.subject_code, Patient.first_name, Patient.last_name)
        .order_by(Patient.patient_id)
        .offset(offset)
        .limit(page_size)
    )
    rows = db.execute(stmt_items).all()
    items: List[PatientSimpleItem] = []
    for r in rows:
        full_name = f"{r.first_name} {r.last_name}"
        items.append(PatientSimpleItem(
            patient_id=r.patient_id,
            subject_code=r.subject_code,
            full_name=full_name
        ))
    return PatientMonitorListResp(items=items, total=total)


@router.get("/detail/{patient_id}", response_model=PatientMonitorDetail)
def get_patient_monitor_detail(
    patient_id: int,
    db: Session = Depends(get_db),
    # _ = Depends(admin_required)
):
    """
    获取单个患者完整监控统计
    业务规则：
    1.时间范围：患者账号create_time → 当前日期
    2.AI对话：PatientAIDialogHistory，按日期分组，当天有任意对话记录=has_ai_chat=True
    3.风险预测：Case表记录，当天存在预测记录=has_risk_predict=True；糖尿病/CKD互斥由前端根据patient.has_diabetes区分
    4.食物图片上传：FoodImage，当天有上传记录=has_food_upload=True
    频率计算公式：活跃天数 / (当前日期 - 账号创建日期).days；总天数为0则频率=0
    """
    # 1.读取患者基础信息
    stmt_patient = select(Patient).where(Patient.patient_id == patient_id)
    patient = db.scalar(stmt_patient)
    if not patient:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="患者不存在")

    account_create_dt: datetime = patient.create_time
    account_create_date: date = account_create_dt.date()
    today = date.today()

    # 总经历天数（账号创建到今天，包含首尾两天）
    delta_days = (today - account_create_date).days
    total_duration_days = delta_days + 1
    if total_duration_days <= 0:
        total_duration_days = 1

    # -------- 1. AI对话按天统计 Message --------
    stmt_ai = (
        select(func.date(Message.create_time).label("stat_date"), func.count(1).label("cnt"))
        .where(Message.sender_id == patient.patient_id)
        .group_by(func.date(Message.create_time))
    )
    ai_rows = db.execute(stmt_ai).all()
    ai_date_set = {row.stat_date for row in ai_rows if row.stat_date}  # 用于 has_ai_chat
    ai_count_dict = {row.stat_date: row.cnt for row in ai_rows}  # 用于计数

    # -------- 2.风险预测 Case 按天统计 --------
    stmt_case = (
        select(func.date(Case.create_time).label("stat_date"), func.count(1).label("cnt"))
        .where(Case.user_id == patient.patient_id)
        .group_by(func.date(Case.create_time))
    )
    case_rows = db.execute(stmt_case).all()
    predict_date_set = {row.stat_date for row in case_rows if row.stat_date}
    predict_count_dict = {row.stat_date: row.cnt for row in case_rows}

    # -------- 3.食物图片上传 FoodImage 按天统计 --------
    stmt_food = (
        select(func.date(FoodImage.upload_timestamp).label("stat_date"), func.count(1).label("cnt"))
        .where(FoodImage.patient_id == patient.patient_id)
        .group_by(func.date(FoodImage.upload_timestamp))
    )
    food_rows = db.execute(stmt_food).all()
    food_date_set = {row.stat_date for row in food_rows if row.stat_date}
    food_count_dict = {row.stat_date: row.cnt for row in food_rows}

    # 组装每日明细：从账号创建到今天循环每一天
    daily_list: List[PatientDailyStat] = []
    import datetime as dt
    current_loop_date = account_create_date
    while current_loop_date <= today:
        daily_list.append(PatientDailyStat(
            stat_date=current_loop_date,
            has_ai_chat=current_loop_date in ai_date_set,
            ai_chat_count=ai_count_dict.get(current_loop_date, 0),
            has_risk_predict=current_loop_date in predict_date_set,
            risk_predict_count=predict_count_dict.get(current_loop_date, 0),
            has_food_upload=current_loop_date in food_date_set,
            food_upload_count=food_count_dict.get(current_loop_date, 0)
        ))
        current_loop_date = current_loop_date + dt.timedelta(days=1)

    # 统计活跃天数
    total_ai_chat_days = len(ai_date_set)
    total_risk_predict_days = len(predict_date_set)
    total_food_upload_days = len(food_date_set)

    # 计算频率 0~1
    ai_chat_frequency = round(total_ai_chat_days / total_duration_days, 4)
    risk_predict_frequency = round(total_risk_predict_days / total_duration_days, 4)
    food_upload_frequency = round(total_food_upload_days / total_duration_days, 4)

    return PatientMonitorDetail(
        patient_id=patient.patient_id,
        subject_code=patient.subject_code,
        full_name=f"{patient.first_name} {patient.last_name}",
        phone=patient.phone,
        has_diabetes=patient.has_diabetes,
        account_create_time=patient.create_time,
        total_ai_chat_days=total_ai_chat_days,
        ai_chat_frequency=ai_chat_frequency,
        total_risk_predict_days=total_risk_predict_days,
        risk_predict_frequency=risk_predict_frequency,
        total_food_upload_days=total_food_upload_days,
        food_upload_frequency=food_upload_frequency,
        daily_list=daily_list
    )


@router.get("/daily-chat/{patient_id}/{target_date}")
def get_patient_day_ai_chat_records(
    patient_id: int,
    target_date: date,
    db: Session = Depends(get_db),
    # _ = Depends(admin_required)
):
    """获取患者某一天AI对话原始记录，供前端弹窗查看当日对话"""
    stmt_p = select(Patient).where(Patient.patient_id == patient_id)
    p = db.scalar(stmt_p)
    if not p:
        raise HTTPException(status_code=404, detail="患者不存在")

    stmt_history = (
        select(Message)
        .where(
            and_(
                Message.sender_id == p.patient_id,
                func.date(Message.create_time) == target_date
            )
        )
        .order_by(Message.create_time)
    )
    records = db.scalars(stmt_history).all()
    result = []
    for rec in records:
        result.append({
            "history_id": rec.history_id,
            "session_key": rec.session_key,
            "ai_model": rec.ai_model,
            "title": rec.title,
            "message_count": rec.message_count,
            "last_message_time": rec.last_message_time,
            "create_time": rec.create_time
        })
    return {"date": target_date, "records": result}