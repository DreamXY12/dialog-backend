from sqlalchemy.orm import Session
from sqlalchemy import desc
from sql.ckd_model import CkdPredictionRecord, CkdPredictionFile


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