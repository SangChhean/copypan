# -*- coding: utf-8 -*-
"""只读服务探针（供 Srey 本机运行）。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Optional

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from config import get_settings, reset_settings_cache  # noqa: E402
from core.ready import redact_secrets  # noqa: E402

EXPECT_VECTOR_DIMS = 1024


def _safe_str(exc: BaseException) -> str:
    return redact_secrets(str(exc) or type(exc).__name__)


def merge_status(*parts: str) -> str:
    """ok < degraded < not_ready。"""
    order = {"ok": 0, "degraded": 1, "not_ready": 2}
    worst = "ok"
    for p in parts:
        if order.get(p, 0) > order.get(worst, 0):
            worst = p
    return worst


def evaluate_neo4j(
    counts: dict[str, Optional[int]],
    expected: dict[str, int],
    *,
    ping_ok: bool = True,
    ping_error: Optional[str] = None,
) -> dict[str, Any]:
    """按标签给出 status（ok / degraded）与 actual/expected。"""
    if not ping_ok:
        return {
            "status": "not_ready",
            "ping": False,
            "message": redact_secrets(ping_error or "Neo4j ping failed"),
            "labels": {},
        }
    labels: dict[str, Any] = {}
    overall = "ok"
    for lb, exp in expected.items():
        actual = counts.get(lb)
        if actual is None:
            st = "not_ready"
            overall = merge_status(overall, st)
            labels[lb] = {
                "status": st,
                "actual": None,
                "expected": int(exp),
                "message": f"无法读取标签 {lb} 计数",
            }
            continue
        if int(actual) != int(exp):
            st = "degraded"
            overall = merge_status(overall, st)
            labels[lb] = {
                "status": st,
                "actual": int(actual),
                "expected": int(exp),
                "message": f"实际={actual} 预期={exp}",
            }
        else:
            labels[lb] = {
                "status": "ok",
                "actual": int(actual),
                "expected": int(exp),
            }
    return {"status": overall, "ping": True, "labels": labels}


def _vector_info_from_properties(
    properties: dict[str, Any], field: str
) -> dict[str, Any]:
    """从 mapping.properties 取向量字段 type / dims。"""
    cur: Any = properties or {}
    for part in field.split("."):
        if not isinstance(cur, dict):
            return {"exists": False}
        if part in cur:
            cur = cur[part]
        elif isinstance(cur.get("properties"), dict) and part in cur["properties"]:
            cur = cur["properties"][part]
        else:
            return {"exists": False}
    if not isinstance(cur, dict):
        return {"exists": False}
    return {
        "exists": True,
        "type": cur.get("type"),
        "dims": cur.get("dims"),
    }


def extract_index_properties(mapping_body: Any, index_name: str) -> dict[str, Any]:
    """兼容 get_mapping / 测试夹具多种形态 → properties 字典。"""
    if not isinstance(mapping_body, dict):
        return {}
    # 直接 properties
    if isinstance(mapping_body.get("properties"), dict) and all(
        isinstance(v, dict) for v in mapping_body["properties"].values()
    ):
        # 且没有外层 index 键包一层
        if "mappings" not in mapping_body and index_name not in mapping_body:
            return mapping_body["properties"]
    # {index: {mappings: {properties}}}
    block = mapping_body.get(index_name)
    if block is None and len(mapping_body) == 1:
        block = next(iter(mapping_body.values()))
    if isinstance(block, dict):
        mappings = block.get("mappings") or block
        if isinstance(mappings, dict):
            props = mappings.get("properties")
            if isinstance(props, dict):
                return props
            # block 本身就是 properties（字段名 → {type:...}）
            if any(isinstance(v, dict) and "type" in v for v in mappings.values()):
                return mappings
    # mapping_body 本身就是 properties
    if any(isinstance(v, dict) and "type" in v for v in mapping_body.values()):
        return mapping_body
    return {}


def evaluate_es(
    *,
    index_map: dict[str, dict],
    expected: dict[str, int],
    stats: dict[str, dict],
    mappings: dict[str, Any],
    ping_ok: bool = True,
    ping_error: Optional[str] = None,
) -> dict[str, Any]:
    """文档数 + mapping 向量字段核对。

    - 有 vector_field：须存在、type=dense_vector、dims=1024；否则 not_ready
    - vector_field 为空时：不要求向量字段（历史 pano_catalog；现配置已无该项）
    - 仅文档数不符：degraded
    - 索引缺失：not_ready
    """
    if not ping_ok:
        return {
            "status": "not_ready",
            "ping": False,
            "message": redact_secrets(ping_error or "ES ping failed"),
            "indices": {},
        }

    indices: dict[str, Any] = {}
    overall = "ok"
    for logical, exp in expected.items():
        meta = index_map.get(logical) or {}
        index_name = meta.get("index") or f"qa4_{logical}"
        vec_field = meta.get("vector_field")
        st_row = stats.get(logical) or {}
        exists = bool(st_row.get("exists", False))
        count = st_row.get("count")
        row: dict[str, Any] = {
            "index": index_name,
            "vector_field": vec_field,
            "exists": exists,
            "count": count,
            "expected": int(exp),
        }
        status = "ok"
        messages: list[str] = []

        if not exists:
            status = "not_ready"
            messages.append(f"索引不存在：{index_name}")
        else:
            if count is None:
                status = merge_status(status, "not_ready")
                messages.append(f"无法读取文档数：{index_name}")
            elif int(count) != int(exp):
                status = merge_status(status, "degraded")
                messages.append(f"文档数实际={count} 预期={exp}")

            if vec_field:
                raw_map = mappings.get(index_name) or mappings.get(logical) or {}
                props = extract_index_properties(raw_map, index_name)
                info = _vector_info_from_properties(props, vec_field)
                row["vector"] = info
                if not info.get("exists"):
                    status = merge_status(status, "not_ready")
                    messages.append(
                        f"向量字段缺失：index={index_name} field={vec_field}"
                    )
                else:
                    typ = info.get("type")
                    dims = info.get("dims")
                    if typ != "dense_vector":
                        status = merge_status(status, "not_ready")
                        messages.append(
                            f"向量类型不符：index={index_name} field={vec_field} "
                            f"actual_type={typ} expected=dense_vector"
                        )
                    if dims != EXPECT_VECTOR_DIMS:
                        status = merge_status(status, "not_ready")
                        messages.append(
                            f"向量维度不符：index={index_name} field={vec_field} "
                            f"actual_dims={dims} expected={EXPECT_VECTOR_DIMS}"
                        )

        row["status"] = status
        if messages:
            row["message"] = "; ".join(messages)
        indices[logical] = row
        overall = merge_status(overall, status)

    return {"status": overall, "ping": True, "indices": indices}


def fetch_es_mappings(es: Any, index_names: list[str]) -> dict[str, Any]:
    """读取各索引 mapping；失败项记 error（脱敏）。"""
    out: dict[str, Any] = {}
    client = getattr(es, "_client", None)
    for name in index_names:
        if client is None:
            out[name] = {"_error": "NoClient"}
            continue
        try:
            raw = client.indices.get_mapping(index=name)
            # elasticsearch 客户端可能返回 ObjectApiResponse
            if hasattr(raw, "body"):
                raw = raw.body
            out[name] = dict(raw) if isinstance(raw, dict) else {"_raw": str(type(raw))}
        except Exception as e:
            out[name] = {"_error": _safe_str(e)}
    return out


def summarize_report(
    *,
    redis: dict[str, Any],
    elasticsearch: dict[str, Any],
    neo4j: dict[str, Any],
) -> dict[str, Any]:
    status = merge_status(
        redis.get("status") or "not_ready",
        elasticsearch.get("status") or "not_ready",
        neo4j.get("status") or "not_ready",
    )
    return {
        "status": status,
        "redis": redis,
        "elasticsearch": elasticsearch,
        "neo4j": neo4j,
    }


def exit_code_for_status(status: str) -> int:
    return 1 if status == "not_ready" else 0


def _print_targets(settings, expected, index_map) -> None:
    rows = []
    rows.append(("Redis URL", settings.redis_url or "(empty→MemoryStore)"))
    rows.append(("ES URL", settings.es_url or "(empty)"))
    rows.append(("Neo4j URI", settings.neo4j_uri or "(empty)"))
    for logical, meta in index_map.items():
        rows.append(
            (
                f"ES {logical}",
                f"{meta.get('index')} vec={meta.get('vector_field')} "
                f"expect={expected.get('es', {}).get(logical)}",
            )
        )
    for lb, n in (expected.get("neo4j") or {}).items():
        rows.append((f"Neo4j {lb}", f"expect={n}"))

    print("=== check_services targets ===")
    for k, v in rows:
        print(f"{k:24} {v}")


def run_live_checks(settings) -> dict[str, Any]:
    from core.es_client import EsClient
    from core.neo4j_client import Neo4jClient
    from core.redis_store import create_store

    expected = settings.expected_counts
    index_map = settings.index_map.get("indices") or {}

    # Redis
    try:
        store = create_store(settings.redis_url, settings.redis_prefix)
        r_ok = bool(store.ping())
        redis_rep: dict[str, Any] = {
            "status": "ok" if r_ok else "not_ready",
            "ping": r_ok,
        }
        if r_ok:
            store.set("selftest:ping", "1", ttl=30)
            got = store.get("selftest:ping")
            store.delete("selftest:ping")
            redis_rep["selftest"] = got
        else:
            redis_rep["message"] = "Redis ping failed"
    except Exception as e:
        redis_rep = {
            "status": "not_ready",
            "ping": False,
            "message": _safe_str(e),
        }

    # ES
    es = EsClient(
        settings.es_url,
        settings.es_user,
        settings.es_secret,
        verify=settings.es_verify,
        index_map=settings.index_map,
    )
    print(
        "ES auth configured:",
        bool(settings.es_user or settings.es_secret),
        "(user set)" if settings.es_user else "(no user)",
    )
    es_ok = es.ping()
    print("ES ping:", es_ok)
    if not es_ok:
        err = es.last_ping_error or {}
        ping_msg = redact_secrets(
            f"exc_type={err.get('exc_type')} status_code={err.get('status_code')} "
            f"phase={err.get('phase')} message={err.get('message')}"
        )
        print("ES ping detail:", ping_msg)
        es_rep = evaluate_es(
            index_map=index_map,
            expected=expected.get("es") or {},
            stats={},
            mappings={},
            ping_ok=False,
            ping_error=ping_msg,
        )
    else:
        stats = es.stats_by_logical(expected.get("es") or {})
        index_names = [
            (index_map.get(k) or {}).get("index") or f"qa4_{k}"
            for k in (expected.get("es") or {})
        ]
        mappings = fetch_es_mappings(es, index_names)
        # 将 mapping 错误升为 not_ready 线索：evaluate 时若 properties 空且有 _error
        norm_maps: dict[str, Any] = {}
        for name, body in mappings.items():
            if isinstance(body, dict) and body.get("_error"):
                norm_maps[name] = {"properties": {}}
            else:
                norm_maps[name] = body
        es_rep = evaluate_es(
            index_map=index_map,
            expected=expected.get("es") or {},
            stats=stats,
            mappings=norm_maps,
            ping_ok=True,
        )
        # mapping 拉取失败补 message
        for logical, row in es_rep.get("indices", {}).items():
            idx = row.get("index")
            raw = mappings.get(idx) or {}
            if isinstance(raw, dict) and raw.get("_error") and row.get("vector_field"):
                row["status"] = merge_status(row.get("status") or "ok", "not_ready")
                err = redact_secrets(str(raw["_error"]))
                extra = f"mapping 读取失败：{err}"
                row["message"] = (
                    f"{row['message']}; {extra}" if row.get("message") else extra
                )
        es_rep["status"] = merge_status(
            es_rep.get("status") or "ok",
            *[
                r.get("status") or "ok"
                for r in (es_rep.get("indices") or {}).values()
            ],
        )

    # Neo4j
    neo = Neo4jClient(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_secret)
    try:
        n_ok = neo.ping()
        print("Neo4j ping:", n_ok)
        if not n_ok:
            neo_rep = evaluate_neo4j(
                {},
                expected.get("neo4j") or {},
                ping_ok=False,
                ping_error="Neo4j ping failed",
            )
        else:
            labels = list((expected.get("neo4j") or {}).keys())
            counts = neo.label_counts(labels)
            neo_rep = evaluate_neo4j(counts, expected.get("neo4j") or {}, ping_ok=True)
    except Exception as e:
        neo_rep = evaluate_neo4j(
            {},
            expected.get("neo4j") or {},
            ping_ok=False,
            ping_error=_safe_str(e),
        )
    finally:
        neo.close()

    report = summarize_report(
        redis=redis_rep, elasticsearch=es_rep, neo4j=neo_rep
    )
    return report


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="qa4 服务连通性检查")
    p.add_argument("--dry-run", action="store_true", help="不联网，只打印将检查的目标")
    args = p.parse_args(argv)

    reset_settings_cache()
    import os

    env = getattr(os, "environ")
    env.setdefault("QA4_ES_URL", "http://localhost:9202")
    env.setdefault("QA4_NEO4J_URI", "bolt://localhost:7689")
    env.setdefault("QA4_REDIS_URL", "redis://127.0.0.1:6381/0")

    settings = get_settings(require_runtime=False)
    expected = settings.expected_counts
    index_map = settings.index_map.get("indices") or {}

    _print_targets(settings, expected, index_map)

    if args.dry_run:
        print("dry-run：不联网")
        print("总体状态: ok (dry-run)")
        return 0

    try:
        report = run_live_checks(settings)
    except Exception as e:
        print("check_services 异常:", _safe_str(e))
        print("总体状态: not_ready")
        return 1

    print(json.dumps(report, ensure_ascii=False, indent=2))
    status = report.get("status") or "not_ready"
    print(f"总体状态: {status}")
    return exit_code_for_status(status)


if __name__ == "__main__":
    raise SystemExit(main())
