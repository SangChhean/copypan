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
from testD.backend.additional_pool import levenshtein_distance, normalize_zh, zh_eq
from testD.backend.enhanced_translate_prompts import REFERENCE_SOURCE_TRANSLATE_PROMPT

logger = logging.getLogger("testD.source_translator")


# ── 1. 解析剥离 ──────────────────────────────────────────────
# 纲目行出处格式：（***）没有「，第***段」
# 多条出处靠起始词切分，不依赖；等分隔符。

_SOURCE_ANCHORS_LITERAL = [
    # 生命读经（63卷，含上下合并卷）
    "创世记生命读经", "出埃及记生命读经", "利未记生命读经", "民数记生命读经",
    "申命记生命读经", "约书亚记生命读经", "士师记生命读经", "路得记生命读经",
    "撒母耳记上下生命读经", "撒母耳记上生命读经", "撒母耳记下生命读经",
    "列王纪上下生命读经", "列王纪上生命读经", "列王纪下生命读经",
    "历代志上下生命读经", "历代志上生命读经", "历代志下生命读经",
    "历代志生命读经",
    "以斯拉记生命读经", "尼希米记生命读经", "以斯帖记生命读经",
    "约伯记生命读经", "诗篇生命读经", "箴言生命读经", "传道书生命读经",
    "雅歌生命读经", "以赛亚书生命读经", "耶利米书生命读经",
    "耶利米哀歌生命读经", "以西结书生命读经", "但以理书生命读经",
    "何西阿书生命读经", "约珥书生命读经", "阿摩司书生命读经",
    "俄巴底亚书生命读经", "约拿书生命读经", "弥迦书生命读经",
    "那鸿书生命读经", "哈巴谷书生命读经", "西番雅书生命读经",
    "哈该书生命读经", "撒迦利亚书生命读经", "玛拉基书生命读经",
    "马太福音生命读经", "马可福音生命读经", "路加福音生命读经",
    "约翰福音生命读经", "使徒行传生命读经", "罗马书生命读经",
    "哥林多前书生命读经", "哥林多后书生命读经", "加拉太书生命读经",
    "以弗所书生命读经", "腓立比书生命读经", "歌罗西书生命读经",
    "帖撒罗尼迦前书生命读经", "帖撒罗尼迦后书生命读经",
    "提摩太前书生命读经", "提摩太后书生命读经", "提多书生命读经",
    "腓利门书生命读经", "希伯来书生命读经", "雅各书生命读经",
    "彼得前书生命读经", "彼得后书生命读经",
    "约翰书信生命读经", "约翰一书生命读经", "约翰二书生命读经", "约翰三书生命读经",
    "犹大书生命读经", "启示录生命读经",
    # 文集
    "倪柝声文集", "李常受文集",
    # 其他
    "新约总论", "真理课程", "圣经恢复本", "诗歌", "今时代神圣启示的先见",
]

_LITERAL_ANCHORS_SORTED = sorted(_SOURCE_ANCHORS_LITERAL, key=len, reverse=True)
_YEAR_ANCHOR_RE = re.compile(r"\d{4}年")


def _anchor_len_at(inner: str, pos: int) -> int:
    """返回 pos 处最长匹配的起始词长度，无匹配返回 0。"""
    best = 0
    m = _YEAR_ANCHOR_RE.match(inner, pos)
    if m:
        best = m.end() - pos
    for anchor in _LITERAL_ANCHORS_SORTED:
        if inner.startswith(anchor, pos) and len(anchor) > best:
            best = len(anchor)
    return best


def _find_source_starts(inner: str) -> list[int]:
    """扫描 inner，返回每条出处的起始下标（仅 anchor 边界，不按分隔符切）。"""
    starts: list[int] = []
    i = 0
    while i < len(inner):
        if _anchor_len_at(inner, i):
            starts.append(i)
        i += 1
    return starts


def _trim_source_segment(seg: str) -> str:
    return seg.strip().strip("；,，; \t")


