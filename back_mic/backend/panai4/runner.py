# -*- coding: utf-8 -*-
"""后台执行。最多同时跑 max_concurrent_runs() 个运行，其余排队，先到先跑。
每个运行内部仍一篇一篇、一步一步依次执行。全部在同一个事件循环里，不开线程。
"""
from __future__ import annotations

import asyncio
import json
import logging

from . import db
from .config import BURDEN_MAX_TOKENS, MAX_TOKENS, SELECT_MAX_TOKENS, max_concurrent_runs
from .llm import complete
from .pipeline import (
    MISSING_BURDEN,
    MISSING_TERM_DATA,
    STEP_LABELS,
    dependency_skip,
    extract_burden_body,
)
from .prompts import load_template, render_user

logger = logging.getLogger("panai4.runner")


class _State:
    def __init__(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop
        self.lock = asyncio.Lock()
        # 整次运行用 run_id；确认后续跑用 ("cont", item_id)。合计计入并发上限。
        self.active: dict = {}
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


def _prune_active(state: _State) -> None:
    for key in [k for k, task in state.active.items() if task.done()]:
        state.active.pop(key, None)


def _active_slots(state: _State) -> int:
    _prune_active(state)
    return len(state.active)

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
    flow_kind: str = "full",
    batch_mode: int = 1,
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
        flow_kind=flow_kind,
        batch_mode=batch_mode,
    )
    await dispatch()
    return run_id


async def dispatch() -> None:
    state = _current()
    async with state.lock:
        while _active_slots(state) < max_concurrent_runs():
            run_id = db.claim_next_queued()
            if run_id is None:
                break
            task = asyncio.create_task(_execute(run_id))
            state.active[run_id] = task
            task.add_done_callback(lambda _t, rid=run_id, st=state: _finished(st, rid))


def _finished(state: _State, key) -> None:
    state.active.pop(key, None)
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
    return [rid for rid, task in state.active.items() if isinstance(rid, int) and not task.done()]


async def cancel_run(run_id: int) -> str:
    """返回 cancelled、missing 或 finished（已结束，不能取消）。

    awaiting_confirm 可取消；取消后不可再确认。
    """
    state = _current()
    async with state.lock:
        run = db.get_run(run_id)
        if run is None:
            return "missing"
        status = run["status"]
        if status == "queued":
            db.cancel_run_rows(run_id)
            return "cancelled"
        if status == "awaiting_confirm":
            db.cancel_run_rows(run_id)
            return "cancelled"
        if status != "running":
            return "finished"
        task = state.active.get(run_id)
        # 可能只有续跑任务在跑（整次 select 已结束）
        cont_tasks = [
            t for k, t in state.active.items() if isinstance(k, tuple) and k[0] == "cont" and not t.done()
        ]
        if task is None or task.done():
            if not cont_tasks:
                db.cancel_run_rows(run_id)
                return "cancelled"
            state.cancel_requested.add(run_id)
            for t in cont_tasks:
                t.cancel()
        else:
            state.cancel_requested.add(run_id)
            task.cancel()
            for t in cont_tasks:
                t.cancel()
    if task is not None and not task.done():
        await asyncio.wait({task}, timeout=10)
    return "cancelled"


async def _execute(run_id: int) -> None:
    state = _current()
    try:
        run = db.get_run(run_id) or {}
        batch_mode = bool(run.get("batch_mode"))
        paused = False
        for item in db.list_items(run_id):
            if item.get("status") in {"done", "cancelled", "interrupted", "skipped"}:
                continue
            outcome = await _execute_item(item, stop_at_confirm=not batch_mode)
            if outcome == "awaiting_confirm":
                paused = True
        if paused:
            db.set_run_status(run_id, "awaiting_confirm")
        else:
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


