# -*- coding: utf-8 -*-
"""Probe5-A: 辩理材料重统计（只读）。"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(r"G:\copypan")
NOTES = REPO / "qa4" / "notes"
OUT_JSON = NOTES / "probe5" / "a_result.json"
OUT_CSV = NOTES / "devine_argument_items_all.csv"

DESK_SPECIAL = Path(r"C:\Users\28121\Desktop\可导入资料\2 特殊标注")
DEVINE = DESK_SPECIAL / "【devine_argument】越进入高峰，真理越需要辨明得准确.json"
ORG_QA4 = REPO / "qa4" / "data" / "graph_annotations" / "organic_advance.json"
CLASS4 = DESK_SPECIAL / "【intrinsic_significance】2372词条内在意义分类.json"
IMPORT_MD = REPO / "docs" / "panai4_graph" / "import_devine_argument.md"
STATE = REPO / "logs" / "import_annotation_devine_argument_state.json"

PAREN_PAIRS = [
    ("产生男孩子", "产生得胜者"),
    ("晨晨复兴", "晨兴"),
    ("妇人", "女人"),
    ("挂虑", "忧虑"),
    ("火湖", "地狱"),
    ("扩大", "显大"),
    ("扩增", "扩展"),
    ("那灵的浇灌", "圣灵的浇灌"),
]


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def top_keys(obj) -> list[str]:
    if isinstance(obj, list) and obj and isinstance(obj[0], dict):
        return sorted(obj[0].keys())
    if isinstance(obj, dict):
        return sorted(obj.keys())
    return []


def norm_title(t: str) -> str:
    """T3：去空白与标点，统一全半角后再比较。"""
    s = unicodedata.normalize("NFKC", t or "")
    out = []
    for ch in s:
        if ch.isspace():
            continue
        if unicodedata.category(ch).startswith("P"):
            continue
        out.append(ch)
    return "".join(out)


def build_2380(class4_path: Path) -> dict:
    data = load_json(class4_path)
    words = data.get("words") if isinstance(data, dict) else data
    names = []
    for w in words:
        n = w.get("name") if isinstance(w, dict) else None
        if n:
            names.append(n)
    # 明确按 inventory_v4_pre 的 8 对拆合写名
    expanded: set[str] = set()
    combined = {f"{o}（{i}）": (o, i) for o, i in PAREN_PAIRS}
    for n in names:
        if n in combined:
            o, i = combined[n]
            expanded.add(o)
            expanded.add(i)
        else:
            expanded.add(n)
    # 路得/路德 两种写法都认
    variants = set(expanded)
    for n in list(expanded):
        if "路得马丁" in n:
            variants.add(n.replace("路得马丁", "路德马丁"))
        if "路德马丁" in n:
            variants.add(n.replace("路德马丁", "路得马丁"))
    exact_lude = [n for n in names if n in ("路德马丁", "路得马丁")]
    return {
        "class4_n": len(names),
        "class4_unique": len(set(names)),
        "set_2380_size": len(expanded),
        "set_with_variants_size": len(variants),
        "expanded_names": sorted(expanded),
        "variants": sorted(variants),
        "lude_in_class4": exact_lude,
        "has_路德马丁": "路德马丁" in set(names),
        "has_路得马丁": "路得马丁" in set(names),
    }


def find_near_count_files() -> list[dict]:
    """桌面可导入资料下，条目数接近 189 或 73 的其它 json。"""
    root = Path(r"C:\Users\28121\Desktop\可导入资料")
    hits = []
    for p in root.rglob("*.json"):
        try:
            data = load_json(p)
        except Exception:
            continue
        n = None
        if isinstance(data, list):
            n = len(data)
        elif isinstance(data, dict):
            for k in ("words", "items", "data", "records"):
                if isinstance(data.get(k), list):
                    n = len(data[k])
                    break
            if n is None:
                n = len(data)
        if n is None:
            continue
        if abs(n - 189) <= 5 or abs(n - 73) <= 5 or abs(n - 72) <= 2:
            hits.append({"path": str(p), "n": n, "keys": top_keys(data)})
    return hits


def analyze_devine(data: list) -> dict:
    names = [x.get("name") for x in data]
    name_c = Counter(names)
    dup_names = [n for n, c in name_c.items() if c > 1]

    # flatten items
    rows = []
    first_titles = set()
    all_titles = []
    all_titles_norm = []
    title_outline = []
    outlines_ws = []
    len_dist = Counter()

    for rec in data:
        name = rec.get("name")
        c1 = rec.get("content_1") or []
        if not isinstance(c1, list):
            c1 = []
        len_dist[len(c1)] += 1
        for i, item in enumerate(c1):
            if not isinstance(item, dict):
                continue
            title = item.get("title") or ""
            desc = item.get("description") or ""
            outline = item.get("outline") or ""
            is_first = i == 0
            if is_first:
                first_titles.add(title)
            all_titles.append(title)
            all_titles_norm.append(norm_title(title))
            title_outline.append((title, outline))
            outlines_ws.append(re.sub(r"\s+", "", outline))
            rows.append(
                {
                    "name": name,
                    "idx": i + 1,
                    "title": title,
                    "desc30": (desc[:30] if isinstance(desc, str) else ""),
                    "outline_len": len(outline) if isinstance(outline, str) else 0,
                    "title_is_first_somewhere": None,  # fill later
                }
            )

    # titles that appear as first item somewhere
    titles_as_first = set(first_titles)
    for r in rows:
        r["title_is_first_somewhere"] = r["title"] in titles_as_first

    non_first_only = sorted(
        {r["title"] for r in rows if r["idx"] > 1 and r["title"] not in titles_as_first}
    )

    # same title -> different outlines
    by_title = defaultdict(set)
    for t, o in title_outline:
        by_title[t].add(o)
    title_multi_outline = {
        t: len(os) for t, os in by_title.items() if len(os) > 1
    }
    # samples (truncate)
    title_multi_samples = []
    for t, os in by_title.items():
        if len(os) > 1:
            title_multi_samples.append(
                {
                    "title": t[:30],
                    "n_outlines": len(os),
                    "outline_lens": sorted(len(x) for x in os)[:5],
                }
            )

    # different titles -> same outline (ws-stripped)
    by_ol = defaultdict(set)
    for t, o in title_outline:
        key = re.sub(r"\s+", "", o or "")
        by_ol[key].add(t)
    outline_multi_title = {k: sorted(vs) for k, vs in by_ol.items() if len(vs) > 1 and k}
    outline_multi_samples = []
    for k, vs in list(outline_multi_title.items())[:20]:
        outline_multi_samples.append(
            {"outline_ws_len": len(k), "titles": [v[:30] for v in vs]}
        )

    t2 = len(set(all_titles))
    t3 = len(set(all_titles_norm))
    c1 = len(set(title_outline))
    c2 = len(set(outlines_ws))

    return {
        "n_entries": len(data),
        "n_unique_names": len(set(names)),
        "dup_names": dup_names,
        "content1_len_dist": dict(sorted(len_dist.items())),
        "total_items": len(rows),
        "T1_first_titles": len(first_titles),
        "T2_all_titles": t2,
        "T3_norm_titles": t3,
        "C1_title_outline": c1,
        "C2_outline_ws": c2,
        "non_first_only_titles": non_first_only,
        "n_titles_multi_outline": len(title_multi_outline),
        "title_multi_samples": title_multi_samples[:15],
        "n_outlines_multi_title": len(outline_multi_title),
        "outline_multi_samples": outline_multi_samples[:15],
        "rows": rows,
        "first_title_list_sample": sorted(first_titles)[:10],
    }


def find_189_vs_187() -> dict:
    out = {"from_md": None, "from_state": None, "discarded": None}
    if IMPORT_MD.is_file():
        text = IMPORT_MD.read_text(encoding="utf-8")
        # look for discarded names
        m = re.search(r"丢弃\s*=\s*\[([^\]]+)\]", text)
        m2 = re.search(r'"discarded"\s*:\s*\[(.*?)\]', text, re.S)
        out["from_md_snip"] = []
        for line in text.splitlines():
            if "丢弃" in line or "discarded" in line or "产生得胜者" in line or "圣灵的浇灌" in line:
                out["from_md_snip"].append(line.strip()[:120])
        if m2:
            names = re.findall(r'"([^"]+)"', m2.group(1))
            out["discarded"] = names
            out["from_md"] = f"import_devine_argument.md discarded={names}"
    if STATE.is_file():
        st = load_json(STATE)
        disc = None
        if isinstance(st, dict):
            for path in (
                ("import", "discarded"),
                ("discarded",),
                ("check", "discarded"),
            ):
                cur = st
                ok = True
                for k in path:
                    if isinstance(cur, dict) and k in cur:
                        cur = cur[k]
                    else:
                        ok = False
                        break
                if ok:
                    disc = cur
                    break
            # also search recursively for discarded list of 2
            if disc is None:

                def walk(o, path=""):
                    if isinstance(o, dict):
                        for k, v in o.items():
                            if k == "discarded":
                                return v, path + "/" + k
                            r = walk(v, path + "/" + k)
                            if r:
                                return r
                    elif isinstance(o, list) and len(o) < 20:
                        pass
                    return None

                found = walk(st)
                if found:
                    disc, p = found
                    out["from_state_path"] = p
            out["from_state"] = disc
            if isinstance(disc, list) and out.get("discarded") is None:
                out["discarded"] = disc
    return out


def main():
    result = {"script": "qa4/notes/probe5/a_devine.py"}

    # locate near-count files
    result["near_count_files"] = find_near_count_files()

    # (a)
    a = {}
    if DEVINE.is_file():
        a["path"] = str(DEVINE)
        a["sha256"] = sha256_file(DEVINE)
        data = load_json(DEVINE)
        a["n"] = len(data) if isinstance(data, list) else None
        a["top_keys"] = top_keys(data)
        stats = analyze_devine(data)
        rows = stats.pop("rows")
        a["stats"] = stats
        # CSV
        with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(
                [
                    "name",
                    "项序号",
                    "title",
                    "description前30字",
                    "outline字数",
                    "title是否出现在某条第一项",
                ]
            )
            for r in rows:
                w.writerow(
                    [
                        r["name"],
                        r["idx"],
                        r["title"],
                        r["desc30"],
                        r["outline_len"],
                        "是" if r["title_is_first_somewhere"] else "否",
                    ]
                )
        a["csv"] = str(OUT_CSV)
        a["csv_rows"] = len(rows)
    else:
        a["path"] = str(DEVINE)
        a["error"] = "未找到"
    result["a"] = a

    # 2380 set
    lex = build_2380(CLASS4)
    expanded = set(lex["expanded_names"])
    variants = set(lex["variants"])
    result["lex2380"] = {
        k: v
        for k, v in lex.items()
        if k not in ("expanded_names", "variants")
    }
    result["lex2380"]["paren_pairs"] = PAREN_PAIRS
    if a.get("stats"):
        data = load_json(DEVINE)
        names = [x["name"] for x in data]
        in_set = [n for n in names if n in variants]
        out_set = [n for n in names if n not in variants]
        # which spelling matched
        spelling = []
        for n in names:
            if n in expanded:
                spelling.append((n, "exact"))
            elif n.replace("路得马丁", "路德马丁") in expanded:
                spelling.append((n, "via_路得→路德"))
            elif n.replace("路德马丁", "路得马丁") in expanded:
                spelling.append((n, "via_路德→路得"))
            else:
                spelling.append((n, "missing"))
        result["name_vs_2380"] = {
            "n_in": len(in_set),
            "n_out": len(out_set),
            "out_names": out_set,
            "dup_names": a["stats"]["dup_names"],
            "lude_spelling_hits": [x for x in spelling if "via_" in x[1] or x[0] in ("路德马丁", "路得马丁")],
        }

    result["diff_189_187"] = find_189_vs_187()

    # (b) organic
    b = {}
    if ORG_QA4.is_file():
        b["path"] = str(ORG_QA4)
        b["sha256"] = sha256_file(ORG_QA4)
        data = load_json(ORG_QA4)
        b["n"] = len(data) if isinstance(data, list) else None
        b["top_keys"] = top_keys(data)
        names = [x.get("name") for x in data] if isinstance(data, list) else []
        b["n_unique_names"] = len(set(names))
        b["dup_names"] = [n for n, c in Counter(names).items() if c > 1]
        variants = set(lex["variants"])
        missing = [n for n in names if n not in variants]
        b["n_in_2380"] = len(names) - len(missing)
        b["missing"] = missing
    else:
        b["error"] = "未找到"
        b["path"] = str(ORG_QA4)
    result["b"] = b

    # also desktop organic files
    desk_orgs = []
    for p in DESK_SPECIAL.glob("*organic_advance*"):
        try:
            d = load_json(p)
            desk_orgs.append(
                {
                    "path": str(p),
                    "sha256": sha256_file(p),
                    "n": len(d) if isinstance(d, list) else None,
                    "keys": top_keys(d),
                }
            )
        except Exception as e:
            desk_orgs.append({"path": str(p), "error": str(e)})
    result["desk_organic"] = desk_orgs

    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", OUT_JSON)
    print("CSV", OUT_CSV, "rows", a.get("csv_rows"))
    print("T1", a.get("stats", {}).get("T1_first_titles"))
    print("T2", a.get("stats", {}).get("T2_all_titles"))
    print("T3", a.get("stats", {}).get("T3_norm_titles"))
    print("2380", result["lex2380"]["set_2380_size"], "class4", result["lex2380"]["class4_n"])
    print("name_in", result.get("name_vs_2380", {}).get("n_in"), "out", result.get("name_vs_2380", {}).get("out_names"))
    print("discarded", result["diff_189_187"].get("discarded"))
    print("organic", b.get("n"), "in2380", b.get("n_in_2380"))


if __name__ == "__main__":
    main()
