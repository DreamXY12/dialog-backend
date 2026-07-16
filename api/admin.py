from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, desc, and_
from typing import List, Optional
from datetime import datetime,timedelta
from pydantic import BaseModel
from sqlalchemy import desc
from sql.common_model import Feedback
import zipfile
# ====================== 新增：第九周问卷管理员接口（多语言PDF + 列表 + 批量打包ZIP） ======================
import re
from io import BytesIO
from fastapi.responses import StreamingResponse
# from fastapi import Query
# from reportlab.lib.pagesizes import A4
# from reportlab.pdfgen import canvas
# from reportlab.pdfbase import pdfmetrics
# from reportlab.pdfbase.cidfonts import UnicodeCIDFont

from urllib.parse import quote

from sql.start import get_db
from sql.people_models import (
    Patient, Nurse, ChatRoom, ConversationSession,
    Message, PatientLoginCode, NurseWorkShift,NurseLoginCode
)
from sql.chat_histoty_curd import get_chat_room_by_uuid

# 导入 Redis 客户端（复用 chat_socket 中的实例）
from api import chat_server
import asyncio

router = APIRouter(prefix="/polyu/dialog/admin", tags=["admin"])

# ---------- 响应模型（可选，用于 swagger 文档） ----------
class OnlineUserResponse(BaseModel):
    user_id: str
    role: str

class NurseInfo(BaseModel):
    nurse_id: int
    phone: str
    full_name: str
    is_online: bool
    patient_count: int
    work_start: Optional[str]
    work_end: Optional[str]
    is_working_now: bool

class PatientInfo(BaseModel):
    patient_id: int
    phone: str
    full_name: str
    is_online: bool
    last_login: Optional[datetime]
    assigned_nurse_id: Optional[int]
    assigned_nurse_name: Optional[str]
    subject_code: Optional[str] = None

class MessageResponse(BaseModel):
    message_uuid: str
    sender_type: str
    sender_id: int
    content: str
    create_time: datetime
    chat_mode: str

class RoomInfo(BaseModel):
    room_uuid: str
    patient_id: int
    nurse_id: Optional[int]
    current_session_uuid: Optional[str]
    current_session_number: Optional[int]
    last_activity_time: Optional[datetime]

# ---------- 辅助函数 ----------
async def get_online_users() -> dict:
    """获取所有在线用户的 user_id -> role 映射"""
    online = {}
    all_users = await chat_server.redis.hgetall(chat_server.REDIS_ONLINE_USER)  # {user_id: sid}
    for uid, _ in all_users.items():
        role = await chat_server.redis.hget(f"chat:user_role", uid)  # 注意：key 与代码一致
        online[uid] = role or "unknown"
    return online

# ---------- 接口实现 ----------
@router.get("/online-users", response_model=List[OnlineUserResponse])
async def list_online_users():
    """获取当前所有在线用户（护士 + 患者）"""
    online = await get_online_users()
    return [{"user_id": uid, "role": role} for uid, role in online.items()]