async def _continue_item(run_id: int, item_id: int) -> None:
    """确认后从 term_defs 起续跑这一篇。"""
    state = _current()
    try:
        item = db.get_item(item_id)
        if item is None:
            return
        db.set_run_status(run_id, "running")
        await _execute_item(item, stop_at_confirm=False)
        if run_id in state.cancel_requested:
            state.cancel_requested.discard(run_id)
            db.cancel_run_rows(run_id)
            return
        db.refresh_run_status_after_items(run_id)
    except asyncio.CancelledError:
        if run_id in state.cancel_requested:
            state.cancel_requested.discard(run_id)
            db.cancel_run_rows(run_id)
            return
        raise
    except Exception:
        logger.exception("run %s item %s 续跑失败", run_id, item_id)
        db.set_item_status(item_id, "failed", "续跑失败")
        db.refresh_run_status_after_items(run_id)


async def schedule_continue(run_id: int, item_id: int) -> None:
    """把确认后续跑排进并发槽；待确认本身不占槽。"""
    state = _current()
    key = ("cont", item_id)

    async def _wait_and_start() -> None:
        while True:
            async with state.lock:
                _prune_active(state)
                if key in state.active and not state.active[key].done():
                    return
                if _active_slots(state) < max_concurrent_runs():
                    task = asyncio.create_task(_continue_item(run_id, item_id))
                    state.active[key] = task
                    task.add_done_callback(lambda _t, k=key, st=state: _finished(st, k))
                    return
            await asyncio.sleep(0.05)

    await _wait_and_start()


def _validate_confirm_terms(terms: list[dict]) -> tuple[list[dict], list[str]]:
    data = _load_sc_data_or_fail()
    unknown: list[str] = []
    cleaned: list[dict] = []
    seen: set[str] = set()
    for row in terms:
        name = (row.get("name") or "").strip()
        if not name:
            continue
        if name in seen:
            continue
        seen.add(name)
        if name not in data.tier_of:
            unknown.append(name)
            continue
        tier = (row.get("tier") or data.tier_of.get(name) or "").strip()
        if tier not in {"最内在", "内在", "外在"}:
            tier = data.tier_of[name]
        cleaned.append(
            {
                "name": name,
                "tier": tier,
                "reason": (row.get("reason") or "").strip(),
            }
        )
    return cleaned, unknown


async def confirm_item_terms(run_id: int, position: int, terms: list[dict]) -> dict:
    """人工确认词表并续跑。第二次确认 / 已取消 → 调用方应转 400。"""
    run = db.get_run(run_id)
    if run is None:
        raise LookupError("missing")
    if run.get("status") == "cancelled":
        raise PermissionError("cancelled")
    if run.get("status") not in {"awaiting_confirm", "running", "done"}:
        # done 若误点；仅 awaiting 的篇可确认
        pass
    item = next((row for row in db.list_items(run_id) if row["position"] == position), None)
    if item is None:
        raise LookupError("item")
    if item.get("status") == "cancelled" or run.get("status") == "cancelled":
        raise PermissionError("cancelled")
    if item.get("status") != "awaiting_confirm":
        raise PermissionError("already")

    cleaned, unknown = _validate_confirm_terms(terms)
    if unknown:
        raise ValueError(unknown)
    if not cleaned:
        raise ValueError(["（词表为空）"])

    if not db.claim_await_confirm(item["id"]):
        raise PermissionError("already")

    counts = _tier_counts([{"tier_actual": row["tier"]} for row in cleaned])
    db.set_item_final_terms(item["id"], json.dumps(cleaned, ensure_ascii=False))
    a, b, c = counts.get("最内在", 0), counts.get("内在", 0), counts.get("外在", 0)
    text = f"已确认 {len(cleaned)} 个词（最内在 {a} / 内在 {b} / 外在 {c}）"
    meta = {"tier_counts": counts, "confirmed_count": len(cleaned), "batch_mode": False}
    # claim 后把步骤写完
    steps = {s["step"]: s for s in db.list_steps(item["id"])}
    step = steps.get("await_confirm")
    if step:
        db.update_step(
            step["id"],
            status="done",
            output_text=text,
            prompt_text="",
            model="",
            meta_json=json.dumps(meta, ensure_ascii=False),
        )
    db.set_item_status(item["id"], "running", None)
    await schedule_continue(run_id, item["id"])
    return {
        "ok": True,
        "run_id": run_id,
        "position": position,
        "confirmed_count": len(cleaned),
        "final_terms": cleaned,
    }

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


