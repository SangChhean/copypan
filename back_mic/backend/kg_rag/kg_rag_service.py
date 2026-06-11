# -*- coding: utf-8 -*-
"""KgRagService：编排 Step 1→5 全流程与检索/预览。"""
import asyncio
import hashlib
import json
import logging
import os
import re
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
    BURDEN_DESCRIPTION_PROMPT,
    STEP1_CONCEPT_EXTRACTION,
    FIREWALL_INSTRUCTION,
    STEP2_SKELETON_BUILD,
    QUERY_REWRITE,
    STEP5_GENERATION,
    STEP5_GENERATION_V4,
    STEP5_GENERATION_FLAT,
    STEP5_GENERATION_FLAT_V4,
)
from .bird_view_prompts import (
    BIRD_VIEW_SKELETON_PROMPT,
    BIRD_VIEW_OUTLINE_PROMPT,
    BIRD_VIEW_SOURCE_PROMPT_MINISTRY,
    BIRD_VIEW_SOURCE_PROMPT_FEAST,
)
from ai_search.monitoring import get_monitoring
from ai_search.ai_service import _strip_code_fence_for_outline

# QUERY_REWRITE 调用时传入 Claude 的 system，与 prompts 中说明一致
QUERY_REWRITE_SYSTEM = "你是一个资深的圣经研究学者，只输出 JSON，不输出其他任何内容。"
BURDEN_DESCRIPTION_SYSTEM = (
    "你是一个资深的圣经研究学者。"
    "严格只输出最终结果，不输出内部流程、步骤说明、分析过程、分隔线。"
    "情境A时只输出一行：负担说明：..."
    "情境B时只输出三行：候选一（侧重...）：...\\n候选二（侧重...）：...\\n候选三（侧重...）：..."
)
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
    "rerank_top_n": 15,
    "skeleton_route_top_k": 45,
    "skeleton_route_max_per_node": 15,  # 路3 每扩展节点去重后并入 expanded_results 的条数上限
    "temperature": 0.3,
    "skip_query_rewrite": False,
    "skip_skeleton_route": False,
    "skip_generation": False,
    "llm_model": os.environ.get("CLAUDE_MODEL", "claude-sonnet-4-6"),
    "step1_model": "",  # 空字符串表示与 llm_model 相同
    "step5_model": "",  # 空字符串则 Step5 用 FULL_QUERY_STEP5_MODEL（默认 Sonnet 4.6）
    "stop_after_step1": False,
    "stop_after_step2": False,  # True 时在 Step2 完成后返回（需与 stop_after_step1 互斥）
    "outline_nature": "一般性",  # 一般性 / 真理启示 / 生命经历 / 应用实行
    "burden_description": "",  # 负担说明（可选）
    "audience": "",  # 面对对象（可选）
    "depth": "general",  # general / deep；deep 时可触发检索参数预设（见 full_query）
    "skip_cache": False,  # True 时跳过缓存读取（强制重跑），但仍写入缓存
}

CACHE_TTL = 604800  # 7 天

_INDICES_BASE = ",".join([
    "kg-rag_life", "kg-rag_cwwl", "kg-rag_cwwn",
    "kg-rag_others", "kg-rag_bib", "kg-rag_map_note",
    "kg-rag_7feasts",
])
_INDICES_FULL = _INDICES_BASE + ",kg-rag_pano,kg-rag_dictionary"


