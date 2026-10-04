# -*- coding: utf-8 -*-
"""恢复本圣经：区间形成 + 三级细分 + 渲染 → chunks_bible.json。

绝不生成向量、不建索引。绝不解析 outline_content 里的经文范围文字。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import statistics
import sys
import time
from collections import Counter, defaultdict

from . import config
from . import read_sqlite


def verse_chars(verses: list) -> int:
    return sum(len(v.get("content") or "") for v in verses)


def fmt_ref(chapter: int, verse: int, unit: int) -> str:
    return "{0}{1}{2}".format(
        config.to_cn_number(chapter),
        verse,
        config.UNIT_SUFFIX.get(unit, ""),
    )


def fmt_range(verses: list) -> str:
    if not verses:
        return ""
    a, b = verses[0], verses[-1]
    left = fmt_ref(a["chapter"], a["verse"], a["unit"])
    if a is b or (a["chapter"] == b["chapter"] and a["verse"] == b["verse"] and a["unit"] == b["unit"]):
        return left
    if a["chapter"] == b["chapter"]:
        right = "{0}{1}".format(b["verse"], config.UNIT_SUFFIX.get(b["unit"], ""))
        return "{0}～{1}".format(left, right)
    return "{0}～{1}".format(left, fmt_ref(b["chapter"], b["verse"], b["unit"]))


def chunk_id_of(message_key: str, chunk_index: int) -> str:
    digest = hashlib.sha1("{0}#{1}".format(message_key, chunk_index).encode("utf-8")).hexdigest()[:12]
    return "{0}_{1}".format(config.CHUNK_ID_PREFIX, digest)


def build_ancestor_paths(outlines: list) -> dict:
    """volume_order 顺序建栈，返回 outline.id → [从 level1 到本节点]。"""
    stack = []
    paths = {}
    for node in outlines:
        while stack and stack[-1]["level"] >= node["level"]:
            stack.pop()
        paths[node["id"]] = list(stack) + [node]
        stack.append(node)
    return paths


def pick_starts(outlines: list) -> list:
    """相同 start_key 合成一个起点，归属最深（level 最大；同级 volume_order 最大）。"""
    by_key = {}
    for node in outlines:
        key = node["start_key"]
        prev = by_key.get(key)
        if prev is None:
            by_key[key] = node
            continue
        if node["level"] > prev["level"] or (
            node["level"] == prev["level"] and node["volume_order"] > prev["volume_order"]
        ):
            by_key[key] = node
    return sorted(by_key.items(), key=lambda item: item[0])


def form_intervals(verses: list, starts: list, paths: dict) -> list:
    """相邻起点之间的区间；首起点之前的经文并入第一区间。"""
    if not verses:
        return []
    if not starts:
        return [{
            "verses": list(verses),
            "owner": None,
            "path": [],
            "start_key": verses[0]["key"],
        }]
    intervals = []
    for index, (start_key, owner) in enumerate(starts):
        end_key = starts[index + 1][0] if index + 1 < len(starts) else None
        if index == 0:
            piece = [v for v in verses if end_key is None or v["key"] < end_key]
        else:
            piece = [
                v for v in verses
                if v["key"] >= start_key and (end_key is None or v["key"] < end_key)
            ]
        intervals.append({
            "verses": piece,
            "owner": owner,
            "path": paths.get(owner["id"], [owner]) if owner else [],
            "start_key": start_key,
        })
    return intervals


def split_by_chapter(verses: list) -> list:
    groups = []
    current = []
    current_ch = None
    for verse in verses:
        if current_ch is None:
            current_ch = verse["chapter"]
        if verse["chapter"] != current_ch:
            groups.append(current)
            current = [verse]
            current_ch = verse["chapter"]
        else:
            current.append(verse)
    if current:
        groups.append(current)
    return groups


def split_by_paragraph(verses: list, para_keys: set) -> list:
    if not verses:
        return []
    groups = []
    current = []
    for verse in verses:
        if current and verse["key"] in para_keys and verse["key"] != current[0]["key"]:
            groups.append(current)
            current = [verse]
        else:
            current.append(verse)
    if current:
        groups.append(current)
    return groups


def refine_interval(interval: dict, para_keys: set, counters: dict, interval_id: int) -> list:
    """②③④。字数只计经文正文。绝不做碎片合并。"""
    verses = interval["verses"]
    if not verses:
        return []
    chars = verse_chars(verses)
    multi_chapter = len({v["chapter"] for v in verses}) > 1
    base = {
        "path": interval["path"],
        "owner": interval["owner"],
        "need_synthetic": multi_chapter,
        "interval_id": interval_id,
    }
    if chars <= config.CHAR_LIMIT:
        return [{**base, "verses": verses, "split_rule": "none"}]

    counters["rule2"] += 1
    pieces = []
    for chapter_verses in split_by_chapter(verses):
        ch_chars = verse_chars(chapter_verses)
        if ch_chars <= config.CHAR_LIMIT:
            pieces.append({**base, "verses": chapter_verses, "split_rule": "by_chapter"})
            continue
        counters["rule3"] += 1
        para_pieces = split_by_paragraph(chapter_verses, para_keys)
        if len(para_pieces) <= 1:
            pieces.append({**base, "verses": chapter_verses, "split_rule": "keep_oversize"})
            if ch_chars > config.CHAR_LIMIT:
                counters["rule4"] += 1
            continue
        for para_verses in para_pieces:
            p_chars = verse_chars(para_verses)
            rule = "by_paragraph"
            if p_chars > config.CHAR_LIMIT:
                rule = "keep_oversize"
                counters["rule4"] += 1
            pieces.append({**base, "verses": para_verses, "split_rule": rule})
    return pieces


def synthetic_line(book_title: str, chapter: int) -> str:
    if book_title == "诗篇":
        return "第{0}篇".format(config.to_cn_number(chapter))
    return "第{0}章".format(config.to_cn_number(chapter))


def render_outline_lines(path: list, synthetic: str | None = None) -> list:
    lines = []
    for node in path:
        indent = config.IDEOGRAPHIC_SPACE * max(node["level"] - 1, 0)
        lines.append(indent + node["outline_content"])
    if synthetic and path:
        deepest = path[-1]["level"]
        lines.append(config.IDEOGRAPHIC_SPACE * deepest + synthetic)
    elif synthetic:
        lines.append(synthetic)
    return lines


def render_verse_block(book_title: str, piece: dict) -> tuple:
    verses = piece["verses"]
    verse_range = fmt_range(verses)
    header = book_title + config.IDEOGRAPHIC_SPACE + verse_range
    path = piece["path"]
    syn = None
    if piece.get("need_synthetic") and verses:
        syn = synthetic_line(book_title, verses[0]["chapter"])
    outline_lines = render_outline_lines(path, syn)
    body_lines = []
    for verse in verses:
        ref = fmt_ref(verse["chapter"], verse["verse"], verse["unit"])
        body_lines.append(ref + config.IDEOGRAPHIC_SPACE + (verse["content"] or ""))
    parts = [header]
    parts.extend(outline_lines)
    parts.append("")
    parts.extend(body_lines)
    text = "\n".join(parts)
    outline_path = [n["outline_content"] for n in path]
    if syn:
        outline_path = outline_path + [syn]
    if syn:
        message_title = syn
    elif path:
        message_title = path[-1]["outline_content"]
    else:
        message_title = book_title
    outline_level = path[-1]["level"] if path else None
    return text, verse_range, outline_path, message_title, outline_level


def render_book_outline(book_title: str, topic: str, outlines: list) -> str:
    lines = [book_title, "主题：{0}".format(topic or ""), "", "纲目："]
    for node in outlines:
        indent = config.IDEOGRAPHIC_SPACE * max(node["level"] - 1, 0)
        lines.append(indent + node["outline_content"])
    return "\n".join(lines)


def build_book(book: dict, topic: str, outlines: list, verses: list, para_keys: set, counters: dict) -> list:
    book_no = book["book_no"]
    book_title = book["book_title"]
    message_key = "bible/{0}-{1}".format(book_no, book_title)
    paths = build_ancestor_paths(outlines)
    starts = pick_starts(outlines)
    intervals = form_intervals(verses, starts, paths)
    counters["intervals"] += len(intervals)

    verse_pieces = []
    for idx, interval in enumerate(intervals):
        if not interval["verses"]:
            continue
        verse_pieces.extend(refine_interval(interval, para_keys, counters, idx))

    chunks = []
    # 卷首块
    book_text = render_book_outline(book_title, topic, outlines)
    chunks.append({
        "chunk_id": chunk_id_of(message_key, 0),
        "message_key": message_key,
        "batch": config.BATCH,
        "chunk_type": "book_outline",
        "text": book_text,
        "book_title": book_title,
        "book_no": book_no,
        "message_title": book_title,
        "message_number": None,
        "author": config.AUTHOR,
        "verse_range": None,
        "outline_path": [n["outline_content"] for n in outlines],
        "outline_level": None,
        "paragraph_type": config.PARAGRAPH_TYPE,
        "tokens": int(len(book_text) / 1.5),
        "chunk_index": 0,
        "chunk_total": len(verse_pieces),
        "split_rule": "none",
        "source_keys": [],
    })

    for index, piece in enumerate(verse_pieces, 1):
        text, verse_range, outline_path, message_title, outline_level = render_verse_block(book_title, piece)
        chunks.append({
            "chunk_id": chunk_id_of(message_key, index),
            "message_key": message_key,
            "batch": config.BATCH,
            "chunk_type": "verses",
            "text": text,
            "book_title": book_title,
            "book_no": book_no,
            "message_title": message_title,
            "message_number": piece["verses"][0]["chapter"] if piece["verses"] else None,
            "author": config.AUTHOR,
            "verse_range": verse_range,
            "outline_path": outline_path,
            "outline_level": outline_level,
            "paragraph_type": config.PARAGRAPH_TYPE,
            "tokens": int(len(text) / 1.5),
            "chunk_index": index,
            "chunk_total": len(verse_pieces),
            "split_rule": piece["split_rule"],
            "source_keys": [v["key"] for v in piece["verses"]],
            "_verses": piece["verses"],
            "_chars": verse_chars(piece["verses"]),
            "_interval_id": piece.get("interval_id"),
        })
    return chunks


def _pct(n, total):
    if not total:
        return "0.0%"
    return "{0:.1f}%".format(n / total * 100)


def write_report(path: str, data: dict) -> None:
    lines = []
    w = lines.append
    w("# 恢复本圣经建块报告")
    w("")
    w("- 方案：`docs/panai4_es/bible_index_plan.md`")
    w("- 模拟对照：`docs/panai4_es/bible_chunk_sim_v2.md`")
    w("- 种子：{0}".format(config.SAMPLE_SEED))
    w("- 输出 JSONL，不含 embedding。")
    w("")
    w("## 1. 覆盖（硬指标）")
    w("")
    w("- 经文总节数：{0}".format(data["verse_total"]))
    w("- 已分配：{0}".format(data["assigned"]))
    w("- 未分配：{0}".format(len(data["unassigned"])))
    w("- 重复分配：{0}".format(len(data["duplicated"])))
    for book_no, key in data["unassigned"][:50]:
        w("- 未分配 book={0} key=`{1}`".format(book_no, key))
    for (book_no, key), n in data["duplicated"][:50]:
        w("- 重复 book={0} key=`{1}` × {2}".format(book_no, key, n))
    if data["unassigned"] or data["duplicated"]:
        w("")
        w("覆盖失败，报告在此停下。")
        open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
        return
    w("")
    w("## 2. 块数")
    w("")
    w("| 项 | 本步 | sim_v2 |")
    w("|---|---:|---:|")
    w("| 区间数 | {0} | 2507 |".format(data["counters"]["intervals"]))
    w("| 经文块 | {0} | 3625 |".format(data["verse_chunks"]))
    w("| 卷首块 | {0} | 66 |".format(data["outline_chunks"]))
    w("| 合计 | {0} | 3691 |".format(data["total_chunks"]))
    w("| ② 区间数 | {0} | 163 |".format(data["counters"]["rule2"]))
    w("| ③ 片数 | {0} | 124 |".format(data["counters"]["rule3"]))
    w("| ④ 片数 | {0} | 3 |".format(data["counters"]["rule4"]))
    w("")
    diffs = []
    expect = {
        "intervals": 2507, "verse_chunks": 3625, "outline_chunks": 66,
        "total_chunks": 3691, "rule2": 163, "rule3": 124, "rule4": 3,
    }
    actual = {
        "intervals": data["counters"]["intervals"],
        "verse_chunks": data["verse_chunks"],
        "outline_chunks": data["outline_chunks"],
        "total_chunks": data["total_chunks"],
        "rule2": data["counters"]["rule2"],
        "rule3": data["counters"]["rule3"],
        "rule4": data["counters"]["rule4"],
    }
    for key, exp in expect.items():
        if actual[key] != exp:
            diffs.append("{0}: 本步 {1} / sim {2}".format(key, actual[key], exp))
    if diffs:
        w("与 sim_v2 偏差：")
        for item in diffs:
            w("- {0}".format(item))
    else:
        w("与 sim_v2 块数与各步次数完全一致。")
    # 自洽验算（与 sim_v2 同口径：最终片数>1 的区间视为被切分）
    s = data.get("split_intervals", 0)
    p = data.get("split_pieces", 0)
    formula = data["counters"]["intervals"] - s + p + 66
    w("")
    w("自洽验算：被切分区间 S={0}，其最终片数之和 P={1}；".format(s, p))
    w("`区间数 − S + P + 66 = {0} − {1} + {2} + 66 = {3}`（合计 {4}）。".format(
        data["counters"]["intervals"], s, p, formula, data["total_chunks"]))
    w("")
    w("## 3. 各步生效次数")
    w("")
    w("见上表。本步切分字数只计经文正文（与模拟相同），不含 text 头部与纲目路径。")
    w("")
    w("## 4. 唯一性")
    w("")
    w("chunk_id 碰撞：{0}。".format(len(data["collisions"])))
    for left, right in data["collisions"][:20]:
        w("- `{0}` / `{1}`".format(left, right))
    w("")
    w("## 5. 诗篇 119")
    w("")
    ps = data["psalm119"]
    w("- 块数：{0}（须 22）".format(ps["n"]))
    w("- 每块节数：{0}".format(ps["sizes"]))
    if ps["n"] != 22 or any(s != 8 for s in ps["sizes"]):
        w("- **未通过**，报告在此停下。")
        open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")
        return
    w("- 通过：22 块，每块恰好 8 节。")
    w("")
    w("## 6. 字数 / token 分布")
    w("")
    w("本步 tokens = `int(len(text)/1.5)`，text 含头部与纲目路径，故高于模拟（模拟只计经文正文）。")
    w("")
    w("| | 本步（含头部） | sim_v2（仅经文） |")
    w("|---|---:|---:|")
    dist = data["token_dist"]
    w("| 经文块数 | {0} | 3625 |".format(dist["n"]))
    w("| 字数 min | {0} | 5 |".format(dist["cmin"]))
    w("| 字数 max | {0} | 1791 |".format(dist["cmax"]))
    w("| 字数 avg | {0:.2f} | 299.31 |".format(dist["cavg"]))
    w("| 字数 median | {0} | 219.0 |".format(dist["cmed"]))
    w("| token min | {0} | — |".format(dist["tmin"]))
    w("| token max | {0} | — |".format(dist["tmax"]))
    w("| token avg | {0:.1f} | — |".format(dist["tavg"]))
    w("| token median | {0} | — |".format(dist["tmed"]))
    w("| <150 token | {0}（{1}） | 1859（51.3%） |".format(dist["lt"], _pct(dist["lt"], dist["n"])))
    w("| 150～800 | {0}（{1}） | 1763（48.6%） |".format(dist["mid"], _pct(dist["mid"], dist["n"])))
    w("| >800 | {0}（{1}） | 3（0.08%） |".format(dist["gt"], _pct(dist["gt"], dist["n"])))
    w("")
    w("纯经文字数（与模拟同口径）并列：min={0} max={1} avg={2:.2f} median={3}。".format(
        dist["vcmin"], dist["vcmax"], dist["vcavg"], dist["vcmed"]))
    w("")
    w("中文章数转换（`config.to_cn_number`）：1→一、10→十、11→十一、20→二十、99→九十九、")
    w("100→一百、101→一百零一、107→一百零七、110→一百一十、119→一百一十九、150→一百五十。")
    w("百后的 10～19 须带「一十」（一百一十九，不是一百十九）。")
    w("")
    w("## 7. 字段覆盖率")
    w("")
    w("- book_title 空：{0}；message_title 空：{1}；text 空：{2}".format(
        data["missing_title"], data["missing_msg"], data["missing_text"]))
    w("- chunk_type 取值：{0}".format(dict(data["type_counts"])))
    w("- book_outline 条数：{0}（须 66）".format(data["type_counts"].get("book_outline", 0)))
    w("- verses 的 verse_range 空：{0}；book_outline 的 verse_range 非空：{1}".format(
        data["verse_range_missing"], data["outline_range_set"]))
    w("")
    w("## 8. chunk_index")
    w("")
    w("断号或卷首非 0 的卷：{0}。".format(len(data["index_bad"])))
    for key in data["index_bad"][:20]:
        w("- `{0}`".format(key))
    w("")
    w("## 9. 抽样打印")
    w("")
    w("种子 {0}。".format(config.SAMPLE_SEED))
    w("")
    samples = data["samples"]
    w("### 9.1 以弗所书卷首块")
    w("")
    w("```")
    w(samples["eph_outline"])
    w("```")
    w("")
    w("### 9.2 以弗所书前 3 个经文块")
    w("")
    for index, text in enumerate(samples["eph_verses"], 1):
        w("#### 第 {0} 块".format(index))
        w("")
        w("```")
        w(text)
        w("```")
        w("")
    w("### 9.3 诗篇 119 全部 22 块")
    w("")
    for index, text in enumerate(samples["ps119"], 1):
        w("#### 第 {0} 块".format(index))
        w("")
        w("```")
        if index == 1:
            w(text)
        else:
            w(text[:60] + ("…" if len(text) > 60 else ""))
        w("```")
        w("")
    w("### 9.4 走了②的例子")
    w("")
    for text in samples["rule2"]:
        w("```")
        w(text)
        w("```")
        w("")
    w("### 9.5 走了③的例子")
    w("")
    for text in samples["rule3"]:
        w("```")
        w(text)
        w("```")
        w("")
    w("### 9.6 走了④的例子")
    w("")
    for text in samples["rule4"]:
        w("```")
        w(text)
        w("```")
        w("")
    w("### 9.7 上/下分节")
    w("")
    for text in samples["halves"]:
        w("```")
        w(text)
        w("```")
        w("")
    w("### 9.8 诗篇合成层")
    w("")
    for text in samples["ps_syn"]:
        w("```")
        w(text)
        w("```")
        w("")
    w("### 9.9 非诗篇合成层")
    w("")
    for text in samples["other_syn"]:
        w("```")
        w(text)
        w("```")
        w("")
    w("## 10. 源文件未改动")
    w("")
    w("| | 建块前 | 建块后 |")
    w("|---|---:|---:|")
    w("| 字节 | {0} | {1} |".format(data["before"]["size"], data["after"]["size"]))
    w("| mtime | {0} | {1} |".format(data["before"]["mtime"], data["after"]["mtime"]))
    w("")
    same = data["before"] == data["after"]
    w("sqlite 字节数与 mtime 在建块前后完全一致。" if same else "sqlite 元数据发生变化。")
    w("")
    w("## 11. 头部行校验")
    w("")
    w("不符：{0}。".format(len(data["header_bad"])))
    for item in data["header_bad"][:20]:
        w("- `{0}` chunk_index={1}".format(item[0], item[1]))
    w("")
    w("## 12. 产出")
    w("")
    w("- chunks_bible.json 条数：{0}".format(data["total_chunks"]))
    w("- 字节：{0}".format(data["out_size"]))
    w("")
    open(path, "w", encoding="utf-8", newline="\n").write("\n".join(lines) + "\n")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="恢复本圣经建块")
    parser.add_argument("--out", default=config.DEFAULT_OUT_DIR)
    parser.add_argument("--db", default=config.SQLITE_PATH)
    parser.add_argument("--report", default=config.default_report_path())
    args = parser.parse_args(argv)

    before = read_sqlite.file_stat(args.db)
    con = read_sqlite.connect(args.db)
    volumes = read_sqlite.load_volumes(con)
    topics = read_sqlite.load_topics(con)

    counters = Counter()
    all_chunks = []
    key_hits = Counter()
    all_verse_keys = []
    collisions = {}
    collide_list = []
    index_bad = []
    header_bad = []
    type_counts = Counter()
    missing_title = missing_msg = missing_text = 0
    verse_range_missing = outline_range_set = 0
    verse_char_lens = []
    text_char_lens = []
    token_lens = []
    psalm119 = []
    by_book = {}

    for book in volumes:
        book_no = book["book_no"]
        outlines = read_sqlite.load_outlines(con, book_no)
        verses = read_sqlite.load_verses(con, book_no)
        para_keys = set(read_sqlite.load_paragraph_keys(con, book_no))
        for verse in verses:
            # 覆盖按 (book_no, key) 计：坐标键不含卷号，跨卷会撞。
            all_verse_keys.append((book_no, verse["key"]))
        chunks = build_book(book, topics.get(book_no, ""), outlines, verses, para_keys, counters)
        by_book[book_no] = chunks

        # chunk_index 校验
        verse_chunks = [c for c in chunks if c["chunk_type"] == "verses"]
        outline_chunks = [c for c in chunks if c["chunk_type"] == "book_outline"]
        if len(outline_chunks) != 1 or outline_chunks[0]["chunk_index"] != 0:
            index_bad.append(chunks[0]["message_key"])
        idxs = [c["chunk_index"] for c in verse_chunks]
        total = verse_chunks[0]["chunk_total"] if verse_chunks else 0
        if idxs != list(range(1, total + 1)):
            index_bad.append(chunks[0]["message_key"])

        for chunk in chunks:
            cid = chunk["chunk_id"]
            if cid in collisions:
                collide_list.append((collisions[cid], chunk["message_key"]))
            else:
                collisions[cid] = chunk["message_key"]
            type_counts[chunk["chunk_type"]] += 1
            if not chunk.get("book_title"):
                missing_title += 1
            if not chunk.get("message_title"):
                missing_msg += 1
            if not chunk.get("text"):
                missing_text += 1
            first = (chunk["text"] or "").split("\n", 1)[0]
            if chunk["chunk_type"] == "book_outline":
                if first != chunk["book_title"]:
                    header_bad.append((chunk["message_key"], chunk["chunk_index"]))
                if chunk.get("verse_range") is not None:
                    outline_range_set += 1
            else:
                expect = chunk["book_title"] + config.IDEOGRAPHIC_SPACE + (chunk.get("verse_range") or "")
                if first != expect:
                    header_bad.append((chunk["message_key"], chunk["chunk_index"]))
                if not chunk.get("verse_range"):
                    verse_range_missing += 1
                for key in chunk.get("source_keys") or []:
                    key_hits[(book_no, key)] += 1
                verse_char_lens.append(chunk.get("_chars") or verse_chars(chunk.get("_verses") or []))
                text_char_lens.append(len(chunk["text"] or ""))
                token_lens.append(chunk["tokens"])
                if book_no == 19 and chunk.get("message_number") == 119:
                    psalm119.append(chunk)
            public = {k: v for k, v in chunk.items() if not k.startswith("_")}
            all_chunks.append(public)

    con.close()
    after = read_sqlite.file_stat(args.db)

    verse_key_set = set(all_verse_keys)
    assigned = set(key_hits)
    unassigned = sorted(verse_key_set - assigned)
    duplicated = sorted((k, n) for k, n in key_hits.items() if n > 1)

    # 自洽：最终片数 > 1 的区间
    per_interval = Counter()
    for book_no, chunks in by_book.items():
        for chunk in chunks:
            if chunk["chunk_type"] != "verses":
                continue
            iid = "{0}:{1}".format(book_no, chunk.get("_interval_id"))
            per_interval[iid] += 1
    split_intervals = sum(1 for n in per_interval.values() if n > 1)
    split_pieces = sum(n for n in per_interval.values() if n > 1)

    # token dist
    def stats(vals):
        if not vals:
            return 0, 0, 0, 0.0, 0
        ordered = sorted(vals)
        return ordered[0], ordered[-1], statistics.median(ordered), sum(ordered) / len(ordered), len(ordered)

    tmin, tmax, tmed, tavg, tn = stats(token_lens)
    cmin, cmax, cmed, cavg, cn = stats(text_char_lens)
    vcmin, vcmax, vcmed, vcavg, _ = stats(verse_char_lens)
    token_dist = {
        "n": tn,
        "tmin": tmin, "tmax": tmax, "tmed": tmed, "tavg": tavg,
        "cmin": cmin, "cmax": cmax, "cmed": cmed, "cavg": cavg,
        "vcmin": vcmin, "vcmax": vcmax, "vcmed": vcmed, "vcavg": vcavg,
        "lt": sum(1 for t in token_lens if t < 150),
        "mid": sum(1 for t in token_lens if 150 <= t <= 800),
        "gt": sum(1 for t in token_lens if t > 800),
    }

    ps_sizes = [len(c.get("source_keys") or []) for c in sorted(psalm119, key=lambda c: c["chunk_index"])]

    # samples
    eph = by_book.get(49) or []
    eph_outline = next(c["text"] for c in eph if c["chunk_type"] == "book_outline")
    eph_verses = [c["text"] for c in eph if c["chunk_type"] == "verses"][:3]
    ps119_texts = [c["text"] for c in sorted(psalm119, key=lambda c: c["chunk_index"])]

    def find_rule(rule, limit=2):
        found = []
        for book_no, chunks in by_book.items():
            verses = [c for c in chunks if c["chunk_type"] == "verses" and c["split_rule"] == rule]
            if len(verses) >= 2 and rule in ("by_chapter", "by_paragraph"):
                # take first two consecutive from same book
                found = [verses[0]["text"], verses[1]["text"]]
                break
            if rule == "keep_oversize" and verses:
                found = [verses[0]["text"]]
                if len(verses) > 1:
                    found.append(verses[1]["text"])
                break
        return found[:limit]

    halves = []
    for chunks in by_book.values():
        for chunk in chunks:
            if chunk["chunk_type"] != "verses":
                continue
            if "上" in (chunk.get("verse_range") or "") or "下" in (chunk.get("verse_range") or ""):
                halves.append(chunk["text"])
            if len(halves) >= 2:
                break
        if len(halves) >= 2:
            break

    ps_syn = []
    other_syn = []
    for book_no, chunks in by_book.items():
        title = chunks[0]["book_title"]
        for chunk in chunks:
            if chunk["chunk_type"] != "verses":
                continue
            path = chunk.get("outline_path") or []
            if not path:
                continue
            last = path[-1]
            if title == "诗篇" and last.startswith("第") and last.endswith("篇"):
                if len(ps_syn) < 2:
                    ps_syn.append(chunk["text"])
            elif title != "诗篇" and last.startswith("第") and last.endswith("章"):
                if len(other_syn) < 1:
                    other_syn.append(chunk["text"])
        if len(ps_syn) >= 2 and other_syn:
            break

    samples = {
        "eph_outline": eph_outline,
        "eph_verses": eph_verses,
        "ps119": ps119_texts,
        "rule2": find_rule("by_chapter"),
        "rule3": find_rule("by_paragraph"),
        "rule4": find_rule("keep_oversize"),
        "halves": halves[:2],
        "ps_syn": ps_syn[:2],
        "other_syn": other_syn[:1],
    }

    out_path = os.path.join(args.out, "chunks_bible.json")
    os.makedirs(args.out, exist_ok=True)
    with open(out_path, "w", encoding="utf-8", newline="\n") as fp:
        for chunk in all_chunks:
            fp.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    verse_chunks = type_counts.get("verses", 0)
    outline_chunks = type_counts.get("book_outline", 0)
    report_data = {
        "verse_total": len(all_verse_keys),
        "assigned": len(assigned),
        "unassigned": unassigned,
        "duplicated": duplicated,
        "counters": counters,
        "verse_chunks": verse_chunks,
        "outline_chunks": outline_chunks,
        "total_chunks": len(all_chunks),
        "collisions": collide_list,
        "psalm119": {"n": len(psalm119), "sizes": ps_sizes},
        "token_dist": token_dist,
        "missing_title": missing_title,
        "missing_msg": missing_msg,
        "missing_text": missing_text,
        "type_counts": type_counts,
        "verse_range_missing": verse_range_missing,
        "outline_range_set": outline_range_set,
        "index_bad": index_bad,
        "samples": samples,
        "before": before,
        "after": after,
        "header_bad": header_bad,
        "out_size": os.path.getsize(out_path),
        "split_intervals": split_intervals,
        "split_pieces": split_pieces,
    }
    os.makedirs(os.path.dirname(args.report), exist_ok=True)
    write_report(args.report, report_data)

    print("intervals", counters["intervals"], "verses_chunks", verse_chunks, "outline", outline_chunks, flush=True)
    print("rule2", counters["rule2"], "rule3", counters["rule3"], "rule4", counters["rule4"], flush=True)
    print("ps119", len(psalm119), ps_sizes[:5], "...", flush=True)
    print("unassigned", len(unassigned), "dup", len(duplicated), "collide", len(collide_list), flush=True)
    ok = (
        not unassigned and not duplicated and not collide_list
        and verse_chunks == 3625 and outline_chunks == 66
        and len(psalm119) == 22 and all(s == 8 for s in ps_sizes)
        and not header_bad and not index_bad
        and before == after
        and counters["intervals"] == 2507
        and counters["rule2"] == 163
        and counters["rule3"] == 124
        and counters["rule4"] == 3
    )
    print("BIBLE_CHUNKS_OK" if ok else "BIBLE_CHUNKS_BAD", flush=True)
    return 0 if ok else 2


if __name__ == "__main__":
    sys.exit(main())
