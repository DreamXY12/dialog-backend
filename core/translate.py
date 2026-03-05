'''
Description: GCP translate API for translation services, base language is English
'''
# 尝试导入 Google Cloud Translate API，如果失败则只使用 deep_translator
try:
    from google.cloud import translate_v2 as translate
    import os
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "resources/iabot-386300-3d0a88bf4d0f.json"
    has_google_cloud = True
    #google_translate_client = translate.Client()
except ImportError:
    has_google_cloud = False
    print("Warning: Google Cloud Translate not available, using deep_translator only")

from deep_translator import GoogleTranslator

#将一些提示词固定下来，不让翻译软件翻译
HEALTH_INFO_DICT={
    "weight":"體重",
    "height":"身高",
    "age":"年齡",
    "sex":"性別",
    "family_history":"家族病史",
    "family history":"家族病史",
    "smoking":"吸烟習慣",
    "alcohol":"飲酒習慣"
}

RESPONSE_INFO_DICT={
    "female":"女",
    "male":"男",
    "prefer not to tell":"不願透露",
    "yes":"有",
    "no":"沒有",
    "unknown":"不清楚",
    "never":"從不",
    "rarely":"很少（一年幾次）",
    "occasionally":"偶爾（每月一次）",
    "frequently":"頻繁地（每週數次）",
    "daily":"每日"
}

# ================== 语义词表 ==================

AFFIRMATIVE_WORDS = [
    "yes", "have", "has", "with", "positive", "present",
    "there is", "there are", "history of"
]

NEGATIVE_WORDS = [
    "no", "not", "none", "without", "negative",
    "does not", "do not", "never", "deny"
]

UNKNOWN_WORDS = [
    "unknown", "unsure", "not sure", "uncertain"
]

PREFER_NOT_WORDS = [
    "prefer not", "rather not", "decline"
]

ALCOHOL_OCCASIONAL_WORDS = [
    "occasionally",
    "occasional",
    "occasionals",
    "occasionalies",   # 非标准但高频
    "sometimes"
]


# ================== 工具函数 ==================

def normalize_yes_no(text: str):
    """Yes / No / Unknown / Prefer not to tell"""
    text = text.lower()

    for w in PREFER_NOT_WORDS:
        if w in text:
            return "Prefer not to tell"

    for w in UNKNOWN_WORDS:
        if w in text:
            return "Unknown"

    for w in NEGATIVE_WORDS:
        if w in text:
            return "No"

    for w in AFFIRMATIVE_WORDS:
        if w in text:
            return "Yes"

    return None


def normalize_alcohol(text: str):
    """饮酒频率（容错拼写）"""
    text = text.lower()

    if any(w in text for w in ["never", "do not drink", "does not drink"]):
        return "Never"

    if any(w in text for w in ALCOHOL_OCCASIONAL_WORDS):
        return "Occasionally"

    if "rarely" in text:
        return "Rarely"

    if any(w in text for w in ["frequently", "often"]):
        return "Frequently"

    if any(w in text for w in ["daily", "every day"]):
        return "Daily"

    return None


def extract_local_context(text, keyword, window=40):
    """字段级上下文截取"""
    idx = text.find(keyword)
    if idx == -1:
        return ""
    start = max(0, idx - window)
    end = min(len(text), idx + len(keyword) + window)
    return text[start:end]

#Input text
# def to_other_language(text, target_language):
#     # Translate to Traditional Chinese (often outputs Cantonese-style if informal)
#     print("开始翻译")
#     result = google_translate_client.translate(
#         text, 
#         target_language=target_language, 
#         model='nmt',
#         format_='text'
#         )
#     # Output result
#     return result['translatedText']

#这个函数是用于处理用户在注册后的对话和模型返回的消息，进行相应的翻译
def to_other_language(text, target_language):
    if target_language == "yue":
        target_language="zh-TW"
    translate_text = GoogleTranslator(source="auto", target=target_language).translate(text)
    return translate_text

#包一层，用户输入繁中->内部英文
def user_input_to_internal_language(text) -> str:
    translate_text = GoogleTranslator(source="zh-TW", target="en").translate(text)
    return translate_text

#获取固定字段的翻译
def get_fixed_field_translation(text) -> str:
    if text not in HEALTH_INFO_DICT:
        return text #没有就原路返回
    else:
        return HEALTH_INFO_DICT[text]

def get_fixed_response_translation(text) -> str:
    if text not in RESPONSE_INFO_DICT:
        return text
    else:
        return RESPONSE_INFO_DICT[text]
