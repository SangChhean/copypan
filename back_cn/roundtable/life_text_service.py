# -*- coding: utf-8 -*-
"""生命读经原文查询（Step 0 数据读取层）。"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

LIFE_TEXTS_DIR = Path(__file__).parent.parent / "data" / "life_texts"
BOOK_ORDER_PATH = Path(__file__).parent.parent / "data" / "lsm_book_order.json"


@lru_cache(maxsize=None)
def _load_book(book_id: int) -> dict:
    path = LIFE_TEXTS_DIR / f"life_{book_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"找不到卷号 {book_id} 的生命读经数据")
    return json.loads(path.read_text(encoding="utf-8"))


def load_book(book_id: int) -> dict:
    """公开包装：加载一卷 life_texts JSON（不破坏 _load_book 私有约定）。"""
    return _load_book(book_id)


def list_book_issues(book_id: int) -> dict:
    """返回某一卷的完整篇目列表（供起始篇选择器使用）。"""
    book = _load_book(book_id)
    messages = book.get("messages", {})
    issues = [
        {"issue": int(k), "title": v.get("title", "")}
        for k, v in messages.items()
    ]
    issues.sort(key=lambda x: x["issue"])
    return {
        "book_id": book_id,
        "book_name": book.get("book_name", ""),
        "issues": issues,
    }


@lru_cache(maxsize=1)
def _load_book_order_raw() -> list[int]:
    """
    与 front_cn/public/lsm_mapping.json 的 oldTestament + newTestament
    按 order 字段排序后拼接一致；order 即卷号 book_id。
    """
    if not BOOK_ORDER_PATH.exists():
        raise FileNotFoundError(
            f"找不到卷序文件：{BOOK_ORDER_PATH}（应与前端 lsm_mapping.json 的 order 一致）"
        )
    data = json.loads(BOOK_ORDER_PATH.read_text(encoding="utf-8"))
    order = data.get("order")
    if not isinstance(order, list) or not order:
        raise ValueError(f"卷序文件格式无效：{BOOK_ORDER_PATH}")
    return [int(x) for x in order]


def get_book_order() -> list[int]:
    """
    返回生命读经全部卷号按顺序排列的列表（用于确定「下一卷」）。
    顺序来自 lsm_book_order.json（与前端 lsm_mapping 同步）；
    仅保留本地已有 life_{id}.json 的卷（当前缺 10/12/14），避免跨卷续接踩空。
    """
    return [
        bid
        for bid in _load_book_order_raw()
        if (LIFE_TEXTS_DIR / f"life_{bid}.json").exists()
    ]


def list_books() -> list[dict]:
    """返回本地已有书卷列表：book_id + 去掉「生命读经」后缀的卷名。"""
    books = []
    for book_id in get_book_order():
        book_name = _load_book(book_id).get("book_name", "")
        books.append(
            {
                "book_id": book_id,
                "name": book_name.replace("生命读经", ""),
            }
        )
    return books


def get_book_message_count(book_id: int) -> int:
    """返回某卷生命读经的总篇数。"""
    book = _load_book(book_id)
    return len(book.get("messages", {}))


def resolve_cross_book_selection(
    start_book: int, start_issue: int, count: int
) -> list[tuple[int, int]]:
    """
    从 start_book 的 start_issue 篇开始，取 count 篇（1-3）。
    本卷剩余篇数不够时，自动按卷序延续到下一卷第1篇继续取。
    返回按顺序排列的 [(book_id, issue), ...]。
    """
    if not (1 <= count <= 3):
        raise ValueError("篇数须在 1~3 之间")
    order = get_book_order()
    if start_book not in order:
        raise ValueError(f"未知卷号: {start_book}")
    cur_idx = order.index(start_book)
    cur_book = start_book
    cur_issue = start_issue
    result: list[tuple[int, int]] = []
    while len(result) < count:
        total = get_book_message_count(cur_book)
        if cur_issue <= total:
            result.append((cur_book, cur_issue))
            cur_issue += 1
        else:
            cur_idx += 1
            if cur_idx >= len(order):
                raise ValueError(
                    "已达生命读经全集最后一卷，没有更多篇可续接"
                )
            cur_book = order[cur_idx]
            cur_issue = 1
    return result


def get_messages_by_selection(selection: list[tuple[int, int]]) -> list[dict]:
    """按 (book_id, issue) 顺序列表取出对应篇的完整内容。"""
    return [get_message(b, i) for b, i in selection]


def get_message(book_id: int, message_no: int) -> dict:
    """返回 {"book_name": ..., "title": ..., "paragraphs": [...], "full_text": "..."}"""
    book = _load_book(book_id)
    msg = book.get("messages", {}).get(str(message_no))
    if msg is None:
        raise ValueError(f"卷 {book_id} 没有第 {message_no} 篇")
    full_text = "\n".join(msg["paragraphs"])
    return {
        "book_name": book["book_name"],
        "title": msg["title"],
        "paragraphs": msg["paragraphs"],
        "full_text": full_text,
    }


def get_messages(book_id: int, message_nos: list[int]) -> list[dict]:
    """支持 1-3 篇，按用户选择顺序返回（单卷；脚本/测试仍可用）"""
    if not (1 <= len(message_nos) <= 3):
        raise ValueError("篇号数量须在 1~3 之间")
    return [get_message(book_id, n) for n in message_nos]
