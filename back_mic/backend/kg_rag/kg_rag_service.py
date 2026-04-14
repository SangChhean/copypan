# -*- coding: utf-8 -*-
"""KgRagService：编排 Step 1→5 全流程与检索/预览。"""
import asyncio
import hashlib
import json
import logging
import os
from pathlib import Path
from collections.abc import Callable
from typing import Any, Optional

logger = logging.getLogger("kg_rag")

# 确保可导入 ai_search（Claude 客户端）、retrieval、prompts
try:
    from ai_search.ai_service import claude_client
except ImportError:
    _backend = str(Path(__file__).resolve().parents[1])
    if _backend not in __import__("sys").path:
        __import__("sys").path.insert(0, _backend)
    try:
        from ai_search.ai_service import claude_client
    except ImportError:
        claude_client = None

from kg_rag.prompts import (
    STEP1_CONCEPT_EXTRACTION,
    FIREWALL_INSTRUCTION,
    STEP2_SKELETON_BUILD,
    QUERY_REWRITE,
    STEP5_GENERATION,
    STEP5_GENERATION_FLAT,
)

# QUERY_REWRITE 调用时传入 Claude 的 system，与 prompts 中说明一致
QUERY_REWRITE_SYSTEM = "你是一个资深的圣经研究学者，只输出 JSON，不输出其他任何内容。"
from kg_rag.firewall import match_firewall
from kg_rag.llm_pricing import pack_llm_usage_response, register_llm_usage


def _finalize_llm_usage(
    llm_calls: list[dict[str, Any]],
    pipeline_start: float,
    step_elapsed_ms: dict[str, float],
) -> dict[str, Any]:
    """为全流程响应附加各 LLM 步耗时与总墙钟耗时（秒表时间，含网络等待）。"""
    total_ms = (asyncio.get_event_loop().time() - pipeline_start) * 1000
    return pack_llm_usage_response(
        llm_calls,
        step_elapsed_ms=step_elapsed_ms,
        total_elapsed_ms=total_ms,
    )
from kg_rag.retrieval import (
    bm25_search,
    dense_search,
    rrf_merge,
    rerank,
    skeleton_route_search,
)

DEFAULT_PARAMS = {
    "bm25_top_k": 30,
    "dense_top_k": 0,  # 0：按 bm25_top_k / dense 路数动态计算每路 top_k；>0 则强制使用该值
    "num_candidates": 100,
    "rrf_k": 60,
    "bm25_weight": 1.0,
    "dense_weight": 1.0,
    "rerank_top_n": 20,
    "skeleton_route_top_k": 5,
    "skeleton_route_max_per_node": 2,  # 路3 每扩展节点去重后并入 expanded_results 的条数上限
    "temperature": 0.3,
    "skip_query_rewrite": False,
    "skip_skeleton_route": False,
    "skip_generation": False,
    "llm_model": os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6"),
    "step1_model": "",  # 空字符串表示与 llm_model 相同
    "stop_after_step1": False,
    "stop_after_step2": False,  # True 时在 Step2 完成后返回（需与 stop_after_step1 互斥）
    "outline_nature": "一般性",  # 一般性 / 高真理浓度 / 高生命浓度 / 重实行应用
    "burden_description": "",  # 负担说明（可选）
    "audience": "",  # 面对对象（可选）
    "depth": "general",  # general / deep；deep 时可触发检索参数预设（见 full_query）
    "skip_cache": False,  # True 时跳过缓存读取（强制重跑），但仍写入缓存
}

CACHE_TTL = 604800  # 7 天


def _make_cache_key(query: str, outline_nature: str, burden_description: str, audience: str, depth: str) -> str:
    """query + outline_nature + burden_description + audience + depth 拼接 SHA256，返回 Redis key。"""
    raw = f"{query}|{outline_nature}|{burden_description}|{audience}|{depth}"
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return f"kg_rag:cache:{h}"


def _extract_main_sources(main_results: list[dict]) -> list[dict]:
    """从 main_results 提取前端展示用的引用摘要。"""
    out = []
    for d in main_results:
        raw_text = d.get("text", "")
        preview = raw_text[:200] + "…" if len(raw_text) > 200 else raw_text
        out.append({
            "chunk_id": d.get("chunk_id", ""),
            "book_title": d.get("book_title", ""),
            "source_zh": d.get("source_zh", ""),
            "message_title": d.get("message_title", ""),
            "text_preview": preview,
        })
    return out

# 纲目性质 → 索引/年份加权配置
# 每条规则：(条件函数, 权重倍数)
# 条件函数接收 (index_name: str, chunk_id: str) → bool


def _extract_cwwl_year(chunk_id: str) -> int | None:
    """从 cwwl chunk_id 提取年份。格式：cwwl_{年份}-{册号}-{书序号}#{章号}-{段序号}"""
    if not chunk_id.startswith("cwwl_"):
        return None
    try:
        return int(chunk_id.split("_")[1].split("-")[0])
    except (IndexError, ValueError):
        return None


def _is_cwwl_year_range(chunk_id: str, start: int, end: int) -> bool:
    year = _extract_cwwl_year(chunk_id)
    return year is not None and start <= year <= end


OUTLINE_NATURE_WEIGHTS: dict[str, list[tuple[Callable[[str, str], bool], float]]] = {
    "一般性": [
        (lambda idx, cid: _is_cwwl_year_range(cid, 1994, 1997), 1.1),
    ],
    "高真理浓度": [
        (lambda idx, cid: _is_cwwl_year_range(cid, 1994, 1997), 1.5),
    ],
    "高生命浓度": [
        (lambda idx, cid: idx in ("kg-rag_cwwn", "kg-rag_life"), 1.5),
    ],
    "重实行应用": [
        (lambda idx, cid: _is_cwwl_year_range(cid, 1985, 1993), 1.5),
    ],
}


def _apply_outline_nature_weight(
    results: list[dict],
    outline_nature: str,
    *,
    log_full_list: bool = False,
) -> list[dict]:
    """根据纲目性质对检索结果加权重排序（BM25/Dense/路3 返回后调用；不叠乘，取匹配规则中的最大倍数）。"""
    rules = OUTLINE_NATURE_WEIGHTS.get(outline_nature, [])
    if not results:
        return results
    if not rules:
        for doc in results:
            s = float(doc.get("score", 0) or 0)
            doc["weighted_score"] = s
            doc["weight_multiplier"] = 1.0
        return results

    before_order = [d.get("chunk_id", "?") for d in results] if log_full_list else []

    for doc in results:
        idx = doc.get("_index", "") or ""
        cid = doc.get("chunk_id", "") or ""
        original_score = float(doc.get("score", 0) or 0)
        multiplier = 1.0
        for condition, weight in rules:
            try:
                if condition(idx, cid):
                    multiplier = max(multiplier, float(weight))
            except Exception:
                continue
        doc["weighted_score"] = original_score * multiplier
        doc["weight_multiplier"] = multiplier

    results.sort(key=lambda x: float(x.get("weighted_score", 0) or 0), reverse=True)

    if log_full_list:
        lines = []
        for rank, doc in enumerate(results, 1):
            cid = doc.get("chunk_id", "?")
            idx = doc.get("_index", "?")
            sc = float(doc.get("score", 0) or 0)
            wsc = float(doc.get("weighted_score", 0) or 0)
            mult = float(doc.get("weight_multiplier", 1.0) or 1.0)
            old_rank = before_order.index(cid) + 1 if cid in before_order else "?"
            change = f"({old_rank}→{rank})" if old_rank != rank else "(不变)"
            mult_str = f"×{mult}" if mult != 1.0 else ""
            lines.append(f"  #{rank}{change} {cid} [{idx}] score={sc:.4f} weighted={wsc:.4f} {mult_str}".rstrip())

        logger.info(
            f"[KG-RAG DEBUG] outline_weight full list: nature='{outline_nature}', "
            f"total={len(results)}\n" + "\n".join(lines)
        )
    return results


