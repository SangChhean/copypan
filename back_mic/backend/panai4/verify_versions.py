# -*- coding: utf-8 -*-
"""测试版、排队与取消、重启、同时写入的自测（假模型，只写 data/panai4/panai4_test.db）。在 back_mic/backend 下执行：python panai4/verify_versions.py"""
from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))
TEST_DB = BACKEND / "data" / "panai4" / "panai4_test.db"
os.environ["PANAI4_FAKE_LLM"] = "1"
os.environ["PANAI4_FAKE_DELAY"] = "0"
os.environ["PANAI4_DB_PATH"] = str(TEST_DB)

from fastapi.testclient import TestClient  # noqa: E402

from main import app  # noqa: E402
from panai4.config import db_path  # noqa: E402
from panai4.prompts import load_template  # noqa: E402
from user.token import test_token  # noqa: E402

app.dependency_overrides[test_token] = lambda: {"username": "shared", "role": "t1"}
API = "/api/panai4"
TAG = uuid.uuid4().hex[:6]
A = f"甲{TAG}"
B = f"乙{TAG}"


def poll(client, run_id, timeout=60):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"{API}/runs/{run_id}/progress").json()
        if body["status"] not in {"queued", "running"}:
            return body
        time.sleep(0.1)
    raise SystemExit(f"超时 {run_id}")


def status(client, run_id):
    return client.get(f"{API}/runs/{run_id}/progress").json()["status"]


def step_of(body, name, position=1):
    item = next(i for i in body["items"] if i["position"] == position)
    return next(s for s in item["steps"] if s["step"] == name)


def part1_versions(client):
    print("=== 1. 建 Prompt2 测试版 ===")
    base = load_template("skeleton", "v0.2")
    old_line = next(line for line in base.split("\n") if line.startswith("确定目标固定排在整份龙骨列表最后"))
    new_line = "确定目标固定排在整份龙骨列表最后；应用实行固定排在确定目标之前；其余各项严格按负担说明原文的先后顺序排列。"
    edited = base.replace(old_line, new_line)
    missing = edited.replace("{burden}", "")
    check = client.post(f"{API}/prompt_tests/check", json={"step": "skeleton", "template": missing}).json()
    print("check missing", check["ok"], check["problems"], check["version_name"])
    assert not check["ok"] and check["missing"] == ["burden"]
    extra = edited + "\n{original_outline}\n{query}"
    check = client.post(f"{API}/prompt_tests/check", json={"step": "skeleton", "template": extra}).json()
    print("check extra", check["problems"])
    assert check["repeated"] == ["query"] and check["unexpected"] == ["original_outline"]
    refused = client.post(
        f"{API}/prompt_tests",
        json={"step": "skeleton", "template": missing, "change_note": "少一个", "created_by": A},
    )
    print("save missing", refused.status_code, refused.json()["detail"]["problems"])
    assert refused.status_code == 422
    nameless = client.post(f"{API}/prompt_tests", json={"step": "skeleton", "template": edited, "change_note": "x", "created_by": " "})
    assert nameless.status_code == 400 and nameless.json()["detail"] == "请先填写你的名字"
    no_note = client.post(f"{API}/prompt_tests", json={"step": "skeleton", "template": edited, "change_note": " ", "created_by": A})
    assert no_note.status_code == 400
    listed = client.get(f"{API}/prompts").json()["prompts"]
    existing = [t for p in listed if p["step"] == "skeleton" for t in p["tests"]]
    expected_name = f"v0.2-测{client.post(f'{API}/prompt_tests/check', json={'step': 'skeleton', 'template': edited}).json()['version_name'].split('测')[1]}"
    saved = client.post(
        f"{API}/prompt_tests",
        json={"step": "skeleton", "template": edited, "change_note": "排序：应用实行排在确定目标之前", "created_by": f"  {A}  "},
    )
    assert saved.status_code == 201, saved.text
    test = saved.json()
    print("saved", test["version_name"], test["created_by"], "existing before", len(existing))
    assert test["version_name"] == expected_name
    assert test["created_by"] == A
    diff = client.post(
        f"{API}/prompt_diff",
        json={"step": "skeleton", "template": test["template"], "against_kind": "current", "against_version": "v0.2"},
    ).json()
    print("diff vs current", diff["changes"], [b for b in diff["blocks"] if b["type"] != "same"])
    assert diff["changes"] == 1
    child = client.post(
        f"{API}/prompt_tests",
        json={
            "step": "skeleton",
            "template": test["template"] + "\n补一句",
            "change_note": "以测1为底稿",
            "created_by": B,
            "parent_kind": "test",
            "parent_test_id": test["id"],
        },
    ).json()
    print("child", child["version_name"], child["parent_version"], child["base_current_version"])
    assert child["parent_version"] == test["version_name"] and child["base_current_version"] == "v0.2"
    burden_text = load_template("burden").replace("【负担说明】", "【负担】")
    warn = client.post(f"{API}/prompt_tests/check", json={"step": "burden", "template": burden_text}).json()
    print("prompt1 warning", warn["ok"], warn["warnings"])
    assert warn["ok"] and warn["warnings"]
    current = client.post(f"{API}/prompt_tests/check", json={"step": "burden", "template": load_template("burden")}).json()
    assert current["ok"] and not current["warnings"]
    for step in ("burden", "skeleton", "orig_skeleton", "diagnosis"):
        assert client.post(f"{API}/prompt_tests/check", json={"step": step, "template": load_template(step)}).json()["ok"], step
    return test, new_line, child


