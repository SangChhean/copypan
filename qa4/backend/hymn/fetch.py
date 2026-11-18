# -*- coding: utf-8 -*-
"""按识别结果取诗歌整首（调用 targeted.hymn）。"""

from __future__ import annotations

from typing import Any

from hymn.catalog import SERIES_TO_ES
from hymn.parse import SERIES_LABEL, HymnRef, HymnRefList, parse_hymn_refs


async def fetch_hymns(
    text: str,
    targeted: Any,
    *,
    catalog: Any = None,
) -> dict[str, Any]:
    """识别并取首数。不存在/儿童不调 ES。"""
    refs = parse_hymn_refs(text, catalog=catalog)
    return await fetch_hymn_ref_list(refs, targeted)


async def fetch_hymn_ref_list(refs: HymnRefList, targeted: Any) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for r in refs:
        items.append(await _fetch_one(r, targeted))
    return {
        "refs": [
            {
                "series": r.series,
                "number": r.number,
                "explicit_series": r.explicit_series,
                "fallback": r.fallback,
                "exists": r.exists,
            }
            for r in refs
        ],
        "truncated": bool(getattr(refs, "truncated", False)),
        "items": items,
    }


async def _fetch_one(r: HymnRef, targeted: Any) -> dict[str, Any]:
    base = {
        "series": r.series,
        "number": r.number,
        "label": f"{SERIES_LABEL.get(r.series, r.series)} {r.number}",
        "fallback": r.fallback,
        "exists": r.exists,
        "explicit_series": r.explicit_series,
    }
    if r.series == "child":
        return {
            **base,
            "status": "not_indexed",
            "reason": "儿童诗歌未收录",
            "result": None,
        }
    if not r.exists:
        return {
            **base,
            "status": "not_found",
            "reason": f"无此首 {SERIES_LABEL.get(r.series, r.series)} {r.number}",
            "result": None,
        }
    es_series = SERIES_TO_ES.get(r.series)
    if not es_series:
        return {**base, "status": "not_supported", "reason": f"未知系列 {r.series}", "result": None}
    result = await targeted.hymn(int(r.number), es_series)
    return {
        **base,
        "status": getattr(result, "status", None),
        "reason": None,
        "result": result.to_dict() if hasattr(result, "to_dict") else result,
    }
