# -*- coding: utf-8 -*-
"""QA 翻译服务：简体→台湾繁体（OpenCC + 术语表），以及 chunk 级中文→英文（Gemini）。

入口函数:
- to_traditional(text)                       简→繁
- translate_answer_to_traditional(answer)    Step4 答案简→繁
- prepare_english_chunks(passages)           检索 chunk 列表中文→英文（已带 en 字段优先）
"""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger("qa")

# 术语表与 back_mic 一致，但本服务读取 back_qa/zh_tw_terms.json（避免跨项目依赖）
_TERMS_PATH = Path(__file__).resolve().parents[1] / "zh_tw_terms.json"

# Gemini 客户端懒加载（参考 asr_service 中 _get_client 的写法）
_gemini_client: Any = None
_GEMINI_MODEL = os.environ.get("QA_TRANSLATION_GEMINI_MODEL", "gemini-2.5-flash")

_CHUNK_TRANSLATION_INSTRUCTION = (
    "你是专业的职事信息中翻英助手。请将以下中文段落翻译成英文。\n"
    "要求：直接输出译文，不加任何前缀或解释；保留原文语气和神学术语；\n"
    "专有词参考：召会=church, 那灵=the Spirit, 职事=ministry, 三一神=the Triune God 等"
)


def _get_gemini_client() -> Any:
    global _gemini_client
    if _gemini_client is None:
        api_key = (os.environ.get("GEMINI_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError("未配置 GEMINI_API_KEY")
        from google import genai
        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


# ---------------------------------------------------------------------------
# 简 → 繁
# ---------------------------------------------------------------------------

def to_traditional(text: str) -> str:
    """简体 → 台湾繁体：先按术语表占位替换，再 OpenCC s2tw（失败回退 zhconv zh-tw）。
    依赖全部缺失或异常时返回原文（不抛错）。
    """
    src = text or ""
    if not src.strip():
        return src
    out = src
    try:
        placeholders: list[tuple[str, str]] = []
        if _TERMS_PATH.exists():
            try:
                terms = json.loads(_TERMS_PATH.read_text(encoding="utf-8"))
            except Exception as e:
                logger.warning("[QA] 繁简术语表解析失败: %s", e)
                terms = {}
            sorted_keys = sorted(terms.keys(), key=len, reverse=True)
            for idx, simp in enumerate(sorted_keys):
                trad = terms.get(simp)
                if simp and trad is not None:
                    ph = f"__TW_{idx}__"
                    placeholders.append((ph, trad))
                    out = out.replace(simp, ph)
        else:
            logger.warning("[QA] 繁简术语表不存在: %s，仅做通用简繁转换", _TERMS_PATH)

        try:
            from opencc import OpenCC
            cc = OpenCC("s2tw")
            out = cc.convert(out)
        except Exception:
            try:
                import zhconv
                out = zhconv.convert(out, "zh-tw")
            except ImportError:
                logger.warning("[QA] OpenCC/zhconv 未安装，无法做通用简繁转换")
                return src

        for ph, trad in placeholders:
            out = out.replace(ph, trad)
        return out
    except Exception as e:
        logger.error("[QA] 简转繁失败: %s", e, exc_info=True)
        return src


def translate_answer_to_traditional(answer: str) -> str:
    """Step4 答案简体 → 台湾繁体。"""
    return to_traditional(answer)


# ---------------------------------------------------------------------------
# chunk 级 中文 → 英文
# ---------------------------------------------------------------------------

def _gemini_translate(text: str, max_retries: int = 3) -> str:
    """同步：把单段中文翻译成英文。空输入返回空串；失败抛异常由调用方处理。

    针对 Gemini 503 / UNAVAILABLE 高负载场景做指数退避重试（1s / 2s / 4s），
    其他错误（4xx、配额、配置错误）立刻抛出由调用方处理。
    """
    if not (text or "").strip():
        return ""
    client = _get_gemini_client()
    from google.genai import types

    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=_GEMINI_MODEL,
                contents=text,
                config=types.GenerateContentConfig(
                    system_instruction=_CHUNK_TRANSLATION_INSTRUCTION,
                ),
            )
            out = (getattr(response, "text", "") or "").strip()
            if not out:
                raise RuntimeError("Gemini 返回空响应")
            return out
        except Exception as e:
            last_exc = e
            err_str = str(e)
            # 仅对 503 / UNAVAILABLE 重试，其他错误立刻抛出
            if "503" not in err_str and "UNAVAILABLE" not in err_str:
                raise
            if attempt < max_retries - 1:
                wait = 2 ** attempt  # 1s, 2s, 4s
                logger.warning(
                    "[QA] Gemini 503，第 %d 次重试，等待 %ds: %s",
                    attempt + 1, wait, e,
                )
                time.sleep(wait)
    # 所有重试都失败
    assert last_exc is not None
    raise last_exc


def _translate_chunk_to_english(chunk: dict) -> dict:
    """中文 chunk → 英文 chunk dict（text/source_en 失败时各自降级保留原文，不抛异常）。"""
    text_zh = (chunk.get("text") or "").strip()
    source_zh = (chunk.get("source_zh") or "").strip()

    text_en = text_zh
    if text_zh:
        try:
            text_en = _gemini_translate(text_zh)
        except Exception as e:
            logger.warning("[QA] chunk 文本翻译失败，保留中文原文: %s", e)
            text_en = text_zh

    source_en = source_zh
    if source_zh:
        try:
            source_en = _gemini_translate(source_zh)
        except Exception as e:
            logger.warning("[QA] chunk 来源翻译失败，保留中文 source_zh: %s", e)
            source_en = source_zh

    return {
        **chunk,
        "text": text_en,
        "source_en": source_en,
        "book_title": chunk.get("book_title", ""),
    }


def prepare_english_chunks(passages: list[dict]) -> tuple[list[dict], bool]:
    """每个 chunk：若已有非空 chunk['en'] 直接采用，否则 Gemini 翻译。
    返回 (english_passages, has_translation)；has_translation 表示是否实际触发过翻译。
    """
    english_passages: list[dict] = []
    has_translation = False
    for chunk in passages or []:
        en_field = chunk.get("en")
        en_text = en_field.strip() if isinstance(en_field, str) else ""
        if en_text:
            english_passages.append({
                **chunk,
                "text": en_text,
                "source_en": chunk.get("source_en") or chunk.get("source_zh", ""),
                "book_title": chunk.get("book_title", ""),
            })
            continue

        has_translation = True
        try:
            english_passages.append(_translate_chunk_to_english(chunk))
        except Exception as e:
            logger.warning("[QA] chunk 翻译异常，降级保留原文: %s", e, exc_info=True)
            english_passages.append({
                **chunk,
                "text": chunk.get("text", ""),
                "source_en": chunk.get("source_zh", ""),
                "book_title": chunk.get("book_title", ""),
            })
    return english_passages, has_translation
