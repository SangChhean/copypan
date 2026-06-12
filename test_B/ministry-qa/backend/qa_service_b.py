# -*- coding: utf-8 -*-
"""
职事问答测试 — 普通通道四步流水线（无 Redis / Firewall / 定向 / 经文分支）。
"""
import asyncio
import json
import logging
import os
import re
import time
from collections.abc import AsyncGenerator
from typing import Any

import retrieval as retrieval

from qa_prompts import (
    STEP1_CONCEPT_EXTRACTION,
    STEP3_RELEVANCE_CHECK,
    STEP4_ANSWER_GENERATION,
)

logger = logging.getLogger("ministry-qa")

STEP1_MODEL = "claude-sonnet-4-6"
STEP3_MODEL = "claude-haiku-4-5-20251001"
STEP4_MODEL = "claude-sonnet-4-6"

BM25_TOP_K = 30
DENSE_TOP_K = 30
RRF_K = 60
RERANK_TOP_N = 20

_async_claude_client: Any = None


def _get_async_claude_client():
    global _async_claude_client
    if _async_claude_client is None:
        api_key = os.environ.get("CLAUDE_API_KEY", "")
        if not api_key:
            raise RuntimeError("未配置 CLAUDE_API_KEY")
        from anthropic import AsyncAnthropic

        _async_claude_client = AsyncAnthropic(api_key=api_key)
    return _async_claude_client


def _claude_message_text(message: Any) -> str:
    if not message or not getattr(message, "content", None):
        return ""
    parts: list[str] = []
    for block in message.content:
        btype = getattr(block, "type", None)
        if btype == "text":
            t = getattr(block, "text", None)
            if isinstance(t, str) and t.strip():
                parts.append(t)
        elif isinstance(block, dict) and block.get("type") == "text":
            t = block.get("text")
            if isinstance(t, str) and t.strip():
                parts.append(t)
    out = "\n".join(parts).strip()
    if out:
        return out
    try:
        b0 = message.content[0]
        t0 = getattr(b0, "text", None) if not isinstance(b0, dict) else b0.get("text")
        if isinstance(t0, str) and t0.strip():
            return t0.strip()
    except (IndexError, TypeError):
        pass
    return ""


async def _call_llm(
    prompt: str,
    model: str,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    system: str = "你是一位专业、精确的助手。请严格按要求的格式输出。",
) -> tuple[str, Any]:
    client = _get_async_claude_client()
    kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    if not model.startswith("claude-opus-4-7"):
        kwargs["temperature"] = temperature
    try:
        msg = await client.messages.create(**kwargs)
        text = _claude_message_text(msg)
        if not text:
            blocks = getattr(msg, "content", None) or []
            logger.warning(
                "[ministry-qa] Claude 返回空文本 model=%s stop=%s block_types=%s",
                model,
                getattr(msg, "stop_reason", None),
                [getattr(b, "type", type(b).__name__) for b in blocks],
            )
        usage = getattr(msg, "usage", None)
        return text, usage
    except Exception as e:
        logger.error("[ministry-qa] LLM 调用失败 model=%s: %s", model, e)
        raise


_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-6": (5.0, 25.0),
    "claude-opus-4-7": (5.0, 25.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-haiku-4-5-20251001": (1.0, 5.0),
}


def _calc_cost(model: str, usage: Any) -> float:
    if usage is None:
        return 0.0
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    in_price, out_price = _PRICING.get(model, (3.0, 15.0))
    return round(
        input_tokens * in_price / 1_000_000 + output_tokens * out_price / 1_000_000,
        6,
    )


def _safe_parse_json(text: str) -> dict | None:
    if not text:
        return None
    s = text.strip()
    s = re.sub(r"^```(?:json)?\s*", "", s, count=1)
    s = re.sub(r"\s*```\s*$", "", s, count=1)
    s = s.strip()
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    i = s.find("{")
    if i >= 0:
        try:
            obj, _end = json.JSONDecoder().raw_decode(s[i:])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            pass
    i2 = s.find("{")
    last = s.rfind("}")
    if i2 >= 0 and last > i2:
        try:
            obj = json.loads(s[i2 : last + 1])
            return obj if isinstance(obj, dict) else None
        except json.JSONDecodeError:
            pass
    return None


