# -*- coding: utf-8 -*-
"""PanAI 4.0 测试台接口。鉴权与 KgRagTest 相同，使用 test_token。
团队共用一个登录账号，建立人取页面“我是”里填的名字（created_by）。
"""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from user.token import test_token

from . import db
from .config import (
    CREATOR_MAX_LEN,
    ESTIMATE_USD_BURDEN,
    ESTIMATE_USD_DIAGNOSIS,
    ESTIMATE_USD_FOUR_STEPS,
    ESTIMATE_USD_ORIG_SKELETON,
    ESTIMATE_USD_SKELETON,
    ESTIMATE_USD_TWO_STEPS,
    max_concurrent_runs,
)
from .export_docx import (
    EXPORT_STEPS,
    build_article_zip,
    build_run_zip,
    build_step_docx,
    completed_export_steps,
    content_disposition,
)
from .pipeline import (
    ALL_STEPS,
    ANALYSIS_SCOPES,
    MAIN_SCOPES,
    SKIP_UNSELECTED,
    STEP_IDS,
    STEP_LABELS,
    cover_start_step,
    initial_step_status,
)
from .prompt_diff import paragraph_diff
from .prompts import REGISTRY, check_placeholders, current_prompt, load_template, render_user
from .runner import cancel_run, step_public, submit_run

RERUN_STEPS = ("burden", "skeleton", "orig_skeleton", "diagnosis")
NEED_NAME = "请先填写你的名字"
TEST_DELETED = "所用测试版已删除，请重新选择版本"

router = APIRouter(prefix="/api/panai4", tags=["panai4"], dependencies=[Depends(test_token)])


