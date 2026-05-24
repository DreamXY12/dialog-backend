from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text,Index, Date
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship,Mapped, mapped_column
from sql.people_models import TimeStampMixIn
from datetime import datetime,date
from typing import Optional

Base = declarative_base()

# ====================== CKD 预测主表（已加 user_id） ======================
# ====== 已废弃，但表还在 ========
class CkdPredictionRecord(Base):
    __tablename__ = "ckd_prediction_record"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="预测记录ID")
    user_id = Column(Integer, index=True, nullable=False, comment="用户ID（用于区分用户）")  
    request_id = Column(String(64), unique=True, index=True, comment="请求唯一ID，可选")

    # 请求入参
    model_type = Column(String(20), comment="模型版本")
    horizon = Column(String(10), comment="预测年限")
    age = Column(Integer, comment="年龄")
    sex = Column(String(10), comment="性别")
    bmi = Column(Float, comment="身体质量指数")
    hba1c = Column(Float, comment="糖化血红蛋白")
    tc = Column(Float, comment="总胆固醇")
    ldl = Column(Float, comment="低密度脂蛋白胆固醇")
    hdl = Column(Float, comment="高密度脂蛋白胆固醇")
    k = Column(Float, comment="钾")
    creat = Column(Float, comment="肌酐")
    use_insulin = Column(Boolean, default=False, comment="是否使用胰岛素")
    stroke = Column(Boolean, default=False, comment="中风病史")
    smoke = Column(Boolean, default=False, comment="是否吸烟")
    anti_ht = Column(Boolean, default=False, comment="是否使用降压药")
    angio = Column(Boolean, default=False, comment="心绞痛/冠心病史")
    other_dm = Column(Boolean, default=False, comment="糖尿病合并症")
    whr = Column(Float, comment="腰臀比")
    fpg = Column(Float, comment="空腹血糖")
    sbp = Column(Float, comment="收缩压")
    dbp = Column(Float, comment="舒张压")
    foot_prob = Column(Boolean, default=False, comment="糖尿病足问题")
    eye_prob = Column(Boolean, default=False, comment="糖尿病眼部问题")

    # 预测结果
    model_key = Column(String(32), comment="模型标识")
    predicted_probability = Column(Float, comment="预测概率")
    predicted_risk_percent = Column(Float, comment="风险百分比")
    population_percentile = Column(Float, comment="人群百分位")
    risk_group = Column(String(20), comment="风险等级")
    risk_2y_probability = Column(Float, comment="2年风险概率")
    risk_2y_percent = Column(Float, comment="2年风险百分比")
    risk_5y_probability = Column(Float, comment="5年风险概率")
    risk_5y_percent = Column(Float, comment="5年风险百分比")

    # 时间
    create_time = Column(DateTime, default=datetime.now, comment="创建时间")
    update_time = Column(DateTime, default=datetime.now, onupdate=datetime.now, comment="更新时间")

    # 关联文件表
    file_info = relationship("CkdPredictionFile", back_populates="prediction", uselist=False)


# ====================== CKD 预测文件表 ======================
# ===== 已废弃，但表还在 =====
class CkdPredictionFile(Base):
    __tablename__ = "ckd_prediction_file"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="文件ID")
    record_id = Column(Integer, ForeignKey("ckd_prediction_record.id"), comment="预测记录ID")
    image_id = Column(String(64), comment="图片唯一ID")
    bucket = Column(String(128), comment="S3存储桶")
    key = Column(Text, comment="文件路径")
    s3_path = Column(Text, comment="完整S3路径")

    prediction = relationship("CkdPredictionRecord", back_populates="file_info")


# ====== CKD表，真正的使用的，里面包含了AI生成图的路径 =====
class PatientCkdRiskRecord(TimeStampMixIn, Base):
    """
    CKD 肾病风险检测记录表
    对应：/ai/ckd_predict
    """
    __tablename__ = "patient_ckd_risk_record"
    __table_args__ = (
        Index("idx_patient_date", "patient_id", "test_date"),
        {
            "comment": "CKD肾病风险检测记录",
            "mysql_engine": "InnoDB",
            "mysql_charset": "utf8mb4",
            "mysql_collate": "utf8mb4_unicode_ci",
        },
    )

    # 主键
    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="自增ID"
    )

    # 关联患者
    patient_id: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="患者ID（对应用户表）"
    )

    # 基础信息
    age: Mapped[int] = mapped_column(Integer, comment="年龄")
    sex: Mapped[str] = mapped_column(String(10), comment="性别：Male/Female")
    bmi: Mapped[float] = mapped_column(Float, comment="身体质量指数")
    whr: Mapped[float] = mapped_column(Float, comment="腰臀比")

    # 血液/生化指标
    hba1c: Mapped[float] = mapped_column(Float, comment="糖化血红蛋白")
    tc: Mapped[float] = mapped_column(Float, comment="总胆固醇")
    ldl: Mapped[float] = mapped_column(Float, comment="低密度脂蛋白胆固醇")
    hdl: Mapped[float] = mapped_column(Float, comment="高密度脂蛋白胆固醇")
    k: Mapped[float] = mapped_column(Float, comment="血钾")
    creat: Mapped[float] = mapped_column(Float, comment="肌酐")
    fpg: Mapped[float] = mapped_column(Float, comment="空腹血糖")
    sbp: Mapped[float] = mapped_column(Float, comment="收缩压")
    dbp: Mapped[float] = mapped_column(Float, comment="舒张压")

    # 病史/行为
    use_insulin: Mapped[bool] = mapped_column(Boolean, default=False, comment="使用胰岛素")
    stroke: Mapped[bool] = mapped_column(Boolean, default=False, comment="中风")
    smoke: Mapped[bool] = mapped_column(Boolean, default=False, comment="吸烟")
    anti_ht: Mapped[bool] = mapped_column(Boolean, default=False, comment="高血压药物")
    angio: Mapped[bool] = mapped_column(Boolean, default=False, comment="心绞痛")
    other_dm: Mapped[bool] = mapped_column(Boolean, default=False, comment="其他糖尿病并发症")
    foot_prob: Mapped[bool] = mapped_column(Boolean, default=False, comment="足部问题")
    eye_prob: Mapped[bool] = mapped_column(Boolean, default=False, comment="眼部问题")

    # 检测结果
    test_date: Mapped[date] = mapped_column(Date, nullable=False, comment="检测日期")
    model_type: Mapped[Optional[str]] = mapped_column(String(20), comment="模型类型")
    risk_group: Mapped[Optional[str]] = mapped_column(String(20), comment="风险等级：low/medium/high")
    risk_2y_percent: Mapped[Optional[float]] = mapped_column(Float, comment="2年风险概率%")
    risk_5y_percent: Mapped[Optional[float]] = mapped_column(Float, comment="5年风险概率%")
    population_percentile: Mapped[Optional[float]] = mapped_column(Float, comment="人群百分位%")
    image_url: Mapped[Optional[str]] = mapped_column(String(512), comment="风险曲线图片地址")
