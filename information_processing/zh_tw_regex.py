# 繁体中文注册过程中对注册信息做正则解析
# 作者：钟闯
# 邮箱：zhongchuang19951190@gmail.com
# 创建日期：2026年1月12日

import re
import logging

logging.basicConfig(
    level=logging.INFO,
    filename='dev.log',             # Write logs to dev.log
    filemode='a',                   # Append mode (use 'w' to overwrite)
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)

# ================== 中文语义词表 ==================

YES_WORDS = [
    "有", "是", "曾經", "有過", "存在"
]

NO_WORDS = [
    "沒有", "無", "否", "未", "不"
]

UNKNOWN_WORDS = [
    "不確定", "不知道", "不清楚"
]

PREFER_NOT_WORDS = [
    "不方便透露", "不想說", "拒絕回答"
]

ALCOHOL_OCCASIONAL_WORDS = [
    "偶爾", "偶而", "有時", "間中"
]

# ================== 工具函数 ==================

def normalize_yes_no_zh(text: str):
    """
    中文语义 → Yes / No / Unknown / Prefer not to tell
    """
    for w in PREFER_NOT_WORDS:
        if w in text:
            return "Prefer not to tell"

    for w in UNKNOWN_WORDS:
        if w in text:
            return "Unknown"

    for w in NO_WORDS:
        if w in text:
            return "No"

    for w in YES_WORDS:
        if w in text:
            return "Yes"

    return None


def normalize_alcohol_zh(text: str):
    """
    中文饮酒频率
    """
    if "從不" in text or "不喝" in text or "沒喝" in text:
        return "Never"

    if any(w in text for w in ALCOHOL_OCCASIONAL_WORDS):
        return "Occasionally"

    if "很少" in text:
        return "Rarely"

    if "經常" in text or "常常" in text:
        return "Frequently"

    if "每天" in text or "每日" in text:
        return "Daily"

    return None


def extract_local_context(text, keyword, window=20):
    """
    提取中文关键词附近上下文
    """
    idx = text.find(keyword)
    if idx == -1:
        return ""
    start = max(0, idx - window)
    end = min(len(text), idx + len(keyword) + window)
    return text[start:end]


# ================== 主函数 ==================

def parse_natural_language(text: str):
    """
    直接解析【繁體中文】输入
    """
    logger.info(f"Parsing natural language (ZH): {text}")

    extracted = {}

    # ---------- 模式选择 ----------
    if text.strip() in {"1", "2", "3"}:
        return extracted

    # ---------- 正则模式 ----------

    weight_patterns = [
        r'體重[:：]?\s*(\d+(?:\.\d+)?)\s*(公斤|kg)',
        r'(\d+(?:\.\d+)?)\s*(公斤|kg)'
    ]

    height_patterns = [
        r'身高[:：]?\s*(\d+(?:\.\d+)?)\s*(公分|cm)',
        r'(\d+(?:\.\d+)?)\s*(公分|cm)'
    ]

    age_patterns = [
        r'(\d{1,3})\s*歲',
        r'年齡[:：]?\s*(\d{1,3})'
    ]

    sex_patterns = [
        r'(男|男性)',
        r'(女|女性)'
    ]

    family_patterns = [
        r'家族病史',
        r'家族史',
        r'家人.*糖尿病',
        r'父母.*糖尿病'
    ]

    smoking_patterns = [
        r'抽菸',
        r'吸菸',
        r'抽煙'
    ]

    alcohol_patterns = [
        r'喝酒',
        r'飲酒'
    ]

    # ---------- 體重 ----------
    for pattern in weight_patterns:
        match = re.search(pattern, text)
        if match:
            extracted["weight"] = match.group(1)
            break

    # ---------- 身高 ----------
    for pattern in height_patterns:
        match = re.search(pattern, text)
        if match:
            extracted["height"] = match.group(1)
            break

    # ---------- 年齡 ----------
    for pattern in age_patterns:
        match = re.search(pattern, text)
        if match:
            extracted["age"] = match.group(1)
            break

    # ---------- 性別 ----------
    for pattern in sex_patterns:
        match = re.search(pattern, text)
        if match:
            extracted["sex"] = "Male" if "男" in match.group(1) else "Female"
            break

    # ---------- 家族病史 ----------
    for pattern in family_patterns:
        match = re.search(pattern, text)
        if match:
            context = extract_local_context(text, match.group())
            val = normalize_yes_no_zh(context)
            if val:
                extracted["family_history"] = val
            break

    # ---------- 吸菸 ----------
    for pattern in smoking_patterns:
        match = re.search(pattern, text)
        if match:
            context = extract_local_context(text, match.group())
            val = normalize_yes_no_zh(context)
            if val:
                extracted["smoking"] = val
            break

    # ---------- 飲酒 ----------
    for pattern in alcohol_patterns:
        match = re.search(pattern, text)
        if match:
            context = extract_local_context(text, match.group())
            val = normalize_alcohol_zh(context)
            if val:
                extracted["alcohol"] = val
            break

    logger.info(f"Final extracted fields (ZH): {extracted}")
    return extracted
