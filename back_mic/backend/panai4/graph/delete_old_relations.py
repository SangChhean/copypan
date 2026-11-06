# -*- coding: utf-8 -*-
"""neo4j-v4：删除从 3.5 迁移来的 6 种旧词条间关系（仅此一事）。

不新建关系、不碰节点/标注、不导入 JSON、不运行 build_v4.py。
连接：NEO4J_V4_*（dotenv 加载 .env，绝不打印密码）。

用法（在 back_mic/backend 下）:
    python -m panai4.graph.delete_old_relations --stage check
    python -m panai4.graph.delete_old_relations --stage delete
    python -m panai4.graph.delete_old_relations --stage verify
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from neo4j import READ_ACCESS, WRITE_ACCESS, GraphDatabase

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parents[1]
_REPORT = _REPO / "docs" / "panai4_graph" / "delete_old_relations.md"
_LOG_DIR = _REPO / "logs"
_STATE = _LOG_DIR / "delete_old_relations_state.json"

_OLD6 = (
    "LEADS_TO",
    "EXPERIENCES",
    "PRACTICED_AS",
    "CONTAINS",
    "OPPOSES",
    "LOCATED_IN",
)
_CLASS4 = (
    "BELONGS_TO_TRUNK",
    "OF_BRANCH_DIRECTLY",
    "OF_BRANCH_INDIRECTLY",
    "GRAFTING",
)
_EXPECTED = {
    "nodes_total": 2483,
    "Truth_Point": 2380,
    "Trunk": 12,
    "Branch": 91,
    "rels_total": 45700,
    "old6_total": 39173,
    "class_total": 6527,
    "BELONGS_TO_TRUNK": 2380,
    "OF_BRANCH_DIRECTLY": 2380,
    "OF_BRANCH_INDIRECTLY": 1676,
    "GRAFTING": 91,
    "LEADS_TO": 14140,
    "EXPERIENCES": 7725,
    "PRACTICED_AS": 7431,
    "CONTAINS": 5977,
    "OPPOSES": 3372,
    "LOCATED_IN": 528,
}
_CLASS_ENDPOINTS = {
    "BELONGS_TO_TRUNK": ("Truth_Point", "Trunk"),
    "OF_BRANCH_DIRECTLY": ("Truth_Point", "Branch"),
    "OF_BRANCH_INDIRECTLY": ("Truth_Point", "Branch"),
    "GRAFTING": ("Branch", "Trunk"),
}
_PAREN_PAIRS = [
    ("产生男孩子", "产生得胜者"),
    ("晨晨复兴", "晨兴"),
    ("妇人", "女人"),
    ("挂虑", "忧虑"),
    ("火湖", "地狱"),
    ("扩大", "显大"),
    ("扩增", "扩展"),
    ("那灵的浇灌", "圣灵的浇灌"),
]
_BATCH = 5000

# 写死在语句里的删除 Cypher（类型名不得参数化拼接）
_DELETE_QUERIES = {
    "LEADS_TO": (
        "MATCH (:Truth_Point)-[r:LEADS_TO]->(:Truth_Point) "
        "WITH r LIMIT $limit DELETE r RETURN count(*) AS deleted"
    ),
    "EXPERIENCES": (
        "MATCH (:Truth_Point)-[r:EXPERIENCES]->(:Truth_Point) "
        "WITH r LIMIT $limit DELETE r RETURN count(*) AS deleted"
    ),
    "PRACTICED_AS": (
        "MATCH (:Truth_Point)-[r:PRACTICED_AS]->(:Truth_Point) "
        "WITH r LIMIT $limit DELETE r RETURN count(*) AS deleted"
    ),
    "CONTAINS": (
        "MATCH (:Truth_Point)-[r:CONTAINS]->(:Truth_Point) "
        "WITH r LIMIT $limit DELETE r RETURN count(*) AS deleted"
    ),
    "OPPOSES": (
        "MATCH (:Truth_Point)-[r:OPPOSES]->(:Truth_Point) "
        "WITH r LIMIT $limit DELETE r RETURN count(*) AS deleted"
    ),
    "LOCATED_IN": (
        "MATCH (:Truth_Point)-[r:LOCATED_IN]->(:Truth_Point) "
        "WITH r LIMIT $limit DELETE r RETURN count(*) AS deleted"
    ),
}

_WRITE_HEAD = re.compile(
    r"^\s*(CREATE|MERGE|SET|REMOVE|DELETE|DETACH|DROP|LOAD\s+CSV)\b",
    re.IGNORECASE,
)


def _now() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


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
    uri4 = (os.environ.get("NEO4J_V4_URI") or "").strip()
    user4 = (os.environ.get("NEO4J_V4_USER") or "").strip()
    pass4 = os.environ.get("NEO4J_V4_PASSWORD") or ""
    uri35 = (os.environ.get("NEO4J_URI") or "").strip()
    missing = [
        name
        for name, value in (
            ("NEO4J_V4_URI", uri4),
            ("NEO4J_V4_USER", user4),
            ("NEO4J_V4_PASSWORD", pass4),
        )
        if not str(value).strip()
    ]
    if missing:
        raise SystemExit("缺少环境变量（值不打印）: " + ", ".join(missing))
    if uri35 and uri35 == uri4:
        raise SystemExit("中止：NEO4J_V4_URI 与 NEO4J_URI 相同，拒绝连接。")
    return {"uri4": uri4, "user4": user4, "pass4": pass4}


def _read(tx, query: str, params: dict | None = None):
    if _WRITE_HEAD.search(query):
        raise RuntimeError(f"只读会话拒绝写语句: {query[:80]}")
    head = query.lstrip().split(None, 1)[0].upper()
    if head not in {"MATCH", "SHOW", "CALL", "WITH", "RETURN", "UNWIND"}:
        raise RuntimeError(f"只读会话拒绝语句头: {head}")
    return [record.data() for record in tx.run(query, params or {})]


def _run(session, query: str, params: dict | None = None):
    return session.execute_read(_read, query, params)


def _delete_batch(tx, query: str, limit: int):
    """仅允许预置的 DELETE 语句。"""
    if "DELETE r" not in query or "DETACH" in query.upper():
        raise RuntimeError("拒绝非预期删除语句")
    if not any(f"[r:{t}]" in query for t in _OLD6):
        raise RuntimeError("删除语句必须写死旧关系类型")
    if "(:Truth_Point)-[r:" not in query or "]->(:Truth_Point)" not in query:
        raise RuntimeError("删除语句必须限定两端 Truth_Point")
    result = tx.run(query, {"limit": limit})
    row = result.single()
    return int(row["deleted"]) if row else 0


class Logger:
    def __init__(self, path: Path, pass4: str):
        self.path = path
        self.pass4 = pass4
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")

    def log(self, msg: str) -> None:
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {_redact(msg, self.pass4)}"
        print(line)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def snapshot_baseline(session) -> dict[str, Any]:
    components = _run(
        session,
        "CALL dbms.components() YIELD name, versions, edition "
        "RETURN name, versions, edition",
    )
    try:
        docker_ps = subprocess.check_output(
            [
                "docker",
                "ps",
                "--filter",
                "name=neo4j-v4",
                "--format",
                "{{.Names}}\t{{.Status}}\t{{.Image}}\t{{.Ports}}",
            ],
            text=True,
            encoding="utf-8",
            errors="replace",
        ).strip()
    except Exception as exc:
        docker_ps = f"docker ps 失败: {exc}"

    labels = {
        r["l"]: r["c"]
        for r in _run(
            session,
            "MATCH (n) UNWIND labels(n) AS l RETURN l, count(*) AS c ORDER BY l",
        )
    }
    nodes_total = _run(session, "MATCH (n) RETURN count(n) AS c")[0]["c"]
    same_as_n = _run(
        session,
        """
        MATCH (n:Truth_Point)
        WHERE n.same_as IS NOT NULL AND toString(n.same_as) <> ''
        RETURN count(n) AS c
        """,
    )[0]["c"]
    no_same = labels.get("Truth_Point", 0) - same_as_n
    same_as_rows = _run(
        session,
        """
        MATCH (n:Truth_Point)
        WHERE n.same_as IS NOT NULL AND toString(n.same_as) <> ''
        OPTIONAL MATCH (t:Truth_Point {name: n.same_as})
        RETURN n.name AS inner, n.same_as AS outer, t IS NOT NULL AS outer_exists
        ORDER BY inner
        """,
    )

    rels_total = _run(session, "MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
    by_type = {
        r["t"]: r["c"]
        for r in _run(
            session,
            "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c ORDER BY t",
        )
    }
    try:
        db_types = [
            r["relationshipType"]
            for r in _run(session, "CALL db.relationshipTypes() YIELD relationshipType RETURN relationshipType")
        ]
    except Exception:
        db_types = list(by_type.keys())

    endpoint_combos = _run(
        session,
        """
        MATCH (a)-[r]->(b)
        RETURN type(r) AS rel_type,
               labels(a) AS start_labels,
               labels(b) AS end_labels,
               count(*) AS c
        ORDER BY rel_type
        """,
    )

    # both ends Truth_Point for old6
    old6_both_tp = {}
    for t in _OLD6:
        # type written into query via fixed map of queries — use separate fixed MATCH per type
        qmap = {
            "LEADS_TO": "MATCH (:Truth_Point)-[r:LEADS_TO]->(:Truth_Point) RETURN count(r) AS c",
            "EXPERIENCES": "MATCH (:Truth_Point)-[r:EXPERIENCES]->(:Truth_Point) RETURN count(r) AS c",
            "PRACTICED_AS": "MATCH (:Truth_Point)-[r:PRACTICED_AS]->(:Truth_Point) RETURN count(r) AS c",
            "CONTAINS": "MATCH (:Truth_Point)-[r:CONTAINS]->(:Truth_Point) RETURN count(r) AS c",
            "OPPOSES": "MATCH (:Truth_Point)-[r:OPPOSES]->(:Truth_Point) RETURN count(r) AS c",
            "LOCATED_IN": "MATCH (:Truth_Point)-[r:LOCATED_IN]->(:Truth_Point) RETURN count(r) AS c",
        }
        old6_both_tp[t] = _run(session, qmap[t])[0]["c"]

    # node keys
    node_keys = {}
    for label in ("Truth_Point", "Trunk", "Branch"):
        keys = _run(
            session,
            f"""
            MATCH (n:{label})
            UNWIND keys(n) AS k
            WITH k, count(*) AS nodes_with_key,
                 sum(CASE WHEN n[k] IS NULL THEN 0
                          WHEN toString(n[k]) = '' THEN 0
                          ELSE 1 END) AS nonempty
            RETURN k AS key, nodes_with_key, nonempty
            ORDER BY k
            """,
        )
        name_stats = _run(
            session,
            f"""
            MATCH (n:{label})
            RETURN count(n) AS total,
                   sum(CASE WHEN n.name IS NULL OR toString(n.name)='' THEN 0 ELSE 1 END) AS name_nonempty,
                   count(DISTINCT n.name) AS name_distinct
            """,
        )[0]
        node_keys[label] = {"keys": keys, "name_stats": name_stats}

    try:
        constraints = _run(session, "SHOW CONSTRAINTS")
    except Exception as exc:
        constraints = [{"error": str(exc)}]
    try:
        indexes = _run(session, "SHOW INDEXES")
    except Exception as exc:
        indexes = [{"error": str(exc)}]

    # orphan preview after deleting old6
    orphan_preview = _run(
        session,
        """
        MATCH (n:Truth_Point)
        OPTIONAL MATCH (n)-[c:BELONGS_TO_TRUNK|OF_BRANCH_DIRECTLY|OF_BRANCH_INDIRECTLY]->()
        OPTIONAL MATCH (n)<-[g:GRAFTING]-()
        WITH n, count(c) + count(g) AS class_deg
        WHERE class_deg = 0
        RETURN n.name AS name
        ORDER BY name
        LIMIT 20
        """,
    )
    orphan_count = _run(
        session,
        """
        MATCH (n:Truth_Point)
        OPTIONAL MATCH (n)-[c:BELONGS_TO_TRUNK|OF_BRANCH_DIRECTLY|OF_BRANCH_INDIRECTLY]->()
        OPTIONAL MATCH (n)<-[g:GRAFTING]-()
        WITH n, count(c) + count(g) AS class_deg
        WHERE class_deg = 0
        RETURN count(n) AS c
        """,
    )[0]["c"]

    return {
        "components": components,
        "docker_ps": docker_ps,
        "labels": labels,
        "nodes_total": nodes_total,
        "same_as_n": same_as_n,
        "no_same_as_n": no_same,
        "same_as_rows": same_as_rows,
        "rels_total": rels_total,
        "by_type": by_type,
        "db_relationship_types": db_types,
        "endpoint_combos": endpoint_combos,
        "old6_both_tp": old6_both_tp,
        "node_keys": node_keys,
        "constraints": constraints,
        "indexes": indexes,
        "orphan_after_delete_preview_count": orphan_count,
        "orphan_after_delete_preview_names": [r["name"] for r in orphan_preview],
        "class_total": sum(by_type.get(t, 0) for t in _CLASS4),
        "old6_total": sum(by_type.get(t, 0) for t in _OLD6),
    }


def gate_check(base: dict) -> list[str]:
    """返回失败原因列表；空列表=通过。"""
    fails: list[str] = []
    types = set(base["by_type"].keys())
    expected_types = set(_CLASS4) | set(_OLD6)
    if types != expected_types:
        fails.append(f"类型集合不符：实测 {sorted(types)}，期望 {sorted(expected_types)}")

    for t in _OLD6:
        total = base["by_type"].get(t, 0)
        both = base["old6_both_tp"].get(t, -1)
        if total != both:
            fails.append(f"{t}: 总数 {total} ≠ 两端皆 Truth_Point {both}")

    for row in base["endpoint_combos"]:
        t = row["rel_type"]
        starts = sorted(row["start_labels"] or [])
        ends = sorted(row["end_labels"] or [])
        if t in _OLD6:
            if starts != ["Truth_Point"] or ends != ["Truth_Point"]:
                fails.append(f"{t} 起止标签异常: {starts}→{ends} ×{row['c']}")
        elif t in _CLASS4:
            exp_s, exp_e = _CLASS_ENDPOINTS[t]
            if starts != [exp_s] or ends != [exp_e]:
                fails.append(f"{t} 起止标签异常: {starts}→{ends}，期望 {exp_s}→{exp_e}")

    checks = [
        ("nodes_total", base["nodes_total"], _EXPECTED["nodes_total"]),
        ("Truth_Point", base["labels"].get("Truth_Point"), _EXPECTED["Truth_Point"]),
        ("Trunk", base["labels"].get("Trunk"), _EXPECTED["Trunk"]),
        ("Branch", base["labels"].get("Branch"), _EXPECTED["Branch"]),
        ("rels_total", base["rels_total"], _EXPECTED["rels_total"]),
        ("old6_total", base["old6_total"], _EXPECTED["old6_total"]),
        ("class_total", base["class_total"], _EXPECTED["class_total"]),
    ]
    for t in list(_CLASS4) + list(_OLD6):
        checks.append((t, base["by_type"].get(t, 0), _EXPECTED[t]))
    for name, actual, expected in checks:
        if actual != expected:
            fails.append(f"{name}: 实测 {actual} ≠ 预期 {expected}")

    if base["orphan_after_delete_preview_count"] != 0:
        fails.append(
            f"删除后将孤立的 Truth_Point 预期 0，实测 {base['orphan_after_delete_preview_count']}: "
            f"{base['orphan_after_delete_preview_names']}"
        )
    return fails


def save_state(data: dict) -> None:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    _STATE.write_text(json.dumps(data, ensure_ascii=False, indent=2, default=str), encoding="utf-8")


def load_state() -> dict:
    if not _STATE.is_file():
        raise SystemExit(f"缺少状态文件 {_STATE}，请先 --stage check")
    return json.loads(_STATE.read_text(encoding="utf-8"))


def stage_check(env: dict, log: Logger) -> int:
    log.log("stage=check 开始（只读）")
    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            base = snapshot_baseline(session)
    except Exception as exc:
        raise SystemExit("check 失败: " + _redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    fails = gate_check(base)
    state = {
        "check_ok": not fails,
        "fails": fails,
        "baseline": base,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    save_state(state)
    log.log(f"nodes={base['nodes_total']} labels={base['labels']} same_as={base['same_as_n']}/{base['no_same_as_n']}")
    log.log(f"rels={base['rels_total']} by_type={base['by_type']}")
    log.log(f"old6_both_tp={base['old6_both_tp']}")
    log.log(f"class_total={base['class_total']} old6_total={base['old6_total']}")
    log.log(f"orphan_preview={base['orphan_after_delete_preview_count']}")
    if fails:
        for f in fails:
            log.log("GATE FAIL: " + f)
        write_report(state, delete=None, verify=None, env=env, log_path=log.path, stopped="check")
        log.log("闸门未通过，停止。未进入 delete。")
        return 2
    log.log("闸门全部通过。可进入 --stage delete")
    write_report(state, delete=None, verify=None, env=env, log_path=log.path, stopped=None)
    return 0


def class_counts(session) -> dict[str, int]:
    out = {}
    q = {
        "BELONGS_TO_TRUNK": "MATCH ()-[r:BELONGS_TO_TRUNK]->() RETURN count(r) AS c",
        "OF_BRANCH_DIRECTLY": "MATCH ()-[r:OF_BRANCH_DIRECTLY]->() RETURN count(r) AS c",
        "OF_BRANCH_INDIRECTLY": "MATCH ()-[r:OF_BRANCH_INDIRECTLY]->() RETURN count(r) AS c",
        "GRAFTING": "MATCH ()-[r:GRAFTING]->() RETURN count(r) AS c",
    }
    for t, query in q.items():
        out[t] = _run(session, query)[0]["c"]
    return out


def type_count_old(session, t: str) -> int:
    q = {
        "LEADS_TO": "MATCH ()-[r:LEADS_TO]->() RETURN count(r) AS c",
        "EXPERIENCES": "MATCH ()-[r:EXPERIENCES]->() RETURN count(r) AS c",
        "PRACTICED_AS": "MATCH ()-[r:PRACTICED_AS]->() RETURN count(r) AS c",
        "CONTAINS": "MATCH ()-[r:CONTAINS]->() RETURN count(r) AS c",
        "OPPOSES": "MATCH ()-[r:OPPOSES]->() RETURN count(r) AS c",
        "LOCATED_IN": "MATCH ()-[r:LOCATED_IN]->() RETURN count(r) AS c",
    }
    return _run(session, q[t])[0]["c"]


def stage_delete(env: dict, log: Logger) -> int:
    state = load_state()
    if not state.get("check_ok"):
        log.log("check 未通过，拒绝 delete")
        return 2
    base = state["baseline"]
    log.log("stage=delete 开始")

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    deleted: dict[str, int] = {t: 0 for t in _OLD6}
    batches: dict[str, list[int]] = {t: [] for t in _OLD6}
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=WRITE_ACCESS) as session:
            # D1 recheck
            rels = session.execute_read(_read, "MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
            by = {
                r["t"]: r["c"]
                for r in session.execute_read(
                    _read,
                    "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c ORDER BY t",
                )
            }
            if rels != base["rels_total"] or by != base["by_type"]:
                log.log(f"D1 失败：删除前与 C2 不一致 rels={rels}/{base['rels_total']} by={by}")
                write_report(state, delete={"aborted": True, "reason": "D1 mismatch", "by": by, "rels": rels}, verify=None, env=env, log_path=log.path, stopped="delete-D1")
                return 2
            log.log("D1 通过：关系总数与各类型与 C2 相同")
            class_before = {t: by[t] for t in _CLASS4}

            for t in _OLD6:
                log.log(f"删除 {t} 开始，目标 {base['by_type'][t]}")
                query = _DELETE_QUERIES[t]
                while True:
                    n = session.execute_write(_delete_batch, query, _BATCH)
                    if n == 0:
                        break
                    deleted[t] += n
                    batches[t].append(n)
                    log.log(f"  {t} batch deleted={n} cumulative={deleted[t]}")
                # verify type == 0
                left = type_count_old(session, t)
                if left != 0:
                    log.log(f"GATE FAIL: {t} 删后仍剩 {left}，停止后续类型")
                    write_report(
                        state,
                        delete={
                            "aborted": True,
                            "reason": f"{t} left={left}",
                            "deleted": deleted,
                            "batches": batches,
                        },
                        verify=None,
                        env=env,
                        log_path=log.path,
                        stopped="delete-type",
                    )
                    return 2
                class_now = class_counts(session)
                if class_now != class_before:
                    log.log(f"GATE FAIL: {t} 删后分类关系变化 {class_before} → {class_now}")
                    write_report(
                        state,
                        delete={
                            "aborted": True,
                            "reason": "class changed",
                            "deleted": deleted,
                            "class_before": class_before,
                            "class_now": class_now,
                        },
                        verify=None,
                        env=env,
                        log_path=log.path,
                        stopped="delete-class",
                    )
                    return 2
                log.log(f"  {t} 完成 deleted={deleted[t]}；分类关系未变")

            total = sum(deleted.values())
            log.log(f"全部完成 deleted={deleted} total={total}（预期 {_EXPECTED['old6_total']}）")
    except Exception as exc:
        raise SystemExit("delete 失败: " + _redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    delete_info = {
        "aborted": False,
        "deleted": deleted,
        "batches": batches,
        "total": sum(deleted.values()),
        "expected_total": _EXPECTED["old6_total"],
    }
    state["delete"] = delete_info
    save_state(state)
    write_report(state, delete=delete_info, verify=None, env=env, log_path=log.path, stopped=None)
    log.log("delete 完成。请运行 --stage verify")
    return 0


def stage_verify(env: dict, log: Logger) -> int:
    state = load_state()
    base = state["baseline"]
    log.log("stage=verify 开始（只读）")
    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            now = snapshot_baseline(session)
            # V2 per-TP checks
            belong = _run(
                session,
                """
                MATCH (n:Truth_Point)
                OPTIONAL MATCH (n)-[r:BELONGS_TO_TRUNK]->(:Trunk)
                WITH n, count(r) AS c
                RETURN sum(CASE WHEN c = 1 THEN 1 ELSE 0 END) AS exactly_one,
                       sum(CASE WHEN c <> 1 THEN 1 ELSE 0 END) AS bad,
                       count(n) AS points
                """,
            )[0]
            direct = _run(
                session,
                """
                MATCH (n:Truth_Point)
                OPTIONAL MATCH (n)-[r:OF_BRANCH_DIRECTLY]->(:Branch)
                WITH n, count(r) AS c
                RETURN sum(CASE WHEN c = 1 THEN 1 ELSE 0 END) AS exactly_one,
                       sum(CASE WHEN c <> 1 THEN 1 ELSE 0 END) AS bad,
                       count(n) AS points
                """,
            )[0]
            paren = []
            for outer, inner in _PAREN_PAIRS:
                rows = _run(
                    session,
                    """
                    MATCH (o:Truth_Point {name:$outer})
                    MATCH (i:Truth_Point {name:$inner})
                    OPTIONAL MATCH (o)-[:BELONGS_TO_TRUNK]->(ot:Trunk)
                    OPTIONAL MATCH (i)-[:BELONGS_TO_TRUNK]->(it:Trunk)
                    OPTIONAL MATCH (o)-[:OF_BRANCH_DIRECTLY]->(od:Branch)
                    OPTIONAL MATCH (i)-[:OF_BRANCH_DIRECTLY]->(id:Branch)
                    OPTIONAL MATCH (o)-[:OF_BRANCH_INDIRECTLY]->(oi:Branch)
                    OPTIONAL MATCH (i)-[:OF_BRANCH_INDIRECTLY]->(ii:Branch)
                    WITH collect(DISTINCT ot.name) AS o_t, collect(DISTINCT it.name) AS i_t,
                         collect(DISTINCT od.name) AS o_d, collect(DISTINCT id.name) AS i_d,
                         collect(DISTINCT oi.name) AS o_i, collect(DISTINCT ii.name) AS i_i
                    RETURN o_t, i_t, o_d, i_d, o_i, i_i
                    """,
                    {"outer": outer, "inner": inner},
                )
                row = rows[0]
                paren.append(
                    {
                        "outer": outer,
                        "inner": inner,
                        "trunk_eq": set(row["o_t"] or []) == set(row["i_t"] or []),
                        "direct_eq": set(row["o_d"] or []) == set(row["i_d"] or []),
                        "indirect_eq": set(row["o_i"] or []) == set(row["i_i"] or []),
                    }
                )
            isolated = _run(
                session,
                """
                MATCH (n:Truth_Point)
                WHERE NOT (n)--()
                RETURN count(n) AS c
                """,
            )[0]["c"]
            try:
                df = subprocess.check_output(
                    ["docker", "system", "df", "-v"],
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                vol_lines = [ln.strip() for ln in df.splitlines() if "neo4j_v4_data" in ln]
            except Exception as exc:
                vol_lines = [f"未取得: {exc}"]
    except Exception as exc:
        raise SystemExit("verify 失败: " + _redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    fails: list[str] = []
    # V1
    if now["rels_total"] != _EXPECTED["class_total"]:
        fails.append(f"关系总数 {now['rels_total']} ≠ {_EXPECTED['class_total']}")
    if set(now["by_type"].keys()) != set(_CLASS4):
        fails.append(f"类型集合 {sorted(now['by_type'].keys())} ≠ {list(_CLASS4)}")
    for t in _OLD6:
        if now["by_type"].get(t, 0) != 0:
            fails.append(f"旧类型 {t} 仍有 {now['by_type'].get(t)}")
    db_still = [t for t in now["db_relationship_types"] if t in _OLD6]
    # V2
    for t in _CLASS4:
        if now["by_type"].get(t, 0) != base["by_type"].get(t, 0):
            fails.append(f"分类 {t} 变化 {base['by_type'].get(t)} → {now['by_type'].get(t)}")
    if belong["bad"] != 0 or belong["exactly_one"] != _EXPECTED["Truth_Point"]:
        fails.append(f"BELONGS_TO_TRUNK 不满足: {belong}")
    if direct["bad"] != 0 or direct["exactly_one"] != _EXPECTED["Truth_Point"]:
        fails.append(f"OF_BRANCH_DIRECTLY 不满足: {direct}")
    for p in paren:
        if not (p["trunk_eq"] and p["direct_eq"] and p["indirect_eq"]):
            fails.append(f"括号分类不一致: {p}")
    # V3
    if now["nodes_total"] != base["nodes_total"] or now["labels"] != base["labels"]:
        fails.append(f"节点变化 nodes {base['nodes_total']}→{now['nodes_total']} labels {base['labels']}→{now['labels']}")
    tp = now["node_keys"]["Truth_Point"]["name_stats"]
    if not (tp["name_nonempty"] == tp["total"] == tp["name_distinct"] == _EXPECTED["Truth_Point"]):
        fails.append(f"Truth_Point name 异常: {tp}")
    if now["same_as_n"] != 8:
        fails.append(f"same_as 非空数 {now['same_as_n']} ≠ 8")
    base_pairs = {(r["inner"], r["outer"]) for r in base["same_as_rows"]}
    now_pairs = {(r["inner"], r["outer"]) for r in now["same_as_rows"]}
    if base_pairs != now_pairs:
        fails.append(f"same_as 对变化: {base_pairs} → {now_pairs}")
    for label in ("Truth_Point", "Trunk", "Branch"):
        keys = {r["key"] for r in now["node_keys"][label]["keys"]}
        expect = {"name", "same_as"} if label == "Truth_Point" else {"name"}
        # same_as may only appear on 8 nodes but key still listed
        if label == "Truth_Point":
            if keys - {"name", "same_as"}:
                fails.append(f"Truth_Point 多余标注: {keys}")
            if "name" not in keys:
                fails.append("Truth_Point 缺 name")
        else:
            if keys != {"name"}:
                fails.append(f"{label} 标注应为仅 name，实测 {keys}")
    # V4 compare constraint/index names lightly
    def _ci_sig(rows):
        out = []
        for r in rows:
            out.append(
                {
                    k: r.get(k)
                    for k in ("name", "type", "entityType", "labelsOrTypes", "properties", "state")
                    if k in r
                }
            )
        return sorted(out, key=lambda x: str(x.get("name")))

    if _ci_sig(now["constraints"]) != _ci_sig(base["constraints"]):
        fails.append("CONSTRAINTS 与基线不同")
    if _ci_sig(now["indexes"]) != _ci_sig(base["indexes"]):
        fails.append("INDEXES 与基线不同")
    # V6
    if isolated != 0:
        fails.append(f"孤立 Truth_Point = {isolated}")

    verify = {
        "fails": fails,
        "ok": not fails,
        "now": {
            "nodes_total": now["nodes_total"],
            "labels": now["labels"],
            "rels_total": now["rels_total"],
            "by_type": now["by_type"],
            "db_relationship_types": now["db_relationship_types"],
            "db_still_lists_old6": db_still,
            "same_as_rows": now["same_as_rows"],
            "belong": belong,
            "direct": direct,
            "paren": paren,
            "isolated": isolated,
            "volume_lines": vol_lines,
            "constraints": now["constraints"],
            "indexes": now["indexes"],
            "node_keys": now["node_keys"],
        },
    }
    state["verify"] = verify
    save_state(state)
    write_report(state, delete=state.get("delete"), verify=verify, env=env, log_path=log.path, stopped=None if not fails else "verify")
    if fails:
        for f in fails:
            log.log("VERIFY FAIL: " + f)
        return 2
    log.log("verify 全部通过")
    return 0


def write_report(state: dict, delete: dict | None, verify: dict | None, env: dict, log_path: Path, stopped: str | None) -> None:
    base = state["baseline"]
    lines: list[str] = []
    a = lines.append
    a("# neo4j-v4 删除旧 6 种关系报告")
    a("")
    a(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}；脚本：`panai4.graph.delete_old_relations`。")
    a("只删除 LEADS_TO / EXPERIENCES / PRACTICED_AS / CONTAINS / OPPOSES / LOCATED_IN（两端 Truth_Point）；未运行 build_v4.py；未打印密码。")
    a("")
    a("## 摘要")
    a("")
    # (1)
    mismatches = state.get("fails") or []
    a(f"1. **基线 vs 预期**：{'一致' if state.get('check_ok') else '不一致'}；不一致项：{mismatches or '无'}。")
    a(f"   实测节点={base['nodes_total']}（TP={base['labels'].get('Truth_Point')} Trunk={base['labels'].get('Trunk')} Branch={base['labels'].get('Branch')}）；"
      f"关系={base['rels_total']}；分类={base['class_total']}；旧6={base['old6_total']}；by_type={base['by_type']}。")
    # (2)
    if delete and not delete.get("aborted"):
        a(f"2. **删除条数**：{delete.get('deleted')}；合计 **{delete.get('total')}**（预期 {delete.get('expected_total')}）。")
    elif delete and delete.get("aborted"):
        a(f"2. **删除中止**：{delete}。")
    else:
        a("2. **删除条数**：尚未执行 delete。")
    # (3)(4)(5)(6)
    if verify:
        n = verify["now"]
        a(f"3. **删除后关系**：总数={n['rels_total']}；类型={n['by_type']}；"
          f"db.relationshipTypes 仍列旧名={n['db_still_lists_old6'] or '无'}（以 MATCH count 为准）。")
        a(f"4. **分类关系不变**：与基线比较失败项中分类相关见 verify.fails；当前 { {t:n['by_type'].get(t) for t in _CLASS4} } vs 基线 { {t:base['by_type'].get(t) for t in _CLASS4} }。")
        a(f"5. **节点/标注/约束/索引**：节点 {n['nodes_total']} labels={n['labels']}；same_as={n['same_as_rows']}；"
          f"verify.ok={verify['ok']}；失败={verify['fails'] or '无'}。")
        a(f"6. **孤立 Truth_Point**：{n['isolated']}（预期 0）。")
    else:
        a("3–6. 尚未 verify。")
    a(f"7. **闸门/待决**：stopped={stopped}；check_ok={state.get('check_ok')}；verify_ok={(verify or {}).get('ok')}。")
    a("")

    a("## C. check 基线")
    a(f"- docker：`{base['docker_ps']}`")
    a(f"- 组件：`{json.dumps(base['components'], ensure_ascii=False)}`")
    a(f"- 节点标签：{base['labels']}；合计 {base['nodes_total']}；same_as 有/无 = {base['same_as_n']}/{base['no_same_as_n']}")
    a("| 预期项 | 预期 | 实测 | 一致 |")
    a("|---|---:|---:|---|")
    rows = [
        ("nodes_total", _EXPECTED["nodes_total"], base["nodes_total"]),
        ("Truth_Point", _EXPECTED["Truth_Point"], base["labels"].get("Truth_Point")),
        ("Trunk", _EXPECTED["Trunk"], base["labels"].get("Trunk")),
        ("Branch", _EXPECTED["Branch"], base["labels"].get("Branch")),
        ("rels_total", _EXPECTED["rels_total"], base["rels_total"]),
        ("class_total", _EXPECTED["class_total"], base["class_total"]),
        ("old6_total", _EXPECTED["old6_total"], base["old6_total"]),
    ]
    for t in list(_CLASS4) + list(_OLD6):
        rows.append((t, _EXPECTED[t], base["by_type"].get(t, 0)))
    for name, exp, act in rows:
        a(f"| {name} | {exp} | {act} | {exp == act} |")
    a("")
    a("### 起止标签")
    for row in base["endpoint_combos"]:
        a(f"- {row['rel_type']}: {'+'.join(row['start_labels'] or [])}→{'+'.join(row['end_labels'] or [])} ×{row['c']}")
    a("")
    a("### 旧6两端皆 Truth_Point")
    for t, c in base["old6_both_tp"].items():
        a(f"- {t}: both_tp={c} total={base['by_type'].get(t)} equal={c==base['by_type'].get(t)}")
    a("")
    a("### 节点标注")
    for label, block in base["node_keys"].items():
        a(f"- {label} name_stats={block['name_stats']} keys={block['keys']}")
    a("")
    a("### same_as 8 对")
    for r in base["same_as_rows"]:
        a(f"- {r['inner']} → {r['outer']} (exists={r['outer_exists']})")
    a("")
    a("### 约束 / 索引（简表）")
    a("```json")
    a(json.dumps([{k: r.get(k) for k in ('name','type','entityType','labelsOrTypes','properties','state') if k in r} for r in base['constraints']], ensure_ascii=False, indent=2, default=str))
    a("```")
    a("```json")
    a(json.dumps([{k: r.get(k) for k in ('name','type','entityType','labelsOrTypes','properties','state') if k in r} for r in base['indexes']], ensure_ascii=False, indent=2, default=str))
    a("```")
    a(f"- 删除预演：将删旧6={base['old6_total']}；剩余={base['class_total']}；删除后无分类关系的 TP={base['orphan_after_delete_preview_count']} 样本={base['orphan_after_delete_preview_names']}")
    a(f"- 闸门失败：{state.get('fails') or '无'}")
    a("")

    a("## D. delete")
    if not delete:
        a("未执行。")
    else:
        a(f"```json\n{json.dumps(delete, ensure_ascii=False, indent=2)}\n```")
    a("")

    a("## V. verify")
    if not verify:
        a("未执行。")
    else:
        n = verify["now"]
        a(f"- ok={verify['ok']} fails={verify['fails'] or '无'}")
        a(f"- rels={n['rels_total']} by_type={n['by_type']}")
        a(f"- db.relationshipTypes={n['db_relationship_types']}；仍列旧6={n['db_still_lists_old6']}")
        a(f"- belong={n['belong']} direct={n['direct']}")
        a(f"- paren={n['paren']}")
        a(f"- nodes={n['nodes_total']} labels={n['labels']} isolated={n['isolated']}")
        a(f"- same_as={n['same_as_rows']}")
        a(f"- volume: {n['volume_lines']}")
    a("")

    a("## 最终验证")
    # secret check
    report_so_far = "\n".join(lines)
    leaked = bool(env["pass4"] and env["pass4"] in report_so_far)
    log_text = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    leaked_log = bool(env["pass4"] and env["pass4"] in log_text)
    a(f"- 只执行按类型删除旧6种：是（若已 delete）")
    a(f"- 未运行 build_v4.py：是")
    a(f"- 未读取并打印 .env 值：是")
    a(f"- 报告密码检查：{'不通过' if leaked else '通过'}；日志密码检查：{'不通过' if leaked_log else '通过'}")
    try:
        gs = subprocess.check_output(
            ["git", "status", "--short"],
            cwd=str(_REPO),
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except Exception as exc:
        gs = str(exc)
    a("- git status（本任务仅应新增 delete_old_relations.py / 本报告 / logs；其余为既有改动）：")
    a("```")
    a(gs)
    a("```")
    a("")

    text = "\n".join(lines) + "\n"
    if env["pass4"] and env["pass4"] in text:
        raise SystemExit("中止：报告含密码")
    _REPORT.parent.mkdir(parents=True, exist_ok=True)
    _REPORT.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="删除 neo4j-v4 旧 6 种词条间关系")
    parser.add_argument("--stage", required=True, choices=["check", "delete", "verify"])
    args = parser.parse_args()
    env = _load_env()
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = Logger(_LOG_DIR / f"delete_old_relations_{_now()}.log", env["pass4"])
    log.log(f"stage={args.stage}；使用 NEO4J_V4_URI / NEO4J_V4_USER / NEO4J_V4_PASSWORD（值不记录）")
    if args.stage == "check":
        return stage_check(env, log)
    if args.stage == "delete":
        return stage_delete(env, log)
    return stage_verify(env, log)


if __name__ == "__main__":
    sys.exit(main())