async def _step1(question: str, neo4j_client) -> dict:
    history_questions = ""

    concept_names = neo4j_client.get_concept_names()
    concept_list = "\n".join(f"- {name}" for name in concept_names) if concept_names else "（词表暂不可用）"

    prompt = STEP1_CONCEPT_EXTRACTION.format(
        question=question,
        concept_list=concept_list,
        history_questions=history_questions,
    )

    try:
        raw, usage = await _call_llm(
            prompt,
            STEP1_MODEL,
            temperature=0,
            max_tokens=512,
            system="你是一位深研圣经与职事文献的神学助手。请严格按要求的格式输出 JSON，不输出其他内容。",
        )
        cost = _calc_cost(STEP1_MODEL, usage)
    except Exception as e:
        logger.warning("[ministry-qa] Step1 LLM 失败，降级为空概念: %s", e)
        return {
            "surface": [],
            "deep": [],
            "concepts": [],
            "targeted": None,
            "reasoning": "",
            "greek_terms_context": "",
            "key_verses_context": "",
            "graph_context": "",
            "cost_usd": 0.0,
            "rewritten_query": question,
        }

    logger.info("[ministry-qa] Step1 raw_len=%d", len(raw or ""))
    parsed = _safe_parse_json(raw)
    surface: list[str] = []
    deep: list[str] = []
    targeted: dict | None = None
    reasoning = ""

    if parsed:
        raw_surface = parsed.get("surface", [])
        raw_deep = parsed.get("deep", [])
        if isinstance(raw_surface, list):
            surface = [str(c).strip() for c in raw_surface if str(c).strip()][:3]
        if isinstance(raw_deep, list):
            deep = [str(c).strip() for c in raw_deep if str(c).strip()][:5]

        raw_targeted = parsed.get("targeted")
        if isinstance(raw_targeted, dict):
            book_keyword = str(raw_targeted.get("book_keyword", "")).strip()
            message_keyword = str(raw_targeted.get("message_keyword", "")).strip()
            if book_keyword and message_keyword:
                targeted = {
                    "book_keyword": book_keyword,
                    "message_keyword": message_keyword,
                }

        reasoning = str(parsed.get("reasoning", "") or "").strip()

        logger.info(
            "[ministry-qa] Step1 surface=%s deep=%s targeted=%s reasoning=%s",
            surface,
            deep,
            targeted,
            reasoning[:100],
        )
    else:
        logger.warning("[ministry-qa] Step1 JSON 解析失败，raw=%s", (raw or "")[:200])

    rw_raw = (parsed or {}).get("rewritten_query") if parsed else None
    if rw_raw is None or rw_raw == "":
        rewritten_query = ""
    else:
        rewritten_query = str(rw_raw).strip()
    if not rewritten_query:
        rewritten_query = question

    seen = set()
    concepts = []
    for c in surface + deep:
        if c not in seen:
            seen.add(c)
            concepts.append(c)

    greek_terms_context = ""
    key_verses_context = ""

    if concepts:
        try:
            greek_map = neo4j_client.get_greek_terms(concepts)
            if greek_map:
                lines = [f"- {c}：{g}" for c, g in greek_map.items()]
                greek_terms_context = "\n【相关原文参考】\n" + "\n".join(lines) + "\n"
        except Exception as e:
            logger.warning("[ministry-qa] get_greek_terms 失败: %s", e)

        try:
            verses_map = neo4j_client.get_key_verses(concepts)
            if verses_map:
                lines = []
                for concept, verse_list in verses_map.items():
                    for sid, stext in verse_list[:3]:
                        lines.append(f"- {sid}：{stext}")
                if lines:
                    key_verses_context = "\n【相关关键经文】\n" + "\n".join(lines) + "\n"
        except Exception as e:
            logger.warning("[ministry-qa] get_key_verses 失败: %s", e)

    graph_context = ""
    if concepts:
        try:
            relations = neo4j_client.get_concept_relations(concepts)
            if relations:
                rel_labels = {
                    "CONTAINS": "包含",
                    "OPPOSES": "对立",
                    "LEADS_TO": "引导",
                    "EXPERIENCES": "经历",
                    "PRACTICED_AS": "实践",
                    "LOCATED_IN": "位于",
                }
                lines = []
                for r in relations:
                    label = rel_labels.get(r["rel"], r["rel"])
                    lines.append(f"- {r['from']} [{label}] {r['to']}")
                graph_context = "\n【概念关系参考】\n" + "\n".join(lines) + "\n"
        except Exception as e:
            logger.warning("[ministry-qa] get_concept_relations 失败: %s", e)

    logger.info(
        "[ministry-qa] Step1 graph_context=%s",
        graph_context[:200] if graph_context else "(空)",
    )

    return {
        "surface": surface,
        "deep": deep,
        "concepts": concepts,
        "targeted": targeted,
        "reasoning": reasoning,
        "greek_terms_context": greek_terms_context,
        "key_verses_context": key_verses_context,
        "graph_context": graph_context,
        "rewritten_query": rewritten_query,
        "cost_usd": cost,
    }


