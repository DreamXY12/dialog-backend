from fastapi import APIRouter, Depends, Query,HTTPException,UploadFile,File
from sqlalchemy.orm import Session
from sqlalchemy import select, func, and_, case
from typing import List
from datetime import date, datetime,time
from api.s3_service import s3_service
from sql.start import get_db
from api.food_service import food_service
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
import io
import zipfile
from fastapi.responses import Response, StreamingResponse
from schema.admin_monitor import ExportRequest
from sql.people_models import ChatRoom, SenderType
from sql.ckd_model import PatientCkdRiskRecord

router = APIRouter(prefix="/admin/patient-monitor", tags=["管理员-患者数据监控"])

def remove_area_code(full_phone: str | None, area_code: str | None) -> str:
    """
    从完整手机号开头移除区号
    :param full_phone: 带区号完整号码，例如 "+85211111111"
    :param area_code: 区号，例如 "+852"
    :return: 去除区号后的纯号码
    """
    # 处理空值
    if not full_phone or not area_code:
        return full_phone if full_phone else ""

    # 判断是否以区号开头，是则切掉前缀
    if full_phone.startswith(area_code):
        return full_phone[len(area_code):]
    # 如果号码前缀不匹配区号，原样返回
    return full_phone

# ===================== 数据导出服务 =====================
class PatientExportService:
    """患者数据导出服务（类方法，不写原始SQL）"""

    def __init__(self, db: Session, start_date: date, end_date: date):
        self.db = db
        self.start_date = start_date
        self.end_date = end_date

    def get_patients(self):
        """获取所有正式受试者患者（与下拉列表规则一致）"""
        stmt = (
            select(Patient)
            .where(Patient.official_subject_sql_filter())
            .order_by(Patient.patient_id)
        )
        return self.db.scalars(stmt).all()

    # ---------- AI 对话 ----------
    def get_room_id_by_patient(self, patient_id: int):
        """通过患者ID获取聊天室ID"""
        stmt = select(ChatRoom.room_id).where(ChatRoom.patient_id == patient_id)
        return self.db.scalar(stmt)

    def get_ai_messages(self, patient_id: int):
        """获取患者在指定时间段内的AI对话记录（患者与AI的消息）"""
        room_id = self.get_room_id_by_patient(patient_id)
        if not room_id:
            return []

        stmt = (
            select(Message)
            .where(
                Message.room_id == room_id,
                func.date(Message.create_time).between(self.start_date, self.end_date),
                Message.sender_type.in_([SenderType.PATIENT, SenderType.AI])
            )
            .order_by(Message.create_time)
        )
        return self.db.scalars(stmt).all()

    # ---------- 糖尿病风险预测 ----------
    def get_diabetes_risks(self, patient_id: int):
        """获取患者在指定时间段内的糖尿病风险预测记录"""
        stmt = (
            select(Case)
            .where(
                Case.user_id == patient_id,
                func.date(Case.test_date).between(self.start_date, self.end_date)
            )
            .order_by(Case.test_date)
        )
        return self.db.scalars(stmt).all()

    # ---------- CKD 肾病风险预测 ----------
    def get_ckd_risks(self, patient_id: int):
        """获取患者在指定时间段内的CKD肾病风险预测记录"""
        stmt = (
            select(PatientCkdRiskRecord)
            .where(
                PatientCkdRiskRecord.patient_id == patient_id,
                func.date(PatientCkdRiskRecord.test_date).between(self.start_date, self.end_date)
            )
            .order_by(PatientCkdRiskRecord.test_date)
        )
        return self.db.scalars(stmt).all()

    # ---------- 食物图片上传 ----------
    def get_food_images(self, patient_id: int):
        """获取患者在指定时间段内的食物图片上传记录"""
        stmt = (
            select(FoodImage)
            .where(
                FoodImage.patient_id == patient_id,
                func.date(FoodImage.upload_timestamp).between(self.start_date, self.end_date)
            )
            .order_by(FoodImage.upload_timestamp)
        )
        return self.db.scalars(stmt).all()

    # ---------- 格式化单个患者的完整报告 ----------
    def format_patient_report(self, patient: Patient) -> str:
        """生成单个患者的完整文本报告"""
        lines = []
        phone=remove_area_code(patient.phone,patient.phone_area_code)
        header = f"========== 患者：{patient.full_name} (编号: {patient.subject_code or '无'}, 电话号码: {phone}) =========="
        lines.append(header)
        lines.append("")

        # 1. AI 对话记录
        lines.append("【AI对话记录】")
        msgs = self.get_ai_messages(patient.patient_id)
        if msgs:
            for m in msgs:
                sender = m.sender_type.value if hasattr(m.sender_type, 'value') else str(m.sender_type)
                content = m.content or ""
                time_str = m.create_time.strftime('%Y-%m-%d %H:%M:%S') if m.create_time else ""
                lines.append(f"{time_str} [{sender}]: {content}")
        else:
            lines.append("  无记录")
        lines.append("")

        # 2. 糖尿病风险预测记录，如果有
        if patient.has_diabetes!="Yes":
            lines.append("【糖尿病风险预测记录】")
            cases = self.get_diabetes_risks(patient.patient_id)
            if cases:
                for c in cases:
                    # 输入参数
                    inputs = (
                        f"HbA1c:{c.hba1c or '-'}, FPG:{c.fasting_glucose or '-'}, "
                        f"HDL:{c.hdl_cholesterol or '-'}, TC:{c.total_cholesterol or '-'}, "
                        f"LDL:{c.ldl_cholesterol or '-'}, Creat:{c.creatinine or '-'}, "
                        f"TG:{c.triglyceride or '-'}, K:{c.potassium or '-'}"
                    )
                    # 输出结果
                    # outputs = (
                    #     f"2年风险:{c.analysis_result_2 or '-'}({c.score_2 or '-'}), "
                    #     f"5年风险:{c.analysis_result or '-'}({c.score or '-'}), "
                    #     f"10年风险:{c.analysis_result_10 or '-'}({c.score_10 or '-'})"
                    # )
                    outputs = (
                        f"2年风险:{c.analysis_result_2 or '-'}, "
                        f"5年风险:{c.analysis_result or '-'}, "
                        f"10年风险:{c.analysis_result_10 or '-'}"
                    )
                    lines.append(f"日期:{c.test_date} | 输入: {inputs} | 输出: {outputs}")
            else:
                lines.append("  无记录")
            lines.append("")
        else:
            # 3. CKD 肾病风险预测记录
            lines.append("【CKD肾病风险预测记录】")
            ckd_list = self.get_ckd_risks(patient.patient_id)
            if ckd_list:
                for c in ckd_list:
                    # 输入参数（按模型字段顺序）
                    inputs = (
                        f"Age:{c.age or '-'}, Sex:{c.sex or '-'}, BMI:{c.bmi or '-'}, WHR:{c.whr or '-'}, "
                        f"HbA1c:{c.hba1c or '-'}, TC:{c.tc or '-'}, LDL:{c.ldl or '-'}, HDL:{c.hdl or '-'}, "
                        f"K:{c.k or '-'}, Creat:{c.creat or '-'}, FPG:{c.fpg or '-'}, "
                        f"SBP:{c.sbp or '-'}, DBP:{c.dbp or '-'}, "
                        f"Insulin:{'是' if c.use_insulin else '否'}, Stroke:{'是' if c.stroke else '否'}, "
                        f"Smoke:{'是' if c.smoke else '否'}, AntiHT:{'是' if c.anti_ht else '否'}, "
                        f"Angio:{'是' if c.angio else '否'}, OtherDM:{'是' if c.other_dm else '否'}, "
                        f"Foot:{'是' if c.foot_prob else '否'}, Eye:{'是' if c.eye_prob else '否'}"
                    )
                    # 输出结果
                    outputs = (
                        f"风险等级:{c.risk_group or '-'}, "
                        f"2年风险概率:{c.risk_2y_percent or '-'}%, "
                        f"5年风险概率:{c.risk_5y_percent or '-'}%, "
                        f"人群百分位:{c.population_percentile or '-'}%"
                    )
                    # 如有AI生成图片URL，附在备注中
                    image_info = f", 图片:{c.image_url}" if c.image_url else ""
                    lines.append(f"日期:{c.test_date} | 输入: {inputs} | 输出: {outputs}{image_info}")
            else:
                lines.append("  无记录")
            lines.append("")

        # 4. 食物图片上传记录
        lines.append("【食物图片上传记录】")
        foods = self.get_food_images(patient.patient_id)
        if foods:
            for f in foods:
                time_str = f.upload_timestamp.strftime('%Y-%m-%d %H:%M:%S') if f.upload_timestamp else ""
                remark = f" 备注:{f.remark}" if f.remark else ""
                lines.append(f"时间:{time_str} | 文件路径:{f.s3_key}{remark}")
        else:
            lines.append("  无记录")

        lines.append("")
        lines.append("=" * 60)
        lines.append("")
        return "\n".join(lines)

    def get_simple_patient_data(self, patient: Patient) -> dict:
        """
        获取单个患者的简化汇总数据（时间段内最近一次记录日期）
        """
        # AI 对话（仅患者发送的消息）
        ai_msgs = self.get_ai_messages(patient.patient_id)
        last_ai_date = max((m.create_time for m in ai_msgs), default=None)

        if patient.has_diabetes!="Yes":
            # 糖尿病风险预测（使用 Case 表）
            cases = self.get_diabetes_risks(patient.patient_id)
            last_risk_date = max((c.update_time for c in cases), default=None)
        else:
            # CKD 风险预测（使用 PatientCkdRiskRecord）
            ckd_records = self.get_ckd_risks(patient.patient_id)
            last_risk_date = max((r.create_time for r in ckd_records), default=None)

        # 食物图片上传
        foods = self.get_food_images(patient.patient_id)
        last_food_date = max((f.upload_timestamp for f in foods), default=None)

        return {
            "patient_id": patient.subject_code, # 这是的
            "full_name": patient.full_name,
            "phone": remove_area_code(patient.phone,patient.phone_area_code),
            "last_ai_date": last_ai_date,
            "last_risk_date": last_risk_date,
            "last_food_date": last_food_date,
        }

    def format_simple_report(self, patient: Patient) -> str:
        """生成单个患者的简化报告（一行制表符分隔）"""
        data = self.get_simple_patient_data(patient)

        # 统一格式化日期：YYYY-MM-DD HH:MM:SS
        def fmt_date(d):
            if d is None:
                return "-"
            # 如果是 datetime 对象
            if isinstance(d, datetime):
                return d.strftime('%Y-%m-%d %H:%M:%S')
            # 如果是 date 对象（不含时间）
            if isinstance(d, date):
                return d.strftime('%Y-%m-%d 00:00:00')
            # 其他情况（如字符串）直接转字符串
            return str(d)

        ai = fmt_date(data["last_ai_date"])
        risk = fmt_date(data["last_risk_date"])
        food = fmt_date(data["last_food_date"])

        # 注意：patient_id 已经改为 subject_code
        return f"{data['patient_id']}\t{data['full_name']}\t{data['phone']}\t{ai}\t{risk}\t{food}"

