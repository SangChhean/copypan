# -*- coding: utf-8 -*-
"""
QA 四步流水线核心逻辑。

Step 1: 概念抽取（Opus）→ greek_terms + key_verses
Step 2: BM25 + Dense → RRF → Reranker
Step 3: 相关性判断（Haiku）
Step 4: 答案生成（Sonnet，temp=0.3）

Firewall 在 Step 1 完成后并发发起，Step 3 通过后 await。
"""
import asyncio
import hashlib
import json
import logging
import os
import re
import sys
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any

logger = logging.getLogger("qa")

# ---------------------------------------------------------------------------
# 模型常量
# ---------------------------------------------------------------------------
# Step1 与设计方案一致默认 Opus；长词表偶发 refusal 可观察日志；可用 QA_STEP1_MODEL 临时覆盖
STEP1_MODEL = os.environ.get("QA_STEP1_MODEL", "claude-opus-4-6")
STEP3_MODEL = "claude-haiku-4-5-20251001"
STEP4_MODEL = "claude-sonnet-4-6"

# 检索参数
BM25_TOP_K = 30
DENSE_TOP_K = 30
RRF_K = 60
RERANK_TOP_N = 20

# ES 索引（多索引用逗号分隔）
QA_INDEX = os.environ.get(
    "QA_ES_INDEX",
    "kg-rag_7feasts,kg-rag_bib,kg-rag_cwwl,kg-rag_cwwn,kg-rag_life,kg-rag_map_note,kg-rag_others"
)

# 调试用：最近一次 Step4 发给 LLM 的完整 prompt
_last_step4_prompt = ""

# ---------------------------------------------------------------------------
# LLM 客户端（复用 back_mic 的 CLAUDE_API_KEY）
# ---------------------------------------------------------------------------

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
    """拼接 Messages API 中所有 type==text 的块（与 ai_search.ai_service._claude_message_text 一致）。"""
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
    # 回退：首块 .text（兼容仅一块或非标准 SDK 表示）
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
    """异步调用 Claude（AsyncAnthropic）。返回 (text, usage)。"""
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
                "[QA] Claude 返回空文本 model=%s stop=%s block_types=%s",
                model,
                getattr(msg, "stop_reason", None),
                [getattr(b, "type", type(b).__name__) for b in blocks],
            )
        usage = getattr(msg, "usage", None)
        return text, usage
    except Exception as e:
        logger.error("[QA] LLM 调用失败 model=%s: %s", model, e)
        raise


# ---------------------------------------------------------------------------
# 费用计算
# ---------------------------------------------------------------------------

# 美元每百万 token（输入/输出）
_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4-6":           (5.0,  25.0),
    "claude-opus-4-7":           (5.0,  25.0),
    "claude-sonnet-4-6":         (3.0,   15.0),
    "claude-haiku-4-5-20251001": (1.0,   5.0),
}

def _calc_cost(model: str, usage: Any) -> float:
    """根据 usage 对象计算费用（美元）。"""
    if usage is None:
        return 0.0
    input_tokens = getattr(usage, "input_tokens", 0) or 0
    output_tokens = getattr(usage, "output_tokens", 0) or 0
    in_price, out_price = _PRICING.get(model, (3.0, 15.0))
    return round(
        input_tokens * in_price / 1_000_000 + output_tokens * out_price / 1_000_000,
        6,
    )


# ---------------------------------------------------------------------------
# 缓存
# ---------------------------------------------------------------------------

def _make_cache_key(question: str, history: list[dict] | None = None) -> str:
    from back_shared.version_manifest import PROMPT_VERSION, MODEL_PROFILE, FIREWALL_RULES_VERSION

    hist = history or []
    hist_ser = json.dumps(hist, ensure_ascii=False, separators=(",", ":"))
    raw = f"{question}|{hist_ser}|{PROMPT_VERSION}|{MODEL_PROFILE}|{FIREWALL_RULES_VERSION}"
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    prefix = os.environ.get("QA_REDIS_PREFIX", "qa:cache:")
    return f"{prefix}{h}"


def _read_cache(redis_client, key: str) -> dict | None:
    if redis_client is None:
        return None
    try:
        raw = redis_client.get(key)
        if raw:
            return json.loads(raw)
    except Exception as e:
        logger.warning("[QA] 缓存读取失败: %s", e)
    return None


def _write_cache(redis_client, key: str, value: dict) -> None:
    if redis_client is None:
        return
    try:
        ttl = int(os.environ.get("QA_CACHE_TTL", "259200"))
        redis_client.setex(key, ttl, json.dumps(value, ensure_ascii=False))
    except Exception as e:
        logger.warning("[QA] 缓存写入失败: %s", e)


# ---------------------------------------------------------------------------
# 监控写入
# ---------------------------------------------------------------------------

_MONITOR_KEY = "qa:monitor:records"
_MONITOR_MAX = 5000  # 最多保留最近 N 条


def _write_monitor(redis_client, record: dict) -> None:
    if redis_client is None:
        return
    try:
        import time as _time
        record["ts"] = _time.strftime("%Y-%m-%dT%H:%M:%SZ", _time.gmtime())
        redis_client.lpush(_MONITOR_KEY, json.dumps(record, ensure_ascii=False))
        redis_client.ltrim(_MONITOR_KEY, 0, _MONITOR_MAX - 1)
    except Exception as e:
        logger.warning("[QA] 监控写入失败: %s", e)


# ---------------------------------------------------------------------------
# JSON 解析工具
# ---------------------------------------------------------------------------

def _safe_parse_json(text: str) -> dict | None:
    """尽力解析 LLM 输出的 JSON，去除 markdown 代码块；支持首尾多余文字。"""
    if not text:
        return None
    s = text.strip()
    # 去除 ```json ... ``` 或 ``` ... ```（可多行）
    s = re.sub(r"^```(?:json)?\s*", "", s, count=1)
    s = re.sub(r"\s*```\s*$", "", s, count=1)
    s = s.strip()
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else None
    except json.JSONDecodeError:
        pass
    # 从首个 { 起用 raw_decode 解析单个对象（忽略尾部杂质）
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


# ---------------------------------------------------------------------------
# Firewall（直接调用 back_mic 的 firewall 模块）
# ---------------------------------------------------------------------------

