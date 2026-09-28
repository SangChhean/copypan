# -*- coding: utf-8 -*-
"""后台执行。最多同时跑 max_concurrent_runs() 个运行，其余排队，先到先跑。
每个运行内部仍一篇一篇、一步一步依次执行。全部在同一个事件循环里，不开线程。
"""
from __future__ import annotations

import asyncio
import json
import logging

from .config import BURDEN_MAX_TOKENS, MAX_TOKENS, max_concurrent_runs
from . import db
from .llm import complete
from .pipeline import STEP_LABELS, dependency_skip, extract_burden_body
from .prompts import load_template, render_user

logger = logging.getLogger("panai4.runner")


class _State:
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.lock = asyncio.Lock()
        self.active: dict[int, asyncio.Task] = {}
        self.cancel_requested: set[int] = set()
        self.background: set[asyncio.Task] = set()


_state: _State | None = None


def _current() -> _State:
    """每个事件循环一份。后端重启或测试里重建应用时，旧循环的任务不再计入。"""
    global _state
    loop = asyncio.get_running_loop()
    if _state is None or _state.loop is not loop:
        _state = _State(loop)
    return _state


async def submit_run(
    items: list[dict],
    note: str,
    prepared_steps: list[dict],
    parent_run_id: int | None = None,
    start_step: str | None = None,
    topic_set_id: int | None = None,
    main_scope: str | None = None,
    analysis_scope: str | None = None,
    created_by: str | None = None,
    prompt_selection: dict | None = None,
    uses_test: bool = False,
) -> int:
    run_id = db.create_run(
        items,
        note,
        prepared_steps,
        parent_run_id=parent_run_id,
        start_step=start_step,
        topic_set_id=topic_set_id,
        main_scope=main_scope,
        analysis_scope=analysis_scope,
        created_by=created_by,
        prompt_selection=prompt_selection,
        uses_test=uses_test,
    )
    await dispatch()
    return run_id


async def dispatch() -> None:
    state = _current()
    async with state.lock:
        for run_id in [rid for rid, task in state.active.items() if task.done()]:
            state.active.pop(run_id, None)
        while len(state.active) < max_concurrent_runs():
            run_id = db.claim_next_queued()
            if run_id is None:
                break
            task = asyncio.create_task(_execute(run_id))
            state.active[run_id] = task
            task.add_done_callback(lambda _t, rid=run_id, st=state: _finished(st, rid))


def _finished(state: _State, run_id: int) -> None:
    state.active.pop(run_id, None)
    if state.loop.is_closed():
        return
    try:
        follow = state.loop.create_task(dispatch())
    except RuntimeError:
        return
    state.background.add(follow)
    follow.add_done_callback(state.background.discard)


def active_run_ids() -> list[int]:
    state = _current()
    return [rid for rid, task in state.active.items() if not task.done()]


async def cancel_run(run_id: int) -> str:
    """返回 cancelled、missing 或 finished（已结束，不能取消）。"""
    state = _current()
    async with state.lock:
        run = db.get_run(run_id)
        if run is None:
            return "missing"
        if run["status"] == "queued":
            db.cancel_run_rows(run_id)
            return "cancelled"
        if run["status"] != "running":
            return "finished"
        task = state.active.get(run_id)
        if task is None or task.done():
            db.cancel_run_rows(run_id)
            return "cancelled"
        state.cancel_requested.add(run_id)
        task.cancel()
    await asyncio.wait({task}, timeout=10)
    return "cancelled"


async def _execute(run_id: int) -> None:
    state = _current()
    try:
        for item in db.list_items(run_id):
            await _execute_item(item)
        db.set_run_status(run_id, "done")
    except asyncio.CancelledError:
        if run_id in state.cancel_requested:
            state.cancel_requested.discard(run_id)
            db.cancel_run_rows(run_id)
            return
        raise
    except Exception:
        logger.exception("run %s 执行失败", run_id)
        db.set_run_status(run_id, "failed")


def _template_for(row: dict) -> str:
    """用建立运行时记下的版本：测试版取库里的全文，当前版按版本号取 texts/。"""
    test_id = row.get("prompt_test_version_id")
    if test_id:
        test = db.get_prompt_test(int(test_id))
        if test is None:
            raise RuntimeError("找不到所用的测试版")
        return test["template"]
    try:
        return load_template(row["step"], row.get("prompt_version") or None)
    except KeyError:
        return load_template(row["step"])


def _filled_prompt(step: dict, item: dict, outputs: dict[str, str], burden_body: str) -> str:
    return render_user(
        step["step"],
        topic=item["title"],
        original_outline=item.get("original_outline") or "",
        burden=burden_body,
        original_skeleton=outputs.get("orig_skeleton") or "",
        generated_skeleton=outputs.get("skeleton") or "",
        template=_template_for(step),
    )