@router.get("/patient-list", response_model=PatientMonitorListResp)
def get_patient_simple_list(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
    # _ = Depends(admin_required)
):
    """获取患者简易下拉列表，用于监控面板选择患者"""
    offset = (page - 1) * page_size
    stmt_total = (select(func.count(Patient.patient_id)).where(Patient.official_subject_sql_filter()))
    total = db.scalar(stmt_total) or 0

    stmt_items = (
        select(Patient.patient_id, Patient.subject_code, Patient.first_name, Patient.last_name)
        .where(Patient.official_subject_sql_filter())
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

    # -------- 2. 风险预测按天统计（根据 has_diabetes 选择表） --------
    if patient.has_diabetes == "Yes":
        # CKD 肾病风险预测（使用 create_time 作为日期）
        stmt_risk = (
            select(func.date(PatientCkdRiskRecord.create_time).label("stat_date"), func.count(1).label("cnt"))
            .where(PatientCkdRiskRecord.patient_id == patient.patient_id)
            .group_by(func.date(PatientCkdRiskRecord.create_time))
        )
    else:
        # 糖尿病风险预测 (Case)
        stmt_risk = (
            select(func.date(Case.create_time).label("stat_date"), func.count(1).label("cnt"))
            .where(Case.user_id == patient.patient_id)
            .group_by(func.date(Case.create_time))
        )
    risk_rows = db.execute(stmt_risk).all()
    predict_date_set = {row.stat_date for row in risk_rows if row.stat_date}
    predict_count_dict = {row.stat_date: row.cnt for row in risk_rows}

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

@router.post("/export")
def export_patient_data(
    req: ExportRequest,
    db: Session = Depends(get_db),
    # _ = Depends(admin_required)
):
    """
    导出患者数据（AI对话、风险预测、食物图片）
    支持两种模式：
    - combined: 所有患者合并到一个txt文件
    - separate: 每个患者单独txt，打包成zip下载
    """
    # 校验日期
    if req.start_date > req.end_date:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")

    service = PatientExportService(db, req.start_date, req.end_date)
    patients = service.get_patients()

    # 如果时间段内没有患者（或所有患者无数据），返回空提示
    if not patients:
        empty_msg = f"所选时间段 {req.start_date} 至 {req.end_date} 内无任何正式患者记录。"
        return Response(
            content=empty_msg,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename=empty_export.txt"}
        )

    # ---------- 合并模式 ----------
    if req.mode == "combined":
        full_content = ""
        for p in patients:
            report = service.format_patient_report(p)
            # 如果报告只有表头和无记录，可以跳过（保留也行，这里保留显示无记录）
            full_content += report

        if not full_content.strip():
            full_content = f"所选时间段 {req.start_date} 至 {req.end_date} 内无任何患者活动记录。"

        filename = f"combined_export_{req.start_date}_{req.end_date}.txt"
        return Response(
            content=full_content,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    # ---------- 分离模式（打包ZIP） ----------
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        has_content = False
        for p in patients:
            report = service.format_patient_report(p)
            # 只保存有实际记录的（可根据需求调整：可保留全部，这里保留有内容的）
            # 简单判断：如果包含至少一条非"无记录"的内容（排除表头和空行），即为有数据
            lines = report.splitlines()
            has_data = any("无记录" not in line and "======" not in line and line.strip() != "" for line in lines)
            if has_data:
                # 文件名：患者全名 + 患者正式编号 + 使用记录.txt
                safe_name = f"{p.full_name}_{p.subject_code}_使用记录.txt"
                zip_file.writestr(safe_name, report)
                has_content = True

        if not has_content:
            zip_file.writestr("提示.txt", f"所选时间段 {req.start_date} 至 {req.end_date} 内无任何患者活动记录。")

    zip_buffer.seek(0)
    zip_filename = f"patient_records_{req.start_date}_{req.end_date}.zip"
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={zip_filename}"}
    )

from urllib.parse import quote
@router.get("/download-day-image-zip")
def download_day_zip(
    target_date: date = Query(..., description="目标日期 YYYY‑MM‑DD"),
    patient_id: int | None = Query(None, description="指定患者ID，不传则导出该日全部患者图片"),
    db: Session = Depends(get_db)
):
    day_start = datetime.combine(target_date, time.min)
    day_end = datetime.combine(target_date, time.max)

    # ✅ join同时取出 subject_code + remark
    q = (
        db.query(FoodImage, Patient.subject_code, FoodImage.remark)
        .join(Patient, FoodImage.patient_id == Patient.patient_id)
        .filter(
            FoodImage.upload_timestamp >= day_start,
            FoodImage.upload_timestamp <= day_end
        )
    )
    if patient_id is not None:
        q = q.filter(FoodImage.patient_id == patient_id)

    records = q.limit(20).all()
    if not records:
        return Response(status_code=204)

    mem_zip = io.BytesIO()
    remark_lines = []  # 收集备注文本行

    with zipfile.ZipFile(mem_zip, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for fi, subject_code, remark in records:
            pid = fi.patient_id
            s3_key = fi.s3_key
            file_name = s3_key.split("/")[-1]

            # 📝构建remark.txt行：文件名:备注，remark为None就为空字符串
            remark_content = remark if remark is not None else ""
            line = f"{file_name}:{remark_content}"
            remark_lines.append(line)

            # 🆕优先使用subject_code，为空兜底 patient_xxx
            if subject_code and subject_code.strip():
                outer_folder = subject_code.strip()
            else:
                outer_folder = f"patient_{pid}"

            zip_inner_path = f"{outer_folder}/{file_name}"
            try:
                img_bytes = s3_service.get_bytes(s3_key)
                zf.writestr(zip_inner_path, img_bytes)
                del img_bytes
            except Exception as e:
                print(f"[WARN] 跳过图片 s3_key={s3_key}, err={str(e)}")

        # ✅ 将 remark.txt 写入zip根目录
        remark_text = "\n".join(remark_lines)
        zf.writestr("remark.txt", remark_text.encode("utf‑8"))

    mem_zip.seek(0)
    zip_filename = f"food_images_{target_date}.zip"

    # RFC5987 编码文件名，处理中文
    encoded_filename = quote(zip_filename, encoding="utf-8")

    return StreamingResponse(
        mem_zip,
        media_type="application/zip",
        headers={
            # ！！！重点：这里是标准短横线 "-"，不要复制粘贴带‑的字符串！！！
            "Content-Disposition": f'attachment; filename*=utf-8\'\'{encoded_filename}'
        }
    )

@router.post("/export-simple")
def export_simple_patient_data(
    req: ExportRequest,  # 复用相同的 Schema（start_date, end_date, mode）
    db: Session = Depends(get_db),
):
    """
    简化导出：每个患者一行，包含ID、姓名、电话、最近使用AI日期、最近风险预测日期、最近食物上传日期。
    支持合并为一个txt（制表符分隔，可直接粘贴到Excel）或按患者分开打包zip。
    """
    if req.start_date > req.end_date:
        raise HTTPException(status_code=400, detail="开始日期不能晚于结束日期")

    service = PatientExportService(db, req.start_date, req.end_date)
    patients = service.get_patients()

    if not patients:
        empty_msg = f"所选时间段 {req.start_date} 至 {req.end_date} 内无任何正式患者记录。"
        return Response(
            content=empty_msg,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": "attachment; filename=empty_export.txt"}
        )

    # ---------- 合并模式 ----------
    if req.mode == "combined":
        # 生成表头
        header = "ID\t姓名\t电话\t上次AI对话日期\t上次风险预测日期\t上次食物上传日期"
        lines = [header]
        for p in patients:
            line = service.format_simple_report(p)
            lines.append(line)
        content = "\n".join(lines)

        filename = f"simple_combined_{req.start_date}_{req.end_date}.txt"
        return Response(
            content=content,
            media_type="text/plain; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    # ---------- 分离模式 ----------
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        has_content = False
        for p in patients:
            line = service.format_simple_report(p)
            # 检查是否有任何日期不是 '-'（即至少有一条记录）
            parts = line.split("\t")
            # parts: [id, name, phone, ai, risk, food]
            if any(part not in ["-", ""] for part in parts[3:]):
                # 有记录才保存
                safe_name = f"{p.full_name}_{p.subject_code}_简化记录.txt"
                zip_file.writestr(safe_name, line)
                has_content = True
        if not has_content:
            zip_file.writestr("提示.txt", f"所选时间段 {req.start_date} 至 {req.end_date} 内无任何患者活动记录。")

    zip_buffer.seek(0)
    zip_filename = f"simple_records_{req.start_date}_{req.end_date}.zip"
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={zip_filename}"}
    )

@router.post("/upload-food-image")
async def admin_upload_food_image(
    patient_id: int = Query(..., description="患者ID"),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    # _ = Depends(admin_required)   # 如果需要权限验证，取消注释并实现
):
    """
    管理员为指定患者上传单张食物图片（时间从文件名中提取）
    """
    # 验证患者存在
    patient = db.get(Patient, patient_id)
    if not patient:
        raise HTTPException(status_code=404, detail="患者不存在")

    # 1. 从文件名中提取时间（格式：YYYY-MM-DD_HH-MM-SS）
    #    如果匹配失败，则使用当前时间
    import re
    match = re.search(r'(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2}-\d{2})', file.filename)
    if match:
        date_part, time_part = match.groups()
        # 将下划线分隔转为空格，替换 '-' 为 ':' 得到 HH:MM:SS
        time_str = time_part.replace('-', ':')
        eat_time = f"{date_part} {time_str}"
    else:
        # 无匹配时使用当前时间（字符串格式）
        from datetime import datetime
        eat_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        file_bytes = await file.read()
        result = await food_service.upload(
            db=db,
            patient_id=patient_id,
            file_bytes=file_bytes,
            filename=file.filename,
            content_type=file.content_type or "application/octet-stream",
            remark=None,          # 无备注
            eat_time=eat_time     # 从文件名提取或当前时间
        )
        return {
            "id": result.id,
            "image_url": result.image_url,
            "upload_timestamp": result.upload_timestamp
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))