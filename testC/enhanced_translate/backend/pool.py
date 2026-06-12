# -*- coding: utf-8 -*-
"""增强式翻译练习版笔记本（testC 专属，端口 8062）。
pool.jsonl 位于本文件同目录，与主站数据完全隔离，互不污染。
"""
from __future__ import annotations

import json
import logging
import re
import shutil
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("testc.enhanced_translate_pool")

# testC 专属语料文件，绝不指向主站
_POOL_FILE = Path(__file__).resolve().parent / "pool.jsonl"

_cache_by_norm: dict[str, dict[str, Any]] = {}
_cache_mtime: float = 0.0

# opencc 繁简转换：有则用，无则跳过
try:
    import opencc as _opencc
    _T2S = _opencc.OpenCC("t2s")
    def _t2s(s: str) -> str:
        return _T2S.convert(s)
except ImportError:
    def _t2s(s: str) -> str:
        return s

_VARIANT_MAP = str.maketrans({
    "藉": "借", "著": "着", "彀": "够", "裏": "里",
    "裡": "里", "於": "于", "麽": "么", "牠": "它",
    "那": "哪", "豫": "预",
})


def normalize_zh(s: str) -> str:
    s = _t2s(s or "")
    s = s.translate(_VARIANT_MAP)
    s = unicodedata.normalize("NFKC", s)
    return re.sub(r"[\W_]+", "", s, flags=re.UNICODE)


def zh_eq(a: str, b: str) -> bool:
    na, nb = normalize_zh(a), normalize_zh(b)
    return bool(na) and na == nb


def _load_pool_file() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not _POOL_FILE.is_file():
        logger.warning("[pool] pool.jsonl 不存在：%s", _POOL_FILE)
        return out
    with _POOL_FILE.open(encoding="utf-8-sig") as f:
        for line_no, raw in enumerate(f, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning("[pool] L%s 无效 JSON: %s", line_no, e)
                continue
            zh = (rec.get("zh") or "").strip()
            en = (rec.get("en") or "").strip()
            if not zh or not en:
                continue
            norm = normalize_zh(zh)
            if not norm:
                continue
            out[norm] = {**rec, "zh": zh, "en": en, "norm_zh": norm}
    return out


def reload_pool(force: bool = False) -> int:
    global _cache_by_norm, _cache_mtime
    if not _POOL_FILE.is_file():
        _cache_by_norm = {}
        _cache_mtime = 0.0
        return 0
    mtime = _POOL_FILE.stat().st_mtime
    if not force and mtime == _cache_mtime and _cache_by_norm:
        return len(_cache_by_norm)
    _cache_by_norm = _load_pool_file()
    _cache_mtime = mtime
    logger.info("[pool] 已加载 %s 条", len(_cache_by_norm))
    return len(_cache_by_norm)


def lookup(zh: str) -> str | None:
    """第一层查找：整行精确匹配，命中返回英文，否则 None。"""
    zh = (zh or "").strip()
    if not zh:
        return None
    reload_pool()
    rec = _cache_by_norm.get(normalize_zh(zh))
    if not rec:
        return None
    en = (rec.get("en") or "").strip()
    return en or None


def append_records(rows: list[dict[str, Any]]) -> int:
    """回写闭环：把新译文追加进 pool.jsonl。已存在的跳过，返回实际追加数。"""
    if not rows:
        return 0
    reload_pool(force=True)
    existing = dict(_cache_by_norm)
    now = datetime.now(timezone.utc).isoformat()
    added = 0
    for rec in rows:
        zh = (rec.get("zh") or "").strip()
        en = (rec.get("en") or "").strip()
        if not zh or not en:
            continue
        norm = normalize_zh(zh)
        if norm in existing:
            continue
        existing[norm] = {
            "zh": zh,
            "en": en,
            "norm_zh": norm,
            "saved_at": now,
            "prompt_version": "",
            "source": rec.get("source") or "practice",
        }
        added += 1
    if added > 0:
        _write_pool(existing)
    return added


def update_record(zh: str, new_en: str) -> bool:
    """人工修订回写：更新已有条目的译文。找不到返回 False。"""
    zh = (zh or "").strip()
    new_en = (new_en or "").strip()
    if not zh or not new_en:
        return False
    reload_pool(force=True)
    norm = normalize_zh(zh)
    if norm not in _cache_by_norm:
        return False
    existing = dict(_cache_by_norm)
    old = existing[norm]
    existing[norm] = {
        "zh": zh,
        "en": new_en,
        "norm_zh": norm,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "prompt_version": old.get("prompt_version") or "",
        "source": old.get("source") or "practice",
    }
    _write_pool(existing)
    logger.info("[pool] 已更新 norm_zh=%s", norm)
    return True


def _write_pool(existing: dict[str, dict[str, Any]]) -> None:
    tmp = _POOL_FILE.with_suffix(".jsonl.tmp")
    if _POOL_FILE.is_file():
        shutil.copy2(_POOL_FILE, _POOL_FILE.with_suffix(".jsonl.bak"))
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for row in existing.values():
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(_POOL_FILE)
    reload_pool(force=True)


# 模块导入时自动加载一次
_initial_count = reload_pool()
print(f"[pool] 启动加载完成，共 {_initial_count} 条")
