# -*- coding: utf-8 -*-
"""全流程步骤 E+F 验证（假模型）。

    python -m panai4.verify_step_ef

写入 logs/sc_fullflow_stepEF.log。
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import uuid
import zipfile
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

LOG = _REPO / "logs" / "sc_fullflow_stepEF.log"
lines: list[str] = []


def log(msg: str = "") -> None:
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("utf-8", errors="replace").decode("utf-8", errors="replace"))
    lines.append(msg)


def flush() -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")


def setup_env(name: str = "panai4_stepEF_test.db") -> None:
    os.environ["PANAI4_FAKE_LLM"] = "1"
    os.environ["PANAI4_FAKE_DELAY"] = "0"
    os.environ["PANAI4_DB_PATH"] = str(_BACKEND / "data" / "panai4" / name)
    from panai4 import db

    db.reset_connection_for_tests()
    db.init_db()


def poll(client, run_id, want=("done", "failed", "interrupted", "cancelled", "awaiting_confirm"), timeout=90):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/panai4/runs/{run_id}/progress").json()
        if body["status"] in want:
            return body
        time.sleep(0.05)
    raise RuntimeError(f"timeout {run_id}")


def section_cache() -> bool:
    log("=== 1. 原纲目龙骨缓存键（只查 + FAKE 验证） ===")
    setup_env("panai4_stepEF_cache.db")
    from fastapi.testclient import TestClient

    from main import app
    from panai4 import db, llm
    from panai4.db import outline_hash
    from user.token import test_token

    app.dependency_overrides[test_token] = lambda: {"username": "stepEF", "role": "t0"}
    ok = True
    # 文档化键
    log("缓存主键：orig_skeleton_cache(outline_hash, prompt3_version)")
    log("  - outline_hash：原纲目正文规范化后的 SHA256（非篇题/篇号）")
    log("  - prompt3_version：该步所用 Prompt3 版本号")
    log("  - 不含模型名：同纲目+同版本换模型仍会命中（现状）")

    with TestClient(app) as client:
        outline_a = f"壹 缓存A{uuid.uuid4().hex[:6]}。"
        outline_b = f"壹 缓存B{uuid.uuid4().hex[:6]}。内容不同。"
        title = f"缓存篇{uuid.uuid4().hex[:4]}"
        # 第一跑
        llm.call_log.clear()
        r1 = client.post(
            "/api/panai4/runs",
            json={
                "created_by": "stepEF",
                "batch_mode": True,
                "main_scope": "skeleton",
                "analysis_scope": "diagnosis",
                "items": [{"title": title, "original_outline": outline_a}],
            },
        )
        b1 = poll(client, r1.json()["run_id"], want=("done",))
        orig1 = next(s for s in b1["items"][0]["steps"] if s["step"] == "orig_skeleton")
        calls1 = sum(1 for c in llm.call_log if c.get("step") == "orig_skeleton")
        log(f"run1 orig reused_from={orig1.get('reused_from')} model={orig1.get('model')} calls={calls1}")
        if orig1.get("reused_from") is not None or calls1 != 1:
            ok = False

        # 同题不同纲目 → 不应命中
        llm.call_log.clear()
        r2 = client.post(
            "/api/panai4/runs",
            json={
                "created_by": "stepEF",
                "batch_mode": True,
                "main_scope": "none",
                "analysis_scope": "orig_skeleton",
                "items": [{"title": title, "original_outline": outline_b}],
            },
        )
        b2 = poll(client, r2.json()["run_id"], want=("done",))
        orig2 = next(s for s in b2["items"][0]["steps"] if s["step"] == "orig_skeleton")
        calls2 = sum(1 for c in llm.call_log if c.get("step") == "orig_skeleton")
        log(f"different outline: reused_from={orig2.get('reused_from')} calls={calls2} hashA={outline_hash(outline_a)[:8]} hashB={outline_hash(outline_b)[:8]}")
        if orig2.get("reused_from") is not None or calls2 != 1:
            ok = False
            log("FAIL different outline should miss cache")

        # 同纲目再跑 → 应命中
        llm.call_log.clear()
        r3 = client.post(
            "/api/panai4/runs",
            json={
                "created_by": "stepEF",
                "batch_mode": True,
                "main_scope": "none",
                "analysis_scope": "orig_skeleton",
                "items": [{"title": title, "original_outline": outline_a}],
            },
        )
        b3 = poll(client, r3.json()["run_id"], want=("done",))
        orig3 = next(s for s in b3["items"][0]["steps"] if s["step"] == "orig_skeleton")
        calls3 = sum(1 for c in llm.call_log if c.get("step") == "orig_skeleton")
        log(f"same outline again: reused_from={orig3.get('reused_from')} calls={calls3}")
        if orig3.get("reused_from") is None or calls3 != 0:
            ok = False
            log("FAIL same outline should hit cache")

        # 建 Prompt3 测试版换版本 → 不应命中
        from panai4.prompts import load_template

        base = load_template("orig_skeleton")
        edited = base + "\n【步骤EF测版标记】\n"
        saved = client.post(
            "/api/panai4/prompt_tests",
            json={
                "step": "orig_skeleton",
                "template": edited,
                "change_note": "stepEF cache version",
                "created_by": "stepEF",
            },
        )
        if saved.status_code != 201:
            log(f"FAIL create prompt3 test {saved.text}")
            ok = False
        else:
            tid = saved.json()["id"]
            ver = saved.json()["version_name"]
            llm.call_log.clear()
            r4 = client.post(
                "/api/panai4/runs",
                json={
                    "created_by": "stepEF",
                    "batch_mode": True,
                    "main_scope": "none",
                    "analysis_scope": "orig_skeleton",
                    "prompt_tests": {"orig_skeleton": tid},
                    "items": [{"title": title, "original_outline": outline_a}],
                },
            )
            b4 = poll(client, r4.json()["run_id"], want=("done",))
            orig4 = next(s for s in b4["items"][0]["steps"] if s["step"] == "orig_skeleton")
            calls4 = sum(1 for c in llm.call_log if c.get("step") == "orig_skeleton")
            log(f"prompt3 test {ver}: version={orig4.get('prompt_version')} reused_from={orig4.get('reused_from')} calls={calls4}")
            if orig4.get("reused_from") is not None or calls4 != 1:
                ok = False
                log("FAIL different Prompt3 version should miss cache")
            client.delete(f"/api/panai4/prompt_tests/{tid}?deleted_by=stepEF")

    log(f"section_cache -> {'PASS' if ok else 'FAIL'}")
    log("")
    return ok


def _docx_text(data: bytes) -> str:
    from docx import Document

    doc = Document(io.BytesIO(data))
    return "\n".join(p.text for p in doc.paragraphs)


def section_export() -> bool:
    log("=== 2. 全流程导出 + 旧运行导出 ===")
    setup_env("panai4_stepEF_export.db")
    from fastapi.testclient import TestClient

    from main import app
    from user.token import test_token

    app.dependency_overrides[test_token] = lambda: {"username": "stepEF", "role": "t0"}
    ok = True
    with TestClient(app) as client:
        created = client.post(
            "/api/panai4/runs",
            json={
                "created_by": "stepEF",
                "batch_mode": True,
                "main_scope": "skeleton",
                "analysis_scope": "diagnosis",
                "items": [
                    {
                        "title": f"导出篇{uuid.uuid4().hex[:4]}",
                        "original_outline": "壹 导出用原纲目。贰 第二点。",
                    }
                ],
            },
        )
        run_id = created.json()["run_id"]
        body = poll(client, run_id, want=("done",))
        # 单篇 zip
        z = client.get(f"/api/panai4/runs/{run_id}/items/1/export.zip")
        log(f"article zip status={z.status_code} bytes={len(z.content)}")
        if z.status_code != 200:
            ok = False
        else:
            with zipfile.ZipFile(io.BytesIO(z.content)) as archive:
                names = archive.namelist()
                log(f"zip files={names}")
                combined = next((n for n in names if n.startswith("【全流程】")), None)
                if not combined:
                    ok = False
                    log("FAIL missing combined full-flow docx")
                else:
                    text = _docx_text(archive.read(combined))
                    for mark in ("主题", "选出的词条", "负担说明", "新生成的龙骨", "原纲目的龙骨", "对比诊断"):
                        if mark not in text:
                            ok = False
                            log(f"FAIL missing section {mark}")
                    if "【用到的参考材料】" in text:
                        ok = False
                        log("FAIL materials leaked into combined export")
                    # 简单乱码检查：不应有大量替换符
                    if "\ufffd" in text:
                        ok = False
                        log("FAIL replacement chars in docx")
                    log(f"combined chars={len(text)} ok_sections={ok}")
                if not any("选词" in n or "选出的词条" in n or n.startswith("【选词") for n in names):
                    # select file named 【选词】...
                    if not any("选词" in n for n in names):
                        ok = False
                        log("FAIL missing select docx in zip")
        # 选词单独
        sel = client.get(f"/api/panai4/runs/{run_id}/items/1/steps/select/docx")
        log(f"select docx status={sel.status_code} bytes={len(sel.content)}")
        if sel.status_code != 200:
            ok = False
        else:
            st = _docx_text(sel.content)
            if "选出的词条" not in st and "【最内在】" not in st and "【内在】" not in st:
                ok = False
                log(f"FAIL select docx content unexpected: {st[:120]!r}")
        # 全部导出
        allz = client.get(f"/api/panai4/runs/{run_id}/export.zip")
        log(f"run zip status={allz.status_code} bytes={len(allz.content)}")
        if allz.status_code != 200:
            ok = False

        # 旧运行：同库插入一条 flow_kind=legacy 的完成篇，验证导出路径未改坏
        from panai4 import db

        legacy_id = db.create_run(
            items=[{"position": 1, "title": "旧流程导出篇", "original_outline": "旧纲", "outline_hash": None}],
            note="stepEF legacy export",
            steps=[
                {
                    "position": 1,
                    "step": "burden",
                    "status": "done",
                    "prompt_name": "Prompt1",
                    "prompt_version": "v0.3",
                    "model": "fake",
                    "prompt_text": "legacy burden prompt",
                    "output_text": "【负担说明】\n旧运行负担正文。\n【用到的参考材料】\n材料略。",
                    "input_tokens": 10,
                    "output_tokens": 10,
                    "cost_usd": 0.0,
                    "duration_ms": 1,
                }
            ],
            created_by="stepEF",
            main_scope="burden",
            analysis_scope="none",
            flow_kind="legacy",
            batch_mode=0,
        )
        db.set_run_status(legacy_id, "done")
        db.set_item_status(db.list_items(legacy_id)[0]["id"], "done", None)
        exp = client.get(f"/api/panai4/runs/{legacy_id}/items/1/steps/burden/docx")
        log(f"legacy burden export={exp.status_code} bytes={len(exp.content)}")
        if exp.status_code != 200:
            ok = False
        else:
            lt = _docx_text(exp.content)
            if "旧运行负担正文" not in lt or "\ufffd" in lt:
                ok = False
                log("FAIL legacy burden docx content")
        # 旧运行不应能导出 select
        bad = client.get(f"/api/panai4/runs/{legacy_id}/items/1/steps/select/docx")
        log(f"legacy select export={bad.status_code} (expect 400)")
        if bad.status_code != 400:
            ok = False
        # 旧 zip 不应含【全流程】/【选词】
        lz = client.get(f"/api/panai4/runs/{legacy_id}/items/1/export.zip")
        log(f"legacy article zip={lz.status_code} bytes={len(lz.content)}")
        if lz.status_code != 200:
            ok = False
        else:
            with zipfile.ZipFile(io.BytesIO(lz.content)) as archive:
                names = archive.namelist()
                log(f"legacy zip files={names}")
                if any(n.startswith("【全流程】") or n.startswith("【选词】") for n in names):
                    ok = False
                    log("FAIL legacy zip gained full-flow files")
                if not any("负担说明" in n for n in names):
                    ok = False
                    log("FAIL legacy zip missing burden")

    log(f"section_export -> {'PASS' if ok else 'FAIL'}")
    log("")
    return ok


def section_frontend_static() -> bool:
    log("=== 3. 前端页签静态检查 ===")
    vue = _REPO / "front_mic" / "frontend" / "src" / "components" / "toolbox" / "PanAI4Test.vue"
    text = vue.read_text(encoding="utf-8")
    ok = True
    if "全流程测试" not in text:
        ok = False
        log("FAIL missing 全流程测试")
    if "词条定义生成负担说明测试（SC）" in text:
        ok = False
        log("FAIL SC tab label still visible")
    else:
        log("PASS SC tab label hidden")
    if "PanAI4SC" not in text:
        ok = False
        log("FAIL PanAI4SC removed")
    else:
        log("PASS PanAI4SC code retained")
    if "普通版" in text and "tab === 'sc'" in text:
        pass
    # 新建入口均为 full（后端强制 flow_kind=full）；前端无旧流程切换
    if "flow_kind" in text and "legacy" in text and "新建" in text:
        log("WARN check legacy create UI")
    log(f"section_frontend -> {'PASS' if ok else 'FAIL'}")
    log("")
    return ok


def section_stage2() -> bool:
    log("=== 4. verify_stage2（已更新过时断言） ===")
    log("改动说明：")
    log("  A) plain 默认值：原断言 plain_prompt_default == load_template('burden')（当时 CURRENT=v0.3）")
    log("     → 现改为 plain_prompt_default == build_plain_prompt_default_v3(load_template('burden','v0.3'))")
    log("  B) ref 新句子：原断言 ref 中 PLAIN_NEW 恰好 1 次")
    log("     → 现行直写 v3 正文不再含该替换句，改为期望计数 = 0")
    import subprocess

    r = subprocess.run(
        [sys.executable, "-m", "panai4.sc.verify_stage2"],
        cwd=str(_BACKEND),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    out = (r.stdout or "") + (r.stderr or "")
    out = out.replace("\ufffd", "?")
    for line in out.splitlines():
        if any(k in line for k in ("FAIL", "PASS", "DONE", "plain", "PLAIN", "FRONTEND", "tab", "fails=")):
            log(f"  {line}")
    ok = r.returncode == 0 and ("fails=0" in out or "DONE fails=0" in out)
    log(f"verify_stage2 exit={r.returncode} -> {'PASS' if ok else 'FAIL'}")
    log("")
    return ok


def section_cd() -> bool:
    log("=== 5. 回归 verify_step_c / verify_step_d ===")
    import subprocess

    ok = True
    for mod in ("panai4.verify_step_c", "panai4.verify_step_d"):
        r = subprocess.run(
            [sys.executable, "-m", mod],
            cwd=str(_BACKEND),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        tail = "\n".join((r.stdout or "").splitlines()[-8:])
        log(f"--- {mod} exit={r.returncode} ---")
        log(tail)
        if r.returncode != 0:
            ok = False
            log((r.stderr or "")[-500:])
    log(f"section_cd -> {'PASS' if ok else 'FAIL'}")
    log("")
    return ok


def main() -> int:
    log("=== Step E+F verification ===")
    log("")
    ok = True
    ok = section_cache() and ok
    ok = section_export() and ok
    ok = section_frontend_static() and ok
    ok = section_stage2() and ok
    ok = section_cd() and ok
    log("=== Frontend screenshot ===")
    log("SKIP automated browser (no local vite assumed). Static checks above cover tab labels.")
    log("")
    log(f"=== OVERALL: {'PASS' if ok else 'FAIL'} ===")
    flush()
    print(f"wrote {LOG}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