def _split_sources(inner: str) -> list[str]:
    """
    对括号内容正向扫描，用起始词识别每条出处位置，切分成 1～N 条。
    inner 为已去掉最外层括号的内容；未找到任何起始词返回 []。
    """
    inner = inner.strip()
    starts = _find_source_starts(inner)
    if not starts or starts[0] != 0:
        return []

    pieces: list[str] = []
    for k, start in enumerate(starts):
        end = starts[k + 1] if k + 1 < len(starts) else len(inner)
        seg = _trim_source_segment(inner[start:end])
        if seg:
            pieces.append(seg)
    return pieces


def format_source_zh(sources: list[str]) -> str:
    """将出处列表格式化为带外层括号的展示串。"""
    if not sources:
        return ""
    return "（" + "；".join(sources) + "）"


def bracket_has_star(reference_source_zh: str) -> bool:
    """原始括号内容去掉外层括号后，末尾是否带 *。"""
    inner = (reference_source_zh or "").strip().strip("（）()")
    return inner.rstrip().endswith("*")


def format_source_en(en_parts: list[str], has_star: bool = False) -> str:
    """
    纯净英文出处块，与 ``format_source_zh`` 结构对应：
    中文（a；b；c*）→ 英文 (a; b; c*)
    """
    parts = [
        _clean_source_en(p.strip().rstrip("*").strip())
        for p in en_parts
        if (p or "").strip()
    ]
    if not parts:
        return ""
    if has_star:
        parts[-1] = f"{parts[-1]}*"
    return "(" + "; ".join(parts) + ")"


def format_source_en_analysis(en_parts: list[str], has_star: bool) -> str:
    """
    带 Analysis_source[N] 标签的出处块，仅用于日志/调试输出。
    (Analysis_source[1]: {en_1}; Analysis_source[2]: {en_2}*)
    """
    parts = [p.strip().rstrip("*").strip() for p in en_parts if (p or "").strip()]
    if not parts:
        return ""
    items = [f"Analysis_source[{i}]: {p}" for i, p in enumerate(parts, 1)]
    if has_star:
        items[-1] = f"{items[-1]}*"
    return "(" + "; ".join(items) + ")"


def _outer_bracket_spans(line: str) -> list[tuple[int, int]]:
    """返回行内各最外层 （...） 的 (start, end)，按出现顺序。"""
    spans: list[tuple[int, int]] = []
    depth = 0
    start: int | None = None
    for i, ch in enumerate(line):
        if ch == "（":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "）":
            if depth == 0:
                continue
            depth -= 1
            if depth == 0 and start is not None:
                spans.append((start, i + 1))
                start = None
    return spans


def parse_source_from_line(line: str) -> tuple[str, list[str]]:
    """
    从纲目行中解析并剥离出处标注。
    返回：(剥离后的行内容, reference_source_zh 列表，每条不带外层括号)
    出处通常在行末；从右向左尝试各最外层括号，避免误命中正文内（犹3）等。
  """
    for start, end in reversed(_outer_bracket_spans(line)):
        inner = line[start + 1 : end - 1]
        sources = _split_sources(inner)
        if sources:
            stripped_line = (line[:start] + line[end:]).strip()
            return stripped_line, sources
    return line, []


# ── 2. 出处查询预处理与 kg-rag 路1 ─────────────────────────────

_CN_DIGIT = {
    "零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4,
    "五": 5, "六": 6, "七": 7, "八": 8, "九": 9,
}


def _chinese_numeral_to_int(text: str) -> int:
    """汉字数字 → 阿拉伯数字，支持到百位以上（如 二十三、一百零三、一百一十四）。"""
    s = (text or "").strip()
    if not s:
        return 0
    if s.isdigit():
        return int(s)
    total = 0
    current = 0
    for ch in s:
        if ch in _CN_DIGIT:
            current = _CN_DIGIT[ch]
        elif ch == "十":
            total += (current or 1) * 10
            current = 0
        elif ch == "百":
            total += (current or 1) * 100
            current = 0
        elif ch == "千":
            total += (current or 1) * 1000
            current = 0
        else:
            raise ValueError(f"unsupported chinese numeral: {ch!r}")
    return total + current


_PARA_SUFFIX_END_RE = re.compile(r"，第([^，）\*]+)段\**$")
_PARA_SUFFIX_BEFORE_CLOSE_RE = re.compile(r"，第([^，）]+)段(?=）)")


