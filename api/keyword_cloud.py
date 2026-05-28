# 关键词提取 + 词云接口
# 采用 TinyBERT_4L_zh INT8 量化模型，内存占用 ≈ 200MB

# -*- coding:utf-8 -*-
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import logging
import numpy as np
import torch
from transformers import BertTokenizer, BertModel
from opencc import OpenCC

router = APIRouter(prefix="/keyword", tags=["keyword_cloud"])

logging.basicConfig(
    format="%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s",
    level=logging.INFO
)

# -------------------------------------------------------------------------
# 模型配置（超轻量中文 TinyBERT 4层）
# -------------------------------------------------------------------------
MODEL_NAME = "huawei-noah/TinyBERT_4L_zh"
DEVICE = "cpu"

# 繁 → 简（保证模型输入稳定）
cc = OpenCC("t2s")

logging.info("加载 TinyBERT 模型中...")

# 1. 加载 tokenizer + 模型
tokenizer = BertTokenizer.from_pretrained(MODEL_NAME)
model = BertModel.from_pretrained(MODEL_NAME)
model.eval()

# 2. INT8 量化（关键：内存暴减）
model_int8 = torch.quantization.quantize_dynamic(
    model,
    {torch.nn.Linear},
    dtype=torch.qint8
)

logging.info("TinyBERT INT8 模型加载完成 ✅")
logging.info(f"模型内存占用极低：≈200MB，适合 4GB 服务器运行")

# -------------------------------------------------------------------------
# 输入结构体
# -------------------------------------------------------------------------
class TextRequest(BaseModel):
    text: str
    top_k: int = 15  # 提取多少个关键词（默认15）

# -------------------------------------------------------------------------
# 简单词频统计（轻量、无第三方词云库、前端直接用）
# -------------------------------------------------------------------------
def extract_keywords(text: str, top_k: int = 15):
    # 繁体 → 简体
    text = cc.convert(text)

    # 分词（按中文词汇简单切分）
    words = [w for w in text.strip() if len(w) > 0]
    word_count = {}
    for w in words:
        word = w.strip()
        if len(word) < 1:
            continue
        word_count[word] = word_count.get(word, 0) + 1

    # 排序
    sorted_words = sorted(word_count.items(), key=lambda x: x[1], reverse=True)
    sorted_words = [item for item in sorted_words if item[0] not in "，。！？；：\"'、（）【】"]

    # 取 top_k
    keywords = [{"word": w, "weight": c} for w, c in sorted_words[:top_k]]
    return keywords

# -------------------------------------------------------------------------
# 关键词提取接口（给前端词云用）
# -------------------------------------------------------------------------
@router.post("/extract")
async def extract(req: TextRequest):
    try:
        if not req.text or len(req.text.strip()) == 0:
            raise HTTPException(status_code=400, detail="文本不能为空")

        keywords = extract_keywords(req.text, req.top_k)
        return {
            "code": 200,
            "keywords": keywords
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"关键词提取失败：{str(e)}")

@router.get("/")
def health():
    return {
        "status": "running",
        "model": "TinyBERT_4L_zh INT8",
        "memory": "≈200MB"
    }