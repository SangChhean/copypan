# -*- coding: utf-8 -*-
"""阶段 2/3 补丁三：在线检查 4b / 6b / 8 / 9 / 10 / 11（只读摘要；详情进 JSON）。"""

from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any, Optional

FIXED_QUESTION = "什么是神的爱？"  # 与检查 7 相同；控制台不打印


def _diag(pass_: bool = True) -> dict:
    return {"pass": pass_, "diagnostic": True}


def check_map_note_full(es, bible) -> dict:
    """检查 4b：全部可抽取 mid；原始 v2.1 vs 包装层；失败分类（上限 200 条入 JSON）。"""
    from retrieval.config import actual_index
    from retrieval.dedupe import map_note_key
    from scripture import vendor_get_vers_v21 as v21
    from scripture.normalize import build_validator, parse_refs, preprocess_ref_text
    from tools.verify_stage2_live import _scroll_map_note_source_zh, extract_map_note_ref

    all_sz = _scroll_map_note_source_zh(es)
    pairs: list[tuple[str, str]] = []
    for sz in all_sz:
        mid = extract_map_note_ref(sz)
        if mid:
            pairs.append((sz, mid))

    validate = build_validator(bible, psalm_title=True)

    def raw_ok(mid: str) -> bool:
        p = v21.VerseParser(validate=validate)
        p.start_paragraph()
        for g in p.parse_text(mid) or []:
            if any(part.strip() for part in (g.get("verses") or "").split("，")):
                return True
        return False

    v_ok = w_ok = 0
    fails: list[dict[str, Any]] = []
    buckets = {"含〇": 0, "其它异常数字写法": 0, "其它": 0}
    for sz, mid in pairs:
        ro = raw_ok(mid)
        # 包装层：含预处理
        wo = map_note_key(sz, bible=bible) is not None
        # 也统计「仅预处理后 mid」是否能 parse_refs
        if ro:
            v_ok += 1
        if wo:
            w_ok += 1
        if not ro or not wo:
            cat = "其它"
            if "〇" in (sz or "") or "〇" in mid:
                cat = "含〇"
            elif re.search(r"[零○Oｏ]", sz or ""):
                cat = "其它异常数字写法"
            buckets[cat] = buckets.get(cat, 0) + 1
            if len(fails) < 200:
                fails.append(
                    {
                        "source_zh": sz,
                        "mid": mid,
                        "raw_v21_ok": ro,
                        "wrapper_ok": wo,
                        "category": cat,
                        "preprocessed_mid": preprocess_ref_text(mid),
                    }
                )

    print(
        f"检查4b map_note 全量可抽取 {len(pairs)}：原始v2.1 成功 {v_ok} 失败 {len(pairs)-v_ok}；"
        f"包装层成功 {w_ok} 失败 {len(pairs)-w_ok}；分类 {buckets}"
    )
    return {
        "diagnostic": True,
        "pass": True,
        "extractable_n": len(pairs),
        "raw_v21_ok": v_ok,
        "raw_v21_fail": len(pairs) - v_ok,
        "wrapper_ok": w_ok,
        "wrapper_fail": len(pairs) - w_ok,
        "fail_categories": buckets,
        "fail_samples": fails,
    }


def check_vectors_extra(es, settings) -> dict:
    from core.embedding_client import EmbeddingClient, cosine
    from retrieval.config import actual_index, index_cfg

    cli = EmbeddingClient(settings.embed_base_url, settings.embed_api_key, settings.embed_model)
    out: dict[str, Any] = {**_diag(True)}
    for lg in ("outline_feasts", "text_life", "text_cwwn", "text_others", "map_note"):
        icfg = index_cfg(lg)
        vf = icfg.get("vector_field")
        tf = icfg.get("text_field") or "text"
        resp = es.search(actual_index(lg), {"size": 5, "query": {"match_all": {}}, "_source": [tf, vf]})
        docs = [h.get("_source") or {} for h in resp["hits"]["hits"]]
        texts = [str(d.get(tf) or "") for d in docs]
        vecs = asyncio.run(cli.embed(texts)) if texts else []
        scores = [round(cosine(v, d.get(vf) or []), 6) for v, d in zip(vecs, docs)]
        mn = min(scores) if scores else None
        avg = (sum(scores) / len(scores)) if scores else None
        print(f"检查6b {lg}：min={mn} avg={avg} n={len(scores)}")
        out[lg] = {"min": mn, "avg": avg, "n": len(scores)}
    return out


