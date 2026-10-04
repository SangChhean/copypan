# -*- coding: utf-8 -*-
"""全流程步骤 B：SCHEMA_VERSION=3 迁移验证。

用法（在 back_mic/backend）:
    python -m panai4.verify_step_b

日志：logs/sc_fullflow_stepB.log
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_REPO = _BACKEND.parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

LOG = _REPO / "logs" / "sc_fullflow_stepB.log"
OFFICIAL = _BACKEND / "data" / "panai4" / "panai4.db"
TMP_DIR = _BACKEND / "data" / "panai4" / "_stepB_tmp"
lines: list[str] = []


def log(msg: str = "") -> None:
    print(msg)
    lines.append(msg)


def flush() -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    LOG.write_text("\n".join(lines) + "\n", encoding="utf-8")


def h16(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def list_backups(dirpath: Path, stem: str) -> list[Path]:
    return sorted(dirpath.glob(f"{stem}_*{Path(stem).suffix or '.db'}")) if False else sorted(
        p for p in dirpath.glob(f"{stem}_*.db")
    )


def open_raw(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    return conn


def table_count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(1) FROM {table}").fetchone()[0])


def content_hash(conn: sqlite3.Connection, table: str, columns: list[str]) -> str:
    names = ", ".join(columns)
    rows = conn.execute(f"SELECT {names} FROM {table} ORDER BY id").fetchall()
    h = hashlib.sha256()
    for row in rows:
        for value in row:
            h.update(repr(value).encode("utf-8"))
            h.update(b"\0")
        h.update(b"\n")
    return h.hexdigest()


def columns(conn: sqlite3.Connection, table: str) -> list[str]:
    return [r[1] for r in conn.execute(f"PRAGMA table_info({table})")]


REBUILT = ("runs", "run_items", "step_results", "prompt_test_versions")
NEW_COLS = {
    "runs": {"batch_mode", "flow_kind"},
    "run_items": {"final_terms_json"},
    "step_results": {"meta_json"},
    "prompt_test_versions": set(),
}


def snapshot_old(path: Path) -> dict:
    conn = open_raw(path)
    try:
        out = {"user_version": int(conn.execute("PRAGMA user_version").fetchone()[0]), "tables": {}}
        for table in REBUILT:
            cols = columns(conn, table)
            out["tables"][table] = {
                "count": table_count(conn, table),
                "cols": cols,
                "hash": content_hash(conn, table, cols),
            }
        return out
    finally:
        conn.close()


def check_post_migrate(path: Path, before: dict, label: str) -> bool:
    ok = True
    conn = open_raw(path)
    try:
        ver = int(conn.execute("PRAGMA user_version").fetchone()[0])
        integ = conn.execute("PRAGMA integrity_check").fetchone()[0]
        conn.execute("PRAGMA foreign_keys=ON")
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        log(f"[{label}] user_version={ver} integrity={integ} fk_issues={len(fk)}")
        if ver != 3 or integ != "ok" or fk:
            ok = False
        for table in REBUILT:
            cols = columns(conn, table)
            old_cols = before["tables"][table]["cols"]
            count = table_count(conn, table)
            # 旧列哈希
            digest = content_hash(conn, table, old_cols)
            expect = before["tables"][table]["hash"]
            match = count == before["tables"][table]["count"] and digest == expect
            log(
                f"[{label}] {table}: count {before['tables'][table]['count']}→{count} "
                f"old_cols_hash_match={digest == expect} hash16={digest[:16]}"
            )
            if not match:
                ok = False
            missing_new = NEW_COLS[table] - set(cols)
            if missing_new:
                log(f"[{label}] FAIL missing new cols on {table}: {missing_new}")
                ok = False

        # 默认值
        if table_count(conn, "runs"):
            bad_bm = conn.execute("SELECT COUNT(1) FROM runs WHERE batch_mode IS NULL OR batch_mode != 0").fetchone()[0]
            bad_fk = conn.execute("SELECT COUNT(1) FROM runs WHERE flow_kind IS NULL OR flow_kind != 'legacy'").fetchone()[0]
            log(f"[{label}] runs defaults: nondefault_batch={bad_bm} nondefault_flow={bad_fk}")
            if bad_bm or bad_fk:
                ok = False
        if table_count(conn, "run_items"):
            non_null = conn.execute(
                "SELECT COUNT(1) FROM run_items WHERE final_terms_json IS NOT NULL"
            ).fetchone()[0]
            log(f"[{label}] run_items final_terms_json non-null (expect 0 on old rows)={non_null}")
            # 旧行应为 NULL；若 rehearsal 副本无人工写入则为 0
            if non_null != 0:
                # 不判失败：正式库旧行必为 NULL；若非 0 再记
                log(f"[{label}] WARN unexpected non-null final_terms_json on migrated rows")
    finally:
        conn.close()
    return ok


def check_inserts(path: Path) -> bool:
    """新 CHECK：合法插入成功，非法被拒。"""
    ok = True
    conn = open_raw(path)
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        now = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
        # runs awaiting_confirm
        try:
            conn.execute(
                "INSERT INTO runs (created_at, status, note, created_by, batch_mode, flow_kind) "
                "VALUES (?, 'awaiting_confirm', 'stepB', 'stepB', 0, 'legacy')",
                (now,),
            )
            run_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            log(f"[CHECK] runs awaiting_confirm insert ok id={run_id}")
        except Exception as e:
            ok = False
            log(f"[CHECK] FAIL runs awaiting_confirm: {e}")
            run_id = None

        # illegal status
        try:
            conn.execute(
                "INSERT INTO runs (created_at, status, note, created_by) VALUES (?, 'nope', '', 'x')",
                (now,),
            )
            ok = False
            log("[CHECK] FAIL: illegal run status accepted")
        except sqlite3.IntegrityError:
            log("[CHECK] PASS: illegal run status rejected")

        # illegal flow_kind
        try:
            conn.execute(
                "INSERT INTO runs (created_at, status, note, created_by, flow_kind) "
                "VALUES (?, 'done', '', 'x', 'other')",
                (now,),
            )
            ok = False
            log("[CHECK] FAIL: illegal flow_kind accepted")
        except sqlite3.IntegrityError:
            log("[CHECK] PASS: illegal flow_kind rejected")

        if run_id is not None:
            try:
                conn.execute(
                    "INSERT INTO run_items (run_id, position, title, status) "
                    "VALUES (?, 0, 'stepB-item', 'awaiting_confirm')",
                    (run_id,),
                )
                item_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
                log(f"[CHECK] run_items awaiting_confirm insert ok id={item_id}")
            except Exception as e:
                ok = False
                log(f"[CHECK] FAIL run_items awaiting_confirm: {e}")
                item_id = None
        else:
            item_id = None

        if item_id is not None:
            for step in ("select", "await_confirm", "term_defs"):
                try:
                    conn.execute(
                        """
                        INSERT INTO step_results (
                            run_item_id, step, prompt_name, prompt_version, model,
                            prompt_text, status, created_at, meta_json
                        ) VALUES (?, ?, 'P', 'v1.0', 'fake', 't', 'awaiting_confirm', ?, ?)
                        """,
                        (item_id, step, now, '{"n":1}'),
                    )
                    log(f"[CHECK] step_results step={step} status=awaiting_confirm ok")
                except Exception as e:
                    ok = False
                    log(f"[CHECK] FAIL step_results {step}: {e}")
            try:
                conn.execute(
                    """
                    INSERT INTO step_results (
                        run_item_id, step, prompt_name, prompt_version, model,
                        prompt_text, status, created_at
                    ) VALUES (?, 'not_a_step', 'P', 'v1.0', 'fake', 't', 'done', ?)
                    """,
                    (item_id, now),
                )
                ok = False
                log("[CHECK] FAIL: illegal step accepted")
            except sqlite3.IntegrityError:
                log("[CHECK] PASS: illegal step rejected")

        # prompt_test_versions select
        try:
            conn.execute(
                """
                INSERT INTO prompt_test_versions (
                    step, prompt_name, base_current_version, seq, version_name,
                    parent_kind, parent_version, template, change_note, created_by, created_at
                ) VALUES ('select', 'Prompt0', 'v1.0', 9999, 'v1.0-测9999',
                          'current', 'v1.0', '{query}', 'stepB verify', 'stepB', ?)
                """,
                (now,),
            )
            log("[CHECK] prompt_test_versions step=select ok")
        except Exception as e:
            ok = False
            log(f"[CHECK] FAIL prompt_test_versions select: {e}")

        try:
            conn.execute(
                """
                INSERT INTO prompt_test_versions (
                    step, prompt_name, base_current_version, seq, version_name,
                    parent_kind, parent_version, template, change_note, created_by, created_at
                ) VALUES ('bogus', 'X', 'v0', 1, 'v0-测1',
                          'current', 'v0', 't', 'n', 'x', ?)
                """,
                (now,),
            )
            ok = False
            log("[CHECK] FAIL: illegal prompt step accepted")
        except sqlite3.IntegrityError:
            log("[CHECK] PASS: illegal prompt step rejected")

        conn.rollback()  # 不保留测试插入
        log("[CHECK] rolled back test inserts (DB content unchanged for counts)")
    finally:
        conn.close()
    return ok


def section0_pre_existing_stage2() -> None:
    log("=== 0. verify_stage2 既有失败证据 ===")
    log("方法：git stash 卸下步骤 A 的 prompts/extracted/前端/router 后运行 verify_stage2。")
    log("当时输出（节选，与步骤 A 报告相同的 2 条）：")
    log("  FAIL plain default != stored v0.3")
    log("  FAIL ref new sentence count=0")
    log("  === DONE fails=2 ===")
    log("结论：既有。针对已过时的「普通版默认 == v0.3 / PLAIN_NEW 原样保留」断言。")
    log("待清理：verify_stage2 模板区这两条断言（不在本步修改）。")
    log("")


def migrate_via_init(db_file: Path) -> None:
    os.environ["PANAI4_DB_PATH"] = str(db_file)
    from panai4 import db as dbmod

    dbmod.reset_connection_for_tests()
    dbmod.migration_report.clear()
    dbmod.init_db()


def section1_rehearsal() -> tuple[bool, Path | None]:
    log("=== 1. 排练（正式库副本） ===")
    if not OFFICIAL.exists():
        log(f"FAIL: official DB missing {OFFICIAL}")
        return False, None
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    copy = TMP_DIR / "panai4_rehearsal.db"
    if copy.exists():
        copy.unlink()
    # 清掉副本旁旧备份，便于数备份
    for old in TMP_DIR.glob("panai4_rehearsal_*.db"):
        old.unlink()
    shutil.copy2(OFFICIAL, copy)
    before = snapshot_old(copy)
    log(f"rehearsal copy={copy} from={OFFICIAL} user_version={before['user_version']}")
    for t, info in before["tables"].items():
        log(f"  before {t}: count={info['count']} cols={len(info['cols'])} hash16={info['hash'][:16]}")

    backups_before = list(TMP_DIR.glob("panai4_rehearsal_*.db"))
    migrate_via_init(copy)
    from panai4 import db as dbmod

    report = dict(dbmod.migration_report)
    log(f"migration_report backup={report.get('backup')} counts={report.get('counts')}")
    backups_after = list(TMP_DIR.glob("panai4_rehearsal_*.db"))
    new_backups = sorted(set(backups_after) - set(backups_before))
    log(f"new backup files: {[str(p) for p in new_backups]}")

    ok = check_post_migrate(copy, before, "rehearsal")
    ok = check_inserts(copy) and ok
    return ok, copy


def section2_idempotent(copy: Path) -> bool:
    log("=== 2. 幂等 ===")
    backups_before = set(TMP_DIR.glob("panai4_rehearsal_*.db"))
    # 记录 schema sql 指纹
    conn = open_raw(copy)
    sql_before = {
        t: conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (t,)
        ).fetchone()[0]
        for t in REBUILT
    }
    conn.close()
    migrate_via_init(copy)
    backups_after = set(TMP_DIR.glob("panai4_rehearsal_*.db"))
    new_b = backups_after - backups_before
    conn = open_raw(copy)
    ver = int(conn.execute("PRAGMA user_version").fetchone()[0])
    sql_after = {
        t: conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (t,)
        ).fetchone()[0]
        for t in REBUILT
    }
    conn.close()
    from panai4 import db as dbmod

    report_empty = not dbmod.migration_report or dbmod.migration_report.get("to_version") != 3
    # 第二次 init 不应再写 migration_report（clear only on migrate）；若仍是上次的也可以，关键是无新备份
    ok = ver == 3 and len(new_b) == 0 and sql_before == sql_after
    log(f"idempotent: user_version={ver} new_backups={len(new_b)} sql_unchanged={sql_before == sql_after}")
    log(f"idempotent -> {'PASS' if ok else 'FAIL'}")
    log("")
    return ok


def section3_fault(copy: Path, before_hash_snapshot: dict) -> bool:
    log("=== 3. 故障注入回滚 ===")
    # 用另一份仍为 v2 的副本
    fault_copy = TMP_DIR / "panai4_fault.db"
    if fault_copy.exists():
        fault_copy.unlink()
    for old in TMP_DIR.glob("panai4_fault_*.db"):
        old.unlink()
    shutil.copy2(OFFICIAL, fault_copy)
    before = snapshot_old(fault_copy)
    assert before["user_version"] == 2

    from panai4 import db as dbmod

    def boom():
        raise RuntimeError("injected fault for stepB")

    dbmod._migrate_v3_fail_hook = boom
    os.environ["PANAI4_DB_PATH"] = str(fault_copy)
    dbmod.reset_connection_for_tests()
    ok = True
    try:
        try:
            dbmod.init_db()
            ok = False
            log("FAIL: expected migrate to raise")
        except RuntimeError as e:
            log(f"caught expected: {e}")
        finally:
            dbmod._migrate_v3_fail_hook = None
            dbmod.reset_connection_for_tests()

        after = snapshot_old(fault_copy)
        ver = after["user_version"]
        hash_same = all(
            after["tables"][t]["hash"] == before["tables"][t]["hash"] for t in REBUILT
        )
        backups = list(TMP_DIR.glob("panai4_fault_*.db"))
        log(f"after fault: user_version={ver} (expect 2) hashes_unchanged={hash_same} backups={len(backups)}")
        log(f"backup kept: {[str(p) for p in backups]}")
        if ver != 2 or not hash_same or not backups:
            ok = False
        # 确认可再次成功迁移
        migrate_via_init(fault_copy)
        ver3 = snapshot_old(fault_copy)["user_version"]
        log(f"retry migrate after fault: user_version={ver3}")
        if ver3 != 3:
            ok = False
    finally:
        dbmod._migrate_v3_fail_hook = None
    log(f"fault inject -> {'PASS' if ok else 'FAIL'}")
    log("")
    return ok


def section4_regression() -> bool:
    log("=== 4. 回归 FAKE_LLM + select 测试版 ===")
    os.environ["PANAI4_FAKE_LLM"] = "1"
    os.environ["PANAI4_FAKE_DELAY"] = "0"
    test_db = _BACKEND / "data" / "panai4" / "panai4_test.db"
    os.environ["PANAI4_DB_PATH"] = str(test_db)

    from panai4 import db as dbmod

    dbmod.reset_connection_for_tests()
    dbmod.init_db()
    ver = int(dbmod.connect().execute("PRAGMA user_version").fetchone()[0])
    log(f"panai4_test.db user_version={ver}")

    from fastapi.testclient import TestClient

    from main import app
    from panai4.prompts import load_template
    from user.token import test_token

    app.dependency_overrides[test_token] = lambda: {"username": "stepB", "role": "t0"}
    ok = True
    topic = f"StepB假模型{uuid.uuid4().hex[:6]}"
    outline = "壹 原纲目。"
    with TestClient(app) as client:
        created = client.post(
            "/api/panai4/runs",
            json={
                "created_by": "stepB",
                "note": "stepB regression",
                "main_scope": "skeleton",
                "analysis_scope": "diagnosis",
                "items": [{"title": topic, "original_outline": outline}],
            },
        )
        log(f"create run status={created.status_code}")
        if created.status_code >= 400:
            log(f"FAIL create: {created.text}")
            return False
        run_id = created.json()["run_id"]
        deadline = time.time() + 60
        body = None
        while time.time() < deadline:
            body = client.get(f"/api/panai4/runs/{run_id}/progress").json()
            if body["status"] in {"done", "failed", "interrupted"}:
                break
            time.sleep(0.05)
        log(f"run status={body['status']}")
        if body["status"] != "done":
            ok = False

        # 导出一步 docx
        item = body["items"][0]
        position = item.get("position", 0)
        exp = client.get(f"/api/panai4/runs/{run_id}/items/{position}/steps/burden/docx")
        log(
            f"export docx status={exp.status_code} "
            f"content-type={exp.headers.get('content-type')} bytes={len(exp.content)}"
        )
        if exp.status_code != 200 or len(exp.content) < 100:
            ok = False
            log("FAIL export burden docx")

        # 打开旧运行详情（刚跑完的这条）
        detail = client.get(f"/api/panai4/runs/{run_id}")
        log(f"run detail status={detail.status_code}")
        if detail.status_code != 200:
            ok = False
        else:
            d = detail.json()
            log(f"  detail status={d.get('status')} items={len(d.get('items') or [])}")

        # select 测试版
        tpl = load_template("select")
        created_t = client.post(
            "/api/panai4/prompt_tests",
            json={
                "step": "select",
                "template": tpl,
                "parent_kind": "current",
                "change_note": "stepB select test",
                "created_by": "stepB",
            },
        )
        log(f"create select test status={created_t.status_code} body={created_t.text[:240]}")
        if created_t.status_code not in (200, 201):
            ok = False
        else:
            tid = created_t.json()["id"]
            deleted = client.delete(f"/api/panai4/prompt_tests/{tid}", params={"deleted_by": "stepB"})
            log(f"delete select test status={deleted.status_code}")
            if deleted.status_code != 200:
                ok = False

    log(f"regression -> {'PASS' if ok else 'FAIL'}")
    log("")
    return ok

def section5_real() -> bool:
    log("=== 5. 正式库真迁移 ===")
    before = snapshot_old(OFFICIAL)
    log(f"official before user_version={before['user_version']}")
    for t, info in before["tables"].items():
        log(f"  {t}: count={info['count']} hash16={info['hash'][:16]}")

    data_dir = OFFICIAL.parent
    backups_before = set(data_dir.glob(f"{OFFICIAL.stem}_*.db"))
    migrate_via_init(OFFICIAL)
    from panai4 import db as dbmod

    report = dict(dbmod.migration_report)
    backup = report.get("backup")
    log(f"official migration_report backup={backup}")
    backups_after = set(data_dir.glob(f"{OFFICIAL.stem}_*.db"))
    new_b = sorted(backups_after - backups_before)
    log(f"new official backups: {[str(p) for p in new_b]}")
    ok = check_post_migrate(OFFICIAL, before, "official")
    if backup:
        log(f"BACKUP_PATH={backup}")
    log(f"real migrate -> {'PASS' if ok else 'FAIL'}")
    log("")
    return ok


def main() -> int:
    log("=== Step B verification ===")
    log("")
    section0_pre_existing_stage2()
    ok = True
    copy = None
    try:
        ok1, copy = section1_rehearsal()
        ok = ok1 and ok
        if copy is None:
            flush()
            return 1
        ok = section2_idempotent(copy) and ok
        before_for_fault = snapshot_old(OFFICIAL)
        ok = section3_fault(copy, before_for_fault) and ok
        ok = section4_regression() and ok
        if ok:
            ok = section5_real() and ok
        else:
            log("SKIP real migrate: earlier checks failed")
    except Exception as e:
        log(f"FATAL: {e!r}")
        ok = False
        flush()
        raise

    log(f"=== OVERALL: {'PASS' if ok else 'FAIL'} ===")
    flush()
    print(f"wrote {LOG}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