def _ensure_backend_on_path() -> Path:
    """back_qa 运行时使 back_mic/backend 可被 import（kg_rag.firewall）。"""
    root = Path(__file__).resolve().parents[2]
    backend = root / "back_mic" / "backend"
    s = str(backend)
    if s not in sys.path:
        sys.path.insert(0, s)
    return backend


def _load_firewall():
    """加载防火墙数据（复用 back_mic kg_rag firewall）。"""
    try:
        _ensure_backend_on_path()
        from kg_rag.firewall import load_firewall, match_firewall
        load_firewall()
        return match_firewall
    except Exception as e:
        logger.warning("[QA] Firewall 加载失败，跳过: %s", e)
        return None


_match_firewall_fn = None  # 延迟初始化


async def _run_firewall(question: str) -> dict | None:
    """运行防火墙匹配，失败时静默返回 None。"""
    global _match_firewall_fn
    if _match_firewall_fn is None:
        _match_firewall_fn = _load_firewall()
    if _match_firewall_fn is None:
        return None
    try:
        return await _match_firewall_fn(question, _call_llm)
    except Exception as e:
        logger.warning("[QA] Firewall 执行失败: %s", e)
        return None


# ---------------------------------------------------------------------------
# Step 1：概念抽取
# ---------------------------------------------------------------------------

async def _detect_targeted(question: str) -> dict | None:
    """
    用 Haiku 轻量预判是否为定向查询。
    命中返回 {"book_keyword": "...", "message_keyword": "..."}，否则返回 None。
    失败时静默返回 None（降级为完整流水线）。
    """
    from back_qa.qa.prompts import TARGETED_DETECTION

    prompt = TARGETED_DETECTION.format(question=question)

    try:
        raw, _ = await _call_llm(
            prompt,
            STEP3_MODEL,  # Haiku
            temperature=0,
            max_tokens=128,
            system="你是一位书目专家，只输出 JSON，不输出其他任何内容。",
        )
    except Exception as e:
        logger.warning("[QA] 定向预判失败，降级为完整流水线: %s", e)
        return None

    parsed = _safe_parse_json(raw)
    if not parsed:
        logger.warning("[QA] 定向预判 JSON 解析失败，raw=%s", raw[:200])
        return None

    raw_targeted = parsed.get("targeted")
    if not isinstance(raw_targeted, dict):
        return None

    book_keyword = str(raw_targeted.get("book_keyword", "")).strip()
    message_keyword = str(raw_targeted.get("message_keyword", "")).strip()

    if book_keyword and message_keyword:
        logger.info("[QA] 定向预判命中 book=%s msg=%s", book_keyword, message_keyword)
        return {"book_keyword": book_keyword, "message_keyword": message_keyword}

    return None


async def _step1(question: str, neo4j_client, history: list[dict] | None = None) -> dict:
    """
    返回：{
        surface: list[str],
        deep: list[str],
        concepts: list[str],        # surface + deep 去重，供监控与前端展示
        greek_terms_context: str,
        key_verses_context: str,
        rewritten_query: str,
        cost_usd: float,
    }
    """
    from back_qa.qa.prompts import STEP1_CONCEPT_EXTRACTION

    history = history or []
    if history:
        recent = history[-3:]
        lines = [
            f"第{i + 1}轮：{t.get('question', '').strip()}"
            for i, t in enumerate(recent)
            if str(t.get("question", "")).strip()
        ]
        history_questions = (
            "对话历史（仅供理解追问上下文）：\n" + "\n".join(lines) + "\n" if lines else ""
        )
    else:
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
            prompt, STEP1_MODEL,
            temperature=0,
            max_tokens=512,
            system="你是一位深研圣经与职事文献的神学助手。请严格按要求的格式输出 JSON，不输出其他内容。",
        )
        cost = _calc_cost(STEP1_MODEL, usage)
    except Exception as e:
        logger.warning("[QA] Step1 LLM 失败，降级为空概念: %s", e)
        return {
            "surface": [], "deep": [], "concepts": [],
            "targeted": None,
            "reasoning": "",
            "greek_terms_context": "", "key_verses_context": "", "cost_usd": 0.0,
            "rewritten_query": question,
        }

    logger.info("[QA] Step1 raw_len=%d", len(raw or ""))
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

        # 解析定向查询
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
            "[QA] Step1 surface=%s deep=%s targeted=%s reasoning=%s",
            surface,
            deep,
            targeted,
            reasoning[:100],
        )
    else:
        logger.warning("[QA] Step1 JSON 解析失败，raw=%s", (raw or "")[:200])

    rw_raw = (parsed or {}).get("rewritten_query") if parsed else None
    if rw_raw is None or rw_raw == "":
        rewritten_query = ""
    else:
        rewritten_query = str(rw_raw).strip()
    if not rewritten_query:
        rewritten_query = question

    # concepts = surface + deep 去重，供前端展示
    seen = set()
    concepts = []
    for c in surface + deep:
        if c not in seen:
            seen.add(c)
            concepts.append(c)

    # 从 Neo4j 取 greek_terms 与 key_verses（用全部 concepts）
    greek_terms_context = ""
    key_verses_context = ""

    if concepts:
        try:
            greek_map = neo4j_client.get_greek_terms(concepts)
            if greek_map:
                lines = [f"- {c}：{g}" for c, g in greek_map.items()]
                greek_terms_context = "\n【相关原文参考】\n" + "\n".join(lines) + "\n"
        except Exception as e:
            logger.warning("[QA] get_greek_terms 失败: %s", e)

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
            logger.warning("[QA] get_key_verses 失败: %s", e)

    return {
        "surface": surface,
        "deep": deep,
        "concepts": concepts,
        "targeted": targeted,
        "reasoning": reasoning,
        "greek_terms_context": greek_terms_context,
        "key_verses_context": key_verses_context,
        "rewritten_query": rewritten_query,
        "cost_usd": cost,
    }


# ---------------------------------------------------------------------------
# Step 2：文献检索
# ---------------------------------------------------------------------------

