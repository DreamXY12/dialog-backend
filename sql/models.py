from sqlalchemy import Boolean, Column, ForeignKey, Integer, String, DateTime, Date, Float, JSON, Text, Double
from sqlalchemy.orm import (
    relationship,
    Mapped,
    mapped_column,
    DeclarativeBase
)
from sqlalchemy.sql import func
from sql.start import Base
from typing import Optional, Any, List

class TimeStampMixIn(object):
    '''
    create time and update time mix in.
    '''
    create_time = mapped_column(DateTime(timezone=True), server_default=func.now())
    update_time = mapped_column(DateTime(timezone=True), onupdate=func.now())

class Invitation(TimeStampMixIn, Base):
    __tablename__ = 'invitation_code'

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    status: Mapped[Boolean] = mapped_column(Boolean, default=True) # if the code is still available
    tag: Mapped[Optional[str]] = mapped_column(String(255))# the extra information for the code, like the target user
    # dependencies
    users: Mapped["User"] = relationship(
        back_populates="invitation_code",
        cascade="all, delete-orphan"
    )

class User(TimeStampMixIn, Base):
    __tablename__ = 'user'

    user_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    identity: Mapped[Optional[str]] = mapped_column(String(100)) # identify of the user, could be doctor, patients.
    code: Mapped[int] = mapped_column(ForeignKey("invitation_code.code"))
    username: Mapped[Optional[str]] = mapped_column(String(255), unique=True)
    hashed_password: Mapped[Optional[str]] = mapped_column(String(255))
    date_of_birth: Mapped[Optional[Date]]= mapped_column(Date)
    sex: Mapped[Optional[str]] = mapped_column(String(10))
    family_history: Mapped[Optional[str]] = mapped_column(String(255))
    smoking_status: Mapped[Optional[str]] = mapped_column(String(255))
    drinking_history: Mapped[Optional[str]] = mapped_column(String(255))
    height: Mapped[Optional[float]] = mapped_column(Double)
    weight: Mapped[Optional[float]] = mapped_column(Double)

    invitation_code: Mapped["Invitation"] = relationship(back_populates="users")
    
    sessions: Mapped["Session"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan"
    )
    
    evaluation_results: Mapped["DoctorResponse"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan"
    )
    
    evaluation_scores: Mapped["DoctorScore"] = relationship(
        back_populates="user",
        cascade="all, delete-orphan"
    )


class Case(TimeStampMixIn,Base):
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


class Session(TimeStampMixIn, Base):
    __tablename__ = 'session'

    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user.user_id"))
    session_key: Mapped[str] = mapped_column(String(255), primary_key=True, index=True, unique=True)
    status: Mapped[bool] = False
    prompts = Column(JSON, nullable=True)

    user: Mapped["User"] = relationship(back_populates="sessions")
    queries: Mapped["Query"] = relationship(back_populates="session")


class Query(TimeStampMixIn, Base):
    __tablename__ = 'query'

    query_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    session_key: Mapped[int] =  mapped_column(ForeignKey("session.session_key"))
    enquiry: Mapped[Text] = mapped_column(Text)
    response: Mapped[Optional[Text]] = mapped_column(Text)
    session: Mapped["Session"] = relationship(back_populates="queries")
    
class DoctorResponse(TimeStampMixIn, Base):
    __tablename__ = "doctor_response"
    
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user.user_id"))
    eval_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    
    query: Mapped[Text] = mapped_column(Text)
    response: Mapped[Optional[Text]] = mapped_column(Text)
    user: Mapped["User"] = relationship(back_populates="evaluation_results")
    
class DoctorScore(TimeStampMixIn, Base):
    __tablename__ = "doctor_score"
    
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user.user_id"))
    score_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True, index=True)
    
    query: Mapped[Text] = mapped_column(Text)
    response: Mapped[Text] = mapped_column(Text)
    score: Mapped[Optional[int]] = mapped_column(Integer)
    user: Mapped["User"] = relationship(back_populates="evaluation_scores")