def _make_cache_key(
    query: str,
    outline_nature: str,
    burden_description: str,
    audience: str,
    depth: str,
    mode: str,
    revelation_joined: str = "",
    experience_joined: str = "",
    practice_joined: str = "",
) -> str:
    """query + outline_nature + burden_description + audience + depth + mode + revelation_joined + experience_joined + practice_joined 拼接 SHA256，返回 Redis key。"""
    raw = f"{query}|{outline_nature}|{burden_description}|{audience}|{depth}|{mode}|{revelation_joined}|{experience_joined}|{practice_joined}"
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
    "真理启示": [
        (lambda idx, cid: _is_cwwl_year_range(cid, 1994, 1997), 1.5),
    ],
    "生命经历": [
        (lambda idx, cid: idx in ("kg-rag_cwwn", "kg-rag_life"), 1.5),
    ],
    "应用实行": [
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


# 全流程 full_query：Step1 默认 Opus 4.7；Query Rewrite 固定 Opus 4.6；Step2 使用 params.llm_model（前端下拉）；Step5 默认 Sonnet（可被 params.step5_model 覆盖）
FULL_QUERY_OPUS_MODEL = "claude-opus-4-6"  # Query 改写专用
FULL_QUERY_STEP1_MODEL = "claude-opus-4-7"  # Step1 概念抽取默认（可被 params.step1_model 覆盖）
FULL_QUERY_STEP5_MODEL = "claude-sonnet-4-6"


def _resolve_step1_model(p: dict) -> str:
    """Step1 专用模型；未配置时回退到 FULL_QUERY_STEP1_MODEL。"""
    m = str(p.get("step1_model") or "").strip()
    return m if m else FULL_QUERY_STEP1_MODEL


def _max_tokens_for_model(model: str, base: int) -> int:
    """
    gpt-5.4-thinking 走 Responses API 时，reasoning 与可见输出共用 max_output_tokens。
    base 仅够短 JSON 时，推理会先占满配额，导致 output_text 为空、Step1 等解析失败。
    """
    if (model or "").strip().lower() == "gpt-5.4-thinking":
        return max(int(base), 4096)
    if _is_deepseek_kg_model(model):
        return max(int(base), 4000)
    return int(base)

PATH_COUNT_THRESHOLD = 20  # 多概念路径数少于此则取全路径，否则 shortestPath + 单概念扩展


def _format_skeleton(skeleton: list[dict] | None) -> str:
    """将 Step 2 输出的骨架步骤列表格式化为可读文本（兼容 Prompt 预览等旧路径）。"""
    if not skeleton:
        return ""
    return "\n".join(
        f"{i + 1}. {s['step']}" for i, s in enumerate(skeleton) if s.get("step")
    )


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


def _format_chunk_line(c: dict, max_text: int = 300) -> str:
    """单条段落格式化为一行摘要。"""
    chunk_id = c.get("chunk_id", "")
    book = c.get("book_title", "")
    msg = c.get("message_number", "")
    msg_title = c.get("message_title", "")
    text = (c.get("text") or "").strip()
    header = f"[{chunk_id}] {book}"
    if msg:
        header += f" 第{msg}篇"
    if msg_title:
        header += f" {msg_title}"
    preview = text if len(text) <= max_text else text[:max_text] + "…"
    return f"{header}\n{preview}"


def _build_skeleton_bound_prompt_block(
    skeleton: list[dict],
    expanded_results: list[dict],
    deep: list[str],
    main_results: list[dict],
) -> str:
    """将骨架步骤与 expanded_results 按 deep_indices 绑定，构建结构化的 Prompt 文本块。

    每步输出：
        【第N步】{step}
          支撑段落：
            [段落] ...
    末尾追加补充段落（main_results）。
    """
    used_expanded_ids: set[str] = set()
    sections: list[str] = []

    for idx, sk_item in enumerate(skeleton):
        step_text = sk_item.get("step", "")
        deep_indices = sk_item.get("deep_indices", [])
        target_concepts = {deep[i] for i in deep_indices if 0 <= i < len(deep)}

        bound_chunks = []
        for c in expanded_results:
            if c.get("expanded_from") in target_concepts:
                bound_chunks.append(c)
                used_expanded_ids.add(c.get("chunk_id", ""))

        lines = [f"【第{idx + 1}步】{step_text}"]
        if bound_chunks:
            lines.append("  支撑段落：")
            for c in bound_chunks:
                lines.append(f"    {_format_chunk_line(c)}")
                lines.append("    ---")
        else:
            lines.append("  支撑段落：（无绑定段落）")
        sections.append("\n".join(lines))

    leftover_expanded = [
        c for c in expanded_results if c.get("chunk_id", "") not in used_expanded_ids
    ]

    supplement_lines = ["【补充段落】（来自 BM25 与向量检索，适用于任何大点）"]
    for c in main_results:
        supplement_lines.append(f"  {_format_chunk_line(c)}")
        supplement_lines.append("  ---")
    if leftover_expanded:
        for c in leftover_expanded:
            supplement_lines.append(f"  {_format_chunk_line(c)}")
            supplement_lines.append("  ---")
    sections.append("\n".join(supplement_lines))

    return "\n\n".join(sections)


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


def _parse_burden_generation_output(raw: str) -> dict[str, Any]:
    """解析负担说明 LLM 输出：情境 A（负担说明：）或情境 B（候选一～三）。"""
    text = (raw or "").strip()
    logger.info(
        "[KG-RAG BURDEN DEBUG] parse start: raw_len=%s preview=%r",
        len(text),
        text[:300],
    )
    if not text:
        return {"scenario": "B", "candidates": [], "error": "解析失败", "debug": {"reason": "empty_raw"}}
    if "候选一" in text:
        candidates: list[str] = []
        for label in ("候选一", "候选二", "候选三"):
            # 候选一：… 或 候选一（侧重…）：…
            pat = rf"{re.escape(label)}(?:（侧重[^）]*）)?[：:]\s*(.+?)(?=\n\s*候选[一二三]|$)"
            m = re.search(pat, text, re.DOTALL)
            if m:
                candidates.append(re.sub(r"\s+", " ", m.group(1).strip()))
            else:
                candidates.append("")
        logger.info(
            "[KG-RAG BURDEN DEBUG] parse scenario B: candidate_lens=%s",
            [len(c or "") for c in candidates],
        )
        if not any(c.strip() for c in candidates):
            return {"scenario": "B", "candidates": [], "error": "解析失败", "debug": {"reason": "b_candidates_all_empty"}}
        while len(candidates) < 3:
            candidates.append("")
        return {
            "scenario": "B",
            "candidates": candidates[:3],
            "debug": {"reason": "matched_b", "candidate_lens": [len(c or "") for c in candidates[:3]]},
        }
    if "负担说明" in text:
        m = re.search(r"负担说明[：:]\s*(.+)", text, re.DOTALL)
        if m:
            # 保留整段，避免只取首行导致前端看起来“被截断”
            line = re.sub(r"\s+", " ", m.group(1).strip())
            if line:
                logger.info(
                    "[KG-RAG BURDEN DEBUG] parse scenario A: result_len=%s preview=%r",
                    len(line),
                    line[:200],
                )
                return {"scenario": "A", "result": line, "debug": {"reason": "matched_a", "result_len": len(line)}}
    logger.info("[KG-RAG BURDEN DEBUG] parse failed: fallback to error")
    return {"scenario": "B", "candidates": [], "error": "解析失败", "debug": {"reason": "no_pattern_matched"}}


def _parse_step1_layers(
    text: str, outline_nature: str = "一般性"
) -> tuple[list[str], list[str], list[str], str]:
    """解析 Step 1 返回的 JSON（含 reasoning、revelation、experience、practice）。reasoning 仅写入 Step1 结果，不传入 Step2。"""
    if not text or not text.strip():
        return ([], [], [], "")
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
        return ([], [], [], "")
    r_raw = obj.get("reasoning", "")
    reasoning = str(r_raw).strip() if r_raw is not None else ""
    revelation_raw = obj.get("revelation", [])
    experience_raw = obj.get("experience", [])
    practice_raw = obj.get("practice", [])
    revelation = [str(x).strip() for x in revelation_raw if str(x).strip()] if isinstance(revelation_raw, list) else []
    experience = [str(x).strip() for x in experience_raw if str(x).strip()] if isinstance(experience_raw, list) else []
    practice = [str(x).strip() for x in practice_raw if str(x).strip()] if isinstance(practice_raw, list) else []
    nature = (outline_nature or "一般性").strip()
    if nature == "真理启示":
        max_rev, max_exp, max_prac = 8, 4, 4
    elif nature == "生命经历":
        max_rev, max_exp, max_prac = 4, 8, 4
    elif nature == "应用实行":
        max_rev, max_exp, max_prac = 4, 4, 8
    else:
        max_rev, max_exp, max_prac = 6, 5, 5

    experience = experience[:max_exp]
    practice = practice[:max_prac]
    max_revelation = min(max_rev, 16 - len(experience) - len(practice))
    revelation = revelation[:max_revelation]
    return (revelation, experience, practice, reasoning)


def _safe_parse_json(text: str) -> dict:
    """尽量稳健地解析 JSON 对象；失败返回空 dict。"""
    if not text or not text.strip():
        return {}
    s = text.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        s = "\n".join(lines[1:-1] if len(lines) > 2 and lines[-1].strip() == "```" else lines[1:])
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    try:
        obj = json.loads(s)
        logger.info(f"[KG-RAG DEBUG] _safe_parse_json success, type={type(obj)}, is_dict={isinstance(obj, dict)}")
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError as e:
        logger.info(f"[KG-RAG DEBUG] _safe_parse_json JSONDecodeError: {e}, s preview: {s[:200]}")
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
                    f"{from_name} ──{rel_parts[0]}──► {via_name} ──{rel_parts[1]}──► {to_name}"
                )
            else:
                lines.append(f"{from_name} ──{relation}──► {to_name}")
        elif via and int(hops or 0) == 3:
            rel_parts = [x.strip() for x in str(relation).split("→")]
            via_parts = [x.strip() for x in str(via).split("→")]
            if len(rel_parts) == 3 and len(via_parts) == 2:
                lines.append(
                    f"{from_name} ──{rel_parts[0]}──► {via_parts[0]} ──{rel_parts[1]}──► {via_parts[1]} ──{rel_parts[2]}──► {to_name}"
                )
            else:
                lines.append(f"{from_name} ──{relation}──► {to_name}")
        else:
            lines.append(f"{from_name} ──{relation}──► {to_name}")
    return "\n".join(lines)


def _format_key_verses_text(raw: dict[str, list[tuple[str, str]]]) -> str:
    """将 get_key_verses 结果格式化为 Step2 Prompt 块：每行「- 概念名：id「正文」；id「正文」…」。"""
    if not raw:
        return "（无）"
    lines_out: list[str] = []
    for concept, pairs in raw.items():
        parts: list[str] = []
        for vid, vtext in pairs:
            vtext = (vtext or "").strip()
            vid = (vid or "").strip()
            if not vtext:
                continue
            clean_text = vtext.replace("“", "'").replace("”", "'")
            if vid:
                parts.append(f"{vid}「{clean_text}」")
            else:
                parts.append(f"「{clean_text}」")
        if parts:
            lines_out.append(f"- {concept}：{'；'.join(parts)}")
    return "\n".join(lines_out) if lines_out else "（无）"


