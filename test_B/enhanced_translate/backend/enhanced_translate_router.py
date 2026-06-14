# -*- coding: utf-8 -*-
import asyncio
import os
import re

from elasticsearch import Elasticsearch
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from gemini_translation_instruction import GEMINI_TRANSLATION_SYSTEM_INSTRUCTION
from prompts import TRANSLATE_RULES
import pool
from retrieval import bm25_search, dense_search, rerank, rrf_merge

router = APIRouter(prefix="/api/testb/enhanced-translate")

INDICES = ",".join([
    "kg-rag_life", "kg-rag_cwwl", "kg-rag_cwwn",
    "kg-rag_others", "kg-rag_bib", "kg-rag_map_note",
    "kg-rag_7feasts",
])

GEMINI_MODEL = "gemini-2.5-flash"
PRICE_IN, PRICE_OUT = 0.30, 2.50
BATCH_SIZE = 10
MAX_LINES = 200

ES_HOST = os.getenv("ES_HOST", "localhost")
ES_PORT = os.getenv("ES_PORT", "9200")
ES_USERNAME = os.getenv("ES_USERNAME", "elastic")
ES_PASSWORD = os.getenv("ES_PASSWORD", "")
es_client = Elasticsearch(
    hosts=[f"http://{ES_HOST}:{ES_PORT}"],
    basic_auth=(ES_USERNAME, ES_PASSWORD),
    request_timeout=30,
)

_LINE_OUT_RE = re.compile(r"^Line (\d+):\s*(.*)$", re.MULTILINE)

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

_OUTLINE_HEAD_RE = re.compile(
    r"^(?:"
    r"[壹贰叁肆伍陆柒捌一二三四五六七八九十]"
    r"|\d+"
    r"|[a-z]"
    r"|[（(](?:[一二三四五六七八九十]+|\d+|[a-z])[)）]"
    r")"
)


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


_gemini_client = None


def _get_gemini_client():
    global _gemini_client
    if _gemini_client is None:
        api_key = os.getenv("GEMINI_API_KEY", "")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY 未配置")
        from google import genai

        _gemini_client = genai.Client(api_key=api_key)
    return _gemini_client


def _gemini_generate_config(*, use_thinking: bool = True):
    from google.genai import types as genai_types

    max_out = 32768
    raw = os.getenv("GEMINI_TRANSLATION_MAX_OUTPUT_TOKENS", "32768")
    try:
        max_out = max(1024, min(int(raw), 65536))
    except ValueError:
        pass
    kwargs = dict(
        system_instruction=GEMINI_TRANSLATION_SYSTEM_INSTRUCTION,
        automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
        max_output_tokens=max_out,
    )
    if (
        use_thinking
        and hasattr(genai_types, "ThinkingConfig")
        and hasattr(genai_types, "ThinkingLevel")
    ):
        kwargs["thinking_config"] = genai_types.ThinkingConfig(
            thinking_level=genai_types.ThinkingLevel.MINIMAL
        )
    return genai_types.GenerateContentConfig(**kwargs)


def _extract_response_text(response) -> str:
    if not response:
        return ""
    try:
        t = response.text
        if isinstance(t, str) and t.strip():
            return t.strip()
    except Exception:
        pass
    try:
        cands = getattr(response, "candidates", None) or []
        if cands and cands[0].content and cands[0].content.parts:
            parts = []
            for part in cands[0].content.parts:
                if getattr(part, "thought", None) is True:
                    continue
                pt = getattr(part, "text", None)
                if isinstance(pt, str) and pt:
                    parts.append(pt)
            return "".join(parts).strip()
    except Exception:
        pass
    return ""