class RunItemIn(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    original_outline: Optional[str] = None


class RunCreate(BaseModel):
    items: list[RunItemIn] = Field(..., min_length=1, max_length=50)
    note: str = ""
    topic_set_id: Optional[int] = None
    main_scope: str = "skeleton"
    analysis_scope: str = "diagnosis"
    created_by: str = ""
    # 步骤 → 测试版 id。没列出的步骤用当前版。
    prompt_tests: dict[str, Optional[int]] = Field(default_factory=dict)


class RerunIn(BaseModel):
    start_step: str
    main_scope: Optional[str] = None
    analysis_scope: Optional[str] = None
    created_by: str = ""
    # None：沿用原运行的版本选择。
    prompt_tests: Optional[dict[str, Optional[int]]] = None


class EstimateItem(BaseModel):
    original_outline: Optional[str] = None


class EstimateIn(BaseModel):
    items: list[EstimateItem] = Field(default_factory=list, max_length=50)
    main_scope: str = "skeleton"
    analysis_scope: str = "diagnosis"
    prompt_tests: dict[str, Optional[int]] = Field(default_factory=dict)


class TopicItemIn(BaseModel):
    title: str = Field("", max_length=500)
    original_outline: Optional[str] = None


class TopicSetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    items: list[TopicItemIn] = Field(..., min_length=1, max_length=50)


class TopicSetUpdate(BaseModel):
    items: list[TopicItemIn] = Field(..., min_length=1, max_length=50)


class PromptCheckIn(BaseModel):
    step: str
    template: str = ""
    parent_kind: str = "current"
    parent_test_id: Optional[int] = None


class PromptTestCreate(PromptCheckIn):
    change_note: str = ""
    created_by: str = ""


class PromptDiffIn(BaseModel):
    step: str
    template: str
    against_kind: str
    against_version: Optional[str] = None
    against_test_id: Optional[int] = None


def _creator(raw: str) -> str:
    name = (raw or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail=NEED_NAME)
    if len(name) > CREATOR_MAX_LEN:
        raise HTTPException(status_code=400, detail=f"名字最多 {CREATOR_MAX_LEN} 字")
    return name


def _check_prompt_step(step: str) -> None:
    if step not in RERUN_STEPS:
        raise HTTPException(status_code=400, detail="Prompt 步骤无效")


def _validate_scopes(main_scope: str, analysis_scope: str) -> None:
    if main_scope not in MAIN_SCOPES or analysis_scope not in ANALYSIS_SCOPES:
        raise HTTPException(status_code=400, detail="步骤选择无效")
    if main_scope != "skeleton" and analysis_scope == "diagnosis":
        raise HTTPException(status_code=400, detail="对比诊断需要新生成的龙骨")
    if main_scope == "none" and analysis_scope == "none":
        raise HTTPException(status_code=400, detail="请至少选择一个步骤")


def _kept_outline(raw: str | None) -> str | None:
    text = raw or ""
    if not text.strip():
        return None
    return text


class _Choices:
    """每一步用哪一版。只有真正要执行的步骤才解析；所选测试版已删除时拒绝。"""

    def __init__(self, tests: dict[str, Optional[int]] | None):
        self.tests = {step: int(value) for step, value in (tests or {}).items() if step in RERUN_STEPS and value}
        self.resolved: dict[str, dict] = {}

    def get(self, step: str) -> dict:
        if step in self.resolved:
            return self.resolved[step]
        test_id = self.tests.get(step)
        if test_id:
            row = db.get_prompt_test(test_id)
            if row is None or row["step"] != step:
                raise HTTPException(status_code=400, detail="所选测试版不存在")
            if row.get("deleted_at"):
                raise HTTPException(status_code=409, detail=TEST_DELETED)
            choice = {
                "kind": "test",
                "id": row["id"],
                "name": row["prompt_name"],
                "version": row["version_name"],
                "created_by": row["created_by"],
                "template": row["template"],
            }
        else:
            current = current_prompt(step)
            choice = {
                "kind": "current",
                "id": None,
                "name": current["name"],
                "version": current["version"],
                "template": current["template"],
            }
        self.resolved[step] = choice
        return choice

    def uses_test(self) -> bool:
        return any(choice["kind"] == "test" for choice in self.resolved.values())

    def selection(self) -> dict:
        rows = db.get_prompt_tests(set(self.tests.values()))
        out = {}
        for step in RERUN_STEPS:
            test_id = self.tests.get(step)
            if test_id:
                row = rows.get(test_id) or {}
                out[step] = {
                    "kind": "test",
                    "id": test_id,
                    "version": row.get("version_name"),
                    "created_by": row.get("created_by"),
                }
            else:
                out[step] = {"kind": "current", "id": None, "version": current_prompt(step)["version"]}
        return out


def _fresh_step(position: int, spec, status: str, output: str | None, title: str, outline: str | None, choices: _Choices) -> dict:
    prompt_name = ""
    prompt_version = ""
    prompt_text = ""
    test_id = None
    if status == "pending":
        choice = choices.get(spec.step)
        prompt_name = choice["name"]
        prompt_version = choice["version"]
        test_id = choice["id"]
        if spec.step in {"burden", "orig_skeleton"}:
            prompt_text = render_user(spec.step, topic=title, original_outline=outline or "", template=choice["template"])
    return {
        "position": position,
        "step": spec.step,
        "status": status,
        "output_text": output,
        "prompt_name": prompt_name,
        "prompt_version": prompt_version,
        "prompt_text": prompt_text,
        "prompt_test_version_id": test_id,
        "model": "",
    }


def _steps_for_item(
    position: int,
    title: str,
    outline: str | None,
    main_scope: str,
    analysis_scope: str,
    choices: _Choices,
    parent_steps: dict | None = None,
    start_step: str | None = None,
) -> list[dict]:
    has_outline = bool(outline)
    start_index = STEP_IDS.index(start_step) if start_step else None
    steps = []
    for spec in ALL_STEPS:
        src = (parent_steps or {}).get(spec.step)
        before = start_index is not None and STEP_IDS.index(spec.step) < start_index
        if before and src and (src.get("output_text") or "") != SKIP_UNSELECTED:
            steps.append(_copy_step(position, src))
            continue
        status, output = initial_step_status(spec, has_outline, main_scope, analysis_scope)
        steps.append(_fresh_step(position, spec, status, output, title, outline, choices))
    return steps


def _prepare(body: RunCreate, choices: _Choices) -> tuple[list[dict], list[dict]]:
    _validate_scopes(body.main_scope, body.analysis_scope)
    items = []
    steps = []
    for index, item in enumerate(body.items, start=1):
        outline = _kept_outline(item.original_outline)
        items.append(
            {
                "position": index,
                "title": item.title.strip(),
                "original_outline": outline,
                "outline_hash": db.outline_hash(outline) if outline else None,
            }
        )
        steps.extend(
            _steps_for_item(index, item.title.strip(), outline, body.main_scope, body.analysis_scope, choices)
        )
    return items, steps


def _selection_of(run: dict) -> dict | None:
    raw = run.get("prompt_selection")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def _public_selection(selection: dict | None) -> dict:
    """补上测试版目前是否已删除。旧运行没有记录时视为全部当前版（按当时步骤里记下的版本号）。"""
    selection = selection or {}
    ids = {int(entry["id"]) for entry in selection.values() if entry.get("kind") == "test" and entry.get("id")}
    rows = db.get_prompt_tests(ids)
    out = {}
    for step in RERUN_STEPS:
        entry = dict(selection.get(step) or {"kind": "current", "id": None, "version": None})
        if entry.get("kind") == "test":
            row = rows.get(int(entry["id"])) if entry.get("id") else None
            entry["deleted"] = row is None or bool(row.get("deleted_at"))
            if row:
                entry["version"] = row["version_name"]
                entry["created_by"] = row["created_by"]
        out[step] = entry
    return out


def _run_body(run_id: int, *, include_prompt: bool) -> dict:
    run = db.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    raw_items = db.list_items(run_id)
    raw_steps = {item["id"]: db.list_steps(item["id"]) for item in raw_items}
    test_ids = {
        int(step["prompt_test_version_id"])
        for steps in raw_steps.values()
        for step in steps
        if step.get("prompt_test_version_id")
    }
    tests = db.get_prompt_tests(test_ids)
    items = []
    for item in raw_items:
        public_steps = []
        for step in raw_steps[item["id"]]:
            public = step_public(step, include_prompt=include_prompt)
            test = tests.get(int(step["prompt_test_version_id"])) if step.get("prompt_test_version_id") else None
            if test is not None:
                public["prompt_test_deleted"] = bool(test.get("deleted_at"))
                public["prompt_test_created_by"] = test.get("created_by")
            if public["step"] == "orig_skeleton" and public["status"] == "done" and not (public.get("model") or ""):
                public["cache_from_run_id"] = db.cache_source_run_id(
                    item.get("original_outline") or "", step.get("prompt_version") or ""
                )
            public_steps.append(public)
        items.append(
            {
                "id": item["id"],
                "position": item["position"],
                "title": item["title"],
                "original_outline": item.get("original_outline"),
                "status": item["status"],
                "error": item.get("error"),
                "steps": public_steps,
            }
        )
    summary = _summary(items)
    return {
        "run_id": run["id"],
        "created_at": run["created_at"],
        "started_at": run.get("started_at"),
        "finished_at": run.get("finished_at"),
        "status": run["status"],
        "queue_ahead": db.queue_ahead(run_id) if run["status"] == "queued" else 0,
        "max_concurrent_runs": max_concurrent_runs(),
        "created_by": run.get("created_by") or "",
        "uses_test": bool(run.get("uses_test")),
        "prompt_selection": _public_selection(_selection_of(run)),
        "note": run.get("note") or "",
        "parent_run_id": run.get("parent_run_id"),
        "start_step": run.get("start_step"),
        "main_scope": run.get("main_scope") or "skeleton",
        "analysis_scope": run.get("analysis_scope") or "diagnosis",
        "topic_set_id": run.get("topic_set_id"),
        "cost_usd": summary["cost_usd"],
        "completed_count": summary["completed_count"],
        "total_count": summary["total_count"],
        "current": summary["current"],
        "items": items,
    }


def _summary(items: list[dict]) -> dict:
    cost = 0.0
    current = None
    completed = 0
    for item in items:
        if item["status"] not in ("pending", "running"):
            completed += 1
        for step in item["steps"]:
            if step.get("cost_usd"):
                cost += float(step["cost_usd"])
            if current is None and step["status"] == "running":
                current = {
                    "position": item["position"],
                    "title": item["title"],
                    "step": step["step"],
                    "label": step["label"],
                }
        if current is None and item["status"] == "running":
            current = {
                "position": item["position"],
                "title": item["title"],
                "step": None,
                "label": None,
            }
    return {
        "cost_usd": round(cost, 6),
        "completed_count": completed,
        "total_count": len(items),
        "current": current,
    }


def _copy_step(position: int, src: dict) -> dict:
    return {
        "position": position,
        "step": src["step"],
        "status": src["status"],
        "output_text": src.get("output_text"),
        "prompt_name": src.get("prompt_name") or "",
        "prompt_version": src.get("prompt_version") or "",
        "prompt_text": src.get("prompt_text") or "",
        "prompt_test_version_id": src.get("prompt_test_version_id"),
        "model": src.get("model") or "",
        "input_tokens": src.get("input_tokens"),
        "output_tokens": src.get("output_tokens"),
        "cache_creation_input_tokens": src.get("cache_creation_input_tokens"),
        "cache_read_input_tokens": src.get("cache_read_input_tokens"),
        "cache_creation_5m_tokens": src.get("cache_creation_5m_tokens"),
        "cost_usd": src.get("cost_usd"),
        "duration_ms": src.get("duration_ms"),
        "stop_reason": src.get("stop_reason"),
        "error": src.get("error"),
        "content_blocks": src.get("content_blocks"),
        "thinking_text": src.get("thinking_text"),
        "reused_from": src["id"],
    }


def _rerun_note(parent_id: int, parent_note: str, start_step: str, position: int | None = None) -> str:
    label = STEP_LABELS[start_step]
    if position is None:
        head = f"重跑自 #{parent_id}，从{label}"
    else:
        head = f"重跑自 #{parent_id} 第{position}篇，从{label}"
    old = (parent_note or "").strip()
    if not old:
        return head
    return f"{head}。{old}"


def _prepare_rerun(
    parent_id: int,
    start_step: str,
    main_scope: str,
    analysis_scope: str,
    choices: _Choices,
    only_position: int | None = None,
) -> tuple[list[dict], list[dict]]:
    items = []
    steps = []
    for item in db.list_items(parent_id):
        if only_position is not None and item["position"] != only_position:
            continue
        outline = _kept_outline(item.get("original_outline"))
        position = item["position"]
        items.append(
            {
                "position": position,
                "title": item["title"],
                "original_outline": outline,
                "outline_hash": db.outline_hash(outline) if outline else None,
            }
        )
        parent_steps = {row["step"]: row for row in db.list_steps(item["id"])}
        steps.extend(
            _steps_for_item(
                position,
                item["title"],
                outline,
                main_scope,
                analysis_scope,
                choices,
                parent_steps,
                start_step,
            )
        )
    return items, steps


def _normalize_topic_items(items: list[TopicItemIn]) -> list[dict]:
    rows = []
    for index, item in enumerate(items, start=1):
        outline = (item.original_outline or "").strip()
        rows.append(
            {
                "position": index,
                "title": item.title.strip(),
                "original_outline": outline or None,
            }
        )
    return rows


def _check_start_step(start_step: str) -> None:
    if start_step not in RERUN_STEPS:
        raise HTTPException(status_code=400, detail="start_step 只能是 burden、skeleton、orig_skeleton、diagnosis")


def _submitted(run_id: int, **extra) -> dict:
    run = db.get_run(run_id) or {}
    status = run.get("status") or "queued"
    return {
        "run_id": run_id,
        "status": status,
        "queue_ahead": db.queue_ahead(run_id) if status == "queued" else 0,
        **extra,
    }


@router.get("/meta")
async def meta():
    return {
        "estimate_usd_burden": ESTIMATE_USD_BURDEN,
        "estimate_usd_skeleton": ESTIMATE_USD_SKELETON,
        "estimate_usd_orig_skeleton": ESTIMATE_USD_ORIG_SKELETON,
        "estimate_usd_diagnosis": ESTIMATE_USD_DIAGNOSIS,
        "estimate_usd_two_steps": ESTIMATE_USD_TWO_STEPS,
        "estimate_usd_four_steps": ESTIMATE_USD_FOUR_STEPS,
        "max_concurrent_runs": max_concurrent_runs(),
        "creator_max_len": CREATOR_MAX_LEN,
    }


@router.get("/creators")
async def creators():
    return {"names": db.creator_names()}


@router.post("/estimate")
async def estimate(body: EstimateIn):
    _validate_scopes(body.main_scope, body.analysis_scope)
    version = current_prompt("orig_skeleton")["version"]
    test_id = (body.prompt_tests or {}).get("orig_skeleton")
    if test_id:
        row = db.get_prompt_test(int(test_id))
        if row is not None and row["step"] == "orig_skeleton":
            version = row["version_name"]
    total = 0.0
    hits = []
    for item in body.items:
        outline = item.original_outline or ""
        cost = 0.0
        if body.main_scope in {"burden", "skeleton"}:
            cost += ESTIMATE_USD_BURDEN
        if body.main_scope == "skeleton":
            cost += ESTIMATE_USD_SKELETON
        hit = False
        if outline.strip() and body.analysis_scope in {"orig_skeleton", "diagnosis"}:
            hit = db.orig_cache_exists(outline, version)
            if not hit:
                cost += ESTIMATE_USD_ORIG_SKELETON
        if outline.strip() and body.analysis_scope == "diagnosis":
            cost += ESTIMATE_USD_DIAGNOSIS
        hits.append(hit)
        total += cost
    return {"usd": round(total, 6), "orig_cache_hits": hits}


@router.get("/topic_sets")
async def list_topic_sets():
    return {"sets": db.list_topic_sets()}


@router.post("/topic_sets", status_code=201)
async def create_topic_set(body: TopicSetCreate):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="请填写题组名称")
    if db.topic_set_name_exists(name):
        raise HTTPException(status_code=409, detail="名称已存在，请改名")
    set_id = db.create_topic_set(name, _normalize_topic_items(body.items))
    return db.get_topic_set(set_id)


