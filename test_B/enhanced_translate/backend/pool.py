# -*- coding: utf-8 -*-
import json
import os
import re
import threading
import unicodedata

POOL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pool.jsonl")
_LOCK = threading.Lock()

_POOL: dict[str, dict] = {}


def normalize_zh(s: str) -> str:
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"[\W_]+", "", s)


def zh_eq(a: str, b: str) -> bool:
    na, nb = normalize_zh(a), normalize_zh(b)
    return bool(na) and na == nb


def zh_contains(sub: str, s: str) -> bool:
    ns, nh = normalize_zh(sub), normalize_zh(s)
    return bool(ns) and bool(nh) and ns in nh


def load_pool() -> None:
    global _POOL
    pool: dict[str, dict] = {}
    with open(POOL_FILE, encoding="utf-8") as f:
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
            pool[key] = rec
    _POOL = pool
    print(f"[pool] 已加载 {len(_POOL)} 条翻译语料")


def lookup(zh: str) -> str | None:
    rec = _POOL.get(normalize_zh(zh))
    if rec is None:
        return None
    en = rec.get("en")
    return str(en) if en is not None else None


def append_records(rows: list[dict]) -> None:
    with _LOCK:
        with open(POOL_FILE, "a", encoding="utf-8") as f:
            for rec in rows:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                zh = rec.get("zh")
                if zh is not None:
                    key = normalize_zh(str(zh))
                    if key:
                        _POOL[key] = rec


def update_record(zh: str, new_en: str) -> bool:
    key = normalize_zh(zh)
    with _LOCK:
        rec = _POOL.get(key)
        if rec is None:
            return False
        rec = dict(rec)
        rec["en"] = new_en
        _POOL[key] = rec
        with open(POOL_FILE, "w", encoding="utf-8") as f:
            for item in _POOL.values():
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        return True


load_pool()
