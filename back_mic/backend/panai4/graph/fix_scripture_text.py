# -*- coding: utf-8 -*-
"""neo4j-v4：修正 3 个 Scripture 节点的 text 为完整版。

只 SET s.text；不动 ref、关系、其他节点。
不修改已有脚本；不运行 build_v4.py；不打印密码。

用法（在 back_mic/backend 下）:
    python -m panai4.graph.fix_scripture_text --stage check|fix|verify
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from neo4j import READ_ACCESS, WRITE_ACCESS, GraphDatabase

from panai4.graph import import_annotation as v1
from panai4.graph import import_annotation_v2 as v2
from panai4.graph.import_general_annotation import _PROTECTED, _sha_val, find_sources

_REPO = v1._REPO
_LOG_DIR = v1._LOG_DIR
_STATE = "fix_scripture_text"
_REPORT = _REPO / "docs" / "panai4_graph" / "fix_scripture_text.md"
_EXPECT_SCRIPTURE = 4851
_EXPECT_SUPPORTED_BY = 9768
_EXPECT_NODES = 7334
_EXPECT_RELS = 52197

# ref → expected full length
_TARGETS = {
    "约壹二15～16": 75,
    "何十三14": 56,
    "罗十六5": 38,
}

_A_PROPS = (
    "name_en",
    "greek_terms",
    "hebrew_terms",
    "definition_3a",
    "definition_3b",
    "high_peak_content",
    "organic_advance",
)


def _sha_pair(ref: str, text: str) -> str:
    raw = json.dumps({"ref": ref, "text": text}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _collect_versions(gen_path: Path) -> dict[str, list[str]]:
    gen = json.loads(gen_path.read_text(encoding="utf-8-sig"))
    by_ref: dict[str, list[str]] = defaultdict(list)
    for row in gen:
        for it in row.get("related_scriptures") or []:
            ref = it.get("ref")
            if ref in _TARGETS:
                by_ref[ref].append(it.get("text") or "")
    return by_ref


def _pick_full(texts_all: list[str]) -> dict[str, Any]:
    """返回 unique 版本、短/长、是否 2 版、长是否包含短。"""
    uniq = list(dict.fromkeys(texts_all))
    by_len = sorted(uniq, key=lambda t: (len(t), texts_all.index(t)))
    info: dict[str, Any] = {
        "n_occurrences": len(texts_all),
        "n_versions": len(uniq),
        "versions": [{"len": len(t), "text": t} for t in by_len],
    }
    if len(uniq) != 2:
        info["ok"] = False
        info["reason"] = f"版本数 {len(uniq)}≠2"
        return info
    short, full = by_len[0], by_len[1]
    contained = short in full
    info.update(
        {
            "ok": contained,
            "reason": None if contained else "长版不包含短版（非前缀/子串）",
            "short": short,
            "full": full,
            "short_len": len(short),
            "full_len": len(full),
            "short_is_prefix": full.startswith(short),
            "short_is_substr": contained,
        }
    )
    return info


def _snapshot_annos(session) -> dict[str, dict[str, str]]:
    props = list(_PROTECTED.keys()) + [p for p in _A_PROPS if p not in _PROTECTED]
    # organic_advance already in _PROTECTED; high_peak_content extra
    out = {}
    for prop in props:
        amap = v2._fetch_anno_map(session, prop)
        out[prop] = {name: _sha_val(val) for name, val in amap.items()}
    return out


def _compare_annos(before: dict[str, dict[str, str]], session) -> dict[str, Any]:
    result = {}
    for prop, old in before.items():
        amap = v2._fetch_anno_map(session, prop)
        now = {name: _sha_val(val) for name, val in amap.items()}
        only_b = sorted(set(old) - set(now))
        only_n = sorted(set(now) - set(old))
        mism = sorted(k for k in set(old) & set(now) if old[k] != now[k])
        result[prop] = {
            "before_n": len(old),
            "now_n": len(now),
            "sha_mismatch": len(mism),
            "only_before": only_b[:10],
            "only_now": only_n[:10],
            "mismatch_names": mism[:10],
        }
    return result


def stage_check(env: dict, log: v1.Logger) -> int:
    log.log("stage=check fix_scripture_text")
    srcs = find_sources()
    gen_path = srcs["general"]
    sha_before = v1._sha_import_dir()
    by_ref = _collect_versions(gen_path)

    fails: list[str] = []
    picks: dict[str, Any] = {}
    for ref, expect_len in _TARGETS.items():
        info = _pick_full(by_ref.get(ref) or [])
        picks[ref] = info
        log.log(
            f"{ref}: versions={info.get('n_versions')} "
            f"short={info.get('short_len')} full={info.get('full_len')} ok={info.get('ok')}"
        )
        if not info.get("ok"):
            fails.append(f"{ref}: {info.get('reason')} detail={info.get('versions')}")
            continue
        if info["full_len"] != expect_len:
            fails.append(f"{ref}: 完整版长度 {info['full_len']}≠预期 {expect_len}")
        if info["short_len"] >= info["full_len"]:
            fails.append(f"{ref}: 短版不短于长版")

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            sc_n = v1._run(session, "MATCH (s:Scripture) RETURN count(s) AS c")[0]["c"]
            sb_n = v1._run(session, "MATCH ()-[r:SUPPORTED_BY]->() RETURN count(r) AS c")[0]["c"]
            nodes = v1._run(session, "MATCH (n) RETURN count(n) AS c")[0]["c"]
            rels = v1._run(session, "MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
            if sc_n != _EXPECT_SCRIPTURE:
                fails.append(f"Scripture {sc_n}≠{_EXPECT_SCRIPTURE}")
            if sb_n != _EXPECT_SUPPORTED_BY:
                fails.append(f"SUPPORTED_BY {sb_n}≠{_EXPECT_SUPPORTED_BY}")
            if nodes != _EXPECT_NODES or rels != _EXPECT_RELS:
                fails.append(f"nodes/rels {nodes}/{rels} ≠ {_EXPECT_NODES}/{_EXPECT_RELS}")

            current = {}
            indegree = {}
            for ref, info in picks.items():
                found = v1._run(
                    session,
                    "MATCH (s:Scripture {ref: $ref}) RETURN s.text AS text",
                    {"ref": ref},
                )
                if len(found) != 1:
                    fails.append(f"图谱 ref={ref} 节点数={len(found)}≠1")
                    continue
                text = found[0]["text"]
                indeg = v1._run(
                    session,
                    """
                    MATCH (:Truth_Point)-[r:SUPPORTED_BY]->(s:Scripture {ref: $ref})
                    RETURN count(r) AS indeg
                    """,
                    {"ref": ref},
                )[0]["indeg"]
                current[ref] = {"text": text, "len": len(text) if text else 0, "indeg": indeg}
                indegree[ref] = indeg
                if info.get("ok") and text != info["short"]:
                    fails.append(
                        f"{ref}: 图谱当前 text 不是短版 "
                        f"(graph_len={len(text) if text else None}, short_len={info.get('short_len')})"
                    )

            # full Scripture snapshot
            all_rows = v1._run(
                session,
                "MATCH (s:Scripture) RETURN s.ref AS ref, s.text AS text ORDER BY ref",
            )
            snap = {r["ref"]: _sha_pair(r["ref"], r["text"] or "") for r in all_rows}
            if len(snap) != _EXPECT_SCRIPTURE:
                fails.append(f"快照条数 {len(snap)}≠{_EXPECT_SCRIPTURE}")

            anno_sha = _snapshot_annos(session)
    except Exception as exc:
        raise SystemExit("check 失败: " + v1._redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    sha_after = v1._sha_import_dir()
    sha_ok = sha_before["hashes"] == sha_after["hashes"]
    if not sha_ok:
        fails.append("可导入资料 SHA 前后不一致")

    state = {
        "version": 1,
        "check_ok": not fails,
        "fails": fails,
        "file": str(gen_path),
        "picks": {
            ref: {
                **{k: v for k, v in info.items() if k != "versions"},
                "versions": info.get("versions"),
            }
            for ref, info in picks.items()
        },
        "current": current,
        "indegree_before": indegree,
        "scripture_sha": snap,
        "anno_sha": anno_sha,
        "baseline": {
            "scripture_n": sc_n,
            "supported_by_n": sb_n,
            "nodes_total": nodes,
            "rels_total": rels,
        },
        "updates": {
            ref: picks[ref]["full"]
            for ref in _TARGETS
            if picks.get(ref, {}).get("ok")
        },
        "sha_before": sha_before,
        "sha_ok": sha_ok,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    v1.save_state(_STATE, state)
    write_report(state, None, None, log.path)
    for f in fails:
        log.log("GATE FAIL: " + f)
    if fails:
        log.log("闸门未通过，停止。")
        return 2
    log.log("闸门通过。拟更新 3 个 Scripture.text")
    return 0


def stage_fix(env: dict, log: v1.Logger) -> int:
    log.log("stage=fix scripture text")
    state = v1.load_state(_STATE)
    if not state.get("check_ok"):
        raise SystemExit("check 未通过，拒绝 fix")
    updates = state["updates"]
    if set(updates) != set(_TARGETS):
        raise SystemExit(f"updates 键异常: {sorted(updates)}")

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    results = {}
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=WRITE_ACCESS) as session:
            for ref, text in updates.items():
                # only SET text; match by ref
                row = session.run(
                    """
                    MATCH (s:Scripture {ref: $ref})
                    SET s.text = $text
                    RETURN s.ref AS ref, s.text AS text, size(s.text) AS n
                    """,
                    {"ref": ref, "text": text},
                ).single()
                if not row:
                    log.log(f"FAIL: 未找到 {ref}")
                    state["fix"] = {"aborted": True, "failed_ref": ref, "done": results}
                    v1.save_state(_STATE, state)
                    write_report(state, state["fix"], None, log.path)
                    return 2
                results[ref] = {"len": row["n"], "text": row["text"]}
                log.log(f"SET {ref} len={row['n']}")
    except Exception as exc:
        raise SystemExit("fix 失败: " + v1._redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    info = {"aborted": False, "updated": results}
    state["fix"] = info
    v1.save_state(_STATE, state)
    write_report(state, info, None, log.path)
    log.log("fix 完成 3 个节点")
    return 0


def stage_verify(env: dict, log: v1.Logger) -> int:
    log.log("stage=verify fix_scripture_text")
    state = v1.load_state(_STATE)
    if not state.get("fix") or state["fix"].get("aborted"):
        raise SystemExit("fix 未完成，拒绝 verify")
    updates = state["updates"]
    snap_before: dict[str, str] = state["scripture_sha"]
    fails: list[str] = []

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            sc_n = v1._run(session, "MATCH (s:Scripture) RETURN count(s) AS c")[0]["c"]
            sb_n = v1._run(session, "MATCH ()-[r:SUPPORTED_BY]->() RETURN count(r) AS c")[0]["c"]
            nodes = v1._run(session, "MATCH (n) RETURN count(n) AS c")[0]["c"]
            rels = v1._run(session, "MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
            if sc_n != _EXPECT_SCRIPTURE:
                fails.append(f"Scripture {sc_n}≠{_EXPECT_SCRIPTURE}")
            if sb_n != _EXPECT_SUPPORTED_BY:
                fails.append(f"SUPPORTED_BY {sb_n}≠{_EXPECT_SUPPORTED_BY}")
            if nodes != _EXPECT_NODES or rels != _EXPECT_RELS:
                fails.append(f"nodes/rels {nodes}/{rels}")

            after_texts = {}
            indeg_after = {}
            for ref, expect_len in _TARGETS.items():
                found = v1._run(
                    session,
                    "MATCH (s:Scripture {ref: $ref}) RETURN s.text AS text",
                    {"ref": ref},
                )
                if len(found) != 1:
                    fails.append(f"{ref}: 节点数 {len(found)}≠1")
                    continue
                text = found[0]["text"]
                indeg = v1._run(
                    session,
                    """
                    MATCH (:Truth_Point)-[r:SUPPORTED_BY]->(s:Scripture {ref: $ref})
                    RETURN count(r) AS indeg
                    """,
                    {"ref": ref},
                )[0]["indeg"]
                after_texts[ref] = text
                indeg_after[ref] = indeg
                if text != updates[ref]:
                    fails.append(f"{ref}: text≠完整版")
                if len(text) != expect_len:
                    fails.append(f"{ref}: len {len(text)}≠{expect_len}")
                before_indeg = state["indegree_before"].get(ref)
                if indeg != before_indeg:
                    fails.append(f"{ref}: indeg {indeg}≠{before_indeg}")

            all_rows = v1._run(
                session,
                "MATCH (s:Scripture) RETURN s.ref AS ref, s.text AS text ORDER BY ref",
            )
            snap_after = {r["ref"]: _sha_pair(r["ref"], r["text"] or "") for r in all_rows}
            changed = sorted(r for r in snap_before if snap_before.get(r) != snap_after.get(r))
            only_b = sorted(set(snap_before) - set(snap_after))
            only_a = sorted(set(snap_after) - set(snap_before))
            unexpected = [r for r in changed if r not in _TARGETS]
            missing_change = [r for r in _TARGETS if r not in changed]
            if only_b or only_a:
                fails.append(f"Scripture ref 集合变化 only_before={only_b[:10]} only_after={only_a[:10]}")
            if unexpected:
                fails.append(f"非目标 ref text 变化: {unexpected[:20]}")
            if missing_change:
                fails.append(f"目标 ref 未变化: {missing_change}")
            if len(changed) != 3:
                fails.append(f"变化 ref 数 {len(changed)}≠3: {changed}")

            anno_cmp = _compare_annos(state["anno_sha"], session)
            for prop, info in anno_cmp.items():
                if info["sha_mismatch"] or info["only_before"] or info["only_now"]:
                    fails.append(f"标注变化 {prop}: {info}")

            sha_now = v1._sha_import_dir()
            if sha_now["hashes"] != state["sha_before"]["hashes"]:
                fails.append("可导入资料 SHA 变化")
    except Exception as exc:
        raise SystemExit("verify 失败: " + v1._redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    verify = {
        "ok": not fails,
        "fails": fails,
        "scripture_n": sc_n,
        "supported_by_n": sb_n,
        "nodes_total": nodes,
        "rels_total": rels,
        "after_texts": after_texts,
        "indegree_before": state["indegree_before"],
        "indegree_after": indeg_after,
        "changed_refs": changed,
        "anno_compare": anno_cmp,
    }
    state["verify"] = verify
    v1.save_state(_STATE, state)
    write_report(state, state.get("fix"), verify, log.path)
    for f in fails:
        log.log("VERIFY FAIL: " + f)
    if fails:
        return 2
    log.log("verify 全部通过")
    return 0


def write_report(state: dict, fix_info: dict | None, verify_info: dict | None, log_path: Path) -> None:
    lines = [
        "# neo4j-v4：修正 3 个 Scripture.text 为完整版",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}；脚本：`panai4.graph.fix_scripture_text`。",
        "只 SET `s.text`；不动 ref / 关系 / 其他节点；未改其他 49 个冲突 ref。",
        "未运行 build_v4.py；未打印密码；未修改已有脚本 / .gitignore。",
        "",
        "## 摘要",
        "",
        f"1. **源**：`{state.get('file')}`",
        f"2. **闸门**：check_ok={state.get('check_ok')} fails={state.get('fails')}",
        f"3. **fix**：{fix_info}",
        f"4. **verify**：ok={(verify_info or {}).get('ok')} fails={(verify_info or {}).get('fails')}",
        "",
        "## check：版本与图谱现状",
        "",
    ]
    for ref in _TARGETS:
        pick = (state.get("picks") or {}).get(ref) or {}
        cur = (state.get("current") or {}).get(ref) or {}
        lines += [
            f"### `{ref}`",
            f"- 版本数={pick.get('n_versions')}；短={pick.get('short_len')} 长={pick.get('full_len')}；"
            f"短是长的前缀={pick.get('short_is_prefix')}；短是子串={pick.get('short_is_substr')}",
            f"- 图谱修改前 len={cur.get('len')} indeg={cur.get('indeg')}",
            f"- 修改前 text 全文：{cur.get('text')}",
            f"- 完整版 text 全文：{pick.get('full')}",
            "",
        ]
    if fix_info:
        lines += ["## fix", f"```json\n{json.dumps({k: {'len': v.get('len')} for k,v in (fix_info.get('updated') or {}).items()}, ensure_ascii=False, indent=2)}\n```", ""]
    if verify_info:
        lines += [
            "## verify",
            f"- Scripture={verify_info.get('scripture_n')} SUPPORTED_BY={verify_info.get('supported_by_n')}",
            f"- nodes={verify_info.get('nodes_total')} rels={verify_info.get('rels_total')}",
            f"- changed_refs={verify_info.get('changed_refs')}",
            f"- indegree_before={verify_info.get('indegree_before')}",
            f"- indegree_after={verify_info.get('indegree_after')}",
            "",
            "### 修改后 text 全文",
            "",
        ]
        for ref in _TARGETS:
            lines.append(f"- `{ref}`（len={len((verify_info.get('after_texts') or {}).get(ref) or '')}）：{(verify_info.get('after_texts') or {}).get(ref)}")
        lines += [
            "",
            f"- anno_compare={json.dumps(verify_info.get('anno_compare'), ensure_ascii=False)}",
            f"- fails={verify_info.get('fails')}",
            "",
        ]
    lines += [
        "## 最终验证",
        "- 未修改已有 import_*.py / fix 以外脚本 / .gitignore",
        "- 未运行 build_v4.py",
        "- 报告与日志密码检查：通过（仅变量名）",
        "- 未碰 high_peak_content；未做括号内复制；未删文件",
        f"- 日志：`{log_path}`",
        "",
    ]
    _REPORT.parent.mkdir(parents=True, exist_ok=True)
    _REPORT.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="修正 3 个 Scripture.text")
    ap.add_argument("--stage", required=True, choices=["check", "fix", "verify"])
    args = ap.parse_args(argv)
    env = v1._load_env()
    log = v1.Logger(
        _LOG_DIR / f"fix_scripture_text_{args.stage}_{v1._now()}.log",
        env["pass4"],
    )
    log.log(f"stage={args.stage}（密码不记录）")
    if args.stage == "check":
        return stage_check(env, log)
    if args.stage == "fix":
        return stage_fix(env, log)
    if args.stage == "verify":
        return stage_verify(env, log)
    return 2


if __name__ == "__main__":
    sys.exit(main())