@router.get("/topic_sets/{set_id}")
async def read_topic_set(set_id: int):
    body = db.get_topic_set(set_id)
    if body is None:
        raise HTTPException(status_code=404, detail="题组不存在")
    return body


@router.put("/topic_sets/{set_id}")
async def update_topic_set(set_id: int, body: TopicSetUpdate):
    if not db.replace_topic_set_items(set_id, _normalize_topic_items(body.items)):
        raise HTTPException(status_code=404, detail="题组不存在")
    return db.get_topic_set(set_id)


@router.delete("/topic_sets/{set_id}")
async def remove_topic_set(set_id: int):
    if not db.delete_topic_set(set_id):
        raise HTTPException(status_code=404, detail="题组不存在")
    return {"ok": True}


@router.post("/runs", status_code=202)
async def create_run(body: RunCreate):
    creator = _creator(body.created_by)
    if body.topic_set_id is not None and db.get_topic_set(body.topic_set_id) is None:
        raise HTTPException(status_code=404, detail="题组不存在")
    choices = _Choices(body.prompt_tests)
    items, steps = _prepare(body, choices)
    run_id = await submit_run(
        items,
        body.note,
        steps,
        topic_set_id=body.topic_set_id,
        main_scope=body.main_scope,
        analysis_scope=body.analysis_scope,
        created_by=creator,
        prompt_selection=choices.selection(),
        uses_test=choices.uses_test(),
    )
    return _submitted(run_id)


