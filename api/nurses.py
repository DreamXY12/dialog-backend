from fastapi import APIRouter, HTTPException, Query, Path, Depends,status
from pydantic import BaseModel
from typing import List, Optional
from sql.people_models import Nurse,Message
import re
from sqlalchemy.orm import Session
from sql.start import get_db
from sql.nurse_curd import  get_patients_without_nurse_paginated_by_phone,assign_patient_to_nurse_by_phone
from sql.nurse_curd import unassign_patient_from_specific_nurse_by_phone,get_patients_by_nurse_paginated
from sql.patient_curd import get_patient_by_phone
from sql.nurse_curd import get_nurse_today_work_time_curd,update_nurse_today_work_time
from datetime import datetime
from sql.people_models import ConversationSession, ChatRoom
from typing import Any
from datetime import time

# 初始化路由
router = APIRouter(prefix="/nurses", tags=["nurses"])

class CommonResponse(BaseModel):
    success: bool
    message: str = ""
    data: Optional[Any] = None

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
    phone_pattern = r'^(?:\+86)?1[3-9]\d{9}$|^\+852\d{8}$'

    if not re.match(phone_pattern, patient_phone):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="患者手机号格式错误！"
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
    phone_pattern = r'^(?:\+86)?1[3-9]\d{9}$|^\+852\d{8}$'
    if not re.match(phone_pattern, patient_phone):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="患者手机号格式错误！"
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
            # 验证手机号格式（适配中国大陆 +86 / 中国香港 +852）
            # 匹配规则：
            # 1. 中国大陆：+861[3-9]\d{9} 或 1[3-9]\d{9}
            # 2. 中国香港：+852\d{8} （香港手机号8位数字）
            phone_pattern = r'^(?:\+86)?1[3-9]\d{9}$|^\+852\d{8}$'
            if not re.match(phone_pattern, patient_phone):
                results["failed"].append({
                    "patient_phone": patient_phone,  # 替换 patient_login_code
                    "reason": f"手机号格式错误（支持：中国大陆+86/11位、香港+852/8位）"
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


# 消息返回模型（适配前端ChatMessage类型）
class ChatMessageSchema:
    def __init__(self, msg: Message):
        self.message_id = msg.message_id
        self.content = msg.content or "無消息內容"
        self.sender_type = msg.sender_type.value  # 转字符串：patient/nurse/ai/system
        self.sender_id = msg.sender_id
        self.create_time = msg.create_time.strftime("%Y-%m-%d %H:%M:%S")  # 统一时间格式
        self.chat_mode = msg.chat_mode.value  # 转字符串：AI/assist/nurseType
        self.is_read = 1 if msg.is_read else 0


@router.get("/patient/{patient_phone}/messages", summary="查询患者所有对话记录（按天分组用）")
async def get_patient_chat_messages(
        patient_phone: str,
        start_date: Optional[str] = Query(None, description="开始日期（格式：YYYY-MM-DD）"),
        end_date: Optional[str] = Query(None, description="结束日期（格式：YYYY-MM-DD）"),
        db: Session = Depends(get_db)
):
    # 1. 校验患者是否存在
    patient = get_patient_by_phone(db, patient_phone)
    if not patient:
        raise HTTPException(status_code=404, detail="患者不存在，请核对手机号")

    # ===================== 这里是修复后的正确联表 =====================
    query = db.query(Message)\
        .join(ConversationSession, Message.session_uuid == ConversationSession.session_uuid)\
        .join(ChatRoom, ConversationSession.room_id == ChatRoom.room_id)\
        .filter(ChatRoom.patient_id == patient.patient_id)

    # 3. 时间过滤
    if start_date:
        try:
            start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
            query = query.filter(Message.create_time >= start_datetime)
        except ValueError:
            raise HTTPException(status_code=400, detail="开始日期格式错误")

    if end_date:
        try:
            end_datetime = datetime.strptime(end_date, "%Y-%m-%d")
            end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
            query = query.filter(Message.create_time <= end_datetime)
        except ValueError:
            raise HTTPException(status_code=400, detail="结束日期格式错误")

    # 4. 排序
    messages = query.order_by(Message.create_time.asc()).all()

    # 5. 格式化
    result = [ChatMessageSchema(msg).__dict__ for msg in messages]

    return success_response(
        data=result,
        message=f"查询成功，共{len(result)}条对话记录"
    )

class ResponseModel(BaseModel):
    code: int
    message: str
    data: Optional[Any] = None


def success_response(data: Any, message: str = "操作成功") -> ResponseModel:
    return ResponseModel(code=200, message=message, data=data)


def error_response(code: int, message: str) -> ResponseModel:
    return ResponseModel(code=code, message=message)

# 获取护士当日工作时间
@router.get("/{nurse_id}/today-work-time", response_model=CommonResponse)
def get_nurse_today_work_time(nurse_id: int, db: Session = Depends(get_db)):
    try:
        # 查询当日排班记录
        shift =  get_nurse_today_work_time_curd(db, nurse_id)

        if not shift:
            raise Exception("未查询到该护士当日排班记录")

        # 2. 获取服务器当前本地时间（新加坡UTC+8，与香港时间一致）
        now = datetime.now()
        current_time = now.time()  # 提取当前时分秒（如09:30:25）

        # 3. 核心判断：当前时间是否在护士工作时间区间内
        # work_start_time/work_end_time为数据库的time类型，可直接比较
        is_working = shift.work_start_time <= current_time <= shift.work_end_time

        # 4. 动态设置status：工作时间内=active，否则=no-active
        dynamic_status = "active" if is_working else "no-active"

        # 格式化时间返回
        return CommonResponse(
            success=True,
            data={
                "start_time": shift.work_start_time.strftime("%H:%M:%S"),
                "end_time": shift.work_end_time.strftime("%H:%M:%S"),
                "status": dynamic_status
            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取工作时间失败: {str(e)}"
        )

#  更新护士当日工作时间
@router.post("/{nurse_id}/update-today-work-time", response_model=CommonResponse)
def update_nurse_today_work_time_api(
    nurse_id: int,
    new_start_time: str | None = None,
    new_end_time: str | None = None,
    db: Session = Depends(get_db)
):
    try:
        # 时间字符串转time对象
        start_time = time.fromisoformat(new_start_time) if new_start_time else None
        end_time = time.fromisoformat(new_end_time) if new_end_time else None
        # 调用你写的更新函数
        shift = update_nurse_today_work_time(
            db=db,
            nurse_id=nurse_id,
            new_start_time=start_time,
            new_end_time=end_time
        )
        if not shift:
            return CommonResponse(success=False, message="无当日排班记录，请先登录创建")
        return CommonResponse(
            success=True,
            message="修改成功",
            data={
                "start_time": shift.work_start_time.strftime("%H:%M:%S"),
                "end_time": shift.work_end_time.strftime("%H:%M:%S")

            }
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"修改工作时间失败: {str(e)}"
        )