def part2_run_with_test(client, test, new_line):
    print("=== 2. 用测试版跑一篇 ===")
    res = client.post(
        f"{API}/runs",
        json={"created_by": A, "items": [{"title": f"测试版篇{TAG}"}], "main_scope": "skeleton", "analysis_scope": "none",
              "prompt_tests": {"skeleton": test["id"]}},
    )
    assert res.status_code == 202, res.text
    run_id = res.json()["run_id"]
    poll(client, run_id)
    detail = client.get(f"{API}/runs/{run_id}").json()
    skeleton = step_of(detail, "skeleton")
    burden = step_of(detail, "burden")
    print("run", run_id, detail["uses_test"], skeleton["prompt_version"], skeleton["prompt_test_version_id"], burden["prompt_version"])
    assert detail["uses_test"] and skeleton["prompt_version"] == test["version_name"]
    assert skeleton["prompt_test_version_id"] == test["id"] and burden["prompt_test_version_id"] is None
    assert new_line in skeleton["prompt_text"] and "{burden}" not in skeleton["prompt_text"]
    assert detail["prompt_selection"]["skeleton"]["version"] == test["version_name"]
    listed = client.get(f"{API}/runs?created_by={A}").json()["runs"]
    assert next(r for r in listed if r["id"] == run_id)["uses_test"] is True
    return run_id


