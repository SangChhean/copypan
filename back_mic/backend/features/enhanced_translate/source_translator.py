# -*- coding: utf-8 -*-
"""reference_source_zh 解析与翻译。"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from es_config import es as es_client
from features.enhanced_translate.pool import zh_eq
from features.enhanced_translate.prompts import REFERENCE_SOURCE_TRANSLATE_PROMPT

logger = logging.getLogger("ai_search.enhanced_translate_source")

_SOURCE_RE = re.compile(
    r'（'
    r'(?:'
    r'[^\s，）]{1,30}生命读经[^）]*'
    r'|倪柝声文集[^）]+'
    r'|李常受文集[^）]+'
    r'|新约总论[^）]*'
    r'|真理课程[^）]+'
    r'|圣经恢复本[^）]+'
    r'|诗歌，第[零一二三四五六七八九十百千\d]+首'
    r'|\d{4}年[^）]+'
    r')'
    r'）'
)

_POOL_INDICES = ",".join([
    "life", "cwwn", "cwwl", "others",
    "bib", "foo", "hymn", "feasts",
])


def parse_source_from_line(line: str) -> tuple[str, str]:
    m = _SOURCE_RE.search(line)
    if not m:
        return line, ""
    full_match = m.group(0)
    stripped_line = (line[: m.start()] + line[m.end() :]).strip()
    return stripped_line, full_match


def _strip_paragraph_suffix(source0: str) -> str:
    return re.sub(r'，第[^，）]+段(?=）)', '', source0)


async def _bm25_source_search(source_zh: str, top_k: int = 5) -> list[dict[str, Any]]:
    query = re.sub(r'[（）]', '', source_zh).strip()
    if not query:
        return []
    body = {
        "query": {"match": {"title": {"query": query, "operator": "and"}}},
        "size": top_k,
        "_source": ["source", "title"],
    }
    try:
        resp = await asyncio.to_thread(
            es_client.search,
            index=_POOL_INDICES,
            body=body,
            request_timeout=8,
        )
    except Exception as e:
        logger.warning("[source_translator] BM25 source 检索失败: %s", e)
        return []
    out = []
    for hit in (resp.get("hits") or {}).get("hits") or []:
        src = hit.get("_source") or {}
        source = src.get("source") or []
        zh_src = source[0] if len(source) > 0 else ""
        en_src = source[1] if len(source) > 1 else ""
        if zh_src:
            out.append({
                "zh_source": zh_src,
                "en_source": en_src,
                "title": src.get("title") or "",
            })
    return out


async def translate_source_zh_batch(
    items: list[tuple[int, str, list[dict[str, Any]]]],
) -> tuple[dict[int, str], dict[str, int | float]]:
    """返回 ({prep_index: source_en}, usage)。"""
    if not items:
        return {}, {"in_tok": 0, "out_tok": 0, "cost_usd": 0.0}

    from features.enhanced_translate.service import _call_gemini_sync

    results: dict[int, str] = {}
    fallback_items: list[tuple[int, str, list]] = []

    for idx, source_zh, line_refs in items:
        hit_en = ""
        for ref in line_refs:
            zh_src = (ref.get("ch_source") or ref.get("source") or "").strip()
            if not zh_src:
                continue
            stripped = _strip_paragraph_suffix(zh_src)
            if zh_eq(stripped, source_zh):
                en_src = (ref.get("en_source") or "").strip()
                if en_src:
                    hit_en = en_src
                    break
        if hit_en:
            results[idx] = hit_en
        else:
            fallback_items.append((idx, source_zh, line_refs))

    cumulative: dict[str, Any] = {"in_tok": 0, "out_tok": 0, "cost_usd": 0.0}
    if not fallback_items:
        return results, cumulative

    blocks: list[str] = []
    for pos, (idx, source_zh, line_refs) in enumerate(fallback_items, 1):
        ref_source_entry = None
        for ref in line_refs:
            zh_src = (ref.get("ch_source") or "").strip()
            en_src = (ref.get("en_source") or "").strip()
            if zh_src and en_src:
                ref_source_entry = {"zh_source": zh_src, "en_source": en_src}
                break
        ref_block = ""
        if ref_source_entry:
            ref_block += (
                f"\nParagraph 1"
                f"\nzh_source: {ref_source_entry['zh_source']}"
                f"\nen_source: {ref_source_entry['en_source']}"
            )
        blocks.append(
            f"Source {pos}: {source_zh}"
            + (f"\n参考语料：{ref_block}" if ref_block else "")
        )

    contents = (
        REFERENCE_SOURCE_TRANSLATE_PROMPT
        + "\n\n"
        + "\n\n".join(blocks)
        + "\n\n请逐条输出英文出处，格式：\n"
        + "\n".join(f"Source {pos}: {{英文出处}}" for pos in range(1, len(fallback_items) + 1))
    )

    try:
        text, cumulative = await asyncio.to_thread(
            _call_gemini_sync, contents, 0, None, cumulative
        )
        if text:
            pattern = re.compile(r"^Source\s+(\d+)\s*:\s*(.+)$", re.MULTILINE)
            for m in pattern.finditer(text):
                pos = int(m.group(1)) - 1
                if 0 <= pos < len(fallback_items):
                    idx = fallback_items[pos][0]
                    results[idx] = m.group(2).strip()
    except Exception as e:
        logger.warning("[source_translator] 路2 Gemini 失败: %s", e)

    for idx, source_zh, _ in fallback_items:
        if idx not in results:
            results[idx] = source_zh

    return results, cumulative