async def _step2(
    rewritten_query: str,
    es_client,
    index: str,
    bm25_top_k: int | None = None,
    dense_top_k: int | None = None,
    rerank_top_n: int | None = None,
) -> list[dict]:
    tk_bm25 = bm25_top_k if bm25_top_k is not None else BM25_TOP_K
    tk_dense = dense_top_k if dense_top_k is not None else DENSE_TOP_K
    tk_rerank = rerank_top_n if rerank_top_n is not None else RERANK_TOP_N

    bm25_task = retrieval.bm25_search(es_client, rewritten_query, index, top_k=tk_bm25)
    dense_task = retrieval.dense_search(es_client, rewritten_query, index, top_k=tk_dense)

    bm25_results, dense_results = await asyncio.gather(bm25_task, dense_task)
    logger.info("[ministry-qa] Step2 BM25=%d Dense=%d", len(bm25_results), len(dense_results))

    merged = await retrieval.rrf_merge(bm25_results, dense_results, k=RRF_K)
    reranked = await retrieval.rerank(merged, rewritten_query, top_n=tk_rerank)
    logger.info("[ministry-qa] Step2 reranked=%d", len(reranked))

    return reranked


async def _step2_with_expansion(
    rewritten_query: str,
    deep: list[str],
    es_client,
    index: str,
    bm25_top_k: int | None = None,
    dense_top_k: int | None = None,
    rerank_top_n: int | None = None,
    expansion_top_n: int | None = None,
) -> list[dict]:
    exp_rerank = expansion_top_n if expansion_top_n is not None else 5

    async def _expand_one(combined_q: str, concept: str) -> list[dict]:
        bm25 = await retrieval.bm25_search(es_client, combined_q, index, top_k=15)
        dense = await retrieval.dense_search(es_client, combined_q, index, top_k=15)
        merged = await retrieval.rrf_merge(bm25, dense, k=RRF_K)
        reranked = await retrieval.rerank(merged, combined_q, top_n=exp_rerank)
        for doc in reranked:
            doc["expanded_from"] = concept
        return reranked

    main_task = asyncio.create_task(
        _step2(
            rewritten_query,
            es_client,
            index,
            bm25_top_k=bm25_top_k,
            dense_top_k=dense_top_k,
            rerank_top_n=rerank_top_n,
        )
    )
    expansion_tasks = []
    for concept in deep:
        combined_query = f"{rewritten_query} {concept}".strip()
        expansion_tasks.append(asyncio.create_task(_expand_one(combined_query, concept)))

    all_results = await asyncio.gather(main_task, *expansion_tasks, return_exceptions=True)

    main_results = all_results[0] if not isinstance(all_results[0], Exception) else []
    if isinstance(all_results[0], Exception):
        logger.warning("[ministry-qa] Step2 主路失败: %s", all_results[0])
    logger.info("[ministry-qa] Step2 主路=%d 段落", len(main_results))

    main_ids = {r.get("chunk_id") for r in main_results if r.get("chunk_id")}
    expanded: list[dict] = []
    for i, result in enumerate(all_results[1:]):
        if isinstance(result, Exception):
            logger.warning("[ministry-qa] 扩展检索失败 deep[%d]: %s", i, result)
            continue
        for doc in result:
            cid = doc.get("chunk_id")
            if cid and cid not in main_ids:
                expanded.append(doc)
                main_ids.add(cid)

    logger.info("[ministry-qa] Step2 扩展路=%d 段落（去重后）", len(expanded))
    return main_results + expanded


async def _step3(rewritten_query: str, passages: list[dict]) -> tuple[bool, float]:
    passage_lines = []
    for i, p in enumerate(passages[:10], 1):
        text = (p.get("text") or "").strip()[:200]
        book = p.get("book_title", "")
        passage_lines.append(f"[{i}] {book}\n{text}")
    passages_text = "\n---\n".join(passage_lines) if passage_lines else "（无检索结果）"

    prompt = STEP3_RELEVANCE_CHECK.format(
        rewritten_query=rewritten_query,
        passages=passages_text,
    )

    try:
        raw, usage = await _call_llm(prompt, STEP3_MODEL, temperature=0, max_tokens=512)
        cost = _calc_cost(STEP3_MODEL, usage)
    except Exception as e:
        logger.warning("[ministry-qa] Step3 LLM 失败，默认 relevant=True: %s", e)
        return True, 0.0

    parsed = _safe_parse_json(raw)
    if parsed is None:
        logger.warning("[ministry-qa] Step3 JSON 解析失败，默认 relevant=True，raw=%s", raw[:200])
        logger.info("[ministry-qa] Step3 relevant=True reason=(parse_fallback)")
        return True, cost

    relevant = bool(parsed.get("relevant", True))
    logger.info("[ministry-qa] Step3 relevant=%s reason=%s", relevant, parsed.get("reason", ""))
    return relevant, cost


