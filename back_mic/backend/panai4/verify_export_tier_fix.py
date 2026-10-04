# -*- coding: utf-8 -*-
"""选词导出档次分组修复验证（假模型）。写入 logs/sc_fullflow_export_tier_fix.log"""
from __future__ import annotations

import io
import json
import os
import re
import sys
import uuid
import zipfile
from collections import Counter
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

LOG = _REPO / "logs" / "sc_fullflow_export_tier_fix.log"
lines: list[str] = []


def log(msg: str = "") -> None:
    print(msg)
    lines.append(msg)


def flush() -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")


def setup_env(name: str) -> None:
    os.environ["PANAI4_FAKE_LLM"] = "1"
    os.environ["PANAI4_FAKE_DELAY"] = "0"
    os.environ["PANAI4_DB_PATH"] = str(_BACKEND / "data" / "panai4" / name)
    from panai4 import db

    db.reset_connection_for_tests()
    db.init_db()


def poll(client, run_id, want=("done", "failed", "interrupted", "cancelled", "awaiting_confirm"), timeout=90):
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        body = client.get(f"/api/panai4/runs/{run_id}/progress").json()
        if body["status"] in want:
            return body
        time.sleep(0.05)
    raise RuntimeError(f"timeout {run_id}")


def docx_paras(data: bytes) -> list[str]:
    from docx import Document

    return [p.text for p in Document(io.BytesIO(data)).paragraphs]


def parse_tier_sections(paras: list[str]) -> dict[str, list[str]]:
    """从段落解析【档次】（n）标题后的词条名。"""
    out: dict[str, list[str]] = {}
    current = None
    heading = re.compile(r"^【(最内在|内在|外在|未分档)】(?:（(\d+)）)?$")
    for text in paras:
        t = (text or "").strip()
        m = heading.match(t)
        if m:
            current = m.group(1)
            out.setdefault(current, [])
            continue
        if current and t and "｜" in t:
            name = t.split("｜", 1)[0].replace("（人工调整）", "").strip()
            out[current].append(name)
        elif current and t and t not in {"选出的词条", "主题"} and not t.startswith("第"):
            # 无依据分隔也可能只有名字
            if not t.startswith("【"):
                out[current].append(t)
    return out


def check_export_tiers(label: str, paras: list[str], expect_total: int) -> bool:
    sections = parse_tier_sections(paras)
    ok = True
    log(f"  [{label}] headings={[k for k in ('最内在','内在','外在','未分档') if k in sections]}")
    counts = {k: len(v) for k, v in sections.items()}
    log(f"  [{label}] counts={counts}")
    # 标题括号条数与实际一致
    heading = re.compile(r"^【(最内在|内在|外在|未分档)】（(\d+)）$")
    seen = set()
    for t in paras:
        m = heading.match((t or "").strip())
        if not m:
            # 旧式无括号也不接受（本修复要求带条数）
            if re.match(r"^【(最内在|内在|外在)】$", (t or "").strip()):
                ok = False
                log(f"  FAIL heading missing count: {t!r}")
            continue
        tier, n = m.group(1), int(m.group(2))
        seen.add(tier)
        actual = len(sections.get(tier) or [])
        if n != actual:
            ok = False
            log(f"  FAIL {tier} header={n} actual={actual}")
    for required in ("最内在", "内在", "外在"):
        if required not in seen:
            ok = False
            log(f"  FAIL missing counted heading for {required}")
    total_all = sum(len(sections.get(k) or []) for k in ("最内在", "内在", "外在", "未分档"))
    log(f"  [{label}] sum={total_all} expect={expect_total}")
    if total_all != expect_total:
        ok = False
        log("  FAIL sum != expect")
    if (
        expect_total >= 3
        and counts.get("外在", 0) == expect_total
        and counts.get("最内在", 0) == 0
        and counts.get("内在", 0) == 0
    ):
        ok = False
        log("  FAIL all dumped into 外在")
    return ok


