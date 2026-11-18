# -*- coding: utf-8 -*-
"""提示注入过滤（沿用 3.0 规则）。"""

from __future__ import annotations

import logging

logger = logging.getLogger("qa4.input_guard")

_INJECTION_PATTERNS = [
    "ignore previous instructions",
    "ignore all instructions",
    "disregard your instructions",
    "你现在是",
    "忘记之前的指令",
    "忘记你的指令",
    "忽略之前",
    "忽略上面",
    "不要遵守",
    "system prompt",
    "new instructions:",
    "override instructions",
    "jailbreak",
]


def check_prompt_injection(question: str) -> bool:
    """True=安全；False=疑似注入。"""
    if not question:
        return True
    lower = question.lower()
    for pattern in _INJECTION_PATTERNS:
        if pattern.lower() in lower:
            logger.warning("疑似提示注入已拦截 pattern=%r", pattern)
            return False
    return True
