# -*- coding: utf-8 -*-
"""
增强式翻译：逐行解析纲目 → 分句检索参考 → Gemini 中翻英。
业务代码位于 testD/，复用 back_mic 的 ES / 检索 / Gemini。
"""
from __future__ import annotations

import asyncio
import logging
import os
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
from ai_search.gemini_translation_instruction import GEMINI_TRANSLATION_SYSTEM_INSTRUCTION
from ai_search.gemini_response_utils import (
    extract_translatable_text,
    gemini_translation_generate_config,
)

logger = logging.getLogger("testD.enhanced_translate")

# 增强式翻译仅检索以下 6 个索引（不含 map_note / pano / dictionary）
_INDICES_BASE = ",".join([
    "kg-rag_cwwl",
    "kg-rag_life",
    "kg-rag_cwwn",
    "kg-rag_others",
    "kg-rag_7feasts",
    "kg-rag_bib",
])

MAX_CONTENT_CHARS = 100_000

# 增强式翻译附加说明（拼在每条翻译 user 内容末尾）；API update_prompt 可写入 _PROMPT_OVERRIDE 覆盖
ENHANCED_TRANSLATE_PROMPT_SUFFIX = """【语料使用规则】
1. 标记为 [直接引用] 的语料：对应片段必须照搬 en 字段原句，不得任何改写
2. 标记为 [参考翻译] 的语料：必须尽量保留 en 字段的完整句式结构，只有在语义与当前片段有出入时才做最小幅度调整，目标是「调整后的句子」而不是「重新翻译的句子」
3. 若有多个语料段落，按片段顺序对应使用，将各片段译文拼接成完整的一行输出

【序号格式规则】
4. 序号转换规则如下，序号后不缩进直接接英文内容：
   壹 → I.　　贰 → II.　　叁 → III.　　肆 → IV.　　伍 → V.　　陆 → VI.　　柒 → VII.　　捌 → VIII.
   一 → A.　　二 → B.　　三 → C.　　四 → D.　　五 → E.　　六 → F.
   1 → 1.　　2 → 2.　　3 → 3.
   a → a.　　b → b.　　c → c.
   (一) → 1)　　(二) → 2)　　(三) → 3)
5. 序号必须原样保留并放在译文最前面，不可省略

【术语与输出规则】
6. 严格使用 System instructions 中的专用术语表
7. 纲目标题末尾的读经标注保持缩写格式，例如：—约三16： → —John 3:16:
8. 正文中出现的经文引用须翻译为标准英文缩写格式，例如：罗马书一章一节 → Rom. 1:1
9. 不要缩进，直接输出译文
10. 只输出翻译结果，不要输出任何解释、分析或备注"""

# 经 POST /enhanced_translate/update_prompt 写入；非空时优先于 ENHANCED_TRANSLATE_PROMPT_SUFFIX
_PROMPT_OVERRIDE: str = ""

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


def get_prompt_override() -> str:
    return _PROMPT_OVERRIDE


def set_prompt_override(prompt: str) -> None:
    global _PROMPT_OVERRIDE
    _PROMPT_OVERRIDE = (prompt or "").strip()


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
    """返回 (prefix, body, suffix)。suffix 为行末读经标注（—约三16： 等）。"""
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
    """
    将正文按中文分号拆成子句。
    - 含；的行：每段独立检索/翻译，译文用英文分号连接。
    - 无分号：整段作为一句。
    - 空正文（仅经文后缀行）：返回空列表，该行只保留编号与读经后缀。
    """
    body = (body or "").strip()
    if not body:
        return []
    if "；" in body:
        parts = [p.strip() for p in body.split("；")]
        return [p for p in parts if p]
    return [body]


