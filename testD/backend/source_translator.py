# -*- coding: utf-8 -*-
"""
reference_source_zh 解析与翻译。
从纲目行剥离出处标注，翻译为英文后拼接回去。
"""
from __future__ import annotations

import re
import asyncio
import logging
from typing import Any

from testD.backend._bootstrap import ensure_main_backend_path
ensure_main_backend_path()

from es_config import es as es_client
from testD.backend.additional_pool import normalize_zh, zh_eq
from testD.backend.enhanced_translate_prompts import REFERENCE_SOURCE_TRANSLATE_PROMPT

logger = logging.getLogger("testD.source_translator")


# ── 1. 解析剥离 ──────────────────────────────────────────────
# 纲目行出处格式：（***）没有「，第***段」

_SOURCE_RE = re.compile(
    r'（'
    r'(?:'
    r'[^\s，）]{1,30}生命读经[^）]*'       # 腓利比书生命读经，第四十三篇
    r'|倪柝声文集[^）]+'                    # 倪柝声文集第二辑...
    r'|李常受文集[^）]+'                    # 李常受文集一九九一...
    r'|新约总论[^）]*'                      # 新约总论，第***篇
    r'|真理课程[^）]+'                      # 真理课程，第***课
    r'|圣经恢复本[^）]+'                    # 圣经恢复本，***（含注解）
    r'|诗歌，第[零一二三四五六七八九十百千\d]+首'  # 诗歌，第***首
    r'|\d{4}年[^）]+'                       # 2004年安那翰...
    r')'
    r'）'
)


def parse_source_from_line(line: str) -> tuple[str, str]:
    """
    从纲目行中解析并剥离出处标注。
    返回：(剥离后的行内容, reference_source_zh)
    纲目行出处本身没有「，第***段」，直接原样返回。
    """
    m = _SOURCE_RE.search(line)
    if not m:
        return line, ""
    full_match = m.group(0)
    stripped_line = (line[:m.start()] + line[m.end():]).strip()
    return stripped_line, full_match


# ── 2. normalize_zh 验证 ──────────────────────────────────────

def _strip_paragraph_suffix(source0: str) -> str:
    """
    去掉 ES source[0] 里末尾的「，第***段」。
    只去最末尾一个，不影响中间的篇/章/课编号。
    例：（腓利比书生命读经，第四十三篇，第二十八段）
      → （腓利比书生命读经，第四十三篇）
    """
    return re.sub(r'，第[^，）]+段(?=）)', '', source0)


# ── 3. ES BM25 检索 title 字段 ────────────────────────────────

_POOL_INDICES = ",".join([
    "life", "cwwn", "cwwl", "others",
    "bib", "foo", "hymn", "feasts",
])


