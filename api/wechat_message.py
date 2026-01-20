import logging
from twilio.rest import Client
from fastapi import Request, APIRouter, HTTPException
from core.translate import to_other_language, user_input_to_internal_language, get_fixed_field_translation
from core.translate import get_fixed_response_translation
from core.translate import normalize_alcohol, normalize_yes_no, extract_local_context
from sql.cache_database import r, store_message, get_chat_history
from sql.start import get_db
import sql.crud as crud
from api.user import sign_up, CreateUser
from api.session import response_from_llm
from sql.models import Session, Query
from typing import Annotated
from fastapi import Depends
from sqlalchemy.orm import Session as Connection
import re
from datetime import datetime, timedelta
import uuid
from config import get_parameter
from enum import Enum

# 默认是繁体中文
is_en = False

# 配置参数
TWILIO_ACCOUNT_SID = get_parameter("twilio", "account_sid")
TWILIO_AUTH_TOKEN = get_parameter("twilio", "auth_token")
TWILIO_NUMBER = get_parameter("twilio", "phone_number")
DEBUG = get_parameter("dev", "debug") == "1"

router = APIRouter(prefix='/wechat', tags=["wechat"])

account_sid = TWILIO_ACCOUNT_SID
auth_token = TWILIO_AUTH_TOKEN
client = Client(account_sid, auth_token)

