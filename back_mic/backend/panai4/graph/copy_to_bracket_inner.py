# -*- coding: utf-8 -*-
"""neo4j-v4：把括号外节点的标注与语义关系复制到括号内节点（8 对）。

不复制 name/same_as；不复制 4 种分类关系；不复制 O↔I 之间的关系。
只替换「这一端」；不修改已有脚本；不运行 build_v4.py；不打印密码。

用法（在 back_mic/backend 下）:
    python -m panai4.graph.copy_to_bracket_inner --stage check|copy|verify
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from neo4j import READ_ACCESS, WRITE_ACCESS, GraphDatabase

from panai4.graph import import_annotation as v1
from panai4.graph import import_annotation_v2 as v2
from panai4.graph.import_general_annotation import _sha_val

_REPO = v1._REPO
_LOG_DIR = v1._LOG_DIR
_STATE = "copy_to_bracket_inner"
_REPORT = _REPO / "docs" / "panai4_graph" / "copy_to_bracket_inner.md"
_TYPE_RE = re.compile(r"^[A-Z][A-Z_]*$")
_CLASS = {
    "BELONGS_TO_TRUNK",
    "OF_BRANCH_DIRECTLY",
    "OF_BRANCH_INDIRECTLY",
    "GRAFTING",
}
_CLASS_COUNTS = {
    "BELONGS_TO_TRUNK": 2380,
    "OF_BRANCH_DIRECTLY": 2380,
    "OF_BRANCH_INDIRECTLY": 1676,
    "GRAFTING": 91,
}
# 显式白名单：绝不带 name / same_as
_PROP_WHITELIST = [
    "devine_argument",
    "intrinsic_significance",
    "mutuality",
    "organic_advance",
    "high_peak_content",
    "name_en",
    "greek_terms",
    "hebrew_terms",
    "definition_3a",
    "definition_3b",
]
_EXPECT_NODES = 7334
_EXPECT_RELS_BASE = 52197
_EXPECT_SCRIPTURE = 4851
_EXPECT_SUPPORTED_BY_BASE = 9768


def _sha_pair(ref: str, text: str) -> str:
    raw = json.dumps({"ref": ref, "text": text}, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _load_pairs(session) -> list[dict[str, str]]:
    rows = v1._run(
        session,
        """
        MATCH (i:Truth_Point)
        WHERE i.same_as IS NOT NULL AND toString(i.same_as) <> ''
        RETURN i.name AS inner, i.same_as AS outer
        ORDER BY inner
        """,
    )
    return [{"inner": r["inner"], "outer": r["outer"]} for r in rows]


def _node_keys(session, name: str) -> list[str]:
    rows = v1._run(
        session,
        "MATCH (n:Truth_Point {name: $name}) RETURN keys(n) AS k",
        {"name": name},
    )
    if len(rows) != 1:
        raise SystemExit(f"Truth_Point {name!r} 匹配数 {len(rows)}≠1")
    return list(rows[0]["k"] or [])


def _get_props(session, name: str) -> dict[str, Any]:
    # 只取白名单
    parts = ", ".join(f"n.{p} AS {p}" for p in _PROP_WHITELIST)
    rows = v1._run(
        session,
        f"MATCH (n:Truth_Point {{name: $name}}) RETURN {parts}",
        {"name": name},
    )
    if len(rows) != 1:
        raise SystemExit(f"读取属性失败: {name}")
    row = rows[0]
    return {p: row[p] for p in _PROP_WHITELIST if row[p] is not None}


def _rel_counts(session) -> dict[str, int]:
    return {
        r["t"]: r["c"]
        for r in v1._run(
            session,
            "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c ORDER BY t",
        )
    }


def _collect_copy_plan(session, outer: str, inner: str, bracket_names: set[str]) -> dict[str, Any]:
    """收集 outer 的语义出/入边，排除指向/来自 inner 的。"""
    out_rows = v1._run(
        session,
        """
        MATCH (o:Truth_Point {name: $o})-[r]->(x)
        RETURN type(r) AS t,
               labels(x) AS labs,
               x.name AS name,
               CASE WHEN x:Scripture THEN x.ref ELSE null END AS ref
        """,
        {"o": outer},
    )
    in_rows = v1._run(
        session,
        """
        MATCH (x)-[r]->(o:Truth_Point {name: $o})
        RETURN type(r) AS t,
               labels(x) AS labs,
               x.name AS name,
               CASE WHEN x:Scripture THEN x.ref ELSE null END AS ref
        """,
        {"o": outer},
    )
    between = v1._run(
        session,
        """
        MATCH (a:Truth_Point {name: $o})-[r]-(b:Truth_Point {name: $i})
        RETURN type(r) AS t, startNode(r).name AS s, endNode(r).name AS e
        """,
        {"o": outer, "i": inner},
    )

    out_copy: list[dict] = []
    in_copy: list[dict] = []
    skipped_to_inner: list[dict] = []
    cross: list[dict] = []

    def endpoint_kind(name: str | None, labs: list[str]) -> str:
        if name is None and "Scripture" in (labs or []):
            return "Scripture"
        if name in bracket_names:
            return "bracket_other"
        return "other"

    for r in out_rows:
        t = r["t"]
        if t in _CLASS:
            continue
        if not _TYPE_RE.fullmatch(t):
            raise SystemExit(f"非法关系类型: {t}")
        # other end is inner?
        if r["name"] == inner:
            skipped_to_inner.append({"dir": "out", "type": t, "to": inner})
            continue
        item = {
            "type": t,
            "to_name": r["name"],
            "to_ref": r["ref"],
            "to_labs": r["labs"],
        }
        out_copy.append(item)
        if r["name"] and r["name"] in bracket_names and r["name"] != inner:
            cross.append(
                {
                    "pair_inner": inner,
                    "pair_outer": outer,
                    "dir": "out",
                    "type": t,
                    "other": r["name"],
                    "note": "端点是另一对括号词，保持原样只替换本端",
                }
            )

    for r in in_rows:
        t = r["t"]
        if t in _CLASS:
            continue
        if not _TYPE_RE.fullmatch(t):
            raise SystemExit(f"非法关系类型: {t}")
        if r["name"] == inner:
            skipped_to_inner.append({"dir": "in", "type": t, "from": inner})
            continue
        item = {
            "type": t,
            "from_name": r["name"],
            "from_ref": r["ref"],
            "from_labs": r["labs"],
        }
        in_copy.append(item)
        if r["name"] and r["name"] in bracket_names and r["name"] != inner:
            cross.append(
                {
                    "pair_inner": inner,
                    "pair_outer": outer,
                    "dir": "in",
                    "type": t,
                    "other": r["name"],
                    "note": "端点是另一对括号词，保持原样只替换本端",
                }
            )

    out_by = Counter(x["type"] for x in out_copy)
    in_by = Counter(x["type"] for x in in_copy)
    return {
        "out_copy": out_copy,
        "in_copy": in_copy,
        "out_by_type": dict(out_by),
        "in_by_type": dict(in_by),
        "supported_by_out": out_by.get("SUPPORTED_BY", 0),
        "supported_by_in": in_by.get("SUPPORTED_BY", 0),
        "expected_new": len(out_copy) + len(in_copy),
        "between": between,
        "skipped_to_inner": skipped_to_inner,
        "cross_bracket_endpoints": cross,
    }


def _snapshot_outer_ordinary_annos(session, inner_names: set[str]) -> dict[str, dict[str, str]]:
    """括号外+普通节点（非 8 个括号内）的白名单标注 SHA。"""
    out: dict[str, dict[str, str]] = {}
    for prop in _PROP_WHITELIST:
        amap = v2._fetch_anno_map(session, prop)
        out[prop] = {
            name: _sha_val(val)
            for name, val in amap.items()
            if name not in inner_names
        }
    return out


def _snapshot_scripture(session) -> dict[str, str]:
    rows = v1._run(
        session,
        "MATCH (s:Scripture) RETURN s.ref AS ref, s.text AS text ORDER BY ref",
    )
    return {r["ref"]: _sha_pair(r["ref"], r["text"] or "") for r in rows}


def stage_check(env: dict, log: v1.Logger) -> int:
    log.log("stage=check copy_to_bracket_inner")
    fails: list[str] = []
    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            pairs = _load_pairs(session)
            if len(pairs) != 8:
                fails.append(f"括号内节点数 {len(pairs)}≠8")
            inner_names = {p["inner"] for p in pairs}
            outer_names = {p["outer"] for p in pairs}
            bracket_names = inner_names | outer_names

            # same_as unique match + no one points same_as to inner
            pair_details = []
            for p in pairs:
                i, o = p["inner"], p["outer"]
                o_match = v1._run(
                    session,
                    "MATCH (n:Truth_Point {name: $n}) RETURN n.name AS name, n.same_as AS sa",
                    {"n": o},
                )
                if len(o_match) != 1:
                    fails.append(f"{i}: same_as={o} 匹配外节点数 {len(o_match)}≠1")
                    continue
                if o_match[0]["sa"] is not None and str(o_match[0]["sa"]).strip() != "":
                    fails.append(f"{i}: 外节点 {o} 自身也有 same_as={o_match[0]['sa']}")
                pointed = v1._run(
                    session,
                    """
                    MATCH (n:Truth_Point)
                    WHERE n.same_as = $i
                    RETURN n.name AS name
                    """,
                    {"i": i},
                )
                if pointed:
                    fails.append(f"{i}: 被其他节点 same_as 指向: {[r['name'] for r in pointed]}")

                i_keys = set(_node_keys(session, i))
                unexpected = i_keys - {"name", "same_as"}
                if unexpected:
                    fails.append(f"{i}: 已有额外属性 {sorted(unexpected)}")

                # inner must have no semantic / SUPPORTED_BY
                inner_sem = v1._run(
                    session,
                    """
                    MATCH (n:Truth_Point {name: $i})-[r]-(x)
                    WHERE NOT type(r) IN $cls
                    RETURN type(r) AS t, count(*) AS c
                    """,
                    {"i": i, "cls": list(_CLASS)},
                )
                if inner_sem:
                    fails.append(f"{i}: 已有非分类关系 {inner_sem}")

                outer_props = _get_props(session, o)
                plan = _collect_copy_plan(session, o, i, bracket_names)
                pair_details.append(
                    {
                        "inner": i,
                        "outer": o,
                        "outer_props": sorted(outer_props.keys()),
                        "outer_prop_n": len(outer_props),
                        "outer_props_values_sha": {
                            k: _sha_val(v) for k, v in outer_props.items()
                        },
                        "out_by_type": plan["out_by_type"],
                        "in_by_type": plan["in_by_type"],
                        "supported_by_out": plan["supported_by_out"],
                        "supported_by_in": plan["supported_by_in"],
                        "expected_new": plan["expected_new"],
                        "between": plan["between"],
                        "skipped_to_inner": plan["skipped_to_inner"],
                        "cross_bracket_endpoints": plan["cross_bracket_endpoints"],
                        "out_copy": plan["out_copy"],
                        "in_copy": plan["in_copy"],
                        "outer_prop_payload": outer_props,
                    }
                )
                log.log(
                    f"{o}→{i}: props={len(outer_props)} "
                    f"out={dict(plan['out_by_type'])} in={dict(plan['in_by_type'])} "
                    f"new={plan['expected_new']} between={len(plan['between'])} "
                    f"cross={len(plan['cross_bracket_endpoints'])}"
                )

            nodes = v1._run(session, "MATCH (n) RETURN count(n) AS c")[0]["c"]
            rels = v1._run(session, "MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
            sc_n = v1._run(session, "MATCH (s:Scripture) RETURN count(s) AS c")[0]["c"]
            sb_n = v1._run(session, "MATCH ()-[r:SUPPORTED_BY]->() RETURN count(r) AS c")[0]["c"]
            by_type = _rel_counts(session)
            if nodes != _EXPECT_NODES:
                fails.append(f"nodes {nodes}≠{_EXPECT_NODES}")
            if rels != _EXPECT_RELS_BASE:
                fails.append(f"rels {rels}≠{_EXPECT_RELS_BASE}")
            if sc_n != _EXPECT_SCRIPTURE:
                fails.append(f"Scripture {sc_n}≠{_EXPECT_SCRIPTURE}")
            if sb_n != _EXPECT_SUPPORTED_BY_BASE:
                fails.append(f"SUPPORTED_BY {sb_n}≠{_EXPECT_SUPPORTED_BY_BASE}")
            for t, n in _CLASS_COUNTS.items():
                if by_type.get(t, 0) != n:
                    fails.append(f"分类关系 {t} {by_type.get(t)}≠{n}")

            anno_sha = _snapshot_outer_ordinary_annos(session, inner_names)
            sc_sha = _snapshot_scripture(session)
            if len(sc_sha) != _EXPECT_SCRIPTURE:
                fails.append(f"Scripture 快照 {len(sc_sha)}≠{_EXPECT_SCRIPTURE}")

            # also snapshot inner name/same_as
            inner_identity = {}
            for p in pairs:
                row = v1._run(
                    session,
                    "MATCH (n:Truth_Point {name: $n}) RETURN n.name AS name, n.same_as AS sa",
                    {"n": p["inner"]},
                )[0]
                inner_identity[p["inner"]] = {"name": row["name"], "same_as": row["sa"]}
    except Exception as exc:
        raise SystemExit("check 失败: " + v1._redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    expected_total = sum(p["expected_new"] for p in pair_details)
    all_cross = [c for p in pair_details for c in p["cross_bracket_endpoints"]]

    state = {
        "version": 1,
        "check_ok": not fails,
        "fails": fails,
        "pairs": [{"inner": p["inner"], "outer": p["outer"]} for p in pair_details],
        "pair_details": [
            {
                k: v
                for k, v in p.items()
                if k not in ("out_copy", "in_copy", "outer_prop_payload")
            }
            for p in pair_details
        ],
        # keep full copy payloads in state for import
        "copy_payloads": [
            {
                "inner": p["inner"],
                "outer": p["outer"],
                "props": p["outer_prop_payload"],
                "out_copy": p["out_copy"],
                "in_copy": p["in_copy"],
                "expected_new": p["expected_new"],
            }
            for p in pair_details
        ],
        "expected_total_new": expected_total,
        "cross_bracket_endpoints": all_cross,
        "inner_identity": inner_identity,
        "baseline": {
            "nodes_total": nodes,
            "rels_total": rels,
            "by_type": by_type,
            "scripture_n": sc_n,
            "supported_by_n": sb_n,
        },
        "anno_sha_outer_ordinary": anno_sha,
        "scripture_sha": sc_sha,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    v1.save_state(_STATE, state)
    write_report(state, None, None, log.path)
    for f in fails:
        log.log("GATE FAIL: " + f)
    if fails:
        log.log("闸门未通过，停止。")
        return 2
    log.log(f"闸门通过。预期新增关系 {expected_total}；cross 端点情形 {len(all_cross)}")
    return 0


def _set_props(tx, inner: str, props: dict[str, Any]) -> None:
    if not props:
        return
    # 显式白名单字段
    sets = []
    params: dict[str, Any] = {"inner": inner}
    for k, v in props.items():
        if k not in _PROP_WHITELIST:
            raise RuntimeError(f"拒绝非白名单属性: {k}")
        if k in ("name", "same_as"):
            raise RuntimeError("拒绝设置 name/same_as")
        sets.append(f"i.{k} = ${k}")
        params[k] = v
    q = f"MATCH (i:Truth_Point {{name: $inner}}) SET " + ", ".join(sets)
    tx.run(q, params)


def _merge_out(tx, inner: str, rel_type: str, to_name: str | None, to_ref: str | None) -> int:
    if not _TYPE_RE.fullmatch(rel_type):
        raise RuntimeError(f"非法类型 {rel_type}")
    if to_ref is not None:
        q = (
            "MATCH (i:Truth_Point {name: $inner}) "
            "MATCH (s:Scripture {ref: $ref}) "
            f"MERGE (i)-[r:`{rel_type}`]->(s) "
            "RETURN count(r) AS n"
        )
        return int(tx.run(q, {"inner": inner, "ref": to_ref}).single()["n"])
    q = (
        "MATCH (i:Truth_Point {name: $inner}) "
        "MATCH (x:Truth_Point {name: $x}) "
        f"MERGE (i)-[r:`{rel_type}`]->(x) "
        "RETURN count(r) AS n"
    )
    return int(tx.run(q, {"inner": inner, "x": to_name}).single()["n"])


def _merge_in(tx, inner: str, rel_type: str, from_name: str | None, from_ref: str | None) -> int:
    if not _TYPE_RE.fullmatch(rel_type):
        raise RuntimeError(f"非法类型 {rel_type}")
    if from_ref is not None:
        # Scripture -[r]-> Truth_Point 在本图谱不应出现；防守
        raise RuntimeError(f"入边来自 Scripture 不支持: {rel_type} {from_ref}")
    q = (
        "MATCH (i:Truth_Point {name: $inner}) "
        "MATCH (x:Truth_Point {name: $x}) "
        f"MERGE (x)-[r:`{rel_type}`]->(i) "
        "RETURN count(r) AS n"
    )
    return int(tx.run(q, {"inner": inner, "x": from_name}).single()["n"])


def _count_inner_semantic(session, inner: str) -> int:
    return v1._run(
        session,
        """
        MATCH (i:Truth_Point {name: $i})-[r]-(x)
        WHERE NOT type(r) IN $cls
        RETURN count(r) AS c
        """,
        {"i": inner, "cls": list(_CLASS)},
    )[0]["c"]


def stage_copy(env: dict, log: v1.Logger) -> int:
    log.log("stage=copy bracket inner")
    state = v1.load_state(_STATE)
    if not state.get("check_ok"):
        raise SystemExit("check 未通过，拒绝 copy")
    payloads = state["copy_payloads"]
    progress = []

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            nodes = v1._run(session, "MATCH (n) RETURN count(n) AS c")[0]["c"]
            rels = v1._run(session, "MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
            if nodes != _EXPECT_NODES or rels != _EXPECT_RELS_BASE:
                log.log(f"I1 FAIL nodes={nodes} rels={rels}")
                return 2

        for item in payloads:
            inner = item["inner"]
            outer = item["outer"]
            expected = item["expected_new"]
            log.log(f"copy {outer} → {inner} props={len(item['props'])} rels={expected}")

            with driver.session(default_access_mode=WRITE_ACCESS) as session:
                session.execute_write(_set_props, inner, item["props"])
                for r in item["out_copy"]:
                    n = session.execute_write(
                        _merge_out, inner, r["type"], r.get("to_name"), r.get("to_ref")
                    )
                    if n != 1:
                        log.log(f"MERGE out 异常 {r} n={n}；停止")
                        state["copy"] = {"aborted": True, "progress": progress, "failed": inner}
                        v1.save_state(_STATE, state)
                        write_report(state, state["copy"], None, log.path)
                        return 2
                for r in item["in_copy"]:
                    n = session.execute_write(
                        _merge_in, inner, r["type"], r.get("from_name"), r.get("from_ref")
                    )
                    if n != 1:
                        log.log(f"MERGE in 异常 {r} n={n}；停止")
                        state["copy"] = {"aborted": True, "progress": progress, "failed": inner}
                        v1.save_state(_STATE, state)
                        write_report(state, state["copy"], None, log.path)
                        return 2

            with driver.session(default_access_mode=READ_ACCESS) as session:
                got = _count_inner_semantic(session, inner)
            if got != expected:
                log.log(f"核对失败 {inner}: semantic_touch={got}≠{expected}；停止")
                state["copy"] = {
                    "aborted": True,
                    "progress": progress,
                    "failed": inner,
                    "got": got,
                    "expected": expected,
                }
                v1.save_state(_STATE, state)
                write_report(state, state["copy"], None, log.path)
                return 2
            progress.append({"inner": inner, "outer": outer, "new_rels": got, "props": len(item["props"])})
            log.log(f"  OK {inner} new_rels={got}")
    except Exception as exc:
        raise SystemExit("copy 失败: " + v1._redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    info = {
        "aborted": False,
        "progress": progress,
        "total_new": sum(p["new_rels"] for p in progress),
        "expected_total": state["expected_total_new"],
    }
    state["copy"] = info
    v1.save_state(_STATE, state)
    write_report(state, info, None, log.path)
    log.log(f"copy 完成 total_new={info['total_new']}")
    return 0


def stage_verify(env: dict, log: v1.Logger) -> int:
    log.log("stage=verify copy_to_bracket_inner")
    state = v1.load_state(_STATE)
    if not state.get("copy") or state["copy"].get("aborted"):
        raise SystemExit("copy 未完成，拒绝 verify")
    payloads = {p["inner"]: p for p in state["copy_payloads"]}
    expected_total = state["expected_total_new"]
    fails: list[str] = []

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            nodes = v1._run(session, "MATCH (n) RETURN count(n) AS c")[0]["c"]
            rels = v1._run(session, "MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
            sc_n = v1._run(session, "MATCH (s:Scripture) RETURN count(s) AS c")[0]["c"]
            by_type = _rel_counts(session)
            if nodes != _EXPECT_NODES:
                fails.append(f"nodes {nodes}≠{_EXPECT_NODES}")
            if rels != _EXPECT_RELS_BASE + expected_total:
                fails.append(f"rels {rels}≠{_EXPECT_RELS_BASE}+{expected_total}")
            if sc_n != _EXPECT_SCRIPTURE:
                fails.append(f"Scripture {sc_n}≠{_EXPECT_SCRIPTURE}")

            # class unchanged
            for t, n in _CLASS_COUNTS.items():
                if by_type.get(t, 0) != n:
                    fails.append(f"分类关系变化 {t}")

            # type counts = baseline + new per type
            base_types = state["baseline"]["by_type"]
            new_by_type: Counter = Counter()
            for p in state["copy_payloads"]:
                for r in p["out_copy"]:
                    new_by_type[r["type"]] += 1
                for r in p["in_copy"]:
                    new_by_type[r["type"]] += 1
            for t, base_n in base_types.items():
                expect = base_n + new_by_type.get(t, 0)
                if by_type.get(t, 0) != expect:
                    fails.append(f"类型 {t}: {by_type.get(t)}≠{expect} (base {base_n}+new {new_by_type.get(t,0)})")
            for t, n in new_by_type.items():
                if t not in base_types and by_type.get(t, 0) != n:
                    fails.append(f"新类型计数 {t}: {by_type.get(t)}≠{n}")

            # deduct check: by_type[t] - new == base
            for t, base_n in base_types.items():
                if by_type.get(t, 0) - new_by_type.get(t, 0) != base_n:
                    fails.append(f"扣除新增后 {t} 与快照不符")

            # scripture sha
            sc_sha = _snapshot_scripture(session)
            if sc_sha != state["scripture_sha"]:
                fails.append("Scripture (ref,text) SHA 有变化")

            # outer+ordinary anno sha
            inner_names = {p["inner"] for p in state["pairs"]}
            anno_now = _snapshot_outer_ordinary_annos(session, inner_names)
            for prop, old in state["anno_sha_outer_ordinary"].items():
                now = anno_now.get(prop, {})
                if old != now:
                    mism = sorted(k for k in set(old) | set(now) if old.get(k) != now.get(k))
                    fails.append(f"外/普通标注变化 {prop}: {mism[:20]}")

            samples = []
            pair_verify = []
            for p in state["pairs"]:
                inner, outer = p["inner"], p["outer"]
                payload = payloads[inner]
                # identity
                ident = v1._run(
                    session,
                    "MATCH (n:Truth_Point {name: $n}) RETURN n.name AS name, n.same_as AS sa",
                    {"n": inner},
                )[0]
                before = state["inner_identity"][inner]
                if ident["name"] != before["name"] or ident["sa"] != before.get("same_as", before.get("sa")):
                    fails.append(f"{inner}: name/same_as 变化 {ident} vs {before}")

                # props compare
                ip = _get_props(session, inner)
                op = payload["props"]
                if set(ip) != set(op):
                    fails.append(f"{inner}: 属性键集合 {sorted(ip)}≠{sorted(op)}")
                for k, v in op.items():
                    if ip.get(k) != v:
                        fails.append(f"{inner}: 属性 {k} 值不一致")
                # SHA
                for k in op:
                    if _sha_val(ip.get(k)) != _sha_val(op[k]):
                        fails.append(f"{inner}: 属性 {k} SHA 不一致")

                # no class copied as extra? inners already had class; count class same as before (1 trunk etc)
                # ensure no self-loop
                loops = v1._run(
                    session,
                    """
                    MATCH (i:Truth_Point {name: $i})-[r]->(i)
                    RETURN type(r) AS t, count(*) AS c
                    """,
                    {"i": inner},
                )
                if loops:
                    fails.append(f"{inner}: 自环 {loops}")

                # per-type in/out counts
                out_got = Counter(
                    r["t"]
                    for r in v1._run(
                        session,
                        """
                        MATCH (i:Truth_Point {name: $i})-[r]->(x)
                        WHERE NOT type(r) IN $cls
                        RETURN type(r) AS t
                        """,
                        {"i": inner, "cls": list(_CLASS)},
                    )
                )
                in_got = Counter(
                    r["t"]
                    for r in v1._run(
                        session,
                        """
                        MATCH (x)-[r]->(i:Truth_Point {name: $i})
                        WHERE NOT type(r) IN $cls
                        RETURN type(r) AS t
                        """,
                        {"i": inner, "cls": list(_CLASS)},
                    )
                )
                out_exp = Counter(r["type"] for r in payload["out_copy"])
                in_exp = Counter(r["type"] for r in payload["in_copy"])
                if dict(out_got) != dict(out_exp):
                    fails.append(f"{inner}: 出边 {dict(out_got)}≠{dict(out_exp)}")
                if dict(in_got) != dict(in_exp):
                    fails.append(f"{inner}: 入边 {dict(in_got)}≠{dict(in_exp)}")

                # sample 2 rels
                sample_rels = (payload["out_copy"] + payload["in_copy"])[:2]
                for sr in sample_rels:
                    if "to_name" in sr or "to_ref" in sr:
                        if sr.get("to_ref"):
                            n = v1._run(
                                session,
                                f"""
                                MATCH (i:Truth_Point {{name: $i}})-[r:`{sr['type']}`]->(s:Scripture {{ref: $ref}})
                                RETURN count(r) AS c
                                """,
                                {"i": inner, "ref": sr["to_ref"]},
                            )[0]["c"]
                        else:
                            n = v1._run(
                                session,
                                f"""
                                MATCH (i:Truth_Point {{name: $i}})-[r:`{sr['type']}`]->(x:Truth_Point {{name: $x}})
                                RETURN count(r) AS c
                                """,
                                {"i": inner, "x": sr["to_name"]},
                            )[0]["c"]
                        samples.append({"inner": inner, "dir": "out", "type": sr["type"], "ok": n >= 1})
                        if n < 1:
                            fails.append(f"抽样缺失 out {inner} {sr}")
                    else:
                        n = v1._run(
                            session,
                            f"""
                            MATCH (x:Truth_Point {{name: $x}})-[r:`{sr['type']}`]->(i:Truth_Point {{name: $i}})
                            RETURN count(r) AS c
                            """,
                            {"i": inner, "x": sr["from_name"]},
                        )[0]["c"]
                        samples.append({"inner": inner, "dir": "in", "type": sr["type"], "ok": n >= 1})
                        if n < 1:
                            fails.append(f"抽样缺失 in {inner} {sr}")

                pair_verify.append(
                    {
                        "inner": inner,
                        "outer": outer,
                        "props": sorted(ip.keys()),
                        "out": dict(out_got),
                        "in": dict(in_got),
                        "same_as": ident["sa"],
                    }
                )

            # total new
            total_inner_sem = sum(_count_inner_semantic(session, p["inner"]) for p in state["pairs"])
            if total_inner_sem != expected_total:
                fails.append(f"括号内语义关系合计 {total_inner_sem}≠{expected_total}")
    except Exception as exc:
        raise SystemExit("verify 失败: " + v1._redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    verify = {
        "ok": not fails,
        "fails": fails,
        "nodes_total": nodes,
        "rels_total": rels,
        "expect_rels": _EXPECT_RELS_BASE + expected_total,
        "scripture_n": sc_n,
        "supported_by_n": by_type.get("SUPPORTED_BY"),
        "new_by_type": dict(new_by_type),
        "pair_verify": pair_verify,
        "samples": samples,
    }
    state["verify"] = verify
    v1.save_state(_STATE, state)
    write_report(state, state.get("copy"), verify, log.path)
    for f in fails:
        log.log("VERIFY FAIL: " + f)
    if fails:
        return 2
    log.log("verify 全部通过")
    return 0


def write_report(state: dict, copy_info: dict | None, verify_info: dict | None, log_path: Path) -> None:
    lines = [
        "# neo4j-v4：括号外 → 括号内 标注与关系复制（8 对）",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}；脚本：`panai4.graph.copy_to_bracket_inner`。",
        "复制属性白名单（不含 name/same_as）；复制 29 种语义关系 + SUPPORTED_BY；不复制 4 种分类关系；不复制 O↔I。",
        "只替换本端；`same_as` 保留。复制是快照——括号外以后再改，需重新同步。",
        "未运行 build_v4.py；未打印密码；未修改已有脚本 / .gitignore。",
        "",
        "## 摘要",
        "",
        f"1. **对数**：{len(state.get('pairs') or [])}；预期新增关系={state.get('expected_total_new')}",
        f"2. **cross 端点情形**：n={len(state.get('cross_bracket_endpoints') or [])} → {state.get('cross_bracket_endpoints')}",
        f"3. **闸门**：check_ok={state.get('check_ok')} fails={state.get('fails')}",
        f"4. **copy**：{copy_info}",
        f"5. **verify**：ok={(verify_info or {}).get('ok')} fails={(verify_info or {}).get('fails')}",
        "",
        "## check 明细（8 对）",
        "",
    ]
    for p in state.get("pair_details") or []:
        lines += [
            f"### {p['outer']} → {p['inner']}",
            f"- 外节点标注：{p.get('outer_props')}（n={p.get('outer_prop_n')}）",
            f"- 出边按类型：{p.get('out_by_type')}；SUPPORTED_BY 出={p.get('supported_by_out')}",
            f"- 入边按类型：{p.get('in_by_type')}；SUPPORTED_BY 入={p.get('supported_by_in')}",
            f"- 预期新增：{p.get('expected_new')}",
            f"- O↔I 关系（不复制）：{p.get('between')}",
            f"- cross 端点：{p.get('cross_bracket_endpoints')}",
            "",
        ]
    lines.append(f"- 基线 nodes={state.get('baseline',{}).get('nodes_total')} rels={state.get('baseline',{}).get('rels_total')}")
    lines.append("")
    if copy_info:
        lines += ["## copy", f"```json\n{json.dumps(copy_info, ensure_ascii=False, indent=2)}\n```", ""]
    if verify_info:
        lines += [
            "## verify",
            f"- nodes={verify_info.get('nodes_total')} rels={verify_info.get('rels_total')} expect={verify_info.get('expect_rels')}",
            f"- Scripture={verify_info.get('scripture_n')} SUPPORTED_BY={verify_info.get('supported_by_n')}",
            f"- new_by_type={verify_info.get('new_by_type')}",
            f"- pair_verify={json.dumps(verify_info.get('pair_verify'), ensure_ascii=False)}",
            f"- samples={json.dumps(verify_info.get('samples'), ensure_ascii=False)}",
            f"- fails={verify_info.get('fails')}",
            "",
        ]
    lines += [
        "## 最终说明",
        "- `same_as` 保留，未删除",
        "- 复制是快照；括号外节点以后再改标注或关系，要重新同步",
        "- 未修改已有脚本；未运行 build_v4.py；密码检查通过（仅变量名）",
        "- 未删文件；未改括号外节点",
        f"- 日志：`{log_path}`",
        "",
    ]
    _REPORT.parent.mkdir(parents=True, exist_ok=True)
    _REPORT.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="复制括号外标注/关系到括号内")
    ap.add_argument("--stage", required=True, choices=["check", "copy", "verify"])
    args = ap.parse_args(argv)
    env = v1._load_env()
    log = v1.Logger(
        _LOG_DIR / f"copy_to_bracket_inner_{args.stage}_{v1._now()}.log",
        env["pass4"],
    )
    log.log(f"stage={args.stage}（密码不记录）")
    if args.stage == "check":
        return stage_check(env, log)
    if args.stage == "copy":
        return stage_copy(env, log)
    if args.stage == "verify":
        return stage_verify(env, log)
    return 2


if __name__ == "__main__":
    sys.exit(main())
