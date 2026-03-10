'''
@author: george 
@email: george6.lu@polyu.edu.hk
@date: 16 May 2023
@description: the module defines database crud operation functions
'''
from typing import Union

from sqlalchemy import select, update, desc, JSON, func, text
from sql.start import engine, Base
from sql.models import User, Query, Session, Invitation
from sql.people_models import Case
from sqlalchemy.orm import Session as Connection
from datetime import datetime

'''clean work space'''
def init_models():
    # 只创建表，不删除表
    # 这样可以保留数据库中的数据
    
    # 创建所有表（如果不存在）
    Base.metadata.create_all(engine)
    print("数据库表初始化完成")

'''
invitation code operation
'''

def get_invitation_by_code(db: Connection, code: str) -> Invitation:
     
    stmt = (
         select(Invitation)\
         .where(Invitation.code == code)
     )
    result = db.execute(stmt)
    return result.scalar()

def set_invitation_status(db: Connection, inv: Invitation, s: bool) -> None:
    inv.status = s
    try:
        db.commit()
    except Exception as e:
        db.rollback()
        raise e

def get_n_users(db: Connection, code:str) -> int:
    rows = db.query(User).where(User.code == code).count()
    return rows


'''user operations'''

def get_user_by_id(db: Connection, user_id: int):
    
    stmt = (
        select(User)\
        .where(User.user_id == user_id)
    )
    result = db.execute(stmt)
    return result.scalar()


def get_user_by_username(db: Connection, username: str):

    result = db.query(User)\
        .filter(User.username == username)\
        .first()
    return result


def create_user(db: Connection, user: User):
        
    db.add(user)

    try:
        db.commit()
        return user
    except Exception as e:
        db.rollback()
        raise e


'''case operation'''

def create_case(db: Connection, case: Case):
    
    db.add(case)
    try:
        db.commit()
        return case
    except Exception as e:
        db.rollback()
        raise e

def get_cases_by_user(db: Connection, user):
    # 根据用户类型获取用户ID
    if hasattr(user, 'user_id'):
        user_id = user.user_id
    elif hasattr(user, 'patient_id'):
        user_id = user.patient_id
    elif hasattr(user, 'nurse_id'):
        user_id = user.nurse_id
    else:
        raise ValueError("Invalid user type")
    
    stmt = (
        select(Case.case_id, Case.test_date, Case.create_time, Case.time_spec, Case.analysis_result, Case.score,
               Case.hba1c, Case.fasting_glucose, Case.hdl_cholesterol, 
               Case.total_cholesterol, Case.ldl_cholesterol, Case.creatinine, 
               Case.triglyceride, Case.potassium)\
        .where(Case.user_id == user_id)\
        .order_by(Case.create_time.desc())\
    )
    result = db.execute(stmt)

    return result.all()



def get_case_by_id(db: Connection, case_id: int):
    
    stmt = (
        select(Case)
        .where(Case.case_id == case_id)
        )
    result = db.execute(stmt)
    return result.scalar()


def get_latest_case(db: Connection, user_id: int):
    '''return the latest case of the user'''
    result = db.query(Case)\
        .filter(Case.user_id == user_id)\
        .order_by(desc(Case.case_id))\
        .first()
    return result

def get_latest_session(db: Connection, user_id: int):
    result = db.query(Session)\
        .filter(Session.user_id == user_id)\
        .order_by(desc(Session.session_key))\
        .first()
    return result

# 用于获取病人的对话，这里修改了，user_id指的是用户独一无二的登录码，原来是user表的主键
def get_latest_session_new(db: Connection, user_id: int):
    result = db.query(Session)\
        .filter(Session.user_id == user_id)\
        .order_by(desc(Session.session_key))\
        .first()
    return result


def update_case_result(db: Connection, case: Case, result: str) -> Case:

    case.analysis_result = result
    try:
        db.commit()
        return case
    except Exception as e:
        db.rollback()
        raise e
        
'''session operation'''

def create_session(db: Connection, session: Session) -> Session:
    '''
    add a new session to database
    '''
        
    db.add(session)
    try:
        db.commit()
        return session
    except Exception as e:
        db.rollback()
        raise e
        
def get_session_by_key(db: Connection, session_key: str) -> Session:
    return db.query(Session)\
        .filter(Session.session_key == session_key)\
        .first()

def update_prompts(db: Connection, session: Session, json_data: JSON):
    session.prompts = json_data
    try:
        db.commit()
        return session
    except Exception as e:
        db.rollback()
        raise e


'''query operation'''

def  create_query(db: Connection, query: Query):
    db.add(query)
    try:
        db.commit()
        return query
    except Exception as e:
        db.rollback()
        raise e

def update_response(db: Connection, query: Query, response: str):
    query.response = response
    try:
        db.commit()
        return query
    except Exception as e:
        db.rollback()
        raise e
    
def get_queries_by_session(db: Connection, session_key: str):
    result = db.query(Query)\
            .filter(Query.session_key == session_key)\
            .all()
    return result

def get_total_queries(db: Connection, user) -> int:
    # 根据用户类型获取用户ID
    if hasattr(user, 'user_id'):
        user_id = user.user_id
    elif hasattr(user, 'patient_id'):
        user_id = user.patient_id
    elif hasattr(user, 'nurse_id'):
        user_id = user.nurse_id
    else:
        raise ValueError("Invalid user type")
    
    rows = db.query(Session, Query)\
    .filter(Session.user_id == user_id)\
    .filter(Query.session_key == Session.session_key)\
    .count()
    return rows

def get_case_by_closest_date(db: Connection, date_str: str, user_id: int) -> Case:
    date = datetime.fromisoformat(date_str)
    rows = db.query(Case)\
        .filter(Case.user_id == user_id)\
        .order_by(func.abs(func.datediff(date, Case.labtest_date)))
    return rows.first()
