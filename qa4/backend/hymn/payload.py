# -*- coding: utf-8 -*-
"""诗歌 hymn_data SSE 载荷（供前端 HymnMessage）。"""

from __future__ import annotations

from typing import Any, Optional

from hymn.parse import SERIES_LABEL


def _series_zh(series: str) -> str:
    s = (series or "").strip()
    if s in SERIES_LABEL:
        return SERIES_LABEL[s]
    if "补充" in s:
        return "补充本"
    if "附" in s:
        return "诗歌附"
    if s in {"诗歌", "大本"}:
        return "大本"
    return s or "大本"


def build_hymn_data(
    targeted: Optional[dict[str, Any]],
    *,
    plan: Any = None,
) -> Optional[dict[str, Any]]:
    """从定向诗歌结果构造 {hymns, notes}；无块则 None（留给 not_found 文案）。"""
    t = targeted or {}
    blocks = list(t.get("blocks") or [])
    meta = dict(t.get("meta") or {})
    notes = [str(x) for x in (meta.get("notes") or []) if x]
    hymns: list[dict[str, Any]] = []

    # 优先：每个成功块一首
    for b in blocks:
        if not isinstance(b, dict):
            continue
        text = str(b.get("text") or "").strip()
        if not text:
            continue
        series = str(b.get("series") or "")
        number = b.get("hymn_number")
        if number is None and plan and getattr(plan, "locator", None):
            number = plan.locator.hymn_number
            series = series or (plan.locator.hymn_series or "big")
        # ES 中文系列名 → 展示名
        series_zh = _series_zh(series)
        hymns.append(
            {
                "series": series,
                "series_zh": series_zh,
                "hymn_number": int(number) if number is not None else None,
                "name": b.get("name") or b.get("book_title") or "",
                "title": b.get("title") or b.get("message_title") or "",
                "text": text,
            }
        )

    # 无正文时不发 hymn_data（留给 not_found / 文案）
    if not hymns:
        return None
    return {"hymns": hymns, "notes": notes}
