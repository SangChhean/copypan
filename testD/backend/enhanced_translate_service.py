# -*- coding: utf-8 -*-
"""
增强式翻译：逐行解析纲目 → Pool 短路 → 分句检索参考 → Gemini 批量中翻英。
业务代码位于 testD/，复用 back_mic 的 ES / 检索 / Gemini。
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from testD.backend._bootstrap import ensure_main_backend_path

ensure_main_backend_path()

from dotenv import load_dotenv

load_dotenv(ensure_main_backend_path() / ".env")

from kg_rag.embedding_adapter import OPENROUTER_API_KEY
from kg_rag.retrieval import bm25_search, dense_search, rrf_merge
from testD.backend.rerank_service import rerank
from es_config import es as es_client
from ai_search.ai_service import (
    GEMINI_SEMAPHORE,
    GEMINI_MODEL,
    GEMINI_TRANSLATION_FALLBACK_MODEL,
    _gemini_error_is_retryable,
    gemini_client,
)
# 增强式翻译独立模型配置（覆盖 ai_service 全局设置）
GEMINI_MODEL = "gemini-3.5-flash"
GEMINI_TRANSLATION_FALLBACK_MODEL = "gemini-2.5-flash"


from ai_search.gemini_translation_instruction import GEMINI_TRANSLATION_SYSTEM_INSTRUCTION
from ai_search.gemini_response_utils import (
    extract_translatable_text,
    gemini_translation_generate_config,
)

from testD.backend.additional_pool import (
    append_records,
    auto_append_enabled,
    collect_auto_append_rows,
    levenshtein_distance,
    lookup_line_en,
    normalize_zh,
    recall_local_pool_hits,
    zh_contains,
    zh_eq,
    zh_fuzzy_eq,
)
from testD.backend.enhanced_translate_prompts import (
    ENHANCED_TRANSLATE_PROMPT_EN2ZH,
    ENHANCED_TRANSLATE_PROMPT_FEASTS,
    ENHANCED_TRANSLATE_PROMPT_SUFFIX,
    PROOFREAD_OUTLINE_PROMPT,
)
from testD.backend.source_translator import (
    format_source_zh,
    parse_source_from_line,
    translate_source_zh_batch,
)

logger = logging.getLogger("testD.enhanced_translate")

_INDICES_DENSE = ",".join([
    "kg-rag_cwwl",
    "kg-rag_life",
    "kg-rag_cwwn",
    "kg-rag_others",
    "kg-rag_bib",
])

_INDICES_BM25 = ",".join([
    "life", "cwwn", "cwwl", "others",
    "bib", "foo", "hymn", "feasts",
])

_POOL_INDICES = _INDICES_BM25

MAX_CONTENT_CHARS = 100_000

_PROMPT_OVERRIDE: str = ""
_RERANK_SEM = asyncio.Semaphore(10)

_BATCH_LINE_OUT_RE = re.compile(r"^Line\s+(\d+)\s*:\s*(.*)$", re.MULTILINE)

_MINISTERIALIZE_PREFIX_RE = re.compile(
    r"^[壹貳贰參叄叁参肆伍陸陆柒捌玖拾一二三四五六七八九十\da-zａ-ｚ（）()]+[\t　 ]"
)
_BIBLE_BOOKS_66 = (
    "创出利民申书士得撒上撒下王上王下代上代下拉尼斯伯诗箴传歌赛耶哀结但"
    "何珥摩俄拿弥鸿哈番该亚玛"
    "太可路约徒罗林前林后加弗腓西帖前帖后提前提后多门来雅彼前彼后约壹约贰约叁犹启"
    "参"
)
_BIBLE_BOOKS = "".join(dict.fromkeys(_BIBLE_BOOKS_66))
_BOOK_PAT = rf"[{_BIBLE_BOOKS}]{{1,4}}"
_CHAP_PAT = r"[\d一二三四五六七八九十百～~\-至、\s]+"
_REF_UNIT = rf"(?:{_BOOK_PAT})?{_CHAP_PAT}"
_DASH_CLASS = "[—─–―]"
_SCRIPTURE_REF_RE = re.compile(
    rf"({_DASH_CLASS}{_BOOK_PAT}{_CHAP_PAT}(?:[,，；;]{_REF_UNIT})*[：:。]?\s*)$"
)
_PURE_VERSE_RE = re.compile(rf"({_DASH_CLASS}[\d～~\-至、\s\d]+节[。：:]?\s*)$")
_SCRIPTURE_PLACEHOLDER_SUFFIX_RE = re.compile(
    r"(?:[：:]\s*)?[—─–―\-]?引用经文\s*$"
)
_SCRIPTURE_CANDIDATE_RE = re.compile(
    rf"^{_DASH_CLASS}参?(?:"
    rf"(?:[{_BIBLE_BOOKS}]{{1,4}})[一二三四五六七八九十百千]*\d"
    rf"|[一二三四五六七八九十百千]+\d"
    rf"|\d"
    rf")"
)

_PREFIX_TO_EN = {
    "壹": "I.",
    "贰": "II.",
    "參": "III.",
    "参": "III.",
    "肆": "IV.",
    "伍": "V.",
    "陆": "VI.",
    "陸": "VI.",
    "柒": "VII.",
    "捌": "VIII.",
    "玖": "IX.",
    "拾": "X.",
    "一": "A.",
    "二": "B.",
    "三": "C.",
    "四": "D.",
    "五": "E.",
}

_OUTLINE_HEAD_RE = re.compile(
    r"^(?:"
    r"[壹贰叁肆伍陆柒捌一二三四五六七八九十]"
    r"|\d+"
    r"|[a-z]"
    r"|[（(](?:[一二三四五六七八九十]+|\d+|[a-z])[)）]"
    r")"
)

_CN_NUM = r"[一二三四五六七八九十百千零〇\d]+"
_TITLE_PREFIX_RE = re.compile(rf"^第{_CN_NUM}[篇章课题问期][\t　\s]*")
_BIBLE_READING_COLON_RE = re.compile(r"^读经[：:]")
_BIBLE_READING_AFTER_TITLE_RE = re.compile(r"^读经")


def get_prompt_override() -> str:
    return _PROMPT_OVERRIDE


def set_prompt_override(prompt: str) -> None:
    global _PROMPT_OVERRIDE
    _PROMPT_OVERRIDE = (prompt or "").strip()


def _find_scripture_suffix(rest: str) -> tuple[str, str]:
    m_ph = _SCRIPTURE_PLACEHOLDER_SUFFIX_RE.search(rest)
    if m_ph:
        return rest[: m_ph.start()].rstrip(), rest[m_ph.start() :].strip()
    m = re.search(r"[—─–―]", rest[::-1])
    if not m:
        return rest, ""
    pos = len(rest) - m.start() - 1
    candidate = rest[pos:]
    if _SCRIPTURE_CANDIDATE_RE.match(candidate):
        return rest[:pos], candidate
    return rest, ""


_DASH_VARIANTS_RE = re.compile(r"[─–―－−‐﹘]")


def _strip_scripture_suffix(line: str) -> tuple[str, str, str]:
    line = _DASH_VARIANTS_RE.sub("—", line)
    # 双破折号（——）归一为单破折号，避免候选正则只认单破折号导致剥离失败
    line = re.sub(r"—{2,}", "—", line)
    text = line
    m = _MINISTERIALIZE_PREFIX_RE.match(text)
    if m:
        prefix = m.group(0)
        rest = text[m.end() :]
    else:
        prefix = ""
        rest = text
    body, suffix = _find_scripture_suffix(rest)
    return prefix, body.strip(), suffix


def _split_body(body: str) -> list[str]:
    body = (body or "").strip()
    if not body:
        return []
    if "；" in body:
        parts = [p.strip() for p in body.split("；")]
        return [p for p in parts if p]
    return [body]


def _split_reference(body: str) -> list[str]:
    """reference 行按强分句标点切句，短句（<15字）自动合并到下一句。"""
    body = (body or "").strip()
    if not body:
        return []
    parts = re.split(r"(?<=[。！？])", body)
    parts = [p.strip() for p in parts if p.strip()]

    # 短句合并：少于15字的句子与下一句合并
    merged: list[str] = []
    buffer = ""
    for p in parts:
        if buffer:
            buffer = buffer + p
        else:
            buffer = p
        if len(buffer) >= 15:
            merged.append(buffer)
            buffer = ""
    if buffer:
        if merged:
            merged[-1] = merged[-1] + buffer
        else:
            merged.append(buffer)

    return [p for p in merged if len(p) >= 5]


def _detect_line_type(
    body: str,
    prefix: str = "",
    *,
    prev_line_type: str = "",
) -> str:
    if (prefix or "").strip():
        return "outline"
    s = (body or "").lstrip()
    if not s:
        return "reference"
    if _BIBLE_READING_COLON_RE.match(s):
        return "bible-reading"
    if prev_line_type == "title" and _BIBLE_READING_AFTER_TITLE_RE.match(s):
        return "bible-reading"
    if _TITLE_PREFIX_RE.match(s):
        return "title"
    if _OUTLINE_HEAD_RE.match(s):
        return "outline"
    return "reference"


def _precompute_line_types(lines: list[str]) -> list[str]:
    types: list[str] = []
    for line in lines:
        line_for_retrieval, _ = parse_source_from_line(line)
        prefix, body, _ = _strip_scripture_suffix(line_for_retrieval)
        prev = types[-1] if types else ""
        types.append(_detect_line_type(body, prefix, prev_line_type=prev))
    return types


def _strip_title_prefix(body: str) -> str:
    s = (body or "").lstrip()
    return _TITLE_PREFIX_RE.sub("", s, count=1).strip()


def _dedupe_hits_by_zh(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for h in hits:
        key = normalize_zh(_hit_zh_text(h))
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


def _translate_prefix(prefix: str) -> str:
    if not prefix:
        return ""
    core = prefix.rstrip("\t　 ")
    mapped = _PREFIX_TO_EN.get(core.strip())
    if mapped:
        sep = "\t" if "\t" in prefix else ("　" if "　" in prefix else " ")
        return mapped + sep
    return prefix


@dataclass
class _RetrievalCtx:
    index: str
    bm25_index: str = ""
    es_enabled: bool = True
    dense_enabled: bool = True
    en_dense_enabled: bool = False
    warnings: list[str] = field(default_factory=list)
    _es_down_logged: bool = False

    @classmethod
    def create(cls, index: str | None = None) -> "_RetrievalCtx":
        ctx = cls(index=index or _INDICES_DENSE, bm25_index=_INDICES_BM25)
        if not (OPENROUTER_API_KEY or "").strip():
            ctx.dense_enabled = False
            ctx.warnings.append(
                "未配置 OPENROUTER_API_KEY，已跳过向量检索（dense）；可在 back_mic/backend/.env 中设置"
            )
        return ctx

    def mark_es_down(self, reason: str) -> None:
        if self.es_enabled:
            self.es_enabled = False
            self.warnings.append(
                "Elasticsearch 暂时无法连接，请稍等片刻后重试。若持续出现请检查 ES 是否启动、kg-rag_* 索引是否正常。"
            )
        if not self._es_down_logged:
            logger.warning("[enhanced_translate] ES 不可用，本请求跳过检索: %s", reason)
            self._es_down_logged = True


def _is_es_failure(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return (
        "503" in msg
        or "search_phase_execution_exception" in msg
        or "unavailable" in msg
        or "connection" in msg
        or "timeout" in msg
    )


async def _probe_es(ctx: _RetrievalCtx) -> None:
    max_attempts = 3
    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            ok = await asyncio.to_thread(es_client.ping, request_timeout=10)
            if ok:
                return
            raise Exception("ping 返回 False")
        except Exception as e:
            last_err = e
            if attempt < max_attempts:
                logger.warning(
                    "[enhanced_translate] ES 探测失败，3 秒后重试 (%s/%s): %s",
                    attempt,
                    max_attempts,
                    e,
                )
                await asyncio.sleep(3)
    ctx.mark_es_down(str(last_err) if last_err else "未知错误")


async def _pool_lookup(clause: str, *, fuzzy: bool = False) -> str | None:
    clause = (clause or "").strip()
    if not clause:
        return None
    match_fn = zh_fuzzy_eq if fuzzy else zh_eq
    body = {
        "query": {"match": {"zh": {"query": clause, "operator": "or"}}},
        "size": 300,
        "_source": ["zh", "en", "text"],
    }
    try:
        resp = await asyncio.to_thread(
            es_client.search,
            index=_POOL_INDICES,
            body=body,
            request_timeout=8,
        )
    except Exception as e:
        logger.warning("[enhanced_translate] pool lookup 失败: %s", e)
        return None
    for hit in (resp.get("hits") or {}).get("hits") or []:
        src = hit.get("_source") or {}
        hit_zh = (src.get("zh") or src.get("text") or "").strip()
        if match_fn(hit_zh, clause):
            en = (src.get("en") or "").strip()
            if en:
                return en
    return None


async def _pool_lookup_hit(clause: str, *, fuzzy: bool = False) -> dict[str, Any] | None:
    clause = (clause or "").strip()
    if not clause:
        return None
    match_fn = zh_fuzzy_eq if fuzzy else zh_eq
    body = {
        "query": {"match": {"zh": {"query": clause, "operator": "or"}}},
        "size": 300,
        "_source": ["zh", "en", "text", "chunk_id", "source", "source_zh", "source_en"],
    }
    try:
        resp = await asyncio.to_thread(
            es_client.search,
            index=_POOL_INDICES,
            body=body,
            request_timeout=8,
        )
    except Exception as e:
        logger.warning("[enhanced_translate] pool lookup hit 失败: %s", e)
        return None
    for hit in (resp.get("hits") or {}).get("hits") or []:
        src = hit.get("_source") or {}
        hit_zh = (src.get("zh") or src.get("text") or "").strip()
        if match_fn(hit_zh, clause):
            out = dict(src)
            out.setdefault("chunk_id", hit.get("_id", ""))
            out.setdefault("text", hit_zh)
            out["match_kind"] = "pool"
            return out
    return None


def _hit_zh_text(hit: dict[str, Any]) -> str:
    return ((hit.get("text") or hit.get("zh") or "")).strip()


async def _pool_recall_hits(query: str, top_k: int = 300) -> list[dict[str, Any]]:
    """ES Pool 同款 match zh 召回；供 reference 整行子串匹配，与 BM25 排序无关。"""
    query = (query or "").strip()
    if not query:
        return []
    body = {
        "query": {"match": {"zh": {"query": query, "operator": "or"}}},
        "size": top_k,
        "_source": [
            "chunk_id",
            "text",
            "zh",
            "en",
            "book_title",
            "author",
            "source_zh",
            "source_en",
            "source",
            "message_number",
            "message_title",
            "section_title",
        ],
    }
    try:
        resp = await asyncio.to_thread(
            es_client.search,
            index=_POOL_INDICES,
            body=body,
            request_timeout=8,
        )
    except Exception as e:
        logger.warning("[enhanced_translate] pool recall 失败: %s", e)
        return []
    out: list[dict[str, Any]] = []
    for hit in (resp.get("hits") or {}).get("hits") or []:
        src = (hit.get("_source") or {}).copy()
        src["score"] = hit.get("_score") or 0.0
        src["retrieval_route"] = "pool_recall"
        src["_index"] = hit.get("_index") or ""
        src.setdefault("chunk_id", hit.get("_id", ""))
        if not (src.get("text") or "").strip() and (src.get("zh") or "").strip():
            src["text"] = src["zh"]
        out.append(src)
    return out


def _pool_hit_body(hit: dict[str, Any]) -> str:
    _, hit_body, _ = _strip_scripture_suffix(_hit_zh_text(hit))
    return hit_body.strip()


def _is_feasts_hit(hit: dict[str, Any]) -> bool:
    idx = (hit.get("_index") or "").strip().lower()
    return idx == "feasts" or idx.startswith("feasts")


def _pool_hit_matches_outline_body(body: str, hit: dict[str, Any]) -> bool:
    """Feasts 仅 body 全等；非 Feasts 另接受 body 为 hit 全文子串（纲要句嵌在长段语料）。"""
    if not (body or "").strip():
        return False
    if zh_eq(body, _pool_hit_body(hit)):
        return True
    if _is_feasts_hit(hit):
        return False
    return zh_contains(body, _hit_zh_text(hit))


async def _outline_body_pool_exact(body: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """body Pool 300 召回后筛匹配；返回 (feasts_hits, other_hits)。"""
    body = (body or "").strip()
    if not body:
        return [], []
    feasts_exact: list[dict[str, Any]] = []
    other_exact: list[dict[str, Any]] = []
    for h in await _pool_recall_hits(body, 300):
        if not _pool_hit_matches_outline_body(body, h):
            continue
        if not (h.get("en") or "").strip():
            continue
        if _is_feasts_hit(h):
            feasts_exact.append(h)
        else:
            other_exact.append(h)
    return feasts_exact, other_exact


async def _pool_lookup_clause(clause: str) -> str | None:
    """分句检索专用：子串匹配，normalize_zh(clause) in normalize_zh(hit_zh)。"""
    clause = (clause or "").strip()
    if not clause:
        return None
    body = {
        "query": {"match": {"zh": {"query": clause, "operator": "or"}}},
        "size": 10,
        "_source": ["zh", "en", "text"],
    }
    try:
        resp = await asyncio.to_thread(
            es_client.search,
            index=_POOL_INDICES,
            body=body,
            request_timeout=8,
        )
    except Exception as e:
        logger.warning("[enhanced_translate] pool clause lookup 失败: %s", e)
        return None
    for hit in (resp.get("hits") or {}).get("hits") or []:
        src = hit.get("_source") or {}
        hit_zh = (src.get("zh") or src.get("text") or "").strip()
        if zh_contains(clause, hit_zh):
            en = (src.get("en") or "").strip()
            if en:
                return en
    return None


async def _feasts_body_lookup(body: str) -> str | None:
    """用 body 在 feasts 索引做 match 召回 + normalize 验证，返回英文 body 或 None。"""
    body = (body or "").strip()
    if not body:
        return None
    es_body = {
        "query": {"match": {"zh": {"query": body, "operator": "or"}}},
        "size": 300,
        "_source": ["zh", "en", "text"],
    }
    try:
        resp = await asyncio.to_thread(
            es_client.search,
            index="feasts",
            body=es_body,
            request_timeout=8,
        )
    except Exception as e:
        logger.warning("[enhanced_translate] feasts body lookup 失败: %s", e)
        return None
    for hit in (resp.get("hits") or {}).get("hits") or []:
        src = hit.get("_source") or {}
        hit_zh = (src.get("zh") or src.get("text") or "").strip()
        _, hit_body, _ = _strip_scripture_suffix(hit_zh)
        if zh_eq(hit_body, body):
            en = (src.get("en") or "").strip()
            if en:
                return en
    return None


async def _pool_lookup_en2zh(clause: str) -> str | None:
    clause = (clause or "").strip()
    if not clause:
        return None
    body = {
        "query": {"match_phrase": {"en": {"query": clause}}},
        "size": 10,
        "_source": ["zh", "en", "text"],
    }
    try:
        resp = await asyncio.to_thread(
            es_client.search,
            index=_POOL_INDICES,
            body=body,
            request_timeout=8,
        )
    except Exception as e:
        logger.warning("[enhanced_translate] pool en2zh lookup 失败: %s", e)
        return None
    for hit in (resp.get("hits") or {}).get("hits") or []:
        src = hit.get("_source") or {}
        hit_en = (src.get("en") or "").strip()
        if zh_eq(hit_en, clause):
            zh = (src.get("zh") or src.get("text") or "").strip()
            if zh:
                return zh
    return None


async def _exact_match(clause: str, ctx: _RetrievalCtx) -> list[dict[str, Any]]:
    if not ctx.es_enabled or not clause or not clause.strip():
        return []
    body = {
        "query": {"match_phrase": {"text": {"query": clause}}},
        "size": 40,
        "_source": [
            "chunk_id",
            "text",
            "en",
            "book_title",
            "source_zh",
            "source_en",
            "message_number",
            "message_title",
        ],
    }
    try:
        resp = await asyncio.to_thread(
            es_client.search,
            index=ctx.index,
            body=body,
            request_timeout=8,
        )
    except Exception as e:
        if _is_es_failure(e):
            ctx.mark_es_down(str(e))
        else:
            logger.warning("[enhanced_translate] exact_match 失败: %s", e)
        return []
    out: list[dict[str, Any]] = []
    for hit in (resp.get("hits") or {}).get("hits") or []:
        src = (hit.get("_source") or {}).copy()
        text = (src.get("text") or "").strip()
        if zh_contains(clause, text):
            src["score"] = hit.get("_score") or 0.0
            src["chunk_id"] = src.get("chunk_id") or hit.get("_id", "")
            src["_index"] = hit.get("_index") or ""
            src["match_kind"] = "exact"
            out.append(src)
    return out


async def _exact_match_en(clause: str, ctx: _RetrievalCtx) -> list[dict[str, Any]]:
    if not ctx.es_enabled or not clause or not clause.strip():
        return []
    body = {
        "query": {"match_phrase": {"en": {"query": clause}}},
        "size": 40,
        "_source": [
            "chunk_id",
            "text",
            "en",
            "zh",
            "book_title",
            "source_zh",
            "source_en",
            "message_number",
            "message_title",
        ],
    }
    try:
        resp = await asyncio.to_thread(
            es_client.search,
            index=ctx.index,
            body=body,
            request_timeout=8,
        )
    except Exception as e:
        if _is_es_failure(e):
            ctx.mark_es_down(str(e))
        else:
            logger.warning("[enhanced_translate] exact_match_en 失败: %s", e)
        return []
    out: list[dict[str, Any]] = []
    for hit in (resp.get("hits") or {}).get("hits") or []:
        src = (hit.get("_source") or {}).copy()
        en = (src.get("en") or "").strip()
        if zh_contains(clause, en):
            src["score"] = hit.get("_score") or 0.0
            src["chunk_id"] = src.get("chunk_id") or hit.get("_id", "")
            src["_index"] = hit.get("_index") or ""
            src["match_kind"] = "exact"
            out.append(src)
    return out


def _hit_chunk_id(hit: dict[str, Any]) -> str:
    return (hit.get("chunk_id") or hit.get("_id") or "").strip()


def _dedup_key(hit: dict[str, Any]) -> str:
    """
    去重键：优先用 normalize_zh(text) 跨索引去重；
    text 为空时用 {index}::{chunk_id} 区分来源。
    """
    nt = normalize_zh((hit.get("text") or hit.get("zh") or "").strip())
    if nt:
        return nt
    index = (hit.get("_index") or "").strip()
    cid = _hit_chunk_id(hit)
    return f"{index}::{cid}" if index else cid


def _dedupe_hits_by_chunk_id(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for h in hits:
        cid = _hit_chunk_id(h)
        if cid:
            if cid in seen:
                continue
            seen.add(cid)
        out.append(h)
    return out


def _filter_en_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [h for h in hits if (h.get("en") or "").strip()]


def _filter_zh_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [h for h in hits if (h.get("zh") or h.get("text") or "").strip()]


async def _bm25_hits(query: str, index: str, top_k: int = 40) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    raw = await bm25_search(es_client, q, index, top_k)
    return _filter_en_hits(raw)


async def _bm25_hits_en(query: str, index: str, top_k: int = 40) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    body_q = {
        "query": {"match": {"en": {"query": q, "analyzer": "standard"}}},
        "size": top_k,
        "_source": ["chunk_id", "text", "en", "zh", "book_title", "source_zh", "source_en", "source"],
    }
    try:
        resp = await asyncio.to_thread(es_client.search, index=index, body=body_q)
    except Exception as e:
        logger.warning("[enhanced_translate] bm25_en 失败: %s", e)
        return []
    out = []
    for hit in (resp.get("hits") or {}).get("hits") or []:
        src = (hit.get("_source") or {}).copy()
        src["score"] = hit.get("_score") or 0.0
        src["retrieval_route"] = "bm25"
        src["_index"] = hit.get("_index") or ""
        src.setdefault("chunk_id", hit.get("_id", ""))
        out.append(src)
    return _filter_zh_hits(out)


async def _dense_hits(query: str, ctx: _RetrievalCtx, top_k: int = 40) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not ctx.es_enabled or not ctx.dense_enabled or not q:
        return []
    raw = await dense_search(es_client, q, ctx.index, top_k, 100)
    return _filter_en_hits(raw)


async def _clause_retrieval(clause: str, ctx: _RetrievalCtx) -> list[dict[str, Any]]:
    exact_hits, bm25_hits = await asyncio.gather(
        _exact_match(clause, ctx),
        _bm25_hits(clause, ctx.bm25_index, 40),
    )
    return exact_hits + bm25_hits


async def _clause_retrieval_en(clause: str, ctx: _RetrievalCtx) -> list[dict[str, Any]]:
    exact_hits, bm25_hits = await asyncio.gather(
        _exact_match_en(clause, ctx),
        _bm25_hits_en(clause, ctx.bm25_index, 40),
    )
    return exact_hits + bm25_hits


async def _enrich_hit_en(hit: dict[str, Any], ctx: _RetrievalCtx) -> dict[str, Any]:
    if not ctx.es_enabled or (hit.get("en") or "").strip():
        return hit
    cid = hit.get("chunk_id") or hit.get("_id")
    if not cid:
        return hit
    idx = hit.get("_index") or (ctx.index.split(",")[0] if ctx.index else "kg-rag_life")
    try:
        resp = await asyncio.to_thread(
            es_client.get,
            index=idx,
            id=cid,
            _source=["en", "text", "source_zh", "source_en", "book_title"],
            request_timeout=8,
        )
        src = (resp.get("_source") or {}).copy()
        hit.update({k: v for k, v in src.items() if v})
    except Exception as e:
        if _is_es_failure(e):
            ctx.mark_es_down(str(e))
        else:
            logger.debug("[enhanced_translate] enrich en 失败 %s: %s", cid, e)
    return hit


def _extract_source(hit: dict) -> str:
    source_arr = hit.get("source")
    if isinstance(source_arr, list) and source_arr:
        return (source_arr[0] or "").strip()
    return (
        (hit.get("source_zh") or "").strip()
        or (hit.get("book_title") or "").strip()
        or (hit.get("title") or "").strip()
    )


def _extract_en_source(hit: dict) -> str:
    source_arr = hit.get("source")
    if isinstance(source_arr, list) and len(source_arr) > 1:
        return (source_arr[1] or "").strip()
    return (hit.get("source_en") or "").strip()


def _build_ref_entry(
    line_index: int,
    clause_index: int,
    clause: str,
    hit: dict[str, Any] | None,
) -> dict[str, Any]:
    if not hit:
        return {
            "line_index": line_index,
            "clause_index": clause_index,
            "zh": clause,
            "match_kind": "none",
            "match_type": "none",
            "zh_snippet": "",
            "en_snippet": "",
            "text": "",
            "en": "",
            "chunk_id": "",
            "id": "",
            "source": "",
            "ch_source": "",
            "en_source": "",
            "source_type": "main",
            "clauses": [],
        }
    text = (hit.get("text") or "").strip()
    en = (hit.get("en") or "").strip()
    chunk_id = (hit.get("chunk_id") or hit.get("_id") or "").strip()
    mk = hit.get("match_kind")
    if mk in ("pool", "exact", "retrieved"):
        match_kind = mk
        if match_kind == "exact":
            zh_snippet = clause
        elif match_kind == "retrieved":
            zh_snippet = text[:200] + ("…" if len(text) > 200 else "") if text else clause
        else:
            zh_snippet = clause
    elif zh_contains(clause, text):
        match_kind = "exact"
        zh_snippet = clause
    elif text or chunk_id:
        match_kind = "retrieved"
        zh_snippet = text[:200] + ("…" if len(text) > 200 else "") if text else clause
    else:
        match_kind = "none"
        zh_snippet = ""
    match_type = (
        "direct"
        if match_kind == "exact"
        else ("reference" if match_kind in ("retrieved", "pool") else "none")
    )
    source = _extract_source(hit)
    en_source = _extract_en_source(hit)
    logger.debug("[ref_entry] ch_source=%r en_source=%r", source, en_source)
    return {
        "line_index": line_index,
        "clause_index": clause_index,
        "zh": clause,
        "match_kind": match_kind,
        "match_type": match_type,
        "zh_snippet": zh_snippet if match_kind != "none" else "",
        "en_snippet": en,
        "text": text,
        "en": en,
        "chunk_id": chunk_id,
        "id": chunk_id,
        "source": source,
        "ch_source": source,
        "en_source": en_source,
        "source_type": hit.get("source_type") or "main",
        "clauses": hit.get("clauses") or [],
    }


def _dedupe_refs_by_chunk_id(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for r in refs:
        key = _dedup_key(r)
        if key and key not in seen:
            seen.add(key)
            deduped.append(r)
        elif not key:
            deduped.append(r)
    return deduped


def _assign_paragraph_numbers(deduped_refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for i, r in enumerate(deduped_refs, 1):
        item = dict(r)
        item["paragraph"] = i
        out.append(item)
    return out


def _format_ref_block_for_gemini(deduped_refs: list[dict[str, Any]]) -> str:
    if not deduped_refs:
        return ""
    block = "\n\n参考语料："
    for i, r in enumerate(deduped_refs, 1):
        block += (
            f"\nParagraph {i}"
            f"\nid: {r.get('chunk_id') or r.get('id') or ''}"
            f"\ntext: {r.get('text') or ''}"
            f"\nen: {r.get('en') or ''}"
        )
    return block


def _format_ref_block_for_gemini_en2zh(deduped_refs: list[dict[str, Any]]) -> str:
    if not deduped_refs:
        return ""
    block = "\n\n参考语料："
    for i, r in enumerate(deduped_refs, 1):
        block += (
            f"\nParagraph {i}"
            f"\nid: {r.get('chunk_id') or r.get('id') or ''}"
            f"\nen: {r.get('en') or ''}"
            f"\nzh: {r.get('zh') or r.get('text') or ''}"
        )
    return block


def _stats_from_line_refs(
    line_refs: list[dict[str, Any]],
    *,
    additional_pool_line: bool = False,
    retrieval_skipped: bool = False,
    pool_line: bool = False,
    feasts_line: bool = False,
) -> dict[str, Any]:
    pool = sum(1 for r in line_refs if r.get("match_kind") == "pool")
    exact = sum(1 for r in line_refs if r.get("match_kind") == "exact")
    retrieved = sum(1 for r in line_refs if r.get("match_kind") == "retrieved")
    none = sum(1 for r in line_refs if r.get("match_kind") == "none")
    return {
        "pool": pool,
        "exact": exact,
        "retrieved": retrieved,
        "none": none,
        "additional_pool_line": additional_pool_line,
        "retrieval_skipped": retrieval_skipped,
        "pool_line": pool_line,
        "feasts_line": feasts_line,
    }


def _build_line_ref_group(
    line_index: int,
    original_line: str,
    line_refs: list[dict[str, Any]],
    *,
    line_type: str = "reference",
    gemini_translate: str = "",
    additional_pool_line: bool = False,
    retrieval_skipped: bool = False,
    pool_line: bool = False,
    feasts_line: bool = False,
    reference_source_zh: str = "",
    reference_source_en: str = "",
) -> dict[str, Any]:
    deduped = _assign_paragraph_numbers(_dedupe_refs_by_chunk_id(line_refs))
    stats = _stats_from_line_refs(
        line_refs,
        additional_pool_line=additional_pool_line,
        retrieval_skipped=retrieval_skipped,
        pool_line=pool_line,
        feasts_line=feasts_line,
    )
    return {
        "line_index": line_index,
        "original_line": original_line,
        "line_type": line_type,
        "gemini_translate": gemini_translate,
        "deduped_refs": deduped,
        "line_refs": line_refs,
        "stats": stats,
        "reference_source_zh": reference_source_zh,
        "reference_source_en": reference_source_en,
    }


def _gemini_cost_usd(in_tok: int, out_tok: int) -> float:
    return (in_tok * 1.50 + out_tok * 9.0) / 1_000_000


def _build_summary(
    line_ref_groups: list[dict[str, Any]],
    *,
    total_in_tok: int = 0,
    total_out_tok: int = 0,
    append_added: int = 0,
    append_skipped: int = 0,
) -> dict[str, Any]:
    total_lines = len(line_ref_groups)
    pool = exact = retrieved = none = 0
    additional_pool_lines = pool_full_match_lines = feasts_lines = 0
    for g in line_ref_groups:
        st = g.get("stats") or {}
        pool += int(st.get("pool") or 0)
        exact += int(st.get("exact") or 0)
        retrieved += int(st.get("retrieved") or 0)
        none += int(st.get("none") or 0)
        if st.get("additional_pool_line"):
            additional_pool_lines += 1
        if st.get("pool_line"):
            pool_full_match_lines += 1
        if st.get("feasts_line"):
            feasts_lines += 1
    source_translated = sum(
        1 for g in line_ref_groups
        if (g.get("reference_source_en") or "").strip()
    )
    gemini_cost = _gemini_cost_usd(total_in_tok, total_out_tok)
    return {
        "total_lines": total_lines,
        "pool": pool,
        "exact": exact,
        "retrieved": retrieved,
        "none": none,
        "additional_pool_lines": additional_pool_lines,
        "pool_full_match_lines": pool_full_match_lines,
        "feasts_lines": feasts_lines,
        "source_translated": source_translated,
        "additional_pool_appended": append_added,
        "additional_pool_append_skipped": append_skipped,
        "gemini_cost_usd": gemini_cost,
        "total_cost_usd": gemini_cost,
    }


def _gemini_config():
    if gemini_translation_generate_config:
        return gemini_translation_generate_config(GEMINI_TRANSLATION_SYSTEM_INSTRUCTION)
    from google.genai import types

    return types.GenerateContentConfig(system_instruction=GEMINI_TRANSLATION_SYSTEM_INSTRUCTION)


def _call_gemini_sync(
    contents: str,
    retry_count: int = 0,
    model: str | None = None,
    cumulative_usage: dict | None = None,
) -> tuple[str | None, dict[str, int]]:
    if cumulative_usage is None:
        cumulative_usage = {"in_tok": 0, "out_tok": 0}
    use_model = model or GEMINI_MODEL
    if not gemini_client:
        return None, cumulative_usage
    with GEMINI_SEMAPHORE:
        try:
            response = gemini_client.models.generate_content(
                model=use_model,
                contents=contents,
                config=_gemini_config(),
            )
            log_p = f"[enhanced_translate] model={use_model}"
            text = None
            if extract_translatable_text:
                text = extract_translatable_text(response, log_p)
            else:
                rt = getattr(response, "text", None) if response else None
                text = rt.strip() if isinstance(rt, str) and rt.strip() else None
            call_in = call_out = call_think = 0
            meta = getattr(response, "usage_metadata", None)
            if meta:
                call_in = int(getattr(meta, "prompt_token_count", 0) or 0)
                call_out = int(getattr(meta, "candidates_token_count", 0) or 0)
                call_think = int(getattr(meta, "thoughts_token_count", 0) or 0)
            cumulative_usage["in_tok"] += call_in
            cumulative_usage["out_tok"] += call_out + call_think
            logger.info(
                "[enhanced_translate] gemini call: model=%s in_tok=%d out_tok=%d think_tok=%d",
                use_model, call_in, call_out, call_think
            )
            return text, cumulative_usage
        except Exception as e:
            err = str(e)
            retryable = _gemini_error_is_retryable(err)
            if retryable and retry_count == 0:
                time.sleep(2)
                return _call_gemini_sync(
                    contents,
                    retry_count=1,
                    model=use_model,
                    cumulative_usage=cumulative_usage,
                )
            logger.warning("[enhanced_translate] Gemini 失败: %s", e)
    return None, cumulative_usage


def _parse_batch_translations(
    raw: str,
    items: list[tuple[int, str]],
) -> dict[int, str]:
    out: dict[int, str] = {}
    for m in _BATCH_LINE_OUT_RE.finditer(raw or ""):
        idx = int(m.group(1)) - 1
        if 0 <= idx < len(items):
            line_i, _ = items[idx]
            out[line_i] = (m.group(2) or "").strip()
    for pos, (line_i, zh_line) in enumerate(items):
        if line_i not in out:
            out[line_i] = zh_line
    return out


async def _translate_batch(
    items: list[tuple[int, str, list[dict[str, Any]], str]],
) -> tuple[dict[int, str], dict[str, int]]:
    """items: (line_i, zh_line, deduped_refs, prompt_extra)"""
    if not items:
        return {}, {}
    blocks: list[str] = []
    for pos, (line_i, zh_line, deduped_refs, _) in enumerate(items, 1):
        ref_block = _format_ref_block_for_gemini(deduped_refs)
        blocks.append(f"Line {pos}: {zh_line}{ref_block}")

    prompt_extra = items[0][3] if items else ""
    extra = f"\n\n{prompt_extra}" if prompt_extra else ""
    contents = (
        "\n\n".join(blocks)
        + extra
        + "\n\nTranslate each line above to English. Output ONLY in this exact format:\n"
        + "\n".join(f"Line {pos}: {{english translation}}" for pos in range(1, len(items) + 1))
    )

    indexed = [(line_i, zh) for line_i, zh, _, _ in items]
    cumulative_usage: dict[str, int] = {"in_tok": 0, "out_tok": 0}
    text, _ = await asyncio.to_thread(_call_gemini_sync, contents, 0, None, cumulative_usage)
    if not text and GEMINI_TRANSLATION_FALLBACK_MODEL != GEMINI_MODEL:
        text, _ = await asyncio.to_thread(
            _call_gemini_sync, contents, 0, GEMINI_TRANSLATION_FALLBACK_MODEL, cumulative_usage
        )

    if not text:
        return {line_i: zh for line_i, zh in indexed}, cumulative_usage

    parsed = _parse_batch_translations(text, indexed)
    return parsed, cumulative_usage


async def _translate_batch_en2zh(
    items: list[tuple[int, str, list[dict[str, Any]], str]],
) -> tuple[dict[int, str], dict[str, int]]:
    """items: (line_i, en_line, deduped_refs, prompt_extra)"""
    if not items:
        return {}, {}
    blocks: list[str] = []
    for pos, (line_i, en_line, deduped_refs, _) in enumerate(items, 1):
        ref_block = _format_ref_block_for_gemini_en2zh(deduped_refs)
        blocks.append(f"Line {pos}: {en_line}{ref_block}")

    prompt_extra = items[0][3] if items else ""
    extra = f"\n\n{prompt_extra}" if prompt_extra else ""
    contents = (
        "\n\n".join(blocks)
        + extra
        + "\n\nTranslate each line above to Chinese. Output ONLY in this exact format:\n"
        + "\n".join(f"Line {pos}: {{chinese translation}}" for pos in range(1, len(items) + 1))
    )

    indexed = [(line_i, en) for line_i, en, _, _ in items]
    cumulative_usage: dict[str, int] = {"in_tok": 0, "out_tok": 0}
    text, _ = await asyncio.to_thread(_call_gemini_sync, contents, 0, None, cumulative_usage)
    if not text and GEMINI_TRANSLATION_FALLBACK_MODEL != GEMINI_MODEL:
        text, _ = await asyncio.to_thread(
            _call_gemini_sync, contents, 0, GEMINI_TRANSLATION_FALLBACK_MODEL, cumulative_usage
        )

    if not text:
        return {line_i: en for line_i, en in indexed}, cumulative_usage

    parsed = _parse_batch_translations(text, indexed)
    return parsed, cumulative_usage


async def _translate_batch_feasts(
    items: list[tuple[int, str]],
) -> tuple[dict[int, str], dict[str, int]]:
    """items: (line_i, feasts_line) — feasts 索引已提供英文 body，Gemini 仅校对格式。"""
    if not items:
        return {}, {}
    blocks = [f"Line {pos}: {feasts_line}" for pos, (_, feasts_line) in enumerate(items, 1)]
    contents = (
        ENHANCED_TRANSLATE_PROMPT_FEASTS
        + "\n\n"
        + "\n\n".join(blocks)
        + "\n\nProofread each line above. Output ONLY in this exact format:\n"
        + "\n".join(f"Line {pos}: {{corrected english text}}" for pos in range(1, len(items) + 1))
    )

    indexed = [(line_i, feasts_line) for line_i, feasts_line in items]
    cumulative_usage: dict[str, int] = {"in_tok": 0, "out_tok": 0}
    text, _ = await asyncio.to_thread(_call_gemini_sync, contents, 0, None, cumulative_usage)
    if not text and GEMINI_TRANSLATION_FALLBACK_MODEL != GEMINI_MODEL:
        text, _ = await asyncio.to_thread(
            _call_gemini_sync, contents, 0, GEMINI_TRANSLATION_FALLBACK_MODEL, cumulative_usage
        )

    if not text:
        return {line_i: feasts_line for line_i, feasts_line in indexed}, cumulative_usage

    parsed = _parse_batch_translations(text, indexed)
    return parsed, cumulative_usage


def _prep_cached_line(
    line_i: int,
    line: str,
    cached_en: str,
    *,
    line_type: str,
) -> dict[str, Any]:
    line_for_retrieval, reference_source_zh_list = parse_source_from_line(line)
    reference_source_zh = format_source_zh(reference_source_zh_list)
    prefix, body, _ = _strip_scripture_suffix(line_for_retrieval)
    return {
        "line_i": line_i,
        "line": line,
        "line_for_retrieval": line_for_retrieval,
        "body": body,
        "line_type": line_type,
        "line_refs": [],
        "deduped_refs": [],
        "needs_batch": False,
        "line_cached_en": cached_en,
        "pool_line_en": "",
        "feasts_line": "",
        "retrieval_failed": False,
        "reference_source_zh": reference_source_zh,
        "reference_source_zh_list": reference_source_zh_list,
        "reference_source_en": "",
    }


def _empty_retrieval_prep(
    line_i: int,
    line: str,
    body: str,
    line_type: str,
    _src: dict[str, Any],
    *,
    needs_batch: bool,
) -> dict[str, Any]:
    return {
        "line_i": line_i,
        "line": line,
        "body": body,
        "line_type": line_type,
        "line_refs": [],
        "deduped_refs": [],
        "needs_batch": needs_batch,
        "line_cached_en": "",
        "pool_line_en": "",
        "feasts_line": "",
        "retrieval_failed": False,
        **_src,
    }


async def _retrieve_bible_reading_line(
    line_i: int,
    line: str,
    body: str,
    line_type: str,
    _src: dict[str, Any],
) -> dict[str, Any]:
    return _empty_retrieval_prep(
        line_i, line, body, line_type, _src, needs_batch=True
    )


async def _retrieve_title_line(
    line_i: int,
    line: str,
    body: str,
    line_type: str,
    line_for_retrieval: str,
    _src: dict[str, Any],
    ctx: _RetrievalCtx,
) -> dict[str, Any]:
    ref_clause = body.strip() or line_for_retrieval.strip()

    pool_hit = await _pool_lookup_hit(line_for_retrieval, fuzzy=False)
    if pool_hit is not None:
        main_hit = await _enrich_hit_en(dict(pool_hit), ctx)
        main_hit["match_kind"] = "pool"
        main_hit["source_type"] = "main"
        main_hit["clauses"] = []
        line_refs = [_build_ref_entry(line_i, 0, ref_clause, main_hit)]
        deduped_refs = _assign_paragraph_numbers(_dedupe_refs_by_chunk_id(line_refs))
        return {
            "line_i": line_i,
            "line": line,
            "body": body,
            "line_type": line_type,
            "line_refs": line_refs,
            "deduped_refs": deduped_refs,
            "needs_batch": True,
            "line_cached_en": "",
            "pool_line_en": "",
            "feasts_line": "",
            "retrieval_failed": False,
            **_src,
        }

    title_part = _strip_title_prefix(body)
    if title_part:
        norm_title = normalize_zh(title_part)
        if norm_title:
            es_hits = await _pool_recall_hits(title_part, 300)
            if body.strip() and body.strip() != title_part:
                es_hits = _dedupe_hits_by_zh(
                    es_hits + await _pool_recall_hits(body.strip(), 300)
                )
            local_hits = recall_local_pool_hits(title_part, body_prefix=body.strip())
            candidates = _dedupe_hits_by_zh(es_hits + local_hits)
            scored: list[tuple[tuple[int, int], dict[str, Any]]] = []
            for h in candidates:
                hit_zh = _hit_zh_text(h)
                nh = normalize_zh(hit_zh)
                dist = levenshtein_distance(nh, norm_title)
                scored.append(((dist, len(nh)), h))
            scored.sort(key=lambda x: x[0])
            if scored:
                dist = scored[0][0][0]
                ratio = dist / len(norm_title)
                pick_n = 1 if ratio < 0.2 else min(2, len(scored))
                picked = [h for _, h in scored[:pick_n]]
                line_refs: list[dict[str, Any]] = []
                for ci, h in enumerate(picked):
                    enriched = await _enrich_hit_en(dict(h), ctx)
                    enriched["match_kind"] = "retrieved"
                    enriched["source_type"] = "main" if ci == 0 else "clause"
                    enriched["clauses"] = []
                    line_refs.append(_build_ref_entry(line_i, ci, ref_clause, enriched))
                deduped_refs = _assign_paragraph_numbers(_dedupe_refs_by_chunk_id(line_refs))
                return {
                    "line_i": line_i,
                    "line": line,
                    "body": body,
                    "line_type": line_type,
                    "line_refs": line_refs,
                    "deduped_refs": deduped_refs,
                    "needs_batch": True,
                    "line_cached_en": "",
                    "pool_line_en": "",
                    "feasts_line": "",
                    "retrieval_failed": False,
                    **_src,
                }

    return _empty_retrieval_prep(
        line_i, line, body, line_type, _src, needs_batch=True
    )


async def _retrieve_line(
    line_i: int,
    line: str,
    ctx: _RetrievalCtx,
    *,
    line_type: str,
) -> dict[str, Any]:
    line_for_retrieval, reference_source_zh_list = parse_source_from_line(line)
    prefix, body, _ = _strip_scripture_suffix(line_for_retrieval)
    reference_source_zh = format_source_zh(reference_source_zh_list)
    _src = {
        "line_for_retrieval": line_for_retrieval,
        "reference_source_zh": reference_source_zh,
        "reference_source_zh_list": reference_source_zh_list,
        "reference_source_en": "",
    }

    if line_type == "bible-reading":
        return await _retrieve_bible_reading_line(line_i, line, body, line_type, _src)

    if line_type == "title":
        return await _retrieve_title_line(
            line_i, line, body, line_type, line_for_retrieval, _src, ctx
        )

    if line_type == "outline":
        clauses = _split_body(body)
    else:
        clauses = [body] if body.strip() else []

    async def _noop() -> None:
        return None

    async def _noop_list() -> list:
        return []

    async def _cancel_tasks(*tasks: asyncio.Task | None) -> None:
        for t in tasks:
            if t is None or t.done():
                continue
            t.cancel()
            try:
                await t
            except asyncio.CancelledError:
                pass

    if not body.strip() and not clauses:
        return {
            "line_i": line_i,
            "line": line,
            "body": body,
            "line_type": line_type,
            "line_refs": [],
            "deduped_refs": [],
            "needs_batch": False,
            "line_cached_en": "",
            "pool_line_en": "",
            "feasts_line": "",
            "retrieval_failed": False,
            **_src,
        }

    if line_type == "reference":
        if line_for_retrieval.strip():
            pool_en = await _pool_lookup(line_for_retrieval, fuzzy=True)
            if pool_en is not None:
                return {
                    "line_i": line_i,
                    "line": line,
                    "body": body,
                    "line_type": line_type,
                    "line_refs": [],
                    "deduped_refs": [],
                    "needs_batch": False,
                    "line_cached_en": "",
                    "pool_line_en": pool_en,
                    "feasts_line": "",
                    "retrieval_failed": False,
                    **_src,
                }

        main_hit_r: dict[str, Any] | None = None
        skip_clause = False
        main_query = line_for_retrieval.strip()

        # 步骤 2：整行子串匹配（Pool 同款 300 召回，与 BM25 top1 无关）
        recall_hits = await _pool_recall_hits(line_for_retrieval, 300)
        substring_hits = [
            h
            for h in recall_hits
            if main_query and zh_contains(main_query, _hit_zh_text(h))
        ]
        if substring_hits:
            best = min(substring_hits, key=lambda h: len(_hit_zh_text(h)))
            main_hit_r = await _enrich_hit_en(dict(best), ctx)
            main_hit_r["match_kind"] = "exact"
            main_hit_r["source_type"] = "main"
            main_hit_r["clauses"] = []
            skip_clause = True
        else:
            # 步骤 3：BM25 top1 + 分句检索
            whole_hits = await _bm25_hits(line_for_retrieval, ctx.bm25_index, 1)
            if whole_hits:
                main_hit_r = await _enrich_hit_en(dict(whole_hits[0]), ctx)
                main_hit_r["match_kind"] = "retrieved"
                main_hit_r["source_type"] = "main"
                main_hit_r["clauses"] = []

        ref_clauses = _split_reference(body or line_for_retrieval)
        clause_results: list[list[dict[str, Any]]] = []
        if not skip_clause:
            clause_results = list(
                await asyncio.gather(
                    *[_bm25_hits(rc, ctx.bm25_index, 1) for rc in ref_clauses]
                )
            )

        main_dedup_key = _dedup_key(main_hit_r) if main_hit_r else ""
        main_cid = _hit_chunk_id(main_hit_r) if main_hit_r else ""
        main_hit_text = (main_hit_r.get("text") or "").strip() if main_hit_r else ""
        seen_keys: set[str] = set()
        if main_dedup_key:
            seen_keys.add(main_dedup_key)
        if main_cid:
            seen_keys.add(main_cid)

        clause_ref_list: list[dict[str, Any]] = []
        for rc, hits in zip(ref_clauses, clause_results):
            if len(clause_ref_list) >= 2:
                break
            if main_hit_text and zh_contains(rc, main_hit_text):
                continue
            if not hits:
                continue
            h = await _enrich_hit_en(dict(hits[0]), ctx)
            key = _dedup_key(h)
            cid = _hit_chunk_id(h)
            if key and key in seen_keys:
                continue
            if cid and cid in seen_keys:
                continue
            h["match_kind"] = "exact" if zh_contains(rc, (h.get("text") or "")) else "retrieved"
            h["source_type"] = "clause"
            h["clauses"] = [rc]
            if key:
                seen_keys.add(key)
            if cid:
                seen_keys.add(cid)
            clause_ref_list.append(h)

        ref_clause = body.strip() or line_for_retrieval.strip()
        line_refs: list[dict[str, Any]] = []
        if main_hit_r:
            line_refs.append(_build_ref_entry(line_i, 0, ref_clause, main_hit_r))
        for ci, ch in enumerate(clause_ref_list, 1):
            rc = (ch.get("clauses") or [ref_clause])[0]
            entry = _build_ref_entry(line_i, ci, rc, ch)
            entry["clauses"] = ch.get("clauses") or []
            line_refs.append(entry)

        deduped_refs = _assign_paragraph_numbers(_dedupe_refs_by_chunk_id(line_refs))
        retrieval_failed = main_hit_r is None and not clause_ref_list

        return {
            "line_i": line_i,
            "line": line,
            "body": body,
            "line_type": line_type,
            "line_refs": line_refs,
            "deduped_refs": deduped_refs,
            "needs_batch": True,
            "line_cached_en": "",
            "pool_line_en": "",
            "feasts_line": "",
            "retrieval_failed": retrieval_failed,
            **_src,
        }

    pool_task = (
        asyncio.create_task(_pool_lookup(line_for_retrieval))
        if line_for_retrieval.strip()
        else None
    )

    if pool_task is not None:
        pool_en = await pool_task
        if pool_en is not None:
            return {
                "line_i": line_i,
                "line": line,
                "body": body,
                "line_type": line_type,
                "line_refs": [],
                "deduped_refs": [],
                "needs_batch": False,
                "line_cached_en": "",
                "pool_line_en": pool_en,
                "feasts_line": "",
                "retrieval_failed": False,
                **_src,
            }

    if line_type == "outline" and body.strip():
        feasts_exact, other_exact = await _outline_body_pool_exact(body)
        if feasts_exact:
            best = min(feasts_exact, key=lambda h: len(_hit_zh_text(h)))
            feasts_en_body = (best.get("en") or "").strip()
            prefix, _, suffix = _strip_scripture_suffix(line_for_retrieval)
            en_prefix = _translate_prefix(prefix)
            feasts_line = f"{en_prefix}{feasts_en_body}{suffix}"
            feasts_ref = {
                "line_index": line_i,
                "clause_index": 0,
                "zh": body,
                "match_kind": "match_body",
                "match_type": "reference",
                "zh_snippet": body,
                "en_snippet": feasts_en_body,
                "text": body,
                "en": feasts_en_body,
                "chunk_id": _hit_chunk_id(best),
                "id": _hit_chunk_id(best),
                "source": "feasts",
                "ch_source": "feasts",
                "en_source": "",
            }
            deduped_refs = _assign_paragraph_numbers([feasts_ref])
            return {
                "line_i": line_i,
                "line": line,
                "body": body,
                "line_type": line_type,
                "line_refs": [feasts_ref],
                "deduped_refs": deduped_refs,
                "needs_batch": True,
                "line_cached_en": "",
                "pool_line_en": "",
                "feasts_line": feasts_line,
                "retrieval_failed": False,
                **_src,
            }

        if other_exact:
            best = min(other_exact, key=lambda h: len(_hit_zh_text(h)))
            main_hit = await _enrich_hit_en(dict(best), ctx)
            main_hit["match_kind"] = "exact"
            main_hit["source_type"] = "main"
            main_hit["clauses"] = []
            ref_clause = body.strip()
            line_refs = [_build_ref_entry(line_i, 0, ref_clause, main_hit)]
            deduped_refs = _assign_paragraph_numbers(_dedupe_refs_by_chunk_id(line_refs))
            return {
                "line_i": line_i,
                "line": line,
                "body": body,
                "line_type": line_type,
                "line_refs": line_refs,
                "deduped_refs": deduped_refs,
                "needs_batch": True,
                "line_cached_en": "",
                "pool_line_en": "",
                "feasts_line": "",
                "retrieval_failed": False,
                **_src,
            }

    body_bm25_hits, dense_hits = await asyncio.gather(
        _bm25_hits(body, ctx.bm25_index, 40),
        _dense_hits(body, ctx),
    )

    bm25_bucket = _dedupe_hits_by_chunk_id(body_bm25_hits)
    dense_bucket = dense_hits

    all_hits = _dedupe_hits_by_chunk_id(bm25_bucket + dense_bucket)
    if not all_hits:
        feasts_raw = await bm25_search(es_client, body, "feasts", 50)
        if feasts_raw:
            async with _RERANK_SEM:
                feasts_reranked = await rerank(feasts_raw, body.strip(), 1)
            if feasts_reranked:
                bm25_bucket = _dedupe_hits_by_chunk_id(feasts_reranked)
                dense_bucket = []
                all_hits = list(bm25_bucket)
                for h in bm25_bucket:
                    h["match_kind"] = "retrieved"

    if not all_hits:
        return {
            "line_i": line_i,
            "line": line,
            "body": body,
            "line_type": line_type,
            "line_refs": [],
            "deduped_refs": [],
            "needs_batch": False,
            "line_cached_en": "",
            "pool_line_en": "",
            "feasts_line": "",
            "retrieval_failed": True,
            **_src,
        }

    rrf_merged = await rrf_merge(
        bm25_bucket, dense_bucket, k=60, bm25_weight=1.5, dense_weight=1.0
    )
    rerank_query = body.strip()
    async with _RERANK_SEM:
        reranked_main = await rerank(rrf_merged, rerank_query, 1)

    if not reranked_main:
        return {
            "line_i": line_i,
            "line": line,
            "body": body,
            "line_type": line_type,
            "line_refs": [],
            "deduped_refs": [],
            "needs_batch": False,
            "line_cached_en": "",
            "pool_line_en": "",
            "feasts_line": "",
            "retrieval_failed": True,
            **_src,
        }

    main_hit = await _enrich_hit_en(dict(reranked_main[0]), ctx)
    if main_hit.get("match_kind") != "exact":
        main_hit["match_kind"] = main_hit.get("match_kind") or "retrieved"
    main_hit["source_type"] = "main"
    main_hit["clauses"] = []

    main_key = _dedup_key(main_hit)
    main_cid = _hit_chunk_id(main_hit)
    main_hit_text = (main_hit.get("text") or "").strip()
    seen_keys: set[str] = set()
    if main_key:
        seen_keys.add(main_key)
    if main_cid:
        seen_keys.add(main_cid)

    clause_results: list[list[dict[str, Any]]] = []
    if clauses:
        clause_results = list(
            await asyncio.gather(
                *[_bm25_hits(c, ctx.bm25_index, 1) for c in clauses]
            )
        )

    clause_refs: list[dict[str, Any]] = []
    for rc, hits in zip(clauses, clause_results):
        if main_hit_text and zh_contains(rc, main_hit_text):
            continue
        if not hits:
            continue
        h = await _enrich_hit_en(dict(hits[0]), ctx)
        key = _dedup_key(h)
        cid = _hit_chunk_id(h)
        if key and key in seen_keys:
            continue
        if cid and cid in seen_keys:
            continue
        h["match_kind"] = "exact" if zh_contains(rc, (h.get("text") or "")) else "retrieved"
        h["source_type"] = "clause"
        h["clauses"] = [rc]
        if key:
            seen_keys.add(key)
        if cid:
            seen_keys.add(cid)
        clause_refs.append(h)

    ref_clause = body.strip() or line_for_retrieval.strip()
    line_refs = [_build_ref_entry(line_i, 0, ref_clause, main_hit)]

    for ci, ch in enumerate(clause_refs, 1):
        rc = (ch.get("clauses") or [ref_clause])[0]
        entry = _build_ref_entry(line_i, ci, rc, ch)
        entry["clauses"] = ch.get("clauses") or []
        line_refs.append(entry)

    deduped_refs = _assign_paragraph_numbers(_dedupe_refs_by_chunk_id(line_refs))

    return {
        "line_i": line_i,
        "line": line,
        "body": body,
        "line_type": line_type,
        "line_refs": line_refs,
        "deduped_refs": deduped_refs,
        "needs_batch": True,
        "line_cached_en": "",
        "pool_line_en": "",
        "feasts_line": "",
        "retrieval_failed": False,
        **_src,
    }


async def _retrieve_line_en2zh(
    line_i: int,
    line: str,
    ctx: _RetrievalCtx,
    *,
    line_type: str,
) -> dict[str, Any]:
    prefix, body, _ = _strip_scripture_suffix(line)

    if line_type in ("bible-reading", "title"):
        return {
            "line_i": line_i,
            "line": line,
            "body": body,
            "line_type": line_type,
            "line_refs": [],
            "deduped_refs": [],
            "needs_batch": True,
            "line_cached_en": "",
            "pool_line_en": "",
            "retrieval_failed": False,
        }

    if line_type == "outline":
        clauses = _split_body(body)
    else:
        clauses = [body] if body.strip() else []

    if line.strip():
        pool_zh = await _pool_lookup_en2zh(line)
        if pool_zh is not None:
            return {
                "line_i": line_i,
                "line": line,
                "body": body,
                "line_type": line_type,
                "line_refs": [],
                "deduped_refs": [],
                "needs_batch": False,
                "line_cached_en": "",
                "pool_line_en": pool_zh,
                "retrieval_failed": False,
            }

    if not body.strip() and not clauses:
        return {
            "line_i": line_i,
            "line": line,
            "body": body,
            "line_type": line_type,
            "line_refs": [],
            "deduped_refs": [],
            "needs_batch": False,
            "line_cached_en": "",
            "pool_line_en": "",
            "retrieval_failed": False,
        }

    clause_tasks = [_clause_retrieval_en(c, ctx) for c in clauses]
    gather_results = await asyncio.gather(
        _exact_match_en(line, ctx),
        _bm25_hits_en(body, ctx.bm25_index, 40),
        *clause_tasks,
    )
    line_exact = gather_results[0]
    body_bm25 = gather_results[1]
    clause_groups = gather_results[2:]
    clause_hits = [h for group in clause_groups for h in group]

    merged_hits = _dedupe_hits_by_chunk_id(line_exact + body_bm25 + clause_hits)

    if not merged_hits:
        feasts_raw = await _bm25_hits_en(line, "feasts", 50)
        if feasts_raw:
            async with _RERANK_SEM:
                feasts_reranked = await rerank(feasts_raw, body.strip() or line.strip(), 1)
            merged_hits = _dedupe_hits_by_chunk_id(feasts_reranked)
            for h in merged_hits:
                h["match_kind"] = "retrieved"

    if not merged_hits:
        return {
            "line_i": line_i,
            "line": line,
            "body": body,
            "line_type": line_type,
            "line_refs": [],
            "deduped_refs": [],
            "needs_batch": False,
            "line_cached_en": "",
            "pool_line_en": "",
            "retrieval_failed": True,
        }

    enriched = await asyncio.gather(*[_enrich_hit_en(dict(h), ctx) for h in merged_hits])

    rrf_merged = await rrf_merge(list(enriched), [], k=60, bm25_weight=1.0, dense_weight=1.0)
    rerank_query = body.strip() or line.strip()
    async with _RERANK_SEM:
        reranked = await rerank(rrf_merged, rerank_query, 1)

    if not reranked:
        return {
            "line_i": line_i,
            "line": line,
            "body": body,
            "line_type": line_type,
            "line_refs": [],
            "deduped_refs": [],
            "needs_batch": False,
            "line_cached_en": "",
            "pool_line_en": "",
            "retrieval_failed": True,
        }

    top = dict(reranked[0])
    if top.get("match_kind") != "exact":
        top["match_kind"] = "retrieved"

    ref_clause = body.strip() or line.strip()
    line_refs = [_build_ref_entry(line_i, 0, ref_clause, top)]
    deduped_refs = _assign_paragraph_numbers(_dedupe_refs_by_chunk_id(line_refs))

    return {
        "line_i": line_i,
        "line": line,
        "body": body,
        "line_type": line_type,
        "line_refs": line_refs,
        "deduped_refs": deduped_refs,
        "needs_batch": True,
        "line_cached_en": "",
        "pool_line_en": "",
        "retrieval_failed": False,
    }


def _append_source_en(body_en: str, prep: dict[str, Any]) -> str:
    text = (body_en or "").strip()
    source_en = (prep.get("reference_source_en") or "").strip()
    if not text:
        return source_en
    if source_en:
        return f"{text} {source_en}"
    return text


def _source_group_kwargs(prep: dict[str, Any]) -> dict[str, str]:
    return {
        "reference_source_zh": prep.get("reference_source_zh") or "",
        "reference_source_en": prep.get("reference_source_en") or "",
    }


async def _assemble_line(
    prep: dict[str, Any],
    prompt_extra: str,
    translate_by_line: dict[int, str],
) -> tuple[str, dict[str, Any]]:
    line_i = prep["line_i"]
    line = prep["line"]
    src_kw = _source_group_kwargs(prep)

    cached_en = (prep.get("line_cached_en") or "").strip()
    if cached_en:
        out = _append_source_en(cached_en, prep)
        return out, _build_line_ref_group(
            line_i,
            line,
            [],
            line_type=prep["line_type"],
            gemini_translate=out,
            additional_pool_line=True,
            retrieval_skipped=True,
            **src_kw,
        )

    pool_line_en = (prep.get("pool_line_en") or "").strip()
    if pool_line_en:
        out = _append_source_en(pool_line_en, prep)
        return out, _build_line_ref_group(
            line_i,
            line,
            [],
            line_type=prep["line_type"],
            gemini_translate=out,
            pool_line=True,
            **src_kw,
        )

    if not prep["needs_batch"]:
        fallback = (prep.get("line_for_retrieval") or line).strip()
        out = _append_source_en(fallback, prep)
        return out, _build_line_ref_group(
            line_i,
            line,
            prep.get("line_refs") or [],
            line_type=prep["line_type"],
            gemini_translate=out,
            **src_kw,
        )

    translate_line = (prep.get("line_for_retrieval") or line).strip()
    body_en = (translate_by_line.get(line_i) or translate_line).strip()
    body_en = _append_source_en(body_en, prep)
    is_feasts = bool(prep.get("feasts_line"))
    return body_en, _build_line_ref_group(
        line_i,
        line,
        prep.get("line_refs") or [],
        line_type=prep["line_type"],
        gemini_translate=body_en,
        feasts_line=is_feasts,
        **src_kw,
    )


async def enhanced_translate(
    content: str,
    prompt_override: str | None = None,
) -> dict[str, Any]:
    outline = (content or "").strip()
    if not outline:
        return {"result": None, "refs": [], "summary": None, "error": "纲目内容为空", "warnings": []}
    if len(outline) > MAX_CONTENT_CHARS:
        return {
            "result": None,
            "refs": [],
            "summary": None,
            "error": f"纲目过长（最多 {MAX_CONTENT_CHARS} 字）",
            "warnings": [],
        }
    if not gemini_client:
        return {
            "result": None,
            "refs": [],
            "summary": None,
            "error": "英文翻译服务未配置（请设置 GEMINI_API_KEY）",
            "warnings": [],
        }

    if prompt_override is not None:
        prompt_extra = prompt_override.strip()
    else:
        prompt_extra = (_PROMPT_OVERRIDE or ENHANCED_TRANSLATE_PROMPT_SUFFIX).strip()

    lines = [ln for ln in outline.splitlines() if ln.strip()]
    line_types = _precompute_line_types(lines)

    line_cached_en: dict[int, str] = {}
    for i, line in enumerate(lines):
        cached = lookup_line_en(line)
        if cached:
            line_cached_en[i] = cached

    ctx = _RetrievalCtx.create(_INDICES_DENSE)
    if any(i not in line_cached_en for i in range(len(lines))):
        await _probe_es(ctx)

    async def _prep_one(i: int, line: str, lt: str) -> dict[str, Any]:
        if i in line_cached_en:
            return _prep_cached_line(i, line, line_cached_en[i], line_type=lt)
        prep = await _retrieve_line(i, line, ctx, line_type=lt)
        prep["line_cached_en"] = ""
        return prep

    preps = await asyncio.gather(
        *[_prep_one(i, line, line_types[i]) for i, line in enumerate(lines)]
    )

    if any(prep.get("retrieval_failed") for prep in preps):
        return {
            "result": None,
            "refs": [],
            "summary": None,
            "error": "部分纲目行检索失败，无法获取参考语料，请稍后重试。",
            "warnings": [],
        }

    batch_items = [
        (
            prep["line_i"],
            prep.get("line_for_retrieval") or prep["line"],
            prep["deduped_refs"],
            prompt_extra,
        )
        for prep in preps
        if prep["needs_batch"] and not prep.get("line_cached_en") and not prep.get("feasts_line")
    ]

    feasts_items = [
        (prep["line_i"], prep["feasts_line"])
        for prep in preps
        if prep.get("feasts_line")
    ]

    chunks = [batch_items[i : i + 10] for i in range(0, len(batch_items), 10)]
    batch_sem = asyncio.Semaphore(10)

    async def _run_batch_chunk(chunk: list) -> tuple[dict[int, str], dict[str, int]]:
        async with batch_sem:
            return await _translate_batch(chunk)

    batch_outcomes = await asyncio.gather(*[_run_batch_chunk(c) for c in chunks]) if chunks else []
    translate_by_line: dict[int, str] = {}
    total_in_tok = 0
    total_out_tok = 0
    for trans, usage in batch_outcomes:
        translate_by_line.update(trans)
        total_in_tok += usage.get("in_tok", 0)
        total_out_tok += usage.get("out_tok", 0)

    feasts_chunks = [feasts_items[i : i + 10] for i in range(0, len(feasts_items), 10)]

    async def _run_feasts_chunk(chunk: list) -> tuple[dict[int, str], dict[str, int]]:
        async with batch_sem:
            return await _translate_batch_feasts(chunk)

    feasts_outcomes = await asyncio.gather(*[_run_feasts_chunk(c) for c in feasts_chunks]) if feasts_chunks else []
    for trans, usage in feasts_outcomes:
        translate_by_line.update(trans)
        total_in_tok += usage.get("in_tok", 0)
        total_out_tok += usage.get("out_tok", 0)

    from testD.backend.source_translator import bracket_has_star

    source_items = [
        (
            i,
            prep.get("reference_source_zh_list") or [],
            prep.get("line_refs") or [],
            bracket_has_star(prep.get("reference_source_zh") or ""),
        )
        for i, prep in enumerate(preps)
        if prep.get("reference_source_zh_list")
    ]
    source_en_map = await translate_source_zh_batch(source_items)
    for i, prep in enumerate(preps):
        prep["reference_source_en"] = source_en_map.get(i, "")

    results = await asyncio.gather(
        *[
            _assemble_line(prep, prompt_extra, translate_by_line)
            for prep in preps
        ]
    )

    out_lines: list[str] = []
    line_ref_groups: list[dict[str, Any]] = []
    for translated, line_group in results:
        out_lines.append(translated)
        line_ref_groups.append(line_group)

    append_added = append_skipped = 0
    if auto_append_enabled():
        rows = collect_auto_append_rows(line_ref_groups, out_lines)
        append_added, append_skipped = append_records(rows)

    summary = _build_summary(
        line_ref_groups,
        total_in_tok=total_in_tok,
        total_out_tok=total_out_tok,
        append_added=append_added,
        append_skipped=append_skipped,
    )

    return {
        "result": "\n".join(out_lines),
        "refs": line_ref_groups,
        "summary": summary,
        "error": None,
        "warnings": list(dict.fromkeys(ctx.warnings)),
    }


async def enhanced_translate_en2zh(
    content: str,
    prompt_override: str | None = None,
) -> dict[str, Any]:
    outline = (content or "").strip()
    if not outline:
        return {"result": None, "refs": [], "summary": None, "error": "内容为空", "warnings": []}
    if len(outline) > MAX_CONTENT_CHARS:
        return {
            "result": None,
            "refs": [],
            "summary": None,
            "error": f"内容过长（最多 {MAX_CONTENT_CHARS} 字）",
            "warnings": [],
        }
    if not gemini_client:
        return {
            "result": None,
            "refs": [],
            "summary": None,
            "error": "翻译服务未配置（请设置 GEMINI_API_KEY）",
            "warnings": [],
        }

    if prompt_override is not None:
        prompt_extra = prompt_override.strip()
    else:
        prompt_extra = ENHANCED_TRANSLATE_PROMPT_EN2ZH.strip()

    lines = [ln for ln in outline.splitlines() if ln.strip()]
    line_types = _precompute_line_types(lines)

    line_cached_en: dict[int, str] = {}
    for i, line in enumerate(lines):
        cached = lookup_line_en(line)
        if cached:
            line_cached_en[i] = cached

    ctx = _RetrievalCtx.create(_INDICES_DENSE)
    if any(i not in line_cached_en for i in range(len(lines))):
        await _probe_es(ctx)

    async def _prep_one(i: int, line: str, lt: str) -> dict[str, Any]:
        if i in line_cached_en:
            return _prep_cached_line(i, line, line_cached_en[i], line_type=lt)
        prep = await _retrieve_line_en2zh(i, line, ctx, line_type=lt)
        prep["line_cached_en"] = ""
        return prep

    preps = await asyncio.gather(
        *[_prep_one(i, line, line_types[i]) for i, line in enumerate(lines)]
    )

    if any(prep.get("retrieval_failed") for prep in preps):
        return {
            "result": None,
            "refs": [],
            "summary": None,
            "error": "部分行检索失败，无法获取参考语料，请稍后重试。",
            "warnings": [],
        }

    batch_items = [
        (prep["line_i"], prep["line"], prep["deduped_refs"], prompt_extra)
        for prep in preps
        if prep["needs_batch"] and not prep.get("line_cached_en")
    ]

    chunks = [batch_items[i : i + 10] for i in range(0, len(batch_items), 10)]
    batch_sem = asyncio.Semaphore(10)

    async def _run_batch_chunk(chunk: list) -> tuple[dict[int, str], dict[str, int]]:
        async with batch_sem:
            return await _translate_batch_en2zh(chunk)

    batch_outcomes = await asyncio.gather(*[_run_batch_chunk(c) for c in chunks]) if chunks else []
    translate_by_line: dict[int, str] = {}
    total_in_tok = 0
    total_out_tok = 0
    for trans, usage in batch_outcomes:
        translate_by_line.update(trans)
        total_in_tok += usage.get("in_tok", 0)
        total_out_tok += usage.get("out_tok", 0)

    results = await asyncio.gather(
        *[_assemble_line(prep, prompt_extra, translate_by_line) for prep in preps]
    )

    out_lines: list[str] = []
    line_ref_groups: list[dict[str, Any]] = []
    for translated, line_group in results:
        out_lines.append(translated)
        line_ref_groups.append(line_group)

    append_added = append_skipped = 0
    if auto_append_enabled():
        rows = collect_auto_append_rows(line_ref_groups, out_lines)
        append_added, append_skipped = append_records(rows)

    summary = _build_summary(
        line_ref_groups,
        total_in_tok=total_in_tok,
        total_out_tok=total_out_tok,
        append_added=append_added,
        append_skipped=append_skipped,
    )

    return {
        "result": "\n".join(out_lines),
        "refs": line_ref_groups,
        "summary": summary,
        "error": None,
        "warnings": list(dict.fromkeys(ctx.warnings)),
    }