# 全流程 full_query：Step1 与 Query Rewrite 固定 Opus 4.6；Step2a/2b 使用 params.llm_model（前端下拉）；Step5 固定 Sonnet
FULL_QUERY_OPUS_MODEL = "claude-opus-4-6"
FULL_QUERY_STEP5_MODEL = "claude-sonnet-4-6"


def _resolve_step1_model(p: dict) -> str:
    """Step1 专用模型；未配置时回退到 llm_model。"""
    m = str(p.get("step1_model") or "").strip()
    return m if m else str(p.get("llm_model") or DEFAULT_PARAMS["llm_model"])


def _max_tokens_for_model(model: str, base: int) -> int:
    """
    gpt-5.4-thinking 走 Responses API 时，reasoning 与可见输出共用 max_output_tokens。
    base 仅够短 JSON 时，推理会先占满配额，导致 output_text 为空、Step1 等解析失败。
    """
    if (model or "").strip().lower() == "gpt-5.4-thinking":
        return max(int(base), 4096)
    return int(base)

PATH_COUNT_THRESHOLD = 20  # 多概念路径数少于此则取全路径，否则 shortestPath + 单概念扩展


def _format_skeleton(skeleton: list[str] | None) -> str:
    """将 Step 2 输出的骨架维度列表格式化为可读文本。"""
    if not skeleton:
        return ""
    return "\n".join(f"{i + 1}. {str(x)}" for i, x in enumerate(skeleton) if str(x).strip())


def _format_chunks(chunks: list[dict]) -> str:
    """格式化段落列表为 Prompt 文本。"""
    out = []
    for c in chunks:
        chunk_id = c.get("chunk_id", "")
        book = c.get("book_title", "")
        msg = c.get("message_number", "")
        msg_title = c.get("message_title", "")
        sec = c.get("section_title", "")
        text = c.get("text", "")
        line1 = f"[{chunk_id}] {book}"
        if msg:
            line1 += f" 第{msg}篇"
        if msg_title:
            line1 += f" {msg_title}"
        if sec:
            line1 += f" {sec}"
        out.append(line1)
        out.append(text.strip() if text else "")
        out.append("---")
    return "\n".join(out)


def _format_expanded_chunks(chunks: list[dict]) -> str:
    """格式化扩展段落，标注来源概念。"""
    out = []
    for c in chunks:
        chunk_id = c.get("chunk_id", "")
        expanded_from = c.get("expanded_from", "")
        book = c.get("book_title", "")
        msg = c.get("message_number", "")
        msg_title = c.get("message_title", "")
        text = c.get("text", "")
        line1 = f"[{chunk_id}] (扩展自: {expanded_from}) {book}"
        if msg:
            line1 += f" 第{msg}篇"
        if msg_title:
            line1 += f" {msg_title}"
        out.append(line1)
        out.append(text.strip() if text else "")
        out.append("---")
    return "\n".join(out)


def _parse_json_array(text: str) -> list[Any]:
    """从 Claude 返回文本解析 JSON 数组，支持被截断的 JSON 修复。"""
    if not text or not text.strip():
        return []
    s = text.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        s = "\n".join(lines[1:-1] if len(lines) > 2 and lines[-1].strip() == "```" else lines[1:])
    try:
        arr = json.loads(s)
        return arr if isinstance(arr, list) else []
    except json.JSONDecodeError as e:
        logger.info(f"[KG-RAG DEBUG] _parse_json_array JSON parse error: {e} — text[:200]={s[:200]}")
        last_brace = s.rfind("}")
        if last_brace > 0:
            truncated = s[: last_brace + 1] + "]"
            try:
                arr = json.loads(truncated)
                if isinstance(arr, list):
                    logger.info(f"[KG-RAG DEBUG] _parse_json_array truncated recovery OK, got {len(arr)} items")
                    return arr
            except json.JSONDecodeError:
                pass
        return []


def _parse_step1_layers(text: str) -> tuple[list[str], list[str], str]:
    """解析 Step 1 返回的 JSON（含 reasoning、surface、deep）。reasoning 传入 Step 2a/2b。"""
    if not text or not text.strip():
        return ([], [], "")
    s = text.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        s = "\n".join(lines[1:-1] if len(lines) > 2 and lines[-1].strip() == "```" else lines[1:])
    obj: Optional[dict] = None
    try:
        parsed = json.loads(s)
        if isinstance(parsed, dict):
            obj = parsed
    except json.JSONDecodeError:
        pass
    if obj is None:
        recovered = _safe_parse_json(s)
        obj = recovered if recovered else None
    if not obj:
        return ([], [], "")
    r_raw = obj.get("reasoning", "")
    reasoning = str(r_raw).strip() if r_raw is not None else ""
    surface_raw = obj.get("surface", [])
    deep_raw = obj.get("deep", [])
    surface = [str(x).strip() for x in surface_raw if str(x).strip()] if isinstance(surface_raw, list) else []
    deep = [str(x).strip() for x in deep_raw if str(x).strip()] if isinstance(deep_raw, list) else []
    return (surface[:3], deep[:4], reasoning)


def _safe_parse_json(text: str) -> dict:
    """尽量稳健地解析 JSON 对象；失败返回空 dict。"""
    if not text or not text.strip():
        return {}
    s = text.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        s = "\n".join(lines[1:-1] if len(lines) > 2 and lines[-1].strip() == "```" else lines[1:])
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        last_brace = s.rfind("}")
        if last_brace > 0:
            try:
                obj = json.loads(s[: last_brace + 1])
                return obj if isinstance(obj, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}


