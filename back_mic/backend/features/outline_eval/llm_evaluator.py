# -*- coding: utf-8 -*-
"""纲目品质评估：并发调用 Claude 执行 F1-F4 / T1-T4 八维评估。"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any

import anthropic

from .prompts import (
    PROMPT_F1,
    PROMPT_F2,
    PROMPT_F3,
    PROMPT_F4,
    PROMPT_T1,
    PROMPT_T2,
    PROMPT_T3,
    PROMPT_T4,
    PROMPT_SYNTHESIS,
)

_MODEL_F = "claude-haiku-4-5-20251001"
_MODEL_T = "claude-sonnet-4-6"

# 各模型单价（per token）
_MODEL_PRICING = {
    "claude-haiku-4-5-20251001": {
        "input": 0.80 / 1_000_000,
        "output": 4.00 / 1_000_000,
    },
    "claude-sonnet-4-6": {
        "input": 3.00 / 1_000_000,
        "output": 15.00 / 1_000_000,
    },
}

_SYSTEM_PROMPT = (
    "你只能以合法的 JSON 对象格式回复，"
    "不得包含任何前缀文字、解释说明或 Markdown 代码块。"
    "直接输出 JSON，第一个字符必须是 '{'，最后一个字符必须是 '}'。"
    "JSON 字符串值内禁止使用英文双引号，引用短语请用「」或『』。"
)

_SECOND_EVAL_SUFFIX = """

【上轮评估评语】
{prev_comment}

