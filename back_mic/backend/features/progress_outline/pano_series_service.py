# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from typing import Any

from elastic_transport import ConnectionError as ESConnectionError, TransportError
from elasticsearch import ApiError as ESApiError
from es_config import es as es_client

from features.progress_outline.grouping import (
    format_pano_group_response,
    group_records_by_theme,
)
from features.progress_outline.prompts import PANO_GROUP_PROMPT
from features.progress_outline.token_utils import (
    estimate_tokens,
    outline_indent,
)

logger = logging.getLogger(__name__)

PANO_INDEX = "progress_pano"

SOURCE_GROUP_LABELS = {
    1: "倪柝声弟兄职事",
    2: "李常受弟兄职事第一阶段（1932-1973）",
    3: "李常受弟兄职事第三阶段（1974-1984）",
    4: "李常受弟兄职事第四阶段（1985-1990）",
    5: "李常受弟兄职事高峰阶段（1991-1997）",
}


def _empty_search_result(source_group_no: int) -> dict[str, Any]:
    return {
        "articles": [],
        "count": 0,
        "estimated_tokens": 0,
        "plain_text": "",
        "source_group_label": SOURCE_GROUP_LABELS.get(source_group_no, ""),
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
    try:
        resp = es_client.search(index=PANO_INDEX, body=body)
    except (ESConnectionError, TransportError, ESApiError) as e:
        logger.warning("[progress_outline] 系列列表检索失败: %s", e)
        return []
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
    try:
        resp = es_client.search(index=PANO_INDEX, body=body)
    except (ESConnectionError, TransportError, ESApiError) as e:
        logger.warning("[progress_outline] 进展文章检索失败: %s", e)
        return _empty_search_result(source_group_no)
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
                "source_group_label": src.get("source_group_label")
                or SOURCE_GROUP_LABELS.get(source_group_no, ""),
            }
        )
    plain = articles_to_plain_text(articles)
    tokens = estimate_tokens(plain)
    return {
        "articles": articles,
        "count": len(articles),
        "estimated_tokens": tokens,
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


def _pano_record_line(art: dict[str, Any]) -> str:
    rid = art.get("id") or ""
    title = art.get("title") or f"第{art.get('article_no')}篇"
    return f"{rid} | {title}"


async def group_articles_by_theme(articles: list[dict[str, Any]]) -> dict[str, Any]:
    record_list = "\n".join(_pano_record_line(a) for a in articles)
    grouped = await group_records_by_theme(
        articles,
        id_key="id",
        record_list=record_list,
        prompt_template=PANO_GROUP_PROMPT,
        to_plain_text=articles_to_plain_text,
        fallback_title="全部篇目",
    )
    return {
        "groups": format_pano_group_response(grouped),
        "n_groups": grouped.get("n_groups", 0),
        "grouping_usage": grouped.get("usage"),
    }