def _format_paths_text(paths: list[dict]) -> str:
    if not paths:
        return "暂无已知路径"
    lines = []
    for p in paths:
        from_name = p.get("from", "")
        relation = p.get("relation", "")
        to_name = p.get("to", "")
        via = p.get("via")
        hops = p.get("hops", "")
        if via and int(hops or 0) == 2:
            rel_parts = [x.strip() for x in str(relation).split("→")]
            via_name = str(via).strip()
            if len(rel_parts) == 2 and via_name:
                lines.append(
                    f"{from_name} ──{rel_parts[0]}──► {via_name} ──{rel_parts[1]}──► {to_name}（{hops}跳）"
                )
            else:
                lines.append(f"{from_name} ──{relation}──► {to_name}（{hops}跳）")
        elif via and int(hops or 0) == 3:
            rel_parts = [x.strip() for x in str(relation).split("→")]
            via_parts = [x.strip() for x in str(via).split("→")]
            if len(rel_parts) == 3 and len(via_parts) == 2:
                lines.append(
                    f"{from_name} ──{rel_parts[0]}──► {via_parts[0]} ──{rel_parts[1]}──► {via_parts[1]} ──{rel_parts[2]}──► {to_name}（{hops}跳）"
                )
            else:
                lines.append(f"{from_name} ──{relation}──► {to_name}（{hops}跳）")
        else:
            lines.append(f"{from_name} ──{relation}──► {to_name}（{hops}跳）")
    return "\n".join(lines)


def _parse_step2_skeleton(text: str) -> list[str] | None:
    """解析 Step 2 骨架 JSON，返回 skeleton 列表；为 null 或失败时返回 None。"""
    obj = _safe_parse_json(text or "")
    if not obj:
        return None
    sk = obj.get("skeleton")
    if sk is None:
        return None
    if isinstance(sk, list):
        return [str(x).strip() for x in sk if str(x).strip()]
    return None


async def _call_claude(
    prompt: str,
    model: str,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    system: str | None = None,
) -> tuple[str, dict[str, int] | None]:
    """
    封装 Claude API 调用。复用 ai_search 的 Claude 客户端（CLAUDE_API_KEY）。
    参考：back_mic/backend/ai_search/ai_service.py 第 177 行 claude_client、第 62-66 行 messages.create。
    """
    client = claude_client
    if not client:
        try:
            import anthropic
            api_key = os.environ.get("CLAUDE_API_KEY")
            client = anthropic.Anthropic(api_key=api_key) if api_key else None
        except Exception:
            client = None
    if not client:
        raise RuntimeError("Claude 客户端未配置（请设置 CLAUDE_API_KEY）")

    def _sync_create():
        return client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system or "你是一位专业、精确的助手。请严格按要求的格式输出。",
            messages=[{"role": "user", "content": prompt}],
        )

    try:
        msg = await asyncio.to_thread(_sync_create)
    except Exception as e:
        print(f"[KG-RAG] Claude 调用失败: {e}")
        raise
    usage: dict[str, int] | None = None
    uobj = getattr(msg, "usage", None)
    if uobj is not None:
        it = int(getattr(uobj, "input_tokens", 0) or 0)
        ot = int(getattr(uobj, "output_tokens", 0) or 0)
        if it or ot:
            usage = {"input_tokens": it, "output_tokens": ot}
    if not msg.content or not getattr(msg.content[0], "text", None):
        return "", usage
    return msg.content[0].text, usage


def _is_openai_kg_model(model: str) -> bool:
    """根据模型 id 判断是否走 OpenAI（与 claude-* 区分）。"""
    m = (model or "").strip().lower()
    if not m:
        return False
    if m.startswith("claude-"):
        return False
    return m.startswith("gpt-") or m.startswith("o1") or m.startswith("o3")


def _kg_openai_api_model_and_options(model: str) -> tuple[str, dict[str, Any]]:
    """
    解析 KG-RAG 使用的 OpenAI 模型 id。
    - gpt-5.4-thinking：与 gpt-5.4 同为底座模型 gpt-5.4（不使用 gpt-5.4-pro），
      走 Responses API 并将 reasoning.effort 设为 high，以加深推理链。
    """
    raw = (model or "").strip()
    key = raw.lower()
    base: dict[str, Any] = {"use_responses": False, "reasoning": None}
    if key == "gpt-5.4-thinking":
        return "gpt-5.4", {**base, "use_responses": True, "reasoning": {"effort": "high"}}
    return raw, base


async def _call_openai_kg_rag(
    prompt: str,
    model: str,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    system: str | None = None,
) -> tuple[str, dict[str, int] | None]:
    """OpenAI Chat Completions 或 Responses API（高推理 GPT-5.4）。"""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OpenAI 未配置（请设置 OPENAI_API_KEY）")
    api_model, extra = _kg_openai_api_model_and_options(model)
    use_responses = bool(extra.get("use_responses"))
    reasoning = extra.get("reasoning")

    def _sync() -> tuple[str, dict[str, int] | None]:
        from openai import OpenAI

        sys_text = (system or "").strip() or "你是一位专业、精确的助手。请严格按要求的格式输出。"
        long_job = bool(reasoning) or (
            "pro" in api_model.lower() and "mini" not in api_model.lower()
        )
        timeout = 600.0 if long_job else 180.0
        client = OpenAI(api_key=api_key, timeout=timeout)
        if use_responses:
            kw: dict[str, Any] = {
                "model": api_model,
                "input": prompt,
                "max_output_tokens": max_tokens,
            }
            if sys_text:
                kw["instructions"] = sys_text
            if reasoning:
                kw["reasoning"] = reasoning
            r = client.responses.create(**kw)
            text = getattr(r, "output_text", None)
            if not (text and str(text).strip()) and getattr(r, "output", None):
                parts: list[str] = []
                for item in r.output or []:
                    if getattr(item, "type", None) == "message" and getattr(item, "content", None):
                        for c in item.content:
                            t = getattr(c, "type", None)
                            if t in ("output_text", "text"):
                                parts.append(getattr(c, "text", "") or "")
                text = "".join(parts)
            out_text = str(text or "").strip()
            usage: dict[str, int] | None = None
            us = getattr(r, "usage", None)
            if us is not None:
                it = int(getattr(us, "input_tokens", 0) or getattr(us, "prompt_tokens", 0) or 0)
                ot = int(getattr(us, "output_tokens", 0) or getattr(us, "completion_tokens", 0) or 0)
                if it or ot:
                    usage = {"input_tokens": it, "output_tokens": ot}
            return out_text, usage
        messages: list[dict[str, str]] = []
        if sys_text:
            messages.append({"role": "system", "content": sys_text})
        messages.append({"role": "user", "content": prompt})
        kw2: dict[str, Any] = {
            "model": api_model,
            "messages": messages,
            "max_completion_tokens": max_tokens,
        }
        mlow = api_model.lower()
        if not mlow.startswith("gpt-5"):
            kw2["temperature"] = temperature
        r2 = client.chat.completions.create(**kw2)
        if not r2.choices:
            return "", None
        msg = r2.choices[0].message
        content = getattr(msg, "content", None) or ""
        usage2: dict[str, int] | None = None
        us2 = getattr(r2, "usage", None)
        if us2 is not None:
            it2 = int(getattr(us2, "prompt_tokens", 0) or 0)
            ot2 = int(getattr(us2, "completion_tokens", 0) or 0)
            if it2 or ot2:
                usage2 = {"input_tokens": it2, "output_tokens": ot2}
        return str(content).strip(), usage2

    return await asyncio.to_thread(_sync)


