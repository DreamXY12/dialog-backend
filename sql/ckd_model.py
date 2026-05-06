from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime

Base = declarative_base()

# ====================== CKD 预测主表（已加 user_id） ======================
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
class CkdPredictionFile(Base):
    __tablename__ = "ckd_prediction_file"

    id = Column(Integer, primary_key=True, autoincrement=True, comment="文件ID")
    record_id = Column(Integer, ForeignKey("ckd_prediction_record.id"), comment="预测记录ID")
    image_id = Column(String(64), comment="图片唯一ID")
    bucket = Column(String(128), comment="S3存储桶")
    key = Column(Text, comment="文件路径")
    s3_path = Column(Text, comment="完整S3路径")

    prediction = relationship("CkdPredictionRecord", back_populates="file_info")