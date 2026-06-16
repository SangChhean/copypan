# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from typing import Any

from es_client import PANO_INDEX, es
from token_utils import default_output_length, estimate_tokens, outline_indent

logger = logging.getLogger(__name__)

SOURCE_GROUP_LABELS = {
    1: "倪柝声弟兄职事",
    2: "李常受弟兄职事第一阶段（1932-1960）",
    3: "李常受弟兄职事第二阶段（1961-1973）",
    4: "李常受弟兄职事第三阶段（1974-1984）",
    5: "李常受弟兄职事第四阶段（1984-1990）",
    6: "李常受弟兄职事高峰阶段（1990-1997）",
}


def list_series() -> list[dict[str, Any]]:
    body = {
        "size": 0,
        "aggs": {
            "series": {
                "terms": {"field": "series_no", "size": 500, "order": {"_key": "asc"}},
                "aggs": {"title": {"top_hits": {"size": 1, "_source": ["series_title"]}}},
            }
        },
    }
    resp = es.search(index=PANO_INDEX, body=body)
    buckets = (resp.get("aggregations") or {}).get("series", {}).get("buckets") or []
    out = []
    for b in buckets:
        series_no = int(b["key"])
        hits = (b.get("title") or {}).get("hits", {}).get("hits") or []
        series_title = ""
        if hits:
            series_title = (hits[0].get("_source") or {}).get("series_title") or ""
        out.append({"series_no": series_no, "series_title": series_title})
    return out


def search_articles(series_no: int, source_group_no: int) -> dict[str, Any]:
    body = {
        "query": {
            "bool": {
                "must": [
                    {"term": {"series_no": series_no}},
                    {"term": {"source_group_no": source_group_no}},
                ]
            }
        },
        "size": 5000,
        "sort": [{"article_no": "asc"}],
    }
    resp = es.search(index=PANO_INDEX, body=body)
    hits = (resp.get("hits") or {}).get("hits") or []
    articles = []
    for h in hits:
        src = h.get("_source") or {}
        articles.append(
            {
                "id": h.get("_id"),
                "article_no": src.get("article_no"),
                "title": src.get("title") or "",
                "outline": src.get("outline") or [],
                "ministry_excerpt": src.get("ministry_excerpt") or [],
                "series_no": src.get("series_no"),
                "series_title": src.get("series_title") or "",
                "source_group_no": src.get("source_group_no"),
                "source_group_label": src.get("source_group_label") or SOURCE_GROUP_LABELS.get(source_group_no, ""),
            }
        )
    plain = articles_to_plain_text(articles)
    tokens = estimate_tokens(plain)
    return {
        "articles": articles,
        "count": len(articles),
        "estimated_tokens": tokens,
        "default_output_length": default_output_length(tokens),
        "plain_text": plain,
        "source_group_label": SOURCE_GROUP_LABELS.get(source_group_no, ""),
    }


def articles_to_plain_text(articles: list[dict]) -> str:
    parts: list[str] = []
    for art in articles:
        parts.append(art.get("title") or "")
        for item in art.get("outline") or []:
            level = item.get("type") or "ot2"
            text = item.get("text") or ""
            parts.append(f"{outline_indent(level)}{text}")
        for item in art.get("ministry_excerpt") or []:
            if isinstance(item, dict):
                text = item.get("text") or ""
            elif isinstance(item, str):
                text = item
            else:
                text = ""
            if text.strip():
                parts.append(text.strip())
        parts.append("")
    return "\n".join(parts).strip()
