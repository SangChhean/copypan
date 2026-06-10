# -*- coding: utf-8 -*-
"""Additional Pool：本地 pool.jsonl 整行缓存。

``normalize_zh`` / ``zh_eq`` / ``zh_contains`` 是 testD 检索与 Pool 匹配的**唯一**
中文归一化入口（OpenCC t2s + ``_VARIANT_MAP`` + NFKC + 去标点）。
凡中文全等、子串 ``in`` 比对均须经此模块，勿另写繁简或去标点逻辑。

调用方：``enhanced_translate_service``、``source_translator``、
``retrieve_test_router``、Additional-pool 工具脚本。
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import unicodedata

import opencc as _opencc
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("testD.additional_pool")

_POOL_DIR = Path(__file__).resolve().parent / "Additional-pool"
_POOL_FILE = _POOL_DIR / "pool.jsonl"

_cache_by_norm: dict[str, dict[str, Any]] = {}
_cache_mtime: float = 0.0

_T2S = _opencc.OpenCC("t2s")

# 异体字/繁简混用归一化：仅用于生成匹配键，不影响存储与展示文本。
# OpenCC 是词组级转换，单字残留（如「藉一个」「显著/显着」）由此表兜底。
# 注意：不收 祢/祂（神学专用）、甚/祇（简体有独立含义，误映射风险高）。
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
    """中文全等：两侧均经 ``normalize_zh``。"""
    na, nb = normalize_zh(a), normalize_zh(b)
    return bool(na) and na == nb


def zh_contains(sub: str, s: str) -> bool:
    """中文子串：``normalize_zh(sub) in normalize_zh(s)``。"""
    ns, nh = normalize_zh(sub), normalize_zh(s)
    return bool(ns) and bool(nh) and ns in nh


def _load_pool_file() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    path = _POOL_FILE
    if not path.is_file():
        return out
    with path.open(encoding="utf-8-sig") as f:
        for line_no, raw in enumerate(f, 1):
            line = raw.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning("[additional_pool] pool.jsonl L%s 无效 JSON: %s", line_no, e)
                continue
            zh = (rec.get("zh") or "").strip()
            en = (rec.get("en") or "").strip()
            if not zh or not en:
                continue
            # 忽略记录里预存的 norm_zh（可能由旧规则生成），总是按当前规则现算
            norm = normalize_zh(zh)
            if not norm:
                continue
            out[norm] = {**rec, "zh": zh, "en": en, "norm_zh": norm}
    return out


def reload_pool(force: bool = False) -> int:
    global _cache_by_norm, _cache_mtime
    path = _POOL_FILE
    if not path.is_file():
        _cache_by_norm = {}
        _cache_mtime = 0.0
        return 0
    mtime = path.stat().st_mtime
    if not force and mtime == _cache_mtime and _cache_by_norm:
        return len(_cache_by_norm)
    _cache_by_norm = _load_pool_file()
    _cache_mtime = mtime
    logger.info("[additional_pool] 已加载 %s 条", len(_cache_by_norm))
    return len(_cache_by_norm)


def lookup_line_en(zh_line: str) -> str | None:
    zh_line = (zh_line or "").strip()
    if not zh_line:
        return None
    reload_pool()
    rec = _cache_by_norm.get(normalize_zh(zh_line))
    if not rec:
        return None
    en = (rec.get("en") or "").strip()
    return en or None


def append_records(records: list[dict[str, Any]], *, force: bool = False) -> tuple[int, int]:
    if not records:
        return 0, 0
    reload_pool(force=True)
    existing = dict(_cache_by_norm)
    added = 0
    skipped = 0
    now = datetime.now(timezone.utc).isoformat()
    for rec in records:
        zh = (rec.get("zh") or "").strip()
        en = (rec.get("en") or "").strip()
        if not zh or not en:
            continue
        norm = (rec.get("norm_zh") or "").strip() or normalize_zh(zh)
        if norm in existing and not force:
            skipped += 1
            continue
        existing[norm] = {
            "zh": zh,
            "en": en,
            "norm_zh": norm,
            "saved_at": rec.get("saved_at") or now,
            "prompt_version": rec.get("prompt_version") or "",
            "source": rec.get("source") or "enhanced_translate",
        }
        added += 1

    if added == 0:
        return 0, skipped

    _write_pool(existing)
    return added, skipped


def collect_auto_append_rows(
    line_ref_groups: list[dict[str, Any]],
    out_lines: list[str],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for i, group in enumerate(line_ref_groups):
        st = group.get("stats") or {}
        if st.get("additional_pool_line"):
            continue
        if not (group.get("gemini_translate") or "").strip():
            continue
        zh = (group.get("original_line") or "").strip()
        en = (out_lines[i] if i < len(out_lines) else "").strip()
        if not zh or not en:
            continue
        if zh == en:
            continue
        rows.append({
            "zh": zh,
            "en": en,
            "norm_zh": normalize_zh(zh),
            "source": "enhanced_translate",
        })
    return rows


def auto_append_enabled() -> bool:
    raw = (os.environ.get("ENHANCED_TRANSLATE_AUTO_APPEND") or "1").strip().lower()
    return raw not in ("0", "false", "no", "off")


def _write_pool(existing: dict[str, dict[str, Any]]) -> None:
    _POOL_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _POOL_FILE.with_suffix(".jsonl.tmp")
    if _POOL_FILE.is_file():
        shutil.copy2(_POOL_FILE, _POOL_FILE.with_suffix(".jsonl.bak"))
    with tmp.open("w", encoding="utf-8", newline="\n") as f:
        for row in existing.values():
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    tmp.replace(_POOL_FILE)
    reload_pool(force=True)


def update_record(zh: str, new_en: str) -> bool:
    """按 norm_zh 查找条目，替换 en 字段并写回 pool.jsonl。"""
    zh = (zh or "").strip()
    new_en = (new_en or "").strip()
    if not zh or not new_en:
        return False
    reload_pool(force=True)
    norm = normalize_zh(zh)
    if norm not in _cache_by_norm:
        return False
    existing = dict(_cache_by_norm)
    old = existing.pop(norm)
    now = datetime.now(timezone.utc).isoformat()
    existing[norm] = {
        "zh": zh,
        "en": new_en,
        "norm_zh": norm,
        "saved_at": now,
        "prompt_version": old.get("prompt_version") or "",
        "source": old.get("source") or "enhanced_translate",
    }
    _write_pool(existing)
    logger.info("[additional_pool] 已更新 norm_zh=%s", norm)
    return True
