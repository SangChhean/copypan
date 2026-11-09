# -*- coding: utf-8 -*-
"""只读对比 qa4-es 上的 qa4_* 与旧 ES 上的 panai4_*。

不允许任何写操作。密码仅从环境变量读取：
  QA4_ES_PASSWORD -> qa4-es（默认 http://127.0.0.1:9202）
  OLD_ES_PASSWORD  -> 旧 ES（默认 http://127.0.0.1:9200）

用法：
  python es_verify.py --self-test
  python es_verify.py --old-user elastic
  python es_verify.py --only hymns bible --skip-bm25 --skip-knn
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import random
import sys
import time
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterable, Iterator

HERE = Path(__file__).resolve().parent
QUERIES_PATH = HERE.parent / "eval" / "es_verify_queries.json"
DEFAULT_LOG_DIR = Path(r"G:\PanAI4.0专用\logs")
SOURCE_PREFIX = "panai4_"
TARGET_PREFIX = "qa4_"
QA4_CLUSTER = "qa4"
VEC_DIMS = 1024
SCROLL_SIZE = 2000
SCROLL_KEEP = "2m"
CONTENT_EXCLUDE = frozenset({"embedding", "text_vector"})
ANALYZE_TEXTS = [
    "神的经纶与基督的身体",
    "生命的流与生命的供应",
    "召会是基督的身体",
    "那灵与我们的灵同证",
    "圣经恢复本的注解",
]
# 用于确认走的是 IK 词级分析，而非 standard 逐字切分
ANALYZE_PROBE_TEXT = "神的经纶与基督的身体"
# field=text → ik_max_word（细）：可拆出 经纶/基督/身体
ANALYZE_PROBE_WORDS_FIELD_TEXT = ("经纶", "基督", "身体")
# analyzer=ik_smart（粗）：常见为「神的经纶」「基督的身体」，不保证单独「经纶」
ANALYZE_PROBE_WORDS_IK_SMART = ("神的经纶",)
RNG_SEED = 20261109

# suffix -> meta（与 es_import INDEX_SPECS 对齐）
INDEX_PAIRS: dict[str, dict[str, Any]] = {
    "outline_12490": {"expect": 55841, "vec_field": "embedding", "full_vec": False},
    "outline_feasts": {"expect": 11110, "vec_field": "embedding", "full_vec": False},
    "bible": {"expect": 3691, "vec_field": "embedding", "full_vec": True},
    "hymns": {"expect": 9154, "vec_field": "embedding", "full_vec": True},
    "text_life": {"expect": 39463, "vec_field": "text_vector", "full_vec": False},
    "text_cwwl": {"expect": 178107, "vec_field": "text_vector", "full_vec": False},
    "text_cwwn": {"expect": 32032, "vec_field": "text_vector", "full_vec": False},
    "text_others": {"expect": 15481, "vec_field": "text_vector", "full_vec": False},
    "map_note": {"expect": 16052, "vec_field": "text_vector", "full_vec": False},
    "pano_catalog": {"expect": 53151, "vec_field": None, "full_vec": False},
}

WRITE_METHOD_NAMES = frozenset(
    {
        "index",
        "create",
        "delete",
        "update",
        "bulk",
        "update_by_query",
        "delete_by_query",
        "reindex",
        "put_script",
        "put_template",
        "put_alias",
        "close",
        "open",
        "shrink",
        "split",
        "clone",
        "rollover",
        "forcemerge",
        "refresh",
        "flush",
        "put_settings",
        "put_mapping",
        "simulate_index_template",
    }
)


class ReadOnlyError(PermissionError):
    pass


class _ReadOnlyProxy:
    """递归包装 ES 客户端/子对象，拦截写方法名与危险 perform_request。"""

    def __init__(self, inner: Any, label: str = "es"):
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "_label", label)

    def __getattr__(self, name: str) -> Any:
        if name in WRITE_METHOD_NAMES:
            raise ReadOnlyError(f"拒绝写调用: {self._label}.{name}()")
        attr = getattr(self._inner, name)
        if callable(attr):
            if name in ("perform_request", "http_request"):
                return self._wrap_perform(attr)
            # indices / cat / cluster 等命名空间继续包装
            return attr
        if name in ("indices", "cat", "cluster", "nodes", "snapshot", "tasks", "ingest"):
            return _ReadOnlyProxy(attr, f"{self._label}.{name}")
        return attr

    def _wrap_perform(self, fn: Callable) -> Callable:
        def _guard(*args: Any, **kwargs: Any) -> Any:
            method = (kwargs.get("method") or (args[0] if args else "") or "").upper()
            path = str(kwargs.get("path") or (args[1] if len(args) > 1 else "") or "")
            path_l = path.lower()
            allowed = False
            if method == "GET":
                allowed = True
            elif method == "POST" and any(
                x in path_l
                for x in ("/_search", "/_count", "/_analyze", "/_msearch", "/_mtermvectors")
            ):
                allowed = True
            elif method == "DELETE" and "/_search/scroll" in path_l:
                allowed = True  # clear_scroll
            if not allowed:
                raise ReadOnlyError(f"拒绝写/未知请求: {method} {path}")
            return fn(*args, **kwargs)

        return _guard

    # 常用高层读 API 显式转发，便于 mock / 类型提示
    def info(self) -> Any:
        return self._inner.info()

    def ping(self) -> Any:
        return self._inner.ping()

    def count(self, **kwargs: Any) -> Any:
        return self._inner.count(**kwargs)

    def search(self, **kwargs: Any) -> Any:
        return self._inner.search(**kwargs)

    def scroll(self, **kwargs: Any) -> Any:
        return self._inner.scroll(**kwargs)

    def clear_scroll(self, **kwargs: Any) -> Any:
        return self._inner.clear_scroll(**kwargs)


def make_readonly(es: Any) -> _ReadOnlyProxy:
    return _ReadOnlyProxy(es)


class _RedactingFilter(logging.Filter):
    def __init__(self, secrets: list[str]):
        super().__init__()
        self._secrets = [s for s in secrets if s]

    def filter(self, record: logging.LogRecord) -> bool:
        msg = record.getMessage()
        for s in self._secrets:
            if s and s in msg:
                msg = msg.replace(s, "***")
        record.msg = msg
        record.args = ()
        return True


def setup_logging(log_file: Path | None, secrets: list[str]) -> logging.Logger:
    logger = logging.getLogger("qa4_es_verify")
    logger.handlers.clear()
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    sh.addFilter(_RedactingFilter(secrets))
    logger.addHandler(sh)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(fmt)
        fh.addFilter(_RedactingFilter(secrets))
        logger.addHandler(fh)
    return logger


def old_name(suffix: str) -> str:
    return SOURCE_PREFIX + suffix


def new_name(suffix: str) -> str:
    return TARGET_PREFIX + suffix


def canonical_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def classify_field_diff(old_val: Any, new_val: Any, *, old_present: bool, new_present: bool) -> dict[str, Any]:
    """分类单个字段差异（用于报告；比仅用 .get() 能区分 null 与缺失）。"""
    if old_present and not new_present:
        kind = "null_vs_missing" if old_val is None else "only_old_key"
        return {"kind": kind, "old": old_val, "new": "<missing>"}
    if new_present and not old_present:
        kind = "missing_vs_null" if new_val is None else "only_new_key"
        return {"kind": kind, "old": "<missing>", "new": new_val}
    # both present
    if old_val is None and new_val is None:
        return {"kind": "equal", "old": None, "new": None}
    if (type(old_val) is int and type(new_val) is float) or (
        type(old_val) is float and type(new_val) is int
    ):
        if float(old_val) == float(new_val):
            return {
                "kind": "type_int_vs_float",
                "old": old_val,
                "new": new_val,
                "note": "numeric equal after float()",
            }
        return {"kind": "type_int_vs_float", "old": old_val, "new": new_val, "note": "numeric unequal"}
    if isinstance(old_val, str) and isinstance(new_val, str) and old_val != new_val:
        return {"kind": "string_value_diff", "old": old_val, "new": new_val}
    if isinstance(old_val, list) and isinstance(new_val, list):
        if old_val == new_val:
            return {"kind": "equal", "old": old_val, "new": new_val}
        if sorted(map(canonical_json, old_val)) == sorted(map(canonical_json, new_val)):
            return {"kind": "list_order_diff", "old": old_val, "new": new_val}
        return {"kind": "list_value_diff", "old": old_val, "new": new_val}
    if isinstance(old_val, dict) and isinstance(new_val, dict):
        if canonical_json(old_val) == canonical_json(new_val):
            return {"kind": "equal", "old": old_val, "new": new_val}
        return {"kind": "nested_struct_diff", "old": old_val, "new": new_val}
    if old_val != new_val:
        if type(old_val) is not type(new_val):
            return {
                "kind": "type_mismatch",
                "old_type": type(old_val).__name__,
                "new_type": type(new_val).__name__,
                "old": old_val,
                "new": new_val,
            }
        return {"kind": "value_diff", "old": old_val, "new": new_val}
    return {"kind": "equal", "old": old_val, "new": new_val}


def diff_document_fields(sa: dict, sb: dict) -> list[dict[str, Any]]:
    """逐顶层字段比较；区分缺失键与显式 null（修复 fields=[] 盲区）。"""
    keys = sorted(set(sa) | set(sb))
    out: list[dict[str, Any]] = []
    for k in keys:
        old_present = k in sa
        new_present = k in sb
        # 旧逻辑用 .get() 会把缺失与 null 都变成 None，导致整文档指纹不同却 fields=[]
        info = classify_field_diff(
            sa[k] if old_present else None,
            sb[k] if new_present else None,
            old_present=old_present,
            new_present=new_present,
        )
        if info.get("kind") != "equal":
            out.append({"field": k, **info})
    return out


def drop_top_level_nulls(doc: dict) -> dict:
    """只去掉顶层值为 null 的键（以及向量字段）；不递归改嵌套。"""
    return {
        k: v
        for k, v in doc.items()
        if v is not None and k not in CONTENT_EXCLUDE
    }


def semantic_normalize(obj: Any) -> Any:
    """语义无关规范化：数值→float、去掉 null 键、列表保持原顺序。"""
    if isinstance(obj, dict):
        return {
            k: semantic_normalize(v)
            for k, v in sorted(obj.items())
            if v is not None and k not in CONTENT_EXCLUDE
        }
    if isinstance(obj, list):
        return [semantic_normalize(x) for x in obj]
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, int) or isinstance(obj, float):
        return float(obj)
    return obj


def first_path_diff(a: Any, b: Any, path: str = "$") -> dict[str, Any] | None:
    """返回第一处不同的 JSON 路径与取值。"""
    if type(a) is not type(b) and not (
        isinstance(a, (int, float)) and isinstance(b, (int, float))
    ):
        return {"path": path, "old": a, "new": b, "reason": "type"}
    if isinstance(a, dict) and isinstance(b, dict):
        keys = sorted(set(a) | set(b))
        for k in keys:
            pa, pb = k in a, k in b
            if pa != pb:
                return {
                    "path": f"{path}.{k}",
                    "old": a.get(k, "<missing>"),
                    "new": b.get(k, "<missing>"),
                    "reason": "key_presence",
                }
            d = first_path_diff(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return None
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return {"path": path, "old_len": len(a), "new_len": len(b), "reason": "list_len"}
        for i, (x, y) in enumerate(zip(a, b)):
            d = first_path_diff(x, y, f"{path}[{i}]")
            if d:
                return d
        return None
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if float(a) == float(b):
            return None
        return {"path": path, "old": a, "new": b, "reason": "number"}
    if a != b:
        return {"path": path, "old": a, "new": b, "reason": "value"}
    return None


def normalize_mapping_props(props: dict) -> dict:
    """规范化 mapping properties：深拷贝 + 键排序结构。"""

    def norm(v: Any) -> Any:
        if isinstance(v, dict):
            return {k: norm(v[k]) for k in sorted(v.keys())}
        if isinstance(v, list):
            return [norm(x) for x in v]
        return v

    return norm(props)


def extract_mapping_props(mapping_resp: dict, index: str) -> dict:
    # ES 8: {index: {mappings: {properties: ...}}}
    node = mapping_resp.get(index) or next(iter(mapping_resp.values()))
    props = node.get("mappings", {}).get("properties", {})
    return normalize_mapping_props(props)


def extract_analysis_settings(settings_resp: dict, index: str) -> dict:
    node = settings_resp.get(index) or next(iter(settings_resp.values()))
    settings = node.get("settings", {})
    index_settings = settings.get("index", settings)
    analysis = index_settings.get("analysis", {})
    shards = index_settings.get("number_of_shards")
    replicas = index_settings.get("number_of_replicas")
    return {
        "analysis": normalize_mapping_props(analysis) if analysis else {},
        "number_of_shards": shards,
        "number_of_replicas": replicas,
    }


def check_vector_mapping(props: dict, vec_field: str | None, log: logging.Logger) -> list[str]:
    issues = []
    if not vec_field:
        return issues
    vf = props.get(vec_field)
    if not isinstance(vf, dict):
        issues.append(f"缺少向量字段 {vec_field}")
        return issues
    if vf.get("dims") != VEC_DIMS:
        issues.append(f"{vec_field}.dims={vf.get('dims')} 期望 {VEC_DIMS}")
    if vf.get("similarity") != "cosine":
        issues.append(f"{vec_field}.similarity={vf.get('similarity')} 期望 cosine")
    iopts = vf.get("index_options") or {}
    if iopts.get("type") != "int8_hnsw":
        issues.append(f"{vec_field}.index_options.type={iopts.get('type')} 期望 int8_hnsw")
    return issues


def scroll_ids(es: Any, index: str) -> list[str]:
    ids: list[str] = []
    resp = es.search(
        index=index,
        scroll=SCROLL_KEEP,
        size=SCROLL_SIZE,
        _source=False,
        query={"match_all": {}},
    )
    sid = resp.get("_scroll_id")
    try:
        while True:
            hits = resp.get("hits", {}).get("hits", [])
            if not hits:
                break
            for h in hits:
                ids.append(h["_id"])
            resp = es.scroll(scroll_id=sid, scroll=SCROLL_KEEP)
            sid = resp.get("_scroll_id")
    finally:
        if sid:
            try:
                es.clear_scroll(scroll_id=sid)
            except Exception:
                pass
    return ids


def scroll_sources(
    es: Any, index: str, *, exclude_vecs: bool = True
) -> Iterator[tuple[str, dict]]:
    source_filter: Any
    if exclude_vecs:
        source_filter = {"excludes": list(CONTENT_EXCLUDE)}
    else:
        source_filter = True
    resp = es.search(
        index=index,
        scroll=SCROLL_KEEP,
        size=SCROLL_SIZE,
        _source=source_filter,
        query={"match_all": {}},
    )
    sid = resp.get("_scroll_id")
    try:
        while True:
            hits = resp.get("hits", {}).get("hits", [])
            if not hits:
                break
            for h in hits:
                yield h["_id"], (h.get("_source") or {})
            resp = es.scroll(scroll_id=sid, scroll=SCROLL_KEEP)
            sid = resp.get("_scroll_id")
    finally:
        if sid:
            try:
                es.clear_scroll(scroll_id=sid)
            except Exception:
                pass


def mget_sources(es: Any, index: str, ids: list[str], *, include_vec: bool) -> dict[str, dict]:
    """分批 search by ids（只读）。"""
    out: dict[str, dict] = {}
    batch = 200
    src: Any = True if include_vec else {"excludes": list(CONTENT_EXCLUDE)}
    for i in range(0, len(ids), batch):
        chunk = ids[i : i + batch]
        resp = es.search(
            index=index,
            size=len(chunk),
            _source=src,
            query={"ids": {"values": chunk}},
        )
        for h in resp.get("hits", {}).get("hits", []):
            out[h["_id"]] = h.get("_source") or {}
    return out


def stream_id_fingerprint(ids: Iterable[str]) -> str:
    h = hashlib.sha256()
    for _id in ids:
        h.update(_id.encode("utf-8"))
        h.update(b"\n")
    return h.hexdigest()


def content_fingerprint_and_diffs(
    a: dict[str, dict], b: dict[str, dict]
) -> dict[str, Any]:
    """按 _id 排序比较文档内容。

    返回：
      fp_raw_old/new, fp_norm_old/new,
      raw_mismatch, norm_mismatch,
      diffs_sample（仅 normalized 不相等的样本，最多 20）,
      raw_equal_all, normalized_equal_all

    相等判据以 normalized_equal 为准：比较前两边都 drop_top_level_nulls。
    raw_* 保留显式 null，仅作附带记录。
    """
    ha_raw = hashlib.sha256()
    hb_raw = hashlib.sha256()
    ha_n = hashlib.sha256()
    hb_n = hashlib.sha256()
    diffs: list[dict] = []
    raw_mismatch = 0
    norm_mismatch = 0
    all_ids = sorted(set(a) | set(b))
    for _id in all_ids:
        sa = a.get(_id)
        sb = b.get(_id)
        if sa is None or sb is None:
            raw_mismatch += 1
            norm_mismatch += 1
            ca_raw = canonical_json(sa) if sa is not None else ""
            cb_raw = canonical_json(sb) if sb is not None else ""
            ca_n, cb_n = ca_raw, cb_raw
            if len(diffs) < 20:
                diffs.append(
                    {
                        "id": _id,
                        "raw_equal": False,
                        "normalized_equal": False,
                        "fields": ["<missing_doc>"],
                        "field_diffs": [
                            {
                                "field": "<missing_doc>",
                                "kind": "missing_doc",
                                "old_present": sa is not None,
                                "new_present": sb is not None,
                            }
                        ],
                    }
                )
        else:
            sa2 = {k: v for k, v in sa.items() if k not in CONTENT_EXCLUDE}
            sb2 = {k: v for k, v in sb.items() if k not in CONTENT_EXCLUDE}
            ca_raw = canonical_json(sa2)
            cb_raw = canonical_json(sb2)
            sa_n = drop_top_level_nulls(sa2)
            sb_n = drop_top_level_nulls(sb2)
            ca_n = canonical_json(sa_n)
            cb_n = canonical_json(sb_n)
            raw_eq = ca_raw == cb_raw
            norm_eq = ca_n == cb_n
            if not raw_eq:
                raw_mismatch += 1
            if not norm_eq:
                norm_mismatch += 1
                field_diffs = diff_document_fields(sa_n, sb_n)
                if not field_diffs:
                    # 回退到原始字段差异（含 null_vs_missing）便于诊断
                    field_diffs = diff_document_fields(sa2, sb2)
                if not field_diffs:
                    field_diffs = [
                        {
                            "field": "<document>",
                            "kind": "fingerprint_mismatch_without_field",
                            "old": ca_n[:200],
                            "new": cb_n[:200],
                        }
                    ]
                if len(diffs) < 20:
                    diffs.append(
                        {
                            "id": _id,
                            "raw_equal": raw_eq,
                            "normalized_equal": False,
                            "fields": [fd["field"] for fd in field_diffs],
                            "field_diffs": field_diffs,
                        }
                    )
        for h, c in ((ha_raw, ca_raw), (hb_raw, cb_raw), (ha_n, ca_n), (hb_n, cb_n)):
            h.update(_id.encode("utf-8"))
            h.update(b"\0")
            h.update(c.encode("utf-8"))
            h.update(b"\n")
    return {
        "fp_raw_old": ha_raw.hexdigest(),
        "fp_raw_new": hb_raw.hexdigest(),
        "fp_norm_old": ha_n.hexdigest(),
        "fp_norm_new": hb_n.hexdigest(),
        "raw_mismatch": raw_mismatch,
        "norm_mismatch": norm_mismatch,
        "raw_equal_all": raw_mismatch == 0,
        "normalized_equal_all": norm_mismatch == 0,
        "diffs_sample": diffs,
    }


def analyze_tokens(
    es: Any,
    index: str,
    text: str,
    *,
    field: str | None = None,
    analyzer: str | None = None,
) -> list[str]:
    """调用 _analyze。必须指定 field 或 analyzer，避免落到索引默认/standard 逐字切分。"""
    body: dict[str, Any] = {"text": text}
    if field:
        body["field"] = field
    if analyzer:
        body["analyzer"] = analyzer
    try:
        resp = es.indices.analyze(index=index, body=body)
    except TypeError:
        kwargs: dict[str, Any] = {"index": index, "text": text}
        if field:
            kwargs["field"] = field
        if analyzer:
            kwargs["analyzer"] = analyzer
        try:
            resp = es.indices.analyze(**kwargs)
        except AttributeError:
            resp = es.analyze(**kwargs)
    except AttributeError:
        resp = es.analyze(index=index, text=text, field=field, analyzer=analyzer)
    return [t.get("token", "") for t in resp.get("tokens", [])]


def analyze_looks_like_words(tokens: list[str], *, require_words: tuple[str, ...] = ()) -> tuple[bool, str]:
    """若几乎全是单字，判定未走 IK。require_words 中的词应作为 token 出现。"""
    non_empty = [t for t in tokens if t]
    if not non_empty:
        return False, "无 token"
    multi = [t for t in non_empty if len(t) >= 2]
    if not multi:
        return False, "全部为单字，疑似 standard/逐字分析器，未走 IK"
    for w in require_words:
        if w not in non_empty:
            return False, f"缺少预期词 token {w!r}（当前={non_empty}）"
    return True, "ok"


def bm25_search(
    es: Any, index: str, query: str, field: str = "text", k: int = 10
) -> tuple[list[str], list[float], int]:
    """返回 (ids, scores, total_hits)。"""
    resp = es.search(
        index=index,
        size=k,
        _source=False,
        track_total_hits=True,
        query={"match": {field: query}},
    )
    hits = resp.get("hits", {}).get("hits", [])
    ids = [h["_id"] for h in hits]
    scores = [float(h.get("_score") or 0.0) for h in hits]
    total_raw = resp.get("hits", {}).get("total", len(ids))
    if isinstance(total_raw, dict):
        total = int(total_raw.get("value") or 0)
    else:
        total = int(total_raw or 0)
    return ids, scores, total


def bm25_top_ids(es: Any, index: str, query: str, field: str = "text", k: int = 10) -> tuple[list[str], list[float]]:
    ids, scores, _total = bm25_search(es, index, query, field=field, k=k)
    return ids, scores


def _bm25_tie_groups(ids: list[str], scores: list[float], eps: float = 1e-9) -> list[list[str]]:
    groups: list[list[str]] = []
    cur: list[str] = []
    prev = None
    for i, s in zip(ids, scores):
        if prev is None or abs(s - prev) <= eps:
            cur.append(i)
        else:
            groups.append(cur)
            cur = [i]
        prev = s
    if cur:
        groups.append(cur)
    return groups


def classify_bm25_diff(
    old_ids: list[str],
    old_scores: list[float],
    new_ids: list[str],
    new_scores: list[float],
) -> dict[str, Any]:
    """BM25 对照：精确一致 / 并列排序无害 / 真正 FAIL。"""
    max_rel = 0.0
    for a, b in zip(old_scores, new_scores):
        denom = max(abs(a), abs(b), 1e-12)
        max_rel = max(max_rel, abs(a - b) / denom)

    if old_ids == new_ids:
        return {
            "exact": True,
            "tie_harmless": False,
            "fail": False,
            "label": "exact",
            "max_rel_score_diff": round(max_rel, 6),
            "overlap": len(old_ids),
        }

    overlap = len(set(old_ids) & set(new_ids))
    if sorted(old_ids) != sorted(new_ids):
        return {
            "exact": False,
            "tie_harmless": False,
            "fail": True,
            "label": "id_set_or_multiset_diff",
            "max_rel_score_diff": round(max_rel, 6),
            "overlap": overlap,
        }

    # 同多重集合：若仅并列组内重排 -> 无害
    tie_only = True
    idx = 0
    for g in _bm25_tie_groups(old_ids, old_scores):
        nslice = new_ids[idx : idx + len(g)]
        if set(nslice) != set(g):
            tie_only = False
            break
        # 组内分数应相同（旧侧）
        idx += len(g)

    # 亦要求新侧对应名次分数与旧侧同组分数一致（允许整体缩放？不：并列无害指同侧同分置换）
    # 用户：若排序不同的名次分数相同，标并列无害。用旧侧并列组判定即可。
    if tie_only:
        return {
            "exact": False,
            "tie_harmless": True,
            "fail": False,
            "label": "并列排序差异（无害）",
            "max_rel_score_diff": round(max_rel, 6),
            "overlap": overlap,
            "old_tie_groups": _bm25_tie_groups(old_ids, old_scores),
            "new_tie_groups": _bm25_tie_groups(new_ids, new_scores),
        }

    return {
        "exact": False,
        "tie_harmless": False,
        "fail": True,
        "label": "order_diff_non_tie",
        "max_rel_score_diff": round(max_rel, 6),
        "overlap": overlap,
    }


def knn_search_hits(
    es: Any, index: str, field: str, vector: list[float], k: int = 10
) -> list[dict[str, Any]]:
    body = {
        "knn": {
            "field": field,
            "query_vector": vector,
            "k": k,
            "num_candidates": 100,
        },
        "size": k,
        "_source": False,
    }
    try:
        resp = es.search(index=index, body=body)
    except TypeError:
        resp = es.search(index=index, knn=body["knn"], size=k, _source=False)
    return [
        {"_id": h["_id"], "_score": float(h.get("_score") or 0.0)}
        for h in resp.get("hits", {}).get("hits", [])
    ]


def knn_search(es: Any, index: str, field: str, vector: list[float], k: int = 10) -> list[str]:
    return [h["_id"] for h in knn_search_hits(es, index, field, vector, k=k)]


def classify_knn_top1(
    query_id: str,
    query_vec: list[float],
    top1_id: str | None,
    top1_vec: list[float] | None,
) -> dict[str, Any]:
    """单侧 knn top1 判定。

    - top1 即自身 → self_top1
    - top1 非自身但向量与查询完全相同 → 重复向量并列（无害）
    - top1 非自身且向量不同（或缺失）→ FAIL
    """
    if not top1_id:
        return {
            "label": "missing_top1",
            "fail": True,
            "harmless_dup": False,
            "self_top1": False,
        }
    if top1_id == query_id:
        return {
            "label": "self_top1",
            "fail": False,
            "harmless_dup": False,
            "self_top1": True,
        }
    if (
        isinstance(top1_vec, list)
        and isinstance(query_vec, list)
        and top1_vec == query_vec
    ):
        return {
            "label": "重复向量并列（无害）",
            "fail": False,
            "harmless_dup": True,
            "self_top1": False,
        }
    return {
        "label": "top1_vector_mismatch",
        "fail": True,
        "harmless_dup": False,
        "self_top1": False,
    }


def bm25_top_ids(es: Any, index: str, query: str, field: str = "text", k: int = 10) -> tuple[list[str], list[float]]:
    resp = es.search(
        index=index,
        size=k,
        _source=False,
        query={"match": {field: query}},
    )
    hits = resp.get("hits", {}).get("hits", [])
    ids = [h["_id"] for h in hits]
    scores = [float(h.get("_score") or 0.0) for h in hits]
    return ids, scores


class CheckResult:
    def __init__(self, name: str):
        self.name = name
        self.pass_fail: dict[str, str] = {}  # suffix -> PASS/FAIL/SKIP
        self.details: dict[str, Any] = {}
        self.failed = False

    def set(self, suffix: str, ok: bool, detail: Any = None) -> None:
        self.pass_fail[suffix] = "PASS" if ok else "FAIL"
        if detail is not None:
            self.details[suffix] = detail
        if not ok:
            self.failed = True


def verify_pair(
    old_es: Any,
    new_es: Any,
    suffix: str,
    *,
    skip_bm25: bool,
    skip_knn: bool,
    queries: dict,
    log: logging.Logger,
) -> dict[str, CheckResult]:
    meta = INDEX_PAIRS[suffix]
    oidx, nidx = old_name(suffix), new_name(suffix)
    log.info(f"==== 对比 {oidx} <-> {nidx} ====")
    results = {
        "count": CheckResult("count"),
        "mapping": CheckResult("mapping"),
        "settings": CheckResult("settings"),
        "ids": CheckResult("ids"),
        "content": CheckResult("content"),
        "vectors": CheckResult("vectors"),
        "knn": CheckResult("knn"),
        "bm25": CheckResult("bm25"),
        "analyze": CheckResult("analyze"),
    }

    # a) count
    co = int(old_es.count(index=oidx)["count"])
    cn = int(new_es.count(index=nidx)["count"])
    ok = co == cn
    results["count"].set(suffix, ok, {"old": co, "new": cn, "expect": meta["expect"]})
    log.info(f"[count] {suffix}: old={co} new={cn} -> {'PASS' if ok else 'FAIL'}")

    # b) mapping
    mo = extract_mapping_props(old_es.indices.get_mapping(index=oidx), oidx)
    mn = extract_mapping_props(new_es.indices.get_mapping(index=nidx), nidx)
    vec_issues = check_vector_mapping(mo, meta["vec_field"], log) + check_vector_mapping(
        mn, meta["vec_field"], log
    )
    map_ok = canonical_json(mo) == canonical_json(mn) and not vec_issues
    results["mapping"].set(
        suffix,
        map_ok,
        {"equal": canonical_json(mo) == canonical_json(mn), "vector_issues": vec_issues},
    )
    log.info(f"[mapping] {suffix}: -> {'PASS' if map_ok else 'FAIL'} vec_issues={vec_issues}")

    # c) settings
    so = extract_analysis_settings(old_es.indices.get_settings(index=oidx), oidx)
    sn = extract_analysis_settings(new_es.indices.get_settings(index=nidx), nidx)
    set_ok = canonical_json(so["analysis"]) == canonical_json(sn["analysis"])
    results["settings"].set(
        suffix,
        set_ok,
        {
            "analysis_equal": set_ok,
            "old_shards": so["number_of_shards"],
            "old_replicas": so["number_of_replicas"],
            "new_shards": sn["number_of_shards"],
            "new_replicas": sn["number_of_replicas"],
        },
    )
    log.info(
        f"[settings] {suffix}: analysis -> {'PASS' if set_ok else 'FAIL'} "
        f"shards={so['number_of_shards']}/{sn['number_of_shards']} "
        f"replicas={so['number_of_replicas']}/{sn['number_of_replicas']}"
    )

    # d) ids
    ids_o = sorted(scroll_ids(old_es, oidx))
    ids_n = sorted(scroll_ids(new_es, nidx))
    set_o, set_n = set(ids_o), set(ids_n)
    only_o = len(set_o - set_n)
    only_n = len(set_n - set_o)
    fp_o = stream_id_fingerprint(ids_o)
    fp_n = stream_id_fingerprint(ids_n)
    ids_ok = fp_o == fp_n and only_o == 0 and only_n == 0
    results["ids"].set(
        suffix,
        ids_ok,
        {
            "old_n": len(ids_o),
            "new_n": len(ids_n),
            "fp_old": fp_o,
            "fp_new": fp_n,
            "only_old": only_o,
            "only_new": only_n,
        },
    )
    log.info(
        f"[ids] {suffix}: n={len(ids_o)}/{len(ids_n)} only_old={only_o} only_new={only_n} -> "
        f"{'PASS' if ids_ok else 'FAIL'}"
    )

    # e) content：结论以去掉顶层 null 后的 normalized_equal 为准；raw 作附带记录
    src_o = {i: s for i, s in scroll_sources(old_es, oidx, exclude_vecs=True)}
    src_n = {i: s for i, s in scroll_sources(new_es, nidx, exclude_vecs=True)}
    cinfo = content_fingerprint_and_diffs(src_o, src_n)
    content_ok = bool(cinfo["normalized_equal_all"])
    results["content"].set(
        suffix,
        content_ok,
        {
            "raw_equal": cinfo["raw_equal_all"],
            "normalized_equal": cinfo["normalized_equal_all"],
            "fp_raw_old": cinfo["fp_raw_old"],
            "fp_raw_new": cinfo["fp_raw_new"],
            "fp_norm_old": cinfo["fp_norm_old"],
            "fp_norm_new": cinfo["fp_norm_new"],
            "raw_mismatch": cinfo["raw_mismatch"],
            "norm_mismatch": cinfo["norm_mismatch"],
            # 兼容旧字段名
            "fp_old": cinfo["fp_raw_old"],
            "fp_new": cinfo["fp_raw_new"],
            "diffs_sample": cinfo["diffs_sample"],
        },
    )
    log.info(
        f"[content] {suffix}: raw_equal={cinfo['raw_equal_all']} "
        f"normalized_equal={cinfo['normalized_equal_all']} "
        f"raw_mism={cinfo['raw_mismatch']} norm_mism={cinfo['norm_mismatch']} -> "
        f"{'PASS' if content_ok else 'FAIL'}"
    )
    for d in cinfo["diffs_sample"][:5]:
        log.info(f"  content_diff id={d['id']} fields={d['fields']}")

    # f) vectors
    vf = meta["vec_field"]
    if not vf:
        results["vectors"].pass_fail[suffix] = "SKIP"
        results["vectors"].details[suffix] = {"reason": "no vector field"}
        log.info(f"[vectors] {suffix}: SKIP")
    else:
        common = sorted(set_o & set_n)
        if meta["full_vec"]:
            sample_ids = common
        else:
            rng = random.Random(RNG_SEED)
            sample_ids = common[:]
            rng.shuffle(sample_ids)
            sample_ids = sample_ids[:500]
        docs_o = mget_sources(old_es, oidx, sample_ids, include_vec=True)
        docs_n = mget_sources(new_es, nidx, sample_ids, include_vec=True)
        mism = 0
        for _id in sample_ids:
            vo = docs_o.get(_id, {}).get(vf)
            vn = docs_n.get(_id, {}).get(vf)
            if vo != vn:
                mism += 1
        vec_ok = mism == 0
        results["vectors"].set(
            suffix,
            vec_ok,
            {"compared": len(sample_ids), "mismatch": mism, "full": bool(meta["full_vec"])},
        )
        log.info(
            f"[vectors] {suffix}: compared={len(sample_ids)} mismatch={mism} -> "
            f"{'PASS' if vec_ok else 'FAIL'}"
        )

    # g) knn
    if skip_knn or not vf:
        results["knn"].pass_fail[suffix] = "SKIP"
        log.info(f"[knn] {suffix}: SKIP")
    else:
        common = sorted(set_o & set_n)
        rng = random.Random(RNG_SEED + 1)
        pick = common[:]
        rng.shuffle(pick)
        pick = pick[:30]
        docs = mget_sources(old_es, oidx, pick, include_vec=True)
        self_top1 = 0
        harmless_dup = 0
        overlaps: list[int] = []
        low_queries: list[dict[str, Any]] = []
        fail_samples: list[dict[str, Any]] = []
        harmless_samples: list[dict[str, Any]] = []
        any_fail = False
        for _id in pick:
            vec = docs.get(_id, {}).get(vf)
            if not isinstance(vec, list):
                any_fail = True
                fail_samples.append({"id": _id, "reason": "missing_query_vector"})
                continue
            hits_old = knn_search_hits(old_es, oidx, vf, vec, k=10)
            hits_new = knn_search_hits(new_es, nidx, vf, vec, k=10)
            ids_old = [h["_id"] for h in hits_old]
            ids_new = [h["_id"] for h in hits_new]
            top1_old = ids_old[0] if ids_old else None
            top1_new = ids_new[0] if ids_new else None
            # 仅当非自身时取 top1 向量，判断是否重复内容并列
            need_old = [top1_old] if top1_old and top1_old != _id else []
            need_new = [top1_new] if top1_new and top1_new != _id else []
            top_docs_o = (
                mget_sources(old_es, oidx, need_old, include_vec=True) if need_old else {}
            )
            top_docs_n = (
                mget_sources(new_es, nidx, need_new, include_vec=True) if need_new else {}
            )
            vec_top_o = (
                top_docs_o.get(top1_old or "", {}).get(vf) if need_old else vec
            )
            vec_top_n = (
                top_docs_n.get(top1_new or "", {}).get(vf) if need_new else vec
            )
            cls_o = classify_knn_top1(_id, vec, top1_old, vec_top_o if need_old else vec)
            cls_n = classify_knn_top1(_id, vec, top1_new, vec_top_n if need_new else vec)
            if cls_o["self_top1"] and cls_n["self_top1"]:
                self_top1 += 1
            if cls_o["harmless_dup"] or cls_n["harmless_dup"]:
                harmless_dup += 1
                harmless_samples.append(
                    {
                        "id": _id,
                        "old": {
                            "top1": top1_old,
                            "label": cls_o["label"],
                            "harmless_dup": cls_o["harmless_dup"],
                            "self_top1": cls_o["self_top1"],
                        },
                        "new": {
                            "top1": top1_new,
                            "label": cls_n["label"],
                            "harmless_dup": cls_n["harmless_dup"],
                            "self_top1": cls_n["self_top1"],
                        },
                        "both_sides_harmless_dup": bool(
                            cls_o["harmless_dup"] and cls_n["harmless_dup"]
                        ),
                    }
                )
            if cls_o["fail"] or cls_n["fail"]:
                any_fail = True
                fail_samples.append(
                    {
                        "id": _id,
                        "old": {
                            "top1": top1_old,
                            "label": cls_o["label"],
                            "fail": cls_o["fail"],
                        },
                        "new": {
                            "top1": top1_new,
                            "label": cls_n["label"],
                            "fail": cls_n["fail"],
                        },
                    }
                )
            inter = len(set(ids_old) & set(ids_new))
            overlaps.append(inter)
            top1_same = ids_old[:1] == ids_new[:1]
            if inter < 5 or not top1_same:
                low_queries.append(
                    {
                        "id": _id,
                        "overlap": inter,
                        "top1_same": top1_same,
                        "old": ids_old,
                        "new": ids_new,
                    }
                )
        mean_ov = sum(overlaps) / len(overlaps) if overlaps else 0.0
        min_ov = min(overlaps) if overlaps else 0
        # 样本须全部完成；自身非第一仅当 top1 向量≠查询向量才 FAIL
        knn_ok = (not any_fail) and len(overlaps) == len(pick)
        results["knn"].set(
            suffix,
            knn_ok,
            {
                "samples": len(pick),
                "self_top1": self_top1,
                "harmless_dup": harmless_dup,
                "overlap_mean": round(mean_ov, 3),
                "overlap_min": min_ov,
                "low_queries": low_queries[:10],
                "harmless_samples": harmless_samples[:10],
                "fail_samples": fail_samples[:10],
                "note": (
                    "int8/HNSW 近似；不要求 top-10 完全一致；"
                    "自身非第一但 top1 向量==查询向量 → 重复向量并列（无害）"
                ),
            },
        )
        log.info(
            f"[knn] {suffix}: self_top1={self_top1}/{len(pick)} "
            f"harmless_dup={harmless_dup} "
            f"overlap_mean={mean_ov:.2f} min={min_ov} -> {'PASS' if knn_ok else 'FAIL'}"
        )

    # h) bm25
    if skip_bm25:
        results["bm25"].pass_fail[suffix] = "SKIP"
        log.info(f"[bm25] {suffix}: SKIP")
    else:
        group_queries = []
        field = "text"
        for gname, g in queries.get("groups", {}).items():
            if suffix in g.get("applies_to_suffixes", []):
                group_queries = list(g.get("queries", []))
                field = g.get("field_hint") or "text"
                break
        if not group_queries:
            results["bm25"].pass_fail[suffix] = "SKIP"
            log.info(f"[bm25] {suffix}: SKIP (no queries)")
        else:
            rows = []
            any_fail = False
            harm_n = 0
            for q in group_queries:
                ido, sco, tot_o = bm25_search(old_es, oidx, q, field=field)
                idn, scn, tot_n = bm25_search(new_es, nidx, q, field=field)
                cls = classify_bm25_diff(ido, sco, idn, scn)
                if cls.get("fail"):
                    any_fail = True
                if cls.get("tie_harmless"):
                    harm_n += 1
                rows.append(
                    {
                        "q": q,
                        "exact": cls.get("exact"),
                        "label": cls.get("label"),
                        "tie_harmless": cls.get("tie_harmless"),
                        "fail": cls.get("fail"),
                        "overlap": cls.get("overlap"),
                        "old_total": tot_o,
                        "new_total": tot_n,
                        "max_rel_score_diff": cls.get("max_rel_score_diff"),
                        "old_ids": ido,
                        "new_ids": idn,
                        "old_scores": sco,
                        "new_scores": scn,
                    }
                )
            bm25_ok = not any_fail
            results["bm25"].set(
                suffix,
                bm25_ok,
                {"queries": rows, "tie_harmless_count": harm_n},
            )
            log.info(
                f"[bm25] {suffix}: fail={any_fail} tie_harmless={harm_n}/{len(rows)} -> "
                f"{'PASS' if bm25_ok else 'FAIL'}"
            )

    # i) analyze：field=text（ik_max_word）与 analyzer=ik_smart 各测一轮
    analyze_ok = True
    arows: list[dict[str, Any]] = []
    modes = [
        {
            "name": "field:text",
            "field": "text",
            "analyzer": None,
            "require_words": ANALYZE_PROBE_WORDS_FIELD_TEXT,
        },
        {
            "name": "analyzer:ik_smart",
            "field": None,
            "analyzer": "ik_smart",
            "require_words": ANALYZE_PROBE_WORDS_IK_SMART,
        },
    ]
    # 探针：必须产出词而非单字；field:text 与 ik_smart 预期词不同
    probe_detail: dict[str, Any] = {"text": ANALYZE_PROBE_TEXT, "modes": []}
    for mode in modes:
        to = analyze_tokens(
            old_es, oidx, ANALYZE_PROBE_TEXT, field=mode["field"], analyzer=mode["analyzer"]
        )
        tn = analyze_tokens(
            new_es, nidx, ANALYZE_PROBE_TEXT, field=mode["field"], analyzer=mode["analyzer"]
        )
        ok_words_o, reason_o = analyze_looks_like_words(
            to, require_words=mode["require_words"]
        )
        ok_words_n, reason_n = analyze_looks_like_words(
            tn, require_words=mode["require_words"]
        )
        same = to == tn
        mode_ok = same and ok_words_o and ok_words_n
        if not mode_ok:
            analyze_ok = False
            if not ok_words_o or not ok_words_n:
                log.error(
                    f"[analyze] {suffix} 探针未走 IK（{mode['name']}）："
                    f"old={reason_o}; new={reason_n}; old_tokens={to}; new_tokens={tn}"
                )
        probe_detail["modes"].append(
            {
                "mode": mode["name"],
                "equal": same,
                "old_ik_ok": ok_words_o,
                "new_ik_ok": ok_words_n,
                "old_reason": reason_o,
                "new_reason": reason_n,
                "old": to,
                "new": tn,
            }
        )

    for text in ANALYZE_TEXTS:
        for mode in modes:
            to = analyze_tokens(old_es, oidx, text, field=mode["field"], analyzer=mode["analyzer"])
            tn = analyze_tokens(new_es, nidx, text, field=mode["field"], analyzer=mode["analyzer"])
            same = to == tn
            if not same:
                analyze_ok = False
            arows.append(
                {
                    "text": text,
                    "mode": mode["name"],
                    "equal": same,
                    "old": to,
                    "new": tn,
                }
            )
    results["analyze"].set(
        suffix,
        analyze_ok,
        {"probe": probe_detail, "texts": arows},
    )
    log.info(f"[analyze] {suffix}: -> {'PASS' if analyze_ok else 'FAIL'}")

    return results


def assert_clusters(old_es: Any, new_es: Any, log: logging.Logger) -> None:
    oinfo = old_es.info()
    ninfo = new_es.info()
    oc = str(oinfo.get("cluster_name") or "")
    nc = str(ninfo.get("cluster_name") or "")
    if nc != QA4_CLUSTER:
        raise SystemExit(f"中止：qa4-es cluster_name={nc!r}，必须为 {QA4_CLUSTER!r}")
    if oc == QA4_CLUSTER:
        raise SystemExit(f"中止：旧 ES cluster_name 也是 {QA4_CLUSTER!r}，疑似连错集群")
    log.info(f"cluster_ok old={oc} new={nc}")


def make_es_client(url: str, user: str, password: str) -> Any:
    try:
        from elasticsearch import Elasticsearch
    except ImportError as e:
        raise SystemExit("需要安装 elasticsearch：pip install elasticsearch") from e
    return Elasticsearch(
        hosts=[url],
        basic_auth=(user, password),
        request_timeout=180,
        verify_certs=False,
        ssl_show_warn=False,
    )


# ---------------- mock / self-test ----------------


class _MockIndices:
    def __init__(self, store: "_MockES"):
        self._s = store

    def get_mapping(self, index: str) -> dict:
        return {index: {"mappings": {"properties": deepcopy(self._s.mappings[index])}}}

    def get_settings(self, index: str) -> dict:
        return {
            index: {
                "settings": {
                    "index": {
                        "number_of_shards": "1",
                        "number_of_replicas": "0",
                        "analysis": deepcopy(self._s.analysis),
                        "uuid": "ignore-me",
                        "creation_date": "0",
                        "version": {"created": "1"},
                        "provided_name": index,
                    }
                }
            }
        }

    def analyze(self, index: str, body: dict | None = None, text: str | None = None, **kwargs: Any) -> dict:
        body = body or {}
        t = text if text is not None else body.get("text")
        if t is None:
            t = kwargs.get("text")
        field = body.get("field", kwargs.get("field"))
        analyzer = body.get("analyzer", kwargs.get("analyzer"))
        # 未指定 field/analyzer 时模拟 standard 逐字（用于证明旧写法的问题）
        if not field and not analyzer:
            tokens = [{"token": ch} for ch in (t or "") if not ch.isspace()]
            return {"tokens": tokens}
        # ik_smart：粗粒度；field=text≈ik_max_word：重叠细词（含 经纶/基督/身体）
        # 探针句用固定表，保证与真机序列一致量级，供 self-test 断言。
        s = t or ""
        smart = analyzer == "ik_smart"
        probe_smart = {
            "神的经纶与基督的身体": ["神的经纶", "与", "基督的身体"],
            "生命的流与生命的供应": ["生命的流", "与", "生命的供应"],
            "召会是基督的身体": ["召", "会是", "基督的身体"],
            "那灵与我们的灵同证": ["那灵", "与", "我们", "的", "灵", "同", "证"],
            "圣经恢复本的注解": ["圣经恢复本", "的", "注解"],
        }
        probe_max = {
            "神的经纶与基督的身体": [
                "神的经纶",
                "经纶",
                "与",
                "基督的身体",
                "基督",
                "的",
                "身体",
            ],
            "生命的流与生命的供应": [
                "生命的流",
                "生命",
                "的",
                "流",
                "与",
                "生命的供应",
                "生命",
                "的",
                "供应",
            ],
            "召会是基督的身体": ["召会", "会是", "基督的身体", "基督", "的", "身体"],
            "那灵与我们的灵同证": ["那灵", "与我", "我们", "的", "灵", "同", "证"],
            "圣经恢复本的注解": [
                "圣经恢复本",
                "圣经",
                "恢复本",
                "恢复",
                "复本",
                "的",
                "注解",
            ],
        }
        table = probe_smart if smart else probe_max
        if s in table:
            return {"tokens": [{"token": x} for x in table[s]]}
        # 其它文本：最长匹配；max_word 额外挂出「经纶/基督/身体」等子词
        coarse = [
            "神的经纶",
            "基督的身体",
            "生命的流",
            "生命的供应",
            "圣经恢复本",
            "那灵",
            "同证",
            "注解",
        ]
        fine = ["经纶", "基督", "身体", "生命", "供应", "召会", "圣经", "恢复本"]
        lex = list(coarse) if smart else (list(coarse) + list(fine))
        out: list[str] = []
        i = 0
        while i < len(s):
            if s[i].isspace():
                i += 1
                continue
            matched = None
            for w in sorted(lex, key=len, reverse=True):
                if s.startswith(w, i):
                    matched = w
                    break
            if matched:
                out.append(matched)
                if not smart:
                    for sub in fine:
                        pos = matched.find(sub)
                        if pos >= 0 and sub != matched:
                            out.append(sub)
                i += len(matched)
            else:
                out.append(s[i])
                i += 1
        return {"tokens": [{"token": x} for x in out]}


class _MockES:
    """内存假 ES：支持本脚本用到的只读 API。"""

    def __init__(self, cluster_name: str):
        self.cluster_name = cluster_name
        self.docs: dict[str, dict[str, dict]] = {}  # index -> id -> source
        self.mappings: dict[str, dict] = {}
        self.analysis = {
            "analyzer": {"default": {"type": "standard"}},
            "tokenizer": {},
            "filter": {},
        }
        self.indices = _MockIndices(self)
        self._scrolls: dict[str, list[str]] = {}

    def info(self) -> dict:
        return {"cluster_name": self.cluster_name, "version": {"number": "8.19.0"}}

    def ping(self) -> bool:
        return True

    def count(self, index: str, **kwargs: Any) -> dict:
        query = kwargs.get("query")
        body = kwargs.get("body") or {}
        if query is None and isinstance(body, dict):
            query = body.get("query")
        docs = self.docs.get(index, {})
        if not query:
            return {"count": len(docs)}
        if "match" in query:
            field, qtext = next(iter(query["match"].items()))
            if isinstance(qtext, dict):
                qtext = qtext.get("query", "")
            n = sum(1 for src in docs.values() if qtext and qtext in str(src.get(field, "")))
            return {"count": n}
        return {"count": len(docs)}

    def search(self, index: str, **kwargs: Any) -> dict:
        body = kwargs.get("body") or {}
        # knn
        knn = kwargs.get("knn") or body.get("knn")
        if knn:
            field = knn["field"]
            qv = knn["query_vector"]
            k = int(knn.get("k") or 10)
            scored = []
            for _id, src in self.docs.get(index, {}).items():
                vec = src.get(field)
                if not isinstance(vec, list):
                    continue
                # 负 L2 作分
                dist = sum((a - b) ** 2 for a, b in zip(qv, vec))
                scored.append((_id, -dist))
            # 同分按 _id 升序，便于 mock 复现「重复向量并列」
            scored.sort(key=lambda x: (-x[1], x[0]))
            hits = [{"_id": i, "_score": s, "_source": {}} for i, s in scored[:k]]
            return {"hits": {"hits": hits}}

        query = kwargs.get("query") or body.get("query") or {"match_all": {}}
        size = int(kwargs.get("size") or body.get("size") or 10)
        source = kwargs.get("_source", True)
        scroll = kwargs.get("scroll")

        ids = list(self.docs.get(index, {}).keys())
        if "ids" in query:
            want = set(query["ids"]["values"])
            ids = [i for i in ids if i in want]
        elif "match" in query:
            field, qtext = next(iter(query["match"].items()))
            if isinstance(qtext, dict):
                qtext = qtext.get("query", "")
            scored = []
            for _id in ids:
                text = str(self.docs[index][_id].get(field, ""))
                score = 1.0 if qtext and qtext in text else (0.1 if text else 0.0)
                scored.append((_id, score))
            scored.sort(key=lambda x: (-x[1], x[0]))
            ids = [i for i, _ in scored]
        else:
            ids = sorted(ids)

        page = ids[:size]
        hits = []
        for _id in page:
            src = self.docs[index][_id]
            if source is False:
                s = None
            elif isinstance(source, dict) and source.get("excludes"):
                s = {k: v for k, v in src.items() if k not in source["excludes"]}
            else:
                s = src
            hit = {"_id": _id, "_score": 1.0}
            if s is not None:
                hit["_source"] = s
            hits.append(hit)

        resp: dict[str, Any] = {
            "hits": {
                "hits": hits,
                "total": {"value": len(ids), "relation": "eq"},
            }
        }
        if scroll:
            sid = f"scroll-{index}-{len(self._scrolls)}"
            # remaining after first page
            self._scrolls[sid] = ids[size:]
            resp["_scroll_id"] = sid
        return resp

    def scroll(self, scroll_id: str | None = None, **kwargs: Any) -> dict:
        sid = scroll_id or kwargs.get("scroll_id")
        remain = self._scrolls.get(sid or "", [])
        index = ""
        if sid and sid.startswith("scroll-"):
            rest = sid[len("scroll-") :]
            index = rest.rsplit("-", 1)[0]
        page = remain[:SCROLL_SIZE]
        self._scrolls[sid or ""] = remain[SCROLL_SIZE:]
        hits = []
        for _id in page:
            src = self.docs.get(index, {}).get(_id, {})
            hits.append({"_id": _id, "_source": src, "_score": 1.0})
        return {"_scroll_id": sid, "hits": {"hits": hits}}

    def clear_scroll(self, scroll_id: str | None = None, **kwargs: Any) -> dict:
        sid = scroll_id or kwargs.get("scroll_id")
        self._scrolls.pop(sid or "", None)
        return {"succeeded": True}

    def seed_index(
        self,
        index: str,
        *,
        vec_field: str | None,
        docs: dict[str, dict],
    ) -> None:
        props: dict[str, Any] = {
            "text": {"type": "text", "analyzer": "ik_max_word", "search_analyzer": "ik_smart"},
            "chunk_id": {"type": "keyword"},
        }
        if vec_field:
            props[vec_field] = {
                "type": "dense_vector",
                "dims": VEC_DIMS,
                "index": True,
                "similarity": "cosine",
                "index_options": {"type": "int8_hnsw"},
            }
        self.mappings[index] = props
        self.docs[index] = deepcopy(docs)


def _vec(seed: int) -> list[float]:
    rng = random.Random(seed)
    return [rng.random() for _ in range(VEC_DIMS)]


def run_self_test(log: logging.Logger) -> int:
    log.info("=== self-test（不连接真实 ES）===")
    ok = True
    secrets = ["FAKE_QA4_PW_SELFTEST_9911", "FAKE_OLD_PW_SELFTEST_8822"]

    # --- 写调用拒绝 ---
    class _Writable:
        def index(self, *a, **k):
            return {"result": "created"}

        def info(self):
            return {"cluster_name": "x"}

        def perform_request(self, method, path, **k):
            return {}

    ro = make_readonly(_Writable())
    try:
        ro.index(index="x", document={})
        log.error("WRITE_REJECT_FAIL: index 未被拒绝")
        ok = False
    except ReadOnlyError:
        log.info("WRITE_REJECT_OK: index")
    try:
        ro.perform_request("PUT", "/qa4_bible/_settings", body={})
        log.error("WRITE_REJECT_FAIL: PUT settings")
        ok = False
    except ReadOnlyError:
        log.info("WRITE_REJECT_OK: PUT settings")

    # --- cluster 不符 ---
    try:
        assert_clusters(
            make_readonly(_MockES("qa4")),
            make_readonly(_MockES("qa4")),
            log,
        )
        log.error("CLUSTER_FAIL: 应中止")
        ok = False
    except SystemExit as e:
        log.info(f"CLUSTER_OK old=qa4 blocked: {e}")
    try:
        assert_clusters(
            make_readonly(_MockES("docker-cluster")),
            make_readonly(_MockES("wrong")),
            log,
        )
        log.error("CLUSTER_FAIL: new 非 qa4 应中止")
        ok = False
    except SystemExit as e:
        log.info(f"CLUSTER_OK new!=qa4 blocked: {e}")

    # --- PASS 路径（小索引 hymns 风格）---
    old = _MockES("docker-cluster")
    new = _MockES("qa4")
    docs = {}
    for i in range(20):
        _id = f"h{i}"
        docs[_id] = {
            "chunk_id": _id,
            "text": f"奇异恩典与十字架 {i}",
            "embedding": _vec(1000 + i),
        }
    old.seed_index("panai4_hymns", vec_field="embedding", docs=docs)
    new.seed_index("qa4_hymns", vec_field="embedding", docs=docs)
    # 再做一个无向量的 pano 小集
    pdocs = {f"n{i}": {"node_id": f"n{i}", "text": f"生命课程 {i}"} for i in range(10)}
    old.seed_index("panai4_pano_catalog", vec_field=None, docs=pdocs)
    new.seed_index("qa4_pano_catalog", vec_field=None, docs=pdocs)

    queries = json.loads(QUERIES_PATH.read_text(encoding="utf-8"))
    old_ro, new_ro = make_readonly(old), make_readonly(new)
    assert_clusters(old_ro, new_ro, log)

    for suffix in ("hymns", "pano_catalog"):
        res = verify_pair(
            old_ro,
            new_ro,
            suffix,
            skip_bm25=False,
            skip_knn=(INDEX_PAIRS[suffix]["vec_field"] is None),
            queries=queries,
            log=log,
        )
        for k, cr in res.items():
            st = cr.pass_fail.get(suffix, "SKIP")
            log.info(f"PASS_PATH {suffix}.{k}={st}")
            if st == "FAIL":
                ok = False

    # --- 三种差异检出 ---
    # 1) 少一个 _id
    new2 = _MockES("qa4")
    docs_miss = deepcopy(docs)
    docs_miss.pop("h0")
    new2.seed_index("qa4_hymns", vec_field="embedding", docs=docs_miss)
    res = verify_pair(
        make_readonly(old),
        make_readonly(new2),
        "hymns",
        skip_bm25=True,
        skip_knn=True,
        queries=queries,
        log=log,
    )
    if res["ids"].pass_fail.get("hymns") != "FAIL":
        log.error("DIFF_DETECT_FAIL: 少一个 _id 未被检出")
        ok = False
    else:
        log.info("DIFF_DETECT_OK: missing _id")

    # 2) 某文档字段不同
    new3 = _MockES("qa4")
    docs_field = deepcopy(docs)
    docs_field["h1"]["text"] = "被篡改的文本"
    new3.seed_index("qa4_hymns", vec_field="embedding", docs=docs_field)
    res = verify_pair(
        make_readonly(old),
        make_readonly(new3),
        "hymns",
        skip_bm25=True,
        skip_knn=True,
        queries=queries,
        log=log,
    )
    if res["content"].pass_fail.get("hymns") != "FAIL":
        log.error("DIFF_DETECT_FAIL: 字段不同未被检出")
        ok = False
    else:
        log.info("DIFF_DETECT_OK: field diff")
        sample = res["content"].details.get("hymns", {}).get("diffs_sample", [])
        log.info(f"  sample={sample[:3]}")

    # 3) 向量差一位
    new4 = _MockES("qa4")
    docs_vec = deepcopy(docs)
    v = list(docs_vec["h2"]["embedding"])
    v[0] = v[0] + 1e-3
    docs_vec["h2"]["embedding"] = v
    new4.seed_index("qa4_hymns", vec_field="embedding", docs=docs_vec)
    res = verify_pair(
        make_readonly(old),
        make_readonly(new4),
        "hymns",
        skip_bm25=True,
        skip_knn=True,
        queries=queries,
        log=log,
    )
    if res["vectors"].pass_fail.get("hymns") != "FAIL":
        log.error("DIFF_DETECT_FAIL: 向量差一位未被检出")
        ok = False
    else:
        log.info("DIFF_DETECT_OK: vector bit diff")

    # 4) content 规范化：null ↔ 缺失 → PASS；数值/字符串不同仍 FAIL
    null_a = {
        "d1": {"text": "same", "year": None, "note": None},
        "d2": {"text": "ok", "n": 1},
    }
    null_b = {
        "d1": {"text": "same"},  # year/note 缺失
        "d2": {"text": "ok", "n": 1},
    }
    c_null = content_fingerprint_and_diffs(null_a, null_b)
    if not c_null["normalized_equal_all"] or c_null["raw_equal_all"]:
        log.error(
            f"NULL_NORM_FAIL: expected norm PASS / raw FAIL, got "
            f"norm={c_null['normalized_equal_all']} raw={c_null['raw_equal_all']}"
        )
        ok = False
    else:
        log.info(
            f"NULL_NORM_OK: raw_equal={c_null['raw_equal_all']} "
            f"normalized_equal={c_null['normalized_equal_all']}"
        )

    val_a = {"d1": {"text": "aaa", "n": 1}}
    val_b_str = {"d1": {"text": "bbb", "n": 1}}
    val_b_num = {"d1": {"text": "aaa", "n": 2}}
    c_str = content_fingerprint_and_diffs(val_a, val_b_str)
    c_num = content_fingerprint_and_diffs(val_a, val_b_num)
    if c_str["normalized_equal_all"] or c_num["normalized_equal_all"]:
        log.error(
            f"VALUE_DIFF_FAIL: expected FAIL, got str_norm={c_str['normalized_equal_all']} "
            f"num_norm={c_num['normalized_equal_all']}"
        )
        ok = False
    else:
        log.info("VALUE_DIFF_OK: string/number mismatch still FAIL")

    # 5) analyze：field:text 含 经纶；ik_smart 含 神的经纶（粗粒度，不要求 经纶）
    tok_field = analyze_tokens(old_ro, "panai4_hymns", ANALYZE_PROBE_TEXT, field="text")
    tok_smart = analyze_tokens(
        old_ro, "panai4_hymns", ANALYZE_PROBE_TEXT, analyzer="ik_smart"
    )
    ok_f, reason_f = analyze_looks_like_words(
        tok_field, require_words=ANALYZE_PROBE_WORDS_FIELD_TEXT
    )
    ok_s, reason_s = analyze_looks_like_words(
        tok_smart, require_words=ANALYZE_PROBE_WORDS_IK_SMART
    )
    has_jinglun = "经纶" in tok_smart
    if not ok_f or not ok_s or has_jinglun:
        log.error(
            f"ANALYZE_PROBE_FAIL: field_ok={ok_f}({reason_f}) smart_ok={ok_s}({reason_s}) "
            f"ik_smart_tokens={tok_smart} field_tokens={tok_field}"
        )
        ok = False
    else:
        log.info(
            f"ANALYZE_PROBE_OK: field={tok_field} ik_smart={tok_smart} "
            f"(ik_smart 不含独立『经纶』)"
        )

    # 6) knn：重复向量并列 → 无害 PASS；top1 向量不同 → FAIL
    cls_self = classify_knn_top1("a", [1.0, 0.0], "a", [1.0, 0.0])
    cls_dup = classify_knn_top1("a", [1.0, 0.0], "b", [1.0, 0.0])
    cls_bad = classify_knn_top1("a", [1.0, 0.0], "b", [0.0, 1.0])
    if (
        cls_self["fail"]
        or not cls_self["self_top1"]
        or cls_dup["fail"]
        or not cls_dup["harmless_dup"]
        or not cls_bad["fail"]
        or cls_bad["harmless_dup"]
    ):
        log.error(
            f"KNN_CLASSIFY_FAIL: self={cls_self} dup={cls_dup} bad={cls_bad}"
        )
        ok = False
    else:
        log.info("KNN_CLASSIFY_OK: self / dup-harmless / mismatch-fail")

    dup_docs = deepcopy(docs)
    shared = list(dup_docs["h10"]["embedding"])
    dup_docs["h11"]["embedding"] = list(shared)
    old_dup = _MockES("docker-cluster")
    new_dup = _MockES("qa4")
    old_dup.seed_index("panai4_hymns", vec_field="embedding", docs=dup_docs)
    new_dup.seed_index("qa4_hymns", vec_field="embedding", docs=dup_docs)
    res_dup = verify_pair(
        make_readonly(old_dup),
        make_readonly(new_dup),
        "hymns",
        skip_bm25=True,
        skip_knn=False,
        queries=queries,
        log=log,
    )
    knn_dup = res_dup["knn"]
    det_dup = knn_dup.details.get("hymns", {})
    if knn_dup.pass_fail.get("hymns") != "PASS" or int(det_dup.get("harmless_dup") or 0) < 1:
        log.error(
            f"KNN_DUP_FAIL: status={knn_dup.pass_fail.get('hymns')} detail={det_dup}"
        )
        ok = False
    else:
        log.info(
            f"KNN_DUP_OK: status=PASS harmless_dup={det_dup.get('harmless_dup')} "
            f"both_sides={[s.get('both_sides_harmless_dup') for s in det_dup.get('harmless_samples', [])]}"
        )

    class _WrongTop1(_MockES):
        """强制返回向量不同的非自身 top1，用于检出 FAIL。"""

        def search(self, index: str, **kwargs: Any) -> dict:
            body = kwargs.get("body") or {}
            knn = kwargs.get("knn") or body.get("knn")
            if knn:
                field = knn["field"]
                qv = knn["query_vector"]
                other = None
                for _id, src in self.docs.get(index, {}).items():
                    v = src.get(field)
                    if isinstance(v, list) and v != qv:
                        other = _id
                        break
                if other is None:
                    return super().search(index, **kwargs)
                rest = [i for i in self.docs.get(index, {}) if i != other][:9]
                hits = [{"_id": other, "_score": 99.0, "_source": {}}]
                hits.extend({"_id": i, "_score": 1.0, "_source": {}} for i in rest)
                return {"hits": {"hits": hits}}
            return super().search(index, **kwargs)

    old_bad = _MockES("docker-cluster")
    new_bad = _WrongTop1("qa4")
    old_bad.seed_index("panai4_hymns", vec_field="embedding", docs=docs)
    new_bad.seed_index("qa4_hymns", vec_field="embedding", docs=docs)
    res_bad = verify_pair(
        make_readonly(old_bad),
        make_readonly(new_bad),
        "hymns",
        skip_bm25=True,
        skip_knn=False,
        queries=queries,
        log=log,
    )
    if res_bad["knn"].pass_fail.get("hymns") != "FAIL":
        log.error(
            f"KNN_MISMATCH_FAIL: expected FAIL, got "
            f"{res_bad['knn'].pass_fail.get('hymns')} "
            f"detail={res_bad['knn'].details.get('hymns')}"
        )
        ok = False
    else:
        log.info("KNN_MISMATCH_OK: top1 vector different → FAIL")

    # 假密码脱敏
    filt = _RedactingFilter(secrets)
    rec = logging.LogRecord(
        "t", logging.INFO, __file__, 1, f"pw={secrets[0]} old={secrets[1]}", (), None
    )
    filt.filter(rec)
    if secrets[0] in rec.getMessage() or secrets[1] in rec.getMessage():
        log.error("REDACT_FAIL")
        ok = False
    else:
        log.info("REDACT_OK")

    log.info(f"self-test {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def write_reports(
    report_base: Path,
    summary: dict,
    log: logging.Logger,
) -> None:
    report_base.parent.mkdir(parents=True, exist_ok=True)
    md = report_base.with_suffix(".md")
    js = report_base.with_suffix(".json")
    js.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# qa4_* <-> panai4_* 只读验证报告",
        "",
        f"- 时间: {summary.get('ts')}",
        f"- 旧 ES: {summary.get('old_url')} cluster={summary.get('old_cluster')}",
        f"- qa4-es: {summary.get('new_url')} cluster={summary.get('new_cluster')}",
        f"- 总结果: {'PASS' if summary.get('ok') else 'FAIL'}",
        "",
    ]
    for suffix, block in summary.get("indices", {}).items():
        lines.append(f"## {SOURCE_PREFIX}{suffix} <-> {TARGET_PREFIX}{suffix}")
        for check, info in block.items():
            st = info.get("status", "?")
            lines.append(f"- **{check}**: {st}")
            detail = info.get("detail")
            if detail is not None:
                lines.append(f"  ```json\n  {json.dumps(detail, ensure_ascii=False)[:2000]}\n  ```")
        lines.append("")
    md.write_text("\n".join(lines), encoding="utf-8")
    log.info(f"报告已写: {md} / {js}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Read-only verify qa4_* vs panai4_*")
    p.add_argument("--qa4-url", default="http://127.0.0.1:9202")
    p.add_argument("--old-url", default="http://127.0.0.1:9200")
    p.add_argument("--qa4-user", default="elastic")
    p.add_argument("--old-user", default="elastic", help="旧 ES 用户名")
    p.add_argument("--only", nargs="+", default=None, help="限定 suffix，如 hymns bible")
    p.add_argument("--skip-bm25", action="store_true")
    p.add_argument("--skip-knn", action="store_true")
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--report-base", default=None, help="不含后缀的报告路径前缀")
    p.add_argument("--log-file", default=None)
    p.add_argument("--queries", default=str(QUERIES_PATH))
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    qa4_pw = os.environ.get("QA4_ES_PASSWORD") or ""
    old_pw = os.environ.get("OLD_ES_PASSWORD") or ""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = Path(args.log_file) if args.log_file else (DEFAULT_LOG_DIR / f"qa4_verify_{ts}.log")
    log = setup_logging(log_file, [qa4_pw, old_pw])
    log.info(f"log_file={log_file}")

    if args.self_test:
        return run_self_test(log)

    if not qa4_pw or not old_pw:
        log.error("需要环境变量 QA4_ES_PASSWORD 与 OLD_ES_PASSWORD")
        return 1

    queries = json.loads(Path(args.queries).read_text(encoding="utf-8"))
    raw_only = list(args.only) if args.only else list(INDEX_PAIRS.keys())
    suffixes: list[str] = []
    for s in raw_only:
        if s.startswith(SOURCE_PREFIX):
            suffixes.append(s[len(SOURCE_PREFIX) :])
        elif s.startswith(TARGET_PREFIX):
            suffixes.append(s[len(TARGET_PREFIX) :])
        else:
            suffixes.append(s)
    for s in suffixes:
        if s not in INDEX_PAIRS:
            log.error(f"未知 suffix: {s}")
            return 1

    old_raw = make_es_client(args.old_url, args.old_user, old_pw)
    new_raw = make_es_client(args.qa4_url, args.qa4_user, qa4_pw)
    old_es = make_readonly(old_raw)
    new_es = make_readonly(new_raw)

    try:
        if not old_es.ping() or not new_es.ping():
            log.error("ping 失败")
            return 1
        assert_clusters(old_es, new_es, log)
    except SystemExit as e:
        log.error(str(e))
        return 1

    oinfo = old_es.info()
    ninfo = new_es.info()
    summary: dict[str, Any] = {
        "ts": ts,
        "old_url": args.old_url,
        "new_url": args.qa4_url,
        "old_cluster": oinfo.get("cluster_name"),
        "new_cluster": ninfo.get("cluster_name"),
        "indices": {},
        "ok": True,
        "total_count_old": 0,
        "total_count_new": 0,
    }

    any_fail = False
    for suffix in suffixes:
        pair_res = verify_pair(
            old_es,
            new_es,
            suffix,
            skip_bm25=args.skip_bm25,
            skip_knn=args.skip_knn,
            queries=queries,
            log=log,
        )
        block = {}
        for name, cr in pair_res.items():
            st = cr.pass_fail.get(suffix, "SKIP")
            block[name] = {"status": st, "detail": cr.details.get(suffix)}
            if st == "FAIL":
                any_fail = True
        # accumulate counts
        cd = pair_res["count"].details.get(suffix) or {}
        summary["total_count_old"] += int(cd.get("old") or 0)
        summary["total_count_new"] += int(cd.get("new") or 0)
        summary["indices"][suffix] = block

    if set(suffixes) == set(INDEX_PAIRS.keys()):
        tot_ok = summary["total_count_old"] == 414082 and summary["total_count_new"] == 414082
        log.info(
            f"[total_count] old={summary['total_count_old']} new={summary['total_count_new']} "
            f"expect=414082 -> {'PASS' if tot_ok else 'FAIL'}"
        )
        if not tot_ok:
            any_fail = True
        summary["total_count_ok"] = tot_ok

    summary["ok"] = not any_fail
    report_base = (
        Path(args.report_base)
        if args.report_base
        else (DEFAULT_LOG_DIR / f"qa4_verify_{ts}")
    )
    write_reports(report_base, summary, log)
    return 0 if not any_fail else 4


if __name__ == "__main__":
    sys.exit(main())
