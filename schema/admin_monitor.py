from pydantic import BaseModel, Field
from datetime import datetime,date
from typing import List, Optional, Union


class PatientOption(BaseModel):
    patient_id: str
    name: str


# ========= Chat Stats =========
class ChatDailyItem(BaseModel):
    date: str
    has_record: bool
    record_list: Optional[List[dict]] = Field(default=None)


class ChatStatsResp(BaseModel):
    patient_id: str
    account_create_time: datetime
    total_days: int
    active_days: int
    frequency: float
    daily_list: List[ChatDailyItem]


# ========= Risk Stats =========
class RiskDailyItem(BaseModel):
    date: str
    has_operate: bool


class RiskStatsResp(BaseModel):
    patient_id: str
    risk_type: str  # diabetes | ckd
    total_days: int
    active_days: int
    frequency: float
    daily_list: List[RiskDailyItem]


# ========= Food Image =========
class FoodImageDailyItem(BaseModel):
    date: str
    has_upload: bool


class FoodImageStatsResp(BaseModel):
    patient_id: str
    total_days: int
    active_days: int
    frequency: float
    daily_list: List[FoodImageDailyItem]

# 单患者每日统计项
class PatientDailyStat(BaseModel):
    stat_date: date
    has_ai_chat: bool
    ai_chat_count: int = 0
    has_risk_predict: bool
    risk_predict_count: int = 0
    has_food_upload: bool
    food_upload_count: int = 0

# 患者监控详情响应
class PatientMonitorDetail(BaseModel):
    patient_id: int
    subject_code: Optional[str]
    full_name: str
    phone: str
    has_diabetes: Optional[str]
    account_create_time: datetime
    total_ai_chat_days: int
    ai_chat_frequency: float = Field(description="AI对话频率：活跃对话天数 / 总经历天数，0~1")
    total_risk_predict_days: int
    risk_predict_frequency: float
    total_food_upload_days: int
    food_upload_frequency: float
    daily_list: List[PatientDailyStat]

# 简易患者列表（用于页面下拉选择）
class PatientSimpleItem(BaseModel):
    patient_id: int
    subject_code: Optional[str]
    full_name: str

class PatientMonitorListResp(BaseModel):
    items: List[PatientSimpleItem]
    total: int