async def _step2(
    rewritten_query: str,
    es_client,
    bm25_top_k: int | None = None,
    dense_top_k: int | None = None,
    rerank_top_n: int | None = None,
) -> list[dict]:
    """BM25 + Dense → RRF → Reranker，返回精排后段落列表。"""
    import back_shared.retrieval as retrieval

    index = QA_INDEX
    tk_bm25 = bm25_top_k if bm25_top_k is not None else BM25_TOP_K
    tk_dense = dense_top_k if dense_top_k is not None else DENSE_TOP_K
    tk_rerank = rerank_top_n if rerank_top_n is not None else RERANK_TOP_N

    bm25_task = retrieval.bm25_search(es_client, rewritten_query, index, top_k=tk_bm25)
    dense_task = retrieval.dense_search(es_client, rewritten_query, index, top_k=tk_dense)

    bm25_results, dense_results = await asyncio.gather(bm25_task, dense_task)
    logger.info("[QA] Step2 BM25=%d Dense=%d", len(bm25_results), len(dense_results))

    merged = await retrieval.rrf_merge(bm25_results, dense_results, k=RRF_K)
    reranked = await retrieval.rerank(merged, rewritten_query, top_n=tk_rerank)
    logger.info("[QA] Step2 reranked=%d", len(reranked))

    return reranked


async def _step2_with_expansion(
    rewritten_query: str,
    deep: list[str],
    es_client,
    bm25_top_k: int | None = None,
    dense_top_k: int | None = None,
    rerank_top_n: int | None = None,
    expansion_top_n: int | None = None,
) -> list[dict]:
    """
    主路检索 + deep 概念扩展检索并发。
    主路：改写检索句 BM25 + Dense → RRF → Reranker（Top 20）
    扩展路：对每个 deep 概念用「改写句 + 概念名」做独立检索，去重后追加
    """
    import back_shared.retrieval as retrieval

    index = QA_INDEX
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
        logger.warning("[QA] Step2 主路失败: %s", all_results[0])
    logger.info("[QA] Step2 主路=%d 段落", len(main_results))

    main_ids = {r.get("chunk_id") for r in main_results if r.get("chunk_id")}
    expanded: list[dict] = []
    for i, result in enumerate(all_results[1:]):
        if isinstance(result, Exception):
            logger.warning("[QA] 扩展检索失败 deep[%d]: %s", i, result)
            continue
        for doc in result:
            cid = doc.get("chunk_id")
            if cid and cid not in main_ids:
                expanded.append(doc)
                main_ids.add(cid)

    logger.info("[QA] Step2 扩展路=%d 段落（去重后）", len(expanded))
    return main_results + expanded


# 支持定向查询的索引（message_title 字段可靠）
_TARGETED_SUPPORTED_INDICES = {
    "kg-rag_cwwl",
    "kg-rag_life",
    "kg-rag_bib",
    "kg-rag_map_note",
    "kg-rag_others",
    "kg-rag_7feasts",
    "kg-rag_cwwn",
}

# 定向查询单篇段落数上限
_TARGETED_MAX_PASSAGES = 50


def _normalize_unit(s: str) -> str:
    """把篇章单位词统一去掉，只保留数字部分，用于精确匹配。
    注意：只去单位词，保留「第」字和数字，不做 strip 以免影响前缀匹配。
    """
    return (
        s.replace("章", "")
        .replace("篇", "")
        .replace("课", "")
        .replace("题", "")
        .replace("问", "")
    )


async def _step2_targeted(
    book_keyword: str,
    message_keyword: str,
    es_client,
) -> list[dict]:
    """
    定向精确查询，两步走：
    Step A：book_title match book_keyword，按 message_key 聚合（最多 500 个 key），
            每个 key 取一个 message_title，Python 层过滤匹配篇/章号，得到 message_key
    Step B：term message_key 精确取出该章/篇所有段落（上限 50 条）
    返回空列表时调用方降级为语义检索。
    """
    target_indices = ",".join(_TARGETED_SUPPORTED_INDICES)

    # Step A：找 message_key（聚合，避免被 size 截断漏掉靠后的篇）
    body_a = {
        "query": {"match": {"book_title": book_keyword}},
        "size": 0,
        "aggs": {
            "by_message_key": {
                "terms": {"field": "message_key", "size": 500},
                "aggs": {
                    "title": {
                        "terms": {"field": "message_title", "size": 1}
                    }
                },
            }
        },
    }

    try:
        resp_a = await asyncio.to_thread(
            es_client.search, index=target_indices, body=body_a
        )
    except Exception as e:
        logger.warning("[QA] 定向查询 Step A 失败: %s", e)
        return []

    # 从聚合结果里解析所有 message_key + message_title
    buckets = (resp_a.get("aggregations") or {}).get("by_message_key", {}).get("buckets") or []

    normalized_keyword = _normalize_unit(message_keyword)
    message_key = None
    for bucket in buckets:
        mk = bucket.get("key", "")
        # 取该 message_key 下的第一个 message_title
        title_buckets = bucket.get("title", {}).get("buckets") or []
        msg_title = title_buckets[0].get("key", "") if title_buckets else ""
        # 截到「篇/章/课」为止，去掉副标题，再与 message_keyword 归一化比较
        msg_title_for_match = re.sub(
            r"([篇章课]).*$", r"\1", (msg_title or "").strip()
        )
        normalized_title = _normalize_unit(msg_title_for_match)
        if normalized_keyword and (
            normalized_title == normalized_keyword
            or normalized_title.startswith(normalized_keyword + "\u3000")
            or normalized_title.startswith(normalized_keyword + " ")
            or normalized_title.startswith(normalized_keyword + "　")
        ):
            message_key = mk
            logger.info(
                "[QA] 定向查询 Step A 命中 message_key=%s title=%s",
                message_key,
                msg_title,
            )
            break

    if not message_key:
        logger.info(
            "[QA] 定向查询 Step A 未找到匹配的 message_key，book=%s msg=%s",
            book_keyword,
            message_keyword,
        )
        # 兜底：message_title 未命中时，尝试在 book_title 里匹配 message_keyword
        logger.info("[QA] 定向查询 Step A 兜底：尝试从 book_title 匹配 message_keyword")
        try:
            resp_fallback = await asyncio.to_thread(
                es_client.search,
                index=target_indices,
                body={
                    "size": 1,
                    "query": {
                        "wildcard": {
                            "book_title": {
                                "value": f"*{book_keyword}*{message_keyword}*"
                            }
                        }
                    },
                    "_source": ["message_key", "message_title", "book_title"],
                },
            )
            fallback_hits = (resp_fallback.get("hits") or {}).get("hits") or []
            if fallback_hits:
                src = fallback_hits[0].get("_source") or {}
                message_key = src.get("message_key", "")
                logger.info(
                    "[QA] 定向查询 Step A 兜底命中 message_key=%s book_title=%s",
                    message_key,
                    src.get("book_title", ""),
                )
        except Exception as e:
            logger.warning("[QA] 定向查询 Step A 兜底失败: %s", e)

    if not message_key:
        return []

    # Step B：用 message_key 精确取出所有段落
    body_b = {
        "query": {"term": {"message_key": message_key}},
        "size": _TARGETED_MAX_PASSAGES,
        "_source": [
            "chunk_id", "text", "book_title", "author",
            "source_zh", "message_number", "message_title",
            "section_title", "paragraph_type", "tokens",
            "en", "source_en",
        ],
    }

    try:
        resp_b = await asyncio.to_thread(
            es_client.search, index=target_indices, body=body_b
        )
    except Exception as e:
        logger.warning("[QA] 定向查询 Step B 失败: %s", e)
        return []

    hits_b = (resp_b.get("hits") or {}).get("hits") or []
    results = []
    for hit in hits_b:
        src = (hit.get("_source") or {}).copy()
        src["score"] = float(hit.get("_score") or 0.0)
        src["source"] = "targeted"
        src["_index"] = hit.get("_index") or ""
        src.setdefault("chunk_id", hit.get("_id", ""))
        results.append(src)

    logger.info("[QA] 定向查询 Step B message_key=%s 命中=%d 段",
                message_key, len(results))
    return results