async def call_gemini(prompt: str) -> tuple[str, int, int]:
    def _run() -> tuple[str, int, int]:
        from google.genai import errors as genai_errors

        client = _get_gemini_client()
        for use_thinking in (True, False):
            try:
                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=prompt,
                    config=_gemini_generate_config(use_thinking=use_thinking),
                )
                break
            except genai_errors.ClientError as e:
                msg = str(e).lower()
                if use_thinking and "thinking" in msg:
                    continue
                raise
        else:
            raise RuntimeError("Gemini 调用失败")
        text = _extract_response_text(response)
        in_tok = out_tok = 0
        usage = getattr(response, "usage_metadata", None)
        if usage:
            in_tok = int(getattr(usage, "prompt_token_count", 0) or 0)
            out_tok = int(getattr(usage, "candidates_token_count", 0) or 0)
        return text, in_tok, out_tok

    return await asyncio.to_thread(_run)


async def retrieve_line(es_client, line: str) -> dict:
    try:
        en = pool.lookup(line)
        if en is not None:
            return {
                "line": line,
                "status": "pool",
                "en": en,
                "ref": None,
                "needs_ai": False,
            }

        prefix, body, suffix = _strip_scripture_suffix(line)
        if not (body or "").strip():
            body = line

        bm25_results = await bm25_search(es_client, body, INDICES, 5)
        dense_results = await dense_search(es_client, body, INDICES, 20, 100)
        merged = await rrf_merge(bm25_results, dense_results, k=60)
        reranked = await rerank(merged, body, 1)

        if reranked:
            top1 = reranked[0]
            ref = {
                "text": (top1.get("text") or "").strip(),
                "en": (top1.get("en") or "").strip(),
            }
            if pool.zh_eq(body, ref["text"]) and not prefix and not suffix:
                return {
                    "line": line,
                    "status": "exact",
                    "en": ref["en"].strip(),
                    "ref": ref,
                    "needs_ai": False,
                }
            if pool.zh_contains(body, ref["text"]):
                return {
                    "line": line,
                    "status": "exact",
                    "en": None,
                    "ref": ref,
                    "needs_ai": True,
                }
            return {
                "line": line,
                "status": "retrieved",
                "en": None,
                "ref": ref,
                "needs_ai": True,
            }
        return {
            "line": line,
            "status": "none",
            "en": None,
            "ref": None,
            "needs_ai": True,
        }
    except Exception as e:
        print(f"[retrieve_line] 检索降级 line={line[:20]}... 异常: {type(e).__name__}: {e}")
        return {
            "line": line,
            "status": "none",
            "en": None,
            "ref": None,
            "needs_ai": True,
        }


_EXACT_MATCH_PROMPT = (
    "[EXACT MATCH] The exact source sentence of this line appears verbatim "
    "in the reference below. You MUST copy its official English translation "
    "word-for-word from the reference. Do NOT retranslate or rephrase. "
    "Only convert the leading outline numeral (e.g. 二→B.) and trailing "
    "scripture references to English format per the rules."
)


def build_batch_prompt(items: list[dict]) -> str:
    parts: list[str] = []
    for i, item in enumerate(items, 1):
        parts.append(f"Line {i}: {item['line']}")
        ref = item.get("ref")
        if ref:
            parts.append(
                f"[Reference] 原文: {ref.get('text', '')} / 定译: {ref.get('en', '')}"
            )
        if item.get("status") == "exact" and item.get("needs_ai"):
            parts.append(_EXACT_MATCH_PROMPT)
    parts.append(TRANSLATE_RULES)
    parts.append(
        "Translate each line above to English. Output ONLY in this exact format, "
        "no extra text, no explanations:\n"
        "Line 1: {english}\n"
        "Line 2: {english}"
    )
    return "\n".join(parts)


def parse_batch_reply(text: str, n: int) -> dict[int, str]:
    parsed: dict[int, str] = {}
    for m in _LINE_OUT_RE.finditer(text or ""):
        idx = int(m.group(1))
        parsed[idx] = m.group(2).strip()
    if len(parsed) != n:
        preview = (text or "")[:200]
        raise ValueError(
            f"解析行数 {len(parsed)} 与期望 {n} 不一致，原始返回前200字符: {preview!r}"
        )
    return parsed


