from sqlalchemy.orm import Session
from sqlalchemy import desc
from sql.ckd_model import CkdPredictionRecord, CkdPredictionFile, PatientCkdRiskRecord
from datetime import date
from sqlalchemy import cast, Date


# ====================== 1. 创建 CKD 预测记录（最常用） ======================
def create_ckd_prediction(
        db: Session,
        user_id: int,
        request_data: dict,  # 前端传过来的完整参数
        result_data: dict  # AI 预测返回的结果
):
    # 创建主记录
    db_record = CkdPredictionRecord(
        user_id=user_id,
        # 请求字段
        model_type=request_data.get("model_type"),
        horizon=request_data.get("horizon"),
        age=request_data.get("age"),
        sex=request_data.get("sex"),
        bmi=request_data.get("bmi"),
        hba1c=request_data.get("hba1c"),
        tc=request_data.get("tc"),
        ldl=request_data.get("ldl"),
        hdl=request_data.get("hdl"),
        k=request_data.get("k"),
        creat=request_data.get("creat"),
        use_insulin=request_data.get("use_insulin"),
        stroke=request_data.get("stroke"),
        smoke=request_data.get("smoke"),
        anti_ht=request_data.get("anti_ht"),
        angio=request_data.get("angio"),
        other_dm=request_data.get("other_dm"),
        whr=request_data.get("whr"),
        fpg=request_data.get("fpg"),
        sbp=request_data.get("sbp"),
        dbp=request_data.get("dbp"),
        foot_prob=request_data.get("foot_prob"),
        eye_prob=request_data.get("eye_prob"),

        # 结果字段
        model_key=result_data.get("model_key"),
        predicted_probability=result_data.get("predicted_probability"),
        predicted_risk_percent=result_data.get("predicted_risk_percent"),
        population_percentile=result_data.get("population_percentile"),
        risk_group=result_data.get("risk_group"),
        risk_2y_probability=result_data.get("risk_2y_probability"),
        risk_2y_percent=result_data.get("risk_2y_percent"),
        risk_5y_probability=result_data.get("risk_5y_probability"),
        risk_5y_percent=result_data.get("risk_5y_percent"),
    )

    db.add(db_record)
    db.commit()
    db.refresh(db_record)

    # 如果有图片信息，创建文件记录
    if all(k in result_data for k in ["image_id", "bucket", "key", "s3_path"]):
        db_file = CkdPredictionFile(
            record_id=db_record.id,
            image_id=result_data.get("image_id"),
            bucket=result_data.get("bucket"),
            key=result_data.get("key"),
            s3_path=result_data.get("s3_path"),
        )
        db.add(db_file)
        db.commit()

    return db_record


# ====================== 2. 查询【当前用户最新一条】记录（最需要的） ======================
def get_latest_ckd_prediction_by_user(db: Session, user_id: int):
    return (
        db.query(CkdPredictionRecord)
        .filter(CkdPredictionRecord.user_id == user_id)
        .order_by(desc(CkdPredictionRecord.create_time))
        .first()
    )


# ====================== 3. 查询用户所有历史记录（可选） ======================
def get_all_ckd_predictions_by_user(db: Session, user_id: int, skip: int = 0, limit: int = 10):
    return (
        db.query(CkdPredictionRecord)
        .filter(CkdPredictionRecord.user_id == user_id)
        .order_by(desc(CkdPredictionRecord.create_time))
        .offset(skip)
        .limit(limit)
        .all()
    )


# ====================== 4. 根据记录ID查询单条详情 ======================
def get_ckd_prediction_by_id(db: Session, record_id: int):
    return db.query(CkdPredictionRecord).filter(CkdPredictionRecord.id == record_id).first()


# ====================== 5. 删除单条记录 ======================
def delete_ckd_prediction(db: Session, record_id: int):
    record = db.query(CkdPredictionRecord).filter(CkdPredictionRecord.id == record_id).first()
    if record:
        db.delete(record)
        db.commit()
    return record


# ====================== 6. 更新记录（极少用） ======================
def update_ckd_prediction(db: Session, record_id: int, update_data: dict):
    record = db.query(CkdPredictionRecord).filter(CkdPredictionRecord.id == record_id).first()
    if not record:
        return None
    for key, value in update_data.items():
        setattr(record, key, value)
    db.commit()
    db.refresh(record)
    return record