def _strip_paragraph_suffix(source0: str) -> tuple[str, str]:
    """
    去掉末尾「，第***段」，返回 (去掉段号后的串, 段号汉字)。
    支持行内出处（末尾段/段*）及 ES 带闭括号形式。
    """
    s = (source0 or "").strip()
    m = _PARA_SUFFIX_END_RE.search(s)
    if m:
        return s[: m.start()].rstrip("*").rstrip(), m.group(1)
    m2 = _PARA_SUFFIX_BEFORE_CLOSE_RE.search(s)
    if m2:
        return s[: m2.start()].rstrip("*").rstrip(), m2.group(1)
    return s.rstrip("*").rstrip(), ""


def _paragraph_suffix_en(para_zh: str) -> str:
    if not para_zh:
        return ""
    try:
        n = _chinese_numeral_to_int(para_zh)
    except ValueError:
        return ""
    return f"p. {n}" if n else ""


def _normalize_source_query(source_zh: str) -> tuple[str, str]:
    """
    出处查询预处理。
    返回 (normalize_zh 后的查询词, 段号英文后缀如 ``p. 3``，无段号则空串)。
    """
    raw = (source_zh or "").strip()
    base, para_zh = _strip_paragraph_suffix(raw)
    base = base.rstrip("*").rstrip()
    return normalize_zh(base), _paragraph_suffix_en(para_zh)


def _source_zh_base_from_hit(hit_source_zh: str) -> str:
    inner = (hit_source_zh or "").strip().strip("（）()")
    base, _ = _strip_paragraph_suffix(inner)
    return base


def _clean_source_en(source_en: str) -> str:
    return (source_en or "").strip().strip("（）()")


def _route1_source_en(source_zh: str, line_refs: list[dict[str, Any]]) -> str:
    """旧路1（line_refs），保留但不再调用。"""
    for ref in line_refs:
        zh_src = (ref.get("ch_source") or ref.get("source") or "").strip()
        if not zh_src:
            continue
        stripped, _ = _strip_paragraph_suffix(zh_src)
        if zh_eq(stripped, source_zh):
            en_src = (ref.get("en_source") or "").strip()
            if en_src:
                return en_src
    return ""


_KG_RAG_SOURCE_INDICES = ",".join([
    "kg-rag_cwwl",
    "kg-rag_life",
    "kg-rag_cwwn",
    "kg-rag_others",
    "kg-rag_bib",
    "kg-rag_7feasts",
    "kg-rag_map_note",
])

_FEASTS_POOL_INDEX = "feasts"

_MSG_NUM_RE = re.compile(r"，第(.+?)篇$")
_CHAPTER_NUM_RE = re.compile(r"，第(.+?)章$")
_YEAR_TRAINING_RE = re.compile(r"^(\d{4}年[^，]+)，第(.+?)篇$")
_BIB_RECOVERY_RE = re.compile(r"^圣经恢复本，")


def _lookup_variants(base: str) -> list[str]:
    """节期/训练出处检索变体（缺字、特会 等）。含季节补全的变体优先。"""
    seen: set[str] = set()
    prioritized: list[str] = []
    fallback: list[str] = []

    def add(s: str, *, priority: bool = False) -> None:
        s = (s or "").strip()
        if not s or s in seen:
            return
        seen.add(s)
        (prioritized if priority else fallback).append(s)

    if "安那翰全时间训练" in base and "秋季" not in base and "春季" not in base:
        add(base.replace("安那翰全时间", "安那翰秋季全时间"), priority=True)
    if "特会" in base:
        add(base.replace("特会", ""), priority=True)
    add(base)
    return prioritized + fallback


