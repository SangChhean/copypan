# -*- coding: utf-8 -*-
"""只读探测：经文格式测试集 + 按时分粮别名对照 + 诗歌现状调查。

不修改 normalize / vendor；不联网；不读密钥。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Optional

_BACKEND = Path(__file__).resolve().parents[1]
_QA4 = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

DEFAULT_CASES = _QA4 / "notes" / "scripture_format_cases.csv"
DEFAULT_HYMN_CASES = _QA4 / "notes" / "hymn_format_cases.csv"
DEFAULT_OUT = Path(r"G:\PanAI4.0专用\logs\formats")
ANSHI_SCRIPTS = Path(r"G:\copypan\back_anshifenliang\data\scripts.js")
HYMNS_SRC = Path(r"G:\PanAI4.0专用\qa4_import_src\es\data\panai4_hymns\chunks_hymns_vec.json")


def build_std_to_full() -> dict[str, str]:
    """从 vendor BOOK_MAP 反推标准简称 → 恢复本全称（取最长非简称别名）。

    来源：qa4/backend/scripture/vendor_get_vers_v21.py 的 BOOK_MAP。
    """
    from scripture.vendor_get_vers_v21 import BOOK_MAP, STD_ORDER

    cands: dict[str, list[str]] = defaultdict(list)
    for alias, std in BOOK_MAP.items():
        if alias == std:
            continue
        cands[std].append(alias)
    out: dict[str, str] = {}
    for std in STD_ORDER:
        aliases = cands.get(std) or []
        if not aliases:
            out[std] = std
            continue
        # 优先带书卷后缀的全称
        def score(a: str) -> tuple:
            suf = any(a.endswith(x) for x in ("福音", "书", "记", "纪")) or a in ("诗篇", "使徒行传", "雅歌", "传道书")
            return (1 if suf else 0, len(a), a)

        out[std] = sorted(aliases, key=score, reverse=True)[0]
    return out


def format_ref_expected_style(ref, std_to_full: dict[str, str]) -> str:
    from scripture.normalize import KIND_BOOK, KIND_CHAPTER, KIND_CHAPTER_RANGE, KIND_CROSS

    book = std_to_full.get(ref.book, ref.book)
    if ref.kind == KIND_BOOK:
        return f"{book}"
    if ref.kind == KIND_CHAPTER_RANGE:
        return f"{book} {ref.chapter}-{ref.end_chapter}"
    if ref.kind == KIND_CHAPTER:
        return f"{book} {ref.chapter}"
    if ref.kind == KIND_CROSS:
        return f"{book} {ref.chapter}:{ref.v_start}-{ref.end_chapter}:{ref.v_end}"
    if ref.v_start == ref.v_end:
        return f"{book} {ref.chapter}:{ref.v_start}"
    return f"{book} {ref.chapter}:{ref.v_start}-{ref.v_end}"


def raw_key_tuple(ref) -> tuple:
    return (ref.book, ref.chapter, ref.v_start, ref.end_chapter, ref.v_end)


def parse_one(input_text: str, bible, std_to_full: dict[str, str]) -> dict[str, Any]:
    """调用流水线入口 parse_refs（normalize 包装 vendor）。不 strip 输入。"""
    from scripture.normalize import parse_refs

    try:
        refs = parse_refs(input_text, bible=bible, validate=True)
    except Exception as e:
        return {
            "actual": "",
            "raw_keys": "",
            "match": "报错",
            "error": f"{type(e).__name__}: {e}",
            "refs_n": 0,
        }
    if not refs:
        actual = "无出处"
        raw = ""
    else:
        actual = " ; ".join(format_ref_expected_style(r, std_to_full) for r in refs)
        raw = " ; ".join(str(raw_key_tuple(r)) for r in refs)
    return {"actual": actual, "raw_keys": raw, "match": "", "error": "", "refs_n": len(refs)}


def load_cases(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def run_scripture(cases: list[dict[str, str]], out_dir: Path, only: Optional[set[str]]) -> dict[str, Any]:
    from scripture.bible_text import BibleText
    from config import get_settings

    settings = get_settings(require_runtime=False)
    bible = BibleText(settings.bible_dir)
    std_to_full = build_std_to_full()
    map_src = "qa4/backend/scripture/vendor_get_vers_v21.py::BOOK_MAP（反推最长全称）"

    rows_out = []
    by_group: dict[str, Counter] = defaultdict(Counter)
    mismatches = []
    errors = []
    pendings = []
    unsupported_note = []

    selected = [r for r in cases if (not only or r["id"] in only)]
    for row in selected:
        cid = row["id"]
        inp = row["input"]  # 不 strip
        expected = row["expected"]
        status = row["status"]
        group = row["group"]
        got = parse_one(inp, bible, std_to_full)
        if got["error"]:
            match = "报错"
        elif status == "待定":
            match = "待定"
        else:
            match = "一致" if got["actual"] == expected else "不一致"
        rec = {
            "id": cid,
            "group": group,
            "input": inp,
            "expected": expected,
            "status": status,
            "actual": got["actual"],
            "raw_keys": got["raw_keys"],
            "match": match,
            "error": got["error"],
        }
        rows_out.append(rec)
        by_group[group][match] += 1
        if only:
            print(
                f"{cid}\tmatch={match}\tinput={inp!r}\texpected={expected!r}\t"
                f"actual={got['actual']!r}\traw={got['raw_keys']}\terror={got['error']}"
            )
        if match == "不一致":
            mismatches.append(rec)
        elif match == "报错":
            errors.append(rec)
        elif match == "待定":
            pendings.append(rec)

    # CSV / MD：全量跑才写；--only 只打印屏幕，避免覆盖全量结果
    out_dir.mkdir(parents=True, exist_ok=True)
    if only:
        return {
            "n": len(rows_out),
            "counts": dict(Counter(r["match"] for r in rows_out)),
            "mismatch_ids": [r["id"] for r in mismatches],
            "error_ids": [r["id"] for r in errors],
            "pending_ids": [r["id"] for r in pendings],
            "unsupported_note": "",
        }

    csv_path = out_dir / "scripture_format_results.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(
            f,
            fieldnames=["id", "group", "input", "expected", "status", "actual", "raw_keys", "match", "error"],
        )
        w.writeheader()
        for r in rows_out:
            w.writerow(r)

    # 失败原因归类（观察）
    reasons: dict[str, list[str]] = defaultdict(list)
    for r in mismatches:
        act, exp = r["actual"], r["expected"]
        if act == "无出处":
            reasons["实际无出处（期望有）"].append(r["id"])
        elif exp == "无出处" and act != "无出处":
            reasons["期望无出处但抽到了"].append(r["id"])
        elif " ; " in act and " ; " not in exp:
            reasons["抽到多个出处（期望单个）"].append(r["id"])
        elif act.count(":") != exp.count(":"):
            reasons["章节形态不同（冒号数不等）"].append(r["id"])
        else:
            reasons["其它不一致"].append(r["id"])

    md_lines = [
        "# 经文格式测试结果",
        "",
        f"卷名全称映射来源：`{map_src}`",
        f"入口：`scripture.normalize.parse_refs`（含 `preprocess_ref_text`）",
        f"用例文件：`{DEFAULT_CASES}`",
        f"跑过条数：{len(rows_out)}",
        "",
        "## 各组条数",
        "",
    ]
    for g in sorted(by_group.keys()):
        c = by_group[g]
        md_lines.append(
            f"- {g}：一致={c.get('一致', 0)} 不一致={c.get('不一致', 0)} "
            f"报错={c.get('报错', 0)} 待定={c.get('待定', 0)}"
        )
    tot = Counter()
    for c in by_group.values():
        tot.update(c)
    md_lines += [
        "",
        f"合计：一致={tot.get('一致', 0)} 不一致={tot.get('不一致', 0)} "
        f"报错={tot.get('报错', 0)} 待定={tot.get('待定', 0)}",
        "",
        "## 不一致（逐条）",
        "",
    ]
    if not mismatches:
        md_lines.append("- （无）")
    for r in mismatches:
        md_lines.append(
            f"- {r['id']} 输入=`{r['input']}` 期望=`{r['expected']}` 实际=`{r['actual']}` raw=`{r['raw_keys']}`"
        )
    md_lines += ["", "## 报错（逐条）", ""]
    if not errors:
        md_lines.append("- （无）")
    for r in errors:
        md_lines.append(f"- {r['id']} 输入=`{r['input']}` 错误=`{r['error']}`")
    md_lines += ["", "## 待定（实际结果）", ""]
    if not pendings:
        md_lines.append("- （无）")
    for r in pendings:
        md_lines.append(f"- {r['id']} 输入=`{r['input']}` 实际=`{r['actual']}` raw=`{r['raw_keys']}`")
    md_lines += ["", "## 失败原因归类（观察）", ""]
    for k, ids in reasons.items():
        md_lines.append(f"- {k}：{', '.join(ids)}")
    if not reasons:
        md_lines.append("- （无不一致可归类）")
    md_lines += [
        "",
        "## 入口能力说明",
        "",
        "- 使用 `parse_refs`：可从整段/整句抽取多处出处（如「读经：…」类）。",
        "- 无单独「只解析整卷书名」的成功路径时，整卷用例实际常为「无出处」（见待定组）。",
        "- 未另行实现新的句子抽取器；不支持时不会自行补逻辑。",
    ]
    if unsupported_note:
        md_lines += ["", "## 现有入口不支持", ""] + [f"- {x}" for x in unsupported_note]

    (out_dir / "scripture_format_results.md").write_text("\n".join(md_lines) + "\n", encoding="utf-8")
    return {
        "totals": dict(tot),
        "mismatch_ids": [r["id"] for r in mismatches],
        "error_ids": [r["id"] for r in errors],
        "by_group": {g: dict(c) for g, c in by_group.items()},
        "std_to_full_source": map_src,
        "rows": rows_out,
    }


def extract_js_string_map(text: str, const_name: str) -> dict[str, str]:
    m = re.search(rf"const\s+{re.escape(const_name)}\s*=\s*\{{", text)
    if not m:
        return {}
    start = m.end() - 1
    depth = 0
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                body = text[start + 1 : i]
                break
        i += 1
    else:
        return {}
    out: dict[str, str] = {}
    for km in re.finditer(r"['\"]([^'\"]+)['\"]\s*:\s*['\"]([^'\"]+)['\"]", body):
        out[km.group(1)] = km.group(2)
    return out


def extract_ambiguous_set(text: str) -> list[str]:
    m = re.search(r"const\s+AMBIGUOUS_BARE_BOOK_NAMES\s*=\s*new\s+Set\(\[(.*?)\]\)", text, re.S)
    if not m:
        return []
    return re.findall(r"['\"]([^'\"]+)['\"]", m.group(1))


def run_alias_compare(out_dir: Path, bible, std_to_full: dict[str, str]) -> dict[str, Any]:
    text = ANSHI_SCRIPTS.read_text(encoding="utf-8")
    variant = extract_js_string_map(text, "BOOK_VARIANT_COMPLETE_MAP")
    name_map = extract_js_string_map(text, "BOOK_NAME_MAP")
    ambiguous = extract_ambiguous_set(text)

    # 合并别名：优先 VARIANT，再 NAME（目标保留按时分粮侧字符串）
    aliases: dict[str, str] = {}
    aliases.update(name_map)
    aliases.update(variant)  # variant 覆盖同名

    rows = []
    counts = Counter()
    for alias, target in sorted(aliases.items(), key=lambda x: x[0]):
        samples = [f"{alias}一1", f"{alias}1:1"]
        parsed_books = []
        for s in samples:
            got = parse_one(s, bible, std_to_full)
            if got["error"]:
                parsed_books.append(None)
                continue
            if got["actual"] == "无出处" or not got["raw_keys"]:
                parsed_books.append(None)
            else:
                # 取第一个出处的全称卷名
                first = got["actual"].split(" ; ")[0]
                book = first.split(" ")[0] if first else None
                parsed_books.append(book)
        books = [b for b in parsed_books if b]
        uniq = sorted(set(books))
        if not books:
            st = "qa4 不识别"
        elif len(uniq) > 1:
            st = "有歧义"
        else:
            # 按时分粮 target 可能是全称或简称；与 qa4 全称或简称比较
            qa4_book = uniq[0]
            # target 也可能是全称（VARIANT）或简称（NAME_MAP）
            from scripture.vendor_get_vers_v21 import BOOK_MAP

            target_std = BOOK_MAP.get(target, target)
            qa4_std = BOOK_MAP.get(qa4_book, qa4_book)
            if target == qa4_book or target_std == qa4_std or std_to_full.get(target_std) == qa4_book:
                st = "一致"
            else:
                st = "不一致"
        counts[st] += 1
        rows.append(
            {
                "别名": alias,
                "按时分粮的目标": target,
                "qa4 解析到的卷名": uniq[0] if len(uniq) == 1 else ("|".join(uniq) if uniq else ""),
                "状态": st,
            }
        )

    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "alias_compare.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["别名", "按时分粮的目标", "qa4 解析到的卷名", "状态"])
        w.writeheader()
        for r in rows:
            w.writerow(r)

    md = [
        "# 别名对照（按时分粮 scripts.js vs qa4 parse_refs）",
        "",
        f"源：`{ANSHI_SCRIPTS}`（只读文本抽取 BOOK_VARIANT_COMPLETE_MAP / BOOK_NAME_MAP）",
        f"别名总数：{len(rows)}",
        f"一致={counts['一致']} 不一致={counts['不一致']} qa4 不识别={counts['qa4 不识别']} 有歧义={counts['有歧义']}",
        "",
        "## AMBIGUOUS_BARE_BOOK_NAMES（逐字）",
        "",
    ]
    for a in ambiguous:
        md.append(f"- `{a}`")
    md += ["", "## 不一致", ""]
    bad = [r for r in rows if r["状态"] == "不一致"]
    if not bad:
        md.append("- （无）")
    for r in bad:
        md.append(f"- `{r['别名']}` → 按时分粮=`{r['按时分粮的目标']}` qa4=`{r['qa4 解析到的卷名']}`")
    md += ["", "## qa4 不识别", ""]
    miss = [r for r in rows if r["状态"] == "qa4 不识别"]
    if not miss:
        md.append("- （无）")
    for r in miss:
        md.append(f"- `{r['别名']}` → 按时分粮=`{r['按时分粮的目标']}`")
    md += ["", "## 有歧义", ""]
    amb = [r for r in rows if r["状态"] == "有歧义"]
    if not amb:
        md.append("- （无）")
    for r in amb:
        md.append(f"- `{r['别名']}` → qa4=`{r['qa4 解析到的卷名']}`")

    (out_dir / "alias_compare.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    return {
        "counts": dict(counts),
        "ambiguous": ambiguous,
        "n_aliases": len(rows),
        "mismatch": [r["别名"] for r in bad],
        "unrecognized": [r["别名"] for r in miss],
    }


def scan_hymn_source(path: Path) -> dict[str, Any]:
    """只读 JSONL（.json 扩展名，逐行对象），统计 series / 号码范围。"""
    if not path.is_file():
        return {"found": False, "path": str(path)}
    series_chunks: Counter = Counter()
    series_numbers: dict[str, set[int]] = defaultdict(set)
    n_lines = 0
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            n_lines += 1
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            series = str(obj.get("series") or "")
            num = obj.get("hymn_number")
            series_chunks[series] += 1
            if isinstance(num, int) or (isinstance(num, str) and str(num).isdigit()):
                series_numbers[series].add(int(num))
    ranges = {}
    for s, nums in series_numbers.items():
        ranges[s] = {
            "distinct_numbers": len(nums),
            "min": min(nums) if nums else None,
            "max": max(nums) if nums else None,
        }
    return {
        "found": True,
        "path": str(path),
        "lines": n_lines,
        "series_chunk_counts": dict(series_chunks),
        "series_number_ranges": ranges,
    }


def run_hymn_findings(out_dir: Path) -> dict[str, Any]:
    lines = [
        "# 诗歌首数识别现状（只读调查）",
        "",
        "## a) qa4 是否已有从文本识别诗歌首数的代码",
        "",
    ]
    # Search findings - hardcoded from investigation with line refs
    lines += [
        "- **未找到**独立的「从任意文本抽取诗歌首数」解析模块（无类似 `parse_hymn_refs`）。",
        "- `scripture/vendor_get_vers_v21.py:295-300`：`HYMN` 正则用于**排除**诗歌号被误判为经节，不是取篇识别器。",
        "- `core/llm_fake.py` 约 `:339` / `:412-416`：假模型标记 `【诗歌N】` → `locator.hymn_number`（流水线定位，非自然语言首数解析）。",
        "- `retrieval/targeted.py:303-317`：`TargetedFetcher.hymn(number, series=…)` 要求调用方已给出 **int 首数** 与 series。",
        "",
        "## b) 中文数字 → 阿拉伯数字工具",
        "",
        "- 有：`scripture/vendor_get_vers_v21.py:142` `cn2num`（注释：三十 / 二四 / 十五）。",
        "- 另有：`tools/gen_lookups.py:140` `_cn_num_to_int`（注释：简易中文数字，辑/册；含十/百/千）。",
        "- `廿`：`cn2num` 数字表**不含**「廿」（`vendor_get_vers_v21.py:152-154`）→ 【观察】不能处理「廿」。",
        "- 「一百零五」「一百二十」：下面用 `cn2num` 实测。",
        "",
        "## b) 实测（仅数字部分，H 组中文数字）",
        "",
    ]
    from scripture.vendor_get_vers_v21 import cn2num

    hymn_cases = load_cases(DEFAULT_HYMN_CASES)
    cn_cases = [r for r in hymn_cases if r["group"].startswith("02")]
    # 抽取数字部分：尽量取「第…首」或末尾中文数字
    num_re = re.compile(
        r"第([一二三四五六七八九十百千万零〇○两廿]+)首|([一二三四五六七八九十百千万零〇○两廿]+)$"
    )
    for r in cn_cases:
        inp = r["input"]
        m = num_re.search(inp.replace(" ", ""))
        piece = m.group(1) or m.group(2) if m else ""
        if not piece:
            # 尝试去掉前缀后整段
            piece = re.sub(r"^(诗歌|大本|补充本|儿童)+", "", inp.replace(" ", ""))
            piece = piece.replace("第", "").replace("首", "")
        try:
            out = cn2num(piece)
        except Exception as e:
            out = f"ERR {type(e).__name__}"
        lines.append(f"- {r['id']} 输入=`{inp}` 数字部分=`{piece}` cn2num=`{out}` 期望相关=`{r['expected']}`")

    lines += [
        "",
        "## c) targeted.py / retrieval.json 诗歌配置",
        "",
        "- `retrieval/targeted.py:303-310`：`hymn(number: int, series: Optional[str]=None)`；"
        "默认 series 来自配置 `default_series` 或字面「诗歌」；过滤字段 `series` + `hymn_number`。",
        "- `config/retrieval.json:78-101`：`hymns` 索引；`filters.series` / `hymn_number`；"
        "`default_series` 为「诗歌」；`full_unit_type.value` 为「full」（verified=false）。",
        "- 首数类型：Python `int`（见函数签名）。",
        "",
        "## d) 本地建索引源",
        "",
    ]
    stats = scan_hymn_source(HYMNS_SRC)
    if not stats.get("found"):
        lines.append(f"- 未找到源文件：`{HYMNS_SRC}`")
    else:
        lines.append(f"- 源路径：`{stats['path']}`（JSONL 形态，逐行 JSON；行数={stats['lines']}）")
        lines.append("- series 取值与 chunk 条数：")
        for s, n in sorted(stats["series_chunk_counts"].items(), key=lambda x: -x[1]):
            rng = stats["series_number_ranges"].get(s) or {}
            lines.append(
                f"  - `{s}`：chunks={n}；distinct_numbers={rng.get('distinct_numbers')}；"
                f"min={rng.get('min')} max={rng.get('max')}"
            )

    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "hymn_findings.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return {"hymn_stats": stats, "cn_cases_n": len(cn_cases)}


def write_summary(out_dir: Path, scripture: dict, alias: dict, hymn: dict) -> None:
    notes = _QA4 / "notes" / "format_probe_results_20261117.md"
    lines = [
        "# 格式探测总结 2026-11-17",
        "",
        "## 任务一：经文格式测试集",
        "",
        f"- 输出目录：`{out_dir}` → `scripture_format_results.csv` / `.md`",
        f"- 卷名映射来源：{scripture.get('std_to_full_source')}",
        f"- 合计：{scripture.get('totals')}",
        f"- 不一致 id：{', '.join(scripture.get('mismatch_ids') or []) or '（无）'}",
        f"- 报错 id：{', '.join(scripture.get('error_ids') or []) or '（无）'}",
        "",
        "## 任务二：别名对照",
        "",
        f"- 别名条数：{alias.get('n_aliases')}；状态计数：{alias.get('counts')}",
        f"- AMBIGUOUS_BARE_BOOK_NAMES 条数：{len(alias.get('ambiguous') or [])}",
        f"- 不一致别名：{', '.join(alias.get('mismatch') or []) or '（无）'}",
        f"- qa4 不识别别名条数：{len(alias.get('unrecognized') or [])}",
        "",
        "## 任务三：诗歌现状",
        "",
        "- 文本级诗歌首数识别器：**未找到**",
        "- 中文数字工具：`vendor_get_vers_v21.cn2num`；另有 `gen_lookups._cn_num_to_int`",
        f"- 本地 hymns 源：{ (hymn.get('hymn_stats') or {}).get('path') }",
        f"- H 组中文数字实测条数：{hymn.get('cn_cases_n')}",
        "",
        "## 未完成 / 受限",
        "",
        "- 未改 normalize/vendor；不支持的写法只如实记实际结果。",
        "- 未跑 ES；诗歌 series 统计来自本地 jsonl。",
        "- 未新增单元测试。",
        "",
        "## 【待核实】",
        "",
        "- 按时分粮 BOOK_NAME_MAP 与 VARIANT 表是否完全覆盖繁体别名。",
        "- `创世记第一章第一节` 等用例若抽到「整章+单节」双 Ref，是否符合产品预期。",
    ]
    notes.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", type=Path, default=DEFAULT_CASES)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--only", default="", help="逗号分隔 id；只跑这些并打印屏幕")
    ap.add_argument("--skip-alias", action="store_true")
    ap.add_argument("--skip-hymn", action="store_true")
    ap.add_argument("--no-notes", action="store_true", help="不写 qa4/notes 下摘要，只写 --out")
    args = ap.parse_args(argv)

    only = {s.strip() for s in args.only.split(",") if s.strip()} or None
    cases = load_cases(args.cases)
    scripture = run_scripture(cases, args.out, only)

    if only:
        # --only 模式：不强制跑别名/诗歌全量（节省时间）；仍可写空提示
        print(f"ONLY mode done → {args.out / 'scripture_format_results.csv'}")
        return 0

    from scripture.bible_text import BibleText
    from config import get_settings

    bible = BibleText(get_settings(require_runtime=False).bible_dir)
    std_to_full = build_std_to_full()
    alias = {} if args.skip_alias else run_alias_compare(args.out, bible, std_to_full)
    hymn = {} if args.skip_hymn else run_hymn_findings(args.out)
    if not args.no_notes:
        write_summary(args.out, scripture, alias, hymn)
        print(f"NOTES={_QA4 / 'notes' / 'format_probe_results_20261117.md'}")
    print(f"OUT_DIR={args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
