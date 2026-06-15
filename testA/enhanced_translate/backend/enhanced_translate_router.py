# -*- coding: utf-8 -*-
"""增强翻译逻辑层（本批不含 API 路由）。"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

from elasticsearch import Elasticsearch
from fastapi import APIRouter, HTTPException
from gemini_translation_instruction import GEMINI_TRANSLATION_SYSTEM_INSTRUCTION
from prompts import TRANSLATE_RULES
from pydantic import BaseModel
from retrieval import bm25_search, dense_search, rerank, rrf_merge

import pool
from source_format import format_source

router = APIRouter(prefix="/api/testa/enhanced-translate")


class TranslateRequest(BaseModel):
    content: str


class UpdateRequest(BaseModel):
    original_line: str
    new_translation: str

logger = logging.getLogger("enhanced_translate")

INDICES = ",".join([
    "kg-rag_life", "kg-rag_cwwl", "kg-rag_cwwn",
    "kg-rag_others", "kg-rag_bib", "kg-rag_map_note", "kg-rag_7feasts",
])

GEMINI_MODEL = "gemini-2.5-flash"
PRICE_IN = 0.30
PRICE_OUT = 2.50

ES_HOST = os.getenv("ES_HOST", "localhost")
ES_PORT = os.getenv("ES_PORT", "9200")
ES_USERNAME = os.getenv("ES_USERNAME", "elastic")
ES_PASSWORD = os.getenv("ES_PASSWORD", "")

es_client = Elasticsearch(
    hosts=[f"http://{ES_HOST}:{ES_PORT}"],
    basic_auth=(ES_USERNAME, ES_PASSWORD),
    request_timeout=60,
)

_BATCH_LINE_RE = re.compile(r"^Line (\d+):\s*(.*)$", re.MULTILINE)
_BATCH_SIZE = 10


def _format_ref_block(ref: dict[str, Any] | None) -> str:
    if not ref:
        return ""
    text = (ref.get("text") or "").strip()
    en = (ref.get("en") or "").strip()
    if not text and not en:
        return ""
    return f"\n\n参考语料：\ntext: {text}\nen: {en}"


def build_batch_prompt(items: list[dict[str, Any]]) -> str:
    blocks: list[str] = []
    for pos, item in enumerate(items, 1):
        line = (item.get("line") or "").strip()
        ref_block = _format_ref_block(item.get("ref"))
        blocks.append(f"Line {pos}: {line}{ref_block}")

    format_lines = "\n".join(
        f"Line {pos}: {{english}}" for pos in range(1, len(items) + 1)
    )
    rules = (TRANSLATE_RULES or "").strip()
    rules_block = f"\n\n{rules}" if rules else ""

    return (
        "\n\n".join(blocks)
        + rules_block
        + "\n\nTranslate each line above to English. Output ONLY in this exact format:\n"
        + format_lines
        + "\n\nDo not output any extra text."
    )


def parse_batch_reply(text: str, n: int) -> dict[int, str]:
    parsed: dict[int, str] = {}
    for m in _BATCH_LINE_RE.finditer(text or ""):
        idx = int(m.group(1))
        parsed[idx] = (m.group(2) or "").strip()
    if len(parsed) != n:
        snippet = (text or "")[:200]
        raise ValueError(
            f"批量译文行数不符：期望 {n} 行，解析到 {len(parsed)} 行；原文前200字：{snippet!r}"
        )
    return parsed


def _translation_max_output_tokens() -> int:
    raw = os.getenv("GEMINI_TRANSLATION_MAX_OUTPUT_TOKENS", "32768")
    try:
        v = int(raw)
    except ValueError:
        v = 32768
    return max(1024, min(v, 65536))


def _gemini_translation_generate_config(system_instruction: str) -> Any:
    """对齐主站 gemini_translation_generate_config；gemini-2.5-flash 不支持 thinking，故不下发。"""
    from google.genai import types as genai_types

    return genai_types.GenerateContentConfig(
        system_instruction=system_instruction,
        automatic_function_calling=genai_types.AutomaticFunctionCallingConfig(disable=True),
        max_output_tokens=_translation_max_output_tokens(),
    )


def _extract_gemini_text(response: Any) -> str:
    if not response:
        return ""
    try:
        text = response.text
        if isinstance(text, str) and text.strip():
            return text.strip()
    except Exception:
        pass
    try:
        cands = getattr(response, "candidates", None) or []
        if cands and cands[0].content and cands[0].content.parts:
            parts = [
                getattr(p, "text", "")
                for p in cands[0].content.parts
                if getattr(p, "thought", None) is not True and getattr(p, "text", None)
            ]
            merged = "".join(parts).strip()
            if merged:
                return merged
    except Exception:
        pass
    return ""


async def call_gemini(prompt: str) -> tuple[str, int, int]:
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY 未配置")

    def _sync() -> tuple[str, int, int]:
        from google import genai

        client = genai.Client(api_key=api_key)
        config = _gemini_translation_generate_config(GEMINI_TRANSLATION_SYSTEM_INSTRUCTION)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=config,
        )
        body = _extract_gemini_text(response)
        meta = getattr(response, "usage_metadata", None)
        in_tok = int(getattr(meta, "prompt_token_count", 0) or 0) if meta else 0
        out_tok = int(getattr(meta, "candidates_token_count", 0) or 0) if meta else 0
        think_tok = int(getattr(meta, "thoughts_token_count", 0) or 0) if meta else 0
        return body, in_tok, out_tok + think_tok

    return await asyncio.to_thread(_sync)


async def retrieve_line(es: Any, line: str) -> dict[str, Any]:
    line = (line or "").strip()
    try:
        cached_en = pool.lookup(line)
        if cached_en is not None:
            return {"line": line, "status": "pool", "en": cached_en}

        bm25_results, dense_results = await asyncio.gather(
            bm25_search(es, line, INDICES, 5),
            dense_search(es, line, INDICES, 20, 100),
        )
        merged = await rrf_merge(
            bm25_results, dense_results, k=60, bm25_weight=1.0, dense_weight=1.0,
        )
        reranked = await rerank(merged, line, 1)
        if not reranked:
            return {"line": line, "status": "none", "ref": None}

        top = reranked[0]
        ref = {
            "text": (top.get("text") or "").strip(),
            "en": "" if top.get("en") is None else str(top.get("en")).strip(),
            "source": format_source(top),
        }
        if not ref["text"] and not ref["en"]:
            return {"line": line, "status": "none", "ref": None}
        return {"line": line, "status": "retrieved", "ref": ref}
    except Exception as e:
        logger.warning(
            "[enhanced_translate] retrieve_line 降级为 none: %s: %s",
            type(e).__name__,
            e,
        )
        return {"line": line, "status": "none", "ref": None}


async def _translate_one_batch(batch: list[dict[str, Any]]) -> tuple[dict[int, str], int, int]:
    if not batch:
        return {}, 0, 0
    prompt = build_batch_prompt(batch)
    n = len(batch)
    last_err: Exception | None = None

    for attempt in range(2):
        text, in_tok, out_tok = await call_gemini(prompt)
        try:
            parsed = parse_batch_reply(text, n)
            out: dict[int, str] = {}
            for pos, item in enumerate(batch, 1):
                line_i = int(item["line_i"])
                out[line_i] = parsed[pos]
            return out, in_tok, out_tok
        except Exception as e:
            last_err = e
            if attempt == 0:
                logger.warning("[enhanced_translate] 批量解析失败，重试一次: %s", e)
                continue
            raise last_err from e

    raise RuntimeError("translate batch failed")


async def translate_items(
    items: list[dict[str, Any]],
) -> tuple[dict[int, str], int, int, set[int]]:
    """返回 (译文映射, 输入token, 输出token, 翻译失败的 line_i 集合)。"""
    if not items:
        return {}, 0, 0, set()

    batches = [
        items[i:i + _BATCH_SIZE]
        for i in range(0, len(items), _BATCH_SIZE)
    ]
    results = await asyncio.gather(
        *[_translate_one_batch(batch) for batch in batches],
        return_exceptions=True,
    )

    merged: dict[int, str] = {}
    failed: set[int] = set()
    total_in = 0
    total_out = 0
    for batch, result in zip(batches, results):
        if isinstance(result, Exception):
            logger.error("[enhanced_translate] 批量翻译失败: %s", result)
            for item in batch:
                failed.add(int(item["line_i"]))
            continue
        part, in_tok, out_tok = result
        merged.update(part)
        total_in += in_tok
        total_out += out_tok
    return merged, total_in, total_out, failed


def _row_from_retrieve(res: dict[str, Any]) -> dict[str, Any]:
    status = res.get("status", "none")
    row: dict[str, Any] = {
        "line": res.get("line", ""),
        "status": status,
        "en": "",
        "ref": None,
    }
    if status == "pool":
        row["en"] = res.get("en") or ""
    elif status == "retrieved":
        row["ref"] = res.get("ref")
    return row


@router.post("/translate")
async def translate(req: TranslateRequest):
    lines = [ln.strip() for ln in (req.content or "").split("\n") if ln.strip()]
    if len(lines) > 200:
        raise HTTPException(status_code=400, detail="超过 200 行")

    retrieved = await asyncio.gather(
        *[retrieve_line(es_client, line) for line in lines]
    )

    rows: list[dict[str, Any]] = [_row_from_retrieve(res) for res in retrieved]
    to_translate: list[dict[str, Any]] = []
    for i, res in enumerate(retrieved):
        if res.get("status") in ("retrieved", "none"):
            to_translate.append({
                "line_i": i,
                "line": res["line"],
                "status": res["status"],
                "ref": res.get("ref"),
            })

    in_tok = 0
    out_tok = 0
    if to_translate:
        translations, in_tok, out_tok, failed = await translate_items(to_translate)
        new_records: list[dict[str, str]] = []
        for item in to_translate:
            i = int(item["line_i"])
            if i in failed:
                rows[i]["en"] = ""
                rows[i]["error"] = True
                continue
            en = (translations.get(i) or "").strip()
            rows[i]["en"] = en
            if en:
                new_records.append({
                    "zh": lines[i],
                    "en": en,
                    "source": "practice",
                })
        if new_records:
            pool.append_records(new_records)

    cost_usd = (in_tok * PRICE_IN + out_tok * PRICE_OUT) / 1_000_000
    result_text = "\n".join(row.get("en") or "" for row in rows)
    return {
        "rows": rows,
        "result": result_text,
        "cost_usd": round(cost_usd, 6),
    }


@router.post("/update_translation")
async def update_translation(req: UpdateRequest):
    ok = pool.update_record(req.original_line, req.new_translation)
    return {"success": ok}
