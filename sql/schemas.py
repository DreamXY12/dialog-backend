# schemas.py
from pydantic import BaseModel, validator, Field, ConfigDict
from typing import Optional
from datetime import date, datetime
import re
import enum
from typing import Any


# 枚举类
class Gender(str, enum.Enum):
    FEMALE = "Female"
    MALE = "Male"
    PREFER_NOT_TO_TELL = "Prefer not to tell"


class FamilyHistory(str, enum.Enum):
    YES = "Yes"
    NO = "No"
    UNKNOWN = "Unknown"


class SmokingStatus(str, enum.Enum):
    YES = "Yes"
    NO = "No"
    PREFER_NOT_TO_TELL = "Prefer not to tell"


class DrinkingFrequency(str, enum.Enum):
    NEVER = "Never"
    RARELY = "Rarely"
    OCCASIONALLY = "Occasionally"
    FREQUENTLY = "Frequently"
    DAILY = "Daily"

class UserType(str, enum.Enum):
    PATIENT = "patient"
    NURSE = "nurse"

# 基础请求/响应模型
class LoginRequest(BaseModel):
    """登录请求"""
    login_code: str
    password: str

    @validator('login_code')
    def validate_login_code(cls, v):
        if not re.match(r'^\d{4}$', v):
            raise ValueError('登录码必须是4位数字')
        return v


# 添加TokenResponse模型
class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user_type: str
    user_id: int
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    login_code: Optional[str] = None

    class Config:
        from_attributes = True


class LoginCodeResponse(BaseModel):
    """登录码响应"""
    login_code: str
    message: str
    created_at: datetime


class CheckCodeResponse(BaseModel):
    """检查登录码响应"""
    code: str
    is_available: bool
    is_used: bool
    exists: bool


# 护士模型
class NurseCreate(BaseModel):
    """护士创建"""
    login_code: str
    first_name: str
    last_name: str
    password: str

    @validator('login_code')
    def validate_login_code(cls, v):
        if not re.match(r'^\d{4}$', v):
            raise ValueError('登录码必须是4位数字')
        return v

    @validator('password')
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError('密码长度至少6位')
        return v


class NurseResponse(BaseModel):
    """护士响应"""
    nurse_id: int
    login_code: str
    first_name: str
    last_name: str
    full_name: str

    model_config = ConfigDict(from_attributes=True)

    def model_post_init(self, __context: Any) -> None:
        """确保full_name字段有值"""
        if not self.full_name:
            self.full_name = f"{self.first_name}{self.last_name}"


# 患者模型
class PatientCreate(BaseModel):
    """患者创建"""
    login_code: str
    first_name: str
    last_name: str
    password: str
    assigned_nurse_id: Optional[str] = None  # 改为Optional[str]

    @validator('login_code')
    def validate_login_code(cls, v):
        if not re.match(r'^\d{4}$', v):
            raise ValueError('登录码必须是4位数字')
        return v

    @validator('assigned_nurse_id')
    def validate_nurse_login_code(cls, v):
        if v is not None and not re.match(r'^\d{4}$', v):
            raise ValueError('护士登录码必须是4位数字')
        return v

    @validator('password')
    def validate_password(cls, v):
        if len(v) < 6:
            raise ValueError('密码长度至少6位')
        return v


class PatientUpdate(BaseModel):
    """患者信息更新"""
    date_of_birth: Optional[date] = None
    sex: Optional[Gender] = None
    family_history: Optional[FamilyHistory] = None
    smoking_status: Optional[SmokingStatus] = None
    drinking_history: Optional[DrinkingFrequency] = None
    height: Optional[float] = Field(None, ge=0, le=300)
    weight: Optional[float] = Field(None, ge=0, le=500)
    assigned_nurse_id: Optional[str] = None  # 改为Optional[str]

    @validator('assigned_nurse_id')
    def validate_nurse_login_code(cls, v):
        if v is not None and not re.match(r'^\d{4}$', v):
            raise ValueError('护士登录码必须是4位数字')
        return v

    class Config:
        use_enum_values = True

