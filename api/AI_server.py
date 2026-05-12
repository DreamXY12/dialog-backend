# 忽略 SSL 不安全警告（测试环境专用）
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from fastapi import APIRouter
from fastapi import HTTPException
import requests  # 用来发请求第三方后端
import time
from fastapi.responses import StreamingResponse
import json
import asyncio

AI_BASE_URL="https://agent.dialog.polyusn.com"

router = APIRouter(tags=["dialog_ai"])

# 1. 健康检查AI 请求失败
@router.get("/health")
async def ai_health():
    try:
        res = requests.get(f"{AI_BASE_URL}/health", timeout=5, verify=False)
        return res.json()
    except:
        raise HTTPException(status_code=503, detail="AI 服务不可用")

# 2. 公共聊天接口（创建/继续对话）
@router.post("/api/public/chat")
async def public_chat(request_data: dict):
    try:
        res = requests.post(
            url=f"{AI_BASE_URL}/api/public/chat",
            json=request_data,
            timeout=30,
            verify=False
        )
        if not res.ok:
            raise HTTPException(status_code=res.status_code, detail=res.text)
        return res.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI聊天错误：{str(e)}")

# 3. 获取历史会话（刷新恢复对话）,对我前端没有用，因为我还得加载护士对话
@router.get("/api/public/sessions/{session_id}")
async def get_public_session(session_id: str):
    try:
        res = requests.get(
            url=f"{AI_BASE_URL}/api/public/sessions/{session_id}",
            timeout=10,
            verify=False
        )
        if not res.ok:
            raise HTTPException(status_code=res.status_code, detail="会话不存在或已失效")
        return res.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取会话失败：{str(e)}")

# 3. AI 总结对话
@router.post("/ai/summary")
async def ai_summary(request_data: dict):
    try:
        res = requests.post(
            url=f"{AI_BASE_URL}/ai/summary",
            json=request_data,
            timeout=20,
            verify=False
        )
        if not res.ok:
            raise HTTPException(status_code=res.status_code, detail=res.text)
        return res.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"总结失败：{str(e)}")

# ======================================================
# 【三】DEBUG 调试接口（全部加 /debug 前缀！）
# 仅开发用，不上生产
# ======================================================

# Debug 聊天（带内部信息）
@router.post("/debug/api/chat")
async def debug_chat(request_data: dict):
    try:
        res = requests.post(
            url=f"{AI_BASE_URL}/api/chat",
            json=request_data,
            timeout=30,
            verify=False
        )
        if not res.ok:
            raise HTTPException(status_code=res.status_code, detail=res.text)
        return res.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Debug聊天错误：{str(e)}")

# Debug 获取会话（完整内部信息）
@router.get("/debug/api/sessions/{session_id}")
async def debug_session(session_id: str):
    try:
        res = requests.get(
            url=f"{AI_BASE_URL}/api/sessions/{session_id}",
            timeout=10,
            verify=False
        )
        if not res.ok:
            raise HTTPException(status_code=res.status_code, detail=res.text)
        return res.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Debug会话错误：{str(e)}")

# 百度 OpenAI 兼容模式 强制要求的路径
@router.post("/compatible/api/public/chat/chat/completions")
async def compatible_public_chat(request_data: dict):
    try:
        # 1. 提取用户消息
        user_message = ""
        if "messages" in request_data:
            for msg in request_data["messages"]:
                if msg.get("role") == "user":
                    user_message = msg.get("content", "").strip()
                    break

        if not user_message:
            raise HTTPException(status_code=400, detail="未获取到用户消息")

        session_id = request_data.get("session_id", "")
        stream = request_data.get("stream", False)

        # 2. 调用你真实的AI接口
        res = requests.post(
            url=f"{AI_BASE_URL}/api/public/chat",
            json={"message": user_message, "session_id": session_id},
            timeout=100,
            verify=False
        )
        ai_response = res.json()
        content = ai_response.get("message", "未获取到回复")

        # ==============================================
        # 关键：百度开启了 stream=True，逐字流式输出！
        # ==============================================
        if stream:
            async def generate():
                # 逐字发送
                for char in content:
                    data = {
                        "id": f"chat-{int(time.time())}",
                        "object": "chat.completion.chunk",
                        "created": int(time.time()),
                        "model": "Dialog",
                        "choices": [
                            {"delta": {"content": char}, "index": 0, "finish_reason": None}
                        ]
                    }
                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                    await asyncio.sleep(0.05)  # 逐字速度

                # 结束标志
                yield "data: [DONE]\n\n"

            return StreamingResponse(generate(), media_type="text/event-stream")

        # 非流式（备用）
        return {
            "id": f"chat-{int(time.time())}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "gpt-3.5-turbo",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": "stop"
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"错误：{str(e)}")