def _rerun_scopes(parent: dict, body: RerunIn) -> tuple[str, str]:
    main = body.main_scope or parent.get("main_scope") or "skeleton"
    analysis = body.analysis_scope or parent.get("analysis_scope") or "diagnosis"
    main, analysis = cover_start_step(main, analysis, body.start_step)
    _validate_scopes(main, analysis)
    return main, analysis


def _rerun_choices(parent: dict, body: RerunIn) -> _Choices:
    if body.prompt_tests is not None:
        return _Choices(body.prompt_tests)
    selection = _selection_of(parent) or {}
    inherited = {
        step: entry.get("id")
        for step, entry in selection.items()
        if isinstance(entry, dict) and entry.get("kind") == "test"
    }
    return _Choices(inherited)


async def _submit_rerun(run_id: int, body: RerunIn, position: int | None) -> dict:
    _check_start_step(body.start_step)
    creator = _creator(body.created_by)
    parent = db.get_run(run_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    main_scope, analysis_scope = _rerun_scopes(parent, body)
    choices = _rerun_choices(parent, body)
    items, steps = _prepare_rerun(run_id, body.start_step, main_scope, analysis_scope, choices, only_position=position)
    if not items:
        raise HTTPException(status_code=404, detail="这一篇不存在")
    new_id = await submit_run(
        items,
        _rerun_note(run_id, parent.get("note") or "", body.start_step, position),
        steps,
        parent_run_id=run_id,
        start_step=body.start_step,
        topic_set_id=parent.get("topic_set_id"),
        main_scope=main_scope,
        analysis_scope=analysis_scope,
        created_by=creator,
        prompt_selection=choices.selection(),
        uses_test=choices.uses_test(),
    )
    return _submitted(new_id, parent_run_id=run_id, start_step=body.start_step)


@router.post("/runs/{run_id}/rerun", status_code=202)
async def rerun(run_id: int, body: RerunIn):
    return await _submit_rerun(run_id, body, None)


@router.post("/runs/{run_id}/items/{position}/rerun", status_code=202)
async def rerun_item(run_id: int, position: int, body: RerunIn):
    return await _submit_rerun(run_id, body, position)


@router.post("/runs/{run_id}/cancel")
async def cancel(run_id: int):
    result = await cancel_run(run_id)
    if result == "missing":
        raise HTTPException(status_code=404, detail="运行不存在")
    if result == "finished":
        raise HTTPException(status_code=409, detail="这次运行已结束，不能取消")
    return {"ok": True, "status": (db.get_run(run_id) or {}).get("status")}


DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


def _load_item(run_id: int, position: int) -> tuple[dict, list[dict]]:
    if db.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    item = next((row for row in db.list_items(run_id) if row["position"] == position), None)
    if item is None:
        raise HTTPException(status_code=404, detail="这一篇不存在")
    return item, db.list_steps(item["id"])


@router.get("/runs/{run_id}/items/{position}/steps/{step}/docx")
async def export_step(run_id: int, position: int, step: str):
    if step not in EXPORT_STEPS:
        raise HTTPException(status_code=400, detail="这一步不能导出")
    item, steps = _load_item(run_id, position)
    row = next((entry for entry in steps if entry["step"] == step), None)
    if row is None or row["status"] != "done":
        raise HTTPException(status_code=404, detail="这一步还没有完成")
    try:
        filename, data = build_step_docx(item, row)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return Response(content=data, media_type=DOCX_TYPE, headers={"Content-Disposition": content_disposition(filename)})


@router.get("/runs/{run_id}/items/{position}/export.zip")
async def export_item_zip(run_id: int, position: int):
    item, steps = _load_item(run_id, position)
    if not completed_export_steps(steps):
        raise HTTPException(status_code=404, detail="没有可导出的步骤")
    filename, data = build_article_zip(item, steps)
    return Response(content=data, media_type="application/zip", headers={"Content-Disposition": content_disposition(filename)})


@router.get("/runs/{run_id}/export.zip")
async def export_run_zip(run_id: int):
    if db.get_run(run_id) is None:
        raise HTTPException(status_code=404, detail="运行不存在")
    packed = [(item, db.list_steps(item["id"])) for item in db.list_items(run_id)]
    if not any(completed_export_steps(steps) for _item, steps in packed):
        raise HTTPException(status_code=404, detail="没有可导出的步骤")
    data = build_run_zip(packed)
    return Response(
        content=data,
        media_type="application/zip",
        headers={"Content-Disposition": content_disposition(f"运行{run_id}.zip")},
    )


@router.delete("/runs/{run_id}")
async def remove_run(run_id: int):
    result = db.delete_run(run_id)
    if result == "missing":
        raise HTTPException(status_code=404, detail="运行不存在")
    if result == "active":
        raise HTTPException(status_code=409, detail="排队中或运行中的任务不能删除，请先取消")
    return {"ok": True}


@router.get("/runs")
async def list_runs(limit: int = 50, created_by: Optional[str] = None):
    limit = max(1, min(limit, 200))
    name = created_by.strip() if created_by is not None else None
    rows = db.list_runs(limit, name if name else None)
    for row in rows:
        row["uses_test"] = bool(row.get("uses_test"))
        row["queue_ahead"] = row.get("queue_ahead") if row["status"] == "queued" else 0
        row.pop("prompt_selection", None)
    return {"runs": rows, "max_concurrent_runs": max_concurrent_runs()}


@router.get("/runs/{run_id}/progress")
async def run_progress(run_id: int):
    return _run_body(run_id, include_prompt=False)


@router.get("/runs/{run_id}")
async def run_detail(run_id: int):
    return _run_body(run_id, include_prompt=True)


def _test_public(row: dict, *, include_template: bool) -> dict:
    body = {
        "id": row["id"],
        "step": row["step"],
        "prompt_name": row["prompt_name"],
        "label": STEP_LABELS[row["step"]],
        "base_current_version": row["base_current_version"],
        "version_name": row["version_name"],
        "parent_kind": row["parent_kind"],
        "parent_version": row["parent_version"],
        "parent_test_id": row.get("parent_test_id"),
        "change_note": row["change_note"],
        "created_by": row["created_by"],
        "created_at": row["created_at"],
        "used_count": int(row.get("used_count") or 0),
        "deleted": bool(row.get("deleted_at")),
    }
    if include_template:
        body["template"] = row["template"]
    return body


def _parent_for(step: str, parent_kind: str, parent_test_id: Optional[int]) -> dict:
    """底稿：当前版或某个未删除的测试版。返回所属当前版号与底稿版本名。"""
    if parent_kind == "current":
        version = current_prompt(step)["version"]
        return {"kind": "current", "base": version, "version": version, "test_id": None}
    if parent_kind != "test" or not parent_test_id:
        raise HTTPException(status_code=400, detail="底稿无效")
    row = db.get_prompt_test(parent_test_id)
    if row is None or row["step"] != step:
        raise HTTPException(status_code=404, detail="底稿不存在")
    if row.get("deleted_at"):
        raise HTTPException(status_code=409, detail="底稿已删除")
    return {"kind": "test", "base": row["base_current_version"], "version": row["version_name"], "test_id": row["id"]}


def _normalized_template(text: str) -> str:
    return (text or "").replace("\r\n", "\n").replace("\r", "\n")


@router.get("/prompts")
async def list_prompts():
    tests = [_test_public(row, include_template=False) for row in db.list_prompt_tests()]
    out = []
    for step in RERUN_STEPS:
        module = REGISTRY[step]
        out.append(
            {
                "step": step,
                "name": module.NAME,
                "label": STEP_LABELS[step],
                "current_version": module.CURRENT,
                "tests": [row for row in tests if row["step"] == step],
            }
        )
    return {"prompts": out}


@router.get("/prompts/{step}/current")
async def read_current_prompt(step: str):
    _check_prompt_step(step)
    current = current_prompt(step)
    return {
        "step": step,
        "name": current["name"],
        "label": STEP_LABELS[step],
        "version": current["version"],
        "template": current["template"],
    }


@router.get("/prompt_tests/{test_id}")
async def read_prompt_test(test_id: int):
    row = db.get_prompt_test(test_id)
    if row is None:
        raise HTTPException(status_code=404, detail="测试版不存在")
    if row.get("deleted_at"):
        raise HTTPException(status_code=404, detail="这个测试版已删除")
    return _test_public(row, include_template=True)


@router.post("/prompt_tests/check")
async def check_prompt_test(body: PromptCheckIn):
    _check_prompt_step(body.step)
    parent = _parent_for(body.step, body.parent_kind, body.parent_test_id)
    result = check_placeholders(body.step, _normalized_template(body.template))
    result["version_name"] = f"{parent['base']}-测{db.next_test_seq(body.step, parent['base'])}"
    return result


@router.post("/prompt_tests", status_code=201)
async def create_prompt_test(body: PromptTestCreate):
    _check_prompt_step(body.step)
    creator = _creator(body.created_by)
    note = (body.change_note or "").strip()
    if not note:
        raise HTTPException(status_code=400, detail="请填写修改说明")
    template = _normalized_template(body.template)
    checked = check_placeholders(body.step, template)
    if not checked["ok"]:
        raise HTTPException(status_code=422, detail={"message": "填入位不对，不能保存", **checked})
    parent = _parent_for(body.step, body.parent_kind, body.parent_test_id)
    test_id = db.create_prompt_test(
        step=body.step,
        prompt_name=REGISTRY[body.step].NAME,
        base_current_version=parent["base"],
        parent_kind=parent["kind"],
        parent_version=parent["version"],
        parent_test_id=parent["test_id"],
        template=template,
        change_note=note,
        created_by=creator,
    )
    created = _test_public(db.get_prompt_test(test_id), include_template=True)
    created["warnings"] = checked["warnings"]
    return created


@router.get("/prompt_tests/{test_id}/usage")
async def prompt_test_usage(test_id: int):
    row = db.get_prompt_test(test_id)
    if row is None:
        raise HTTPException(status_code=404, detail="测试版不存在")
    return {"id": test_id, "created_by": row["created_by"], "used_count": int(row.get("used_count") or 0)}


@router.delete("/prompt_tests/{test_id}")
async def remove_prompt_test(test_id: int, deleted_by: Optional[str] = None):
    removed = db.delete_prompt_test(test_id, (deleted_by or "").strip() or None)
    if removed is None:
        raise HTTPException(status_code=404, detail="测试版不存在或已删除")
    return {"ok": True, **removed}


@router.post("/prompt_diff")
async def prompt_diff(body: PromptDiffIn):
    """把一份全文与当前版（或某个版本号）或某个测试版比较。"""
    _check_prompt_step(body.step)
    if body.against_kind == "current":
        version = body.against_version or current_prompt(body.step)["version"]
        try:
            base_text = load_template(body.step, version)
        except KeyError:
            raise HTTPException(status_code=404, detail=f"找不到当前版 {version}")
        label = f"{version}（当前版）" if version == current_prompt(body.step)["version"] else version
    elif body.against_kind == "test" and body.against_test_id:
        row = db.get_prompt_test(body.against_test_id)
        if row is None or row["step"] != body.step:
            raise HTTPException(status_code=404, detail="对比的测试版不存在")
        base_text = row["template"]
        label = row["version_name"] + ("（已删除）" if row.get("deleted_at") else "")
    else:
        raise HTTPException(status_code=400, detail="对比对象无效")
    result = paragraph_diff(base_text, _normalized_template(body.template))
    result["against"] = label
    return result
