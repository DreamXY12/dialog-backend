# 语音识别模块
# 采用SenseVoice small模型，占据内存（无GPU）大概800MB到1G

# -*- coding:utf-8 -*-
from fastapi import APIRouter, UploadFile, HTTPException
import os
import logging
import io
import numpy as np
import soundfile as sf
import subprocess
import re

# 简繁转换库
from opencc import OpenCC

from sensevoice.onnx.sense_voice_ort_session import SenseVoiceInferenceSession
from sensevoice.utils.frontend import WavFrontend
from sensevoice.utils.fsmn_vad import FSMNVad
from huggingface_hub import snapshot_download

router = APIRouter(prefix="/voice", tags=["speech_recognition"])

logging.basicConfig(
    format="%(asctime)s %(levelname)s [%(filename)s:%(lineno)d] %(message)s",
    level=logging.INFO
)

# 配置简繁转换（粤语 → 香港繁体）
cc_yue = OpenCC('s2hk')

MODEL_PATH = os.path.join(os.path.dirname(__file__), "resource")
LANGUAGES = {"auto": 0, "zh": 3, "en": 4, "yue": 7, "ja": 11, "ko": 12, "nospeech": 13}

if not os.path.exists(MODEL_PATH):
    logging.info("正在下载模型...")
    snapshot_download(repo_id="lovemefan/SenseVoice-onnx", local_dir=MODEL_PATH)

logging.info("加载模型中...")
front = WavFrontend(os.path.join(MODEL_PATH, "am.mvn"))
vad = FSMNVad(MODEL_PATH)
model = SenseVoiceInferenceSession(
    os.path.join(MODEL_PATH, "embedding.npy"),
    os.path.join(MODEL_PATH, "sense-voice-encoder.onnx"),
    os.path.join(MODEL_PATH, "chn_jpn_yue_eng_ko_spectok.bpe.model"),
    device_id=-1,
    intra_op_num_threads=4
)
logging.info("模型加载完成 ✅")


# -------------------------------------------------------------------------
# 智能清理文本：按语言标签自动转换
# -------------------------------------------------------------------------
def clean_text(text: str) -> str:
    # 1. 提取语言类型 yue / zh / en
    lang_match = re.search(r"<\|(yue|zh|en)\|>", text)
    lang = lang_match.group(1) if lang_match else "zh"

    # 2. 移除所有模型标签 <|xxx|>
    text = re.sub(r"<\|.*?\|>", "", text)
    text = text.strip()

    # 3. 只有粤语转香港繁体
    if lang == "yue" or lang == "zh":
        text = cc_yue.convert(text)

    return text


# -------------------------------------------------------------------------
# 直接用 ffmpeg 内存转码，不使用 pydub，彻底解决报错
# -------------------------------------------------------------------------
def process_audio(audio_bytes: bytes) -> np.ndarray:
    cmd = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel", "error",
        "-i", "pipe:0",
        "-ar", "16000",
        "-ac", "1",
        "-f", "wav",
        "pipe:1"
    ]
    try:
        proc = subprocess.run(
            cmd,
            input=audio_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        wav_bytes = proc.stdout
        wav_io = io.BytesIO(wav_bytes)
        waveform, sr = sf.read(wav_io, dtype="float32")
        return waveform
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"音频转换失败: {e.stderr.decode()}")


# -------------------------------------------------------------------------
# 识别接口
# -------------------------------------------------------------------------
@router.post("/recognize")
async def recognize(file: UploadFile):
    try:
        audio_bytes = await file.read()
        waveform = process_audio(audio_bytes)

        segments = vad.segments_offline(waveform)
        result_text = ""

        for seg in segments:
            start_idx = seg[0] * 16
            end_idx = seg[1] * 16
            feats = front.get_features(waveform[start_idx:end_idx])
            text = model(feats[None, ...], language=LANGUAGES["auto"], use_itn=True)

            # 智能清理 + 繁简转换
            text = clean_text(text)
            result_text += text + " "

        return {
            "code": 200,
            "text": result_text.strip()
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"处理失败：{str(e)}")


@router.get("/")
def health():
    return {"status": "running", "model": "SenseVoice Small ONNX"}