# -*- coding: utf-8 -*-
"""离线：源 jsonl 重复 id / 文本哈希统计（不连 ES、不读密钥）。

用法：
  python qa4/backend/tools/analyze_source_dupes.py \\
    --source-root <es/data> --out G:\\PanAI4.0专用\\logs\\stage2
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

DEFAULT_OUT = Path(r"G:\PanAI4.0专用\logs\stage2")
DEFAULT_ROOT = Path(os.environ.get("QA4_SOURCE_ROOT") or "") / "es" / "data" if os.environ.get("QA4_SOURCE_ROOT") else None
INDICES = ("text_life", "text_cwwl", "text_cwwn", "text_others", "map_note")
FOCUS_PREFIX = "cwwl_1994-1997-2"


def resolve_root(arg: Optional[Path]) -> Optional[Path]:
    if arg and Path(arg).is_dir():
        return Path(arg)
    env = (os.environ.get("QA4_SOURCE_ROOT") or "").strip()
    if env:
        p = Path(env)
        if (p / "es" / "data").is_dir():
            return p / "es" / "data"
        if p.is_dir() and (p / "panai4_text_life").is_dir():
            return p
        if p.is_dir():
            return p
    # 约定：qa4/data/es_src
    cand = _BACKEND.parent / "data" / "es_src"
    return cand if cand.is_dir() else None


def jsonl_paths(root: Path, logical: str) -> list[Path]:
    d = root / f"panai4_{logical}"
    if (d / "shards").is_dir():
        return sorted((d / "shards").glob("*.jsonl"))
    if d.is_dir():
        return sorted(d.glob("**/*.jsonl"))
    return []


def iter_rows(paths: Iterable[Path]) -> Iterator[dict[str, Any]]:
    for p in paths:
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)


def text_hash(text: str) -> str:
    s = re.sub(r"\s+", "", text or "")
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def volume_key(logical: str, row: dict[str, Any]) -> str:
    cid = str(row.get("chunk_id") or "")
    if logical == "text_cwwl" and cid.startswith("cwwl_"):
        # cwwl_1994-1997-2-1#1-10 → cwwl_1994-1997-2 ；cwwl_1998-1-3#1-2 → cwwl_1998-1
        body = cid[5:]
        left = body.split("#", 1)[0]
        parts = left.split("-")
        # year or year-range + volume number (first numeric group after years)
        if len(parts) >= 2:
            # 1994-1997-2-1 → take 1994-1997-2 ；1998-1-3 → 1998-1
            if parts[0].isdigit() and len(parts[0]) == 4:
                if len(parts) >= 2 and parts[1].isdigit() and len(parts[1]) == 4:
                    # year range
                    return "cwwl_" + "-".join(parts[:3]) if len(parts) >= 3 else "cwwl_" + "-".join(parts[:2])
                return "cwwl_" + "-".join(parts[:2])
        return "cwwl_" + left
    if logical == "text_life" and cid.startswith("life_"):
        parts = cid.split("-")
        return "-".join(parts[:2]) if len(parts) >= 2 else cid
    bt = row.get("book_title")
    if bt:
        return str(bt)
    if "#" in cid:
        return cid.split("#", 1)[0]
    if "-" in cid:
        return cid.rsplit("-", 1)[0]
    return cid or "_empty"


def analyze_index(paths: list[Path], logical: str) -> dict[str, Any]:
    id_count: Counter[str] = Counter()
    hash_to_ids: dict[str, list[str]] = defaultdict(list)
    empty_n = 0
    lengths: list[int] = []
    by_vol: dict[str, list[str]] = defaultdict(list)
    rows_n = 0
    for row in iter_rows(paths):
        rows_n += 1
        cid = str(row.get("chunk_id") or "")
        text = str(row.get("text") or "")
        id_count[cid] += 1
        ln = len(text)
        lengths.append(ln)
        if not text.strip():
            empty_n += 1
        h = text_hash(text)
        if cid:
            hash_to_ids[h].append(cid)
            by_vol[volume_key(logical, row)].append(cid)

    dup_id_rows = sum(c - 1 for c in id_count.values() if c > 1)
    dup_id_keys = sum(1 for c in id_count.values() if c > 1)
    # 文本完全相同（去空白后）：出现次数>1 的哈希所覆盖的条数
    multi_hash = {h: ids for h, ids in hash_to_ids.items() if len(ids) > 1}
    same_text_rows = sum(len(ids) for ids in multi_hash.values())
    unique_ids = len([k for k in id_count if k])

    vol_stats = []
    for vol, ids in by_vol.items():
        vol_stats.append({"volume": vol, "n": len(ids), "unique_ids": len(set(ids))})
    vol_stats.sort(key=lambda x: -x["n"])

    focus = None
    if logical == "text_cwwl":
        focus_ids = []
        focus_hashes = []
        for row in iter_rows(paths):
            cid = str(row.get("chunk_id") or "")
            if not cid.startswith(FOCUS_PREFIX):
                continue
            focus_ids.append(cid)
            focus_hashes.append((cid, text_hash(str(row.get("text") or ""))))
        # 其它册哈希集合
        other_hash_ids: dict[str, list[str]] = defaultdict(list)
        for row in iter_rows(paths):
            cid = str(row.get("chunk_id") or "")
            if cid.startswith(FOCUS_PREFIX):
                continue
            other_hash_ids[text_hash(str(row.get("text") or ""))].append(cid)
        cross = []
        for cid, h in focus_hashes:
            if h in other_hash_ids:
                cross.append({"chunk_id": cid, "other_n": len(other_hash_ids[h]), "other_sample": other_hash_ids[h][:3]})
        focus = {
            "prefix": FOCUS_PREFIX,
            "n": len(focus_ids),
            "unique_ids": len(set(focus_ids)),
            "cross_volume_same_text_n": len(cross),
            "cross_volume_same_text_ids": [x["chunk_id"] for x in cross[:80]],
            "cross_details_sample": cross[:30],
        }

    return {
        "logical": logical,
        "files": len(paths),
        "source_rows": rows_n,
        "unique_chunk_ids": unique_ids,
        "chunk_id_duplicate_extra_rows": dup_id_rows,
        "chunk_id_keys_with_dupes": dup_id_keys,
        "same_text_rows": same_text_rows,
        "same_text_row_ratio": round(same_text_rows / rows_n, 4) if rows_n else 0,
        "distinct_texts_with_dupes": len(multi_hash),
        "empty_text_n": empty_n,
        "chars_min": min(lengths) if lengths else None,
        "chars_max": max(lengths) if lengths else None,
        "volumes_top20": vol_stats[:20],
        "focus_cwwl_1994_1997_2": focus,
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-root", type=Path, default=None)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    root = resolve_root(args.source_root)
    if root is None:
        print("跳过：找不到源根目录（--source-root 或 QA4_SOURCE_ROOT 或 qa4/data/es_src）")
        return 1
    print(f"source_root={root}")
    report: dict[str, Any] = {"started_at": datetime.now().isoformat(timespec="seconds"), "source_root": str(root), "indices": {}}
    for lg in INDICES:
        paths = jsonl_paths(root, lg)
        if not paths:
            print(f"{lg}: 跳过（无 jsonl）")
            report["indices"][lg] = {"skipped": True}
            continue
        print(f"{lg}: 读 {len(paths)} 文件…")
        info = analyze_index(paths, lg)
        report["indices"][lg] = info
        print(
            f"  rows={info['source_rows']} unique_ids={info['unique_chunk_ids']} "
            f"id_dup_extra={info['chunk_id_duplicate_extra_rows']} "
            f"same_text_rows={info['same_text_rows']} ({info['same_text_row_ratio']}) "
            f"empty={info['empty_text_n']} chars={info['chars_min']}..{info['chars_max']}"
        )
        if info.get("focus_cwwl_1994_1997_2"):
            f = info["focus_cwwl_1994_1997_2"]
            print(
                f"  focus {f['prefix']}: n={f['n']} unique={f['unique_ids']} "
                f"cross_volume_same_text={f['cross_volume_same_text_n']}"
            )

    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out / f"analyze_source_dupes_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OUT={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
