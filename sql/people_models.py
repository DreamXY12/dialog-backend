# 病人，护士，验证码的sql模型，利用SQLAlchemy

from __future__ import annotations
from sqlalchemy import Boolean
from datetime import datetime

# 基础导入（确保环境安装：pip install sqlalchemy>=2.0 python-dotenv）
import enum
import datetime
from typing import List, Optional
from sqlalchemy import (
    Integer, String, Date, DateTime, DECIMAL,
    Index, ForeignKey, Enum, func,Float
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship
)

from sqlalchemy.dialects.mysql import JSON

# ---------------------------
# 基础类定义
# ---------------------------
class Base(DeclarativeBase):
    """SQLAlchemy 2.0+ 基础模型类"""
    pass

class TimeStampMixIn:
    """时间戳混合类（匹配表中的create_time/update_time）"""
    create_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),  # 匹配MySQL timestamp类型（无时区）
        server_default=func.now(),
        comment='创建时间'
    )
    update_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=func.now(),
        onupdate=func.now(),
        comment='更新时间'
    )

# ---------------------------
# 枚举类定义（完全匹配表中的enum值）
# ---------------------------
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

# ---------------------------
# 护士表模型（完全匹配nurse表结构）
# ---------------------------
class Nurse(TimeStampMixIn, Base):
    """护士表（全新）"""
    __tablename__ = 'nurse'
    __table_args__ = (
        # 唯一索引（匹配表中的uk_nurse_phone）- 注意：comment需要通过mysql_comment传递
        Index('uk_nurse_phone', 'phone', unique=True),
        # 组合索引（匹配表中的idx_nurse_name）
        Index('idx_nurse_name', 'first_name', 'last_name'),
        # 表级参数
        {
            'comment': '护士表（全新）',
            'mysql_engine': 'InnoDB',
            'mysql_charset': 'utf8mb4',
            'mysql_collate': 'utf8mb4_unicode_ci'
        }
    )

    # 主键
    nurse_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment='护士ID，主键'
    )
    # 核心字段
    phone: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        unique=True,  # 添加唯一约束
        comment='护士手机号（带区号，如+85212345678，唯一）'
    )
    phone_area_code: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
        comment='手机号区号（如+852/+86）'
    )
    first_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment='姓氏'
    )
    last_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment='名字'
    )

    # 关系：一个护士对应多个患者（一对多）
    patients: Mapped[List["Patient"]] = relationship(
        back_populates="nurse",
        cascade="all, delete-orphan",
        lazy="selectin"  # 优化关联查询性能
    )

    # 计算属性
    @property
    def full_name(self):
        """获取护士完整姓名"""
        return f"{self.first_name} {self.last_name}"

    def __repr__(self):
        return f"<Nurse(nurse_id={self.nurse_id}, phone={self.phone}, full_name={self.full_name})>"

