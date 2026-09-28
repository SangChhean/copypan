# -*- coding: utf-8 -*-
"""本机验证 PanAI 4.0 后端骨架。在 back_mic/backend 下执行：

    python panai4/verify_skeleton.py

写入 data/panai4/panai4_test.db，不使用正式库。
"""
from __future__ import annotations

import os
import sqlite3
import sys
import time
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ["PANAI4_FAKE_LLM"] = "1"
os.environ.setdefault("PANAI4_FAKE_DELAY", "1")
os.environ["PANAI4_DB_PATH"] = str(BACKEND / "data" / "panai4" / "panai4_test.db")

from fastapi.testclient import TestClient

from main import app
from panai4.config import db_path
from panai4.db import init_db
from user.token import test_token

app.dependency_overrides[test_token] = lambda: {"username": "verify", "role": "t0"}


def _steps(payload: dict, title: str) -> list[dict]:
    for item in payload["items"]:
        if item["title"] == title:
            return item["steps"]
    raise SystemExit(f"找不到篇题 {title}")


def _print_steps(payload: dict) -> None:
    print(f"run {payload['run_id']} status={payload['status']}")
    for item in payload["items"]:
        print(f"  [{item['status']}] {item['title']}")
        for step in item["steps"]:
            print(f"    {step['step']} {step['status']} {step.get('output_text') or ''}")


def _poll(client: TestClient, run_id: int, timeout: float = 60) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        res = client.get(f"/api/panai4/runs/{run_id}/progress")
        res.raise_for_status()
        body = res.json()
        if body["status"] in {"done", "failed", "interrupted"}:
            return body
        time.sleep(0.4)
    raise SystemExit(f"轮询超时 run={run_id}")


def _sqlite(run_id: int) -> None:
    init_db()
    conn = sqlite3.connect(str(db_path()))
    conn.row_factory = sqlite3.Row
    run = conn.execute("SELECT id, status FROM runs WHERE id = ?", (run_id,)).fetchone()
    items = conn.execute(
        "SELECT id, title, status FROM run_items WHERE run_id = ? ORDER BY position",
        (run_id,),
    ).fetchall()
    print(f"sqlite run {run['id']} {run['status']} items {len(items)}")
    for item in items:
        steps = conn.execute(
            "SELECT step, status, output_text FROM step_results WHERE run_item_id = ? ORDER BY id",
            (item["id"],),
        ).fetchall()
        print(f"  item {item['title']} {item['status']} steps {len(steps)}")
        for step in steps:
            print(f"    {step['step']} {step['status']}")
    conn.close()


