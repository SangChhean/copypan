# -*- coding: utf-8 -*-
"""Probe6-A: organic_advance 新版结构（只读）。"""
from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(r"G:\copypan")
NOTES = REPO / "qa4" / "notes" / "probe6"
OUT = NOTES / "a_result.json"

NEW = REPO / "qa4" / "data" / "graph_annotations" / "organic_advance.json"
OLD = Path(
    r"C:\Users\28121\Desktop\可导入资料\2 特殊标注"
    r"\【organic_advance】生机关联的进展.json"
)
STATE = REPO / "logs" / "import_annotation_organic_advance_state.json"
IMPORT_MD = REPO / "docs" / "panai4_graph" / "import_organic_advance.md"
CHECK_MD = REPO / "docs" / "panai4_graph" / "check_organic_advance.md"

CN_HEAVENLY = "壹贰叁肆伍陆柒捌玖拾"
CN_EARTHLY = "一二三四五六七八九十"


def sha16(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()[:16]


def median(xs: list[int | float]) -> float:
    if not xs:
        return float("nan")
    ys = sorted(xs)
    m = len(ys) // 2
    return float(ys[m]) if len(ys) % 2 else 0.5 * (ys[m - 1] + ys[m])


def line_lead_type(line: str) -> str:
    s = line.strip()
    if not s:
        return "空行"
    # 去掉全角空格后看行首
    s2 = s.lstrip("　 \t")
    if not s2:
        return "空行"
    ch = s2[0]
    if ch in CN_HEAVENLY:
        return "天干序号(壹贰…)"
    if ch in CN_EARTHLY:
        return "地支/小写中文数(一二…)"
    if ch.isdigit() or (ch in "０１２３４５６７８９"):
        return "阿拉伯数字"
    return "其他"


def is_heading_line(line: str) -> bool:
    s = line.strip().lstrip("　 \t")
    if not s:
        return False
    # 典型标题：天干/地支开头，且不太长
    if s[0] in CN_HEAVENLY or (s[0] in CN_EARTHLY and ("、" in s[:4] or "　" in s[:4] or len(s) < 40)):
        return True
    return False


def old_content_len(rec: dict) -> int:
    """旧版 content_1..6 多为 list[dict]；字数按 JSON 序列化字符计。"""
    total = 0
    for k in ("content_1", "content_2", "content_3", "content_4", "content_5", "content_6"):
        v = rec.get(k)
        if isinstance(v, str):
            total += len(v)
        elif isinstance(v, list):
            for item in v:
                if isinstance(item, dict):
                    for kk in ("outline", "title", "book", "date", "source"):
                        vv = item.get(kk)
                        if isinstance(vv, str):
                            total += len(vv)
                elif isinstance(item, str):
                    total += len(item)
            total += len(json.dumps(v, ensure_ascii=False))  # 结构开销一并计入总序列化
            # 上面会双计；改为只 JSON：
        elif v is not None:
            total += len(json.dumps(v, ensure_ascii=False))
    # 重算为纯 JSON 长度，避免双计
    total = 0
    for k in ("content_1", "content_2", "content_3", "content_4", "content_5", "content_6"):
        v = rec.get(k)
        if v is None:
            continue
        if isinstance(v, str):
            total += len(v)
        else:
            total += len(json.dumps(v, ensure_ascii=False))
    return total


def old_stage_names(rec: dict) -> set[str]:
    names = set()
    series = rec.get("series")
    if isinstance(series, str) and series.strip():
        names.add(series.strip())
        # 去编号前缀「1.xxx」
        m = re.match(r"^\d+\s*[\.、．]?\s*(.+)$", series.strip())
        if m:
            names.add(m.group(1).strip())
    stages = rec.get("stages")
    if isinstance(stages, dict):
        for v in stages.values():
            if isinstance(v, str) and v.strip():
                names.add(v.strip())
    elif isinstance(stages, list):
        for s in stages:
            if isinstance(s, str) and s.strip():
                names.add(s.strip())
            elif isinstance(s, dict):
                for k in ("name", "title", "stage"):
                    if isinstance(s.get(k), str) and s[k].strip():
                        names.add(s[k].strip())
    return names


def main():
    result = {"script": "qa4/notes/probe6/a_organic.py"}
    h = hashlib.sha256(NEW.read_bytes()).hexdigest()
    result["new_path"] = str(NEW)
    result["new_sha256"] = h
    result["new_sha16"] = h[:16]
    if h[:16] != "2ab34918389a6640":
        result["stopped"] = True
        result["reason"] = f"SHA 前16位不符：{h[:16]}"
        OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print("STOP", result["reason"])
        return

    data = json.loads(NEW.read_text(encoding="utf-8"))
    result["top_type"] = type(data).__name__
    result["n"] = len(data) if isinstance(data, list) else None
    result["keys"] = sorted(data[0].keys()) if data else []

    content_types = Counter(type(x.get("content")).__name__ for x in data)
    result["content_types"] = dict(content_types)
    clens = [len(x["content"]) for x in data if isinstance(x.get("content"), str)]
    result["content_len"] = {
        "min": min(clens) if clens else None,
        "median": median(clens) if clens else None,
        "max": max(clens) if clens else None,
        "n_str": len(clens),
    }
    tlens = [len(x.get("title") or "") for x in data if isinstance(x.get("title"), str)]
    # 字数分布：按区间
    bins = Counter()
    for L in tlens:
        if L <= 10:
            bins["1-10"] += 1
        elif L <= 20:
            bins["11-20"] += 1
        elif L <= 30:
            bins["21-30"] += 1
        else:
            bins["31+"] += 1
    result["title_len"] = {
        "min": min(tlens) if tlens else None,
        "median": median(tlens) if tlens else None,
        "max": max(tlens) if tlens else None,
        "bins": dict(bins),
    }

    # name vs title
    by_name = defaultdict(list)
    for x in data:
        by_name[x.get("name")].append(x)
    name_counts = {n: len(xs) for n, xs in by_name.items()}
    multi = {n: c for n, c in name_counts.items() if c > 1}
    result["n_unique_names"] = len(by_name)
    result["name_multi"] = multi
    bible_rows = []
    for x in by_name.get("圣经", []):
        c = x.get("content") or ""
        bible_rows.append(
            {
                "title": (x.get("title") or "")[:30],
                "content_len": len(c) if isinstance(c, str) else None,
                "content_head30": (c[:30] if isinstance(c, str) else str(type(c))),
            }
        )
    result["bible_rows"] = bible_rows

    # content structure (assume str dominant)
    lead = Counter()
    stage_heading = 0
    heading_samples = []
    list_dict_info = []
    for x in data:
        c = x.get("content")
        if isinstance(c, str):
            for line in c.splitlines():
                lead[line_lead_type(line)] += 1
                if ("阶段" in line or "时期" in line) and is_heading_line(line):
                    stage_heading += 1
                if is_heading_line(line) and len(heading_samples) < 5:
                    heading_samples.append(line.strip()[:30])
                elif ("阶段" in line or "时期" in line) and len(heading_samples) < 5:
                    # also collect stage/period lines as heading-ish
                    pass
            # also collect first 5 lines that look like 天干 titles specifically
        elif isinstance(c, list):
            list_dict_info.append({"name": x.get("name"), "type": "list", "len": len(c)})
        elif isinstance(c, dict):
            list_dict_info.append(
                {"name": x.get("name"), "type": "dict", "keys": sorted(c.keys())}
            )
    # better heading samples: lines starting with 天干 and containing 阶段/时期, else 天干
    heading_samples = []
    stage_lines = []
    for x in data:
        c = x.get("content")
        if not isinstance(c, str):
            continue
        for line in c.splitlines():
            s = line.strip()
            if "阶段" in s or "时期" in s:
                stage_lines.append(s[:30])
            if s and s[0] in CN_HEAVENLY and len(heading_samples) < 5:
                heading_samples.append(s[:30])
    result["content_str_stats"] = {
        "lead_types": dict(lead),
        "stage_or_period_lines": len(stage_lines),
        "stage_or_period_samples": stage_lines[:5],
        "heading_samples_heavenly": heading_samples[:5],
        "non_str": list_dict_info,
    }

    # --- old vs new ---
    old_sha = hashlib.sha256(OLD.read_bytes()).hexdigest()
    result["old_path"] = str(OLD)
    result["old_sha16"] = old_sha[:16]
    old = json.loads(OLD.read_text(encoding="utf-8"))
    old_names = {x.get("name") for x in old}
    new_names = set(by_name.keys())
    result["only_new_names"] = sorted(new_names - old_names)
    result["only_old_names"] = sorted(old_names - new_names)
    # content len ratio for shared names
    old_by = {x["name"]: x for x in old}
    ratios = []
    title_match = 0
    shared = sorted(new_names & old_names)
    for n in shared:
        # new may have multiple; take first for ratio, also all titles
        new_recs = by_name[n]
        old_rec = old_by[n]
        old_len = old_content_len(old_rec) or 1
        for nr in new_recs:
            nl = len(nr.get("content") or "") if isinstance(nr.get("content"), str) else 0
            ratios.append(nl / old_len)
            t = (nr.get("title") or "").strip()
            if t and t in old_stage_names(old_rec):
                title_match += 1
    result["shared_n"] = len(shared)
    result["content_len_ratio_median"] = median(ratios) if ratios else None
    result["title_match_series_or_stages"] = title_match
    result["title_match_note"] = "新版每条 title 与旧版同 name 的 series/stages 名称精确相同的条数"

    # import relation
    imp = {"state": None, "md": None}
    if STATE.is_file():
        st = json.loads(STATE.read_text(encoding="utf-8"))
        written = None
        file_names = st.get("file_names")
        if isinstance(st.get("import"), dict):
            written = st["import"].get("written")
        verify = st.get("verify") or {}
        graph_names = None
        if isinstance(verify, dict):
            # try find name set
            for k in ("names", "written_names", "anno_names", "file_only", "graph_only"):
                if k in verify:
                    pass
        imp["state"] = {
            "file": st.get("file"),
            "written": written,
            "expect_anno": st.get("expect_anno"),
            "file_names_n": len(file_names) if isinstance(file_names, list) else None,
            "file_names_sample": (file_names[:5] if isinstance(file_names, list) else None),
            "sha_related": {
                k: st.get(k)
                for k in (
                    "existing_anno_sha256",
                    "sha_import_before",
                    "sha_import_after_check",
                )
                if k in st
            },
            "copy": st.get("copy"),
            "plan_summary": st.get("plan_summary"),
        }
        if isinstance(file_names, list):
            fn_set = set(file_names)
            imp["state"]["file_names_vs_new69"] = {
                "file_n": len(fn_set),
                "new_unique_n": len(new_names),
                "equal_to_new": fn_set == new_names,
                "only_in_import": sorted(fn_set - new_names)[:20],
                "only_in_new": sorted(new_names - fn_set)[:20],
            }
    if IMPORT_MD.is_file():
        text = IMPORT_MD.read_text(encoding="utf-8")
        snips = []
        for line in text.splitlines():
            if any(
                k in line
                for k in ("记录数", "写入", "SHA", "sha", "找到", "n_records", "written")
            ):
                snips.append(line.strip()[:120])
        imp["md_path"] = str(IMPORT_MD)
        imp["md_snips"] = snips[:15]
    if CHECK_MD.is_file():
        imp["check_md"] = str(CHECK_MD)
    result["import_info"] = imp

    # all copies in repo
    copies = []
    for p in REPO.rglob("organic_advance*.json"):
        if not p.is_file():
            continue
        # skip huge unrelated if any
        b = p.read_bytes()
        copies.append(
            {
                "path": str(p),
                "bytes": len(b),
                "sha16": hashlib.sha256(b).hexdigest()[:16],
            }
        )
    # also desktop? user asked 仓库内
    result["repo_copies"] = copies

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print("WROTE", OUT)
    print("n", result["n"], "unique", result["n_unique_names"], "multi", multi)
    print("content_len", result["content_len"])
    print("only_new", result["only_new_names"])
    print("only_old", result["only_old_names"])
    print("ratio_med", result["content_len_ratio_median"], "title_match", title_match)
    print("import", imp.get("state", {}).get("file_names_vs_new69"))


if __name__ == "__main__":
    main()
