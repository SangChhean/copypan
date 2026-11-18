# -*- coding: utf-8 -*-
"""诗歌数据只读探测（一次性脚本，输出 CSV + 汇总打印）。不改业务代码。"""

from __future__ import annotations

import csv
import json
import random
import re
import statistics
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

SRC = Path(r"G:\PanAI4.0专用\索引数据\panai4_hymns\02_清洗JSON\chunks_hymns.json")
OUT_CSV_DIR = Path(r"G:\PanAI4.0专用\logs\hymn")
OUT_MD = Path(r"G:\copypan\qa4\notes\hymn_data_probe.md")
OUT_JSON = OUT_CSV_DIR / "hymn_probe_summary.json"

PUNCT_CATS = set("P")  # Unicode punctuation categories start with P


def load_rows(path: Path) -> list[dict]:
    rows = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


def gaps(nums: list[int]) -> list[tuple[int, int]]:
    if not nums:
        return []
    s = sorted(set(nums))
    out = []
    expect = s[0]
    for n in s:
        if n > expect:
            out.append((expect, n - 1))
        expect = n + 1
    return out


def format_gaps(gs: list[tuple[int, int]]) -> list[str]:
    return [f"{a}" if a == b else f"{a}-{b}" for a, b in gs]


def normalize_line(s: str) -> str:
    # 去空白与标点
    out = []
    for ch in s:
        if ch.isspace():
            continue
        if unicodedata.category(ch).startswith("P"):
            continue
        out.append(ch)
    return "".join(out)


def is_traditional_heavy(text: str) -> bool:
    """粗检：含常见繁体专字且对应简体未同时占主导。"""
    trad_chars = "國們來說為時會過還這對開關長東來體業經發點實現應裏"
    simp_chars = "国们来说为时会过还这对开关长东来体业经发点实现应里"
    # use distinct traditional-only-ish
    markers = set("國們為時會過還這對開關長東體業經發點實現應萬與麼於")
    return any(ch in markers for ch in text)