def section_fake() -> bool:
    log("=== 1. FAKE 批量 + 非批量（删/加词）导出 ===")
    setup_env("panai4_export_tier_fix.db")
    from fastapi.testclient import TestClient

    from main import app
    from user.token import test_token

    app.dependency_overrides[test_token] = lambda: {"username": "tierFix", "role": "t0"}
    ok = True
    with TestClient(app) as client:
        # 批量
        r = client.post(
            "/api/panai4/runs",
            json={
                "created_by": "tierFix",
                "batch_mode": True,
                "main_scope": "skeleton",
                "analysis_scope": "none",
                "items": [{"title": f"批量档次篇{uuid.uuid4().hex[:4]}", "original_outline": "壹 点。"}],
            },
        )
        run_b = r.json()["run_id"]
        body = poll(client, run_b, want=("done",))
        item = body["items"][0]
        detail = client.get(f"/api/panai4/runs/{run_b}").json()
        final = json.loads(detail["items"][0].get("final_terms_json") or "[]")
        log(f"batch run={run_b} terms={len(final)} tier_counter={dict(Counter(x.get('tier') for x in final))}")
        sel = client.get(f"/api/panai4/runs/{run_b}/items/1/steps/select/docx")
        if sel.status_code != 200:
            ok = False
            log(f"FAIL select docx {sel.status_code}")
        else:
            paras = docx_paras(sel.content)
            ok = check_export_tiers("batch-select", paras, len(final)) and ok
        z = client.get(f"/api/panai4/runs/{run_b}/items/1/export.zip")
        if z.status_code != 200:
            ok = False
            log(f"FAIL zip {z.status_code}")
        else:
            with zipfile.ZipFile(io.BytesIO(z.content)) as archive:
                combined = next(n for n in archive.namelist() if n.startswith("【全流程】"))
                paras = docx_paras(archive.read(combined))
                # 只取「选出的词条」到下一节
                start = next(i for i, t in enumerate(paras) if t.strip() == "选出的词条")
                end = next(
                    (i for i, t in enumerate(paras) if i > start and t.strip() in {"负担说明", "主题"}),
                    len(paras),
                )
                # 下一主标题：负担说明
                end = next((i for i, t in enumerate(paras) if i > start and t.strip() == "负担说明"), len(paras))
                ok = check_export_tiers("batch-full", paras[start:end], len(final)) and ok

        # 非批量：确认时删一词、加一词
        r2 = client.post(
            "/api/panai4/runs",
            json={
                "created_by": "tierFix",
                "batch_mode": False,
                "main_scope": "skeleton",
                "analysis_scope": "none",
                "items": [{"title": f"确认档次篇{uuid.uuid4().hex[:4]}"}],
            },
        )
        run_m = r2.json()["run_id"]
        body2 = poll(client, run_m, want=("awaiting_confirm",))
        d2 = client.get(f"/api/panai4/runs/{run_m}").json()
        item2 = d2["items"][0]
        gate = next(s for s in item2["steps"] if s["step"] == "await_confirm")
        raw_meta = gate.get("meta_json")
        if isinstance(raw_meta, str):
            meta = json.loads(raw_meta or "{}")
        else:
            meta = raw_meta or {}
        cands = list(meta.get("candidates") or meta.get("items") or [])
        if len(cands) < 2:
            ok = False
            log("FAIL not enough candidates for edit")
        else:
            removed = cands[0]["name"]
            kept = [
                {"name": c["name"], "tier": c.get("tier") or "", "reason": c.get("reason") or ""}
                for c in cands[1:]
            ]
            # 加一个三档里必有的词
            from panai4.sc.data import load_sc_data

            data = load_sc_data()
            add_name = next(n for n in data.tier_of if n not in {c["name"] for c in cands})
            kept.append({"name": add_name, "tier": data.tier_of[add_name], "reason": "人工加词"})
            conf = client.post(
                f"/api/panai4/runs/{run_m}/items/1/confirm",
                json={"terms": kept},
            )
            log(f"confirm status={conf.status_code} removed={removed} added={add_name}")
            if conf.status_code != 200:
                ok = False
                log(conf.text[:200])
            else:
                body3 = poll(client, run_m, want=("done",))
                d3 = client.get(f"/api/panai4/runs/{run_m}").json()
                final3 = json.loads(d3["items"][0].get("final_terms_json") or "[]")
                log(f"manual terms={len(final3)} counter={dict(Counter(x.get('tier') for x in final3))}")
                sel3 = client.get(f"/api/panai4/runs/{run_m}/items/1/steps/select/docx")
                paras3 = docx_paras(sel3.content)
                ok = check_export_tiers("manual-select", paras3, len(final3)) and ok
                # 应含人工调整标记
                if not any("人工调整" in (p or "") for p in paras3):
                    log("WARN no 人工调整 mark (加词应有)")
                z3 = client.get(f"/api/panai4/runs/{run_m}/items/1/export.zip")
                with zipfile.ZipFile(io.BytesIO(z3.content)) as archive:
                    combined = next(n for n in archive.namelist() if n.startswith("【全流程】"))
                    paras = docx_paras(archive.read(combined))
                    start = next(i for i, t in enumerate(paras) if t.strip() == "选出的词条")
                    end = next((i for i, t in enumerate(paras) if i > start and t.strip() == "负担说明"), len(paras))
                    ok = check_export_tiers("manual-full", paras[start:end], len(final3)) and ok

    log(f"section_fake -> {'PASS' if ok else 'FAIL'}")
    log("")
    return ok


