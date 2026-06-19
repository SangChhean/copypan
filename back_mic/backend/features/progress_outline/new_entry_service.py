# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from typing import Any

from es_config import es as es_client

from features.progress_outline import retrieval
from features.progress_outline.grouping import (
    format_entry_group_response,
    group_records_by_theme,
)
from features.progress_outline.prompts import ENTRY_GROUP_PROMPT
from features.progress_outline.token_utils import estimate_tokens

logger = logging.getLogger(__name__)

STAGE_CONFIG: dict[int, dict[str, Any]] = {
    1: {"index": "kg-rag_cwwn", "year_range": None},
    2: {"index": "kg-rag_cwwl", "year_range": (1932, 1973)},
    3: {"index": "kg-rag_cwwl", "year_range": (1974, 1984)},
    4: {"index": "kg-rag_cwwl", "year_range": (1985, 1990)},
    5: {"index": "kg-rag_cwwl", "year_range": (1991, 1997)},
}

SOURCE_GROUP_LABELS = {
    1: "倪柝声弟兄职事",
    2: "李常受弟兄职事第一阶段（1932-1973）",
    3: "李常受弟兄职事第三阶段（1974-1984）",
    4: "李常受弟兄职事第四阶段（1985-1990）",
    5: "李常受弟兄职事高峰阶段（1991-1997）",
}


def _entry_record_line(it: dict[str, Any]) -> str:
    rid = it.get("chunk_id") or ""
    header = it.get("source_zh") or it.get("book_title") or rid
    return f"{rid} | {header}"


async def group_entries_by_theme(items: list[dict[str, Any]]) -> dict[str, Any]:
    record_list = "\n".join(_entry_record_line(it) for it in items)
    grouped = await group_records_by_theme(
        items,
        id_key="chunk_id",
        record_list=record_list,
        prompt_template=ENTRY_GROUP_PROMPT,
        to_plain_text=entries_to_plain_text,
        fallback_title="全部段落",
    )
    return {
        "groups": format_entry_group_response(grouped),
        "n_groups": grouped.get("n_groups", 0),
        "grouping_usage": grouped.get("usage"),
    }


async def search_entries(term: str, source_group_no: int, top_k: int = 80) -> dict[str, Any]:
    cfg = STAGE_CONFIG.get(source_group_no)
    if not cfg:
        raise ValueError(f"无效阶段: {source_group_no}")
    query = (term or "").strip()
    if not query:
        raise ValueError("词条名称不能为空")

    results = await retrieval.hybrid_search(
        es_client,
        query,
        cfg["index"],
        top_k=top_k,
        year_range=cfg["year_range"],
    )
    items = []
    for r in results:
        items.append(
            {
                "chunk_id": r.get("chunk_id") or "",
                "source_zh": r.get("source_zh") or r.get("book_title") or "",
                "text": r.get("text") or "",
                "book_title": r.get("book_title") or "",
                "author": r.get("author") or "",
                "year": r.get("year"),
                "message_title": r.get("message_title") or "",
                "section_title": r.get("section_title") or "",
            }
        )
    plain = entries_to_plain_text(items)
    tokens = estimate_tokens(plain)
    grouped = await group_entries_by_theme(items)
    return {
        "items": items,
        "groups": grouped["groups"],
        "n_groups": grouped["n_groups"],
        "grouping_usage": grouped.get("grouping_usage"),
        "count": len(items),
        "estimated_tokens": tokens,
        "plain_text": plain,
        "source_group_label": SOURCE_GROUP_LABELS.get(source_group_no, ""),
        "index": cfg["index"],
    }


def entries_to_plain_text(items: list[dict]) -> str:
    parts: list[str] = []
    for it in items:
        header = it.get("source_zh") or it.get("book_title") or it.get("chunk_id") or ""
        if header:
            parts.append(header)
        text = it.get("text") or ""
        if text:
            parts.append(text)
        parts.append("")
    return "\n".join(parts).strip()
