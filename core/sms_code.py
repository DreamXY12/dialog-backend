# 利用亚马逊SNS发送短信（只能用于中国香港，中国大陆无法使用）

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
import random

# 导入数据库模型（请确认路径正确）
from sql.people_models import SmsVerificationCode

# ---------------------------
# 1. 沙盒模式核心配置（关键！）
# ---------------------------
# AWS 配置（自动读取 ~/.aws/credentials 中的配置）
AWS_REGION = "ap-southeast-1"  # 你配置的区域
SNS_SANDBOX_MODE = True  # 开启沙盒模式
# 沙盒模式下必须配置已验证的测试手机号（在AWS控制台验证后填入）
SANDBOX_TEST_PHONES = [
    "+85269714291",  # 替换为你在AWS验证的香港测试手机号
    "+85294839076"
]

# 验证码规则
VERIFY_CODE_LENGTH = 6  # 6位数字验证码
VERIFY_CODE_EXPIRE_HOURS = 1  # 有效期1小时
VERIFY_CODE_EXPIRE_MINUTES = 5 # 有效期5分鐘
VERIFY_CODE_SEND_INTERVAL = 60  # 防刷间隔：60秒
SNS_SENDER_ID = "OPT"  # 沙盒模式下可随意填（无需审核）

# 初始化AWS SNS客户端（自动加载本地配置）
try:
    sns_client = boto3.client("sns", region_name=AWS_REGION)
except NoCredentialsError:
    sns_client = None


# ---------------------------
# 2. 核心工具函数
# ---------------------------
def generate_verify_code() -> str:
    """生成6位数字验证码"""
    return ''.join(random.choices('0123456789', k=VERIFY_CODE_LENGTH))


def check_send_frequency(db: Session, phone: str, role: str, mode: str) -> bool:
    """检查60秒内是否重复发送（防刷）- 完全适配数据库字段"""
    # 时间阈值：当前时间往前推60秒
    time_threshold = datetime.now() - timedelta(seconds=VERIFY_CODE_SEND_INTERVAL)
    # 转换为MySQL TIMESTAMP格式（兼容时区）
    time_threshold = time_threshold.replace(tzinfo=None)

    recent_code = db.query(SmsVerificationCode).filter(
        SmsVerificationCode.phone == phone,
        SmsVerificationCode.role == role,
        SmsVerificationCode.mode == mode,
        SmsVerificationCode.create_time >= time_threshold,
        SmsVerificationCode.is_used == False  # 仅检查未使用的验证码
    ).first()
    return recent_code is None


def validate_sandbox_phone(phone: str) -> bool:
    """沙盒模式：校验手机号是否已在AWS验证"""
    if not SNS_SANDBOX_MODE:
        return True
    return phone in SANDBOX_TEST_PHONES


def send_sms_via_sns_sandbox(phone: str, code: str) -> dict:
    """沙盒模式下发送短信（仅支持已验证手机号）"""
    if not sns_client:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="AWS SNS客户端初始化失败，请检查本地aws configure配置"
        )

    # 沙盒模式短信内容（需包含【TEST】标识，AWS要求）
    sms_message = f"【TEST】Your verification code: {code} (Valid for {VERIFY_CODE_EXPIRE_MINUTES} minutes). 您的验证码：{code}（有效期{VERIFY_CODE_EXPIRE_MINUTES}分鐘）。"

    try:
        # 沙盒模式发送短信（自动使用本地AWS凭证）
        response = sns_client.publish(
            PhoneNumber=phone,
            Message=sms_message,
            MessageAttributes={
                'AWS.SNS.SMS.SMSType': {
                    'DataType': 'String',
                    'StringValue': 'Transactional'  # 交易类短信
                },
                'AWS.SNS.SMS.SenderID': {
                    'DataType': 'String',
                    'StringValue': SNS_SENDER_ID
                }
            }
        )
        return {
            "success": True,
            "message_id": response["MessageId"],
            "phone": phone,
            "sandbox_mode": True
        }
    except ClientError as e:
        error_code = e.response['Error']['Code']
        error_msg = e.response['Error']['Message']
        # 沙盒模式专属错误提示
        if error_code == "InvalidParameter":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"沙盒模式仅支持已验证手机号：{SANDBOX_TEST_PHONES}，请在AWS控制台验证手机号后重试"
            )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"AWS SNS发送失败：{error_code} - {error_msg}"
        )


# ---------------------------
# 3. 主业务函数（对外暴露）
# ---------------------------
def send_verification_code(
        db: Session,
        phone: str,
        role: str,  # patient/nurse
        mode: str,  # login/register
        mock: bool = False  # 模拟发送（无需AWS）
) -> dict:
    """
    发送验证码（适配沙盒模式）
    :param mock: True=仅存储不发送（测试用），False=调用AWS SNS
    """
    # Step 1: 基础校验
    if not phone or not phone.startswith("+"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="手机号必须以国际区号开头（如+85212345678）"
        )
    if role not in ["patient", "nurse"]:
        raise HTTPException(status_code=400, detail="角色仅支持patient/nurse")
    if mode not in ["login", "register"]:
        raise HTTPException(status_code=400, detail="用途仅支持login/register")

    # Step 2: 沙盒模式校验（仅允许已验证手机号）
    if SNS_SANDBOX_MODE and not validate_sandbox_phone(phone):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"沙盒模式下仅支持发送至已验证手机号：{SANDBOX_TEST_PHONES}"
        )

    # Step 3: 防刷校验
    if not check_send_frequency(db, phone, role, mode):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"验证码发送过于频繁，请{VERIFY_CODE_SEND_INTERVAL}秒后再试"
        )

    # Step 4: 生成验证码
    code = generate_verify_code()

    # 计算过期时间（示例：5分钟过期，匹配数据库注释）
    expire_at = datetime.now() + timedelta(minutes=5)
    # 转换为TIMESTAMP格式（兼容MySQL）
    expire_at = expire_at.replace(tzinfo=None)

    # Step 5: 存储验证码到数据库
    # expire_at = datetime.now() + timedelta(hours=VERIFY_CODE_EXPIRE_HOURS)
    new_code = SmsVerificationCode(
        phone=phone,
        code=code,
        role=role,
        mode=mode,
        expire_at=expire_at,
        is_used=False,
        create_time=datetime.now(),
    )
    db.add(new_code)
    db.commit()
    db.refresh(new_code)

    # Step 6: 发送短信（模拟/真实）
    if mock:
        # 模拟发送（无AWS依赖，测试用）
        return {
            "success": True,
            "message": f"【模拟发送】验证码已生成：{code}（有效期{VERIFY_CODE_EXPIRE_HOURS}小时）",
            "phone": phone,
            "sandbox_mode": SNS_SANDBOX_MODE,
            "test_code": code  # 测试用，生产环境删除
        }
    else:
        # 沙盒模式真实发送
        sns_response = send_sms_via_sns_sandbox(phone, code)
        print("沙盒模式发送验证码!")
        return {
            "success": True,
            "message": f"验证码{code}已发送至{phone}（沙盒模式），有效期{VERIFY_CODE_EXPIRE_HOURS}小时",
            "phone": phone,
            "message_id": sns_response["message_id"],
            "sandbox_mode": True
        }