def _tier_counts(terms: list[dict]) -> dict[str, int]:
    counts = {"最内在": 0, "内在": 0, "外在": 0}
    for row in terms:
        tier = row.get("tier_actual") or row.get("tier") or ""
        if tier in counts:
            counts[tier] += 1
    return counts


def _load_sc_data_or_fail():
    from .sc.data import load_sc_data

    data = load_sc_data()
    if data.load_error:
        raise RuntimeError(MISSING_TERM_DATA)
    return data


def _run_select(step: dict, item: dict) -> tuple[str, str, dict]:
    """返回 (prompt, output_text, meta)."""
    data = _load_sc_data_or_fail()
    from .sc.data import fill_select_prompt
    from .sc.parse_select import parse_select_output

    template = _template_for(step)
    prompt = fill_select_prompt(template, item["title"], data)
    return prompt, "", {"_pending": True, "_data_names": list(data.tier_of.keys())}


async def _finish_select(step: dict, item: dict, prompt: str, result_text: str) -> tuple[str, dict]:
    data = _load_sc_data_or_fail()
    from .sc.parse_select import parse_select_output

    has_3a = {n: bool(data.content_3a.get(n)) for n in data.tier_of}
    parsed = parse_select_output(result_text, data.tier_of, has_3a)
    unknown = [row["name"] for row in parsed if not row.get("in_list")]
    valid = [row for row in parsed if row.get("in_list")]
    counts = _tier_counts(valid)
    meta = {
        "items": [
            {
                "name": row["name"],
                "tier": row["tier_actual"],
                "tier_by_model": row["tier_by_model"],
                "reason": row.get("reason") or "",
                "tier_mismatch": bool(row.get("tier_mismatch")),
            }
            for row in valid
        ],
        "unknown_names": unknown,
        "tier_counts": counts,
        "valid_count": len(valid),
    }
    return result_text, meta


def _run_await_confirm(item: dict, select_meta: dict | None, *, batch_mode: bool) -> tuple[str, str, dict | None]:
    """返回 (status, output_text, meta)。

    batch_mode=True：自动写入 final_terms_json，status=done。
    batch_mode=False：不写 final_terms，status=awaiting_confirm，由确认接口续跑。
    """
    items = list((select_meta or {}).get("items") or [])
    counts = _tier_counts([{"tier_actual": row.get("tier")} for row in items])
    a, b, c = counts.get("最内在", 0), counts.get("内在", 0), counts.get("外在", 0)
    if not batch_mode:
        # --- 闸门：人工确认 ---
        n = len(items)
        text = f"待确认 {n} 个词（最内在 {a} / 内在 {b} / 外在 {c}）"
        meta = {
            "tier_counts": counts,
            "pending_count": n,
            "batch_mode": False,
            "candidates": [
                {"name": row["name"], "tier": row["tier"], "reason": row.get("reason") or ""}
                for row in items
            ],
        }
        return "awaiting_confirm", text, meta
    # --- 批量：自动确认 ---
    final = [
        {"name": row["name"], "tier": row["tier"], "reason": row.get("reason") or ""}
        for row in items
    ]
    db.set_item_final_terms(item["id"], json.dumps(final, ensure_ascii=False))
    n = len(final)
    text = f"批量模式：自动确认 {n} 个词（最内在 {a} / 内在 {b} / 外在 {c}）"
    meta = {"tier_counts": counts, "confirmed_count": n, "batch_mode": True}
    return "done", text, meta


def _run_term_defs(item: dict) -> tuple[str, dict]:
    data = _load_sc_data_or_fail()
    from .sc.data import build_term_defs

    raw = item.get("final_terms_json")
    if not raw:
        fresh = db.get_item(item["id"]) or item
        raw = fresh.get("final_terms_json")
    if not raw:
        raise RuntimeError("缺少已确认词表（final_terms_json）")
    final = json.loads(raw) if isinstance(raw, str) else raw
    names = [row["name"] for row in final]
    text, skipped, merged, _chars, defs_sent = build_term_defs(names, data)
    by_tier = {"最内在": 0, "内在": 0, "外在": 0}
    for row in final:
        tier = row.get("tier") or ""
        if tier in by_tier:
            by_tier[tier] += 1
    meta = {
        "defs_sent_count": defs_sent,
        "skipped_names": skipped,
        "merged_names": merged,
        "tier_counts": by_tier,
    }
    return text, meta