# ---------------------------------------------------------------------------
# Step 3：相关性判断
# ---------------------------------------------------------------------------

async def _step3(rewritten_query: str, passages: list[dict]) -> tuple[bool, float]:
    """
    返回 (relevant: bool, cost_usd: float)。
    relevant=False 时调用方写入 step_fail_stage 监控并返回「未找到」。
    """
    from back_qa.qa.prompts import STEP3_RELEVANCE_CHECK

    # 构建段落摘要（每段最多 200 字）
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
        logger.warning("[QA] Step3 LLM 失败，默认 relevant=True: %s", e)
        return True, 0.0

    parsed = _safe_parse_json(raw)
    if parsed is None:
        logger.warning("[QA] Step3 JSON 解析失败，默认 relevant=True，raw=%s", raw[:200])
        logger.info("[QA] Step3 relevant=True reason=(parse_fallback)")
        return True, cost

    relevant = bool(parsed.get("relevant", True))
    logger.info("[QA] Step3 relevant=%s reason=%s", relevant, parsed.get("reason", ""))
    return relevant, cost


def _build_history_context(history: list[dict]) -> str:
    """取最近 3 轮问答格式化为 Step4 历史块；history 为空返回空串。"""
    if not history:
        return ""
    from back_qa.qa.prompts import HISTORY_CONTEXT_TEMPLATE, HISTORY_TURN_TEMPLATE

    recent = history[-3:]
    turns: list[str] = []
    idx = 0
    for turn in recent:
        q = str(turn.get("question", "")).strip()
        a = str(turn.get("answer", "")).strip()
        if not q and not a:
            continue
        idx += 1
        turns.append(
            HISTORY_TURN_TEMPLATE.format(idx=idx, question=q, answer=a)
        )
    if not turns:
        return ""
    count = len(turns)
    return HISTORY_CONTEXT_TEMPLATE.format(count=count, turns="\n".join(turns))


# ---------------------------------------------------------------------------
# Step 4：答案生成
# ---------------------------------------------------------------------------

def _step4_build_prompt(
    question: str,
    passages: list[dict],
    greek_terms_context: str,
    key_verses_context: str,
    firewall_doc: dict | None,
    history_context: str = "",
) -> str:
    """构建 Step4 发给 Claude 的 user prompt（不含 LLM 调用）。"""
    from back_qa.qa.prompts import STEP4_ANSWER_GENERATION, FIREWALL_INSTRUCTION

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

    firewall_instruction = ""
    if firewall_doc:
        firewall_instruction = FIREWALL_INSTRUCTION.format(
            fw_title=firewall_doc.get("title", ""),
            fw_note=firewall_doc.get("note", ""),
            fw_full_text=firewall_doc.get("full_text", ""),
        )

    return STEP4_ANSWER_GENERATION.format(
        history_context=history_context or "",
        question=question,
        passages=passages_text,
        greek_context=greek_terms_context,
        verse_context=key_verses_context,
        firewall_instruction=firewall_instruction,
    )


def _step4_build_prompt_en(
    question: str,
    passages: list[dict],
    greek_terms_context: str,
    key_verses_context: str,
    firewall_doc: dict | None,
    history_context: str = "",
) -> str:
    """构建 Step4 英文版 user prompt。结构与中文版完全相同，仅替换 header / 模板。"""
    from back_qa.qa.prompts import (
        STEP4_ANSWER_GENERATION_EN,
        FIREWALL_INSTRUCTION_EN,
    )

    passage_lines = []
    for p in passages:
        text = (p.get("text") or "").strip()
        source_en_raw = (p.get("source_en") or p.get("source_zh") or "").strip()
        # 与中文版同样的段号清理（去掉「，第X段/节...」尾巴和外层括号）
        source_en_clean = re.sub(
            r"，第[零一二三四五六七八九十百千]+[段节].*$",
            "",
            source_en_raw,
        ).strip()
        source_en_clean = source_en_clean.strip("（）()").strip()
        header = f"[Source: {source_en_clean}]"
        passage_lines.append(f"{header}\n{text}")
    passages_text = "\n---\n".join(passage_lines)

    firewall_instruction = ""
    if firewall_doc:
        firewall_instruction = FIREWALL_INSTRUCTION_EN.format(
            fw_title=firewall_doc.get("title", ""),
            fw_note=firewall_doc.get("note", ""),
            fw_full_text=firewall_doc.get("full_text", ""),
        )

    return STEP4_ANSWER_GENERATION_EN.format(
        history_context=history_context or "",
        question=question,
        passages=passages_text,
        greek_context=greek_terms_context,
        verse_context=key_verses_context,
        firewall_instruction=firewall_instruction,
    )


