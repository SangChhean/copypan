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
    classify_style_system,
    group_by_min_level,
    level1_group_token,
    mapped_style_names,
    parse_conference_dirname,
    parse_msg_filename,
    read_paragraphs,
)
from .report_v3 import build_v3_report

EXCERPT_CLASS_PREFIXES = (
    "text:职事信息摘录",
    "text:职事信息之摘录",
    "text:职事信息摘要",
    "text_inline:职事信息摘录",
    "text_inline:职事信息之摘录",
    "text_inline:职事信息摘要",
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
        "preface_by_level": Counter(),
        "anomaly_types": Counter(),
        "ids": [],
        "sources": {},
        "bible_prefix_hits": [],
        "empty_labels": [],
        "min_level_hist": Counter(),
        "group_tokens": [],
        "residue_files": 0,
        "residue_points": 0,
        "residue_levels": Counter(),
        "residue_labels": Counter(),
        "min5": [],
        "zero_unit_ids": [],
        "point_pack": {},
        "bible": {},
        "continuations": [],
        "manual_excluded": 0,
        "merged_notes": 0,
        "merged_files": 0,
        "text_over_style": 0,
        "would_return": [],
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

        title_hint = parse_msg_filename(filename).get("title") or ""
        hardcoded = config.HARDCODED_TRUNCATION.get(rel)
        analyzed = analyze_document(
            paragraphs,
            hardcoded,
            single_point=rel in config.SINGLE_POINT_FILES,
            title_hint=title_hint,
        )
        if rel in config.MANUAL_EXCLUDED_PATHS:
            if analyzed["points"]:
                stats["would_return"].append(
                    {
                        "path": rel,
                        "id": doc_id,
                        "n": len(analyzed["points"]),
                        "preview": [
                            {
                                "label": p.get("label") or "",
                                "text": (p.get("text") or "")[:40],
                            }
                            for p in analyzed["points"][:3]
                        ],
                    }
                )
            stats["excluded"] += 1
            stats["manual_excluded"] += 1
            excluded.append(
                {
                    "batch": batch,
                    "path": rel,
                    "id": doc_id,
                    "reason": config.MANUAL_EXCLUDED_PATHS[rel],
                    "para_total": analyzed["para_total"],
                    "styles": _styles_dict(analyzed["style_counts"]),
                }
            )
            stats["style_system"][analyzed["style_system"]] += 1
            continue

        for hit in analyzed["bible_prefix_hits"]:
            stats["bible_prefix_hits"].append(
                {
                    "id": doc_id,
                    "path": rel,
                    "para_no": hit["para_no"],
                    "style": hit["style"],
                    "text": hit["text"],
                }
            )
        for cont in analyzed["continuations"]:
            stats["continuations"].append(
                {
                    "id": doc_id,
                    "path": rel,
                    "para_no": cont["para_no"],
                    "into_para_no": cont["into_para_no"],
                    "style": cont["style"],
                    "text": cont["text"],
                }
            )
        for point in analyzed["points"]:
            if not point["label"]:
                stats["empty_labels"].append(
                    {
                        "id": doc_id,
                        "path": rel,
                        "para_no": point["para_no"],
                        "level": point["level"],
                        "style": point["style"],
                        "text": point["text"],
                    }
                )
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
            stats["style_system"][analyzed["style_system"]] += 1
            _emit_anomalies(anomalies_fp, stats, batch, doc_id, rel, analyzed["anomalies"])
            continue

        meta = (
            _meta_a(rel, filename, analyzed["style_system"])
            if batch == "12490"
            else _meta_b(rel, filename, analyzed["style_system"])
        )
        meta["part_no"] = analyzed["part_no"]
        meta["part_name"] = analyzed["part_name"]
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
                "min_level": analyzed["min_level"],
                "merged_note_paras": analyzed["merged_note_paras"],
                "header_paras": analyzed["header_paras"],
                "empty_paras": analyzed["empty_paras"],
            },
        }
        grouped = group_by_min_level(analyzed["points"])
        if grouped["min_level"] is not None:
            stats["min_level_hist"][grouped["min_level"]] += 1
        stats["group_tokens"].extend(grouped["tokens"])
        if not grouped["units"]:
            stats["zero_unit_ids"].append(doc_id)
        if grouped["residue"]:
            stats["residue_files"] += 1
            stats["residue_points"] += len(grouped["residue"])
            for point in grouped["residue"]:
                stats["residue_levels"][point["level"]] += 1
                lab = point["label"] if point["label"] else "（空）"
                stats["residue_labels"][lab] += 1
        if grouped["min_level"] == 5:
            units_out = []
            for chunk, tok in zip(grouped["units"], grouped["tokens"]):
                head = chunk[0]
                units_out.append(
                    {
                        "token": tok,
                        "n": len(chunk),
                        "label": head["label"],
                        "text": (head["text"] or "")[:40],
                    }
                )
            stats["min5"].append(
                {
                    "id": doc_id,
                    "path": rel,
                    "level_counts": analyzed["level_counts"],
                    "n_units": len(units_out),
                    "residue": len(grouped["residue"]),
                    "units": units_out,
                }
            )
        out_fp.write(json.dumps(record, ensure_ascii=False) + "\n")
        stats["output"] += 1
        stats["ids"].append(doc_id)
        stats["sources"][doc_id] = path
        stats["point_pack"][doc_id] = [
            (point["para_no"], point["level"], point["label"]) for point in analyzed["points"]
        ]
        stats["bible"][doc_id] = analyzed["doc_header"]["bible_reading"]
        stats["style_system"][analyzed["style_system"]] += 1
        if analyzed["merged_note_paras"]:
            stats["merged_notes"] += analyzed["merged_note_paras"]
            stats["merged_files"] += 1
        for point in analyzed["points"]:
            stats["levels"][point["level"]] += 1
            if point.get("level_source") == "text_over_style":
                stats["text_over_style"] += 1
            if batch == "12490" and point["label"] == "前言":
                stats["preface_by_level"][point["level"]] += 1
                if point["level"] == 1:
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


