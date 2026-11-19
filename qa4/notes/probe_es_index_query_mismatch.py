# -*- coding: utf-8 -*-
"""一次性只读：对比检索查询体与 ES 索引映射，打印真实报错。

用法（在 G:\\copypan 下）:
  $env:QA4_ENV_FILE = \"G:\\copypan\\qa4\\backend\\.env\"
  python qa4/notes/probe_es_index_query_mismatch.py

不写索引、不打印密钥。默认检查 text_cwwl、outline_12490，并以 text_life 作对照。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

_NOTES = Path(__file__).resolve().parent
_QA4 = _NOTES.parent
_BACKEND = _QA4 / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

# 与 restart_qa4.bat 一致：未设时默认本机 backend/.env（不打印内容）
os.environ.setdefault("QA4_ENV_FILE", str(_BACKEND / ".env"))

from config import get_settings, reset_settings_cache  # noqa: E402
from core.es_client import EsClient  # noqa: E402
from retrieval.config import actual_index, index_cfg, retrieval_cfg  # noqa: E402
from retrieval.es_search import build_bm25_body, build_knn_body  # noqa: E402

LOGICALS = ["text_cwwl", "outline_12490", "text_life"]
PROBE_QUERY = "包罗万有的基督"
PROBE_PHRASES = ["包罗万有的基督"]


def _flatten_props(props: dict[str, Any], prefix: str = "") -> dict[str, dict]:
    out: dict[str, dict] = {}
    for k, v in (props or {}).items():
        name = f"{prefix}{k}"
        out[name] = v if isinstance(v, dict) else {"_raw": v}
        if not isinstance(v, dict):
            continue
        for sub, sv in (v.get("fields") or {}).items():
            out[f"{name}.{sub}"] = sv if isinstance(sv, dict) else {"_raw": sv}
        if v.get("properties"):
            out.update(_flatten_props(v["properties"], name + "."))
    return out


def _es_error_bits(exc: BaseException) -> dict[str, Any]:
    status: Optional[int] = None
    meta = getattr(exc, "meta", None)
    if meta is not None:
        st = getattr(meta, "status", None)
        if isinstance(st, int):
            status = st
    if status is None:
        for attr in ("status_code", "status"):
            v = getattr(exc, attr, None)
            if isinstance(v, int):
                status = v
                break
    body = getattr(exc, "body", None)
    err = body.get("error") if isinstance(body, dict) else None
    etype = reason = ""
    root: Any = None
    if isinstance(err, dict):
        etype = str(err.get("type") or "")
        reason = str(err.get("reason") or "")
        root = err.get("root_cause")
        if not reason and isinstance(root, list) and root and isinstance(root[0], dict):
            etype = etype or str(root[0].get("type") or "")
            reason = str(root[0].get("reason") or "")
    elif isinstance(err, str):
        reason = err
    return {
        "exc_type": type(exc).__name__,
        "status": status,
        "error_type": etype or None,
        "error_reason": reason or str(exc)[:400],
        "root_cause": root,
        "body": body if isinstance(body, dict) else (str(body)[:800] if body is not None else None),
    }


def _collect_query_fields(obj: Any, out: set[str]) -> None:
    """从查询体里收集可能引用的字段名（粗提取）。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in {
                "match",
                "match_phrase",
                "term",
                "terms",
                "range",
                "exists",
                "wildcard",
                "prefix",
            }:
                if isinstance(v, dict):
                    out.update(str(f) for f in v.keys())
            if k == "field" and isinstance(v, str):
                out.add(v)
            if k == "knn" and isinstance(v, dict) and isinstance(v.get("field"), str):
                out.add(v["field"])
            _collect_query_fields(v, out)
    elif isinstance(obj, list):
        for x in obj:
            _collect_query_fields(x, out)


