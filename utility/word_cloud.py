# -*- coding:utf-8 -*-
import re
import torch
import numpy as np
from collections import Counter
from typing import List, Dict
from opencc import OpenCC
from transformers import BertTokenizer, BertModel

# ====================== 全局模型（只加载一次） ======================
MODEL_NAME = "huawei-noah/TinyBERT_4L_zh"
DEVICE = "cpu"

# 繁 → 简
cc = OpenCC("t2s")

# 加载模型 & INT8 量化（内存 ≈ 200MB）
print("🔹 加载 TinyBERT 关键词模型（INT8 量化）...")
tokenizer = BertTokenizer.from_pretrained(MODEL_NAME)
model = BertModel.from_pretrained(MODEL_NAME)
model.eval()

model_int8 = torch.quantization.quantize_dynamic(
    model,
    {torch.nn.Linear},
    dtype=torch.qint8
)
print("✅ TinyBERT INT8 模型加载完成！内存占用极低 ≈200MB")

ZH_STOP_WORDS = {
    # —————— 1. 结构助词（简+繁）——————
    "的", "嘅", "地", "得", "了", "瞭", "着", "著", "过", "過", "之",

    # —————— 2. 人称代词（简+繁，含单复数）——————
    "我", "我們", "吾", "你", "你們", "妳", "妳們",
    "他", "他們", "她", "她們", "它", "它們",
    "自己", "自己", "本人", "本人", "大家", "大家", "大伙", "大伙",

    # —————— 3. 指示代词（简+繁，重点：这个/那个/这里/那里）——————
    "这", "這", "那", "那",
    "这个", "這個", "那个", "那個",
    "这些", "這些", "那些", "那些",
    "这里", "這裡", "那里", "那裡",
    "这边", "這邊", "那边", "那邊",
    "这样", "這樣", "那样", "那樣",
    "这儿", "這兒", "那儿", "那兒",
    "此", "此", "彼", "彼",

    # —————— 4. 疑问代词（简+繁，重点：哪里/什么/怎么/一下）——————
    "谁", "誰", "什么", "什麼", "哪", "哪",
    "哪里", "哪裡", "哪儿", "哪兒",
    "怎么", "怎麼", "怎么样", "怎麼樣",
    "为什么", "為什麼", "为何", "為何",
    "多少", "多少", "几", "幾", "几时", "幾時",
    "一下", "一下", "一点儿", "一點兒", "一些", "一些",

    # —————— 5. 语气词（简+繁，含口语/粤语）——————
    "吗", "嗎", "吧", "吧", "啊", "啊", "哦", "哦",
    "呀", "呀", "嗯", "嗯", "呢", "呢", "啦", "啦",
    "呦", "呦", "咯", "咯", "哇", "哇", "喔", "喔",
    "嘛", "嘛", "罢了", "罷了", "而已", "而已",
    # 粤语语气词
    "嘅", "咗", "㗎", "㗎啦", "呀嘛", "吖", "嗱", "噃",

    # —————— 6. 副词（高频无用，简+繁）——————
    "很", "很", "非常", "非常", "太", "太", "极", "極",
    "都", "都", "全", "全", "只", "只", "仅", "僅",
    "也", "也", "又", "又", "再", "再", "还", "還",
    "就", "就", "才", "才", "刚", "剛", "已经", "已經",
    "曾经", "曾經", "正在", "正在", "将要", "將要",
    "马上", "馬上", "立刻", "立刻", "忽然", "忽然",
    "大概", "大概", "也许", "也許", "可能", "可能",

    # —————— 7. 介词/连词（简+繁）——————
    "在", "在", "于", "於", "对", "對", "对于", "對於",
    "和", "和", "与", "與", "及", "及", "或", "或",
    "并", "並", "而", "而", "但", "但", "但是", "但是",
    "因为", "因為", "所以", "所以", "虽然", "雖然",
    "如果", "如果", "只要", "只要", "除非", "除非",

    # —————— 8. 数量词（重点：一个/两个/几个，简+繁）——————
    "一", "一", "二", "二", "三", "三", "四", "四", "五", "五",
    "六", "六", "七", "七", "八", "八", "九", "九", "十", "十",
    "零", "零", "百", "百", "千", "千", "万", "萬",
    "一个", "一個", "两个", "兩個", "三个", "三個",
    "几个", "幾個", "多少个", "多少個", "半个", "半個",
    "所有", "所有", "全部", "全部", "一切", "一切",

    # —————— 9. 时间/方位虚词（简+繁）——————
    "现在", "現在", "今天", "今天", "昨天", "昨天", "明天", "明天",
    "刚才", "剛才", "然后", "然後", "后来", "後來", "最后", "最後",
    "这里面", "這裡面", "那里边", "那裡邊", "中间", "中間", "旁边", "旁邊",

    # —————— 10. 粤语口语高频垃圾词（补充）——————
    "唔", "冇", "邊", "點", "同", "而家", "唔好", "嘅话", "嘅話"
}