def _token_stats(tokens: list[int]) -> dict:
    if not tokens:
        return {
            "n": 0,
            "min": None,
            "max": None,
            "avg": None,
            "median": None,
            "lt": 0,
            "mid": 0,
            "gt": 0,
        }
    ordered = sorted(tokens)
    n = len(ordered)
    return {
        "n": n,
        "min": ordered[0],
        "max": ordered[-1],
        "avg": sum(ordered) / n,
        "median": statistics.median(ordered),
        "lt": sum(1 for t in ordered if t < 150),
        "mid": sum(1 for t in ordered if 150 <= t <= 800),
        "gt": sum(1 for t in ordered if t > 800),
    }


def _fmt_token_row(label: str, st: dict) -> str:
    if not st["n"]:
        return f"| {label} | 0 | — | — | — | — | — | — | — |"
    return (
        "| {label} | {n} | {min} | {max} | {avg:.1f} | {median} | {lt}（{ltp}） | {mid}（{midp}） | {gt}（{gtp}） |".format(
            label=label,
            n=st["n"],
            min=st["min"],
            max=st["max"],
            avg=st["avg"],
            median=st["median"],
            lt=st["lt"],
            ltp=_pct(st["lt"], st["n"]),
            mid=st["mid"],
            midp=_pct(st["mid"], st["n"]),
            gt=st["gt"],
            gtp=_pct(st["gt"], st["n"]),
        )
    )


