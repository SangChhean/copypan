# -*- coding: utf-8 -*-
"""歌词查找探针：从真实诗歌数据自动生成用例（答案已知）；歌词原文不进仓库。"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import statistics
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

_BACKEND = Path(__file__).resolve().parents[1]
_QA4 = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

DEFAULT_OUT = Path(r"G:\PanAI4.0专用\logs\hymn_lyrics")
DEFAULT_NOTES = _QA4 / "notes" / "hymn_lyrics_probe_summary.md"
DEFAULT_SEED = 20261117
DEFAULT_N = 300

_STANZA_MARK = re.compile(r"^\s*([一二三四五六七八九十百千零〇○两廿卅]+|副)\s*　\s*")
_CLAUSE_SPLIT = re.compile(r"[，。！？；、；;,.!?\n]+")

TEXT_LIFE = Path(r"G:\PanAI4.0专用\索引数据\panai4_text_life\02_清洗JSON\life_rendered.new.jsonl")
TEXT_CWWL_DIR = Path(r"G:\PanAI4.0专用\索引数据\panai4_text_cwwl\02_清洗JSON")


def _s2t(text: str) -> str:
    try:
        from opencc import OpenCC

        return OpenCC("s2t").convert(text)
    except Exception:
        pass
    # 反向 t2s 字表
    from scripture.ref_enhance import _load_t2s

    table = _load_t2s()
    rev = {v: k for k, v in table.items() if len(v) == 1 and len(k) == 1}
    return "".join(rev.get(ch, ch) for ch in text)


def _clauses_from_text(text: str) -> list[tuple[str, str]]:
    """→ [(unit_label, clause)]，跳过诗名行。"""
    lines = (text or "").split("\n")
    out: list[tuple[str, str]] = []
    label = "一"
    for raw in lines[1:]:
        line = raw
        m = _STANZA_MARK.match(line)
        if m:
            label = m.group(1)
            line = line[m.end() :]
        line = line.strip()
        if not line:
            continue
        for part in _CLAUSE_SPLIT.split(line):
            p = part.strip()
            if p:
                out.append((label, p))
    return out


def _norm_len(s: str) -> int:
    from hymn.lyrics import normalize_lyric_text

    return len(normalize_lyric_text(s, strip_hints=False))


def _load_hymn_pool():
    from hymn.catalog import get_catalog
    from hymn.lyrics import get_lyrics_index, reset_lyrics_index

    cat = get_catalog()
    cat.ensure_loaded()
    reset_lyrics_index()
    idx = get_lyrics_index(catalog=cat)
    rows = cat.full_rows()
    by_series: dict[str, list[dict]] = defaultdict(list)
    clause_index: dict[str, list[tuple[str, int]]] = defaultdict(list)  # norm_clause -> [(series, num)]
    pool: list[dict[str, Any]] = []
    for r in rows:
        clauses = _clauses_from_text(r["text"])
        usable = [(lab, c) for lab, c in clauses if _norm_len(c) >= 8]
        item = {**r, "clauses": clauses, "usable": usable}
        pool.append(item)
        by_series[r["series"]].append(item)
        from hymn.lyrics import normalize_lyric_text

        for _, c in usable:
            key = normalize_lyric_text(c)
            if key:
                clause_index[key].append((r["series"], r["hymn_number"]))
    return pool, by_series, clause_index, idx


def _pick_balanced(by_series: dict[str, list], rng: random.Random, n: int) -> list[dict]:
    """跨系列抽样 hymn 条目。"""
    keys = [k for k, v in by_series.items() if v]
    if not keys:
        return []
    out = []
    i = 0
    while len(out) < n:
        series = keys[i % len(keys)]
        item = rng.choice(by_series[series])
        if item.get("usable"):
            out.append(item)
        i += 1
        if i > n * 20:
            break
    return out


def _hit_source(res: dict, series: str, num: int) -> bool:
    for m in res.get("matches") or []:
        sc = m.get("series_code") or m.get("series")
        from hymn.catalog import ES_TO_SERIES, SERIES_TO_ES

        if sc in ES_TO_SERIES:
            code = ES_TO_SERIES[sc]
        elif sc in SERIES_TO_ES:
            code = sc
        else:
            code = sc
        if code == series and int(m.get("hymn_number") or -1) == int(num):
            return True
    return False


def _rank_of_source(res: dict, series: str, num: int) -> Optional[int]:
    for i, m in enumerate(res.get("matches") or [], 1):
        sc = m.get("series_code") or m.get("series")
        from hymn.catalog import ES_TO_SERIES, SERIES_TO_ES

        if sc in ES_TO_SERIES:
            code = ES_TO_SERIES[sc]
        elif sc in SERIES_TO_ES:
            code = sc
        else:
            code = sc
        if code == series and int(m.get("hymn_number") or -1) == int(num):
            return i
    return None


def _sample_text_sentences(path: Path, rng: random.Random, need: int, min_len: int = 12) -> list[str]:
    from hymn.lyrics import normalize_lyric_text

    if not path.is_file():
        return []
    buf: list[str] = []
    # 水库抽样
    seen = 0
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = str(obj.get("text") or "")
            for part in re.split(r"[。！？\n]", text):
                p = part.strip()
                if _norm_len(p) < min_len:
                    continue
                # 排除太像诗歌标记
                if _STANZA_MARK.match(p):
                    continue
                seen += 1
                if len(buf) < need * 3:
                    buf.append(p)
                else:
                    j = rng.randrange(seen)
                    if j < len(buf):
                        buf[j] = p
    rng.shuffle(buf)
    return buf[:need]


def _cwwl_path() -> Optional[Path]:
    if not TEXT_CWWL_DIR.is_dir():
        return None
    for p in sorted(TEXT_CWWL_DIR.glob("*.jsonl")):
        return p
    for p in sorted(TEXT_CWWL_DIR.glob("*.json")):
        return p
    return None


def build_cases(n: int, seed: int) -> tuple[list[dict[str, Any]], Any]:
    from hymn.lyrics import normalize_lyric_text

    rng = random.Random(seed)
    pool, by_series, clause_index, idx = _load_hymn_pool()
    hymns = _pick_balanced(by_series, rng, max(n * 2, 100))
    cases: list[dict[str, Any]] = []

    def add(kind: str, query: str, expect: dict[str, Any], meta: Optional[dict] = None):
        cases.append({"kind": kind, "query": query, "expect": expect, "meta": meta or {}})

    # ---- T1 exact full clause ----
    t1_items = [h for h in hymns if h["usable"]]
    rng.shuffle(t1_items)
    for h in t1_items:
        if sum(1 for c in cases if c["kind"] == "T1") >= n:
            break
        lab, clause = rng.choice(h["usable"])
        key = normalize_lyric_text(clause)
        owners = list({(s, num) for s, num in clause_index.get(key, [])})
        add(
            "T1",
            clause,
            {"owners": owners[:5], "must_include": (h["series"], h["hymn_number"])},
            {"unit": lab},
        )

    # ---- T2 fragment 6-12 ----
    for h in t1_items:
        if sum(1 for c in cases if c["kind"] == "T2") >= n:
            break
        _, clause = rng.choice(h["usable"])
        nn = normalize_lyric_text(clause)
        if len(nn) < 6:
            continue
        L = rng.randint(6, min(12, len(nn)))
        start = rng.randint(0, len(nn) - L)
        frag = nn[start : start + L]
        add("T2", frag, {"must_include": (h["series"], h["hymn_number"])})

    # ---- T3 cross two adjacent clauses（必须正文相邻，不能只用 usable 过滤后的相邻）----
    # 排除「拼接后过短且过于常见」→ too_common 且来源不进前5 的用例
    t3_pool = list(t1_items) + [h for h in pool if h.get("clauses") and h not in t1_items]
    rng.shuffle(t3_pool)
    for h in t3_pool:
        if sum(1 for c in cases if c["kind"] == "T3") >= n:
            break
        clauses = h["clauses"]
        if len(clauses) < 2:
            continue
        candidates = []
        for i in range(len(clauses) - 1):
            a = normalize_lyric_text(clauses[i][1])
            b = normalize_lyric_text(clauses[i + 1][1])
            if len(a) >= 4 and len(b) >= 4 and len(a) + len(b) >= 8:
                candidates.append(a + b)
        if not candidates:
            continue
        rng.shuffle(candidates)
        picked = None
        for cand in candidates:
            if not _t3_query_ok(cand, h["series"], h["hymn_number"], idx):
                continue
            picked = cand
            break
        if picked is None:
            continue
        add("T3", picked, {"must_include": (h["series"], h["hymn_number"])})
    # ---- T4 punct + quotes ----
    for h in t1_items:
        if sum(1 for c in cases if c["kind"] == "T4") >= n:
            break
        _, clause = rng.choice(h["usable"])
        q = f"「{clause}」"
        add("T4", q, {"must_include": (h["series"], h["hymn_number"])})

    # ---- T5 traditional ----
    for h in t1_items:
        if sum(1 for c in cases if c["kind"] == "T5") >= n:
            break
        _, clause = rng.choice(h["usable"])
        add("T5", _s2t(clause), {"must_include": (h["series"], h["hymn_number"])})

    # ---- T6 fuzzy errors（从全库有足够长句的诗歌中抽）----
    modes = ["sub", "del", "ins"]
    t6_pool = [h for h in pool if any(_norm_len(c) >= 10 for _, c in h["clauses"])]
    rng.shuffle(t6_pool)
    t6_count = 0
    for h in t6_pool:
        if t6_count >= n:
            break
        long_clauses = [c for _, c in h["clauses"] if _norm_len(c) >= 10]
        if not long_clauses:
            continue
        clause = rng.choice(long_clauses)
        nn = normalize_lyric_text(clause)
        if len(nn) < 10:
            continue
        L = rng.randint(10, min(16, len(nn)))
        start = rng.randint(0, len(nn) - L)
        frag = list(nn[start : start + L])
        mode = modes[t6_count % 3]
        if mode == "sub" and frag:
            j = rng.randrange(len(frag))
            frag[j] = "测" if frag[j] != "测" else "试"
        elif mode == "del" and len(frag) > 1:
            del frag[rng.randrange(len(frag))]
        elif mode == "ins":
            frag.insert(rng.randrange(len(frag) + 1), "啊")
        add(
            "T6",
            "".join(frag),
            {"must_include_top3": (h["series"], h["hymn_number"])},
            {"mode": mode},
        )
        t6_count += 1

    # ---- T7 embedded questions ----
    templates = [
        "哪首诗歌有这句：{x}",
        "{x}是哪首诗歌的歌词？",
        "我记得有一句是「{x}」",
        "这句歌词「{x}」出自哪首",
        "诗歌里有「{x}」是哪一首",
    ]
    for h in t1_items:
        if sum(1 for c in cases if c["kind"] == "T7") >= n:
            break
        _, clause = rng.choice(h["usable"])
        tpl = templates[len([c for c in cases if c["kind"] == "T7"]) % len(templates)]
        add(
            "T7",
            tpl.format(x=clause),
            {
                "must_include": (h["series"], h["hymn_number"]),
                "intent": True,
            },
        )

    # ---- T8 too short ----
    shorts = ["主", "爱", "主啊", "耶稣", "恩典"]
    while sum(1 for c in cases if c["kind"] == "T8") < n:
        s = rng.choice(shorts)
        if _norm_len(s) >= 4:
            s = s[:2]
        add("T8", s, {"status": "too_short"})

    # ---- T9 title：唯一诗名、≥6字，且不会作为正文 exact 命中过多首----
    title_owners: dict[str, list[tuple[str, int]]] = defaultdict(list)
    for h in pool:
        tn = normalize_lyric_text(h.get("title") or "")
        if len(tn) >= 6:
            title_owners[tn].append((h["series"], h["hymn_number"]))
    # 正文中该串出现次数（用于排除「诗名=常见歌词短句」）
    body_hit_n = {tn: 0 for tn in title_owners}
    for doc in idx.docs:
        for tn in body_hit_n:
            if tn in doc.body_norm:
                body_hit_n[tn] += 1
    unique_titles = [
        (tn, owners[0])
        for tn, owners in title_owners.items()
        if len(owners) == 1 and body_hit_n.get(tn, 0) <= 1
    ]
    rng.shuffle(unique_titles)
    for tn, (series, num) in unique_titles:
        if sum(1 for c in cases if c["kind"] == "T9") >= n:
            break
        add(
            "T9",
            tn,
            {
                "must_include": (series, num),
                "match_type": "title",
            },
        )

    # ---- T10 negatives ----
    # (a) other corpora：排除与任一首诗歌有≥8字精确公共子串的句子
    body_8grams = _body_ngrams(idx, 8)
    life_sents = _sample_text_sentences(TEXT_LIFE, rng, 900, 12)
    cwwl_p = _cwwl_path()
    cwwl_sents = _sample_text_sentences(cwwl_p, rng, 900, 12) if cwwl_p else []
    neg = life_sents + cwwl_sents
    rng.shuffle(neg)
    t10a_excluded = 0
    t10a_n = 0
    for s in neg:
        if t10a_n >= 500:
            break
        nn = normalize_lyric_text(s, strip_hints=False)
        if _has_ngram_overlap(nn, body_8grams, 8):
            t10a_excluded += 1
            continue
        add("T10a", s, {"intent": False, "no_hit": True})
        t10a_n += 1
    # (b) format case inputs
    for fname in ("scripture_format_cases_v2.csv", "hymn_format_cases_v2.csv"):
        path = _QA4 / "notes" / fname
        if not path.is_file():
            continue
        with path.open(encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                inp = (row.get("input") or "").strip()
                if not inp:
                    continue
                add("T10b", inp, {"intent": False})

    # 元信息挂在返回值之外：调用方从 cases 无法取；写入临时属性
    setattr(idx, "_probe_t10a_excluded", t10a_excluded)
    setattr(idx, "_probe_t10a_kept", t10a_n)
    return cases, idx


def _body_ngrams(idx, n: int) -> set[str]:
    grams: set[str] = set()
    for doc in idx.docs:
        b = doc.body_norm or ""
        if len(b) < n:
            continue
        for i in range(len(b) - n + 1):
            grams.add(b[i : i + n])
    return grams


def _has_ngram_overlap(norm: str, grams: set[str], n: int) -> bool:
    if len(norm) < n or not grams:
        return False
    for i in range(len(norm) - n + 1):
        if norm[i : i + n] in grams:
            return True
    return False


def _t3_query_ok(query: str, series: str, hymn_number: int, idx) -> bool:
    """T3 可用：精确命中数≤5（非 too_common），且来源首出现在返回列表中。"""
    from hymn.lyrics import find_lyrics

    res = find_lyrics(query, index=idx)
    if res.get("status") == "too_common":
        return False
    if res.get("status") != "found":
        return False
    if int(res.get("total") or 0) > 5:
        return False
    return _hit_source(res, series, hymn_number)


def run_cases(cases: list[dict[str, Any]], idx, out_dir: Path) -> dict[str, Any]:
    from hymn.lyrics import find_lyrics, lyric_intent

    out_dir.mkdir(parents=True, exist_ok=True)
    stats: dict[str, dict[str, Any]] = defaultdict(lambda: {"n": 0, "hit": 0, "top1": 0, "top3": 0, "fail": 0})
    times: list[float] = []
    fails: list[dict[str, Any]] = []
    t10_false = 0

    for i, case in enumerate(cases):
        kind = case["kind"]
        q = case["query"]
        exp = case["expect"]
        t0 = time.perf_counter()
        res = find_lyrics(q, index=idx)
        intent = lyric_intent(q, index=idx)
        dt = (time.perf_counter() - t0) * 1000
        times.append(dt)
        st = stats[kind]
        st["n"] += 1
        ok = True
        reason = ""

        if kind == "T8":
            ok = res.get("status") == "too_short" and not res.get("matches")
            reason = f"status={res.get('status')}"
        elif kind in {"T10a", "T10b"}:
            if intent:
                ok = False
                t10_false += 1
                reason = "intent_true"
            elif kind == "T10a" and res.get("status") in {"found", "too_common"} and res.get("matches"):
                # 负例不应命中诗歌；若精确命中也算误触
                ok = False
                t10_false += 1
                reason = f"hit_status={res.get('status')}"
            else:
                ok = True
        elif kind == "T6":
            series, num = exp["must_include_top3"]
            rank = _rank_of_source(res, series, num)
            if rank == 1:
                st["top1"] += 1
            if rank is not None and rank <= 3:
                st["top3"] += 1
                st["hit"] += 1
            else:
                ok = False
                reason = f"rank={rank}"
        elif kind == "T7":
            series, num = exp["must_include"]
            if not intent:
                ok = False
                reason = "intent_false"
            elif not _hit_source(res, series, num):
                ok = False
                reason = "miss_source"
            else:
                st["hit"] += 1
        elif kind == "T9":
            series, num = exp["must_include"]
            matched = False
            for m in res.get("matches") or []:
                if m.get("match_type") == "title" and _hit_source({"matches": [m]}, series, num):
                    matched = True
                    break
            # 也允许 exact 若诗名正文恰在歌词中；仍要求来源首出现
            if not matched and _hit_source(res, series, num):
                # 若命中来源但不是 title，仍算部分；验收要求 match_type=title
                ok = False
                reason = "no_title_type"
            elif matched:
                st["hit"] += 1
            else:
                ok = False
                reason = "miss"
        elif kind == "T1":
            series, num = exp["must_include"]
            owners = exp.get("owners") or [(series, num)]
            got = {(m.get("series_code"), m.get("hymn_number")) for m in res.get("matches") or []}
            # series in result is ES name; normalize
            from hymn.catalog import ES_TO_SERIES

            got2 = set()
            for m in res.get("matches") or []:
                sc = m.get("series_code") or m.get("series")
                code = ES_TO_SERIES.get(sc, sc)
                got2.add((code, int(m["hymn_number"])))
            if not _hit_source(res, series, num):
                ok = False
                reason = "miss_source"
            else:
                # 多首共享句：期望结果覆盖 owners（≤5）
                need = set(owners[:5])
                if need and not need.issubset(got2) and len(need) <= 5:
                    # 若 too_common 只给前5，只要来源在前5即可
                    if res.get("status") == "too_common" and _hit_source(res, series, num):
                        st["hit"] += 1
                    elif need.issubset(got2):
                        st["hit"] += 1
                    else:
                        ok = False
                        reason = "owners_incomplete"
                else:
                    st["hit"] += 1
        else:
            series, num = exp["must_include"]
            if _hit_source(res, series, num):
                st["hit"] += 1
            else:
                ok = False
                reason = "miss_source"

        if not ok:
            st["fail"] += 1
            if len(fails) < 500:
                fails.append(
                    {
                        "id": f"{kind}-{st['n']}",
                        "kind": kind,
                        "reason": reason,
                        "status": res.get("status"),
                        "total": res.get("total"),
                        "n_matches": len(res.get("matches") or []),
                        "match_types": [m.get("match_type") for m in (res.get("matches") or [])],
                        "query_len": len(q),
                        "meta": case.get("meta") or {},
                        # 不写歌词原文
                    }
                )

    times_sorted = sorted(times)
    summary = {
        "n_cases": len(cases),
        "by_kind": {},
        "timing_ms": {
            "median": round(statistics.median(times_sorted), 3) if times_sorted else 0,
            "p95": round(times_sorted[int(0.95 * (len(times_sorted) - 1))] if times_sorted else 0, 3),
            "mean": round(statistics.mean(times_sorted), 3) if times_sorted else 0,
        },
        "t10_false_triggers": t10_false,
    }
    for kind, st in sorted(stats.items()):
        n = st["n"] or 1
        entry = {
            "n": st["n"],
            "hit": st["hit"],
            "fail": st["fail"],
            "hit_rate": round(st["hit"] / n, 4) if kind not in {"T8", "T10a", "T10b"} else round(1 - st["fail"] / n, 4),
        }
        if kind == "T6":
            entry["top1_rate"] = round(st["top1"] / n, 4)
            entry["top3_rate"] = round(st["top3"] / n, 4)
        if kind.startswith("T10"):
            entry["false_triggers"] = st["fail"]
        summary["by_kind"][kind] = entry

    (out_dir / "hymn_lyrics_fails.json").write_text(
        json.dumps({"n_fail": len(fails), "fails": fails}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_dir / "hymn_lyrics_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def write_notes(summary: dict[str, Any], notes_path: Path, seed: int, n: int) -> None:
    lines = [
        "# 歌词查找探针汇总",
        "",
        f"- seed={seed} n={n}",
        f"- 用例总数={summary.get('n_cases')}",
        f"- 耗时 ms：median={summary['timing_ms']['median']} p95={summary['timing_ms']['p95']} mean={summary['timing_ms']['mean']}",
        f"- T10 误触发合计={summary.get('t10_false_triggers')}",
        f"- T10a 因≥8字诗歌公共子串排除={summary.get('t10a_excluded')}",
        "",
        "## 各类",
        "",
        "| 类 | n | hit_rate | 备注 |",
        "|---|---:|---:|---|",
    ]
    for kind, st in summary.get("by_kind", {}).items():
        note = ""
        if kind == "T6":
            note = f"top1={st.get('top1_rate')} top3={st.get('top3_rate')}"
        if kind.startswith("T10"):
            note = f"false_triggers={st.get('false_triggers')}"
        lines.append(f"| {kind} | {st['n']} | {st['hit_rate']} | {note} |")
    lines += ["", "失败明细（含查询原文）仅写 logs/hymn_lyrics/，不进仓库。", ""]
    notes_path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--n", type=int, default=DEFAULT_N)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--no-notes", action="store_true")
    args = ap.parse_args(argv)

    print(f"building cases seed={args.seed} n={args.n} ...")
    cases, idx = build_cases(args.n, args.seed)
    t10a_ex = int(getattr(idx, "_probe_t10a_excluded", 0) or 0)
    t10a_kept = int(getattr(idx, "_probe_t10a_kept", 0) or 0)
    print(f"cases={len(cases)} t10a_kept={t10a_kept} t10a_excluded={t10a_ex} running...")
    summary = run_cases(cases, idx, args.out)
    summary["t10a_excluded"] = t10a_ex
    summary["t10a_kept"] = t10a_kept
    # 覆盖写入 summary json（run_cases 已写过一次）
    try:
        (args.out / f"hymn_lyrics_summary_{args.seed}.json").write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception:
        pass
    if not args.no_notes:
        notes = DEFAULT_NOTES.with_name(f"hymn_lyrics_probe_summary_{args.seed}.md")
        write_notes(summary, notes, args.seed, args.n)
        # 兼容默认文件名（最后一次覆盖）
        write_notes(summary, DEFAULT_NOTES, args.seed, args.n)
        print(f"NOTES={notes}")
    print(f"OUT={args.out}")
    print(json.dumps(summary["by_kind"], ensure_ascii=False, indent=2))
    print("timing", summary["timing_ms"])
    print("t10_false", summary["t10_false_triggers"])
    print("t10a_excluded", t10a_ex)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
