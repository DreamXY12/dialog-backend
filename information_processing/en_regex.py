# 英文注册过程中对英文注册信息做正则解析
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