# -*- coding: utf-8 -*-
"""检索层数据结构。"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class SubQuestionSpec:
    query: str
    qtype: str = "默认"
    angle: Optional[str] = None
    words: list[str] = field(default_factory=list)  # 推荐词（第 2–5 层），每个各开一路
    layer1_words: list[str] = field(default_factory=list)  # 第 1 层：精确短语加权
    author: Optional[str] = None
    year_range: Optional[tuple[int, int]] = None
    original_question: str = ""
    synthesis: bool = False
    relaxed: bool = False
    cap: Optional[int] = None
    scope_override: Optional[list[str]] = None


@dataclass
class Passage:
    id: str
    index: str  # 逻辑索引名
    book_title: str = ""
    message_title: str = ""
    location: dict[str, Any] = field(default_factory=dict)
    text: str = ""
    route: str = "main"
    meta: dict[str, Any] = field(default_factory=dict)
    score: float = 0.0
    number: int = 0  # 第 6 步由程序编号

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RetrievalResult:
    passages: list[Passage] = field(default_factory=list)
    coverage: dict[str, Any] = field(default_factory=dict)
    synthesis: bool = False
    none_flag: Optional[str] = None  # 如「职事信息里没有」
    degraded: bool = False
    degraded_reasons: list[str] = field(default_factory=list)
    year_range_covered: Optional[tuple[int, int]] = None
    scope: list[str] = field(default_factory=list)


def stable_id(index: str, raw_id: str, text: str = "") -> str:
    if raw_id:
        return f"{index}:{raw_id}"
    return f"{index}:h{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}"