logging.basicConfig(
    level=logging.INFO,
    filename='dev.log',
    filemode='a',
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class RegistrationState(Enum):
    """注册状态枚举"""
    INITIAL = "initial"  # 初始状态
    CODE_REQUIRED = "code_required"  # 需要邀请码
    CODE_VERIFIED = "code_verified"  # 邀请码已验证，等待开始
    COLLECTING = "collecting"  # 收集信息中
    CONFIRMING = "confirming"  # 确认信息中
    COMPLETED = "completed"  # 注册完成

# 健康信息收集的问题
health_questions = [
    "What is your weight (kg)?",
    "What is your height in cm?",
    "What is your age?",
    "What is your sex? (Female/Male/Prefer not to tell)",
    "Do you have family history of diabetes? (Yes/No/Unknown)",
    "Do you smoke? (Yes/No/Prefer not to tell)",
    '''How often do you consume alcoholic beverages? You can choose from the following options:
Never
Rarely (a few times a year)
Occasionally (once a month)
Frequently (several times a week)
Daily
'''
]

health_questions_tchinese = [
    "你的體重是多少（公斤）？",
    "你的身高是多少公分？"
    "你的年齡是多少？",
    "你的性別是甚麼？（女／男／不願透露）",
    "你有糖尿病家族病史嗎？（是／否／未知）",
    "你有吸菸嗎？（是/否/不願透露）",
    '''你多久飲用一次含酒精飲品？你可以從以下選項中選擇：
從不
很少（一年幾次）
偶爾（每月一次）
頻繁地（每週數次）
每日
'''
]

# 错误提示信息
error_messages = [
    '''Sorry, I cannot understand you. What is your weight? You can say:" My weight is 78kg."''',
    '''Sorry, I cannot understand you. What is your height? You can say:" My height is 173cm."''',
    '''Sorry, I cannot understand you. What is your age? You can say:" 45"''',
    '''Sorry, I cannot understand you. What is your sex? You can say:" Female."''',
    '''Sorry, I cannot understand you. Do you have family history of diabetes? You can say:" Yes."''',
    '''Sorry, I cannot understand you. Do you smoke? You can say:" Yes."''',
    '''Sorry, I cannot understand you. How often do you consume alcoholic beverages? You can choose from the following: Never
Rarely (a few times a year)
Occasionally (once a month)
Frequently (several times a week)
Daily.
'''
]

error_messages_tchinese = [
    '''對不起，我無法理解你。你的體重是多少？你可以說：我的體重是78公斤。''',
    '''對不起，我無法理解你。你的身高是多少？你可以說：我的身高是173公分。''',
    '''對不起，我無法理解你。你幾歲？你可以說：45''',
    '''對不起，我無法理解你。你的性別是什麼？你可以說：女性。''',
    '''對不起，我無法理解你的意思。你有糖尿病家族史嗎？你可以說：有。''',
    '''對不起，我無法理解你。你吸菸嗎？你可以說：是的。''',
    '''對不起，我無法理解你。你多久喝一次含酒精的飲品？你可以從以下選項中選擇：從不
極少（一年數次）
偶爾（每月一次）
頻繁地（每週數次）
每日。
'''
]

@router.get("/")
def read_root(request: Request):
    print(request.query_params.get("message"))
    return {"message": "连接测试成功!"}


# 添加一个字段is_fixed,用于表明这是预先固定好的字段或者信息，有自用的繁体中文
# 1 代表需要翻译，0代表本身就是繁体中文，2代表需要做下本地字典转换
def send_message(to_number, body_text, role, is_fixed=0,is_register=0):
    """发送微信消息"""
    try:
        print(f"DEBUG: Sending message to {to_number}: {body_text}")
        if not is_en:
            if is_fixed == 1:
                yue_body_text = to_other_language(body_text, "yue")
            elif is_fixed == 0:  # 本来就已经设置成了繁体中文
                yue_body_text = body_text
            elif is_fixed == 2:
                yue_body_text = get_fixed_field_translation(body_text)
        else:
            yue_body_text = body_text

        store_message(to_number, (role, body_text))
        logger.info(f"Message sent to {to_number}: {yue_body_text}")
        return {"code": 200, "data": {"message": yue_body_text, "role": role, "to_number": to_number}, "error_info": "","is_register":is_register}
    except Exception as e:
        logger.error(f"Error sending message to {to_number}: {e}")
        print(f"Error sending message to {to_number}: {e}")
        return {"code": -1, "data": {"message": "接收消息失敗，請稍後重試", "role": role, "to_number": to_number},
                "error_info": str(e),"is_register":is_register}


async def extract(request: Request):
    """提取请求数据"""
    json_data = await request.json()
    return {
        "prompt": json_data.get("prompt"),
        "phone_number": json_data.get("phone_number"),
        "user_info": json_data.get("user_info"),
    }

def get_user_state(phone_number):
    """获取用户状态"""
    state_key = f"user:{phone_number}:state"
    if r.exists(state_key):
        state_value = r.get(state_key)
        # 解码字节字符串
        if isinstance(state_value, bytes):
            state_value = state_value.decode('utf-8')
        try:
            return RegistrationState(state_value)
        except ValueError:
            # 如果状态值无效，返回初始状态
            logger.warning(f"Invalid state value '{state_value}' for user {phone_number}, resetting to INITIAL")
            return RegistrationState.INITIAL
    return RegistrationState.INITIAL


def set_user_state(phone_number, state: RegistrationState):
    """设置用户状态"""
    logger.info(f"Setting state for {phone_number}: {state.value}")
    r.set(f"user:{phone_number}:state", state.value)
    # 设置30分钟过期时间
    r.expire(f"user:{phone_number}:state", 1800)


def get_user_data(phone_number, field=None):
    """获取用户数据"""
    if field:
        value = r.get(f"user:{phone_number}:data:{field}")
        if value is not None and isinstance(value, bytes):
            value = value.decode('utf-8')
        return value
    else:
        # 获取所有数据
        pattern = f"user:{phone_number}:data:*"
        keys = r.keys(pattern)
        data = {}
        for key in keys:
            if isinstance(key, bytes):
                key = key.decode('utf-8')
            field_name = key.split(":")[-1]
            value = r.get(key)
            if value is not None and isinstance(value, bytes):
                value = value.decode('utf-8')
            data[field_name] = value
        return data

#這是设置单个信息
def set_user_data(phone_number, field, value):
    """设置用户数据"""
    # 确保值是字符串
    if not isinstance(value, str):
        value = str(value)
    logger.info(f"Setting data for {phone_number}: {field}={value}")
    r.set(f"user:{phone_number}:data:{field}", value)
    # 设置30分钟过期时间
    r.expire(f"user:{phone_number}:data:{field}", 1800)

#设置字典，从前端获取表单信息然后存入
def set_user_profile(phone_number: str, data: dict, ttl: int = 1800):
    if not data:
        return

    key = f"user:{phone_number}:profile"

    mapping = {
        str(k): str(v)
        for k, v in data.items()
        if v is not None
    }

    logger.info(f"[Redis] HMSET {key} {mapping}")

    r.hmset(key, mapping)   # ✅ Redis 3.0 完美支持
    r.expire(key, ttl)

#获取之前存入的表单数据
def get_user_profile(phone_number: str) -> dict:
    key = f"user:{phone_number}:profile"
    raw = r.hgetall(key)

    return {
        k.decode(): v.decode()
        for k, v in raw.items()
    }

def clear_user_data(phone_number):
    """清理用户数据"""
    pattern = f"user:{phone_number}:*"
    keys = r.keys(pattern)
    for key in keys:
        r.delete(key)
    logger.info(f"Cleared data for {phone_number}")


def get_missing_fields(phone_number):
    """获取缺失的字段"""
    collected = get_user_data(phone_number)
    all_fields = ['weight', 'height', 'age', 'sex', 'family_history', 'smoking', 'alcohol']
    missing = [field for field in all_fields if field not in collected]
    logger.info(f"Missing fields for {phone_number}: {missing}")
    return missing


def validate_invitation_code(db, code):
    """验证邀请码"""
    logger.info(f"Validating invitation code: {code}")
    if crud.get_invitation_by_code(db, code) is not None:
        logger.info(f"Invitation code {code} is valid")
        return True
    logger.warning(f"Invitation code {code} is invalid")
    return False


def parse_natural_language1(text):
    """解析自然语言输入"""
    logger.info(f"Parsing natural language: {text}")
    text = text.lower()
    extracted = {}

    # 处理数字"3"作为模式选择
    if text.strip() in ['1', '2', '3']:
        logger.info(f"User selected mode: {text}")
        return extracted  # 返回空，让上层处理模式选择

    # 体重解析
    weight_patterns = [
        r'(?:weight|wt)[:\s]*(\d+(?:\.\d+)?)\s*(?:kg|kilograms?)?',
        r'(\d+(?:\.\d+)?)\s*(?:kg|kilograms?)\b',
        r'\b(\d{2,3})\s*(?:pounds?|lbs)\b',
    ]

    # 身高解析
    height_patterns = [
        r'(?:height|ht)[:\s]*(\d+(?:\.\d+)?)\s*(?:cm|centimeters?)?',
        r'(\d+(?:\.\d+)?)\s*(?:cm|centimeters?)\b',
        r"(\d)'\s*(\d+)''?",
        r'(\d)\s*feet?\s*(\d+)\s*inches?',
    ]

    # 年龄解析
    age_patterns = [
        r'(?:age|aged?)[:\s]*(\d{1,3})\s*(?:years?)?',
        r'\b(\d{1,3})\s*(?:years?\s*old|yo)\b',
        r"I'?m\s*(\d{1,3})\b",
        r'\b(\d{1,3})\b(?!\s*(?:kg|cm|years?))',  # 单独的年龄数字
    ]

    # 性别解析
    sex_patterns = [
        r'(?:sex|gender)[:\s]*(male|female|prefer not to tell)',
        r'\b(male|female|prefer not)\b',
        r'\b(M|F)\b',
    ]

    # 家族史解析
    # family_patterns = [
    #     r'(?:family\s*history|family\s*has|parents?)[:\s]*(yes|no|unknown)',
    #     r'(?:diabetes\s*in\s*family)[:\s]*(yes|no|unknown)',
    #     r'\b(yes|no|unknown)\b.*?(?:family|parents?).*?diabetes',
    # ]

    family_patterns = [
        # 模式1: family history 在前，回答在後
        r'(?:family[\s_]history|fh|parents?)\s*[:=]\s*(yes|no|unknown)\b',

        # 模式2: 回答在前，family history 在後
        r'\b(yes|no|unknown)\s+(?:family[\s_]history|fh)\b',

        # 模式3: 完整句子結構
        r'(?:there\s+is|has)\s+(yes|no|unknown)\s+family[\s_]history',

        # 模式4: 糖尿病特定
        r'(?:diabetes\s*in\s*family|family[\s_]history\s*of\s*diabetes)\s*[:=]\s*(yes|no|unknown)\b',

        # 模式5: 動詞結構
        r'family[\s_]history\s+(?:is|are)\s+(yes|no|unknown)\b',

        # 模式6: 最簡單的直接匹配
        r'\bfamily[\s_]history\s*[:=]?\s*(yes|no|unknown)\b',
        r'\b(yes|no|unknown)\s*[:]?\s*family[\s_]history\b'
    ]

    # 吸烟解析
    smoking_patterns = [
        r'(?:smoke|smoking)[:\s]*(yes|no|prefer not to tell)',
        r'\b(yes|no|prefer not)\b.*?(?:smoke|smoking)',
        r'I\s+(?:am\s+)?a\s+smoker',
        r'I\s+(?:do\s+)?not\s+smoke',
    ]

    # 饮酒解析
    alcohol_patterns = [
        r'(?:alcohol|drink)[:\s]*(never|rarely|occasionally|frequently|daily)',
        r'\b(never|rarely|occasionally|frequently|daily)\b.*?(?:drink|alcohol)',
        r"I\s+don'?t\s+drink",
        r"I\s+drink\s+daily",
    ]

    # 尝试提取所有字段
    patterns = {
        'weight': weight_patterns,
        'height': height_patterns,
        'age': age_patterns,
        'sex': sex_patterns,
        'family_history': family_patterns,
        'smoking': smoking_patterns,
        'alcohol': alcohol_patterns
    }

    for field, field_patterns in patterns.items():
        for pattern in field_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                logger.info(f"Matched pattern for {field}: {pattern}")
                try:
                    if field == 'weight' and 'pounds' in text:
                        # 转换磅到公斤
                        pounds = float(match.group(1))
                        extracted[field] = str(pounds * 0.453592)
                    elif field == 'height' and ("'" in text or 'feet' in text):
                        # 转换英尺英寸到厘米
                        feet = int(match.group(1))
                        inches = int(match.group(2)) if len(match.groups()) > 1 else 0
                        extracted[field] = str(feet * 30.48 + inches * 2.54)
                    elif field == 'sex':
                        value = match.group(1).lower()
                        if 'male' in value or value == 'm':
                            extracted[field] = 'Male'
                        elif 'female' in value or value == 'f':
                            extracted[field] = 'Female'
                        else:
                            extracted[field] = 'Prefer not to tell'
                    elif field in ['family_history', 'smoking']:
                        value = match.group(1).lower()
                        if value == 'yes':
                            extracted[field] = 'Yes'
                        elif value == 'no':
                            extracted[field] = 'No'
                        elif 'prefer' in value:
                            extracted[field] = 'Prefer not to tell'
                        else:
                            extracted[field] = 'Unknown'
                    elif field == 'alcohol':
                        value = match.group(1).lower()
                        extracted[field] = value.title()
                    else:
                        extracted[field] = match.group(1)
                    logger.info(f"Extracted {field}: {extracted[field]}")
                    break
                except Exception as e:
                    logger.error(f"Error processing {field} match: {e}")
                    continue

    logger.info(f"Final extracted fields: {extracted}")
    return extracted


# ========= 主解析函数 =========
def parse_natural_language(text: str):
    """
    解析自然语言（支持繁中→机器翻译→自然英文）
    """
    logger.info(f"Parsing natural language: {text}")

    text = text.lower()
    extracted = {}

    # ---------- 模式选择 ----------
    if text.strip() in {"1", "2", "3"}:
        return extracted

    # ---------- 正则模式 ----------

    weight_patterns = [
        r'(?:weight|wt)[:\s]*(\d+(?:\.\d+)?)\s*(kg|kilograms?)?',
        r'\b(\d+(?:\.\d+)?)\s*(kg|kilograms?)\b',
        r'\b(\d{2,3})\s*(pounds?|lbs)\b',
    ]

    height_patterns = [
        r'(?:height|ht)[:\s]*(\d+(?:\.\d+)?)\s*(cm|centimeters?)?',
        r'\b(\d+(?:\.\d+)?)\s*(cm|centimeters?)\b',
        r"(\d)'\s*(\d+)''?",
        r'(\d)\s*feet?\s*(\d+)\s*inches?',
    ]

    age_patterns = [
        r'(?:age|aged?)[:\s]*(\d{1,3})',
        r'\b(\d{1,3})\s*(years?\s*old|yo)\b',
        r"i'?m\s*(\d{1,3})\b",
    ]

    sex_patterns = [
        r'(?:sex|gender)[:\s]*(male|female|prefer not)',
        r'\b(male|female)\b',
        r'\b(m|f)\b',
    ]

    family_patterns = [
        r'family[\s_]history',
        r'diabetes\s+in\s+family'
    ]

    smoking_patterns = [
        r'smoke',
        r'smoking',
        r'smoker'
    ]

    alcohol_patterns = [
        r'drink',
        r'alcohol'
    ]

    # ---------- 体重 ----------
    for pattern in weight_patterns:
        match = re.search(pattern, text)
        if match:
            value = match.group(1)
            unit = match.group(2) if len(match.groups()) > 1 else ""
            if unit and ("pound" in unit or "lb" in unit):
                extracted["weight"] = str(float(value) * 0.453592)
            else:
                extracted["weight"] = value
            break

    # ---------- 身高 ----------
    for pattern in height_patterns:
        match = re.search(pattern, text)
        if match:
            if "'" in pattern or "feet" in pattern:
                feet = int(match.group(1))
                inches = int(match.group(2)) if match.lastindex >= 2 else 0
                extracted["height"] = str(feet * 30.48 + inches * 2.54)
            else:
                extracted["height"] = match.group(1)
            break

    # ---------- 年龄 ----------
    for pattern in age_patterns:
        match = re.search(pattern, text)
        if match:
            extracted["age"] = match.group(1)
            break

    # ---------- 性别 ----------
    for pattern in sex_patterns:
        match = re.search(pattern, text)
        if match:
            val = match.group(1)
            extracted["sex"] = "Male" if val in {"m", "male"} else "Female"
            break

    # ---------- 家族史 ----------
    for pattern in family_patterns:
        match = re.search(pattern, text)
        if match:
            context = extract_local_context(text, match.group())
            val = normalize_yes_no(context)
            if val:
                extracted["family_history"] = val
            break

    # ---------- 吸烟 ----------
    for pattern in smoking_patterns:
        match = re.search(pattern, text)
        if match:
            context = extract_local_context(text, match.group())
            val = normalize_yes_no(context)
            if val:
                extracted["smoking"] = val
            break

    # ---------- 饮酒 ----------
    for pattern in alcohol_patterns:
        match = re.search(pattern, text)
        if match:
            context = extract_local_context(text, match.group())
            val = normalize_alcohol(context)
            if val:
                extracted["alcohol"] = val
            break

    logger.info(f"Final extracted fields: {extracted}")
    return extracted


def validate_field(field, value):
    """验证字段值"""
    logger.info(f"Validating {field}: {value}")
    if field == 'weight':
        try:
            weight = float(value)
            valid = 20 <= weight <= 300
            logger.info(f"Weight validation: {valid}")
            return valid
        except:
            logger.warning(f"Invalid weight value: {value}")
            return False
    elif field == 'height':
        try:
            height = float(value)
            valid = 50 <= height <= 250
            logger.info(f"Height validation: {valid}")
            return valid
        except:
            logger.warning(f"Invalid height value: {value}")
            return False
    elif field == 'age':
        try:
            age = int(value)
            valid = 1 <= age <= 120
            logger.info(f"Age validation: {valid}")
            return valid
        except:
            logger.warning(f"Invalid age value: {value}")
            return False
    elif field == 'sex':
        if value == "No" or value == "no":
            return True
        else:
            valid = value in ['Male', 'Female', 'Prefer not to tell']
            logger.info(f"Sex validation: {valid}")
            return valid
    elif field == 'family_history':
        valid = value in ['Yes', 'No', 'Unknown']
        logger.info(f"Family history validation: {valid}")
        return valid
    elif field == 'smoking':
        valid = value in ['Yes', 'No', 'Prefer not to tell']
        logger.info(f"Smoking validation: {valid}")
        return valid
    elif field == 'alcohol':
        valid = value in ['Never', 'Rarely', 'Occasionally', 'Frequently', 'Daily']
        logger.info(f"Alcohol validation: {valid}")
        return valid
    return False


@router.post("/")
async def reply(request: Request, db: Annotated[Connection, Depends(get_db)]):
    """处理微信消息"""
    try:
        data = await extract(request)
        question = data["prompt"]
        phone_number = data["phone_number"]
        user_info=data["user_info"]
        set_user_profile(phone_number, user_info)

        logger.info(f"Received message from {phone_number}: {question}")

        # 检查用户是否已注册
        user = crud.get_user_by_username(db, phone_number)
        if user is not None:
            # 已注册用户，处理正常对话
            logger.info(f"User {phone_number} is already registered")
            return await handle_registered_user(user, phone_number, question, db)

        # 新用户，处理注册流程
        logger.info(f"User {phone_number} is new, handling registration")
        return await handle_registration(phone_number, question, db)
    except Exception as e:
        logger.error(f"Error in reply handler: {e}")
        if not is_en:
            return send_message(phone_number, "對不起，處理您的請求時發生錯誤。請再試一次。", "system")
        else:
            return send_message(phone_number,"Sorry, an error occurred while processing your request. Please try again.", "system")

async def handle_registration(phone_number, question, db):
    """处理用户注册流程"""
    try:
        state = get_user_state(phone_number)
        logger.info(f"Current state for {phone_number}: {state}")

        # 处理特殊命令
        question_lower = ""
        if not is_en:
            # 如果是繁体中文
            translate_question = user_input_to_internal_language(question)
            question_lower = translate_question.strip().lower()
        else:
            # 如果是英文
            question_lower = question.strip().lower()

        if question_lower in ['/start', 'start', 'restart', 'reset']:
            clear_user_data(phone_number)
            set_user_state(phone_number, RegistrationState.CODE_REQUIRED)
            welcome_msg = """Greeting! My name is DiaLOG, a diabetes AI chatbot.

To use our service, please enter your invitation code."""
            welcome_msg_tchinese = """您好！我叫DiaLOG，是一個糖尿病人工智慧聊天機器人。

要使用我們的服務，請輸入您的邀請碼。"""
            if not is_en:
                return send_message(phone_number, welcome_msg_tchinese, "system")
            else:
                return send_message(phone_number, welcome_msg, "system")

        if question_lower in ['/cancel', 'cancel', 'quit']:
            clear_user_data(phone_number)
            if not is_en:
                return send_message(phone_number, "註冊已取消。輸入/start以重新開始。", "system")
            else:
                return send_message(phone_number, "Registration has been canceled. Enter /start to begin again.",
                                    "system")

        if state == RegistrationState.INITIAL:
            # 初始状态，发送欢迎消息并询问邀请码
            welcome_msg = """Greeting! My name is DiaLOG, a diabetes AI chatbot.

To use our service, please enter your invitation code."""
            welcome_msg_translated = """您好！我是DiaLOG，一個糖尿病AI聊天機器人。
要使用我們的服務，請輸入您的邀請碼。"""
            set_user_state(phone_number, RegistrationState.CODE_REQUIRED)
            if not is_en:
                return send_message(phone_number, welcome_msg_translated, "system")
            else:
                return send_message(phone_number, welcome_msg, "system")

        elif state == RegistrationState.CODE_REQUIRED:
            # 处理邀请码输入
            code = question.strip()
            logger.info(f"Validating invitation code: {code}")
            if validate_invitation_code(db, code):
                # 邀请码有效
                set_user_data(phone_number, "invitation_code", code)
                set_user_state(phone_number, RegistrationState.COLLECTING)

                # 发送欢迎消息和说明
#                 welcome_msg = """✅ Invitation code accepted!
#
# 👋 Welcome to DiaLOG Registration
#
# You can now provide your health information for diabetes assessment.
#
# **How to provide information:**
#
# 1️⃣ **All at once** (Recommended):
# "Age 45, male, 75kg, 175cm, family history yes, non-smoker, drink occasionally"
#
# 2️⃣ **Multiple parts**:
# "Age 45, male, 75kg"
# then "Height 175cm, family history yes"
# then "Don't smoke, drink occasionally"
#
# 3️⃣ **One after another**:
# I'll ask you each question separately.
#
# **Please type 1, 2, or 3 to choose your preferred method:**"""
#                 welcome_msg_tchinese = """✅ 邀請碼已接受!
#
# 👋 歡迎來到DiaLOG註冊頁面
#
# 您現在可以提供您的健康資訊以進行糖尿病評估。
#
# **如何提供資訊:**
#
# 1️⃣ **一次全部** (推薦):
# "年齡45歲，男性，體重75公斤，身高175公分，有家族病史，不吸煙，偶爾飲酒"
#
# 2️⃣ **多次提供**:
# "年齡45歲，男性，體重75公斤"
# 然後 "身高175公分，有家族病史"
# 然後 "不吸煙，偶爾飲酒"
#
# 3️⃣ **一個接一個提供**:
# 我會分別問你每一個問題。
#
# **請輸入1、2或3來選擇您偏好的方式:**"""
                welcome_msg_tchinese="驗證碼有效，請填寫彈窗中的表格"
                welcome_msg="The verification code is valid. Please fill out the form in the pop-up window."
                if not is_en:
                    return send_message(phone_number, welcome_msg_tchinese, "system",0,1)
                else:
                    return send_message(phone_number, welcome_msg, "system",0,1)

            else:
                # 邀请码无效
                error_msg = ""
                if not is_en:
                    error_msg = "抱歉，邀請碼無效，請向管理員索取最新的邀請碼。"
                else:
                    error_msg = "Sorry, the invitation code is invalid. Please contact the administrator to obtain the latest invitation code."
                return send_message(phone_number, error_msg, "system")

        elif state == RegistrationState.CODE_VERIFIED:
            # 已验证邀请码，处理用户选择的模式
            logger.info(f"User {phone_number} in CODE_VERIFIED state, processing: {question}")

            if question_lower in ['1', '2', '3']:
                # 用户选择了模式
                set_user_data(phone_number, "collection_mode", question_lower)

                if question_lower == '1':
                    # 一次性提供所有信息
                    msg = """Great! You've chosen to provide all information at once.

Please provide your health information now. For example:
"Age 45, male, 75kg, 175cm, family history yes, non-smoker, drink occasionally" """
                    msg_tchinese = """太棒了！你已選擇一次性提供所有信息。
請立即提供您的健康信息。例如：
"45歲，男性，75公斤，175公分，有家族病史，不吸烟，偶爾飲酒" """
                    # 直接进入收集状态，等待用户输入
                    set_user_state(phone_number, RegistrationState.COLLECTING)
                    if not is_en:
                        return send_message(phone_number, msg_tchinese, "system")
                    else:
                        return send_message(phone_number, msg, "system")

                elif question_lower == '2':
                    # 分部分提供
                    msg = """Great! You've chosen to provide information in multiple parts.

You can provide information in any order. I'll let you know what's still needed.

Please start by providing some of your health information."""
                    msg_tchinese = """太棒了！你已選擇分多部分提供資訊。
你可以以任何順序提供資訊。我會告知你還需要哪些內容。
請先提供一些您的健康資訊。"""
                    set_user_state(phone_number, RegistrationState.COLLECTING)
                    if not is_en:
                        return send_message(phone_number, msg_tchinese, "system")
                    else:
                        return send_message(phone_number, msg, "system")

                elif question_lower == '3':
                    # 一问一答模式
                    msg = """Great! You've chosen the step-by-step method.

I'll ask you each question one by one. Let's start!"""
                    msg_tchinese = """太棒了！你選擇了逐步進行的方法。
我會逐一問你每個問題。我們開始吧！"""
                    if not is_en:
                        return send_message(phone_number, msg_tchinese, "system")
                    else:
                        return send_message(phone_number, msg, "system")
                    set_user_state(phone_number, RegistrationState.COLLECTING)
                    # 开始询问第一个问题
                    await ask_next_field_step_by_step(phone_number)
                return
            else:
                # 用户没有选择模式，可能直接提供了信息
                if not is_en:
                    return send_message(phone_number, "请选择注册方式，输入：1，2，3", "system")
                else:
                    return send_message(phone_number, "Please select a registration method, enter: 1, 2, 3", "system")
                return
                # logger.info(f"User didn't select mode, assuming they're providing info: {question}")
                # set_user_state(phone_number, RegistrationState.COLLECTING)
                # set_user_data(phone_number, "collection_mode", "2")  # 默认多部分模式
                # await process_health_info(phone_number, question, db)

        elif state == RegistrationState.COLLECTING:
            # 收集健康信息中
            logger.info(f"User {phone_number} in COLLECTING state, processing: {question}")
            return await precess_form_collection(phone_number,db)
            return await process_health_info(phone_number, question, db)

        elif state == RegistrationState.CONFIRMING:
            # 确认信息中
            logger.info(f"User {phone_number} in CONFIRMING state, processing: {question}")
            return await handle_confirmation(phone_number, question, db)

        elif state == RegistrationState.COMPLETED:
            # 已完成注册
            if not is_en:
                msg_tchinese = "您已完成註冊。現在您可以與我們的聊天機器人交談了。"
                return send_message(phone_number, msg_tchinese, "system")
            else:
                msg = "You have completed the registration. You can now chat with our chatbot."
                return send_message(phone_number, msg, "system")
            return

    except Exception as e:
        logger.error(f"Error in handle_registration for {phone_number}: {e}")
        if not is_en:
            return send_message(phone_number, "對不起，處理您的請求時發生錯誤。請再試一次。", "system")
        else:
            return send_message(phone_number,
                                "I'm sorry, an error occurred while processing your request. Please try again.",
                                "system")


async def ask_next_field_step_by_step(phone_number):
    """在一步一步模式下询问下一个字段"""
    try:
        missing_fields = get_missing_fields(phone_number)
        logger.info(f"Asking next field step by step, missing: {missing_fields}")

        if not missing_fields:
            # 所有字段都已收集，请求确认
            await request_confirmation(phone_number)
            return

        # 定义询问顺序
        priority_order = ['age', 'sex', 'weight', 'height',
                          'family_history', 'smoking', 'alcohol']

        for field in priority_order:
            if field in missing_fields:
                field_index = {
                    'weight': 0, 'height': 1, 'age': 2, 'sex': 3,
                    'family_history': 4, 'smoking': 5, 'alcohol': 6
                }[field]

                if not is_en:
                    question = health_questions_tchinese[field_index]
                else:
                    question = health_questions[field_index]
                # 存储当前正在询问的字段
                set_user_data(phone_number, "current_question_field", field)

                return send_message(phone_number, question, "system")

        # 如果没有按优先级找到，询问第一个缺失字段
        if missing_fields:
            first_field = missing_fields[0]
            field_index = {
                'weight': 0, 'height': 1, 'age': 2, 'sex': 3,
                'family_history': 4, 'smoking': 5, 'alcohol': 6
            }[first_field]

            if not is_en:
                question = health_questions_tchinese[field_index]
            else:
                question = health_questions[field_index]

            # 存储当前正在询问的字段
            set_user_data(phone_number, "current_question_field", first_field)

            return send_message(phone_number, question, "system")

    except Exception as e:
        logger.error(f"Error in ask_next_field_step_by_step for {phone_number}: {e}")
        if not is_en:
            return send_message(phone_number, "請提供您的健康資訊。", "system")
        else:
            return send_message(phone_number, "Please provide your health information.", "system")

async def form_info_process(phone_number,db):
    """完成注册"""
    try:
        # 获取所有数据
        data = get_user_profile(phone_number)
        logger.info(f"Completing registration with data: {data}")
        data["invitation_code"] = get_user_data(phone_number,"invitation_code")

        # 计算出生年份
        age = int(data['age'])
        current_year = datetime.now().year
        birth_year = current_year - age
        birth_date = datetime(birth_year, 1, 1).strftime("%Y-%m-%d")

        # 创建用户
        salt = get_parameter("auth", "salt")
        # 这里减少下密码的长度，就暂时不用slat了
        # password=f"{salt}{phone_number}"
        new_user = CreateUser(
            username=phone_number,
            password=f"{salt}{phone_number}",
            invitation_code=data['invitation_code'],
            date_of_birth=birth_date,
            height=float(data['height']),
            weight=float(data['weight']),
            sex=data.get('sex'),
            family_history=data.get('family_history'),
            smoking_status=data.get('smoking'),
            drinking_history=data.get('drinking')
        )

        logger.info(f"Creating user: {new_user.username}")

        user = sign_up(new_user, db)
        set_user_state(phone_number, RegistrationState.COMPLETED)

        # 清理缓存数据
        clear_user_data(phone_number)

        # 清理聊天历史
        pattern = f"chat:{phone_number}*"
        keys = r.keys(pattern)
        for key in keys:
            r.delete(key)

        # 发送完成消息
        if not is_en:
            completion_msg = "🎉 **註冊完成！**\n\n您已成功註冊。您現在可以與我們的聊天機器人談論有關糖尿病評估和管理的事宜。"
        else:
            completion_msg = "🎉 **Registration Complete!**\n\nYou have successfully registered. You can now discuss matters related to diabetes assessment and management with our chatbot."
        return send_message(phone_number, completion_msg, "system")
    except HTTPException as e:
        logger.error(f"註冊失敗 {phone_number}: {e}")
        if not is_en:
            error_msg = f"抱歉，註冊流程失敗: {str(e)}. Please try again."
        else:
            error_msg = f"Sorry, the registration process failed:{str(e)}. "
        # 重置状态，让用户重试
        set_user_state(phone_number, RegistrationState.CODE_REQUIRED)
        clear_user_data(phone_number)
        return send_message(phone_number, error_msg, "system")

    except Exception as e:
        logger.error(f"Unexpected error in complete_registration for {phone_number}: {e}")
        if not is_en:
            error_msg = "對不起，發生了一個意外錯誤。請再試一次。"
        else:
            error_msg = "Sorry, an unexpected error occurred. Please try again."
        return send_message(phone_number, error_msg, "system")

async def process_health_info(phone_number, question, db):
    """处理健康信息收集"""
    try:
        # 获取收集模式
        collection_mode = get_user_data(phone_number, "collection_mode")
        logger.info(f"Processing health info for {phone_number}, mode: {collection_mode}")

        # 尝试解析自然语言输入
        extracted = parse_natural_language(question)
        logger.info(f"Extracted fields: {extracted}")

        if collection_mode == '3':  # 一步一步模式
            current_field = get_user_data(phone_number, "current_question_field")
            logger.info(f"Step-by-step mode, current field: {current_field}")

            if current_field:
                # 尝试从输入中提取当前字段的值
                field_value = None

                if current_field == 'age':
                    match = re.search(r'\b(\d{1,3})\b', question)
                    if match:
                        field_value = match.group(1)
                elif current_field == 'weight':
                    match = re.search(r'\b(\d+(?:\.\d+)?)\s*(?:kg|kilograms?)?\b', question, re.IGNORECASE)
                    if match:
                        field_value = match.group(1)
                elif current_field == 'height':
                    match = re.search(r'\b(\d+(?:\.\d+)?)\s*(?:cm|centimeters?)?\b', question, re.IGNORECASE)
                    if match:
                        field_value = match.group(1)
                elif current_field == 'sex':
                    if 'male' in question.lower() or 'm' in question.lower():
                        field_value = 'Male'
                    elif 'female' in question.lower() or 'f' in question.lower():
                        field_value = 'Female'
                    elif 'prefer' in question.lower():
                        field_value = 'Prefer not to tell'
                elif current_field in ['family_history', 'smoking']:
                    if 'yes' in question.lower():
                        field_value = 'Yes'
                    elif 'no' in question.lower():
                        field_value = 'No'
                    elif 'unknown' in question.lower():
                        field_value = 'Unknown'
                    elif 'prefer' in question.lower():
                        field_value = 'Prefer not to tell'
                elif current_field == 'alcohol':
                    for option in ['Never', 'Rarely', 'Occasionally', 'Frequently', 'Daily']:
                        if option.lower() in question.lower():
                            field_value = option
                            break

                if field_value and validate_field(current_field, field_value):
                    set_user_data(phone_number, current_field, field_value)
                    if not is_en:
                        return send_message(phone_number,
                                            f"✅ 已經取得如下信息! {get_fixed_field_translation(current_field)}: {get_fixed_response_translation(field_value.lower())}",
                                            "system")
                    else:
                        return send_message(phone_number, f"✅ Got it! {current_field}: {field_value.lower()}",
                                            "system")
                    # 清除当前字段标记
                    r.delete(f"user:{phone_number}:data:current_question_field")

                    # 检查是否还有缺失字段
                    missing_fields = get_missing_fields(phone_number)
                    if missing_fields:
                        # 询问下一个字段
                        await ask_next_field_step_by_step(phone_number)
                    else:
                        # 所有字段收集完成
                        await request_confirmation(phone_number)
                else:
                    # 当前字段的值无效
                    field_index = {
                        'weight': 0, 'height': 1, 'age': 2, 'sex': 3,
                        'family_history': 4, 'smoking': 5, 'alcohol': 6
                    }[current_field]

                    if not is_en:
                        error_msg = error_messages_tchinese[field_index]
                    else:
                        error_msg = error_messages[field_index]
                    return send_message(phone_number, error_msg, "system")
            else:
                # 没有当前字段，使用通用解析
                return await process_general_collection(phone_number, extracted)

        else:
            # 模式1或2，使用通用收集逻辑
            return await process_general_collection(phone_number, extracted)

    except Exception as e:
        logger.error(f"Error in process_health_info for {phone_number}: {e}")
        if not is_en:
            return send_message(phone_number, "對不起，我無法處理您的資訊。請再試一次。", "system")
        else:
            return send_message(phone_number, "I'm sorry, I cannot process your information. Please try again.",
                                "system")

async def precess_form_collection(phone_number, db):
    return await form_info_process(phone_number, db)

async def process_general_collection(phone_number, extracted):
    """通用信息收集逻辑（用于模式1和2）"""
    try:
        if extracted:
            # 成功解析到信息
            update_summary = []
            for field, value in extracted.items():
                if validate_field(field, value):
                    set_user_data(phone_number, field, value)
                    update_summary.append(
                        f"{get_fixed_field_translation(field.lower())}: {get_fixed_response_translation(value.lower())}")

            if update_summary:
                # 显示已更新的信息
                if not is_en:
                    response = "✅ 已經取得如下信息!\n"
                else:
                    response = "✅ The following information has been obtained!"
                for item in update_summary:
                    response += f"• {item}\n"
                return send_message(phone_number, response, "system")

        # 检查是否还有缺失字段
        missing_fields = get_missing_fields(phone_number)
        logger.info(f"Missing fields after processing: {missing_fields}")

        if not missing_fields:
            # 所有字段都已收集，请求确认
            return await request_confirmation(phone_number)
            return

        # 询问下一个缺失字段
        collection_mode = get_user_data(phone_number, "collection_mode")
        if collection_mode == '2':  # 多部分模式
            return await ask_next_field_multi_part(phone_number, missing_fields)
        # 模式1（一次性）不需要询问，等待用户输入,但要给个提示
        if collection_mode == '1':
            if not is_en:
                missing_fields_tchinese = []
                for field_en in missing_fields:
                    missing_fields_tchinese.append(get_fixed_field_translation(field_en))
                sendText = f"請繼續輸入資訊: {missing_fields_tchinese}\n例如:\n"
                # 遍历缺失的字段，然后给出对应的示例
                for field in missing_fields:
                    if re.fullmatch("height", field, flags=re.IGNORECASE):
                        sendText += "173公分\n"
                    elif re.fullmatch("weight", field, flags=re.IGNORECASE):
                        sendText += "60公斤\n"
                    elif re.fullmatch("age", field, flags=re.IGNORECASE):
                        sendText += "18嵗\n"
                    elif re.fullmatch("sex", field, flags=re.IGNORECASE):
                        sendText += "男性 (女性/不願透露)\n"
                    elif re.fullmatch("family_history", field, flags=re.IGNORECASE):
                        sendText += "家族病史 有 (沒有/不清楚)\n"
                    elif re.fullmatch("smoking", field, flags=re.IGNORECASE):
                        sendText += "吸烟習慣 沒有 (有/不願透露)\n"
                    elif re.fullmatch("alcohol", field, flags=re.IGNORECASE):
                        sendText += "飲酒習慣 從不 (很少（一年幾次） 偶爾（每月一次） 頻繁地（每週數次） 每日)\n"
                sendText += "請用逗號分隔上述信息。\n"
                return send_message(phone_number, sendText, "system")
            else:
                missing_fields_english = []
                for field_en in missing_fields:
                    missing_fields_english.append(field_en)
                sendText = f"Please continue entering information: {missing_fields_english}\nExamples:\n"
                # 遍历缺失的字段，然后给出对应的示例
                for field in missing_fields:
                    if re.fullmatch("height", field, flags=re.IGNORECASE):
                        sendText += "173 cm\n"
                    elif re.fullmatch("weight", field, flags=re.IGNORECASE):
                        sendText += "60 kg\n"
                    elif re.fullmatch("age", field, flags=re.IGNORECASE):
                        sendText += "18 years old\n"
                    elif re.fullmatch("sex", field, flags=re.IGNORECASE):
                        sendText += "Male (Female/Prefer not to say)\n"
                    elif re.fullmatch("family_history", field, flags=re.IGNORECASE):
                        sendText += "Family medical history Yes (No/Unknown)\n"
                    elif re.fullmatch("smoking", field, flags=re.IGNORECASE):
                        sendText += "Smoking habit No (Yes/Prefer not to say)\n"
                    elif re.fullmatch("alcohol", field, flags=re.IGNORECASE):
                        sendText += "Alcohol consumption Never (Rarely (few times a year)/Occasionally (once a month)/Frequently (several times a week)/Daily)\n"
                sendText += "Please separate the above information with commas.\n"
                return send_message(phone_number, sendText, "system")

    except Exception as e:
        logger.error(f"Error in process_general_collection for {phone_number}: {e}")
        if is_en:
            return send_message(phone_number, "對不起，處理您的資訊時發生錯誤。", "system")
        else:
            return send_message(phone_number, "I'm sorry, an error occurred while processing your information.",
                                "system")


async def ask_next_field_multi_part(phone_number, missing_fields):
    """在多部分模式下询问下一个字段"""
    try:
        # 显示已收集和未收集的信息
        collected = get_user_data(phone_number)

        collected_display = []
        for field in ['age', 'sex', 'weight', 'height', 'family_history', 'smoking', 'alcohol']:
            if field in collected and collected[field]:
                field_display = {
                    'age': 'Age', 'sex': 'Sex', 'weight': 'Weight',
                    'height': 'Height', 'family_history': 'Family History',
                    'smoking': 'Smoking', 'alcohol': 'Alcohol'
                }[field]
                if not is_en:
                    collected_display.append(
                        f"✓ {get_fixed_field_translation(field_display.lower())}: {get_fixed_response_translation(collected[field].lower())}")
                else:
                    collected_display.append(
                        f"✓ {field_display.lower()}: {collected[field].lower()}")

        missing_display = []
        for field in missing_fields:
            field_display = {
                'age': 'Age', 'sex': 'Sex', 'weight': 'Weight',
                'height': 'Height', 'family_history': 'Family History',
                'smoking': 'Smoking', 'alcohol': 'Alcohol'
            }[field]
            missing_display.append(f"✗ {field_display}")

        if collected_display:
            if is_en:
                response = "📊 **進度:**\n\n"
                response += "✅ **已經收集:**\n" + "\n".join(collected_display) + "\n\n"
            else:
                response = "📊 **Progress:**\n\n"
                response += "✅ **has been collected:**\n" + "\n".join(collected_display) + "\n\n"
        else:
            response = ""

        if missing_display:
            if not is_en:
                missing_fields_thinese = []
                for missing_field in missing_display:
                    missing_fields_thinese.append(get_fixed_field_translation(missing_field))

                response += "📋 **仍然需要如下資訊:**\n" + "\n".join(missing_fields_thinese) + "\n\n"

                if len(missing_fields) <= 2:
                    # 如果缺失字段少，一起问
                    missing_names = [{
                                         'age': 'age', 'sex': 'sex', 'weight': 'weight',
                                         'height': 'height', 'family_history': 'family history of diabetes',
                                         'smoking': 'smoking status', 'alcohol': 'alcohol consumption'
                                     }[field] for field in missing_fields]

                    response += f"請提供你的 {', '.join(get_fixed_field_translation(missing_names))}."
                else:
                    # 建议提供一些信息
                    response += "您現在可以提供任何遺漏的資訊。"
            else:

                response += "📋 **The following information is still required:**\n" + "\n".join(missing_display) + "\n\n"

                if len(missing_fields) <= 2:
                    # 如果缺失字段少，一起问
                    missing_names = [{
                                         'age': 'age', 'sex': 'sex', 'weight': 'weight',
                                         'height': 'height', 'family_history': 'family history of diabetes',
                                         'smoking': 'smoking status', 'alcohol': 'alcohol consumption'
                                     }[field] for field in missing_fields]

                    response += f"Please provide your {', '.join(missing_names)}."
                else:
                    # 建议提供一些信息
                    response += "You can now provide any missing information."

        return send_message(phone_number, response, "system")

    except Exception as e:
        logger.error(f"Error in ask_next_field_multi_part for {phone_number}: {e}")
        if not is_en:
            return send_message(phone_number, "請提供您的健康資訊。", "system")
        else:
            return send_message(phone_number, "Please provide your health information.", "system")


async def request_confirmation(phone_number):
    """请求用户确认信息"""
    try:
        set_user_state(phone_number, RegistrationState.CONFIRMING)

        # 获取所有已收集的数据
        data = get_user_data(phone_number)
        logger.info(f"Data for confirmation: {data}")

        # 构建确认消息
        if not is_en:
            confirmation_msg = "📋 **請確認您的資訊:**\n\n"
        else:
            confirmation_msg = "📋 **Please confirm your information:**\n\n"

        field_display = {
            'invitation_code': 'Invitation Code',
            'weight': 'Weight',
            'height': 'Height',
            'age': 'Age',
            'sex': 'Sex',
            'family_history': 'Family History',
            'smoking': 'Smoking',
            'alcohol': 'Alcohol'
        }

        for field, display in field_display.items():
            if field in data and data[field]:
                if field == "weight":
                    if not is_en:
                        confirmation_msg += f"• *體重: {data[field]}公斤\n"
                    else:
                        confirmation_msg += f"• *weight: {data[field]}kg\n"
                elif field == "height":
                    if not is_en:
                        confirmation_msg += f"• *身高: {data[field]}公分\n"
                    else:
                        confirmation_msg += f"• *height: {data[field]}cm\n"
                elif field.lower() == "invitation_code":
                    if not is_en:
                        confirmation_msg += f"• *邀請碼: {data[field]}\n"
                    else:
                        confirmation_msg += f"• *invitation_code: {data[field]}\n"
                else:
                    if not is_en:
                        confirmation_msg += f"• *{get_fixed_field_translation(display.lower())}: {get_fixed_response_translation(data[field].lower())}\n"
                    else:
                        confirmation_msg += f"• *{display.lower()}: {data[field].lower()}\n"

        if not is_en:
            confirmation_msg += "\n**所有內容都正確嗎？**\n回覆「確認」以確認，或告知我哪些內容需要更改，邀請碼除外\n例如：「將體重改為70公斤」"
        else:
            confirmation_msg += "\n**Is all the content correct?**\nReply with \"YES\" to verify, or let me know what needs to be changed, except for the invitation code.\nFor example: \"Change weight to 70 kilograms.\""

        return send_message(phone_number, confirmation_msg, "system")

    except Exception as e:
        logger.error(f"Error in request_confirmation for {phone_number}: {e}")
        if not is_en:
            return send_message(phone_number, "請確認您的資訊是否正確。", "system")
        else:
            return send_message(phone_number, "Please confirm whether your information is correct.", "system")


def parse_modification_command(text):
    """专门解析修改命令"""
    text = text.lower()
    modifications = {}

    # 更灵活的修改模式
    patterns = [
        # change X to Y
        (r'change\s+(?:my\s+)?(weight|height|age|sex|gender|family\s*history|smoking|alcohol|drinking)\s+to\s+(.+)',
         lambda m: (normalize_field_name(m.group(1)), normalize_value(m.group(2)))),

        # update X to Y
        (r'update\s+(?:my\s+)?(weight|height|age|sex|gender|family\s*history|smoking|alcohol|drinking)\s+to\s+(.+)',
         lambda m: (normalize_field_name(m.group(1)), normalize_value(m.group(2)))),

        # X is Y
        (r'(?:my\s+)?(weight|height|age|sex|gender|family\s*history|smoking|alcohol|drinking)\s+is\s+(.+)',
         lambda m: (normalize_field_name(m.group(1)), normalize_value(m.group(2)))),

        # X should be Y
        (r'(?:my\s+)?(weight|height|age|sex|gender|family\s*history|smoking|alcohol|drinking)\s+should\s+be\s+(.+)',
         lambda m: (normalize_field_name(m.group(1)), normalize_value(m.group(2)))),
    ]

    for pattern, processor in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            field, value = processor(match)
            if field and value:
                modifications[field] = value
                logger.info(f"Parsed modification: {field} = {value}")
                break

    return modifications


def normalize_field_name(field_str):
    """标准化字段名"""
    field_str = field_str.lower().replace(' ', '_')

    mapping = {
        'weight': 'weight',
        'height': 'height',
        'age': 'age',
        'sex': 'sex',
        'gender': 'sex',
        'family_history': 'family_history',
        'family': 'family_history',
        'smoking': 'smoking',
        'alcohol': 'alcohol',
        'drinking': 'alcohol'
    }

    return mapping.get(field_str)


def normalize_value(value_str):
    """标准化值"""
    value_str = value_str.strip().lower()

    # 处理family history
    if 'no' in value_str or 'negative' in value_str or 'none' in value_str:
        return 'No'
    elif 'yes' in value_str or 'positive' in value_str or 'have' in value_str:
        return 'Yes'
    elif 'unknown' in value_str or 'not sure' in value_str or 'uncertain' in value_str:
        return 'Unknown'

    # 处理性别
    if 'male' in value_str or 'm' == value_str:
        return 'Male'
    elif 'female' in value_str or 'f' == value_str:
        return 'Female'
    elif 'prefer' in value_str:
        return 'Prefer not to tell'

    # 处理饮酒
    if 'never' in value_str:
        return 'Never'
    elif 'rarely' in value_str or 'few times' in value_str:
        return 'Rarely'
    elif 'occasionally' in value_str or 'once a month' in value_str:
        return 'Occasionally'
    elif 'frequently' in value_str or 'several times' in value_str:
        return 'Frequently'
    elif 'daily' in value_str:
        return 'Daily'

    # 处理吸烟
    if 'yes' in value_str:
        return 'Yes'
    elif 'no' in value_str:
        return 'No'
    elif 'prefer' in value_str:
        return 'Prefer not to tell'

    # 如果是数字，直接返回
    if re.match(r'^\d+(\.\d+)?$', value_str):
        return value_str

    return None


async def handle_confirmation(phone_number, response, db):
    """处理用户确认"""
    try:
        response_lower = response.strip().lower()
        logger.info(f"Confirmation response: {response_lower}")

        if response_lower in ['yes', 'y', 'confirm', 'correct']:
            # 用户确认，完成注册
            return await complete_registration(phone_number, db)

        elif response_lower in ['no', 'n', 'wrong', 'change']:
            # 用户要修改信息
            if not is_en:
                return send_message(phone_number, "你想改變什麼？請具體告訴我。\n例如：“我的體重是70公斤”", "system")
            else:
                return send_message(phone_number,
                                    "What do you want to change? Please tell me specifically.\nFor example: \"My weight is 70 kilograms.\"",
                                    "system")
            set_user_state(phone_number, RegistrationState.COLLECTING)

        else:
            # 尝试解析修改信息
            extracted = parse_modification_command(response)
            if not extracted:
                # 如果不是修改命令，使用原有的自然语言解析
                extracted = parse_natural_language(response)
            if extracted:
                # 更新信息并重新请求确认
                for field, value in extracted.items():
                    if validate_field(field, value):
                        if value == "No" or value == "no":
                            set_user_data(phone_number, field, "Prefer not to tell")
                        else:
                            set_user_data(phone_number, field, value)

                return await request_confirmation(phone_number)
            else:
                # 不理解用户的输入
                if not is_en:
                    return send_message(phone_number, "我不確定您想要更改什麼。請具體說明。\n例如：「將體重更改為70公斤」",
                                        "system")
                else:
                    return send_message(phone_number,
                                        "I'm not sure what you want to change. Please be specific.\nFor example, \"Change the weight to 70 kilograms.\"",
                                        "system")

    except Exception as e:
        logger.error(f"Error in handle_confirmation for {phone_number}: {e}")
        if not is_en:
            return send_message(phone_number, "抱歉，我無法處理您的確認。請再試一次。", "system")
        else:
            return send_message(phone_number, "Sorry, I'm unable to process your confirmation. Please try again.",
                                "system")


async def complete_registration(phone_number, db):
    """完成注册"""
    try:
        # 获取所有数据
        data = get_user_data(phone_number)
        logger.info(f"Completing registration with data: {data}")

        # 检查是否所有必要字段都存在
        required_fields = ['invitation_code', 'age', 'height', 'weight', 'sex']
        missing_required = [field for field in required_fields if field not in data or not data[field]]

        if missing_required:
            if not is_en:
                missing_required_tchinese = []
                for field in missing_required:
                    if field.lower() == "invitation_code":
                        missing_required_tchinese.append("邀請碼")
                    else:
                        missing_required_tchinese.append(get_fixed_field_translation(field))

                return send_message(phone_number,
                                    f"缺少必填信息: {', '.join(missing_required_tchinese)}. 請提供這些信息.", "system")
            else:
                return send_message(phone_number,
                                    f"Missing required information: {', '.join(missing_required)}. 請提供這些信息.",
                                    "system")
            set_user_state(phone_number, RegistrationState.COLLECTING)
            return

        # 预处理数据
        def pre_process(value):
            if value is None:
                return None
            if isinstance(value, bytes):
                value = value.decode('utf-8', errors='ignore')

            value = str(value).strip()

            if value.lower() in ["unknown", "prefer not to tell"]:
                return None
            elif value.lower() == "yes":
                return True
            elif value.lower() == "no":
                return False
            return value

        # 计算出生年份
        age = int(data['age'])
        current_year = datetime.now().year
        birth_year = current_year - age
        birth_date = datetime(birth_year, 1, 1).strftime("%Y-%m-%d")

        # 创建用户
        salt = get_parameter("auth", "salt")
        # 这里减少下密码的长度，就暂时不用slat了
        # password=f"{salt}{phone_number}"
        sex = pre_process(data.get('sex'))
        new_user = CreateUser(
            username=phone_number,
            password=f"{salt}{phone_number}",
            invitation_code=data['invitation_code'],
            date_of_birth=birth_date,
            height=float(data['height']),
            weight=float(data['weight']),
            sex=pre_process(data.get('sex')),
            family_history=data.get('family_history'),
            smoking_status=data.get('smoking'),
            drinking_history=data.get('alcohol')
        )

        logger.info(f"Creating user: {new_user.username}")

        user = sign_up(new_user, db)
        set_user_state(phone_number, RegistrationState.COMPLETED)

        # 清理缓存数据
        clear_user_data(phone_number)

        # 清理聊天历史
        pattern = f"chat:{phone_number}*"
        keys = r.keys(pattern)
        for key in keys:
            r.delete(key)

        # 发送完成消息
        if not is_en:
            completion_msg = "🎉 **註冊完成！**\n\n您已成功註冊。您現在可以與我們的聊天機器人談論有關糖尿病評估和管理的事宜。"
        else:
            completion_msg = "🎉 **Registration Complete!**\n\nYou have successfully registered. You can now discuss matters related to diabetes assessment and management with our chatbot."
        return send_message(phone_number, completion_msg, "system")

    except HTTPException as e:
        logger.error(f"註冊失敗 {phone_number}: {e}")
        if not is_en:
            error_msg = f"抱歉，註冊流程失敗: {str(e)}. Please try again."
        else:
            error_msg = f"Sorry, the registration process failed:{str(e)}. "
        # 重置状态，让用户重试
        set_user_state(phone_number, RegistrationState.CODE_REQUIRED)
        clear_user_data(phone_number)
        return send_message(phone_number, error_msg, "system")

    except Exception as e:
        logger.error(f"Unexpected error in complete_registration for {phone_number}: {e}")
        if not is_en:
            error_msg = "對不起，發生了一個意外錯誤。請再試一次。"
        else:
            error_msg = "Sorry, an unexpected error occurred. Please try again."
        return send_message(phone_number, error_msg, "system")


async def handle_registered_user(user, phone_number, question, db):
    """处理已注册用户的对话"""
    try:
        # 获取或创建会话
        session = crud.get_latest_session(db, user_id=user.user_id)

        if session is None or session.create_time < datetime.utcnow() - timedelta(minutes=30):
            session_key = str(uuid.uuid4())
            db_session = Session(session_key=session_key, user_id=user.user_id, status=True)
            session = crud.create_session(db, db_session)

        # 创建查询
        q = Query(session_key=session.session_key, enquiry=question)
        q = crud.create_query(db, q)

        # 获取LLM响应
        chat_response = response_from_llm(q, session, db, phone_number)

        # 发送响应
        return send_message(phone_number, chat_response["response"], "ai", 1)

    except Exception as e:
        logger.error(f"Error in handle_registered_user for {phone_number}: {e}")
        if not is_en:
            return send_message(phone_number, "對不起，處理您的訊息時發生錯誤。", "system")
        else:
            return send_message(phone_number, "Sorry, an error occurred while processing your message.", "system")