def _field_ok_for_query(fname: str, props: dict[str, dict], *, knn: bool = False) -> tuple[bool, str]:
    if fname not in props:
        # 允许 text 类主字段带 .keyword 等；若不存在整段
        return False, "missing"
    meta = props[fname]
    t = meta.get("type")
    if knn:
        if t != "dense_vector":
            return False, f"type={t!r} (want dense_vector)"
        return True, f"dense_vector dims={meta.get('dims')}"
    if t in {None, "object", "nested"} and meta.get("properties"):
        return True, "object"
    return True, f"type={t!r}"


def _probe_one(es: EsClient, logical: str, cfg: dict) -> dict[str, Any]:
    idx = actual_index(logical)
    icfg = index_cfg(logical, cfg)
    row: dict[str, Any] = {
        "logical": logical,
        "index": idx,
        "exists": False,
        "count": None,
        "fields": {},
        "bm25": {},
        "knn": {},
        "field_compare": {},
    }

    row["exists"] = bool(es.index_exists(idx))
    if row["exists"]:
        row["count"] = es.count(idx)

    props: dict[str, dict] = {}
    if row["exists"]:
        try:
            m = es.get_mapping(idx)
            body = m.get(idx) or next(iter(m.values()), {})
            props = _flatten_props(((body.get("mappings") or {}).get("properties")) or {})
            row["fields"] = {
                name: {
                    "type": (meta or {}).get("type"),
                    "dims": (meta or {}).get("dims"),
                    "analyzer": (meta or {}).get("analyzer"),
                    "search_analyzer": (meta or {}).get("search_analyzer"),
                }
                for name, meta in sorted(props.items())
            }
        except Exception as e:
            row["mapping_error"] = _es_error_bits(e)

    # —— BM25：检索代码实际发出的查询体 ——
    bm25_body = build_bm25_body(
        logical,
        PROBE_QUERY,
        size=3,
        phrases=PROBE_PHRASES,
        phrase_boost=2.0,
        cfg=cfg,
    )
    row["bm25"]["body"] = bm25_body
    qfields: set[str] = set()
    _collect_query_fields(bm25_body.get("query"), qfields)
    # _source 也算「查询用到」的配置字段
    for sf in bm25_body.get("_source") or []:
        qfields.add(str(sf))
    row["bm25"]["query_fields"] = sorted(qfields)

    compare = []
    for f in sorted(qfields):
        ok, note = _field_ok_for_query(f, props)
        compare.append({"field": f, "ok": ok, "note": note, "kind": "bm25"})
    row["field_compare"]["bm25"] = compare

    if row["exists"]:
        try:
            resp = es.search(idx, bm25_body)
            hits = ((resp or {}).get("hits") or {}).get("hits") or []
            row["bm25"]["ok"] = True
            row["bm25"]["hits"] = len(hits)
            tot = ((resp or {}).get("hits") or {}).get("total")
            row["bm25"]["total"] = tot.get("value") if isinstance(tot, dict) else tot
        except Exception as e:
            row["bm25"]["ok"] = False
            row["bm25"]["error"] = _es_error_bits(e)
    else:
        row["bm25"]["ok"] = False
        row["bm25"]["error"] = {"error_reason": "index missing"}

    # —— knn：用单位长度向量探测（cosine 不接受零向量；不调用嵌入 API）——
    import math

    dims = 1024
    if props:
        vf = icfg.get("vector_field")
        if vf and vf in props and props[vf].get("dims"):
            dims = int(props[vf]["dims"])
    unit = 1.0 / math.sqrt(dims)
    knn_body = build_knn_body(
        logical,
        [unit] * dims,
        k=3,
        num_candidates=10,
        cfg=cfg,
    )
    row["knn"]["body_meta"] = {
        "has_body": knn_body is not None,
        "vector_field": (icfg.get("vector_field") if knn_body else None),
        "dims_used": dims if knn_body else None,
        # 不打印整段 query_vector
        "size": (knn_body or {}).get("size"),
        "knn_field": ((knn_body or {}).get("knn") or {}).get("field"),
    }
    if knn_body is not None:
        kfields: set[str] = set()
        _collect_query_fields(knn_body, kfields)
        kfields.discard("query_vector")  # 不是字段名
        row["knn"]["query_fields"] = sorted(kfields)
        kcmp = []
        for f in sorted(kfields):
            ok, note = _field_ok_for_query(f, props, knn=(f == icfg.get("vector_field")))
            kcmp.append({"field": f, "ok": ok, "note": note, "kind": "knn"})
        row["field_compare"]["knn"] = kcmp
        if row["exists"]:
            try:
                resp = es.search(idx, knn_body)
                hits = ((resp or {}).get("hits") or {}).get("hits") or []
                row["knn"]["ok"] = True
                row["knn"]["hits"] = len(hits)
            except Exception as e:
                row["knn"]["ok"] = False
                row["knn"]["error"] = _es_error_bits(e)
        else:
            row["knn"]["ok"] = False
            row["knn"]["error"] = {"error_reason": "index missing"}
    else:
        row["knn"]["ok"] = None
        row["knn"]["skip"] = "no vector_field in config"

    bad = [c for group in row["field_compare"].values() for c in group if not c["ok"]]
    row["mismatched_or_missing_fields"] = bad
    return row


