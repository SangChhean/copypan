# -*- coding: utf-8 -*-
"""
Gemini generate_content 响应解析与纲目翻译专用配置。

- 关闭 AFC，避免仅返回 function_call 而无正文。
- 纲目翻译不下发 thinking_config（不同 google-genai / 服务端对 ThinkingConfig 字段校验不一致，易触发 extra_forbidden）。
- 从响应中提取可翻译正文（与 SDK 的 response.text 一致，并补充诊断日志）。
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# 纲目翻译单次输出 token 上限（避免模型默认过低导致长纲目译文被截断为空）
_TRANSLATION_MAX_OUT_MIN = 1024
_TRANSLATION_MAX_OUT_CAP = 65536


def translation_max_output_tokens() -> int:
    """环境变量 GEMINI_TRANSLATION_MAX_OUTPUT_TOKENS，默认 32768，夹在 [_TRANSLATION_MAX_OUT_MIN, _TRANSLATION_MAX_OUT_CAP]。"""
    raw = os.getenv("GEMINI_TRANSLATION_MAX_OUTPUT_TOKENS", "32768")
    try:
        v = int(raw)
    except ValueError:
        v = 32768
    return max(_TRANSLATION_MAX_OUT_MIN, min(v, _TRANSLATION_MAX_OUT_CAP))

try:
    from google.genai import types as genai_types
except ImportError:
    genai_types = None


def gemini_translation_generate_config(system_instruction: Any) -> Any:
    """
    纲目翻译专用 GenerateContentConfig：关闭 AFC、显式 max_output_tokens（见 translation_max_output_tokens）。
    不设置 thinking_config（避免各版本 SDK/服务端对 ThinkingConfig 校验不一致导致请求失败）。
    """
    if genai_types is None:
        raise RuntimeError("google.genai 未安装")

    max_out = translation_max_output_tokens()
    return genai_types.GenerateContentConfig(
        system_instruction=system_instruction,
        automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
        max_output_tokens=max_out,
    )


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
