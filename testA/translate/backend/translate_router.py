"""
testA 独立练习后端 — 纲目翻译路由（不依赖主项目）。
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

from gemini_response_utils import extract_translatable_text, gemini_translation_generate_config
from gemini_translation_instruction import GEMINI_TRANSLATION_SYSTEM_INSTRUCTION
from gemini_translation_instruction_en2zh import GEMINI_TRANSLATION_SYSTEM_INSTRUCTION_EN2ZH

# 英翻西班牙文术语表
import json as _json

_EN2ES_TERMS_PATH = Path(__file__).resolve().parent / "en2es_terms.json"
try:
    with open(_EN2ES_TERMS_PATH, encoding="utf-8") as _f:
        EN2ES_TERMS: dict = _json.load(_f)
    _EN2ES_SORTED = sorted(EN2ES_TERMS.keys(), key=len, reverse=True)
except Exception:
    EN2ES_TERMS = {}
    _EN2ES_SORTED = []

logger = logging.getLogger(__name__)

MAX_CONTENT_CHARS = 100_000

OUTLINE_TRANSLATE_PROMPT_ZH2EN = (
    "请将文章翻译为英文，严格使用System instructions中的专用术语表进行翻译。"
    "格式要求：①中文序号为壹，翻译为英文I.，一翻译为A.，二翻译为B.，1翻译为1.，a翻译为a.，(一)翻译为1)，以此类推；②不要缩进，直接输出。"
)
OUTLINE_TRANSLATE_PROMPT_EN2ZH = (
    "请将文章翻译为中文，严格使用System instructions中的专用术语表进行翻译。"
    "格式要求：①读经格式为缩写，例如：罗一1；②英文序号为I.，翻译为中文壹，A.翻译为一，B.翻译为二，1.翻译为1，a.翻译为a，1)翻译为(一)，以此类推；注意，纲目层级之后只加空格，不加其他符号，如：壹 神爱世人，为世人舍了自己的独生子—约三16：；③不要缩进，直接输出。"
)
OUTLINE_TRANSLATE_PROMPT_EN2ES = (
    "Translate the following English text into Spanish. "
    "Output ONLY the Spanish translation, with no explanations, no notes, no original text, and no markdown formatting."
)


def _build_en2es_system_instruction() -> str:
    if not EN2ES_TERMS:
        return ""
    lines = [
        "You are a professional English-to-Spanish translator for Christian ministry materials.",
        "CRITICAL RULE: Output ONLY the Spanish translation. No explanations, no notes, no original English text, no Chinese text, no markdown, no bullet points. Just the translated Spanish text.",
    ]
    lines.append("Strictly use the following terminology glossary:")
    lines.append("")
    for en, es in EN2ES_TERMS.items():
        lines.append(f"  {en} → {es}")
    return "\n".join(lines)

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
        gemini_client = None
else:
    logger.warning("GEMINI_API_KEY 未设置")


def _parse_concurrent_limit(env_key: str, default: int) -> int:
    try:
        v = int(os.getenv(env_key, str(default)))
        return max(1, v)
    except (ValueError, TypeError):
        return default


GEMINI_SEMAPHORE = threading.Semaphore(_parse_concurrent_limit("GEMINI_CONCURRENT_LIMIT", 10))

router = APIRouter(prefix="/api/test/translate")


class TranslateContentRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=MAX_CONTENT_CHARS, description="待翻译纲目全文")


def _user_facing_translate_error(api_errors: List[str], empty_body: bool) -> str:
    if empty_body and not api_errors:
        return "模型未返回正文，可尝试缩短内容或稍后重试"
    blob = " ".join(api_errors)
    bl = blob.lower()
    if any(
        x in bl
        for x in (
            "api key",
            "api_key",
            "unauthorized",
            "401",
            "invalid authentication",
            "permission_denied",
            "permission denied",
        )
    ):
        return "Gemini API 密钥无效或未授权，请检查 .env 中的 GEMINI_API_KEY"
    if any(
        x in bl
        for x in (
            "429",
            "resource_exhausted",
            "quota",
            "rate limit",
            "too many requests",
            "exhausted",
        )
    ):
        return "调用频率或配额已达上限，请稍后再试或提高 Gemini 配额"
    if any(x in bl for x in ("404", "not_found", "is not found", "not supported for generatecontent")):
        return "当前 GEMINI_MODEL 不可用，请在 .env 中更换模型或调整 GEMINI_TRANSLATION_FALLBACK_MODEL"
    if any(
        x in bl
        for x in (
            "503",
            "unavailable",
            "500",
            "internal",
            "deadline_exceeded",
            "timeout",
            "temporary",
            "connection",
            "reset",
        )
    ):
        return "翻译服务暂时不稳定，请稍后重试"
    if any(x in bl for x in ("safety", "blocked", "recitation", "prohibited", "harmful")):
        return "内容触发安全策略未返回译文，请删减或改写后重试"
    if "max_tokens" in bl or "max token" in bl or "output_token" in bl or "length limit" in bl:
        return "译文长度达到模型输出上限，请缩短原文或分段翻译，或提高 GEMINI_TRANSLATION_MAX_OUTPUT_TOKENS"
    if api_errors:
        tail = (api_errors[-1] or "")[:280]
        return f"翻译失败：{tail}"
    return "纲目内容翻译失败，请稍后重试"


def _gemini_error_is_retryable(error_msg: str) -> bool:
    em = error_msg.lower()
    return (
        "503" in error_msg
        or "unavailable" in em
        or "429" in error_msg
        or "timeout" in em
        or "temporary" in em
        or "deadline_exceeded" in em
        or "500" in error_msg
        or "internal" in em
        or "resource_exhausted" in em
    )


def _is_model_not_found(err: str) -> bool:
    return "404" in err or "NOT_FOUND" in err or "is not found" in err.lower()


def _zh2en_config():
    if gemini_translation_generate_config:
        return gemini_translation_generate_config(GEMINI_TRANSLATION_SYSTEM_INSTRUCTION)
    from google.genai import types

    return types.GenerateContentConfig(system_instruction=GEMINI_TRANSLATION_SYSTEM_INSTRUCTION)


def _en2zh_config():
    if gemini_translation_generate_config:
        return gemini_translation_generate_config(GEMINI_TRANSLATION_SYSTEM_INSTRUCTION_EN2ZH)
    from google.genai import types

    return types.GenerateContentConfig(system_instruction=GEMINI_TRANSLATION_SYSTEM_INSTRUCTION_EN2ZH)


def _en2es_config():
    si = _build_en2es_system_instruction()
    return gemini_translation_generate_config(si if si else None)


def _extract_text(response, log_prefix: str) -> Optional[str]:
    if extract_translatable_text:
        return extract_translatable_text(response, log_prefix)
    raw = getattr(response, "text", None) if response else None
    return raw.strip() if isinstance(raw, str) and raw.strip() else None


def _call_gemini_translate(
    *,
    contents: str,
    config_factory,
    log_label: str,
    system_instruction_ok: bool,
    missing_instruction_error: str,
) -> dict:
    if not system_instruction_ok:
        return {"result": None, "error": missing_instruction_error}
    if not gemini_client:
        return {"result": None, "error": "翻译服务未配置（请设置 GEMINI_API_KEY）"}

    _last_error_model_not_found = [False]
    _last_error_retryable = [False]
    _last_error_empty = [False]
    api_errors: List[str] = []

    def _call(retry_count: int = 0, model: Optional[str] = None) -> Optional[str]:
        use_model = model or GEMINI_MODEL
        with GEMINI_SEMAPHORE:
            try:
                response = gemini_client.models.generate_content(
                    model=use_model,
                    contents=contents,
                    config=config_factory(),
                )
                text = _extract_text(response, f"[{log_label}] model={use_model}")
                if text:
                    return text
                _last_error_empty[0] = True
                logger.warning("%s 返回空响应（重试次数: %s）", log_label, retry_count)
            except Exception as e:
                error_msg = str(e)
                api_errors.append(error_msg)
                if _is_model_not_found(error_msg):
                    _last_error_model_not_found[0] = True
                is_retryable = _gemini_error_is_retryable(error_msg)
                if is_retryable:
                    _last_error_retryable[0] = True
                if is_retryable and retry_count == 0:
                    logger.warning("%s 调用失败（可重试）: %s，等待2秒后重试...", log_label, e)
                    time.sleep(2)
                else:
                    logger.warning("%s 调用失败（重试次数: %s）: %s", log_label, retry_count, e)
        return None

    answer = _call(retry_count=0)
    if answer is None:
        answer = _call(retry_count=1)
    if answer is None and (
        _last_error_model_not_found[0] or _last_error_retryable[0] or _last_error_empty[0]
    ) and GEMINI_TRANSLATION_FALLBACK_MODEL != GEMINI_MODEL:
        answer = _call(retry_count=0, model=GEMINI_TRANSLATION_FALLBACK_MODEL)
        if answer is None:
            answer = _call(retry_count=1, model=GEMINI_TRANSLATION_FALLBACK_MODEL)

    if answer is None:
        return {
            "result": None,
            "error": _user_facing_translate_error(api_errors, _last_error_empty[0]),
        }
    return {"result": answer, "error": None}


def _translate_zh2en(content: str) -> dict:
    outline = (content or "").strip()
    if not outline:
        return {"result": None, "error": "中文纲目为空"}
    if len(outline) > MAX_CONTENT_CHARS:
        return {"result": None, "error": f"中文纲目过长（最多 {MAX_CONTENT_CHARS} 字）"}

    contents_zh2en = outline + "\n\n" + OUTLINE_TRANSLATE_PROMPT_ZH2EN
    return _call_gemini_translate(
        contents=contents_zh2en,
        config_factory=_zh2en_config,
        log_label="testA-Gemini翻译",
        system_instruction_ok=bool(GEMINI_TRANSLATION_SYSTEM_INSTRUCTION),
        missing_instruction_error="中翻英 instruction 未配置",
    )


def _translate_en2zh(content: str) -> dict:
    outline = (content or "").strip()
    if not outline:
        return {"result": None, "error": "英文纲目为空"}
    if len(outline) > MAX_CONTENT_CHARS:
        return {"result": None, "error": f"英文纲目过长（最多 {MAX_CONTENT_CHARS} 字）"}

    if not GEMINI_TRANSLATION_SYSTEM_INSTRUCTION_EN2ZH:
        return {"result": None, "error": "英翻中 instruction 未配置"}

    contents_en2zh = outline + "\n\n" + OUTLINE_TRANSLATE_PROMPT_EN2ZH
    return _call_gemini_translate(
        contents=contents_en2zh,
        config_factory=_en2zh_config,
        log_label="testA-Gemini英翻中",
        system_instruction_ok=True,
        missing_instruction_error="英翻中 instruction 未配置",
    )


def _translate_en2es(content: str) -> dict:
    outline = (content or "").strip()
    if not outline:
        return {"result": None, "error": "英文纲目为空"}
    if len(outline) > MAX_CONTENT_CHARS:
        return {"result": None, "error": f"英文纲目过长（最多 {MAX_CONTENT_CHARS} 字）"}

    contents_en2es = outline + "\n\n" + OUTLINE_TRANSLATE_PROMPT_EN2ES
    raw = _call_gemini_translate(
        contents=contents_en2es,
        config_factory=_en2es_config,
        log_label="testA-Gemini英翻西",
        system_instruction_ok=True,
        missing_instruction_error="",
    )
    # 清洗：提取最长的连续西班牙文段落，去除多余说明
    if raw.get("result"):
        import re

        text = raw["result"]
        # 去除 markdown 加粗
        text = re.sub(r"\*+", "", text)
        # 只保留含拉丁字母的行，过滤中文行
        lines = text.splitlines()
        es_lines = [l.strip() for l in lines if l.strip() and not re.search(r"[\u4e00-\u9fff]", l)]
        # 去除以 * - • 开头的注释行
        es_lines = [l for l in es_lines if not re.match(r"^[\*\-•]", l)]
        raw["result"] = "\n".join(es_lines).strip()
    return raw


@router.post("/zh2en", summary="纲目翻译练习 - 中文→英文")
async def translate_zh2en(request: TranslateContentRequest):
    try:
        return await asyncio.to_thread(_translate_zh2en, request.content)
    except Exception as e:
        logger.error("translate zh2en 失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/en2zh", summary="纲目翻译练习 - 英文→中文")
async def translate_en2zh(request: TranslateContentRequest):
    try:
        return await asyncio.to_thread(_translate_en2zh, request.content)
    except Exception as e:
        logger.error("translate en2zh 失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/en2es", summary="纲目翻译练习 - 英文→西班牙文")
async def translate_en2es(request: TranslateContentRequest):
    try:
        return await asyncio.to_thread(_translate_en2es, request.content)
    except Exception as e:
        logger.error("translate en2es 失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e
