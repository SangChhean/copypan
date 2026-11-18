# -*- coding: utf-8 -*-
"""流水线数据结构（pydantic 2）。"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


class QType(str, Enum):
    定义 = "定义"
    比较 = "比较"
    个人经历 = "个人经历"
    团体实行 = "团体实行"
    召会生活 = "召会生活"
    汇集 = "汇集"
    核实说法 = "核实说法"  # 旧名；与「话语检索」行为等价
    反找经文 = "反找经文"
    发展 = "发展"
    默认 = "默认"  # 旧名；与「真理」行为等价
    真理 = "真理"
    列举 = "列举"
    话语检索 = "话语检索"
    人物与历史 = "人物与历史"
    预表与象征 = "预表与象征"
    # 取具体对象
    生命读经 = "生命读经"
    节期纲目 = "节期纲目"
    注解 = "注解"
    诗歌 = "诗歌"
    经文 = "经文"


TARGETED_TYPES = {"生命读经", "节期纲目", "注解", "诗歌", "经文"}
GENERAL_TYPES = {t.value for t in QType if t.value not in TARGETED_TYPES}

# 话语检索 ≡ 核实说法（跳过第 5 步、把关规则、不放宽重试）
_VERIFY_LIKE = frozenset({"核实说法", "话语检索"})
# 真理 ≡ 默认；列举/人物与历史/预表与象征本批按默认行为（caps/retrieval），但题型名原样保留
_DEFAULT_BEHAVIOR = frozenset({"默认", "真理", "列举", "人物与历史", "预表与象征"})


def coerce_qtype(v: Any) -> str:
    s = str(v or "").strip()
    return s if s in {t.value for t in QType} else QType.默认.value


def is_verify_like(qtype: str) -> bool:
    """核实说法 / 话语检索：同一条行为路径。"""
    return (qtype or "").strip() in _VERIFY_LIKE


def is_layer1_only_type(qtype: str) -> bool:
    """跳过第 5 步（仅第 1 层）：核实说法/话语检索/反找经文。"""
    s = (qtype or "").strip()
    return is_verify_like(s) or s == "反找经文"


def behavior_alias(qtype: str) -> str:
    """行为别名（caps/retrieval 查表用）。题型名字段本身不要用此函数改写。

    - 话语检索 → 核实说法
    - 真理 / 列举 / 人物与历史 / 预表与象征 → 默认
    - 其余原样
    """
    s = (qtype or "").strip()
    if is_verify_like(s):
        return "核实说法"
    if s in _DEFAULT_BEHAVIOR:
        return "默认"
    return s


class Restriction(BaseModel):
    kind: str  # author | year
    value: Any
    role: str = "限定"  # 限定 | 对象


class Locator(BaseModel):
    book_title: Optional[str] = None
    message_number: Optional[int] = None
    feast_year: Optional[int] = None
    feast_month: Optional[str] = None
    # 诗歌：规则路径存逻辑码 big/sup/fu；模型路径可能仍给 ES 中文名（step6 兼容）
    hymn_series: Optional[str] = None
    hymn_number: Optional[int] = None
    scripture: Optional[str] = None
    note_topic: Optional[str] = None


class SubQuestion(BaseModel):
    text: str
    qtype: str = QType.默认.value
    scope: Optional[list[str]] = None
    angle: Optional[str] = None
    synthesis: bool = False
    depends_on: list[int] = Field(default_factory=list)
    # 比较类：两个对象的词；非比较类为空【暂定】
    compare_objects: list[str] = Field(default_factory=list)

    @field_validator("qtype", mode="before")
    @classmethod
    def _qt(cls, v: Any) -> str:
        return coerce_qtype(v)

    @field_validator("compare_objects", mode="before")
    @classmethod
    def _objs(cls, v: Any) -> list[str]:
        if not v:
            return []
        if isinstance(v, (list, tuple)):
            return [str(x).strip() for x in v if str(x).strip()]
        return [str(v).strip()] if str(v).strip() else []


class Plan(BaseModel):
    main_type: str = QType.默认.value
    restrictions: list[Restriction] = Field(default_factory=list)
    complex: bool = False
    subquestions: list[SubQuestion] = Field(default_factory=list)
    sensitive: bool = False
    understanding: str = ""
    locator: Optional[Locator] = None
    degraded: bool = False
    # model / scripture_rule / hymn_rule / lyrics_rule
    source: str = "model"
    # 多首诗歌：[{series, number, fallback, exists, explicit_series}]
    hymn_refs: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("main_type", mode="before")
    @classmethod
    def _mt(cls, v: Any) -> str:
        return coerce_qtype(v)

    @field_validator("source", mode="before")
    @classmethod
    def _src(cls, v: Any) -> str:
        s = str(v or "model").strip() or "model"
        return s

    @property
    def targeted(self) -> bool:
        return self.main_type in TARGETED_TYPES

    def author(self) -> Optional[str]:
        for r in self.restrictions:
            if r.kind == "author" and r.role == "限定":
                return str(r.value)
        return None

    def year_range(self) -> Optional[tuple[int, int]]:
        for r in self.restrictions:
            if r.kind == "year" and r.role == "限定":
                v = r.value
                if isinstance(v, (list, tuple)) and len(v) == 2:
                    return (int(v[0]), int(v[1]))
                if isinstance(v, int):
                    return (v, v)
        return None


class Layers(BaseModel):
    layer1: list[str] = Field(default_factory=list)
    layer1_is_entry: dict[str, bool] = Field(default_factory=dict)
    revelation: list[str] = Field(default_factory=list)
    intrinsic: list[str] = Field(default_factory=list)
    experience: list[str] = Field(default_factory=list)
    practice: list[str] = Field(default_factory=list)
    # 第 2–5 层词 → 偏向的比较对象（可空）
    object_of: dict[str, str] = Field(default_factory=dict)

    def recommended(self) -> list[str]:
        return list(self.revelation) + list(self.intrinsic) + list(self.experience) + list(self.practice)

    def total_2_5(self) -> int:
        return len(self.recommended())

    def all_words(self) -> list[str]:
        return list(self.layer1) + self.recommended()


class Passage(BaseModel):
    number: int = 0
    id: str
    index: str
    book_title: str = ""
    message_title: str = ""
    location: dict[str, Any] = Field(default_factory=dict)
    text: str = ""
    route: str = "main"
    meta: dict[str, Any] = Field(default_factory=dict)
    subq: int = 0


class Verdict(BaseModel):
    subq: int
    keep: dict[int, bool] = Field(default_factory=dict)
    overall: str = "够"  # 够 | 部分够 | 不够
    retried: bool = False
    note: str = ""
    defaulted: bool = False


class Citation(BaseModel):
    n: int
    book_title: str = ""
    message_title: str = ""
    location: dict[str, Any] = Field(default_factory=dict)
    index: str = ""
    years: Optional[list[int]] = None
    out_of_range: bool = False


class QuoteCheck(BaseModel):
    quote: str
    ok: bool
    passage_n: Optional[int] = None
    parts: int = 1


class Answer(BaseModel):
    text: str = ""
    citations: list[Citation] = Field(default_factory=list)
    quote_checks: list[QuoteCheck] = Field(default_factory=list)
    premise_note: str = ""
    degraded: bool = False
    not_found: bool = False
    invalid_refs: list[int] = Field(default_factory=list)
    awaiting_choice: bool = False
    lyrics_status: Optional[str] = None
    # 候选摘要（不含歌词原文长文；可含短 snippet 供前端）
    choose_candidates: list[dict[str, Any]] = Field(default_factory=list)


class TraceRecord(BaseModel):
    request_id: str
    question_hash: str
    question_len: int
    question_text: Optional[str] = None
    history_json: Optional[list[dict[str, Any]]] = None
    rewritten_question: str = ""
    steps: dict[str, Any] = Field(default_factory=dict)
    models: dict[str, Any] = Field(default_factory=dict)
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    timings_ms: dict[str, int] = Field(default_factory=dict)
    tokens: dict[str, Any] = Field(default_factory=dict)
    retrieval: dict[str, Any] = Field(default_factory=dict)
    verdicts: list[dict[str, Any]] = Field(default_factory=list)
    retried: bool = False
    quote_checks: list[dict[str, Any]] = Field(default_factory=list)
    cache_hit: bool = False
    degraded: bool = False
    degraded_reasons: list[str] = Field(default_factory=list)
    not_found: bool = False
    main_type: str = ""
    elapsed_ms: int = 0
    warnings: list[str] = Field(default_factory=list)
