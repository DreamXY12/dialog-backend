from sqlalchemy import Date, cast
from datetime import date
from sqlalchemy.orm import Session
from .people_models import Case

# 根据 user_id + 日期（date）获取当天所有糖尿病风险记录
def get_diabetes_records_by_user_and_date(
    db: Session,
    user_id: int,
    query_date: date  # 传入 date 类型，如 date.today()
):
    return db.query(Case)\
        .filter(Case.user_id == user_id)\
        .filter(cast(Case.create_time, Date) == query_date)\
        .order_by(Case.case_id.desc())\
        .all()

# 2. 按【时间段】获取糖尿病记录（支持灵活条件）
def get_diabetes_by_date_range(
    db: Session,
    user_id: int,
    start_date: date | None = None,
    end_date: date | None = None
):
    query = db.query(Case).filter(Case.user_id == user_id)

    if start_date is not None:
        query = query.filter(cast(Case.create_time, Date) >= start_date)
    if end_date is not None:
        query = query.filter(cast(Case.create_time, Date) <= end_date)

    return query.order_by(Case.create_time.desc()).all()

def get_diabetes_by_date_range_paginated(
    db: Session,
    user_id: int,
    start_date: date | None = None,
    end_date: date | None = None,
    page: int = 1,
    page_size: int = 5
):
    query = db.query(Case).filter(Case.user_id == user_id)

    if start_date is not None:
        query = query.filter(cast(Case.create_time, Date) >= start_date)
    if end_date is not None:
        query = query.filter(cast(Case.create_time, Date) <= end_date)

    total = query.count()
    records = query.order_by(Case.create_time.desc())\
                   .offset((page - 1) * page_size)\
                   .limit(page_size)\
                   .all()
    return total, records