# -*- coding: utf-8 -*-
"""全流程步骤 D 验证（假模型）。在 back_mic/backend 下执行：

    python -m panai4.verify_step_d

写入 logs/sc_fullflow_stepD.log；使用 data/panai4/panai4_stepD_test.db。
"""
from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

LOG = _REPO / "logs" / "sc_fullflow_stepD.log"
lines: list[str] = []


def log(msg: str = "") -> None:
    print(msg)
    lines.append(msg)


def flush() -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")


def setup_env(db_name: str = "panai4_stepD_test.db") -> None:
    os.environ["PANAI4_FAKE_LLM"] = "1"
    os.environ["PANAI4_FAKE_DELAY"] = "0"
    os.environ["PANAI4_DB_PATH"] = str(_BACKEND / "data" / "panai4" / db_name)
    from panai4 import db

    db.reset_connection_for_tests()
    db.init_db()


def poll(client, run_id, *, want=("done", "failed", "interrupted", "cancelled", "awaiting_confirm"), timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/panai4/runs/{run_id}/progress").json()
        if body["status"] in want:
            return body
        time.sleep(0.05)
    raise RuntimeError(f"poll timeout {run_id}")


def poll_done(client, run_id, timeout=90):
    return poll(client, run_id, want=("done", "failed", "interrupted", "cancelled"), timeout=timeout)


def terms_from_item(item: dict) -> list[dict]:
    gate = next(s for s in item["steps"] if s["step"] == "await_confirm")
    meta = gate.get("meta_json") or {}
    if isinstance(meta, str):
        meta = json.loads(meta)
    cands = meta.get("candidates") or meta.get("items") or []
    return [{"name": r["name"], "tier": r["tier"], "reason": r.get("reason") or ""} for r in cands]


def section1_single_pause() -> tuple[bool, int | None]:
    log("=== 1. 未勾跳过、单篇：停待确认，确认后续跑 ===")
    setup_env()
    from fastapi.testclient import TestClient

    from main import app
    from user.token import test_token

    app.dependency_overrides[test_token] = lambda: {"username": "stepD", "role": "t0"}
    ok = True
    run_id = None
    with TestClient(app) as client:
        created = client.post(
            "/api/panai4/runs",
            json={
                "created_by": "stepD",
                "batch_mode": False,
                "main_scope": "skeleton",
                "analysis_scope": "none",
                "items": [{"title": f"单篇待确认{uuid.uuid4().hex[:4]}"}],
            },
        )
        log(f"create status={created.status_code} batch_mode=false")
        if created.status_code >= 400:
            log(f"FAIL create: {created.text}")
            return False, None
        run_id = created.json()["run_id"]
        body = poll(client, run_id)
        log(f"run status={body['status']} awaiting={body.get('awaiting_confirm_count')}")
        if body["status"] != "awaiting_confirm":
            ok = False
        item = body["items"][0]
        steps = {s["step"]: s for s in item["steps"]}
        if steps["select"]["status"] != "done" or steps["await_confirm"]["status"] != "awaiting_confirm":
            ok = False
            log(f"FAIL select/await statuses {steps['select']['status']} {steps['await_confirm']['status']}")
        if steps["term_defs"]["status"] != "pending" or steps["burden"]["status"] != "pending":
            ok = False
            log("FAIL downstream should still be pending before confirm")
        terms = terms_from_item(item)
        conf = client.post(
            f"/api/panai4/runs/{run_id}/items/1/confirm",
            json={"terms": terms},
        )
        log(f"confirm status={conf.status_code}")
        if conf.status_code != 200:
            ok = False
            log(f"FAIL confirm {conf.text}")
            return ok, run_id
        body2 = poll_done(client, run_id)
        log(f"after confirm run={body2['status']} item={body2['items'][0]['status']}")
        s2 = {s["step"]: s for s in body2["items"][0]["steps"]}
        for name in ("await_confirm", "term_defs", "burden", "skeleton"):
            if s2[name]["status"] != "done":
                ok = False
                log(f"FAIL {name}={s2[name]['status']}")
        if body2["status"] != "done":
            ok = False
    log(f"section1 -> {'PASS' if ok else 'FAIL'}")
    log("")
    return ok, run_id


def section2_edit_terms(run_id: int | None) -> bool:
    log("=== 2. 确认前删一个、加一个 ===")
    setup_env("panai4_stepD_edit.db")
    from fastapi.testclient import TestClient

    from main import app
    from panai4.sc.data import load_sc_data
    from user.token import test_token

    app.dependency_overrides[test_token] = lambda: {"username": "stepD", "role": "t0"}
    ok = True
    data = load_sc_data()
    extra = next(n for n in data.tier_of if data.tier_of[n] == "内在")
    with TestClient(app) as client:
        created = client.post(
            "/api/panai4/runs",
            json={
                "created_by": "stepD",
                "batch_mode": False,
                "main_scope": "skeleton",
                "analysis_scope": "none",
                "items": [{"title": f"改词表{uuid.uuid4().hex[:4]}"}],
            },
        )
        run_id = created.json()["run_id"]
        body = poll(client, run_id)
        terms = terms_from_item(body["items"][0])
        removed = terms[0]["name"]
        kept = terms[1:]
        kept.append({"name": extra, "tier": data.tier_of[extra], "reason": "手工加入"})
        conf = client.post(
            f"/api/panai4/runs/{run_id}/items/1/confirm",
            json={"terms": kept},
        )
        log(f"confirm edited status={conf.status_code} removed={removed} added={extra}")
        if conf.status_code != 200:
            log(f"FAIL {conf.text}")
            return False
        body2 = poll_done(client, run_id)
        detail = client.get(f"/api/panai4/runs/{run_id}").json()
        final = json.loads(detail["items"][0]["final_terms_json"] or "[]")
        names = [r["name"] for r in final]
        log(f"final_terms={names}")
        if removed in names or extra not in names:
            ok = False
            log("FAIL final_terms mismatch")
        # term_defs 输出应反映新词表
        td = next(s for s in detail["items"][0]["steps"] if s["step"] == "term_defs")
        if extra not in (td.get("output_text") or "") and data.tier_of[extra] != "外在":
            # 外在只列名；内在应出现在定义块
            ok = False
            log("FAIL term_defs missing added term")
        if body2["status"] != "done":
            ok = False
    log(f"section2 -> {'PASS' if ok else 'FAIL'}")
    log("")
    return ok


def section3_unknown() -> bool:
    log("=== 3. 提交不存在的词条名 ===")
    setup_env("panai4_stepD_unknown.db")
    from fastapi.testclient import TestClient

    from main import app
    from user.token import test_token

    app.dependency_overrides[test_token] = lambda: {"username": "stepD", "role": "t0"}
    ok = True
    with TestClient(app) as client:
        created = client.post(
            "/api/panai4/runs",
            json={
                "created_by": "stepD",
                "batch_mode": False,
                "main_scope": "burden",
                "analysis_scope": "none",
                "items": [{"title": f"未知词{uuid.uuid4().hex[:4]}"}],
            },
        )
        run_id = created.json()["run_id"]
        body = poll(client, run_id)
        terms = terms_from_item(body["items"][0])
        terms.append({"name": "绝对不存在的词条XYZ123", "tier": "外在", "reason": ""})
        conf = client.post(
            f"/api/panai4/runs/{run_id}/items/1/confirm",
            json={"terms": terms},
        )
        log(f"confirm unknown status={conf.status_code} detail={conf.json()}")
        if conf.status_code != 400:
            ok = False
        detail = conf.json().get("detail") or {}
        names = detail.get("unknown_names") if isinstance(detail, dict) else None
        if not names or "绝对不存在的词条XYZ123" not in names:
            ok = False
            log("FAIL unknown list missing")
        # 仍待确认
        body2 = client.get(f"/api/panai4/runs/{run_id}").json()
        if body2["status"] != "awaiting_confirm":
            ok = False
            log(f"FAIL status became {body2['status']}")
    log(f"section3 -> {'PASS' if ok else 'FAIL'}")
    log("")
    return ok


def section4_batch_skip() -> bool:
    log("=== 4. 勾选跳过：一路跑完 ===")
    setup_env("panai4_stepD_batch.db")
    from fastapi.testclient import TestClient

    from main import app
    from user.token import test_token

    app.dependency_overrides[test_token] = lambda: {"username": "stepD", "role": "t0"}
    ok = True
    with TestClient(app) as client:
        created = client.post(
            "/api/panai4/runs",
            json={
                "created_by": "stepD",
                "batch_mode": True,
                "main_scope": "skeleton",
                "analysis_scope": "none",
                "items": [{"title": f"批量{uuid.uuid4().hex[:4]}"}],
            },
        )
        run_id = created.json()["run_id"]
        body = poll_done(client, run_id)
        log(f"batch run status={body['status']} batch={body.get('batch_mode')}")
        if body["status"] != "done" or body.get("awaiting_confirm_count"):
            ok = False
        steps = {s["step"]: s for s in body["items"][0]["steps"]}
        if steps["await_confirm"]["status"] != "done":
            ok = False
        if "批量模式：自动确认" not in (steps["await_confirm"].get("output_text") or ""):
            ok = False
            log(f"FAIL await text={steps['await_confirm'].get('output_text')}")
    log(f"section4 -> {'PASS' if ok else 'FAIL'}")
    log("")
    return ok


def section5_three_articles() -> bool:
    log("=== 5. 未勾跳过、3 篇：全停；确认 1 篇 ===")
    setup_env("panai4_stepD_three.db")
    from fastapi.testclient import TestClient

    from main import app
    from user.token import test_token

    app.dependency_overrides[test_token] = lambda: {"username": "stepD", "role": "t0"}
    ok = True
    with TestClient(app) as client:
        created = client.post(
            "/api/panai4/runs",
            json={
                "created_by": "stepD",
                "batch_mode": False,
                "main_scope": "skeleton",
                "analysis_scope": "none",
                "items": [
                    {"title": f"A{uuid.uuid4().hex[:3]}"},
                    {"title": f"B{uuid.uuid4().hex[:3]}"},
                    {"title": f"C{uuid.uuid4().hex[:3]}"},
                ],
            },
        )
        run_id = created.json()["run_id"]
        body = poll(client, run_id)
        log(f"run={body['status']} awaiting={body.get('awaiting_confirm_count')}")
        if body["status"] != "awaiting_confirm" or body.get("awaiting_confirm_count") != 3:
            ok = False
        for item in body["items"]:
            if item["status"] != "awaiting_confirm":
                ok = False
                log(f"FAIL item {item['position']} status={item['status']}")
        # 只确认第 2 篇
        terms = terms_from_item(body["items"][1])
        conf = client.post(
            f"/api/panai4/runs/{run_id}/items/2/confirm",
            json={"terms": terms},
        )
        log(f"confirm pos2 status={conf.status_code}")
        # 等第 2 篇完成，整次仍 awaiting
        deadline = time.time() + 60
        while time.time() < deadline:
            body2 = client.get(f"/api/panai4/runs/{run_id}/progress").json()
            item2 = next(i for i in body2["items"] if i["position"] == 2)
            if item2["status"] == "done" and body2["status"] == "awaiting_confirm":
                break
            time.sleep(0.1)
        else:
            ok = False
            log("FAIL timeout waiting item2 done")
            body2 = client.get(f"/api/panai4/runs/{run_id}").json()
        statuses = {i["position"]: i["status"] for i in body2["items"]}
        log(f"statuses={statuses} run={body2['status']} awaiting={body2.get('awaiting_confirm_count')}")
        if statuses.get(2) != "done" or statuses.get(1) != "awaiting_confirm" or statuses.get(3) != "awaiting_confirm":
            ok = False
        if body2["status"] != "awaiting_confirm" or body2.get("awaiting_confirm_count") != 2:
            ok = False
    log(f"section5 -> {'PASS' if ok else 'FAIL'}")
    log("")
    return ok


def section6_rerun_burden() -> bool:
    log("=== 6. 从负担说明重跑：不重选词、不要求确认 ===")
    setup_env("panai4_stepD_rerun.db")
    from fastapi.testclient import TestClient

    from main import app
    from panai4 import llm
    from user.token import test_token

    app.dependency_overrides[test_token] = lambda: {"username": "stepD", "role": "t0"}
    ok = True
    with TestClient(app) as client:
        created = client.post(
            "/api/panai4/runs",
            json={
                "created_by": "stepD",
                "batch_mode": True,
                "main_scope": "skeleton",
                "analysis_scope": "none",
                "items": [{"title": f"重跑负担{uuid.uuid4().hex[:4]}"}],
            },
        )
        run_id = created.json()["run_id"]
        poll_done(client, run_id)
        parent = client.get(f"/api/panai4/runs/{run_id}").json()
        final0 = parent["items"][0].get("final_terms_json")
        llm.call_log.clear()
        rr = client.post(
            f"/api/panai4/runs/{run_id}/rerun",
            json={"start_step": "burden", "created_by": "stepD", "main_scope": "skeleton", "analysis_scope": "none"},
        )
        log(f"rerun status={rr.status_code}")
        new_id = rr.json()["run_id"]
        body = poll_done(client, new_id)
        select_calls = [c for c in llm.call_log if c.get("step") == "select"]
        log(f"select LLM calls={len(select_calls)} (expect 0) status={body['status']}")
        if select_calls:
            ok = False
        detail = client.get(f"/api/panai4/runs/{new_id}").json()
        if detail["items"][0].get("final_terms_json") != final0:
            ok = False
            log("FAIL final_terms changed")
        steps = {s["step"]: s for s in detail["items"][0]["steps"]}
        if steps["select"]["status"] != "done" or steps["await_confirm"]["status"] != "done":
            ok = False
        if steps["select"].get("reused_from") is None:
            ok = False
            log("FAIL select not reused")
        if body["status"] != "done":
            ok = False
    log(f"section6 -> {'PASS' if ok else 'FAIL'}")
    log("")
    return ok


def section7_legacy_and_concurrency() -> bool:
    log("=== 7. 旧运行只读 + verify_versions 并发/取消 ===")
    ok = True
    # legacy：沿用正式库一条
    setup_env()
    from fastapi.testclient import TestClient

    from main import app
    from panai4 import db
    from user.token import test_token

    app.dependency_overrides[test_token] = lambda: {"username": "stepD", "role": "t0"}
    os.environ["PANAI4_DB_PATH"] = str(_BACKEND / "data" / "panai4" / "panai4.db")
    db.reset_connection_for_tests()
    db.init_db()
    with TestClient(app) as client:
        legacy_id = None
        for row in client.get("/api/panai4/runs").json().get("runs") or []:
            d = client.get(f"/api/panai4/runs/{row['id']}").json()
            if d.get("flow_kind") == "legacy":
                legacy_id = d["run_id"]
                break
        if legacy_id is None:
            log("WARN no legacy run; skip legacy open/export")
        else:
            d = client.get(f"/api/panai4/runs/{legacy_id}").json()
            log(f"legacy #{legacy_id} status={d['status']}")
            bur = next((s for s in d["items"][0]["steps"] if s["step"] == "burden" and s["status"] == "done"), None)
            if bur:
                exp = client.get(f"/api/panai4/runs/{legacy_id}/items/1/steps/burden/docx")
                log(f"legacy export={exp.status_code} bytes={len(exp.content)}")
                if exp.status_code != 200:
                    ok = False

    # 并发/取消：跑 verify_versions 的 part4 太重；改跑精简并发
    setup_env("panai4_stepD_conc.db")
    os.environ["PANAI4_FAKE_DELAY"] = "0.8"
    db.reset_connection_for_tests()
    db.init_db()
    with TestClient(app) as client:
        ids = []
        for n in range(4):
            r = client.post(
                "/api/panai4/runs",
                json={
                    "created_by": "stepD",
                    "batch_mode": True,
                    "note": f"conc{n}",
                    "items": [{"title": f"并发{n}"}],
                    "main_scope": "burden",
                    "analysis_scope": "none",
                },
            )
            ids.append(r.json()["run_id"])
        states = [client.get(f"/api/panai4/runs/{rid}/progress").json()["status"] for rid in ids]
        log(f"concurrent states={dict(zip(ids, states))}")
        if states.count("running") != 3 or states.count("queued") != 1:
            ok = False
            log("FAIL expected 3 running + 1 queued")
        # 取消排队
        fifth = client.post(
            "/api/panai4/runs",
            json={"created_by": "stepD", "batch_mode": True, "items": [{"title": "第五"}], "main_scope": "burden", "analysis_scope": "none"},
        ).json()
        cancel_q = client.post(f"/api/panai4/runs/{fifth['run_id']}/cancel")
        log(f"cancel queued={cancel_q.status_code}")
        if client.get(f"/api/panai4/runs/{fifth['run_id']}").json()["status"] != "cancelled":
            ok = False
        for rid in ids:
            poll_done(client, rid, timeout=30)
    os.environ["PANAI4_FAKE_DELAY"] = "0"
    log(f"section7 -> {'PASS' if ok else 'FAIL'}")
    log("")
    return ok


def section_restart_and_double() -> bool:
    log("=== 重启恢复 + 双重点击确认 ===")
    setup_env("panai4_stepD_restart.db")
    from fastapi.testclient import TestClient

    from main import app
    from panai4 import db
    from user.token import test_token

    app.dependency_overrides[test_token] = lambda: {"username": "stepD", "role": "t0"}
    ok = True
    with TestClient(app) as client:
        created = client.post(
            "/api/panai4/runs",
            json={
                "created_by": "stepD",
                "batch_mode": False,
                "main_scope": "skeleton",
                "analysis_scope": "none",
                "items": [{"title": f"重启{uuid.uuid4().hex[:4]}"}],
            },
        )
        run_id = created.json()["run_id"]
        body = poll(client, run_id)
        if body["status"] != "awaiting_confirm":
            log(f"FAIL before restart status={body['status']}")
            return False
        # 模拟服务重启清理
        marked = db.mark_running_interrupted()
        log(f"mark_running_interrupted -> {marked}")
        after = client.get(f"/api/panai4/runs/{run_id}").json()
        log(f"after restart status={after['status']} item={after['items'][0]['status']}")
        if after["status"] != "awaiting_confirm" or after["items"][0]["status"] != "awaiting_confirm":
            ok = False
            log("FAIL awaiting_confirm was damaged by interrupt")
        terms = terms_from_item(after["items"][0])
        c1 = client.post(f"/api/panai4/runs/{run_id}/items/1/confirm", json={"terms": terms})
        c2 = client.post(f"/api/panai4/runs/{run_id}/items/1/confirm", json={"terms": terms})
        log(f"double confirm {c1.status_code} then {c2.status_code}")
        if c1.status_code != 200 or c2.status_code != 400:
            ok = False
        poll_done(client, run_id)

        # 取消后不能确认
        created2 = client.post(
            "/api/panai4/runs",
            json={
                "created_by": "stepD",
                "batch_mode": False,
                "main_scope": "burden",
                "analysis_scope": "none",
                "items": [{"title": f"取消后{uuid.uuid4().hex[:4]}"}],
            },
        )
        rid2 = created2.json()["run_id"]
        body2 = poll(client, rid2)
        terms2 = terms_from_item(body2["items"][0])
        cancel = client.post(f"/api/panai4/runs/{rid2}/cancel")
        conf = client.post(f"/api/panai4/runs/{rid2}/items/1/confirm", json={"terms": terms2})
        log(f"cancel={cancel.status_code} then confirm={conf.status_code} detail={conf.json()}")
        if conf.status_code != 400:
            ok = False
    log(f"restart/double/cancel -> {'PASS' if ok else 'FAIL'}")
    log("")
    return ok


def main() -> int:
    log("=== Step D verification ===")
    log("")
    ok = True
    ok1, _ = section1_single_pause()
    ok = ok1 and ok
    ok = section2_edit_terms(None) and ok
    ok = section3_unknown() and ok
    ok = section4_batch_skip() and ok
    ok = section5_three_articles() and ok
    ok = section6_rerun_burden() and ok
    ok = section7_legacy_and_concurrency() and ok
    ok = section_restart_and_double() and ok
    log(f"=== OVERALL: {'PASS' if ok else 'FAIL'} ===")
    flush()
    print(f"wrote {LOG}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