@router.get("/nurses", response_model=List[NurseInfo])
async def list_nurses(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """分页获取护士列表，含在线状态、患者数量、工作时段"""
    offset = (page - 1) * size
    nurses = db.query(Nurse).offset(offset).limit(size).all()
    online_map = await get_online_users()

    result = []
    for nurse in nurses:
        nurse_id = str(nurse.nurse_id)
        # 患者数量
        patient_count = db.query(Patient).filter(Patient.assigned_nurse_id == nurse.nurse_id).count()
        # 工作时段（取当天有效的一条，简化：取第一条）
        shift = db.query(NurseWorkShift).filter(
            NurseWorkShift.nurse_id == nurse.nurse_id,
            NurseWorkShift.work_date == datetime.now().date()
        ).first()
        work_start = shift.work_start_time.strftime("%H:%M") if shift and shift.work_start_time else None
        work_end = shift.work_end_time.strftime("%H:%M") if shift and shift.work_end_time else None
        # 是否在值班（假设 working_hours 字段）
        is_working_now = shift.is_working_hours if shift else False

        result.append({
            "nurse_id": nurse.nurse_id,
            "phone": nurse.phone,
            "full_name": nurse.full_name,
            "is_online": nurse_id in online_map,
            "patient_count": patient_count,
            "work_start": work_start,
            "work_end": work_end,
            "is_working_now": is_working_now,
        })
    return result

@router.get("/patients", response_model=List[PatientInfo])
async def list_patients(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """分页获取患者列表，含在线状态、最后登录时间、负责护士"""
    offset = (page - 1) * size
    patients = db.query(Patient).offset(offset).limit(size).all()
    online_map = await get_online_users()
    # 预查询最后登录时间（从 PatientLoginCode）
    login_codes = {
        pc.patient_id: pc.update_time
        for pc in db.query(PatientLoginCode).filter(PatientLoginCode.patient_id.in_([p.patient_id for p in patients])).all()
    }

    result = []
    for patient in patients:
        pid = str(patient.patient_id)
        nurse_name = None
        if patient.assigned_nurse_id:
            nurse = db.query(Nurse).filter(Nurse.nurse_id == patient.assigned_nurse_id).first()
            nurse_name = nurse.full_name if nurse else None

        result.append({
            "patient_id": patient.patient_id,
            "phone": patient.phone,
            "full_name": patient.full_name,
            "is_online": pid in online_map,
            "last_login": login_codes.get(patient.patient_id),
            "assigned_nurse_id": patient.assigned_nurse_id,
            "assigned_nurse_name": nurse_name,
            "subject_code": patient.subject_code,
        })
    return result

@router.get("/patients/{patient_id}/messages", response_model=List[MessageResponse])
async def get_patient_messages(
    patient_id: int,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """分页获取指定患者的聊天消息（按时间倒序）"""
    # 先找到该患者的所有房间
    rooms = db.query(ChatRoom).filter(ChatRoom.patient_id == patient_id).all()
    if not rooms:
        return []
    room_ids = [r.room_id for r in rooms]
    # 获取消息
    offset = (page - 1) * size
    messages = (
        db.query(Message)
        .filter(Message.room_id.in_(room_ids))
        .order_by(desc(Message.create_time))
        .offset(offset)
        .limit(size)
        .all()
    )
    return [
        {
            "message_uuid": m.message_uuid,
            "sender_type": m.sender_type,
            "sender_id": m.sender_id,
            "content": m.content,
            "create_time": m.create_time,
            "chat_mode": m.chat_mode,
        }
        for m in messages
    ]

@router.get("/rooms", response_model=List[RoomInfo])
async def list_rooms(
    db: Session = Depends(get_db)
):
    """列出所有聊天房间，含当前活跃会话信息"""
    rooms = db.query(ChatRoom).all()
    result = []
    for room in rooms:
        # 获取当前活跃会话（如果有）
        active_session = (
            db.query(ConversationSession)
            .filter(
                ConversationSession.room_id == room.room_id,
                ConversationSession.session_status == "active"
            )
            .order_by(desc(ConversationSession.start_time))
            .first()
        )
        result.append({
            "room_uuid": room.room_uuid,
            "patient_id": room.patient_id,
            "nurse_id": room.nurse_id,
            "current_session_uuid": active_session.session_uuid if active_session else None,
            "current_session_number": active_session.session_number if active_session else None,
            "last_activity_time": room.last_activity_time,
        })
    return result

@router.get("/nurses/{nurse_id}/patients", response_model=List[PatientInfo])
async def get_nurse_patients(
    nurse_id: int,
    db: Session = Depends(get_db)
):
    """获取指定护士负责的所有患者（含在线状态）"""
    patients = db.query(Patient).filter(Patient.assigned_nurse_id == nurse_id).all()
    online_map = await get_online_users()
    login_codes = {
        pc.patient_id: pc.update_time
        for pc in db.query(PatientLoginCode).filter(PatientLoginCode.patient_id.in_([p.patient_id for p in patients])).all()
    }
    result = []
    for p in patients:
        result.append({
            "patient_id": p.patient_id,
            "phone": p.phone,
            "full_name": p.full_name,
            "is_online": str(p.patient_id) in online_map,
            "last_login": login_codes.get(p.patient_id),
            "assigned_nurse_id": p.assigned_nurse_id,
            "assigned_nurse_name": None,  # 可忽略或查询
        })
    return result

@router.get("/feedbacks", response_model=dict)
async def get_feedbacks(
    page: int = Query(1, ge=1),
    size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """
    获取用户反馈列表（分页）
    - 按创建时间倒序
    - 返回总条数、当前页数据
    """
    offset = (page - 1) * size
    total = db.query(Feedback).count()
    feedbacks = (
        db.query(Feedback)
        .order_by(desc(Feedback.create_time))
        .offset(offset)
        .limit(size)
        .all()
    )
    return {
        "total": total,
        "page": page,
        "size": size,
        "data": [
            {
                "id": f.id,
                "rating": f.rating,
                "type": f.type,
                "content": f.content,
                "attachments": f.attachments,      # 原样返回 JSON 字符串
                "role": f.role,
                "phone": f.phone,
                "ai_context": f.ai_context,
                "create_time": f.create_time.isoformat() if f.create_time else None,
            }
            for f in feedbacks
        ]
    }


@router.get("/feedbacks/{feedback_id}/user")
async def get_feedback_user(
        feedback_id: int,
        db: Session = Depends(get_db)
):
    """
    根据反馈ID获取对应的用户信息（姓名、电话、角色）
    仅在管理员点击查看详情时调用
    """
    feedback = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="反馈不存在")

    name = None
    if feedback.role == "nurse":
        nurse = db.query(Nurse).filter(Nurse.phone == feedback.phone).first()
        if nurse:
            name = nurse.full_name
    elif feedback.role == "patient":
        patient = db.query(Patient).filter(Patient.phone == feedback.phone).first()
        if patient:
            name = patient.full_name

    return {
        "phone": feedback.phone,
        "role": feedback.role,
        "name": name
    }

from sql.people_models import Patient, PatientLoginCode

@router.get("/inactive-patients")
async def get_inactive_patients(
    days: int = Query(3, ge=1, le=30, description="超过多少天未登录"),
    db: Session = Depends(get_db)
):
    """
    获取超过指定天数未登录（基于 patient_login_code.update_time）的患者列表
    返回姓名、电话、最后登录时间
    """
    now_tz = datetime.now()
    cutoff_time = now_tz - timedelta(days=days)

    # 关联查询：patient_login_code 和 patient
    results = db.query(
        Patient.patient_id,
        Patient.first_name,
        Patient.last_name,
        Patient.phone,
        PatientLoginCode.update_time
    ).join(
        PatientLoginCode,
        Patient.patient_id == PatientLoginCode.patient_id
    ).filter(
        PatientLoginCode.update_time < cutoff_time
    ).order_by(
        desc(PatientLoginCode.update_time)
    ).all()

    data = []
    for row in results:
        data.append({
            "patient_id": row.patient_id,
            "full_name": f"{row.first_name} {row.last_name}".strip(),
            "phone": row.phone,
            "last_active": row.update_time.isoformat() if row.update_time else None,
        })

    return {"total": len(data), "data": data}

# 1. 查找患者（按完整手机号）
@router.get("/patients/lookup")
async def lookup_patient(phone: str = Query(..., description="完整手机号，如+85212345678"),
                         db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.phone == phone).first()
    if not patient:
        raise HTTPException(status_code=404, detail="未找到该患者")
    return {
        "patient_id": patient.patient_id,
        "phone": patient.phone,
        "full_name": patient.full_name,
    }

# 2. 删除患者
@router.delete("/patients/{patient_id}")
async def delete_patient(patient_id: int, db: Session = Depends(get_db)):
    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="患者不存在")
    db.delete(patient)
    db.commit()
    return {"message": f"患者 {patient.full_name} 已删除"}

# 3. 查找护士
@router.get("/nurses/lookup")
async def lookup_nurse(phone: str = Query(..., description="完整手机号，如+85212345678"),
                       db: Session = Depends(get_db)):
    nurse = db.query(Nurse).filter(Nurse.phone == phone).first()
    if not nurse:
        raise HTTPException(status_code=404, detail="未找到该护士")
    return {
        "nurse_id": nurse.nurse_id,
        "phone": nurse.phone,
        "full_name": nurse.full_name,
        "account_type": nurse.account_type,
    }

# 4. 删除护士
@router.delete("/nurses/{nurse_id}")
async def delete_nurse(nurse_id: int, db: Session = Depends(get_db)):
    nurse = db.query(Nurse).filter(Nurse.nurse_id == nurse_id).first()
    if not nurse:
        raise HTTPException(status_code=404, detail="护士不存在")
    db.delete(nurse)
    db.commit()
    return {"message": f"护士 {nurse.full_name} 已删除"}

# 5. 获取未使用的患者登录码（patient_id 为 NULL）
@router.get("/unused-patient-codes")
async def get_unused_patient_codes(db: Session = Depends(get_db)):
    codes = db.query(PatientLoginCode).filter(PatientLoginCode.patient_id == None).all()
    return [
        {
            "id": c.id,
            "login_code_hash": c.login_code_hash,
            "is_active": c.is_active,
            "create_time": c.create_time.isoformat() if c.create_time else None,
        }
        for c in codes
    ]

# 6. 删除患者登录码
@router.delete("/patient-codes/{code_id}")
async def delete_patient_code(code_id: int, db: Session = Depends(get_db)):
    code = db.query(PatientLoginCode).filter(PatientLoginCode.id == code_id).first()
    if not code:
        raise HTTPException(status_code=404, detail="登录码不存在")
    db.delete(code)
    db.commit()
    return {"message": "患者登录码已删除"}

# 7. 获取未使用的护士登录码（nurse_id 为 NULL）
@router.get("/unused-nurse-codes")
async def get_unused_nurse_codes(db: Session = Depends(get_db)):
    codes = db.query(NurseLoginCode).filter(NurseLoginCode.nurse_id == None).all()
    return [
        {
            "id": c.id,
            "login_code_hash": c.login_code_hash,
            "is_active": c.is_active,
            "create_time": c.create_time.isoformat() if c.create_time else None,
        }
        for c in codes
    ]

# 8. 删除护士登录码
@router.delete("/nurse-codes/{code_id}")
async def delete_nurse_code(code_id: int, db: Session = Depends(get_db)):
    code = db.query(NurseLoginCode).filter(NurseLoginCode.id == code_id).first()
    if not code:
        raise HTTPException(status_code=404, detail="登录码不存在")
    db.delete(code)
    db.commit()
    return {"message": "护士登录码已删除"}




# 注册内置中文字体（无需额外文件，服务器可用）
# pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
FONT_CN = 'STSong-Light'

# 问卷模型导入
from sql.people_models import (
    PatientWeek9Questionnaire,
    QuestionnaireDMAnswer,
    QuestionnaireHTAnswer
)

# ---------------- 多语言文案配置（预留简体、繁体、英文，按需扩展） ----------------
PDF_LANG_TEXT = {
    "zh-CN": {
        "title": "第九周健康整合问卷",
        "patient_name": "患者姓名",
        "phone": "联系电话",
        "submit_time": "提交时间",
        "base_health_title": "一、基础健康评估信息",
        "assessment_date": "评估日期",
        "body_weight": "体重(kg)",
        "cardio_exercise": "每周有氧运动",
        "muscle_exercise": "每周肌力训练",
        "alcohol_use": "饮酒习惯",
        "smoking": "吸烟状态",
        "healthy_diet": "健康饮食习惯",
        "bp_monitor": "血压自我监测",
        "bg_monitor": "血糖自我监测",
        "quit_smoking_attempt": "尝试戒烟",
        "weight_manage_attempt": "尝试体重管理",
        "dm_quiz_title": "二、糖尿病知识问卷作答",
        "ht_quiz_title": "三、高血压知识问卷作答",
        "question_text": "题目",
        "answer_text": "答案",
        "empty_text": "无",
        "unanswered_text": "未作答"
    },
    "zh-HK": {
        "title": "第九週健康整合問卷",
        "patient_name": "患者姓名",
        "phone": "聯繫電話",
        "submit_time": "提交時間",
        "base_health_title": "一、基礎健康評估資訊",
        "assessment_date": "評估日期",
        "body_weight": "體重(kg)",
        "cardio_exercise": "每週有氧運動",
        "muscle_exercise": "每週肌力訓練",
        "alcohol_use": "飲酒習慣",
        "smoking": "吸煙狀態",
        "healthy_diet": "健康飲食習慣",
        "bp_monitor": "血壓自我監測",
        "bg_monitor": "血糖自我監測",
        "quit_smoking_attempt": "嘗試戒煙",
        "weight_manage_attempt": "嘗試體重管理",
        "dm_quiz_title": "二、糖尿病知識問卷作答",
        "ht_quiz_title": "三、高血壓知識問卷作答",
        "question_text": "題目",
        "answer_text": "答案",
        "empty_text": "無",
        "unanswered_text": "未作答"
    },
    "en": {
        "title": "Week 9 Health Integrated Questionnaire",
        "patient_name": "Patient Name",
        "phone": "Phone Number",
        "submit_time": "Submit Time",
        "base_health_title": "1. Basic Health Assessment Information",
        "assessment_date": "Assessment Date",
        "body_weight": "Body Weight(kg)",
        "cardio_exercise": "Weekly Cardio Exercise",
        "muscle_exercise": "Weekly Muscle Strengthening",
        "alcohol_use": "Alcohol Use Habit",
        "smoking": "Smoking Status",
        "healthy_diet": "Healthy Diet Habit",
        "bp_monitor": "Blood Pressure Self-monitoring",
        "bg_monitor": "Blood Glucose Self-monitoring",
        "quit_smoking_attempt": "Attempt to Quit Smoking",
        "weight_manage_attempt": "Attempt to Manage Weight",
        "dm_quiz_title": "2. Diabetes Knowledge Questionnaire Answers",
        "ht_quiz_title": "3. Hypertension Knowledge Questionnaire Answers",
        "question_text": "Question",
        "answer_text": "Answer",
        "empty_text": "None",
        "unanswered_text": "Unanswered"
    }
}


# ---------------- Pydantic 响应模型 ----------------
class AdminWeek9QuestionnaireItem(BaseModel):
    questionnaireId: int
    patientId: int
    fullName: str
    phoneRaw: str
    phonePure: str
    submitTime: str


class AdminWeek9ListResp(BaseModel):
    total: int
    page: int
    pageSize: int
    list: List[AdminWeek9QuestionnaireItem]


# ---------------- 工具函数：清洗手机号去除区号 ----------------
def clean_phone_number(phone: str) -> str:
    for prefix in ["+86", "+852"]:
        if phone.startswith(prefix):
            return phone[len(prefix):].strip()
    return phone   # 不匹配则原样返回


# ---------------- 工具函数：多语言生成单患者问卷PDF字节流 ----------------
# def generate_questionnaire_pdf(
#         patient_name: str,
#         phone: str,
#         submit_time: str,
#         detail: dict,
#         lang: str = "zh-HK"
# ) -> BytesIO:
#     """根据传入语言生成对应语种PDF"""
#     # 兼容非法语言，默认繁体中文
#     if lang not in PDF_LANG_TEXT:
#         lang = "zh-HK"
#     text = PDF_LANG_TEXT[lang]
#
#     buf = BytesIO()
#     c = canvas.Canvas(buf, pagesize=A4)
#     # 英文使用默认字体，中文使用思源黑体
#     c.setFont(FONT_CN if lang != "en" else "Helvetica", 11)
#     width, height = A4
#
#     # 标题
#     c.setFont(FONT_CN if lang != "en" else "Helvetica", 16)
#     c.drawCentredString(width / 2, height - 50, text["title"])
#     c.setFont(FONT_CN if lang != "en" else "Helvetica", 11)
#
#     y = height - 80
#     c.drawString(50, y, f"{text['patient_name']}：{patient_name}")
#     y -= 25
#     c.drawString(50, y, f"{text['phone']}：{phone}")
#     y -= 25
#     c.drawString(50, y, f"{text['submit_time']}：{submit_time}")
#     y -= 40
#
#     # 基础健康信息
#     c.setFont(FONT_CN if lang != "en" else "Helvetica", 13)
#     c.drawString(50, y, text["base_health_title"])
#     c.setFont(FONT_CN if lang != "en" else "Helvetica", 11)
#     y -= 30
#
#     base = detail["baseHealth"]
#     items = [
#         (text["assessment_date"], base["assessmentDate"]),
#         (text["body_weight"], str(base["bodyWeight"]) if base["bodyWeight"] else text["empty_text"]),
#         (text["cardio_exercise"], base["cardioExercisePerWeek"] or text["empty_text"]),
#         (text["muscle_exercise"], base["muscleStrengthenPerWeek"] or text["empty_text"]),
#         (text["alcohol_use"], base["alcoholUse"] or text["empty_text"]),
#         (text["smoking"], base["smoking"] or text["empty_text"]),
#         (text["healthy_diet"], base["healthyDietHabit"] or text["empty_text"]),
#         (text["bp_monitor"], base["selfMonitorBP"] or text["empty_text"]),
#         (text["bg_monitor"], base["selfMonitorBG"] or text["empty_text"]),
#         (text["quit_smoking_attempt"], base["attemptQuitSmoking"] or text["empty_text"]),
#         (text["weight_manage_attempt"], base["attemptManageWeight"] or text["empty_text"]),
#     ]
#
#     for k, v in items:
#         c.drawString(60, y, f"{k}：{v}")
#         y -= 22
#         if y < 60:
#             c.showPage()
#             c.setFont(FONT_CN if lang != "en" else "Helvetica", 11)
#             y = height - 50
#
#     # 糖尿病题目
#     y -= 20
#     c.setFont(FONT_CN if lang != "en" else "Helvetica", 13)
#     c.drawString(50, y, text["dm_quiz_title"])
#     c.setFont(FONT_CN if lang != "en" else "Helvetica", 11)
#     y -= 30
#     for idx, item in enumerate(detail["dmQuiz"]):
#         ans = item["selectedAnswer"] or text["unanswered_text"]
#         c.drawString(60, y, f"{idx + 1}. {text['question_text']}({item['questionId']}) {text['answer_text']}：{ans}")
#         y -= 22
#         if y < 60:
#             c.showPage()
#             c.setFont(FONT_CN if lang != "en" else "Helvetica", 11)
#             y = height - 50
#
#     # 高血压题目
#     y -= 20
#     c.setFont(FONT_CN if lang != "en" else "Helvetica", 13)
#     c.drawString(50, y, text["ht_quiz_title"])
#     c.setFont(FONT_CN if lang != "en" else "Helvetica", 11)
#     y -= 30
#     for idx, item in enumerate(detail["htQuiz"]):
#         ans = item["selectedAnswer"] or text["unanswered_text"]
#         c.drawString(60, y, f"{idx + 1}. {text['question_text']}({item['questionId']}) {text['answer_text']}：{ans}")
#         y -= 22
#         if y < 60:
#             c.showPage()
#             c.setFont(FONT_CN if lang != "en" else "Helvetica", 11)
#             y = height - 50
#
#     c.save()
#     buf.seek(0)
#     return buf


# ---------------- 1. 管理员分页查询所有已填报问卷列表（无语言影响） ----------------
@router.get("/week9-questionnaires", response_model=AdminWeek9ListResp)
def admin_get_all_week9_questionnaires(
        page: int = Query(1, ge=1),
        pageSize: int = Query(10, ge=1, le=100),
        db: Session = Depends(get_db)
):
    offset = (page - 1) * pageSize

    from sqlalchemy import select, func
    # 正确select联查
    stmt = select(
        PatientWeek9Questionnaire.id,
        PatientWeek9Questionnaire.patient_id,
        PatientWeek9Questionnaire.create_time,
        Patient.first_name,
        Patient.last_name,
        Patient.phone
    ).join(
        Patient,
        Patient.patient_id == PatientWeek9Questionnaire.patient_id
    ).order_by(
        PatientWeek9Questionnaire.create_time.desc()
    )

    # 分页数据执行
    rows = db.execute(stmt.offset(offset).limit(pageSize)).all()

    # 单独统计总数
    count_stmt = select(func.count(PatientWeek9Questionnaire.id)).join(
        Patient,
        Patient.patient_id == PatientWeek9Questionnaire.patient_id
    )
    total = db.execute(count_stmt).scalar() or 0

    list_data = []
    for row in rows:
        pure_phone = clean_phone_number(row.phone)
        list_data.append(AdminWeek9QuestionnaireItem(
            questionnaireId=row.id,
            patientId=row.patient_id,
            fullName=row.first_name+row.last_name,
            phoneRaw=row.phone,
            phonePure=pure_phone,
            submitTime=row.create_time.strftime("%Y-%m-%d %H:%M:%S") if row.create_time else ""
        ))

    return AdminWeek9ListResp(
        total=total,
        page=page,
        pageSize=pageSize,
        list=list_data
    )



# ---------------- 2. 管理员批量导出全部问卷（多语言PDF + ZIP打包下载） ----------------
# @router.get("/week9-questionnaires/export-all")
# def admin_export_all_week9_questionnaires(
#         lang: Optional[str] = Query("zh-HK", description="语言参数：zh-CN(简体)、zh-HK(繁体)、en(英文)"),
#         db: Session = Depends(get_db)
# ):
#     """
#     批量导出全部第九周问卷为多语言PDF并打包ZIP
#     自动分批读取所有数据、内存生成、无落地文件
#     """
#     # 1. 查出所有问卷ID+患者信息
#     all_rows = (
#         db.query(
#             PatientWeek9Questionnaire.id,
#             PatientWeek9Questionnaire.patient_id,
#             PatientWeek9Questionnaire.create_time,
#             Patient.full_name,
#             Patient.phone
#         )
#         .join(Patient, Patient.patient_id == PatientWeek9Questionnaire.patient_id)
#         .order_by(PatientWeek9Questionnaire.create_time.desc())
#         .all()
#     )
#
#     if not all_rows:
#         raise HTTPException(status_code=404, detail="暂无问卷数据可导出")
#
#     # 2. 内存zip包
#     zip_buffer = BytesIO()
#     with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
#         for row in all_rows:
#             q_id = row.id
#             p_id = row.patient_id
#             p_name = row.full_name
#             p_phone = clean_phone_number(row.phone)
#             submit_time = row.create_time.strftime("%Y-%m-%d %H:%M:%S") if row.create_time else ""
#
#             # 查询单条问卷详情
#             q_main = db.query(PatientWeek9Questionnaire).filter(PatientWeek9Questionnaire.id == q_id).first()
#             dm_list = db.query(QuestionnaireDMAnswer).filter(QuestionnaireDMAnswer.questionnaire_id == q_id).all()
#             ht_list = db.query(QuestionnaireHTAnswer).filter(QuestionnaireHTAnswer.questionnaire_id == q_id).all()
#
#             detail_dict = {
#                 "baseHealth": {
#                     "assessmentDate": q_main.assessment_date,
#                     "bodyWeight": q_main.body_weight,
#                     "cardioExercisePerWeek": q_main.cardio_exercise_per_week,
#                     "muscleStrengthenPerWeek": q_main.muscle_strengthen_per_week,
#                     "alcoholUse": q_main.alcohol_use,
#                     "smoking": q_main.smoking,
#                     "healthyDietHabit": q_main.healthy_diet_habit,
#                     "selfMonitorBP": q_main.self_monitor_bp,
#                     "selfMonitorBG": q_main.self_monitor_bg,
#                     "attemptQuitSmoking": q_main.attempt_quit_smoking,
#                     "attemptManageWeight": q_main.attempt_manage_weight,
#                 },
#                 "dmQuiz": [{"questionId": d.question_id, "selectedAnswer": d.answer} for d in dm_list],
#                 "htQuiz": [{"questionId": h.question_id, "selectedAnswer": h.answer} for h in ht_list]
#             }
#
#             # 生成对应语言PDF
#             pdf_buf = generate_questionnaire_pdf(p_name, p_phone, submit_time, detail_dict, lang)
#             zipf.writestr(f"{p_name}_{p_id}_问卷.pdf", pdf_buf.getvalue())
#
#     zip_buffer.seek(0)
#
#     return StreamingResponse(
#         zip_buffer,
#         media_type="application/zip",
#         headers={"Content-Disposition": "attachment; filename=问卷全部导出.zip"}
#     )


# ---------------- 3. 新增：单问卷多语言PDF导出接口（弹窗单条下载使用） ----------------
# @router.get("/week9-questionnaires/{q_id}/export-single")
# def export_single_questionnaire(
#         q_id: int,
#         lang: Optional[str] = Query("zh-HK", description="语言参数：zh-CN(简体)、zh-HK(繁体)、en(英文)"),
#         db: Session = Depends(get_db)
# ):
#     """
#     单条问卷PDF导出（支持多语言）
#     用于前端弹窗【单条下载PDF】功能
#     """
#     # 查询问卷主数据
#     q_main = db.query(PatientWeek9Questionnaire).filter(PatientWeek9Questionnaire.id == q_id).first()
#     if not q_main:
#         raise HTTPException(status_code=404, detail="问卷不存在")
#
#     # 关联患者信息
#     patient = db.query(Patient).filter(Patient.patient_id == q_main.patient_id).first()
#     if not patient:
#         raise HTTPException(status_code=404, detail="患者信息不存在")
#
#     # 查询答题明细
#     dm_list = db.query(QuestionnaireDMAnswer).filter(QuestionnaireDMAnswer.questionnaire_id == q_id).all()
#     ht_list = db.query(QuestionnaireHTAnswer).filter(QuestionnaireHTAnswer.questionnaire_id == q_id).all()
#
#     # 数据整理
#     p_name = patient.full_name
#     p_phone = clean_phone_number(patient.phone)
#     submit_time = q_main.create_time.strftime("%Y-%m-%d %H:%M:%S") if q_main.create_time else ""
#
#     detail_dict = {
#         "baseHealth": {
#             "assessmentDate": q_main.assessment_date,
#             "bodyWeight": q_main.body_weight,
#             "cardioExercisePerWeek": q_main.cardio_exercise_per_week,
#             "muscleStrengthenPerWeek": q_main.muscle_strengthen_per_week,
#             "alcoholUse": q_main.alcohol_use,
#             "smoking": q_main.smoking,
#             "healthyDietHabit": q_main.healthy_diet_habit,
#             "selfMonitorBP": q_main.self_monitor_bp,
#             "selfMonitorBG": q_main.self_monitor_bg,
#             "attemptQuitSmoking": q_main.attempt_quit_smoking,
#             "attemptManageWeight": q_main.attempt_manage_weight,
#         },
#         "dmQuiz": [{"questionId": d.question_id, "selectedAnswer": d.answer} for d in dm_list],
#         "htQuiz": [{"questionId": h.question_id, "selectedAnswer": h.answer} for h in ht_list]
#     }
#
#     # 生成对应语言PDF
#     pdf_buf = generate_questionnaire_pdf(p_name, p_phone, submit_time, detail_dict, lang)
#
#     return StreamingResponse(
#         pdf_buf,
#         media_type="application/pdf",
#         headers={"Content-Disposition": f"attachment; filename={p_name}_第九周问卷.pdf"}
#     )


QUIZ_FULL_TEXT = {
    # 简体中文
    "zh-CN": {
        # 糖尿病知识评估（原版5题）
        "q_dm_1": {
            "question": "以下哪个不是控制糖尿病的重要指标？",
            "options": {
                "a": "糖化血红蛋白(HbA1c)",
                "b": "血压",
                "c": "胆固醇",
                "d": "肝功能",
                "e": "不知道"
            }
        },
        "q_dm_2": {
            "question": "如果服食糖尿药后，怀疑出现副作用时(例如头晕、手震)，该怎么办？",
            "options": {
                "a": "立即改服旧药",
                "b": "密切留意血糖的状况，并及早寻求医护人员的意见",
                "c": "自行减少剂量",
                "d": "停服糖尿药一次",
                "e": "不知道"
            }
        },
        "q_dm_3": {
            "question": "若想透过带氧运动(例如步行、行山、踏单车)帮助控制糖尿病，病人应：",
            "options": {
                "a": "每星期一天运动，合共约60分钟",
                "b": "每星期两天运动，合共约60分钟",
                "c": "每星期三天运动，每次约30分钟",
                "d": "每星期五天运动，每次约30分钟",
                "e": "不知道"
            }
        },
        "q_dm_4": {
            "question": "自我管理糖尿病，其中最有效的方法是：",
            "options": {
                "a": "立即为自己订立目标，改变生活习惯",
                "b": "服用坊间流传的偏方来降血糖",
                "c": "自行调校药物剂量",
                "d": "谢绝社交应酬",
                "e": "不知道"
            }
        },
        "q_dm_5": {
            "question": "糖尿病患者可以进食米饭吗？",
            "options": {
                "a": "可以随意进食",
                "b": "进食时要计算份量",
                "c": "要避免进食",
                "d": "改吃粥更佳",
                "e": "不知道"
            }
        },
        # 高血压知识评估（原版5题）
        "q_ht_1": {
            "question": "80岁以下的高血压患者，血压应控制于：",
            "options": {
                "a": "高于 160 / 100mmHg",
                "b": "低于 140 / 90mmHg",
                "c": "低于 120 / 70mmHg",
                "d": "低于 100 / 70mmHg",
                "e": "不知道"
            }
        },
        "q_ht_2": {
            "question": "如果服食血压药后，怀疑出现副作用时(例如头晕、咳嗽)，该怎么办？",
            "options": {
                "a": "立即停药",
                "b": "立即改服旧药",
                "c": "继续按医生指示服药，如情况持续，便尽早复诊",
                "d": "自行减少剂量",
                "e": "不知道"
            }
        },
        "q_ht_3": {
            "question": "患有高血压的病人应避免以下哪一项运动？",
            "options": {
                "a": "快速短跑",
                "b": "太极",
                "c": "步行",
                "d": "伸展运动",
                "e": "不知道"
            }
        },
        "q_ht_4": {
            "question": "以下哪一种是患有高血压的病人应有的健康生活模式：",
            "options": {
                "a": "追求刺激活动",
                "b": "吸烟、酗酒",
                "c": "有足够的睡眠，作息有序",
                "d": "多喝浓茶和咖啡",
                "e": "不知道"
            }
        },
        "q_ht_5": {
            "question": "以下哪种食物盐份较高？",
            "options": {
                "a": "新鲜猪肉",
                "b": "午餐肉",
                "c": "蒸鱼",
                "d": "巧克力",
                "e": "不知道"
            }
        }
    },
    # 繁体中文（完全匹配你原版问卷）
    "zh-HK": {
        "q_dm_1": {
            "question": "以下哪個不是控制糖尿病的重要指標？",
            "options": {
                "a": "糖化血紅蛋白(HbA1c)",
                "b": "血壓",
                "c": "膽固醇",
                "d": "肝功能",
                "e": "不知道"
            }
        },
        "q_dm_2": {
            "question": "如果服食糖尿藥後，懷疑出現副作用時(例如頭暈、手震)，該怎麼辦？",
            "options": {
                "a": "立即改服舊藥",
                "b": "密切留意血糖的狀況，並及早尋求醫護人員的意見",
                "c": "自行減少劑量",
                "d": "停服糖尿藥一次",
                "e": "不知道"
            }
        },
        "q_dm_3": {
            "question": "若想透過帶氧運動(例如步行、行山、踏單車)幫助控制糖尿病，病人應：",
            "options": {
                "a": "每星期一天運動，合共約60分鐘",
                "b": "每星期兩天運動，合共約60分鐘",
                "c": "每星期三天運動，每次約30分鐘",
                "d": "每星期五天運動，每次約30分鐘",
                "e": "不知道"
            }
        },
        "q_dm_4": {
            "question": "自我管理糖尿病，其中最有效的方法是：",
            "options": {
                "a": "立即為自己訂立目標，改變生活習慣",
                "b": "服用坊間流傳的偏方來降血糖",
                "c": "自行調較藥物劑量",
                "d": "謝絕社交應酬",
                "e": "不知道"
            }
        },
        "q_dm_5": {
            "question": "糖尿病患者可以進食米飯嗎？",
            "options": {
                "a": "可以隨意進食",
                "b": "進食時要計算份量",
                "c": "要避免進食",
                "d": "改吃粥更佳",
                "e": "不知道"
            }
        },
        "q_ht_1": {
            "question": "80歲以下的高血壓患者，血壓應控制於：",
            "options": {
                "a": "高於 160 / 100mmHg",
                "b": "低於 140 / 90mmHg",
                "c": "低於 120 / 70mmHg",
                "d": "低於 100 / 70mmHg",
                "e": "不知道"
            }
        },
        "q_ht_2": {
            "question": "如果服食血壓藥後，懷疑出現副作用時(例如頭暈、咳嗽)，該怎麼辦？",
            "options": {
                "a": "立即停藥",
                "b": "立即改服舊藥",
                "c": "繼續按醫生指示服藥，如情況持續，便盡早覆診",
                "d": "自行減少劑量",
                "e": "不知道"
            }
        },
        "q_ht_3": {
            "question": "患有高血壓的病人應避免以下哪一項運動？",
            "options": {
                "a": "快速短跑",
                "b": "太極",
                "c": "步行",
                "d": "伸展運動",
                "e": "不知道"
            }
        },
        "q_ht_4": {
            "question": "以下哪一種是患有高血壓的病人應有的健康生活模式：",
            "options": {
                "a": "追求刺激活動",
                "b": "吸煙、酗酒",
                "c": "有足夠的睡眠，作息有序",
                "d": "多喝濃茶和咖啡",
                "e": "不知道"
            }
        },
        "q_ht_5": {
            "question": "以下哪種食物鹽份較高？",
            "options": {
                "a": "新鮮豬肉",
                "b": "午餐肉",
                "c": "蒸魚",
                "d": "朱古力",
                "e": "不知道"
            }
        }
    },
    # 英文翻译
    "en": {
        "q_dm_1": {
            "question": "Which of the following is NOT an important indicator for diabetes control?",
            "options": {
                "a": "Glycated hemoglobin (HbA1c)",
                "b": "Blood pressure",
                "c": "Cholesterol",
                "d": "Liver function",
                "e": "Unknown"
            }
        },
        "q_dm_2": {
            "question": "What to do if you suspect side effects (dizziness, hand tremors) after taking diabetes medication?",
            "options": {
                "a": "Switch to old medicine immediately",
                "b": "Monitor blood sugar closely and seek medical advice promptly",
                "c": "Reduce dosage by yourself",
                "d": "Skip one dose of diabetes medicine",
                "e": "Unknown"
            }
        },
        "q_dm_3": {
            "question": "To control diabetes through aerobic exercise (walking, hiking, cycling), patients should:",
            "options": {
                "a": "Exercise 1 day a week for 60 minutes total",
                "b": "Exercise 2 days a week for 60 minutes total",
                "c": "Exercise 3 days a week for 30 minutes each time",
                "d": "Exercise 5 days a week for 30 minutes each time",
                "e": "Unknown"
            }
        },
        "q_dm_4": {
            "question": "The most effective way for diabetes self-management is:",
            "options": {
                "a": "Set goals and change lifestyle habits actively",
                "b": "Take folk remedies to lower blood sugar",
                "c": "Adjust medication dosage by yourself",
                "d": "Refuse all social engagements",
                "e": "Unknown"
            }
        },
        "q_dm_5": {
            "question": "Can diabetic patients eat rice?",
            "options": {
                "a": "Eat freely",
                "b": "Control portion size when eating",
                "c": "Avoid eating completely",
                "d": "Porridge is better",
                "e": "Unknown"
            }
        },
        "q_ht_1": {
            "question": "For hypertensive patients under 80 years old, blood pressure should be controlled at:",
            "options": {
                "a": "Higher than 160 / 100mmHg",
                "b": "Lower than 140 / 90mmHg",
                "c": "Lower than 120 / 70mmHg",
                "d": "Lower than 100 / 70mmHg",
                "e": "Unknown"
            }
        },
        "q_ht_2": {
            "question": "What to do if you suspect side effects (dizziness, cough) after taking hypertension medication?",
            "options": {
                "a": "Stop medication immediately",
                "b": "Switch to old medicine immediately",
                "c": "Continue medication as prescribed and follow up promptly if symptoms persist",
                "d": "Reduce dosage by yourself",
                "e": "Unknown"
            }
        },
        "q_ht_3": {
            "question": "Which exercise should hypertensive patients avoid?",
            "options": {
                "a": "Sprinting",
                "b": "Tai Chi",
                "c": "Walking",
                "d": "Stretching exercise",
                "e": "Unknown"
            }
        },
        "q_ht_4": {
            "question": "Which lifestyle is suitable for hypertensive patients?",
            "options": {
                "a": "Thrilling activities",
                "b": "Smoking and heavy drinking",
                "c": "Adequate sleep and regular schedule",
                "d": "Strong tea and coffee",
                "e": "Unknown"
            }
        },
        "q_ht_5": {
            "question": "Which food has high salt content?",
            "options": {
                "a": "Fresh pork",
                "b": "Luncheon meat",
                "c": "Steamed fish",
                "d": "Chocolate",
                "e": "Unknown"
            }
        }
    }
}

# 基礎健康欄位 答案翻譯對照表（解決英文輸出問題）
HEALTH_VALUE_TRANS = {
    "zh-CN": {
        "Less than 1 hour": "少于1小時",
        "1-2 hours": "1-2小時",
        "2-3 hours": "2-3小時",
        "More than 3 hours": "3小時以上",
        "Non-drinker": "不飲酒",
        "Occasional": "偶爾飲酒",
        "Regular": "經常飲酒",
        "Never": "從不吸煙",
        "Former smoker": "已戒煙",
        "Current smoker": "現吸煙",
        "Yes": "是",
        "No": "否",
        "Not applicable": "不適用"
    },
    "zh-HK": {
        "Less than 1 hour": "少於1小時",
        "1-2 hours": "1-2小時",
        "2-3 hours": "2-3小時",
        "More than 3 hours": "3小時以上",
        "Non-drinker": "不飲酒",
        "Occasional": "偶爾飲酒",
        "Regular": "經常飲酒",
        "Never": "從不吸煙",
        "Former smoker": "已戒煙",
        "Current smoker": "現吸煙",
        "Yes": "是",
        "No": "否",
        "Not applicable": "不適用"
    },
    "en": {}
}

# 多語言文本模板
TXT_LANG_TEXT = {
    "zh-CN": {
        "title": "健康问卷",
        "patient_name": "患者姓名",
        "phone": "联系电话",
        "submit_time": "提交时间",
        "base_health_title": "一、基础健康评估信息",
        "assessment_date": "评估日期",
        "body_weight": "体重(kg)",
        "cardio_exercise": "每周有氧运动",
        "muscle_exercise": "每周肌力训练",
        "alcohol_use": "饮酒习惯",
        "smoking": "吸烟状态",
        "healthy_diet": "健康饮食习惯",
        "bp_monitor": "血压自我监测",
        "bg_monitor": "血糖自我监测",
        "quit_smoking_attempt": "尝试戒烟",
        "weight_manage_attempt": "尝试体重管理",
        "dm_quiz_title": "二、糖尿病知识问卷作答",
        "ht_quiz_title": "三、高血压知识问卷作答",
        "question_text": "题目",
        "answer_text": "所选答案",
        "option_text": "全部选项",
        "empty_text": "无",
        "unanswered_text": "未作答",
        "split_line": "----------------------------------------"
    },
    "zh-HK": {
        "title": "健康問卷",
        "patient_name": "患者姓名",
        "phone": "聯繫電話",
        "submit_time": "提交時間",
        "base_health_title": "一、基礎健康評估資訊",
        "assessment_date": "評估日期",
        "body_weight": "體重(kg)",
        "cardio_exercise": "每週有氧運動",
        "muscle_exercise": "每週肌力訓練",
        "alcohol_use": "飲酒習慣",
        "smoking": "吸煙狀態",
        "healthy_diet": "健康飲食習慣",
        "bp_monitor": "血壓自我監測",
        "bg_monitor": "血糖自我監測",
        "quit_smoking_attempt": "嘗試戒煙",
        "weight_manage_attempt": "嘗試體重管理",
        "dm_quiz_title": "二、糖尿病知識問卷作答",
        "ht_quiz_title": "三、高血壓知識問卷作答",
        "question_text": "題目",
        "answer_text": "所選答案",
        "option_text": "全部選項",
        "empty_text": "無",
        "unanswered_text": "未作答",
        "split_line": "----------------------------------------"
    },
    "en": {
        "title": "Health Questionnaire",
        "patient_name": "Patient Name",
        "phone": "Phone Number",
        "submit_time": "Submit Time",
        "base_health_title": "1. Basic Health Assessment Information",
        "assessment_date": "Assessment Date",
        "body_weight": "Body Weight(kg)",
        "cardio_exercise": "Weekly Cardio Exercise",
        "muscle_exercise": "Weekly Muscle Strengthening",
        "alcohol_use": "Alcohol Use Habit",
        "smoking": "Smoking Status",
        "healthy_diet": "Healthy Diet Habit",
        "bp_monitor": "Blood Pressure Self-monitoring",
        "bg_monitor": "Blood Glucose Self-monitoring",
        "quit_smoking_attempt": "Attempt to Quit Smoking",
        "weight_manage_attempt": "Attempt to Manage Weight",
        "dm_quiz_title": "2. Diabetes Knowledge Questionnaire Answers",
        "ht_quiz_title": "3. Hypertension Knowledge Questionnaire Answers",
        "question_text": "Question",
        "answer_text": "Selected Answer",
        "option_text": "All Options",
        "empty_text": "None",
        "unanswered_text": "Unanswered",
        "split_line": "----------------------------------------"
    }
}

# ---------------- 翻譯工具函數 ----------------
def trans_health_value(val: str, lang: str) -> str:
    """自動翻譯基礎健康英文答案為對應語言"""
    if not val:
        return TXT_LANG_TEXT[lang]["empty_text"]
    if lang == "en":
        return val
    return HEALTH_VALUE_TRANS[lang].get(val, val)

# ---------------- 生成單份問卷TXT文本字符串（最終完整版：題目+全部選項+選中答案） ----------------
def generate_questionnaire_txt(
        patient_name: str,
        phone: str,
        submit_time: str,
        detail: dict,
        lang: str = "zh-HK"
) -> str:
    if lang not in TXT_LANG_TEXT:
        lang = "zh-HK"
    text = TXT_LANG_TEXT[lang]
    quiz_text = QUIZ_FULL_TEXT[lang]
    lines = []
    split = text["split_line"]

    # 標題與基礎資訊
    lines.append(text["title"])
    lines.append(split)
    lines.append(f"{text['patient_name']}：{patient_name}")
    lines.append(f"{text['phone']}：{phone}")
    lines.append(f"{text['submit_time']}：{submit_time}")
    lines.append(split)

    # 基礎健康評估（自動翻譯）
    lines.append(text["base_health_title"])
    base = detail["baseHealth"]
    items = [
        (text["assessment_date"], base["assessmentDate"]),
        (text["body_weight"], str(base["bodyWeight"]) if base["bodyWeight"] else text["empty_text"]),
        (text["cardio_exercise"], trans_health_value(base["cardioExercisePerWeek"], lang)),
        (text["muscle_exercise"], trans_health_value(base["muscleStrengthenPerWeek"], lang)),
        (text["alcohol_use"], trans_health_value(base["alcoholUse"], lang)),
        (text["smoking"], trans_health_value(base["smoking"], lang)),
        (text["healthy_diet"], trans_health_value(base["healthyDietHabit"], lang)),
        (text["bp_monitor"], trans_health_value(base["selfMonitorBP"], lang)),
        (text["bg_monitor"], trans_health_value(base["selfMonitorBG"], lang)),
        (text["quit_smoking_attempt"], trans_health_value(base["attemptQuitSmoking"], lang)),
        (text["weight_manage_attempt"], trans_health_value(base["attemptManageWeight"], lang)),
    ]
    for k, v in items:
        lines.append(f"{k}：{v}")
    lines.append(split)

    # 糖尿病題目（完整題目+全部五選項+答案）
    lines.append(text["dm_quiz_title"])
    for idx, item in enumerate(detail["dmQuiz"]):
        q_id = item["questionId"]
        # 獲取原版題目和選項
        quiz_item = quiz_text.get(q_id, None)
        if not quiz_item:
            lines.append(f"{idx + 1}. {q_id}")
            continue
        q_content = quiz_item["question"]
        q_options = quiz_item["options"]
        ans = item["selectedAnswer"] or text["unanswered_text"]

        # 拼裝題目
        lines.append(f"{idx + 1}. {text['question_text']}：{q_content}")
        # 拼裝全部選項
        for opt_key, opt_val in q_options.items():
            lines.append(f"   {opt_key}. {opt_val}")
        # 拼裝選中答案
        lines.append(f"   {text['answer_text']}：{ans}")
        lines.append("")
    lines.append(split)

    # 高血壓題目（完整題目+全部五選項+答案）
    lines.append(text["ht_quiz_title"])
    for idx, item in enumerate(detail["htQuiz"]):
        q_id = item["questionId"]
        quiz_item = quiz_text.get(q_id, None)
        if not quiz_item:
            lines.append(f"{idx + 1}. {q_id}")
            continue
        q_content = quiz_item["question"]
        q_options = quiz_item["options"]
        ans = item["selectedAnswer"] or text["unanswered_text"]

        lines.append(f"{idx + 1}. {text['question_text']}：{q_content}")
        for opt_key, opt_val in q_options.items():
            lines.append(f"   {opt_key}. {opt_val}")
        lines.append(f"   {text['answer_text']}：{ans}")
        lines.append("")

    return "\n".join(lines)

# ---------------- 單條/批量導出接口（完全不變、編碼修復完畢） ----------------
# 新增：单问卷TXT导出接口
@router.get("/week9-questionnaires/{q_id}/export-single-txt")
def export_single_questionnaire_txt(
        q_id: int,
        lang: Optional[str] = Query("zh-HK", description="语言参数：zh-CN(简体)、zh-HK(繁体)、en(英文)"),
        db: Session = Depends(get_db)
):
    q_main = db.query(PatientWeek9Questionnaire).filter(PatientWeek9Questionnaire.id == q_id).first()
    if not q_main:
        raise HTTPException(status_code=404, detail="问卷不存在")
    patient = db.query(Patient).filter(Patient.patient_id == q_main.patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="患者信息不存在")

    dm_list = db.query(QuestionnaireDMAnswer).filter(QuestionnaireDMAnswer.questionnaire_id == q_id).all()
    ht_list = db.query(QuestionnaireHTAnswer).filter(QuestionnaireHTAnswer.questionnaire_id == q_id).all()

    p_name = patient.full_name
    p_phone = clean_phone_number(patient.phone)
    submit_time = q_main.create_time.strftime("%Y-%m-%d %H:%M:%S") if q_main.create_time else ""

    detail_dict = {
        "baseHealth": {
            "assessmentDate": q_main.assessment_date,
            "bodyWeight": q_main.body_weight,
            "cardioExercisePerWeek": q_main.cardio_exercise_per_week,
            "muscleStrengthenPerWeek": q_main.muscle_strengthen_per_week,
            "alcoholUse": q_main.alcohol_use,
            "smoking": q_main.smoking,
            "healthyDietHabit": q_main.healthy_diet_habit,
            "selfMonitorBP": q_main.self_monitor_bp,
            "selfMonitorBG": q_main.self_monitor_bg,
            "attemptQuitSmoking": q_main.attempt_quit_smoking,
            "attemptManageWeight": q_main.attempt_manage_weight,
        },
        "dmQuiz": [{"questionId": d.question_id, "selectedAnswer": d.answer} for d in dm_list],
        "htQuiz": [{"questionId": h.question_id, "selectedAnswer": h.answer} for h in ht_list]
    }

    txt_str = generate_questionnaire_txt(p_name, p_phone, submit_time, detail_dict, lang)
    txt_bytes = txt_str.encode("utf-8")
    buf = BytesIO(txt_bytes)
    buf.seek(0)

    # 修復中文文件名編碼報錯
    filename_raw = f"{p_name}_问卷.txt"
    filename_encoded = quote(filename_raw)
    return StreamingResponse(
        buf,
        media_type="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f"attachment; filename*=utf-8''{filename_encoded}"
        }
    )

# 批量导出全部问卷为TXT压缩包
@router.get("/week9-questionnaires/export-all-txt")
def admin_export_all_week9_txt(
        lang: Optional[str] = Query("zh-HK", description="语言：zh-CN / zh-HK / en"),
        db: Session = Depends(get_db)
):
    all_rows = (
        db.query(
            PatientWeek9Questionnaire.id,
            PatientWeek9Questionnaire.patient_id,
            PatientWeek9Questionnaire.create_time,
            Patient.first_name,
            Patient.last_name,
            Patient.phone
        )
        .join(Patient, Patient.patient_id == PatientWeek9Questionnaire.patient_id)
        .order_by(PatientWeek9Questionnaire.create_time.desc())
        .all()
    )
    if not all_rows:
        raise HTTPException(status_code=404, detail="暂无问卷数据可导出")
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zipf:
        for row in all_rows:
            q_id = row.id
            p_id = row.patient_id
            p_name = row.first_name + row.last_name
            p_phone = clean_phone_number(row.phone)
            submit_time = row.create_time.strftime("%Y%m%d_%H%M%S") if row.create_time else ""
            q_main = db.query(PatientWeek9Questionnaire).filter(PatientWeek9Questionnaire.id == q_id).first()
            dm_list = db.query(QuestionnaireDMAnswer).filter(QuestionnaireDMAnswer.questionnaire_id == q_id).all()
            ht_list = db.query(QuestionnaireHTAnswer).filter(QuestionnaireHTAnswer.questionnaire_id == q_id).all()
            detail_dict = {
                "baseHealth": {
                    "assessmentDate": q_main.assessment_date,
                    "bodyWeight": q_main.body_weight,
                    "cardioExercisePerWeek": q_main.cardio_exercise_per_week,
                    "muscleStrengthenPerWeek": q_main.muscle_strengthen_per_week,
                    "alcoholUse": q_main.alcohol_use,
                    "smoking": q_main.smoking,
                    "healthyDietHabit": q_main.healthy_diet_habit,
                    "selfMonitorBP": q_main.self_monitor_bp,
                    "selfMonitorBG": q_main.self_monitor_bg,
                    "attemptQuitSmoking": q_main.attempt_quit_smoking,
                    "attemptManageWeight": q_main.attempt_manage_weight,
                },
                "dmQuiz": [{"questionId": d.question_id, "selectedAnswer": d.answer} for d in dm_list],
                "htQuiz": [{"questionId": h.question_id, "selectedAnswer": h.answer} for h in ht_list]
            }
            txt_content = generate_questionnaire_txt(p_name, p_phone, row.create_time.strftime("%Y-%m-%d %H:%M:%S"),
                                                     detail_dict, lang)
            file_name = f"{p_name}_pid{p_id}_qid{q_id}_{submit_time}.txt"
            zipf.writestr(file_name, txt_content.encode("utf-8"))
    zip_buffer.seek(0)

    filename_raw = "问卷全部TXT导出.zip"
    filename_encoded = quote(filename_raw)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={
            "Content-Disposition": f"attachment; filename*=utf-8''{filename_encoded}"
        }
    )
from typing import Literal
from fastapi import  status
class NurseUpdateAccountTypeRequest(BaseModel):
    phone: str
    account_type: Literal["official", "test"]

@router.put("/update-account-type", status_code=status.HTTP_200_OK)
async def update_nurse_account_type(
    req: NurseUpdateAccountTypeRequest,
    db: Session = Depends(get_db),
):
    # 1. 根据完整手机号查询护士
    nurse = db.query(Nurse).filter(Nurse.phone == req.phone).first()
    if not nurse:
        raise HTTPException(status_code=404, detail="未找到该护士账号")

    # 3. 判断是否无需修改
    if nurse.account_type == req.account_type:
        return {
            "success": True,
            "message": "护士账号类型未发生变化，无需更新",
            "phone": req.phone,
            "current_account_type": nurse.account_type
        }

    # 4. 更新数据库
    nurse.account_type = req.account_type
    db.commit()
    db.refresh(nurse)

    return {
        "success": True,
        "message": "护士账号类型修改成功，患者可见范围已同步更新",
        "phone": nurse.phone,
        "full_name": nurse.full_name,
        "old_account_type": nurse.account_type if nurse.account_type != req.account_type else None,
        "new_account_type": req.account_type
    }
