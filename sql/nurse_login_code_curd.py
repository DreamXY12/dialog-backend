from sqlalchemy.orm import Session
from .people_models import NurseLoginCode  # 按你项目路径导入
from .patient_login_code_curd import generate_4digit_code,hash_code,verify_code

# ------------------------------
# 护士：创建登录码（注册时用）
# ------------------------------
def create_nurse_login_code(db: Session, nurse_id: int) -> str:
    existing = db.query(NurseLoginCode).filter(NurseLoginCode.nurse_id == nurse_id).first()
    if existing:
        raise Exception("该护士已存在登录码")

    while True:
        plain_code = generate_4digit_code()
        code_hash = hash_code(plain_code)
        exists = db.query(NurseLoginCode).filter(NurseLoginCode.login_code_hash == code_hash).first()
        if not exists:
            break

    new_code = NurseLoginCode(
        nurse_id=nurse_id,
        login_code_hash=code_hash,
        is_active=True
    )
    db.add(new_code)
    db.commit()
    return plain_code

# ------------------------------
# 护士：重置登录码（忘记用）
# ------------------------------
def reset_nurse_login_code(db: Session, nurse_id: int) -> str:
    record = db.query(NurseLoginCode).filter(NurseLoginCode.nurse_id == nurse_id).first()
    if not record:
        return create_nurse_login_code(db, nurse_id)

    while True:
        new_code = generate_4digit_code()
        new_hash = hash_code(new_code)
        exists = db.query(NurseLoginCode).filter(NurseLoginCode.login_code_hash == new_hash).first()
        if not exists:
            break

    record.login_code_hash = new_hash
    db.commit()
    return new_code

# ------------------------------
# 护士：验证登录码（登录用）
# ------------------------------
def authenticate_nurse_code(db: Session, nurse_id: int, plain_code: str) -> bool:
    record = db.query(NurseLoginCode).filter(
        NurseLoginCode.nurse_id == nurse_id,
        NurseLoginCode.is_active == True
    ).first()
    if not record:
        return False
    return verify_code(plain_code, record.login_code_hash)