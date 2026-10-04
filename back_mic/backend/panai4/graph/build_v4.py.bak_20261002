# -*- coding: utf-8 -*-
"""在 neo4j-v4 上建立 PanAI 4.0 基础图谱，并从 3.5 只读迁移 6 种词条间关系。

3.5（NEO4J_URI）只读。写入只发生在 NEO4J_V4_URI，且两者相同时立即中止。
密码只从环境变量读取，不写入报告或日志。

默认只 MERGE：补建节点和关系，并 SET 本脚本负责的标注。不删除。
清理必须先 --cleanup 列出候选，再 --cleanup --confirm 按清单删除。

用法:
    python back_mic/backend/panai4/graph/build_v4.py
    python back_mic/backend/panai4/graph/build_v4.py --dry-run
    python back_mic/backend/panai4/graph/build_v4.py --apply
    python back_mic/backend/panai4/graph/build_v4.py --cleanup
    python back_mic/backend/panai4/graph/build_v4.py --cleanup --confirm
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from dotenv import load_dotenv
from neo4j import READ_ACCESS, WRITE_ACCESS, GraphDatabase

from panai4.graph.inventory_35 import build_2380, load_terms_txt, parse_trunks

_REPO = _BACKEND.parents[1]
_DATA = _REPO / "docs" / "panai4_graph"
_REPORTS = _DATA / "reports"
_TERMS_JSON = _DATA / "主恢复真理词典_词条主干枝子映射 (1).json"
_TRUNKS_TXT = _DATA / "12大类与91小类的对应关系.txt"
_CSV = _DATA / "concept_mapping_35_to_40.csv"
_CLEANUP_MD = _REPORTS / "cleanup_candidates.md"
_CLEANUP_JSON_RE = re.compile(r"```cleanup-json\n(.*?)\n```", re.DOTALL)

_CLEANUP_LABELS = ("Truth_Point", "Trunk", "Branch")
_CLEANUP_REL_TYPES = (
    "GRAFTING",
    "BELONGS_TO_TRUNK",
    "OF_BRANCH_DIRECTLY",
    "OF_BRANCH_INDIRECTLY",
)

_OLD_REL_TYPES = (
    "CONTAINS",
    "EXPERIENCES",
    "LEADS_TO",
    "LOCATED_IN",
    "OPPOSES",
    "PRACTICED_AS",
)
_EXPECTED_OLD = {
    "CONTAINS": 5977,
    "EXPERIENCES": 7725,
    "LEADS_TO": 14140,
    "LOCATED_IN": 528,
    "OPPOSES": 3372,
    "PRACTICED_AS": 7431,
}
_EXPECTED_OLD_TOTAL = 39173
_BATCH = 500


def _redact(text: str, *secrets: str) -> str:
    out = text
    for secret in secrets:
        if secret:
            out = out.replace(secret, "***")
    return out


def _load_env() -> dict[str, str]:
    env_path = _BACKEND / ".env"
    if env_path.is_file():
        load_dotenv(env_path)
    uri35 = (os.environ.get("NEO4J_URI") or "").strip()
    user35 = (os.environ.get("NEO4J_USER") or "").strip()
    pass35 = os.environ.get("NEO4J_PASSWORD") or ""
    uri4 = (os.environ.get("NEO4J_V4_URI") or "").strip()
    user4 = (os.environ.get("NEO4J_V4_USER") or "").strip()
    pass4 = os.environ.get("NEO4J_V4_PASSWORD") or ""
    missing = [
        name
        for name, value in (
            ("NEO4J_URI", uri35),
            ("NEO4J_USER", user35),
            ("NEO4J_PASSWORD", pass35),
            ("NEO4J_V4_URI", uri4),
            ("NEO4J_V4_USER", user4),
            ("NEO4J_V4_PASSWORD", pass4),
        )
        if not str(value).strip()
    ]
    if missing:
        raise SystemExit("缺少环境变量（值不打印）: " + ", ".join(missing))
    if uri35 == uri4:
        raise SystemExit("中止：NEO4J_V4_URI 与 3.5 的 NEO4J_URI 相同，拒绝连接。")
    return {
        "uri35": uri35,
        "user35": user35,
        "pass35": pass35,
        "uri4": uri4,
        "user4": user4,
        "pass4": pass4,
    }


def _read(tx, query: str, params: dict | None = None):
    head = query.lstrip().split(None, 1)[0].upper()
    if head not in {"MATCH", "SHOW", "CALL", "WITH", "RETURN", "UNWIND"}:
        raise RuntimeError(f"只读连接拒绝语句: {head}")
    result = tx.run(query, params or {})
    return [record.data() for record in result]


def _read_session(session, query: str, params: dict | None = None):
    return session.execute_read(_read, query, params)


def _write(tx, query: str, params: dict | None = None):
    tx.run(query, params or {}).consume()


def load_plan() -> dict:
    terms, _dirty = load_terms_txt()
    list_2380, splits, bad_parens = build_2380(terms)
    if bad_parens:
        raise SystemExit("词表中有无法按单层括号拆开的行: " + "、".join(bad_parens))
    if len(list_2380) != 2380 or len(set(list_2380)) != 2380:
        raise SystemExit(f"2380 名单长度异常: {len(list_2380)} / 去重 {len(set(list_2380))}")
    split_by_src = {src: (outer, inner) for src, outer, inner in splits}
    trunks_text = _TRUNKS_TXT.read_text(encoding="utf-8-sig")
    trunk_pairs, trunk_notes = parse_trunks(trunks_text)
    term_rows = json.loads(_TERMS_JSON.read_text(encoding="utf-8-sig"))
    by_name = {str(row.get("name", "")).strip(): row for row in term_rows}

    branch_to_trunk: dict[str, str] = {}
    for trunk, branches in trunk_pairs:
        for branch in branches:
            branch_to_trunk[branch] = trunk

    points = []
    missing_json = []
    for term in terms:
        row = by_name.get(term)
        if row is None:
            missing_json.append(term)
            continue
        trunk = str(row.get("trunk", "")).strip()
        direct = str(row.get("branch_directly", "")).strip()
        indirect = [str(x).strip() for x in (row.get("branch_indirectly") or []) if str(x).strip()]
        if term in split_by_src:
            outer, inner = split_by_src[term]
            points.append(
                {"name": outer, "same_as": None, "trunk": trunk, "direct": direct, "indirect": indirect, "source": term}
            )
            points.append(
                {"name": inner, "same_as": outer, "trunk": trunk, "direct": direct, "indirect": list(indirect), "source": term}
            )
        else:
            points.append(
                {"name": term, "same_as": None, "trunk": trunk, "direct": direct, "indirect": indirect, "source": term}
            )

    indirect_base = 0
    indirect_paren_copy = 0
    both_roles = []
    for term, row in ((str(r.get("name", "")).strip(), r) for r in term_rows):
        indirect = [str(x).strip() for x in (row.get("branch_indirectly") or []) if str(x).strip()]
        indirect_base += len(indirect)
        if term in split_by_src:
            indirect_paren_copy += len(indirect)
    for point in points:
        if point["direct"] in point["indirect"]:
            both_roles.append((point["name"], point["direct"]))

    grafting = [(branch, trunk) for trunk, branches in trunk_pairs for branch in branches]
    trunk_branch_counts = {trunk: len(branches) for trunk, branches in trunk_pairs}

    return {
        "terms": terms,
        "points": points,
        "splits": splits,
        "trunk_pairs": trunk_pairs,
        "trunk_notes": trunk_notes,
        "branch_to_trunk": branch_to_trunk,
        "grafting": grafting,
        "trunk_branch_counts": trunk_branch_counts,
        "missing_json": missing_json,
        "indirect_base": indirect_base,
        "indirect_paren_copy": indirect_paren_copy,
        "indirect_expected": indirect_base + indirect_paren_copy,
        "both_roles": both_roles,
        "point_names": {p["name"] for p in points},
    }


def load_mapping() -> dict[str, dict]:
    rows = {}
    with _CSV.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            rows[row["旧名"]] = row
    return rows


def read_35(env: dict) -> dict:
    driver = GraphDatabase.driver(env["uri35"], auth=(env["user35"], env["pass35"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            nodes = _read_session(session, "MATCH (n) RETURN count(n) AS c")[0]["c"]
            rels = _read_session(session, "MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
            labels = _read_session(
                session,
                "MATCH (n) RETURN labels(n) AS labels, count(*) AS cnt",
            )
            edges = _read_session(
                session,
                """
                MATCH (a:Concept)-[r]->(b:Concept)
                WHERE type(r) IN $types
                RETURN type(r) AS rel_type, a.name AS start_name, b.name AS end_name
                """,
                {"types": list(_OLD_REL_TYPES)},
            )
        return {"nodes": nodes, "rels": rels, "labels": labels, "edges": edges}
    except Exception as exc:
        raise SystemExit("读取 3.5 失败: " + _redact(str(exc), env["pass35"], env["pass4"])) from exc
    finally:
        driver.close()


def classify_edges(edges: list[dict], mapping: dict[str, dict], point_names: set[str]) -> dict:
    kept: dict[str, list[tuple[str, str]]] = {name: [] for name in _OLD_REL_TYPES}
    discarded = Counter()
    missing_old = []
    missing_new = []
    for edge in edges:
        rel_type = edge["rel_type"]
        if rel_type not in kept:
            continue
        start = mapping.get(edge["start_name"])
        end = mapping.get(edge["end_name"])
        if start is None or end is None:
            missing_old.append((rel_type, edge["start_name"], edge["end_name"]))
            continue
        if start["处理方式"] == "删除" or end["处理方式"] == "删除":
            discarded[rel_type] += 1
            continue
        new_start = start["新名"]
        new_end = end["新名"]
        if new_start not in point_names or new_end not in point_names:
            missing_new.append((rel_type, edge["start_name"], new_start, edge["end_name"], new_end))
            continue
        kept[rel_type].append((new_start, new_end))
    unique = {}
    duplicate_extra = {}
    for rel_type, pairs in kept.items():
        counts = Counter(pairs)
        unique[rel_type] = len(counts)
        duplicate_extra[rel_type] = sum(c - 1 for c in counts.values() if c > 1)
    return {
        "kept": {k: len(v) for k, v in kept.items()},
        "pairs": kept,
        "discarded": dict(discarded),
        "missing_old": missing_old,
        "missing_new": missing_new,
        "unique": unique,
        "duplicate_extra": duplicate_extra,
    }


def _chunks(rows: list, size: int):
    for index in range(0, len(rows), size):
        yield rows[index : index + size]


def apply_v4(env: dict, plan: dict, classified: dict) -> None:
    """只连接 NEO4J_V4_URI。调用前已经确认它不等于 3.5 的 URI。"""
    if env["uri4"] == env["uri35"]:
        raise SystemExit("中止：目标 URI 与 3.5 相同。")
    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=WRITE_ACCESS) as session:
            for statement in (
                """
                CREATE CONSTRAINT truth_point_name IF NOT EXISTS
                FOR (n:Truth_Point) REQUIRE n.name IS UNIQUE
                """,
                """
                CREATE CONSTRAINT trunk_name IF NOT EXISTS
                FOR (n:Trunk) REQUIRE n.name IS UNIQUE
                """,
                """
                CREATE CONSTRAINT branch_name IF NOT EXISTS
                FOR (n:Branch) REQUIRE n.name IS UNIQUE
                """,
            ):
                session.execute_write(_write, statement)

            trunks = [{"name": trunk} for trunk, _branches in plan["trunk_pairs"]]
            session.execute_write(
                _write,
                "UNWIND $rows AS row MERGE (n:Trunk {name: row.name})",
                {"rows": trunks},
            )
            branches = [{"name": branch} for branch, _trunk in plan["grafting"]]
            session.execute_write(
                _write,
                "UNWIND $rows AS row MERGE (n:Branch {name: row.name})",
                {"rows": branches},
            )
            point_rows = [
                {"name": point["name"], "same_as": point["same_as"]}
                for point in plan["points"]
                if point["same_as"]
            ]
            name_only = [{"name": point["name"]} for point in plan["points"] if not point["same_as"]]
            for batch in _chunks(name_only, _BATCH):
                session.execute_write(
                    _write,
                    "UNWIND $rows AS row MERGE (n:Truth_Point {name: row.name})",
                    {"rows": batch},
                )
            for batch in _chunks(point_rows, _BATCH):
                session.execute_write(
                    _write,
                    """
                    UNWIND $rows AS row
                    MERGE (n:Truth_Point {name: row.name})
                    SET n.same_as = row.same_as
                    """,
                    {"rows": batch},
                )
            graft_rows = [{"branch": branch, "trunk": trunk} for branch, trunk in plan["grafting"]]
            session.execute_write(
                _write,
                """
                UNWIND $rows AS row
                MATCH (b:Branch {name: row.branch})
                MATCH (t:Trunk {name: row.trunk})
                MERGE (b)-[:GRAFTING]->(t)
                """,
                {"rows": graft_rows},
            )
            belong_rows = [{"name": p["name"], "trunk": p["trunk"]} for p in plan["points"]]
            for batch in _chunks(belong_rows, _BATCH):
                session.execute_write(
                    _write,
                    """
                    UNWIND $rows AS row
                    MATCH (n:Truth_Point {name: row.name})
                    MATCH (t:Trunk {name: row.trunk})
                    MERGE (n)-[:BELONGS_TO_TRUNK]->(t)
                    """,
                    {"rows": batch},
                )
            direct_rows = [{"name": p["name"], "branch": p["direct"]} for p in plan["points"]]
            for batch in _chunks(direct_rows, _BATCH):
                session.execute_write(
                    _write,
                    """
                    UNWIND $rows AS row
                    MATCH (n:Truth_Point {name: row.name})
                    MATCH (b:Branch {name: row.branch})
                    MERGE (n)-[:OF_BRANCH_DIRECTLY]->(b)
                    """,
                    {"rows": batch},
                )
            indirect_rows = [
                {"name": p["name"], "branch": branch}
                for p in plan["points"]
                for branch in p["indirect"]
            ]
            for batch in _chunks(indirect_rows, _BATCH):
                session.execute_write(
                    _write,
                    """
                    UNWIND $rows AS row
                    MATCH (n:Truth_Point {name: row.name})
                    MATCH (b:Branch {name: row.branch})
                    MERGE (n)-[:OF_BRANCH_INDIRECTLY]->(b)
                    """,
                    {"rows": batch},
                )
            merge_by_type = {
                "CONTAINS": """
                    UNWIND $rows AS row
                    MATCH (a:Truth_Point {name: row.a})
                    MATCH (b:Truth_Point {name: row.b})
                    MERGE (a)-[:CONTAINS]->(b)
                """,
                "EXPERIENCES": """
                    UNWIND $rows AS row
                    MATCH (a:Truth_Point {name: row.a})
                    MATCH (b:Truth_Point {name: row.b})
                    MERGE (a)-[:EXPERIENCES]->(b)
                """,
                "LEADS_TO": """
                    UNWIND $rows AS row
                    MATCH (a:Truth_Point {name: row.a})
                    MATCH (b:Truth_Point {name: row.b})
                    MERGE (a)-[:LEADS_TO]->(b)
                """,
                "LOCATED_IN": """
                    UNWIND $rows AS row
                    MATCH (a:Truth_Point {name: row.a})
                    MATCH (b:Truth_Point {name: row.b})
                    MERGE (a)-[:LOCATED_IN]->(b)
                """,
                "OPPOSES": """
                    UNWIND $rows AS row
                    MATCH (a:Truth_Point {name: row.a})
                    MATCH (b:Truth_Point {name: row.b})
                    MERGE (a)-[:OPPOSES]->(b)
                """,
                "PRACTICED_AS": """
                    UNWIND $rows AS row
                    MATCH (a:Truth_Point {name: row.a})
                    MATCH (b:Truth_Point {name: row.b})
                    MERGE (a)-[:PRACTICED_AS]->(b)
                """,
            }
            for rel_type in _OLD_REL_TYPES:
                pairs = [{"a": a, "b": b} for a, b in classified["pairs"][rel_type]]
                for batch in _chunks(pairs, _BATCH):
                    session.execute_write(_write, merge_by_type[rel_type], {"rows": batch})
    except Exception as exc:
        raise SystemExit("写入 neo4j-v4 失败: " + _redact(str(exc), env["pass4"], env["pass35"])) from exc
    finally:
        driver.close()


def read_v4_actual(env: dict) -> dict | None:
    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            return _snapshot_v4(session)
    except Exception as exc:
        return {"error": _redact(str(exc), env["pass4"], env["pass35"])}
    finally:
        driver.close()


def _snapshot_v4(session) -> dict:
    labels = _read_session(session, "MATCH (n) RETURN labels(n) AS labels, count(*) AS cnt")
    rels = _read_session(
        session,
        """
        MATCH (a)-[r]->(b)
        RETURN type(r) AS rel_type, labels(a) AS start_labels, labels(b) AS end_labels, count(*) AS cnt
        """,
    )
    same_as = _read_session(
        session,
        """
        MATCH (n:Truth_Point)
        WHERE n.same_as IS NOT NULL
        OPTIONAL MATCH (t:Truth_Point {name: n.same_as})
        RETURN n.name AS name, n.same_as AS same_as, t IS NOT NULL AS target_exists,
               t.same_as IS NOT NULL AS target_has_same_as
        ORDER BY name
        """,
    )
    graft_per_branch = _read_session(
        session,
        """
        MATCH (b:Branch)
        OPTIONAL MATCH (b)-[:GRAFTING]->(t:Trunk)
        RETURN b.name AS branch, count(t) AS trunks
        """,
    )
    belong_stats = _read_session(
        session,
        """
        MATCH (n:Truth_Point)
        OPTIONAL MATCH (n)-[r:BELONGS_TO_TRUNK]->(:Trunk)
        WITH n, count(r) AS c
        RETURN count(n) AS points,
               sum(CASE WHEN c = 1 THEN 1 ELSE 0 END) AS exactly_one,
               sum(c) AS rels
        """,
    )[0]
    direct_stats = _read_session(
        session,
        """
        MATCH (n:Truth_Point)
        OPTIONAL MATCH (n)-[r:OF_BRANCH_DIRECTLY]->(:Branch)
        WITH n, count(r) AS c
        RETURN count(n) AS points,
               sum(CASE WHEN c = 1 THEN 1 ELSE 0 END) AS exactly_one,
               sum(c) AS rels
        """,
    )[0]
    direct_trunk_mismatch = _read_session(
        session,
        """
        MATCH (n:Truth_Point)-[:BELONGS_TO_TRUNK]->(t:Trunk)
        MATCH (n)-[:OF_BRANCH_DIRECTLY]->(b:Branch)-[:GRAFTING]->(tb:Trunk)
        WHERE t.name <> tb.name
        RETURN count(*) AS c
        """,
    )[0]["c"]
    both_roles = _read_session(
        session,
        """
        MATCH (n:Truth_Point)-[:OF_BRANCH_DIRECTLY]->(b:Branch)
        MATCH (n)-[:OF_BRANCH_INDIRECTLY]->(b)
        RETURN n.name AS name, b.name AS branch
        ORDER BY name
        """,
    )
    indirect_count = _read_session(
        session,
        "MATCH ()-[r:OF_BRANCH_INDIRECTLY]->() RETURN count(r) AS c",
    )[0]["c"]
    graft_by_trunk = _read_session(
        session,
        """
        MATCH (b:Branch)-[:GRAFTING]->(t:Trunk)
        RETURN t.name AS trunk, count(b) AS branches
        ORDER BY trunk
        """,
    )
    nodes = _read_session(session, "MATCH (n) RETURN count(n) AS c")[0]["c"]
    rel_total = _read_session(session, "MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
    return {
        "nodes": nodes,
        "rel_total": rel_total,
        "labels": labels,
        "rels": rels,
        "same_as": same_as,
        "graft_per_branch": graft_per_branch,
        "belong_stats": belong_stats,
        "direct_stats": direct_stats,
        "direct_trunk_mismatch": direct_trunk_mismatch,
        "both_roles": both_roles,
        "indirect_count": indirect_count,
        "graft_by_trunk": graft_by_trunk,
    }


def _yn(ok: bool) -> str:
    return "通过" if ok else "不通过"


def _row(item: str, expected, actual, ok: bool | None = None) -> str:
    if ok is None:
        ok = expected == actual
    return f"| {item} | {expected} | {actual} | {_yn(ok)} |"


def render_report(
    path: Path,
    *,
    mode: str,
    env: dict,
    plan: dict,
    before: dict,
    after: dict,
    classified: dict,
    v4_before: dict | None,
    v4_after: dict | None,
) -> None:
    lines: list[str] = []
    add = lines.append
    add(f"# neo4j-v4 建图报告（{mode}）")
    add("")
    add("由 `back_mic/backend/panai4/graph/build_v4.py` 生成。3.5 只读。报告不含密码。")
    add("")
    add(f"- 3.5 地址：`{env['uri35']}`，用户 `{env['user35']}`")
    add(f"- 4.0 地址：`{env['uri4']}`，用户 `{env['user4']}`")
    if mode == "dry-run":
        add("- 本报告只计算计划写入的数量，没有连接 neo4j-v4，也没有写入。")
    add("")
    add("| 项目 | 预期 | 实际 | 通过否 |")
    add("|---|---|---|---|")

    point_count = len(plan["points"])
    trunk_count = len(plan["trunk_pairs"])
    branch_count = len(plan["grafting"])
    same_as_rows = [p for p in plan["points"] if p["same_as"]]
    same_as_targets_ok = all(
        p["same_as"] in plan["point_names"]
        and not any(q["name"] == p["same_as"] and q["same_as"] for q in plan["points"])
        for p in same_as_rows
    )
    graft_each_one = len(plan["grafting"]) == len({b for b, _t in plan["grafting"]}) == branch_count
    belong_each_one = all(p["trunk"] for p in plan["points"]) and point_count == 2380
    direct_each_one = all(p["direct"] for p in plan["points"])
    direct_trunk_bad = [
        p["name"]
        for p in plan["points"]
        if plan["branch_to_trunk"].get(p["direct"]) != p["trunk"]
    ]
    kept_total = sum(classified["kept"].values())
    unique_total = sum(classified["unique"].values())

    def actual_of(planned, key_path=None):
        if mode == "dry-run" or not v4_after or v4_after.get("error"):
            return planned
        return key_path

    # For dry-run, 实际 is the planned figure. For apply, 实际 comes from the database.
    if mode == "dry-run" or not v4_after or "error" in (v4_after or {}):
        live = None
    else:
        live = v4_after

    label_counts = Counter()
    rel_counts = Counter()
    if live:
        for row in live["labels"]:
            label_counts["+".join(row["labels"])] += int(row["cnt"])
        for row in live["rels"]:
            rel_counts[row["rel_type"]] += int(row["cnt"])

    def show(item, expected, planned, live_value=None):
        actual = planned if live is None else live_value
        add(_row(item, expected, actual))

    show("Truth_Point", 2380, point_count, label_counts.get("Truth_Point"))
    show("Trunk", 12, trunk_count, label_counts.get("Trunk"))
    show("Branch", 91, branch_count, label_counts.get("Branch"))
    other_labels = [k for k in (label_counts if live else {}) if k not in {"Truth_Point", "Trunk", "Branch"}]
    planned_other = "无"
    show("其他节点标签", "无", planned_other, "无" if live and not other_labels else (other_labels or "无"))

    same_actual = len(same_as_rows) if live is None else len(live["same_as"])
    add(_row("same_as 标注的节点数", 8, same_actual))
    if live is None:
        targets_ok = same_as_targets_ok and len(same_as_rows) == 8
    else:
        targets_ok = (
            len(live["same_as"]) == 8
            and all(row["target_exists"] and not row["target_has_same_as"] for row in live["same_as"])
        )
    add(_row("same_as 指向存在且对方自身无 same_as", "是", "是" if targets_ok else "否", targets_ok))

    graft_actual = len(plan["grafting"]) if live is None else rel_counts.get("GRAFTING", 0)
    add(_row("GRAFTING", 91, graft_actual))
    if live is None:
        each_branch = graft_each_one
    else:
        each_branch = all(int(row["trunks"]) == 1 for row in live["graft_per_branch"]) and len(live["graft_per_branch"]) == 91
    add(_row("每个枝子恰一条 GRAFTING", "是", "是" if each_branch else "否", each_branch))

    if live is None:
        trunk_match = plan["trunk_branch_counts"]
        trunk_ok = not plan["trunk_notes"] and trunk_count == 12 and branch_count == 91
    else:
        live_trunks = {row["trunk"]: int(row["branches"]) for row in live["graft_by_trunk"]}
        trunk_ok = live_trunks == plan["trunk_branch_counts"]
    add(_row("各主干下枝子数与 12 大类文件一致", "是", "是" if trunk_ok else "否", trunk_ok))

    belong_actual = point_count if live is None else live["belong_stats"]["rels"]
    add(_row("BELONGS_TO_TRUNK", 2380, belong_actual))
    if live is None:
        belong_one = belong_each_one and not plan["missing_json"]
    else:
        belong_one = int(live["belong_stats"]["exactly_one"]) == 2380
    add(_row("每个真理要点恰一条 BELONGS_TO_TRUNK", "是", "是" if belong_one else "否", belong_one))

    direct_actual = point_count if live is None else live["direct_stats"]["rels"]
    add(_row("OF_BRANCH_DIRECTLY", 2380, direct_actual))
    if live is None:
        direct_one = direct_each_one and not direct_trunk_bad
    else:
        direct_one = int(live["direct_stats"]["exactly_one"]) == 2380 and int(live["direct_trunk_mismatch"]) == 0
    add(_row("每个真理要点恰一条直接枝子，且枝子所属主干等于词条主干", "是", "是" if direct_one else "否", direct_one))

    indirect_planned = len({(p["name"], b) for p in plan["points"] for b in p["indirect"]})
    indirect_raw = plan["indirect_expected"]
    indirect_actual = indirect_planned if live is None else live["indirect_count"]
    add(_row("OF_BRANCH_INDIRECTLY", indirect_raw, indirect_actual, indirect_actual == indirect_raw))

    if live is None:
        role_ok = not plan["both_roles"]
        role_actual = "无" if role_ok else len(plan["both_roles"])
    else:
        role_ok = not live["both_roles"]
        role_actual = "无" if role_ok else len(live["both_roles"])
    add(_row("同一词条不同时直接并间接属于同一枝子", "无", role_actual, role_ok))

    for rel_type in _OLD_REL_TYPES:
        expected = _EXPECTED_OLD[rel_type]
        planned = classified["kept"][rel_type]
        live_value = rel_counts.get(rel_type) if live else None
        show(rel_type, expected, planned, live_value if live else planned)
    show("六种旧关系合计", _EXPECTED_OLD_TOTAL, kept_total, (sum(rel_counts.get(t, 0) for t in _OLD_REL_TYPES) if live else kept_total))

    scripture_actual = "无" if live is None or label_counts.get("Scripture", 0) == 0 else label_counts.get("Scripture")
    supported_actual = "无" if live is None or rel_counts.get("SUPPORTED_BY", 0) == 0 else rel_counts.get("SUPPORTED_BY")
    concept_actual = "无" if live is None or label_counts.get("Concept", 0) == 0 else label_counts.get("Concept")
    add(_row("Scripture 节点", "无", scripture_actual, scripture_actual == "无"))
    add(_row("SUPPORTED_BY", "无", supported_actual, supported_actual == "无"))
    add(_row("Concept 标签", "无", concept_actual, concept_actual == "无"))

    add(_row("3.5 运行前节点数", 2588, before["nodes"]))
    add(_row("3.5 运行前关系数", 44429, before["rels"]))
    add(_row("3.5 运行后节点数", 2588, after["nodes"]))
    add(_row("3.5 运行后关系数", 44429, after["rels"]))

    if mode == "dry-run":
        add("| 再次执行后数字不变 | 正式运行后验证 | 不适用（本次未写入） | 不适用 |")
    elif v4_before and "error" not in v4_before and live:
        unchanged = v4_before["nodes"] == live["nodes"] and v4_before["rel_total"] == live["rel_total"]
        add(
            _row(
                "本次写入前后 v4 节点数与关系数",
                f"节点 {v4_before['nodes']} / 关系 {v4_before['rel_total']}",
                f"节点 {live['nodes']} / 关系 {live['rel_total']}",
                unchanged,
            )
        )
    add("")
    add("## 计算明细")
    add("")
    add(f"- 词条映射缺失：{len(plan['missing_json'])}")
    if plan["missing_json"]:
        for name in plan["missing_json"]:
            add(f"  - `{name}`")
    add(f"- 12 大类解析提示：{len(plan['trunk_notes'])}")
    for note in plan["trunk_notes"]:
        add(f"  - {note}")
    add(f"- 间接关系列表长度之和（2372 条）：{plan['indirect_base']}")
    add(f"- 其中 8 个括号词条再复制给括号内节点：{plan['indirect_paren_copy']}")
    add(f"- 去重后的间接关系条数（MERGE 后会得到的条数）：{indirect_planned}")
    if indirect_planned != indirect_raw:
        add("- 列表长度之和与去重后条数不同。重复项没有改资料，MERGE 时会收成一条。")
    add(f"- 直接枝子的主干与词条主干不一致：{len(direct_trunk_bad)}")
    for name in direct_trunk_bad[:50]:
        add(f"  - `{name}`")
    add(f"- 同一节点既直接又间接属于同一枝子：{len(plan['both_roles'])}")
    for name, branch in plan["both_roles"]:
        add(f"  - `{name}` → `{branch}`")
    add(f"- 旧关系因删除舍弃：{sum(classified['discarded'].values())}")
    for rel_type in _OLD_REL_TYPES:
        add(f"  - {rel_type}：{classified['discarded'].get(rel_type, 0)}")
    add(f"- 旧名在 3.5 中但 CSV 没有：{len(classified['missing_old'])}")
    for item in classified["missing_old"][:30]:
        add(f"  - {item}")
    add(f"- 新名不在 2380 名单中：{len(classified['missing_new'])}")
    for item in classified["missing_new"][:30]:
        add(f"  - {item}")
    add(f"- 迁过去之后同一起点、终点、类型的多余条数：{sum(classified['duplicate_extra'].values())}（去重后合计 {unique_total}）")
    if mode != "dry-run" and v4_after and v4_after.get("error"):
        add("")
        add("## neo4j-v4 读取失败")
        add("")
        add(v4_after["error"])
    if live and live.get("same_as"):
        add("")
        add("## same_as")
        add("")
        for row in live["same_as"]:
            add(f"- `{row['name']}` → `{row['same_as']}`")
    elif mode == "dry-run":
        add("")
        add("## 计划中的 same_as")
        add("")
        for point in same_as_rows:
            add(f"- `{point['name']}` → `{point['same_as']}`")
    add("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _expected_catalog(plan: dict) -> dict:
    return {
        "Truth_Point": {point["name"] for point in plan["points"]},
        "Trunk": {trunk for trunk, _branches in plan["trunk_pairs"]},
        "Branch": {branch for branch, _trunk in plan["grafting"]},
        "GRAFTING": {(branch, trunk) for branch, trunk in plan["grafting"]},
        "BELONGS_TO_TRUNK": {(point["name"], point["trunk"]) for point in plan["points"]},
        "OF_BRANCH_DIRECTLY": {(point["name"], point["direct"]) for point in plan["points"]},
        "OF_BRANCH_INDIRECTLY": {
            (point["name"], branch) for point in plan["points"] for branch in point["indirect"]
        },
        "same_as": {point["name"]: point["same_as"] for point in plan["points"]},
    }


def _v4_counts(session) -> dict[str, int]:
    nodes = _read_session(session, "MATCH (n) RETURN count(n) AS c")[0]["c"]
    rels = _read_session(session, "MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
    return {"nodes": int(nodes), "rels": int(rels)}


def collect_cleanup_candidates(session, plan: dict) -> dict:
    """只读。候选限于本脚本负责的节点、四种分类关系，以及 same_as。"""
    catalog = _expected_catalog(plan)
    nodes = []
    for label in _CLEANUP_LABELS:
        rows = _read_session(
            session,
            f"""
            MATCH (n:{label})
            WHERE n.name IS NULL OR NOT n.name IN $names
            RETURN n.name AS name, elementId(n) AS element_id
            ORDER BY name
            """,
            {"names": list(catalog[label])},
        )
        for row in rows:
            nodes.append({"label": label, "name": row["name"], "element_id": row["element_id"]})

    rel_query = {
        "GRAFTING": """
            MATCH (a)-[r:GRAFTING]->(b)
            RETURN labels(a) AS start_labels, a.name AS start_name,
                   labels(b) AS end_labels, b.name AS end_name, elementId(r) AS element_id
        """,
        "BELONGS_TO_TRUNK": """
            MATCH (a)-[r:BELONGS_TO_TRUNK]->(b)
            RETURN labels(a) AS start_labels, a.name AS start_name,
                   labels(b) AS end_labels, b.name AS end_name, elementId(r) AS element_id
        """,
        "OF_BRANCH_DIRECTLY": """
            MATCH (a)-[r:OF_BRANCH_DIRECTLY]->(b)
            RETURN labels(a) AS start_labels, a.name AS start_name,
                   labels(b) AS end_labels, b.name AS end_name, elementId(r) AS element_id
        """,
        "OF_BRANCH_INDIRECTLY": """
            MATCH (a)-[r:OF_BRANCH_INDIRECTLY]->(b)
            RETURN labels(a) AS start_labels, a.name AS start_name,
                   labels(b) AS end_labels, b.name AS end_name, elementId(r) AS element_id
        """,
    }
    expected_ends = {
        "GRAFTING": ("Branch", "Trunk"),
        "BELONGS_TO_TRUNK": ("Truth_Point", "Trunk"),
        "OF_BRANCH_DIRECTLY": ("Truth_Point", "Branch"),
        "OF_BRANCH_INDIRECTLY": ("Truth_Point", "Branch"),
    }
    relationships = []
    for rel_type in _CLEANUP_REL_TYPES:
        start_label, end_label = expected_ends[rel_type]
        for row in _read_session(session, rel_query[rel_type]):
            pair = (row["start_name"], row["end_name"])
            labels_ok = (
                start_label in (row["start_labels"] or [])
                and end_label in (row["end_labels"] or [])
            )
            if (not labels_ok) or pair not in catalog[rel_type]:
                relationships.append(
                    {
                        "type": rel_type,
                        "start_label": start_label if labels_ok else "+".join(row["start_labels"] or []),
                        "start": row["start_name"],
                        "end_label": end_label if labels_ok else "+".join(row["end_labels"] or []),
                        "end": row["end_name"],
                        "element_id": row["element_id"],
                    }
                )

    same_as_rows = _read_session(
        session,
        """
        MATCH (n:Truth_Point)
        WHERE n.same_as IS NOT NULL
        RETURN n.name AS name, n.same_as AS same_as
        ORDER BY name
        """,
    )
    same_as = []
    for row in same_as_rows:
        expected = catalog["same_as"].get(row["name"])
        if expected != row["same_as"]:
            same_as.append(
                {"name": row["name"], "current": row["same_as"], "expected": expected}
            )
    return {"nodes": nodes, "relationships": relationships, "same_as": same_as}


def _candidate_lines(candidates: dict) -> list[str]:
    lines = ["## 节点", ""]
    if candidates["nodes"]:
        lines.append("| 标签 | 名字 |")
        lines.append("|---|---|")
        for row in candidates["nodes"]:
            lines.append(f"| {row['label']} | {row['name']} |")
    else:
        lines.append("（无）")
    lines.extend(["", "## 关系", ""])
    if candidates["relationships"]:
        lines.append("| 类型 | 起点 | 终点 |")
        lines.append("|---|---|---|")
        for row in candidates["relationships"]:
            lines.append(
                f"| {row['type']} | {row['start_label']}:{row['start']} | {row['end_label']}:{row['end']} |"
            )
    else:
        lines.append("（无）")
    lines.extend(["", "## same_as", ""])
    if candidates["same_as"]:
        lines.append("| 真理要点 | 当前值 | 资料中的值 |")
        lines.append("|---|---|---|")
        for row in candidates["same_as"]:
            lines.append(f"| {row['name']} | {row['current']} | {row['expected']} |")
    else:
        lines.append("（无）")
    lines.append("")
    return lines


def write_cleanup_report(path: Path, candidates: dict, counts: dict[str, int]) -> None:
    payload = {
        "nodes": candidates["nodes"],
        "relationships": candidates["relationships"],
        "same_as": candidates["same_as"],
    }
    lines = [
        "# 清理候选",
        "",
        "由 `build_v4.py --cleanup` 生成。这一步没有删除任何节点、关系或标注。",
        "`--cleanup --confirm` 只删除本文件代码块里的这些候选，不会重新计算。",
        "",
        f"- 列出时的节点数：**{counts['nodes']}**",
        f"- 列出时的关系数：**{counts['rels']}**",
        f"- 候选节点：**{len(candidates['nodes'])}**",
        f"- 候选关系：**{len(candidates['relationships'])}**",
        f"- 候选 same_as：**{len(candidates['same_as'])}**",
        "",
        "范围只包括 Truth_Point、Trunk、Branch 中不在资料名单里的节点，",
        "以及 GRAFTING、BELONGS_TO_TRUNK、OF_BRANCH_DIRECTLY、OF_BRANCH_INDIRECTLY 中与资料不符的关系，",
        "和与资料不符的 same_as。6 种迁移来的旧关系、其他关系类型、其他标注都不在此列。",
        "",
    ]
    lines.extend(_candidate_lines(candidates))
    lines.append("```cleanup-json")
    lines.append(json.dumps(payload, ensure_ascii=False, indent=2))
    lines.append("```")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def load_cleanup_candidates(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"没有候选清单 {path}。请先运行 --cleanup。")
    text = path.read_text(encoding="utf-8")
    match = _CLEANUP_JSON_RE.search(text)
    if not match:
        raise SystemExit("候选清单里没有 cleanup-json 代码块，拒绝删除。")
    data = json.loads(match.group(1))
    for key in ("nodes", "relationships", "same_as"):
        if key not in data or not isinstance(data[key], list):
            raise SystemExit("候选清单格式不对，拒绝删除。")
    for row in data["nodes"]:
        if row.get("label") not in _CLEANUP_LABELS:
            raise SystemExit(f"候选节点标签不在清理范围：{row.get('label')}")
    for row in data["relationships"]:
        if row.get("type") not in _CLEANUP_REL_TYPES:
            raise SystemExit(f"候选关系类型不在清理范围：{row.get('type')}")
    return data


def confirm_cleanup(env: dict, candidates: dict) -> tuple[dict, dict, list[str]]:
    """只删除清单中的项。先关系，再 same_as，最后节点。节点若仍连着其他关系则跳过，不使用 DETACH DELETE。"""
    if env["uri4"] == env["uri35"]:
        raise SystemExit("中止：目标 URI 与 3.5 相同。")
    notes: list[str] = []
    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=WRITE_ACCESS) as session:
            before = _v4_counts(session)
            for row in candidates["relationships"]:
                session.execute_write(
                    _write,
                    """
                    MATCH ()-[r]->()
                    WHERE elementId(r) = $id AND type(r) = $rel_type
                    DELETE r
                    """,
                    {"id": row["element_id"], "rel_type": row["type"]},
                )
            for row in candidates["same_as"]:
                session.execute_write(
                    _write,
                    "MATCH (n:Truth_Point {name: $name}) REMOVE n.same_as",
                    {"name": row["name"]},
                )
            for row in candidates["nodes"]:
                label = row["label"]
                try:
                    session.execute_write(
                        _write,
                        f"""
                        MATCH (n:{label})
                        WHERE elementId(n) = $id
                        DELETE n
                        """,
                        {"id": row["element_id"]},
                    )
                except Exception as exc:
                    message = _redact(str(exc), env["pass4"], env["pass35"])
                    notes.append(f"未删除 {label}:{row['name']}：{message}")
            after = _v4_counts(session)
        return before, after, notes
    except Exception as exc:
        raise SystemExit("清理失败: " + _redact(str(exc), env["pass4"], env["pass35"])) from exc
    finally:
        driver.close()


def append_cleanup_confirm(path: Path, before: dict, after: dict, notes: list[str]) -> None:
    extra = [
        "",
        "## 确认删除",
        "",
        "按上一份清单删除，没有重新扫描。",
        "",
        f"- 删除前节点数：**{before['nodes']}**",
        f"- 删除前关系数：**{before['rels']}**",
        f"- 删除后节点数：**{after['nodes']}**",
        f"- 删除后关系数：**{after['rels']}**",
        "",
    ]
    if notes:
        extra.append("未删掉的项：")
        extra.append("")
        extra.extend(f"- {note}" for note in notes)
        extra.append("")
    with path.open("a", encoding="utf-8") as handle:
        handle.write("\n".join(extra))


def main() -> int:
    parser = argparse.ArgumentParser(description="建立 neo4j-v4 基础图谱")
    parser.add_argument("--dry-run", action="store_true", help="只计算并写报告，不写入")
    parser.add_argument("--apply", action="store_true", help="只 MERGE，补建和更新本脚本负责的标注")
    parser.add_argument("--cleanup", action="store_true", help="只列出清理候选，不删除")
    parser.add_argument("--confirm", action="store_true", help="与 --cleanup 合用，按上一份清单删除")
    args = parser.parse_args()
    if args.confirm and not args.cleanup:
        raise SystemExit("--confirm 必须和 --cleanup 一起用。")
    if args.cleanup and (args.dry_run or args.apply):
        raise SystemExit("--cleanup 不能和 --dry-run / --apply 一起用。")
    if args.dry_run and args.apply:
        raise SystemExit("--dry-run 和 --apply 只能选一个。")
    env = _load_env()
    print(f"3.5 {env['uri35']} 用户 {env['user35']}")
    print(f"v4  {env['uri4']} 用户 {env['user4']}")
    plan = load_plan()
    _REPORTS.mkdir(parents=True, exist_ok=True)
    if args.cleanup:
        return _run_cleanup(env, plan, confirm=args.confirm)
    return _run_build(env, plan, dry_run=args.dry_run)


def _run_cleanup(env: dict, plan: dict, confirm: bool) -> int:
    if confirm:
        candidates = load_cleanup_candidates(_CLEANUP_MD)
        before, after, notes = confirm_cleanup(env, candidates)
        append_cleanup_confirm(_CLEANUP_MD, before, after, notes)
        print(
            f"删除前 节点 {before['nodes']} 关系 {before['rels']}；"
            f"删除后 节点 {after['nodes']} 关系 {after['rels']}"
        )
        for note in notes:
            print(note)
        print("已追加", _CLEANUP_MD)
        return 0
    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            counts = _v4_counts(session)
            candidates = collect_cleanup_candidates(session, plan)
    except Exception as exc:
        raise SystemExit("读取 neo4j-v4 失败: " + _redact(str(exc), env["pass4"], env["pass35"])) from exc
    finally:
        driver.close()
    write_cleanup_report(_CLEANUP_MD, candidates, counts)
    print(
        "候选",
        f"节点 {len(candidates['nodes'])}",
        f"关系 {len(candidates['relationships'])}",
        f"same_as {len(candidates['same_as'])}",
        "未删除",
    )
    print("已写", _CLEANUP_MD)
    return 0


def _run_build(env: dict, plan: dict, dry_run: bool) -> int:
    mapping = load_mapping()
    before = read_35(env)
    classified = classify_edges(before["edges"], mapping, plan["point_names"])
    mode = "dry-run" if dry_run else "apply"
    v4_before = None
    if dry_run:
        v4_after = None
    else:
        v4_before = read_v4_actual(env)
        if v4_before and v4_before.get("error"):
            raise SystemExit("正式运行前无法连接 neo4j-v4: " + v4_before["error"])
        apply_v4(env, plan, classified)
        v4_after = read_v4_actual(env)
    after = read_35(env)
    report = _REPORTS / ("build_v4_report_dry_run.md" if dry_run else "build_v4_report.md")
    render_report(
        report,
        mode=mode,
        env=env,
        plan=plan,
        before=before,
        after=after,
        classified=classified,
        v4_before=v4_before,
        v4_after=v4_after,
    )
    print("已写", report)
    if v4_before and v4_after and "error" not in v4_before and "error" not in (v4_after or {}):
        print(
            f"v4 写入前 节点 {v4_before['nodes']} 关系 {v4_before['rel_total']}；"
            f"写入后 节点 {v4_after['nodes']} 关系 {v4_after['rel_total']}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
