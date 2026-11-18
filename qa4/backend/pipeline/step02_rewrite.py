# -*- coding: utf-8 -*-
"""第 2 步：有历史才做。历史取最近 3 轮，每轮回答只取前 300 字；Haiku 改写；失败用原问题。"""

from __future__ import annotations

from typing import Any

from pipeline.context import RequestContext


def build_history(history: list[dict[str, Any]], *, turns: int, answer_chars: int) -> list[dict[str, str]]:
    recent = list(history or [])[-max(0, int(turns)):] if turns else []
    return [
        {"question": str(h.get("question") or ""), "answer": str(h.get("answer") or "")[: int(answer_chars)]}
        for h in recent
    ]


def history_text(turns: list[dict[str, str]]) -> str:
    return "\n".join(f"问：{t['question']}\n答：{t['answer']}" for t in turns)


async def run(ctx: RequestContext, deps: Any) -> str:
    cfg = deps.cfg
    turns = build_history(ctx.history, turns=int(cfg.get("history_turns", 3)), answer_chars=int(cfg.get("history_answer_chars", 300)))
    ctx.history_for_rewrite = turns
    ctx.record(2, history_turns=len(turns), answer_lens=[len(t["answer"]) for t in turns])
    tpl = deps.prompts.get("step2")
    prompt = tpl.render(history=history_text(turns), question=ctx.question_orig)
    try:
        res = await deps.llm.complete("haiku", "", [{"role": "user", "content": prompt}], step="step2", max_tokens=int(cfg.get("json_max_tokens", 2000)))
        ctx.note_llm("step2", res)
        out = (res.text or "").strip()
        if not out:
            raise ValueError("empty rewrite")
        ctx.record(2, rewritten_len=len(out))
        return out
    except Exception as e:
        ctx.degrade(f"step2:{type(e).__name__}")
        ctx.record(2, fallback="原问题")
        return ctx.question_orig
