# -*- coding: utf-8 -*-
"""从 qa4-neo4j 移除 Truth_Point/节点上的 mutuality 属性（REMOVE）。

不依赖 qa4 / neo4j Python 包；默认 Neo4j HTTP（127.0.0.1:7476）。
密码只从环境变量读取，不打印。

前置核对（不符则停止）:
  - mutuality 非空 == 116
  - 括号内（same_as 非空）带 mutuality == 0
后置核对:
  - mutuality 非空 == 0
  - 节点 7331、关系 52426、Scripture 4848 不变（可用参数覆盖）
  - 其他标注属性非空数与删前一致

环境变量: QA4_NEO4J_HTTP_URL / QA4_NEO4J_USER / QA4_NEO4J_PASSWORD / QA4_NEO4J_DATABASE / QA4_ENV_FILE

用法:
  python graph_remove_mutuality.py           # 只核对
  python graph_remove_mutuality.py --yes     # 执行 REMOVE
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, List

ANNOTATION_PROPS = (
    "name",
    "name_en",
    "definition_3a",
    "definition_3b",
    "intrinsic_significance",
    "greek_terms",
    "hebrew_terms",
    "high_peak_content",
    "mutuality",
    "organic_advance",
    "same_as",
    "devine_argument",
)

EXPECT_MUTUALITY = 116
EXPECT_BRACKET_MUTUALITY = 0
DEFAULT_NODES = 7331
DEFAULT_RELS = 52426
DEFAULT_SCRIPTURE = 4848


def _load_env_file(path: Path) -> None:
    if not path.is_file():
        raise SystemExit("QA4_ENV_FILE not found: %s" % path)
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        if not k or k in os.environ:
            continue
        v = v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        os.environ[k] = v


def _http_run(statements: List[str]) -> List[List[dict]]:
    base = (os.environ.get("QA4_NEO4J_HTTP_URL") or "http://127.0.0.1:7476").rstrip("/")
    user = (os.environ.get("QA4_NEO4J_USER") or "neo4j").strip()
    password = os.environ.get("QA4_NEO4J_PASSWORD") or ""
    db = (os.environ.get("QA4_NEO4J_DATABASE") or "neo4j").strip()
    if not password:
        raise SystemExit("QA4_NEO4J_PASSWORD missing")
    url = "%s/db/%s/tx/commit" % (base, db)
    body = {"statements": [{"statement": s} for s in statements]}
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": "Basic "
            + base64.b64encode(("%s:%s" % (user, password)).encode("utf-8")).decode("ascii"),
        },
    )
    password = ""
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:400]
        raise SystemExit("Neo4j HTTP %s: %s" % (e.code, detail))
    errs = payload.get("errors") or []
    if errs:
        raise SystemExit("Neo4j Cypher error: %s" % (errs[0].get("message") or errs[0]))
    results: List[List[dict]] = []
    for block in payload.get("results") or []:
        cols = block.get("columns") or []
        rows = []
        for row in block.get("data") or []:
            vals = row.get("row") or []
            rows.append({cols[i]: vals[i] for i in range(len(cols))})
        results.append(rows)
    return results


def _snapshot() -> Dict[str, Any]:
    stmts = [
        "MATCH (n) RETURN count(n) AS c",
        "MATCH ()-[r]->() RETURN count(r) AS c",
        "MATCH (n:Scripture) RETURN count(n) AS c",
        "MATCH (n) WHERE n.mutuality IS NOT NULL AND toString(n.mutuality) <> '' RETURN count(n) AS c",
        "MATCH (n:Truth_Point) WHERE n.same_as IS NOT NULL AND toString(n.same_as) <> '' "
        "RETURN count(n) AS total, "
        "sum(CASE WHEN n.mutuality IS NOT NULL AND toString(n.mutuality) <> '' THEN 1 ELSE 0 END) AS with_m",
    ]
    for prop in ANNOTATION_PROPS:
        if prop == "mutuality":
            continue
        stmts.append(
            "MATCH (n) WHERE n.`%s` IS NOT NULL AND toString(n.`%s`) <> '' RETURN count(n) AS c"
            % (prop, prop)
        )
    blocks = _http_run(stmts)
    props = {}
    other_props = [p for p in ANNOTATION_PROPS if p != "mutuality"]
    for i, prop in enumerate(other_props):
        props[prop] = int((blocks[5 + i][0] or {}).get("c") or 0)
    br = blocks[4][0] if blocks[4] else {}
    return {
        "node_total": int((blocks[0][0] or {}).get("c") or 0),
        "rel_total": int((blocks[1][0] or {}).get("c") or 0),
        "scripture_nodes": int((blocks[2][0] or {}).get("c") or 0),
        "mutuality_nonempty": int((blocks[3][0] or {}).get("c") or 0),
        "bracket_inner_nodes": int(br.get("total") or 0),
        "mutuality_on_bracket_inner": int(br.get("with_m") or 0),
        "prop_nonempty_other": props,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="REMOVE n.mutuality on qa4-neo4j")
    ap.add_argument("--yes", action="store_true", help="actually REMOVE")
    ap.add_argument("--expect-nodes", type=int, default=DEFAULT_NODES)
    ap.add_argument("--expect-rels", type=int, default=DEFAULT_RELS)
    ap.add_argument("--expect-scripture", type=int, default=DEFAULT_SCRIPTURE)
    ap.add_argument("--expect-mutuality", type=int, default=EXPECT_MUTUALITY)
    args = ap.parse_args()

    env_file = (os.environ.get("QA4_ENV_FILE") or "").strip()
    if env_file:
        _load_env_file(Path(env_file))

    before = _snapshot()
    print("before=%s" % json.dumps(before, ensure_ascii=False, sort_keys=True))
    if before["mutuality_nonempty"] != args.expect_mutuality:
        print(
            "REFUSE: mutuality nonempty %d != %d"
            % (before["mutuality_nonempty"], args.expect_mutuality),
            file=sys.stderr,
        )
        return 2
    if before["mutuality_on_bracket_inner"] != EXPECT_BRACKET_MUTUALITY:
        print(
            "REFUSE: bracket mutuality %d != %d"
            % (before["mutuality_on_bracket_inner"], EXPECT_BRACKET_MUTUALITY),
            file=sys.stderr,
        )
        return 2
    if before["node_total"] != args.expect_nodes:
        print(
            "REFUSE: nodes %d != %d" % (before["node_total"], args.expect_nodes),
            file=sys.stderr,
        )
        return 2
    if before["rel_total"] != args.expect_rels:
        print(
            "REFUSE: rels %d != %d" % (before["rel_total"], args.expect_rels),
            file=sys.stderr,
        )
        return 2
    if before["scripture_nodes"] != args.expect_scripture:
        print(
            "REFUSE: scripture %d != %d" % (before["scripture_nodes"], args.expect_scripture),
            file=sys.stderr,
        )
        return 2

    if not args.yes:
        print("DRY_RUN: pass --yes to REMOVE mutuality. No changes made.")
        return 0

    print("REMOVING mutuality ...")
    _http_run(
        [
            "MATCH (n) WHERE n.mutuality IS NOT NULL REMOVE n.mutuality RETURN count(n) AS removed"
        ]
    )
    after = _snapshot()
    print("after=%s" % json.dumps(after, ensure_ascii=False, sort_keys=True))
    ok = True
    if after["mutuality_nonempty"] != 0:
        print("FAIL: mutuality still nonempty=%d" % after["mutuality_nonempty"], file=sys.stderr)
        ok = False
    if after["node_total"] != before["node_total"]:
        print("FAIL: node_total changed", file=sys.stderr)
        ok = False
    if after["rel_total"] != before["rel_total"]:
        print("FAIL: rel_total changed", file=sys.stderr)
        ok = False
    if after["scripture_nodes"] != before["scripture_nodes"]:
        print("FAIL: scripture changed", file=sys.stderr)
        ok = False
    for k, v in before["prop_nonempty_other"].items():
        if after["prop_nonempty_other"].get(k) != v:
            print(
                "FAIL: prop %s changed %s -> %s"
                % (k, v, after["prop_nonempty_other"].get(k)),
                file=sys.stderr,
            )
            ok = False
    if not ok:
        return 1
    print("OK: mutuality removed; nodes/rels/scripture/other props unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