# ====================== 英文停用词（补充完善） ======================
EN_STOP_WORDS = {
    "i", "me", "my", "you", "your", "he", "him", "his", "she", "her",
    "we", "us", "our", "they", "them", "their", "it", "its",
    "is", "are", "was", "were", "be", "been", "have", "has", "had",
    "do", "does", "did", "will", "would", "shall", "should",
    "a", "an", "the", "and", "or", "but", "nor", "for", "so", "yet",
    "in", "on", "at", "to", "for", "of", "with", "by", "from", "into",
    "this", "that", "these", "those", "here", "there", "where", "when",
    "why", "how", "what", "which", "who", "whom", "all", "any", "both",
    "each", "few", "more", "most", "other", "some", "such", "no", "nor",
    "not", "only", "own", "same", "so", "than", "too", "very", "just"
}

# ====================== 垃圾词正则（兜底过滤） ======================
# 精准匹配：一个、一下、这里、哪里、这个、那个等固定垃圾词
USELESS_WORD_PATTERN = re.compile(
    r"^(一個|一个|兩個|两个|幾個|几个|這裡|这里|那裡|那里|哪裡|哪里|哪些|這個|这个|那個|那个|什麼|什么|怎麼|怎么|一下|一些|一點兒|一点儿)$"
)

ZH_REGEX = re.compile(r"[\u4e00-\u9fff]+")
EN_REGEX = re.compile(r"[a-zA-Z]+")

# ====================== 工具函数：获取词的语义重要度 ======================
def get_word_importance(text: str, words: List[str]) -> Dict[str, float]:
    if not words:
        return {}
    with torch.no_grad():
        inputs = tokenizer(text, padding=True, truncation=True, max_length=512, return_tensors="pt")
        outputs = model_int8(**inputs)
        sentence_emb = outputs.pooler_output.cpu().numpy().squeeze()

    word_scores = {}
    for word in words:
        w_inputs = tokenizer(word, return_tensors="pt", truncation=True, max_length=32)
        w_outputs = model_int8(**w_inputs)
        w_emb = w_outputs.pooler_output.cpu().numpy().squeeze()
        cos_sim = np.dot(sentence_emb, w_emb) / (np.linalg.norm(sentence_emb) * np.linalg.norm(w_emb) + 1e-8)
        word_scores[word] = float(cos_sim)
    return word_scores

# ====================== 主函数（接口不变） ======================
def generate_multilang_word_cloud(contents: List[str], top_n=30) -> List[Dict]:
    if not contents:
        return []

    all_text = " ".join([str(c).strip() for c in contents if c and str(c).strip()])
    all_text = cc.convert(all_text)

    # 提取中文
    zh_words = []
    zh_blocks = ZH_REGEX.findall(all_text)
    if zh_blocks:
        from jieba import lcut
        zh_raw = lcut("".join(zh_blocks))
        zh_words = [
            w for w in zh_raw
            if len(w) >= 2  # 强制只保留 2 字及以上词语
            and w not in ZH_STOP_WORDS  # 停用词过滤
            and not USELESS_WORD_PATTERN.match(w)  # 双重过滤垃圾词
        ]

    # 提取英文
    en_raw = EN_REGEX.findall(all_text.lower())
    en_words = [
        w for w in en_raw
        if len(w) >= 3
        and w not in EN_STOP_WORDS
    ]

    words = zh_words + en_words
    # 过滤语义分过低的词
    word_scores = get_word_importance(all_text, words)
    # 过滤语义相似度 < 0.2 的弱相关词
    words = [w for w in words if word_scores.get(w, 0.0) >= 0.2]
    if not words:
        return []

    # 语义加权
    word_scores = get_word_importance(all_text, words)
    word_counter = Counter(words)
    final_score = {w: cnt * (0.5 + word_scores.get(w, 0.5)) for w, cnt in word_counter.items()}

    sorted_words = sorted(final_score.items(), key=lambda x: x[1], reverse=True)[:top_n]
    return [{"text": w, "value": round(score)} for w, score in sorted_words]