def _structured_source_queries(base: str) -> list[dict[str, Any]]:
    """从出处 base 生成结构化 ES 查询（弥补 source_zh 不可检索）。"""
    queries: list[dict[str, Any]] = []
    base = (base or "").strip()
    if not base:
        return queries

    m_msg = _MSG_NUM_RE.search(base)
    if m_msg:
        book = base[: m_msg.start()]
        try:
            msg_num = _chinese_numeral_to_int(m_msg.group(1))
        except ValueError:
            msg_num = None
        if book and msg_num:
            for book_try in {book, book.replace("腓立比", "腓利比")}:
                queries.append({
                    "bool": {
                        "must": [
                            {"term": {"book_title": book_try}},
                            {"term": {"message_number": msg_num}},
                        ]
                    }
                })
            short = book.split("，")[0]
            if short != book:
                queries.append({
                    "bool": {
                        "must": [
                            {"wildcard": {"book_title": f"*{short}*"}},
                            {"term": {"message_number": msg_num}},
                        ]
                    }
                })

    if _BIB_RECOVERY_RE.match(base):
        queries.append({"match": {"text": {"query": base, "analyzer": "ik_smart"}}})

    m_ch = _CHAPTER_NUM_RE.search(base)
    if m_ch:
        book_prefix = base[: m_ch.start()]
        if book_prefix:
            queries.insert(0, {"match_phrase": {"text": base}})
            queries.append({"term": {"book_title": book_prefix}})
            subtitle = book_prefix.split("，", 1)[-1][:35]
            if subtitle:
                queries.append({"wildcard": {"book_title": f"*{subtitle}*"}})

    m_train = _YEAR_TRAINING_RE.match(base)
    if m_train:
        book_title, num_zh = m_train.groups()
        try:
            msg_num = _chinese_numeral_to_int(num_zh)
        except ValueError:
            msg_num = None
        if msg_num:
            queries.append({
                "bool": {
                    "must": [
                        {"term": {"book_title": book_title}},
                        {"term": {"message_number": msg_num}},
                    ]
                }
            })

    if "，" in base and not m_msg:
        tail = base.split("，", 1)[1]
        if tail and ("文集" in base or "新约总论" in base):
            key = tail.split("，")[0][:40]
            if key and "篇" not in key:
                queries.append({"wildcard": {"book_title": f"*{key}*"}})

    if base.startswith("李常受文集") or base.startswith("倪柝声文集"):
        queries.append({"wildcard": {"book_title": f"*{base[-30:]}*"}})

    return queries


async def _kg_rag_bm25_recall(base: str, top_k: int = 20) -> list[dict[str, Any]]:
    """
    kg-rag 出处召回。``source_zh`` 映射为 index:false，无法对其 BM25；
    改为对 ``text`` 字段 BM25（与 kg_rag retrieval 一致），并辅以结构化查询。
    """
    if not base:
        return []

    seen_ids: set[str] = set()
    out: list[dict[str, Any]] = []

    async def _collect(body: dict[str, Any], limit: int) -> None:
        nonlocal out
        if limit <= 0:
            return
        try:
            resp = await asyncio.to_thread(
                es_client.search,
                index=indices,
                body={**body, "size": limit},
                request_timeout=10,
            )
        except Exception as e:
            logger.warning("[source_translator] kg-rag 出处召回失败: %s", e)
            return
        for hit in (resp.get("hits") or {}).get("hits") or []:
            if len(out) >= top_k:
                return
            hid = hit.get("_id") or ""
            if hid and hid in seen_ids:
                continue
            if hid:
                seen_ids.add(hid)
            src = hit.get("_source") or {}
            if src.get("source_zh"):
                out.append(src)

    src_fields = ["source_zh", "source_en", "book_title", "message_number"]
    indices = _KG_RAG_SOURCE_INDICES
    if _BIB_RECOVERY_RE.match(base):
        indices = f"{_KG_RAG_SOURCE_INDICES},kg-rag_map_note"

    for q in _structured_source_queries(base):
        await _collect(
            {"query": q, "_source": src_fields},
            top_k - len(out),
        )

    if len(out) < top_k:
        await _collect(
            {
                "query": {"match": {"text": {"query": base, "analyzer": "ik_smart"}}},
                "_source": src_fields,
            },
            top_k - len(out),
        )

    return out