def _resolve_source_vs_es_json(args) -> Optional[Path]:
    path = getattr(args, "source_vs_es_json", None) or (os.environ.get("QA4_SOURCE_VS_ES_JSON") or "").strip()
    if not path:
        return None
    p = Path(path)
    return p if p.is_file() else None


def _load_source_vs_es_report(args) -> Optional[dict[str, Any]]:
    p = _resolve_source_vs_es_json(args)
    if p is None:
        raw = getattr(args, "source_vs_es_json", None) or (os.environ.get("QA4_SOURCE_VS_ES_JSON") or "").strip()
        if raw:
            print(f"检查8：source-vs-es-json 不存在：{raw}")
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def es_existing_chunk_ids(es, index: str, chunk_ids: list[str], *, batch_size: int = 1000) -> set[str]:
    """按 chunk_id 精确存在性查询（ids 查询分批，每批 ≤1000）。不用 message_key / book_title。"""
    found: set[str] = set()
    ids = [str(x) for x in chunk_ids if x]
    bs = max(1, min(int(batch_size), 1000))
    for i in range(0, len(ids), bs):
        batch = ids[i : i + bs]
        body = {
            "size": len(batch),
            "query": {"ids": {"values": batch}},
            "_source": ["chunk_id"],
        }
        resp = es.search(index, body)
        for h in (resp.get("hits") or {}).get("hits") or []:
            src = h.get("_source") or {}
            cid = src.get("chunk_id") or h.get("_id")
            if cid:
                found.add(str(cid))
    return found


# 检查 8 依赖的文字类索引：from_source 分支 sources 字典的四个键
# （life 必取样；cwwl/cwwn 取样；others 同属检查 8 源集合，报告模式亦须齐全）
CHECK8_REQUIRED_INDICES = ("text_life", "text_cwwl", "text_cwwn", "text_others")


