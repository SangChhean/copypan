# -*- coding: utf-8 -*-
"""单次请求的上下文与步骤事件/记录辅助。"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Optional, TypeVar

from pipeline.schemas import Answer, Layers, Passage, Plan, Verdict
from pipeline.textutil import qhash, qmeta

logger = logging.getLogger("qa4.pipeline")

T = TypeVar("T")

STEP_NAMES = {
    1: "入口",
    2: "追问改写",
    3: "理解与计划",
    4: "第1层取词",
    5: "第2-5层取词",
    6: "检索",
    7: "材料把关",
    8: "生成回答",
    9: "记录",
}


@dataclass
class RequestContext:
    request_id: str
    question_orig: str
    history: list[dict[str, Any]] = field(default_factory=list)
    question: str = ""
    plan: Optional[Plan] = None
    layers: list[Layers] = field(default_factory=list)
    definitions: dict[str, str] = field(default_factory=dict)
    devine: list[dict[str, Any]] = field(default_factory=list)
    passages: list[Passage] = field(default_factory=list)
    passages_by_subq: dict[int, list[Passage]] = field(default_factory=dict)
    targeted: Optional[dict[str, Any]] = None
    verdicts: list[Verdict] = field(default_factory=list)
    answer: Answer = field(default_factory=Answer)
    cache_hit: bool = False
    not_found: bool = False
    retried: bool = False
    degraded_reasons: list[str] = field(default_factory=list)
    # 规则前置
    rule_hits: list[dict[str, Any]] = field(default_factory=list)
    lyrics_status: Optional[str] = None
    awaiting_choice: bool = False
    rule_early_done: bool = False  # too_*/choose 等：step3 后直接收尾
    steps: dict[str, Any] = field(default_factory=dict)
    timings_ms: dict[str, int] = field(default_factory=dict)
    tokens: dict[str, Any] = field(default_factory=dict)
    models: dict[str, Any] = field(default_factory=dict)
    retrieval_cov: dict[str, Any] = field(default_factory=dict)
    history_for_rewrite: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    t0: float = field(default_factory=time.perf_counter)

    def __post_init__(self) -> None:
        if not self.question:
            self.question = self.question_orig

    def warn(self, code: str) -> None:
        if code not in self.warnings:
            self.warnings.append(code)
        logger.warning("warning request=%s code=%s", self.request_id[:8], code)

    @property
    def degraded(self) -> bool:
        return bool(self.degraded_reasons)

    def degrade(self, reason: str) -> None:
        if reason not in self.degraded_reasons:
            self.degraded_reasons.append(reason)
        logger.warning("degraded request=%s reason=%s", self.request_id[:8], reason)

    def record(self, step: int, **summary: Any) -> None:
        self.steps.setdefault(f"step{step}", {}).update(summary)

    def note_llm(self, step: str, res: Any) -> None:
        if res is None:
            return
        self.models[step] = {"request_model": getattr(res, "request_model", None), "response_model": getattr(res, "response_model", None)}
        self.tokens[step] = dict(getattr(res, "usage", {}) or {})

    def elapsed_ms(self) -> int:
        return int((time.perf_counter() - self.t0) * 1000)

    def qmeta(self) -> dict[str, Any]:
        return qmeta(self.question_orig)


def step_event(step: int, status: str, **extra: Any) -> dict[str, Any]:
    ev = {"event": "step", "step": step, "name": STEP_NAMES.get(step, ""), "status": status}
    ev.update(extra)
    return ev


async def timed(ctx: RequestContext, step: int, coro: Awaitable[T], timeout_s: float) -> T:
    t = time.perf_counter()
    try:
        return await asyncio.wait_for(coro, timeout=timeout_s)
    finally:
        ctx.timings_ms[f"step{step}"] = ctx.timings_ms.get(f"step{step}", 0) + int((time.perf_counter() - t) * 1000)


def question_hash(q: str) -> str:
    return qhash(q)
