# 验证码的操作单独拿出来

from datetime import datetime
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from typing import Optional, Tuple

# 导入你的验证码模型（确保路径正确）
from sql.people_models import SmsVerificationCode
# 导入枚举类（如果用了的话，也可以直接用字符串）
from sql.people_models import VerificationRole, VerificationMode

def verify_verification_code(
        db: Session,
        phone: str,
        code: str,
        role: str,  # 可选：替换为 VerificationRole 枚举
        mode: str,  # 可选：替换为 VerificationMode 枚举
        raise_exception: bool = True  # 是否抛出异常，False时返回布尔值
) -> bool:
    """
    验证短信验证码的核心函数
    :param db: 数据库会话
    :param phone: 带区号的手机号（如+85212345678）
    :param code: 6位数字验证码
    :param role: 用户角色："nurse" / "patient"
    :param mode: 使用场景："login" / "register"
    :param raise_exception: 验证失败时是否抛出HTTP异常（True=抛出，False=返回False）
    :return: 验证成功返回True，失败返回False（或抛出异常）
    """
    try:
        # --------------------------
        # 1. 前置参数校验（非数据库）
        # --------------------------
        # 校验手机号非空且格式基本合法（简单校验，可根据需求扩展）
        if not phone or not phone.strip():
            if raise_exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="手机号不能为空"
                )
            return False

        # 校验验证码为6位纯数字
        if not code or not code.strip() or len(code) != 6 or not code.isdigit():
            if raise_exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="请输入6位数字的验证码"
                )
            return False

        # 校验角色/用途合法性
        valid_roles = ["nurse", "patient"]
        valid_modes = ["login", "register"]
        if role not in valid_roles:
            if raise_exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="用户角色错误，仅支持nurse/patient"
                )
            return False

        if mode not in valid_modes:
            if raise_exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="验证码用途错误，仅支持login/register"
                )
            return False

        # --------------------------
        # 2. 数据库查询验证码记录
        # --------------------------
        verification_code: Optional[SmsVerificationCode] = db.query(SmsVerificationCode).filter(
            SmsVerificationCode.phone == phone,
            SmsVerificationCode.code == code,
            SmsVerificationCode.role == role,  # 关联枚举时：VerificationRole(role)
            SmsVerificationCode.mode == mode  # 关联枚举时：VerificationMode(mode)
        ).first()

        # --------------------------
        # 3. 多维度验证逻辑
        # --------------------------
        # 校验1：验证码记录是否存在
        if not verification_code:
            if raise_exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="验证码错误，请检查后重新输入"
                )
            return False

        # 校验2：验证码是否过期
        if datetime.now() > verification_code.expire_at:
            if raise_exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="验证码已过期，请重新获取"
                )
            return False

        # 校验3：验证码是否已使用
        if verification_code.is_used:
            if raise_exception:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="验证码已使用，请勿重复验证"
                )
            return False

        # --------------------------
        # 4. 验证通过：标记为已使用
        # --------------------------
        verification_code.is_used = True
        verification_code.used_at = datetime.now()  # 记录使用时间
        db.commit()
        db.refresh(verification_code)  # 可选：刷新记录

        return True

    except HTTPException:
        # 捕获已知的业务异常，直接抛出
        raise
    except Exception as e:
        # 捕获未知异常，回滚并返回/抛出
        db.rollback()
        if raise_exception:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"验证码验证失败：{str(e)}"
            )
        return False