async def _bm25_source_search(source_zh: str, top_k: int = 5) -> list[dict[str, Any]]:
    """
    用 reference_source_zh（去掉括号）检索 title 字段，
    返回 top_k 条含 zh_source + en_source 的结果。
    """
    query = re.sub(r'[（）]', '', source_zh).strip()
    if not query:
        return []
    body = {
        "query": {
            "match": {
                "title": {"query": query, "operator": "and"}
            }
        },
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


# ── 4. 翻译出处 ───────────────────────────────────────────────

async def translate_source_zh(
    source_zh: str,
    line_refs: list[dict[str, Any]],
) -> str:
    """
    翻译 reference_source_zh → reference_source_en。

    路1：normalize_zh 验证
      - 将 line_refs 里每条的 ch_source/source 去掉「，第***段」后
        与 source_zh 做 normalize_zh 比对
      - 匹配 → 直接取 en_source

    路2：fallback
      - BM25 检索 title 字段，top5
      - 加上主参考语料的 zh_source + en_source（共最多6条）
      - 送 Gemini + REFERENCE_SOURCE_TRANSLATE_PROMPT
    """
    if not source_zh:
        return ""

    # 路1：从 line_refs 验证
    for ref in line_refs:
        zh_src = (ref.get("ch_source") or ref.get("source") or "").strip()
        if not zh_src:
            continue
        stripped = _strip_paragraph_suffix(zh_src)
        if zh_eq(stripped, source_zh):
            en_src = (ref.get("en_source") or "").strip()
            if en_src:
                logger.info("[source_translator] 路1命中: %s → %s", source_zh, en_src)
                return en_src

    # 路2：fallback
    logger.info("[source_translator] 路1未命中，走路2: %s", source_zh)

    bm25_results = await _bm25_source_search(source_zh, top_k=5)

    # 主参考语料第1条有 en_source 的
    ref_source_entry = None
    for ref in line_refs:
        zh_src = (ref.get("ch_source") or ref.get("source") or "").strip()
        en_src = (ref.get("en_source") or "").strip()
        if zh_src and en_src:
            ref_source_entry = {"zh_source": zh_src, "en_source": en_src}
            break

    # 组合：主参考在前，BM25 top5 在后，共最多6条
    para_list: list[dict] = []
    if ref_source_entry:
        para_list.append(ref_source_entry)
    para_list.extend(bm25_results)
    para_list = para_list[:6]

    ref_block = ""
    for i, p in enumerate(para_list, 1):
        ref_block += (
            f"\nParagraph {i}"
            f"\nzh_source: {p.get('zh_source') or ''}"
            f"\nen_source: {p.get('en_source') or ''}"
        )

    contents = (
        REFERENCE_SOURCE_TRANSLATE_PROMPT
        + f"\n\n待译出处：{source_zh}"
        + (f"\n\n参考语料：{ref_block}" if ref_block else "")
        + "\n\n请输出英文出处："
    )

    try:
        from testD.backend.enhanced_translate_service import _call_gemini_sync
        cumulative: dict = {"in_tok": 0, "out_tok": 0}
        text, _ = await asyncio.to_thread(
            _call_gemini_sync, contents, 0, None, cumulative
        )
        if text:
            result = text.strip()
            logger.info("[source_translator] Gemini 路2: %s → %s", source_zh, result)
            return result
    except Exception as e:
        logger.warning("[source_translator] Gemini 调用失败: %s", e)

    # 兜底：返回原中文
    return source_zh


async def translate_source_zh_batch(
    items: list[tuple[int, str, list[dict[str, Any]]]],
) -> dict[int, str]:
    """
    批量翻译未命中路1的 reference_source_zh。
    items: [(prep_index, source_zh, line_refs), ...]
    返回：{prep_index: source_en}
    """
    if not items:
        return {}

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
            logger.info("[source_translator] 路1命中: %s → %s", source_zh, hit_en)
        else:
            fallback_items.append((idx, source_zh, line_refs))

    if not fallback_items:
        return results

    logger.info("[source_translator] 路2批量: %d 条", len(fallback_items))

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
        from testD.backend.enhanced_translate_service import _call_gemini_sync
        cumulative: dict = {"in_tok": 0, "out_tok": 0}
        text, _ = await asyncio.to_thread(_call_gemini_sync, contents, 0, None, cumulative)
        if text:
            pattern = re.compile(r"^Source\s+(\d+)\s*:\s*(.+)$", re.MULTILINE)
            for m in pattern.finditer(text):
                pos = int(m.group(1)) - 1
                if 0 <= pos < len(fallback_items):
                    idx = fallback_items[pos][0]
                    results[idx] = m.group(2).strip()
                    logger.info(
                        "[source_translator] 路2命中: %s → %s",
                        fallback_items[pos][1],
                        results[idx],
                    )
    except Exception as e:
        logger.warning("[source_translator] 路2 Gemini 失败: %s", e)

    for idx, source_zh, _ in fallback_items:
        if idx not in results:
            results[idx] = source_zh

    return results
