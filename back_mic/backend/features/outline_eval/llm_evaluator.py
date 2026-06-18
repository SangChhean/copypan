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

from features.outline_eval.prompts import (
    PROMPT_F1,
    PROMPT_F2,
    PROMPT_F3,
    PROMPT_F4,
    PROMPT_T1,
    PROMPT_T2,
    PROMPT_T3,
    PROMPT_T4,
)

_DEFAULT_MODEL = "claude-sonnet-4-6"
_INPUT_PRICE = 0.000003
_OUTPUT_PRICE = 0.000015

_SYSTEM_PROMPT = (
    "你只能以合法的 JSON 对象格式回复，"
    "不得包含任何前缀文字、解释说明或 Markdown 代码块。"
    "直接输出 JSON，第一个字符必须是 '{'，最后一个字符必须是 '}'。"
)

_GENRE_MAP = {
    "一般性": "均衡",
    "真理启示": "重启示",
    "生命经历": "重经历",
    "实行应用": "重实行",
}

_SECOND_EVAL_SUFFIX = """

【上轮评估评语】
{prev_comment}

请在 JSON 中额外增加字段 "improvement_note": "<相较上轮是否有改善，简述；若无变化请说明>"。"""

_DIM_KEYS = ("F1", "F2", "F3", "F4", "T1", "T2", "T3", "T4")

logger = logging.getLogger(__name__)


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
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else {"error": "响应非 JSON 对象"}
    except json.JSONDecodeError:
        pass

    # 提取第一个 { 到最后一个 } 之间的内容
    first = s.find("{")
    last = s.rfind("}")
    if first >= 0 and last > first:
        try:
            obj = json.loads(s[first : last + 1])
            return obj if isinstance(obj, dict) else {"error": "响应非 JSON 对象"}
        except json.JSONDecodeError:
            pass

    logger.warning(f"[outline_eval] JSON 解析失败，原始内容前800字：{s[:800]}")
    return {"error": "JSON 解析失败", "raw": s[:500]}


def _substitute_prompt(template: str, **kwargs: str) -> str:
    """替换 {key} 占位符，避免 .format() 误解析 JSON 示例中的花括号。"""
    result = template
    for key, value in kwargs.items():
        result = result.replace("{" + key + "}", value)
    return result


def _calc_call_cost(input_tokens: int, output_tokens: int) -> float:
    return input_tokens * _INPUT_PRICE + output_tokens * _OUTPUT_PRICE


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


def _map_genre(outline_nature: str) -> str:
    return _GENRE_MAP.get(outline_nature, "均衡")


def _prev_comment(eval_v1: dict[str, Any] | None, dim: str) -> str | None:
    if not eval_v1:
        return None
    block = eval_v1.get(dim)
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
    f1: dict[str, Any],
    f2: dict[str, Any],
    f3: dict[str, Any],
    f4: dict[str, Any],
    t1: dict[str, Any],
    t2: dict[str, Any],
    t3: dict[str, Any],
    t4: dict[str, Any],
) -> float:
    def _f_score(result: dict[str, Any]) -> float:
        if "error" in result:
            return 0.0
        try:
            return float(result.get("score") or 0)
        except (TypeError, ValueError):
            return 0.0

    def _num(result: dict[str, Any], key: str, default: float = 0.0) -> float:
        if "error" in result:
            return default
        try:
            return float(result.get(key) or default)
        except (TypeError, ValueError):
            return default

    f1_s = (_f_score(f1) * 20) * 0.10
    f2_s = (_f_score(f2) * 20) * 0.10
    f3_s = (_f_score(f3) * 20) * 0.10
    f4_s = (_f_score(f4) * 20) * 0.10

    t1_s = (_num(t1, "total") / 50 * 100) * 0.12
    t2_s = (_num(t2, "total") / 50 * 100) * 0.15
    t3_s = _num(t3, "organic_index") * 0.15
    t4_s = _num(t4, "weighted_score") * 0.18

    return round(f1_s + f2_s + f3_s + f4_s + t1_s + t2_s + t3_s + t4_s, 1)


async def _call_claude(
    system: str,
    user: str,
    model: str = _DEFAULT_MODEL,
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
        parsed["_cost_usd"] = _calc_call_cost(input_tokens, output_tokens)
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
    return await _call_claude(_SYSTEM_PROMPT, user)


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
    return await _call_claude(_SYSTEM_PROMPT, user)


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
    return await _call_claude(_SYSTEM_PROMPT, user)


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
    return await _call_claude(_SYSTEM_PROMPT, user)


async def eval_T1(answer: str, *, prev_comment: str | None = None) -> dict[str, Any]:
    user = _append_second_eval(PROMPT_T1 + f"\n\n纲目正文：\n{answer}", prev_comment)
    return await _call_claude(_SYSTEM_PROMPT, user, max_tokens=2500)


async def eval_T2(answer: str, *, prev_comment: str | None = None) -> dict[str, Any]:
    # PROMPT_T2 含 JSON 示例花括号，使用字符串拼接而非 .format()
    user = _append_second_eval(PROMPT_T2 + f"\n\n纲目正文：\n{answer}", prev_comment)
    result = await _call_claude(_SYSTEM_PROMPT, user, max_tokens=4000)
    if result.get("error"):
        logger.warning("[outline_eval] T2 error: %s", result.get("error"))
    elif result.get("total") is None:
        logger.warning("[outline_eval] T2 missing total, keys=%s", list(result.keys()))
    return result


async def eval_T3(answer: str, *, prev_comment: str | None = None) -> dict[str, Any]:
    user = _append_second_eval(PROMPT_T3 + f"\n\n纲目正文：\n{answer}", prev_comment)
    return await _call_claude(_SYSTEM_PROMPT, user, max_tokens=2500)


async def eval_T4(
    answer: str,
    genre: str,
    *,
    prev_comment: str | None = None,
) -> dict[str, Any]:
    user = _append_second_eval(
        _substitute_prompt(PROMPT_T4, genre=genre) + f"\n\n纲目正文：\n{answer}",
        prev_comment,
    )
    return await _call_claude(_SYSTEM_PROMPT, user, max_tokens=2000)


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
    genre = _map_genre(outline_nature)

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
        eval_T1(answer, prev_comment=_prev("T1")),
        eval_T2(answer, prev_comment=_prev("T2")),
        eval_T3(answer, prev_comment=_prev("T3")),
        eval_T4(answer, genre, prev_comment=_prev("T4")),
        return_exceptions=True,
    )

    elapsed_ms = int((time.perf_counter() - started) * 1000)

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

    total_score = _calc_total_score(f1, f2, f3, f4, t1, t2, t3, t4)
    scripture_suggestions = _merge_scripture_suggestions(t1, skeleton)

    result: dict[str, Any] = {
        "F1": f1,
        "F2": f2,
        "F3": f3,
        "F4": f4,
        "T1": t1,
        "T2": t2,
        "T3": t3,
        "T4": t4,
        "total_score": total_score,
        "elapsed_ms": elapsed_ms,
        "cost_usd": round(cost_usd, 6),
        "scripture_suggestions": scripture_suggestions,
        "genre": genre,
    }

    if is_second_eval:
        result["improvement_notes"] = improvement_notes

    return result