请在 JSON 中额外增加字段 "improvement_note": "<相较上轮是否有改善，简述；若无变化请说明>"。"""

_DIM_KEYS = ("F1", "F2", "F3", "F4", "T1", "T2", "T3", "T4")

_T1_LAYER_KEYS = ("L1", "L2", "L3", "L4")
_T2_S_KEYS = ("S1", "S2", "S3", "S4", "S5", "S6")
_T3_R_KEYS = ("R1", "R2", "R3", "R4")
_T3_E_KEYS = ("E1", "E2", "E3", "E4")
_T3_P_KEYS = ("P1", "P2", "P3", "P4")
_T3_FRAMEWORK_KEYS: dict[str, tuple[str, ...]] = {
    "R系": _T3_R_KEYS,
    "E系": _T3_E_KEYS,
    "P系": _T3_P_KEYS,
}
_DEFAULT_STEP_DIM = {"score": 5, "comment": "解析失败", "gap": None}
_DEFAULT_T3_DIM = {"score": 5, "comment": "解析失败", "gap": None}

logger = logging.getLogger(__name__)


def _repair_unescaped_quotes_in_json(s: str) -> str:
    """修复模型在 JSON 字符串值内用 ASCII 双引号引用短语导致的非法 JSON。"""
    pattern = (
        r'([\u4e00-\u9fff，。、；：！？])'
        r'"([^"\\]{1,120})"'
        r'([\u4e00-\u9fff，。、；：！？])'
    )
    prev = None
    result = s
    while prev != result:
        prev = result
        result = re.sub(pattern, r"\1「\2」\3", result)
    return result


def _parse_json_dict(text: str) -> dict[str, Any]:
    if not text or not str(text).strip():
        return {"error": "空响应"}
    s = str(text).strip()

    # 剥离 markdown 代码块（含 ```json 前缀）
    if "```" in s:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)```", s)
        if match:
            s = match.group(1).strip()

    # 尝试直接解析
    for candidate in (s, _repair_unescaped_quotes_in_json(s)):
        try:
            obj = json.loads(candidate)
            return obj if isinstance(obj, dict) else {"error": "响应非 JSON 对象"}
        except json.JSONDecodeError:
            pass

    # 提取第一个 { 到最后一个 } 之间的内容
    first = s.find("{")
    last = s.rfind("}")
    if first >= 0 and last > first:
        chunk = s[first : last + 1]
        for candidate in (chunk, _repair_unescaped_quotes_in_json(chunk)):
            try:
                obj = json.loads(candidate)
                return obj if isinstance(obj, dict) else {"error": "响应非 JSON 对象"}
            except json.JSONDecodeError:
                pass

    # 截断 JSON 补全：未闭合的花括号补齐后再解析
    if first >= 0:
        truncated = s[first:]
        open_count = truncated.count("{") - truncated.count("}")
        if open_count > 0:
            padded = (
                truncated
                + ('"' if truncated.rstrip()[-1] not in '"}]' else "")
                + "}" * open_count
            )
            try:
                obj = json.loads(padded)
                return obj if isinstance(obj, dict) else {"error": "响应非 JSON 对象"}
            except json.JSONDecodeError:
                pass

    logger.warning(f"[outline_eval] JSON 解析失败，原始内容前800字：{s[:800]}")
    return {"error": "JSON 解析失败", "raw": s[:500]}


def _normalize_gap(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("null", "none", "无", "n/a"):
        return None
    return s


def _sub_score(result: dict[str, Any], key: str) -> float | None:
    block = result.get(key)
    if not isinstance(block, dict) or block.get("score") is None:
        return None
    try:
        return float(block["score"])
    except (TypeError, ValueError):
        return None


def _sum_sub_scores(result: dict[str, Any], keys: tuple[str, ...]) -> float | None:
    if "error" in result:
        return None
    scores = [_sub_score(result, k) for k in keys]
    valid = [s for s in scores if s is not None]
    return sum(valid) if valid else None


def _normalize_sub_dims(
    result: dict[str, Any],
    keys: tuple[str, ...],
) -> None:
    for k in keys:
        block = result.get(k)
        if isinstance(block, dict) and "gap" in block:
            block["gap"] = _normalize_gap(block.get("gap"))


def _normalize_t1(result: dict[str, Any]) -> dict[str, Any]:
    if "error" in result:
        return result
    _normalize_sub_dims(result, _T1_LAYER_KEYS)
    if result.get("total") is None:
        total = _sum_sub_scores(result, _T1_LAYER_KEYS)
        if total is not None:
            result["total"] = total
        else:
            result["total"] = 20
    nature_fit = result.get("nature_fit")
    if not isinstance(nature_fit, dict):
        result["nature_fit"] = {"fit": False, "note": "解析失败"}
    else:
        if "fit" not in nature_fit:
            nature_fit["fit"] = False
        if not str(nature_fit.get("note") or "").strip():
            nature_fit["note"] = "解析失败"
    weak_citations = result.get("weak_citations")
    if isinstance(weak_citations, list):
        for item in weak_citations:
            if isinstance(item, dict) and item.get("original_text") is None:
                item["original_text"] = ""
    return result


def _normalize_t2(raw: dict[str, Any]) -> dict[str, Any]:
    if "error" in raw:
        return raw
    result = dict(raw)
    for k in _T2_S_KEYS:
        block = result.get(k)
        if not isinstance(block, dict) or block.get("score") is None:
            result[k] = dict(_DEFAULT_STEP_DIM)
        else:
            if "gap" in block:
                block["gap"] = _normalize_gap(block.get("gap"))
    if result.get("summary") is None:
        result["summary"] = ""
    return result


def _detect_t3_framework(result: dict[str, Any]) -> str:
    framework_type = str(result.get("framework_type") or "").strip()
    if framework_type in _T3_FRAMEWORK_KEYS:
        return framework_type
    for fw, keys in _T3_FRAMEWORK_KEYS.items():
        if any(isinstance(result.get(k), dict) for k in keys):
            return fw
    return "R系"


def _normalize_t3(raw: dict[str, Any]) -> dict[str, Any]:
    if "error" in raw:
        return raw
    result = dict(raw)
    framework_type = _detect_t3_framework(result)
    result["framework_type"] = framework_type
    dim_keys = _T3_FRAMEWORK_KEYS[framework_type]
    for k in dim_keys:
        block = result.get(k)
        if not isinstance(block, dict) or block.get("score") is None:
            result[k] = dict(_DEFAULT_T3_DIM)
        else:
            if "gap" in block:
                block["gap"] = _normalize_gap(block.get("gap"))
    if result.get("coherence") is None:
        result["coherence"] = 5
    if result.get("structural_tension") is None:
        result["structural_tension"] = 5
    if result.get("total") is None:
        total = _sum_sub_scores(result, dim_keys)
        if total is not None:
            result["total"] = total
    if result.get("summary") is None:
        result["summary"] = ""
    return result


def _normalize_t4(raw: dict[str, Any]) -> dict[str, Any]:
    if "error" in raw:
        return raw
    result = dict(raw)
    if result.get("score") is None:
        result["score"] = 5
    if not str(result.get("sharpness_type") or "").strip():
        result["sharpness_type"] = "启示深度"
    if result.get("comment") is None:
        result["comment"] = ""
    if result.get("supply_paragraph") is None:
        result["supply_paragraph"] = ""
    return result


def _substitute_prompt(template: str, **kwargs: str) -> str:
    """替换 {key} 占位符，避免 .format() 误解析 JSON 示例中的花括号。"""
    result = template
    for key, value in kwargs.items():
        result = result.replace("{" + key + "}", value)
    return result


def _calc_call_cost(
    input_tokens: int,
    output_tokens: int,
    model: str = _MODEL_T,
) -> float:
    pricing = _MODEL_PRICING.get(model, _MODEL_PRICING[_MODEL_T])
    return input_tokens * pricing["input"] + output_tokens * pricing["output"]


def _pop_usage(result: dict[str, Any]) -> tuple[dict[str, Any], int, int, float]:
    input_tokens = int(result.pop("_input_tokens", 0) or 0)
    output_tokens = int(result.pop("_output_tokens", 0) or 0)
    cost_usd = float(result.pop("_cost_usd", 0) or 0)
    return result, input_tokens, output_tokens, cost_usd


def _append_second_eval(prompt: str, prev_comment: str | None) -> str:
    if not prev_comment or not str(prev_comment).strip():
        return prompt
    return prompt + _SECOND_EVAL_SUFFIX.format(prev_comment=str(prev_comment).strip())


def _format_skeleton(skeleton: list[dict[str, Any]] | None) -> tuple[str, str]:
    steps: list[str] = []
    paths: list[str] = []
    for i, item in enumerate(skeleton or [], start=1):
        step_text = str(item.get("step") or "").strip()
        path_text = str(item.get("path_evidence") or "").strip() or "无"
        steps.append(f"第{i}步：{step_text}")
        paths.append(f"第{i}步：{path_text}")
    return "\n".join(steps), "\n".join(paths)


def _prev_comment(eval_v1: dict[str, Any] | None, dim: str) -> str | None:
    if not eval_v1:
        return None
    block = eval_v1.get(dim)
    if not isinstance(block, dict):
        if dim.startswith("F"):
            pansai = eval_v1.get("pansai_layer")
            if isinstance(pansai, dict):
                block = pansai.get(dim)
        elif dim.startswith("T"):
            theology = eval_v1.get("theology_layer")
            if isinstance(theology, dict):
                block = theology.get(dim)
    if not isinstance(block, dict):
        return None
    return block.get("comment") or block.get("summary") or block.get("overall_comment")


def _merge_scripture_suggestions(
    t1_result: dict[str, Any],
    skeleton: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    weak_citations = list(t1_result.get("weak_citations") or [])
    if not weak_citations:
        return []

    anchor_entries: list[dict[str, str]] = []
    for i, step in enumerate(skeleton or [], start=1):
        anchor = step.get("scripture_anchor")
        if not anchor or not str(anchor).strip():
            continue
        anchor_entries.append(
            {
                "step_index": str(i),
                "step": str(step.get("step") or "").strip(),
                "scripture_anchor": str(anchor).strip(),
            }
        )

    suggestions: list[dict[str, Any]] = []
    for wc in weak_citations:
        if not isinstance(wc, dict):
            continue
        item = dict(wc)
        current_verse = str(item.get("current_verse") or "").strip()
        matched_anchor: str | None = None
        matched_step: str | None = None

        for entry in anchor_entries:
            anchor = entry["scripture_anchor"]
            if current_verse and (current_verse in anchor or anchor.startswith(current_verse)):
                matched_anchor = anchor
                matched_step = entry["step"]
                break

        if matched_anchor:
            item["skeleton_recommendation"] = matched_anchor
            if matched_step:
                item["skeleton_step"] = matched_step
        else:
            item["skeleton_recommendation"] = None

        suggestions.append(item)

    return suggestions


def _calc_total_score(
    t1: dict[str, Any],
    t2: dict[str, Any],
    t3: dict[str, Any],
    t4: dict[str, Any],
    f1: dict[str, Any],
    f2: dict[str, Any],
    f3: dict[str, Any],
    f4: dict[str, Any],
) -> float:
    def _num(result: dict[str, Any], key: str, default: float = 0.0) -> float:
        if "error" in result:
            return default
        try:
            return float(result.get(key) or default)
        except (TypeError, ValueError):
            return default

    t1_s = (_num(t1, "total") / 40 * 100) * 0.10
    t2_s = _num(t2, "weighted_score") * 0.40
    t3_s = (_num(t3, "total") / 40 * 100) * 0.35
    t4_s = (_num(t4, "score") / 10 * 100) * 0.15

    return round(t1_s + t2_s + t3_s + t4_s, 1)


async def _call_claude(
    system: str,
    user: str,
    model: str = _MODEL_T,
    max_tokens: int = 1500,
) -> dict[str, Any]:
    api_key = (os.environ.get("CLAUDE_API_KEY") or os.environ.get("ANTHROPIC_API_KEY") or "").strip()
    if not api_key:
        return {"error": "Claude 未配置（请设置 CLAUDE_API_KEY）"}

    def _sync() -> dict[str, Any]:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = ""
        if response.content and getattr(response.content[0], "text", None):
            text = response.content[0].text
        usage = response.usage
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        parsed = _parse_json_dict(text)
        parsed["_input_tokens"] = input_tokens
        parsed["_output_tokens"] = output_tokens
        parsed["_cost_usd"] = _calc_call_cost(input_tokens, output_tokens, model)
        return parsed

    try:
        return await asyncio.to_thread(_sync)
    except Exception as e:
        return {"error": str(e)}


async def eval_F1(
    answer: str,
    revelation: str,
    experience: str,
    practice: str,
    query: str,
    *,
    prev_comment: str | None = None,
) -> dict[str, Any]:
    user = _append_second_eval(
        _substitute_prompt(
            PROMPT_F1,
            query=query,
            revelation=revelation,
            experience=experience,
            practice=practice,
            answer=answer,
        ),
        prev_comment,
    )
    return await _call_claude(_SYSTEM_PROMPT, user, model=_MODEL_F, max_tokens=3000)


async def eval_F2(
    answer: str,
    query: str,
    outline_nature: str,
    burden_description: str,
    *,
    prev_comment: str | None = None,
) -> dict[str, Any]:
    user = _append_second_eval(
        _substitute_prompt(
            PROMPT_F2,
            query=query,
            outline_nature=outline_nature,
            burden_description=burden_description,
            answer=answer,
        ),
        prev_comment,
    )
    return await _call_claude(_SYSTEM_PROMPT, user, model=_MODEL_F, max_tokens=3000)


async def eval_F3(
    answer: str,
    skeleton: list[dict[str, Any]] | None,
    *,
    prev_comment: str | None = None,
) -> dict[str, Any]:
    skeleton_steps, skeleton_paths = _format_skeleton(skeleton)
    user = _append_second_eval(
        _substitute_prompt(
            PROMPT_F3,
            answer=answer,
            skeleton_steps=skeleton_steps,
            skeleton_paths=skeleton_paths,
        ),
        prev_comment,
    )
    return await _call_claude(_SYSTEM_PROMPT, user, model=_MODEL_F, max_tokens=3000)


async def eval_F4(
    answer: str,
    outline_nature: str,
    *,
    prev_comment: str | None = None,
) -> dict[str, Any]:
    user = _append_second_eval(
        _substitute_prompt(PROMPT_F4, outline_nature=outline_nature, answer=answer),
        prev_comment,
    )
    return await _call_claude(_SYSTEM_PROMPT, user, model=_MODEL_F, max_tokens=3000)


async def eval_T1(
    answer: str,
    outline_nature: str,
    *,
    prev_comment: str | None = None,
) -> dict[str, Any]:
    user = _append_second_eval(
        _substitute_prompt(PROMPT_T1, outline_nature=outline_nature)
        + f"\n\n纲目正文：\n{answer}",
        prev_comment,
    )
    result = await _call_claude(_SYSTEM_PROMPT, user, model=_MODEL_F, max_tokens=8000)
    return _normalize_t1(result)


async def eval_T2(
    answer: str,
    outline_nature: str,
    *,
    prev_comment: str | None = None,
) -> dict[str, Any]:
    user = _append_second_eval(
        _substitute_prompt(PROMPT_T2, outline_nature=outline_nature)
        + f"\n\n纲目正文：\n{answer}",
        prev_comment,
    )
    result = await _call_claude(_SYSTEM_PROMPT, user, model=_MODEL_T, max_tokens=4000)
    result = _normalize_t2(result)
    if result.get("error"):
        logger.warning("[outline_eval] T2 error: %s", result.get("error"))
    elif result.get("weighted_score") is None:
        logger.warning("[outline_eval] T2 missing weighted_score, keys=%s", list(result.keys()))
    return result


async def eval_T3(
    answer: str,
    outline_nature: str = "一般性",
    *,
    prev_comment: str | None = None,
) -> dict[str, Any]:
    user = _append_second_eval(
        _substitute_prompt(PROMPT_T3, outline_nature=outline_nature)
        + f"\n\n纲目正文：\n{answer}",
        prev_comment,
    )
    result = await _call_claude(_SYSTEM_PROMPT, user, model=_MODEL_T, max_tokens=4000)
    return _normalize_t3(result)


async def eval_T4(
    answer: str,
    outline_nature: str,
    *,
    prev_comment: str | None = None,
) -> dict[str, Any]:
    user = _append_second_eval(
        _substitute_prompt(PROMPT_T4, outline_nature=outline_nature)
        + f"\n\n纲目正文：\n{answer}",
        prev_comment,
    )
    result = await _call_claude(_SYSTEM_PROMPT, user, model=_MODEL_T, max_tokens=3000)
    return _normalize_t4(result)


async def eval_SYNTHESIS(
    answer: str,
    outline_nature: str,
    t2: dict[str, Any],
    t3: dict[str, Any],
    t4: dict[str, Any],
) -> dict[str, Any]:
    user = _substitute_prompt(
        PROMPT_SYNTHESIS,
        outline_nature=outline_nature,
        t2_result=json.dumps(t2, ensure_ascii=False),
        t3_result=json.dumps(t3, ensure_ascii=False),
        t4_result=json.dumps(t4, ensure_ascii=False),
        answer=answer,
    )
    result = await _call_claude(_SYSTEM_PROMPT, user, model=_MODEL_T, max_tokens=4000)
    if "error" in result:
        return {
            "high_priority": [],
            "low_priority": [],
            "overall_note": "综合建议生成失败",
        }
    return result


async def run_evaluation(
    request_data: dict[str, Any],
    is_second_eval: bool = False,
    eval_v1: dict[str, Any] | None = None,
) -> dict[str, Any]:
    answer = str(request_data.get("answer") or "")
    query = str(request_data.get("query") or "")
    revelation = str(request_data.get("revelation") or "")
    experience = str(request_data.get("experience") or "")
    practice = str(request_data.get("practice") or "")
    outline_nature = str(request_data.get("outline_nature") or "一般性")
    burden_description = str(request_data.get("burden_description") or "")
    skeleton = request_data.get("skeleton")
    if skeleton is not None and not isinstance(skeleton, list):
        skeleton = None

    def _prev(dim: str) -> str | None:
        if not is_second_eval:
            return None
        return _prev_comment(eval_v1, dim)

    started = time.perf_counter()

    raw_results = await asyncio.gather(
        eval_F1(answer, revelation, experience, practice, query, prev_comment=_prev("F1")),
        eval_F2(answer, query, outline_nature, burden_description, prev_comment=_prev("F2")),
        eval_F3(answer, skeleton, prev_comment=_prev("F3")),
        eval_F4(answer, outline_nature, prev_comment=_prev("F4")),
        eval_T1(answer, outline_nature, prev_comment=_prev("T1")),
        eval_T2(answer, outline_nature, prev_comment=_prev("T2")),
        eval_T3(answer, outline_nature, prev_comment=_prev("T3")),
        eval_T4(answer, outline_nature, prev_comment=_prev("T4")),
        return_exceptions=True,
    )

    dim_results: dict[str, dict[str, Any]] = {}
    cost_usd = 0.0
    improvement_notes: dict[str, str] = {}

    for key, raw in zip(_DIM_KEYS, raw_results):
        if isinstance(raw, Exception):
            dim_results[key] = {"error": str(raw)}
            continue
        result, in_tok, out_tok, call_cost = _pop_usage(raw)
        cost_usd += call_cost
        dim_results[key] = result
        if is_second_eval:
            note = result.get("improvement_note")
            if note:
                improvement_notes[key] = str(note)

    f1 = dim_results["F1"]
    f2 = dim_results["F2"]
    f3 = dim_results["F3"]
    f4 = dim_results["F4"]
    t1 = dim_results["T1"]
    t2 = dim_results["T2"]
    t3 = dim_results["T3"]
    t4 = dim_results["T4"]

    synthesis_raw = await eval_SYNTHESIS(answer, outline_nature, t2, t3, t4)
    synthesis, _, _, synthesis_cost = _pop_usage(synthesis_raw)
    cost_usd += synthesis_cost

    elapsed_ms = int((time.perf_counter() - started) * 1000)

    total_score = _calc_total_score(t1, t2, t3, t4, f1, f2, f3, f4)
    scripture_suggestions = _merge_scripture_suggestions(t1, skeleton)

    return {
        "total_score": total_score,
        "pansai_layer": {
            "F1": f1,
            "F2": f2,
            "F3": f3,
            "F4": f4,
        },
        "theology_layer": {
            "T1": t1,
            "T2": t2,
            "T3": t3,
            "T4": t4,
        },
        "synthesis": synthesis,
        "scripture_suggestions": scripture_suggestions,
        "is_second_eval": is_second_eval,
        "improvement_note": improvement_notes if is_second_eval else {},
        "elapsed_ms": elapsed_ms,
        "cost_usd": round(cost_usd, 6),
    }
