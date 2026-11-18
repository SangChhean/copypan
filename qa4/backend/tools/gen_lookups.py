# -*- coding: utf-8 -*-
"""生成 qa4/data/lookups 查表（阶段 0）。

路径全部来自 --sources JSON；不写死盘符。
先写临时目录，全部通过后再原子替换。
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

# 允许直接 python qa4/backend/tools/gen_lookups.py
_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from lookups.name_norm import NameNorm  # noqa: E402

# inventory_v4_pre._PAREN_PAIRS：（外词, 内词）
PAREN_PAIRS: list[tuple[str, str]] = [
    ("产生男孩子", "产生得胜者"),
    ("晨晨复兴", "晨兴"),
    ("妇人", "女人"),
    ("挂虑", "忧虑"),
    ("火湖", "地狱"),
    ("扩大", "显大"),
    ("扩增", "扩展"),
    ("那灵的浇灌", "圣灵的浇灌"),
]
INNER_TO_OUTER = {inner: outer for outer, inner in PAREN_PAIRS}
COMBINED_TO_OUTER = {f"{outer}（{inner}）": outer for outer, inner in PAREN_PAIRS}

TIER_ORDER = ("最内在", "外在", "内在", "显出为外在")

EXPECT = {
    "lexicon_main": 2372,
    "lexicon_expanded": 2380,
    "tier_最内在": 133,
    "tier_外在": 1658,
    "tier_内在": 497,
    "tier_显出为外在": 84,
    "tier_exp_最内在": 133,
    "tier_exp_外在": 1661,
    "tier_exp_内在": 499,
    "tier_exp_显出为外在": 87,
    "zui_neizai": 133,
    "other": 2239,
    "wenji_year_rows": 42,
    "no_year_titles": 61,
    "no_year_chunks": 5551,
    "wenji_volume_rows": 1293,
    "life_books": 63,
    "cwwn_books": 106,
    "others_books": 3,
    "feasts": 259,
    "hymn_overlap": 398,
}

CN_DIGIT = {
    "零": 0,
    "〇": 0,
    "○": 0,
    "一": 1,
    "二": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
RE_YEAR_RANGE = re.compile(
    r"([零〇○一二三四五六七八九]{4})至([零〇○一二三四五六七八九]{4})年"
)
RE_YEAR_SINGLE = re.compile(r"([零〇○一二三四五六七八九]{4})年")
RE_CE_LABEL = re.compile(r"(第[零〇○一二三四五六七八九十百千两]+册)")
RE_CWWN = re.compile(
    r"倪柝声文集第([零〇○一二三四五六七八九十百千两]+)辑第([零〇○一二三四五六七八九十百千两]+)册"
)


class GenError(RuntimeError):
    pass


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _write_json(path: Path, obj: Any) -> tuple[int, str]:
    text = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    data = text.encode("utf-8")  # 无 BOM
    path.write_bytes(data)
    return len(data), _sha256_bytes(data)


def _write_csv_bom(path: Path, rows: list[dict], fieldnames: list[str]) -> tuple[int, str]:
    # UTF-8 带 BOM
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for row in rows:
            w.writerow({k: row.get(k, "") for k in fieldnames})
    data = path.read_bytes()
    return len(data), _sha256_bytes(data)


def _cn4_to_int(s: str) -> Optional[int]:
    try:
        return (
            1000 * CN_DIGIT[s[0]]
            + 100 * CN_DIGIT[s[1]]
            + 10 * CN_DIGIT[s[2]]
            + CN_DIGIT[s[3]]
        )
    except Exception:
        return None


def _cn_num_to_int(s: str) -> Optional[int]:
    """简易中文数字（辑/册）。"""
    if not s:
        return None
    digits = {
        "零": 0,
        "〇": 0,
        "○": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    units = {"十": 10, "百": 100, "千": 1000}
    if s.isdigit():
        return int(s)
    total = 0
    num = 0
    for ch in s:
        if ch in digits:
            num = digits[ch]
        elif ch in units:
            unit = units[ch]
            if num == 0:
                num = 1
            total += num * unit
            num = 0
        else:
            return None
    return total + num


def year_mark_from_book_title(title: str) -> Optional[str]:
    """从 book_title 取年份标记：只看第一个全角逗号前的册名头。

    复现技术版口径：42 行年标记；无年份书名 61 / 5551 段。
    """
    head = title.split("，", 1)[0]
    m = RE_YEAR_RANGE.search(head)
    if m:
        a, b = _cn4_to_int(m.group(1)), _cn4_to_int(m.group(2))
        if a is not None and b is not None:
            return f"{a}\u2013{str(b)[-2:]}"
    m = RE_YEAR_SINGLE.search(head)
    if m:
        y = _cn4_to_int(m.group(1))
        if y is not None:
            return str(y)
    return None


def _resolve_path(raw: Any) -> Optional[Path]:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s.startswith("填写"):
        return None
    p = Path(s)
    return p if p.exists() else None


def load_sources(path: Path) -> tuple[dict[str, Optional[Path]], list[str]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    keys = [
        "intrinsic_significance",
        "trunk_branch_map",
        "truth_dictionary_3a3b",
        "devine_argument",
        "high_peak_content",
        "organic_advance",
        "text_cwwl_shards",
        "outline_12490",
        "wenji_volume_draft_csv",
        "text_life_shards",
        "text_cwwn_shards",
        "text_others_shards",
        "outline_feasts",
        "hymns",
    ]
    resolved: dict[str, Optional[Path]] = {}
    missing: list[str] = []
    for k in keys:
        p = _resolve_path(data.get(k))
        resolved[k] = p
        if p is None:
            missing.append(k)
    return resolved, missing


def iter_jsonl_records(root: Path) -> Iterable[dict]:
    if root.is_file():
        files = [root]
    else:
        files = sorted(root.rglob("*.jsonl")) + sorted(root.rglob("*.json"))
    for fp in files:
        # 跳过巨大非行式？对 .json 若是 JSONL（每行一个对象）按行读；若是数组则 loads
        if fp.suffix == ".json":
            # 尝试按行
            used_line = False
            with fp.open(encoding="utf-8") as f:
                first = f.readline()
                if not first:
                    continue
                try:
                    obj = json.loads(first)
                    if isinstance(obj, dict):
                        used_line = True
                        yield obj
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            yield json.loads(line)
                except json.JSONDecodeError:
                    used_line = False
            if not used_line:
                data = json.loads(fp.read_text(encoding="utf-8"))
                if isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            yield item
            continue
        with fp.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)


def load_name_set_from_annotation(path: Path, name_key: str = "name") -> set[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict) and "words" in data:
        data = data["words"]
    out: set[str] = set()
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and name_key in item:
                out.add(str(item[name_key]))
            elif isinstance(item, str):
                out.add(item)
    elif isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, dict) and name_key in v:
                out.add(str(v[name_key]))
            else:
                out.add(str(k))
    return out


def load_3a3b_flags(path: Path) -> dict[str, dict[str, bool]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: dict[str, dict[str, bool]] = {}
    for item in data:
        name = str(item.get("title") or item.get("name") or "")
        if not name:
            continue
        c3a = item.get("content_3a")
        c3b = item.get("content_3b")
        out[name] = {
            "has_3a": bool(c3a) and str(c3a).strip() != "",
            "has_3b": bool(c3b) and str(c3b).strip() != "",
        }
    return out


def build_lexicon(
    sources: dict[str, Optional[Path]], norm: NameNorm
) -> tuple[Optional[list[dict]], dict[str, Any], list[str]]:
    """返回 (entries_or_None, stats, missing_keys)。"""
    missing = [
        k
        for k in (
            "intrinsic_significance",
            "trunk_branch_map",
            "truth_dictionary_3a3b",
            "devine_argument",
            "high_peak_content",
            "organic_advance",
        )
        if sources.get(k) is None
    ]
    # intrinsic 是权威；缺则无法生成
    if sources.get("intrinsic_significance") is None:
        return None, {"missing": missing}, missing

    raw = json.loads(sources["intrinsic_significance"].read_text(encoding="utf-8"))
    words = raw["words"] if isinstance(raw, dict) else raw

    def _canon_source_name(raw: str, *, context: str) -> Optional[str]:
        s = str(raw)
        if s in COMBINED_TO_OUTER:
            s = COMBINED_TO_OUTER[s]
        return norm.normalize(s, context=context)

    trunk_by: dict[str, dict] = {}
    if sources.get("trunk_branch_map"):
        for item in json.loads(sources["trunk_branch_map"].read_text(encoding="utf-8")):
            n = _canon_source_name(str(item.get("name") or ""), context="trunk_branch_map")
            if n is None:
                continue
            trunk_by[n] = item

    flags_3a3b: dict[str, dict[str, bool]] = {}
    if sources.get("truth_dictionary_3a3b"):
        raw_flags = load_3a3b_flags(sources["truth_dictionary_3a3b"])
        for k, v in raw_flags.items():
            nk = _canon_source_name(k, context="truth_dictionary_3a3b")
            if nk is not None:
                flags_3a3b[nk] = v

    def load_flag_names(key: str) -> set[str]:
        p = sources.get(key)
        if not p:
            return set()
        names = load_name_set_from_annotation(p)
        out: set[str] = set()
        for n in names:
            nk = _canon_source_name(n, context=key)
            if nk is not None:
                out.add(nk)
        return out

    set_devine = load_flag_names("devine_argument")
    set_hp = load_flag_names("high_peak_content")
    set_oa = load_flag_names("organic_advance")

    main_entries: list[dict] = []
    by_name: dict[str, dict] = {}
    tier_counter: Counter = Counter()

    for item in words:
        name_raw = str(item.get("name") or "")
        tier = str(item.get("category") or item.get("tier") or "")
        # 四档文件里 8 对以「外词（内词）」合写；主词表只保留外词
        if name_raw in COMBINED_TO_OUTER:
            name_raw = COMBINED_TO_OUTER[name_raw]
        name = norm.normalize(name_raw, context="intrinsic_significance")
        if name is None:
            continue
        # 查附属表时：合写名 / 外词 / 别名后的名都试
        tr = (
            trunk_by.get(name)
            or trunk_by.get(norm.normalize(str(item.get("name") or ""), context="trunk_lookup") or "")
            or {}
        )
        fl = flags_3a3b.get(name) or flags_3a3b.get(
            COMBINED_TO_OUTER.get(str(item.get("name") or ""), "")
        ) or {}
        # 合写名也可能出现在 3a3b / 标注里
        raw_name = str(item.get("name") or "")
        if not fl:
            fl = flags_3a3b.get(raw_name, {})
        entry = {
            "name": name,
            "tier": tier,
            "same_as": None,
            "trunk": tr.get("trunk"),
            "branch_directly": tr.get("branch_directly"),
            "branch_indirectly": tr.get("branch_indirectly") or [],
            "has_3a": bool(fl.get("has_3a")),
            "has_3b": bool(fl.get("has_3b")),
            "has_devine_argument": name in set_devine or raw_name in set_devine,
            "has_high_peak": name in set_hp or raw_name in set_hp,
            "has_organic_advance": name in set_oa or raw_name in set_oa,
        }
        # 合写形式也算进 flag 集合（标注里可能仍是合写）
        if raw_name in COMBINED_TO_OUTER:
            combined = raw_name
            entry["has_devine_argument"] = entry["has_devine_argument"] or combined in set_devine
            entry["has_high_peak"] = entry["has_high_peak"] or combined in set_hp
            entry["has_organic_advance"] = entry["has_organic_advance"] or combined in set_oa
            if not entry["has_3a"] or not entry["has_3b"]:
                fl2 = flags_3a3b.get(combined, {})
                entry["has_3a"] = entry["has_3a"] or bool(fl2.get("has_3a"))
                entry["has_3b"] = entry["has_3b"] or bool(fl2.get("has_3b"))
            tr2 = trunk_by.get(combined) or trunk_by.get(name) or {}
            if not entry.get("trunk"):
                entry["trunk"] = tr2.get("trunk")
                entry["branch_directly"] = tr2.get("branch_directly")
                entry["branch_indirectly"] = tr2.get("branch_indirectly") or []
        main_entries.append(entry)
        by_name[name] = entry
        tier_counter[tier] += 1

    # 括号展开：内词 same_as → 外词，档次沿用外词
    expanded = list(main_entries)
    for outer, inner in PAREN_PAIRS:
        outer_n = norm.normalize(outer, context="paren_outer") or outer
        inner_n = norm.normalize(inner, context="paren_inner") or inner
        base = by_name.get(outer_n)
        if base is None:
            raise GenError(f"括号外词不在主词表中：{outer_n}")
        if inner_n in by_name:
            raise GenError(f"括号内词已在主词表中，无法展开：{inner_n}")
        new_entry = {
            "name": inner_n,
            "tier": base["tier"],
            "same_as": outer_n,
            "trunk": base["trunk"],
            "branch_directly": base["branch_directly"],
            "branch_indirectly": list(base["branch_indirectly"] or []),
            "has_3a": base["has_3a"],
            "has_3b": base["has_3b"],
            "has_devine_argument": base["has_devine_argument"],
            "has_high_peak": base["has_high_peak"],
            "has_organic_advance": base["has_organic_advance"],
        }
        expanded.append(new_entry)

    tier_exp = Counter(e["tier"] for e in expanded)

    trunks = {e["trunk"] for e in main_entries if e.get("trunk")}
    branches: set[str] = set()
    for e in main_entries:
        if e.get("branch_directly"):
            branches.add(str(e["branch_directly"]))
        for b in e.get("branch_indirectly") or []:
            branches.add(str(b))

    stats = {
        "main_n": len(main_entries),
        "expanded_n": len(expanded),
        "tier_main": dict(tier_counter),
        "tier_expanded": dict(tier_exp),
        "trunk_n": len(trunks),
        "branch_n": len(branches),
        "has_3a": sum(1 for e in main_entries if e["has_3a"]),
        "has_3b": sum(1 for e in main_entries if e["has_3b"]),
        "has_devine_argument": sum(1 for e in main_entries if e["has_devine_argument"]),
        "has_high_peak": sum(1 for e in main_entries if e["has_high_peak"]),
        "has_organic_advance": sum(1 for e in main_entries if e["has_organic_advance"]),
        "missing_sources": missing,
    }
    return expanded, stats, missing


def build_zui_other(lexicon_expanded: list[dict]) -> tuple[list[str], list[str]]:
    main = [e for e in lexicon_expanded if not e.get("same_as")]
    zui = sorted(e["name"] for e in main if e["tier"] == "最内在")
    other = sorted(e["name"] for e in main if e["tier"] != "最内在")
    return zui, other


def build_wenji_year(
    cwwl_root: Path, outline_root: Optional[Path]
) -> tuple[list[dict], dict, dict]:
    title_chunks: Counter = Counter()
    for rec in iter_jsonl_records(cwwl_root):
        t = rec.get("book_title") or ""
        title_chunks[t] += 1

    mark_to_cwwl: dict[str, set[str]] = defaultdict(set)
    no_year: dict[str, int] = {}
    for title, n in title_chunks.items():
        mk = year_mark_from_book_title(title)
        if mk is None:
            no_year[title] = n
        else:
            mark_to_cwwl[mk].add(title)

    outline_titles: set[str] = set()
    if outline_root is not None:
        for rec in iter_jsonl_records(outline_root):
            author = rec.get("author") or ""
            title = rec.get("book_title") or ""
            if not title:
                continue
            # 李常受文集书名
            if "李常受文集" in title or author in ("李常受", "Witness Lee"):
                outline_titles.add(title)

    mark_to_outline: dict[str, set[str]] = defaultdict(set)
    for title in outline_titles:
        mk = year_mark_from_book_title(title)
        if mk is not None:
            mark_to_outline[mk].add(title)

    rows = []
    for mk in sorted(mark_to_cwwl.keys(), key=_mark_sort_key):
        rows.append(
            {
                "year_mark": mk,
                "text_cwwl_book_titles": sorted(mark_to_cwwl[mk]),
                "outline_12490_book_titles": sorted(mark_to_outline.get(mk, set())),
            }
        )

    no_year_obj = {
        "titles": [
            {"book_title": t, "n_chunks": no_year[t]}
            for t in sorted(no_year.keys())
        ],
        "title_count": len(no_year),
        "chunk_count": sum(no_year.values()),
    }
    stats = {
        "year_rows": len(rows),
        "no_year_titles": no_year_obj["title_count"],
        "no_year_chunks": no_year_obj["chunk_count"],
        "single_n": sum(1 for r in rows if "\u2013" not in r["year_mark"]),
        "range_n": sum(1 for r in rows if "\u2013" in r["year_mark"]),
    }
    return rows, no_year_obj, stats


def _mark_sort_key(mk: str):
    if "\u2013" in mk:
        a = int(mk.split("\u2013", 1)[0])
        return (a, 1, mk)
    return (int(mk), 0, mk)


def build_volume_csv(draft: Path) -> tuple[list[dict], list[str]]:
    with draft.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(r) for r in reader]
    return rows, fieldnames


def build_life_books(root: Path) -> list[dict]:
    msgs: dict[str, set] = defaultdict(set)
    chunks: Counter = Counter()
    for rec in iter_jsonl_records(root):
        t = rec.get("book_title") or ""
        if not t:
            continue
        chunks[t] += 1
        key = rec.get("message_number")
        if key is None:
            key = rec.get("message_key")
        msgs[t].add(key)
    return [
        {
            "book_title": t,
            "message_count": len(msgs[t]),
            "chunk_count": chunks[t],
        }
        for t in sorted(msgs.keys())
    ]


def build_cwwn_books(root: Path) -> list[dict]:
    chunks: Counter = Counter()
    for rec in iter_jsonl_records(root):
        t = rec.get("book_title") or ""
        if t:
            chunks[t] += 1
    out = []
    for t in sorted(chunks.keys()):
        m = RE_CWWN.search(t)
        series = _cn_num_to_int(m.group(1)) if m else None
        volume = _cn_num_to_int(m.group(2)) if m else None
        out.append(
            {
                "book_title": t,
                "series": series,
                "volume": volume,
                "chunk_count": chunks[t],
            }
        )
    return out


def build_others_books(root: Path) -> list[dict]:
    msgs: dict[str, set] = defaultdict(set)
    chunks: Counter = Counter()
    for rec in iter_jsonl_records(root):
        t = rec.get("book_title") or ""
        if not t:
            continue
        chunks[t] += 1
        key = rec.get("message_number")
        if key is None:
            key = rec.get("message_key")
        msgs[t].add(key)
    return [
        {
            "book_title": t,
            "message_count": len(msgs[t]),
            "chunk_count": chunks[t],
        }
        for t in sorted(msgs.keys())
    ]


def build_feasts(root: Path) -> list[dict]:
    seen: dict[tuple, dict] = {}
    for rec in iter_jsonl_records(root):
        year = rec.get("year")
        month = rec.get("month")
        name = rec.get("book_title") or rec.get("conference") or ""
        if year is None or month is None:
            # 尝试从 conference / book_title 解析 1997-06
            conf = str(rec.get("conference") or name)
            m = re.match(r"(\d{4})-(\d{2})", conf)
            if m:
                year = int(m.group(1))
                month = int(m.group(2))
        if year is None or month is None:
            continue
        month_i = int(month)
        month_code = f"{month_i:02d}"
        key = (int(year), month_code, str(name))
        if key not in seen:
            seen[key] = {
                "year": int(year),
                "month_code": month_code,
                "name": str(name),
            }
    return sorted(seen.values(), key=lambda r: (r["year"], r["month_code"], r["name"]))


def build_hymns(root: Path) -> dict:
    nums: dict[str, set[int]] = defaultdict(set)
    for rec in iter_jsonl_records(root):
        series = str(rec.get("series") or "")
        hn = rec.get("hymn_number")
        if series and hn is not None:
            try:
                nums[series].add(int(hn))
            except Exception:
                continue
    daben = sorted(nums.get("诗歌", set()))
    buchong = sorted(nums.get("补充本诗歌", set()))
    fu = sorted(nums.get("诗歌附", set()))
    overlap = sorted(set(daben) & set(buchong))
    return {
        "series": {
            "诗歌": {"min": 1, "max": 780, "count": len(daben), "numbers": daben},
            "补充本诗歌": {
                "min": 1,
                "max": 1005,
                "count": len(buchong),
                "numbers": buchong,
            },
            "诗歌附": {"min": 1, "max": 6, "count": len(fu), "numbers": fu},
        },
        "daben_buchong_number_overlap": len(overlap),
        "daben_buchong_overlap_numbers": overlap,
        "default_series": "诗歌",
        "note": "默认大本靠 series 字段（诗歌）。",
    }


def build_authors() -> list[dict]:
    return [
        {"id": "lee", "name": "李常受"},
        {"id": "nee", "name": "倪柝声"},
        {"id": "rcv", "name": "恢复本圣经"},
    ]


def _check(actual: int, expect: int, label: str, failures: list[str]) -> None:
    if actual != expect:
        failures.append(f"{label}: 实际={actual} 期望={expect} 差={actual - expect}")


def run(sources_path: Path, out_dir: Path, dry_run: bool) -> int:
    sources, missing_paths = load_sources(sources_path)
    print("=== sources_resolved ===")
    for k, p in sources.items():
        if p is None:
            print(f"  {k}: 缺来源")
        else:
            print(f"  {k}: {p}")

    aliases_path = _BACKEND / "lookups" / "aliases.json"
    norm = NameNorm.from_aliases_file(aliases_path)

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "missing_sources": missing_paths,
        "counts": {},
        "reports_only": {},
    }
    failures: list[str] = []
    outputs: dict[str, Any] = {}
    meta_counts: dict[str, int] = {}

    # --- lexicon ---
    lexicon, lex_stats, lex_missing = build_lexicon(sources, norm)
    if lexicon is None:
        print("lexicon: 缺来源（intrinsic_significance）— 跳过硬门禁写入")
        report["counts"]["lexicon"] = None
    else:
        print(
            f"lexicon main={lex_stats['main_n']} expanded={lex_stats['expanded_n']} "
            f"tiers_main={lex_stats['tier_main']} tiers_exp={lex_stats['tier_expanded']}"
        )
        print(
            f"  trunk_n={lex_stats['trunk_n']} branch_n={lex_stats['branch_n']} "
            f"(参考 12/91；不作通过条件)"
        )
        print(
            "  flags "
            f"3a={lex_stats['has_3a']} 3b={lex_stats['has_3b']} "
            f"devine={lex_stats['has_devine_argument']} "
            f"hp={lex_stats['has_high_peak']} oa={lex_stats['has_organic_advance']} "
            "(只报告)"
        )
        _check(lex_stats["main_n"], EXPECT["lexicon_main"], "lexicon 主词", failures)
        _check(
            lex_stats["expanded_n"],
            EXPECT["lexicon_expanded"],
            "lexicon 展开后",
            failures,
        )
        for tier in TIER_ORDER:
            _check(
                lex_stats["tier_main"].get(tier, 0),
                EXPECT[f"tier_{tier}"],
                f"tier 主词/{tier}",
                failures,
            )
            _check(
                lex_stats["tier_expanded"].get(tier, 0),
                EXPECT[f"tier_exp_{tier}"],
                f"tier 展开/{tier}",
                failures,
            )
        outputs["lexicon.json"] = lexicon
        meta_counts["lexicon.json"] = len(lexicon)
        report["counts"]["lexicon_main"] = lex_stats["main_n"]
        report["counts"]["lexicon_expanded"] = lex_stats["expanded_n"]
        report["reports_only"]["trunk_branch"] = {
            "trunk_n": lex_stats["trunk_n"],
            "branch_n": lex_stats["branch_n"],
            "ref": {"trunk": 12, "branch": 91},
        }
        report["reports_only"]["flags"] = {
            k: lex_stats[k]
            for k in (
                "has_3a",
                "has_3b",
                "has_devine_argument",
                "has_high_peak",
                "has_organic_advance",
            )
        }

        zui, other = build_zui_other(lexicon)
        print(f"zui_neizai={len(zui)} other={len(other)}")
        _check(len(zui), EXPECT["zui_neizai"], "zui_neizai_133", failures)
        _check(len(other), EXPECT["other"], "other_2239", failures)
        if set(zui) & set(other):
            failures.append("zui 与 other 有交集")
        if len(set(zui) | set(other)) != EXPECT["lexicon_main"]:
            failures.append(
                f"zui∪other 实际={len(set(zui)|set(other))} 期望={EXPECT['lexicon_main']}"
            )
        outputs["zui_neizai_133.json"] = zui
        outputs["other_2239.json"] = other
        meta_counts["zui_neizai_133.json"] = len(zui)
        meta_counts["other_2239.json"] = len(other)

    # --- wenji year ---
    if sources.get("text_cwwl_shards") is None:
        print("wenji_year_table: 缺来源 text_cwwl_shards")
    else:
        rows, no_year_obj, wstats = build_wenji_year(
            sources["text_cwwl_shards"], sources.get("outline_12490")
        )
        print(
            f"wenji_year rows={wstats['year_rows']} "
            f"(single={wstats['single_n']} range={wstats['range_n']}) "
            f"no_year titles={wstats['no_year_titles']} chunks={wstats['no_year_chunks']}"
        )
        _check(wstats["year_rows"], EXPECT["wenji_year_rows"], "wenji_year_table", failures)
        _check(
            wstats["no_year_titles"],
            EXPECT["no_year_titles"],
            "no_year_titles",
            failures,
        )
        _check(
            wstats["no_year_chunks"],
            EXPECT["no_year_chunks"],
            "no_year_chunks",
            failures,
        )
        outputs["wenji_year_table.json"] = rows
        outputs["no_year_titles.json"] = no_year_obj
        meta_counts["wenji_year_table.json"] = len(rows)
        meta_counts["no_year_titles.json"] = no_year_obj["title_count"]

    # --- volume csv ---
    vol_fields: list[str] = []
    if sources.get("wenji_volume_draft_csv") is None:
        print("wenji_volume_table: 缺来源 wenji_volume_draft_csv")
    else:
        vol_rows, vol_fields = build_volume_csv(sources["wenji_volume_draft_csv"])
        print(f"wenji_volume_table rows={len(vol_rows)}")
        _check(len(vol_rows), EXPECT["wenji_volume_rows"], "wenji_volume_table", failures)
        outputs["wenji_volume_table.csv"] = (vol_rows, vol_fields)
        meta_counts["wenji_volume_table.csv"] = len(vol_rows)

    # --- life / cwwn / others ---
    if sources.get("text_life_shards") is None:
        print("life_books: 缺来源")
    else:
        life = build_life_books(sources["text_life_shards"])
        print(f"life_books={len(life)}")
        _check(len(life), EXPECT["life_books"], "life_books", failures)
        outputs["life_books.json"] = life
        meta_counts["life_books.json"] = len(life)

    if sources.get("text_cwwn_shards") is None:
        print("cwwn_books: 缺来源")
    else:
        cwwn = build_cwwn_books(sources["text_cwwn_shards"])
        print(f"cwwn_books={len(cwwn)}")
        _check(len(cwwn), EXPECT["cwwn_books"], "cwwn_books", failures)
        outputs["cwwn_books.json"] = cwwn
        meta_counts["cwwn_books.json"] = len(cwwn)

    if sources.get("text_others_shards") is None:
        print("others_books: 缺来源")
    else:
        others = build_others_books(sources["text_others_shards"])
        print(f"others_books={len(others)}")
        _check(len(others), EXPECT["others_books"], "others_books", failures)
        outputs["others_books.json"] = others
        meta_counts["others_books.json"] = len(others)

    if sources.get("outline_feasts") is None:
        print("feasts: 缺来源")
    else:
        feasts = build_feasts(sources["outline_feasts"])
        print(f"feasts={len(feasts)}")
        _check(len(feasts), EXPECT["feasts"], "feasts", failures)
        outputs["feasts.json"] = feasts
        meta_counts["feasts.json"] = len(feasts)

    if sources.get("hymns") is None:
        print("hymn_series: 缺来源")
    else:
        hymns = build_hymns(sources["hymns"])
        print(
            f"hymn_series overlap={hymns['daben_buchong_number_overlap']} "
            f"诗歌={hymns['series']['诗歌']['count']} "
            f"补充本={hymns['series']['补充本诗歌']['count']} "
            f"附={hymns['series']['诗歌附']['count']}"
        )
        _check(
            hymns["daben_buchong_number_overlap"],
            EXPECT["hymn_overlap"],
            "hymn_overlap",
            failures,
        )
        outputs["hymn_series.json"] = hymns
        meta_counts["hymn_series.json"] = hymns["daben_buchong_number_overlap"]

    outputs["authors.json"] = build_authors()
    meta_counts["authors.json"] = len(outputs["authors.json"])
    print(f"authors={meta_counts['authors.json']}")

    # 别名/忽略日志
    outputs["name_norm_log.json"] = norm.logs
    meta_counts["name_norm_log.json"] = len(norm.logs)

    print("=== gate ===")
    if failures:
        for f in failures:
            print("FAIL", f)
    else:
        print("PASS 全部硬门禁计数一致")

    if dry_run:
        print("dry-run：不写文件")
        return 1 if failures else 0

    if failures:
        print("存在计数不符，拒绝写入查表目录")
        return 1

    out_dir = out_dir.resolve()
    out_dir.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="qa4_lookups_") as tmp:
        tmp_path = Path(tmp)
        file_meta: dict[str, Any] = {}
        for name, payload in outputs.items():
            dest = tmp_path / name
            if name.endswith(".csv"):
                rows, fields = payload
                size, sha = _write_csv_bom(dest, rows, fields)
                count = len(rows)
            else:
                size, sha = _write_json(dest, payload)
                if isinstance(payload, list):
                    count = len(payload)
                elif isinstance(payload, dict) and "title_count" in payload:
                    count = payload["title_count"]
                elif name == "hymn_series.json":
                    count = payload["daben_buchong_number_overlap"]
                elif name == "name_norm_log.json":
                    count = len(payload)
                else:
                    count = meta_counts.get(name, 0)
            file_meta[name] = {"count": count, "sha256": sha, "bytes": size}
            # sidecar
            side = {
                "file": name,
                "count": count,
                "sha256": sha,
                "bytes": size,
            }
            _write_json(tmp_path / f"{name}.meta.json", side)

        source_meta = {}
        for k, p in sources.items():
            if p is None:
                source_meta[k] = {"path": None, "status": "缺来源"}
            elif p.is_file():
                source_meta[k] = {
                    "path": str(p),
                    "sha256": _sha256_file(p),
                    "status": "ok",
                }
            else:
                # 目录：列文件 sha 摘要
                files = sorted(
                    [x for x in p.rglob("*") if x.is_file() and x.suffix in {".json", ".jsonl", ".csv"}]
                )
                source_meta[k] = {
                    "path": str(p),
                    "status": "ok",
                    "file_count": len(files),
                    "files_sha256": {str(f.name): _sha256_file(f) for f in files[:50]},
                }

        manifest = {
            "generated_at": report["generated_at"],
            "files": file_meta,
            "sources": source_meta,
            "missing_sources": missing_paths,
            "reports_only": report.get("reports_only", {}),
            "expect": EXPECT,
        }
        _write_json(tmp_path / "MANIFEST.json", manifest)

        # 原子替换
        if out_dir.exists():
            backup = out_dir.with_name(out_dir.name + ".__old__")
            if backup.exists():
                shutil.rmtree(backup)
            out_dir.rename(backup)
            try:
                shutil.copytree(tmp_path, out_dir)
                shutil.rmtree(backup)
            except Exception:
                if out_dir.exists():
                    shutil.rmtree(out_dir)
                backup.rename(out_dir)
                raise
        else:
            shutil.copytree(tmp_path, out_dir)

    print(f"已写入 {out_dir}")
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="生成 qa4 lookups")
    parser.add_argument(
        "--sources",
        required=True,
        help="sources.json 路径（由 sources.example.json 另存填写）",
    )
    parser.add_argument(
        "--out",
        default=str(Path(__file__).resolve().parents[2] / "data" / "lookups"),
        help="输出目录（默认 qa4/data/lookups）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只读来源、打印条数、不写文件",
    )
    args = parser.parse_args(argv)
    sources_path = Path(args.sources)
    if not sources_path.is_file():
        print(f"找不到 sources 文件：{sources_path}", file=sys.stderr)
        return 2
    return run(sources_path, Path(args.out), args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
