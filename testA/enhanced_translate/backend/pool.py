# -*- coding: utf-8 -*-
import json
import os
import re
import threading
import unicodedata

import opencc as _opencc

POOL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pool.jsonl")

_POOL: dict[str, dict] = {}
_LOCK = threading.Lock()

_T2S = _opencc.OpenCC("t2s")

_VARIANT_MAP = str.maketrans({
    "藉": "借",
    "著": "着",
    "彀": "够",
    "裏": "里",
    "裡": "里",
    "於": "于",
    "麽": "么",
    "牠": "它",
    "那": "哪",
    "豫": "预",
})


def normalize_zh(s: str) -> str:
    s = _T2S.convert(s or "")
    s = s.translate(_VARIANT_MAP)
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"[\W_]+", "", s, flags=re.UNICODE)


def zh_eq(a: str, b: str) -> bool:
    na, nb = normalize_zh(a), normalize_zh(b)
    return bool(na) and na == nb


def load_pool() -> int:
    """从 pool.jsonl 加载；返回有效条数（去重后 key 数）。"""
    global _POOL
    loaded: dict[str, dict] = {}
    if os.path.isfile(POOL_FILE):
        with open(POOL_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                zh = rec.get("zh")
                if zh is None:
                    continue
                key = normalize_zh(str(zh))
                if not key:
                    continue
                loaded[key] = rec
    _POOL = loaded
    return len(_POOL)


def lookup(zh: str) -> str | None:
    rec = _POOL.get(normalize_zh(zh))
    if not rec:
        return None
    en = rec.get("en")
    return str(en) if en is not None else None


def append_records(rows: list[dict]) -> None:
    if not rows:
        return
    with _LOCK:
        with open(POOL_FILE, "a", encoding="utf-8") as f:
            for row in rows:
                rec = {
                    "zh": row["zh"],
                    "en": row["en"],
                    "source": row.get("source", "practice"),
                }
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                key = normalize_zh(str(rec["zh"]))
                if key:
                    _POOL[key] = rec


def update_record(zh: str, new_en: str) -> bool:
    key = normalize_zh(zh)
    with _LOCK:
        rec = _POOL.get(key)
        if not rec:
            return False
        rec = dict(rec)
        rec["en"] = new_en
        _POOL[key] = rec
        with open(POOL_FILE, "w", encoding="utf-8") as f:
            for item in _POOL.values():
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        return True


_count = load_pool()
print(f"已加载 {_count} 条")