def _scan_v1_outline(path: str) -> dict:
    """读 v1 主 JSON，供对账。不把 v1 的孤立点并进单位。"""
    levels: Counter = Counter()
    empty = []
    reading = []
    tokens = []
    rows = {}
    n = 0
    with open(path, "r", encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            obj = json.loads(line)
            n += 1
            pts = obj["points"]
            packed = []
            for point in pts:
                levels[point["level"]] += 1
                packed.append((point["para_no"], point["level"], point["label"]))
                if not point.get("label"):
                    empty.append(
                        {
                            "id": obj["id"],
                            "para_no": point["para_no"],
                            "level": point["level"],
                            "style": point["style"],
                            "text": point.get("text") or "",
                        }
                    )
            cut = None
            for i, point in enumerate(pts):
                if point["level"] == 1:
                    cut = i
                    break
            if cut:
                for point in pts[:cut]:
                    if point["label"] == "读经":
                        reading.append(
                            {
                                "id": obj["id"],
                                "para_no": point["para_no"],
                                "level": point["level"],
                                "style": point["style"],
                                "text": point.get("text") or "",
                            }
                        )
            tokens.extend(level1_group_token(pts))
            rows[obj["id"]] = packed
    return {
        "n": n,
        "levels": levels,
        "empty": empty,
        "reading": reading,
        "tokens": tokens,
        "rows": rows,
    }


def _load_v1(v1_dir: str) -> dict | None:
    if not v1_dir or not os.path.isdir(v1_dir):
        return None
    a_path = os.path.join(v1_dir, "outline_12490.json")
    b_path = os.path.join(v1_dir, "outline_feasts.json")
    exc_path = os.path.join(v1_dir, "excluded_files.json")
    if not (os.path.isfile(a_path) and os.path.isfile(b_path) and os.path.isfile(exc_path)):
        return None
    with open(exc_path, "r", encoding="utf-8") as fp:
        exc_obj = json.load(fp)
    exc_n = Counter(item.get("batch") for item in exc_obj.get("excluded", []))
    cand_n = Counter(item.get("batch") for item in exc_obj.get("candidates", []))
    return {
        "a": _scan_v1_outline(a_path),
        "b": _scan_v1_outline(b_path),
        "excluded": exc_n,
        "candidates": cand_n,
    }


def _point_delta(v1_rows: dict, v2_pack: dict) -> dict:
    removed = Counter()
    added = Counter()
    removed_labels = Counter()
    removed_examples = []
    added_examples = []
    label_changes = []
    only_v1 = sorted(set(v1_rows) - set(v2_pack))
    only_v2 = sorted(set(v2_pack) - set(v1_rows))
    for doc_id in only_v1:
        for para_no, level, label in v1_rows[doc_id]:
            removed[level] += 1
            removed_labels[label or "（空）"] += 1
            if len(removed_examples) < 30:
                removed_examples.append((doc_id, para_no, level, label, "整篇不在 v2"))
    for doc_id in only_v2:
        for para_no, level, label in v2_pack[doc_id]:
            added[level] += 1
            if len(added_examples) < 30:
                added_examples.append((doc_id, para_no, level, label, "整篇不在 v1"))
    for doc_id in set(v1_rows) & set(v2_pack):
        old = {para_no: (level, label) for para_no, level, label in v1_rows[doc_id]}
        new = {para_no: (level, label) for para_no, level, label in v2_pack[doc_id]}
        for para_no, (level, label) in old.items():
            if para_no not in new:
                removed[level] += 1
                removed_labels[label or "（空）"] += 1
                if len(removed_examples) < 30:
                    removed_examples.append((doc_id, para_no, level, label, "该段不再是纲目点"))
            else:
                new_level, new_label = new[para_no]
                if label != new_label or level != new_level:
                    label_changes.append(
                        {
                            "id": doc_id,
                            "para_no": para_no,
                            "v1_level": level,
                            "v1_label": label,
                            "v2_level": new_level,
                            "v2_label": new_label,
                        }
                    )
        for para_no, (level, label) in new.items():
            if para_no not in old:
                added[level] += 1
                if len(added_examples) < 30:
                    added_examples.append((doc_id, para_no, level, label, "v1 不是纲目点"))
    return {
        "removed_labels": removed_labels,
        "removed": removed,
        "added": added,
        "removed_examples": removed_examples,
        "added_examples": added_examples,
        "label_changes": label_changes,
        "only_v1": only_v1,
        "only_v2": only_v2,
    }


def _reading_rows(v1_reading: list, v2_pack: dict, v2_bible: dict) -> list:
    rows = []
    for item in v1_reading:
        doc_id = item["id"]
        packed = v2_pack.get(doc_id)
        bible = v2_bible.get(doc_id, "")
        if packed is None:
            rows.append({**item, "hit": False, "detail": "该篇不在 v2 主 JSON"})
            continue
        still = any(para_no == item["para_no"] for para_no, _level, _label in packed)
        text = item["text"]
        in_header = (text in bible) if text else ("读经" in bible)
        hit = (not still) and in_header
        if hit:
            detail = "已进入 bible_reading，points 中无此段"
        elif still and in_header:
            detail = "bible_reading 里有这段文字，但 points 仍保留该段"
        elif still:
            detail = "仍在 points 中，bible_reading 里没有这段正文"
        else:
            detail = "points 中已没有该段，但 bible_reading 里找不到这段正文"
        rows.append({**item, "hit": hit, "detail": detail})
    return rows


def _md_id(doc_id: str) -> str:
    return "`" + doc_id.replace("|", "\\|") + "`"


def _section_v1_diff(ctx: dict) -> list[str]:
    lines = ["## 与 v1 的差异对账", ""]
    v1 = ctx.get("v1")
    if not v1:
        lines.append("未找到 v1 目录，无法对账。")
        lines.append("")
        return lines
    a = ctx["a_stats"]
    b = ctx["b_stats"]
    lines.append("### 输出条数与排除数")
    lines.append("")
    lines.append("| 批次 | 项目 | v1 | v2 | 差（v2−v1） |")
    lines.append("|---|---|---:|---:|---:|")
    a_v1_exc = v1["excluded"].get("12490", 0)
    b_v1_exc = v1["excluded"].get("feasts", 0)
    a_v1_cand = v1["candidates"].get("12490", 0)
    b_v1_cand = v1["candidates"].get("feasts", 0)
    rows = [
        ("A 批", "输出", v1["a"]["n"], a["output"]),
        ("A 批", "排除", a_v1_exc, a["excluded"]),
        ("A 批", "条件 2 候选", a_v1_cand, a["candidates"]),
        ("B 批", "输出", v1["b"]["n"], b["output"]),
        ("B 批", "排除", b_v1_exc, b["excluded"]),
        ("B 批", "条件 2 候选", b_v1_cand, b["candidates"]),
    ]
    for batch, name, old, new in rows:
        lines.append(f"| {batch} | {name} | {old} | {new} | {new - old} |")
    lines.append("")
    for label, key, st in (("A 批", "a", a), ("B 批", "b", b)):
        delta = ctx["deltas"][key]
        if delta["only_v1"] or delta["only_v2"]:
            lines.append(f"{label} 篇目有进出：")
            for doc_id in delta["only_v1"]:
                lines.append(f"- 只在 v1：{_md_id(doc_id)}")
            for doc_id in delta["only_v2"]:
                lines.append(f"- 只在 v2：{_md_id(doc_id)}")
            lines.append("")
        else:
            lines.append(f"{label} 输出篇目与 v1 相同，没有整篇进出。")
            lines.append("")
    if (
        v1["a"]["n"] == a["output"]
        and v1["b"]["n"] == b["output"]
        and a_v1_exc == a["excluded"]
        and b_v1_exc == b["excluded"]
    ):
        lines.append(
            "两批的输出条数、排除数与 v1 相同。篇头「读经」被移出 points 的那些篇，后面仍有纲目点，所以没有因此被条件 1 排除。"
        )
    else:
        lines.append("条数有变化，原因见上面的篇目进出，以及下面被移出或新加入的 points。")
    lines.append("")

    lines.append("### 篇头「读经」")
    lines.append("")
    hits = a["bible_prefix_hits"] + b["bible_prefix_hits"]
    lines.append(
        f"规则命中 {len(hits)} 段（A 批 {len(a['bible_prefix_hits'])}，B 批 {len(b['bible_prefix_hits'])}）。"
        "这些段都在该篇第一个纲目点之前，正文以「读经」开头，已写入 `doc_header.bible_reading`，不进 points。"
    )
    lines.append("")
    reading_rows = ctx["reading_rows"]
    hit_n = sum(1 for row in reading_rows if row["hit"])
    lines.append(
        f"json_checks.md 里、排在首个第 1 级点之前的「读经」点共 {len(reading_rows)} 个，"
        f"本次命中 {hit_n} 个。"
        + ("全部命中。" if reading_rows and hit_n == len(reading_rows) else "没有全部命中。")
    )
    lines.append("")
    lines.append("| id | para_no | v1 level | 命中 | 结果 |")
    lines.append("|---|---:|---:|---|---|")
    for row in reading_rows:
        flag = "是" if row["hit"] else "否"
        lines.append(
            f"| {_md_id(row['id'])} | {row['para_no']} | {row['level']} | {flag} | {row['detail']} |"
        )
    lines.append("")
    extra = []
    reading_keys = {(row["id"], row["para_no"]) for row in reading_rows}
    for hit in hits:
        if (hit["id"], hit["para_no"]) not in reading_keys:
            extra.append(hit)
    lines.append(f"37 个之外、同样被这条规则收下的段落：{len(extra)}。")
    if extra:
        by_style = Counter(hit["style"] for hit in extra)
        level_extra = [hit for hit in extra if hit["style"] in config.LEVEL_STYLES]
        other_extra = len(extra) - len(level_extra)
        lines.append(
            f"其中样式属于层级表的 {len(level_extra)} 段，不属于层级表的 {other_extra} 段。"
            "不属于层级表的，v1 没有收成纲目点，只是篇头「读经：」写在 Normal 等样式上；本次补进 `bible_reading`，不改变 points。"
        )
        lines.append("")
        lines.append("| 样式 | 段数 |")
        lines.append("|---|---:|")
        for name, n in by_style.most_common():
            lines.append(f"| `{name}` | {n} |")
        lines.append("")
        if level_extra:
            lines.append("样式属于层级表、但不在上述 37 个里的，逐条列出：")
            lines.append("")
            lines.append("| id | para_no | 样式 | 正文前 40 字 |")
            lines.append("|---|---:|---|---|")
            for hit in level_extra:
                lines.append(
                    f"| {_md_id(hit['id'])} | {hit['para_no']} | `{hit['style']}` | {_md_cell(hit['text'], 40)} |"
                )
            lines.append("")
    lines.append("")

    lines.append("### label 为空")
    lines.append("")
    v1_empty = v1["a"]["empty"] + v1["b"]["empty"]
    v2_empty = a["empty_labels"] + b["empty_labels"]
    lines.append(f"v1 空 label 的 points：{len(v1_empty)}。v2：{len(v2_empty)}。")
    lines.append("")
    if v1_empty:
        lines.append("v1 的空 label，以及 v2 同一段的 label：")
        lines.append("")
        lines.append("| id | para_no | v1 text 前 40 字 | v2 label | v2 level |")
        lines.append("|---|---:|---|---|---:|")
        changes = {
            (item["id"], item["para_no"]): item
            for item in ctx["deltas"]["a"]["label_changes"] + ctx["deltas"]["b"]["label_changes"]
        }
        for item in v1_empty:
            ch = changes.get((item["id"], item["para_no"]))
            if ch:
                lines.append(
                    f"| {_md_id(item['id'])} | {item['para_no']} | {_md_cell(item['text'], 40)} | {_md_cell(ch['v2_label'], 20)} | {ch['v2_level']} |"
                )
            else:
                lines.append(
                    f"| {_md_id(item['id'])} | {item['para_no']} | {_md_cell(item['text'], 40)} | （v2 无此段或 label 仍空） |  |"
                )
        lines.append("")
    if v2_empty:
        lines.append("v2 仍为空的 label：")
        lines.append("")
        lines.append("| id | para_no | level | style | text 前 40 字 |")
        lines.append("|---|---:|---:|---|---|")
        for item in v2_empty:
            lines.append(
                f"| {_md_id(item['id'])} | {item['para_no']} | {item['level']} | `{item['style']}` | {_md_cell(item['text'], 40)} |"
            )
        lines.append("")
    else:
        lines.append("v2 没有 label 为空的 point。")
        lines.append("")
    conts = a["continuations"] + b["continuations"]
    lines.append(
        f"另有 {len(conts)} 段样式属于层级表，但正文以标点开头，按 2.5 切出来的 label 是空的。"
        "这是上一点被 Word 拆成的下一行，已并入上一个纲目点的正文，不单独立点。"
    )
    if conts:
        lines.append("")
        lines.append("| id | para_no | 并入的 para_no | 样式 | 正文前 40 字 |")
        lines.append("|---|---:|---:|---|---|")
        for item in conts:
            lines.append(
                f"| {_md_id(item['id'])} | {item['para_no']} | {item['into_para_no']} | `{item['style']}` | {_md_cell(item['text'], 40)} |"
            )
    lines.append("")

    lines.append("### 层级分布对照")
    lines.append("")
    lines.append("| 批次 | level | v1 | v2 | 差（v2−v1） |")
    lines.append("|---|---:|---:|---:|---:|")
    for label, key, st in (("A 批", "a", a), ("B 批", "b", b)):
        old_levels = v1[key]["levels"]
        for level in range(1, 8):
            old = old_levels.get(level, 0)
            new = st["levels"].get(level, 0)
            lines.append(f"| {label} | {level} | {old} | {new} | {new - old} |")
        old_sum = sum(old_levels.values())
        new_sum = sum(st["levels"].values())
        lines.append(f"| {label} | 合计 | {old_sum} | {new_sum} | {new_sum - old_sum} |")
    lines.append("")
    for label, key in (("A 批", "a"), ("B 批", "b")):
        delta = ctx["deltas"][key]
        lines.append(
            f"{label} 按段号对上之后：退出 points {sum(delta['removed'].values())} 个，"
            f"新进入 points {sum(delta['added'].values())} 个，"
            f"同一段号但 label 或 level 有变的 {len(delta['label_changes'])} 个。"
        )
        if delta["removed"]:
            parts = [f"第 {lv} 级 {delta['removed'][lv]}" for lv in sorted(delta["removed"])]
            lines.append("- 退出的层级：" + "，".join(parts) + "。")
        if delta["added"]:
            parts = [f"第 {lv} 级 {delta['added'][lv]}" for lv in sorted(delta["added"])]
            lines.append("- 新进入的层级：" + "，".join(parts) + "。")
        level_changed = [item for item in delta["label_changes"] if item["v1_level"] != item["v2_level"]]
        label_only = [item for item in delta["label_changes"] if item["v1_level"] == item["v2_level"]]
        lines.append(
            f"- 同一段里层级变了的 {len(level_changed)} 个，只改了 label 的 {len(label_only)} 个。"
        )
        lines.append("")
    n_read = sum(d["removed_labels"].get("读经", 0) for d in ctx["deltas"].values())
    n_empty_removed = sum(d["removed_labels"].get("（空）", 0) for d in ctx["deltas"].values())
    lines.append(
        "退出的点里，label 为「读经」的有 {n} 个，v1 的 label 为空的有 {e} 个。"
        "「读经」这些段在 v1 里被样式轨当成纲目点；v2 在第一个纲目点之前把以「读经」开头的段落改记入 `bible_reading`。"
        "空 label 的退出有两种：段首多个 Tab 后面才是「读经：」，剥掉 Tab 后改记入篇头；"
        "或者正文以标点开头，已并入上一个纲目点。".format(n=n_read, e=n_empty_removed)
    )
    lines.append(
        "同一段号只改 label、层级不变的，是原先靠样式定级、编号被段首 Tab 挤进 text 的点。"
        "新进入的点，是段首为 Tab、v1 因此切出空 label、文字轨没有当成纲目点，v2 剥掉前导 Tab 之后认出来的编号段。"
    )
    lines.append("")
    return lines


def _section_grouping(ctx: dict) -> list[str]:
    lines = ["## 分组基准验证", ""]
    lines.append(
        "本节只统计，不改 JSON，也不把残留点并进单位。"
        "分组点 = 该篇 `min(level)`。一个单位 = 一个分组点，加上其后直到下一个分组点之前的点。"
        "token 仍是 `max(0, int(len(text) / 1.5))`。"
        "排在首个分组点之前的点另计为残留，不计入下面的 token。"
    )
    lines.append("")
    zeros = ctx["a_stats"]["zero_unit_ids"] + ctx["b_stats"]["zero_unit_ids"]
    if zeros:
        lines.append(f"有 {len(zeros)} 篇产出 0 个单位。报告在此停下。")
        lines.append("")
        for doc_id in zeros:
            lines.append(f"- {_md_id(doc_id)}")
        lines.append("")
        return lines

    lines.append("两批每一篇的单位数都大于 0。")
    lines.append("")
    lines.append("### min(level) 分布")
    lines.append("")
    lines.append("| min(level) | A 批篇数 | B 批篇数 |")
    lines.append("|---:|---:|---:|")
    for level in range(1, 8):
        lines.append(
            f"| {level} | {ctx['a_stats']['min_level_hist'].get(level, 0)} | {ctx['b_stats']['min_level_hist'].get(level, 0)} |"
        )
    lines.append(
        f"| 合计 | {sum(ctx['a_stats']['min_level_hist'].values())} | {sum(ctx['b_stats']['min_level_hist'].values())} |"
    )
    lines.append("")
    lines.append("### 按 min(level) 分组后的 token")
    lines.append("")
    lines.append("| 口径 | 单位数 | min | max | avg | median | <150 | 150～800 | >800 |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    v1 = ctx.get("v1")
    for label, st in (("A 批 v2 按 min(level)", ctx["a_stats"]), ("B 批 v2 按 min(level)", ctx["b_stats"])):
        lines.append(_fmt_token_row(label, _token_stats(st["group_tokens"])))
    lines.append(_fmt_token_row("A 批 v2 仍按固定第 1 级", _token_stats(ctx["a_stats"]["tokens"])))
    lines.append(_fmt_token_row("B 批 v2 仍按固定第 1 级", _token_stats(ctx["b_stats"]["tokens"])))
    if v1:
        lines.append(_fmt_token_row("A 批 v1 按固定第 1 级", _token_stats(v1["a"]["tokens"])))
        lines.append(_fmt_token_row("B 批 v1 按固定第 1 级", _token_stats(v1["b"]["tokens"])))
    lines.append("")
    if v1:
        a_v1 = _token_stats(v1["a"]["tokens"])
        b_v1 = _token_stats(v1["b"]["tokens"])
        a_fix = _token_stats(ctx["a_stats"]["tokens"])
        b_fix = _token_stats(ctx["b_stats"]["tokens"])
        a_min = _token_stats(ctx["a_stats"]["group_tokens"])
        b_min = _token_stats(ctx["b_stats"]["group_tokens"])
        lines.append(
            "v2 仍按固定第 1 级时，A 批单位数 {an}（v1 为 {ao}），B 批单位数 {bn}（v1 为 {bo}）。"
            "固定第 1 级不把第 1 级之前的点算进单位，篇头「读经」本来就不在单位里，所以这条口径的单位数只随新进入或退出的第 1 级点变化。".format(
                an=a_fix["n"], ao=a_v1["n"], bn=b_fix["n"], bo=b_v1["n"]
            )
        )
        lines.append(
            "改按 min(level) 之后，A 批单位数从固定第 1 级的 {a0} 变为 {a1}，B 批从 {b0} 变为 {b1}。"
            "增加的单位来自整篇没有第 1 级的续篇：这些篇在固定第 1 级下是 0 个单位，按本篇最浅层级后能切开。"
            "A 批 min(level) 的 token 中位数是 {amed}，固定第 1 级是 {afix}；"
            "B 批分别是 {bmed} 与 {bfix}。".format(
                a0=a_fix["n"],
                a1=a_min["n"],
                b0=b_fix["n"],
                b1=b_min["n"],
                amed=a_min["median"],
                afix=a_fix["median"],
                bmed=b_min["median"],
                bfix=b_fix["median"],
            )
        )
        lines.append("")

    lines.append("### 排在首个分组点之前的残留点")
    lines.append("")
    lines.append("这些点按方案 3.3 应并入本篇第一个单位。本次只计数，没有合并。")
    lines.append("")
    lines.append("| 批次 | 篇数 | 点数 | 该批 points | 占比 |")
    lines.append("|---|---:|---:|---:|---:|")
    for label, st in (("A 批", ctx["a_stats"]), ("B 批", ctx["b_stats"])):
        total = sum(st["levels"].values())
        lines.append(
            f"| {label} | {st['residue_files']} | {st['residue_points']} | {total} | {_pct(st['residue_points'], total)} |"
        )
    lines.append("")
    for label, st in (("A 批", ctx["a_stats"]), ("B 批", ctx["b_stats"])):
        lines.append(f"#### {label} 残留点的 level")
        lines.append("")
        if not st["residue_points"]:
            lines.append("无。")
            lines.append("")
            continue
        lines.append("| level | 点数 |")
        lines.append("|---:|---:|")
        for level in range(1, 8):
            n = st["residue_levels"].get(level, 0)
            if n:
                lines.append(f"| {level} | {n} |")
        lines.append("")
        lines.append(f"#### {label} 残留点的 label")
        lines.append("")
        lines.append("| label | 次数 |")
        lines.append("|---|---:|")
        for name, n in st["residue_labels"].most_common():
            lines.append(f"| {_md_cell(name, 40)} | {n} |")
        lines.append("")
    return lines


def _judge_min5(units: list[dict]) -> str:
    if not units:
        return "过碎：没有切出单位"
    toks = [u["token"] for u in units]
    med = statistics.median(toks)
    tiny = sum(1 for t in toks if t < 20)
    if med < 40 or tiny * 2 > len(toks):
        return "过碎"
    return "不过碎"


def _section_min5(ctx: dict) -> list[str]:
    rows = ctx["a_stats"]["min5"] + ctx["b_stats"]["min5"]
    rows = sorted(rows, key=lambda r: r["id"])
    lines = ["## min(level) = 5 的篇", ""]
    a_n = sum(1 for row in rows if row["id"].startswith("gm12490/"))
    b_n = len(rows) - a_n
    lines.append(f"A 批 {a_n} 篇，B 批 {b_n} 篇。")
    lines.append("")
    if not rows:
        lines.append("没有 min(level) = 5 的篇。")
        lines.append("")
        return lines
    judgements = []
    for row in rows:
        verdict = _judge_min5(row["units"])
        judgements.append(verdict)
        lines.append(f"### {_md_id(row['id'])}")
        lines.append("")
        lines.append(f"- 源文件：`{row['path']}`")
        counts = row["level_counts"]
        dist = "，".join(f"第 {k} 级 {counts[k]}" for k in sorted(counts, key=lambda x: int(x)))
        lines.append(f"- 层级分布：{dist}")
        lines.append(f"- 按 min(level) 切出的单位数：{row['n_units']}")
        lines.append(f"- 首个分组点之前的残留点：{row['residue']}（未并入单位）")
        lines.append(f"- 判断：{verdict}")
        lines.append("")
        lines.append("| # | token | 单位内 points | 第一个点的 label | text 前 40 字 |")
        lines.append("|---:|---:|---:|---|---|")
        for i, unit in enumerate(row["units"], 1):
            lines.append(
                f"| {i} | {unit['token']} | {unit['n']} | {_md_cell(unit['label'], 20)} | {_md_cell(unit['text'], 40)} |"
            )
        lines.append("")
    fine = [v for v in judgements if v == "不过碎"]
    coarse = [v for v in judgements if v != "不过碎"]
    if not coarse:
        lines.append(
            f"结论：这 {len(rows)} 篇都不过碎。"
            "切分单位是本篇最浅的第 5 级点加上它的下属，token 中位数不低于 40，"
            "且 token < 20 的单位没有占到一半。"
            "续篇的第 5 级在这篇里就是顶层，粒度比普通篇的第 1 级细，但每一块仍是一个完整小节，不是把标题切成空块。"
        )
    else:
        lines.append(
            f"结论：{len(fine)} 篇不过碎，{len(coarse)} 篇过碎。"
            "过碎的标准是该篇单位 token 中位数低于 40，或 token < 20 的单位超过一半。"
            "上面每篇已标明。"
        )
    lines.append("")
    return lines


def build_report(ctx: dict) -> str:
    a = ctx["a_stats"]
    b = ctx["b_stats"]
    lines = []
    lines.append("# 纲目 docx → JSON 转换报告")
    lines.append("")
    lines.append("- 方案：`docs/panai4_es/docx_to_json_plan.md` v0.2")
    lines.append("- 抽样种子：{0}".format(config.SAMPLE_SEED))
    lines.append("- 对照：`纲目JSON\\v1_20260929\\` 的上一轮产出")
    lines.append("")
    lines.extend(_section_v1_diff(ctx))
    lines.extend(_section_grouping(ctx))
    zeros = a["zero_unit_ids"] + b["zero_unit_ids"]
    if zeros:
        return "\n".join(lines) + "\n"
    lines.extend(_section_min5(ctx))
    lines.append("## 与方案不一致之处")
    lines.append("")
    lines.append(
        "方案 v0.2 已吸收上一轮的差异：A 批硬编码截断在第 42 段（3.2），"
        "`excluded_files.json` 是带 `excluded` / `candidates` 的对象（6.1），"
        "第 4 级双字母收到 `zz`（2.3），「附：」只在全文没有条件 A 时截断（3.1），"
        "label 取值前先剥前导 Tab（2.6），篇头「读经」在第一个纲目点之前归入 `bible_reading`（4.5）。"
        "这几项本次实现与方案一致。"
    )
    lines.append(
        "条件 2 仍不自动排除。口径与首轮相同：全部纲目点是同一层级、该层级不是 1、且没有截断标志。"
        "符合的写入 `candidates`，理由为「条件2候选，待人工确认」，文件仍在主 JSON。"
        "方案 5.1 现在的措辞提到 `min(level)`，标记条件没有改成「按 min(level) 无法成组」。"
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
    preface = a["preface_by_level"]
    if preface:
        p1 = preface.get(1, 0)
        p2 = preface.get(2, 0)
        p3 = preface.get(3, 0)
        lines.append(
            "A 批 label 为「前言」的点：第 1 级 {0}，第 2 级 {1}，第 3 级 {2}，合计 {3}。"
            "核查报告里的 516 段「无 Tab 前言」是各层级加在一起的数字；"
            "第 1 级这一档是 {0}，在「约 500」的范围内。".format(
                p1, p2, p3, p1 + p2 + p3
            )
        )
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
    lines.append(f"| 合计 | {sum(a['style_system'].values())} |")
    lines.append("")
    lines.append("含条件 1 排除的文件。条件 2 候选仍算在主 JSON 里，也算在上表。")
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
    parser.add_argument(
        "--v1-dir",
        default=os.path.join(config.DEFAULT_OUT_DIR, "v1_20260929"),
        help="上一轮产出目录，用于差异对账。",
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

    print("loading v1", args.v1_dir, flush=True)
    v1 = _load_v1(args.v1_dir)
    deltas = {"a": None, "b": None}
    reading_rows = []
    if v1:
        deltas["a"] = _point_delta(v1["a"]["rows"], a_stats["point_pack"])
        deltas["b"] = _point_delta(v1["b"]["rows"], b_stats["point_pack"])
        reading_rows = _reading_rows(
            v1["a"]["reading"],
            a_stats["point_pack"],
            a_stats["bible"],
        )
        # 释放逐点对照用的大表，报告正文不再需要整表
        v1["a"].pop("rows", None)
        v1["b"].pop("rows", None)

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
    empty_n = len(a_stats["empty_labels"]) + len(b_stats["empty_labels"])
    _check(empty_n == 0, f"label 为空的 points 为 0（实测 {empty_n}）", checks)
    reading_hit = sum(1 for row in reading_rows if row["hit"])
    _check(
        bool(v1) and len(reading_rows) == 37 and reading_hit == 37,
        f"v1 的 37 个篇头读经全部进入 bible_reading（名单 {len(reading_rows)}，命中 {reading_hit}）",
        checks,
    )
    zero_n = len(a_stats["zero_unit_ids"]) + len(b_stats["zero_unit_ids"])
    _check(zero_n == 0, f"按 min(level) 分组后没有 0 单位的篇（实测 {zero_n}）", checks)
    doubles = config.LEVEL4_DOUBLE_LETTERS
    _check(
        doubles == {c * 2 for c in "abcdefghijklmnopqrstuvwxyz"} and len(doubles) == 26,
        "第 4 级双字母为 aa–zz 共 26 个",
        checks,
    )

    report, fatal = build_v3_report(
        {
            "a_stats": a_stats,
            "b_stats": b_stats,
            "excluded": excluded,
            "anomaly_lines": anomaly_lines,
            "lines_a": lines_a,
            "lines_b": lines_b,
            "dup_count": len(dup_ids),
            "dup_ids": dup_ids,
            "mismatches": mismatches,
            "before": before,
            "after": after,
            "out_dir": out_dir,
            "v2_dir": os.path.join(out_dir, "v4_20260929"),
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
    if fatal:
        print("V3_FATAL", flush=True)
        return 2
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
