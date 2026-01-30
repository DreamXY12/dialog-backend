from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime, Date, Float, DECIMAL, Enum
from sqlalchemy.orm import relationship, Mapped, mapped_column
from sqlalchemy.sql import func
from typing import Optional
import enum
from sql.start import Base

class TimeStampMixIn(object):
    '''
    create time and update time mix in.
    '''
    create_time = mapped_column(DateTime(timezone=True), server_default=func.now())
    update_time = mapped_column(DateTime(timezone=True), onupdate=func.now())


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
    sex: Mapped[Optional[str]] = mapped_column(Enum(Gender), nullable=True)
    family_history: Mapped[Optional[str]] = mapped_column(Enum(FamilyHistory), nullable=True)
    smoking_status: Mapped[Optional[str]] = mapped_column(Enum(SmokingStatus), nullable=True)
    drinking_history: Mapped[Optional[str]] = mapped_column(Enum(DrinkingFrequency), nullable=True)
    height: Mapped[Optional[float]] = mapped_column(DECIMAL(5, 2), nullable=True)
    weight: Mapped[Optional[float]] = mapped_column(DECIMAL(5, 2), nullable=True)

    # 外键
    assigned_nurse_id: Mapped[Optional[int]] = mapped_column(ForeignKey("nurse.nurse_id"), nullable=True)

    # 关系
    nurse: Mapped[Optional["Nurse"]] = relationship(back_populates="patients")