@dataclass
class _RetrievalCtx:
    """单次 enhanced_translate 请求的检索状态，避免 ES 503 时逐子句重试刷屏。"""

    index: str
    es_enabled: bool = True
    dense_enabled: bool = True
    warnings: list[str] = field(default_factory=list)
    _es_down_logged: bool = False

    @classmethod
    def create(cls, index: str) -> "_RetrievalCtx":
        ctx = cls(index=index)
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
                "Elasticsearch 检索不可用，已降级为无参考语料翻译（请检查 ES 是否启动、kg-rag_* 索引是否打开）"
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
    """请求开始时探测 ES，失败则整单跳过检索。"""
    first = (ctx.index.split(",")[0] or "").strip()
    if not first:
        ctx.mark_es_down("索引名为空")
        return
    try:
        await asyncio.to_thread(
            es_client.search,
            index=first,
            body={"size": 0, "query": {"match_all": {}}},
            request_timeout=5,
        )
    except Exception as e:
        ctx.mark_es_down(str(e))


def _translate_prefix(prefix: str) -> str:
    if not prefix:
        return ""
    core = prefix.rstrip("\t　 ")
    mapped = _PREFIX_TO_EN.get(core.strip())
    if mapped:
        sep = "\t" if "\t" in prefix else ("　" if "　" in prefix else " ")
        return mapped + sep
    return prefix


