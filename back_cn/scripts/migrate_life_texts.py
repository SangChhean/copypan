#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性迁移：把 back_anshifenliang 的生命读经 HTML 转为 back_cn 自有纯文本 JSON。

源：back_anshifenliang/data/zhi_shi_html/read_life_v2/life_{书号}-{篇号}.json（实为 HTML）
目标：back_cn/data/life_texts/life_{书号}.json（按卷合并）
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[2]
SOURCE_DIR = REPO_ROOT / "back_anshifenliang" / "data" / "zhi_shi_html" / "read_life_v2"
OUTPUT_DIR = REPO_ROOT / "back_cn" / "data" / "life_texts"

FILENAME_RE = re.compile(r"^life_(\d+)-(\d+)\.json$", re.IGNORECASE)


def clean_text(el) -> str:
    """提取纯文本，去掉 HTML，并压缩多余空白。"""
    text = el.get_text(separator="", strip=False)
    text = text.replace("\xa0", " ").replace("\r", "").replace("\n", "")
    text = re.sub(r"[ \t]+", " ", text).strip()
    return text


def parse_message(path: Path) -> tuple[str, str, list[str]]:
    """返回 (book_name, title, paragraphs)。失败则抛 ValueError。"""
    html = path.read_text(encoding="utf-8")
    if not html.strip():
        raise ValueError("文件内容为空")

    soup = BeautifulSoup(html, "html.parser")
    h3s = soup.find_all("h3")
    if len(h3s) != 2:
        raise ValueError(f"<h3> 数量为 {len(h3s)}，预期为 2")

    book_name = clean_text(h3s[0])
    title = clean_text(h3s[1])
    if not book_name:
        raise ValueError("卷名（第一个 <h3>）为空")
    if not title:
        raise ValueError("篇名（第二个 <h3>）为空")

    paragraphs: list[str] = []
    for div in soup.find_all("div"):
        para = clean_text(div)
        if para:
            paragraphs.append(para)

    if not paragraphs:
        raise ValueError("正文段落为空（无有效 <div> 文本）")

    return book_name, title, paragraphs


def main() -> int:
    if not SOURCE_DIR.is_dir():
        print(f"ERROR: 源目录不存在: {SOURCE_DIR}", file=sys.stderr)
        return 1

    files = sorted(SOURCE_DIR.glob("life_*-*.json"))
    if not files:
        print(f"ERROR: 源目录下没有 life_*-*.json: {SOURCE_DIR}", file=sys.stderr)
        return 1

    # book_id -> { book_name, messages: { msg_id: {...} } }
    books: dict[int, dict] = {}
    book_names: dict[int, set[str]] = defaultdict(set)
    failures: list[str] = []
    skipped_name: list[str] = []
    ok_count = 0

    for path in files:
        m = FILENAME_RE.match(path.name)
        if not m:
            skipped_name.append(path.name)
            failures.append(f"{path.name}: 文件名不符合 life_{{书号}}-{{篇号}}.json")
            continue

        book_id = int(m.group(1))
        msg_id = int(m.group(2))

        try:
            book_name, title, paragraphs = parse_message(path)
        except Exception as e:
            failures.append(f"{path.name}: {e}")
            continue

        book_names[book_id].add(book_name)
        if book_id not in books:
            books[book_id] = {
                "book_id": book_id,
                "book_name": book_name,
                "messages": {},
            }
        # 若同卷出现不同卷名，保留第一次并记失败提示
        if books[book_id]["book_name"] != book_name:
            failures.append(
                f"{path.name}: 卷名不一致 "
                f"(已有 {books[book_id]['book_name']!r}，本文件 {book_name!r})"
            )

        msg_key = str(msg_id)
        if msg_key in books[book_id]["messages"]:
            failures.append(f"{path.name}: 篇号 {msg_id} 重复")
            continue

        books[book_id]["messages"][msg_key] = {
            "title": title,
            "paragraphs": paragraphs,
        }
        ok_count += 1

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 清理旧输出，避免残留
    for old in OUTPUT_DIR.glob("life_*.json"):
        old.unlink()

    written = 0
    for book_id in sorted(books):
        payload = books[book_id]
        # messages 按篇号数字排序写入（JSON 对象键顺序）
        sorted_msgs = {
            k: payload["messages"][k]
            for k in sorted(payload["messages"], key=lambda x: int(x))
        }
        out = {
            "book_id": payload["book_id"],
            "book_name": payload["book_name"],
            "messages": sorted_msgs,
        }
        out_path = OUTPUT_DIR / f"life_{book_id}.json"
        out_path.write_text(
            json.dumps(out, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        written += 1

    total_msgs = sum(len(b["messages"]) for b in books.values())

    print("=== 生命读经迁移汇总 ===")
    print(f"源目录: {SOURCE_DIR}")
    print(f"输出目录: {OUTPUT_DIR}")
    print(f"源文件数: {len(files)}")
    print(f"成功解析篇数: {ok_count}")
    print(f"生成卷文件数: {written}")
    print(f"输出中总篇数: {total_msgs}")
    print(f"失败/异常条目数: {len(failures)}")
    if failures:
        print("--- 失败明细 ---")
        for line in failures:
            print(line)
    else:
        print("失败明细: （无）")

    # 每卷篇数一览
    print("--- 每卷篇数 ---")
    for book_id in sorted(books):
        n = len(books[book_id]["messages"])
        name = books[book_id]["book_name"]
        print(f"  life_{book_id}.json  {name}  {n} 篇")

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