def check_text_source_vs_es(es, settings, args) -> dict:
    """检查 8：样例组 chunk_id 存在性 vs 源（或全量比对 JSON）。

    样例组定义（源侧）：
    - text_life：固定 message_key（如 life_49-1）下全部 chunk_id
    - text_cwwl / text_cwwn：按 message_key 分组（如 cwwl_1994-1997-2#1）；
      注意同一 message_key 可跨多个 book_title（message_number 常同为 1）
    - top3 册：volume 前缀（边界：…-2 不吃 …-20）

    ES 侧：只用源 id 清单做 ids 查询/存在性比对，禁止 book_title+message_number 近似。

    若提供 --source-vs-es-json：要求 CHECK8_REQUIRED_INDICES 均有成功比对；
    缺/失败/跳过 → 整体「跳过」（非 PASS）；有缺 id → FAIL。不重读源。
    未提供时才读源 jsonl。FAIL 如实，不改成诊断。
    """
    from collections import Counter

    from retrieval.config import actual_index
    from retrieval.text_source import chunk_ids_for_message, env_or_default, iter_chunk_rows, resolve_jsonl_paths

    qa4 = Path(__file__).resolve().parents[2]
    report = _load_source_vs_es_report(args)
    out: dict[str, Any] = {
        "samples": {},
        "pass": True,
        "top3_from_report": [],
        "mode": "from_report" if report else "from_source",
        "required_indices": list(CHECK8_REQUIRED_INDICES),
        "sample_group_def": {
            "life": "message_key 精确匹配（life_*）",
            "cwwl_cwwn": "message_key 精确匹配；可跨多个 book_title",
            "top_volume": "chunk_id 册前缀，边界 rest[0] in '-#'",
            "es": "ids 查询按 chunk_id 存在性，每批≤1000",
        },
    }

    life_samples = [
        ("以弗所书生命读经", "life_49-1"),
        ("以斯帖记生命读经", "life_17-1"),
        ("罗马书生命读经", "life_45-1"),
        ("约翰福音生命读经", "life_43-1"),
    ]

    def record(key: str, src: set[str], got: set[str], **extra: Any) -> None:
        missing = sorted(src - got)
        # ids 存在性查询不会产生「源外 extra」；若 got 超出 src 仍如实列出
        extra_ids = sorted(got - src)
        equal = not missing and not extra_ids and bool(src)
        print(
            f"检查8 {key}：源={len(src)} ES存在={len(got & src)} equal={equal} "
            f"missing={len(missing)} extra={len(extra_ids)}"
        )
        out["samples"][key] = {
            "source_n": len(src),
            "es_n": len(got & src),
            "equal": equal,
            "missing_chunk_ids": missing[:50],
            "extra_chunk_ids": extra_ids[:50],
            **extra,
        }
        if missing or extra_ids or not src:
            out["pass"] = False

    if report is not None:
        print("检查8：使用 --source-vs-es-json，不重读源")
        indices = report.get("indices") or {}
        skip_reasons: list[str] = []
        for lg in CHECK8_REQUIRED_INDICES:
            info = indices.get(lg)
            if info is None:
                msg = f"{lg}:报告中缺失"
                print(f"检查8 {lg}：报告中缺失，无法判定")
                skip_reasons.append(msg)
                continue
            if not isinstance(info, dict):
                msg = f"{lg}:报告中缺失"
                print(f"检查8 {lg}：报告中缺失，无法判定")
                skip_reasons.append(msg)
                continue
            if info.get("failed"):
                msg = f"{lg}:报告中失败"
                print(f"检查8 {lg}：报告中失败，无法判定")
                skip_reasons.append(msg)
                continue
            if info.get("skipped"):
                msg = f"{lg}:报告中跳过"
                print(f"检查8 {lg}：报告中跳过，无法判定")
                skip_reasons.append(msg)
                continue
            if "source_n" not in info or "es_n" not in info:
                msg = f"{lg}:报告中缺失"
                print(f"检查8 {lg}：报告中缺失，无法判定")
                skip_reasons.append(msg)
                continue

            miss_n = int(info.get("missing_n") or 0)
            extra_n = int(info.get("extra_n") or 0)
            src_n = int(info.get("source_n") or 0)
            es_n = int(info.get("es_n") or 0)
            equal = miss_n == 0 and extra_n == 0 and src_n > 0
            print(f"检查8 report:{lg}：source={src_n} es={es_n} missing={miss_n} extra={extra_n} equal={equal}")
            miss_ids: list[str] = []
            for vr in info.get("volumes_top_missing") or []:
                miss_ids.extend(vr.get("missing_chunk_ids") or [])
            out["samples"][f"report:{lg}"] = {
                "source_n": src_n,
                "es_n": es_n,
                "equal": equal,
                "missing_n": miss_n,
                "extra_n": extra_n,
                "missing_chunk_ids": miss_ids[:50],
            }
            if not equal:
                out["pass"] = False

        if skip_reasons:
            # 缺完整成功比对 → 跳过（非 PASS）；汇总列出原因
            out.pop("pass", None)
            out["skipped"] = skip_reasons
            out["diagnostic"] = False
            print(f"检查8：报告不完整，跳过判定；原因={skip_reasons}")
            return out

        tops = [
            t
            for t in (report.get("top3_missing_volumes") or [])
            if isinstance(t, dict) and t.get("volume")
        ]
        out["top3_from_report"] = tops
        for t in tops:
            lg = str(t.get("logical") or "")
            vol = str(t.get("volume") or "")
            info = (report.get("indices") or {}).get(lg) or {}
            vol_row = None
            for vr in info.get("volumes_top_missing") or []:
                if vr.get("volume") == vol:
                    vol_row = vr
                    break
            miss_ids = list((vol_row or {}).get("missing_chunk_ids") or [])
            miss_n = int(t.get("missing_n") or (vol_row or {}).get("missing_n") or 0)
            src_n = int(t.get("source_n") or (vol_row or {}).get("source_n") or 0)
            es_n = int(t.get("es_n") or (vol_row or {}).get("es_n") or 0)
            equal = miss_n == 0
            print(
                f"检查8 top-miss {lg} {vol}：源={src_n} ES={es_n} missing={miss_n} equal={equal}（来自报告）"
            )
            out["samples"][f"topmiss:{lg}:{vol}"] = {
                "source_n": src_n,
                "es_n": es_n,
                "equal": equal,
                "report_missing_n": miss_n,
                "report_missing_rate": t.get("missing_rate"),
                "missing_chunk_ids": miss_ids[:50],
                "extra_chunk_ids": [],
            }
            if not equal:
                out["pass"] = False
        out["diagnostic"] = False
        return out

    # —— 无全量报告：读源 + ids 精确查询 ——
    sources = {
        "text_life": resolve_jsonl_paths(
            getattr(args, "source_text_life", None)
            or env_or_default("QA4_SOURCE_TEXT_LIFE", qa4 / "data" / "es_src" / "panai4_text_life")
        ),
        "text_cwwl": resolve_jsonl_paths(
            getattr(args, "source_text_cwwl", None)
            or env_or_default("QA4_SOURCE_TEXT_CWWL", qa4 / "data" / "es_src" / "panai4_text_cwwl")
        ),
        "text_cwwn": resolve_jsonl_paths(
            getattr(args, "source_text_cwwn", None)
            or env_or_default("QA4_SOURCE_TEXT_CWWN", qa4 / "data" / "es_src" / "panai4_text_cwwn")
        ),
        "text_others": resolve_jsonl_paths(
            getattr(args, "source_text_others", None)
            or env_or_default("QA4_SOURCE_TEXT_OTHERS", qa4 / "data" / "es_src" / "panai4_text_others")
        ),
    }
    if not sources["text_life"]:
        print("跳过：检查8 缺少 text_life 源（--source-text-life 或 QA4_SOURCE_TEXT_LIFE / qa4/data/es_src/…）")
        return {"skipped": ["QA4_SOURCE_TEXT_LIFE"], "diagnostic": True}

    print("检查8：未提供 source-vs-es-json，从源 jsonl 取样并以 ids 查询 ES")

    for bt, mk in life_samples:
        src = chunk_ids_for_message(sources["text_life"], message_key=mk)
        got = es_existing_chunk_ids(es, actual_index("text_life"), sorted(src))
        record(f"life:{bt}", src, got, message_key=mk)

    for logical, paths in (("text_cwwl", sources["text_cwwl"]), ("text_cwwn", sources["text_cwwn"])):
        if not paths:
            print(f"检查8 {logical}：跳过（无源）")
            out["samples"][logical] = {"skipped": True}
            continue
        cnt: Counter[str] = Counter()
        for row in iter_chunk_rows(paths):
            mk = str(row.get("message_key") or "")
            if mk:
                cnt[mk] += 1
        for mk, _ in cnt.most_common(2):
            src = chunk_ids_for_message(paths, message_key=mk)
            got = es_existing_chunk_ids(es, actual_index(logical), sorted(src))
            record(f"{logical}:{mk}", src, got, message_key=mk)

    out["diagnostic"] = False
    return out