def _dedupe_source_candidates(
    hits: list[dict[str, Any]],
    nq: str = "",
) -> list[dict[str, str]]:
    seen: set[str] = set()
    pairs: list[dict[str, str]] = []
    for hit in hits:
        sz = (hit.get("source_zh") or "").strip()
        if not sz:
            continue
        base = _source_zh_base_from_hit(sz)
        key = normalize_zh(base)
        if not key or key in seen:
            continue
        seen.add(key)
        pairs.append({
            "source_zh": base,
            "source_en": _clean_source_en(hit.get("source_en") or ""),
            "hit_source_zh": sz,
        })
    if nq:
        pairs.sort(
            key=lambda c: (
                0 if normalize_zh(c["source_zh"]) == nq else 1,
                levenshtein_distance(normalize_zh(c["source_zh"]), nq),
                len(normalize_zh(c["source_zh"])),
            )
        )
    return pairs


async def _feasts_pool_lookup(base: str) -> str:
    """从 feasts pool 索引匹配节期/全时间训练出处 en_source（严格 zh 全等）。"""
    for variant in _lookup_variants(base):
        nqv = normalize_zh(variant)
        try:
            resp = await asyncio.to_thread(
                es_client.search,
                index=_FEASTS_POOL_INDEX,
                body={
                    "query": {"match_phrase": {"title": variant}},
                    "size": 15,
                    "_source": ["source", "title"],
                },
                request_timeout=8,
            )
        except Exception as e:
            logger.warning("[source_translator] feasts pool 检索失败: %s", e)
            continue
        for hit in (resp.get("hits") or {}).get("hits") or []:
            src = (hit.get("_source") or {}).get("source") or []
            if len(src) < 2:
                continue
            zh_inner = (src[0] or "").strip().strip("（）()")
            zh_base, _ = _strip_paragraph_suffix(zh_inner)
            en = _clean_source_en(src[1] or "")
            if not en:
                continue
            nzh = normalize_zh(zh_base)
            if nzh == nqv or nzh == normalize_zh(variant):
                return en
    return ""


async def _gemini_infer_source_en(
    source_zh: str,
    ref_pairs: list[dict[str, str]],
) -> str:
    """距离推算：用 top 参考语料让 Gemini 翻译出处（段号原样交给 Gemini）。"""
    if not ref_pairs:
        return ""
    ref_lines: list[str] = []
    for i, pair in enumerate(ref_pairs[:6], 1):
        ref_lines.append(
            f"参考 {i}:\nzh_source: {pair['source_zh']}\nen_source: {pair['source_en']}"
        )
    contents = (
        REFERENCE_SOURCE_TRANSLATE_PROMPT
        + "\n\n"
        + "\n".join(ref_lines)
        + f"\n\n待译出处：{source_zh}\n\n请只输出英文出处，格式：Source 1: {{英文出处}}"
        + "\n不要在外层再加括号。"
    )
    try:
        from testD.backend.enhanced_translate_service import _call_gemini_sync
        cumulative: dict = {"in_tok": 0, "out_tok": 0}
        text, _ = await asyncio.to_thread(_call_gemini_sync, contents, 0, None, cumulative)
        if text:
            m = re.search(r"^Source\s+1\s*:\s*(.+)$", text.strip(), re.MULTILINE)
            if m:
                return _clean_source_en(m.group(1).strip())
            line = text.strip().splitlines()[0].strip()
            return _clean_source_en(re.sub(r"^Source\s+1\s*:\s*", "", line).strip())
    except Exception as e:
        logger.warning("[source_translator] kg-rag 距离推算 Gemini 失败: %s", e)
    return ""