# ====================== 查询：最新1条 CKD 记录 + 关联文件表所有字段 ======================
def get_latest_ckd_with_file(db: Session, user_id: int):
    """
    连表查询：
    - ckd_prediction_record（主表）
    - ckd_prediction_file（文件表，全部字段）
    返回最新一条，没有则返回 None
    """
    return (
        db.query(CkdPredictionRecord, CkdPredictionFile)
        .outerjoin(CkdPredictionFile, CkdPredictionRecord.id == CkdPredictionFile.record_id)
        .filter(CkdPredictionRecord.user_id == user_id)
        .order_by(desc(CkdPredictionRecord.create_time))
        .first()
    )

# ===== 正在使用的函数 =====
def create_patient_ckd_prediction(
    db: Session,
    patient_id: int,
    age: int,
    sex: str,
    bmi: float,
    whr: float,
    hba1c: float,
    tc: float,
    ldl: float,
    hdl: float,
    k: float,
    creat: float,
    fpg: float,
    sbp: float,
    dbp: float,
    use_insulin: bool,
    stroke: bool,
    smoke: bool,
    anti_ht: bool,
    angio: bool,
    other_dm: bool,
    foot_prob: bool,
    eye_prob: bool,
    test_date: date,
    model_type: str = "Full",
    risk_group: str = None,
    risk_2y_percent: float = None,
    risk_5y_percent: float = None,
    population_percentile: float = None,
    image_url: str = None
):
    # ✅ 安全赋值写法，0 警告
    record = PatientCkdRiskRecord()

    record.patient_id = patient_id
    record.age = age
    record.sex = sex
    record.bmi = bmi
    record.whr = whr
    record.hba1c = hba1c
    record.tc = tc
    record.ldl = ldl
    record.hdl = hdl
    record.k = k
    record.creat = creat
    record.fpg = fpg
    record.sbp = sbp
    record.dbp = dbp
    record.use_insulin = use_insulin
    record.stroke = stroke
    record.smoke = smoke
    record.anti_ht = anti_ht
    record.angio = angio
    record.other_dm = other_dm
    record.foot_prob = foot_prob
    record.eye_prob = eye_prob
    record.test_date = test_date
    record.model_type = model_type
    record.risk_group = risk_group
    record.risk_2y_percent = risk_2y_percent
    record.risk_5y_percent = risk_5y_percent
    record.population_percentile = population_percentile
    record.image_url = image_url

    db.add(record)
    db.commit()
    db.refresh(record)
    return record

# 根据 患者ID + 日期 获取当天最新 CKD 记录
def get_latest_ckd_by_patient_and_date(db: Session, patient_id: int, test_date: date):
    return db.query(PatientCkdRiskRecord)\
        .filter(PatientCkdRiskRecord.patient_id == patient_id)\
        .filter(PatientCkdRiskRecord.test_date == test_date)\
        .order_by(PatientCkdRiskRecord.id.desc())\
        .first()

# 根据 患者ID + 日期 获取当天所有 CKD 记录
def get_all_ckd_by_patient_and_date(db: Session, patient_id: int, test_date: date):
    return db.query(PatientCkdRiskRecord)\
        .filter(PatientCkdRiskRecord.patient_id == patient_id)\
        .filter(PatientCkdRiskRecord.test_date == test_date)\
        .order_by(PatientCkdRiskRecord.id.desc())\
        .all()

# 按【时间段】获取 CKD 记录（支持灵活条件）
def get_ckd_by_date_range(
    db: Session,
    patient_id: int,
    start_date: date | None = None,
    end_date: date | None = None
):
    query = db.query(PatientCkdRiskRecord).filter(PatientCkdRiskRecord.patient_id == patient_id)

    if start_date is not None:
        query = query.filter(cast(PatientCkdRiskRecord.create_time, Date) >= start_date)
    if end_date is not None:
        query = query.filter(cast(PatientCkdRiskRecord.create_time, Date) <= end_date)

    return query.order_by(PatientCkdRiskRecord.create_time.desc()).all()

def get_ckd_by_date_range_paginated(
    db: Session,
    patient_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = 1,
    page_size: int = 5
):
    query = db.query(PatientCkdRiskRecord).filter(
        PatientCkdRiskRecord.patient_id == patient_id
    )

    if start_date is not None:
        query = query.filter(cast(PatientCkdRiskRecord.create_time, Date) >= start_date)
    if end_date is not None:
        query = query.filter(cast(PatientCkdRiskRecord.create_time, Date) <= end_date)

    total = query.count()
    records = query.order_by(PatientCkdRiskRecord.create_time.desc())\
                   .offset((page - 1) * page_size)\
                   .limit(page_size)\
                   .all()
    return total, records