def _print_report(rows: list[dict[str, Any]]) -> None:
    for row in rows:
        print("=" * 72)
        print(f"logical={row['logical']}  index={row['index']}")
        print(f"exists={row['exists']}  count={row['count']}")
        if row.get("mapping_error"):
            print("mapping_error:", json.dumps(row["mapping_error"], ensure_ascii=False))
        print(f"fields_n={len(row.get('fields') or {})}")
        for name, meta in (row.get("fields") or {}).items():
            extra = ""
            if meta.get("dims") is not None:
                extra += f" dims={meta['dims']}"
            if meta.get("analyzer"):
                extra += f" analyzer={meta['analyzer']}"
            if meta.get("search_analyzer"):
                extra += f" search_analyzer={meta['search_analyzer']}"
            print(f"  - {name}: type={meta.get('type')}{extra}")

        print("--- BM25 body ---")
        print(json.dumps(row["bm25"].get("body"), ensure_ascii=False, indent=2))
        if row["bm25"].get("ok"):
            print(f"BM25 OK hits={row['bm25'].get('hits')} total={row['bm25'].get('total')}")
        else:
            print("BM25 FAIL:", json.dumps(row["bm25"].get("error"), ensure_ascii=False, indent=2))

        print("--- knn ---")
        print(json.dumps(row["knn"].get("body_meta"), ensure_ascii=False, indent=2))
        if row["knn"].get("ok") is True:
            print(f"knn OK hits={row['knn'].get('hits')}")
        elif row["knn"].get("ok") is False:
            print("knn FAIL:", json.dumps(row["knn"].get("error"), ensure_ascii=False, indent=2))
        else:
            print("knn skipped:", row["knn"].get("skip"))

        bad = row.get("mismatched_or_missing_fields") or []
        print("--- field compare (query vs mapping) ---")
        if not bad:
            print("  (no missing / type-mismatch among query fields)")
        for c in bad:
            print(f"  MISS/BAD [{c['kind']}] {c['field']}: {c['note']}")
        print()


def main() -> int:
    reset_settings_cache()
    settings = get_settings(require_runtime=False)
    if not (settings.es_url or "").strip():
        print("缺少 QA4_ES_URL（检查 QA4_ENV_FILE）")
        return 2
    es = EsClient(
        settings.es_url,
        settings.es_user,
        settings.es_secret,
        verify=settings.es_verify,
        index_map=settings.index_map,
    )
    if not es.ping():
        err = es.last_ping_error or {}
        print(
            "ES ping 失败:",
            err.get("exc_type"),
            "status=",
            err.get("status_code"),
            # 不打印可能含主机细节以外的密钥
            "message=",
            (err.get("message") or "")[:120],
        )
        return 3

    cfg = retrieval_cfg()
    rows = [_probe_one(es, lg, cfg) for lg in LOGICALS]
    _print_report(rows)

    out = _NOTES / "probe_es_index_query_mismatch_out.json"
    # 报告里去掉可能很大的 fields 全表时可保留；此处保留全文便于对照
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
