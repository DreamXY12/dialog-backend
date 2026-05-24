import re
import jieba
from collections import Counter
from datetime import date
from typing import List, Dict

# ====================== 多语言停用词 ======================
# 中文（简繁通用 + 香港粤语虚词）
ZH_STOP_WORDS = {
    "的", "了", "我", "你", "是", "在", "有", "就", "都", "嗎", "吧",
    "啊", "哦", "呀", "嗯", "呢", "這個", "那個", "什麼", "怎麼", "哪裡",
    "嘅", "咗", "唔", "冇", "邊", "點", "㗎", "㗎啦", "呀嘛", "唔好"
}

# 英文停用词
EN_STOP_WORDS = {
    "i", "me", "my", "you", "your", "he", "him", "his", "she", "her",
    "we", "us", "our", "they", "them", "their", "it", "its",
    "is", "are", "was", "were", "be", "been", "have", "has", "had",
    "do", "does", "did", "will", "would", "shall", "should",
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to",
    "for", "of", "with", "this", "that", "these", "those"
}

# 正则
ZH_REGEX = re.compile(r"[\u4e00-\u9fff]+")
EN_REGEX = re.compile(r"[a-zA-Z]+")

def generate_multilang_word_cloud(contents: List[str], top_n=30) -> List[Dict]:
    """
    支持：简体中文 + 香港繁体 + 英文
    输出：词云格式 [{"text": "xxx", "value": 12}]
    """
    all_text = " ".join([str(c).strip() for c in contents if c and str(c).strip()])
    words = []

    # 提取中文
    zh_texts = ZH_REGEX.findall(all_text)
    if zh_texts:
        zh_words = jieba.lcut("".join(zh_texts))
        words.extend([
            w for w in zh_words
            if len(w) >= 2 and w not in ZH_STOP_WORDS
        ])

    # 提取英文
    en_words = EN_REGEX.findall(all_text.lower())
    words.extend([
        w for w in en_words
        if len(w) >= 3 and w not in EN_STOP_WORDS
    ])

    # 统计 TOP N
    top_words = Counter(words).most_common(top_n)
    return [{"text": w, "value": cnt} for w, cnt in top_words]