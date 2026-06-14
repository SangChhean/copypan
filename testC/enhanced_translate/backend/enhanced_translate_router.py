# -*- coding: utf-8 -*-
"""增强式翻译练习版 Router（testC，端口 8062）。"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any

from elasticsearch import Elasticsearch
from fastapi import APIRouter
from pydantic import BaseModel

from retrieval import bm25_search, dense_search, rrf_merge, rerank
from gemini_translation_instruction import GEMINI_TRANSLATION_SYSTEM_INSTRUCTION
from prompts import TRANSLATE_RULES
import pool

logger = logging.getLogger("testc.enhanced_translate")

# ── ES 客户端（同步，与 ministerialize_router.py 一致）────────────
_es_client: Elasticsearch | None = None

def _get_es() -> Elasticsearch:
    global _es_client
    if _es_client is None:
        host     = os.environ.get("ES_HOST", "localhost")
        port     = os.environ.get("ES_PORT", "9200")
        username = os.environ.get("ES_USERNAME", "elastic")
        password = os.environ.get("ES_PASSWORD", "")
        _es_client = Elasticsearch(
            hosts=[f"http://{host}:{port}"],
            basic_auth=(username, password),
            request_timeout=60,
        )
    return _es_client

# ── 常量 ──────────────────────────────────────────────────────────
INDICES = ",".join([
    "kg-rag_life", "kg-rag_cwwl", "kg-rag_cwwn",
    "kg-rag_others", "kg-rag_bib", "kg-rag_map_note",
    "kg-rag_7feasts",
])
GEMINI_MODEL = "gemini-2.5-flash"
PRICE_IN  = 0.30   # 美元 / 百万 token（输入）
PRICE_OUT = 2.50   # 美元 / 百万 token（输出）

# ── Router ────────────────────────────────────────────────────────
router = APIRouter(prefix="/api/testc/enhanced-translate")


# ── Gemini 调用 ───────────────────────────────────────────────────
async def call_gemini(prompt: str) -> tuple[str, int, int]:
    """调用 Gemini，返回 (响应文本, 输入token, 输出token)。"""
    import google.generativeai as genai

    api_key = os.environ.get("GEMINI_API_KEY", "")
    genai.configure(api_key=api_key)

    model = genai.GenerativeModel(
        model_name=GEMINI_MODEL,
        system_instruction=GEMINI_TRANSLATION_SYSTEM_INSTRUCTION,
    )
    generation_config = genai.types.GenerationConfig(temperature=0.1)

    def _sync_call():
        return model.generate_content(prompt, generation_config=generation_config)

    resp = await asyncio.to_thread(_sync_call)
    text = resp.text or ""
    usage   = getattr(resp, "usage_metadata", None)
    in_tok  = getattr(usage, "prompt_token_count",     0) or 0
    out_tok = getattr(usage, "candidates_token_count", 0) or 0
    return text, in_tok, out_tok


# ── 逐行检索 ──────────────────────────────────────────────────────
async def retrieve_line(es: Elasticsearch, line: str) -> dict[str, Any]:
    """第一层查笔记本，第二层走 ES 检索。"""
    # 第一层：笔记本精确匹配
    en = pool.lookup(line)
    if en:
        return {"line": line, "status": "pool", "en": en, "ref": None}

    # 第二层：ES 检索找参考语料
    try:
        bm25_results  = await bm25_search(es, line, INDICES, 5)
        dense_results = await dense_search(es, line, INDICES, 20, 100)
        merged        = await rrf_merge(
            bm25_results, dense_results, k=60, bm25_weight=1.0, dense_weight=1.0
        )
        reranked = await rerank(merged, line, 1)
        if reranked:
            top = reranked[0]
            return {
                "line": line,
                "status": "retrieved",
                "en": None,
                "ref": {
                    "text": top.get("text", ""),
                    "en":   top.get("en",   ""),
                },
            }
    except Exception as exc:
        logger.warning("[retrieve_line] 检索异常，降级：%s", exc)

    return {"line": line, "status": "none", "en": None, "ref": None}


# ── 批量翻译（第三层）────────────────────────────────────────────
def build_batch_prompt(items: list[dict[str, Any]]) -> str:
    parts = []
    for i, item in enumerate(items, 1):
        parts.append(f"Line {i}: {item['line']}")
        if item.get("ref"):
            ref = item["ref"]
            parts.append(f"  [参考语料原文] {ref.get('text', '')}")
            parts.append(f"  [参考语料英文] {ref.get('en', '')}")
    parts.append("")
    parts.append(TRANSLATE_RULES)
    parts.append("")
    parts.append("Translate each line above to English.")
    parts.append("Output ONLY in this exact format, no extra text, no explanations:")
    for i in range(1, len(items) + 1):
        parts.append(f"Line {i}: {{english translation}}")
    return "\n".join(parts)


def parse_batch_reply(text: str, n: int) -> dict[int, str]:
    pattern = re.compile(r"^Line\s+(\d+):\s*(.*)$", re.MULTILINE)
    result  = {int(idx): val.strip() for idx, val in pattern.findall(text)}
    if len(result) != n:
        raise ValueError(
            f"解析行数不符：期望 {n} 行，实际 {len(result)} 行。"
            f"原始返回前 300 字：{text[:300]}"
        )
    return result


async def translate_items(
    items: list[dict[str, Any]]
) -> tuple[dict[int, str], int, int]:
    """分批（每批≤10行）并发调 Gemini，返回 {0-based索引→译文} 和 token 合计。"""
    BATCH_SIZE = 10
    all_translations: dict[int, str] = {}
    total_in = total_out = 0

    batches = [items[i: i + BATCH_SIZE] for i in range(0, len(items), BATCH_SIZE)]

    async def _do_batch(batch: list[dict[str, Any]], offset: int) -> None:
        nonlocal total_in, total_out
        prompt = build_batch_prompt(batch)
        text, in_tok, out_tok = await call_gemini(prompt)
        total_in  += in_tok
        total_out += out_tok
        parsed = parse_batch_reply(text, len(batch))
        for local_i, en in parsed.items():
            all_translations[offset + local_i - 1] = en  # 转为 0-based 全局索引

    await asyncio.gather(*[
        _do_batch(batch, i * BATCH_SIZE)
        for i, batch in enumerate(batches)
    ])
    return all_translations, total_in, total_out


# ── Pydantic 模型 ─────────────────────────────────────────────────
class TranslateRequest(BaseModel):
    content: str

class UpdateRequest(BaseModel):
    original_line: str
    new_translation: str


# ── API 接口 ──────────────────────────────────────────────────────
@router.post("/translate")
async def api_translate(req: TranslateRequest):
    lines = [ln for ln in req.content.splitlines() if ln.strip()]
    lines = lines[:200]
    if not lines:
        return {"rows": [], "result": "", "cost_usd": 0}

    es = _get_es()

    # Step 1：所有行并发检索（第一层 + 第二层）
    retrieved_list: list[dict[str, Any]] = await asyncio.gather(
        *[retrieve_line(es, line) for line in lines]
    )

    # Step 2：收集需要翻译的行，保留原始索引
    to_translate_indexed = [
        (i, item)
        for i, item in enumerate(retrieved_list)
        if item["status"] != "pool"
    ]

    total_in = total_out = 0
    if to_translate_indexed:
        items_only = [item for _, item in to_translate_indexed]
        translations, total_in, total_out = await translate_items(items_only)
        for batch_i, (orig_i, item) in enumerate(to_translate_indexed):
            item["en"] = translations.get(batch_i, "")

    # Step 3：回写闭环
    new_rows = [
        {"zh": item["line"], "en": item["en"], "source": "practice"}
        for item in retrieved_list
        if item["status"] != "pool" and (item.get("en") or "").strip()
    ]
    if new_rows:
        added = pool.append_records(new_rows)
        logger.info("[translate] 回写 %s 条新译文至 pool", added)

    # Step 4：组装返回
    rows_out = [
        {
            "line":   item["line"],
            "en":     item["en"] or "",
            "status": item["status"],
            "ref":    item.get("ref"),
        }
        for item in retrieved_list
    ]
    result_text = "\n".join(r["en"] for r in rows_out)
    cost = (total_in * PRICE_IN + total_out * PRICE_OUT) / 1_000_000

    return {
        "rows":     rows_out,
        "result":   result_text,
        "cost_usd": round(cost, 6),
    }


@router.post("/update_translation")
async def api_update(req: UpdateRequest):
    success = pool.update_record(req.original_line, req.new_translation)
    return {"success": success}
