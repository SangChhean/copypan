# -*- coding: utf-8 -*-
"""纲目 JSON → chunks。只切块，不生成向量，不建索引。"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import statistics
import sys
from collections import Counter, defaultdict

from . import config

NOTES_PATH = (
    r"2 李常受文集纲目\35 李常受文集一九六〇年第二册\03 李常受弟兄个人笔记"
    r"\李常受弟兄个人笔记.docx"
)
GOSPEL_MARK = "福音题纲"
_INDEX_RE = re.compile(r"^\d+\s+")
_YEAR_RANGE_RE = re.compile(
    r"([〇零一二三四五六七八九]{4})至([〇零一二三四五六七八九]{4})年"
)
_YEAR_ONE_RE = re.compile(r"([〇零一二三四五六七八九]{4})年")
_FEAST_RE = re.compile(r"^(\d{4})-\d{2}\s+(.+)$")


def _cn_year(text: str) -> int:
    return int("".join(config.CN_YEAR_TO_INT[ch] for ch in text))


def strip_dir_index(name: str) -> str:
    return _INDEX_RE.sub("", name or "", count=1)


def split_units(points: list, min_level: int) -> list:
    """按 min_level 切单位。首个分组点之前的残留点并入第一个单位。"""
    if not points or min_level is None:
        return []
    first = None
    for i, point in enumerate(points):
        if point.get("level") == min_level:
            first = i
            break
    if first is None:
        return []
    units = []
    i = first
    n = len(points)
    while i < n:
        if points[i].get("level") != min_level:
            i += 1
            continue
        j = i + 1
        while j < n and points[j].get("level") != min_level:
            j += 1
        if not units:
            units.append(points[:j])
        else:
            units.append(points[i:j])
        i = j
    return units


def render_point(point: dict, min_level: int) -> str:
    gap = point.get("level", min_level) - min_level
    if gap < 0:
        gap = 0
    indent = config.IDEOGRAPHIC_SPACE * gap
    label = point.get("label") or ""
    lines = (point.get("text") or "").split("\n")
    if not lines:
        lines = [""]
    rendered = [indent + label + config.IDEOGRAPHIC_SPACE + lines[0]]
    for extra in lines[1:]:
        rendered.append(indent + extra)
    return "\n".join(rendered)


def render_header(book_title: str | None, message_title: str | None) -> str:
    """v0.2：第一行 = book_title + 全角空格 + message_title。"""
    return "{0}{1}{2}".format(
        book_title or "",
        config.IDEOGRAPHIC_SPACE,
        message_title or "",
    )


def render_unit(
    points: list,
    min_level: int,
    book_title: str | None = None,
    message_title: str | None = None,
) -> str:
    body = "\n".join(render_point(point, min_level) for point in points)
    return render_header(book_title, message_title) + "\n\n" + body


def book_path_of(meta: dict, batch: str) -> list:
    if batch == "feasts":
        conference = meta.get("conference")
        return [conference] if conference else []
    raw = meta.get("book_path") or []
    return [strip_dir_index(part) for part in raw]


def book_title_of(meta: dict, batch: str, book_path: list) -> str | None:
    if batch == "feasts":
        conference = meta.get("conference") or ""
        matched = _FEAST_RE.match(conference.strip())
        if not matched:
            return None
        return "{0}年{1}".format(matched.group(1), matched.group(2).strip())
    if not book_path:
        return None
    if len(book_path) >= 2:
        override = config.BOOK_TITLE_OVERRIDES.get((book_path[0], book_path[1]))
        if override:
            return override
    rest = book_path[1:]
    if not rest:
        return book_path[0] or None
    return "，".join(part for part in rest if part) or book_path[0]


def years_of(meta: dict, batch: str, book_path: list) -> tuple:
    if batch == "feasts":
        year = meta.get("year")
        return year, year
    if len(book_path) < 2:
        return None, None
    volume = book_path[1]
    ranged = _YEAR_RANGE_RE.search(volume)
    if ranged:
        return _cn_year(ranged.group(1)), _cn_year(ranged.group(2))
    one = _YEAR_ONE_RE.search(volume)
    if one:
        value = _cn_year(one.group(1))
        return value, value
    return None, None


def author_of(meta: dict, batch: str):
    if batch != "12490":
        return None
    category = meta.get("category") or ""
    return config.AUTHOR_BY_CATEGORY.get(category, config.AUTHOR_DEFAULT_A)


def chunk_id_of(prefix: str, message_key: str, index: int) -> str:
    digest = hashlib.sha1(message_key.encode("utf-8")).hexdigest()[:12]
    return "{0}_{1}_c{2}".format(prefix, digest, index)


def _null(value):
    if value is None or value == "":
        return None
    return value


def build_message_chunks(record: dict) -> list:
    meta = record.get("meta") or {}
    stats = record.get("stats") or {}
    points = record.get("points") or []
    batch = record.get("batch") or ""
    message_key = record.get("id") or ""
    min_level = stats.get("min_level")
    if min_level is None and points:
        min_level = min(point.get("level") for point in points)
    units = split_units(points, min_level)
    book_path = book_path_of(meta, batch)
    year, year_end = years_of(meta, batch, book_path)
    title = book_title_of(meta, batch, book_path)
    prefix = config.CHUNK_ID_PREFIX.get(batch, batch)
    total = len(units)
    chunks = []
    message_title = _null(meta.get("title"))
    for index, unit in enumerate(units, 1):
        text = render_unit(unit, min_level, title, message_title)
        para_nos = sorted(point.get("para_no") for point in unit if point.get("para_no") is not None)
        chunks.append(
            {
                "chunk_id": chunk_id_of(prefix, message_key, index),
                "message_key": message_key,
                "source_path": meta.get("source_path"),
                "batch": batch,
                "text": text,
                "book_title": title,
                "book_path": book_path,
                "message_title": message_title,
                "message_number": meta.get("msg_no"),
                "author": author_of(meta, batch),
                "year": year,
                "year_end": year_end,
                "paragraph_type": config.PARAGRAPH_TYPE_OUTLINE,
                "tokens": int(len(text) / 1.5),
                "min_level": min_level,
                "point_count": len(unit),
                "chunk_index": index,
                "chunk_total": total,
                "para_nos": para_nos,
                "part_no": meta.get("part_no"),
                "part_name": _null(meta.get("part_name")),
                "conference": meta.get("conference") if batch == "feasts" else None,
                "month": meta.get("month") if batch == "feasts" else None,
                "_points": points,
                "_unit": unit,
                "_source": meta.get("source_path") or "",
            }
        )
    return chunks


def _file_size(path: str) -> int:
    return os.path.getsize(path) if os.path.isfile(path) else 0


def _pct(n, total):
    if not total:
        return "0.0%"
    return "{0:.1f}%".format(n / total * 100)


def _token_row(label, tokens):
    if not tokens:
        return "| {0} | 0 | | | | | | | |".format(label)
    ordered = sorted(tokens)
    n = len(ordered)
    lt = sum(1 for t in ordered if t < 150)
    mid = sum(1 for t in ordered if 150 <= t <= 800)
    gt = sum(1 for t in ordered if t > 800)
    return "| {0} | {1} | {2} | {3} | {4:.1f} | {5} | {6}（{7}） | {8}（{9}） | {10}（{11}） |".format(
        label, n, ordered[0], ordered[-1], sum(ordered) / n, statistics.median(ordered),
        lt, _pct(lt, n), mid, _pct(mid, n), gt, _pct(gt, n),
    )


def _token_stats(tokens: list) -> dict:
    if not tokens:
        return {"n": 0, "min": None, "max": None, "avg": None, "median": None, "lt": 0, "mid": 0, "gt": 0}
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


def _compare_v01(v01_dir: str, a_out: str, b_out: str) -> dict:
    """与 v0.1 chunks 逐条比对 chunk_id，并收集 v0.1 token 分布。"""
    result = {
        "ok": True,
        "count_v01": {"12490": 0, "feasts": 0},
        "count_v02": {"12490": 0, "feasts": 0},
        "id_mismatch": [],
        "tokens_v01": {"12490": [], "feasts": []},
        "missing_v01": False,
    }
    pairs = (
        ("12490", os.path.join(v01_dir, "chunks_12490.json"), a_out),
        ("feasts", os.path.join(v01_dir, "chunks_feasts.json"), b_out),
    )
    for batch, old_path, new_path in pairs:
        if not os.path.isfile(old_path):
            result["missing_v01"] = True
            result["ok"] = False
            continue
        with open(old_path, encoding="utf-8") as old_fp, open(new_path, encoding="utf-8") as new_fp:
            while True:
                old_line = old_fp.readline()
                new_line = new_fp.readline()
                old_empty = not old_line or not old_line.strip()
                new_empty = not new_line or not new_line.strip()
                if old_empty and new_empty:
                    if not old_line and not new_line:
                        break
                    continue
                if old_empty or new_empty:
                    result["ok"] = False
                    if len(result["id_mismatch"]) < 50:
                        result["id_mismatch"].append((batch, "(行数不一致)", "(行数不一致)"))
                    break
                old = json.loads(old_line)
                new = json.loads(new_line)
                result["count_v01"][batch] += 1
                result["count_v02"][batch] += 1
                result["tokens_v01"][batch].append(old.get("tokens") or 0)
                if old.get("chunk_id") != new.get("chunk_id"):
                    result["ok"] = False
                    if len(result["id_mismatch"]) < 50:
                        result["id_mismatch"].append((
                            new.get("message_key"),
                            old.get("chunk_id"),
                            new.get("chunk_id"),
                        ))
    return result


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="纲目 JSON 切成 chunks")
    parser.add_argument("--out", default=config.DEFAULT_OUT_DIR)
    parser.add_argument(
        "--report",
        default=os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))),
            "docs", "panai4_es", "chunking_report.md",
        ),
    )
    args = parser.parse_args(argv)
    out_dir = args.out
    a_path = os.path.join(out_dir, "outline_12490.json")
    b_path = os.path.join(out_dir, "outline_feasts.json")
    before = {"a": _file_size(a_path), "b": _file_size(b_path)}

    for name in ("chunks_12490.json", "chunks_feasts.json"):
        existing = os.path.join(out_dir, name)
        if os.path.isfile(existing):
            n = 1
            while True:
                folder = os.path.join(out_dir, "chunks_v{0}_20260929".format(n))
                if not os.path.exists(folder):
                    break
                n += 1
            os.makedirs(folder)
            os.replace(existing, os.path.join(folder, name))

    seen_ids = {}
    collisions = []
    zero_units = []
    mismatches = []
    index_bad = []
    tokens = {"12490": [], "feasts": []}
    zero_token = []
    book_title_counts = {"12490": Counter(), "feasts": Counter()}
    year_by_layer = Counter()
    year_filled = Counter()
    year_total = Counter()
    part_filled = 0
    part_outside = []
    conf_filled = 0
    month_filled = 0
    conf_outside = 0
    part_box = [0]
    conf_box = [0, 0, 0]
    author_box = [0, 0]
    miss_box = [0, 0]
    header_bad = []
    files = {"12490": 0, "feasts": 0}
    chunk_n = {"12490": 0, "feasts": 0}
    samples = {"a": [], "b": [], "gospel": [], "notes": None, "note_demo": None}
    cwwl_year_miss = Counter()
    a_ids = []
    b_ids = []
    gospel_ids = []

    # 先收集 id，再抽样，避免把全部 text 留在内存里。
    def collect_ids(path, bucket, gospel):
        with open(path, encoding="utf-8") as fp:
            for line in fp:
                if not line.strip():
                    continue
                obj = json.loads(line)
                bucket.append(obj["id"])
                source = (obj.get("meta") or {}).get("source_path") or ""
                if GOSPEL_MARK in source:
                    gospel.append(obj["id"])

    collect_ids(a_path, a_ids, gospel_ids)
    collect_ids(b_path, b_ids, [])
    rng = random.Random(config.SAMPLE_SEED)
    pick_a = set(rng.sample(a_ids, min(10, len(a_ids))))
    pick_b = set(rng.sample(b_ids, min(10, len(b_ids))))
    pick_g = set(rng.sample(gospel_ids, min(3, len(gospel_ids)))) if gospel_ids else set()

    def consume(path, batch, out_fp):
        with open(path, encoding="utf-8") as fp:
            for line in fp:
                if not line.strip():
                    continue
                record = json.loads(line)
                files[batch] += 1
                message_key = record.get("id")
                points = record.get("points") or []
                chunks = build_message_chunks(record)
                if not chunks:
                    zero_units.append(message_key)
                    continue
                indexes = [c["chunk_index"] for c in chunks]
                total = chunks[0]["chunk_total"]
                if indexes != list(range(1, total + 1)):
                    index_bad.append(message_key)
                point_sum = sum(c["point_count"] for c in chunks)
                if point_sum != len(points):
                    mismatches.append((message_key, point_sum, len(points)))
                meta = record.get("meta") or {}
                layer = (chunks[0]["book_path"][0] if chunks[0]["book_path"] else "（无）")
                keep = message_key in pick_a or message_key in pick_b or message_key in pick_g
                kept_chunks = []
                if meta.get("source_path") == NOTES_PATH:
                    samples["notes"] = {
                        "message_key": message_key,
                        "min_level": chunks[0]["min_level"],
                        "rows": [
                            {
                                "chunk_index": c["chunk_index"],
                                "point_count": c["point_count"],
                                "tokens": c["tokens"],
                                "label": (c["_unit"][0].get("label") if c["_unit"] else ""),
                            }
                            for c in chunks
                        ],
                    }
                for chunk in chunks:
                    cid = chunk["chunk_id"]
                    prev = seen_ids.get(cid)
                    if prev is not None:
                        collisions.append((cid, prev, message_key))
                    else:
                        seen_ids[cid] = message_key
                    tokens[batch].append(chunk["tokens"])
                    if chunk["tokens"] == 0:
                        zero_token.append((message_key, chunk["chunk_index"], chunk["point_count"]))
                    expect_head = render_header(chunk["book_title"], chunk["message_title"])
                    text_lines = (chunk["text"] or "").split("\n")
                    if (
                        len(text_lines) < 2
                        or text_lines[0] != expect_head
                        or text_lines[1] != ""
                    ):
                        header_bad.append((message_key, chunk["chunk_index"], text_lines[0] if text_lines else ""))
                    if chunk["book_title"]:
                        book_title_counts[batch][chunk["book_title"]] += 1
                    else:
                        miss_box[0] += 1
                    if not chunk["message_title"]:
                        miss_box[1] += 1
                    year_total[layer] += 1
                    if chunk["year"] is not None:
                        year_filled[layer] += 1
                    elif batch == "12490" and layer == "李常受文集纲目":
                        volume = chunk["book_path"][1] if len(chunk["book_path"]) > 1 else "（无册名）"
                        cwwl_year_miss[volume] += 1
                    if chunk["part_no"] is not None:
                        part_box[0] += 1
                        if GOSPEL_MARK not in (chunk["source_path"] or ""):
                            part_outside.append(message_key)
                    if batch == "12490":
                        if chunk["author"] is None:
                            author_box[0] += 1
                        if chunk["conference"] is not None or chunk["month"] is not None:
                            conf_box[0] += 1
                    else:
                        if chunk["author"] is not None:
                            author_box[1] += 1
                        if chunk["conference"]:
                            conf_box[1] += 1
                        if chunk["month"] is not None:
                            conf_box[2] += 1
                    public = {k: v for k, v in chunk.items() if not k.startswith("_")}
                    out_fp.write(json.dumps(public, ensure_ascii=False) + "\n")
                    chunk_n[batch] += 1
                    if keep:
                        kept_chunks.append(
                            {
                                "text": chunk["text"],
                                "chunk_index": chunk["chunk_index"],
                                "point_count": chunk["point_count"],
                                "unit": [
                                    {
                                        "level": p.get("level"),
                                        "label": p.get("label"),
                                        "text": p.get("text"),
                                    }
                                    for p in chunk["_unit"]
                                ],
                            }
                        )
                if message_key in pick_a:
                    samples["a"].append({"message_key": message_key, "chunks": kept_chunks, "points": points})
                if message_key in pick_b:
                    samples["b"].append({"message_key": message_key, "chunks": kept_chunks, "points": points})
                if message_key in pick_g:
                    samples["gospel"].append({"message_key": message_key, "chunks": kept_chunks, "points": points})
                if (
                    samples["note_demo"] is None
                    and GOSPEL_MARK in (meta.get("source_path") or "")
                    and any("\n" in (p.get("text") or "") for p in points)
                ):
                    samples["note_demo"] = {
                        "message_key": message_key,
                        "chunks": [
                            {
                                "text": c["text"],
                                "chunk_index": c["chunk_index"],
                                "point_count": c["point_count"],
                                "unit": [
                                    {
                                        "level": p.get("level"),
                                        "label": p.get("label"),
                                        "text": p.get("text"),
                                    }
                                    for p in c["_unit"]
                                ],
                            }
                            for c in chunks
                        ],
                    }

    a_out = os.path.join(out_dir, "chunks_12490.json")
    b_out = os.path.join(out_dir, "chunks_feasts.json")
    with open(a_out, "w", encoding="utf-8", newline="\n") as a_fp, open(
        b_out, "w", encoding="utf-8", newline="\n"
    ) as b_fp:
        consume(a_path, "12490", a_fp)
        consume(b_path, "feasts", b_fp)

    after = {"a": _file_size(a_path), "b": _file_size(b_path)}
    v01_dir = os.path.join(out_dir, "chunks_v01_20260929")
    v01 = _compare_v01(v01_dir, a_out, b_out)
    report = _render_report(
        files, chunk_n, zero_units, collisions, mismatches, index_bad, tokens,
        zero_token, book_title_counts, year_by_layer, year_filled, year_total,
        part_box[0], part_outside, conf_box, author_box[0], author_box[1],
        miss_box[1], miss_box[0], samples, cwwl_year_miss, before, after,
        _file_size(a_out), _file_size(b_out), header_bad, v01,
    )
    # year_by_layer unused; year_filled/year_total used
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    with open(args.report, "w", encoding="utf-8", newline="\n") as fp:
        fp.write(report)
    print("files", files, "chunks", chunk_n, flush=True)
    print("zero", len(zero_units), "collide", len(collisions), "mismatch", len(mismatches), flush=True)
    print("header_bad", len(header_bad), "id_mismatch", len(v01["id_mismatch"]), flush=True)
    print("notes", None if not samples["notes"] else len(samples["notes"]["rows"]), flush=True)
    if zero_units or collisions:
        print("STOP", flush=True)
        return 2
    if header_bad or not v01["ok"]:
        print("STOP_V02", flush=True)
        return 2
    notes_n = len(samples["notes"]["rows"]) if samples["notes"] else 0
    if not (60 <= notes_n <= 75):
        print("NOTES_BAD", notes_n, flush=True)
        return 2
    print("CHUNKS_OK", flush=True)
    return 0


def _render_report(
    files, chunk_n, zero_units, collisions, mismatches, index_bad, tokens,
    zero_token, book_title_counts, year_by_layer, year_filled, year_total,
    part_filled, part_outside, conf, author_bad_a, author_bad_b,
    title_missing, book_missing, samples, cwwl_year_miss, before, after, size_a, size_b,
    header_bad, v01,
) -> str:
    del year_by_layer
    lines = []
    w = lines.append
    w("# 纲目切块报告（v0.2）")
    w("")
    w("- 方案：`docs/panai4_es/chunks_es_plan.md` v0.2，第二至五节、9.1")
    w("- 种子：{0}".format(config.SAMPLE_SEED))
    w("- 相对 v0.1：`text` 第一行加 `book_title` + 全角空格 + `message_title`，第二行为空行，其后为原纲目正文。")
    w("- 输出是 JSONL：每条一个对象、占一行，没有外层方括号。")
    w("")
    w("## 1. 条数对账")
    w("")
    w("| 批次 | 篇数 | 单位数 | 0 单位的篇 |")
    w("|---|---:|---:|---:|")
    w("| A 批 | {0} | {1} | {2} |".format(files["12490"], chunk_n["12490"], sum(1 for k in zero_units if str(k).startswith("gm12490"))))
    w("| B 批 | {0} | {1} | {2} |".format(files["feasts"], chunk_n["feasts"], sum(1 for k in zero_units if not str(k).startswith("gm12490"))))
    w("")
    w("产出 0 个单位的篇：{0}。".format(len(zero_units)))
    for key in zero_units:
        w("- `{0}`".format(key))
    if zero_units:
        w("")
        w("报告在此停下。")
        return "\n".join(lines) + "\n"
    w("")
    w("## 2. 唯一性")
    w("")
    w("chunk_id 碰撞：{0}。".format(len(collisions)))
    for cid, left, right in collisions:
        w("- `{0}` 与 `{1}`".format(left, right))
    if collisions:
        w("")
        w("报告在此停下。")
        return "\n".join(lines) + "\n"
    w("")
    w("## 3. 完整性")
    w("")
    w("sum(point_count) 与 len(points) 不一致：{0}。".format(len(mismatches)))
    for key, got, expect in mismatches:
        w("- `{0}` sum={1} len={2}".format(key, got, expect))
    w("")
    w("## 4. chunk_index / chunk_total")
    w("")
    w("断号或未从 1 连续到 chunk_total 的篇：{0}。".format(len(index_bad)))
    for key in index_bad:
        w("- `{0}`".format(key))
    w("")
    w("## 5. token 分布")
    w("")
    w("token = `int(len(text) / 1.5)`，text 是 v0.2 渲染后的正文（含头部行）。")
    w("")
    w("| 批次 | 单位数 | min | max | avg | median | <150 | 150~800 | >800 |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    w(_token_row("A 批 v0.2", tokens["12490"]))
    w(_token_row("B 批 v0.2", tokens["feasts"]))
    if v01 and not v01.get("missing_v01"):
        w(_token_row("A 批 v0.1", v01["tokens_v01"]["12490"]))
        w(_token_row("B 批 v0.1", v01["tokens_v01"]["feasts"]))
    w("")
    w("因加了头部行，v0.2 的 tokens 会略高于 v0.1。逐项并列见附录 A。")
    w("")
    w("## 6. tokens == 0")
    w("")
    w("共 {0} 个。本步照常写出，建索引时再滤。".format(len(zero_token)))
    w("")
    if zero_token:
        w("| message_key | chunk_index | point_count |")
        w("|---|---:|---:|")
        for key, index, count in zero_token:
            w("| `{0}` | {1} | {2} |".format(key, index, count))
        w("")
    w("## 7. 字段覆盖率")
    w("")
    total_chunks = chunk_n["12490"] + chunk_n["feasts"]
    w("- book_title 为空：{0}。message_title 为空：{1}。".format(book_missing, title_missing))
    w("- A 批 author 为空：{0}。B 批 author 非空：{1}。".format(author_bad_a, author_bad_b))
    year_all = sum(year_filled.values())
    year_den = sum(year_total.values())
    w("- year 非空：{0} / {1}（{2}）。".format(year_all, year_den, _pct(year_all, year_den)))
    w("")
    w("| book_path 第一层 | 条数 | year 非空 | 比例 |")
    w("|---|---:|---:|---:|")
    for name in sorted(year_total):
        w("| {0} | {1} | {2} | {3} |".format(name, year_total[name], year_filled.get(name, 0), _pct(year_filled.get(name, 0), year_total[name])))
    w("")
    if cwwl_year_miss:
        detail = "、".join("{0}（{1}）".format(name, cwwl_year_miss[name]) for name in sorted(cwwl_year_miss))
        w("- A 批「李常受文集纲目」里 year 为空的 {0} 条，都在册名不含四字中文年份的册：{1}。".format(
            sum(cwwl_year_miss.values()), detail))
        w("")
    outside_keys = sorted(set(part_outside))
    w("- part_no 非空的 chunk：{0}。其中不在福音题纲路径下的篇：{1}。这些篇的 part_no 来自上游 JSON 的 meta.part_no，切块原样抄出。".format(
        part_filled, len(outside_keys)))
    for key in outside_keys:
        w("  - `{0}`".format(key))
    w("- A 批 conference 或 month 非空的 chunk：{0}。".format(conf[0]))
    w("- B 批 conference 非空：{0}。month 非空：{1}。".format(conf[1], conf[2]))
    w("")
    w("## 8. book_title 取值")
    w("")
    w("### A 批前 50")
    w("")
    w("| book_title | chunk 数 |")
    w("|---|---:|")
    for name, count in book_title_counts["12490"].most_common(50):
        w("| {0} | {1} |".format(name.replace("|", "\\|"), count))
    w("")
    w("### 新约总论、真理课程、生命课程")
    w("")
    w("这三类按原书册名改写，其余书系的规则不变。")
    w("")
    w("| book_title | chunk 数 |")
    w("|---|---:|")
    for title in config.BOOK_TITLE_OVERRIDES.values():
        w("| {0} | {1} |".format(title.replace("|", "\\|"), book_title_counts["12490"].get(title, 0)))
    w("")
    w("### B 批全部")
    w("")
    w("| book_title | chunk 数 |")
    w("|---|---:|")
    bad_b = []
    for name, count in sorted(book_title_counts["feasts"].items()):
        w("| {0} | {1} |".format(name.replace("|", "\\|"), count))
        if "-" in name or not re.match(r"^\d{4}年", name):
            bad_b.append(name)
    w("")
    w("B 批不像「YYYY年特会名」的取值：{0}。".format(len(bad_b)))
    for name in bad_b:
        w("- {0}".format(name))
    w("")
    w("## 9. 抽样比对")
    w("")
    w("种子 {0}。text 全文不截断。对照列是该单位里的 points（level / label / text）。".format(config.SAMPLE_SEED))
    w("")

    def dump(title, rows):
        w("### {0}".format(title))
        w("")
        for row in rows:
            w("#### `{0}`".format(row["message_key"]))
            w("")
            for chunk in row["chunks"]:
                w("##### chunk_index {0}（{1} 个 point）".format(chunk["chunk_index"], chunk["point_count"]))
                w("")
                w("```")
                w(chunk["text"])
                w("```")
                w("")
                w("| level | label | text |")
                w("|---:|---|---|")
                for point in chunk["unit"]:
                    w("| {0} | {1} | {2} |".format(
                        point["level"],
                        (point["label"] or "").replace("|", "\\|").replace("\n", "⏎"),
                        (point["text"] or "").replace("|", "\\|").replace("\n", "⏎"),
                    ))
                w("")

    dump("A 批 10 篇", samples["a"])
    dump("B 批 10 篇", samples["b"])
    gospel_rows = samples["gospel"]
    gospel_has_note = any(
        "\n" in (point.get("text") or "")
        for row in gospel_rows
        for chunk in row["chunks"]
        for point in chunk["unit"]
    )
    dump("福音题纲 3 篇", gospel_rows)
    if gospel_rows and not gospel_has_note:
        w("种子抽出的这 3 篇，points.text 都不含换行，正文里没有并入的说明。说明文字的渲染见下一节。")
        w("")
    demo = samples.get("note_demo")
    if demo and not gospel_has_note:
        w("### 说明文字并入（补充核对）")
        w("")
        w("种子抽出的 3 篇没有说明文字。下面这篇是福音题纲里第一篇含说明的，用来核对：说明行跟在所属点后面，缩进与该点相同，不重复 label。")
        w("")
        dump(demo["message_key"], [demo])
    w("### 李常受弟兄个人笔记")
    w("")
    notes = samples["notes"]
    if not notes:
        w("未找到该篇。")
    else:
        n = len(notes["rows"])
        w("- message_key：`{0}`".format(notes["message_key"]))
        w("- min_level：{0}".format(notes["min_level"]))
        w("- 单位数：{0}。".format(n))
        if n >= 200:
            w("- 单位数接近 283，分组基准不对。报告在此停下。")
            return "\n".join(lines) + "\n"
        w("")
        w("| chunk_index | point_count | tokens | 第一个 point 的 label |")
        w("|---:|---:|---:|---|")
        for row in notes["rows"]:
            w("| {0} | {1} | {2} | {3} |".format(
                row["chunk_index"], row["point_count"], row["tokens"],
                (row["label"] or "").replace("|", "\\|"),
            ))
    w("")
    w("## 10. 文件大小与输入对照")
    w("")
    w("| 文件 | 字节 |")
    w("|---|---:|")
    w("| chunks_12490.json | {0} |".format(size_a))
    w("| chunks_feasts.json | {0} |".format(size_b))
    w("")
    w("| 输入 | 切块前 | 切块后 |")
    w("|---|---:|---:|")
    w("| outline_12490.json | {0} | {1} |".format(before["a"], after["a"]))
    w("| outline_feasts.json | {0} | {1} |".format(before["b"], after["b"]))
    w("")
    same = before == after
    w("两个输入 JSON 的字节数在切块前后一致。" if same else "两个输入 JSON 的字节数在切块前后不一致。")
    w("")
    w("## A. 与 v0.1 的对照")
    w("")
    if not v01 or v01.get("missing_v01"):
        w("找不到 `chunks_v01_20260929` 备份，无法对照。")
        w("")
    else:
        w("| 批次 | v0.1 条数 | v0.2 条数 |")
        w("|---|---:|---:|")
        w("| A | {0} | {1} |".format(v01["count_v01"]["12490"], v01["count_v02"]["12490"]))
        w("| B | {0} | {1} |".format(v01["count_v01"]["feasts"], v01["count_v02"]["feasts"]))
        w("")
        w("chunk_id 与 v0.1 不一致：{0}。".format(len(v01["id_mismatch"])))
        for key, old_id, new_id in v01["id_mismatch"]:
            w("- `{0}`：v0.1=`{1}` / v0.2=`{2}`".format(key, old_id, new_id))
        if v01["id_mismatch"]:
            w("")
            w("chunk_id 必须与 v0.1 完全一致。报告在此停下。")
            return "\n".join(lines) + "\n"
        w("")
        w("token 分布并列（与第 5 节同一套数字）：")
        w("")
        w("| 版本 | 批次 | 单位数 | min | max | avg | median | <150 | 150~800 | >800 |")
        w("|---|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for label, key in (("v0.2", None), ("v0.1", "tokens_v01")):
            for batch, name in (("12490", "A"), ("feasts", "B")):
                series = tokens[batch] if key is None else v01[key][batch]
                row = _token_stats(series)
                w("| {0} | {1} | {2} | {3} | {4} | {5:.1f} | {6} | {7}（{8}） | {9}（{10}） | {11}（{12}） |".format(
                    label, name, row["n"], row["min"], row["max"], row["avg"], row["median"],
                    row["lt"], _pct(row["lt"], row["n"]),
                    row["mid"], _pct(row["mid"], row["n"]),
                    row["gt"], _pct(row["gt"], row["n"]),
                ))
        w("")
    w("## B. 头部行全量校验")
    w("")
    w("期望：第一行 = `book_title` + 全角空格 + `message_title`；第二行为空行。")
    w("")
    w("不符：{0}。".format(len(header_bad)))
    for key, index, first in header_bad[:50]:
        w("- `{0}` chunk_index={1}；第一行=`{2}`".format(key, index, (first or "").replace("|", "\\|")[:120]))
    if header_bad:
        w("")
        w("报告在此停下。")
        return "\n".join(lines) + "\n"
    w("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
