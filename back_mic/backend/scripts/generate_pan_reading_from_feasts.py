# -*- coding: utf-8 -*-
"""
从 ES feasts 索引读取指定特会全文，生成 pan_reading_feasts.json（与 FeastOutlineMaker 格式一致）。

用法：python generate_pan_reading_from_feasts.py
运行时按提示输入 book_id、year、feast_type、book_name_zh、subject。
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from elasticsearch import NotFoundError

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND_ROOT))

from es_config import es

PAN_READING_INDEX = "pan_reading"
FEASTS_INDEX = "feasts"
CONFERENCE_ORDER = ["ic", "is", "mdc", "st", "if", "tgc", "wt", "ftta", "ftta_s", "ftta_f"]

OUTPUT_PATH = _BACKEND_ROOT / "database" / "upload" / "pan_reading_feasts.json"


def to_chinese_num(n: int) -> str:
    digits = ["", "一", "二", "三", "四", "五", "六", "七", "八", "九"]
    if n < 10:
        return digits[n]
    if n < 20:
        return "十" + digits[n % 10]
    tens, ones = divmod(n, 10)
    return digits[tens] + "十" + (digits[ones] if ones else "")


def feast_type_code(feast_type: str) -> str:
    return feast_type.replace("_", "-")


def pan_reading_type(es_type: str) -> str:
    if es_type == "bible_reading":
        return "b_read"
    return es_type


def conference_code_from_refid(refid: str) -> str:
    m = re.match(r"^feasts_\d{4}-(.+)$", refid or "")
    if not m:
        return ""
    return m[1].replace("-", "_")


def merge_by_refid(existing: list, new_items: list) -> list:
    seen = {item["refid"] for item in existing}
    merged = list(existing)
    for item in new_items:
        if item["refid"] not in seen:
            merged.append(item)
            seen.add(item["refid"])
    return merged


def sort_toc_by_conference_order(toc: list) -> list:
    def sort_key(item: dict) -> int:
        code = conference_code_from_refid(item.get("refid", ""))
        try:
            return CONFERENCE_ORDER.index(code)
        except ValueError:
            return 999

    return sorted(toc, key=sort_key)


def parse_line_id(doc_id: str, book_id: str) -> tuple[int, int] | None:
    """feasts_2024-if_1-3 -> (1, 3)"""
    pattern = re.compile(rf"^{re.escape(book_id)}_(\d+)-(\d+)$")
    m = pattern.match(doc_id)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def fetch_feasts_lines(book_id: str) -> list[dict]:
    docs: list[dict] = []
    body = {
        "size": 500,
        "query": {"prefix": {"id": f"{book_id}_"}},
        "_source": ["id", "type", "zh", "en", "text"],
        "sort": [{"id": "asc"}],
    }
    r = es.search(index=FEASTS_INDEX, body=body)
    hits = r["hits"]["hits"]
    while hits:
        for h in hits:
            docs.append(h["_source"])
        if len(hits) < 500:
            break
        body["search_after"] = hits[-1]["sort"]
        r = es.search(index=FEASTS_INDEX, body=body)
        hits = r["hits"]["hits"]
    return docs


def group_by_chapter(feasts_docs: list[dict], book_id: str) -> dict[int, list[dict]]:
    chapters: dict[int, list[dict]] = defaultdict(list)
    for doc in feasts_docs:
        parsed = parse_line_id(doc["id"], book_id)
        if not parsed:
            continue
        msg_num, _line_num = parsed
        chapters[msg_num].append(doc)
    for msg_num in chapters:
        chapters[msg_num].sort(
            key=lambda d: parse_line_id(d["id"], book_id)[1]  # type: ignore[index]
        )
    return dict(sorted(chapters.items()))


def get_pan_reading_source(doc_id: str) -> dict | None:
    try:
        res = es.get(index=PAN_READING_INDEX, id=doc_id)
        return res.get("_source")
    except NotFoundError:
        return None


def build_msg_doc(
    book_id: str,
    year: str,
    book_name_zh: str,
    msg_num: int,
    lines: list[dict],
) -> dict:
    year_ref_id = f"feasts_{year}"
    msg_ref_id = f"{book_id}_{msg_num}"
    zh_rows: list[list] = []
    en_rows: list[list] = []

    for line in lines:
        line_zh = (line.get("zh") or line.get("text") or "").strip()
        line_en = (line.get("en") or "").strip()
        if not line_zh and not line_en:
            continue
        pr_type = pan_reading_type(line.get("type") or "")
        zh_rows.append([line_zh, pr_type])
        en_rows.append([line_en, pr_type])

    return {
        "index": ["pan_reading"],
        "refid": msg_ref_id,
        "type": "msg",
        "showButtons": "1",
        "bread": [
            {"text": "首页", "refid": "index"},
            {"text": "节期", "refid": "feasts"},
            {"text": f"{year}年", "refid": year_ref_id},
            {"text": book_name_zh, "refid": book_id},
            {"text": f"第{to_chinese_num(msg_num)}篇", "refid": ""},
        ],
        "zh": zh_rows,
        "en": en_rows,
    }


def chapter_title_zh(lines: list[dict]) -> str:
    for line in lines:
        if line.get("type") == "title":
            return (line.get("zh") or line.get("text") or "").strip()
    if lines:
        return (lines[0].get("zh") or lines[0].get("text") or "").strip()
    return ""


def generate(
    book_id: str,
    year: str,
    feast_type: str,
    book_name_zh: str,
    subject: str,
) -> list[dict]:
    year_ref_id = f"feasts_{year}"
    type_code = feast_type_code(feast_type)
    if book_id != f"feasts_{year}-{type_code}":
        print(
            f"警告: book_id={book_id} 与 feasts_{year}-{type_code} 不一致，将使用输入的 book_id",
            file=sys.stderr,
        )

    feasts_lines = fetch_feasts_lines(book_id)
    chapters = group_by_chapter(feasts_lines, book_id)
    if not chapters:
        raise RuntimeError(f"未在 feasts 索引中找到 id 前缀为 {book_id}_ 的文档")

    feasts_root = get_pan_reading_source("feasts") or {}
    year_doc = get_pan_reading_source(year_ref_id) or {}

    docs: list[dict] = []

    cells = merge_by_refid(
        list(feasts_root.get("cells") or []),
        [{"text": f"{year}年", "refid": year_ref_id}],
    )
    docs.append(
        {
            "index": ["pan_reading"],
            "refid": "feasts",
            "type": "cells",
            "bread": [
                {"text": "首页", "refid": "index"},
                {"text": "节期", "refid": ""},
            ],
            "cells": cells,
        }
    )

    year_toc = sort_toc_by_conference_order(
        merge_by_refid(
            list(year_doc.get("toc") or []),
            [
                {
                    "text": f"{book_name_zh}，{subject}",
                    "refid": book_id,
                    "type": "toc",
                }
            ],
        )
    )
    docs.append(
        {
            "index": ["pan_reading"],
            "refid": year_ref_id,
            "type": "toc",
            "bread": [
                {"text": "首页", "refid": "index"},
                {"text": "节期", "refid": "feasts"},
                {"text": f"{year}年", "refid": ""},
            ],
            "toc": year_toc,
        }
    )

    book_toc = []
    for msg_num in sorted(chapters.keys()):
        title = chapter_title_zh(chapters[msg_num])
        book_toc.append(
            {
                "text": title,
                "refid": f"{book_id}_{msg_num}",
                "type": "toc",
            }
        )
    docs.append(
        {
            "index": ["pan_reading"],
            "refid": book_id,
            "type": "toc",
            "bread": [
                {"text": "首页", "refid": "index"},
                {"text": "节期", "refid": "feasts"},
                {"text": f"{year}年", "refid": year_ref_id},
                {"text": book_name_zh, "refid": ""},
            ],
            "toc": book_toc,
        }
    )

    for msg_num in sorted(chapters.keys()):
        docs.append(
            build_msg_doc(book_id, year, book_name_zh, msg_num, chapters[msg_num])
        )

    return docs


def prompt_inputs() -> tuple[str, str, str, str, str]:
    print("请输入参数（直接回车可使用括号内默认值）：")
    book_id = input("book_id [feasts_2024-if]: ").strip() or "feasts_2024-if"
    year = input("year [2024]: ").strip() or "2024"
    feast_type = input("feast_type [if]: ").strip() or "if"
    book_name_zh = (
        input("book_name_zh [2024年秋季长老训练]: ").strip() or "2024年秋季长老训练"
    )
    subject = input("subject [活在神国的实际里]: ").strip() or "活在神国的实际里"
    return book_id, year, feast_type, book_name_zh, subject


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    book_id, year, feast_type, book_name_zh, subject = prompt_inputs()
    print(f"\n生成中: book_id={book_id}, year={year}, feast_type={feast_type}")
    print(f"  book_name_zh={book_name_zh}")
    print(f"  subject={subject}")

    docs = generate(book_id, year, feast_type, book_name_zh, subject)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(
        json.dumps(docs, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    type_counts = defaultdict(int)
    for d in docs:
        type_counts[d["type"]] += 1
    msg_docs = [d for d in docs if d["type"] == "msg"]
    total_zh = sum(len(d.get("zh") or []) for d in msg_docs)
    feasts_count = len(fetch_feasts_lines(book_id))

    print(f"\n已写入: {OUTPUT_PATH}")
    print(f"文档数: {len(docs)} (cells/toc/book-toc/msg: {dict(type_counts)})")
    print(f"篇全文 zh 总行数: {total_zh}，feasts 索引行数: {feasts_count}")
    if total_zh != feasts_count:
        print("警告: 篇全文行数与 feasts 索引不一致，请检查空行或 id 解析", file=sys.stderr)
    else:
        print("验证: 篇全文 zh/en 行数与 feasts 索引一致")


if __name__ == "__main__":
    main()