def _step4_build_prompt(
    question: str,
    passages: list[dict],
    greek_terms_context: str,
    key_verses_context: str,
    graph_context: str = "",
) -> str:
    passage_lines = []
    for p in passages:
        book = p.get("book_title", "")
        text = (p.get("text") or "").strip()
        source_zh = (p.get("source_zh") or "").strip()
        source_zh_clean = re.sub(
            r"，第[零一二三四五六七八九十百千]+[段节].*$",
            "",
            source_zh,
        ).strip()
        source_zh_clean = source_zh_clean.strip("（）()").strip()
        header = f"[来源：{source_zh_clean or book}]"
        passage_lines.append(f"{header}\n{text}")
    passages_text = "\n---\n".join(passage_lines)

    return STEP4_ANSWER_GENERATION.format(
        history_context="",
        question=question,
        passages=passages_text,
        greek_context=greek_terms_context,
        verse_context=key_verses_context,
        graph_context=graph_context,
        firewall_instruction="",
    )


def _extract_step4_sources(raw: str) -> list[str]:
    sources: list[str] = []
    if "【引用书目】" not in raw:
        return sources
    bib_block = raw.split("【引用书目】", 1)[1]
    seen: set[str] = set()
    for line in bib_block.splitlines():
        line = line.strip()
        if not line:
            continue
        if "➡️" in line:
            after = line.split("➡️", 1)[1].strip()
        elif re.match(r"^\d+", line):
            after = line.strip()
        else:
            continue
        key = re.sub(r"^\d+[\.\s]+", "", after).strip()
        if key and key not in seen:
            seen.add(key)
            sources.append(after)
    return sources


async def _step4(
    question: str,
    passages: list[dict],
    greek_terms_context: str,
    key_verses_context: str,
    graph_context: str = "",
) -> tuple[str, list[str], float]:
    prompt = _step4_build_prompt(
        question,
        passages,
        greek_terms_context,
        key_verses_context,
        graph_context=graph_context,
    )

    raw, usage = await _call_llm(
        prompt,
        STEP4_MODEL,
        temperature=0.3,
        max_tokens=4096,
        system="你是一位职事信息问答助手，严格基于所提供的段落作答。回答要有清晰的主线，用原文支撑论述，不编造，不拼凑。",
    )
    cost = _calc_cost(STEP4_MODEL, usage)
    sources = _extract_step4_sources(raw)
    return raw.strip(), sources, cost


async def _iter_step4_stream_tokens(prompt: str) -> AsyncGenerator[tuple[str, Any], None]:
    client = _get_async_claude_client()
    system = "你是一位职事信息问答助手，严格基于所提供的段落作答。回答要有清晰的主线，用原文支撑论述，不编造，不拼凑。"
    kwargs: dict[str, Any] = dict(
        model=STEP4_MODEL,
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": prompt}],
    )
    if not STEP4_MODEL.startswith("claude-opus-4-7"):
        kwargs["temperature"] = 0.3
    try:
        async with client.messages.stream(**kwargs) as stream:
            async for text in stream.text_stream:
                if text:
                    yield ("token", text)
            try:
                fm = await stream.get_final_message()
                usage = getattr(fm, "usage", None)
            except Exception:
                usage = None
            yield ("usage", usage)
    except Exception as e:
        logger.error("[ministry-qa] Step4 stream 失败: %s", e)
        yield ("error", str(e))