async def _exact_match(
    clause: str, ctx: _RetrievalCtx
) -> dict[str, Any] | None:
    """ES match_phrase 精确匹配，clause 须出现在 chunk text 中。"""
    if not ctx.es_enabled or not clause or not clause.strip():
        return None
    body = {
        "query": {"match_phrase": {"text": {"query": clause}}},
        "size": 3,
        "_source": [
            "chunk_id",
            "text",
            "en",
            "book_title",
            "source_zh",
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
        return None
    for hit in (resp.get("hits") or {}).get("hits") or []:
        src = (hit.get("_source") or {}).copy()
        text = (src.get("text") or "").strip()
        if clause in text:
            src["score"] = hit.get("_score") or 0.0
            src["chunk_id"] = src.get("chunk_id") or hit.get("_id", "")
            src["_index"] = hit.get("_index") or ""
            src["match_kind"] = "exact"
            return src
    return None


async def _retrieve_top1(clause: str, ctx: _RetrievalCtx) -> dict[str, Any] | None:
    if not ctx.es_enabled:
        return None
    bm25_results = await bm25_search(es_client, clause, ctx.index, 5)
    dense_results: list[dict[str, Any]] = []
    if ctx.dense_enabled:
        dense_results = await dense_search(es_client, clause, ctx.index, 20, 100)
    merged = await rrf_merge(bm25_results, dense_results, k=60, bm25_weight=1.0, dense_weight=1.0)
    reranked = await rerank(merged, clause, 3)
    if not reranked:
        return None
    top = dict(reranked[0])
    top["match_kind"] = "retrieved"
    return top


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
            _source=["en", "text", "source_zh", "book_title"],
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
    source_zh = (hit.get("source_zh") or "").strip()
    if not source_zh:
        return (hit.get("book_title") or "").strip()
    s = re.sub(
        r"，第[零一二三四五六七八九十百千\d]+[段节](?=[）)]*$)",
        "",
        source_zh,
    ).strip()
    while len(s) >= 2 and (
        (s[0] == "（" and s[-1] == "）") or (s[0] == "(" and s[-1] == ")")
    ):
        s = s[1:-1]
    return s.strip()


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
    if clause in text:
        match_kind = "exact"
        zh_snippet = clause
    elif text or chunk_id:
        match_kind = "retrieved"
        zh_snippet = text[:200] + ("…" if len(text) > 200 else "") if text else clause
    else:
        match_kind = "none"
        zh_snippet = ""
    match_type = (
        "direct" if match_kind == "exact" else ("reference" if match_kind == "retrieved" else "none")
    )
    source = _extract_source(hit)
    return {
        "line_index": line_index,
        "clause_index": clause_index,
        "zh": clause,
        "match_kind": match_kind,
        "match_type": match_type,
        "zh_snippet": zh_snippet,
        "en_snippet": en,
        "text": text,
        "en": en,
        "chunk_id": chunk_id,
        "id": chunk_id,
        "source": source,
        "ch_source": source,
        "en_source": "",
    }


def _dedupe_refs_by_chunk_id(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 chunk_id 去重，保留第一次出现。"""
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


def _build_line_ref_group(
    line_index: int,
    original_line: str,
    line_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    deduped = _assign_paragraph_numbers(_dedupe_refs_by_chunk_id(line_refs))
    return {
        "line_index": line_index,
        "original_line": original_line,
        "deduped_refs": deduped,
        "line_refs": line_refs,
    }


def _gemini_config():
    if gemini_translation_generate_config:
        return gemini_translation_generate_config(GEMINI_TRANSLATION_SYSTEM_INSTRUCTION)
    from google.genai import types

    return types.GenerateContentConfig(system_instruction=GEMINI_TRANSLATION_SYSTEM_INSTRUCTION)


def _call_gemini_sync(contents: str, retry_count: int = 0, model: str | None = None) -> str | None:
    use_model = model or GEMINI_MODEL
    if not gemini_client:
        return None
    with GEMINI_SEMAPHORE:
        try:
            response = gemini_client.models.generate_content(
                model=use_model,
                contents=contents,
                config=_gemini_config(),
            )
            log_p = f"[enhanced_translate] model={use_model}"
            if extract_translatable_text:
                return extract_translatable_text(response, log_p)
            rt = getattr(response, "text", None) if response else None
            return rt.strip() if isinstance(rt, str) and rt.strip() else None
        except Exception as e:
            err = str(e)
            retryable = _gemini_error_is_retryable(err)
            if retryable and retry_count == 0:
                time.sleep(2)
                return _call_gemini_sync(contents, retry_count=1, model=use_model)
            logger.warning("[enhanced_translate] Gemini 失败: %s", e)
    return None


async def _translate_one_line(
    clause: str,
    ref: dict[str, Any],
    prompt_extra: str,
) -> str:
    ref_block = ""
    if ref.get("match_kind") == "exact" and ref.get("zh_snippet"):
        ref_block = (
            f"\n\n[Direct quote from ministry text — green reference]\n"
            f"Chinese: {ref['zh_snippet']}\n"
        )
        if ref.get("en_snippet"):
            ref_block += f"English: {ref['en_snippet']}\n"
    elif ref.get("match_kind") == "retrieved" and ref.get("en_snippet"):
        ref_block = (
            f"\n\n[Reference translation from corpus — blue reference]\n"
            f"English: {ref['en_snippet']}\n"
            f"Source: {ref.get('source') or ''}\n"
        )
    extra = f"\n\n{prompt_extra}" if prompt_extra else ""
    contents = (
        f"Translate ONLY the following Chinese outline clause to English. "
        f"Use terminology from system instructions. Output nothing but the English clause.\n\n"
        f"Clause: {clause}"
        f"{ref_block}"
        f"{extra}"
        f"\n\n{OUTLINE_TRANSLATE_PROMPT_ZH2EN}"
    )
    text = await asyncio.to_thread(_call_gemini_sync, contents, 0, None)
    if text:
        return text.strip()
    if GEMINI_TRANSLATION_FALLBACK_MODEL != GEMINI_MODEL:
        text = await asyncio.to_thread(
            _call_gemini_sync, contents, 0, GEMINI_TRANSLATION_FALLBACK_MODEL
        )
        if text:
            return text.strip()
    return clause


async def _translate_line(
    original_line: str,
    deduped_refs: list[dict[str, Any]],
    prompt_extra: str,
) -> str:
    ref_block = _format_ref_block_for_gemini(deduped_refs)
    extra = f"\n\n{prompt_extra}" if prompt_extra else ""
    contents = (
        f"原始纲目行：{original_line}"
        f"{ref_block}"
        f"{extra}"
        f"\n\n{OUTLINE_TRANSLATE_PROMPT_ZH2EN}"
    )
    text = await asyncio.to_thread(_call_gemini_sync, contents, 0, None)
    if text:
        return text.strip()
    if GEMINI_TRANSLATION_FALLBACK_MODEL != GEMINI_MODEL:
        text = await asyncio.to_thread(
            _call_gemini_sync, contents, 0, GEMINI_TRANSLATION_FALLBACK_MODEL
        )
        if text:
            return text.strip()
    return original_line


async def _translate_suffix(suffix: str, prompt_extra: str) -> str:
    if not suffix.strip():
        return suffix
    contents = (
        f"Translate ONLY this Chinese scripture suffix to English abbreviation format "
        f"(e.g. —约三16： → —John 3:16:). Output nothing else.\n\n{suffix}"
        f"\n\n{OUTLINE_TRANSLATE_PROMPT_ZH2EN}{prompt_extra}"
    )
    text = await asyncio.to_thread(_call_gemini_sync, contents, 0, None)
    return (text or suffix).strip()


async def _process_line(
    line_i: int,
    line: str,
    ctx: _RetrievalCtx,
    prompt_extra: str,
) -> tuple[str, dict[str, Any]]:
    """处理单行：分号分子句 → 逐子句检索 → 去重语料 → 一次 Gemini。返回 (译文行, 行级 ref 组)。"""
    prefix, body, suffix = _strip_scripture_suffix(line)
    clauses = _split_body(body)
    en_prefix = _translate_prefix(prefix)

    if not clauses:
        en_suffix = await _translate_suffix(suffix, prompt_extra) if suffix else ""
        translated = en_prefix + en_suffix
        return translated, _build_line_ref_group(line_i, line, [])

    line_refs: list[dict[str, Any]] = []
    for clause_i, clause in enumerate(clauses):
        hit = await _exact_match(clause, ctx)
        if not hit:
            hit = await _retrieve_top1(clause, ctx)
        if hit:
            hit = await _enrich_hit_en(hit, ctx)
        ref = _build_ref_entry(line_i, clause_i, clause, hit)
        line_refs.append(ref)

    line_group = _build_line_ref_group(line_i, line, line_refs)
    deduped_refs = line_group["deduped_refs"]
    en_line = await _translate_line(line, deduped_refs, prompt_extra)
    en_suffix = await _translate_suffix(suffix, prompt_extra) if suffix else ""
    return en_line + en_suffix, line_group


async def enhanced_translate(
    content: str,
    prompt_override: str | None = None,
) -> dict[str, Any]:
    outline = (content or "").strip()
    if not outline:
        return {"result": None, "refs": [], "error": "纲目内容为空", "warnings": []}
    if len(outline) > MAX_CONTENT_CHARS:
        return {
            "result": None,
            "refs": [],
            "error": f"纲目过长（最多 {MAX_CONTENT_CHARS} 字）",
            "warnings": [],
        }
    if not gemini_client:
        return {
            "result": None,
            "refs": [],
            "error": "英文翻译服务未配置（请设置 GEMINI_API_KEY）",
            "warnings": [],
        }

    if prompt_override is not None:
        prompt_extra = prompt_override.strip()
    else:
        prompt_extra = (_PROMPT_OVERRIDE or ENHANCED_TRANSLATE_PROMPT_SUFFIX).strip()
    ctx = _RetrievalCtx.create(_INDICES_BASE)
    await _probe_es(ctx)
    lines = [ln for ln in outline.splitlines() if ln.strip()]

    results = await asyncio.gather(
        *[
            _process_line(i, line, ctx, prompt_extra)
            for i, line in enumerate(lines)
        ]
    )
    out_lines: list[str] = []
    line_ref_groups: list[dict[str, Any]] = []
    for translated, line_group in results:
        out_lines.append(translated)
        line_ref_groups.append(line_group)

    return {
        "result": "\n".join(out_lines),
        "refs": line_ref_groups,
        "error": None,
        "warnings": list(dict.fromkeys(ctx.warnings)),
    }