def main() -> None:
    OUT_CSV_DIR.mkdir(parents=True, exist_ok=True)
    rows = load_rows(SRC)
    summary: dict = {"source": str(SRC), "n_chunks": len(rows)}

    # ---- unit / series ----
    unit_c = Counter(r.get("unit_type") for r in rows)
    series_c = Counter(r.get("series") for r in rows)
    summary["unit_type_counts"] = dict(unit_c)
    summary["series_chunk_counts"] = dict(series_c)

    fulls = [r for r in rows if r.get("unit_type") == "full"]
    summary["n_full"] = len(fulls)

    # hymn_numbers.csv
    csv_path = OUT_CSV_DIR / "hymn_numbers.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["series", "hymn_number", "name", "整首块的字数"])
        w.writeheader()
        for r in sorted(fulls, key=lambda x: (str(x.get("series") or ""), int(x.get("hymn_number") or 0))):
            text = r.get("text") or ""
            w.writerow(
                {
                    "series": r.get("series") or "",
                    "hymn_number": r.get("hymn_number"),
                    "name": r.get("name") or "",
                    "整首块的字数": len(text),
                }
            )

    by_series: dict[str, list[dict]] = defaultdict(list)
    for r in fulls:
        by_series[str(r.get("series") or "")].append(r)

    series_stats = {}
    for ser, items in sorted(by_series.items()):
        nums = sorted(int(x["hymn_number"]) for x in items)
        series_stats[ser] = {
            "count": len(nums),
            "min": min(nums) if nums else None,
            "max": max(nums) if nums else None,
            "gaps": format_gaps(gaps(nums)),
            "contiguous_1_to_max": nums == list(range(1, max(nums) + 1)) if nums else False,
        }
    summary["series_full_stats"] = series_stats

    # 补充本 781-1005
    bu = by_series.get("补充本诗歌") or []
    bu_nums = sorted(int(x["hymn_number"]) for x in bu)
    bu_781 = [n for n in bu_nums if 781 <= n <= 1005]
    summary["buchong_781_1005_count"] = len(bu_781)
    summary["buchong_gaps"] = format_gaps(gaps(bu_nums))

    # ---- structure ----
    # pick 3 hymns different series
    samples = []
    for ser in ("诗歌", "补充本诗歌", "诗歌附"):
        items = by_series.get(ser) or []
        if not items:
            continue
        # prefer one with chorus if possible
        pick = items[len(items) // 3]
        samples.append(pick)

    # relation full vs stanza/chorus for same message_key
    by_key = defaultdict(list)
    for r in rows:
        by_key[r.get("message_key")].append(r)

    rel_checks = []
    for key, parts in list(by_key.items())[:50]:
        full = [p for p in parts if p.get("unit_type") == "full"]
        others = [p for p in parts if p.get("unit_type") != "full"]
        if not full or not others:
            continue
        ft = full[0].get("text") or ""
        contained = 0
        missing = 0
        for o in others:
            ot = (o.get("text") or "").strip()
            # strip leading title lines for compare? use substring of body lines
            body_lines = [ln for ln in ot.splitlines() if ln.strip()]
            if len(body_lines) >= 2:
                probe = body_lines[1][:12] if len(body_lines[1]) >= 4 else body_lines[-1][:12]
            else:
                probe = ot[:12]
            if probe and probe in ft:
                contained += 1
            else:
                missing += 1
        rel_checks.append(
            {
                "message_key": key,
                "n_other": len(others),
                "contained_probe": contained,
                "missing_probe": missing,
                "unit_types": sorted({str(p.get("unit_type") or "") for p in parts}),
                "unit_labels": sorted({str(p.get("unit_label") or "") for p in parts}),
            }
        )
        if len(rel_checks) >= 15:
            break
    summary["full_contains_other_probes"] = rel_checks

    # unit_type / unit_label inventory
    summary["unit_label_counts"] = dict(Counter(r.get("unit_label") for r in rows))

    sample_views = []
    for r in samples:
        text = r.get("text") or ""
        lines = text.splitlines()
        view_lines = []
        for i, ln in enumerate(lines[:12]):
            view_lines.append({"i": i, "prefix6": ln[:6], "len": len(ln)})
        sample_views.append(
            {
                "series": r.get("series"),
                "hymn_number": r.get("hymn_number"),
                "name": r.get("name"),
                "unit_type": r.get("unit_type"),
                "n_lines": len(lines),
                "text_len": len(text),
                "starts_with_name": bool(r.get("name") and text.startswith(str(r.get("name")))),
                "first_line_prefix6": (lines[0][:6] if lines else ""),
                "first_line_len": (len(lines[0]) if lines else 0),
                "lines_preview": view_lines,
                "field_names": sorted(r.keys()),
            }
        )
    summary["sample_views"] = sample_views

    # title with number?
    title_num = 0
    title_no_num = 0
    for r in fulls[:500]:
        text = r.get("text") or ""
        first = text.splitlines()[0] if text else ""
        name = str(r.get("name") or "")
        if re.search(r"\d", first) or re.search(r"[一二三四五六七八九十百零〇]+", first[:8]):
            # number in first line
            if first.startswith(name) or name in first[:20]:
                title_num += 1
            else:
                title_num += 1
        else:
            title_no_num += 1
    # better: does first line equal name or name with number prefix
    first_eq_name = 0
    first_has_num_then_name = 0
    first_other = 0
    for r in fulls:
        text = r.get("text") or ""
        first = (text.splitlines()[0] if text else "").strip()
        name = str(r.get("name") or "").strip()
        if first == name:
            first_eq_name += 1
        elif name and name in first and re.search(r"\d", first):
            first_has_num_then_name += 1
        else:
            first_other += 1
    summary["title_line"] = {
        "first_eq_name": first_eq_name,
        "first_has_num_and_name": first_has_num_then_name,
        "first_other": first_other,
        "n_full": len(fulls),
    }

    # ---- line stats on full texts ----
    all_lines = []
    for r in fulls:
        for ln in (r.get("text") or "").splitlines():
            all_lines.append(ln)
    lens = [len(x) for x in all_lines]
    lens_sorted = sorted(lens)
    summary["line_stats"] = {
        "n_lines": len(all_lines),
        "min": min(lens) if lens else None,
        "median": statistics.median(lens_sorted) if lens else None,
        "max": max(lens) if lens else None,
        "lt6": sum(1 for x in lens if x < 6),
    }

    # shared lines
    norm_to_hymns: dict[str, set] = defaultdict(set)
    norm_to_prefix: dict[str, str] = {}
    for r in fulls:
        key = (str(r.get("series")), int(r.get("hymn_number") or 0))
        for ln in (r.get("text") or "").splitlines():
            nrm = normalize_line(ln)
            if not nrm:
                continue
            norm_to_hymns[nrm].add(key)
            if nrm not in norm_to_prefix:
                # original prefix for display (first 6 of raw line stripped)
                norm_to_prefix[nrm] = ln.strip()[:6]
    multi = {k: v for k, v in norm_to_hymns.items() if len(v) > 1}
    multi5 = {k: v for k, v in multi.items() if len(v) >= 5}
    top10 = sorted(multi.items(), key=lambda kv: len(kv[1]), reverse=True)[:10]
    summary["shared_lines"] = {
        "multi_hymn_line_norms": len(multi),
        "multi_ge5": len(multi5),
        "top10": [
            {"prefix6": norm_to_prefix[k], "n_hymns": len(v), "norm_len": len(k)} for k, v in top10
        ],
    }

    # punctuation set
    punct = set()
    for r in fulls:
        for ch in r.get("text") or "":
            if unicodedata.category(ch).startswith("P") or ch in "，。、；：？！「」『』（）【】《》—…·":
                punct.add(ch)
    summary["punctuation"] = "".join(sorted(punct, key=lambda c: (unicodedata.category(c), c)))

    # traditional sample 200
    rng = random.Random(20261117)
    sample200 = rng.sample(fulls, min(200, len(fulls)))
    trad_hits = sum(1 for r in sample200 if is_traditional_heavy(r.get("text") or ""))
    # also count specific trad chars frequency
    trad_char_hits = Counter()
    markers = "國們為時會過還這對開關長東體業經發點實現應萬與麼於臺經衛"
    for r in sample200:
        for ch in set(r.get("text") or ""):
            if ch in markers:
                trad_char_hits[ch] += 1
    summary["traditional_sample"] = {
        "n": len(sample200),
        "method": "随机200首 full；若含繁体标记字集合（國們為時會過還這對開關長東體業經發點實現應萬與麼於臺經衛）任一则计为含繁体倾向",
        "hit_hymns": trad_hits,
        "marker_char_hymn_counts": dict(trad_char_hits.most_common(20)),
    }

    # ---- memory match ----
    corpus = []
    for r in fulls:
        text = r.get("text") or ""
        nrm = normalize_line(text)
        corpus.append(
            {
                "series": r.get("series"),
                "hymn_number": r.get("hymn_number"),
                "norm": nrm,
                "raw_len": len(text),
            }
        )
    # build 1000 random 8-char fragments from corpus
    frags = []
    while len(frags) < 1000:
        item = rng.choice(corpus)
        nrm = item["norm"]
        if len(nrm) < 8:
            continue
        i = rng.randint(0, len(nrm) - 8)
        frags.append(nrm[i : i + 8])

    t0 = time.perf_counter()
    hit_counts = []
    for frag in frags:
        n_hit = sum(1 for c in corpus if frag in c["norm"])
        hit_counts.append(n_hit)
    elapsed = time.perf_counter() - t0
    summary["memory_match"] = {
        "n_full_in_memory": len(corpus),
        "n_frags": len(frags),
        "frag_len": 8,
        "total_sec": round(elapsed, 4),
        "per_frag_ms": round(elapsed / len(frags) * 1000, 4),
        "hit_1": sum(1 for x in hit_counts if x == 1),
        "hit_2_4": sum(1 for x in hit_counts if 2 <= x <= 4),
        "hit_ge5": sum(1 for x in hit_counts if x >= 5),
        "hit_0": sum(1 for x in hit_counts if x == 0),
        "hit_max": max(hit_counts) if hit_counts else 0,
        "hit_mean": round(sum(hit_counts) / len(hit_counts), 3) if hit_counts else 0,
    }

    # stanza delimiter heuristics on samples
    delim_notes = []
    for r in samples:
        text = r.get("text") or ""
        flags = {
            "has_blank_line": "\n\n" in text,
            "has_numbered_stanza": bool(re.search(r"(?m)^[0-9０-９一二三四五六七八九十]+[\.、．]", text)),
            "has_chorus_word": ("副歌" in text) or ("和" == text.strip()[:1]),
            "line_count": len(text.splitlines()),
        }
        delim_notes.append({"series": r.get("series"), "hymn_number": r.get("hymn_number"), **flags})
    summary["delimiter_notes"] = delim_notes

    # non-full chunks for same keys as samples
    sample_parts = []
    for r in samples:
        key = r.get("message_key")
        parts = by_key.get(key) or []
        sample_parts.append(
            {
                "message_key": key,
                "parts": [
                    {
                        "unit_type": p.get("unit_type"),
                        "unit_label": p.get("unit_label"),
                        "chunk_index": p.get("chunk_index"),
                        "text_len": len(p.get("text") or ""),
                        "prefix6": ((p.get("text") or "").splitlines()[0][:6] if p.get("text") else ""),
                        "n_lines": len((p.get("text") or "").splitlines()),
                    }
                    for p in sorted(parts, key=lambda x: int(x.get("chunk_index") or 0))
                ],
            }
        )
    summary["sample_parts"] = sample_parts

    OUT_JSON.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("WROTE", csv_path)
    print("WROTE", OUT_JSON)
    print("FULLS", len(fulls), "series", {k: v["count"] for k, v in series_stats.items()})
    print("BU781", summary["buchong_781_1005_count"], "gaps_n", len(summary["buchong_gaps"]))
    print("LINES", summary["line_stats"])
    print("SHARED", summary["shared_lines"]["multi_hymn_line_norms"], summary["shared_lines"]["multi_ge5"])
    print("MEM", summary["memory_match"])
    print("TRAD", summary["traditional_sample"]["hit_hymns"])


if __name__ == "__main__":
    main()
