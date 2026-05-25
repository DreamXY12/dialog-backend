import random
import bcrypt
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from .people_models import PatientLoginCode  # 按你项目路径导入

# ------------------------------
# 1. 生成 4 位唯一数字码
# ------------------------------
def generate_4digit_code() -> str:
    """生成 0000~9999 之间的 4 位数字码"""
    return f"{random.randint(0, 9999):04d}"

# ------------------------------
# 2. 加密 4 位码（哈希）
# ------------------------------
def hash_code(plain_code: str) -> str:
    """明文 4 位码 → 加密哈希（不可逆）"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plain_code.encode("utf-8"), salt).decode("utf-8")

# ------------------------------
# 3. 验证登录码是否正确
# ------------------------------
def verify_code(plain_code: str, hashed_code: str) -> bool:
    """前端输入的码 vs 数据库哈希 → 返回是否正确"""
    return bcrypt.checkpw(plain_code.encode("utf-8"), hashed_code.encode("utf-8"))

# ------------------------------
# 4. 创建登录码（患者注册时调用）
# ------------------------------
def create_patient_login_code(db: Session, patient_id: int) -> str:
    """
    为患者创建永久 4 位登录码（无异常抛出，先查询后插入）
    :return: 明文 4 位码（只返回一次！）
    """
    # 第一步：先检查这个患者是否已经有登录码（一人一码）
    existing = db.query(PatientLoginCode).filter(PatientLoginCode.patient_id == patient_id).first()
    if existing:
        raise Exception("该患者已存在登录码，无法重复创建")

    # 第二步：循环生成 4 位码，直到找到数据库中【不存在】的唯一码
    plain_code = None
    while True:
        # 生成 4 位数字码
        plain_code = generate_4digit_code()

        # 查询数据库中是否已存在这个登录码（全局唯一）
        code_exists = db.query(PatientLoginCode).filter(
            PatientLoginCode.login_code_hash == hash_code(plain_code)).first()

        # 如果不存在，退出循环，使用这个码
        if not code_exists:
            break

    # 第三步：加密并插入数据库
    code_hash = hash_code(plain_code)
    login_code = PatientLoginCode(
        patient_id=patient_id,
        login_code_hash=code_hash,
        is_active=True
    )
    db.add(login_code)
    db.commit()

    # 只返回一次明文给前端
    return plain_code

# ------------------------------
# 5. 重置/更新登录码（忘记登录码用）
# ------------------------------
def reset_patient_login_code(db: Session, patient_id: int) -> str:
    """
    重置患者登录码（前端：忘记登录码）
    :return: 新的明文 4 位码
    """
    # 查询旧码
    code_record = db.query(PatientLoginCode).filter(PatientLoginCode.patient_id == patient_id).first()

    if not code_record:
        # 没有则创建
        return create_patient_login_code(db, patient_id)

    # 生成新码
    plain_code = generate_4digit_code()
    code_record.login_code_hash = hash_code(plain_code)

    db.commit()
    db.refresh(code_record)
    return plain_code

# ------------------------------
# 6. 验证患者登录（登录接口用）
# ------------------------------
def authenticate_patient_code(db: Session, patient_id: int, plain_code: str) -> bool:
    """患者登录时验证 4 位码"""
    code_record = db.query(PatientLoginCode).filter(
        PatientLoginCode.patient_id == patient_id,
        PatientLoginCode.is_active == True
    ).first()

    if not code_record:
        return False

    return verify_code(plain_code, code_record.login_code_hash)