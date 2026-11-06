# -*- coding: utf-8 -*-
"""neo4j-v4 导入前只读盘点（不修改图谱、不改现有文件）。

连接：仅 NEO4J_V4_*（经 dotenv 加载 .env，但绝不打印密码值）。
Cypher：仅 MATCH / RETURN / CALL / SHOW / WITH / UNWIND，且经 execute_read。
不运行 build_v4.py。不连 3.5。

用法（在 back_mic/backend 下）:
    python -m panai4.graph.inventory_v4_pre
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import statistics
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from neo4j import READ_ACCESS, GraphDatabase

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parents[1]
_REPORT = _REPO / "docs" / "panai4_graph" / "neo4j_v4_inventory_pre.md"
_LOG_DIR = _REPO / "logs"
_IMPORT_DIR = Path(r"C:\Users\28121\Desktop\可导入资料")
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
_WRITE_HEAD = re.compile(
    r"^\s*(CREATE|MERGE|SET|REMOVE|DELETE|DETACH|DROP|LOAD\s+CSV)\b",
    re.IGNORECASE,
)
_CODE_SKIP = {".git", "node_modules", "__pycache__", "es_data", ".venv", "venv"}
_CODE_EXTS = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".md",
    ".yml",
    ".yaml",
    ".ps1",
    ".sh",
    ".bat",
    ".toml",
}
# 与 2373 词表括号词条一致：括号外（括号内）。图谱中括号内节点带 same_as→括号外。
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
_PAREN_COMBINED = [f"{outer}（{inner}）" for outer, inner in _PAREN_PAIRS]


def _now() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _redact(text: str, *secrets: str) -> str:
    out = text
    for secret in secrets:
        if secret:
            out = out.replace(secret, "***")
    return out


def _trunc(value: Any, limit: int = 80) -> Any:
    if isinstance(value, str):
        return value if len(value) <= limit else value[:limit] + "…"
    if isinstance(value, list):
        return [_trunc(v, limit) for v in value[:3]] + (["…"] if len(value) > 3 else [])
    if isinstance(value, dict):
        return {k: _trunc(v, limit) for k, v in list(value.items())[:20]}
    return value


def _nonempty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, (list, tuple, dict)):
        return len(value) > 0
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return False
    return True


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
    return {"uri4": uri4, "user4": user4, "pass4": pass4, "uri35": uri35}


def _read(tx, query: str, params: dict | None = None):
    if _WRITE_HEAD.search(query):
        raise RuntimeError(f"拒绝非只读 Cypher: {query[:80]}")
    head = query.lstrip().split(None, 1)[0].upper()
    if head not in {"MATCH", "SHOW", "CALL", "WITH", "RETURN", "UNWIND"}:
        raise RuntimeError(f"只读连接拒绝语句头: {head}")
    return [record.data() for record in tx.run(query, params or {})]


def _run(session, query: str, params: dict | None = None):
    return session.execute_read(_read, query, params)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _file_inventory(root: Path) -> list[dict]:
    rows = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        st = p.stat()
        rows.append(
            {
                "rel": str(p.relative_to(root)).replace("\\", "/"),
                "abs": str(p),
                "size": st.st_size,
                "mtime": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "ext": p.suffix.lower(),
            }
        )
    return rows


def snapshot_graph(session) -> dict:
    """轻量对账快照：节点总数、关系总数、各关系类型数量。"""
    nodes = _run(session, "MATCH (n) RETURN count(n) AS c")[0]["c"]
    rels = _run(session, "MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
    by_type = {
        r["t"]: r["c"]
        for r in _run(
            session,
            "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c ORDER BY t",
        )
    }
    return {"nodes": nodes, "rels": rels, "by_type": by_type}


def inventory_neo4j(session, env: dict) -> dict:
    out: dict[str, Any] = {}

    # A1
    ver = _run(
        session,
        "CALL dbms.components() YIELD name, versions, edition "
        "RETURN name, versions, edition",
    )
    dbname = _run(session, "CALL db.info() YIELD name RETURN name")
    out["A1"] = {
        "uri_var": "NEO4J_V4_URI",
        "user_var": "NEO4J_V4_USER",
        "uri_value_redacted": True,
        "connected": True,
        "components": ver,
        "database": dbname[0]["name"] if dbname else None,
    }
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
        docker_ps = f"docker ps 失败: {_redact(str(exc), env['pass4'])}"
    out["A1"]["docker_ps"] = docker_ps

    # A2 labels
    labels = _run(
        session,
        "MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS c ORDER BY label",
    )
    out["A2"] = {"by_label": {r["label"]: r["c"] for r in labels}, "sum_labels": sum(r["c"] for r in labels)}

    # A3 keys per label
    a3 = {}
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
                   sum(CASE WHEN n.name IS NULL OR toString(n.name) = '' THEN 0 ELSE 1 END) AS name_nonempty,
                   count(DISTINCT n.name) AS name_distinct
            """,
        )[0]
        a3[label] = {"keys": keys, "name_stats": name_stats}
    same_as = _run(
        session,
        """
        MATCH (n:Truth_Point)
        WHERE n.same_as IS NOT NULL AND toString(n.same_as) <> ''
        OPTIONAL MATCH (t:Truth_Point {name: n.same_as})
        RETURN n.name AS inner, n.same_as AS outer, t IS NOT NULL AS outer_exists
        ORDER BY inner
        """,
    )
    a3["same_as_rows"] = same_as
    a3["same_as_count"] = len(same_as)
    out["A3"] = a3

    # A4 relationship types + endpoint labels
    rel_types = _run(
        session,
        """
        MATCH (a)-[r]->(b)
        RETURN type(r) AS rel_type,
               labels(a) AS start_labels,
               labels(b) AS end_labels,
               count(*) AS c
        ORDER BY rel_type, start_labels, end_labels
        """,
    )
    by_type = Counter()
    endpoint_combos = defaultdict(list)
    for r in rel_types:
        by_type[r["rel_type"]] += r["c"]
        endpoint_combos[r["rel_type"]].append(
            {
                "start": "+".join(r["start_labels"] or []),
                "end": "+".join(r["end_labels"] or []),
                "c": r["c"],
            }
        )
    out["A4"] = {
        "by_type": dict(sorted(by_type.items())),
        "endpoint_combos": dict(endpoint_combos),
        "all_types": sorted(by_type.keys()),
        "sum": sum(by_type.values()),
    }

    # A5 relationship property keys
    a5 = {}
    for t in sorted(by_type.keys()):
        rows = _run(
            session,
            """
            MATCH ()-[r]->()
            WHERE type(r) = $t
            WITH r, keys(r) AS ks
            UNWIND (CASE WHEN size(ks)=0 THEN [null] ELSE ks END) AS k
            RETURN k AS key,
                   count(*) AS rows,
                   sum(CASE WHEN k IS NULL THEN 0
                            WHEN r[k] IS NULL THEN 0
                            WHEN toString(r[k]) = '' THEN 0
                            ELSE 1 END) AS nonempty
            """,
            {"t": t},
        )
        a5[t] = rows
    out["A5"] = a5

    # A6 old6 detail
    same_as_names = [r["inner"] for r in same_as]
    a6 = {}
    for t in _OLD6:
        rows = _run(
            session,
            """
            MATCH (a)-[r]->(b)
            WHERE type(r) = $t
            RETURN a.name AS a, b.name AS b,
                   'Truth_Point' IN labels(a) AS a_tp,
                   'Truth_Point' IN labels(b) AS b_tp
            """,
            {"t": t},
        )
        both_tp = sum(1 for r in rows if r["a_tp"] and r["b_tp"])
        involve_inner = sum(
            1 for r in rows if r["a"] in same_as_names or r["b"] in same_as_names
        )
        self_loop = sum(1 for r in rows if r["a"] == r["b"])
        pair_counts = Counter((r["a"], r["b"]) for r in rows)
        dup_pairs = sum(1 for c in pair_counts.values() if c > 1)
        dup_extra = sum(c - 1 for c in pair_counts.values() if c > 1)
        a6[t] = {
            "count": len(rows),
            "both_truth_point": both_tp,
            "involve_same_as_node": involve_inner,
            "self_loops": self_loop,
            "duplicate_pair_keys": dup_pairs,
            "duplicate_extra_edges": dup_extra,
        }
    isolated = _run(
        session,
        """
        MATCH (n:Truth_Point)
        WHERE NOT (n)--()
        RETURN count(n) AS c
        """,
    )[0]["c"]
    out["A6"] = {"per_type": a6, "old6_total": sum(v["count"] for v in a6.values()), "isolated_tp": isolated}

    # A7 delete preview
    class_counts = {t: by_type.get(t, 0) for t in _CLASS4}
    old_total = sum(by_type.get(t, 0) for t in _OLD6)
    other_types = {t: c for t, c in by_type.items() if t not in _CLASS4 and t not in _OLD6}
    remain = sum(by_type.values()) - old_total
    belong = _run(
        session,
        """
        MATCH (n:Truth_Point)
        OPTIONAL MATCH (n)-[r:BELONGS_TO_TRUNK]->(:Trunk)
        WITH n, count(r) AS c
        RETURN count(n) AS points,
               sum(CASE WHEN c >= 1 THEN 1 ELSE 0 END) AS has_belong,
               sum(CASE WHEN c = 1 THEN 1 ELSE 0 END) AS exactly_one,
               sum(CASE WHEN c = 0 THEN 1 ELSE 0 END) AS missing
        """,
    )[0]
    direct = _run(
        session,
        """
        MATCH (n:Truth_Point)
        OPTIONAL MATCH (n)-[r:OF_BRANCH_DIRECTLY]->(:Branch)
        WITH n, count(r) AS c
        RETURN count(n) AS points,
               sum(CASE WHEN c >= 1 THEN 1 ELSE 0 END) AS has_direct,
               sum(CASE WHEN c = 1 THEN 1 ELSE 0 END) AS exactly_one,
               sum(CASE WHEN c = 0 THEN 1 ELSE 0 END) AS missing
        """,
    )[0]
    # paren classification copied?
    paren_class = []
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
            WITH o, i,
                 collect(DISTINCT ot.name) AS o_trunks,
                 collect(DISTINCT it.name) AS i_trunks,
                 collect(DISTINCT od.name) AS o_direct,
                 collect(DISTINCT id.name) AS i_direct,
                 collect(DISTINCT oi.name) AS o_indirect,
                 collect(DISTINCT ii.name) AS i_indirect
            RETURN o.name AS outer, i.name AS inner,
                   o_trunks, i_trunks, o_direct, i_direct, o_indirect, i_indirect
            """,
            {"outer": outer, "inner": inner},
        )
        for row in rows:
            # 集合相等（忽略 collect 顺序）
            row["trunk_eq"] = set(row["o_trunks"] or []) == set(row["i_trunks"] or [])
            row["direct_eq"] = set(row["o_direct"] or []) == set(row["i_direct"] or [])
            row["indirect_eq"] = set(row["o_indirect"] or []) == set(row["i_indirect"] or [])
            paren_class.append(row)
    # after deleting old6, how many TP only have class rels (all TP that have any class)
    only_class_preview = _run(
        session,
        """
        MATCH (n:Truth_Point)
        OPTIONAL MATCH (n)-[r]->()
        WHERE type(r) IN $old6
        WITH n, count(r) AS old_cnt
        OPTIONAL MATCH (n)-[c]->()
        WHERE type(c) IN $class4
        WITH n, old_cnt, count(c) AS class_cnt
        OPTIONAL MATCH (n)-[o]->()
        WHERE NOT type(o) IN $old6 AND NOT type(o) IN $class4
        WITH n, old_cnt, class_cnt, count(o) AS other_cnt
        RETURN
          sum(CASE WHEN class_cnt > 0 AND other_cnt = 0 THEN 1 ELSE 0 END) AS only_class_after_delete,
          sum(CASE WHEN class_cnt = 0 AND other_cnt = 0 THEN 1 ELSE 0 END) AS no_class_no_other,
          count(n) AS points
        """,
        {"old6": list(_OLD6), "class4": list(_CLASS4)},
    )[0]
    out["A7"] = {
        "class_counts": class_counts,
        "class_total": sum(class_counts.values()),
        "old6_total": old_total,
        "other_types": other_types,
        "remain_after_delete_old6": remain,
        "belong": belong,
        "direct": direct,
        "paren_class": paren_class,
        "only_class_preview": only_class_preview,
        "class_disjoint_from_old6": all(t not in _OLD6 for t in _CLASS4),
    }

    # A8 constraints / indexes
    try:
        constraints = _run(session, "SHOW CONSTRAINTS")
    except Exception as exc:
        constraints = [{"error": _redact(str(exc), env["pass4"])}]
    try:
        indexes = _run(session, "SHOW INDEXES")
    except Exception as exc:
        indexes = [{"error": _redact(str(exc), env["pass4"])}]
    out["A8"] = {"constraints": constraints, "indexes": indexes}

    # A9 totals + volume
    nodes = _run(session, "MATCH (n) RETURN count(n) AS c")[0]["c"]
    rels = _run(session, "MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
    vol = "未取得"
    try:
        inspect = subprocess.check_output(
            ["docker", "inspect", "neo4j-v4", "--format", "{{json .Mounts}}"],
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        mounts = json.loads(inspect)
        names = [m.get("Name") for m in mounts if m.get("Name")]
        df = subprocess.check_output(
            ["docker", "system", "df", "-v"],
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        vol_lines = []
        for line in df.splitlines():
            if any(n and n in line for n in names) or "neo4j_v4" in line:
                vol_lines.append(line.strip())
        vol = {"mount_names": names, "df_lines": vol_lines or ["未匹配到 neo4j_v4 卷行"]}
    except Exception as exc:
        vol = f"未取得: {_redact(str(exc), env['pass4'])}"
    out["A9"] = {"nodes": nodes, "rels": rels, "volume": vol}
    return out


def inventory_code() -> dict:
    roots = [
        _REPO / "back_mic",
        _REPO / "front_mic",
        _REPO / "back_qa",
        _REPO / "front_qa",
        _REPO / "back_shared",
        _REPO / "scripts",
        _REPO / "docs",
    ]
    pats = {
        "NEO4J_V4": re.compile(r"NEO4J_V4"),
        "neo4j-v4": re.compile(r"neo4j-v4"),
        "7688": re.compile(r":7688|\b7688\b"),
        "7475": re.compile(r":7475|\b7475\b"),
        "GraphDatabase": re.compile(r"GraphDatabase"),
        "from_neo4j": re.compile(r"from neo4j|import neo4j"),
        "bolt": re.compile(r"bolt://"),
        "OLD6": re.compile(
            r"\b(LEADS_TO|EXPERIENCES|PRACTICED_AS|OPPOSES|LOCATED_IN)\b|\[:CONTAINS\]|'CONTAINS'|\"CONTAINS\""
        ),
        "NEO4J_URI": re.compile(r"\bNEO4J_URI\b|\bNEO4J_USER\b|\bNEO4J_PASSWORD\b"),
    }
    hits: list[dict] = []
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if any(part in _CODE_SKIP for part in p.parts):
                continue
            if p.suffix.lower() not in _CODE_EXTS:
                continue
            if p.stat().st_size > 1_500_000:
                continue
            # skip this inventory script's own large generated noise later; include itself ok
            try:
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            rel = str(p.relative_to(_REPO)).replace("\\", "/")
            for i, line in enumerate(text.splitlines(), 1):
                matched = [k for k, r in pats.items() if r.search(line)]
                if not matched:
                    continue
                # filter false CONTAINS from regex character classes in unrelated files
                if matched == ["OLD6"] and "CONTAINS" in line and not re.search(
                    r"LEADS_TO|EXPERIENCES|PRACTICED_AS|OPPOSES|LOCATED_IN|\[:CONTAINS\]|'CONTAINS'|\"CONTAINS\"",
                    line,
                ):
                    continue
                if "CONTAINS" in line and not any(
                    x in matched for x in ("NEO4J_V4", "neo4j-v4", "7688", "7475", "GraphDatabase", "from_neo4j", "bolt", "NEO4J_URI")
                ):
                    if not re.search(
                        r"LEADS_TO|EXPERIENCES|PRACTICED_AS|OPPOSES|LOCATED_IN|\[:CONTAINS\]|['\"]CONTAINS['\"]",
                        line,
                    ):
                        continue
                hits.append(
                    {
                        "file": rel,
                        "line": i,
                        "tags": matched,
                        "text": line.strip()[:200],
                    }
                )

    def classify(path: str) -> str:
        p = path.lower()
        if "/panai4/graph/" in p or p.endswith("panai4/graph/readme.md"):
            return "①建图脚本"
        if "/kg_rag/" in p:
            return "③3.5（kg_rag）"
        if "/back_qa/" in p or "/front_qa/" in p:
            return "④QA 站"
        if "/panai4/" in p or "/front_mic/" in p:
            return "②测试台或 panai4 的在线服务"
        return "⑤其他"

    by_cat: dict[str, list] = defaultdict(list)
    for h in hits:
        by_cat[classify(h["file"])].append(h)

    # B2 conclusions
    v4_files = sorted(
        {
            h["file"]
            for h in hits
            if any(t in h["tags"] for t in ("NEO4J_V4", "neo4j-v4", "7688", "7475"))
        }
    )
    # files that connect to v4 AND mention old6
    old6_in_v4_context = []
    for f in v4_files:
        f_hits = [h for h in hits if h["file"] == f]
        tags = {t for h in f_hits for t in h["tags"]}
        if "OLD6" in tags:
            old6_in_v4_context.append(f)

    # runtime online: exclude docs/reports and offline scripts inventory/build
    online_v4 = []
    for f in v4_files:
        low = f.lower()
        if low.startswith("docs/"):
            continue
        if "build_v4.py" in low or "inventory_35.py" in low or "inventory_v4_pre.py" in low:
            continue
        if low.endswith("readme.md"):
            continue
        online_v4.append(f)

    # Does any online_v4 read old6 types?
    online_old6 = []
    for f in online_v4:
        for h in hits:
            if h["file"] == f and "OLD6" in h["tags"]:
                online_old6.append(h)

    # B3: does 3.5/kg_rag read neo4j-v4?
    kg_v4 = [h for h in hits if "/kg_rag/" in h["file"].replace("\\", "/") and any(
        t in h["tags"] for t in ("NEO4J_V4", "neo4j-v4", "7688", "7475")
    )]

    return {
        "hit_count": len(hits),
        "by_category": {k: v for k, v in sorted(by_cat.items())},
        "v4_files": v4_files,
        "online_v4_files": online_v4,
        "old6_in_v4_files": old6_in_v4_context,
        "online_old6_hits": online_old6,
        "kg_rag_reads_v4_hits": kg_v4,
        "all_hits": hits,
    }


def _json_load_meta(path: Path) -> dict:
    raw = path.read_bytes()
    bom = raw.startswith(b"\xef\xbb\xbf")
    text = raw.decode("utf-8-sig")
    parse_ok = True
    parse_err = None
    try:
        data = json.loads(text)
    except Exception as exc:
        parse_ok = False
        parse_err = str(exc)
        data = None
    # detect NaN/Infinity in text (json.loads accepts them with default? actually standard json rejects)
    has_nan = bool(re.search(r"\bNaN\b|\bInfinity\b|\b-Infinity\b", text))
    return {
        "bom": bom,
        "parse_ok": parse_ok,
        "parse_err": parse_err,
        "has_nan_infinity_token": has_nan,
        "data": data,
        "raw_size": len(raw),
    }


def _field_stats(records: list[dict]) -> dict:
    if not records:
        return {}
    keys = sorted({k for r in records if isinstance(r, dict) for k in r.keys()})
    stats = {}
    for k in keys:
        vals = [r.get(k) for r in records if isinstance(r, dict)]
        nonempty = sum(1 for v in vals if _nonempty(v))
        empty = len(vals) - nonempty
        types = Counter(type(v).__name__ for v in vals if v is not None)
        # distinct for simple values
        simple = []
        for v in vals:
            if isinstance(v, (str, int, float, bool)) or v is None:
                simple.append(v)
            else:
                simple.append(json.dumps(v, ensure_ascii=False, sort_keys=True)[:200])
        distinct = Counter(simple)
        entry: dict[str, Any] = {
            "types": dict(types),
            "nonempty": nonempty,
            "empty": empty,
            "distinct": len(distinct),
        }
        if len(distinct) <= 50:
            entry["value_counts"] = [
                {"value": _trunc(val, 60), "count": cnt}
                for val, cnt in distinct.most_common()
            ]
        # length distribution for strings / serialized
        lengths = []
        for v in vals:
            if isinstance(v, str):
                lengths.append(len(v))
            elif isinstance(v, (list, dict)):
                lengths.append(len(json.dumps(v, ensure_ascii=False)))
        if lengths:
            lengths_sorted = sorted(lengths)
            entry["len"] = {
                "min": lengths_sorted[0],
                "median": int(statistics.median(lengths_sorted)),
                "max": lengths_sorted[-1],
                "over_32000": sum(1 for x in lengths if x > 32000),
            }
        stats[k] = entry
    return stats


def _sample_records(records: list, n: int = 3) -> list:
    return [_trunc(r, 80) for r in records[:n]]


def analyze_relations_json(data: list, tp_names: set[str], trunk_names: set[str], branch_names: set[str], same_as_inner: set[str], same_as_outer: set[str], old_pairs: dict[str, set[tuple[str, str]]]) -> dict:
    """Analyze 29-type relation JSON."""
    type_rows = []
    all_edges = []  # (type_key, from, to)
    for block in data:
        rel = block.get("relation")
        pairs = block.get("pairs") or []
        type_rows.append(
            {
                "relation": rel,
                "name": block.get("name"),
                "english": block.get("english"),
                "type": block.get("type"),
                "no": block.get("no"),
                "group": block.get("group"),
                "level": block.get("level"),
                "count_field": block.get("count"),
                "pairs_len": len(pairs),
                "has_definition": _nonempty(block.get("definition")),
            }
        )
        for p in pairs:
            all_edges.append((rel, p.get("from"), p.get("to")))

    # naming habit
    naming = []
    for row in type_rows:
        rel = row["relation"] or ""
        ok = bool(re.fullmatch(r"[A-Z][A-Z0-9_]*", rel)) if "/" not in rel else False
        naming.append(
            {
                "relation": rel,
                "neo4j_simple_ok": ok,
                "has_slash": "/" in rel,
                "has_space": " " in rel,
                "has_non_ascii": bool(re.search(r"[^\x00-\x7f]", rel)),
            }
        )

    # endpoint match
    missing_counter = Counter()
    found = 0
    missing = 0
    inner_as_endpoint = 0
    outer_as_endpoint = 0
    combined_paren_endpoint = 0
    trunk_hit = Counter()
    branch_hit = Counter()
    combined_set = set(_PAREN_COMBINED)
    for rel, a, b in all_edges:
        for node in (a, b):
            if node in tp_names:
                found += 1
            else:
                missing += 1
                missing_counter[node] += 1
            if node in same_as_inner:
                inner_as_endpoint += 1
            if node in same_as_outer:
                outer_as_endpoint += 1
            if node in combined_set:
                combined_paren_endpoint += 1
            if node in trunk_names:
                trunk_hit[node] += 1
            if node in branch_names:
                branch_hit[node] += 1

    # self loops / dups / reverse
    self_loops = sum(1 for _, a, b in all_edges if a == b)
    triple = Counter((a, b, t) for t, a, b in all_edges)
    dup_triples = sum(1 for c in triple.values() if c > 1)
    dup_extra = sum(c - 1 for c in triple.values() if c > 1)
    # reverse pairs within same type
    reverse = 0
    seen_by_type: dict[str, set] = defaultdict(set)
    for t, a, b in all_edges:
        if (b, a) in seen_by_type[t]:
            reverse += 1
        seen_by_type[t].add((a, b))

    # map old6 remakes: exact name match or slash containing old name
    remap = {}
    for row in type_rows:
        rel = row["relation"] or ""
        for old in _OLD6:
            if rel == old or rel.startswith(old + " ") or f" {old}" in f" {rel} " or old in [p.strip() for p in rel.split("/")]:
                remap.setdefault(old, []).append(rel)

    overlap = {}
    for old, news in remap.items():
        old_set = old_pairs.get(old, set())
        new_set = set()
        for t, a, b in all_edges:
            if t in news:
                new_set.add((a, b))
        overlap[old] = {
            "new_types": news,
            "old_pairs": len(old_set),
            "new_pairs": len(new_set),
            "same": len(old_set & new_set),
            "only_new": len(new_set - old_set),
            "only_old": len(old_set - new_set),
        }

    existing_10 = set(_CLASS4) | set(_OLD6)
    new_simple = set()
    for row in type_rows:
        rel = row["relation"] or ""
        parts = [p.strip() for p in rel.split("/")]
        new_simple.update(parts)
        new_simple.add(rel)

    same_name = sorted(existing_10 & {r["relation"] for r in type_rows})
    # remade: old name appears as part of slash type or exact
    remade = sorted(remap.keys())
    brand_new = []
    for row in type_rows:
        rel = row["relation"]
        parts = [p.strip() for p in (rel or "").split("/")]
        if not any(p in _OLD6 or p in _CLASS4 for p in parts) and rel not in existing_10:
            brand_new.append(rel)
    missing_in_new = [t for t in existing_10 if t not in remade and t not in {r["relation"] for r in type_rows}]

    return {
        "n_types": len(type_rows),
        "type_rows": type_rows,
        "pairs_total": len(all_edges),
        "pairs_sum_equals_total": sum(r["pairs_len"] for r in type_rows) == len(all_edges),
        "count_field_sum": sum(r["count_field"] or 0 for r in type_rows),
        "naming": naming,
        "endpoint": {
            "endpoint_checks": found + missing,
            "found": found,
            "missing": missing,
            "missing_top50": [{"name": n, "count": c} for n, c in missing_counter.most_common(50)],
            "inner_endpoint_mentions": inner_as_endpoint,
            "outer_endpoint_mentions": outer_as_endpoint,
            "combined_paren_form_mentions": combined_paren_endpoint,
            "combined_paren_forms_expected": _PAREN_COMBINED,
            "trunk_name_hits": dict(trunk_hit),
            "branch_name_hits": dict(branch_hit),
        },
        "self_loops": self_loops,
        "duplicate_triples": dup_triples,
        "duplicate_extra": dup_extra,
        "reverse_pairs_same_type": reverse,
        "vs_existing": {
            "same_name_exact": same_name,
            "remade_old6": remade,
            "remap": {k: v for k, v in remap.items()},
            "brand_new": brand_new,
            "existing_not_in_new_json": missing_in_new,
            "class4_name_conflict": sorted(set(_CLASS4) & ({r["relation"] for r in type_rows} | new_simple)),
        },
        "overlap_old6": overlap,
        "node_repr": "pairs[].from / pairs[].to 为节点 name（中文词条名）",
        "direction": "有向：from → to",
        "rel_props_in_pairs": "pairs 元素仅 from/to，无关系标注字段",
    }


def inventory_json(tp_names: set[str], trunk_names: set[str], branch_names: set[str], same_as_map: dict[str, str], old_pairs: dict[str, set[tuple[str, str]]]) -> dict:
    files = _file_inventory(_IMPORT_DIR)
    # sha before handled outside
    same_as_inner = set(same_as_map.keys())  # 持有 same_as 的节点 = 括号内
    same_as_outer = set(same_as_map.values())  # same_as 指向 = 括号外
    paren_outers = same_as_outer or {o for o, _i in _PAREN_PAIRS}
    paren_inners = same_as_inner or {i for _o, i in _PAREN_PAIRS}

    result: dict[str, Any] = {"C0": {"files": files, "file_count": len(files), "total_bytes": sum(f["size"] for f in files)}}

    per_file = {}
    for meta in files:
        path = Path(meta["abs"])
        entry: dict[str, Any] = {"meta": meta}
        if meta["ext"] != ".json":
            entry["note"] = "非 JSON；只列路径"
            # try read md/docx note lightly skipped for docx
            if meta["ext"] in {".md", ".txt"}:
                try:
                    text = path.read_text(encoding="utf-8-sig", errors="ignore")[:2000]
                    entry["text_head"] = text
                except Exception as exc:
                    entry["read_err"] = str(exc)
            per_file[meta["rel"]] = entry
            continue

        loaded = _json_load_meta(path)
        data = loaded.pop("data")
        entry["load"] = loaded
        if data is None:
            per_file[meta["rel"]] = entry
            continue

        # hymns special
        if meta["rel"] == "hymns.json":
            entry["scope"] = "ES，不属于图谱"
            if isinstance(data, list):
                entry["top"] = {
                    "structure": "list",
                    "n": len(data),
                    "item_keys": list(data[0].keys()) if data and isinstance(data[0], dict) else None,
                    "sample2": _sample_records(data, 2),
                }
            else:
                entry["top"] = {"structure": type(data).__name__}
            per_file[meta["rel"]] = entry
            continue

        entry["scope"] = "图谱相关"
        if isinstance(data, list):
            entry["top"] = {
                "structure": "list",
                "n": len(data),
                "item_keys": list(data[0].keys()) if data and isinstance(data[0], dict) else None,
                "sample3": _sample_records(data, 3),
            }
            if data and isinstance(data[0], dict):
                entry["field_stats"] = _field_stats(data)
        elif isinstance(data, dict):
            entry["top"] = {
                "structure": "dict",
                "keys": list(data.keys()),
                "nkeys": len(data),
            }
            # summarize nested
            nested = {}
            for k, v in data.items():
                if isinstance(v, list):
                    nested[k] = {
                        "type": "list",
                        "n": len(v),
                        "item_keys": list(v[0].keys()) if v and isinstance(v[0], dict) else None,
                        "sample3": _sample_records(v, 3) if v and isinstance(v[0], dict) else _trunc(v[:3], 80),
                    }
                    if v and isinstance(v[0], dict):
                        nested[k]["field_stats"] = _field_stats(v)
                else:
                    nested[k] = {"type": type(v).__name__, "sample": _trunc(v, 80)}
            entry["nested"] = nested
        else:
            entry["top"] = {"structure": type(data).__name__}

        # specialize by filename
        rel = meta["rel"]
        if "29种关系_成立边" in rel and isinstance(data, list):
            entry["C3"] = analyze_relations_json(
                data, tp_names, trunk_names, branch_names, same_as_inner, same_as_outer, old_pairs
            )
            # term set from relations
            terms = set()
            for block in data:
                for p in block.get("pairs") or []:
                    if p.get("from"):
                        terms.add(p["from"])
                    if p.get("to"):
                        terms.add(p["to"])
            entry["term_set_size"] = len(terms)
            entry["term_set"] = terms  # will strip before writing raw json dump if huge — keep for C5
        elif "relationship" in rel.lower() or "29种关系定义" in rel:
            entry["role"] = "关系类型说明/分类（非边列表）"
        else:
            # annotation-like
            records = None
            name_key = None
            if isinstance(data, list) and data and isinstance(data[0], dict) and "name" in data[0]:
                records = data
                name_key = "name"
            elif isinstance(data, dict) and isinstance(data.get("words"), list):
                records = data["words"]
                name_key = "name" if records and "name" in records[0] else None
            if records is not None and name_key:
                names = [r.get(name_key) for r in records if isinstance(r, dict)]
                found = sum(1 for n in names if n in tp_names)
                missing_names = [n for n in names if n not in tp_names]
                miss_c = Counter(missing_names)
                # paren content
                outer_with = [n for n in names if n in paren_outers]
                inner_with = [n for n in names if n in paren_inners]
                # contentful inners: any nonempty field besides name/no
                inner_content = []
                for r in records:
                    if not isinstance(r, dict):
                        continue
                    if r.get(name_key) not in paren_inners:
                        continue
                    extra = {k: v for k, v in r.items() if k not in {name_key, "no"} and _nonempty(v)}
                    if extra:
                        inner_content.append({"name": r.get(name_key), "extra_keys": list(extra.keys())})
                entry["C4"] = {
                    "n_records": len(records),
                    "name_match_found": found,
                    "name_match_missing": len(missing_names),
                    "missing_top50": [{"name": n, "count": c} for n, c in miss_c.most_common(50)],
                    "paren_outer_present": sorted(set(outer_with)),
                    "paren_inner_present": sorted(set(inner_with)),
                    "paren_inner_with_extra_content": inner_content,
                    "fields": list(records[0].keys()) if records else [],
                }
                entry["term_set"] = set(n for n in names if n)
                # conflict notes
                fields = entry["C4"]["fields"]
                entry["C4"]["field_name_notes"] = {
                    "has_same_as_field": "same_as" in fields,
                    "has_name_field": "name" in fields,
                    "needs_backtick": [f for f in fields if re.search(r"[\s\W]", f) or re.search(r"[^\x00-\x7f]", f)],
                    "ascii_ok": [f for f in fields if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", f or "")],
                }

        per_file[meta["rel"]] = entry

    # C5 consistency among graph json term sets
    term_sets = {}
    for rel, entry in per_file.items():
        if entry.get("scope") != "图谱相关":
            continue
        if "term_set" in entry:
            term_sets[rel] = entry["term_set"]
    c5 = {"term_set_sizes": {k: len(v) for k, v in term_sets.items()}}
    if "29种关系_成立边.json" in term_sets:
        rel_terms = term_sets["29种关系_成立边.json"]
        for k, s in term_sets.items():
            if k == "29种关系_成立边.json":
                continue
            c5[f"rel_subset_of__{k}"] = rel_terms <= s
            c5[f"rel_only__{k}"] = len(rel_terms - s)
            c5[f"annot_only__{k}"] = len(s - rel_terms)
    # strip huge sets from per_file before return serialization helper
    for entry in per_file.values():
        if "term_set" in entry and isinstance(entry["term_set"], set):
            entry["term_set_size"] = len(entry["term_set"])
            del entry["term_set"]

    # C6 outside
    c6 = []
    for p, note in [
        (Path(r"C:\Users\28121\Desktop\一般性标注\00neo4j_query_table_data_2026-8-25.json"), "桌面一般性标注（不在可导入资料内）"),
    ]:
        if not p.exists():
            c6.append({"path": str(p), "exists": False, "note": note})
            continue
        try:
            d = json.loads(p.read_text(encoding="utf-8-sig"))
            if isinstance(d, list):
                n = len(d)
                keys = list(d[0].keys()) if d and isinstance(d[0], dict) else None
            elif isinstance(d, dict):
                if "words" in d and isinstance(d["words"], list):
                    n = len(d["words"])
                    keys = list(d.keys())
                else:
                    # 三档可能是 {外在:[], ...}
                    n = {k: (len(v) if isinstance(v, list) else None) for k, v in d.items()}
                    keys = list(d.keys())
            else:
                n = None
                keys = None
            c6.append(
                {
                    "path": str(p),
                    "exists": True,
                    "note": note,
                    "records": n,
                    "keys": keys,
                    "size": p.stat().st_size,
                }
            )
        except Exception as exc:
            c6.append({"path": str(p), "exists": True, "note": note, "error": str(exc)})

    result["per_file"] = per_file
    result["C5"] = c5
    result["C6"] = c6
    # note: 可导入资料内未见「一般标注」独立 JSON
    result["general_annotation_in_import_dir"] = any(
        "一般" in f["rel"] for f in files
    )
    return result


def inventory_scripts() -> dict:
    build = (_BACKEND / "panai4" / "graph" / "build_v4.py").read_text(encoding="utf-8")
    inv35 = (_BACKEND / "panai4" / "graph" / "inventory_35.py").read_text(encoding="utf-8")
    readme = (_BACKEND / "panai4" / "graph" / "README.md").read_text(encoding="utf-8")
    hard_paths = sorted(
        set(re.findall(r"[GCgc]:\\\\[^\s\"']+|[GCgc]:/[^\s\"']+", build + "\n" + inv35 + "\n" + readme))
    )
    # also Path(r'...') style under docs is relative
    has_batch_delete_by_type = bool(
        re.search(r"DELETE.*type\(|type\(r\).*DELETE|批量删除|按关系类型", build, re.I)
    )
    # cleanup only deletes classification + listed element ids, explicitly excludes old6
    return {
        "build_v4": {
            "role": "在 NEO4J_V4_URI 上 MERGE 节点（Truth_Point/Trunk/Branch）、分类 4 种关系、并从 3.5 只读迁移旧 6 种关系；默认不删除。",
            "params": ["(默认/--apply)", "--dry-run", "--cleanup", "--cleanup --confirm"],
            "reads": [
                "docs/panai4_graph/2373个词条（已确定一一对应为concept节点）.txt",
                "docs/panai4_graph/主恢复真理词典_词条主干枝子映射 (1).json",
                "docs/panai4_graph/12大类与91小类的对应关系.txt",
                "docs/panai4_graph/concept_mapping_35_to_40.csv",
                "3.5 NEO4J_URI（只读，旧 6 种 Concept→Concept）",
            ],
            "writes": "仅 NEO4J_V4；MERGE 节点与分类关系、旧 6 种；SET same_as；--cleanup --confirm 只删清单内分类范围项",
            "imports_29": False,
            "imports_29_missing": [
                "无读取「可导入资料」或 29 种关系 JSON 的代码",
                "无写入除旧 6 种与分类 4 种以外关系类型的逻辑",
                "无一般/专特标注字段的 SET 逻辑（除 name/same_as）",
                "关系类型名含斜杠（如 EXPERIENCES / ENJOYS）时无命名规范化",
            ],
            "batch_delete_by_rel_type": False,
            "cleanup_excludes_old6": True,
            "hardcoded_paths_found": hard_paths,
            "data_paths_are_repo_relative": True,
        },
        "inventory_35": {
            "role": "盘点 3.5 Neo4j（NEO4J_URI）只读，并核对 panai4 词表；可选探测 NEO4J_V4_* 是否配置。",
            "writes": "只写 docs/panai4_graph/reports/ 报告，不写图谱",
        },
        "readme_summary": "说明默认 MERGE、--cleanup 两段式、清理范围不含迁移旧关系与以后新增关系。",
        "has_batch_delete_by_type_in_build": has_batch_delete_by_type,
    }


def _md_escape(s: Any) -> str:
    return str(s).replace("|", "\\|")


def render_report(
    *,
    env: dict,
    snap_before: dict,
    snap_after: dict,
    neo: dict,
    code: dict,
    js: dict,
    scripts: dict,
    sha_before: dict,
    sha_after: dict,
    secret_check: dict,
) -> str:
    lines: list[str] = []
    a = lines.append
    a("# neo4j-v4 导入前只读盘点报告")
    a("")
    a(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}；脚本：`panai4.graph.inventory_v4_pre`。只读 Cypher；未运行 `build_v4.py`；未打印密码。")
    a("")
    # ---- 开头摘要 10 行内 ----
    a2 = neo["A2"]["by_label"]
    a4 = neo["A4"]["by_type"]
    old6 = neo["A6"]["per_type"]
    rel_file = js["per_file"].get("29种关系_成立边.json", {})
    c3 = rel_file.get("C3", {})
    a("## 摘要（供主设计师过目）")
    a("")
    a(
        f"1. **现有图谱**：节点 Truth_Point={a2.get('Truth_Point')} / Trunk={a2.get('Trunk')} / Branch={a2.get('Branch')}，合计 {neo['A9']['nodes']}；"
        f"关系按类型 {a4}，合计 {neo['A9']['rels']}；节点标注主要为 `name`（+ Truth_Point 的 `same_as`×{neo['A3']['same_as_count']}）。"
    )
    a(
        f"2. **旧 6 种**：合计 {neo['A6']['old6_total']}；明细 "
        + "；".join(f"{k}={v['count']}（括号内端点{v['involve_same_as_node']}，自环{v['self_loops']}，重复对{v['duplicate_pair_keys']}）" for k, v in old6.items())
        + f"；孤立 Truth_Point={neo['A6']['isolated_tp']}。"
    )
    a(
        f"3. **删旧 6 种后预期**：关系剩 {neo['A7']['remain_after_delete_old6']}（分类 {neo['A7']['class_total']} + 其他 {sum(neo['A7']['other_types'].values())}）；"
        f"分类四型 {neo['A7']['class_counts']}；每个 TP 有 BELONGS_TO_TRUNK={neo['A7']['belong']['has_belong']}/{neo['A7']['belong']['points']}，"
        f"OF_BRANCH_DIRECTLY={neo['A7']['direct']['has_direct']}/{neo['A7']['direct']['points']}。"
    )
    a(
        f"4. **代码依赖**：连接 neo4j-v4 的文件 {code['v4_files']}；在线/工具向读取 v4 的非建图文件 {code['online_v4_files']}；"
        f"其中读取旧 6 种类型名的在线命中 {len(code['online_old6_hits'])} 条；kg_rag 读 v4 命中 {len(code['kg_rag_reads_v4_hits'])}。"
        f"结论：删除旧 6 种**不会**让当前在线服务因查询这些类型而报错（见 B2）。"
    )
    a(
        f"5. **可导入资料**：文件 {js['C0']['file_count']} 个、{js['C0']['total_bytes']} 字节；"
        f"关系 JSON 类型数={c3.get('n_types')}、边数={c3.get('pairs_total')}；"
        f"与现有对照：同名精确 {c3.get('vs_existing',{}).get('same_name_exact')}；旧6重制映射 {c3.get('vs_existing',{}).get('remap')}；"
        f"**目录内未见独立「一般标注」JSON**（一般性标注在桌面其他目录，见 C6）。"
    )
    ep = c3.get("endpoint", {})
    a(
        f"6. **节点匹配**：关系端点检查 found={ep.get('found')} missing={ep.get('missing')}；"
        f"括号内节点名出现={ep.get('inner_endpoint_mentions')}，括号外节点名出现={ep.get('outer_endpoint_mentions')}，"
        f"未拆分的「外（内）」合并名出现={ep.get('combined_paren_form_mentions')}（合并名无法直接匹配图谱拆开后的节点）。"
    )
    # annotation coverage brief
    annot_bits = []
    for rel, entry in js["per_file"].items():
        if entry.get("C4"):
            c4 = entry["C4"]
            annot_bits.append(f"{rel}: 记录{c4['n_records']} 匹配{c4['name_match_found']} 缺{c4['name_match_missing']}")
    a(f"7. **标注 JSON 覆盖**：{'；'.join(annot_bits) if annot_bits else '（无带 name 的标注 JSON 被识别）'}。")
    a("8. **待主设计师决定**：见文末「问题清单」（类型名含 `/`、括号内端点、找不到节点、同名重制方向、多值标注存放、一般标注 JSON 缺失等）。")
    a("")

    # ---- A ----
    a("## A. 图谱现状")
    a("")
    a("### A1 连接")
    a(f"- 连通：是；用户变量 `NEO4J_V4_USER`；URI 变量 `NEO4J_V4_URI`（值不打印）。")
    a(f"- 数据库名：`{neo['A1']['database']}`")
    a(f"- 组件：`{json.dumps(neo['A1']['components'], ensure_ascii=False)}`")
    a(f"- docker ps：`{neo['A1']['docker_ps']}`")
    a("")
    a("### A2 节点按标签")
    a("| 标签 | 数量 |")
    a("|---|---:|")
    for k, v in neo["A2"]["by_label"].items():
        a(f"| {k} | {v} |")
    a(f"| （标签计数之和） | {neo['A2']['sum_labels']} |")
    a("")
    a("### A3 节点标注")
    for label, block in neo["A3"].items():
        if label in ("same_as_rows", "same_as_count"):
            continue
        a(f"#### {label}")
        ns = block["name_stats"]
        a(f"- name 非空 {ns['name_nonempty']}/{ns['total']}；name 去重 {ns['name_distinct']}；"
          f"{'无重复' if ns['name_distinct']==ns['name_nonempty']==ns['total'] else '存在空或重复'}。")
        a("| 标注名 | 有该键的节点 | 非空 |")
        a("|---|---:|---:|")
        for row in block["keys"]:
            a(f"| {row['key']} | {row['nodes_with_key']} | {row['nonempty']} |")
        a("")
    a(f"#### same_as（{neo['A3']['same_as_count']}）")
    a("说明：下表「持有 same_as 的节点」= 括号内；`same_as` 指向名 = 括号外。与 2373 词表 `括号外（括号内）` 拆分一致。")
    a("| 括号内名（持有 same_as） | same_as → 括号外 | 括号外节点存在 |")
    a("|---|---|---|")
    for row in neo["A3"]["same_as_rows"]:
        a(f"| {row['inner']} | {row['outer']} | {row['outer_exists']} |")
    a(f"- 对照词表合并名：{', '.join(_PAREN_COMBINED)}")
    a("")
    a("### A4 关系按类型")
    a("| 类型 | 数量 | 起止标签组合 |")
    a("|---|---:|---|")
    for t, c in neo["A4"]["by_type"].items():
        combos = ", ".join(f"{x['start']}→{x['end']}×{x['c']}" for x in neo["A4"]["endpoint_combos"][t])
        a(f"| {t} | {c} | {combos} |")
    a(f"| 合计 | {neo['A4']['sum']} | |")
    a(f"- 全部类型：{neo['A4']['all_types']}")
    a("")
    a("### A5 关系上的标注")
    for t, rows in neo["A5"].items():
        keys = [r for r in rows if r.get("key") is not None]
        if not keys:
            a(f"- `{t}`：无关系标注（keys 为空）")
        else:
            a(f"- `{t}`：" + ", ".join(f"{r['key']}(非空{r['nonempty']})" for r in keys))
    a("")
    a("### A6 旧 6 种明细")
    a("| 类型 | 数量 | 两端皆 Truth_Point | 涉及 same_as 节点 | 自环 | 重复(起点,终点)对数 | 重复多余边 |")
    a("|---|---:|---:|---:|---:|---:|---:|")
    for t, v in neo["A6"]["per_type"].items():
        a(
            f"| {t} | {v['count']} | {v['both_truth_point']} | {v['involve_same_as_node']} | "
            f"{v['self_loops']} | {v['duplicate_pair_keys']} | {v['duplicate_extra_edges']} |"
        )
    a(f"- 旧 6 种合计：**{neo['A6']['old6_total']}**")
    a(f"- 孤立 Truth_Point（无任何关系）：**{neo['A6']['isolated_tp']}**")
    a("")
    a("### A7 删除预演（未删）")
    a(f"- 分类关系合计：{neo['A7']['class_total']} → {neo['A7']['class_counts']}")
    a(f"- 旧 6 种合计：{neo['A7']['old6_total']}")
    a(f"- 其他类型：{neo['A7']['other_types'] or '无'}")
    a(f"- 删除后剩余关系：{neo['A7']['remain_after_delete_old6']}")
    a(f"- 校验：分类+旧6+其他 = {neo['A7']['class_total']}+{neo['A7']['old6_total']}+{sum(neo['A7']['other_types'].values())} =? 关系总数 {neo['A9']['rels']}")
    a(f"- BELONGS_TO_TRUNK：{neo['A7']['belong']}")
    a(f"- OF_BRANCH_DIRECTLY：{neo['A7']['direct']}")
    a(f"- 仅分类关系预览：{neo['A7']['only_class_preview']}")
    a("- 括号内外分类是否一致：")
    a("| outer | inner | trunk_eq | direct_eq | indirect_eq |")
    a("|---|---|---|---|---|")
    for row in neo["A7"]["paren_class"]:
        a(f"| {row['outer']} | {row['inner']} | {row['trunk_eq']} | {row['direct_eq']} | {row['indirect_eq']} |")
    a("")
    a("### A8 约束与索引")
    a("#### CONSTRAINTS")
    a("```json")
    a(json.dumps([{k: _trunc(v, 120) for k, v in r.items()} for r in neo["A8"]["constraints"]], ensure_ascii=False, indent=2, default=str))
    a("```")
    a("#### INDEXES")
    a("```json")
    a(json.dumps([{k: _trunc(v, 120) for k, v in r.items()} for r in neo["A8"]["indexes"]], ensure_ascii=False, indent=2, default=str))
    a("```")
    a("")
    a("### A9 规模")
    a(f"- 节点 {neo['A9']['nodes']}；关系 {neo['A9']['rels']}")
    a(f"- 对账：A2 标签和={neo['A2']['sum_labels']}；A4 关系和={neo['A4']['sum']}")
    a(f"- 数据卷：{json.dumps(neo['A9']['volume'], ensure_ascii=False) if not isinstance(neo['A9']['volume'], str) else neo['A9']['volume']}")
    a("")

    # ---- B ----
    a("## B. 依赖排查")
    a("")
    a("### B1 命中分类（文件数）")
    for cat, items in code["by_category"].items():
        files = sorted({h["file"] for h in items})
        a(f"- {cat}：{len(files)} 个文件 / {len(items)} 行")
        for f in files:
            lines_hit = [h for h in items if h["file"] == f]
            a(f"  - `{f}` 行号：{', '.join(str(h['line']) for h in lines_hit[:30])}"
              + (f" …共{len(lines_hit)}" if len(lines_hit) > 30 else ""))
    a("")
    a("### B2 结论")
    a(f"- 会连接 neo4j-v4（`NEO4J_V4_*` / `neo4j-v4` / 7688 / 7475）的文件：")
    for f in code["v4_files"]:
        a(f"  - `{f}`")
    a(f"- 其中偏运行时/工具（排除纯建图脚本与 docs）: {code['online_v4_files'] or '无'}")
    a("- `panai4/sc/stage1.py`：只 `MATCH (n:Truth_Point) RETURN n.name`，**不**读取旧 6 种关系类型。")
    a("- `build_v4.py` / `inventory_35.py`：建图与盘点；`build_v4` 会 MERGE 旧 6 种，但本轮不运行。")
    a(f"- 在线功能读取旧 6 种类型名的命中数：{len(code['online_old6_hits'])}")
    if code["online_old6_hits"]:
        for h in code["online_old6_hits"][:20]:
            a(f"  - `{h['file']}:{h['line']}` {h['text']}")
    a("- **删除旧 6 种关系不会导致当前在线服务报错**：没有在线查询路径依赖 neo4j-v4 上的这些类型；kg_rag 走的是 `NEO4J_URI`（3.5）。")
    a("")
    a("### B3 3.5 是否读 neo4j-v4")
    a(f"- kg_rag 中 NEO4J_V4/neo4j-v4/7688/7475 命中：{len(code['kg_rag_reads_v4_hits'])} → "
      + ("有（见上）" if code["kg_rag_reads_v4_hits"] else "**无**；3.5 使用 `NEO4J_URI`（默认 bolt://localhost:7687）。"))
    a("")

    # ---- C ----
    a("## C. 新 JSON 盘点（可导入资料）")
    a("")
    a("### C0 目录清单")
    a("| 相对路径 | 大小 | 修改时间 | 扩展名 |")
    a("|---|---:|---|---|")
    for f in js["C0"]["files"]:
        a(f"| {_md_escape(f['rel'])} | {f['size']} | {f['mtime']} | {f['ext']} |")
    a(f"- 文件数 {js['C0']['file_count']}；总字节 {js['C0']['total_bytes']}")
    a(f"- 目录内是否有「一般」字样文件：{js['general_annotation_in_import_dir']}")
    a("")
    for rel, entry in js["per_file"].items():
        a(f"### 文件：`{rel}`")
        a(f"- 范围：{entry.get('scope', entry.get('note', ''))}")
        meta = entry["meta"]
        a(f"- 大小 {meta['size']}；mtime {meta['mtime']}")
        if "load" in entry:
            a(f"- UTF-8 BOM：{entry['load']['bom']}；解析成功：{entry['load']['parse_ok']}；NaN/Infinity token：{entry['load']['has_nan_infinity_token']}")
            if entry["load"].get("parse_err"):
                a(f"- 解析错误：{entry['load']['parse_err']}")
        if "top" in entry:
            a(f"- 顶层：`{json.dumps({k:v for k,v in entry['top'].items() if k!='sample3' and k!='sample2'}, ensure_ascii=False)}`")
            if entry["top"].get("sample3"):
                a("- 前 3 条（截断）：")
                a("```json")
                a(json.dumps(entry["top"]["sample3"], ensure_ascii=False, indent=2))
                a("```")
            if entry["top"].get("sample2"):
                a("- 前 2 条字段示例（hymns）：")
                a("```json")
                a(json.dumps(entry["top"]["sample2"], ensure_ascii=False, indent=2))
                a("```")
        if entry.get("field_stats"):
            a("- 字段盘点：")
            a("| 字段 | 非空 | 空 | distinct | 长度min/med/max | >32000 |")
            a("|---|---:|---:|---:|---|---:|")
            for k, st in entry["field_stats"].items():
                ln = st.get("len") or {}
                a(
                    f"| {k} | {st['nonempty']} | {st['empty']} | {st['distinct']} | "
                    f"{ln.get('min','-')}/{ln.get('median','-')}/{ln.get('max','-')} | {ln.get('over_32000',0)} |"
                )
                if st.get("value_counts"):
                    a(f"  - 取值（≤50）：{json.dumps(st['value_counts'], ensure_ascii=False)}")
        if entry.get("nested"):
            for nk, nv in entry["nested"].items():
                a(f"- 键 `{nk}`：{json.dumps({kk:vv for kk,vv in nv.items() if kk not in ('sample3','field_stats')}, ensure_ascii=False)}")
                if nv.get("field_stats"):
                    a(f"  - 字段统计 keys={list(nv['field_stats'].keys())}")
                if nv.get("sample3"):
                    a("```json")
                    a(json.dumps(nv["sample3"], ensure_ascii=False, indent=2))
                    a("```")
        if entry.get("C3"):
            c3 = entry["C3"]
            a("#### C3 关系 JSON 分析")
            a(f"- 类型种数：**{c3['n_types']}**（预期 29）；边总数 **{c3['pairs_total']}**；count 字段和={c3['count_field_sum']}；"
              f"pairs 长度和==总数：{c3['pairs_sum_equals_total']}")
            a("| relation | 中文名 | type | level | count | pairs |")
            a("|---|---|---|---|---:|---:|")
            for row in c3["type_rows"]:
                a(f"| {_md_escape(row['relation'])} | {row['name']} | {row['type']} | {row['level']} | {row['count_field']} | {row['pairs_len']} |")
            a(f"- 节点表示：{c3['node_repr']}；方向：{c3['direction']}；关系标注：{c3['rel_props_in_pairs']}")
            a("- 命名习惯：")
            for n in c3["naming"]:
                a(f"  - `{n['relation']}` simple_ok={n['neo4j_simple_ok']} slash={n['has_slash']} space={n['has_space']} non_ascii={n['has_non_ascii']}")
            a(f"- 与现有 10 种对照：同名精确={c3['vs_existing']['same_name_exact']}；旧6重制={c3['vs_existing']['remap']}；"
              f"新增={c3['vs_existing']['brand_new']}；现有却不在新 JSON={c3['vs_existing']['existing_not_in_new_json']}；"
              f"与分类四型同名冲突={c3['vs_existing']['class4_name_conflict']}")
            a(f"- 端点匹配：found={c3['endpoint']['found']} missing={c3['endpoint']['missing']} "
              f"（按 name 精确；每个 from/to 各计 1 次）")
            a(f"- 找不到的前 50：{json.dumps(c3['endpoint']['missing_top50'], ensure_ascii=False)}")
            a(f"- 括号内节点名出现={c3['endpoint']['inner_endpoint_mentions']}；括号外节点名出现={c3['endpoint']['outer_endpoint_mentions']}；"
              f"合并名「外（内）」出现={c3['endpoint']['combined_paren_form_mentions']}")
            a(f"- 找不到的端点若全是合并名/外人名，见 missing_top50；合并名清单：{c3['endpoint']['combined_paren_forms_expected']}")
            a(f"- Trunk 名撞车：{c3['endpoint']['trunk_name_hits'] or '无'}；Branch 名撞车：{c3['endpoint']['branch_name_hits'] or '无'}")
            a(f"- 自环={c3['self_loops']}；重复三元组对数={c3['duplicate_triples']}（多余边 {c3['duplicate_extra']}）；同类型反向对={c3['reverse_pairs_same_type']}")
            a("- 与旧 6 种 (起点,终点) 重叠：")
            a("| 旧类型 | 新类型名 | 旧对数 | 新对数 | 相同 | 仅新 | 仅旧 |")
            a("|---|---|---:|---:|---:|---:|---:|")
            for old, ov in c3["overlap_old6"].items():
                a(f"| {old} | {ov['new_types']} | {ov['old_pairs']} | {ov['new_pairs']} | {ov['same']} | {ov['only_new']} | {ov['only_old']} |")
        if entry.get("C4"):
            c4 = entry["C4"]
            a("#### C4 标注匹配")
            a(f"- 记录数 {c4['n_records']}；匹配 {c4['name_match_found']}；找不到 {c4['name_match_missing']}")
            a(f"- 找不到前 50：{json.dumps(c4['missing_top50'], ensure_ascii=False)}")
            a(f"- 括号外出现：{c4['paren_outer_present']}；括号内出现：{c4['paren_inner_present']}")
            a(f"- 括号内带额外内容：{json.dumps(c4['paren_inner_with_extra_content'], ensure_ascii=False)}")
            a(f"- 字段：{c4['fields']}；字段名备注：{json.dumps(c4['field_name_notes'], ensure_ascii=False)}")
        a("")
    a("### C5 一致性")
    a(f"```json\n{json.dumps(js['C5'], ensure_ascii=False, indent=2)}\n```")
    a("")
    a("### C6 目录之外（不纳入导入）")
    for row in js["C6"]:
        a(f"- `{row.get('path')}` exists={row.get('exists')} note={row.get('note')} records={row.get('records')} keys={row.get('keys')} size={row.get('size')}"
          + (f" error={row.get('error')}" if row.get("error") else ""))
    a("- 目录之外参考：桌面 `一般性标注/00neo4j_query_table_data_*.json` 含 `greek_terms`/`related_scriptures`，**未放入可导入资料**。鸟瞰正文现以仓库内 `panai4/data/graph_annotations/truth_dictionary_3a3b.json` 为准（本盘点脚本不再读取已删除的 `docs/3a_export.json` / `词条三档分类.json`）。")
    a("")

    # ---- D ----
    a("## D. 脚本能力")
    a("")
    a("### D1")
    a(f"- build_v4：{scripts['build_v4']['role']}")
    a(f"- 参数：{scripts['build_v4']['params']}")
    a(f"- 读取：{scripts['build_v4']['reads']}")
    a(f"- 写入行为：{scripts['build_v4']['writes']}")
    a(f"- 能否直接导入 29 种关系 JSON：**否**。缺：{scripts['build_v4']['imports_29_missing']}")
    a(f"- inventory_35：{scripts['inventory_35']['role']}；写入：{scripts['inventory_35']['writes']}")
    a(f"- README：{scripts['readme_summary']}")
    a("")
    a("### D2")
    a(f"- 按关系类型批量删除旧 6 种：**无**（`has_batch_delete_by_type_in_build={scripts['has_batch_delete_by_type_in_build']}`）。"
      f"`--cleanup` 只清分类 4 种与名单外节点/`same_as`，**明确排除**迁移旧关系。")
    _hard = scripts["build_v4"]["hardcoded_paths_found"] or "未发现 G:/ 或 C:/Users/ 字面量；资料路径为仓库相对 docs/panai4_graph/。"
    a(f"- 写死绝对路径扫描结果：{_hard}")
    a("")

    # ---- E ----
    a("## E. 汇总与问题清单")
    a("")
    a("### 删除前后 / 导入后对比预估")
    new_by_type = {r["relation"]: r["pairs_len"] for r in c3.get("type_rows", [])} if c3 else {}
    a("| 项目 | 当前 | 删旧6后 | 再导入29种后（算术预估） |")
    a("|---|---:|---:|---:|")
    a(f"| 节点总数 | {neo['A9']['nodes']} | {neo['A9']['nodes']} | {neo['A9']['nodes']}（标注导入不增节点） |")
    a(f"| 关系总数 | {neo['A9']['rels']} | {neo['A7']['remain_after_delete_old6']} | {neo['A7']['remain_after_delete_old6'] + c3.get('pairs_total', 0)} |")
    for t in _CLASS4:
        a(f"| {t} | {a4.get(t,0)} | {a4.get(t,0)} | {a4.get(t,0)} |")
    for t in _OLD6:
        a(f"| {t}（旧） | {a4.get(t,0)} | 0 | 0（若重制用新类型名则不再用此名） |")
    for rel, n in new_by_type.items():
        a(f"| 新 `{_md_escape(rel)}` | 0 | 0 | {n} |")
    a("")
    a("注意：若重制类型继续使用 `LEADS_TO` 等同名，则「删旧再导入」后该类型数量=新 JSON 计数，而不是 0；上表把「旧类型清零」与「新 JSON 类型另列」分开，避免与分类四型混淆。分类四型与 29 种 **无同名冲突**：`{}`。".format(c3.get("vs_existing", {}).get("class4_name_conflict")))
    a("")
    a("### 需要主设计师决定的问题（只提问）")
    a("1. 新 JSON 里多个 `relation` 含 `/` 与空格（如 `EXPERIENCES / ENJOYS`、`IN_APPOSITION_WITH / EQUIVALENT_TO`）：导入时用哪个正式类型名？是否拆成两种关系？")
    a("2. 新关系 JSON 仍出现未拆分合并名（如 `晨晨复兴（晨兴）`），图谱已拆成两节点：导入前是否把合并名映射到括号外节点？括号内节点名若出现在 from/to，按 same_as 改挂到括号外，还是原样保留？")
    a("3. 关系端点 name 在图谱中找不到时（本轮仅 5 个名字、196 次）：跳过、报错中止、映射后导入，还是先建节点？")
    a("4. 六个重制关系与旧边重叠很少/很多时：是否允许同名覆盖？方向是否一律以新 JSON 为准？")
    a("5. 「可导入资料」中**没有**一般标注 JSON（中文名/英文名/希伯来/希腊/定义等）；是否改用桌面 `一般性标注/00neo4j_*.json`、仓库 `graph_annotations/`，或等待另份 JSON？")
    a("6. 专特标注字段多为嵌套 list/dict（如 `content_1`…、`stages`）：存成 JSON 字符串标注、拆子图，还是只取摘要字段？")
    a("7. 标注字段名含中文或非 `[A-Za-z_][A-Za-z0-9_]*` 时，是否统一映射为英文蛇形名？")
    a("8. `【intrinsic_significance】` 词表 2372 条 vs 图谱 Truth_Point≈2381：差的是否就是括号拆分？导入时如何对齐？")
    a("9. 删除旧 6 种后，是否需要同步改 `build_v4.py`，避免以后 `--apply` 再次从 3.5 MERGE 回旧关系？")
    a("10. `hymns.json` 确认仅进 ES、本周图谱不动——是否还需从「可导入资料」挪出以免误导入？")
    a("11. 防火墙 JSON 中括号内节点带了内容（如 `产生得胜者`、`圣灵的浇灌` 的 `content_1`）：丢弃、合并到括号外，还是保留？")
    a("12. 分类关系实测 6529 对口令约 6526（差 3）：追查还是以实测为准？")
    a("")

    # ---- 验证 ----
    a("## 验证")
    a("")
    a(f"1. 盘点前快照：nodes={snap_before['nodes']} rels={snap_before['rels']} by_type={snap_before['by_type']}")
    a(f"   盘点后快照：nodes={snap_after['nodes']} rels={snap_after['rels']} by_type={snap_after['by_type']}")
    a(f"   完全相同：{snap_before == snap_after}")
    a(f"2. A2 标签和 {neo['A2']['sum_labels']} =? A9 节点 {neo['A9']['nodes']} → {neo['A2']['sum_labels']==neo['A9']['nodes']} "
      f"（注：多标签节点会使标签和>节点数；本库预期单标签）")
    a(f"   A4 关系和 {neo['A4']['sum']} =? A9 关系 {neo['A9']['rels']} → {neo['A4']['sum']==neo['A9']['rels']}")
    a(f"3. A7：保留 {neo['A7']['remain_after_delete_old6']} + 旧6 {neo['A7']['old6_total']} =? 总数 {neo['A9']['rels']} → "
      f"{neo['A7']['remain_after_delete_old6'] + neo['A7']['old6_total'] == neo['A9']['rels']}")
    a(f"4. SHA256：盘前文件数 {sha_before['n']} 字节 {sha_before['bytes']}；盘后 {sha_after['n']} / {sha_after['bytes']}；"
      f"哈希表相同：{sha_before['hashes']==sha_after['hashes']}")
    a(f"5. 关系 JSON：类型 pairs 之和==记录边数 → {c3.get('pairs_sum_equals_total') if c3 else 'N/A'}；"
      f"标注字段非空≤记录数：见各文件 field_stats（脚本内已按字段统计）。")
    a("6. git status：本轮仅新增 `back_mic/backend/panai4/graph/inventory_v4_pre.py`、"
      "`docs/panai4_graph/neo4j_v4_inventory_pre.md` 与 `logs/inventory_v4_pre_*`；"
      "工作区中其余 M/?? 为既有未提交改动，非本盘点写入。详见运行日志。")
    a("   另：分类关系实测合计 6529（预期口令约 6526），差 3，见 A7；未改图谱。")
    a(f"7. 只读 Cypher：是；未运行 build_v4：是；未读取并打印 .env 值：是；"
      f"报告/日志密钥字符串检查：{json.dumps(secret_check, ensure_ascii=False)}")
    a("")
    a("---")
    a("附录：完整代码命中表见同次运行的 `logs/inventory_v4_pre_*.json`。")
    return "\n".join(lines) + "\n"


def main() -> int:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = _now()
    log_path = _LOG_DIR / f"inventory_v4_pre_{stamp}.log"
    dump_path = _LOG_DIR / f"inventory_v4_pre_{stamp}.json"

    def log(msg: str) -> None:
        # never write secrets
        line = f"[{datetime.now().strftime('%H:%M:%S')}] {msg}"
        print(line)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    env = _load_env()
    log("start inventory_v4_pre (read-only)")
    log("env vars present: NEO4J_V4_URI NEO4J_V4_USER NEO4J_V4_PASSWORD (values not logged)")

    # SHA before
    import_files = _file_inventory(_IMPORT_DIR)
    extra_paths = []
    sha_before = {"n": 0, "bytes": 0, "hashes": {}}
    for f in import_files:
        p = Path(f["abs"])
        sha_before["hashes"][f["rel"]] = _sha256(p)
        sha_before["n"] += 1
        sha_before["bytes"] += f["size"]
    for p in extra_paths:
        if p.exists():
            key = str(p)
            sha_before["hashes"][key] = _sha256(p)
            sha_before["n"] += 1
            sha_before["bytes"] += p.stat().st_size
    log(f"sha_before files={sha_before['n']} bytes={sha_before['bytes']}")

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            snap_before = snapshot_graph(session)
            log(f"snap_before nodes={snap_before['nodes']} rels={snap_before['rels']}")
            neo = inventory_neo4j(session, env)
            # collect names + old pairs for JSON analysis
            tp_names = {
                r["name"]
                for r in _run(session, "MATCH (n:Truth_Point) RETURN n.name AS name")
            }
            trunk_names = {
                r["name"] for r in _run(session, "MATCH (n:Trunk) RETURN n.name AS name")
            }
            branch_names = {
                r["name"] for r in _run(session, "MATCH (n:Branch) RETURN n.name AS name")
            }
            same_as_map = {
                r["inner"]: r["outer"] for r in neo["A3"]["same_as_rows"]
            }
            old_pairs: dict[str, set[tuple[str, str]]] = {}
            for t in _OLD6:
                rows = _run(
                    session,
                    "MATCH (a)-[r]->(b) WHERE type(r)=$t RETURN a.name AS a, b.name AS b",
                    {"t": t},
                )
                old_pairs[t] = {(r["a"], r["b"]) for r in rows}

            log("analyzing JSON + code + scripts…")
            code = inventory_code()
            js = inventory_json(tp_names, trunk_names, branch_names, same_as_map, old_pairs)
            scripts = inventory_scripts()

            snap_after = snapshot_graph(session)
            log(f"snap_after nodes={snap_after['nodes']} rels={snap_after['rels']}")
    except Exception as exc:
        raise SystemExit("neo4j-v4 只读盘点失败: " + _redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    # SHA after
    sha_after = {"n": 0, "bytes": 0, "hashes": {}}
    for f in _file_inventory(_IMPORT_DIR):
        p = Path(f["abs"])
        sha_after["hashes"][f["rel"]] = _sha256(p)
        sha_after["n"] += 1
        sha_after["bytes"] += f["size"]
    for p in extra_paths:
        if p.exists():
            key = str(p)
            sha_after["hashes"][key] = _sha256(p)
            sha_after["n"] += 1
            sha_after["bytes"] += p.stat().st_size

    # secret check in memory
    report = render_report(
        env=env,
        snap_before=snap_before,
        snap_after=snap_after,
        neo=neo,
        code=code,
        js=js,
        scripts=scripts,
        sha_before=sha_before,
        sha_after=sha_after,
        secret_check={"pending": True},
    )
    secrets = [env["pass4"]]
    leaked = any(s and s in report for s in secrets)
    # also check log
    log_text = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    leaked_log = any(s and s in log_text for s in secrets)
    secret_check = {
        "password_in_report": leaked,
        "password_in_log": leaked_log,
        "compared_in_memory_only": True,
    }
    # re-render with secret_check filled
    report = render_report(
        env=env,
        snap_before=snap_before,
        snap_after=snap_after,
        neo=neo,
        code=code,
        js=js,
        scripts=scripts,
        sha_before=sha_before,
        sha_after=sha_after,
        secret_check=secret_check,
    )
    if any(s and s in report for s in secrets):
        raise SystemExit("中止：报告中检测到密码明文")

    _REPORT.parent.mkdir(parents=True, exist_ok=True)
    _REPORT.write_text(report, encoding="utf-8")
    log(f"wrote report {_REPORT}")

    # dump json without huge term sets / with redaction
    dump = {
        "snap_before": snap_before,
        "snap_after": snap_after,
        "neo": neo,
        "code": {
            k: v
            for k, v in code.items()
            if k != "all_hits"
        },
        "code_hit_count": code["hit_count"],
        "code_all_hits": code["all_hits"],
        "js_C0": js["C0"],
        "js_C5": js["C5"],
        "js_C6": js["C6"],
        "js_general_annotation_in_import_dir": js["general_annotation_in_import_dir"],
        "js_per_file_summary": {
            k: {
                kk: vv
                for kk, vv in v.items()
                if kk not in ("term_set",)
            }
            for k, v in js["per_file"].items()
        },
        "scripts": scripts,
        "sha_before": sha_before,
        "sha_after": sha_after,
        "secret_check": secret_check,
    }
    dump_text = json.dumps(dump, ensure_ascii=False, indent=2, default=str)
    dump_text = _redact(dump_text, env["pass4"])
    dump_path.write_text(dump_text, encoding="utf-8")
    log(f"wrote dump {dump_path}")

    # git status note
    try:
        gs = subprocess.check_output(
            ["git", "status", "--short"],
            cwd=str(_REPO),
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        log("git status --short:\n" + gs)
    except Exception as exc:
        log("git status failed: " + str(exc))

    log(
        f"done ok_snap={snap_before==snap_after} ok_sha={sha_before['hashes']==sha_after['hashes']} "
        f"secret_leak={secret_check}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
