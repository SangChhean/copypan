# -*- coding: utf-8 -*-
"""Additional Pool：本地 pool.jsonl 整行缓存。

``normalize_zh`` / ``zh_eq`` / ``zh_contains`` 是 testD 检索与 Pool 匹配的**唯一**
中文归一化入口（OpenCC t2s + ``_VARIANT_MAP`` + NFKC + 去标点）。
凡中文全等、子串 ``in`` 比对均须经此模块，勿另写繁简或去标点逻辑。
``zh_fuzzy_eq`` 仅供 reference 行整行 Pool 全等（``_pool_lookup(fuzzy=True)``），outline 不得使用。

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
    "题": "提",
    "唯": "惟",
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


def levenshtein_distance(a: str, b: str) -> int:
    """标准 Levenshtein 编辑距离（双层循环 DP）。"""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i]
        for j, cb in enumerate(b, 1):
            curr.append(
                min(
                    curr[j - 1] + 1,
                    prev[j] + 1,
                    prev[j - 1] + (ca != cb),
                )
            )
        prev = curr
    return prev[-1]


def _edit_positions_in_a(a: str, b: str) -> list[int]:
    """回溯 Levenshtein，返回字符串 a 中参与编辑的 0-based 下标。"""
    m, n = len(a), len(b)
    if m == 0 and n == 0:
        return []
    dp = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        dp[i][0] = i
    for j in range(n + 1):
        dp[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,
                dp[i][j - 1] + 1,
                dp[i - 1][j - 1] + cost,
            )
    positions: set[int] = set()
    i, j = m, n
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            cost = 0 if a[i - 1] == b[j - 1] else 1
            if dp[i][j] == dp[i - 1][j - 1] + cost:
                if cost == 1:
                    positions.add(i - 1)
                i -= 1
                j -= 1
                continue
        if i > 0 and dp[i][j] == dp[i - 1][j] + 1:
            positions.add(i - 1)
            i -= 1
        elif j > 0 and dp[i][j] == dp[i][j - 1] + 1:
            positions.add(max(i - 1, 0))
            j -= 1
        else:
            break
    return sorted(positions)


def _max_consecutive_run(indices: list[int]) -> int:
    if not indices:
        return 0
    indices = sorted(indices)
    best = run = 1
    for k in range(1, len(indices)):
        if indices[k] == indices[k - 1] + 1:
            run += 1
            best = max(best, run)
        else:
            run = 1
    return best


def _edits_non_consecutive(a: str, b: str) -> bool:
    """编辑位点在 a 上不得连续（仅允许分散的单点差异）。"""
    positions = _edit_positions_in_a(a, b)
    if not positions:
        return True
    return _max_consecutive_run(positions) <= 1


def _fuzzy_threshold(ref_len: int) -> tuple[int, bool]:
    if ref_len > 30:
        return 8, False
    if ref_len <= 20:
        return 3, True
    return 4, True


def zh_fuzzy_eq(a: str, b: str) -> bool:
    """
    reference 行专用模糊全等（整行 Pool 全等，非子串）：
    1. 先 ``zh_eq``
    2. normalize 后 ≤ 20 字：编辑距离 ≤ 3，且编辑位点不连续
    3. normalize 后 21～30 字：编辑距离 ≤ 4，且编辑位点不连续
    4. normalize 后 > 30 字：编辑距离 ≤ 8
    """
    if zh_eq(a, b):
        return True
    na, nb = normalize_zh(a), normalize_zh(b)
    if not na or not nb:
        return False
    ref_len = max(len(na), len(nb))
    threshold, require_non_consecutive = _fuzzy_threshold(ref_len)
    if abs(len(na) - len(nb)) > threshold:
        return False
    dist = levenshtein_distance(na, nb)
    if dist > threshold:
        return False
    if require_non_consecutive and not _edits_non_consecutive(na, nb):
        return False
    return True


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


def recall_local_pool_hits(query: str, *, body_prefix: str = "") -> list[dict[str, Any]]:
    """
    本地 Additional Pool 子串召回，供篇题行第二轮补充 ES 未覆盖条目。
    body_prefix 非空时优先保留 normalize_zh(hit) 以 normalize_zh(body_prefix) 开头的命中。
    """
    query = (query or "").strip()
    body_prefix = (body_prefix or "").strip()
    if not query and not body_prefix:
        return []
    reload_pool()
    nq = normalize_zh(query) if query else ""
    nbp = normalize_zh(body_prefix) if body_prefix else ""
    hits: list[dict[str, Any]] = []
    for rec in _cache_by_norm.values():
        zh = (rec.get("zh") or "").strip()
        if not zh:
            continue
        nz = normalize_zh(zh)
        if nbp and nz.startswith(nbp):
            matched = True
        elif nq and nq in nz:
            matched = True
        else:
            matched = False
        if not matched:
            continue
        hits.append({
            "zh": zh,
            "text": zh,
            "en": (rec.get("en") or "").strip(),
            "retrieval_route": "local_pool",
        })
    return hits


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
