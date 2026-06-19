#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从 5 个双语 kg-rag 索引导出去重后的中英文出处对照 JSON。"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_BACKEND))

from es_config import es
from features.enhanced_translate.pool import normalize_zh
from features.enhanced_translate.source_translator import _strip_paragraph_suffix

_OUT = _BACKEND / "data" / "enhanced_translate" / "source_pairs.json"

_INDICES = [
    "kg-rag_cwwl",
    "kg-rag_life",
    "kg-rag_cwwn",
    "kg-rag_others",
    "kg-rag_bib",
]

_PAR_EN_RE = re.compile(r",\s*par\.\s*[\d\-]+", re.IGNORECASE)


def _zh_base_key(source_zh: str) -> str:
    inner = (source_zh or "").strip().strip("（）()")
    base, _ = _strip_paragraph_suffix(inner)
    return base.strip()


def _format_source_zh(base: str) -> str:
    base = (base or "").strip()
    if not base:
        return ""
    if base.startswith("（"):
        return base
    return f"（{base}）"


def _clean_source_en(en: str) -> str:
    s = (en or "").strip().strip("（）()")
    s = _PAR_EN_RE.sub("", s).strip().rstrip(",").strip()
    if not s:
        return ""
    return f"({s})"


def _en_quality(en: str) -> int:
    if not en:
        return 999
    return 1 if _PAR_EN_RE.search(en) else 0


def _scroll_index(index: str) -> list[dict]:
    resp = es.search(
        index=index,
        scroll="5m",
        size=2000,
        body={
            "query": {"match_all": {}},
            "_source": ["source_zh", "source_en"],
        },
        request_timeout=60,
    )
    scroll_id = resp.get("_scroll_id")
    hits = list(resp.get("hits", {}).get("hits") or [])
    while True:
        if not scroll_id:
            break
        page = es.scroll(scroll_id=scroll_id, scroll="5m", request_timeout=60)
        scroll_id = page.get("_scroll_id")
        batch = page.get("hits", {}).get("hits") or []
        if not batch:
            break
        hits.extend(batch)
    if scroll_id:
        try:
            es.clear_scroll(scroll_id=scroll_id)
        except Exception:
            pass
    return hits


def _merge_hits(hits: list[dict]) -> dict[str, dict]:
    pairs: dict[str, dict] = {}
    for hit in hits:
        src = hit.get("_source") or {}
        sz = (src.get("source_zh") or "").strip()
        se = (src.get("source_en") or "").strip()
        if not sz or not se:
            continue
        base = _zh_base_key(sz)
        if not base:
            continue
        norm = normalize_zh(base)
        if not norm:
            continue
        en_clean = _clean_source_en(se)
        row = pairs.get(norm)
        if row is None:
            pairs[norm] = {
                "key": base,
                "source_zh": _format_source_zh(base),
                "source_en": en_clean,
                "norm_zh": norm,
            }
        elif _en_quality(en_clean) < _en_quality(row["source_en"]):
            row["source_en"] = en_clean
    return dict(sorted(pairs.items(), key=lambda x: x[1]["key"]))


def main() -> None:
    by_index: dict[str, dict[str, dict]] = {}
    counts: dict[str, int] = {}
    for index in _INDICES:
        print(f"Scrolling {index}...")
        hits = _scroll_index(index)
        pairs = _merge_hits(hits)
        by_index[index] = pairs
        counts[index] = len(pairs)
        print(f"  chunks={len(hits)} unique={len(pairs)}")

    out = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "path": str(_OUT.relative_to(_BACKEND)).replace("\\", "/"),
            "indices": _INDICES,
            "dedupe": "strip paragraph suffix (，第*段); source_en strips , par. N",
            "counts": counts,
        },
        **by_index,
    }

    _OUT.parent.mkdir(parents=True, exist_ok=True)
    with _OUT.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"Wrote {_OUT} ({_OUT.stat().st_size // 1024} KB)")


if __name__ == "__main__":
    main()