async def _execute_item(item: dict) -> None:
    db.set_item_status(item["id"], "running")
    failed = False
    error = ""
    outputs: dict[str, str] = {}
    unavailable: set[str] = set()
    for existing in db.list_steps(item["id"]):
        if existing["status"] == "done":
            outputs[existing["step"]] = existing.get("output_text") or ""
        elif existing["status"] == "failed":
            unavailable.add(existing["step"])
    run = db.get_run(item["run_id"]) or {}
    force_orig = run.get("start_step") == "orig_skeleton"

    for step in db.pending_steps(item["id"]):
        reason = dependency_skip(step["step"], unavailable)
        if reason:
            db.update_step(step["id"], status="skipped", output_text=reason)
            unavailable.add(step["step"])
            continue

        version = step.get("prompt_version") or ""
        burden_body = ""
        if step["step"] == "skeleton":
            try:
                burden_body = extract_burden_body(outputs.get("burden") or "")
            except ValueError as exc:
                failed = True
                error = str(exc)
                db.update_step(step["id"], status="failed", error=error)
                unavailable.add("skeleton")
                continue

        try:
            prompt = _filled_prompt(step, item, outputs, burden_body)
        except Exception as exc:
            failed = True
            error = str(exc)
            db.update_step(step["id"], status="failed", error=error)
            unavailable.add(step["step"])
            continue
        if step["step"] == "orig_skeleton" and not force_orig and item.get("original_outline"):
            cached = db.lookup_orig_cache(item["original_outline"], version)
            if cached:
                db.update_step(
                    step["id"],
                    status="done",
                    output_text=cached["output_text"],
                    reused_from=cached["source_step_result_id"],
                    prompt_text=prompt,
                    model="",
                )
                outputs["orig_skeleton"] = cached["output_text"] or ""
                continue

        db.update_step(step["id"], status="running", prompt_text=prompt)
        try:
            token_limit = BURDEN_MAX_TOKENS if step["step"] == "burden" else MAX_TOKENS
            result = await complete(prompt, topic=item["title"], max_tokens=token_limit)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failed = True
            error = str(exc)
            db.update_step(step["id"], status="failed", error=error)
            unavailable.add(step["step"])
            continue
        db.update_step(
            step["id"],
            status="done",
            model=result.model,
            output_text=result.text,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            cache_creation_input_tokens=result.cache_creation_input_tokens,
            cache_read_input_tokens=result.cache_read_input_tokens,
            cache_creation_5m_tokens=result.cache_creation_5m_tokens,
            cost_usd=result.cost_usd,
            duration_ms=result.duration_ms,
            stop_reason=result.stop_reason,
            error=result.cost_note,
            content_blocks=json.dumps(result.content_blocks, ensure_ascii=False),
            thinking_text=result.thinking_text,
        )
        outputs[step["step"]] = result.text
        if step["step"] == "orig_skeleton" and item.get("original_outline"):
            db.save_orig_cache(db.outline_hash(item["original_outline"]), version, result.text, step["id"])

    if failed:
        db.set_item_status(item["id"], "failed", error)
    else:
        db.set_item_status(item["id"], "done", None)


def step_public(row: dict, *, include_prompt: bool) -> dict:
    raw_blocks = row.get("content_blocks")
    if isinstance(raw_blocks, str) and raw_blocks:
        try:
            content_blocks = json.loads(raw_blocks)
        except json.JSONDecodeError:
            content_blocks = None
    else:
        content_blocks = raw_blocks or None
    body = {
        "id": row["id"],
        "step": row["step"],
        "label": STEP_LABELS.get(row["step"], row["step"]),
        "status": row["status"],
        "output_text": row.get("output_text"),
        "model": row.get("model") or None,
        "stop_reason": row.get("stop_reason"),
        "input_tokens": row.get("input_tokens"),
        "output_tokens": row.get("output_tokens"),
        "cache_creation_input_tokens": row.get("cache_creation_input_tokens"),
        "cache_read_input_tokens": row.get("cache_read_input_tokens"),
        "cache_creation_5m_tokens": row.get("cache_creation_5m_tokens"),
        "cost_usd": row.get("cost_usd"),
        "cost_note": row.get("error") if row.get("status") == "done" and row.get("cost_usd") is None and row.get("model") else None,
        "duration_ms": row.get("duration_ms"),
        "error": row.get("error") if row.get("status") == "failed" else None,
        "reused_from": row.get("reused_from"),
        "content_blocks": content_blocks,
        "prompt_name": row.get("prompt_name") or None,
        "prompt_version": row.get("prompt_version") or None,
        "prompt_test_version_id": row.get("prompt_test_version_id"),
    }
    if include_prompt:
        body["prompt_text"] = row.get("prompt_text") or None
        body["thinking_text"] = row.get("thinking_text") or None
    return body
