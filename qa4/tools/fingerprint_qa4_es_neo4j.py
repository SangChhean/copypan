# -*- coding: utf-8 -*-
"""只读指纹：本机/服务器比对 qa4-es 与 qa4-neo4j。

不依赖 qa4 其他模块。ES 用 elasticsearch 包；Neo4j 用 HTTP（默认 127.0.0.1:7476）
或 docker exec cypher-shell，无需安装 neo4j Python 包。

密码只从环境变量读取，不打印、不落盘。

环境变量:
  QA4_NEO4J_HTTP_URL   默认 http://127.0.0.1:7476
  QA4_NEO4J_USER       默认 neo4j
  QA4_NEO4J_PASSWORD   必填（neo4j 段）
  QA4_NEO4J_DATABASE   默认 neo4j
  QA4_NEO4J_VIA        http | cypher-shell（默认 http）
  QA4_NEO4J_CONTAINER  cypher-shell 时容器名，默认 qa4-neo4j
  QA4_ES_URL           必填（es 段），如 http://127.0.0.1:9202
  QA4_ES_USER          默认 elastic（有密码时用于 basic_auth）
  QA4_ES_PASSWORD      ES 开认证时必填；无密码则先尝试匿名
  QA4_ES_VERIFY        默认 1
  QA4_ENV_FILE         可选，注入未设置的 KEY=VALUE（不覆盖已有环境变量）

用法:
  python3 fingerprint_qa4_es_neo4j.py
  python3 fingerprint_qa4_es_neo4j.py --out /tmp/fp.json
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, List, Optional

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
VECTOR_FIELDS = ("embedding", "text_vector")
SAMPLE_N = 200
# 抽样规则版本：全量 _id 排序后等距取样（与物理/_doc 顺序无关）
SAMPLE_RULE = "sorted_id_stride_v2"


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


def _sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _norm_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


# ---------------- Neo4j via HTTP ----------------


def _neo4j_http_auth_header(user: str, password: str) -> str:
    token = base64.b64encode(("%s:%s" % (user, password)).encode("utf-8")).decode("ascii")
    return "Basic %s" % token


def _neo4j_http_run(statements: List[str]) -> List[Any]:
    """Run Cypher list via Neo4j HTTP transactional endpoint. Returns list of row lists."""
    base = (os.environ.get("QA4_NEO4J_HTTP_URL") or "http://127.0.0.1:7476").rstrip("/")
    user = (os.environ.get("QA4_NEO4J_USER") or "neo4j").strip()
    password = os.environ.get("QA4_NEO4J_PASSWORD") or ""
    db = (os.environ.get("QA4_NEO4J_DATABASE") or "neo4j").strip()
    if not password:
        raise RuntimeError(
            "缺少 Neo4j 密码：请 export QA4_NEO4J_PASSWORD=... "
            "（用户名 QA4_NEO4J_USER，默认 neo4j）"
        )
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
            "Authorization": _neo4j_http_auth_header(user, password),
        },
    )
    password = ""
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        if e.code in (401, 403):
            raise RuntimeError(
                "Neo4j 认证失败 HTTP %s：请检查 QA4_NEO4J_PASSWORD，"
                "以及 QA4_NEO4J_USER（默认 neo4j）。" % e.code
            ) from e
        raise RuntimeError("Neo4j HTTP %s: %s" % (e.code, detail)) from e
    errs = payload.get("errors") or []
    if errs:
        raise RuntimeError("Neo4j Cypher error: %s" % (errs[0].get("message") or errs[0]))
    results = []
    for block in payload.get("results") or []:
        cols = block.get("columns") or []
        rows = []
        for row in block.get("data") or []:
            vals = row.get("row") or []
            rows.append({cols[i]: vals[i] for i in range(len(cols))})
        results.append(rows)
    return results


def _neo4j_cypher_shell_run(statements: List[str]) -> List[Any]:
    """Run via: docker exec -i qa4-neo4j cypher-shell -u … -p … --format plain"""
    container = (os.environ.get("QA4_NEO4J_CONTAINER") or "qa4-neo4j").strip()
    user = (os.environ.get("QA4_NEO4J_USER") or "neo4j").strip()
    password = os.environ.get("QA4_NEO4J_PASSWORD") or ""
    db = (os.environ.get("QA4_NEO4J_DATABASE") or "neo4j").strip()
    if not password:
        raise RuntimeError(
            "缺少 Neo4j 密码：请 export QA4_NEO4J_PASSWORD=... "
            "（用户名 QA4_NEO4J_USER，默认 neo4j）"
        )
    # Wrap each statement to RETURN JSON string for stable parse
    wrapped = []
    for i, s in enumerate(statements):
        wrapped.append(
            "CALL { %s } YIELD * WITH collect(*) AS rows "
            "RETURN %d AS stmt_i, apoc.convert.toJson(rows) AS j" % (s.rstrip(";"), i)
        )
    # Without APOC: run one-by-one with --format json if available; fallback plain counts.
    # Prefer one HTTP-style: use cypher-shell --format json (Neo4j 5).
    out_blocks: List[Any] = []
    for s in statements:
        cmd = [
            "docker",
            "exec",
            "-i",
            container,
            "cypher-shell",
            "-u",
            user,
            "-p",
            password,
            "-d",
            db,
            "--format",
            "json",
            s if s.rstrip().endswith(";") else (s.rstrip() + ";"),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            password = ""
            err = (proc.stderr or proc.stdout or "")[:300]
            raise RuntimeError("cypher-shell failed: %s" % err)
        # json format: one JSON object per line / or array
        text = (proc.stdout or "").strip()
        rows = []
        if text:
            # Neo4j 5 cypher-shell --format json prints NDJSON records
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                if isinstance(obj, dict):
                    rows.append(obj)
                elif isinstance(obj, list):
                    for item in obj:
                        if isinstance(item, dict):
                            rows.append(item)
        out_blocks.append(rows)
    password = ""
    return out_blocks


def _neo4j_run(statements: List[str]) -> List[Any]:
    via = (os.environ.get("QA4_NEO4J_VIA") or "http").strip().lower()
    if via in {"cypher-shell", "shell", "docker"}:
        return _neo4j_cypher_shell_run(statements)
    return _neo4j_http_run(statements)


def _scalar(rows: List[dict], key: str) -> Any:
    if not rows:
        return None
    return rows[0].get(key)


def fingerprint_neo4j() -> dict[str, Any]:
    http = (os.environ.get("QA4_NEO4J_HTTP_URL") or "http://127.0.0.1:7476").rstrip("/")
    via = (os.environ.get("QA4_NEO4J_VIA") or "http").strip().lower()
    out: dict[str, Any] = {
        "via": via,
        "http_url_host": http.split("://", 1)[-1],
        "node_total": 0,
        "rel_total": 0,
        "labels": {},
        "rel_types": {},
        "prop_nonempty": {},
        "scripture_nodes": 0,
        "mutuality_on_bracket_inner": 0,
        "bracket_inner_nodes": 0,
        "constraints": [],
        "indexes": [],
    }
    stmts = [
        "MATCH (n) RETURN count(n) AS c",
        "MATCH ()-[r]->() RETURN count(r) AS c",
        "MATCH (n) UNWIND labels(n) AS lb RETURN lb AS label, count(*) AS c ORDER BY label",
        "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c ORDER BY t",
        "MATCH (n:Scripture) RETURN count(n) AS c",
        "MATCH (n:Truth_Point) WHERE n.same_as IS NOT NULL AND toString(n.same_as) <> '' "
        "RETURN count(n) AS total, "
        "sum(CASE WHEN n.mutuality IS NOT NULL AND toString(n.mutuality) <> '' THEN 1 ELSE 0 END) AS with_m",
    ]
    for prop in ANNOTATION_PROPS:
        if not prop.replace("_", "").isalnum():
            continue
        stmts.append(
            "MATCH (n) WHERE n.`%s` IS NOT NULL AND toString(n.`%s`) <> '' RETURN count(n) AS c"
            % (prop, prop)
        )
    stmts.append(
        "SHOW CONSTRAINTS YIELD name, type, entityType, labelsOrTypes, properties "
        "RETURN name, type, entityType, labelsOrTypes, properties ORDER BY name"
    )
    stmts.append(
        "SHOW INDEXES YIELD name, type, entityType, labelsOrTypes, properties, state "
        "RETURN name, type, entityType, labelsOrTypes, properties, state ORDER BY name"
    )
    blocks = _neo4j_run(stmts)
    out["node_total"] = int(_scalar(blocks[0], "c") or 0)
    out["rel_total"] = int(_scalar(blocks[1], "c") or 0)
    for rec in blocks[2]:
        out["labels"][str(rec["label"])] = int(rec["c"])
    for rec in blocks[3]:
        out["rel_types"][str(rec["t"])] = int(rec["c"])
    out["scripture_nodes"] = int(_scalar(blocks[4], "c") or 0)
    br = blocks[5][0] if blocks[5] else {}
    out["bracket_inner_nodes"] = int(br.get("total") or 0)
    out["mutuality_on_bracket_inner"] = int(br.get("with_m") or 0)
    prop_offset = 6
    for i, prop in enumerate(ANNOTATION_PROPS):
        out["prop_nonempty"][prop] = int(_scalar(blocks[prop_offset + i], "c") or 0)
    cons_i = prop_offset + len(ANNOTATION_PROPS)
    idx_i = cons_i + 1
    for rec in blocks[cons_i]:
        out["constraints"].append(
            {
                "name": rec.get("name"),
                "type": rec.get("type"),
                "entityType": rec.get("entityType"),
                "labelsOrTypes": list(rec.get("labelsOrTypes") or []),
                "properties": list(rec.get("properties") or []),
            }
        )
    for rec in blocks[idx_i]:
        out["indexes"].append(
            {
                "name": rec.get("name"),
                "type": rec.get("type"),
                "entityType": rec.get("entityType"),
                "labelsOrTypes": list(rec.get("labelsOrTypes") or []),
                "properties": list(rec.get("properties") or []),
                "state": rec.get("state"),
            }
        )
    return out


# ---------------- Elasticsearch ----------------


def _es_auth_hint() -> str:
    return (
        "请 export QA4_ES_PASSWORD=... ；"
        "用户名 QA4_ES_USER（默认 elastic）。"
        "例: export QA4_ES_USER=elastic"
    )


def _es_client():
    url = (os.environ.get("QA4_ES_URL") or "").strip().rstrip("/")
    if not url:
        raise RuntimeError("缺少 QA4_ES_URL，例: export QA4_ES_URL=http://127.0.0.1:9202")
    # 默认用户名 elastic（ES 8 内置）；无密码时先尝试匿名连接
    user = (os.environ.get("QA4_ES_USER") or "elastic").strip()
    password = os.environ.get("QA4_ES_PASSWORD") or ""
    verify_raw = (os.environ.get("QA4_ES_VERIFY") or "1").strip().lower()
    verify = verify_raw not in {"0", "false", "no"}
    from elasticsearch import Elasticsearch
    from elasticsearch.exceptions import AuthenticationException, AuthorizationException

    kwargs: dict[str, Any] = {"hosts": [url], "verify_certs": verify}
    if password:
        kwargs["basic_auth"] = (user, password)
    password = ""
    es = Elasticsearch(**kwargs)
    try:
        es.info()
    except (AuthenticationException, AuthorizationException) as e:
        raise RuntimeError("ES 认证失败（401/403）：%s" % _es_auth_hint()) from e
    except Exception as e:
        msg = str(e)
        if "401" in msg or "Unauthorized" in msg or "security_exception" in msg.lower():
            raise RuntimeError("ES 认证失败：%s" % _es_auth_hint()) from e
        raise
    return es, url


def _strip_source_for_hash(doc: dict[str, Any]) -> dict[str, Any]:
    """去掉向量字段与顶层 null 键（内容哈希用）。"""
    return {
        k: v
        for k, v in doc.items()
        if k not in VECTOR_FIELDS and v is not None
    }


def _scroll_all_ids(es, index: str) -> List[str]:
    """scroll 取全部 _id（仅 id，无 _source）。"""
    ids: List[str] = []
    scroll = "2m"
    page_size = 2000
    resp = es.search(
        index=index,
        scroll=scroll,
        size=page_size,
        _source=False,
        query={"match_all": {}},
    )
    sid = resp.get("_scroll_id")
    try:
        while True:
            hits = (resp.get("hits") or {}).get("hits") or []
            if not hits:
                break
            ids.extend(h["_id"] for h in hits)
            if not sid:
                break
            resp = es.scroll(scroll_id=sid, scroll=scroll)
            sid = resp.get("_scroll_id")
    finally:
        if sid:
            try:
                es.clear_scroll(scroll_id=sid)
            except Exception:
                pass
    return ids


def _stride_sample_ids(sorted_ids: List[str], n: int = SAMPLE_N) -> List[str]:
    """排序后的 id：k = len // n，取 sorted_ids[0], [k], [2k], … 共 n 个。"""
    total = len(sorted_ids)
    if total == 0:
        return []
    if total <= n:
        return list(sorted_ids)
    k = total // n
    if k < 1:
        k = 1
    return [sorted_ids[i * k] for i in range(n)]


