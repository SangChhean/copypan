# -*- coding: utf-8 -*-
"""全流程步骤 C 验证。假模型为主；真跑需 CLAUDE_API_KEY。

用法（back_mic/backend）:
    python -m panai4.verify_step_c
    python -m panai4.verify_step_c --real
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import time
import uuid
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

LOG = _REPO / "logs" / "sc_fullflow_stepC.log"
lines: list[str] = []


def log(msg: str = "") -> None:
    print(msg)
    lines.append(msg)


def flush() -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")


def h16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def poll(client, run_id, timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/panai4/runs/{run_id}/progress").json()
        if body["status"] in {"done", "failed", "interrupted", "cancelled"}:
            return body
        time.sleep(0.05)
    raise RuntimeError(f"poll timeout {run_id}")


def setup_env(db_name: str = "panai4_stepC_test.db") -> None:
    os.environ["PANAI4_FAKE_LLM"] = "1"
    os.environ["PANAI4_FAKE_DELAY"] = "0"
    os.environ["PANAI4_DB_PATH"] = str(_BACKEND / "data" / "panai4" / db_name)
    from panai4 import db

    db.reset_connection_for_tests()
    db.init_db()


def section1_fake_full() -> tuple[bool, int | None]:
    log("=== 1. FAKE full run (2 articles) ===")
    setup_env()
    from fastapi.testclient import TestClient

    from main import app
    from panai4 import db
    from panai4 import llm
    from panai4.prompts import load_template
    from panai4.sc.data import fill_ref_prompt, fill_select_prompt, load_sc_data
    from panai4.sc.export_sc import extract_burden_export
    from user.token import test_token

    app.dependency_overrides[test_token] = lambda: {"username": "stepC", "role": "t0"}
    llm.call_log.clear()
    ok = True
    run_id = None
    with TestClient(app) as client:
        created = client.post(
            "/api/panai4/runs",
            json={
                "created_by": "stepC",
                "note": "stepC fake full",
                "main_scope": "skeleton",
                "analysis_scope": "diagnosis",
                "batch_mode": True,
                "items": [
                    {
                        "title": f"带纲目篇{uuid.uuid4().hex[:4]}",
                        "original_outline": "壹 原纲目第一条。贰 第二条。",
                    },
                    {"title": f"无纲目篇{uuid.uuid4().hex[:4]}"},
                ],
            },
        )
        log(f"create status={created.status_code}")
        if created.status_code >= 400:
            log(f"FAIL create: {created.text}")
            return False, None
        run_id = created.json()["run_id"]
        body = poll(client, run_id)
        log(f"run status={body['status']} flow={body.get('flow_kind')} batch={body.get('batch_mode')}")
        if body["status"] != "done":
            ok = False

        detail = client.get(f"/api/panai4/runs/{run_id}").json()
        data = load_sc_data()
        for item in detail["items"]:
            steps = {s["step"]: s for s in item["steps"]}
            order = [s["step"] for s in item["steps"] if s["status"] != "skipped" or s["step"] in (
                "select", "await_confirm", "term_defs", "burden", "skeleton", "orig_skeleton", "diagnosis"
            )]
            log(f"--- item {item['position']} {item['title'][:20]} ---")
            for name in ("select", "await_confirm", "term_defs", "burden", "skeleton"):
                st = steps.get(name)
                log(f"  {name}: status={st and st['status']} meta={bool(st and st.get('meta_json'))}")
                if not st or st["status"] != "done":
                    ok = False
            if not item.get("final_terms_json"):
                ok = False
                log("  FAIL missing final_terms_json")
            else:
                terms = json.loads(item["final_terms_json"])
                log(f"  final_terms n={len(terms)}")

            # prompt hashes
            sel = steps["select"]
            exp_sel = fill_select_prompt(load_template("select"), item["title"], data)
            match_sel = (sel.get("prompt_text") or "") == exp_sel
            log(f"  select prompt hash={h16(sel.get('prompt_text') or '')} expected={h16(exp_sel)} match={match_sel}")
            ok = ok and match_sel

            bur = steps["burden"]
            term_text = steps["term_defs"]["output_text"] or ""
            exp_bur = fill_ref_prompt(load_template("burden"), item["title"], term_text, data)
            match_bur = (bur.get("prompt_text") or "") == exp_bur
            log(f"  burden prompt hash={h16(bur.get('prompt_text') or '')} expected={h16(exp_bur)} match={match_bur}")
            ok = ok and match_bur

            sk = steps["skeleton"]
            body_b, _ = extract_burden_export(bur["output_text"] or "")
            has_ref = "【用到的参考材料】" in body_b
            log(f"  skeleton {{burden}} has 用到的参考材料={has_ref} (expect False) chars={len(body_b)}")
            if has_ref:
                ok = False
            from panai4.prompts import render_user

            exp_sk = render_user("skeleton", topic=item["title"], burden=body_b)
            match_sk = (sk.get("prompt_text") or "") == exp_sk
            log(f"  skeleton prompt hash={h16(sk.get('prompt_text') or '')} expected={h16(exp_sk)} match={match_sk}")
            ok = ok and match_sk

            if item.get("original_outline"):
                os_ = steps.get("orig_skeleton")
                dia = steps.get("diagnosis")
                log(f"  orig={os_ and os_['status']} diagnosis={dia and dia['status']}")
                if not os_ or os_["status"] != "done" or not dia or dia["status"] != "done":
                    ok = False
            else:
                os_ = steps.get("orig_skeleton")
                log(f"  orig skipped? {os_ and os_['status']} output={os_ and (os_.get('output_text') or '')[:20]}")

    log(f"section1 -> {'PASS' if ok else 'FAIL'}")
    log("")
    return ok, run_id


def section2_rerun(run_id: int) -> bool:
    log("=== 2. Rerun from burden / select ===")
    setup_env()  # same db
    from fastapi.testclient import TestClient

    from main import app
    from panai4 import llm
    from user.token import test_token

    app.dependency_overrides[test_token] = lambda: {"username": "stepC", "role": "t0"}
    ok = True
    with TestClient(app) as client:
        parent = client.get(f"/api/panai4/runs/{run_id}").json()
        terms0 = parent["items"][0].get("final_terms_json")
        llm.call_log.clear()
        r = client.post(
            f"/api/panai4/runs/{run_id}/rerun",
            json={"start_step": "burden", "created_by": "stepC", "main_scope": "skeleton", "analysis_scope": "none"},
        )
        log(f"rerun from burden status={r.status_code}")
        if r.status_code >= 400:
            log(f"FAIL: {r.text}")
            return False
        new_id = r.json()["run_id"]
        body = poll(client, new_id)
        log(f"  new run {new_id} status={body['status']}")
        select_calls = [c for c in llm.call_log if c.get("step") == "select"]
        log(f"  select LLM calls={len(select_calls)} (expect 0)")
        if select_calls:
            ok = False
        d = client.get(f"/api/panai4/runs/{new_id}").json()
        terms1 = d["items"][0].get("final_terms_json")
        same = terms0 == terms1
        log(f"  final_terms same={same}")
        ok = ok and same and body["status"] == "done"

        llm.call_log.clear()
        r2 = client.post(
            f"/api/panai4/runs/{run_id}/rerun",
            json={"start_step": "select", "created_by": "stepC", "main_scope": "skeleton", "analysis_scope": "none"},
        )
        log(f"rerun from select status={r2.status_code}")
        new2 = r2.json()["run_id"]
        body2 = poll(client, new2)
        select_calls2 = [c for c in llm.call_log if c.get("step") == "select"]
        log(f"  select LLM calls={len(select_calls2)} (expect >=1) status={body2['status']}")
        if len(select_calls2) < 1 or body2["status"] != "done":
            ok = False
    log(f"section2 -> {'PASS' if ok else 'FAIL'}")
    log("")
    return ok


def section3_legacy_and_batch() -> bool:
    log("=== 3. Legacy readonly + batch_mode=false ===")
    setup_env("panai4_test.db")  # may have old runs; also official
    from fastapi.testclient import TestClient

    from main import app
    from panai4 import db
    from user.token import test_token

    app.dependency_overrides[test_token] = lambda: {"username": "stepC", "role": "t0"}
    ok = True
    with TestClient(app) as client:
        # batch false 现已允许（步骤 D）
        ok_batch = client.post(
            "/api/panai4/runs",
            json={
                "created_by": "stepC",
                "batch_mode": False,
                "items": [{"title": "x"}],
                "main_scope": "burden",
                "analysis_scope": "none",
            },
        )
        log(f"batch_mode=false -> {ok_batch.status_code} (stepD allows)")
        if ok_batch.status_code != 202:
            ok = False
        else:
            # 取消掉，避免占库
            client.post(f"/api/panai4/runs/{ok_batch.json()['run_id']}/cancel")

        # find a legacy run on official db
        os.environ["PANAI4_DB_PATH"] = str(_BACKEND / "data" / "panai4" / "panai4.db")
        db.reset_connection_for_tests()
        db.init_db()
        legacy = None
        for row in db.list_runs(50):
            if (row.get("flow_kind") or "legacy") == "legacy":
                legacy = row
                break
        if legacy is None:
            log("WARN: no legacy run on official db; skip legacy checks")
        else:
            # need app with official db - recreate client after env change
            pass
    # reopen client with official
    os.environ["PANAI4_DB_PATH"] = str(_BACKEND / "data" / "panai4" / "panai4.db")
    db.reset_connection_for_tests()
    from fastapi.testclient import TestClient
    from main import app

    app.dependency_overrides[test_token] = lambda: {"username": "stepC", "role": "t0"}
    with TestClient(app) as client:
        runs = client.get("/api/panai4/runs").json().get("runs") or []
        legacy_id = None
        for r in runs:
            # list may not include flow_kind; fetch detail
            d = client.get(f"/api/panai4/runs/{r['id']}").json()
            if d.get("flow_kind") == "legacy":
                legacy_id = d["run_id"]
                break
        if legacy_id is None:
            log("WARN no legacy in list")
        else:
            d = client.get(f"/api/panai4/runs/{legacy_id}").json()
            log(f"legacy detail #{legacy_id} status={d['status']} items={len(d['items'])}")
            item = d["items"][0]
            pos = item["position"]
            step = next((s for s in item["steps"] if s["step"] == "burden" and s["status"] == "done"), None)
            if step:
                exp = client.get(f"/api/panai4/runs/{legacy_id}/items/{pos}/steps/burden/docx")
                log(f"legacy export status={exp.status_code} bytes={len(exp.content)}")
                if exp.status_code != 200:
                    ok = False
            rr = client.post(
                f"/api/panai4/runs/{legacy_id}/rerun",
                json={"start_step": "burden", "created_by": "stepC"},
            )
            log(f"legacy rerun -> {rr.status_code} {rr.json()}")
            if rr.status_code != 400 or "旧流程" not in str(rr.json().get("detail")):
                ok = False
    log(f"section3 -> {'PASS' if ok else 'FAIL'}")
    log("")
    return ok


def section4_prompt_tests() -> bool:
    log("=== 4. Prompt tests for select/burden/skeleton ===")
    setup_env()
    from fastapi.testclient import TestClient

    from main import app
    from panai4.prompts import load_template
    from user.token import test_token

    app.dependency_overrides[test_token] = lambda: {"username": "stepC", "role": "t0"}
    ok = True
    ids = {}
    with TestClient(app) as client:
        for step in ("select", "burden", "skeleton"):
            tpl = load_template(step)
            bad = client.post(
                "/api/panai4/prompt_tests",
                json={
                    "step": step,
                    "template": tpl.replace("{query}", "GONE", 1),
                    "parent_kind": "current",
                    "change_note": "missing ph",
                    "created_by": "stepC",
                },
            )
            log(f"  {step} missing ph -> {bad.status_code}")
            if bad.status_code not in (400, 422):
                ok = False
            good = client.post(
                "/api/panai4/prompt_tests",
                json={
                    "step": step,
                    "template": tpl,
                    "parent_kind": "current",
                    "change_note": f"stepC {step} test",
                    "created_by": "stepC",
                },
            )
            log(f"  {step} create -> {good.status_code}")
            if good.status_code not in (200, 201):
                ok = False
                log(f"    {good.text[:200]}")
            else:
                ids[step] = good.json()["id"]

        created = client.post(
            "/api/panai4/runs",
            json={
                "created_by": "stepC",
                "main_scope": "skeleton",
                "analysis_scope": "none",
                "batch_mode": True,
                "items": [{"title": f"测试版篇{uuid.uuid4().hex[:4]}"}],
                "prompt_tests": ids,
            },
        )
        run_id = created.json()["run_id"]
        body = poll(client, run_id)
        d = client.get(f"/api/panai4/runs/{run_id}").json()
        for step, tid in ids.items():
            st = next(s for s in d["items"][0]["steps"] if s["step"] == step)
            match = st.get("prompt_test_version_id") == tid
            log(f"  run step {step} test_id={st.get('prompt_test_version_id')} expect={tid} ok={match}")
            ok = ok and match and body["status"] == "done"
            client.delete(f"/api/panai4/prompt_tests/{tid}", params={"deleted_by": "stepC"})
    log(f"section4 -> {'PASS' if ok else 'FAIL'}")
    log("")
    return ok


def section5_missing_data() -> bool:
    log("=== 5. Missing term data files ===")
    setup_env()
    from fastapi.testclient import TestClient

    from main import app
    from panai4.sc import data as sc_data
    from user.token import test_token

    app.dependency_overrides[test_token] = lambda: {"username": "stepC", "role": "t0"}
    ok = True
    orig = sc_data.tiers_json_path
    sc_data._cache = None

    def broken():
        return Path("/nonexistent/tiers.json")

    sc_data.tiers_json_path = broken  # type: ignore
    sc_data._cache = None
    try:
        with TestClient(app) as client:
            created = client.post(
                "/api/panai4/runs",
                json={
                    "created_by": "stepC",
                    "main_scope": "burden",
                    "analysis_scope": "none",
                    "items": [{"title": "缺文件篇"}],
                },
            )
            run_id = created.json()["run_id"]
            body = poll(client, run_id)
            d = client.get(f"/api/panai4/runs/{run_id}").json()
            sel = next(s for s in d["items"][0]["steps"] if s["step"] == "select")
            log(f"select status={sel['status']} error={sel.get('error')}")
            if sel["status"] != "failed" or "缺少词条数据文件" not in (sel.get("error") or ""):
                ok = False
            log(f"run finished without crash status={body['status']}")
    finally:
        sc_data.tiers_json_path = orig
        sc_data._cache = None
    log(f"section5 -> {'PASS' if ok else 'FAIL'}")
    log("")
    return ok


def section7_real() -> bool:
    log("=== 7. Real API run ===")
    if not (os.environ.get("CLAUDE_API_KEY") or "").strip():
        log("SKIP: CLAUDE_API_KEY not set")
        log("")
        return True
    os.environ.pop("PANAI4_FAKE_LLM", None)
    os.environ["PANAI4_DB_PATH"] = str(_BACKEND / "data" / "panai4" / "panai4_stepC_real.db")
    from panai4 import db

    db.reset_connection_for_tests()
    db.init_db()
    from fastapi.testclient import TestClient

    from main import app
    from panai4.sc.exp_skel4 import analyze_b4
    from panai4.sc.export_sc import extract_burden_export
    from user.token import test_token

    app.dependency_overrides[test_token] = lambda: {"username": "stepC", "role": "t0"}
    topic = "亚伯拉罕的神见于祂对待亚伯拉罕的事"
    ok = True
    with TestClient(app) as client:
        created = client.post(
            "/api/panai4/runs",
            json={
                "created_by": "stepC",
                "note": "stepC real",
                "main_scope": "skeleton",
                "analysis_scope": "none",
                "items": [{"title": topic}],
            },
        )
        if created.status_code >= 400:
            log(f"FAIL create: {created.text}")
            return False
        run_id = created.json()["run_id"]
        body = poll(client, run_id, timeout=600)
        d = client.get(f"/api/panai4/runs/{run_id}").json()
        item = d["items"][0]
        steps = {s["step"]: s for s in item["steps"]}
        sel_meta = steps["select"].get("meta_json") or {}
        term_meta = steps["term_defs"].get("meta_json") or {}
        bur_out = steps["burden"]["output_text"] or ""
        body_b, _ = extract_burden_export(bur_out)
        sk_out = steps["skeleton"]["output_text"] or ""
        items = [ln.strip() for ln in sk_out.splitlines() if ln.strip()]
        log(f"run status={body['status']}")
        log(f"tier_counts={sel_meta.get('tier_counts')} valid={sel_meta.get('valid_count')}")
        log(f"defs_sent_count={term_meta.get('defs_sent_count')} skipped={term_meta.get('skipped_names')}")
        log(f"burden chars={len(body_b)} skeleton items={len(items)}")
        analysis = analyze_b4(body_b, items)
        log(
            f"B4: boundary_bad={sum(1 for c in analysis['per_item'] if c['boundary_bad'])} "
            f"unchanged={analysis.get('unchanged_n')} residual={sum(len(c['residual']) for c in analysis['per_item'])}"
        )
        costs = []
        total = 0.0
        for name in ("select", "burden", "skeleton"):
            c = steps[name].get("cost_usd") or 0.0
            costs.append((name, round(float(c), 3)))
            total += float(c)
        log(f"costs={costs} total={round(total, 3)}")
        if not (6 <= len(items) <= 9):
            ok = False
            log("FAIL skeleton item count not in 6-9")
        if body["status"] != "done":
            ok = False
    log(f"section7 -> {'PASS' if ok else 'FAIL'}")
    log("")
    return ok


def note_rollback() -> None:
    log("=== CURRENT rollback ===")
    log("回退方法：")
    log("  1. panai4/prompts/prompt1_burden.py 将 CURRENT = \"v1.0\" 改回 \"v0.3\"")
    log("  2. panai4/prompts/prompt2_skeleton.py 将 CURRENT = \"v1.0\" 改回 \"v0.2\"")
    log("  3. panai4/prompts/prompt0_select.py 将 ENABLED = True 改回 False（若需停用选词）")
    log("  4. 重启后端；旧运行仍可读（prompt_text 已落库）")
    log("")


def main() -> int:
    real = "--real" in sys.argv
    log("=== Step C verification ===")
    log("")
    from panai4.prompts import REGISTRY

    log(
        f"CURRENT select={REGISTRY['select'].CURRENT} burden={REGISTRY['burden'].CURRENT} "
        f"skeleton={REGISTRY['skeleton'].CURRENT}"
    )
    log("")
    ok = True
    ok1, run_id = section1_fake_full()
    ok = ok1 and ok
    if run_id:
        ok = section2_rerun(run_id) and ok
    else:
        log("SKIP section2 (no run)")
    ok = section3_legacy_and_batch() and ok
    ok = section4_prompt_tests() and ok
    ok = section5_missing_data() and ok
    if real:
        ok = section7_real() and ok
    else:
        log("=== 7. Real API run ===")
        log("SKIP (pass --real and set CLAUDE_API_KEY)")
        log("")
    note_rollback()
    log(f"=== OVERALL: {'PASS' if ok else 'FAIL'} ===")
    flush()
    print(f"wrote {LOG}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