def _extract_step4_sources(raw: str) -> list[str]:
    """从 Step4 原始输出中提取【引用书目】列表（保留编号；按书名去重）。"""
    sources: list[str] = []
    if "【引用书目】" not in raw:
        return sources
    bib_block = raw.split("【引用书目】", 1)[1]
    seen: set[str] = set()
    for line in bib_block.splitlines():
        line = line.strip()
        if not line:
            continue
        # 兼容有无 ➡️（旧缓存可能仍带符号）
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


def _extract_references(answer: str) -> list[str]:
    """从英文 Step4 答案里提取 [References] 块。
    返回 ["1 Life-Study of Samuel, msg. 34", ...] 样式，按书名去重保留编号。
    """
    sources: list[str] = []
    if "[References]" not in answer:
        return sources
    bib_block = answer.split("[References]", 1)[1]
    seen: set[str] = set()
    for line in bib_block.splitlines():
        line = line.strip()
        if not line:
            continue
        if not re.match(r"^\d+", line):
            continue
        key = re.sub(r"^\d+[\.\s]+", "", line).strip()
        if key and key not in seen:
            seen.add(key)
            sources.append(line)
    return sources


def _translation_cache_key(zh_cache_key: str, lang: str) -> str:
    """zh 缓存 key 加 lang 后缀，与 zh 缓存隔离。"""
    return f"{zh_cache_key}:{lang}"


async def _translate_question_to_english(question: str) -> str:
    """用 Gemini 把用户问题翻译成英文，失败时返回原文。"""
    q = (question or "").strip()
    if not q:
        return q
    try:
        from back_qa.qa.translation_service import _gemini_translate
        return await asyncio.to_thread(_gemini_translate, q)
    except Exception as e:
        logger.warning("[QA] question 翻译失败，回退原文: %s", e)
        return q


async def _step4(
    question: str,
    passages: list[dict],
    greek_terms_context: str,
    key_verses_context: str,
    firewall_doc: dict | None,
    history_context: str = "",
) -> tuple[str, list[str], float]:
    """
    返回 (answer: str, sources: list[str], cost_usd: float)。
    sources 从答案中的【引用书目】块提取。
    """
    prompt = _step4_build_prompt(
        question,
        passages,
        greek_terms_context,
        key_verses_context,
        firewall_doc,
        history_context=history_context,
    )

    global _last_step4_prompt
    _last_step4_prompt = prompt

    raw, usage = await _call_llm(
        prompt, STEP4_MODEL,
        temperature=0.3,
        max_tokens=4096,
        system="你是一位职事信息问答助手，严格基于所提供的段落作答。回答要有清晰的主线，用原文支撑论述，不编造，不拼凑。",
    )
    cost = _calc_cost(STEP4_MODEL, usage)
    sources = _extract_step4_sources(raw)
    return raw.strip(), sources, cost


async def _run_pipeline_until_step4(
    question: str,
    skip_cache: bool,
    request_id: str,
    app: Any,
    history: list[dict],
    debug: bool,
    debug_params: dict | None,
    lang: str = "zh",
) -> tuple[dict | None, dict | None]:
    """
    缓存检查、定向/Step1-2-3、Firewall await，直到 Step4 之前。
    返回 (early_result, ctx)：early 非空则直接作为最终响应；ctx 非空则进入 Step4。
    """
    start = time.monotonic()

    from back_qa.qa.dependencies import get_es_client, get_redis_client

    neo4j_client = app.state.neo4j_client
    es_client = get_es_client()
    redis_client = get_redis_client()

    cache_key = _make_cache_key(question, history)
    if not skip_cache:
        cached = _read_cache(redis_client, cache_key)
        if cached:
            logger.info("[QA] 缓存命中 request_id=%s", request_id)
            cached["cache_hit"] = True
            cached["request_id"] = request_id
            _write_monitor(redis_client, {
                "request_id": request_id,
                "question": question,
                "cache_hit": True,
                "found": cached.get("found", False),
            })
            return cached, None

    _bm25_top_k = BM25_TOP_K
    _dense_top_k = DENSE_TOP_K
    _rerank_top_n = RERANK_TOP_N
    _expansion_top_n = 5
    if debug_params:
        _bm25_top_k = int(debug_params.get("bm25_top_k", BM25_TOP_K))
        _dense_top_k = int(debug_params.get("dense_top_k", DENSE_TOP_K))
        _rerank_top_n = int(debug_params.get("rerank_top_n", RERANK_TOP_N))
        _expansion_top_n = int(debug_params.get("expansion_top_n", 5))

    total_cost = 0.0

    if os.environ.get("QA_SKIP_TARGETED") == "1":
        precheck_targeted = None
    else:
        precheck_targeted = await _detect_targeted(question)
    targeted = precheck_targeted

    passages: list[dict] = []
    is_targeted = False
    concepts: list = []
    greek_terms_context = ""
    key_verses_context = ""
    firewall_task = None
    step1_snapshot: dict | None = None
    rewritten_query = question

    if targeted:
        try:
            targeted_passages = await _step2_targeted(
                targeted["book_keyword"],
                targeted["message_keyword"],
                es_client,
            )
            if targeted_passages:
                passages = targeted_passages
                is_targeted = True
                logger.info("[QA] 使用定向查询，共 %d 段", len(passages))
            else:
                logger.info("[QA] 定向查询无结果，降级为完整流水线")
                targeted = None
        except Exception as e:
            logger.warning("[QA] 定向查询异常，降级为完整流水线: %s", e)
            targeted = None

    if not is_targeted:
        step1_task = asyncio.create_task(_step1(question, neo4j_client, history=history))
        firewall_task = asyncio.create_task(_run_firewall(question))

        step1_result = await step1_task
        step1_snapshot = step1_result
        total_cost += step1_result["cost_usd"]
        concepts = step1_result["concepts"]
        deep = step1_result["deep"]
        greek_terms_context = step1_result["greek_terms_context"]
        key_verses_context = step1_result["key_verses_context"]
        rw = step1_result.get("rewritten_query")
        rewritten_query = str(rw).strip() if rw else ""
        if not rewritten_query:
            rewritten_query = question

        try:
            passages = await _step2_with_expansion(
                rewritten_query,
                deep,
                es_client,
                bm25_top_k=_bm25_top_k,
                dense_top_k=_dense_top_k,
                rerank_top_n=_rerank_top_n,
                expansion_top_n=_expansion_top_n,
            )
        except Exception as e:
            logger.error("[QA] Step2 检索失败: %s", e)
            passages = []

    if is_targeted:
        relevant = True
        step3_cost = 0.0
        logger.info("[QA] 定向查询，跳过 Step3")
    else:
        relevant, step3_cost = await _step3(rewritten_query, passages)
    total_cost += step3_cost

    if not relevant:
        if firewall_task is not None:
            firewall_task.cancel()
            try:
                await firewall_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        elapsed = int((time.monotonic() - start) * 1000)
        _write_monitor(redis_client, {
            "request_id": request_id,
            "question": question,
            "cache_hit": False,
            "found": False,
            "step_fail_stage": "step3",
            "total_elapsed_ms": elapsed,
            "total_cost_usd": round(total_cost, 4),
        })
        result = {
            "request_id": request_id,
            "answer": "以下内容未能在职事信息中找到相关依据。",
            "sources": [],
            "concepts": concepts,
            "found": False,
            "cache_hit": False,
            "total_elapsed_ms": elapsed,
            "total_cost_usd": round(total_cost, 4),
        }
        if debug:
            result["debug"] = {
                "targeted": precheck_targeted,
                "surface": (step1_snapshot or {}).get("surface", []) if not is_targeted else [],
                "deep": (step1_snapshot or {}).get("deep", []) if not is_targeted else [],
                "reasoning": (step1_snapshot or {}).get("reasoning", "") if not is_targeted else "",
                "rewritten_query": rewritten_query,
                "firewall": None,
                "step4_prompt": "",
                "retrieved_chunks": [p.get("chunk_id", "") for p in (passages or [])],
            }
        if not debug:
            _write_cache(redis_client, cache_key, result)
        return result, None

    firewall_doc = None
    if not is_targeted and firewall_task is not None:
        firewall_doc = await firewall_task

    history_context = _build_history_context(history)
    ctx = {
        "start": start,
        "question": question,
        "rewritten_query": rewritten_query,
        "passages": passages,
        "greek_terms_context": greek_terms_context,
        "key_verses_context": key_verses_context,
        "firewall_doc": firewall_doc,
        "history_context": history_context,
        "concepts": concepts,
        "total_cost": total_cost,
        "cache_key": cache_key,
        "redis_client": redis_client,
        "request_id": request_id,
        "precheck_targeted": precheck_targeted,
        "is_targeted": is_targeted,
        "step1_snapshot": step1_snapshot,
        "debug": debug,
        "debug_params": debug_params,
    }
    return None, ctx


