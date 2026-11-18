# -*- coding: utf-8 -*-
"""检索范围决策：题型→范围、软优先、作者/年代硬过滤、冲突标志。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from retrieval.config import filter_field, retrieval_cfg

NONE_FLAG = "职事信息里没有"


@dataclass
class ScopeDecision:
    indices: list[str] = field(default_factory=list)
    priority: list[str] = field(default_factory=list)  # 软优先，先取
    priority_terms: dict[str, list[str]] = field(default_factory=dict)  # 软优先内的书名限定（团体实行年标记）
    hard_terms: dict[str, dict[str, list[str]]] = field(default_factory=dict)  # 索引 → {字段: 值}
    none_flag: Optional[str] = None
    year_range_covered: Optional[tuple[int, int]] = None
    reverse: bool = False


def _default_scope(cfg: dict[str, Any]) -> list[str]:
    return [i for i in cfg.get("default_scope") or [] if (cfg["indices"].get(i) or {}).get("searchable", True)]


def decide_scope(
    spec: Any,
    *,
    year_table: Any = None,
    cfg: Optional[dict[str, Any]] = None,
) -> ScopeDecision:
    cfg = cfg or retrieval_cfg()
    from pipeline.schemas import behavior_alias

    qmap = cfg.get("qtype_scope") or {}
    qcfg = (
        qmap.get(spec.qtype)
        or qmap.get(behavior_alias(spec.qtype))
        or qmap.get("默认")
        or {}
    )
    dec = ScopeDecision()
    if qcfg.get("scope") == "reverse":
        dec.reverse = True
        dec.indices = ["bible"]
        return dec

    indices = list(spec.scope_override) if spec.scope_override else _default_scope(cfg)

    # 软优先
    soft = list(qcfg.get("soft_priority") or [])
    soft_years = qcfg.get("soft_priority_year_range")
    if spec.qtype == "召会生活" and spec.angle:
        acfg = (qcfg.get("angles") or {}).get(spec.angle) or {}
        soft = list(acfg.get("soft_priority") or soft)
        soft_years = acfg.get("soft_priority_year_range", soft_years)
    if soft_years and year_table is not None:
        sel = year_table.select(int(soft_years[0]), int(soft_years[1]))
        f = filter_field("text_cwwl", "book_title", cfg)
        if f and sel.book_titles:
            dec.priority_terms["text_cwwl"] = sel.book_titles

    # 作者硬过滤
    author_rules = cfg.get("author_rules") or {}
    if spec.author:
        if spec.year_range and spec.author == "倪柝声":
            dec.none_flag = NONE_FLAG
            return dec
        allowed = list(author_rules.get(spec.author) or [])
        if not allowed:
            dec.none_flag = NONE_FLAG
            return dec
        # 节期 + 作者：节期纲目无作者字段 → 冲突
        if spec.scope_override and set(spec.scope_override) <= {"outline_feasts"}:
            dec.none_flag = NONE_FLAG
            return dec
        indices = [i for i in indices if i in allowed] or allowed
        for i in indices:
            f = filter_field(i, "author", cfg)
            if f:
                dec.hard_terms.setdefault(i, {})[f] = [spec.author]

    # 年代硬过滤（只对 text_cwwl）
    if spec.year_range:
        applies = list((cfg.get("year_rules") or {}).get("applies_to") or ["text_cwwl"])
        indices = [i for i in indices if i in applies]
        if not indices:
            dec.none_flag = NONE_FLAG
            return dec
        if year_table is None:
            dec.none_flag = NONE_FLAG
            return dec
        sel = year_table.select(int(spec.year_range[0]), int(spec.year_range[1]))
        if not sel.book_titles:
            dec.none_flag = NONE_FLAG
            return dec
        dec.year_range_covered = sel.covered_range
        for i in indices:
            f = filter_field(i, "book_title", cfg)
            if f:
                dec.hard_terms.setdefault(i, {})[f] = sel.book_titles

    dec.indices = indices
    if not spec.relaxed:
        dec.priority = [i for i in soft if i in indices]
    else:
        dec.priority_terms = {}
    return dec