# ---------------------------
# 患者表模型（完全匹配patient表结构）
# ---------------------------
class Patient(TimeStampMixIn, Base):
    """患者表（全新）"""
    __tablename__ = 'patient'
    __table_args__ = (
        # 唯一索引（匹配表中的uk_patient_phone）
        Index('uk_patient_phone', 'phone', unique=True),
        # 组合索引（匹配表中的idx_patient_name）
        Index('idx_patient_name', 'first_name', 'last_name'),
        # 🔴 修改1：更新索引名，匹配新字段名
        Index('idx_assigned_nurse_id', 'assigned_nurse_id'),
        # 表级参数
        {
            'comment': '患者表（全新）',
            'mysql_engine': 'InnoDB',
            'mysql_charset': 'utf8mb4',
            'mysql_collate': 'utf8mb4_unicode_ci'
        }
    )

    # 主键
    patient_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment='患者ID，主键'
    )
    # 核心字段
    phone: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        unique=True,  # 添加唯一约束
        comment='患者手机号（带区号，如+85212345678，唯一）'
    )
    phone_area_code: Mapped[Optional[str]] = mapped_column(
        String(10),
        nullable=True,
        comment='手机号区号（如+852/+86）'
    )
    first_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment='姓氏'
    )
    last_name: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment='名字'
    )

    # 健康信息字段（完全匹配表结构）
    date_of_birth: Mapped[Optional[datetime.date]] = mapped_column(
        Date,
        nullable=True,
        comment='出生日期'
    )
    sex: Mapped[Optional[Gender]] = mapped_column(
        Enum(Gender, values_callable=lambda e: [i.value for i in e]),
        nullable=True,
        comment='性别'
    )
    family_history: Mapped[Optional[FamilyHistory]] = mapped_column(
        Enum(FamilyHistory, values_callable=lambda e: [i.value for i in e]),
        nullable=True,
        comment='糖尿病家族史'
    )
    smoking_status: Mapped[Optional[SmokingStatus]] = mapped_column(
        Enum(SmokingStatus, values_callable=lambda e: [i.value for i in e]),
        nullable=True,
        comment='是否吸烟'
    )
    drinking_history: Mapped[Optional[DrinkingFrequency]] = mapped_column(
        Enum(DrinkingFrequency, values_callable=lambda e: [i.value for i in e]),
        nullable=True,
        comment='饮酒频率'
    )
    height: Mapped[Optional[float]] = mapped_column(
        DECIMAL(5, 2),
        nullable=True,
        comment='身高（厘米）'
    )
    weight: Mapped[Optional[float]] = mapped_column(
        DECIMAL(5, 2),
        nullable=True,
        comment='体重（公斤）'
    )

    # 🔴 修改2：替换外键字段（核心修改）
    assigned_nurse_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey(
            'nurse.nurse_id',  # 关联nurse表的nurse_id
            ondelete='SET NULL',
            onupdate='CASCADE'
        ),
        nullable=True,
        comment='负责护士ID（关联nurse.nurse_id）'  # 更新注释
    )

    # 🔴 修改3：保持关系映射不变（字段名变了但关系逻辑不变）
    nurse: Mapped[Optional[Nurse]] = relationship(
        back_populates="patients",
        lazy="selectin"
    )

    # 计算属性（无修改）
    @property
    def full_name(self):
        """获取患者完整姓名"""
        return f"{self.first_name} {self.last_name}"

    @property
    def age(self):
        """计算患者年龄（基于出生日期）"""
        if not self.date_of_birth:
            return None
        today = datetime.date.today()
        age = today.year - self.date_of_birth.year
        # 未到生日则年龄减1
        if (today.month, today.day) < (self.date_of_birth.month, self.date_of_birth.day):
            age -= 1
        return age

    @property
    def bmi(self):
        """计算BMI指数（体重(kg)/身高(m)²）"""
        if not (self.height and self.weight) or float(self.height) <= 0:
            return None
        height_m = float(self.height) / 100
        bmi_value = float(self.weight) / (height_m * height_m)
        return round(bmi_value, 2)

    def __repr__(self):
        return f"<Patient(patient_id={self.patient_id}, phone={self.phone}, full_name={self.full_name})>"


# 定义验证码用途/角色的枚举类（增强类型安全）
class VerificationRole(str, enum.Enum):
    """验证码适用的用户角色"""
    NURSE = "nurse"
    PATIENT = "patient"


class VerificationMode(str, enum.Enum):
    """验证码的使用场景"""
    LOGIN = "login"
    REGISTER = "register"
    RESET_PASSWORD = "reset_password"


