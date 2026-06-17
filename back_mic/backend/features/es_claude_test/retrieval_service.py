# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import re
from typing import Any

from es_config import es
from kg_rag.retrieval import bm25_search, dense_search, rerank, rrf_merge

INDICES = "kg-rag_life,kg-rag_cwwl,kg-rag_cwwn,kg-rag_others"

STAGES = [
    {"key": "nee", "label": "倪柝声弟兄职事（1920–1952）", "year_min": 1920, "year_max": 1952},
    {"key": "lee_1", "label": "李常受弟兄职事第一阶段（1932–1960）", "year_min": 1932, "year_max": 1960},
    {"key": "lee_2", "label": "李常受弟兄职事第二阶段（1961–1973）", "year_min": 1961, "year_max": 1973},
    {"key": "lee_3", "label": "李常受弟兄职事第三阶段（1974–1984）", "year_min": 1974, "year_max": 1984},
    {"key": "lee_4", "label": "李常受弟兄职事第四阶段（1984–1990）", "year_min": 1985, "year_max": 1990},
    {"key": "lee_peak", "label": "李常受弟兄职事高峰阶段（1990–1997）", "year_min": 1990, "year_max": 1997},
]

_YEAR_RE = re.compile(r"(19\d{2}|20\d{2})")

_KEEP_FIELDS = (
    "chunk_id",
    "text",
    "source_zh",
    "book_title",
    "author",
    "message_title",
    "section_title",
    "year",
    "_index",
)


def _extract_year(doc: dict) -> int | None:
    raw_year = doc.get("year")
    if raw_year is not None:
        try:
            return int(raw_year)
        except (TypeError, ValueError):
            pass
    chunk_id = str(doc.get("chunk_id") or "")
    if chunk_id.startswith("cwwl_"):
        try:
            return int(chunk_id.split("_")[1].split("-")[0])
        except (IndexError, ValueError):
            pass
    m = _YEAR_RE.search(chunk_id)
    if m:
        try:
            return int(m.group(1))
        except ValueError:
            pass
    return None


def _assign_stage(doc: dict) -> str:
    chunk_id = str(doc.get("chunk_id") or "")
    index_name = str(doc.get("_index") or "")
    if "cwwn_" in chunk_id or "cwwn" in index_name:
        return "nee"
    if "others" in index_name:
        return "lee_peak"
    year = _extract_year(doc)
    if year is not None:
        for stage in reversed(STAGES):
            if stage["year_min"] <= year <= stage["year_max"]:
                return stage["key"]
    return "lee_peak"


def _deduplicate(docs: list[dict]) -> list[dict]:
    seen_ids: set[str] = set()
    seen_texts: set[str] = set()
    out: list[dict] = []
    for doc in docs:
        cid = str(doc.get("chunk_id") or "")
        if cid and cid in seen_ids:
            continue
        prefix = str(doc.get("text") or "")[:50]
        if prefix and prefix in seen_texts:
            continue
        if cid:
            seen_ids.add(cid)
        if prefix:
            seen_texts.add(prefix)
        out.append(doc)
    return out


def _slim_doc(doc: dict) -> dict[str, Any]:
    year = doc.get("year")
    if year is None:
        year = _extract_year(doc)
    slim: dict[str, Any] = {}
    for key in _KEEP_FIELDS:
        if key == "year":
            slim[key] = year
        else:
            slim[key] = doc.get(key)
    return slim


async def search_and_stage(keyword: str, keywords: list[str]) -> dict:
    query = " ".join(keywords)

    bm25_results = await bm25_search(es, query, INDICES, top_k=150)

    dense_tasks = [
        dense_search(es, kw, INDICES, top_k=30, num_candidates=150) for kw in keywords
    ]
    all_dense = await asyncio.gather(*dense_tasks)
    dense_results: list[dict] = []
    for hits in all_dense:
        dense_results.extend(hits)

    merged = await rrf_merge(
        bm25_results,
        dense_results,
        k=60,
        bm25_weight=1.5,
        dense_weight=1.0,
    )
    total_retrieved = len(bm25_results) + len(dense_results)

    deduped = _deduplicate(merged)
    total_deduped = len(deduped)

    final = await rerank(deduped, keyword, top_n=80)
    total_reranked = len(final)

    stage_map = {
        stage["key"]: {"label": stage["label"], "count": 0, "docs": []}
        for stage in STAGES
    }
    for doc in final:
        key = _assign_stage(doc)
        slim = _slim_doc(doc)
        stage_map[key]["docs"].append(slim)
        stage_map[key]["count"] += 1

    return {
        "total_retrieved": total_retrieved,
        "total_deduped": total_deduped,
        "total_reranked": total_reranked,
        "stages": stage_map,
    }