async def _kg_rag_source_lookup(source_zh: str) -> tuple[str, str]:
    """
    新路1：查 kg-rag 索引 source_zh/source_en。
    返回 (英文出处, 段号英文如 p. 3)；均未命中时首项为空串。
    """
    raw = (source_zh or "").strip()
    _, para_zh = _strip_paragraph_suffix(raw)
    para_display = _paragraph_suffix_en(para_zh)
    para_append = f", {para_display}" if para_display else ""

    base, _ = _strip_paragraph_suffix(raw)
    base = base.rstrip("*").rstrip()
    nq = normalize_zh(base)

    if _YEAR_TRAINING_RE.match(base) or "感恩节" in base or "训练" in base:
        for variant in _lookup_variants(base):
            feast_en = await _feasts_pool_lookup(variant)
            if feast_en:
                return f"{feast_en}{para_append}", para_display

    hits = await _kg_rag_bm25_recall(base, top_k=20)
    candidates = _dedupe_source_candidates(hits, nq)

    for cand in candidates:
        nz = normalize_zh(cand["source_zh"])
        if nz == nq or levenshtein_distance(nz, nq) <= 1:
            en = cand["source_en"]
            if en:
                return f"{en}{para_append}", para_display
            if _YEAR_TRAINING_RE.match(base) or "训练" in base or "感恩节" in base:
                feast_en = await _feasts_pool_lookup(base)
                if feast_en:
                    return f"{feast_en}{para_append}", para_display

    if not candidates:
        feast_en = await _feasts_pool_lookup(base)
        if feast_en:
            return f"{feast_en}{para_append}", para_display
        return "", para_display

    ranked = sorted(
        candidates,
        key=lambda c: (
            levenshtein_distance(normalize_zh(c["source_zh"]), nq),
            len(normalize_zh(c["source_zh"])),
        ),
    )[:6]
    inferred = await _gemini_infer_source_en(raw, ranked)
    if inferred:
        return f"{inferred}{para_append}", para_display
    return "", para_display


class SourceLookupResult:
    """调试用：单条出处匹配详情。"""

    __slots__ = (
        "source_zh", "query", "match_method", "source_en",
        "para_en", "final_part",
    )

    def __init__(
        self,
        source_zh: str,
        query: str,
        match_method: str,
        source_en: str,
        para_en: str,
        final_part: str,
    ):
        self.source_zh = source_zh
        self.query = query
        self.match_method = match_method
        self.source_en = source_en
        self.para_en = para_en
        self.final_part = final_part


async def _kg_rag_source_lookup_debug(source_zh: str) -> SourceLookupResult:
    """带匹配方式标注的出处查询（验证用）。"""
    raw = (source_zh or "").strip()
    query, para_display = _normalize_source_query(raw)
    base = raw.rstrip("*").rstrip()
    base, _ = _strip_paragraph_suffix(base)
    base = base.rstrip("*").rstrip()
    nq = normalize_zh(base)
    para_append = f", {para_display}" if para_display else ""

    if _YEAR_TRAINING_RE.match(base) or "感恩节" in base or "训练" in base:
        for variant in _lookup_variants(base):
            feast_en = await _feasts_pool_lookup(variant)
            if feast_en:
                part = f"{feast_en}{para_append}"
                return SourceLookupResult(
                    source_zh=raw, query=base, match_method="全等命中(feasts)",
                    source_en=feast_en, para_en=para_display, final_part=part,
                )

    hits = await _kg_rag_bm25_recall(base, top_k=20)
    candidates = _dedupe_source_candidates(hits, nq)

    for cand in candidates:
        nz = normalize_zh(cand["source_zh"])
        if nz == nq or levenshtein_distance(nz, nq) <= 1:
            en = cand["source_en"]
            if en:
                part = f"{en}{para_append}"
                return SourceLookupResult(
                    source_zh=raw, query=base, match_method="全等命中",
                    source_en=en, para_en=para_display, final_part=part,
                )

    if candidates:
        ranked = candidates[:6]
        inferred = await _gemini_infer_source_en(raw, ranked)
        if inferred:
            part = f"{inferred}{para_append}" if para_display else inferred
            return SourceLookupResult(
                source_zh=raw, query=base, match_method="距离推算(top6)",
                source_en=inferred, para_en=para_display, final_part=part,
            )

    feast_en = await _feasts_pool_lookup(base)
    if feast_en:
        part = f"{feast_en}{para_append}"
        return SourceLookupResult(
            source_zh=raw, query=base, match_method="全等命中(feasts)",
            source_en=feast_en, para_en=para_display, final_part=part,
        )

    return SourceLookupResult(
        source_zh=raw, query=base, match_method="无命中",
        source_en="", para_en=para_display, final_part="",
    )


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


def _ref_block_from_line_refs(line_refs: list[dict[str, Any]]) -> str:
    for ref in line_refs:
        zh_src = (ref.get("ch_source") or ref.get("source") or "").strip()
        en_src = (ref.get("en_source") or "").strip()
        if zh_src and en_src:
            return (
                f"\nParagraph 1"
                f"\nzh_source: {zh_src}"
                f"\nen_source: {en_src}"
            )
    return ""


