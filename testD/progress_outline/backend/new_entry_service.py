# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from typing import Any

import retrieval
from es_client import es
from token_utils import default_output_length, estimate_tokens

logger = logging.getLogger(__name__)

STAGE_CONFIG: dict[int, dict[str, Any]] = {
    1: {"index": "kg-rag_cwwn", "year_range": None},
    2: {"index": "kg-rag_cwwl", "year_range": (1932, 1960)},
    3: {"index": "kg-rag_cwwl", "year_range": (1961, 1973)},
    4: {"index": "kg-rag_cwwl", "year_range": (1974, 1984)},
    5: {"index": "kg-rag_cwwl", "year_range": (1984, 1990)},
    6: {"index": "kg-rag_cwwl", "year_range": (1990, 1997)},
}

SOURCE_GROUP_LABELS = {
    1: "倪柝声弟兄职事",
    2: "李常受弟兄职事第一阶段（1932-1960）",
    3: "李常受弟兄职事第二阶段（1961-1973）",
    4: "李常受弟兄职事第三阶段（1974-1984）",
    5: "李常受弟兄职事第四阶段（1984-1990）",
    6: "李常受弟兄职事高峰阶段（1990-1997）",
}


async def search_entries(term: str, source_group_no: int, top_k: int = 80) -> dict[str, Any]:
    cfg = STAGE_CONFIG.get(source_group_no)
    if not cfg:
        raise ValueError(f"无效阶段: {source_group_no}")
    query = (term or "").strip()
    if not query:
        raise ValueError("词条名称不能为空")

    results = await retrieval.hybrid_search(
        es,
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
    return {
        "items": items,
        "count": len(items),
        "estimated_tokens": tokens,
        "default_output_length": default_output_length(tokens),
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
