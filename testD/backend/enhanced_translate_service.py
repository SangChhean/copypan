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

from embedding_adapter import OPENROUTER_API_KEY
from kg_rag.retrieval import bm25_search, dense_search, rrf_merge, rerank
from es_config import es as es_client
from ai_search.ai_service import (
    GEMINI_SEMAPHORE,
    GEMINI_MODEL,
    GEMINI_TRANSLATION_FALLBACK_MODEL,
    OUTLINE_TRANSLATE_PROMPT_ZH2EN,
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
    lookup_line_en,
    normalize_zh,
)
from testD.backend.enhanced_translate_prompts import ENHANCED_TRANSLATE_PROMPT_SUFFIX

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
_POOL_KEYWORD_MAX_LEN = 10

_PROMPT_OVERRIDE: str = ""
_RERANK_SEM = asyncio.Semaphore(10)

_BATCH_LINE_OUT_RE = re.compile(r"^Line\s+(\d+)\s*:\s*(.*)$", re.MULTILINE)

_MINISTERIALIZE_PREFIX_RE = re.compile(
    r"^[壹貳贰參叄叁参肆伍陸陆柒捌玖拾一二三四五六七八九十\da-z（）()]+[\t　]"
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
_SCRIPTURE_REF_RE = re.compile(
    rf"(—{_BOOK_PAT}{_CHAP_PAT}(?:[,，；;]{_REF_UNIT})*[：:。]?\s*)$"
)
_PURE_VERSE_RE = re.compile(r"(—[\d～~\-至、\s\d]+节[。：:]?\s*)$")

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


def get_prompt_override() -> str:
    return _PROMPT_OVERRIDE


def set_prompt_override(prompt: str) -> None:
    global _PROMPT_OVERRIDE
    _PROMPT_OVERRIDE = (prompt or "").strip()


def _normalize_pool_text(s: str) -> str:
    return normalize_zh(s)


def _find_scripture_suffix(rest: str) -> tuple[str, str]:
    matches = list(_SCRIPTURE_REF_RE.finditer(rest))
    if matches:
        m = matches[-1]
        return rest[: m.start()], m.group(0)
    m = _PURE_VERSE_RE.search(rest)
    if m:
        return rest[: m.start()], m.group(0)
    return rest, ""


def _strip_scripture_suffix(line: str) -> tuple[str, str, str]:
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


def _detect_line_type(body: str, prefix: str = "") -> str:
    if (prefix or "").strip():
        return "outline"
    s = (body or "").lstrip()
    if not s:
        return "reference"
    if _OUTLINE_HEAD_RE.match(s):
        return "outline"
    return "reference"


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
    first = (ctx.index.split(",")[0] or "").strip()
    if not first:
        ctx.mark_es_down("索引名为空")
        return
    max_attempts = 3
    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            await asyncio.to_thread(
                es_client.search,
                index=first,
                body={"size": 0, "query": {"match_all": {}}},
                request_timeout=5,
            )
            return
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


async def _pool_lookup_keyword(clause: str) -> str | None:
    body = {
        "query": {"match_phrase": {"zh": {"query": clause}}},
        "size": 3,
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
        logger.warning("[enhanced_translate] pool keyword 失败: %s", e)
        return None
    norm_clause = _normalize_pool_text(clause)
    for hit in (resp.get("hits") or {}).get("hits") or []:
        src = hit.get("_source") or {}
        hit_zh = (src.get("zh") or src.get("text") or "").strip()
        if norm_clause == _normalize_pool_text(hit_zh):
            en = (src.get("en") or "").strip()
            if en:
                return en
    return None


async def _pool_lookup_bm25_punct(clause: str) -> str | None:
    body = {
        "query": {"match_phrase": {"zh": {"query": clause}}},
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
        logger.warning("[enhanced_translate] pool bm25 失败: %s", e)
        return None
    hits = (resp.get("hits") or {}).get("hits") or []
    norm_clause = _normalize_pool_text(clause)
    for hit in hits:
        src = hit.get("_source") or {}
        hit_zh = (src.get("zh") or src.get("text") or "").strip()
        if _normalize_pool_text(hit_zh) == norm_clause:
            en = (src.get("en") or "").strip()
            if en:
                return en
    return None


async def _pool_lookup(clause: str) -> str | None:
    clause = (clause or "").strip()
    if not clause:
        return None
    if len(clause) <= _POOL_KEYWORD_MAX_LEN:
        return await _pool_lookup_keyword(clause)
    return await _pool_lookup_bm25_punct(clause)


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
        if normalize_zh(clause) in normalize_zh(text):
            src["score"] = hit.get("_score") or 0.0
            src["chunk_id"] = src.get("chunk_id") or hit.get("_id", "")
            src["_index"] = hit.get("_index") or ""
            src["match_kind"] = "exact"
            out.append(src)
    return out


def _hit_chunk_id(hit: dict[str, Any]) -> str:
    return (hit.get("chunk_id") or hit.get("_id") or "").strip()


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


async def _bm25_hits(query: str, index: str, top_k: int = 40) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    raw = await bm25_search(es_client, q, index, top_k)
    return _filter_en_hits(raw)


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
    return (
        (hit.get("source_zh") or "").strip()
        or (hit.get("book_title") or "").strip()
        or (hit.get("source") or "").strip()
        or (hit.get("title") or "").strip()
    )


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
        }
    text = (hit.get("text") or "").strip()
    en = (hit.get("en") or "").strip()
    chunk_id = (hit.get("chunk_id") or hit.get("_id") or "").strip()
    mk = hit.get("match_kind")
    if mk == "pool":
        match_kind = "pool"
    elif clause in text:
        match_kind = "exact"
        zh_snippet = clause
    elif text or chunk_id:
        match_kind = "retrieved"
        zh_snippet = text[:200] + ("…" if len(text) > 200 else "") if text else clause
    else:
        match_kind = "none"
        zh_snippet = ""
    if mk == "pool":
        zh_snippet = clause
    match_type = (
        "direct"
        if match_kind == "exact"
        else ("reference" if match_kind in ("retrieved", "pool") else "none")
    )
    source = _extract_source(hit)
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
        "en_source": (hit.get("source_en") or "").strip(),
    }


def _dedupe_refs_by_chunk_id(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for r in refs:
        cid = (r.get("chunk_id") or r.get("id") or "").strip()
        if cid and cid not in seen:
            seen.add(cid)
            deduped.append(r)
        elif not cid:
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
        kind = r.get("match_kind", "retrieved")
        label = "直接引用" if kind == "exact" else "参考翻译"
        block += (
            f"\nParagraph {i} [{label}]"
            f"\nid: {r.get('chunk_id') or r.get('id') or ''}"
            f"\ntext: {r.get('text') or ''}"
            f"\nen: {r.get('en') or ''}"
        )
    return block


def _stats_from_line_refs(
    line_refs: list[dict[str, Any]],
    *,
    additional_pool_line: bool = False,
    retrieval_skipped: bool = False,
    pool_line: bool = False,
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
) -> dict[str, Any]:
    deduped = _assign_paragraph_numbers(_dedupe_refs_by_chunk_id(line_refs))
    stats = _stats_from_line_refs(
        line_refs,
        additional_pool_line=additional_pool_line,
        retrieval_skipped=retrieval_skipped,
        pool_line=pool_line,
    )
    return {
        "line_index": line_index,
        "original_line": original_line,
        "line_type": line_type,
        "gemini_translate": gemini_translate,
        "deduped_refs": deduped,
        "line_refs": line_refs,
        "stats": stats,
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
    additional_pool_lines = pool_full_match_lines = 0
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
    gemini_cost = _gemini_cost_usd(total_in_tok, total_out_tok)
    return {
        "total_lines": total_lines,
        "pool": pool,
        "exact": exact,
        "retrieved": retrieved,
        "none": none,
        "additional_pool_lines": additional_pool_lines,
        "pool_full_match_lines": pool_full_match_lines,
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
            call_in = call_out = 0
            meta = getattr(response, "usage_metadata", None)
            if meta:
                call_in = int(getattr(meta, "prompt_token_count", 0) or 0)
                call_out = int(getattr(meta, "candidates_token_count", 0) or 0)
            cumulative_usage["in_tok"] += call_in
            cumulative_usage["out_tok"] += call_out
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
        + "\n\n"
        + OUTLINE_TRANSLATE_PROMPT_ZH2EN
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


def _prep_cached_line(line_i: int, line: str, cached_en: str) -> dict[str, Any]:
    prefix, body, suffix = _strip_scripture_suffix(line)
    return {
        "line_i": line_i,
        "line": line,
        "body": body,
        "suffix": suffix,
        "en_prefix": _translate_prefix(prefix),
        "line_type": _detect_line_type(body, prefix),
        "line_refs": [],
        "deduped_refs": [],
        "needs_batch": False,
        "line_cached_en": cached_en,
        "pool_line_en": "",
        "retrieval_failed": False,
    }


async def _retrieve_line(
    line_i: int,
    line: str,
    ctx: _RetrievalCtx,
) -> dict[str, Any]:
    prefix, body, suffix = _strip_scripture_suffix(line)
    en_prefix = _translate_prefix(prefix)
    line_type = _detect_line_type(body, prefix)

    if line_type == "outline":
        clauses = _split_body(body)
    else:
        clauses = [body] if body.strip() else []

    if line.strip():
        pool_en = await _pool_lookup(line)
        if pool_en is not None:
            return {
                "line_i": line_i,
                "line": line,
                "body": body,
                "suffix": suffix,
                "en_prefix": en_prefix,
                "line_type": line_type,
                "line_refs": [],
                "deduped_refs": [],
                "needs_batch": False,
                "line_cached_en": "",
                "pool_line_en": pool_en,
                "retrieval_failed": False,
            }

    if not body.strip() and not clauses:
        return {
            "line_i": line_i,
            "line": line,
            "body": body,
            "suffix": suffix,
            "en_prefix": en_prefix,
            "line_type": line_type,
            "line_refs": [],
            "deduped_refs": [],
            "needs_batch": False,
            "line_cached_en": "",
            "pool_line_en": "",
            "retrieval_failed": False,
        }

    clause_tasks = [_clause_retrieval(c, ctx) for c in clauses]
    line_exact, body_bm25, dense_hits, *clause_groups = await asyncio.gather(
        _exact_match(line, ctx),
        _bm25_hits(body, ctx.bm25_index, 40),
        _dense_hits(line, ctx),
        *clause_tasks,
    )
    clause_hits = [h for group in clause_groups for h in group]

    merged_hits = _dedupe_hits_by_chunk_id(line_exact + body_bm25 + clause_hits + dense_hits)

    if not merged_hits:
        feasts_raw = await bm25_search(es_client, line, "feasts", 50)
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
            "suffix": suffix,
            "en_prefix": en_prefix,
            "line_type": line_type,
            "line_refs": [],
            "deduped_refs": [],
            "needs_batch": False,
            "line_cached_en": "",
            "pool_line_en": "",
            "retrieval_failed": True,
        }

    enriched = await asyncio.gather(*[_enrich_hit_en(dict(h), ctx) for h in merged_hits])

    dense_ids = {_hit_chunk_id(h) for h in dense_hits if _hit_chunk_id(h)}
    bm25_bucket: list[dict[str, Any]] = []
    dense_bucket: list[dict[str, Any]] = []
    for h in enriched:
        cid = _hit_chunk_id(h)
        if cid and cid in dense_ids:
            dense_bucket.append(h)
        else:
            bm25_bucket.append(h)

    rrf_merged = await rrf_merge(bm25_bucket, dense_bucket, k=60, bm25_weight=1.0, dense_weight=1.0)
    rerank_query = body.strip() or line.strip()
    async with _RERANK_SEM:
        reranked = await rerank(rrf_merged, rerank_query, 1)

    if not reranked:
        return {
            "line_i": line_i,
            "line": line,
            "body": body,
            "suffix": suffix,
            "en_prefix": en_prefix,
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
        "suffix": suffix,
        "en_prefix": en_prefix,
        "line_type": line_type,
        "line_refs": line_refs,
        "deduped_refs": deduped_refs,
        "needs_batch": True,
        "line_cached_en": "",
        "pool_line_en": "",
        "retrieval_failed": False,
    }


async def _assemble_line(
    prep: dict[str, Any],
    prompt_extra: str,
    translate_by_line: dict[int, str],
) -> tuple[str, dict[str, Any]]:
    line_i = prep["line_i"]
    line = prep["line"]

    cached_en = (prep.get("line_cached_en") or "").strip()
    if cached_en:
        return cached_en, _build_line_ref_group(
            line_i,
            line,
            [],
            line_type=prep["line_type"],
            gemini_translate=cached_en,
            additional_pool_line=True,
            retrieval_skipped=True,
        )

    pool_line_en = (prep.get("pool_line_en") or "").strip()
    if pool_line_en:
        return pool_line_en, _build_line_ref_group(
            line_i,
            line,
            [],
            line_type=prep["line_type"],
            gemini_translate=pool_line_en,
            pool_line=True,
        )

    if not prep["needs_batch"]:
        translated = (prep.get("en_prefix") or "").strip()
        return translated, _build_line_ref_group(
            line_i,
            line,
            prep.get("line_refs") or [],
            line_type=prep["line_type"],
            gemini_translate="",
        )

    body_en = (translate_by_line.get(line_i) or line).strip()
    return body_en, _build_line_ref_group(
        line_i,
        line,
        prep.get("line_refs") or [],
        line_type=prep["line_type"],
        gemini_translate=body_en,
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

    line_cached_en: dict[int, str] = {}
    for i, line in enumerate(lines):
        cached = lookup_line_en(line)
        if cached:
            line_cached_en[i] = cached

    ctx = _RetrievalCtx.create(_INDICES_DENSE)
    if any(i not in line_cached_en for i in range(len(lines))):
        await _probe_es(ctx)

    async def _prep_one(i: int, line: str) -> dict[str, Any]:
        if i in line_cached_en:
            return _prep_cached_line(i, line, line_cached_en[i])
        prep = await _retrieve_line(i, line, ctx)
        prep["line_cached_en"] = ""
        return prep

    preps = await asyncio.gather(*[_prep_one(i, line) for i, line in enumerate(lines)])

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
            prep["line"],
            prep["deduped_refs"],
            prompt_extra,
        )
        for prep in preps
        if prep["needs_batch"] and not prep.get("line_cached_en")
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