def part3_delete(client, test, run_id):
    print("=== 3. 删除测试版 ===")
    usage = client.get(f"{API}/prompt_tests/{test['id']}/usage").json()
    print("usage", usage)
    assert usage["used_count"] >= 1 and usage["created_by"] == A
    gone = client.delete(f"{API}/prompt_tests/{test['id']}?deleted_by={B}")
    assert gone.status_code == 200, gone.text
    assert client.get(f"{API}/prompt_tests/{test['id']}").status_code == 404
    detail = client.get(f"{API}/runs/{run_id}").json()
    skeleton = step_of(detail, "skeleton")
    print("after delete", skeleton["prompt_version"], skeleton["prompt_test_deleted"], bool(skeleton["prompt_text"]))
    assert skeleton["prompt_test_deleted"] is True and skeleton["prompt_text"]
    assert detail["prompt_selection"]["skeleton"]["deleted"] is True
    again = client.post(f"{API}/runs/{run_id}/rerun", json={"created_by": A, "start_step": "skeleton"})
    print("rerun inherit", again.status_code, again.json())
    assert again.status_code == 409 and again.json()["detail"] == "所用测试版已删除，请重新选择版本"
    chosen = client.post(f"{API}/runs/{run_id}/rerun", json={"created_by": A, "start_step": "skeleton", "prompt_tests": {}})
    assert chosen.status_code == 202
    poll(client, chosen.json()["run_id"])
    listed = client.get(f"{API}/prompts").json()["prompts"]
    assert all(t["id"] != test["id"] for p in listed for t in p["tests"])

    outline = f"壹 缓存删除用例{TAG}。"
    base3 = load_template("orig_skeleton")
    t3 = client.post(
        f"{API}/prompt_tests",
        json={"step": "orig_skeleton", "template": base3 + "\n测试补充", "change_note": "测缓存", "created_by": A},
    ).json()
    run3 = client.post(
        f"{API}/runs",
        json={"created_by": A, "items": [{"title": "缓存篇", "original_outline": outline}], "main_scope": "none",
              "analysis_scope": "orig_skeleton", "prompt_tests": {"orig_skeleton": t3["id"]}},
    ).json()["run_id"]
    poll(client, run3)
    conn = sqlite3.connect(str(TEST_DB))
    cached = conn.execute("SELECT COUNT(1) FROM orig_skeleton_cache WHERE prompt3_version = ?", (t3["version_name"],)).fetchone()[0]
    client.delete(f"{API}/prompt_tests/{t3['id']}")
    after = conn.execute("SELECT COUNT(1) FROM orig_skeleton_cache WHERE prompt3_version = ?", (t3["version_name"],)).fetchone()[0]
    conn.close()
    print("prompt3 test cache", t3["version_name"], cached, "->", after)
    assert cached == 1 and after == 0


def part4_queue(client):
    print("=== 4. 两个名字同时提交 4 个运行 ===")
    os.environ["PANAI4_FAKE_DELAY"] = "1.2"
    ids = []
    for who, n in ((A, 1), (B, 2), (A, 3), (B, 4)):
        res = client.post(f"{API}/runs", json={"created_by": who, "note": f"并发{n}", "items": [{"title": f"并发{n}-一"}, {"title": f"并发{n}-二"}]})
        assert res.status_code == 202, res.text
        ids.append(res.json()["run_id"])
    states = [status(client, rid) for rid in ids]
    fourth = client.get(f"{API}/runs/{ids[3]}/progress").json()
    print("states", dict(zip(ids, states)), "fourth ahead", fourth["queue_ahead"])
    assert states == ["running", "running", "running", "queued"] and fourth["queue_ahead"] == 0
    fifth = client.post(f"{API}/runs", json={"created_by": A, "items": [{"title": "第五个"}]}).json()
    print("fifth", fifth)
    assert fifth["status"] == "queued" and fifth["queue_ahead"] == 1
    cancelled_queued = client.post(f"{API}/runs/{fifth['run_id']}/cancel")
    print("cancel queued", cancelled_queued.status_code, cancelled_queued.json())
    assert status(client, fifth["run_id"]) == "cancelled"
    time.sleep(1.6)
    target = ids[1]
    mid = client.get(f"{API}/runs/{target}").json()
    done_before = [s["step"] for i in mid["items"] for s in i["steps"] if s["status"] == "done"]
    cancel = client.post(f"{API}/runs/{target}/cancel")
    print("cancel running", cancel.status_code, cancel.json(), "done before", done_before)
    assert cancel.status_code == 200
    after = client.get(f"{API}/runs/{target}").json()
    kept = [s["step"] for i in after["items"] for s in i["steps"] if s["status"] == "done"]
    marked = [s["status"] for i in after["items"] for s in i["steps"] if s["status"] not in {"done", "skipped"}]
    print("after cancel", after["status"], "kept", kept, "others", marked, [i["status"] for i in after["items"]])
    assert after["status"] == "cancelled" and kept == done_before and set(marked) == {"cancelled"}
    deadline = time.time() + 10
    while time.time() < deadline and status(client, ids[3]) == "queued":
        time.sleep(0.1)
    print("queued one started", status(client, ids[3]))
    assert status(client, ids[3]) in {"running", "done"}
    for rid in (ids[0], ids[2], ids[3]):
        assert poll(client, rid)["status"] == "done"
    again = client.post(f"{API}/runs/{ids[0]}/cancel")
    assert again.status_code == 409
    mine_a = client.get(f"{API}/runs", params={"created_by": A}).json()["runs"]
    mine_b = client.get(f"{API}/runs", params={"created_by": B}).json()["runs"]
    print("mine A", [r["id"] for r in mine_a][:5], "mine B", [r["id"] for r in mine_b][:5])
    assert {r["created_by"] for r in mine_a} == {A} and {r["created_by"] for r in mine_b} == {B}
    assert ids[1] in [r["id"] for r in mine_b] and ids[1] not in [r["id"] for r in mine_a]
    deleted = client.delete(f"{API}/runs/{ids[1]}")
    assert deleted.status_code == 200
    names = client.get(f"{API}/creators").json()["names"]
    print("creators", names[:4])
    assert A in names and B in names
    os.environ["PANAI4_FAKE_DELAY"] = "0"