async def _iter_step4_stream_tokens(prompt: str) -> AsyncGenerator[tuple[str, Any], None]:
    """
    使用 AsyncAnthropic messages.stream，产出 ("token", text) 与末尾 ("usage", usage|None)。
    """
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
        logger.error("[QA] Step4 stream 失败: %s", e)
        yield ("error", str(e))


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------

async def run_pipeline(
    question: str,
    skip_cache: bool,
    request_id: str,
    app,
    debug: bool = False,
    debug_params: dict | None = None,
    history: list[dict] | None = None,
    lang: str = "zh",
) -> dict:
    """四步流水线主入口。lang 当前仅由 /stream 落地翻译；/query 非流式接受参数但不做翻译后处理。"""
    history = history or []

    early, ctx = await _run_pipeline_until_step4(
        question, skip_cache, request_id, app, history, debug, debug_params, lang=lang
    )
    if early is not None:
        return early
    assert ctx is not None

    start = ctx["start"]
    total_cost = float(ctx["total_cost"])
    question = ctx["question"]
    passages = ctx["passages"]
    greek_terms_context = ctx["greek_terms_context"]
    key_verses_context = ctx["key_verses_context"]
    firewall_doc = ctx["firewall_doc"]
    history_context = ctx["history_context"]
    concepts = ctx["concepts"]
    cache_key = ctx["cache_key"]
    redis_client = ctx["redis_client"]
    precheck_targeted = ctx["precheck_targeted"]
    is_targeted = ctx["is_targeted"]
    step1_snapshot = ctx["step1_snapshot"]
    rewritten_query = ctx.get("rewritten_query", question)

    try:
        answer, sources, step4_cost = await _step4(
            question,
            passages,
            greek_terms_context,
            key_verses_context,
            firewall_doc,
            history_context=history_context,
        )
        total_cost += step4_cost
    except Exception as e:
        logger.error("[QA] Step4 生成失败: %s", e)
        answer = "答案生成失败，请稍后重试。"
        sources = []

    elapsed = int((time.monotonic() - start) * 1000)

    result = {
        "request_id": request_id,
        "answer": answer,
        "sources": sources,
        "concepts": concepts,
        "found": True,
        "cache_hit": False,
        "total_elapsed_ms": elapsed,
        "total_cost_usd": round(total_cost, 4),
    }

    if debug:
        result["debug"] = {
            "targeted": precheck_targeted,
            "surface": (step1_snapshot or {}).get("surface", []) if not is_targeted else [],
            "deep": (step1_snapshot or {}).get("deep", []) if not is_targeted else [],
            "reasoning": (step1_snapshot or {}).get("reasoning", "") if not is_targeted else "",
            "rewritten_query": rewritten_query,
            "firewall": firewall_doc,
            "step4_prompt": _last_step4_prompt,
            "retrieved_chunks": [p.get("chunk_id", "") for p in (passages or [])],
        }

    if not debug:
        _write_cache(redis_client, cache_key, result)
    _write_monitor(redis_client, {
        "request_id": request_id,
        "question": question,
        "cache_hit": False,
        "found": True,
        "total_elapsed_ms": elapsed,
        "total_cost_usd": round(total_cost, 4),
    })

    return result


