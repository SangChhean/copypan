# -*- coding: utf-8 -*-
"""只读诊断：解释 es_verify content/knn/bm25 FAIL，不改变任何索引。

密码：QA4_ES_PASSWORD / OLD_ES_PASSWORD
用法：
  python es_verify_diag.py --self-test
  python es_verify_diag.py --old-user elastic
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
from collections import Counter
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from es_verify import (  # noqa: E402
    CONTENT_EXCLUDE,
    QUERIES_PATH,
    RNG_SEED,
    bm25_search,
    canonical_json,
    classify_bm25_diff,
    content_fingerprint_and_diffs,
    diff_document_fields,
    first_path_diff,
    knn_search_hits,
    make_es_client,
    make_readonly,
    mget_sources,
    new_name,
    old_name,
    scroll_sources,
    semantic_normalize,
    setup_logging,
    assert_clusters,
    ReadOnlyError,
)

# 优先 QA4_LOG_DIR（与 es_verify / es_import 一致）
DEFAULT_LOG_DIR = Path(
    os.environ.get("QA4_LOG_DIR")
    or (r"G:\PanAI4.0专用\logs" if os.name == "nt" else "/opt/qa4_logs")
)
CONTENT_FAIL_SUFFIXES = [
    "outline_12490",
    "outline_feasts",
    "bible",
    "hymns",
    "text_life",
]
BM25_FAIL_SUFFIXES = ["text_life", "text_cwwl"]
EXTRA_STATS_SUFFIXES = ["outline_12490", "text_life"]


def strip_vecs(doc: dict) -> dict:
    return {k: v for k, v in doc.items() if k not in CONTENT_EXCLUDE}


def diagnose_content(old_es: Any, new_es: Any, suffix: str, log: logging.Logger) -> dict:
    oidx, nidx = old_name(suffix), new_name(suffix)
    log.info(f"==== content diag {oidx} <-> {nidx} ====")
    src_o = {i: strip_vecs(s) for i, s in scroll_sources(old_es, oidx, exclude_vecs=True)}
    src_n = {i: strip_vecs(s) for i, s in scroll_sources(new_es, nidx, exclude_vecs=True)}
    total = len(set(src_o) | set(src_n))
    mism_ids: list[str] = []
    kind_field_counter: Counter[str] = Counter()
    kind_counter: Counter[str] = Counter()
    still_diff_after_sem = 0
    samples: list[dict] = []

    for _id in sorted(set(src_o) | set(src_n)):
        sa, sb = src_o.get(_id), src_n.get(_id)
        if sa is None or sb is None:
            mism_ids.append(_id)
            kind_counter["missing_doc"] += 1
            kind_field_counter["<missing_doc>|missing_doc"] += 1
            continue
        if canonical_json(sa) == canonical_json(sb):
            continue
        mism_ids.append(_id)
        fds = diff_document_fields(sa, sb)
        if not fds:
            fds = [{"field": "<document>", "kind": "fingerprint_mismatch_without_field"}]
        for fd in fds:
            kind_counter[fd["kind"]] += 1
            kind_field_counter[f"{fd['field']}|{fd['kind']}"] += 1
        sem_a = semantic_normalize(sa)
        sem_b = semantic_normalize(sb)
        if canonical_json(sem_a) != canonical_json(sem_b):
            still_diff_after_sem += 1
            semantic_equal = False
        else:
            semantic_equal = True
        if len(samples) < 5:
            samples.append(
                {
                    "id": _id,
                    "field_diffs": fds,
                    "first_path": first_path_diff(sa, sb),
                    "semantic_equal": semantic_equal,
                    "old_json": canonical_json(sa),
                    "new_json": canonical_json(sb),
                }
            )

    ratio = (len(mism_ids) / total) if total else 0.0
    summary_table = [
        {"field": k.split("|", 1)[0], "kind": k.split("|", 1)[1], "count": v}
        for k, v in sorted(kind_field_counter.items(), key=lambda x: -x[1])
    ]
    systemic = ratio >= 0.95
    # 语义规范化后仍不同占比
    sem_ratio = (still_diff_after_sem / total) if total else 0.0
    note = None
    if systemic:
        if still_diff_after_sem == 0:
            note = (
                "近 100% 文档指纹不同，但语义规范化后全部相同 → 系统性表示差异"
                "（如 null vs 缺键、int vs float），非内容实质不同。"
            )
        elif sem_ratio >= 0.95:
            note = "近 100% 文档在语义规范化后仍不同 → 需检查实质字段值差异，不只是表示层。"
        else:
            note = (
                f"近 100% 指纹不同；语义规范化后仍不同 {still_diff_after_sem}/{total} "
                f"({sem_ratio:.2%})，其余为表示层差异。"
            )
    out = {
        "index_pair": f"{oidx}/{nidx}",
        "total_docs": total,
        "mismatch_docs": len(mism_ids),
        "mismatch_ratio": round(ratio, 6),
        "mismatch_ratio_pct": f"{ratio:.2%}",
        "systemic_representation_suspect": systemic,
        "systemic_note": note,
        "kind_counts": dict(kind_counter),
        "field_kind_table": summary_table,
        "still_diff_after_semantic_normalize": still_diff_after_sem,
        "semantic_neutral_mismatches": still_diff_after_sem,
        "samples": samples,
    }
    # 先汇报比例，再汇总种类
    log.info(f"[content] {suffix}: 不一致比例 {len(mism_ids)}/{total} = {ratio:.2%}")
    if note:
        log.info(f"[content] {suffix}: {note}")
    log.info(f"[content] {suffix}: 差异种类 {dict(kind_counter)}；sem_still={still_diff_after_sem}")
    return out


def diagnose_knn_hymns(old_es: Any, new_es: Any, log: logging.Logger) -> dict:
    suffix = "hymns"
    vf = "embedding"
    oidx, nidx = old_name(suffix), new_name(suffix)
    log.info(f"==== knn diag {oidx} ====")
    # 与 es_verify 相同的 30 个采样
    ids_o = sorted({i for i, _ in scroll_sources(old_es, oidx, exclude_vecs=True)})
    ids_n = sorted({i for i, _ in scroll_sources(new_es, nidx, exclude_vecs=True)})
    common = sorted(set(ids_o) & set(ids_n))
    rng = random.Random(RNG_SEED + 1)
    pick = common[:]
    rng.shuffle(pick)
    pick = pick[:30]
    docs = mget_sources(old_es, oidx, pick, include_vec=True)
    failures = []
    for _id in pick:
        vec = docs.get(_id, {}).get(vf)
        if not isinstance(vec, list):
            continue
        old_hits = knn_search_hits(old_es, oidx, vf, vec, k=3)
        new_hits = knn_search_hits(new_es, nidx, vf, vec, k=3)
        old_top1 = old_hits[0]["_id"] if old_hits else None
        new_top1 = new_hits[0]["_id"] if new_hits else None
        self_ok = old_top1 == _id and new_top1 == _id
        if self_ok:
            continue
        # 第一名向量是否与查询完全相同
        top_ids = list({h["_id"] for h in old_hits[:1] + new_hits[:1] if h})
        top_docs = mget_sources(old_es, oidx, list({_id, *top_ids}), include_vec=True)
        qvec = top_docs.get(_id, {}).get(vf)
        old1_vec = top_docs.get(old_top1 or "", {}).get(vf) if old_top1 else None
        # 也取 new 侧 top1 向量（从 new_es）
        new_top_docs = mget_sources(new_es, nidx, [new_top1] if new_top1 else [], include_vec=True)
        new1_vec = new_top_docs.get(new_top1 or "", {}).get(vf) if new_top1 else None
        failures.append(
            {
                "query_id": _id,
                "old_top3": old_hits,
                "new_top3": new_hits,
                "old_top1_is_self": old_top1 == _id,
                "new_top1_is_self": new_top1 == _id,
                "old_top1_vec_equals_query": old1_vec == qvec,
                "new_top1_vec_equals_query": new1_vec == qvec,
                "note": "若 top1 向量==查询向量且 _id 不同，可能是重复内容/并列",
            }
        )
    log.info(f"[knn] hymns failures={len(failures)}")
    for f in failures:
        log.info(
            f"  id={f['query_id']} old_self={f['old_top1_is_self']} new_self={f['new_top1_is_self']} "
            f"old_vec_eq={f['old_top1_vec_equals_query']} new_vec_eq={f['new_top1_vec_equals_query']}"
        )
    return {"failures": failures, "sample_size": len(pick)}


def cat_index_stats(es: Any, index: str) -> dict:
    """只读 _cat/indices 与 _cat/segments。"""
    out: dict[str, Any] = {"index": index}
    try:
        # elasticsearch-py cat APIs
        rows = es.cat.indices(index=index, format="json", bytes="b")
        if isinstance(rows, list) and rows:
            r = rows[0]
            out["docs_count"] = r.get("docs.count")
            out["docs_deleted"] = r.get("docs.deleted")
            out["store_size"] = r.get("store.size")
            out["pri"] = r.get("pri")
            out["rep"] = r.get("rep")
    except Exception as e:
        out["indices_error"] = str(e)
    try:
        segs = es.cat.segments(index=index, format="json")
        if isinstance(segs, list):
            out["segments_count"] = len(segs)
            out["segments_sample"] = segs[:5]
        else:
            out["segments_raw_type"] = type(segs).__name__
    except Exception as e:
        out["segments_error"] = str(e)
    return out


def term_hit_count(es: Any, index: str, term: str = "神", field: str = "text") -> int:
    try:
        resp = es.count(index=index, query={"match": {field: term}})
        return int(resp.get("count") or 0)
    except Exception:
        try:
            resp = es.count(index=index, body={"query": {"match": {field: term}}})
            return int(resp.get("count") or 0)
        except Exception as e:
            return -1


def diagnose_index_stats(old_es: Any, new_es: Any, suffix: str, log: logging.Logger) -> dict:
    oidx, nidx = old_name(suffix), new_name(suffix)
    old_cat = cat_index_stats(old_es, oidx)
    new_cat = cat_index_stats(new_es, nidx)
    old_term = term_hit_count(old_es, oidx, "神")
    new_term = term_hit_count(new_es, nidx, "神")
    out = {
        "old_cat": old_cat,
        "new_cat": new_cat,
        "term_神_match_docs": {"old": old_term, "new": new_term, "diff": new_term - old_term},
    }
    log.info(
        f"[stats] {suffix}: docs.count old/new={old_cat.get('docs_count')}/{new_cat.get('docs_count')} "
        f"deleted={old_cat.get('docs_deleted')}/{new_cat.get('docs_deleted')} "
        f"segments={old_cat.get('segments_count')}/{new_cat.get('segments_count')} "
        f"term[神]={old_term}/{new_term}"
    )
    return out


def diagnose_bm25(old_es: Any, new_es: Any, suffix: str, queries: dict, log: logging.Logger) -> dict:
    oidx, nidx = old_name(suffix), new_name(suffix)
    log.info(f"==== bm25 diag {oidx} ====")
    field = "text"
    qlist = []
    for g in queries.get("groups", {}).values():
        if suffix in g.get("applies_to_suffixes", []):
            qlist = list(g.get("queries", []))
            field = g.get("field_hint") or "text"
            break
    rows = []
    for q in qlist:
        ido, sco, tot_o = bm25_search(old_es, oidx, q, field=field)
        idn, scn, tot_n = bm25_search(new_es, nidx, q, field=field)
        analysis = classify_bm25_diff(ido, sco, idn, scn)
        row = {
            "q": q,
            "old": list(zip(ido, sco)),
            "new": list(zip(idn, scn)),
            "old_total": tot_o,
            "new_total": tot_n,
            **analysis,
        }
        rows.append(row)
        if not analysis.get("exact"):
            log.info(
                f"  q={q!r} label={analysis.get('label')} "
                f"totals={tot_o}/{tot_n} max_rel={analysis.get('max_rel_score_diff')}"
            )
    stats = {
        "old": cat_index_stats(old_es, oidx),
        "new": cat_index_stats(new_es, nidx),
    }
    log.info(f"[bm25] {suffix} cat old={stats['old']} new={stats['new']}")
    return {"queries": rows, "cat": stats}


def run_self_test(log: logging.Logger) -> int:
    log.info("=== es_verify_diag self-test（不连真实 ES）===")
    ok = True
    secrets = ["FAKE_DIAG_QA4_5511", "FAKE_DIAG_OLD_6622"]

    # 写拒绝
    class W:
        def delete(self, *a, **k):
            return {}

        def perform_request(self, method, path, **k):
            return {}

    ro = make_readonly(W())
    try:
        ro.delete(index="x")
        ok = False
        log.error("WRITE_REJECT_FAIL")
    except ReadOnlyError:
        log.info("WRITE_REJECT_OK")

    # --- fields=[] 旧逻辑复现 vs 新逻辑 ---
    # 1 vs 1.0、null vs 缺失、列表顺序
    cases = []
    # null vs missing
    a1 = {"text": "x", "year": None}
    b1 = {"text": "x"}  # year 缺失
    # 旧逻辑
    old_bad = [
        k
        for k in sorted(set(a1) | set(b1))
        if canonical_json(a1.get(k)) != canonical_json(b1.get(k))
    ]
    new_fds = diff_document_fields(a1, b1)
    cases.append(("null_vs_missing", old_bad, new_fds))
    # 1 vs 1.0
    a2 = {"n": 1}
    b2 = {"n": 1.0}
    old_bad2 = [
        k
        for k in sorted(set(a2) | set(b2))
        if canonical_json(a2.get(k)) != canonical_json(b2.get(k))
    ]
    new_fds2 = diff_document_fields(a2, b2)
    cases.append(("int_vs_float", old_bad2, new_fds2))
    # list order
    a3 = {"tags": ["b", "a"]}
    b3 = {"tags": ["a", "b"]}
    old_bad3 = [
        k
        for k in sorted(set(a3) | set(b3))
        if canonical_json(a3.get(k)) != canonical_json(b3.get(k))
    ]
    new_fds3 = diff_document_fields(a3, b3)
    cases.append(("list_order", old_bad3, new_fds3))

    for name, old_b, new_f in cases:
        log.info(f"CASE {name}: old_fields={old_b} new={new_f}")
        if name == "null_vs_missing":
            # 旧逻辑 fields=[]，新逻辑应指出
            if old_b != []:
                log.error("expected old logic empty for null_vs_missing")
                ok = False
            if not any(fd["kind"] == "null_vs_missing" for fd in new_f):
                log.error("new logic missed null_vs_missing")
                ok = False
            else:
                log.info("NULL_MISSING_OK")
        if name == "int_vs_float":
            if not any(fd["kind"] == "type_int_vs_float" for fd in new_f):
                ok = False
                log.error("int_vs_float not classified")
            else:
                log.info("INT_FLOAT_OK")
        if name == "list_order":
            if not any(fd["kind"] == "list_order_diff" for fd in new_f):
                ok = False
                log.error("list_order not classified")
            else:
                log.info("LIST_ORDER_OK")

    # fingerprint 集成：null↔缺失 → normalized PASS；值差异仍进 diffs_sample
    docs_a = {"d1": a1, "d2": a2, "d3": a3}
    docs_b = {"d1": b1, "d2": b2, "d3": b3}
    fp = content_fingerprint_and_diffs(docs_a, docs_b)
    log.info(
        f"FP_SUMMARY raw_equal={fp['raw_equal_all']} "
        f"normalized_equal={fp['normalized_equal_all']} "
        f"raw_mism={fp['raw_mismatch']} norm_mism={fp['norm_mismatch']}"
    )
    # 仅 null↔缺失 时应规范化相等
    fp_null_only = content_fingerprint_and_diffs({"d1": a1}, {"d1": b1})
    if not fp_null_only["normalized_equal_all"] or fp_null_only["raw_equal_all"]:
        ok = False
        log.error(
            f"NULL_NORM_FAIL: expected norm PASS/raw FAIL, got "
            f"norm={fp_null_only['normalized_equal_all']} raw={fp_null_only['raw_equal_all']}"
        )
    else:
        log.info("NULL_NORM_OK")
    # d1 不应再因 null↔缺失进入 norm diffs；d2/d3 仍应有差异
    diffs = fp["diffs_sample"]
    if any(d["id"] == "d1" for d in diffs):
        ok = False
        log.error("d1 null_vs_missing should not appear in norm diffs_sample")
    for d in diffs:
        if d["id"] == "d1" and d.get("fields") == []:
            ok = False
            log.error("fingerprint still reports empty fields for null_vs_missing")
        log.info(
            f"FP_DIFF {d['id']}: fields={d.get('fields')} "
            f"kinds={[x.get('kind') for x in d.get('field_diffs', [])]}"
        )
    if not any(d["id"] in ("d2", "d3") for d in diffs):
        ok = False
        log.error("expected d2/d3 value diffs in diffs_sample")

    # BM25 并列 vs 非并列
    tie = classify_bm25_diff(
        ["a", "b", "c"],
        [1.0, 1.0, 0.5],
        ["b", "a", "c"],
        [1.0, 1.0, 0.5],
    )
    nontie = classify_bm25_diff(
        ["a", "b", "c"],
        [1.0, 0.9, 0.5],
        ["b", "a", "c"],
        [0.95, 0.9, 0.5],
    )
    log.info(
        f"BM25_TIE harmless={tie.get('tie_harmless')} fail={tie.get('fail')} "
        f"nontie_fail={nontie.get('fail')} label={nontie.get('label')}"
    )
    if not tie.get("tie_harmless") or tie.get("fail") or not nontie.get("fail"):
        ok = False
        log.error("BM25 tie discrimination failed")
    else:
        log.info("BM25_TIE_OK")

    # 脱敏
    from es_verify import _RedactingFilter

    filt = _RedactingFilter(secrets)
    import logging as _logging

    rec = _logging.LogRecord("t", _logging.INFO, __file__, 1, f"{secrets[0]} {secrets[1]}", (), None)
    filt.filter(rec)
    if secrets[0] in rec.getMessage():
        ok = False
        log.error("REDACT_FAIL")
    else:
        log.info("REDACT_OK")

    log.info(f"self-test {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


def write_reports(base: Path, summary: dict, log: logging.Logger) -> None:
    base.parent.mkdir(parents=True, exist_ok=True)
    js = base.with_suffix(".json")
    md = base.with_suffix(".md")
    js.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = [
        "# qa4 verify 诊断报告",
        "",
        f"- ts: {summary.get('ts')}",
        f"- ok_self_contained: 见各节",
        "",
        "## 1. fields=[] 根因（代码层）",
        "",
        summary.get("root_cause_note", ""),
        "",
        "## 2. Content 诊断（先比例，再种类）",
        "",
    ]
    for suf, block in (summary.get("content") or {}).items():
        lines.append(f"### {suf}")
        lines.append(
            f"- **不一致比例**: {block.get('mismatch_docs')}/{block.get('total_docs')} "
            f"= **{block.get('mismatch_ratio_pct') or block.get('mismatch_ratio')}**"
        )
        if block.get("systemic_note"):
            lines.append(f"- 系统性判断: {block.get('systemic_note')}")
        lines.append(f"- kinds: `{json.dumps(block.get('kind_counts'), ensure_ascii=False)}`")
        lines.append(
            f"- 语义规范化后仍不同: {block.get('still_diff_after_semantic_normalize')}"
        )
        lines.append("")
        lines.append("| field | kind | count |")
        lines.append("|-------|------|------:|")
        for row in (block.get("field_kind_table") or [])[:30]:
            lines.append(f"| {row['field']} | {row['kind']} | {row['count']} |")
        lines.append("")
        for s in block.get("samples") or []:
            lines.append(f"#### sample `{s['id']}`")
            lines.append(f"- first_path: `{json.dumps(s.get('first_path'), ensure_ascii=False)}`")
            lines.append(f"- semantic_equal: {s.get('semantic_equal')}")
            lines.append("- field_diffs:")
            lines.append(f"```json\n{json.dumps(s.get('field_diffs'), ensure_ascii=False, indent=2)[:3000]}\n```")
            lines.append("<details><summary>并排 JSON</summary>")
            lines.append("")
            lines.append("```json")
            lines.append(s.get("old_json", "")[:4000])
            lines.append("```")
            lines.append("```json")
            lines.append(s.get("new_json", "")[:4000])
            lines.append("```")
            lines.append("</details>")
            lines.append("")
    lines.append("## 3. outline_12490 / text_life 索引统计与「神」命中")
    lines.append("")
    lines.append(
        f"```json\n{json.dumps(summary.get('index_stats'), ensure_ascii=False, indent=2)[:8000]}\n```"
    )
    lines.append("")
    lines.append("## 4. hymns kNN 失败样本")
    lines.append("")
    lines.append(f"```json\n{json.dumps(summary.get('knn'), ensure_ascii=False, indent=2)[:8000]}\n```")
    lines.append("")
    lines.append("## 5. BM25 text_life / text_cwwl")
    lines.append("")
    for suf, block in (summary.get("bm25") or {}).items():
        lines.append(f"### {suf}")
        lines.append(f"```json\n{json.dumps(block.get('cat'), ensure_ascii=False, indent=2)}\n```")
        for q in block.get("queries") or []:
            if q.get("exact"):
                continue
            lines.append(f"- q=`{q.get('q')}` tie_only={q.get('tie_only')} overlap={q.get('overlap')}")
            lines.append(f"  rank_diffs={q.get('rank_diffs')}")
        lines.append("")
    md.write_text("\n".join(lines), encoding="utf-8")
    log.info(f"报告: {md} / {js}")


def parse_args(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--self-test", action="store_true")
    p.add_argument("--qa4-url", default="http://127.0.0.1:9202")
    p.add_argument("--old-url", default="http://127.0.0.1:9200")
    p.add_argument("--qa4-user", default="elastic")
    p.add_argument("--old-user", default="elastic")
    p.add_argument("--log-file", default=None)
    p.add_argument("--report-base", default=None)
    p.add_argument("--queries", default=str(QUERIES_PATH))
    p.add_argument("--skip-content", action="store_true")
    p.add_argument("--skip-knn", action="store_true")
    p.add_argument("--skip-bm25", action="store_true")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    qa4_pw = os.environ.get("QA4_ES_PASSWORD") or ""
    old_pw = os.environ.get("OLD_ES_PASSWORD") or ""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = Path(args.log_file) if args.log_file else (DEFAULT_LOG_DIR / f"qa4_verify_diag_{ts}.log")
    log = setup_logging(log_file, [qa4_pw, old_pw])
    log.info(f"log_file={log_file}")

    root_cause = (
        "指纹使用整文档 `json.dumps(..., sort_keys=True, ensure_ascii=False)`，"
        "会区分「键缺失」与「显式 null」。旧差异字段逻辑用 `dict.get(k)`，"
        "缺失与 null 都变成 None，再 `canonical_json` 都得到 `null`，"
        "于是出现指纹不同但 `fields=[]`。新逻辑用 `k in doc` 区分，并标注差异类型。"
    )

    if args.self_test:
        code = run_self_test(log)
        # 仍写一份短报告
        base = Path(args.report_base) if args.report_base else (DEFAULT_LOG_DIR / f"qa4_verify_diag_{ts}")
        write_reports(
            base,
            {"ts": ts, "root_cause_note": root_cause, "mode": "self-test", "exit": code},
            log,
        )
        return code

    if not qa4_pw or not old_pw:
        log.error("需要 QA4_ES_PASSWORD 与 OLD_ES_PASSWORD")
        return 1

    queries = json.loads(Path(args.queries).read_text(encoding="utf-8"))
    old_es = make_readonly(make_es_client(args.old_url, args.old_user, old_pw))
    new_es = make_readonly(make_es_client(args.qa4_url, args.qa4_user, qa4_pw))
    try:
        assert_clusters(old_es, new_es, log)
    except SystemExit as e:
        log.error(str(e))
        return 1

    summary: dict[str, Any] = {
        "ts": ts,
        "root_cause_note": root_cause,
        "content": {},
        "index_stats": {},
        "knn": {},
        "bm25": {},
    }
    if not args.skip_content:
        for suf in CONTENT_FAIL_SUFFIXES:
            summary["content"][suf] = diagnose_content(old_es, new_es, suf, log)
    for suf in EXTRA_STATS_SUFFIXES:
        summary["index_stats"][suf] = diagnose_index_stats(old_es, new_es, suf, log)
    if not args.skip_knn:
        summary["knn"] = diagnose_knn_hymns(old_es, new_es, log)
    if not args.skip_bm25:
        for suf in BM25_FAIL_SUFFIXES:
            summary["bm25"][suf] = diagnose_bm25(old_es, new_es, suf, queries, log)

    base = Path(args.report_base) if args.report_base else (DEFAULT_LOG_DIR / f"qa4_verify_diag_{ts}")
    write_reports(base, summary, log)
    return 0


if __name__ == "__main__":
    sys.exit(main())