def _fill_burden_prompt(step: dict, item: dict, term_defs_text: str) -> str:
    data = _load_sc_data_or_fail()
    from .sc.data import fill_ref_prompt

    template = _template_for(step)
    return fill_ref_prompt(template, item["title"], term_defs_text, data)


def _fill_skeleton_prompt(step: dict, item: dict, burden_body: str) -> str:
    template = _template_for(step)
    return render_user(
        "skeleton",
        topic=item["title"],
        burden=burden_body,
        template=template,
    )


def _fill_analysis_prompt(step: dict, item: dict, outputs: dict[str, str]) -> str:
    return render_user(
        step["step"],
        topic=item["title"],
        original_outline=item.get("original_outline") or "",
        original_skeleton=outputs.get("orig_skeleton") or "",
        generated_skeleton=outputs.get("skeleton") or "",
        template=_template_for(step),
    )


def _burden_for_skeleton(burden_output: str, flow_kind: str) -> str:
    if flow_kind == "full":
        from .sc.export_sc import extract_burden_export

        body, warning = extract_burden_export(burden_output or "")
        if warning and "未找到" in (warning or ""):
            raise ValueError(MISSING_BURDEN)
        return body
    return extract_burden_body(burden_output or "")


def _token_limit(step_name: str) -> int:
    if step_name in {"select", "burden"}:
        return SELECT_MAX_TOKENS if step_name == "select" else BURDEN_MAX_TOKENS
    return MAX_TOKENS


def _meta_loads(raw) -> dict | None:
    if not raw:
        return None
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return None


