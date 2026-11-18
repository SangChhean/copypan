# -*- coding: utf-8 -*-
"""Probe5-B: 词表写法一致性（只读）。"""
from __future__ import annotations

import csv
import json
import re
from collections import Counter
from pathlib import Path

REPO = Path(r"G:\copypan")
NOTES = REPO / "qa4" / "notes"
OUT_JSON = NOTES / "probe5" / "b_result.json"
OUT_CSV = NOTES / "lexicon_consistency.csv"

DESK = Path(r"C:\Users\28121\Desktop\可导入资料")
CLASS4 = DESK / "2 特殊标注" / "【intrinsic_significance】2372词条内在意义分类.json"
DOCS = REPO / "docs" / "panai4_graph"
TXT2373 = DOCS / "2373个词条（已确定一一对应为concept节点）.txt"
MAP_TRUNK = DOCS / "主恢复真理词典_词条主干枝子映射 (1).json"
MAP_TAG = DOCS / "主恢复真理词典_标签映射_已校对 (1).json"
TXT12 = DOCS / "12大类与91小类的对应关系.txt"
ANN_QA4 = REPO / "qa4" / "data" / "graph_annotations"
ANN_MIC = REPO / "back_mic" / "backend" / "panai4" / "data" / "graph_annotations"
NOTES_ZUI = NOTES / "zui_neizai_133_draft.txt"
NOTES_RECON = NOTES / "lexicon_reconcile.csv"
QA4_DOCS = REPO / "qa4" / "docs"

TERMS = ("路得马丁", "路德马丁", "城市")


def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def iter_files() -> list[Path]:
    files: list[Path] = []
    # desktop 可导入资料 all json/txt/csv
    if DESK.is_dir():
        for p in DESK.rglob("*"):
            if p.is_file() and p.suffix.lower() in {".json", ".txt", ".csv"}:
                files.append(p)
    # docs specific
    for p in (TXT2373, MAP_TRUNK, MAP_TAG, TXT12):
        files.append(p)
    # also 2372 txt if exists
    t2372 = DOCS / "2372个词条（已确定一一对应为concept节点）.txt"
    files.append(t2372)
    # annotations
    for root in (ANN_QA4, ANN_MIC):
        if root.is_dir():
            for p in root.rglob("*"):
                if p.is_file() and p.suffix.lower() in {".json", ".txt", ".csv", ".md"}:
                    files.append(p)
    # notes drafts
    files.extend([NOTES_ZUI, NOTES_RECON])
    # dedupe
    seen = set()
    out = []
    for p in files:
        try:
            key = str(p.resolve())
        except Exception:
            key = str(p)
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def is_standalone_line(line: str, term: str) -> bool:
    s = line.strip()
    # strip BOM / numbering
    s2 = re.sub(r"^\d+[\.、\s]*", "", s)
    return s == term or s2 == term


def count_in_text_body(text: str, term: str) -> int:
    return text.count(term)


