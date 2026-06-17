# -*- coding: utf-8 -*-
"""分组人工校正：重算 plain_text / record_count（与入库 plain 规则一致）。"""
from __future__ import annotations

from typing import Any

from features.progress_outline import new_entry_service, pano_series_service


def recompute_pano_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for g in groups:
        articles = g.get("articles") or []
        if not articles:
            continue
        record_ids = [str(a["id"]) for a in articles if a.get("id")]
        out.append({
            "title": (g.get("title") or "").strip(),
            "burden": (g.get("burden") or "").strip(),
            "record_ids": record_ids,
            "record_count": len(articles),
            "articles": articles,
            "plain_text": pano_series_service.articles_to_plain_text(articles),
        })
    return out


def recompute_entry_groups(groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for g in groups:
        items = g.get("items") or []
        if not items:
            continue
        record_ids = [str(it["chunk_id"]) for it in items if it.get("chunk_id")]
        out.append({
            "title": (g.get("title") or "").strip(),
            "burden": (g.get("burden") or "").strip(),
            "record_ids": record_ids,
            "record_count": len(items),
            "items": items,
            "plain_text": new_entry_service.entries_to_plain_text(items),
        })
    return out