def part5_restart():
    print("=== 5. 运行中重启 ===")
    os.environ["PANAI4_FAKE_DELAY"] = "30"
    with TestClient(app) as client:
        ids = [client.post(f"{API}/runs", json={"created_by": A, "items": [{"title": f"重启{n}"}]}).json()["run_id"] for n in range(4)]
        print("before restart", [status(client, rid) for rid in ids])
    with TestClient(app) as client:
        after = [status(client, rid) for rid in ids]
        print("after restart", after)
        assert after == ["interrupted"] * 4
        detail = client.get(f"{API}/runs/{ids[3]}").json()
        assert {s["status"] for s in detail["items"][0]["steps"] if s["status"] != "skipped"} == {"interrupted"}
    os.environ["PANAI4_FAKE_DELAY"] = "0"


WRITER = r"""
import sqlite3, sys, time
conn = sqlite3.connect(sys.argv[1], timeout=30)
conn.execute("PRAGMA busy_timeout=30000")
for n in range(300):
    conn.execute("BEGIN IMMEDIATE")
    conn.execute("UPDATE topic_sets SET updated_at = updated_at")
    conn.execute("COMMIT")
    time.sleep(0.005)
print("writer ok")
"""


def part6_sqlite(client):
    print("=== 6. 3 个运行同时写，外加另一个进程写 ===")
    os.environ["PANAI4_FAKE_DELAY"] = "0"
    writer = subprocess.Popen([sys.executable, "-c", WRITER, str(TEST_DB)], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    ids = []
    for n in range(3):
        items = [{"title": f"写入{n}-{k}", "original_outline": f"壹 写入{TAG}-{n}-{k}"} for k in range(15)]
        ids.append(client.post(f"{API}/runs", json={"created_by": A, "items": items}).json()["run_id"])
    results = [poll(client, rid, timeout=120) for rid in ids]
    out, err = writer.communicate(timeout=120)
    failed = [s for body in results for i in body["items"] for s in i["steps"] if s["status"] == "failed"]
    print("runs", [r["status"] for r in results], "failed steps", len(failed), "writer", out.strip(), err.strip()[:200])
    assert all(r["status"] == "done" for r in results) and not failed
    assert writer.returncode == 0 and "locked" not in err


def main():
    assert db_path() == TEST_DB
    with TestClient(app) as client:
        test, new_line, _child = part1_versions(client)
        run_id = part2_run_with_test(client, test, new_line)
        part3_delete(client, test, run_id)
        part4_queue(client)
        part6_sqlite(client)
    part5_restart()
    print("B CHECKS DONE")


if __name__ == "__main__":
    main()
