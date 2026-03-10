from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime, Date, Float, DECIMAL, Enum
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from typing import Optional
import enum
from sql.start import Base
import datetime
from sqlalchemy.dialects.mysql import JSON

from pydantic import BaseModel, Field

class TimeStampMixIn(object):
    '''
    create time and update time mix in.
    '''
    create_time = mapped_column(DateTime(timezone=True), server_default=func.now())
    update_time = mapped_column(DateTime(timezone=True), onupdate=func.now())


class Gender(enum.Enum):
    Female = "Female"
    Male = "Male"
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


class LoginCode(TimeStampMixIn, Base):
    """登录码表"""
    __tablename__ = 'login_code'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    code: Mapped[str] = mapped_column(String(4), unique=True)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False)
    user_type: Mapped[Optional[str]] = mapped_column(String(10))  # patient/nurse
    used_at: Mapped[Optional[DateTime]] = mapped_column(DateTime, nullable=True)


class Nurse(TimeStampMixIn, Base):
    """护士表"""
    __tablename__ = 'nurse'

    nurse_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    login_code: Mapped[str] = mapped_column(String(4), unique=True)
    first_name: Mapped[str] = mapped_column(String(50))
    last_name: Mapped[str] = mapped_column(String(50))
    hashed_password: Mapped[str] = mapped_column(String(255))

    # 关系
    patients: Mapped["Patient"] = relationship(
        back_populates="nurse",
        cascade="all, delete-orphan"
    )

    # 计算属性
    @property
    def full_name(self):
        """获取完整姓名"""
        return f"{self.first_name}{self.last_name}"


class Patient(TimeStampMixIn, Base):
    """患者表"""
    __tablename__ = 'patient'

    patient_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    login_code: Mapped[str] = mapped_column(String(4), unique=True)
    first_name: Mapped[str] = mapped_column(String(50))
    last_name: Mapped[str] = mapped_column(String(50))
    hashed_password: Mapped[str] = mapped_column(String(255))

    # 健康信息
    date_of_birth: Mapped[Optional[Date]] = mapped_column(Date, nullable=True)
    sex: Mapped[Optional[str]] = mapped_column(
        Enum(
            Gender,
            values_callable=lambda enum: [e.value for e in enum]
        ),
        nullable=True
    )
    family_history: Mapped[Optional[str]] = mapped_column(
        Enum(
            FamilyHistory,
            values_callable=lambda enum: [e.value for e in enum]
        ),
        nullable=True
    )
    smoking_status: Mapped[Optional[str]] = mapped_column(
        Enum(
            SmokingStatus,
            values_callable=lambda enum: [e.value for e in enum]
        ),
        nullable=True
    )
    drinking_history: Mapped[Optional[str]] = mapped_column(
        Enum(
            DrinkingFrequency,
            values_callable=lambda enum: [e.value for e in enum]
        ),
        nullable=True
    )
    height: Mapped[Optional[float]] = mapped_column(DECIMAL(5, 2), nullable=True)
    weight: Mapped[Optional[float]] = mapped_column(DECIMAL(5, 2), nullable=True)

    # 外键 - 修改为连接护士的login_code
    assigned_nurse_id: Mapped[Optional[str]] = mapped_column(
        String(4),
        ForeignKey("nurse.login_code"),
        nullable=True
    )

    # 关系
    nurse: Mapped[Optional["Nurse"]] = relationship(back_populates="patients")

    # 计算属性
    @property
    def full_name(self):
        """获取完整姓名"""
        return f"{self.first_name}{self.last_name}"

    @property
    def age(self):
        """计算年龄"""
        if self.date_of_birth:
            today = datetime.datetime.now().date()
            age = today.year - self.date_of_birth.year
            # 如果生日还没到，年龄减1
            if (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day):
                age -= 1
            return age
        return None

    @property
    def bmi(self):
        """计算BMI"""
        if self.height and self.weight and float(self.height) > 0:
            height_in_m = float(self.height) / 100
            bmi_value = float(self.weight) / (height_in_m * height_in_m)
            return round(bmi_value, 2)
        return None

class PatientAIDialogHistory(TimeStampMixIn, Base):
    """患者-AI对话历史记录表"""
    __tablename__ = 'ai_dialog_history'

    history_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment='历史记录ID'
    )
    # 核心修改1：字段名改为patient_phone
    # 核心修改2：长度从4改为20（适配带区号的手机号：+86/852+手机号）
    # 核心修改3：外键关联patient.phone字段，保留原有ON DELETE/UPDATE规则
    patient_phone: Mapped[str] = mapped_column(
        String(20),  # 原String(4)太短，20足够容纳+8613800138000/+85298765432
        ForeignKey("patient.phone", ondelete="CASCADE", onupdate="CASCADE"),
        nullable=False,
        comment='患者手机号（含区号，关联patient.phone）'
    )
    session_key: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
        comment='会话唯一标识'
    )
    ai_model: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment='使用的AI模型'
    )
    title: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        comment='会话标题'
    )
    prompts: Mapped[Optional[dict]] = mapped_column(
        JSON,
        nullable=True,
        comment='完整的对话内容/历史'
    )
    message_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment='消息总数量'
    )
    last_message_time: Mapped[Optional[DateTime]] = mapped_column(
        DateTime,
        nullable=True,
        comment='最后消息时间'
    )

    def __repr__(self):
        # 核心修改4：repr方法中字段名同步修改
        return f"<PatientAIDialogHistory(history_id={self.history_id}, patient_phone={self.patient_phone})>"

class BloodGlucoseRecord(Base):
    """血糖记录模型"""
    __tablename__ = "blood_glucose_records"
    
    id: Mapped[int] = mapped_column(
        Integer, 
        primary_key=True, 
        index=True,
        autoincrement=True,
        comment='记录ID'
    )
    patient_login_code: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment='患者登录码'
    )
    value: Mapped[float] = mapped_column(
        DECIMAL(5, 2),
        nullable=False,
        comment='血糖值 (mmol/L)'
    )
    period: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment='测量时段: 空腹、餐前、餐后、睡前'
    )
    recorded_at: Mapped[DateTime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        comment='记录时间'
    )
    
    def __repr__(self):
        return f"<BloodGlucoseRecord(id={self.id}, patient_login_code={self.patient_login_code}, value={self.value})>"

