# -*- coding: utf-8 -*-
"""纲目 docx → JSON 的命令行入口。

默认读桌面上的两批目录，把产出写到桌面的「纲目JSON」。
两个输入目录只读。
"""

from __future__ import annotations

import argparse
import json
import os
import random
import statistics
import sys
from collections import Counter

from . import config
from .docx_parser import (
    analyze_document,
    book_from_dirs,
    category_from_dirname,
    level1_group_token,
    mapped_style_names,
    parse_conference_dirname,
    parse_msg_filename,
    read_paragraphs,
)

EXCERPT_CLASS_PREFIXES = (
    "text:职事信息摘录",
    "text:职事信息之摘录",
    "text:职事信息摘要",
)


def snapshot_dir(root: str) -> dict:
    files = 0
    docx = 0
    total = 0
    for dirpath, _dirs, names in os.walk(root):
        for name in names:
            path = os.path.join(dirpath, name)
            try:
                total += os.path.getsize(path)
            except OSError:
                continue
            files += 1
            if name.lower().endswith(".docx"):
                docx += 1
    return {"files": files, "docx": docx, "bytes": total}


def collect_docx(root: str, name_prefix: str | None = None) -> list[str]:
    found = []
    for dirpath, _dirs, names in os.walk(root):
        for name in names:
            if not name.lower().endswith(".docx"):
                continue
            if name_prefix and not name.startswith(name_prefix):
                continue
            found.append(os.path.join(dirpath, name))
    found.sort()
    return found


def _rel(path: str, root: str) -> str:
    rel = os.path.relpath(path, root)
    return rel.replace("/", "\\")


def _make_id(batch: str, rel: str) -> str:
    stem = rel[:-5] if rel.lower().endswith(".docx") else rel
    if batch == "feasts":
        parent, name = os.path.split(stem)
        if name.startswith("【") and "】" in name:
            name = name.split("】", 1)[1]
        stem = os.path.join(parent, name) if parent else name
    return config.ID_PREFIX[batch] + "/" + stem.replace("\\", "/")


def _meta_a(rel: str, filename: str, style_system: str) -> dict:
    parent = os.path.dirname(rel)
    dirs = [] if parent in ("", ".") else parent.split("\\")
    parsed = parse_msg_filename(filename)
    return {
        "category": category_from_dirname(dirs[0]) if dirs else "",
        "book": book_from_dirs(dirs),
        "book_path": dirs,
        "msg_label": parsed["msg_label"],
        "msg_no": parsed["msg_no"],
        "title": parsed["title"],
        "source_path": rel,
        "style_system": style_system,
    }


def _meta_b(rel: str, filename: str, style_system: str) -> dict:
    parent = os.path.dirname(rel)
    dirs = [] if parent in ("", ".") else parent.split("\\")
    conference = dirs[0] if dirs else ""
    conf = parse_conference_dirname(conference)
    if len(dirs) >= 2:
        seq_dir = dirs[1]
    else:
        seq_dir = ""
    parsed = parse_msg_filename(filename)
    return {
        "conference": conference,
        "year": conf["year"],
        "month": conf["month"],
        "conference_name": conf["conference_name"],
        "seq_dir": seq_dir,
        "version": parsed["version"] or "纲目的原文",
        "msg_no": parsed["msg_no"],
        "title": parsed["title"],
        "source_path": rel,
        "style_system": style_system,
    }


def _new_batch_stats() -> dict:
    return {
        "read": 0,
        "output": 0,
        "excluded": 0,
        "candidates": 0,
        "parse_errors": 0,
        "levels": Counter(),
        "tokens": [],
        "truncate": Counter(),
        "hardcoded": 0,
        "style_system": Counter(),
        "unknown_styles": Counter(),
        "preface": 0,
        "anomaly_types": Counter(),
        "ids": [],
        "sources": {},
    }


def _is_excerpt_class(rule: str | None) -> bool:
    if not rule:
        return False
    return any(rule.startswith(prefix) for prefix in EXCERPT_CLASS_PREFIXES)


def _styles_dict(counts: Counter) -> dict:
    return {name: counts[name] for name in sorted(counts)}


