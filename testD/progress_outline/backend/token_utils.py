# -*- coding: utf-8 -*-
from __future__ import annotations

import re


def estimate_tokens(text: str) -> int:
    """中文字符÷1.5 + 其他字符÷4"""
    if not text:
        return 0
    chinese = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    other = len(text) - chinese
    return int(chinese / 1.5 + other / 4)


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