async def translate_answer(
    text: str,
    sources: list[str],
    target_lang: str,
    question: str = "",
) -> dict[str, Any]:
    """按需翻译已生成的简体答案（供 /api/qa/translate 兜底接口使用）。

    与 stream_query 内的 _emit_translation_events 不同：
    - 这里不重跑 Step 4，只做文本翻译（无 passages 可用）
    - zh_tw 走 OpenCC + 术语表
    - en 走 Gemini，并发翻译 body / 每条 source / question

    返回 {"answer": str, "sources": list[str]}。任何环节失败抛异常由路由层转 500。
    """
    text = text or ""
    sources = list(sources or [])
    target_lang = (target_lang or "").strip().lower()
    if target_lang not in ("zh_tw", "en"):
        raise ValueError(f"unsupported target_lang: {target_lang}")

    if target_lang == "zh_tw":
        from back_qa.qa.translation_service import to_traditional
        # 剥离 【引用书目】 及之后的书目块，仅转换正文；书目走 translated_sources 单独转换，
        # 避免前端 renderAnswer 因 marker 被一起繁化而切分失败导致重复渲染。
        body_text = text or ""
        if "【引用书目】" in body_text:
            body_text = body_text.split("【引用书目】", 1)[0].rstrip()
        translated_answer = await asyncio.to_thread(to_traditional, body_text)
        translated_sources = await asyncio.to_thread(
            lambda src: [to_traditional(s) for s in src],
            sources,
        )
        logger.info("[QA] /translate zh_tw 完成 chars=%d sources=%d",
                    len(translated_answer), len(translated_sources))
        return {"answer": translated_answer, "sources": translated_sources}

    # ---- target_lang == "en" ----
    from back_qa.qa.translation_service import _gemini_translate

    # 1. 拆出正文（去掉 【引用书目】 / [References] 块），书目走单独翻译
    body = text
    if "【引用书目】" in body:
        body = body.split("【引用书目】", 1)[0]
    if "[References]" in body:
        body = body.split("[References]", 1)[0]
    body = body.strip()

    # 2. 并发翻译：body / 每条 source / question
    async def _translate_one(s: str) -> str:
        if not (s or "").strip():
            return s or ""
        try:
            return await asyncio.to_thread(_gemini_translate, s)
        except Exception as e:
            logger.warning("[QA] /translate source 翻译失败，保留中文: %s", e)
            return s

    body_task = asyncio.to_thread(_gemini_translate, body) if body else asyncio.sleep(0, result="")
    sources_task = asyncio.gather(*[_translate_one(s) for s in sources])
    question_task = _translate_question_to_english(question or "")

    translated_body, translated_sources, translated_question = await asyncio.gather(
        body_task, sources_task, question_task
    )
    translated_body = (translated_body or "").strip()
    translated_sources = list(translated_sources or [])

    # 3. 拼接答案：body + [References] block，与 stream_query en 路径输出格式保持一致
    if translated_sources:
        translated_answer = (
            translated_body + "\n\n[References]\n" + "\n".join(translated_sources)
        )
    else:
        translated_answer = translated_body

    logger.info(
        "[QA] /translate en 完成 body_chars=%d sources=%d question_en=%s",
        len(translated_body), len(translated_sources),
        (translated_question or "")[:80],
    )
    return {"answer": translated_answer, "sources": translated_sources}


async def _emit_translation_events(
    *,
    lang: str,
    zh_cache_key: str,
    redis_client,
    answer_zh: str,
    sources_zh: list[str],
    question_zh: str,
    passages: list[dict] | None,
    greek_terms_context: str,
    key_verses_context: str,
    firewall_doc: dict | None,
    history_context: str,
    skip_cache: bool,
) -> AsyncGenerator[dict[str, Any], None]:
    """根据 lang 生成 translation 事件流。命中 {zh_cache_key}:{lang} 缓存直接回放；
    否则现场翻译/重生成并写入翻译缓存。失败时只记日志，不抛错。

    - zh_tw：基于 answer_zh / sources_zh 直接做简繁转换，不依赖 passages。
    - en：需要 passages（来自完整流水线）才能重跑英文版 Step4；缓存命中除外。
    """
    if lang not in ("zh_tw", "en"):
        return

    tr_key = _translation_cache_key(zh_cache_key, lang)

    # 翻译缓存命中直接回放
    if not skip_cache:
        cached_tr = _read_cache(redis_client, tr_key)
        if cached_tr and isinstance(cached_tr, dict):
            yield {
                "type": "translation",
                "lang": lang,
                "answer": cached_tr.get("answer", ""),
                "sources": list(cached_tr.get("sources", []) or []),
                "cache_hit": True,
            }
            return

    if lang == "zh_tw":
        try:
            from back_qa.qa.translation_service import to_traditional
            # 分离正文与书目块：避免转换后「【引用书目】→【引用書目】」让前端 renderAnswer
            # 的简体 marker 切分失败，导致书目在 body 与 displaySources 中各渲染一份。
            body_zh = answer_zh or ""
            if "【引用书目】" in body_zh:
                body_zh = body_zh.split("【引用书目】", 1)[0].rstrip()
            translated_answer = await asyncio.to_thread(to_traditional, body_zh)
            translated_sources = await asyncio.to_thread(
                lambda src: [to_traditional(s) for s in src],
                sources_zh,
            )
        except Exception as e:
            logger.warning("[QA] zh_tw 翻译失败: %s", e)
            return
        payload = {"answer": translated_answer, "sources": translated_sources}
        try:
            _write_cache(redis_client, tr_key, payload)
        except Exception as e:
            logger.warning("[QA] 翻译缓存写入失败: %s", e)
        yield {
            "type": "translation",
            "lang": "zh_tw",
            "answer": translated_answer,
            "sources": translated_sources,
            "cache_hit": False,
        }
        return

    # lang == "en"：需要 passages
    if not passages:
        logger.warning(
            "[QA] en 翻译路径缺少 passages（疑似 zh 缓存命中无法重生成英文答案），跳过 translation 事件"
        )
        return

    try:
        from back_qa.qa.translation_service import prepare_english_chunks
        english_passages, has_translation = await asyncio.to_thread(
            prepare_english_chunks, passages
        )
        en_question = await _translate_question_to_english(question_zh)

        en_prompt = _step4_build_prompt_en(
            question=en_question,
            passages=english_passages,
            greek_terms_context=greek_terms_context,
            key_verses_context=key_verses_context,
            firewall_doc=firewall_doc,
            history_context=history_context,
        )

        client = _get_async_claude_client()
        kwargs: dict[str, Any] = dict(
            model=STEP4_MODEL,
            max_tokens=4096,
            messages=[{"role": "user", "content": en_prompt}],
            system=(
                "You are a ministry Q&A assistant. Answer strictly based on the provided "
                "passages. Quote original text directly; do not fabricate or stitch."
            ),
        )
        if not STEP4_MODEL.startswith("claude-opus-4-7"):
            kwargs["temperature"] = 0.3
        en_message = await client.messages.create(**kwargs)
        en_answer = _claude_message_text(en_message).strip()
        if not en_answer:
            logger.warning("[QA] en 重生成返回空文本，跳过 translation 事件")
            return
        en_sources = _extract_references(en_answer)
    except Exception as e:
        logger.warning("[QA] en 翻译/重生成失败: %s", e, exc_info=True)
        return

    payload = {"answer": en_answer, "sources": en_sources}
    try:
        _write_cache(redis_client, tr_key, payload)
    except Exception as e:
        logger.warning("[QA] 翻译缓存写入失败: %s", e)
    logger.info(
        "[QA] en 翻译完成 has_translation=%s en_sources=%d", has_translation, len(en_sources)
    )
    yield {
        "type": "translation",
        "lang": "en",
        "answer": en_answer,
        "sources": en_sources,
        "cache_hit": False,
    }