async def _execute_item(item: dict, *, stop_at_confirm: bool = False) -> str:
    """执行一篇。返回 done / failed / awaiting_confirm。"""
    db.set_item_status(item["id"], "running")
    failed = False
    error = ""
    outputs: dict[str, str] = {}
    metas: dict[str, dict] = {}
    unavailable: set[str] = set()
    for existing in db.list_steps(item["id"]):
        if existing["status"] == "done":
            outputs[existing["step"]] = existing.get("output_text") or ""
            meta = _meta_loads(existing.get("meta_json"))
            if meta:
                metas[existing["step"]] = meta
        elif existing["status"] == "failed":
            unavailable.add(existing["step"])
        elif existing["status"] == "awaiting_confirm":
            # 续跑不应再碰到；若误入则视为闸门
            pass
    run = db.get_run(item["run_id"]) or {}
    flow_kind = run.get("flow_kind") or "legacy"
    batch_mode = bool(run.get("batch_mode"))
    force_orig = run.get("start_step") == "orig_skeleton"
    item = db.get_item(item["id"]) or item

    for step in db.pending_steps(item["id"]):
        reason = dependency_skip(step["step"], unavailable)
        if reason:
            db.update_step(step["id"], status="skipped", output_text=reason)
            unavailable.add(step["step"])
            continue

        name = step["step"]
        version = step.get("prompt_version") or ""

        try:
            if name == "select":
                prompt, _, _ = _run_select(step, item)
                db.update_step(step["id"], status="running", prompt_text=prompt)
                result = await complete(
                    prompt, topic=item["title"], max_tokens=_token_limit(name), step=name
                )
                out, meta = await _finish_select(step, item, prompt, result.text)
                db.update_step(
                    step["id"],
                    status="done",
                    model=result.model,
                    output_text=out,
                    prompt_text=prompt,
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
                    meta_json=json.dumps(meta, ensure_ascii=False),
                )
                outputs["select"] = out
                metas["select"] = meta
                continue

            if name == "await_confirm":
                # 只看 batch_mode，不再用 flow_kind==full 强行当批量
                status, out, meta = _run_await_confirm(
                    item, metas.get("select"), batch_mode=batch_mode
                )
                item = db.get_item(item["id"]) or item
                db.update_step(
                    step["id"],
                    status=status,
                    output_text=out,
                    prompt_text="",
                    model="",
                    meta_json=json.dumps(meta, ensure_ascii=False) if meta else None,
                )
                outputs["await_confirm"] = out
                if meta:
                    metas["await_confirm"] = meta
                if status == "awaiting_confirm" and stop_at_confirm:
                    db.set_item_status(item["id"], "awaiting_confirm", None)
                    return "awaiting_confirm"
                continue

            if name == "term_defs":
                out, meta = _run_term_defs(item)
                db.update_step(
                    step["id"],
                    status="done",
                    output_text=out,
                    prompt_text="",
                    model="",
                    meta_json=json.dumps(meta, ensure_ascii=False),
                )
                outputs["term_defs"] = out
                metas["term_defs"] = meta
                continue

            if name == "burden":
                if flow_kind == "full":
                    prompt = _fill_burden_prompt(step, item, outputs.get("term_defs") or "")
                else:
                    prompt = render_user(
                        "burden",
                        topic=item["title"],
                        template=_template_for(step),
                    )
                db.update_step(step["id"], status="running", prompt_text=prompt)
                result = await complete(
                    prompt, topic=item["title"], max_tokens=_token_limit(name), step=name
                )
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
                outputs["burden"] = result.text
                continue

            if name == "skeleton":
                try:
                    burden_body = _burden_for_skeleton(outputs.get("burden") or "", flow_kind)
                except ValueError as exc:
                    failed = True
                    error = str(exc)
                    db.update_step(step["id"], status="failed", error=error)
                    unavailable.add("skeleton")
                    continue
                prompt = _fill_skeleton_prompt(step, item, burden_body)
                db.update_step(step["id"], status="running", prompt_text=prompt)
                result = await complete(
                    prompt, topic=item["title"], max_tokens=_token_limit(name), step=name
                )
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
                outputs["skeleton"] = result.text
                continue

            # orig_skeleton / diagnosis
            prompt = _fill_analysis_prompt(step, item, outputs)
            if name == "orig_skeleton" and not force_orig and item.get("original_outline"):
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
            result = await complete(
                prompt, topic=item["title"], max_tokens=_token_limit(name), step=name
            )
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
            outputs[name] = result.text
            if name == "orig_skeleton" and item.get("original_outline"):
                db.save_orig_cache(
                    db.outline_hash(item["original_outline"]), version, result.text, step["id"]
                )

        except asyncio.CancelledError:
            raise
        except Exception as exc:
            failed = True
            error = str(exc)
            if MISSING_TERM_DATA in error:
                error = MISSING_TERM_DATA
            db.update_step(step["id"], status="failed", error=error)
            unavailable.add(name)
            continue

    if failed:
        db.set_item_status(item["id"], "failed", error)
        return "failed"
    db.set_item_status(item["id"], "done", None)
    return "done"

def step_public(row: dict, *, include_prompt: bool) -> dict:
    raw_blocks = row.get("content_blocks")
    if isinstance(raw_blocks, str) and raw_blocks:
        try:
            content_blocks = json.loads(raw_blocks)
        except json.JSONDecodeError:
            content_blocks = None
    else:
        content_blocks = raw_blocks or None
    meta = _meta_loads(row.get("meta_json"))
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
        "cost_note": row.get("error")
        if row.get("status") == "done" and row.get("cost_usd") is None and row.get("model")
        else None,
        "duration_ms": row.get("duration_ms"),
        "error": row.get("error") if row.get("status") == "failed" else None,
        "reused_from": row.get("reused_from"),
        "content_blocks": content_blocks,
        "prompt_name": row.get("prompt_name") or None,
        "prompt_version": row.get("prompt_version") or None,
        "prompt_test_version_id": row.get("prompt_test_version_id"),
        "meta_json": meta,
    }
    if include_prompt:
        body["prompt_text"] = row.get("prompt_text") or None
        body["thinking_text"] = row.get("thinking_text") or None
    return body
