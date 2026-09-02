from fastapi import APIRouter, Query, Path, Depends, HTTPException
from sqlalchemy import func, select, and_,or_
from sqlalchemy.orm import Session
from typing import List
from datetime import datetime, timedelta
from pydantic import BaseModel
from opencc import OpenCC

# 你的模型
from sql.people_models import Patient, ChatRoom, Message
# 你的数据库获取函数
from sql.start import get_db
# 护士权限校验工具（根据你现有逻辑）
from sql.nurse_curd import get_nurse_by_id

# 路由实例
router = APIRouter(prefix="/key_word", tags=["Patient Keyword Message Search"])

cc_t2s = OpenCC('t2s')  # 繁→简
cc_s2t = OpenCC('s2t')  # 简→繁

# ===================== Pydantic 返回模型 =====================
class MsgItem(BaseModel):
    message_uuid: str
    sender_type: str
    content: str | None
    create_time: str
    message_type: str
    file_url: str | None
    is_match_keyword: bool
    matched_keywords: List[str]  # 🆕 实际命中的关键词列表（繁/简）

class TimeBlock(BaseModel):
    block_start: str
    block_end: str
    msg_list: List[MsgItem]

class SearchMessageResponse(BaseModel):
    code: int = 0
    word: str
    total_block: int
    total_msg: int
    time_block_list: List[TimeBlock]

# ===================== 工具函数：合并重叠时间区间 =====================
def merge_time_ranges(ranges: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not ranges:
        return []
    # 按起始时间排序
    sorted_ranges = sorted(ranges, key=lambda x: x[0])
    merged = [sorted_ranges[0]]
    for start, end in sorted_ranges[1:]:
        last_start, last_end = merged[-1]
        # 区间重叠/相接，合并
        if start <= last_end:
            new_range = (last_start, max(last_end, end))
            merged[-1] = new_range
        else:
            merged.append((start, end))
    return merged

# ===================== 核心接口 =====================
@router.get("/{patient_id}/search-message", response_model=SearchMessageResponse)
def search_patient_keyword_message(
    patient_id: int = Path(..., description="患者ID"),
    keyword: str = Query(..., description="检索关键词"),
    date: str = Query(..., description="查询日期 YYYY-MM-DD"),
    nurse_id: int = Query(..., description="当前登录护士ID"),
    context_min: int = Query(5, ge=1, le=120, description="上下文向后时长（分钟），范围1~120"),
    db: Session = Depends(get_db)
):
    # 1. 权限校验
    current_nurse = get_nurse_by_id(db, nurse_id)
    if not current_nurse:
        raise HTTPException(status_code=403, detail="护士身份不存在，无权限访问")

    patient = db.query(Patient).filter(Patient.patient_id == patient_id).first()
    if not patient:
        raise HTTPException(status_code=404, detail="患者不存在")
    if patient.assigned_nurse_id != current_nurse.nurse_id:
        raise HTTPException(status_code=403, detail="无权限查看该患者聊天记录")

    # 2. 获取聊天室
    chat_room = db.query(ChatRoom).filter(ChatRoom.patient_id == patient_id).first()
    if not chat_room:
        return SearchMessageResponse(
            word=keyword,
            total_block=0,
            total_msg=0,
            time_block_list=[]
        )
    room_id = chat_room.room_id

    # 日期边界
    day_start = datetime.strptime(date, "%Y-%m-%d")
    day_end = day_start + timedelta(days=1)

    # ========== 构建繁简候选关键词 ==========
    # cc_t2s = OpenCC('t2s')   # 繁→简
    # cc_s2t = OpenCC('s2t')   # 简→繁

    simplified = cc_t2s.convert(keyword)
    traditional = cc_s2t.convert(keyword)
    # 去重保留唯一词
    search_keywords = list(set([keyword, simplified, traditional]))
    combined_keywords = " ".join(search_keywords)

    # 3. 全文检索匹配时间
    match_stmt = select(Message.create_time).where(
        Message.room_id == room_id,
        Message.content.match(combined_keywords),
        Message.create_time >= day_start,
        Message.create_time < day_end
    )
    match_times = db.scalars(match_stmt).all()
    if not match_times:
        return SearchMessageResponse(
            word=keyword,
            total_block=0,
            total_msg=0,
            time_block_list=[]
        )

    # 4. 生成区间
    raw_ranges = []
    offset = timedelta(minutes=context_min)
    for t in match_times:
        raw_ranges.append((t, t + offset))
    merged_ranges = merge_time_ranges(raw_ranges)

    # 5. 查询所有区间内的消息
    or_filters = []
    for s, e in merged_ranges:
        or_filters.append(and_(Message.create_time >= s, Message.create_time <= e))

    msg_stmt = select(Message).where(
        Message.room_id == room_id,
        Message.create_time >= day_start,
        Message.create_time < day_end,
        or_(*or_filters)
    ).order_by(Message.create_time.asc())
    all_messages = db.scalars(msg_stmt).all()

    # 6. 预存匹配时间集合
    match_time_set = {t.strftime("%Y-%m-%d %H:%M:%S") for t in match_times}

    # 7. 组装结果
    time_block_list = []
    total_msg_count = 0
    for block_start_dt, block_end_dt in merged_ranges:
        block_msg_items = []
        for msg in all_messages:
            msg_time_str = msg.create_time.strftime("%Y-%m-%d %H:%M:%S")
            content = msg.content or ""

            # 🔥 判断是否命中，并找出具体命中的关键词
            matched_keywords = [kw for kw in search_keywords if kw in content]
            hit = bool(matched_keywords) and msg_time_str in match_time_set

            item = MsgItem(
                message_uuid=msg.message_uuid,
                sender_type=msg.sender_type.value if hasattr(msg.sender_type, "value") else msg.sender_type,
                content=content,
                create_time=msg_time_str,
                message_type=msg.message_type.value if hasattr(msg.message_type, "value") else msg.message_type,
                file_url=msg.file_url,
                is_match_keyword=hit,
                matched_keywords=matched_keywords   # 🆕 返回实际命中的词
            )
            block_msg_items.append(item)
            total_msg_count += 1

        time_block_list.append(TimeBlock(
            block_start=block_start_dt.strftime("%Y-%m-%d %H:%M:%S"),
            block_end=block_end_dt.strftime("%Y-%m-%d %H:%M:%S"),
            msg_list=block_msg_items
        ))

    return SearchMessageResponse(
        word=keyword,
        total_block=len(time_block_list),
        total_msg=total_msg_count,
        time_block_list=time_block_list
    )