async def stream_query(
    question: str,
    skip_cache: bool,
    request_id: str,
    app: Any,
    history: list[dict] | None = None,
    debug: bool = False,
    debug_params: dict | None = None,
    lang: str = "zh",
) -> AsyncGenerator[dict[str, Any], None]:
    """
    流式问答：Steps 0-3 与 run_pipeline 相同；Step4 使用 Claude stream。
    yield: step / token / done / translation / error

    lang != "zh" 时，主答案仍以简体生成并通过 done 事件返回；之后再追加一个 translation
    事件，data 形如 {"lang": ..., "answer": ..., "sources": [...]}。
    """
    history = history or []

    early, ctx = await _run_pipeline_until_step4(
        question, skip_cache, request_id, app, history, debug, debug_params, lang=lang
    )
    zh_cache_key = _make_cache_key(question, history)

    if early is not None:
        yield {
            "type": "done",
            "answer": early.get("answer", ""),
            "sources": early.get("sources", []),
            "found": bool(early.get("found", False)),
            "cache_hit": bool(early.get("cache_hit", False)),
            "concepts": early.get("concepts", []),
            "elapsed_ms": int(early.get("total_elapsed_ms", 0)),
            "cost": float(early.get("total_cost_usd", 0.0)),
            "request_id": early.get("request_id", request_id),
        }
        if lang != "zh" and bool(early.get("found", False)):
            from back_qa.qa.dependencies import get_redis_client
            async for tr_event in _emit_translation_events(
                lang=lang,
                zh_cache_key=zh_cache_key,
                redis_client=get_redis_client(),
                answer_zh=early.get("answer", ""),
                sources_zh=list(early.get("sources", []) or []),
                question_zh=question,
                passages=None,
                greek_terms_context="",
                key_verses_context="",
                firewall_doc=None,
                history_context="",
                skip_cache=skip_cache,
            ):
                yield tr_event
        return

    assert ctx is not None
    start = ctx["start"]
    total_cost = float(ctx["total_cost"])
    q = ctx["question"]
    passages = ctx["passages"]
    greek_terms_context = ctx["greek_terms_context"]
    key_verses_context = ctx["key_verses_context"]
    firewall_doc = ctx["firewall_doc"]
    history_context = ctx["history_context"]
    concepts = ctx["concepts"]
    cache_key = ctx["cache_key"]
    redis_client = ctx["redis_client"]
    precheck_targeted = ctx["precheck_targeted"]
    is_targeted = ctx["is_targeted"]
    step1_snapshot = ctx["step1_snapshot"]
    rewritten_query = ctx.get("rewritten_query", q)

    yield {
        "type": "step",
        "stage": "step1",
        "data": {
            "skipped": is_targeted,
            "concept_count": len(concepts) if concepts else 0,
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
        firewall_doc,
        history_context=history_context,
    )
    global _last_step4_prompt
    _last_step4_prompt = prompt

    full_text = ""
    step4_usage = None
    async for item in _iter_step4_stream_tokens(prompt):
        if isinstance(item, tuple) and len(item) == 2 and item[0] == "error":
            yield {"type": "error", "message": str(item[1])}
            return
        kind, payload = item
        if kind == "token":
            full_text += payload
            yield {"type": "token", "text": payload}
        elif kind == "usage":
            step4_usage = payload

    step4_cost = _calc_cost(STEP4_MODEL, step4_usage)
    total_cost += step4_cost
    sources = _extract_step4_sources(full_text)
    answer = full_text.strip()
    if not answer:
        answer = "答案生成失败，请稍后重试。"
        sources = []

    elapsed = int((time.monotonic() - start) * 1000)

    result = {
        "request_id": request_id,
        "answer": answer,
        "sources": sources,
        "concepts": concepts,
        "found": True,
        "cache_hit": False,
        "total_elapsed_ms": elapsed,
        "total_cost_usd": round(total_cost, 4),
    }
    if debug:
        result["debug"] = {
            "targeted": precheck_targeted,
            "surface": (step1_snapshot or {}).get("surface", []) if not is_targeted else [],
            "deep": (step1_snapshot or {}).get("deep", []) if not is_targeted else [],
            "reasoning": (step1_snapshot or {}).get("reasoning", "") if not is_targeted else "",
            "rewritten_query": rewritten_query,
            "firewall": firewall_doc,
            "step4_prompt": _last_step4_prompt,
            "retrieved_chunks": [p.get("chunk_id", "") for p in (passages or [])],
        }

    if not debug:
        _write_cache(redis_client, cache_key, result)
    _write_monitor(redis_client, {
        "request_id": request_id,
        "question": q,
        "cache_hit": False,
        "found": True,
        "total_elapsed_ms": elapsed,
        "total_cost_usd": round(total_cost, 4),
    })

    yield {
        "type": "done",
        "answer": answer,
        "sources": sources,
        "found": True,
        "cache_hit": False,
        "concepts": concepts,
        "elapsed_ms": elapsed,
        "cost": round(total_cost, 4),
        "request_id": request_id,
    }

    if lang != "zh":
        async for tr_event in _emit_translation_events(
            lang=lang,
            zh_cache_key=cache_key,
            redis_client=redis_client,
            answer_zh=answer,
            sources_zh=list(sources or []),
            question_zh=q,
            passages=passages,
            greek_terms_context=greek_terms_context,
            key_verses_context=key_verses_context,
            firewall_doc=firewall_doc,
            history_context=history_context,
            skip_cache=skip_cache,
        ):
            yield tr_event