async def _gemini_translate_sources(
    numbered_sources: list[tuple[int, str]],
    line_refs: list[dict[str, Any]],
) -> dict[int, str]:
    """方案 A：同一条纲目行的多条未命中出处合并一次 Gemini。"""
    if not numbered_sources:
        return {}

    ref_block = _ref_block_from_line_refs(line_refs)
    blocks: list[str] = []
    for pos, (_, source_zh) in enumerate(numbered_sources, 1):
        blocks.append(
            f"Source {pos}: {source_zh}"
            + (f"\n参考语料：{ref_block}" if ref_block else "")
        )

    contents = (
        REFERENCE_SOURCE_TRANSLATE_PROMPT
        + "\n\n"
        + "\n\n".join(blocks)
        + "\n\n请逐条输出英文出处，格式：\n"
        + "\n".join(f"Source {pos}: {{英文出处}}" for pos in range(1, len(numbered_sources) + 1))
    )

    out: dict[int, str] = {}
    try:
        from testD.backend.enhanced_translate_service import _call_gemini_sync
        cumulative: dict = {"in_tok": 0, "out_tok": 0}
        text, _ = await asyncio.to_thread(_call_gemini_sync, contents, 0, None, cumulative)
        if text:
            pattern = re.compile(r"^Source\s+(\d+)\s*:\s*(.+)$", re.MULTILINE)
            for m in pattern.finditer(text):
                pos = int(m.group(1)) - 1
                if 0 <= pos < len(numbered_sources):
                    src_idx = numbered_sources[pos][0]
                    out[src_idx] = m.group(2).strip()
    except Exception as e:
        logger.warning("[source_translator] Gemini 调用失败: %s", e)

    for src_idx, source_zh in numbered_sources:
        if src_idx not in out:
            out[src_idx] = source_zh
    return out


# ── 4. 翻译出处 ───────────────────────────────────────────────

async def translate_source_zh(
    source_list: list[str],
    line_refs: list[dict[str, Any]],
    *,
    has_star: bool = False,
) -> str:
    """
    翻译 reference_source_zh 列表 → reference_source_en。
    路1：kg-rag source_zh/source_en；路2：同条纲目未命中项合并一次 Gemini。
    """
    if not source_list:
        return ""

    en_parts = [""] * len(source_list)
    miss: list[tuple[int, str]] = []

    for i, source_zh in enumerate(source_list):
        hit_en, _ = await _kg_rag_source_lookup(source_zh)
        if hit_en:
            en_parts[i] = hit_en
            logger.info("[source_translator] 路1命中: %s → %s", source_zh, hit_en)
        else:
            miss.append((i, source_zh))

    if miss:
        logger.info("[source_translator] 路2: %d 条出处合并一次 Gemini", len(miss))
        gemini_map = await _gemini_translate_sources(miss, line_refs)
        for i, source_zh in miss:
            en_parts[i] = gemini_map.get(i, source_zh)

    formatted = format_source_en(en_parts, has_star)
    logger.info(
        "[source_translator] 出处译文 %s | debug %s",
        formatted,
        format_source_en_analysis(en_parts, has_star),
    )
    return formatted


