# -*- coding: utf-8 -*-
"""诗歌库查询（Step 0 数据读取层）。"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

HYMNS_PATH = Path(__file__).parent.parent / "data" / "hymns.json"


@lru_cache(maxsize=1)
def _load_hymns() -> dict[tuple[str, int], dict]:
    data = json.loads(HYMNS_PATH.read_text(encoding="utf-8"))
    return {(h["source"], h["no"]): h for h in data["hymns"]}


def verify_hymn(source: str, no: int) -> dict | None:
    """
    校验诗歌编号是否真实存在。
    source: '大本' 或 '补充'（数据里还有 '儿童'/'附' 两种来源，这个功能目前用不到，
    但函数本身不做限制，调用方负责只传 '大本'/'补充'）
    返回 None 表示该 (source, no) 组合不存在（模型可能编造了或者记错了来源），
    否则返回该诗歌的完整信息（含 title、note、content）
    """
    hymns = _load_hymns()
    return hymns.get((source, no))