async def _translate_one_batch(
    batch_items: list[dict],
    batch_to_global: dict[int, int],
) -> tuple[dict[int, str], int, int]:
    n = len(batch_items)
    prompt = build_batch_prompt(batch_items)
    raw, in_tok, out_tok = await call_gemini(prompt)
    parsed = parse_batch_reply(raw, n)
    out: dict[int, str] = {}
    for batch_idx, en in parsed.items():
        global_idx = batch_to_global.get(batch_idx)
        if global_idx is not None:
            out[global_idx] = en
    return out, in_tok, out_tok


async def translate_items(items: list[dict]) -> tuple[dict[int, str], int, int]:
    if not items:
        return {}, 0, 0

    batches: list[tuple[list[dict], dict[int, int]]] = []
    for start in range(0, len(items), BATCH_SIZE):
        chunk = items[start : start + BATCH_SIZE]
        batch_items: list[dict] = []
        batch_to_global: dict[int, int] = {}
        for batch_idx, item in enumerate(chunk, 1):
            batch_items.append(item)
            batch_to_global[batch_idx] = item["global_idx"]
        batches.append((batch_items, batch_to_global))

    results = await asyncio.gather(
        *[_translate_one_batch(bi, mapping) for bi, mapping in batches]
    )

    translations: dict[int, str] = {}
    total_in = total_out = 0
    for trans_map, in_tok, out_tok in results:
        translations.update(trans_map)
        total_in += in_tok
        total_out += out_tok
    return translations, total_in, total_out


class TranslateRequest(BaseModel):
    content: str


class UpdateRequest(BaseModel):
    original_line: str
    new_translation: str


@router.get("/ping")
async def ping():
    return {"status": "ok", "service": "enhanced_translate_b"}


@router.post("/translate")
async def translate(req: TranslateRequest):
    lines = [ln.strip() for ln in req.content.split("\n") if ln.strip()]
    if not lines:
        raise HTTPException(status_code=400, detail="内容不能为空")
    if len(lines) > MAX_LINES:
        raise HTTPException(status_code=400, detail="最多 200 行")

    retrieved_rows = await asyncio.gather(
        *[retrieve_line(es_client, line) for line in lines]
    )

    to_translate: list[dict] = []
    for global_idx, row in enumerate(retrieved_rows):
        if row.get("needs_ai"):
            to_translate.append({**row, "global_idx": global_idx})

    translations, in_tok, out_tok = await translate_items(to_translate)

    rows_out: list[dict] = []
    for global_idx, row in enumerate(retrieved_rows):
        en = row.get("en")
        status = row["status"]
        if row.get("needs_ai"):
            en = translations.get(global_idx, en)
        rows_out.append({
            "line": row["line"],
            "en": en,
            "status": status,
            "ref": row.get("ref"),
            "needs_ai": row.get("needs_ai", False),
        })

    to_append: list[dict] = []
    seen_zh: set[str] = set()
    for row in rows_out:
        if row["status"] not in ("retrieved", "none", "exact"):
            continue
        if not row.get("en"):
            continue
        key = pool.normalize_zh(row["line"])
        if not key or key in seen_zh:
            continue
        seen_zh.add(key)
        to_append.append({
            "zh": row["line"],
            "en": row["en"],
            "source": "exact" if row["status"] == "exact" else "practice",
        })
    if to_append:
        pool.append_records(to_append)

    cost_usd = (in_tok * PRICE_IN + out_tok * PRICE_OUT) / 1_000_000
    result = "\n".join((r.get("en") or "") for r in rows_out)

    return {
        "rows": rows_out,
        "result": result,
        "cost_usd": cost_usd,
    }


@router.post("/update_translation")
async def update_translation(req: UpdateRequest):
    ok = pool.update_record(req.original_line, req.new_translation)
    return {"success": ok}