async def _run_pipeline_until_step4(
    question: str,
    app: Any,
) -> tuple[dict | None, dict | None]:
    start = time.monotonic()

    neo4j_client = app.state.neo4j_client
    es_client = app.state.es_client
    index = app.state.es_indices

    is_targeted = False
    passages: list[dict] = []
    concepts: list = []
    greek_terms_context = ""
    key_verses_context = ""
    graph_context = ""
    step1_snapshot: dict | None = None
    rewritten_query = question

    step1_result = await _step1(question, neo4j_client)
    step1_snapshot = step1_result
    concepts = step1_result["concepts"]
    deep = step1_result["deep"]
    greek_terms_context = step1_result["greek_terms_context"]
    key_verses_context = step1_result["key_verses_context"]
    graph_context = step1_result.get("graph_context", "")
    rw = step1_result.get("rewritten_query")
    rewritten_query = str(rw).strip() if rw else ""
    if not rewritten_query:
        rewritten_query = question

    try:
        passages = await _step2_with_expansion(
            rewritten_query,
            deep,
            es_client,
            index,
        )
    except Exception as e:
        logger.error("[ministry-qa] Step2 检索失败: %s", e)
        passages = []

    relevant, _step3_cost = await _step3(rewritten_query, passages)

    if not relevant:
        elapsed = int((time.monotonic() - start) * 1000)
        result = {
            "answer": "以下内容未能在职事信息中找到相关依据。",
            "sources": [],
            "concepts": concepts,
            "found": False,
            "elapsed_ms": elapsed,
        }
        return result, None

    ctx = {
        "start": start,
        "question": question,
        "rewritten_query": rewritten_query,
        "passages": passages,
        "greek_terms_context": greek_terms_context,
        "key_verses_context": key_verses_context,
        "graph_context": graph_context,
        "concepts": concepts,
        "is_targeted": is_targeted,
        "step1_snapshot": step1_snapshot,
    }
    return None, ctx


async def run_pipeline(question: str, app) -> dict:
    early, ctx = await _run_pipeline_until_step4(question, app)
    if early is not None:
        return early

    assert ctx is not None
    start = ctx["start"]
    question = ctx["question"]
    passages = ctx["passages"]
    greek_terms_context = ctx["greek_terms_context"]
    key_verses_context = ctx["key_verses_context"]
    graph_context = ctx.get("graph_context", "")
    concepts = ctx["concepts"]

    try:
        answer, sources, _step4_cost = await _step4(
            question,
            passages,
            greek_terms_context,
            key_verses_context,
            graph_context=graph_context,
        )
    except Exception as e:
        logger.error("[ministry-qa] Step4 生成失败: %s", e)
        answer = "答案生成失败，请稍后重试。"
        sources = []

    elapsed = int((time.monotonic() - start) * 1000)

    return {
        "answer": answer,
        "sources": sources,
        "concepts": concepts,
        "found": True,
        "elapsed_ms": elapsed,
    }


async def stream_query(
    question: str,
    app: Any,
) -> AsyncGenerator[dict[str, Any], None]:
    early, ctx = await _run_pipeline_until_step4(question, app)

    if early is not None:
        yield {
            "type": "done",
            "answer": early.get("answer", ""),
            "sources": early.get("sources", []),
            "found": bool(early.get("found", False)),
            "concepts": early.get("concepts", []),
            "elapsed_ms": int(early.get("elapsed_ms", 0)),
        }
        return

    assert ctx is not None

    start = ctx["start"]
    q = ctx["question"]
    passages = ctx["passages"]
    greek_terms_context = ctx["greek_terms_context"]
    key_verses_context = ctx["key_verses_context"]
    graph_context = ctx.get("graph_context", "")
    concepts = ctx["concepts"]
    is_targeted = ctx["is_targeted"]
    step1_snapshot = ctx.get("step1_snapshot") or {}
    rewritten_query = ctx.get("rewritten_query", q)

    yield {
        "type": "step",
        "stage": "step1",
        "data": {
            "skipped": is_targeted,
            "concept_count": len(concepts) if concepts else 0,
            "rewritten_query": rewritten_query,
            "surface": list(step1_snapshot.get("surface") or []),
            "deep": list(step1_snapshot.get("deep") or []),
        },
    }
    yield {
        "type": "step",
        "stage": "step2",
        "data": {"passage_count": len(passages), "targeted": is_targeted},
    }
    yield {"type": "step", "stage": "step3", "data": {"relevant": True}}

    prompt = _step4_build_prompt(
        q,
        passages,
        greek_terms_context,
        key_verses_context,
        graph_context=graph_context,
    )

    full_text = ""
    ttft_ms: int | None = None
    async for item in _iter_step4_stream_tokens(prompt):
        if isinstance(item, tuple) and len(item) == 2 and item[0] == "error":
            yield {"type": "error", "message": str(item[1])}
            return
        kind, payload = item
        if kind == "token":
            if ttft_ms is None:
                ttft_ms = int((time.monotonic() - start) * 1000)
            full_text += payload
            yield {"type": "token", "text": payload}
        elif kind == "usage":
            pass

    sources = _extract_step4_sources(full_text)
    answer = full_text.strip()
    if not answer:
        answer = "答案生成失败，请稍后重试。"
        sources = []

    elapsed = ttft_ms if ttft_ms is not None else int((time.monotonic() - start) * 1000)

    yield {
        "type": "done",
        "answer": answer,
        "sources": sources,
        "found": True,
        "concepts": concepts,
        "elapsed_ms": elapsed,
    }