def check_filters_soft(es, settings) -> dict:
    """检查 9：作者/年代硬过滤、冲突、软优先、放宽。"""
    from core.embedding_client import EmbeddingClient
    from core.rerank_client import RerankClient
    from lookups.year_table import YearTable
    from retrieval.service import RetrievalService
    from retrieval.types import SubQuestionSpec

    svc = RetrievalService(
        es,
        EmbeddingClient(settings.embed_base_url, settings.embed_api_key, settings.embed_model),
        RerankClient(settings.rerank_base_url, settings.rerank_api_key, settings.rerank_model),
        year_table=YearTable.from_lookup_dir(settings.lookup_dir),
    )
    out: dict[str, Any] = {"items": {}, "pass": True}

    def run(label: str, spec: SubQuestionSpec) -> dict:
        r = asyncio.run(svc.retrieve(spec))
        by_ix = dict(r.coverage.get("kept_by_index") or {})
        idxs = [p.index for p in r.passages]
        return {
            "none_flag": r.none_flag,
            "kept": len(r.passages),
            "kept_by_index": by_ix,
            "year_range_covered": r.year_range_covered,
            "indices": idxs,
        }

    # 1 倪
    a = run("ni", SubQuestionSpec(query=FIXED_QUESTION, author="倪柝声", cap=20))
    ok1 = a["none_flag"] is None and a["kept"] > 0 and set(a["kept_by_index"]) <= {"text_cwwn"}
    print(f"检查9 作者倪：PASS={ok1} kept_by_index={a['kept_by_index']}")
    out["items"]["author_ni"] = {**a, "pass": ok1}

    # 2 李
    b = run("li", SubQuestionSpec(query=FIXED_QUESTION, author="李常受", cap=20))
    allowed = {"text_cwwl", "text_life", "text_others"}
    ok2 = b["none_flag"] is None and b["kept"] > 0 and set(b["kept_by_index"]) <= allowed
    print(f"检查9 作者李：PASS={ok2} kept_by_index={b['kept_by_index']}")
    out["items"]["author_li"] = {**b, "pass": ok2}

    # 3 年代
    c = run("year", SubQuestionSpec(query=FIXED_QUESTION, year_range=(1985, 1993), cap=20))
    yt = YearTable.from_lookup_dir(settings.lookup_dir)
    sel = yt.select(1985, 1993)
    titles = set(sel.book_titles)
    cwwl_titles = [p.book_title for p in asyncio.run(svc.retrieve(SubQuestionSpec(query=FIXED_QUESTION, year_range=(1985, 1993), cap=20))).passages if p.index == "text_cwwl"]
    ok3 = c["none_flag"] is None and all(t in titles for t in cwwl_titles)
    print(f"检查9 年代1985–1993：PASS={ok3} covered={c.get('year_range_covered')} cwwl_n={len(cwwl_titles)}")
    out["items"]["year_1985_1993"] = {
        **c,
        "pass": ok3,
        "cwwl_titles_in_table": all(t in titles for t in cwwl_titles),
        "covered_range": c.get("year_range_covered"),
    }

    # 4 冲突
    d1 = run("conflict_ny", SubQuestionSpec(query=FIXED_QUESTION, author="倪柝声", year_range=(1985, 1990)))
    d2 = run("conflict_feast", SubQuestionSpec(query=FIXED_QUESTION, author="李常受", scope_override=["outline_feasts"]))
    ok4 = d1["none_flag"] == "职事信息里没有" and d2["none_flag"] == "职事信息里没有"
    print(f"检查9 冲突：PASS={ok4}")
    out["items"]["conflicts"] = {"ni_year": d1, "feast_author": d2, "pass": ok4}

    # 5 团体实行软优先
    e = run("tuanti", SubQuestionSpec(query=FIXED_QUESTION, qtype="团体实行", cap=20))
    pri_titles = set(yt.select(1985, 1993).book_titles)
    # 重新取 passages 判断优先
    r_e = asyncio.run(svc.retrieve(SubQuestionSpec(query=FIXED_QUESTION, qtype="团体实行", cap=20)))
    n = min(10, len(r_e.passages))
    pri_n = sum(1 for p in r_e.passages[:n] if p.index == "text_cwwl" and p.book_title in pri_titles)
    fill_n = sum(1 for p in r_e.passages if not (p.index == "text_cwwl" and p.book_title in pri_titles))
    print(f"检查9 团体软优先：前{n}优先占比 {pri_n}/{n}；补充段 {fill_n}")
    out["items"]["soft_tuanti"] = {
        "pass": True,
        "diagnostic": True,
        "top_n": n,
        "priority_in_top_n": pri_n,
        "fill_count": fill_n,
        "kept_by_index": e["kept_by_index"],
    }

    # 6 放宽
    normal = asyncio.run(svc.retrieve(SubQuestionSpec(query=FIXED_QUESTION, qtype="团体实行", words=["爱神"], cap=20)))
    relaxed = asyncio.run(
        svc.retrieve(
            SubQuestionSpec(
                query=FIXED_QUESTION, qtype="团体实行", words=["爱神"], original_question=FIXED_QUESTION, relaxed=True, cap=20
            )
        )
    )
    diff = {
        "normal_routes": normal.coverage.get("routes"),
        "relaxed_routes": relaxed.coverage.get("routes"),
        "normal_kept": normal.coverage.get("kept"),
        "relaxed_kept": relaxed.coverage.get("kept"),
    }
    print(f"检查9 放宽：normal_kept={diff['normal_kept']} relaxed_kept={diff['relaxed_kept']}")
    out["items"]["relaxed"] = {**diff, "pass": True, "diagnostic": True}

    out["pass"] = all(v.get("pass", True) for k, v in out["items"].items() if not v.get("diagnostic"))
    return out


