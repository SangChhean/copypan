# -*- coding: utf-8 -*-
"""阶段 2 在线检查（只读）。由 Srey 设置好环境变量后运行；缺变量就打印「跳过：缺少 XXX」，不报错、不提示输入密码。

检查项：
  1 十个索引映射里 retrieval.json 配置的字段是否真实存在（逐字段 PASS/FAIL；verified=false 单列）
  2 图谱 Scripture.ref 用 parse_refs 的成功数与失败列表（只列 ref）
  3 qa4_bible verse_range（chunk_type=verses）解析：开关关/开的成功与失败数，失败里带 0 的诗篇条数
  4 map_note source_zh：与探测 5 同口径抽样；拆开「原始 v2.1」与「包装层」成功数；失败样例入 JSON
  5 定向取篇样例：每部分诊断字段（不含正文）；节期按篇；扩充生命读经/节期/诗歌重叠号
  5b targeted.scripture 新 kind：whole_book（罗马书+outline）、chapter_range（创1-3）、截断（诗1-12）
  6 向量一致性抽样（需嵌入密钥）：重新嵌入与索引向量的余弦；只报数
  7 端到端检索：固定问题在默认库检索，打印各路取回数、融合数、精排数、保留数与前 5 条书名/篇名/位置

用法：python qa4/backend/tools/verify_stage2_live.py [--out DIR] [--only 1,2,...]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

DEFAULT_OUT = Path(r"G:\PanAI4.0专用\logs\stage2")
FIXED_QUESTION = "什么是神的爱？"
MAP_NOTE_SEED = 20261116
MAP_NOTE_SAMPLE_N = 2000


def _env_present(*names: str) -> list[str]:
    env = getattr(os, "environ")
    return [n for n in names if not (env.get(n) or "").strip()]


def _flatten_props(props: dict[str, Any], prefix: str = "") -> dict[str, dict]:
    out: dict[str, dict] = {}
    for k, v in (props or {}).items():
        name = f"{prefix}{k}"
        out[name] = v
        for sub, sv in (v.get("fields") or {}).items():
            out[f"{name}.{sub}"] = sv
        if v.get("properties"):
            out.update(_flatten_props(v["properties"], name + "."))
    return out


def _pass_fail(ok: bool) -> str:
    return "PASS" if ok else "FAIL"


def extract_map_note_ref(source_zh: str) -> Optional[str]:
    """与探测 5 c_verse_norm.extract_map_note_ref 同规则。"""
    if not source_zh:
        return None
    s = source_zh.strip().strip("（）()")
    parts = re.split(r"[，,]", s)
    if len(parts) < 2:
        return None
    mid = []
    for i, p in enumerate(parts):
        p = p.strip()
        if i == 0 and ("恢复本" in p or "圣经" in p):
            continue
        if re.match(r"^注\s*\d+", p):
            continue
        if p:
            mid.append(p)
    if not mid:
        return None
    return mid[0]


def _clip_orders(orders: list[int], limit: int = 60) -> Any:
    if len(orders) <= limit:
        return orders
    return {"head": orders[:5], "tail": orders[-5:], "n": len(orders)}


def check_mappings(es, rcfg) -> dict:
    from retrieval.config import actual_index

    res: dict[str, Any] = {"indices": {}, "unverified": [], "pass": True}
    for lg, icfg in (rcfg.get("indices") or {}).items():
        idx = actual_index(lg)
        try:
            m = es.get_mapping(idx)
        except Exception as e:
            res["indices"][lg] = {"error": type(e).__name__}
            res["pass"] = False
            print(f"FAIL {lg}: 映射读取失败 {type(e).__name__}")
            continue
        body = m.get(idx) or next(iter(m.values()), {})
        props = _flatten_props(((body.get("mappings") or {}).get("properties")) or {})
        rows = []
        wanted = [("text_field", icfg.get("text_field"), True), ("vector_field", icfg.get("vector_field"), True)]
        for grp in ("fields", "filters"):
            for key, meta in (icfg.get(grp) or {}).items():
                wanted.append((f"{grp}.{key}", meta.get("name"), meta.get("verified", True)))
        for label, fname, verified in wanted:
            if not fname:
                continue
            ok = fname in props
            if fname and label == "vector_field" and ok:
                t = props[fname].get("type")
                dims = props[fname].get("dims")
                ok = t == "dense_vector" and dims == 1024
            rows.append({"field": label, "name": fname, "ok": ok, "verified_in_config": verified})
            print(f"{_pass_fail(ok)} {lg}.{label} = {fname}" + ("" if verified else "  (verified=false)"))
            if not ok:
                res["pass"] = False
            if verified is False:
                res["unverified"].append(f"{lg}.{label}={fname}:{_pass_fail(ok)}")
        res["indices"][lg] = rows
    return res


def check_graph_refs(neo, bible) -> dict:
    from scripture.normalize import parse_refs

    refs = neo.scripture_refs()
    ok = 0
    fails: list[str] = []
    for r in refs:
        if parse_refs(r, bible=bible):
            ok += 1
        else:
            fails.append(r)
    print(f"图谱 Scripture.ref：总 {len(refs)}，成功 {ok}，失败 {len(fails)}")
    for f in fails:
        print(f"  失败 ref：{f}")
    return {"total": len(refs), "ok": ok, "fail_refs": fails, "pass": len(fails) == 0}


def check_bible_verse_range(es, bible) -> dict:
    from retrieval.config import actual_index
    from scripture.normalize import parse_refs

    body = {
        "size": 10000,
        "query": {"bool": {"filter": [{"term": {"chunk_type": "verses"}}]}},
        "_source": ["book_title", "verse_range"],
    }
    resp = es.search(actual_index("bible"), body)
    rows = [h.get("_source") or {} for h in resp["hits"]["hits"]]
    off_ok = on_ok = 0
    off_fail_psalm0 = 0
    off_fail = 0
    for s in rows:
        t = f"{s.get('book_title') or ''}{s.get('verse_range') or ''}"
        a = parse_refs(t, bible=bible, psalm_title=False)
        b = parse_refs(t, bible=bible, psalm_title=True)
        off_ok += bool(a)
        on_ok += bool(b)
        if not a:
            off_fail += 1
            if (s.get("book_title") or "").startswith("诗") and re.search(
                r"[一二三四五六七八九十百]0", s.get("verse_range") or ""
            ):
                off_fail_psalm0 += 1
    print(
        f"qa4_bible verses：{len(rows)} 条；开关关：成功 {off_ok} 失败 {off_fail}"
        f"（其中诗篇带0 {off_fail_psalm0}，期望 116）；开关开：成功 {on_ok}"
    )
    passed = on_ok == len(rows) and off_fail_psalm0 == 116
    return {
        "n": len(rows),
        "off_ok": off_ok,
        "off_fail": off_fail,
        "off_fail_psalm0": off_fail_psalm0,
        "on_ok": on_ok,
        "pass": passed,
    }


def _scroll_map_note_source_zh(es, max_docs: int = 50000) -> list[str]:
    """收集 map_note 的 source_zh（只读；上限防止过久）。"""
    from retrieval.config import actual_index

    idx = actual_index("map_note")
    out: list[str] = []
    body = {"size": 1000, "query": {"match_all": {}}, "_source": ["source_zh"], "sort": ["_doc"]}
    try:
        resp = es.search(idx, body, scroll="2m")
    except TypeError:
        resp = es.search(idx, {"size": min(max_docs, 10000), "query": {"match_all": {}}, "_source": ["source_zh"]})
        for h in resp["hits"]["hits"]:
            out.append((h.get("_source") or {}).get("source_zh") or "")
        return out

    sid = resp.get("_scroll_id")
    while True:
        hits = resp["hits"]["hits"]
        if not hits:
            break
        for h in hits:
            out.append((h.get("_source") or {}).get("source_zh") or "")
            if len(out) >= max_docs:
                break
        if len(out) >= max_docs or not sid:
            break
        if not hasattr(es, "scroll"):
            break
        resp = es.scroll(scroll_id=sid, scroll="2m")
        sid = resp.get("_scroll_id") or sid
    if sid and hasattr(es, "clear_scroll"):
        es.clear_scroll(scroll_id=sid)
    return out


def _raw_v21_ok(mid: str, bible) -> bool:
    """探测 5 口径：对 mid 跑 vendor VerseParser（带 bible 校验）。"""
    from scripture import vendor_get_vers_v21 as v21
    from scripture.normalize import build_validator

    validate = build_validator(bible, psalm_title=True)
    p = v21.VerseParser(validate=validate)
    p.start_paragraph()
    groups = p.parse_text(mid)
    for g in groups or []:
        vs = g.get("verses") or ""
        if any(part.strip() for part in vs.split("，")):
            return True
    return False


def check_map_note(es, bible) -> dict:
    """抽样对齐探测 5：先滤可抽取 mid，再 Random(20261116).sample(2000)；拆开 v2.1 与包装层。"""
    from retrieval.dedupe import map_note_key
    from scripture.normalize import parse_refs

    print(
        "检查 4 抽样说明：探测 5 从 jsonl 可抽取 mid 集合 Random(20261116) 抽 2000；"
        "本检查从 ES 收集 source_zh 后用同一 extract + 同一种子抽样。"
        "母体仍可能因 ES vs jsonl 全集差异而不完全相同。"
    )

    all_sz = _scroll_map_note_source_zh(es)
    extractable: list[tuple[str, str]] = []
    for sz in all_sz:
        mid = extract_map_note_ref(sz)
        if mid:
            extractable.append((sz, mid))

    rng = random.Random(MAP_NOTE_SEED)
    if len(extractable) > MAP_NOTE_SAMPLE_N:
        sample = rng.sample(extractable, MAP_NOTE_SAMPLE_N)
    else:
        sample = list(extractable)

    v21_ok_n = 0
    wrap_ok_n = 0
    fails: list[dict[str, Any]] = []
    wrap_extra_requirements = [
        "map_note_key 须 parse_refs(剥注后的 body) 成功",
        "注号可缺省为 0（不强制有「注N」）",
        "body 常仍含「恢复本圣经」前缀（与探测 5 的 mid 不同）",
    ]

    for source_zh, mid in sample:
        v_ok = _raw_v21_ok(mid, bible)
        w_key = map_note_key(source_zh, bible=bible)
        w_ok = w_key is not None
        if v_ok:
            v21_ok_n += 1
        if w_ok:
            wrap_ok_n += 1
        if not w_ok or not v_ok:
            reason = []
            if not v_ok:
                reason.append("raw_v21_mid_failed")
            if not w_ok:
                reason.append("wrapper_map_note_key_none")
                body = re.sub(r"注\s*\d+", "", (source_zh or "").strip().strip("（）()"))
                if not parse_refs(body, bible=bible, validate=True):
                    reason.append("wrapper_body_parse_refs_failed")
                else:
                    reason.append("wrapper_body_parses_but_key_none")
            if len(fails) < 30:
                fails.append(
                    {
                        "source_zh": source_zh,
                        "mid": mid,
                        "raw_v21_ok": v_ok,
                        "wrapper_ok": w_ok,
                        "wrapper_fail_reasons": reason,
                    }
                )

    n = len(sample)
    print(
        f"map_note：ES 收集 {len(all_sz)} 条 source_zh；可抽取 mid {len(extractable)}；"
        f"种子 {MAP_NOTE_SEED} 抽样 {n}；原始 v2.1(mid) 成功 {v21_ok_n}；包装层成功 {wrap_ok_n}"
        f"（探测 5 为 1999/2000，母体为 jsonl 可抽取集）"
    )
    print(f"包装层额外条件：{'; '.join(wrap_extra_requirements)}")
    if fails:
        print(f"失败样例（最多 30）已写入 JSON；控制台不打印正文。条数={len(fails)}")

    return {
        "es_source_zh_collected": len(all_sz),
        "extractable_n": len(extractable),
        "sample_n": n,
        "seed": MAP_NOTE_SEED,
        "raw_v21_ok": v21_ok_n,
        "wrapper_ok": wrap_ok_n,
        "wrapper_extra_requirements": wrap_extra_requirements,
        "sampling_note": (
            "与探测 5 一致：extract_map_note_ref 后 Random(20261116).sample(2000)；"
            "差异：母体为 ES 当前索引而非 kg-rag_map_note.jsonl。"
        ),
        "fail_samples": fails,
        "pass": n > 0,
    }


def _part_diag(part: dict[str, Any], *, chunk_ids: Optional[list[str]] = None) -> dict[str, Any]:
    orders = list(part.get("orders") or [])
    out = {
        "fetched": part.get("fetched"),
        "hits_total": part.get("hits_total"),
        "expected_total": part.get("expected_total"),
        "orders": _clip_orders(orders),
        "orders_base": part.get("orders_base"),
        "missing_orders": part.get("missing_orders"),
        "extra_orders": part.get("extra_orders"),
        "duplicate_orders": part.get("duplicate_orders"),
        "orders_contiguous": part.get("orders_contiguous"),
        "chunk_totals": part.get("chunk_totals") or part.get("chunk_total_values"),
        "status": part.get("status"),
    }
    if chunk_ids is not None:
        out["chunk_id_head3"] = chunk_ids[:3]
        out["chunk_id_tail3"] = chunk_ids[-3:] if len(chunk_ids) >= 3 else chunk_ids
    return out


def check_targeted(es, bible, lookup_dir: Path) -> dict:
    from retrieval.targeted import INCOMPLETE, NOT_FOUND, TargetedFetcher

    feasts = json.loads((lookup_dir / "feasts.json").read_text(encoding="utf-8"))
    life = json.loads((lookup_dir / "life_books.json").read_text(encoding="utf-8"))
    hymn_series = {}
    hs_path = lookup_dir / "hymn_series.json"
    if hs_path.is_file():
        hymn_series = json.loads(hs_path.read_text(encoding="utf-8"))
    overlap_nums = list(hymn_series.get("daben_buchong_overlap_numbers") or [1])
    overlap_num = int(overlap_nums[0]) if overlap_nums else 1

    f = TargetedFetcher(es, bible=bible, feasts=feasts)
    out: dict[str, Any] = {"samples": {}, "pass": True}

    def pick_feasts() -> list[dict]:
        """春季长老 + 国殇（同年多场）+ 全时间 1 场 + 再补 1 场。"""
        by_name = {x["name"]: x for x in feasts}
        want_names = [
            "1997年春季长老训练",
            "1997年国殇节特会",
            "1997年安那翰全时间训练",
        ]
        chosen = []
        for n in want_names:
            if n in by_name:
                chosen.append(by_name[n])
        # 再加一场不同年全时间或表中下一场
        for x in feasts:
            if x in chosen:
                continue
            if "全时间" in str(x.get("name") or "") and x.get("year") != 1997:
                chosen.append(x)
                break
        if len(chosen) < 4:
            for x in feasts:
                if x not in chosen:
                    chosen.append(x)
                if len(chosen) >= 4:
                    break
        return chosen[:4]

    def pick_life() -> list[dict]:
        titles = [x["book_title"] for x in life]
        prefer = ["以弗所书生命读经", "以斯帖记生命读经", "罗马书生命读经", "约翰福音生命读经"]
        chosen = []
        for t in prefer:
            for b in life:
                if b["book_title"] == t:
                    chosen.append(b)
                    break
        for b in life:
            if b not in chosen:
                chosen.append(b)
            if len(chosen) >= 4:
                break
        return chosen[:4]

    async def run():
        for b in pick_life():
            r = await f.life_study(b["book_title"], 1)
            entry: dict[str, Any] = {"status": r.status, "parts": {}}
            for ix in ("outline_12490", "text_life"):
                part = (r.meta.get("parts") or {}).get(ix) or {}
                cids = []
                if ix == "text_life":
                    cids = [blk.get("id") for blk in r.blocks if blk.get("index") == ix]
                entry["parts"][ix] = _part_diag(part, chunk_ids=cids if ix == "text_life" else None)
                print(
                    f"生命读经 {b['book_title']} 第1篇 {ix}：fetched={part.get('fetched')} "
                    f"expected={part.get('expected_total')} status={part.get('status')} "
                    f"missing={part.get('missing_orders')} base={part.get('orders_base')} "
                    f"整体={r.status}"
                )
            out["samples"][f"life:{b['book_title']}"] = entry
            if r.status == INCOMPLETE:
                out["pass"] = False

        for ft in pick_feasts():
            r = await f.feast(int(ft["year"]), str(ft["month_code"]))
            msgs = {}
            for mk, mi in (r.meta.get("messages") or {}).items():
                msgs[mk] = _part_diag(mi)
            entry = {
                "status": r.status,
                "n_blocks": len(r.blocks),
                "messages_fetched": r.meta.get("messages_fetched"),
                "hits_total": r.meta.get("hits_total"),
                "expected_message_count": r.meta.get("expected_message_count"),
                "messages": msgs,
            }
            print(
                f"节期 {ft['name']}：blocks={len(r.blocks)} messages={r.meta.get('messages_fetched')} "
                f"status={r.status}"
            )
            for mk, mi in msgs.items():
                print(
                    f"  篇{mk}: fetched={mi.get('fetched')} expected={mi.get('expected_total')} "
                    f"status={mi.get('status')} missing={mi.get('missing_orders')}"
                )
            out["samples"][f"feast:{ft['name']}"] = entry
            if r.status == INCOMPLETE:
                out["pass"] = False

        for num in (1, 2):
            r = await f.hymn(num)
            print(f"诗歌第{num}首（默认大本）：status={r.status} 块数 {len(r.blocks)} series={r.meta.get('series')}")
            out["samples"][f"hymn:{num}"] = {"status": r.status, "n": len(r.blocks), "series": r.meta.get("series")}
            if r.status == NOT_FOUND:
                out["pass"] = False

        # 重叠号：补充本
        r = await f.hymn(overlap_num, series="补充本诗歌")
        print(
            f"诗歌补充本第{overlap_num}首（与大本重叠号）：status={r.status} "
            f"series={r.meta.get('series')} 块数 {len(r.blocks)}"
        )
        out["samples"][f"hymn:补充本:{overlap_num}"] = {
            "status": r.status,
            "n": len(r.blocks),
            "series": r.meta.get("series"),
            "overlap_number": overlap_num,
        }
        # 对照大本同号
        rd = await f.hymn(overlap_num)
        out["samples"][f"hymn:大本:{overlap_num}"] = {
            "status": rd.status,
            "n": len(rd.blocks),
            "series": rd.meta.get("series"),
        }
        if r.status == NOT_FOUND or rd.status == NOT_FOUND:
            out["pass"] = False
        if r.status == "ok" and rd.status == "ok" and r.meta.get("series") == rd.meta.get("series"):
            print("FAIL 重叠号未能靠 series 区分")
            out["pass"] = False

    asyncio.run(run())
    return out


def check_scripture_kinds(es, bible) -> dict:
    """targeted.scripture：whole_book / chapter_range / 截断（不含经文正文）。"""
    from retrieval.config import actual_index
    from retrieval.targeted import OK, TargetedFetcher
    from scripture.normalize import KIND_BOOK, KIND_CHAPTER_RANGE, Ref, parse_refs

    f = TargetedFetcher(es, bible=bible)
    out: dict[str, Any] = {"samples": {}, "pass": True}
    bible_idx = actual_index("bible")
    idx_exists = None
    try:
        if hasattr(es, "index_exists"):
            idx_exists = bool(es.index_exists(bible_idx))
        elif hasattr(es, "indices"):
            idx_exists = bool(es.indices.exists(index=bible_idx))
    except Exception:
        idx_exists = None
    print(f"bible 逻辑索引 → {bible_idx} exists={idx_exists}")

    async def run():
        # whole_book：罗马书
        refs_rom = parse_refs("罗马书", bible=bible, validate=True)
        r = await f.scripture(refs_rom)
        overview = [b for b in r.blocks if b.get("unit") == "book_overview"]
        outline = [b for b in r.blocks if b.get("chunk_type") == "book_outline"]
        entry = {
            "status": r.status,
            "kind": r.meta.get("kind"),
            "chapter_count": r.meta.get("chapter_count"),
            "verse_count": r.meta.get("verse_count"),
            "has_outline": r.meta.get("has_outline"),
            "n_overview": len(overview),
            "n_outline": len(outline),
            "bible_index": bible_idx,
            "bible_index_exists": idx_exists,
            "block_fields": sorted({k for b in r.blocks for k in b.keys()}),
        }
        print(
            f"whole_book 罗马书：status={r.status} kind={r.meta.get('kind')} "
            f"chapters={r.meta.get('chapter_count')} verses={r.meta.get('verse_count')} "
            f"has_outline={r.meta.get('has_outline')} outline_blocks={len(outline)}"
        )
        out["samples"]["whole_book:罗马书"] = entry
        if r.status != OK or r.meta.get("kind") != KIND_BOOK or r.meta.get("chapter_count") != 16:
            out["pass"] = False
        if not r.meta.get("has_outline"):
            print("FAIL whole_book 未带 book_outline（has_outline!=true）")
            out["pass"] = False

        # chapter_range：创1-3
        refs_gen = parse_refs("创一至三章", bible=bible, validate=True)
        r2 = await f.scripture(refs_gen)
        chapters = sorted({int(b["order"]) // 1000 for b in r2.blocks})
        orders = [b["order"] for b in r2.blocks]
        entry2 = {
            "status": r2.status,
            "kind": r2.meta.get("kind"),
            "requested_chapters": r2.meta.get("requested_chapters"),
            "returned_chapters": r2.meta.get("returned_chapters"),
            "truncated": r2.meta.get("truncated"),
            "chapters": chapters,
            "n_blocks": len(r2.blocks),
            "orders_sorted": orders == sorted(orders),
        }
        print(
            f"chapter_range 创1-3：status={r2.status} chapters={chapters} "
            f"requested={r2.meta.get('requested_chapters')} returned={r2.meta.get('returned_chapters')} "
            f"truncated={r2.meta.get('truncated')} orders_sorted={entry2['orders_sorted']}"
        )
        out["samples"]["chapter_range:创1-3"] = entry2
        if (
            r2.status != OK
            or r2.meta.get("kind") != KIND_CHAPTER_RANGE
            or chapters != [1, 2, 3]
            or r2.meta.get("returned_chapters") != 3
            or not entry2["orders_sorted"]
        ):
            out["pass"] = False

        # 诗1-12 → 截断 10 章
        ref_ps = Ref(
            book="诗",
            book_no=19,
            chapter=1,
            v_start=0,
            v_end=0,
            kind=KIND_CHAPTER_RANGE,
            chapter_end=12,
            raw="诗1-12",
        )
        r3 = await f.scripture([ref_ps])
        chapters3 = sorted({int(b["order"]) // 1000 for b in r3.blocks})
        entry3 = {
            "status": r3.status,
            "kind": r3.meta.get("kind"),
            "requested_chapters": r3.meta.get("requested_chapters"),
            "returned_chapters": r3.meta.get("returned_chapters"),
            "truncated": bool(r3.meta.get("truncated")),
            "chapters": chapters3,
            "n_blocks": len(r3.blocks),
        }
        print(
            f"chapter_range 诗1-12：status={r3.status} chapters={chapters3} "
            f"requested={r3.meta.get('requested_chapters')} returned={r3.meta.get('returned_chapters')} "
            f"truncated={r3.meta.get('truncated')}"
        )
        out["samples"]["chapter_range:诗1-12"] = entry3
        if (
            r3.status != OK
            or not r3.meta.get("truncated")
            or r3.meta.get("requested_chapters") != 12
            or r3.meta.get("returned_chapters") != 10
            or chapters3 != list(range(1, 11))
        ):
            out["pass"] = False

    asyncio.run(run())
    return out


def check_vectors(es, settings) -> dict:
    from core.embedding_client import EmbeddingClient, cosine
    from retrieval.config import actual_index, index_cfg

    cli = EmbeddingClient(settings.embed_base_url, settings.embed_api_key, settings.embed_model)
    out: dict[str, Any] = {"pass": True}
    for lg in ("outline_12490", "text_cwwl", "bible", "hymns"):
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
        print(f"{lg} 向量一致性：{scores} min={mn} avg={avg}")
        out[lg] = {"scores": scores, "min": mn, "avg": avg}
        if not scores:
            out["pass"] = False
    return out


def check_e2e(es, settings) -> dict:
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
    res = asyncio.run(svc.retrieve(SubQuestionSpec(query=FIXED_QUESTION)))
    cov = res.coverage
    print(f"端到端：各路取回 {json.dumps(cov.get('routes'), ensure_ascii=False)}")
    print(f"融合后 {cov.get('fused')}；精排后 {cov.get('reranked')}；最终保留 {cov.get('kept')}；degraded={res.degraded}")
    top = [{"book_title": p.book_title, "message_title": p.message_title, "location": p.location} for p in res.passages[:5]]
    for t in top:
        print(f"  {t['book_title']} / {t['message_title']} / {json.dumps(t['location'], ensure_ascii=False)}")
    return {"coverage": cov, "top5": top, "degraded": res.degraded, "pass": True}


def _item_state(v: dict[str, Any]) -> str:
    if "skipped" in v:
        return "跳过"
    if v.get("error"):
        return "FAIL"
    if v.get("diagnostic"):
        return "诊断"
    if v.get("pass") is False:
        return "FAIL"
    if v.get("pass") is True:
        return "PASS"
    return "PASS"


def _sort_key(k: str):
    m = re.match(r"^(\d+)([a-z]*)$", str(k))
    if m:
        return (int(m.group(1)), m.group(2) or "")
    return (999, str(k))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument(
        "--only",
        default="1,2,3,4,4b,5,5b,6,6b,7,8,9,10,11",
        help="逗号分隔检查编号，如 4b,5b,8,9",
    )
    ap.add_argument("--source-text-life", type=Path, default=None)
    ap.add_argument("--source-text-cwwl", type=Path, default=None)
    ap.add_argument("--source-text-cwwn", type=Path, default=None)
    ap.add_argument("--source-text-others", type=Path, default=None)
    ap.add_argument(
        "--source-vs-es-json",
        type=Path,
        default=None,
        help=(
            "check_source_vs_es 结果 JSON；检查8据此判定文字类索引"
            "（text_life/cwwl/cwwn/others 须齐全且成功比对；有缺 id 则 FAIL；"
            "报告缺/失败/跳过则本检查跳过；有 top3 缺失册则一并列出）"
        ),
    )
    args = ap.parse_args(argv)
    only = {s.strip() for s in args.only.split(",") if s.strip()}

    from config import get_settings
    from retrieval.config import retrieval_cfg
    from tools import stage2_live_patch3 as p3

    settings = get_settings(require_runtime=False)
    report: dict[str, Any] = {"started_at": datetime.now().isoformat(timespec="seconds"), "items": {}}

    es = neo = bible = None
    # ES 地址已设但缺密码：依赖 ES 的检查一律跳过，不发起匿名请求
    miss_es = _env_present("QA4_ES_URL", "QA4_ES_PASSWORD")
    if not miss_es:
        from core.es_client import EsClient

        es = EsClient(
            settings.es_url, settings.es_user, settings.es_secret, verify=settings.es_verify, index_map=settings.index_map
        )
    miss_neo = _env_present("QA4_NEO4J_URI", "QA4_NEO4J_PASSWORD")
    if not miss_neo:
        from core.neo4j_client import Neo4jClient

        neo = Neo4jClient(settings.neo4j_uri, settings.neo4j_user, settings.neo4j_secret)
    try:
        from scripture.bible_text import BibleText

        bible = BibleText(settings.bible_dir)
    except Exception as e:
        print(f"跳过经文相关：bible_data 不可用（{type(e).__name__}）")

    def run(item: str, need: list[str], fn):
        if item not in only:
            return
        print(f"===== 检查 {item} =====")
        if need:
            print(f"跳过：缺少 {', '.join(need)}")
            report["items"][item] = {"skipped": need}
            return
        try:
            report["items"][item] = fn()
        except Exception as e:
            from core.ready import redact_secrets

            msg = redact_secrets(f"{type(e).__name__}: {e}")[:300]
            print(f"FAIL 检查 {item} 异常：{msg}")
            report["items"][item] = {"error": msg, "pass": False}

    miss_embed = _env_present("QA4_EMBED_BASE_URL", "QA4_EMBED_API_KEY")
    miss_rerank = _env_present("QA4_RERANK_BASE_URL", "QA4_RERANK_API_KEY")

    run("1", miss_es, lambda: check_mappings(es, retrieval_cfg()))
    run("2", miss_neo + ([] if bible else ["bible_data"]), lambda: check_graph_refs(neo, bible))
    run("3", miss_es + ([] if bible else ["bible_data"]), lambda: check_bible_verse_range(es, bible))
    run("4", miss_es + ([] if bible else ["bible_data"]), lambda: check_map_note(es, bible))
    run("4b", miss_es + ([] if bible else ["bible_data"]), lambda: p3.check_map_note_full(es, bible))
    run("5", miss_es, lambda: check_targeted(es, bible, settings.lookup_dir))
    run(
        "5b",
        miss_es + ([] if bible else ["bible_data"]),
        lambda: check_scripture_kinds(es, bible),
    )
    run("6", miss_es + miss_embed, lambda: check_vectors(es, settings))
    run("6b", miss_es + miss_embed, lambda: p3.check_vectors_extra(es, settings))
    run("7", miss_es + miss_embed + miss_rerank, lambda: check_e2e(es, settings))
    run("8", miss_es, lambda: p3.check_text_source_vs_es(es, settings, args))
    run("9", miss_es + miss_embed + miss_rerank, lambda: p3.check_filters_soft(es, settings))
    run("10", [], lambda: p3.check_e2e_fake_llm_live_retrieval(settings))
    run("11", miss_neo + ([] if bible else ["bible_data"]), lambda: p3.check_devine_and_reverse(neo, settings, bible))

    if neo is not None:
        neo.close()

    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out / f"verify_stage2_live_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")

    print("===== 汇总 =====")
    counts = {"PASS": 0, "FAIL": 0, "跳过": 0, "诊断": 0}
    for k in sorted(report["items"].keys(), key=_sort_key):
        v = report["items"][k]
        state = _item_state(v)
        counts[state] = counts.get(state, 0) + 1
        print(f"检查 {k}: {state}")
    print(
        f"合计 PASS={counts['PASS']} FAIL={counts['FAIL']} 跳过={counts['跳过']} 诊断={counts['诊断']}"
    )
    report["summary"] = counts
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(f"OUT={out}")
    return 1 if counts["FAIL"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
