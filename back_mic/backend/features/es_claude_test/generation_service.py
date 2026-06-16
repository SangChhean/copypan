# -*- coding: utf-8 -*-
from __future__ import annotations

import asyncio
import os
from typing import Any

import anthropic

from features.es_claude_test.prompts import GENERATE_PROMPT_CONCISE, GENERATE_PROMPT_RICH
from features.es_claude_test.retrieval_service import STAGES

_GENERATE_MODEL = "claude-sonnet-4-6"
_INPUT_PRICE_PER_M = 3.0
_OUTPUT_PRICE_PER_M = 15.0


def _format_stages_for_prompt(stages: dict, concise: bool) -> str:
    parts: list[str] = []
    for stage in STAGES:
        stage_key = stage["key"]
        stage_data = stages.get(stage_key) or {}
        count = int(stage_data.get("count") or 0)
        if count == 0:
            continue
        docs = list(stage_data.get("docs") or [])
        selected = docs[:2] if concise else docs
        parts.append(f"【{stage_data.get('label', stage_key)}】")
        parts.append(f"（该阶段共 {count} 条，以下提供 {len(selected)} 条）")
        parts.append("")
        for doc in selected:
            text = str(doc.get("text") or "").strip()
            source_zh = str(doc.get("source_zh") or "").strip()
            parts.append(text)
            if source_zh:
                parts.append(source_zh)
            parts.append("")
        parts.append("")
    return "\n".join(parts).strip()


async def generate_article(keyword: str, stages: dict) -> dict:
    api_key = (os.environ.get("CLAUDE_API_KEY") or "").strip()
    if not api_key:
        raise RuntimeError("Claude 未配置（请设置 CLAUDE_API_KEY）")

    async def _call_claude(prompt_template: str, concise: bool) -> dict[str, Any]:
        formatted = _format_stages_for_prompt(stages, concise)
        system = prompt_template.replace("{keyword}", keyword)
        user = f"请根据以上要求，编排「{keyword}」的进展文章。\n\n{formatted}"

        def _sync() -> dict[str, Any]:
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model=_GENERATE_MODEL,
                max_tokens=8000,
                temperature=0.3,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            text = ""
            if response.content and getattr(response.content[0], "text", None):
                text = response.content[0].text
            usage = response.usage
            return {
                "text": text,
                "input_tokens": int(getattr(usage, "input_tokens", 0) or 0),
                "output_tokens": int(getattr(usage, "output_tokens", 0) or 0),
            }

        return await asyncio.to_thread(_sync)

    concise_result, rich_result = await asyncio.gather(
        _call_claude(GENERATE_PROMPT_CONCISE, True),
        _call_claude(GENERATE_PROMPT_RICH, False),
        return_exceptions=True,
    )

    def _wrap_result(result: Any) -> dict[str, Any]:
        if isinstance(result, Exception):
            return {
                "text": "",
                "error": str(result),
                "input_tokens": 0,
                "output_tokens": 0,
            }
        return {
            "text": result.get("text", ""),
            "error": None,
            "input_tokens": int(result.get("input_tokens", 0) or 0),
            "output_tokens": int(result.get("output_tokens", 0) or 0),
        }

    concise = _wrap_result(concise_result)
    rich = _wrap_result(rich_result)

    total_input = concise["input_tokens"] + rich["input_tokens"]
    total_output = concise["output_tokens"] + rich["output_tokens"]
    input_cost = total_input / 1_000_000 * _INPUT_PRICE_PER_M
    output_cost = total_output / 1_000_000 * _OUTPUT_PRICE_PER_M
    total_cost = round(input_cost + output_cost, 4)

    return {
        "concise": concise,
        "rich": rich,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "estimated_cost_usd": total_cost,
    }