def _parse_step2_skeleton(text: str) -> list[dict] | None:
    """解析 Step 2 骨架 JSON，返回 [{"step": str, "deep_indices": list[int], "path_evidence": str|None, "scripture_anchor": str|None}, ...]；为 null 或失败时返回 None。
    若 scripture_anchor 含全角「，则将其前缀作为出处拼入 step：step +「（出处）」；scripture_anchor 字段原样保留。"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()
    logger.info(f"[KG-RAG DEBUG] Step2 parse input (first 100): {text[:100]}")
    try:
        obj = _safe_parse_json(text or "")
    except Exception as e:
        logger.info(f"[KG-RAG DEBUG] Step2 parse FAILED: {e}, text preview: {text[:200]}")
        return None
    if not obj:
        return None
    sk = obj.get("skeleton")
    if sk is None:
        return None
    if isinstance(sk, list):
        result = []
        for x in sk:
            if isinstance(x, dict) and "step" in x:
                step = str(x.get("step", "")).strip()
                indices = x.get("deep_indices", [])
                if not isinstance(indices, list):
                    indices = []
                indices = [i for i in indices if isinstance(i, int)]
                pe_raw = x.get("path_evidence")
                path_evidence = str(pe_raw).strip() if pe_raw and str(pe_raw).strip() else None
                sa_raw = x.get("scripture_anchor")
                scripture_anchor = str(sa_raw).strip() if sa_raw and str(sa_raw).strip() else None
                if step:
                    if scripture_anchor is not None:
                        pos = scripture_anchor.find("「")
                        if pos != -1:
                            scripture_id = scripture_anchor[:pos].strip()
                            if scripture_id:
                                step = f"{step}（{scripture_id}）"
                    result.append(
                        {
                            "step": step,
                            "deep_indices": indices,
                            "path_evidence": path_evidence,
                            "scripture_anchor": scripture_anchor,
                        }
                    )
            elif isinstance(x, str) and x.strip():
                result.append(
                    {
                        "step": x.strip(),
                        "deep_indices": [],
                        "path_evidence": None,
                        "scripture_anchor": None,
                    }
                )
        return result if result else None
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
        kwargs = dict(
            model=model,
            max_tokens=max_tokens,
            system=system or "你是一位专业、精确的助手。请严格按要求的格式输出。",
            messages=[{"role": "user", "content": prompt}],
        )
        if not (model or "").startswith("claude-opus-4-7"):
            kwargs["temperature"] = temperature
        return client.messages.create(**kwargs)

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


def _is_deepseek_kg_model(model: str) -> bool:
    """根据模型 id 判断是否走 DeepSeek OpenAI 兼容 API。"""
    m = (model or "").strip().lower()
    return bool(m) and m.startswith("deepseek")


def _normalize_deepseek_api_model(model: str) -> str:
    """KG-RAG 请求的 DeepSeek 模型 id → API model 参数。"""
    m = (model or "").strip().lower()
    if m in ("deepseek-v3.2", "deepseek-v3"):
        return "deepseek-chat"
    return (model or "").strip() or "deepseek-v4-pro"


def _is_openai_kg_model(model: str) -> bool:
    """根据模型 id 判断是否走 OpenAI（与 claude-* / deepseek-* 区分）。"""
    m = (model or "").strip().lower()
    if not m:
        return False
    if m.startswith("claude-") or m.startswith("deepseek"):
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


async def _call_deepseek_kg_rag(
    prompt: str,
    model: str,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    system: str | None = None,
) -> tuple[str, dict[str, int] | None]:
    """DeepSeek Chat Completions（OpenAI 兼容，需 DEEPSEEK_API_KEY）。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DeepSeek 未配置（请设置 DEEPSEEK_API_KEY）")
    api_model = _normalize_deepseek_api_model(model)

    def _sync() -> tuple[str, dict[str, int] | None]:
        from openai import OpenAI

        sys_text = (system or "").strip() or "你是一位专业、精确的助手。请严格按要求的格式输出。"
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com", timeout=600.0)
        messages: list[dict[str, str]] = []
        if sys_text:
            messages.append({"role": "system", "content": sys_text})
        messages.append({"role": "user", "content": prompt})
        r = client.chat.completions.create(
            model=api_model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        if not r.choices:
            return "", None
        msg = r.choices[0].message
        content = getattr(msg, "content", None) or ""
        if not content.strip():
            # DeepSeek Reasoner/Thinking 模式：答案在 reasoning_content，content 为空
            content = getattr(msg, "reasoning_content", None) or ""
            if content.strip():
                logger.warning(
                    f"[KG-RAG WARN] DeepSeek content为空，fallback到reasoning_content "
                    f"(很可能max_tokens不足)，chars={len(content)}"
                )
        usage: dict[str, int] | None = None
        us = getattr(r, "usage", None)
        if us is not None:
            it = int(getattr(us, "prompt_tokens", 0) or 0)
            ot = int(getattr(us, "completion_tokens", 0) or 0)
            if it or ot:
                usage = {"input_tokens": it, "output_tokens": ot}
        return str(content).strip(), usage

    return await asyncio.to_thread(_sync)


async def _call_kg_rag_llm(
    prompt: str,
    model: str,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    system: str | None = None,
) -> tuple[str, dict[str, int] | None]:
    """KG-RAG 统一 LLM：Claude、OpenAI（含 GPT-5.4）或 DeepSeek。返回 (文本, usage)。"""
    if _is_deepseek_kg_model(model):
        return await _call_deepseek_kg_rag(
            prompt, model, temperature=temperature, max_tokens=max_tokens, system=system
        )
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
        self.index = os.environ.get("KG_RAG_ES_INDEX", _INDICES_FULL)

    async def _run_step2(
        self,
        query: str,
        revelation: list[str],
        experience: list[str],
        practice: list[str],
        normalized: list[str],
        p: dict,
        llm_calls: list[dict[str, Any]],
        burden_description: str = "",
    ) -> dict[str, Any]:
        """图谱路径查询 + 单次 LLM 骨架构建。expanded_nodes 为 Step1 三层概念并集。"""
        paths: list[dict] = []
        skeleton: list[str] | None = None
        expanded_nodes = list(dict.fromkeys(revelation + experience + practice))
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
                "graph_error": None,
                "llm_elapsed_ms": {},
                "prompt": None,
                "raw_response": None,
                "llm_usage": None,
                "inner_reason": "no_concepts",
            }

        paths = self.neo4j.get_paths_between(normalized)
        if not paths:
            logger.info("[KG-RAG DEBUG] Step2: no 1-hop paths, skeleton=None, skip LLM")
            return {
                "paths": paths,
                "skeleton": None,
                "expanded_nodes": expanded_nodes,
                "graph_error": None,
                "llm_elapsed_ms": {},
                "prompt": None,
                "raw_response": None,
                "llm_usage": None,
                "inner_reason": "no_paths",
            }

        paths_text = _format_paths_text(paths)
        key_verses_raw = self.neo4j.get_key_verses(revelation + experience + practice)
        key_verses_text = _format_key_verses_text(key_verses_raw)
        logger.info(f"[KG-RAG DEBUG] Step2 key_verses_text:\n{key_verses_text}")
        bd = (burden_description or "").strip()
        intrinsic_burden_text = bd if bd else "（未填写负担说明）"
        outline_nature = str(p.get("outline_nature", "一般性") or "一般性").strip() or "一般性"
        step2_prompt = STEP2_SKELETON_BUILD.format(
            query=query,
            outline_nature=outline_nature,
            intrinsic_burden_text=intrinsic_burden_text,
            revelation_json=json.dumps(revelation, ensure_ascii=False),
            experience_json=json.dumps(experience, ensure_ascii=False),
            practice_json=json.dumps(practice, ensure_ascii=False),
            paths_text=paths_text,
            key_verses_text=key_verses_text,
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
            "graph_error": graph_error,
            "llm_elapsed_ms": {"step2": llm_elapsed_ms_step2} if llm_elapsed_ms_step2 else {},
            "prompt": prompt_out,
            "raw_response": raw_out,
            "llm_usage": sn2,
            "inner_reason": None,
        }

    async def full_query(self, query: str, params: dict | None = None, mode: str = "3.0") -> dict:
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
                p["rerank_top_n"] = 25
            if "skeleton_route_top_k" not in raw_params:
                p["skeleton_route_top_k"] = 75
            if "skeleton_route_max_per_node" not in raw_params:
                p["skeleton_route_max_per_node"] = 15

        outline_nature = str(p.get("outline_nature", "一般性") or "一般性").strip() or "一般性"
        burden_description = str(p.get("burden_description") or "").strip()
        audience = str(p.get("audience") or "").strip()

        # ── Mode 选择（2.0 / 3.0 / 4.0）──
        mode = str(mode or "3.0").strip()
        if mode == "4.0":
            active_index = os.environ.get("KG_RAG_ES_INDEX", _INDICES_FULL)
        else:
            active_index = os.environ.get("KG_RAG_ES_INDEX", _INDICES_BASE)

        result["params_used"] = {
            "outline_nature": outline_nature,
            "burden_description": burden_description,
            "audience": audience,
            "depth": depth,
            "mode": mode,
        }

        # ── Redis 缓存读取 ──
        preset_revelation = p.get("preset_revelation") or []
        preset_experience = p.get("preset_experience") or []
        preset_practice = p.get("preset_practice") or []
        revelation_joined = (
            "|".join(sorted(str(c).strip() for c in preset_revelation if str(c).strip()))
            if isinstance(preset_revelation, list)
            else ""
        )
        experience_joined = (
            "|".join(sorted(str(c).strip() for c in preset_experience if str(c).strip()))
            if isinstance(preset_experience, list)
            else ""
        )
        practice_joined = (
            "|".join(sorted(str(c).strip() for c in preset_practice if str(c).strip()))
            if isinstance(preset_practice, list)
            else ""
        )
        cache_key = _make_cache_key(
            query,
            outline_nature,
            burden_description,
            audience,
            depth,
            mode,
            revelation_joined,
            experience_joined,
            practice_joined,
        )
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

        # ── 2.0 模式：跳过 Step1 / Step2 / 路3，直接进入检索 ──
        skip_kg = (mode == "2.0")

        # ── 2.0 模式：放大检索参数（无路3补偿）──
        if skip_kg:
            if depth == "deep":
                p["bm25_top_k"] = 120
                p["rerank_top_n"] = 100
            else:
                p["bm25_top_k"] = 60
                p["rerank_top_n"] = 60

        concepts = []
        revelation: list[str] = []
        experience: list[str] = []
        practice: list[str] = []
        reasoning = ""

        if not skip_kg:
            # Step 1: 概念抽取（skip_skeleton_route 时与 Step2 一并跳过，不走路3 骨架时无需图谱概念）
            step1_start = asyncio.get_event_loop().time()
            step1_elapsed_ms = 0.0
            raw1 = ""
            u1: dict[str, int] | None = None
            m1 = _resolve_step1_model(p)

            if (
                isinstance(preset_revelation, list)
                and isinstance(preset_experience, list)
                and isinstance(preset_practice, list)
                and preset_revelation
            ):
                revelation = [str(c).strip() for c in preset_revelation if str(c).strip()]
                experience = [str(c).strip() for c in preset_experience if str(c).strip()]
                practice = [str(c).strip() for c in preset_practice if str(c).strip()]
                concepts = list(dict.fromkeys(revelation + experience + practice))
                reasoning = "（人工指定概念，跳过 Step 1）"
                step1_elapsed_ms = (asyncio.get_event_loop().time() - step1_start) * 1000
                result["steps"]["step1"] = {
                    "concepts": concepts,
                    "revelation": revelation,
                    "experience": experience,
                    "practice": practice,
                    "reasoning": reasoning,
                    "elapsed_ms": round(step1_elapsed_ms, 1),
                    "raw_response": None,
                    "preset": True,
                }
                step_elapsed_ms["step1"] = round(step1_elapsed_ms, 1)
                logger.info(
                    "[KG-RAG] Step 1 skipped: using preset revelation=%s experience=%s practice=%s",
                    revelation,
                    experience,
                    practice,
                )
            elif p.get("skip_skeleton_route"):
                logger.info("[KG-RAG DEBUG] skip_skeleton_route: 跳过 Step1 概念抽取")
                step1_elapsed_ms = (asyncio.get_event_loop().time() - step1_start) * 1000
                result["steps"]["step1"] = {
                    "skipped": True,
                    "reason": "skip_skeleton_route",
                    "concepts": [],
                    "revelation": [],
                    "experience": [],
                    "practice": [],
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
                        outline_nature=outline_nature,
                        burden_line=burden_line,
                        concept_list=concept_list_text,
                    )
                    logger.info(f"[KG-RAG DEBUG] Step1 prompt (with concept list): {step1_prompt}")
                    step1_extract_start = asyncio.get_event_loop().time()
                    logger.info(
                        f"[KG-RAG DEBUG] Step1 LLM 即将调用，model={m1}，prompt 前100字：{step1_prompt[:100]}"
                    )
                    raw1, u1 = await _call_kg_rag_llm(
                        step1_prompt, m1, temperature=0, max_tokens=_max_tokens_for_model(m1, 800)
                    )
                    logger.info("[KG-RAG DEBUG] Step1 LLM 调用完成")
                    revelation, experience, practice, reasoning = _parse_step1_layers(
                        raw1, outline_nature=outline_nature
                    )
                    if not revelation and not experience and not practice and (m1 or "").strip().lower() == "gpt-5.4-thinking":
                        logger.info(
                            "[KG-RAG DEBUG] Step1 gpt-5.4-thinking returned empty layers, retry once with gpt-5.4"
                        )
                        raw1_fallback, u1_fallback = await _call_kg_rag_llm(
                            step1_prompt, "gpt-5.4", temperature=0, max_tokens=800
                        )
                        r_fb, e_fb, p_fb, reason_fb = _parse_step1_layers(
                            raw1_fallback, outline_nature=outline_nature
                        )
                        logger.info(
                            f"[KG-RAG DEBUG] Step1 fallback raw stats: chars={len(raw1_fallback or '')}, "
                            f"preview={(raw1_fallback or '')[:300]}"
                        )
                        if r_fb or e_fb or p_fb:
                            raw1, u1 = raw1_fallback, u1_fallback
                            revelation, experience, practice, reasoning = r_fb, e_fb, p_fb, reason_fb
                            m1 = "gpt-5.4"
                            logger.info(
                                f"[KG-RAG DEBUG] Step1 fallback success: revelation={revelation}, experience={experience}, practice={practice}"
                            )
                    step1_extract_elapsed_ms = (asyncio.get_event_loop().time() - step1_extract_start) * 1000
                    logger.info(
                        f"[KG-RAG DEBUG] Step1 extraction_parse elapsed_ms={step1_extract_elapsed_ms:.1f}"
                    )
                    logger.info(
                        f"[KG-RAG DEBUG] Step 1 revelation: {revelation}, experience(校验前): {experience}, "
                        f"practice(校验前): {practice}, reasoning: {reasoning[:200] if reasoning else ''}"
                    )
                    concepts = []
                    seen = set()
                    for c in revelation + experience + practice:
                        if c not in seen:
                            seen.add(c)
                            concepts.append(c)
                except Exception as e:
                    result["steps"]["step1"] = {"concepts": [], "raw_response": "", "error": str(e)}
                step1_elapsed_ms = (asyncio.get_event_loop().time() - step1_start) * 1000
                if "step1" not in result["steps"]:
                    s1: dict[str, Any] = {
                        "concepts": concepts,
                        "revelation": revelation,
                        "experience": experience,
                        "practice": practice,
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
        else:
            logger.info("[KG-RAG DEBUG] mode 2.0: skip Step1")
            result["steps"]["step1"] = {
                "skipped": True,
                "reason": "mode_2.0",
                "concepts": [],
                "revelation": [],
                "experience": [],
                "practice": [],
                "reasoning": "",
                "elapsed_ms": 0.0,
                "raw_response": None,
            }
            step_elapsed_ms["step1"] = 0.0


        normalized = concepts

        if p.get("skip_skeleton_route") or skip_kg:
            logger.info("[KG-RAG DEBUG] skip_skeleton_route or mode 2.0: Step1/2 已跳过，进入 Step3")
        else:
            logger.info("[KG-RAG DEBUG] Step 1 done: concepts go directly to Step2")

        if p.get("stop_after_step1"):
            stop_after_step1 = p.get("stop_after_step1")
            logger.info(f"[KG-RAG DEBUG] stop_after_step1={stop_after_step1}，准备返回")
            result["stopped_after"] = "step1"
            result["steps"]["step2"] = {
                "skipped": True,
                "reason": "stop_after_step1",
                "paths": [],
                "paths_count": 0,
                "skeleton": None,
                "expanded_nodes": list(dict.fromkeys(revelation + experience + practice)),
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

        # Step 2 + Query Rewrite：rewrite prompt 提前构建；Step2 与 Query Rewrite LLM 并发（未 skip 时）
        bd_rw = (burden_description or "").strip()
        rewrite_input = f"{query}\n负担方向：{bd_rw}" if bd_rw else query
        rewrite_prompt = QUERY_REWRITE.format(query=rewrite_input)

        u_rw: dict[str, int] | None = None
        query_rewrite_parsed_ok = False
        rewritten_queries: list[str] = [query]

        async def _run_query_rewrite() -> tuple[list[str], bool, dict[str, int] | None]:
            try:
                t_rw0 = asyncio.get_event_loop().time()
                raw_rw, u_rw_local = await _call_kg_rag_llm(
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
                query_rewrite_parsed_ok_local = False
                rewritten_queries_local: list[str] = [query]
                if parsed:
                    rq_list = [str(q).strip() for q in parsed if str(q).strip()]
                    if rq_list:
                        rewritten_queries_local = rq_list
                        query_rewrite_parsed_ok_local = True
                    else:
                        rewritten_queries_local = [query]
                else:
                    rewritten_queries_local = [query]
                if not rewritten_queries_local:
                    rewritten_queries_local = [query]
                return rewritten_queries_local, query_rewrite_parsed_ok_local, u_rw_local
            except Exception:
                return [query], False, None

        async def _measure_step2() -> tuple[dict[str, Any], float]:
            t0 = asyncio.get_event_loop().time()
            s2 = await self._run_step2(
                query,
                revelation,
                experience,
                practice,
                normalized,
                p,
                llm_calls,
                burden_description=burden_description,
            )
            dt_ms = (asyncio.get_event_loop().time() - t0) * 1000
            return s2, dt_ms

        step2_start = asyncio.get_event_loop().time()
        if p.get("skip_skeleton_route") or skip_kg:
            logger.info("[KG-RAG DEBUG] skip_skeleton_route or mode 2.0: 跳过 Step2")
            step2_end = asyncio.get_event_loop().time()
            paths = []
            skeleton = None
            expanded_nodes = [] if skip_kg else list(dict.fromkeys(revelation + experience + practice))
            step2_body = {
                "paths": [],
                "paths_count": 0,
                "skeleton": None,
                "expanded_nodes": expanded_nodes,
                "elapsed_ms": round((step2_end - step2_start) * 1000, 1),
                "skipped": True,
                "reason": "mode_2.0" if skip_kg else "skip_skeleton_route",
            }
            result["steps"]["step2"] = step2_body
            logger.info("[KG-RAG DEBUG] Step2 skipped (skip_skeleton_route or mode 2.0)")
            if not p.get("skip_query_rewrite"):
                rewritten_queries, query_rewrite_parsed_ok, u_rw = await _run_query_rewrite()
        else:
            if p.get("skip_query_rewrite"):
                s2, dt_step2 = await _measure_step2()
            else:
                (s2, dt_step2), rw_pack = await asyncio.gather(
                    _measure_step2(),
                    _run_query_rewrite(),
                )
                rewritten_queries, query_rewrite_parsed_ok, u_rw = rw_pack

            step2_end = asyncio.get_event_loop().time()
            paths = s2["paths"]
            skeleton = s2["skeleton"]
            expanded_nodes = s2["expanded_nodes"]
            for k, v in (s2.get("llm_elapsed_ms") or {}).items():
                step_elapsed_ms[k] = round(float(v), 1)
            if s2.get("graph_error"):
                result["steps"]["step2_error"] = s2["graph_error"]
            step2_elapsed = round(dt_step2, 1)
            step_elapsed_ms["step2"] = step2_elapsed
            step2_body = {
                "paths": paths,
                "paths_count": len(paths),
                "skeleton": skeleton,
                "expanded_nodes": expanded_nodes,
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
                f"skeleton={'yes' if skeleton else 'no'}, elapsed_ms={step2_elapsed:.1f}"
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

        # Step 3: 三路检索（Query Rewrite 已在 Step2 阶段与骨架并发或单独完成）
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
        bm25_task = bm25_search(self.es, query, active_index, bm25_fetch_size)
        dense_tasks = [
            dense_search(self.es, rq, active_index, dense_fetch_size, p["num_candidates"])
            for rq in dense_query_list
        ]
        route3_tasks = []
        sk_top_k = int(p["skeleton_route_top_k"])
        if expanded_nodes and not p.get("skip_skeleton_route"):
            route3_tasks = [
                skeleton_route_search(
                    self.es, node, query, active_index, sk_top_k, outline_nature
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
        # 路3 每节点并入 expanded_results 的条数：skeleton_route_top_k // deep 概念数（skeleton_route_max_per_node 保留在 params 中供测试台等手动场景，此处不参与计算）
        # _sk_top_k 取自 merged 后的 p（深度模式已在上方把 p["skeleton_route_top_k"] 覆盖为 75，未使用字面量 45）
        _deep_count = len(expanded_nodes) if expanded_nodes else 1
        _sk_top_k = int(p["skeleton_route_top_k"])
        max_per_node = max(1, _sk_top_k // max(1, _deep_count))
        logger.info(
            f"[KG-RAG DEBUG] route3 expanded per-node cap: skeleton_route_top_k={_sk_top_k}, "
            f"deep_nodes={len(expanded_nodes) if expanded_nodes else 0}, max_per_node={max_per_node}"
        )
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
            skeleton_with_chunks = _build_skeleton_bound_prompt_block(
                skeleton, expanded_results, list(dict.fromkeys(revelation + experience + practice)), main_results,
            )
            ctx_head = skeleton_with_chunks[:500] if len(skeleton_with_chunks) > 500 else skeleton_with_chunks
            logger.info(
                "[KG-RAG DEBUG] Step5 context (skeleton_with_chunks) first_500_chars: %r",
                ctx_head,
            )
            if mode == "4.0":
                concepts_list = revelation + experience + practice
                concepts_text = "、".join(concepts_list) if concepts_list else "（无）"
                base_prompt = STEP5_GENERATION_V4.format(
                    query=query,
                    metadata_block=metadata_block,
                    concepts=concepts_text,
                    skeleton_with_chunks=skeleton_with_chunks,
                )
            else:
                base_prompt = STEP5_GENERATION.format(
                    query=query,
                    metadata_block=metadata_block,
                    skeleton_with_chunks=skeleton_with_chunks,
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
            if mode == "4.0":
                concepts_list = revelation + experience + practice
                concepts_text = "、".join(concepts_list) if concepts_list else "（无）"
                base_prompt = STEP5_GENERATION_FLAT_V4.format(
                    query=query,
                    metadata_block=metadata_block,
                    concepts=concepts_text,
                    chunks=chunks_text,
                )
            else:
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
            step5_model = p.get("step5_model") or FULL_QUERY_STEP5_MODEL
            t5_0 = asyncio.get_event_loop().time()
            gen, u5 = await _call_kg_rag_llm(
                step5_prompt, step5_model, temperature=p["temperature"], max_tokens=4096, system=None
            )
            step_elapsed_ms["step5"] = round((asyncio.get_event_loop().time() - t5_0) * 1000, 1)
            result["answer"] = gen.strip() if gen else None
            s5: dict[str, Any] = {"answer": result["answer"], "model": step5_model}
            sn5 = register_llm_usage(llm_calls, step="step5", request_model=step5_model, usage=u5)
            if sn5:
                s5["llm_usage"] = sn5
                logger.info(
                    f"[KG-RAG LLM] step5 model={step5_model} billing={sn5['billing_model']} "
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
                    "revelation": step1_data.get("revelation", []),
                    "experience": step1_data.get("experience", []),
                    "practice": step1_data.get("practice", []),
                    "reasoning": step1_data.get("reasoning", ""),
                    "skeleton": (result["steps"].get("step2") or {}).get("skeleton"),
                    "main_sources": _extract_main_sources(
                        (step3_data.get("main_results") or [])
                        + (step3_data.get("expanded_results") or [])
                    ),
                    "total_elapsed_ms": llm_usage.get("total_elapsed_ms"),
                    "total_cost_usd": (llm_usage.get("totals") or {}).get("cost_usd"),
                    "answer_en": None,
                    "answer_zh_tw": None,
                }
                self.redis.setex(cache_key, CACHE_TTL, json.dumps(cache_value, ensure_ascii=False))
                logger.info(f"[KG-RAG CACHE] written: key={cache_key}, ttl={CACHE_TTL}")
            except Exception as e:
                logger.warning(f"[KG-RAG CACHE] write error: {e}")

        # === 监控写入 ===
        try:
            monitoring = get_monitoring(self.redis)
            req_params = params or {}

            # 基础字段
            query_str = query
            cache_hit = bool(result.get("from_cache", False) or result.get("cached", False))
            elapsed_ms = float(result.get("total_elapsed_ms") or (result.get("llm_usage") or {}).get("total_elapsed_ms") or 0)
            cost = float(result.get("total_cost_usd") or ((result.get("llm_usage") or {}).get("totals") or {}).get("cost_usd") or 0.0)

            llm_usage = result.get("llm_usage") or {}
            totals = llm_usage.get("totals") or {}
            input_tokens = int(totals.get("input_tokens") or 0)
            output_tokens = int(totals.get("output_tokens") or 0)

            outline_nature = req_params.get("outline_nature") or "一般性"
            depth = "深度" if (req_params.get("depth") == "deep") else "普通"
            burden_description = req_params.get("burden_description") or ""
            burden_flag = "是" if str(burden_description).strip() else "否"

            monitoring.record_query(
                question=query_str,
                response_time_ms=elapsed_ms,
                cache_hit=cache_hit,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost=cost,
                special_needs=outline_nature,
                mode="KG-RAG",
                depth=depth,
                api_type="claude",
            )

            # 检索统计（仅非缓存命中时才有意义）
            if not cache_hit:
                step3_data = result.get("steps", {}).get("step3") or {}
                main_sources = _extract_main_sources(step3_data.get("main_results") or [])
                main_results = step3_data.get("main_results") or []
                expanded = step3_data.get("expanded_results") or []
                total_retrieved = len(main_results) + len(expanded)
                used_count = len(main_sources)
                waste_rate = round((1 - used_count / total_retrieved) * 100, 1) if total_retrieved > 0 else 0.0

                monitoring.record_retrieval_stats(
                    question_preview=query_str[:30],
                    total=total_retrieved,
                    used=used_count,
                    waste_rate=waste_rate,
                    mode="KG-RAG",
                    depth=depth,
                    burden=burden_flag,
                )
        except Exception as e:
            logger.warning(f"[KG-RAG] 监控写入失败（不影响主流程）: {e}")
        # === 监控写入结束 ===

        return result

    async def generate_burden_description(
        self,
        query: str,
        outline_nature: str = "",
        audience: str = "",
        reference_excerpt: str = "",
        model: str = "claude-sonnet-4-6",
    ) -> dict[str, Any]:
        """根据主题与上下文生成负担说明（情境 A 单条 / 情境 B 三候选）。"""
        query_v = (query or "").strip()
        outline_v = (outline_nature or "").strip() or "（未填）"
        audience_v = (audience or "").strip() or "（未填）"
        excerpt_v = (reference_excerpt or "").strip() or "（空）"
        prompt = BURDEN_DESCRIPTION_PROMPT.format(
            query=query_v,
            outline_nature=outline_v,
            audience=audience_v,
            reference_excerpt=excerpt_v,
        )
        logger.info(
            "[KG-RAG BURDEN DEBUG] request: query_len=%s outline=%r audience=%r excerpt_len=%s prompt_len=%s",
            len(query_v),
            outline_v,
            audience_v,
            len(excerpt_v if excerpt_v != "（空）" else ""),
            len(prompt),
        )
        raw, usage = await _call_kg_rag_llm(
            prompt,
            model,
            temperature=0.3,
            max_tokens=_max_tokens_for_model(model, 1200),
            system=BURDEN_DESCRIPTION_SYSTEM,
        )
        raw_text = raw or ""
        logger.info(
            "[KG-RAG BURDEN DEBUG] llm response: raw_len=%s preview=%r",
            len(raw_text),
            raw_text[:500],
        )
        parsed = _parse_burden_generation_output(raw_text)
        logger.info(
            "[KG-RAG BURDEN DEBUG] parsed: scenario=%s has_error=%s keys=%s",
            parsed.get("scenario"),
            bool(parsed.get("error")),
            list(parsed.keys()),
        )
        llm_calls: list[dict[str, Any]] = []
        sn = register_llm_usage(
            llm_calls, step="generate_burden", request_model=model, usage=usage
        )
        if sn:
            parsed["llm_usage"] = sn
            parsed["model"] = model
            logger.info(
                "[KG-RAG LLM] generate_burden model=%s billing=%s in=%s out=%s cost_usd≈%s",
                model,
                sn["billing_model"],
                sn["input_tokens"],
                sn["output_tokens"],
                sn["cost_usd"],
            )
        return parsed

    async def generate_bird_view_skeleton(
        self,
        keyword: str,
        content_type: str,
        content: str,
    ) -> dict:
        """为鸟瞰纲目生成骨架（4-7步 JSON）。"""
        prompt = BIRD_VIEW_SKELETON_PROMPT.format(
            keyword=keyword,
            content=content,
        )
        raw, usage = await _call_kg_rag_llm(
            prompt,
            "claude-sonnet-4-6",
            temperature=0,
            max_tokens=1000,
        )
        obj = _safe_parse_json(raw or "")
        steps = obj.get("skeleton", []) if obj else []
        skeleton_text = "\n".join(
            f"{i + 1}. {s.get('step', '')}" for i, s in enumerate(steps)
        )
        return {
            "skeleton_json": steps,
            "skeleton_text": skeleton_text,
            "type": content_type,
        }

    async def generate_bird_view_outline(
        self,
        keyword: str,
        content_type: str,
        content: str,
        skeleton: str,
    ) -> dict:
        """根据骨架与原文生成鸟瞰纲目正文。"""
        prompt = BIRD_VIEW_OUTLINE_PROMPT.format(
            keyword=keyword,
            skeleton=skeleton,
            content=content,
        )
        raw, usage = await _call_kg_rag_llm(
            prompt,
            "claude-sonnet-4-6",
            temperature=0,
            max_tokens=8000,
        )
        # 提取最后一个完整代码块（处理模型先输出推理再输出代码块的情况）
        text = (_strip_code_fence_for_outline(raw) or (raw or "")).strip()
        return {
            "outline": text,
            "type": content_type,
        }

    async def generate_bird_view_with_source(
        self,
        keyword: str,
        content_type: str,
        content: str,
        outline: str,
    ) -> dict:
        """为鸟瞰纲目加出处，返回带出处的纲目正文。"""
        if content_type == "ministry":
            prompt = BIRD_VIEW_SOURCE_PROMPT_MINISTRY.format(
                content=content,
                outline=outline,
            )
        else:
            prompt = BIRD_VIEW_SOURCE_PROMPT_FEAST.format(
                content=content,
                outline=outline,
            )
        raw, usage = await _call_kg_rag_llm(
            prompt,
            "claude-sonnet-4-6",
            temperature=0,
            max_tokens=8000,
        )
        # 提取最后一个完整代码块（处理模型先输出推理再输出代码块的情况）
        text = (_strip_code_fence_for_outline(raw) or (raw or "")).strip()
        return {
            "outline_with_source": text,
            "type": content_type,
        }

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
        full = await self.full_query(
            query, {**(params or {}), "skip_generation": True}, mode="3.0"
        )
        full["steps"].pop("step5", None)
        full["answer"] = None
        return full


# ---------------------------------------------------------------------------
# 纲目职事化：逐条检索 + 重排 + Claude 抽句
# ---------------------------------------------------------------------------

MINISTERIALIZE_CLAUDE_MODEL = "claude-haiku-4-5-20251001"
MINISTERIALIZE_JUDGE_MODEL = "claude-haiku-4-5-20251001"
_MINISTERIALIZE_PREFIX_RE = re.compile(
    r"^[壹貳贰參叄叁参肆伍陸陆柒捌玖拾一二三四五六七八九十\da-z（）()]+[\t　]"
)
# 圣经 66 卷常用简称单字集（旧约+新约拆字去重，供 _BOOK_PAT 字符类使用）
_BIBLE_BOOKS_66 = (
    "创出利民申书士得撒上撒下王上王下代上代下拉尼斯伯诗箴传歌赛耶哀结但"
    "何珥摩俄拿弥鸿哈番该亚玛"
    "太可路约徒罗林前林后加弗腓西帖前帖后提前提后多门来雅彼前彼后约壹约贰约叁犹启"
    "参"  # 参书（纲目参考，非 66 卷正典简称）
)
_BIBLE_BOOKS = "".join(dict.fromkeys(_BIBLE_BOOKS_66))  # 去重保序
_BOOK_PAT = rf"[{_BIBLE_BOOKS}]{{1,4}}"
_CHAP_PAT = r"[\d一二三四五六七八九十百～~\-至、\s]+"
_REF_UNIT = rf"(?:{_BOOK_PAT})?{_CHAP_PAT}"  # 书卷名可选，支持「十四34」纯章节
_SCRIPTURE_REF_RE = re.compile(
    rf"(—{_BOOK_PAT}{_CHAP_PAT}(?:[,，；;]{_REF_UNIT})*[：:。]?\s*)$"
)
_PURE_VERSE_RE = re.compile(r"(—[\d～~\-至、\s\d]+节[。：:]?\s*)$")


def _find_scripture_suffix(rest: str) -> tuple[str, str]:
    """从 rest 里识别经文 suffix，返回 (body, suffix)。"""
    matches = list(_SCRIPTURE_REF_RE.finditer(rest))
    if matches:
        m = matches[-1]
        return rest[: m.start()], m.group(0)
    m = _PURE_VERSE_RE.search(rest)
    if m:
        return rest[: m.start()], m.group(0)
    return rest, ""


MINISTERIALIZE_PROMPT_TEMPLATE = """你是一个职事语言抽取助手。

任务：从下方职事摘录中，找出语义最贴近纲目条目的一句原文，直接返回该句，不得改写、不得添加任何解释。

判断标准：
- 返回的句子必须与纲目条目语义高度吻合，核心意思基本一致
- 如果两段摘录中都没有语义足够贴近的句子，只返回空字符串，不要强行抽取
- 返回的句子中，分句之间只能用中文分号（；）连接，不得出现中文句号（。）
- 若语义不够贴近，返回空字符串。

重要规则：若原纲目中某些内容在上述摘录中找不到对应原文，请将该部分原样保留，不得删除、截短或替换；最终输出必须包含原纲目的所有实质内容，不得遗漏任何子句。

纲目条目：{line}

摘录一：{excerpt1}

摘录二：{excerpt2}

只输出抽取的原句（或空字符串），不得输出任何分析过程、自问检查、解释说明或标记符号。
"""


def _parse_outline_line(line: str) -> tuple[str, str, str]:
    """
    返回 (prefix, body, suffix)
    prefix: 行首编号+分隔符，如 "壹\t"
    suffix: 经文引用后缀，如 "—哀三22~23："，没有则为 ""
    body: 中间正文
    """
    text = line
    m = _MINISTERIALIZE_PREFIX_RE.match(text)
    if m:
        prefix = m.group(0)
        rest = text[m.end() :]
    else:
        prefix = ""
        rest = text

    body, suffix = _find_scripture_suffix(rest)

    return prefix, body, suffix


def _assemble_outline_line(prefix: str, body: str, suffix: str) -> str:
    result_body = re.sub(r"[。，、；：,;.]+$", "", body.strip())
    result_body = result_body.replace("。", "；")  # 兜底：正文内句号改分号
    return prefix + result_body + suffix


def _overlap_ratio(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    chars_a = set(a)
    chars_b = set(b)
    return len(chars_a & chars_b) / max(len(chars_a), len(chars_b))


def _is_minor_edit(a: str, b: str, threshold: int = 5) -> bool:
    """判断两个字符串是否只有微小差异（编辑距离≤threshold）"""
    if a == b:
        return False  # 完全相同走 original，不走这里
    len_a, len_b = len(a), len(b)
    if abs(len_a - len_b) > threshold:
        return False
    prev = list(range(len_b + 1))
    for i in range(1, len_a + 1):
        curr = [i] + [0] * len_b
        for j in range(1, len_b + 1):
            if a[i - 1] == b[j - 1]:
                curr[j] = prev[j - 1]
            else:
                curr[j] = 1 + min(prev[j], curr[j - 1], prev[j - 1])
        if min(curr) > threshold:
            return False
        prev = curr
    return prev[len_b] <= threshold


async def _judge_ministerialize_status(
    original_body: str, claude_output: str
) -> tuple[str, dict[str, int] | None]:
    """
    用 Claude Haiku 判断职事化结果的状态。
    返回值：('original' | 'minor' | 'replaced' | 'manual', usage)
    """
    prompt = f"""你是一位熟悉职事书写作风格的编辑助手。请判断「替换后纲目」相对于「原纲目」的修改程度，返回以下四种状态之一：

original：替换后纲目与原纲目完全相同，或仅有标点符号差异。
minor：替换后纲目对原纲目做了轻微调整——例如增删衔接词、连接词、语气助词，或个别字词微调，但核心内容与表述方式基本不变，原纲目的主体句子在替换后仍清晰可见。
replaced：替换后纲目对原纲目有实质性改写——核心表述被重新组织、概括或改写，已不是原句的轻微变体。
manual：替换后纲目与原纲目几乎无关，或替换后内容明显不是从职事信息原文提取的。

原纲目：{original_body}
替换后纲目：{claude_output}

只输出一个词：original、minor、replaced 或 manual，不要有任何其他内容。"""

    try:
        output, usage = await _call_claude(
            prompt,
            MINISTERIALIZE_JUDGE_MODEL,
            temperature=0,
            max_tokens=10,
            system="你是一位专业编辑助手，只输出一个判断词。",
        )
        status = (output or "").strip().lower()
        if status in ("original", "minor", "replaced", "manual"):
            return status, usage
        logger.warning("[职事化判断] Haiku 返回非预期值: %s，fallback 到 replaced", status)
        return "replaced", usage
    except Exception as e:
        logger.warning("[职事化判断] Haiku 调用失败: %s，fallback 到 replaced", e)
        return "replaced", None


async def _ministerialize_one_line(es_client: Any, line: str, index: int) -> dict:
    """单条纲目：解析结构 → BM25/Dense 仅用 body → 拼回 prefix/suffix。"""
    prefix, body, suffix = _parse_outline_line(line)
    body_stripped = body.strip()
    sonnet_input_tokens = 0
    sonnet_output_tokens = 0
    haiku_input_tokens = 0
    haiku_output_tokens = 0

    def _add_sonnet_usage(u: dict[str, int] | None) -> None:
        nonlocal sonnet_input_tokens, sonnet_output_tokens
        if u:
            sonnet_input_tokens += int(u.get("input_tokens", 0) or 0)
            sonnet_output_tokens += int(u.get("output_tokens", 0) or 0)

    def _add_haiku_usage(u: dict[str, int] | None) -> None:
        nonlocal haiku_input_tokens, haiku_output_tokens
        if u:
            haiku_input_tokens += int(u.get("input_tokens", 0) or 0)
            haiku_output_tokens += int(u.get("output_tokens", 0) or 0)

    def _usage_out() -> dict[str, int]:
        return {
            "sonnet_input": sonnet_input_tokens,
            "sonnet_output": sonnet_output_tokens,
            "haiku_input": haiku_input_tokens,
            "haiku_output": haiku_output_tokens,
        }

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

    if not body_stripped:
        return {
            "index": index,
            "original": line,
            "status": "manual",
            "result": line,
            "suggestion": "",
            "source": "",
            "usage": _usage_out(),
        }

    bm25_results = await bm25_search(es_client, body_stripped, _INDICES_BASE, 5)
    dense_results = await dense_search(es_client, body_stripped, _INDICES_BASE, 20, 100)
    merged = await rrf_merge(bm25_results, dense_results, k=60, bm25_weight=1.0, dense_weight=1.0)
    reranked = await rerank(merged, body_stripped, 3)

    if not reranked:
        return {
            "index": index,
            "original": line,
            "status": "manual",
            "result": _assemble_outline_line(prefix, body, suffix),
            "suggestion": "",
            "source": "",
            "usage": _usage_out(),
        }

    top1_source = _extract_source(reranked[0])
    top1_text = reranked[0].get("text") or ""
    if body_stripped in top1_text:
        return {
            "index": index,
            "original": line,
            "status": "original",
            "result": _assemble_outline_line(prefix, body, suffix),
            "suggestion": "",
            "source": top1_source,
            "usage": _usage_out(),
        }

    excerpt1 = reranked[0].get("text", "") if len(reranked) > 0 else ""
    excerpt2 = reranked[1].get("text", "") if len(reranked) > 1 else ""
    prompt = MINISTERIALIZE_PROMPT_TEMPLATE.format(
        line=body_stripped,
        excerpt1=excerpt1,
        excerpt2=excerpt2,
    )
    try:
        claude_output, _usage = await _call_claude(
            prompt,
            MINISTERIALIZE_CLAUDE_MODEL,
            temperature=0,
            max_tokens=200,
            system="你是一位专业、精确的助手。请严格按要求的格式输出。",
        )
        _add_sonnet_usage(_usage)
        raw_output = (claude_output or "").strip()
        if raw_output and any(m in raw_output for m in ("自问", "检查", "**")):
            first_line = ""
            for ln in raw_output.splitlines():
                ln = ln.strip()
                if ln:
                    first_line = ln
                    break
            raw_output = first_line
        output = raw_output
        if output:
            clean_output = re.sub(r"[。，、；：,;.]+$", "", output.strip()).strip()
            if clean_output == body_stripped:
                return {
                    "index": index,
                    "original": line,
                    "status": "original",
                    "result": _assemble_outline_line(prefix, body, suffix),
                    "suggestion": "",
                    "source": top1_source,
                    "usage": _usage_out(),
                }
            # 用 Haiku 判断语义修改程度
            status, _jusage = await _judge_ministerialize_status(body_stripped, clean_output)
            _add_haiku_usage(_jusage)
            if status == "manual":
                return {
                    "index": index,
                    "original": line,
                    "status": status,
                    "result": _assemble_outline_line(prefix, body, suffix),
                    "suggestion": "",
                    "source": "",
                    "usage": _usage_out(),
                }
            if status == "minor":
                return {
                    "index": index,
                    "original": line,
                    "status": status,
                    "result": _assemble_outline_line(prefix, body, suffix),
                    "suggestion": _assemble_outline_line(prefix, clean_output, suffix),
                    "source": top1_source,
                    "usage": _usage_out(),
                }
            return {
                "index": index,
                "original": line,
                "status": status,
                "result": _assemble_outline_line(prefix, clean_output, suffix),
                "suggestion": "",
                "source": top1_source,
                "usage": _usage_out(),
            }
    except Exception as e:
        logger.warning("[纲目职事化] Claude 调用失败 index=%s: %s", index, e)

    return {
        "index": index,
        "original": line,
        "status": "manual",
        "result": _assemble_outline_line(prefix, body, suffix),
        "suggestion": "",
        "source": "",
        "usage": _usage_out(),
    }


async def ministerialize_outline(lines: list[str]) -> dict:
    """
    纲目职事化：对每条非空纲目并发执行检索与抽句，保持原始行号顺序返回。
    返回 results、汇总 usage（Sonnet/Haiku 分列）与分模型单价计算的 cost_usd。
    """
    try:
        from es_config import es as es_client
    except ImportError:
        _backend = str(Path(__file__).resolve().parents[1])
        if _backend not in __import__("sys").path:
            __import__("sys").path.insert(0, _backend)
        from es_config import es as es_client

    items = [(i, line) for i, line in enumerate(lines) if (line or "").strip()]
    if not items:
        return {
            "results": [],
            "usage": {
                "sonnet_input": 0,
                "sonnet_output": 0,
                "haiku_input": 0,
                "haiku_output": 0,
            },
            "cost_usd": 0.0,
        }

    results = await asyncio.gather(
        *[_ministerialize_one_line(es_client, line, i) for i, line in items]
    )
    sorted_results = sorted(results, key=lambda x: x["index"])

    sonnet_in = sum(r.get("usage", {}).get("sonnet_input", 0) for r in sorted_results)
    sonnet_out = sum(r.get("usage", {}).get("sonnet_output", 0) for r in sorted_results)
    haiku_in = sum(r.get("usage", {}).get("haiku_input", 0) for r in sorted_results)
    haiku_out = sum(r.get("usage", {}).get("haiku_output", 0) for r in sorted_results)

    # 两个模型均为 claude-haiku-4-5: $1/M input, $5/M output
    cost_usd = ((sonnet_in + haiku_in) * 1 + (sonnet_out + haiku_out) * 5) / 1_000_000

    for r in sorted_results:
        r.pop("usage", None)

    return {
        "results": sorted_results,
        "usage": {
            "sonnet_input": sonnet_in,
            "sonnet_output": sonnet_out,
            "haiku_input": haiku_in,
            "haiku_output": haiku_out,
        },
        "cost_usd": round(cost_usd, 6),
    }