def process_batch(
    batch: str,
    root: str,
    paths: list[str],
    out_fp,
    anomalies_fp,
    excluded: list,
    candidates: list,
    stats: dict,
) -> None:
    total = len(paths)
    for i, path in enumerate(paths, 1):
        if i % 500 == 0 or i == total:
            print(f"{batch} {i}/{total}", flush=True)
        rel = _rel(path, root)
        filename = os.path.basename(path)
        doc_id = _make_id(batch, rel)
        stats["read"] += 1
        paragraphs, err = read_paragraphs(path)
        if err:
            stats["parse_errors"] += 1
            stats["excluded"] += 1
            excluded.append(
                {
                    "batch": batch,
                    "path": rel,
                    "reason": "解析失败：" + err,
                    "para_total": 0,
                    "styles": {},
                }
            )
            _write_anomaly(
                anomalies_fp,
                stats,
                {
                    "type": "parse_error",
                    "batch": batch,
                    "id": doc_id,
                    "path": rel,
                    "para_no": None,
                    "detail": err,
                },
            )
            continue

        hardcoded = config.HARDCODED_TRUNCATION.get(rel)
        analyzed = analyze_document(paragraphs, hardcoded)
        for name, count in analyzed["style_counts"].items():
            if name not in mapped_style_names():
                stats["unknown_styles"][name] += count

        if not analyzed["points"]:
            stats["excluded"] += 1
            excluded.append(
                {
                    "batch": batch,
                    "path": rel,
                    "id": doc_id,
                    "reason": config.EXCLUDED_REASON,
                    "para_total": analyzed["para_total"],
                    "styles": _styles_dict(analyzed["style_counts"]),
                }
            )
            _emit_anomalies(anomalies_fp, stats, batch, doc_id, rel, analyzed["anomalies"])
            continue

        meta = (
            _meta_a(rel, filename, analyzed["style_system"])
            if batch == "12490"
            else _meta_b(rel, filename, analyzed["style_system"])
        )
        record = {
            "id": doc_id,
            "batch": batch,
            "meta": meta,
            "doc_header": analyzed["doc_header"],
            "points": analyzed["points"],
            "stats": {
                "para_total": analyzed["para_total"],
                "para_outline": len(analyzed["points"]),
                "truncated_at": analyzed["truncated_at"],
                "truncate_rule": analyzed["truncate_rule"],
                "level_counts": analyzed["level_counts"],
            },
        }
        out_fp.write(json.dumps(record, ensure_ascii=False) + "\n")
        stats["output"] += 1
        stats["ids"].append(doc_id)
        stats["sources"][doc_id] = path
        stats["style_system"][analyzed["style_system"]] += 1
        for point in analyzed["points"]:
            stats["levels"][point["level"]] += 1
            if batch == "12490" and point["level"] == 1 and point["label"] == "前言":
                stats["preface"] += 1
        stats["tokens"].extend(level1_group_token(analyzed["points"]))
        rule = analyzed["truncate_rule"]
        if rule is None:
            stats["truncate"]["（未截断）"] += 1
        else:
            stats["truncate"][rule] += 1
            if rule == "hardcoded":
                stats["hardcoded"] += 1
        if analyzed["candidate"]:
            stats["candidates"] += 1
            candidates.append(
                {
                    "batch": batch,
                    "path": rel,
                    "id": doc_id,
                    "reason": config.CANDIDATE_REASON,
                    "level": analyzed["candidate_level"],
                    "point_count": len(analyzed["points"]),
                    "para_total": analyzed["para_total"],
                    "styles": _styles_dict(analyzed["style_counts"]),
                }
            )
        _emit_anomalies(anomalies_fp, stats, batch, doc_id, rel, analyzed["anomalies"])


def _emit_anomalies(fp, stats, batch, doc_id, rel, anomalies) -> None:
    for item in anomalies:
        _write_anomaly(
            fp,
            stats,
            {
                "type": item["type"],
                "batch": batch,
                "id": doc_id,
                "path": rel,
                "para_no": item.get("para_no"),
                "detail": item.get("detail", ""),
            },
        )


def _write_anomaly(fp, stats, obj: dict) -> None:
    fp.write(json.dumps(obj, ensure_ascii=False) + "\n")
    stats["anomaly_types"][obj["type"]] += 1


def _pct(n: int, total: int) -> str:
    if total <= 0:
        return "0.0%"
    return f"{n / total * 100:.1f}%"


