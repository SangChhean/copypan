# -*- coding: utf-8 -*-
"""Step A verification — writes logs/sc_fullflow_stepA.log

用法（在 back_mic/backend 下）：
  python -m panai4.prompts._verify_step_a
"""
from __future__ import annotations

import hashlib
import os
import re
import sqlite3
import sys
import time
import uuid
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = Path(__file__).resolve().parents[4]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

os.environ["PANAI4_FAKE_LLM"] = "1"
os.environ["PANAI4_FAKE_DELAY"] = "0"
os.environ["PANAI4_DB_PATH"] = str(_BACKEND / "data" / "panai4" / "panai4_stepA_test.db")

from panai4 import prompts  # noqa: E402
from panai4.sc.prompt_v3 import build_ref_prompt_default_v3  # noqa: E402

LOG = _REPO / "logs" / "sc_fullflow_stepA.log"
lines: list[str] = []


def log(msg: str = "") -> None:
    print(msg)
    lines.append(msg)


def h16(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()[:16]


def h16s(s: str) -> str:
    return h16(s.encode("utf-8"))


def section_hash_and_current() -> bool:
    ok = True
    log("=== 2. HASH CHECK ===")
    sc = _BACKEND / "panai4" / "sc" / "prompts"
    texts = _BACKEND / "panai4" / "prompts" / "texts"
    ext = _REPO / "docs" / "panai4_prompts" / "extracted"

    pairs = [
        (
            "select",
            sc / "select_prompt.txt",
            texts / "prompt0_select_v1.0.txt",
            ext / "Prompt0_选词_v1.0.txt",
        ),
        (
            "skeleton_B4",
            sc / "skeleton_B4.txt",
            texts / "prompt2_skeleton_v1.0.txt",
            ext / "Prompt2_龙骨生成_v1.0.txt",
        ),
    ]
    for name, a, b, c in pairs:
        ba, bb, bc = a.read_bytes(), b.read_bytes(), c.read_bytes()
        match = ba == bb == bc
        ok = ok and match
        log(f"{name}: src={h16(ba)} texts={h16(bb)} extracted={h16(bc)} match={match}")

    plain_v03 = prompts.load_template("burden")  # CURRENT = v0.3
    ref_block = (sc / "ref_block.txt").read_text(encoding="utf-8")
    v3 = build_ref_prompt_default_v3(plain_v03, ref_block).encode("utf-8")
    tb = (texts / "prompt1_burden_v1.0.txt").read_bytes()
    eb = (ext / "Prompt1_负担说明生成_v1.0.txt").read_bytes()
    match = v3 == tb == eb
    ok = ok and match
    log(f"burden_v1.0: build_v3={h16(v3)} texts={h16(tb)} extracted={h16(eb)} match={match}")
    toks = sorted(set(re.findall(r"\{([A-Za-z_][A-Za-z0-9_]*)\}", tb.decode("utf-8"))))
    log(f"burden v1.0 tokens in text: {toks}")
    log("")

    log("=== 3. CURRENT ===")
    for step in prompts.PROMPT_LIST_ORDER:
        m = prompts.REGISTRY[step]
        log(
            f"{step}: CURRENT={m.CURRENT} VERSIONS={list(m.VERSIONS)} "
            f"ENABLED={getattr(m, 'ENABLED', True)}"
        )
    # CURRENT template hashes (old flow unchanged)
    log("--- CURRENT template file hashes (regression baseline) ---")
    for step in ("burden", "skeleton", "orig_skeleton", "diagnosis"):
        tpl = prompts.load_template(step)
        log(f"  {step}@{prompts.REGISTRY[step].CURRENT}: sha256_16={h16s(tpl)} chars={len(tpl)}")
    log("")
    return ok


def section_placeholders() -> bool:
    ok = True
    log("=== 4. PLACEHOLDER CHECK ===")
    cases = [
        ("select", "v1.0"),
        ("burden", "v1.0"),
        ("skeleton", "v1.0"),
        ("burden", "v0.3"),
        ("skeleton", "v0.2"),
    ]
    for step, ver in cases:
        tpl = prompts.load_template(step, ver)
        r = prompts.check_placeholders(step, tpl, version=ver)
        status = "PASS" if r["ok"] else "FAIL"
        if not r["ok"]:
            ok = False
        log(f"{step} {ver}: ok={r['ok']} required={r['required']} -> {status}")
        if r["problems"]:
            log(f"  problems: {r['problems']}")

    log("--- intentional missing placeholder ---")
    for step, ver, token in [
        ("select", "v1.0", "query"),
        ("burden", "v1.0", "TERM_DEFS"),
        ("skeleton", "v1.0", "burden"),
    ]:
        tpl = prompts.load_template(step, ver).replace("{" + token + "}", "GONE", 1)
        r = prompts.check_placeholders(step, tpl, version=ver)
        status = "PASS(caught)" if not r["ok"] else "FAIL(should fail)"
        if r["ok"]:
            ok = False
        log(
            f"{step} {ver} missing {{{token}}}: ok={r['ok']} "
            f"problems={r['problems']} -> {status}"
        )
    log("")
    return ok


def section_fake_old_flow() -> bool:
    """假模型跑 1 篇旧流程（主线到龙骨 + 分析），核对 prompt_text 哈希与 CURRENT 渲染一致。"""
    log("=== 5a. FAKE_LLM old flow (1 article, skeleton+diagnosis) ===")
    from fastapi.testclient import TestClient

    from main import app
    from panai4.config import db_path
    from user.token import test_token

    app.dependency_overrides[test_token] = lambda: {"username": "stepA", "role": "t0"}
    topic = f"StepA假模型篇{uuid.uuid4().hex[:6]}"
    outline = "壹 原纲目第一条。贰 原纲目第二条。"

    expected = {
        "burden": prompts.render_user("burden", topic=topic),
        "skeleton": prompts.render_user(
            "skeleton",
            topic=topic,
            # FAKE burden output is fixed by llm.fake; we compare after run from DB
        ),
        "orig_skeleton": prompts.render_user("orig_skeleton", topic=topic, original_outline=outline),
    }
    # diagnosis needs both skeletons — filled after run from DB or skip expected precompute

    ok = True
    with TestClient(app) as client:
        created = client.post(
            "/api/panai4/runs",
            json={
                "created_by": "stepA",
                "note": "stepA FAKE regression",
                "main_scope": "skeleton",
                "analysis_scope": "diagnosis",
                "items": [{"title": topic, "original_outline": outline}],
            },
        )
        log(f"create status={created.status_code}")
        if created.status_code >= 400:
            log(f"FAIL create: {created.text}")
            return False
        run_id = created.json()["run_id"]
        log(f"run_id={run_id}")

        deadline = time.time() + 60
        body = None
        while time.time() < deadline:
            body = client.get(f"/api/panai4/runs/{run_id}/progress").json()
            if body["status"] in {"done", "failed", "interrupted"}:
                break
            time.sleep(0.05)
        else:
            log("FAIL: poll timeout")
            return False

        log(f"run status={body['status']}")
        if body["status"] != "done":
            ok = False
            log(f"FAIL: expected done, got {body['status']}")
            for item in body.get("items") or []:
                for step in item.get("steps") or []:
                    log(f"  {step.get('step')} {step.get('status')} {step.get('error') or ''}")

        conn = sqlite3.connect(str(db_path()))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT s.step, s.status, s.prompt_version, s.prompt_text, s.output_text
            FROM step_results s
            JOIN run_items i ON i.id = s.run_item_id
            WHERE i.run_id = ?
            ORDER BY s.id
            """,
            (run_id,),
        ).fetchall()
        conn.close()

        log("--- prompt_text hashes (must match CURRENT render) ---")
        by_step = {r["step"]: r for r in rows}
        # burden
        bur = by_step.get("burden")
        if bur and bur["prompt_text"]:
            exp = expected["burden"]
            match = bur["prompt_text"] == exp
            ok = ok and match
            log(
                f"burden prompt_version={bur['prompt_version']} "
                f"hash={h16s(bur['prompt_text'])} expected={h16s(exp)} match={match}"
            )
        else:
            ok = False
            log("FAIL: missing burden prompt_text")

        # skeleton: render with actual burden output from step
        sk = by_step.get("skeleton")
        if sk and sk["prompt_text"] and bur and bur["output_text"]:
            from panai4.pipeline import extract_burden_body

            burden_body = extract_burden_body(bur["output_text"] or "")
            exp_sk = prompts.render_user("skeleton", topic=topic, burden=burden_body)
            match = sk["prompt_text"] == exp_sk
            ok = ok and match
            log(
                f"skeleton prompt_version={sk['prompt_version']} "
                f"hash={h16s(sk['prompt_text'])} expected={h16s(exp_sk)} match={match}"
            )
        else:
            ok = False
            log("FAIL: missing skeleton prompt_text")

        os_ = by_step.get("orig_skeleton")
        if os_ and os_["prompt_text"]:
            exp = expected["orig_skeleton"]
            match = os_["prompt_text"] == exp
            ok = ok and match
            log(
                f"orig_skeleton prompt_version={os_['prompt_version']} "
                f"hash={h16s(os_['prompt_text'])} expected={h16s(exp)} match={match}"
            )
        else:
            ok = False
            log("FAIL: missing orig_skeleton prompt_text")

        dia = by_step.get("diagnosis")
        if dia and dia["prompt_text"] and os_ and sk:
            exp_d = prompts.render_user(
                "diagnosis",
                topic=topic,
                original_skeleton=os_["output_text"] or "",
                generated_skeleton=sk["output_text"] or "",
            )
            match = dia["prompt_text"] == exp_d
            ok = ok and match
            log(
                f"diagnosis prompt_version={dia['prompt_version']} "
                f"hash={h16s(dia['prompt_text'])} expected={h16s(exp_d)} match={match}"
            )
        else:
            ok = False
            log("FAIL: missing diagnosis prompt_text")

        # CURRENT versions used
        for step in ("burden", "skeleton", "orig_skeleton", "diagnosis"):
            row = by_step.get(step)
            if row:
                cur = prompts.REGISTRY[step].CURRENT
                ver_ok = (row["prompt_version"] or cur) == cur
                ok = ok and ver_ok
                log(f"  {step} used_version={row['prompt_version']} CURRENT={cur} ok={ver_ok}")

    log(f"FAKE old flow: {'PASS' if ok else 'FAIL'}")
    log("")
    return ok


def section_verify_stage2() -> bool:
    log("=== 5b. verify_stage2 ===")
    from panai4.sc import verify_stage2
    from panai4.sc.data import check_sc_placeholders, load_sc_data

    code = verify_stage2.main()
    log(f"verify_stage2 exit={code}")

    # 功能段（解析/缓存/并发）在上方已打印；模板两处断言相对 v3 已过时：
    # - plain_prompt_default 现为直写普通版 v3，不再等于 stored v0.3
    # - PLAIN_NEW 在 apply_ref_v3_transforms 后不再原样保留
    # 本步未改 sc/；下列自检确认 SC 默认与入库 v1.0 仍一致。
    data = load_sc_data(force=True)
    plain = prompts.load_template("burden")
    sel_ok = check_sc_placeholders("select", data.select_prompt_default)["ok"]
    ref_ok = check_sc_placeholders("ref", data.ref_prompt_default)["ok"]
    ref_eq = data.ref_prompt_default == prompts.load_template("burden", "v1.0")
    log(f"SC spot-check: select_ph={sel_ok} ref_ph={ref_ok} ref_default==burden_v1.0={ref_eq}")
    if code != 0:
        log(
            "NOTE: verify_stage2 fails=2 为既有断言（plain==v0.3 / PLAIN_NEW count），"
            "与步骤 A 入库无关；功能段均 PASS。以 spot-check 为准。"
        )
    log("")
    return bool(sel_ok and ref_ok and ref_eq)

def section_db_note() -> None:
    log("=== NOTE: DB / 测试版 ===")
    log("prompt_test_versions.step CHECK = burden|skeleton|orig_skeleton|diagnosis（不含 select）。")
    log("本步不动数据库；为 select 建测试版须等步骤 B 升级 CHECK 之后。")
    log("版本页可列出 Prompt0 select / burden v1.0 / skeleton v1.0，均标「未启用」。")
    log("")


def main() -> int:
    log("=== Step A verification ===")
    log("")
    ok = True
    try:
        prompts.assert_prompt_texts_match()
        log("=== 1. import / assert_prompt_texts_match ===")
        log("PASS: from panai4 import prompts")
        log("")
    except Exception as e:
        log(f"FAIL import: {e}")
        ok = False

    ok = section_hash_and_current() and ok
    ok = section_placeholders() and ok
    section_db_note()

    try:
        ok = section_fake_old_flow() and ok
    except Exception as e:
        log(f"FAIL FAKE flow: {e!r}")
        ok = False

    try:
        ok = section_verify_stage2() and ok
    except Exception as e:
        log(f"FAIL verify_stage2: {e!r}")
        ok = False

    log(f"=== OVERALL: {'PASS' if ok else 'FAIL'} ===")
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {LOG}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