def section_run1() -> bool:
    log("=== 2. 真实运行 #1 重新导出（不调模型） ===")
    prod = _BACKEND / "data" / "panai4" / "panai4.db"
    if not prod.exists():
        log("FAIL missing panai4.db")
        return False
    os.environ["PANAI4_FAKE_LLM"] = "1"
    os.environ["PANAI4_DB_PATH"] = str(prod.resolve())
    from panai4 import db
    from panai4.export_docx import build_full_article_docx, build_select_docx, final_terms_for_export

    db.reset_connection_for_tests()
    db.init_db()
    run = db.get_run(1)
    if not run:
        log("FAIL run 1 missing")
        return False
    ok = True
    for item in db.list_items(1):
        steps = db.list_steps(item["id"])
        final = json.loads(item.get("final_terms_json") or "[]")
        expect = len(final)
        counter = Counter((x.get("tier") or "") for x in final)
        log(f"item pos={item['position']} title={item['title'][:40]} final_n={expect} db_tiers={dict(counter)}")
        terms = final_terms_for_export(item, steps)
        resolved = Counter(t["tier"] for t in terms)
        log(f"  resolved_tiers={dict(resolved)}")
        name, data = build_select_docx(item, steps, flow_kind="full")
        paras = docx_paras(data)
        ok = check_export_tiers(f"run1-p{item['position']}-select", paras, expect) and ok
        cname, cdata = build_full_article_docx(item, steps)
        cparas = docx_paras(cdata)
        start = next(i for i, t in enumerate(cparas) if t.strip() == "选出的词条")
        end = next((i for i, t in enumerate(cparas) if i > start and t.strip() == "负担说明"), len(cparas))
        ok = check_export_tiers(f"run1-p{item['position']}-full", cparas[start:end], expect) and ok
        # 与 final 总数核对
        sections = parse_tier_sections(paras)
        exported_n = sum(len(v) for v in sections.values())
        log(f"  export_n={exported_n} vs final_n={expect} match={exported_n == expect}")
        if exported_n != expect:
            ok = False
    log(f"section_run1 -> {'PASS' if ok else 'FAIL'}")
    log("")
    return ok


def section_regress() -> bool:
    log("=== 3. 回归 verify_step_ef / c / d ===")
    import subprocess

    ok = True
    for mod in ("panai4.verify_step_ef", "panai4.verify_step_c", "panai4.verify_step_d"):
        r = subprocess.run(
            [sys.executable, "-m", mod],
            cwd=str(_BACKEND),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        tail = "\n".join((r.stdout or "").splitlines()[-6:])
        log(f"--- {mod} exit={r.returncode} ---")
        log(tail)
        if r.returncode != 0:
            ok = False
            log((r.stderr or "")[-400:])
    log(f"section_regress -> {'PASS' if ok else 'FAIL'}")
    log("")
    return ok


def section_root_cause() -> None:
    log("=== 0. 根因（只读结论） ===")
    log("1) run#1 final_terms_json：有字段 tier，取值「最内在/内在/外在」（篇1: 10/10/14；篇2: 7/12/13）。")
    log("2) 旧 format_select_export_text 用 `(by_tier.get(tier) or by_tier['外在']).append(...)`；")
    log("   空列表在 Python 为假，首次与之后的最内在/内在全部落入外在；顺序仍按 final 原序，故看起来「顺序对、分组错」。")
    log("3) 全流程 docx 共用 format_select_export_text，同样受影响。")
    log("4) 确认页：候选来自 await_confirm/select 的 meta（tier/tier_actual）；加词来自 /sc/meta（三档分类）。")
    log("")


def main() -> int:
    log("选词导出档次修复验证")
    log("")
    section_root_cause()
    ok = True
    ok = section_fake() and ok
    ok = section_run1() and ok
    ok = section_regress() and ok
    log(f"=== OVERALL: {'PASS' if ok else 'FAIL'} ===")
    flush()
    print(f"wrote {LOG}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