def _token_block(tokens: list[int]) -> list[str]:
    if not tokens:
        return ["无第 1 级单位。"]
    tokens_sorted = sorted(tokens)
    n = len(tokens_sorted)
    avg = sum(tokens_sorted) / n
    mid = statistics.median(tokens_sorted)
    lt = sum(1 for t in tokens_sorted if t < 150)
    mid_n = sum(1 for t in tokens_sorted if 150 <= t <= 800)
    gt = sum(1 for t in tokens_sorted if t > 800)
    return [
        f"- 单位数（一个第 1 级点及其下属）：{n}",
        f"- min / max / avg / median：{tokens_sorted[0]} / {tokens_sorted[-1]} / {avg:.1f} / {mid}",
        f"- 小于 150：{lt}（{_pct(lt, n)}）",
        f"- 150～800：{mid_n}（{_pct(mid_n, n)}）",
        f"- 大于 800：{gt}（{_pct(gt, n)}）",
        "- 估算：`max(0, int(len(text) / 1.5))`，与 v7 的 `estimate_tokens` 一致。",
        "- 每个单位的 text = 该第 1 级点及其后、直到下一个第 1 级点之前的各点，按 `label` 与 `text` 用 Tab 拼成一行，点与点之间用换行连接。第 1 级之前的孤立点不计入单位。",
    ]


def _md_cell(text: str, limit: int = 30) -> str:
    s = (text or "").replace("\t", "→").replace("\n", "⏎").replace("|", "\\|")
    if len(s) > limit:
        return s[:limit]
    return s


def _sample_section(title: str, records: list[dict], root_for_display: str) -> list[str]:
    lines = [f"### {title}", ""]
    if not records:
        lines.append("（无）")
        lines.append("")
        return lines
    for rec in records:
        meta = rec["meta"]
        lines.append(f"#### `{rec['id']}`")
        lines.append("")
        lines.append(f"- 源文件：`{meta.get('source_path', '')}`")
        lines.append(
            f"- 截断：{rec['stats'].get('truncate_rule') or '未截断'}，truncated_at={rec['stats'].get('truncated_at')}"
        )
        lines.append("")
        lines.append("| idx | level | label | JSON text 前 30 字 | para_no | docx 样式 | docx 段落前 30 字 |")
        lines.append("|---:|---:|---|---|---:|---|---|")
        paragraphs, err = read_paragraphs(rec["_abs_path"])
        by_no = {p["para_no"]: p for p in paragraphs} if not err else {}
        for point in rec["points"]:
            raw = by_no.get(point["para_no"])
            raw_style = raw["style"] if raw else ("解析失败" if err else "（无此段）")
            raw_text = raw["text"] if raw else ""
            lines.append(
                "| {idx} | {level} | {label} | {text} | {para} | {style} | {raw} |".format(
                    idx=point["idx"],
                    level=point["level"],
                    label=_md_cell(point["label"], 40),
                    text=_md_cell(point["text"], 30),
                    para=point["para_no"],
                    style=_md_cell(raw_style, 40),
                    raw=_md_cell(raw_text, 30),
                )
            )
        lines.append("")
    return lines


