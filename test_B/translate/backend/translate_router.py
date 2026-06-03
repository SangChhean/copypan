"""
test_B/translate 独立后端 — 纲目翻译路由。
支持：中文→英文（zh2en）、英文→中文（en2zh）、中文→韩文（zh2ko）
"""
from __future__ import annotations
import asyncio
import logging
import os
import threading
import time
from pathlib import Path
from typing import List, Optional
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).resolve().parent / ".env")

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 100_000

OUTLINE_TRANSLATE_PROMPT_ZH2EN = (
    "请将文章翻译为英文，严格使用System instructions中的专用术语表进行翻译。"
    "格式要求：①中文序号为壹，翻译为英文I.，一翻译为A.，二翻译为B.，1翻译为1.，a翻译为a.，(一)翻译为1)，以此类推；②不要缩进，直接输出。"
)
OUTLINE_TRANSLATE_PROMPT_EN2ZH = (
    "请将文章翻译为中文，严格使用System instructions中的专用术语表进行翻译。"
    "格式要求：①读经格式为缩写，例如：罗一1；②英文序号为I.，翻译为中文壹，A.翻译为一，1.翻译为1，a.翻译为a，以此类推；③不要缩进，直接输出。"
)
OUTLINE_TRANSLATE_PROMPT_ZH2KO = (
    "请将以上中文纲目翻译为韩文。要求："
    "1. 使用上方术语表中的专用韩文术语；"
    "2. 严格保留原纲目的层级结构、缩进格式与编号（壹贰叁等保留原字或译为일이삼）；"
    "3. 只输出翻译后的韩文纲目，不添加任何说明或注释。"
)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
GEMINI_TRANSLATION_FALLBACK_MODEL = os.getenv("GEMINI_TRANSLATION_FALLBACK_MODEL", "gemini-2.5-flash")

gemini_client = None
if GEMINI_API_KEY:
    try:
        from google import genai
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        logger.info("Gemini 客户端初始化成功")
    except Exception as e:
        logger.error("Gemini 客户端初始化失败: %s", e)
else:
    logger.warning("GEMINI_API_KEY 未设置")

GEMINI_SEMAPHORE = threading.Semaphore(10)

router = APIRouter(prefix="/api/test_b/translate")

class TranslateRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=MAX_CONTENT_CHARS)
    direction: str = Field(..., description="zh2en | en2zh | zh2ko")

def _is_model_not_found(err: str) -> bool:
    return "404" in err or "NOT_FOUND" in err or "is not found" in err.lower()

def _gemini_error_is_retryable(error_msg: str) -> bool:
    em = error_msg.lower()
    return (
        "503" in error_msg or "unavailable" in em or "429" in error_msg
        or "timeout" in em or "deadline_exceeded" in em
        or "500" in error_msg or "resource_exhausted" in em
    )

def _user_facing_error(api_errors: List[str], empty_body: bool) -> str:
    if empty_body and not api_errors:
        return "模型未返回正文，请稍后重试"
    if api_errors:
        return f"翻译失败：{api_errors[-1][:200]}"
    return "翻译失败，请稍后重试"

def _get_config(system_instruction):
    try:
        from google.genai import types
        return types.GenerateContentConfig(system_instruction=system_instruction)
    except Exception:
        return None

def _call_gemini(contents: str, system_instruction: str, log_label: str) -> dict:
    if not gemini_client:
        return {"result": None, "error": "翻译服务未配置（请设置 GEMINI_API_KEY）"}

    _last_empty = [False]
    _last_404 = [False]
    _last_retryable = [False]
    api_errors: List[str] = []

    def _call(retry_count: int = 0, model: Optional[str] = None) -> Optional[str]:
        use_model = model or GEMINI_MODEL
        with GEMINI_SEMAPHORE:
            try:
                response = gemini_client.models.generate_content(
                    model=use_model,
                    contents=contents,
                    config=_get_config(system_instruction),
                )
                raw = getattr(response, "text", None) if response else None
                text = raw.strip() if isinstance(raw, str) and raw.strip() else None
                if text:
                    return text
                _last_empty[0] = True
                logger.warning("%s 返回空响应（重试: %s）", log_label, retry_count)
            except Exception as e:
                error_msg = str(e)
                api_errors.append(error_msg)
                if _is_model_not_found(error_msg):
                    _last_404[0] = True
                if _gemini_error_is_retryable(error_msg):
                    _last_retryable[0] = True
                    if retry_count == 0:
                        logger.warning("%s 调用失败（可重试）: %s，2秒后重试...", log_label, e)
                        time.sleep(2)
                else:
                    logger.warning("%s 调用失败: %s", log_label, e)
        return None

    answer = _call(0)
    if answer is None:
        answer = _call(1)
    if answer is None and (_last_404[0] or _last_retryable[0] or _last_empty[0]) and GEMINI_TRANSLATION_FALLBACK_MODEL != GEMINI_MODEL:
        answer = _call(0, GEMINI_TRANSLATION_FALLBACK_MODEL)
        if answer is None:
            answer = _call(1, GEMINI_TRANSLATION_FALLBACK_MODEL)

    if answer is None:
        return {"result": None, "error": _user_facing_error(api_errors, _last_empty[0])}
    return {"result": answer, "error": None}

def _do_translate(content: str, direction: str) -> dict:
    from translation_instruction_zh2ko import GEMINI_TRANSLATION_SYSTEM_INSTRUCTION_ZH2KO

    try:
        import sys
        testa_path = str(Path(__file__).resolve().parents[3] / "testA" / "translate" / "backend")
        if testa_path not in sys.path:
            sys.path.insert(0, testa_path)
        from gemini_translation_instruction import GEMINI_TRANSLATION_SYSTEM_INSTRUCTION
        from gemini_translation_instruction_en2zh import GEMINI_TRANSLATION_SYSTEM_INSTRUCTION_EN2ZH
    except Exception as e:
        logger.warning("无法导入 testA 术语表，使用空 instruction: %s", e)
        GEMINI_TRANSLATION_SYSTEM_INSTRUCTION = ""
        GEMINI_TRANSLATION_SYSTEM_INSTRUCTION_EN2ZH = ""

    outline = (content or "").strip()
    if not outline:
        return {"result": None, "error": "纲目内容为空"}

    if direction == "zh2en":
        contents = outline + "\n\n" + OUTLINE_TRANSLATE_PROMPT_ZH2EN
        return _call_gemini(contents, GEMINI_TRANSLATION_SYSTEM_INSTRUCTION, "test_B-中翻英")
    elif direction == "en2zh":
        contents = outline + "\n\n" + OUTLINE_TRANSLATE_PROMPT_EN2ZH
        return _call_gemini(contents, GEMINI_TRANSLATION_SYSTEM_INSTRUCTION_EN2ZH, "test_B-英翻中")
    elif direction == "zh2ko":
        contents = outline + "\n\n" + OUTLINE_TRANSLATE_PROMPT_ZH2KO
        return _call_gemini(contents, GEMINI_TRANSLATION_SYSTEM_INSTRUCTION_ZH2KO, "test_B-中翻韩")
    else:
        return {"result": None, "error": f"不支持的翻译方向：{direction}"}

@router.post("/translate", summary="纲目翻译 - 支持 zh2en / en2zh / zh2ko")
async def translate(request: TranslateRequest):
    try:
        return await asyncio.to_thread(_do_translate, request.content, request.direction)
    except Exception as e:
        logger.error("translate 失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e