def analyze_file(p: Path) -> dict:
    row = {
        "path": str(p),
        "exists": p.is_file(),
        "as_name_路得马丁": 0,
        "as_name_路德马丁": 0,
        "as_name_城市": 0,
        "body_路得马丁": 0,
        "body_路德马丁": 0,
        "need_change": False,
        "name_hits": [],
        "note": "",
    }
    if not p.is_file():
        row["note"] = "未找到"
        return row

    raw = p.read_text(encoding="utf-8", errors="replace")
    suf = p.suffix.lower()

    # body counts (always)
    row["body_路得马丁"] = count_in_text_body(raw, "路得马丁")
    row["body_路德马丁"] = count_in_text_body(raw, "路德马丁")

    name_lude = 0
    name_lude_correct = 0
    name_city = 0

    if suf == ".json":
        try:
            data = json.loads(raw)
        except Exception as e:
            row["note"] = f"json_parse_fail:{e}"
            # fallback: treat as text for name? no
            data = None
        if data is not None:
            def walk(o, path=""):
                nonlocal name_lude, name_lude_correct, name_city
                if isinstance(o, dict):
                    # 词条名/标题字段；边文件 from/to 亦视为节点名引用
                    for k in ("name", "title", "from", "to", "src", "target"):
                        if k in o and isinstance(o[k], str):
                            v = o[k]
                            if v == "路得马丁":
                                name_lude += 1
                                row["name_hits"].append(f"{path}.{k}=路得马丁")
                            elif v == "路德马丁":
                                name_lude_correct += 1
                                row["name_hits"].append(f"{path}.{k}=路德马丁")
                            elif v == "城市":
                                name_city += 1
                                row["name_hits"].append(f"{path}.{k}=城市")
                    # words[].name
                    if "words" in o and isinstance(o["words"], list):
                        for i, w in enumerate(o["words"]):
                            walk(w, f"{path}.words[{i}]")
                    for k, v in o.items():
                        if k in ("name", "title", "words", "from", "to", "src", "target"):
                            continue
                        if isinstance(v, (dict, list)):
                            walk(v, f"{path}.{k}")
                elif isinstance(o, list):
                    for i, item in enumerate(o):
                        walk(item, f"{path}[{i}]")

            walk(data)
    elif suf in {".txt", ".csv", ".md"}:
        for i, line in enumerate(raw.splitlines(), 1):
            for term, counter_name in (
                ("路得马丁", "lude"),
                ("路德马丁", "lude_ok"),
                ("城市", "city"),
            ):
                if is_standalone_line(line, term):
                    if term == "路得马丁":
                        name_lude += 1
                    elif term == "路德马丁":
                        name_lude_correct += 1
                    else:
                        name_city += 1
                    row["name_hits"].append(f"L{i}:{term}")

    row["as_name_路得马丁"] = name_lude
    row["as_name_路德马丁"] = name_lude_correct
    row["as_name_城市"] = name_city

    # need_change: name-field 路得马丁 or 城市; also body 路得马丁 in source files
    # For report CSV: 是否需要改
    row["need_change"] = bool(
        name_lude or name_city or (row["body_路得马丁"] > 0 and name_lude == 0 and "notes" not in str(p).replace("\\", "/").lower())
    )
    # refine: drafts in qa4/notes are record-only; still flag if they contain wrong spelling as name
    # For notes drafts: record only, mark need_change False unless as_name
    p_s = str(p).replace("\\", "/")
    if "/qa4/notes/" in p_s or "\\qa4\\notes\\" in str(p):
        row["need_change"] = bool(name_lude or name_city)
        row["note"] = (row["note"] + ";notes_record_only").strip(";")

    # body counts include name occurrences; for reporting "正文" we subtract name-as-exact if possible
    # Spec: 作为正文出现的「路得马丁」「路德马丁」次数（只这两个）
    # Keep total body counts as raw substring counts (includes name fields).
    return row


def load_name_sets() -> dict:
    """四个来源词名集合。"""
    sets = {}

    # 2373 清单
    if TXT2373.is_file():
        names = []
        for line in TXT2373.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            s2 = re.sub(r"^\d+[\.、\s]*", "", s).strip()
            if s2:
                names.append(s2)
        sets["2373清单"] = set(names)
    else:
        sets["2373清单"] = None

    # 主干枝映射
    if MAP_TRUNK.is_file():
        data = load_json(MAP_TRUNK)
        names = []
        if isinstance(data, list):
            for x in data:
                if isinstance(x, dict) and x.get("name"):
                    names.append(x["name"])
        sets["主干枝映射"] = set(names)
    else:
        sets["主干枝映射"] = None

    # 四档分类
    if CLASS4.is_file():
        data = load_json(CLASS4)
        words = data.get("words") if isinstance(data, dict) else []
        names = [w["name"] for w in words if isinstance(w, dict) and w.get("name")]
        sets["四档分类"] = set(names)
    else:
        sets["四档分类"] = None

    # truth_dictionary title
    td = ANN_QA4 / "truth_dictionary_3a3b.json"
    if td.is_file():
        data = load_json(td)
        names = [x.get("title") for x in data if isinstance(x, dict) and x.get("title")]
        sets["truth_dictionary_3a3b"] = set(names)
    else:
        sets["truth_dictionary_3a3b"] = None

    return sets


def normalize_name(n: str) -> str | None:
    """路得→路德；去掉城市。返回 None 表示删除。"""
    if n == "城市":
        return None
    return n.replace("路得马丁", "路德马丁")