def _load_selected(jsonl_path: str, wanted: set) -> tuple[int, list[str], dict]:
    found = {}
    mismatches = []
    n = 0
    with open(jsonl_path, "r", encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            n += 1
            obj = json.loads(line)
            if obj["stats"]["para_outline"] != len(obj["points"]):
                mismatches.append(obj["id"])
            if obj["id"] in wanted:
                found[obj["id"]] = obj
    return n, mismatches, found


def build_report(ctx: dict) -> str:
    a = ctx["a_stats"]
    b = ctx["b_stats"]
    lines = []
    lines.append("# 纲目 docx → JSON 转换报告")
    lines.append("")
    lines.append("- 方案：`docs/panai4_es/docx_to_json_plan.md`")
    lines.append("- 抽样种子：{0}".format(config.SAMPLE_SEED))
    lines.append("")
    lines.append("## 与方案不一致之处")
    lines.append("")
    lines.append(
        "1. **A 批硬编码截断段号用 42，不是方案正文里点名的第 41 段。** "
        "方案 3.2 说 `msg. 2 哥林多前后书中基督作那灵…` 的规则失效在第 41 段，"
        "因为摘录样式被误套在纲目点上。打开该文件后，第 41 段文字是纲目点「玖→…」，"
        "附录从第 42 段（行首多个 Tab 的小标题）才开始。B 批四个例外的段号是「附录起始段」，"
        "含义是该段及其后丢弃。若把 A 批也从第 41 段丢弃，会丢掉这个第 1 级点。"
        "因此配置里的截断段号是 42，第 41 段仍作为纲目点保留。"
    )
    lines.append(
        "2. **`excluded_files.json` 是带 `excluded` 与 `candidates` 两节的对象，不是单一数组。** "
        "方案 6.1 说每个 JSON 为数组、每条一行。本指令要求条件 2 写入 `candidates`，"
        "并且这些文件仍输出到主 JSON。主文件 `outline_12490.json`、`outline_feasts.json` "
        "和 `anomalies.json` 仍是每条一行。"
    )
    lines.append(
        "3. **条件 2 不自动排除。** 这与方案 5.1「初版先只用条件 1」一致；"
        "本指令进一步要求把符合条件 2 的文件列入 `candidates`，理由为「条件2候选，待人工确认」。"
    )
    lines.append(
        "4. **第 4 级双字母编号收到 zz，方案正文写到 ll。** "
        "aa–ll 仍按第 4 级；mm–zz 同样按第 4 级，避免字母用尽之后的续编被丢掉。表在 `config.py`。"
    )
    lines.append("")
    lines.append("## 1. 条数对账")
    lines.append("")
    lines.append(
        "- A 批读入 docx {read}，排除 {exc}，输出 {out}。等式：{read} = {exc} + {out}，{ok}。".format(
            read=a["read"],
            exc=a["excluded"],
            out=a["output"],
            ok="成立" if a["read"] == a["excluded"] + a["output"] else "不成立",
        )
    )
    lines.append(
        "- B 批读入【纲目的原文】{read}，排除 {exc}，输出 {out}。等式：{read} = {exc} + {out}，{ok}。".format(
            read=b["read"],
            exc=b["excluded"],
            out=b["output"],
            ok="成立" if b["read"] == b["excluded"] + b["output"] else "不成立",
        )
    )
    if b["excluded"]:
        lines.append("- B 批排除明细：")
        for item in ctx["excluded"]:
            if item.get("batch") == "feasts":
                lines.append(f"  - `{item.get('path')}`：{item.get('reason')}")
    else:
        lines.append("- B 批没有排除。2631 = 输出数，当读入数不是 2631 时以实测读入数为准。")
    lines.append(f"- A 批条件 2 候选（仍在主 JSON 中）：{a['candidates']}")
    lines.append(f"- B 批条件 2 候选（仍在主 JSON 中）：{b['candidates']}")
    lines.append(f"- 解析失败：A {a['parse_errors']}，B {b['parse_errors']}")
    lines.append("")
    lines.append("## 2. 层级分布")
    lines.append("")
    for label, st in (("A 批", a), ("B 批", b)):
        total_pts = sum(st["levels"].values())
        lines.append(f"### {label}")
        lines.append("")
        lines.append("| level | 纲目点数 | 占比 |")
        lines.append("|---:|---:|---:|")
        for level in range(1, 8):
            n = st["levels"].get(level, 0)
            lines.append(f"| {level} | {n} | {_pct(n, total_pts)} |")
        lines.append(f"| 合计 | {total_pts} | 100% |")
        lines.append("")
    lines.append("## 3. token 分布")
    lines.append("")
    lines.append("### A 批")
    lines.append("")
    lines.extend(_token_block(a["tokens"]))
    lines.append("")
    lines.append("### B 批")
    lines.append("")
    lines.extend(_token_block(b["tokens"]))
    lines.append("")
    lines.append("## 4. 截断统计")
    lines.append("")
    for label, st in (("A 批", a), ("B 批", b)):
        lines.append(f"### {label}")
        lines.append("")
        lines.append("| 规则 | 文件数 |")
        lines.append("|---|---:|")
        for rule, n in sorted(st["truncate"].items(), key=lambda kv: (-kv[1], kv[0])):
            lines.append(f"| `{rule}` | {n} |")
        excerpt_n = sum(n for rule, n in st["truncate"].items() if _is_excerpt_class(rule))
        lines.append("")
        lines.append(f"- 未截断：{st['truncate'].get('（未截断）', 0)}")
        lines.append(f"- 硬编码：{st['hardcoded']}")
        lines.append(f"- 「职事信息摘录」类（含「之摘录」「摘要」，含冒号/句号变体）：{excerpt_n}")
        lines.append("")
    lines.append("## 5. 异常统计")
    lines.append("")
    all_types = Counter()
    all_types.update(a["anomaly_types"])
    all_types.update(b["anomaly_types"])
    lines.append("| 类型 | A 批 | B 批 | 合计 |")
    lines.append("|---|---:|---:|---:|")
    for name in sorted(all_types):
        lines.append(
            f"| `{name}` | {a['anomaly_types'].get(name, 0)} | {b['anomaly_types'].get(name, 0)} | {all_types[name]} |"
        )
    anomaly_lines = ctx["anomaly_lines"]
    lines.append("")
    lines.append(
        f"合计 {sum(all_types.values())}。`anomalies.json` 行数 {anomaly_lines}。"
        + ("两者相符。" if sum(all_types.values()) == anomaly_lines else "两者不符。")
    )
    lines.append("")
    lines.append("异常按打开过的文件记录，包含后来被条件 1 排除的文件。")
    lines.append("`unknown_style` 每个文件、每种未映射样式一行，detail 里是该文件中的出现次数。")
    lines.append("")
    lines.append("## 6. 抽样比对")
    lines.append("")
    lines.append(
        f"随机种子 {config.SAMPLE_SEED}。先从 A 批输出中抽 10 篇，再从 B 批输出中抽 10 篇。"
        "表中 docx 列是同一 `para_no` 的原段落（Tab 显示为 →，换行显示为 ⏎）。"
    )
    lines.append("")
    lines.extend(_sample_section("A 批 10 篇", ctx["sample_a"], ""))
    lines.extend(_sample_section("B 批 10 篇", ctx["sample_b"], ""))
    lines.append("## 7. 样式体系分布（A 批）")
    lines.append("")
    lines.append("| 样式体系 | 文件数 |")
    lines.append("|---|---:|")
    for name in config.STYLE_SYSTEM_NAMES:
        lines.append(f"| {name} | {a['style_system'].get(name, 0)} |")
    other_sys = sum(
        n for name, n in a["style_system"].items() if name not in config.STYLE_SYSTEM_NAMES
    )
    if other_sys:
        lines.append(f"| （其他） | {other_sys} |")
    lines.append(f"| 合计（输出的纲目文件） | {sum(a['style_system'].values())} |")
    lines.append("")
    lines.append("被条件 1 排除的文件不计入上表。")
    lines.append("")
    lines.append("## 8. 映射表之外的样式名")
    lines.append("")
    lines.append("计数范围是本次打开的文件里的全部段落（含截断之后的摘录），不是纲目点次数。")
    lines.append("")
    for label, st in (("A 批", a), ("B 批", b)):
        lines.append(f"### {label}")
        lines.append("")
        if not st["unknown_styles"]:
            lines.append("无。")
            lines.append("")
            continue
        lines.append("| 样式名 | 出现次数 |")
        lines.append("|---|---:|")
        for name, n in st["unknown_styles"].most_common():
            lines.append(f"| `{name}` | {n} |")
        lines.append("")
    lines.append("## 9. id 与 para_outline")
    lines.append("")
    lines.append(f"- A 输出行数：{ctx['lines_a']}，记录的输出数：{a['output']}")
    lines.append(f"- B 输出行数：{ctx['lines_b']}，记录的输出数：{b['output']}")
    lines.append(f"- id 重复：{ctx['dup_count']}")
    if ctx["dup_ids"]:
        for item in ctx["dup_ids"][:20]:
            lines.append(f"  - `{item}`")
    lines.append(
        f"- 全量核对 `stats.para_outline` 与 points 长度：不一致 {len(ctx['mismatches'])} 条"
    )
    lines.append("")
    lines.append(f"种子 {config.SAMPLE_SEED} 另抽 20 条（A、B 输出合在一起抽）：")
    lines.append("")
    lines.append("| id | para_outline | len(points) |")
    lines.append("|---|---:|---:|")
    for rec in ctx["sample_20"]:
        lines.append(
            f"| `{rec['id']}` | {rec['stats']['para_outline']} | {len(rec['points'])} |"
        )
    lines.append("")
    lines.append("## 10. 输入目录前后对比")
    lines.append("")
    lines.append("| 目录 | 时机 | 文件数 | docx 数 | 字节 |")
    lines.append("|---|---|---:|---:|---:|")
    for key, label in (("a", "A 批"), ("b", "B 批")):
        before = ctx["before"][key]
        after = ctx["after"][key]
        lines.append(
            f"| {label} | 转换前 | {before['files']} | {before['docx']} | {before['bytes']} |"
        )
        lines.append(
            f"| {label} | 转换后 | {after['files']} | {after['docx']} | {after['bytes']} |"
        )
    a_same = ctx["before"]["a"] == ctx["after"]["a"]
    b_same = ctx["before"]["b"] == ctx["after"]["b"]
    lines.append("")
    lines.append(
        "A 批前后一致。" if a_same else "A 批前后不一致。"
    )
    lines.append(
        "B 批前后一致。" if b_same else "B 批前后不一致。"
    )
    lines.append("")
    lines.append("## 11. 校验结论")
    lines.append("")
    for item in ctx["checks"]:
        flag = "通过" if item["ok"] else "未通过"
        lines.append(f"- {flag}：{item['name']}")
    lines.append("")
    return "\n".join(lines) + "\n"


def _check(ok: bool, name: str, checks: list) -> None:
    checks.append({"ok": ok, "name": name})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="纲目 docx 转为结构化 JSON")
    parser.add_argument("--a-root", default=config.DEFAULT_A_ROOT)
    parser.add_argument("--b-root", default=config.DEFAULT_B_ROOT)
    parser.add_argument("--out", default=config.DEFAULT_OUT_DIR)
    parser.add_argument(
        "--report-copy",
        default="",
        help="额外写一份报告的路径。默认不写；由调用方传入仓库内路径。",
    )
    args = parser.parse_args(argv)

    a_root = args.a_root
    b_root = args.b_root
    out_dir = args.out
    os.makedirs(out_dir, exist_ok=True)

    missing = []
    for rel in config.HARDCODED_TRUNCATION:
        if not (
            os.path.isfile(os.path.join(a_root, rel))
            or os.path.isfile(os.path.join(b_root, rel))
        ):
            missing.append(rel)
    if missing:
        print("HARDCODED_PATH_MISSING", file=sys.stderr)
        for rel in missing:
            print(rel, file=sys.stderr)
        return 1

    before = {"a": snapshot_dir(a_root), "b": snapshot_dir(b_root)}
    print(
        "snapshot before A",
        before["a"]["files"],
        before["a"]["docx"],
        before["a"]["bytes"],
        flush=True,
    )
    print(
        "snapshot before B",
        before["b"]["files"],
        before["b"]["docx"],
        before["b"]["bytes"],
        flush=True,
    )

    a_paths = collect_docx(a_root)
    b_paths = collect_docx(b_root, config.B_VERSION_PREFIX)
    print("queued", len(a_paths), len(b_paths), flush=True)

    a_json = os.path.join(out_dir, "outline_12490.json")
    b_json = os.path.join(out_dir, "outline_feasts.json")
    exc_json = os.path.join(out_dir, "excluded_files.json")
    ano_json = os.path.join(out_dir, "anomalies.json")
    report_path = os.path.join(out_dir, "conversion_report.md")

    a_stats = _new_batch_stats()
    b_stats = _new_batch_stats()
    excluded: list = []
    candidates: list = []

    with open(a_json, "w", encoding="utf-8", newline="\n") as a_fp, open(
        b_json, "w", encoding="utf-8", newline="\n"
    ) as b_fp, open(ano_json, "w", encoding="utf-8", newline="\n") as ano_fp:
        process_batch("12490", a_root, a_paths, a_fp, ano_fp, excluded, candidates, a_stats)
        process_batch("feasts", b_root, b_paths, b_fp, ano_fp, excluded, candidates, b_stats)

    with open(exc_json, "w", encoding="utf-8", newline="\n") as fp:
        json.dump(
            {"excluded": excluded, "candidates": candidates},
            fp,
            ensure_ascii=False,
            indent=2,
        )
        fp.write("\n")

    anomaly_lines = 0
    with open(ano_json, "r", encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                anomaly_lines += 1

    seen = set()
    dup_ids = []
    for doc_id in a_stats["ids"] + b_stats["ids"]:
        if doc_id in seen:
            dup_ids.append(doc_id)
        seen.add(doc_id)

    rng = random.Random(config.SAMPLE_SEED)
    sample_a_ids = rng.sample(a_stats["ids"], min(10, len(a_stats["ids"])))
    sample_b_ids = rng.sample(b_stats["ids"], min(10, len(b_stats["ids"])))
    pool = a_stats["ids"] + b_stats["ids"]
    sample_20_ids = rng.sample(pool, min(20, len(pool)))
    wanted = set(sample_a_ids + sample_b_ids + sample_20_ids)

    lines_a, mis_a, found_a = _load_selected(a_json, wanted)
    lines_b, mis_b, found_b = _load_selected(b_json, wanted)
    found = {}
    found.update(found_a)
    found.update(found_b)
    mismatches = mis_a + mis_b

    def _attach(ids, sources):
        rows = []
        for doc_id in ids:
            rec = found[doc_id]
            rec["_abs_path"] = sources[doc_id]
            rows.append(rec)
        return rows

    sample_a = _attach(sample_a_ids, a_stats["sources"])
    sample_b = _attach(sample_b_ids, b_stats["sources"])
    sample_20 = []
    for doc_id in sample_20_ids:
        sample_20.append(found[doc_id])

    after = {"a": snapshot_dir(a_root), "b": snapshot_dir(b_root)}

    a_levels_ok = all(a_stats["levels"].get(level, 0) > 0 for level in (5, 6, 7))
    b_levels_ok = all(b_stats["levels"].get(level, 0) > 0 for level in (5, 6))
    excerpt_n = sum(
        n for rule, n in a_stats["truncate"].items() if _is_excerpt_class(rule)
    )
    checks = []
    _check(a_stats["read"] == 12509, "A 批读入 12509", checks)
    _check(
        a_stats["read"] == a_stats["excluded"] + a_stats["output"],
        "A 批 读入 = 排除 + 输出",
        checks,
    )
    _check(b_stats["read"] == 2631, "B 批读入 2631", checks)
    _check(
        b_stats["read"] == b_stats["excluded"] + b_stats["output"],
        "B 批 读入 = 排除 + 输出",
        checks,
    )
    _check(not dup_ids, "id 全局无重复", checks)
    _check(not mismatches, "全部记录 para_outline 与 points 长度一致", checks)
    _check(a_levels_ok, "A 批出现 level 5、6、7", checks)
    _check(b_levels_ok, "B 批出现 level 5、6", checks)
    _check(a_stats["preface"] > 0, "A 批「前言」第 1 级点不为 0", checks)
    _check(
        11000 <= excerpt_n <= 12509,
        f"A 批职事信息摘录类截断接近 12030（实测 {excerpt_n}）",
        checks,
    )
    _check(before["a"] == after["a"], "A 批目录文件数与字节数前后一致", checks)
    _check(before["b"] == after["b"], "B 批目录文件数与字节数前后一致", checks)
    _check(
        sum(a_stats["anomaly_types"].values()) + sum(b_stats["anomaly_types"].values())
        == anomaly_lines,
        "异常计数与 anomalies.json 行数一致",
        checks,
    )

    report = build_report(
        {
            "a_stats": a_stats,
            "b_stats": b_stats,
            "excluded": excluded,
            "anomaly_lines": anomaly_lines,
            "sample_a": sample_a,
            "sample_b": sample_b,
            "sample_20": sample_20,
            "lines_a": lines_a,
            "lines_b": lines_b,
            "dup_count": len(dup_ids),
            "dup_ids": dup_ids,
            "mismatches": mismatches,
            "before": before,
            "after": after,
            "checks": checks,
        }
    )
    with open(report_path, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(report)
    if args.report_copy:
        copy_dir = os.path.dirname(args.report_copy)
        if copy_dir:
            os.makedirs(copy_dir, exist_ok=True)
        with open(args.report_copy, "w", encoding="utf-8", newline="\n") as fp:
            fp.write(report)

    print("preface", a_stats["preface"], flush=True)
    print("excerpt_class", excerpt_n, flush=True)
    print("A levels", dict(a_stats["levels"]), flush=True)
    print("B levels", dict(b_stats["levels"]), flush=True)
    print("A out/exc", a_stats["output"], a_stats["excluded"], flush=True)
    print("B out/exc", b_stats["output"], b_stats["excluded"], flush=True)
    failed = [c for c in checks if not c["ok"]]
    if failed:
        print("CHECKS_FAILED", len(failed), flush=True)
        for item in failed:
            print("FAIL", item["name"], flush=True)
        return 2
    print("CHECKS_OK", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