def test_fake_flow() -> None:
    os.environ["PANAI4_FAKE_LLM"] = "1"
    os.environ["PANAI4_FAKE_DELAY"] = "0.3"
    print("=== 1. 假模型：两篇，一篇带原纲目 ===")
    with TestClient(app) as client:
        created = client.post(
            "/api/panai4/runs",
            json={
                "created_by": "自测",
                "items": [
                    {"title": "没有原纲目的篇"},
                    {"title": "带原纲目的篇", "original_outline": f"壹 原纲目第一条{uuid.uuid4().hex[:8]}。"},
                ]
            },
        )
        print("submit", created.status_code, created.json())
        created.raise_for_status()
        run_id = created.json()["run_id"]
        body = _poll(client, run_id)
        _print_steps(body)
        plain = _steps(body, "没有原纲目的篇")
        outlined = _steps(body, "带原纲目的篇")
        designed = {"retrieval", "generation", "evaluation"}
        for step in plain:
            if step["step"] in designed:
                assert step["status"] == "skipped" and step["output_text"] == "跳过（待设计）", step
            if step["step"] in {"orig_skeleton", "diagnosis"}:
                assert step["status"] == "skipped", step
        called = [s for s in outlined if s["status"] == "done"]
        assert [s["step"] for s in called] == ["burden", "skeleton", "orig_skeleton", "diagnosis"], called
        for step in outlined:
            if step["step"] in designed:
                assert step["output_text"] == "跳过（待设计）", step
        detail = client.get(f"/api/panai4/runs/{run_id}").json()
        outlined_detail = _steps(detail, "带原纲目的篇")
        by_step = {step["step"]: step for step in outlined_detail}
        assert by_step["burden"]["prompt_name"] == "Prompt1"
        assert by_step["burden"]["prompt_version"] == "v0.3"
        assert by_step["skeleton"]["prompt_name"] == "Prompt2"
        assert by_step["skeleton"]["prompt_version"] == "v0.2"
        assert by_step["orig_skeleton"]["prompt_name"] == "Prompt3"
        assert by_step["orig_skeleton"]["prompt_version"] == "v0.2"
        assert "【输出格式】" in (by_step["skeleton"]["prompt_text"] or "")
        assert "【输出格式】" in (by_step["orig_skeleton"]["prompt_text"] or "")
        for step_name in ("burden", "skeleton", "orig_skeleton", "diagnosis"):
            assert by_step[step_name]["model"] == "fake", by_step[step_name]
            assert by_step[step_name]["cost_usd"] == 0, by_step[step_name]
        assert db_path().name == "panai4_test.db"
        assert by_step["diagnosis"]["prompt_name"] == "Prompt4"
        assert "{query}" not in (by_step["burden"]["prompt_text"] or "")
        assert "没有原纲目" not in (by_step["skeleton"]["prompt_text"] or "")
        assert "【测试负担】带原纲目的篇" in by_step["skeleton"]["prompt_text"]
        assert "{burden}" not in by_step["skeleton"]["prompt_text"]
        assert by_step["burden"]["content_blocks"] == {"text": 1, "thinking": 1}
        assert "【负担说明】" in (by_step["burden"]["output_text"] or "")
        assert by_step["burden"]["reused_from"] is None
        _sqlite(run_id)

        print("=== 2. 运行中再提交，期望同时执行而不是 409；未填名字期望 400 ===")
        os.environ["PANAI4_FAKE_DELAY"] = "3"
        first = client.post("/api/panai4/runs", json={"created_by": "自测", "items": [{"title": "先提交"}]})
        second = client.post("/api/panai4/runs", json={"created_by": "自测", "items": [{"title": "后提交"}]})
        print("first", first.status_code, first.json())
        print("second", second.status_code, second.json())
        assert first.status_code == 202 and second.status_code == 202
        assert second.json()["status"] == "running", second.json()
        nameless = client.post("/api/panai4/runs", json={"created_by": "  ", "items": [{"title": "没名字"}]})
        assert nameless.status_code == 400 and nameless.json()["detail"] == "请先填写你的名字", nameless.text
        _poll(client, first.json()["run_id"], timeout=30)
        _poll(client, second.json()["run_id"], timeout=30)

    print("=== 3. 运行中重启，期望中断 ===")
    os.environ["PANAI4_FAKE_DELAY"] = "30"
    with TestClient(app) as client:
        created = client.post("/api/panai4/runs", json={"created_by": "自测", "items": [{"title": "会被中断"}]})
        print("submit", created.status_code, created.json())
        run_id = created.json()["run_id"]
        time.sleep(0.5)
    with TestClient(app) as client:
        body = client.get(f"/api/panai4/runs/{run_id}").json()
        print("after restart", body["status"])
        assert body["status"] == "interrupted", body["status"]

    os.environ["PANAI4_FAKE_DELAY"] = "0"
    from panai4 import llm

    print("=== 4. 负担截取失败，龙骨失败则对比诊断不执行 ===")
    outline = f"壹 失败用例{uuid.uuid4().hex[:8]}。"
    with TestClient(app) as client:
        created = client.post(
            "/api/panai4/runs",
            json={"created_by": "自测", "items": [{"title": "缺少负担标记", "original_outline": outline}]},
        )
        created.raise_for_status()
        body = _poll(client, created.json()["run_id"])
        item = body["items"][0]
        print("item", item["status"], item.get("error"))
        assert item["status"] == "failed"
        assert item["error"] == "Prompt1 输出中找不到【负担说明】"
        steps = {step["step"]: step for step in item["steps"]}
        assert steps["skeleton"]["status"] == "failed"
        assert steps["skeleton"]["error"] == "Prompt1 输出中找不到【负担说明】"
        assert steps["orig_skeleton"]["status"] == "done"
        assert steps["diagnosis"]["status"] == "skipped"
        assert steps["diagnosis"]["output_text"] == "新生成的龙骨失败，未执行"

    print("=== 5. 同一原纲目再次运行，Prompt3 命中缓存 ===")
    outline = f"壹 缓存用例{uuid.uuid4().hex[:8]}。"
    title = "缓存篇"
    with TestClient(app) as client:
        llm.call_log.clear()
        first = client.post(
            "/api/panai4/runs",
            json={"created_by": "自测", "items": [{"title": title, "original_outline": outline}]},
        )
        first.raise_for_status()
        first_body = _poll(client, first.json()["run_id"])
        first_orig = {s["step"]: s for s in _steps(first_body, title)}["orig_skeleton"]
        assert first_orig["reused_from"] is None
        assert first_orig["model"] == "fake"
        orig_calls = sum(1 for row in llm.call_log if "完整原纲目" in row["prompt"])
        assert orig_calls == 1, orig_calls
        second = client.post(
            "/api/panai4/runs",
            json={"created_by": "自测", "items": [{"title": title, "original_outline": outline}]},
        )
        second.raise_for_status()
        second_body = _poll(client, second.json()["run_id"])
        second_orig = {s["step"]: s for s in _steps(second_body, title)}["orig_skeleton"]
        print("cache reused_from", second_orig["reused_from"], "source", first_orig["id"])
        assert second_orig["reused_from"] == first_orig["id"]
        assert second_orig["output_text"] == first_orig["output_text"]
        assert not second_orig.get("model")
        orig_calls = sum(1 for row in llm.call_log if "完整原纲目" in row["prompt"])
        assert orig_calls == 1, orig_calls

        print("=== 6. 从龙骨重跑：沿用负担说明，重做龙骨和对比诊断 ===")
        before = len(llm.call_log)
        rerun = client.post(
            f"/api/panai4/runs/{second.json()['run_id']}/rerun",
            json={"created_by": "自测", "start_step": "skeleton"},
        )
        print("rerun", rerun.status_code, rerun.json())
        rerun.raise_for_status()
        rerun_body = _poll(client, rerun.json()["run_id"])
        assert rerun_body["parent_run_id"] == second.json()["run_id"]
        assert rerun_body["start_step"] == "skeleton"
        parent_steps = {s["step"]: s for s in _steps(second_body, title)}
        again = {s["step"]: s for s in _steps(rerun_body, title)}
        assert again["burden"]["reused_from"] == parent_steps["burden"]["id"]
        assert again["burden"]["output_text"] == parent_steps["burden"]["output_text"]
        assert again["skeleton"]["reused_from"] is None
        assert again["skeleton"]["model"] == "fake"
        assert again["diagnosis"]["reused_from"] is None
        assert again["diagnosis"]["model"] == "fake"
        assert again["orig_skeleton"]["reused_from"] == first_orig["id"]
        kinds = []
        for row in llm.call_log[before:]:
            prompt = row["prompt"]
            if "完整原纲目" in prompt:
                kinds.append("orig")
            elif "生成的龙骨" in prompt and "诊断" in prompt:
                kinds.append("diagnosis")
            elif "生成一份「龙骨」" in prompt:
                kinds.append("skeleton")
            elif "构建并生成一条「负担说明」" in prompt:
                kinds.append("burden")
            else:
                kinds.append("other")
        print("rerun calls", kinds)
        assert kinds == ["skeleton", "diagnosis"], kinds

        print("=== 7. 从原纲目的龙骨重跑：绕过缓存并更新 ===")
        before = len(llm.call_log)
        forced = client.post(
            f"/api/panai4/runs/{rerun.json()['run_id']}/rerun",
            json={"created_by": "自测", "start_step": "orig_skeleton"},
        )
        forced.raise_for_status()
        forced_body = _poll(client, forced.json()["run_id"])
        forced_orig = {s["step"]: s for s in _steps(forced_body, title)}["orig_skeleton"]
        assert forced_orig["reused_from"] is None
        assert forced_orig["model"] == "fake"
        forced_calls = [row for row in llm.call_log[before:] if "完整原纲目" in row["prompt"]]
        assert len(forced_calls) == 1, len(forced_calls)


def test_real_model() -> None:
    print("真模型四步需要篇题和原纲目全文，本次未提供，不调用。")


def test_mode_35() -> None:
    print("=== 5. 3.5 查询 ===")
    with TestClient(app) as client:
        res = client.post(
            "/api/kg_rag/query",
            json={"query": "爱", "mode": "3.5", "params": {"skip_generation": False}},
            timeout=300,
        )
        print("status", res.status_code)
        if res.status_code != 200:
            print(res.text[:500])
            return
        body = res.json()
        print("mode", (body.get("params_used") or {}).get("mode"))
        answer = body.get("answer") or ""
        print("answer_len", len(answer))
        prompt = ((body.get("steps") or {}).get("step4") or {}).get("prompt") or ""
        print("step4_has_v4_mark", "【V4_MARK_0】" in prompt)


if __name__ == "__main__":
    test_fake_flow()
    if "--with-real" in sys.argv:
        test_real_model()
    if "--with-35" in sys.argv:
        test_mode_35()
    print("FAKE CHECKS DONE")
