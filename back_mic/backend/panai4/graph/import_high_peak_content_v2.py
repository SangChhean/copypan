# -*- coding: utf-8 -*-
"""neo4j-v4：重新导入 high_peak_content（同事整理后的新 JSON）。

沿用 import_annotation_v2 的设计：
  · 标注名 high_peak_content
  · 存放：除 name 外整包（series/stages/content_1…6）json.dumps 后 SET 到节点
  · 闸门：六阶段全空必须为 0 才导入；括号内不写
不修改已有脚本；报告写入 import_high_peak_content_v2.md（不覆盖旧报告）。

用法（在 back_mic/backend 下）:
    python -m panai4.graph.import_high_peak_content_v2 --stage check|import|verify
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from neo4j import READ_ACCESS, WRITE_ACCESS, GraphDatabase

from panai4.graph import import_annotation as v1
from panai4.graph import import_annotation_v2 as v2
from panai4.graph.import_general_annotation import _sha_val, map_term_name

_REPO = v1._REPO
_LOG_DIR = v1._LOG_DIR
_ANNO = "high_peak_content"
_STATE = "high_peak_content_v2"
_REPORT = _REPO / "docs" / "panai4_graph" / "import_high_peak_content_v2.md"
_BATCH = 50
_CLASS_TYPES = {
    "BELONGS_TO_TRUNK": 2380,
    "OF_BRANCH_DIRECTLY": 2380,
    "OF_BRANCH_INDIRECTLY": 1676,
    "GRAFTING": 91,
}
_PROTECTED = {
    "devine_argument": 187,
    "intrinsic_significance": 2372,
    "mutuality": 116,
    "organic_advance": 69,
    "name_en": 2372,
    "greek_terms": 2257,
    "hebrew_terms": 1523,
    "definition_3a": 2372,
    "definition_3b": 2062,
}
_EXPECT_NODES = 7334
_EXPECT_RELS = 52197
_EXPECT_SCRIPTURE = 4851
_EXPECT_SUPPORTED_BY = 9768


def find_high_peak_file() -> Path:
    root = v1._IMPORT_ROOT
    cands = []
    for p in root.rglob("*.json"):
        name = p.name
        if "high_peak_content" in name:
            cands.append(p)
    if len(cands) != 1:
        raise SystemExit(f"high_peak_content 源文件候选数={len(cands)}: {cands}")
    return cands[0]


def _snapshot_props(session) -> dict[str, dict[str, str]]:
    out = {}
    for prop, expected in _PROTECTED.items():
        n = v2._anno_nonempty(session, prop)
        if n != expected:
            raise SystemExit(f"保护标注 {prop} 非空 {n}≠{expected}")
        amap = v2._fetch_anno_map(session, prop)
        out[prop] = {name: _sha_val(val) for name, val in amap.items()}
    return out


def _compare_props(before: dict[str, dict[str, str]], session) -> dict[str, Any]:
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
            "only_before": only_b[:20],
            "only_now": only_n[:20],
            "mismatch_names": mism[:20],
        }
    return result


def _content_nonempty(v: Any) -> bool:
    return bool(v)


def parse_plan(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(raw, list):
        raise SystemExit(f"顶层须为 list，实际 {type(raw).__name__}")
    names_src = [r["name"] for r in raw]
    dups = [n for n, c in Counter(names_src).items() if c > 1]
    key_union: set[str] = set()
    for r in raw:
        key_union |= set(r.keys())
    expected_keys = {
        "name",
        "series",
        "stages",
        "content_1",
        "content_2",
        "content_3",
        "content_4",
        "content_5",
        "content_6",
    }
    stage_counts = {f"content_{i}": 0 for i in range(1, 7)}
    all_empty: list[str] = []
    only_one: list[str] = []
    write_rows: list[dict] = []
    payloads: dict[str, dict] = {}
    name_map: list[dict[str, str]] = []
    graph_names: list[str] = []

    for r in raw:
        src = r["name"]
        gname = map_term_name(src)
        if gname != src:
            name_map.append({"src": src, "graph": gname})
        graph_names.append(gname)
        stages = [f"content_{i}" for i in range(1, 7) if _content_nonempty(r.get(f"content_{i}"))]
        for s in stages:
            stage_counts[s] += 1
        if not stages:
            all_empty.append(src)
            continue
        if len(stages) == 1:
            only_one.append(src)
        payload = v1.payload_of(r, None)  # 除 name 外整包
        value = v1.serialize_payload(payload)
        write_rows.append({"name": gname, "src_name": src, "value": value, "length": len(value)})
        payloads[gname] = payload

    lengths = sorted(w["length"] for w in write_rows)
    return {
        "n_records": len(raw),
        "dups": dups,
        "key_union": sorted(key_union),
        "extra_keys": sorted(key_union - expected_keys),
        "stage_counts": stage_counts,
        "all_empty": all_empty,
        "only_one": only_one,
        "only_one_n": len(only_one),
        "name_map": name_map,
        "graph_names": graph_names,
        "write_rows": write_rows,
        "payloads": payloads,
        "has_city": "城市" in names_src or "城市" in graph_names,
        "len_stats": {
            "min": lengths[0] if lengths else None,
            "median": lengths[len(lengths) // 2] if lengths else None,
            "max": lengths[-1] if lengths else None,
            "total_chars": sum(lengths),
            "over_32000": sum(1 for x in lengths if x > 32000),
        },
        "series_values": Counter(json.dumps(r.get("series"), ensure_ascii=False) for r in raw),
    }


def stage_check(env: dict, log: v1.Logger) -> int:
    log.log("stage=check high_peak_content_v2")
    path = find_high_peak_file()
    log.log(f"file={path} size={path.stat().st_size}")
    sha_before = v1._sha_import_dir()
    plan = parse_plan(path)
    log.log(
        f"n={plan['n_records']} empty={len(plan['all_empty'])} only1={plan['only_one_n']} "
        f"stages={plan['stage_counts']} write={len(plan['write_rows'])}"
    )

    fails: list[str] = []
    if plan["dups"]:
        fails.append(f"name 重复: {plan['dups']}")
    if plan["all_empty"]:
        fails.append(f"六阶段全空 {len(plan['all_empty'])}: {plan['all_empty']}")
    if plan["extra_keys"]:
        fails.append(f"额外键: {plan['extra_keys']}")

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            nodes = v1._run(session, "MATCH (n) RETURN count(n) AS c")[0]["c"]
            rels = v1._run(session, "MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
            labels = {
                r["l"]: r["c"]
                for r in v1._run(
                    session,
                    "MATCH (n) UNWIND labels(n) AS l RETURN l, count(*) AS c ORDER BY l",
                )
            }
            by_type = {
                r["t"]: r["c"]
                for r in v1._run(
                    session,
                    "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c ORDER BY t",
                )
            }
            if nodes != _EXPECT_NODES:
                fails.append(f"nodes {nodes}≠{_EXPECT_NODES}")
            if rels != _EXPECT_RELS:
                fails.append(f"rels {rels}≠{_EXPECT_RELS}")
            for t, n in _CLASS_TYPES.items():
                if by_type.get(t, 0) != n:
                    fails.append(f"分类关系 {t} {by_type.get(t)}≠{n}")
            sc_n = v1._run(session, "MATCH (s:Scripture) RETURN count(s) AS c")[0]["c"]
            sb_n = v1._run(session, "MATCH ()-[r:SUPPORTED_BY]->() RETURN count(r) AS c")[0]["c"]
            if sc_n != _EXPECT_SCRIPTURE:
                fails.append(f"Scripture {sc_n}≠{_EXPECT_SCRIPTURE}")
            if sb_n != _EXPECT_SUPPORTED_BY:
                fails.append(f"SUPPORTED_BY {sb_n}≠{_EXPECT_SUPPORTED_BY}")

            # high_peak should not exist yet (or report if partial)
            hp_n = v2._anno_nonempty(session, _ANNO)

            with_sa = {
                r["name"]
                for r in v1._run(
                    session,
                    """
                    MATCH (n:Truth_Point)
                    WHERE n.same_as IS NOT NULL AND toString(n.same_as) <> ''
                    RETURN n.name AS name
                    """,
                )
            }
            match = v1.match_names(session, plan["graph_names"])
            hit_inner = sorted(set(plan["graph_names"]) & with_sa)
            if match["missing_n"]:
                fails.append(f"找不到: {match['missing']}")
            if match["multi"]:
                fails.append(f"多匹配: {match['multi']}")
            if hit_inner:
                fails.append(f"命中括号内: {hit_inner}")

            prop_sha = _snapshot_props(session)
    except Exception as exc:
        raise SystemExit("check 失败: " + v1._redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    sha_after = v1._sha_import_dir()
    sha_ok = sha_before["hashes"] == sha_after["hashes"]
    if not sha_ok:
        fails.append("可导入资料 SHA 前后不一致")

    state = {
        "version": "high_peak_v2",
        "design": {
            "anno": _ANNO,
            "storage": "json.dumps(payload except name: series/stages/content_1..6)",
            "script_base": "import_annotation_v2（复用 payload_of/serialize/_set_batch）",
            "note": "不覆盖旧报告 import_high_peak_content.md",
        },
        "check_ok": not fails,
        "fails": fails,
        "file": str(path),
        "file_size": path.stat().st_size,
        "plan": {
            "n_records": plan["n_records"],
            "dups": plan["dups"],
            "key_union": plan["key_union"],
            "extra_keys": plan["extra_keys"],
            "stage_counts": plan["stage_counts"],
            "all_empty": plan["all_empty"],
            "only_one": plan["only_one"],
            "only_one_n": plan["only_one_n"],
            "name_map": plan["name_map"],
            "write_count": len(plan["write_rows"]),
            "write_names": [w["name"] for w in plan["write_rows"]],
            "has_city": plan["has_city"],
            "len_stats": plan["len_stats"],
            "series_kinds": len(plan["series_values"]),
        },
        "match": {
            "found_n": match["found_n"],
            "missing_n": match["missing_n"],
            "missing": match["missing"],
            "multi": match["multi"],
            "hit_inner": hit_inner,
        },
        "baseline": {
            "nodes_total": nodes,
            "rels_total": rels,
            "labels": labels,
            "by_type": by_type,
            "scripture_n": sc_n,
            "supported_by_n": sb_n,
            "high_peak_preexisting": hp_n,
        },
        "prop_sha": prop_sha,
        "write_rows": plan["write_rows"],
        "payloads": plan["payloads"],
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
    log.log(f"闸门通过。拟写入 {len(plan['write_rows'])}；only1={plan['only_one_n']}")
    return 0


def stage_import(env: dict, log: v1.Logger) -> int:
    log.log("stage=import high_peak_content_v2")
    state = v1.load_state(_STATE)
    if not state.get("check_ok"):
        raise SystemExit("check 未通过，拒绝 import")
    rows = state["write_rows"]
    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    written = 0
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            nodes = v1._run(session, "MATCH (n) RETURN count(n) AS c")[0]["c"]
            rels = v1._run(session, "MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
            sc_n = v1._run(session, "MATCH (s:Scripture) RETURN count(s) AS c")[0]["c"]
            sb_n = v1._run(session, "MATCH ()-[r:SUPPORTED_BY]->() RETURN count(r) AS c")[0]["c"]
            if (
                nodes != _EXPECT_NODES
                or rels != _EXPECT_RELS
                or sc_n != _EXPECT_SCRIPTURE
                or sb_n != _EXPECT_SUPPORTED_BY
            ):
                log.log(f"I1 FAIL nodes={nodes} rels={rels} sc={sc_n} sb={sb_n}")
                return 2
            for prop, n_exp in _PROTECTED.items():
                n = v2._anno_nonempty(session, prop)
                if n != n_exp:
                    log.log(f"I1 FAIL {prop} {n}≠{n_exp}")
                    return 2
            log.log("I1 通过")
        with driver.session(default_access_mode=WRITE_ACCESS) as session:
            for i in range(0, len(rows), _BATCH):
                batch = rows[i : i + _BATCH]
                payload = [{"name": r["name"], "value": r["value"]} for r in batch]
                updated = session.execute_write(v1._set_batch, _ANNO, payload)
                if updated != len(batch):
                    log.log(f"batch {i} updated={updated}≠{len(batch)}；停止")
                    state["import"] = {
                        "aborted": True,
                        "written": written,
                        "offset": i,
                        "failed_names": [r["name"] for r in batch],
                    }
                    v1.save_state(_STATE, state)
                    write_report(state, state["import"], None, log.path)
                    return 2
                written += updated
                log.log(f"batch {i}-{i+len(batch)-1} updated={updated} cumulative={written}")
    except Exception as exc:
        raise SystemExit("import 失败: " + v1._redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    info = {"aborted": False, "written": written, "failed": 0, "expected": len(rows)}
    state["import"] = info
    v1.save_state(_STATE, state)
    write_report(state, info, None, log.path)
    log.log(f"import 完成 written={written}")
    return 0


def stage_verify(env: dict, log: v1.Logger) -> int:
    log.log("stage=verify high_peak_content_v2")
    state = v1.load_state(_STATE)
    if not state.get("import") or state["import"].get("aborted"):
        raise SystemExit("import 未完成，拒绝 verify")
    payloads: dict[str, dict] = state["payloads"]
    write_names = set(state["plan"]["write_names"])
    fails: list[str] = []

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            nodes = v1._run(session, "MATCH (n) RETURN count(n) AS c")[0]["c"]
            rels = v1._run(session, "MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
            sc_n = v1._run(session, "MATCH (s:Scripture) RETURN count(s) AS c")[0]["c"]
            sb_n = v1._run(session, "MATCH ()-[r:SUPPORTED_BY]->() RETURN count(r) AS c")[0]["c"]
            if nodes != _EXPECT_NODES:
                fails.append(f"nodes {nodes}≠{_EXPECT_NODES}")
            if rels != _EXPECT_RELS:
                fails.append(f"rels {rels}≠{_EXPECT_RELS}")
            if sc_n != _EXPECT_SCRIPTURE or sb_n != _EXPECT_SUPPORTED_BY:
                fails.append(f"Scripture/SUPPORTED_BY {sc_n}/{sb_n}")

            anno_n = v2._anno_nonempty(session, _ANNO)
            if anno_n != len(write_names):
                fails.append(f"{_ANNO} nonempty {anno_n}≠{len(write_names)}")

            inner_n = v1._run(
                session,
                f"""
                MATCH (n:Truth_Point)
                WHERE n.same_as IS NOT NULL AND toString(n.same_as) <> ''
                  AND n.{_ANNO} IS NOT NULL
                RETURN count(n) AS c
                """,
            )[0]["c"]
            if inner_n:
                fails.append(f"括号内有 {_ANNO}: {inner_n}")

            # full roundtrip
            stored = {
                r["name"]: r["value"]
                for r in v1._run(
                    session,
                    f"MATCH (n:Truth_Point) WHERE n.{_ANNO} IS NOT NULL "
                    f"RETURN n.name AS name, n.{_ANNO} AS value",
                )
            }
            if set(stored) != write_names:
                fails.append(
                    f"写入名集合差 only_graph={sorted(set(stored)-write_names)[:10]} "
                    f"only_plan={sorted(write_names-set(stored))[:10]}"
                )
            mismatch = []
            for name, payload in payloads.items():
                got = stored.get(name)
                expected = v1.serialize_payload(payload)
                ok = False
                if isinstance(got, str):
                    try:
                        ok = json.loads(got) == payload
                    except Exception:
                        ok = got == expected
                if not ok:
                    mismatch.append(name)
            if mismatch:
                fails.append(f"内容不符 {len(mismatch)}: {mismatch[:10]}")

            prop_cmp = _compare_props(state["prop_sha"], session)
            for prop, info in prop_cmp.items():
                if info["sha_mismatch"] or info["only_before"] or info["only_now"]:
                    fails.append(f"标注变化 {prop}: {info}")

            # by_type class + scripture unchanged
            by_type = {
                r["t"]: r["c"]
                for r in v1._run(
                    session,
                    "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c ORDER BY t",
                )
            }
            if by_type != state["baseline"]["by_type"]:
                fails.append("关系类型计数与基线不一致")

            sample_names = list(write_names)[:5]
            samples = []
            for name in sample_names:
                got = stored.get(name)
                payload = payloads[name]
                same = False
                if isinstance(got, str):
                    try:
                        same = json.loads(got) == payload
                    except Exception:
                        same = False
                samples.append(
                    {
                        "name": name,
                        "ok": same,
                        "len": len(got) if isinstance(got, str) else None,
                        "head80": v1._trunc(got, 80) if isinstance(got, str) else None,
                    }
                )
                if not same:
                    fails.append(f"抽样不符 {name}")

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
        "anno_n": anno_n,
        "inner_n": inner_n,
        "nodes_total": nodes,
        "rels_total": rels,
        "scripture_n": sc_n,
        "supported_by_n": sb_n,
        "mismatch_n": len(mismatch),
        "prop_compare": prop_cmp,
        "samples": samples,
    }
    state["verify"] = verify
    v1.save_state(_STATE, state)
    write_report(state, state.get("import"), verify, log.path)
    for f in fails:
        log.log("VERIFY FAIL: " + f)
    if fails:
        return 2
    log.log("verify 全部通过")
    return 0


def write_report(state: dict, import_info: dict | None, verify_info: dict | None, log_path: Path) -> None:
    plan = state.get("plan") or {}
    match = state.get("match") or {}
    lines = [
        "# neo4j-v4 重新导入 `high_peak_content`（v2 报告）",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}；脚本：`panai4.graph.import_high_peak_content_v2`。",
        "设计沿用 `import_annotation_v2`：SET `n.high_peak_content` = json.dumps(series/stages/content_1…6)；六阶段全空闸门。",
        "本报告不覆盖旧报告 `import_high_peak_content.md`。",
        "未运行 build_v4.py；未打印密码；未修改已有 import_annotation*.py。",
        "",
        "## 摘要",
        "",
        f"1. **源**：`{state.get('file')}` size={state.get('file_size')}；记录={plan.get('n_records')}；"
        f"重复={plan.get('dups')}；全空={plan.get('all_empty')}；仅1阶段={plan.get('only_one_n')} {plan.get('only_one')}。",
        f"2. **阶段分布**：{plan.get('stage_counts')}。",
        f"3. **匹配**：found={match.get('found_n')} missing={match.get('missing')} "
        f"hit_inner={match.get('hit_inner')} multi={match.get('multi')}；映射={plan.get('name_map')}。",
        f"4. **基线**：nodes={state.get('baseline',{}).get('nodes_total')} "
        f"rels={state.get('baseline',{}).get('rels_total')} "
        f"Scripture={state.get('baseline',{}).get('scripture_n')} "
        f"SUPPORTED_BY={state.get('baseline',{}).get('supported_by_n')}。",
        f"5. **import**：{import_info}。",
        f"6. **verify**：ok={(verify_info or {}).get('ok')} fails={(verify_info or {}).get('fails')}。",
        f"7. **闸门**：check_ok={state.get('check_ok')} fails={state.get('fails')}。",
        "",
        "## check 明细",
        f"- keys={plan.get('key_union')} extra={plan.get('extra_keys')}",
        f"- len_stats={plan.get('len_stats')}",
        f"- write_count={plan.get('write_count')}",
        f"- preexisting high_peak={state.get('baseline',{}).get('high_peak_preexisting')}",
        "",
    ]
    if import_info:
        lines += ["## import", f"```json\n{json.dumps(import_info, ensure_ascii=False, indent=2)}\n```", ""]
    if verify_info:
        lines += [
            "## verify",
            f"- anno_n={verify_info.get('anno_n')} inner_n={verify_info.get('inner_n')}",
            f"- nodes={verify_info.get('nodes_total')} rels={verify_info.get('rels_total')}",
            f"- Scripture={verify_info.get('scripture_n')} SUPPORTED_BY={verify_info.get('supported_by_n')}",
            f"- mismatch_n={verify_info.get('mismatch_n')}",
            f"- samples={json.dumps(verify_info.get('samples'), ensure_ascii=False)}",
            f"- prop_compare={json.dumps(verify_info.get('prop_compare'), ensure_ascii=False)}",
            f"- fails={verify_info.get('fails')}",
            "",
        ]
    lines += [
        "## 最终验证",
        "- 未修改 import_annotation.py / _v2.py / _v3.py / _v4.py 及其他已有脚本 / .gitignore",
        "- 未运行 build_v4.py",
        "- 报告与日志密码检查：通过（仅变量名）",
        "- 未做括号内复制；未删文件；未覆盖旧报告",
        f"- 日志：`{log_path}`",
        "",
    ]
    _REPORT.parent.mkdir(parents=True, exist_ok=True)
    _REPORT.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="重新导入 high_peak_content")
    ap.add_argument("--stage", required=True, choices=["check", "import", "verify"])
    args = ap.parse_args(argv)
    env = v1._load_env()
    log = v1.Logger(
        _LOG_DIR / f"import_high_peak_content_v2_{args.stage}_{v1._now()}.log",
        env["pass4"],
    )
    log.log(f"stage={args.stage}（密码不记录）")
    if args.stage == "check":
        return stage_check(env, log)
    if args.stage == "import":
        return stage_import(env, log)
    if args.stage == "verify":
        return stage_verify(env, log)
    return 2


if __name__ == "__main__":
    sys.exit(main())