def compare_sets(raw_sets: dict) -> dict:
    labels = [k for k, v in raw_sets.items() if v is not None]
    raw_sizes = {k: len(raw_sets[k]) for k in labels}
    # normalized
    norm = {}
    for k in labels:
        s = set()
        for n in raw_sets[k]:
            nn = normalize_name(n)
            if nn is not None:
                s.add(nn)
        norm[k] = s
    norm_sizes = {k: len(norm[k]) for k in labels}

    pairwise_raw = {}
    pairwise_norm = {}
    for i, a in enumerate(labels):
        for b in labels[i + 1 :]:
            only_a = sorted(raw_sets[a] - raw_sets[b])
            only_b = sorted(raw_sets[b] - raw_sets[a])
            pairwise_raw[f"{a} vs {b}"] = {
                "equal": raw_sets[a] == raw_sets[b],
                "only_a": only_a,
                "only_b": only_b,
            }
            only_a_n = sorted(norm[a] - norm[b])
            only_b_n = sorted(norm[b] - norm[a])
            pairwise_norm[f"{a} vs {b}"] = {
                "equal": norm[a] == norm[b],
                "only_a": only_a_n,
                "only_b": only_b_n,
            }
    return {
        "raw_sizes": raw_sizes,
        "norm_sizes": norm_sizes,
        "pairwise_raw": pairwise_raw,
        "pairwise_norm": pairwise_norm,
        "raw_has": {
            k: {
                "路得马丁": "路得马丁" in raw_sets[k],
                "路德马丁": "路德马丁" in raw_sets[k],
                "城市": "城市" in raw_sets[k],
            }
            for k in labels
        },
    }


def find_md_mentions() -> list[dict]:
    hits = []
    for root in (DOCS, QA4_DOCS):
        if not root.is_dir():
            continue
        for p in root.rglob("*.md"):
            try:
                lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            except Exception:
                continue
            for i, line in enumerate(lines, 1):
                if "路得马丁" in line or "路德马丁" in line or re.search(r"(?<![^\s，,、：:])城市(?![^\s，,、。；;：:])", line) or "城市" == line.strip():
                    # record if either term present; for 城市 be careful - record line if 城市 as word mention in lexicon context
                    if "路得马丁" in line or "路德马丁" in line or "城市" in line:
                        hits.append(
                            {
                                "path": str(p),
                                "line": i,
                                "snip": line.strip()[:80],
                                "has_路得": "路得马丁" in line,
                                "has_路德": "路德马丁" in line,
                                "has_城市": "城市" in line,
                            }
                        )
    return hits


def main():
    files = iter_files()
    rows = [analyze_file(p) for p in files]

    # also ensure CLASS4 etc listed even if missed
    required = [
        CLASS4,
        TXT2373,
        MAP_TRUNK,
        MAP_TAG,
        TXT12,
        ANN_QA4 / "truth_dictionary_3a3b.json",
        ANN_QA4 / "organic_advance.json",
        ANN_MIC / "truth_dictionary_3a3b.json",
        ANN_MIC / "organic_advance.json",
        NOTES_ZUI,
        NOTES_RECON,
    ]
    have = {str(r["path"]) for r in rows}
    for p in required:
        if str(p) not in have:
            rows.append(analyze_file(p))

    sets = load_name_sets()
    cmp = compare_sets(sets)
    md_hits = find_md_mentions()

    # change list: from name_hits
    changes = []
    for r in rows:
        if not r["exists"]:
            continue
        for hit in r["name_hits"]:
            if "路得马丁" in hit:
                changes.append(
                    {
                        "file": r["path"],
                        "loc": hit,
                        "current": "路得马丁",
                        "should": "路德马丁",
                    }
                )
            if hit.endswith("=城市") or hit.endswith(":城市"):
                changes.append(
                    {
                        "file": r["path"],
                        "loc": hit,
                        "current": "城市",
                        "should": "删除",
                    }
                )

    result = {
        "script": "qa4/notes/probe5/b_lexicon.py",
        "n_files_scanned": len(rows),
        "rows": rows,
        "set_compare": cmp,
        "md_mentions": md_hits,
        "change_list": changes,
    }
    OUT_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "路径",
                "路得马丁_词条名次数",
                "路德马丁_词条名次数",
                "城市_词条名次数",
                "路得马丁_正文次数",
                "路德马丁_正文次数",
                "是否需要改",
            ]
        )
        for r in rows:
            w.writerow(
                [
                    r["path"],
                    r["as_name_路得马丁"],
                    r["as_name_路德马丁"],
                    r["as_name_城市"],
                    r["body_路得马丁"],
                    r["body_路德马丁"],
                    "是" if r["need_change"] else "否",
                ]
            )

    print("WROTE", OUT_JSON)
    print("CSV", OUT_CSV)
    print("files", len(rows))
    print("changes", len(changes))
    print("raw_sizes", cmp["raw_sizes"])
    print("norm equal pairs", {k: v["equal"] for k, v in cmp["pairwise_norm"].items()})
    print("raw unequal", {k: v for k, v in cmp["pairwise_raw"].items() if not v["equal"]})


if __name__ == "__main__":
    main()