class PatientResponse(BaseModel):
    """患者响应"""
    patient_id: int
    login_code: str
    first_name: str
    last_name: str
    full_name: str

    # 健康信息
    date_of_birth: Optional[date] = None
    age: Optional[int] = None
    sex: Optional[Gender] = None
    family_history: Optional[FamilyHistory] = None
    smoking_status: Optional[SmokingStatus] = None
    drinking_history: Optional[DrinkingFrequency] = None
    height: Optional[float] = None
    weight: Optional[float] = None

    class Config:
        use_enum_values = True

    # 外键
    assigned_nurse_id: Optional[int] = None

    create_time: datetime
    update_time: Optional[datetime] = None  # 改为可选

    #model_config = ConfigDict(from_attributes=True)

    def model_post_init(self, __context: Any) -> None:
        """计算派生字段"""
        # 确保full_name字段有值
        if not self.full_name:
            self.full_name = f"{self.first_name}{self.last_name}"

        # 计算年龄
        if self.date_of_birth:
            today = datetime.now().date()
            age = today.year - self.date_of_birth.year
            if (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day):
                age -= 1
            self.age = age


class FirstLoginUpdate(BaseModel):
    """首次登录更新模型"""
    height: Optional[float] = Field(None, ge=0, le=300, description="身高 (cm)")
    weight: Optional[float] = Field(None, ge=0, le=500, description="体重 (kg)")
    age: Optional[int] = Field(None, ge=0, le=150, description="年龄")
    sex: Optional[str] = None
    drinking: Optional[str] = None
    family_history: Optional[str] = None
    smoking: Optional[str] = None

    @validator('sex')
    def validate_sex(cls, v):
        if v and v not in ["Female", "Male", "Prefer not to tell"]:
            raise ValueError("无效的性别选项")
        return v

    @validator('drinking')
    def validate_drinking(cls, v):
        if v and v not in ["Never", "Rarely", "Occasionally", "Frequently", "Daily"]:
            raise ValueError("无效的饮酒频率选项")
        return v

    @validator('family_history')
    def validate_family_history(cls, v):
        if v and v not in ["Yes", "No", "Prefer not to tell"]:
            raise ValueError("无效的家族病史选项")
        return v

    @validator('smoking')
    def validate_smoking(cls, v):
        if v and v not in ["Yes", "No"]:
            raise ValueError("无效的吸烟选项")
        return v

    class Config:
        use_enum_values = False
        schema_extra = {
            "example": {
                "height": 170.5,
                "weight": 65.2,
                "age": 35,
                "sex": "Male",
                "drinking": "Occasionally",
                "family_history": "Yes",
                "smoking": "No"
            }
        }


# 在现有schemas.py文件末尾添加
class AIDialogHistoryBase(BaseModel):
    """AI对话历史记录基础模型"""
    patient_login_code: str
    session_key: str
    ai_model: Optional[str] = None
    title: Optional[str] = None
    prompts: Optional[dict] = None
    message_count: int = 0
    last_message_time: Optional[datetime] = None


class AIDialogHistoryCreate(AIDialogHistoryBase):
    """创建AI对话历史记录的模型"""
    pass

class AIDialogCreateRequest(BaseModel):
    """创建AI对话请求"""
    patient_login_code: str
    session_key: str
    initial_message: Optional[str] = None
    ai_model: Optional[str] = "default"
    title: Optional[str] = None

class AIDialogMessageUpdate(BaseModel):
    """更新AI对话消息请求"""
    session_key: str
    user_message: str
    ai_response: str
    ai_model: Optional[str] = None

class AIDialogHistoryResponse(AIDialogHistoryBase):
    """AI对话历史记录响应模型"""
    history_id: int
    create_time: datetime
    update_time: Optional[datetime] = None

    class Config:
        from_attributes = True