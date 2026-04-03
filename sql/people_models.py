# 病人，护士，验证码的sql模型，利用SQLAlchemy

from __future__ import annotations
from sqlalchemy import Boolean,Text,Time,text,BigInteger
import datetime

# 基础导入（确保环境安装：pip install sqlalchemy>=2.0 python-dotenv）
import enum
from typing import List, Optional
from sqlalchemy import (
    Integer, String, Date, DateTime, DECIMAL,
    Index, ForeignKey, Enum, func,Float
)
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship
)

from sqlalchemy.dialects.mysql import JSON

# 在枚举类定义区域添加
class ReaderRole(str, enum.Enum):
    """阅读者角色"""
    PATIENT = "patient"
    NURSE = "nurse"

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

    work_shifts: Mapped[List["NurseWorkShift"]] = relationship(
        back_populates="nurse",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    chat_rooms: Mapped[List["ChatRoom"]] = relationship(
        back_populates="nurse",
        cascade="all, delete-orphan",
        lazy="selectin"
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

    # chat_rooms: Mapped[List["ChatRoom"]] = relationship(
    #     back_populates="patient",
    #     cascade="all, delete-orphan",
    #     lazy="selectin"
    # )

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

"""
    以下是记录对话的数据库模型
"""
# ---------------------------
# 枚举类定义
# ---------------------------
class NurseShiftStatus(str, enum.Enum):
    """护士班次状态"""
    SCHEDULED = "scheduled"     # 已排班
    ACTIVE = "active"           # 活跃中（工作时间段内）
    COMPLETED = "completed"     # 已完成


class RoomStatus(str, enum.Enum):
    """聊天室状态"""
    ACTIVE = "active"  # 活跃中
    WAITING_NURSE = "waiting_nurse"  # 等待护士
    NURSE_ASSIGNED = "nurse_assigned"  # 护士已分配
    COMPLETED = "completed"  # 已完成


class SessionType(str, enum.Enum):
    """会话类型"""
    AI_ONLY = "ai_only"  # 仅AI
    NURSE_ASSISTED = "nurse_assisted"  # 护士协助
    NURSE_HANDOVER = "nurse_handover"  # 护士接管


class SessionStatus(str, enum.Enum):
    """会话状态"""
    ACTIVE = "active"  # 活跃中
    PAUSED = "paused"  # 已暂停
    COMPLETED = "completed"  # 已结束


class AutoEndReason(str, enum.Enum):
    """自动结束原因"""
    NURSE_SHIFT_END = "nurse_shift_end"  # 护士下班
    INACTIVITY_TIMEOUT = "inactivity_timeout"  # 不活跃超时
    MANUAL_END = "manual_end"  # 手动结束


class SenderType(str, enum.Enum):
    """发送者类型"""
    PATIENT = "patient"  # 患者
    NURSE = "nurse"  # 护士
    AI = "ai"  # AI助手
    SYSTEM = "system"  # 系统


class MessageType(str, enum.Enum):
    """消息类型"""
    TEXT = "text"  # 文本
    IMAGE = "image"  # 图片
    VOICE = "voice"  # 语音
    FILE = "file"  # 文件
    SYSTEM = "system"  # 系统消息


class ChatMode(str, enum.Enum):
    """聊天模式"""
    AI = "AI"  # AI模式
    ASSIST = "assist"  # 协助模式
    NURSE_TYPE = "nurseType"  # 护士接管模式


# ---------------------------
# 护士班次表模型
# ---------------------------
class NurseWorkShift(TimeStampMixIn, Base):
    """护士工作班次表（按天）"""
    __tablename__ = 'nurse_work_shift'
    __table_args__ = (
        # 唯一约束
        Index('uk_shift_uuid', 'shift_uuid', unique=True),
        # 组合索引
        Index('idx_nurse_date', 'nurse_id', 'work_date'),
        Index('idx_status_date', 'status', 'work_date'),
        Index('idx_work_time_range', 'work_start_time', 'work_end_time'),
        # 表级参数
        {
            'comment': '护士工作班次表（按天）',
            'mysql_engine': 'InnoDB',
            'mysql_charset': 'utf8mb4',
            'mysql_collate': 'utf8mb4_unicode_ci'
        }
    )

    # 主键
    shift_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment='班次ID（自增主键）'
    )
    shift_uuid: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        server_default=text("(UUID())"),
        comment='对外班次UUID（安全标识）'
    )

    # 外键 - 关联护士表
    nurse_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('nurse.nurse_id', ondelete='CASCADE'),
        nullable=False,
        comment='护士ID（外键关联nurse表）'
    )

    # 日期字段
    work_date: Mapped[datetime.date] = mapped_column(
        Date,
        nullable=False,
        comment='工作日期（如2024-03-20）'
    )

    # 工作时间段
    work_start_time: Mapped[datetime.time] = mapped_column(
        Time,
        nullable=False,
        comment='工作时间段开始（如09:00:00）'
    )
    work_end_time: Mapped[datetime.time] = mapped_column(
        Time,
        nullable=False,
        comment='工作时间段结束（如18:00:00）'
    )

    # 状态字段
    status: Mapped[NurseShiftStatus] = mapped_column(
        Enum(NurseShiftStatus,values_callable=lambda e: [i.value for i in e]),
        nullable=False,
        default=NurseShiftStatus.SCHEDULED,
        comment='班次状态：scheduled=已排班, active=活跃中, completed=已完成'
    )

    # 统计字段
    current_session_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment='当前处理的会话数量'
    )
    total_session_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment='本班次总会话数'
    )
    total_message_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment='本班次总消息数'
    )

    # 关系
    nurse: Mapped["Nurse"] = relationship(
        back_populates="work_shifts",
        lazy="selectin"
    )
    sessions: Mapped[List["ConversationSession"]] = relationship(
        back_populates="nurse_shift",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    chat_rooms: Mapped[List["ChatRoom"]] = relationship(
        back_populates="current_shift",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    # 计算属性
    @property
    def is_working_hours(self) -> bool:
        """当前时间是否在工作时间段内"""
        from datetime import datetime
        now = datetime.now()
        current_time = now.time()
        return self.work_start_time <= current_time <= self.work_end_time

    @property
    def is_today(self) -> bool:
        """是否是今天的班次"""
        from datetime import datetime
        today = datetime.now().date()
        return self.work_date == today

    @property
    def shift_duration_hours(self) -> float:
        """班次时长（小时）"""
        start_hour = self.work_start_time.hour + self.work_start_time.minute / 60
        end_hour = self.work_end_time.hour + self.work_end_time.minute / 60
        return end_hour - start_hour

    def __repr__(self):
        return f"<NurseWorkShift(shift_id={self.shift_id}, nurse_id={self.nurse_id}, date={self.work_date}, status={self.status})>"


# ---------------------------
# 聊天室表模型
# ---------------------------
class ChatRoom(TimeStampMixIn, Base):
    """聊天室表（患者与护士的关联）"""
    __tablename__ = 'chat_room'
    __table_args__ = (
        Index('idx_patient_status', 'patient_id', 'room_status'),
        Index('idx_nurse_status', 'nurse_id', 'room_status'),
        Index('idx_last_activity', 'last_activity_time'),
        {
            'comment': '聊天室表（患者与护士的关联）',
            'mysql_engine': 'InnoDB',
            'mysql_charset': 'utf8mb4',
            'mysql_collate': 'utf8mb4_unicode_ci'
        }
    )

    # 主键
    room_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment='聊天室ID（自增主键）'
    )
    room_uuid: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        server_default=text("(UUID())"),
        comment='对外聊天室UUID（安全标识）'
    )

    # 外键
    patient_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('patient.patient_id', ondelete='CASCADE'),
        nullable=False,
        comment='患者ID（外键关联patient表）'
    )
    nurse_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey('nurse.nurse_id', ondelete='SET NULL'),
        nullable=True,
        comment='分配的护士ID（可为空，无分配时由AI单独服务）'
    )
    current_shift_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey('nurse_work_shift.shift_id', ondelete='SET NULL'),
        nullable=True,
        comment='护士当前班次ID（外键关联nurse_work_shift表）'
    )

    # 状态字段
    room_status: Mapped[RoomStatus] = mapped_column(
        Enum(RoomStatus, values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=RoomStatus.ACTIVE,
        comment='聊天室状态：active=活跃中, waiting_nurse=等待护士, nurse_assigned=护士已分配, completed=已完成'
    )

    # 时间相关字段
    last_activity_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
        comment='最后活动时间（用于超时判断）'
    )

    # 冗余字段
    current_session_uuid: Mapped[Optional[str]] = mapped_column(
        String(36),
        nullable=True,
        comment='当前活跃会话的UUID（冗余字段，快速查询）'
    )

    # 配置字段
    inactivity_timeout_minutes: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=30,
        comment='不活跃超时时间（分钟，默认30分钟）'
    )

    # 关系
    # patient: Mapped["Patient"] = relationship(
    #     back_populates="chat_rooms",
    #     lazy="selectin"
    # )
    nurse: Mapped[Optional["Nurse"]] = relationship(
        back_populates="chat_rooms",
        lazy="selectin"
    )
    current_shift: Mapped[Optional["NurseWorkShift"]] = relationship(
        back_populates="chat_rooms",
        lazy="selectin"
    )
    sessions: Mapped[List["ConversationSession"]] = relationship(
        back_populates="chat_room",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    def __repr__(self):
        return f"<ChatRoom(room_id={self.room_id}, patient_id={self.patient_id}, nurse_id={self.nurse_id})>"


# ---------------------------
# 对话会话表模型
# ---------------------------
class ConversationSession(TimeStampMixIn, Base):
    """对话会话表（按护士班次自然分割会话）"""
    __tablename__ = 'conversation_session'
    __table_args__ = (
        Index('idx_room_sessions', 'room_id', 'session_number'),
        Index('idx_session_status_time', 'session_status', 'last_message_time'),
        Index('idx_start_end_time', 'start_time', 'end_time'),
        {
            'comment': '对话会话表（按护士班次自然分割会话）',
            'mysql_engine': 'InnoDB',
            'mysql_charset': 'utf8mb4',
            'mysql_collate': 'utf8mb4_unicode_ci'
        }
    )

    # 主键
    session_id: Mapped[int] = mapped_column(
        Integer,
        primary_key=True,
        autoincrement=True,
        comment='会话ID（自增主键）'
    )
    session_uuid: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        server_default=text("(UUID())"),
        comment='对外会话UUID（安全标识）'
    )

    # 外键
    room_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey('chat_room.room_id', ondelete='CASCADE'),
        nullable=False,
        comment='所属聊天室ID（外键关联chat_room表）'
    )
    nurse_shift_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        ForeignKey('nurse_work_shift.shift_id', ondelete='SET NULL'),
        nullable=True,
        comment='关联的护士班次ID（外键关联nurse_work_shift表）'
    )

    # 会话信息
    session_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        comment='会话序号（同一聊天室的第几次咨询）'
    )
    session_type: Mapped[SessionType] = mapped_column(
        Enum(SessionType, values_callable=lambda e: [i.value for i in e]),
        nullable=False,
        default=SessionType.AI_ONLY,
        comment='会话类型：ai_only=仅AI, nurse_assisted=护士协助, nurse_handover=护士接管'
    )
    session_status: Mapped[SessionStatus] = mapped_column(
        Enum(SessionStatus, values_callable=lambda e: [i.value for i in e]),
        nullable=False,
        default=SessionStatus.ACTIVE,
        comment='会话状态：active=活跃中, paused=已暂停, completed=已结束'
    )

    # 时间字段
    start_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        comment='会话开始时间'
    )
    end_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
        comment='会话结束时间'
    )
    last_message_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
        comment='最后消息时间（用于超时判断）'
    )

    # 结束原因
    auto_end_reason: Mapped[Optional[AutoEndReason]] = mapped_column(
        Enum(AutoEndReason,values_callable=lambda e: [i.value for i in e]),
        nullable=True,
        comment='自动结束原因：nurse_shift_end=护士下班, inactivity_timeout=不活跃超时, manual_end=手动结束'
    )

    # 统计字段
    message_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        comment='本会话的总消息数量'
    )

    # 关系
    chat_room: Mapped["ChatRoom"] = relationship(
        back_populates="sessions",
        lazy="selectin"
    )
    nurse_shift: Mapped[Optional["NurseWorkShift"]] = relationship(
        back_populates="sessions",
        lazy="selectin"
    )
    messages: Mapped[List["Message"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    def __repr__(self):
        return f"<ConversationSession(session_id={self.session_id}, room_id={self.room_id}, status={self.session_status})>"


# ---------------------------
# 消息表模型
# ---------------------------
class Message(Base):
    """消息表（存储所有聊天消息）"""
    __tablename__ = 'message'
    __table_args__ = (
        Index('idx_session_messages', 'session_uuid', 'create_time'),
        Index('idx_message_status', 'session_uuid', 'is_read', 'sender_type'),
        Index('idx_sender_messages', 'sender_type', 'sender_id'),
        Index('idx_create_time', 'create_time'),
        {
            'comment': '消息表（存储所有聊天消息）',
            'mysql_engine': 'InnoDB',
            'mysql_charset': 'utf8mb4',
            'mysql_collate': 'utf8mb4_unicode_ci'
        }
    )

    # 主键
    message_id: Mapped[int] = mapped_column(
        BigInteger,
        primary_key=True,
        autoincrement=True,
        comment='消息ID（自增主键）'
    )
    message_uuid: Mapped[str] = mapped_column(
        String(36),
        nullable=False,
        unique=True,
        server_default=text("(UUID())"),
        comment='对外消息UUID（安全标识）'
    )

    # 外键
    session_uuid: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('conversation_session.session_uuid', ondelete='CASCADE'),
        nullable=False,
        comment='所属会话UUID（外键关联conversation_session表）'
    )

    # 发送者信息
    sender_type: Mapped[SenderType] = mapped_column(
        Enum(SenderType,values_callable=lambda e: [i.value for i in e]),
        nullable=False,
        comment='发送者类型：patient=患者, nurse=护士, ai=AI助手, system=系统'
    )
    sender_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment='发送者ID（对应patient_id或nurse_id，ai固定为0，system固定为-1）'
    )

    # 消息内容
    content: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment='消息内容（文本内容）'
    )
    message_type: Mapped[MessageType] = mapped_column(
        Enum(MessageType,values_callable=lambda e: [i.value for i in e]),
        nullable=False,
        default=MessageType.TEXT,
        comment='消息类型：text=文本, image=图片, voice=语音, file=文件, system=系统消息'
    )
    file_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        comment='文件URL（如果是媒体消息）'
    )

    # 已读状态
    is_read: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        comment='是否已读：0=未读, 1=已读'
    )
    read_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=False),
        nullable=True,
        comment='阅读时间'
    )
    read_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment='阅读者用户ID'
    )
    read_by_role: Mapped[Optional[ReaderRole]] = mapped_column(
        Enum(ReaderRole, values_callable=lambda e: [i.value for i in e]),
        nullable=True,
        comment='阅读者角色'
    )

    # 聊天模式
    chat_mode: Mapped[ChatMode] = mapped_column(
        Enum(ChatMode,values_callable=lambda e: [i.value for i in e]),
        nullable=False,
        default=ChatMode.AI,
        comment='发送时的聊天模式：AI=AI模式, assist=协助模式, nurseType=护士接管模式'
    )

    # 时间戳 - 只有create_time，消息不应该被更新
    create_time: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
        server_default=func.now(),
        comment='创建时间'
    )

    # 关系
    session: Mapped["ConversationSession"] = relationship(
        back_populates="messages",
        lazy="selectin"
    )

    def __repr__(self):
        return f"<Message(message_id={self.message_id}, session_uuid={self.session_uuid}, sender={self.sender_type})>"