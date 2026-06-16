# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

CLAUDE_MODEL = "claude-sonnet-4-6"


def _cjk_char_count(text: str) -> int:
    return sum(1 for c in text if "\u4e00" <= c <= "\u9fff")


def estimate_tokens_heuristic(text: str) -> int:
    """
    Claude Sonnet 中文职事文本的经验校准（无 API 时回退）：
    - CJK 统一汉字约 1.23 token/字
    - 其余字符（标点、数字、拉丁、空白等）约 4 字符/token
    """
    if not text:
        return 0
    cjk = _cjk_char_count(text)
    other = len(text) - cjk
    return max(1, round(cjk * 1.23 + other / 4))


def estimate_tokens_claude(text: str) -> int | None:
    """调用 Anthropic count_tokens 精确计数；失败或未配置密钥时返回 None。"""
    if not text or not text.strip():
        return 0
    api_key = os.getenv("CLAUDE_API_KEY") or os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return None
    try:
        from anthropic import Anthropic

        client = Anthropic(api_key=api_key)
        result = client.messages.count_tokens(
            model=CLAUDE_MODEL,
            messages=[{"role": "user", "content": text}],
        )
        return int(result.input_tokens)
    except Exception as e:
        logger.warning("Anthropic count_tokens 失败，回退启发式: %s", e)
        return None


def estimate_tokens(text: str) -> int:
    """优先 Claude 官方计数，否则使用校准后的启发式。"""
    counted = estimate_tokens_claude(text)
    if counted is not None:
        return counted
    return estimate_tokens_heuristic(text)


def default_output_length(input_tokens: int) -> int:
    return max(1500, min(12000, round(input_tokens / 100000 * 2000)))


def outline_indent(level: str) -> str:
    mapping = {
        "bible_reading": 0,
        "ot1": 0,
        "ot2": 1,
        "ot3": 2,
        "ot4": 3,
        "ot5": 4,
        "ot6": 4,
        "ot7": 4,
    }
    return "\t" * mapping.get(level, 1)
