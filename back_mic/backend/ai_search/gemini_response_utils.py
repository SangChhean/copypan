# -*- coding: utf-8 -*-
"""
Gemini generate_content 响应解析与纲目翻译专用配置。

- 关闭 AFC，避免仅返回 function_call 而无正文。
- 可选关闭 thinking（thinking_budget=0），减少「仅有思考块、用户可见 text 为空」的情况。
- 从响应中提取可翻译正文（与 SDK 的 response.text 一致，并补充诊断日志）。
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

try:
    from google.genai import types as genai_types
except ImportError:
    genai_types = None


def gemini_translation_generate_config(system_instruction: Any) -> Any:
    """
    纲目翻译专用 GenerateContentConfig：关闭 AFC；可按环境变量控制 thinking。
    GEMINI_TRANSLATION_THINKING_BUDGET：未设置或空则 0（关闭内部思考）；设为 skip 则不下发 thinking_config。
    """
    if genai_types is None:
        raise RuntimeError("google.genai 未安装")

    raw_budget = os.environ.get("GEMINI_TRANSLATION_THINKING_BUDGET", "0").strip().lower()
    kwargs: dict[str, Any] = {
        "system_instruction": system_instruction,
        "automatic_function_calling": genai_types.AutomaticFunctionCallingConfig(disable=True),
    }
    if raw_budget not in ("skip", "none", "-"):
        try:
            budget = 0 if raw_budget == "" else int(raw_budget)
            kwargs["thinking_config"] = genai_types.ThinkingConfig(thinking_budget=budget)
        except ValueError:
            logger.warning(
                "GEMINI_TRANSLATION_THINKING_BUDGET=%r 无效，使用 thinking_budget=0",
                os.environ.get("GEMINI_TRANSLATION_THINKING_BUDGET"),
            )
            kwargs["thinking_config"] = genai_types.ThinkingConfig(thinking_budget=0)

    return genai_types.GenerateContentConfig(**kwargs)


def _part_summary(part: Any) -> str:
    """单行摘要，便于排查空响应。"""
    try:
        t = getattr(part, "thought", None)
        if t is True:
            th = "thought=yes"
        elif t is False:
            th = "thought=no"
        else:
            th = "thought=None"
        txt = getattr(part, "text", None)
        text_hint = f"text_len={len(txt)}" if isinstance(txt, str) else "text=None"
        if getattr(part, "function_call", None) is not None:
            return f"{th},{text_hint},has=function_call"
        if getattr(part, "function_response", None) is not None:
            return f"{th},{text_hint},has=function_response"
        return f"{th},{text_hint}"
    except Exception as e:
        return f"<part_summary_err {e}>"


def log_empty_gemini_response(response: Any, log_prefix: str) -> None:
    """空正文时记录 finish_reason 与各 part 摘要。"""
    try:
        cands = getattr(response, "candidates", None) or []
        if not cands:
            logger.warning("%s 空响应诊断: candidates 为空", log_prefix)
            return
        c0 = cands[0]
        fr = getattr(c0, "finish_reason", None)
        parts = None
        if c0.content and getattr(c0.content, "parts", None):
            parts = c0.content.parts
        if not parts:
            logger.warning("%s 空响应诊断: finish_reason=%s, parts 为空", log_prefix, fr)
            return
        summaries = [_part_summary(p) for p in parts]
        logger.warning(
            "%s 空响应诊断: finish_reason=%s, part_count=%d, parts=[%s]",
            log_prefix,
            fr,
            len(parts),
            " | ".join(summaries),
        )
    except Exception as e:
        logger.warning("%s 空响应诊断记录失败: %s", log_prefix, e)


def extract_translatable_text(response: Any, log_prefix: str = "Gemini") -> Optional[str]:
    """
    从 GenerateContentResponse 取出可展示的正文。
    优先使用 SDK 的 response.text（已跳过 thought=True 的 part）。
    若仍为空，做一次按 part 的手动拼接（同样跳过 thought 块），以兼容 SDK 边界情况。
    """
    if not response:
        return None

    text: Optional[str] = None
    try:
        text = response.text
    except Exception as e:
        logger.debug("%s response.text 访问异常: %s", log_prefix, e)

    if isinstance(text, str) and text.strip():
        return text.strip()

    # 手动从 parts 拼接（与 SDK _get_text 逻辑对齐）
    try:
        cands = getattr(response, "candidates", None) or []
        if not cands or not cands[0].content or not cands[0].content.parts:
            log_empty_gemini_response(response, log_prefix)
            return None
        buf: list[str] = []
        for part in cands[0].content.parts:
            if getattr(part, "thought", None) is True:
                continue
            pt = getattr(part, "text", None)
            if isinstance(pt, str) and pt:
                buf.append(pt)
        merged = "".join(buf).strip() if buf else ""
        if merged:
            logger.info("%s 使用 parts 手动拼接得到正文（len=%d）", log_prefix, len(merged))
            return merged
    except Exception as e:
        logger.warning("%s 手动解析 parts 失败: %s", log_prefix, e)

    log_empty_gemini_response(response, log_prefix)
    return None