async def _call_kg_rag_llm(
    prompt: str,
    model: str,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    system: str | None = None,
) -> tuple[str, dict[str, int] | None]:
    """KG-RAG 统一 LLM：Claude 或 OpenAI（含 GPT-5.4 等）。返回 (文本, usage)。"""
    if _is_openai_kg_model(model):
        return await _call_openai_kg_rag(
            prompt, model, temperature=temperature, max_tokens=max_tokens, system=system
        )
    return await _call_claude(
        prompt, model, temperature=temperature, max_tokens=max_tokens, system=system
    )


class KgRagService:
    """KG-RAG 流水线编排：Step 1 概念抽取 → Step 2 骨架 → Step 3 三路检索 → Step 4 Prompt 构建 → Step 5 生成。"""

    def __init__(self, es_client: Any, neo4j_client: Any):
        """
        :param es_client: 已初始化的 Elasticsearch 实例
        :param neo4j_client: 已初始化的 Neo4jClient（可能 _available=False）
        """
        self.es = es_client
        self.neo4j = neo4j_client
        try:
            from ai_search.ai_service import redis_client
            self.redis = redis_client
        except Exception:
            self.redis = None
        _DEFAULT_INDICES = ",".join([
            "kg-rag_life", "kg-rag_cwwl", "kg-rag_cwwn",
            "kg-rag_others", "kg-rag_bib", "kg-rag_map_note",
            "kg-rag_7feasts", "kg-rag_pano", "kg-rag_dictionary",
        ])
        self.index = os.environ.get("KG_RAG_ES_INDEX", _DEFAULT_INDICES)

    async def _run_step2(
        self,
        query: str,
        surface: list[str],
        deep: list[str],
        reasoning: str,
        normalized: list[str],
        p: dict,
        llm_calls: list[dict[str, Any]],
        burden_description: str = "",
    ) -> dict[str, Any]:
        """图谱路径查询 + 单次 LLM 骨架构建。expanded_nodes 仅为 deep 概念。"""
        paths: list[dict] = []
        used_three_hop_fallback = False
        skeleton: list[str] | None = None
        expanded_nodes = list(deep)
        graph_error: str | None = None
        llm_elapsed_ms_step2 = 0.0
        prompt_out: str | None = None
        raw_out: str | None = None
        sn2: dict[str, Any] | None = None

        if not normalized:
            logger.info("[KG-RAG DEBUG] Step2 skipped: no concepts")
            return {
                "paths": paths,
                "skeleton": None,
                "expanded_nodes": expanded_nodes,
                "used_three_hop_fallback": False,
                "graph_error": None,
                "llm_elapsed_ms": {},
                "prompt": None,
                "raw_response": None,
                "llm_usage": None,
                "inner_reason": "no_concepts",
            }

        paths, used_three_hop_fallback = self.neo4j.get_paths_between(normalized)
        if not paths:
            logger.info(
                "[KG-RAG DEBUG] Step2: no paths (1–3 hop), skeleton=None, skip LLM | "
                f"used_three_hop_fallback={used_three_hop_fallback}"
            )
            return {
                "paths": paths,
                "skeleton": None,
                "expanded_nodes": expanded_nodes,
                "used_three_hop_fallback": used_three_hop_fallback,
                "graph_error": None,
                "llm_elapsed_ms": {},
                "prompt": None,
                "raw_response": None,
                "llm_usage": None,
                "inner_reason": "no_paths",
            }

        paths_text = _format_paths_text(paths)
        reasoning_s = (reasoning or "").strip() or "（无）"
        bd = (burden_description or "").strip()
        burden_description_line = f"用户负担说明：{bd}" if bd else ""
        step2_prompt = STEP2_SKELETON_BUILD.format(
            query=query,
            reasoning=reasoning_s,
            burden_description_line=burden_description_line,
            surface_json=json.dumps(surface, ensure_ascii=False),
            deep_json=json.dumps(deep, ensure_ascii=False),
            paths_text=paths_text,
        )
        prompt_out = step2_prompt
        logger.info(f"[KG-RAG DEBUG] Step2 prompt (first 1200 chars): {step2_prompt[:1200]}")
        try:
            t0 = asyncio.get_event_loop().time()
            raw_out, u2 = await _call_kg_rag_llm(
                step2_prompt, p["llm_model"], temperature=0, max_tokens=4096
            )
            llm_elapsed_ms_step2 = (asyncio.get_event_loop().time() - t0) * 1000
            logger.info(f"[KG-RAG DEBUG] Step2 raw response (first 1000 chars): {(raw_out or '')[:1000]}")
            skeleton = _parse_step2_skeleton(raw_out)
            sn2 = register_llm_usage(
                llm_calls, step="step2", request_model=p["llm_model"], usage=u2
            )
            if sn2:
                logger.info(
                    f"[KG-RAG LLM] step2 model={p['llm_model']} billing={sn2['billing_model']} "
                    f"in={sn2['input_tokens']} out={sn2['output_tokens']} cost_usd≈{sn2['cost_usd']}"
                )
        except Exception as e:
            logger.info(f"[KG-RAG DEBUG] Step2 LLM EXCEPTION: {e}")
            graph_error = str(e)
            skeleton = None
            raw_out = raw_out or ""
            sn2 = None

        return {
            "paths": paths,
            "skeleton": skeleton,
            "expanded_nodes": expanded_nodes,
            "used_three_hop_fallback": used_three_hop_fallback,
            "graph_error": graph_error,
            "llm_elapsed_ms": {"step2": llm_elapsed_ms_step2} if llm_elapsed_ms_step2 else {},
            "prompt": prompt_out,
            "raw_response": raw_out,
            "llm_usage": sn2,
            "inner_reason": None,
        }

    async def full_query(self, query: str, params: dict | None = None) -> dict:
        """全流程：Step 1→2→3→4→5，返回最终回答与每步中间结果。"""
        p = {**DEFAULT_PARAMS, **(params or {})}
        result = {"query": query, "params": p, "steps": {}, "answer": None}

        raw_params = params or {}
        depth = str(p.get("depth", "general") or "").strip() or "general"
        # depth 预设：deep 模式下放大检索参数（仅当请求未显式传入对应键时）
        if depth == "deep":
            if "bm25_top_k" not in raw_params:
                p["bm25_top_k"] = 60
            if "rerank_top_n" not in raw_params:
                p["rerank_top_n"] = 40
            if "skeleton_route_top_k" not in raw_params:
                p["skeleton_route_top_k"] = 10
            if "skeleton_route_max_per_node" not in raw_params:
                p["skeleton_route_max_per_node"] = 4

        outline_nature = str(p.get("outline_nature", "一般性") or "一般性").strip() or "一般性"
        burden_description = str(p.get("burden_description") or "").strip()
        audience = str(p.get("audience") or "").strip()
        result["params_used"] = {
            "outline_nature": outline_nature,
            "burden_description": burden_description,
            "audience": audience,
            "depth": depth,
        }

        # ── Redis 缓存读取 ──
        cache_key = _make_cache_key(query, outline_nature, burden_description, audience, depth)
        skip_cache = bool(p.get("skip_cache"))
        if self.redis and not skip_cache:
            try:
                cached_raw = self.redis.get(cache_key)
                if cached_raw:
                    cached = json.loads(cached_raw)
                    logger.info(f"[KG-RAG CACHE] hit: key={cache_key}")
                    return {
                        "query": query,
                        "params": p,
                        "params_used": result["params_used"],
                        "cached": True,
                        "cache_key": cache_key,
                        **cached,
                    }
            except Exception as e:
                logger.warning(f"[KG-RAG CACHE] read error: {e}")

        llm_calls: list[dict[str, Any]] = []
        pipeline_start = asyncio.get_event_loop().time()
        step_elapsed_ms: dict[str, float] = {}
        firewall_task = asyncio.create_task(
            match_firewall(query, _call_kg_rag_llm, llm_calls=llm_calls)
        )

        # Step 1: 概念抽取（skip_skeleton_route 时与 Step2 一并跳过，不走路3 骨架时无需图谱概念）
        concepts = []
        surface: list[str] = []
        deep: list[str] = []
        reasoning = ""
        step1_start = asyncio.get_event_loop().time()
        step1_elapsed_ms = 0.0
        raw1 = ""
        u1: dict[str, int] | None = None
        m1 = FULL_QUERY_OPUS_MODEL
        if p.get("skip_skeleton_route"):
            logger.info("[KG-RAG DEBUG] skip_skeleton_route: 跳过 Step1 概念抽取")
            step1_elapsed_ms = (asyncio.get_event_loop().time() - step1_start) * 1000
            result["steps"]["step1"] = {
                "skipped": True,
                "reason": "skip_skeleton_route",
                "concepts": [],
                "surface": [],
                "deep": [],
                "reasoning": "",
                "elapsed_ms": round(step1_elapsed_ms, 1),
                "raw_response": None,
            }
            step_elapsed_ms["step1"] = round(step1_elapsed_ms, 1)
        else:
            try:
                concept_names = self.neo4j.get_concept_names()
                concept_list_text = "、".join(concept_names)
                burden_line = (
                    f"\n信息负担说明：{burden_description}"
                    if (burden_description or "").strip()
                    else ""
                )
                step1_prompt = STEP1_CONCEPT_EXTRACTION.format(
                    query=query,
                    burden_line=burden_line,
                    concept_list=concept_list_text,
                )
                logger.info(f"[KG-RAG DEBUG] Step1 prompt (with concept list): {step1_prompt}")
                step1_extract_start = asyncio.get_event_loop().time()
                raw1, u1 = await _call_kg_rag_llm(
                    step1_prompt, m1, temperature=0, max_tokens=_max_tokens_for_model(m1, 500)
                )
                if (m1 or "").strip().lower() == "gpt-5.4-thinking":
                    logger.info(
                        f"[KG-RAG DEBUG] Step1 thinking raw stats: chars={len(raw1 or '')}, "
                        f"preview={(raw1 or '')[:300]}"
                    )
                surface, deep, reasoning = _parse_step1_layers(raw1)
                if not surface and not deep and (m1 or "").strip().lower() == "gpt-5.4-thinking":
                    logger.info(
                        "[KG-RAG DEBUG] Step1 gpt-5.4-thinking returned empty layers, retry once with gpt-5.4"
                    )
                    raw1_fallback, u1_fallback = await _call_kg_rag_llm(
                        step1_prompt, "gpt-5.4", temperature=0, max_tokens=800
                    )
                    s_fb, d_fb, r_fb = _parse_step1_layers(raw1_fallback)
                    logger.info(
                        f"[KG-RAG DEBUG] Step1 fallback raw stats: chars={len(raw1_fallback or '')}, "
                        f"preview={(raw1_fallback or '')[:300]}"
                    )
                    if s_fb or d_fb:
                        raw1, u1 = raw1_fallback, u1_fallback
                        surface, deep, reasoning = s_fb, d_fb, r_fb
                        m1 = "gpt-5.4"
                        logger.info(
                            f"[KG-RAG DEBUG] Step1 fallback success: surface={surface}, deep={deep}"
                        )
                step1_extract_elapsed_ms = (asyncio.get_event_loop().time() - step1_extract_start) * 1000
                logger.info(
                    f"[KG-RAG DEBUG] Step1 extraction_parse elapsed_ms={step1_extract_elapsed_ms:.1f}"
                )
                logger.info(f"[KG-RAG DEBUG] Step 1 surface: {surface}, deep(校验前): {deep}, reasoning: {reasoning[:200] if reasoning else ''}")
                concepts = []
                seen = set()
                for c in surface + deep:
                    if c not in seen:
                        seen.add(c)
                        concepts.append(c)
            except Exception as e:
                result["steps"]["step1"] = {"concepts": [], "raw_response": "", "error": str(e)}
            step1_elapsed_ms = (asyncio.get_event_loop().time() - step1_start) * 1000
            if "step1" not in result["steps"]:
                s1: dict[str, Any] = {
                    "concepts": concepts,
                    "surface": surface,
                    "deep": deep,
                    "reasoning": reasoning,
                    "elapsed_ms": round(step1_elapsed_ms, 1),
                    "raw_response": raw1,
                }
                sn1 = register_llm_usage(llm_calls, step="step1", request_model=m1, usage=u1)
                if sn1:
                    s1["llm_usage"] = sn1
                    logger.info(
                        f"[KG-RAG LLM] step1 model={m1} billing={sn1['billing_model']} "
                        f"in={sn1['input_tokens']} out={sn1['output_tokens']} cost_usd≈{sn1['cost_usd']}"
                    )
                result["steps"]["step1"] = s1
            step_elapsed_ms["step1"] = round(step1_elapsed_ms, 1)

        normalized = concepts

        firewall_doc: dict[str, str] | None = await firewall_task
        if firewall_doc:
            logger.info(
                "[KG-RAG] firewall hit: title=%r note_preview=%s",
                firewall_doc.get("title"),
                (firewall_doc.get("note") or "")[:80],
            )
            result["firewall"] = {
                "matched": firewall_doc["title"],
                "note": firewall_doc["note"],
            }
        else:
            logger.info("[KG-RAG DEBUG] firewall: full_query no hit (will not inject chunk)")
        if p.get("skip_skeleton_route"):
            logger.info("[KG-RAG DEBUG] skip_skeleton_route: Step1/2 已跳过，进入 Step3")
        else:
            logger.info("[KG-RAG DEBUG] Step 1 done: concepts go directly to Step2")

        if p.get("stop_after_step1"):
            result["stopped_after"] = "step1"
            result["steps"]["step2"] = {
                "skipped": True,
                "reason": "stop_after_step1",
                "paths": [],
                "paths_count": 0,
                "skeleton": None,
                "expanded_nodes": list(deep),
                "used_three_hop_fallback": False,
                "elapsed_ms": 0.0,
            }
            result["steps"]["step3"] = {
                "skipped": True,
                "rewritten_queries": [],
                "bm25_count": 0,
                "dense_count": 0,
                "rrf_count": 0,
                "main_results": [],
                "expanded_results": [],
                "bm25_results": [],
                "dense_results": [],
            }
            result["steps"]["step4"] = {
                "skipped": True,
                "prompt": "",
                "prompt_type": None,
                "token_estimate": 0,
            }
            result["steps"]["step5"] = {"skipped": True}
            result["llm_usage"] = _finalize_llm_usage(llm_calls, pipeline_start, step_elapsed_ms)
            return result

        # Step 2：路径查询 + 单次 LLM 骨架（skip_skeleton_route 时跳过，与路3 一致）
        step2_start = asyncio.get_event_loop().time()
        if p.get("skip_skeleton_route"):
            logger.info("[KG-RAG DEBUG] skip_skeleton_route: 跳过 Step2")
            step2_end = asyncio.get_event_loop().time()
            paths = []
            skeleton = None
            expanded_nodes = list(deep)
            step2_body = {
                "paths": [],
                "paths_count": 0,
                "skeleton": None,
                "expanded_nodes": expanded_nodes,
                "used_three_hop_fallback": False,
                "elapsed_ms": round((step2_end - step2_start) * 1000, 1),
                "skipped": True,
                "reason": "skip_skeleton_route",
            }
            result["steps"]["step2"] = step2_body
            logger.info("[KG-RAG DEBUG] Step2 skipped (skip_skeleton_route)")
        else:
            s2 = await self._run_step2(
                query,
                surface,
                deep,
                reasoning,
                normalized,
                p,
                llm_calls,
                burden_description=burden_description,
            )
            step2_end = asyncio.get_event_loop().time()
            paths = s2["paths"]
            skeleton = s2["skeleton"]
            expanded_nodes = s2["expanded_nodes"]
            used_3hop = s2["used_three_hop_fallback"]
            for k, v in (s2.get("llm_elapsed_ms") or {}).items():
                step_elapsed_ms[k] = round(float(v), 1)
            if s2.get("graph_error"):
                result["steps"]["step2_error"] = s2["graph_error"]
            step2_elapsed = round((step2_end - step2_start) * 1000, 1)
            step_elapsed_ms["step2"] = step2_elapsed
            step2_body: dict[str, Any] = {
                "paths": paths,
                "paths_count": len(paths),
                "skeleton": skeleton,
                "expanded_nodes": expanded_nodes,
                "used_three_hop_fallback": used_3hop,
                "elapsed_ms": step2_elapsed,
            }
            if s2.get("inner_reason") == "no_concepts":
                step2_body["skipped"] = True
                step2_body["reason"] = "no_concepts"
            elif s2.get("inner_reason") == "no_paths":
                step2_body["skipped"] = False
                step2_body["reason"] = "no_paths"
            if s2.get("prompt") is not None:
                step2_body["prompt"] = s2["prompt"]
            if s2.get("raw_response") is not None:
                step2_body["raw_response"] = s2["raw_response"]
            if s2.get("llm_usage"):
                step2_body["llm_usage"] = s2["llm_usage"]
            result["steps"]["step2"] = step2_body
            logger.info(
                f"[KG-RAG DEBUG] Step2 done: paths={len(paths)}, expanded_nodes={len(expanded_nodes)} (deep only), "
                f"skeleton={'yes' if skeleton else 'no'}, used_three_hop_fallback={used_3hop}, "
                f"elapsed_ms={step2_elapsed:.1f}"
            )
            if s2.get("llm_usage"):
                u2 = s2["llm_usage"]
                logger.info(
                    f"[KG-RAG LLM] step2 in={u2['input_tokens']} out={u2['output_tokens']} "
                    f"cost_usd≈{u2['cost_usd']}"
                )

        if p.get("stop_after_step2"):
            result["stopped_after"] = "step2"
            result["steps"]["step3"] = {
                "skipped": True,
                "reason": "stop_after_step2",
                "rewritten_queries": [],
                "bm25_count": 0,
                "dense_count": 0,
                "rrf_count": 0,
                "main_results": [],
                "expanded_results": [],
                "bm25_results": [],
                "dense_results": [],
            }
            result["steps"]["step4"] = {
                "skipped": True,
                "prompt": "",
                "prompt_type": None,
                "token_estimate": 0,
            }
            result["steps"]["step5"] = {"skipped": True}
            result["llm_usage"] = _finalize_llm_usage(llm_calls, pipeline_start, step_elapsed_ms)
            return result

        # Step 3: 三路检索
        u_rw: dict[str, int] | None = None
        query_rewrite_parsed_ok = False
        if p.get("skip_query_rewrite"):
            rewritten_queries = [query]
        else:
            try:
                bd_rw = (burden_description or "").strip()
                rewrite_input = f"{query}\n负担方向：{bd_rw}" if bd_rw else query
                rewrite_prompt = QUERY_REWRITE.format(query=rewrite_input)
                t_rw0 = asyncio.get_event_loop().time()
                raw_rw, u_rw = await _call_kg_rag_llm(
                    rewrite_prompt,
                    FULL_QUERY_OPUS_MODEL,
                    temperature=0,
                    max_tokens=_max_tokens_for_model(FULL_QUERY_OPUS_MODEL, 300),
                    system=QUERY_REWRITE_SYSTEM,
                )
                step_elapsed_ms["query_rewrite"] = round(
                    (asyncio.get_event_loop().time() - t_rw0) * 1000, 1
                )
                raw_rewrite = (raw_rw or "").strip()
                parsed = _parse_json_array(raw_rewrite)
                if parsed:
                    rq_list = [str(q).strip() for q in parsed if str(q).strip()]
                    if rq_list:
                        rewritten_queries = rq_list
                        query_rewrite_parsed_ok = True
                    else:
                        rewritten_queries = [query]
                else:
                    rewritten_queries = [query]
                if not rewritten_queries:
                    rewritten_queries = [query]
            except Exception:
                rewritten_queries = [query]

        # Dense：dense_query_list 每路独立 kNN；dense_top_k 默认按 bm25_top_k / 路数向上取整（p["dense_top_k"]>0 则用显式值）
        # 改写成功时在最前追加原始主题，与四条角度并列（通常共 5 路）。
        dense_query_list = (
            [query] + rewritten_queries
            if (not p.get("skip_query_rewrite") and query_rewrite_parsed_ok)
            else list(rewritten_queries)
        )

        dense_route_count = max(1, len(dense_query_list))
        bm25_top_k = int(p["bm25_top_k"])
        raw_dense_k = int(p.get("dense_top_k") or 0)
        if raw_dense_k > 0:
            dense_top_k = raw_dense_k
        else:
            dense_top_k = max(1, -(-bm25_top_k // dense_route_count))
        logger.info(
            f"[KG-RAG DEBUG] dense_top_k calculated: bm25_top_k={bm25_top_k}, "
            f"dense_routes={dense_route_count}, per_route_k={dense_top_k}"
            + ("" if raw_dense_k <= 0 else f" (explicit dense_top_k={raw_dense_k})")
        )

        bm25_fetch_size = bm25_top_k * 3
        dense_fetch_size = dense_top_k * 3
        bm25_task = bm25_search(self.es, query, self.index, bm25_fetch_size)
        dense_tasks = [
            dense_search(self.es, rq, self.index, dense_fetch_size, p["num_candidates"])
            for rq in dense_query_list
        ]
        route3_tasks = []
        sk_top_k = int(p["skeleton_route_top_k"])
        if expanded_nodes and not p.get("skip_skeleton_route"):
            route3_tasks = [
                skeleton_route_search(
                    self.es, node, query, self.index, sk_top_k, outline_nature
                )
                for node in expanded_nodes
            ]
        logger.info(f"[KG-RAG TRACE] #1 gather start: bm25=1, dense={len(dense_tasks)}, route3={len(route3_tasks)}")
        results = await asyncio.gather(bm25_task, *dense_tasks, *route3_tasks)
        logger.info(f"[KG-RAG TRACE] #2 gather done: total_results={len(results)}")
        bm25_raw = results[0]
        _apply_outline_nature_weight(bm25_raw, outline_nature, log_full_list=False)
        bm25_weighted_count = sum(
            1 for d in bm25_raw if float(d.get("weight_multiplier", 1.0) or 1.0) != 1.0
        )
        bm25_results = bm25_raw[:bm25_top_k]
        logger.info(
            f"[KG-RAG DEBUG] BM25 weight: fetched={len(bm25_raw)}, "
            f"after_weight_top={bm25_top_k}, "
            f"weighted_count={bm25_weighted_count}/{len(bm25_raw)}"
        )

        dense_raw_results = list(results[1: 1 + len(dense_tasks)])
        total_dense_fetched = sum(len(r) for r in dense_raw_results)
        total_dense_weighted = 0
        dense_route_weighted_lists: list[list[dict]] = []
        for raw in dense_raw_results:
            _apply_outline_nature_weight(raw, outline_nature, log_full_list=False)
            total_dense_weighted += sum(
                1 for d in raw if float(d.get("weight_multiplier", 1.0) or 1.0) != 1.0
            )
            dense_route_weighted_lists.append(raw[:dense_top_k])
        logger.info(
            f"[KG-RAG DEBUG] Dense weight: routes={len(dense_query_list)}, "
            f"per_route_fetch={dense_fetch_size}, per_route_keep={dense_top_k}, "
            f"total_weighted={total_dense_weighted}/{total_dense_fetched}"
        )

        route3_all = list(results[1 + len(dense_tasks):]) if route3_tasks else []
        route3_weighted_total = sum(
            sum(1 for d in route_result if float(d.get("weight_multiplier", 1.0) or 1.0) != 1.0)
            for route_result in route3_all
        )
        if route3_tasks:
            route3_fetch_size = sk_top_k * 3
            logger.info(
                f"[KG-RAG DEBUG] Route3 weight: nodes={len(route3_all)}, "
                f"per_node_fetch={route3_fetch_size}, per_node_keep={sk_top_k}, "
                f"total_weighted={route3_weighted_total}"
            )

        # 多路 Dense 结果合并去重（按 chunk_id，保留加权分最高的一条）
        dense_merged: dict[str, dict] = {}
        for hits in dense_route_weighted_lists:
            for doc in hits:
                cid = doc.get("chunk_id", "")
                w = float(doc.get("weighted_score", doc.get("score", 0) or 0) or 0)
                prev = dense_merged.get(cid)
                if prev is None or w > float(prev.get("weighted_score", prev.get("score", 0) or 0) or 0):
                    dense_merged[cid] = doc
        dense_results = list(dense_merged.values())

        merged = await rrf_merge(bm25_results, dense_results, p["rrf_k"], p["bm25_weight"], p["dense_weight"])
        logger.info(f"[KG-RAG TRACE] #3 RRF done: merged={len(merged)}")
        main_results = await rerank(merged, query, p["rerank_top_n"])
        logger.info(f"[KG-RAG TRACE] #4 main rerank done: main_results={len(main_results)}")
        if firewall_doc:
            fw_chunk: dict[str, Any] = {
                "chunk_id": f"firewall:{firewall_doc['title']}",
                "text": firewall_doc["full_text"],
                "source": "防火墙：" + firewall_doc["title"],
                "score": 1e12,
            }
            main_results = [fw_chunk] + list(main_results)
            logger.info(
                "[KG-RAG DEBUG] firewall: full_query injected first main_result title=%r text_field_chars=%s",
                firewall_doc["title"],
                len(firewall_doc.get("full_text") or ""),
            )

        expanded_results = []
        max_per_node = int(p.get("skeleton_route_max_per_node", 2) or 2)
        max_per_node = max(1, max_per_node)
        if route3_all:
            main_ids = {r.get("chunk_id") for r in main_results}
            for i, _node in enumerate(expanded_nodes):
                node_hits = route3_all[i] if i < len(route3_all) else []
                unique_hits = [r for r in node_hits if r.get("chunk_id") not in main_ids]
                expanded_results.extend(unique_hits[:max_per_node])
        logger.info(f"[KG-RAG TRACE] #5 expanded done: expanded_results={len(expanded_results)}")

        result["steps"]["weight"] = {
            "outline_nature": outline_nature,
            "bm25_weighted": bm25_weighted_count,
            "dense_weighted": total_dense_weighted,
            "route3_weighted": route3_weighted_total,
        }

        step3_body: dict[str, Any] = {
            "rewritten_queries": rewritten_queries,
            "dense_queries": dense_query_list,
            "bm25_count": len(bm25_results),
            "dense_count": len(dense_results),
            "rrf_count": len(merged),
            "main_results": main_results,
            "expanded_results": expanded_results,
            "bm25_results": bm25_results,
            "dense_results": dense_results,
        }
        sn_rw = register_llm_usage(
            llm_calls, step="query_rewrite", request_model=FULL_QUERY_OPUS_MODEL, usage=u_rw
        )
        if sn_rw:
            step3_body["llm_usage"] = sn_rw
            logger.info(
                f"[KG-RAG LLM] query_rewrite model={FULL_QUERY_OPUS_MODEL} billing={sn_rw['billing_model']} "
                f"in={sn_rw['input_tokens']} out={sn_rw['output_tokens']} cost_usd≈{sn_rw['cost_usd']}"
            )
        result["steps"]["step3"] = step3_body

        # Step 4: Prompt 构建（骨架式 / 平铺式共用 base_prompt，再统一追加防火墙指示到 step5_prompt）
        fw_tail = ""
        if firewall_doc:
            fw_title = firewall_doc["title"]
            fw_note = firewall_doc["note"]
            fw_tail = "\n\n" + FIREWALL_INSTRUCTION.format(
                fw_title=fw_title, fw_note=fw_note
            )
            logger.info(
                "[KG-RAG DEBUG] firewall: Step5 fw_tail chars=%s (will append to both skeleton and flat)",
                len(fw_tail),
            )
        metadata_lines: list[str] = []
        if (audience or "").strip():
            metadata_lines.append(f"面对对象：{audience.strip()}")
        if (burden_description or "").strip():
            metadata_lines.append(f"负担说明：{burden_description.strip()}")
        metadata_block = "\n".join(metadata_lines)

        if skeleton:
            skeleton_text = _format_skeleton(skeleton)
            main_chunks_text = _format_chunks(main_results)
            ctx_head = main_chunks_text[:300] if len(main_chunks_text) > 300 else main_chunks_text
            logger.info(
                "[KG-RAG DEBUG] Step5 context (skeleton main_chunks) first_300_chars: %r",
                ctx_head,
            )
            expanded_chunks_text = _format_expanded_chunks(expanded_results)
            base_prompt = STEP5_GENERATION.format(
                query=query,
                metadata_block=metadata_block,
                skeleton=skeleton_text,
                main_chunks=main_chunks_text,
                expanded_chunks=expanded_chunks_text,
            )
            prompt_type = "skeleton"
        else:
            all_chunks = main_results + expanded_results
            chunks_text = _format_chunks(all_chunks)
            ctx_head_flat = chunks_text[:300] if len(chunks_text) > 300 else chunks_text
            logger.info(
                "[KG-RAG DEBUG] Step5 context (flat main+expanded) first_300_chars: %r",
                ctx_head_flat,
            )
            base_prompt = STEP5_GENERATION_FLAT.format(
                query=query,
                metadata_block=metadata_block,
                chunks=chunks_text,
            )
            prompt_type = "flat"
        step5_prompt = base_prompt + fw_tail
        logger.info(f"[KG-RAG TRACE] #6 step4 prompt built: len={len(step5_prompt)}")
        result["steps"]["step4"] = {
            "prompt": step5_prompt,
            "prompt_type": prompt_type,
            "token_estimate": len(step5_prompt) // 4,
        }

        # Step 5: 生成
        if p.get("skip_generation"):
            result["steps"]["step5"] = {"skipped": True}
            result["llm_usage"] = _finalize_llm_usage(llm_calls, pipeline_start, step_elapsed_ms)
            return result
        try:
            tail_preview = step5_prompt[-200:] if len(step5_prompt) > 200 else step5_prompt
            logger.info(
                "[KG-RAG DEBUG] Step5 final prompt tail last_200_chars (prompt_type=%s len=%s): %r",
                prompt_type,
                len(step5_prompt),
                tail_preview,
            )
            t5_0 = asyncio.get_event_loop().time()
            gen, u5 = await _call_kg_rag_llm(
                step5_prompt, FULL_QUERY_STEP5_MODEL, temperature=p["temperature"], max_tokens=4096, system=None
            )
            step_elapsed_ms["step5"] = round((asyncio.get_event_loop().time() - t5_0) * 1000, 1)
            result["answer"] = gen.strip() if gen else None
            s5: dict[str, Any] = {"answer": result["answer"], "model": FULL_QUERY_STEP5_MODEL}
            sn5 = register_llm_usage(llm_calls, step="step5", request_model=FULL_QUERY_STEP5_MODEL, usage=u5)
            if sn5:
                s5["llm_usage"] = sn5
                logger.info(
                    f"[KG-RAG LLM] step5 model={FULL_QUERY_STEP5_MODEL} billing={sn5['billing_model']} "
                    f"in={sn5['input_tokens']} out={sn5['output_tokens']} cost_usd≈{sn5['cost_usd']}"
                )
            result["steps"]["step5"] = s5
        except Exception as e:
            result["steps"]["step5"] = {"error": str(e)}
            result["answer"] = None
        result["llm_usage"] = _finalize_llm_usage(llm_calls, pipeline_start, step_elapsed_ms)
        result["cached"] = False
        result["cache_key"] = cache_key

        # ── Redis 缓存写入（仅当 answer 存在且非 skip_generation 时） ──
        if self.redis and result.get("answer"):
            try:
                step1_data = result["steps"].get("step1") or {}
                step3_data = result["steps"].get("step3") or {}
                llm_usage = result.get("llm_usage") or {}
                cache_value = {
                    "answer": result["answer"],
                    "surface": step1_data.get("surface", []),
                    "deep": step1_data.get("deep", []),
                    "reasoning": step1_data.get("reasoning", ""),
                    "skeleton": (result["steps"].get("step2") or {}).get("skeleton"),
                    "main_sources": _extract_main_sources(step3_data.get("main_results") or []),
                    "total_elapsed_ms": llm_usage.get("total_elapsed_ms"),
                    "total_cost_usd": (llm_usage.get("totals") or {}).get("cost_usd"),
                    "answer_en": None,
                    "answer_zh_tw": None,
                }
                self.redis.setex(cache_key, CACHE_TTL, json.dumps(cache_value, ensure_ascii=False))
                logger.info(f"[KG-RAG CACHE] written: key={cache_key}, ttl={CACHE_TTL}")
            except Exception as e:
                logger.warning(f"[KG-RAG CACHE] write error: {e}")

        return result

    @staticmethod
    def update_cache_translation(cache_key: str, field: str, value: str) -> bool:
        """读出现有缓存 JSON，追加/更新 answer_en 或 answer_zh_tw 字段后重写（保持 7 天 TTL）。"""
        try:
            from ai_search.ai_service import redis_client
        except Exception:
            redis_client = None
        if not redis_client:
            logger.warning("[KG-RAG CACHE] update_cache_translation: redis not available")
            return False
        if field not in ("answer_en", "answer_zh_tw"):
            return False
        try:
            raw = redis_client.get(cache_key)
            if not raw:
                logger.info(f"[KG-RAG CACHE] update_cache_translation: key not found ({cache_key})")
                return False
            data = json.loads(raw)
            data[field] = value
            redis_client.setex(cache_key, CACHE_TTL, json.dumps(data, ensure_ascii=False))
            logger.info(f"[KG-RAG CACHE] updated {field} on {cache_key}")
            return True
        except Exception as e:
            logger.warning(f"[KG-RAG CACHE] update_cache_translation error: {e}")
            return False

    async def build_prompt_preview(self, query: str, params: dict | None = None) -> dict:
        """执行 Step 1→4，返回构建好的 Prompt，不执行 Step 5。"""
        full = await self.full_query(query, {**(params or {}), "skip_generation": True})
        full["steps"].pop("step5", None)
        full["answer"] = None
        return full