async def translate_source_zh_batch(
    items: list[tuple[int, list[str], list[dict[str, Any]], bool]],
) -> dict[int, str]:
    """
    批量翻译 reference_source_zh 列表。
    items: [(prep_index, source_list, line_refs, has_star), ...]
    返回：{prep_index: source_en}
    方案 A：每条纲目内未命中路1的出处合并一次 Gemini（省 token）。
    """
    if not items:
        return {}

    results: dict[int, str] = {}
    gemini_tasks: list[
        tuple[int, list[tuple[int, str]], list[dict[str, Any]], list[str], bool]
    ] = []

    for prep_idx, source_list, line_refs, has_star in items:
        if not source_list:
            continue

        en_parts = [""] * len(source_list)
        miss: list[tuple[int, str]] = []

        for i, source_zh in enumerate(source_list):
            hit_en, _ = await _kg_rag_source_lookup(source_zh)
            if hit_en:
                en_parts[i] = hit_en
                logger.info("[source_translator] 路1命中: %s → %s", source_zh, hit_en)
            else:
                miss.append((i, source_zh))

        if miss:
            gemini_tasks.append((prep_idx, miss, line_refs, en_parts, has_star))
        else:
            results[prep_idx] = format_source_en(en_parts, has_star)
            logger.info(
                "[source_translator] 出处译文 prep=%s %s | debug %s",
                prep_idx,
                results[prep_idx],
                format_source_en_analysis(en_parts, has_star),
            )

    if gemini_tasks:
        logger.info("[source_translator] 路2批量: %d 条纲目", len(gemini_tasks))

    async def _run_line(
        prep_idx: int,
        miss: list[tuple[int, str]],
        line_refs: list[dict[str, Any]],
        en_parts: list[str],
        has_star: bool,
    ) -> tuple[int, str]:
        gemini_map = await _gemini_translate_sources(miss, line_refs)
        for i, source_zh in miss:
            en_parts[i] = gemini_map.get(i, source_zh)
            logger.info(
                "[source_translator] 路2命中: %s → %s",
                source_zh,
                en_parts[i],
            )
        formatted = format_source_en(en_parts, has_star)
        logger.info(
            "[source_translator] 出处译文 prep=%s %s | debug %s",
            prep_idx,
            formatted,
            format_source_en_analysis(en_parts, has_star),
        )
        return prep_idx, formatted

    if gemini_tasks:
        outcomes = await asyncio.gather(
            *[
                _run_line(prep_idx, miss, line_refs, en_parts, has_star)
                for prep_idx, miss, line_refs, en_parts, has_star in gemini_tasks
            ]
        )
        for prep_idx, source_en in outcomes:
            results[prep_idx] = source_en

    return results


async def verify_source_lines(lines: list[str]) -> None:
    """解析 + 路1出处查询，打印每条出处的匹配与译文（验证用）。"""
    for line_no, line in enumerate(lines, 1):
        print(f"\n{'='*60}")
        print(f"行 {line_no}: {line[:80]}...")
        stripped, sources = parse_source_from_line(line)
        has_star = bracket_has_star(format_source_zh(sources))
        print(f"剥离正文: {stripped[:60]}...")
        print(f"出处数: {len(sources)}, has_star={has_star}")

        en_parts: list[str] = []
        for i, src in enumerate(sources, 1):
            detail = await _kg_rag_source_lookup_debug(src)
            print(f"[出处{i}] source_zh查询词: {detail.query}")
            print(f"[出处{i}] 匹配方式: {detail.match_method}")
            print(f"[出处{i}] source_en: {detail.source_en or '(空)'}")
            print(f"[出处{i}] para_en: {detail.para_en or '(空)'}")
            print(f"[出处{i}] 最终拼接: {detail.final_part or '(空)'}")
            en_parts.append(detail.final_part)

        print(f"全行出处块(debug): {format_source_en_analysis(en_parts, has_star) or '(空)'}")
        print(f"全行出处块: {format_source_en(en_parts, has_star) or '(空)'}")


if __name__ == "__main__":
    _TEST_LINES = [
        "1\u3000亚当是旧团体人（人类）的元首，凡他所行的，以及一切发生在他身上的，全人类都有分─12节。（2000年安那翰秋季全时间训练，第二篇；李常受文集一九九〇年第一册，三一神作三部分人的生命，第一章，第一段；李常受文集一九八〇年第一册，成全训练，第二十二章，第一段）",
        "1\u3000亚当是旧团体人（人类）的元首，凡他所行的，以及一切发生在他身上的，全人类都有分─12节。（2000年安那翰秋季全时间训练，第二篇；路加福音生命读经，第五十六篇，第三段*）",
        "1\u3000亚当是旧团体人（人类）的元首，凡他所行的，以及一切发生在他身上的，全人类都有分─12节。（2000年感恩节特会，第四篇；腓立比书生命读经，第三十六篇，第四段*）",
        "1\u3000亚当是旧团体人（人类）的元首，凡他所行的，以及一切发生在他身上的，全人类都有分─12节。（2000年安那翰秋季全时间训练，第二篇；新约总论，第一百一十四篇，第十七段*）",
    ]
    asyncio.run(verify_source_lines(_TEST_LINES))