class SmsVerificationCode(Base):
    """短信验证码表模型"""
    __tablename__ = 'sms_verification_code'
    __table_args__ = (
        # 唯一索引：手机号+验证码（防止重复）
        Index('uk_phone_code', 'phone', 'code', unique=True),
        # 组合索引：手机号+过期时间（优化查询性能）
        Index('idx_phone_expire', 'phone', 'expire_at'),
        # 单字段索引：使用状态
        Index('idx_is_used', 'is_used'),
        # 表级配置
        {
            'comment': '短信验证码表',
            'mysql_engine': 'InnoDB',
            'mysql_charset': 'utf8mb4',
            'mysql_collate': 'utf8mb4_unicode_ci'
        }
    )

    # 主键
    id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment='主键ID'
    )

    # 核心字段
    phone: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment='接收验证码的手机号（带区号，如+85212345678）'
    )

    code: Mapped[str] = mapped_column(
        String(6),
        nullable=False,
        comment='6位数字验证码'
    )

    role: Mapped[VerificationRole] = mapped_column(
        Enum(VerificationRole),
        nullable=False,
        comment='用户角色：nurse/patient'
    )

    mode: Mapped[VerificationMode] = mapped_column(
        Enum(VerificationMode),
        nullable=False,
        comment='用途：login/register/reset_password'
    )

    expire_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        comment='验证码过期时间（默认5分钟）'
    )

    is_used: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment='是否已使用：0未使用/1已使用'
    )

    # 时间戳字段
    create_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        server_default=func.now(),
        comment='创建时间'
    )

    def __repr__(self):
        return f"<SmsVerificationCode(phone={self.phone}, code={self.code}, expire_at={self.expire_at}, is_used={self.is_used})>"

    @property
    def is_expired(self) -> bool:
        """判断验证码是否过期"""
        return datetime.datetime.now() > self.expire_at

# class BloodGlucoseRecord(Base):
#     """血糖记录模型"""
#     __tablename__ = "blood_glucose_records"
#
#     id: Mapped[int] = mapped_column(
#         Integer,
#         primary_key=True,
#         index=True,
#         autoincrement=True,
#         comment='记录ID'
#     )
#     patient_login_code: Mapped[str] = mapped_column(
#         String(255),
#         nullable=False,
#         comment='患者登录码'
#     )
#     value: Mapped[float] = mapped_column(
#         DECIMAL(5, 2),
#         nullable=False,
#         comment='血糖值 (mmol/L)'
#     )
#     period: Mapped[str] = mapped_column(
#         String(50),
#         nullable=False,
#         comment='测量时段: 空腹、餐前、餐后、睡前'
#     )
#     recorded_at: Mapped[DateTime] = mapped_column(
#         DateTime(timezone=True),
#         server_default=func.now(),
#         comment='记录时间'
#     )
#
#     def __repr__(self):
#         return f"<BloodGlucoseRecord(id={self.id}, patient_login_code={self.patient_login_code}, value={self.value})>"

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
    # 核心修改：字段名改为patient_phone，长度调整为20（适配带区号的手机号）
    patient_phone: Mapped[str] = mapped_column(
        String(20),  # 原255过长，20足够容纳+8613800138000/+85298765432等格式
        nullable=False,
        comment='患者手机号（含区号，如+86/+/852）'
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
        return f"<BloodGlucoseRecord(id={self.id}, patient_phone={self.patient_phone}, value={self.value})>"


class Case(TimeStampMixIn, Base):
    __tablename__ = 'patient_case'

    user_id: Mapped[Optional[int]] = mapped_column()
    case_id: Mapped[Optional[int]] = mapped_column(primary_key=True, autoincrement=True, index=True)

    hba1c: Mapped[Optional[float]] = mapped_column()
    fasting_glucose: Mapped[Optional[float]] = mapped_column()
    hdl_cholesterol: Mapped[Optional[float]] = mapped_column()
    total_cholesterol: Mapped[Optional[float]] = mapped_column()
    ldl_cholesterol: Mapped[Optional[float]] = mapped_column()
    creatinine: Mapped[Optional[float]] = mapped_column()
    triglyceride: Mapped[Optional[float]] = mapped_column()
    potassium: Mapped[Optional[float]] = mapped_column()

    time_spec: Mapped[int] = mapped_column(Integer)
    test_date: Mapped[Date] = mapped_column(Date)
    analysis_result: Mapped[Optional[str]] = mapped_column(String(30))
    score: Mapped[Optional[float]] = mapped_column(Float)

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