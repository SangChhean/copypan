# -*- coding: utf-8 -*-
"""只读导出：每个 Scripture 的 ref + 指向它的 SUPPORTED_BY 入边数量。

输出格式与 cypher-shell --format plain 一致，便于与服务器导出做差异比对：
  第一行表头：ref, n
  之后每行："ref", n

用法（本机）:
  set QA4_ENV_FILE=...
  set QA4_NEO4J_HTTP_URL=http://127.0.0.1:7476
  python export_scripture_supported_by.py --out scripture_local.txt

服务器可用 cypher-shell（见脚本末尾注释），不必跑本脚本。
密码：QA4_NEO4J_PASSWORD；用户默认 neo4j。不打印密码。
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


CYPHER = (
    "MATCH (s:Scripture) "
    "OPTIONAL MATCH (t:Truth_Point)-[:SUPPORTED_BY]->(s) "
    "RETURN s.ref AS ref, count(t) AS n "
    "ORDER BY ref"
)

# 服务器手跑（plain 输出应与本脚本一致）:
# docker exec -i qa4-neo4j cypher-shell -u neo4j -p "$QA4_NEO4J_PASSWORD" -d neo4j --format plain \
#   "MATCH (s:Scripture) OPTIONAL MATCH (t:Truth_Point)-[:SUPPORTED_BY]->(s) RETURN s.ref AS ref, count(t) AS n ORDER BY ref;"


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


def _http_run(statement: str) -> list[dict]:
    base = (os.environ.get("QA4_NEO4J_HTTP_URL") or "http://127.0.0.1:7476").rstrip("/")
    user = (os.environ.get("QA4_NEO4J_USER") or "neo4j").strip()
    password = os.environ.get("QA4_NEO4J_PASSWORD") or ""
    db = (os.environ.get("QA4_NEO4J_DATABASE") or "neo4j").strip()
    if not password:
        raise SystemExit(
            "缺少 Neo4j 密码：请 export QA4_NEO4J_PASSWORD=... （用户 QA4_NEO4J_USER 默认 neo4j）"
        )
    url = "%s/db/%s/tx/commit" % (base, db)
    body = {"statements": [{"statement": statement}]}
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
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
        if e.code in (401, 403):
            raise SystemExit(
                "Neo4j 认证失败 HTTP %s：检查 QA4_NEO4J_PASSWORD / QA4_NEO4J_USER（默认 neo4j）"
                % e.code
            )
        raise SystemExit("Neo4j HTTP %s" % e.code)
    errs = payload.get("errors") or []
    if errs:
        raise SystemExit("Neo4j Cypher error: %s" % (errs[0].get("message") or errs[0]))
    block = (payload.get("results") or [{}])[0]
    cols = block.get("columns") or []
    rows = []
    for row in block.get("data") or []:
        vals = row.get("row") or []
        rows.append({cols[i]: vals[i] for i in range(len(cols))})
    return rows


def _escape_plain_ref(ref: str) -> str:
    # cypher-shell plain 对字符串加双引号，内部 " 以 \" 表示（极少见）
    return '"' + str(ref).replace("\\", "\\\\").replace('"', '\\"') + '"'


def main() -> int:
    ap = argparse.ArgumentParser(description="Export Scripture ref + SUPPORTED_BY count")
    ap.add_argument("--out", required=True, help="output .txt path")
    args = ap.parse_args()

    env_file = (os.environ.get("QA4_ENV_FILE") or "").strip()
    if env_file:
        _load_env_file(Path(env_file))

    rows = _http_run(CYPHER)
    lines = ["ref, n"]
    for r in rows:
        ref = r.get("ref")
        n = int(r.get("n") or 0)
        if ref is None:
            continue
        lines.append("%s, %d" % (_escape_plain_ref(ref), n))
    text = "\n".join(lines) + "\n"
    Path(args.out).write_text(text, encoding="utf-8")
    print("wrote %s rows=%d" % (args.out, len(rows)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
