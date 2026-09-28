# -*- coding: utf-8 -*-
"""假模型自测：题组、进度、单篇重跑、max_tokens。写入 data/panai4/panai4_test.db。"""
from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

os.environ["PANAI4_FAKE_LLM"] = "1"
os.environ["PANAI4_FAKE_DELAY"] = "0"
os.environ["PANAI4_DB_PATH"] = str(BACKEND / "data" / "panai4" / "panai4_test.db")

from fastapi.testclient import TestClient

from main import app
from panai4 import llm
from panai4.config import db_path
from user.token import test_token

app.dependency_overrides[test_token] = lambda: {"username": "verify", "role": "t0"}


def poll(client, run_id, timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/panai4/runs/{run_id}/progress").json()
        if body["status"] in {"done", "failed", "interrupted"}:
            return body
        time.sleep(0.05)
    raise SystemExit(f"超时 {run_id}")


def main():
    name = f"题组{uuid.uuid4().hex[:6]}"
    with TestClient(app) as client:
        print("meta", client.get("/api/panai4/meta").json())
        created = client.post(
            "/api/panai4/topic_sets",
            json={
                "name": name,
                "items": [
                    {"title": "甲", "original_outline": "壹 有纲目"},
                    {"title": "乙"},
                    {"title": "丙", "original_outline": "壹 另一篇"},
                ],
            },
        )
        print("create set", created.status_code)
        assert created.status_code == 201, created.text
        set_id = created.json()["id"]
        dup = client.post("/api/panai4/topic_sets", json={"name": name, "items": [{"title": "甲"}]})
        print("dup", dup.status_code, dup.json())
        assert dup.status_code == 409
        assert "改名" in dup.json()["detail"]

        updated = client.put(
            f"/api/panai4/topic_sets/{set_id}",
            json={"items": [{"title": "甲改", "original_outline": "壹 改过"}, {"title": "乙改"}, {"title": "丙改", "original_outline": "壹 仍有"}]},
        )
        assert updated.status_code == 200, updated.text
        loaded = client.get(f"/api/panai4/topic_sets/{set_id}").json()
        assert [item["title"] for item in loaded["items"]] == ["甲改", "乙改", "丙改"]
        assert loaded["items"][0]["original_outline"] == "壹 改过"
        listed = client.get("/api/panai4/topic_sets").json()["sets"]
        assert any(row["id"] == set_id and row["item_count"] == 3 for row in listed)

        os.environ["PANAI4_FAKE_DELAY"] = "0.4"
        llm.call_log.clear()
        submitted = client.post(
            "/api/panai4/runs",
            json={
                "note": "假模型三篇",
                "created_by": "自测",
                "topic_set_id": set_id,
                "items": [
                    {"title": "甲改", "original_outline": f"壹 改过 {name}"},
                    {"title": "乙改"},
                    {"title": "丙改", "original_outline": f"壹 仍有 {name}"},
                ],
            },
        )
        assert submitted.status_code == 202, submitted.text
        run_id = submitted.json()["run_id"]
        mid = client.get(f"/api/panai4/runs/{run_id}/progress").json()
        print("mid", mid["status"], mid["completed_count"], mid["total_count"], mid["current"])
        assert mid["total_count"] == 3
        assert "thinking_text" not in mid["items"][0]["steps"][0]
        also = client.post("/api/panai4/runs", json={"created_by": "自测", "items": [{"title": "同时跑"}]})
        print("also", also.status_code, also.json())
        assert also.status_code == 202
        poll(client, run_id, timeout=20)
        poll(client, also.json()["run_id"], timeout=20)
        detail = client.get(f"/api/panai4/runs/{run_id}").json()
        assert detail["topic_set_id"] == set_id
        assert detail["status"] == "done"
        burden = detail["items"][0]["steps"][0]
        assert db_path().name == "panai4_test.db"
        assert burden["model"] == "fake"
        assert burden["cost_usd"] == 0
        assert burden["thinking_text"]
        by_step = {step["step"]: step for step in detail["items"][0]["steps"]}
        assert by_step["skeleton"]["prompt_name"] == "Prompt2"
        assert by_step["skeleton"]["prompt_version"] == "v0.2"
        assert by_step["skeleton"]["model"] == "fake"
        assert "【输出格式】" in (by_step["skeleton"]["prompt_text"] or "")
        assert by_step["orig_skeleton"]["prompt_name"] == "Prompt3"
        assert by_step["orig_skeleton"]["prompt_version"] == "v0.2"
        assert by_step["orig_skeleton"]["model"] == "fake"
        assert "【输出格式】" in (by_step["orig_skeleton"]["prompt_text"] or "")
        assert "【职事界定】" in burden["output_text"]
        assert "【真理脉络】" in burden["output_text"]
        assert "【负担说明】" in burden["output_text"]
        assert burden["prompt_text"]
        limits = {}
        for row in llm.call_log:
            prompt = row["prompt"]
            if "构建并生成一条「负担说明」" in prompt:
                kind = "burden"
            elif "完整原纲目" in prompt:
                kind = "orig"
            elif "生成的龙骨" in prompt and "诊断" in prompt:
                kind = "diagnosis"
            elif "生成一份「龙骨」" in prompt:
                kind = "skeleton"
            else:
                kind = "other"
            limits.setdefault(kind, set()).add(row["max_tokens"])
        print("limits", {key: sorted(value) for key, value in limits.items()})
        assert limits["burden"] == {16000}
        assert limits["skeleton"] == {8192}
        assert limits["orig"] == {8192}
        assert limits["diagnosis"] == {8192}

        client.put(
            f"/api/panai4/topic_sets/{set_id}",
            json={"items": [{"title": "被改掉的题组"}]},
        )
        again = client.get(f"/api/panai4/runs/{run_id}").json()
        assert again["items"][0]["title"] == "甲改"

        os.environ["PANAI4_FAKE_DELAY"] = "0"
        one = client.post(f"/api/panai4/runs/{run_id}/items/2/rerun", json={"created_by": "自测", "start_step": "skeleton"})
        print("item rerun", one.status_code, one.json())
        assert one.status_code == 202
        one_body = client.get(f"/api/panai4/runs/{one.json()['run_id']}").json()
        poll(client, one.json()["run_id"])
        one_body = client.get(f"/api/panai4/runs/{one.json()['run_id']}").json()
        assert one_body["parent_run_id"] == run_id
        assert one_body["note"] == f"重跑自 #{run_id} 第2篇，从新生成的龙骨。假模型三篇"
        assert len(one_body["items"]) == 1
        assert one_body["items"][0]["position"] == 2
        assert one_body["items"][0]["title"] == "乙改"
        assert one_body["items"][0]["steps"][0]["reused_from"]

        whole = client.post(f"/api/panai4/runs/{run_id}/rerun", json={"created_by": "自测", "start_step": "diagnosis"})
        assert whole.status_code == 202, whole.text
        poll(client, whole.json()["run_id"])
        whole_body = client.get(f"/api/panai4/runs/{whole.json()['run_id']}").json()
        assert whole_body["parent_run_id"] == run_id
        assert whole_body["start_step"] == "diagnosis"
        assert whole_body["note"] == f"重跑自 #{run_id}，从对比诊断。假模型三篇"
        listed_runs = client.get("/api/panai4/runs").json()["runs"]
        hit = next(row for row in listed_runs if row["id"] == one.json()["run_id"])
        assert hit["parent_run_id"] == run_id
        print("BENCH CHECKS DONE")


if __name__ == "__main__":
    main()