def fingerprint_es() -> dict[str, Any]:
    es, url = _es_client()
    out: dict[str, Any] = {
        "url_host": url.split("://", 1)[-1],
        "sample_rule": SAMPLE_RULE,
        "sample_n_target": SAMPLE_N,
        "indices": {},
    }
    try:
        names = sorted(
            n for n in es.indices.get_alias(index="qa4_*").keys() if n.startswith("qa4_")
        )
    except Exception:
        cat = es.cat.indices(index="qa4_*", format="json")
        names = sorted(r["index"] for r in cat if str(r.get("index", "")).startswith("qa4_"))

    for name in names:
        mapping = es.indices.get_mapping(index=name)
        map_body = mapping.get(name, {}).get("mappings", {})
        map_hash = _sha256_text(_norm_json(map_body))
        count = int(es.count(index=name)["count"])
        all_ids = _scroll_all_ids(es, name) if count > 0 else []
        all_ids.sort()
        sample_ids = _stride_sample_ids(all_ids, SAMPLE_N)
        sample_ids_sha = _sha256_text(_norm_json(sample_ids)) if sample_ids else ""
        sample_docs = []
        if sample_ids:
            # mget 分批，避免单次过大
            batch = 200
            found: dict[str, dict] = {}
            for i in range(0, len(sample_ids), batch):
                chunk = sample_ids[i : i + batch]
                mget = es.mget(index=name, ids=chunk, source=True)
                for doc in mget.get("docs", []):
                    if not doc.get("found"):
                        continue
                    found[doc["_id"]] = _strip_source_for_hash(doc.get("_source") or {})
            # 按 sample_ids 顺序写入，保证内容哈希与抽样顺序一致
            for _id in sample_ids:
                if _id in found:
                    sample_docs.append({"_id": _id, "_source": found[_id]})
        content_hash = _sha256_text(_norm_json(sample_docs)) if sample_docs else ""
        out["indices"][name] = {
            "doc_count": count,
            "mapping_sha256": map_hash,
            "sample_n": len(sample_docs),
            "sample_pool": len(all_ids),
            "sample_stride_k": (len(all_ids) // SAMPLE_N) if len(all_ids) > SAMPLE_N else 1,
            "sample_ids_sha256": sample_ids_sha,
            "sample_content_sha256": content_hash,
        }
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Read-only fingerprint for qa4-es + qa4-neo4j")
    ap.add_argument("--out", help="optional JSON output path (no secrets)")
    ap.add_argument("--skip-es", action="store_true")
    ap.add_argument("--skip-neo4j", action="store_true")
    args = ap.parse_args()

    env_file = (os.environ.get("QA4_ENV_FILE") or "").strip()
    if env_file:
        _load_env_file(Path(env_file))

    report: dict[str, Any] = {
        "schema": "qa4_es_neo4j_fingerprint_v2",
        "generated_at_unix": int(time.time()),
        "host_hint": os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "",
        "sample_n": SAMPLE_N,
        "sample_rule": SAMPLE_RULE,
        "neo4j": None,
        "es": None,
        "errors": [],
    }
    ok = True
    if not args.skip_neo4j:
        try:
            report["neo4j"] = fingerprint_neo4j()
        except Exception as e:
            ok = False
            report["errors"].append({"neo4j": type(e).__name__, "msg": str(e)[:300]})
    if not args.skip_es:
        try:
            report["es"] = fingerprint_es()
        except Exception as e:
            ok = False
            report["errors"].append({"es": type(e).__name__, "msg": str(e)[:300]})

    text = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).write_text(text + "\n", encoding="utf-8")
    sys.stdout.write(text + "\n")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