def check_e2e_fake_llm_live_retrieval(settings) -> dict:
    """检查 10：TestClient + fake LLM + live retrieval；临时用户库/trace。"""
    miss = [
        n
        for n in (
            "QA4_ES_URL",
            "QA4_ES_PASSWORD",
            "QA4_EMBED_BASE_URL",
            "QA4_EMBED_API_KEY",
            "QA4_RERANK_BASE_URL",
            "QA4_RERANK_API_KEY",
        )
        if not (os.environ.get(n) or "").strip()
    ]
    if miss:
        print(f"跳过：缺少 {', '.join(miss)}")
        return {"skipped": miss}

    import hashlib
    import shutil

    from fastapi.testclient import TestClient

    from core.auth import AuthStore
    from core.es_client import EsClient
    from core.neo4j_client import Neo4jClient
    from core.redis_store import MemoryStore
    from main import create_app
    from pipeline.deps import build_deps

    tmp = tempfile.mkdtemp(prefix="qa4_chk10_")
    data_dir = Path(tmp) / "data"
    data_dir.mkdir()
    try:
        settings2 = settings
        settings2.data_dir = data_dir
        settings2.traces_db_path = data_dir / "qa4_traces.db"
        settings2.llm_mode = "fake"
        settings2.retrieval_mode = "live"
        if not (settings2.jwt_secret or "").strip():
            settings2.jwt_secret = "chk10-secret-not-real"
        if not (settings2.admin_token or "").strip():
            settings2.admin_token = "chk10-admin-not-real"

        store = MemoryStore(prefix="qa4chk10:")
        auth = AuthStore(
            data_dir / "qa4_users.db",
            jwt_secret=settings2.jwt_secret,
            jwt_expire_days=7,
            daily_limit_default=100,
            tz_name=getattr(settings2, "tz_name", "UTC") or "UTC",
            admin_token=settings2.admin_token,
        )
        auth.create_invite("CHK10", max_uses=10)
        es = EsClient(
            settings2.es_url,
            settings2.es_user,
            settings2.es_secret,
            verify=settings2.es_verify,
            index_map=settings2.index_map,
        )
        neo = None
        if (os.environ.get("QA4_NEO4J_URI") or "").strip() and (os.environ.get("QA4_NEO4J_PASSWORD") or "").strip():
            neo = Neo4jClient(settings2.neo4j_uri, settings2.neo4j_user, settings2.neo4j_secret)
        deps = build_deps(settings2, store=store, es=es, neo4j=neo, traces_db=settings2.traces_db_path)
        app = create_app(
            settings2,
            redis_store=store,
            es_client=es,
            neo4j_client=neo,
            auth_store=auth,
            pipeline_deps=deps,
        )
        client = TestClient(app)
        client.post("/api/auth/register", json={"invite_code": "CHK10", "username": "chk10u", "password": "chk10pass1"})
        tok = client.post("/api/auth/login", json={"username": "chk10u", "password": "chk10pass1"}).json()["token"]
        headers = {"Authorization": f"Bearer {tok}"}

        questions = [
            ("simple", "什么是神的爱？"),
            ("split", "【拆】什么是神的爱与爱神？"),
            ("sensitive", "【敏感】什么是神的爱？"),
            ("tuanti", "【团体】如何实行召会生活？"),
        ]
        samples: dict[str, Any] = {}
        for key, q in questions:
            qh = hashlib.sha256(q.encode("utf-8")).hexdigest()[:12]
            t0 = time.perf_counter()
            r = client.post("/api/qa/ask", headers=headers, json={"question": q, "history": []})
            total_ms = int((time.perf_counter() - t0) * 1000)
            body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            # 不落正文：只取结构字段
            cov = body.get("coverage") or body.get("retrieval") or {}
            samples[key] = {
                "question_sha12": qh,
                "question_len": len(q),
                "http_status": r.status_code,
                "total_ms": total_ms,
                "citations_n": len(body.get("citations") or body.get("refs") or []),
                "degraded": body.get("degraded"),
                "cache_hit": body.get("cache_hit"),
                "coverage_kept": (cov.get("kept") if isinstance(cov, dict) else None),
                "traces_count": deps.traces.count(),
            }
            print(
                f"检查10 {key}：status={r.status_code} ms={total_ms} "
                f"citations={samples[key]['citations_n']} traces={samples[key]['traces_count']}"
            )

        calls_before = len(getattr(deps.llm, "calls", []) or [])
        r2 = client.post("/api/qa/ask", headers=headers, json={"question": questions[0][1], "history": []})
        calls_after = len(getattr(deps.llm, "calls", []) or [])
        cache_hit = bool((r2.json() or {}).get("cache_hit")) or calls_after == calls_before
        print(f"检查10 缓存：llm_calls {calls_before}→{calls_after} cache_hit={cache_hit}")
        if neo:
            neo.close()
        return {
            "pass": cache_hit and all(s.get("http_status") == 200 for s in samples.values()),
            "samples": samples,
            "cache_second_simple_ok": cache_hit,
        }
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_devine_and_reverse(neo, settings, bible) -> dict:
    """检查 11：辩理统计 + live DevineProvider + reverse 样例。"""
    from lookups.definitions import DefinitionStore, same_as_map
    from lookups.loader import load_lookups
    from pipeline.deps import DevineProvider, _devine_content_key
    from scripture.reverse import ReverseFinder

    out: dict[str, Any] = {"pass": True}
    rows = neo.truth_points_with_devine()
    n = len(rows)
    raw_set = set()
    strip_set = set()
    for r in rows:
        val = r.get("devine_argument")
        raw_set.add(json.dumps(val, ensure_ascii=False, sort_keys=True) if not isinstance(val, str) else val)
        key, _ = _devine_content_key(val)
        if key:
            strip_set.add(key)
    print(f"检查11a 辩理：Truth_Point 非空 {n}（期望187）；原样去重 {len(raw_set)}；strip去重 {len(strip_set)}（期望72）")
    out["devine_stats"] = {
        "truth_points_with_devine": n,
        "distinct_raw": len(raw_set),
        "distinct_strip": len(strip_set),
        "expect_points": 187,
        "expect_distinct": 72,
    }

    same_as = {}
    try:
        lex = load_lookups(settings.lookup_dir).lexicon
        same_as = same_as_map(lex)
    except Exception:
        pass
    prov = DevineProvider(None, neo4j=neo, same_as=same_as, max_items=2)
    names = [r["name"] for r in rows[:3]]
    fetched = []
    for name in names:
        items = prov.fetch([name])
        fetched.append({"name": name, "n": len(items), "chars": [len(it.get("content") or "") for it in items], "form": [it.get("form") for it in items]})
    print(f"检查11b DevineProvider：{[{'name': x['name'], 'n': x['n'], 'chars': x['chars']} for x in fetched]}")
    out["devine_fetch"] = fetched

    # reverse
    from retrieval.service import make_retrieval_service

    miss_embed = [n for n in ("QA4_EMBED_BASE_URL", "QA4_EMBED_API_KEY") if not (os.environ.get(n) or "").strip()]
    retrieval = None
    if not miss_embed and (os.environ.get("QA4_ES_URL") or "").strip():
        from core.es_client import EsClient

        es = EsClient(settings.es_url, settings.es_user, settings.es_secret, verify=settings.es_verify, index_map=settings.index_map)
        retrieval = make_retrieval_service(settings, es, fake=False)
    defs = DefinitionStore(Path(settings.graph_annotations_dir) / "truth_dictionary_3a3b.json", same_as=same_as)
    rf = ReverseFinder(graph=neo, definitions=defs, retrieval=retrieval, bible=bible)
    terms = ["神的爱", "包罗万有", "因信称义"]
    # 若不在词表则替换
    titles = set(defs.titles()) if defs.available else set()
    used = []
    for t in terms:
        if titles and t not in titles and t not in same_as:
            # 找替代
            alt = next((x for x in ("生命", "召会", "十字架") if x in titles), None)
            used.append(alt or t)
            if alt:
                print(f"检查11c 词「{t}」不在词表，改用「{alt}」")
        else:
            used.append(t)
    rev = {}
    for t in used:
        r = asyncio.run(rf.find(t))
        top = [h["label"] for h in r["hits"][:5]]
        rev[t] = {
            "counts": r["counts"],
            "total": len(r["hits"]),
            "used_bible_vector": r["used_bible_vector"],
            "top5_refs": top,
        }
        if r["used_bible_vector"] and miss_embed:
            pass
        print(f"检查11c reverse {t}：counts={r['counts']} total={len(r['hits'])} vec={r['used_bible_vector']}")
    if miss_embed:
        out["reverse_embed_skipped"] = miss_embed
        print(f"检查11c bible向量：跳过（缺 {', '.join(miss_embed)}）" if any(v.get("used_bible_vector") is False for v in rev.values()) else "")
    out["reverse"] = rev
    out["diagnostic"] = True
    return out
