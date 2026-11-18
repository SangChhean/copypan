# -*- coding: utf-8 -*-
"""只读：分析 text_* 源 jsonl 的 chunk_id 段号断档（不连 ES、不读密钥）。

用法：
  python qa4/backend/tools/check_text_life_gaps.py \\
    --source-text-life <dir-or-jsonl> \\
    [--source-text-cwwl ...] [--source-text-cwwn ...] [--source-text-others ...] \\
    --out G:\\PanAI4.0专用\\logs\\stage2

源目录可为：
  - panai4_text_life/（内含 shards/*.jsonl）
  - 直接指向 shards/
  - 单个 .jsonl（如 kg-rag_life.jsonl）
默认：环境变量 QA4_SOURCE_TEXT_LIFE 或 qa4/data/es_src/panai4_text_life（找不到则跳过并说明）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Iterator, Optional

_BACKEND = Path(__file__).resolve().parents[1]
_QA4 = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_TRAIL = re.compile(r"(\d+)(?!.*\d)")
DEFAULT_OUT = Path(r"G:\PanAI4.0专用\logs\stage2")
SAMPLE_LIFE = ("life_49-1", "life_17-1", "life_45-1", "life_43-1")  # 弗/斯/罗/约 第1篇


def _env_path(name: str) -> Optional[Path]:
    v = (os.environ.get(name) or "").strip()
    return Path(v) if v else None


def resolve_jsonl_paths(src: Optional[Path]) -> list[Path]:
    if src is None:
        return []
    src = Path(src)
    if not src.exists():
        return []
    if src.is_file() and src.suffix.lower() == ".jsonl":
        return [src]
    shards = src / "shards"
    if shards.is_dir():
        return sorted(shards.glob("*.jsonl"))
    if src.is_dir():
        found = sorted(src.glob("**/*.jsonl"))
        return found
    return []


def iter_rows(paths: Iterable[Path]) -> Iterator[dict[str, Any]]:
    for p in paths:
        with p.open(encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)


def trailing_int(cid: str) -> Optional[int]:
    m = _TRAIL.search(cid or "")
    return int(m.group(1)) if m else None


def message_key_of(row: dict[str, Any], logical: str) -> str:
    mk = row.get("message_key")
    if mk:
        return str(mk)
    cid = str(row.get("chunk_id") or "")
    if logical == "text_life" and cid.startswith("life_"):
        parts = cid.split("-")
        if len(parts) >= 3:
            return "-".join(parts[:-1])
    if "#" in cid:
        # cwwl_…#章-段 → 去掉末段
        left, right = cid.rsplit("#", 1)
        rp = right.rsplit("-", 1)
        return left + "#" + (rp[0] if len(rp) == 2 else right)
    # others / fallback：去掉末尾 -N
    if "-" in cid:
        return cid.rsplit("-", 1)[0]
    return cid


def analyze_index(paths: list[Path], logical: str, sample_keys: tuple[str, ...] = ()) -> dict[str, Any]:
    by_msg: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in iter_rows(paths):
        cid = str(row.get("chunk_id") or "")
        if not cid:
            continue
        mk = message_key_of(row, logical)
        n = trailing_int(cid)
        if n is None:
            continue
        by_msg[mk].append(
            {
                "chunk_id": cid,
                "n": n,
                "chars": len(str(row.get("text") or "")),
                "original_ids": list(row.get("original_ids") or []),
                "paragraph_type": row.get("paragraph_type"),
                "source_zh": row.get("source_zh"),
            }
        )

    gap_counts: list[int] = []
    with_gaps = 0
    for mk, docs in by_msg.items():
        nums = sorted({d["n"] for d in docs})
        if not nums:
            continue
        gaps = set(range(nums[0], nums[-1] + 1)) - set(nums)
        gap_counts.append(len(gaps))
        if gaps:
            with_gaps += 1

    hist = Counter(gap_counts)
    # 分布桶
    buckets = {"0": 0, "1-5": 0, "6-20": 0, "21-50": 0, "51+": 0}
    for g in gap_counts:
        if g == 0:
            buckets["0"] += 1
        elif g <= 5:
            buckets["1-5"] += 1
        elif g <= 20:
            buckets["6-20"] += 1
        elif g <= 50:
            buckets["21-50"] += 1
        else:
            buckets["51+"] += 1

    samples: dict[str, Any] = {}
    keys = list(sample_keys) if sample_keys else sorted(by_msg.keys())[:5]
    for mk in keys:
        docs = by_msg.get(mk) or []
        if not docs and sample_keys:
            samples[mk] = {"missing_in_source": True}
            continue
        nums = sorted(d["n"] for d in docs)
        covered = set()
        for d in docs:
            for oid in d["original_ids"]:
                t = trailing_int(str(oid))
                if t is not None:
                    covered.add(t)
        gaps = sorted(set(range(nums[0], nums[-1] + 1)) - set(nums)) if nums else []
        in_orig = [g for g in gaps if g in covered]
        nowhere = [g for g in gaps if g not in covered]
        samples[mk] = {
            "fetched": len(docs),
            "min": nums[0] if nums else None,
            "max": nums[-1] if nums else None,
            "orders": nums,
            "gap_count": len(gaps),
            "gaps": gaps,
            "gaps_in_original_ids": in_orig,
            "gaps_absent_from_source": nowhere,
            "segments": [{"n": d["n"], "chunk_id": d["chunk_id"], "chars": d["chars"]} for d in sorted(docs, key=lambda x: x["n"])],
            "paragraph_types": sorted({str(d.get("paragraph_type")) for d in docs}),
            "merge_rows": sum(1 for d in docs if len(d["original_ids"]) > 1),
        }

    return {
        "logical": logical,
        "files": len(paths),
        "messages": len(by_msg),
        "chunks": sum(len(v) for v in by_msg.values()),
        "messages_with_gaps": with_gaps,
        "gap_bucket_counts": buckets,
        "gap_count_hist_top": hist.most_common(15),
        "samples": samples,
    }


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source-text-life", type=Path, default=_env_path("QA4_SOURCE_TEXT_LIFE") or (_QA4 / "data" / "es_src" / "panai4_text_life"))
    ap.add_argument("--source-text-cwwl", type=Path, default=_env_path("QA4_SOURCE_TEXT_CWWL") or (_QA4 / "data" / "es_src" / "panai4_text_cwwl"))
    ap.add_argument("--source-text-cwwn", type=Path, default=_env_path("QA4_SOURCE_TEXT_CWWN") or (_QA4 / "data" / "es_src" / "panai4_text_cwwn"))
    ap.add_argument("--source-text-others", type=Path, default=_env_path("QA4_SOURCE_TEXT_OTHERS") or (_QA4 / "data" / "es_src" / "panai4_text_others"))
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    report: dict[str, Any] = {"started_at": datetime.now().isoformat(timespec="seconds"), "indices": {}}

    life_paths = resolve_jsonl_paths(args.source_text_life)
    if not life_paths:
        print(f"跳过 text_life：找不到源（试过 {args.source_text_life}；可用 --source-text-life 或 QA4_SOURCE_TEXT_LIFE）")
        report["indices"]["text_life"] = {"skipped": str(args.source_text_life)}
    else:
        print(f"text_life 源文件 {len(life_paths)} 个 ← {args.source_text_life}")
        life = analyze_index(life_paths, "text_life", SAMPLE_LIFE)
        report["indices"]["text_life"] = life
        print(
            f"  篇数 {life['messages']}；有断档 {life['messages_with_gaps']}；"
            f"断档分布 {life['gap_bucket_counts']}"
        )
        for mk, s in life["samples"].items():
            if s.get("missing_in_source"):
                print(f"  样例 {mk}: 源中无此篇")
                continue
            print(
                f"  样例 {mk}: n={s['fetched']} min..max={s['min']}..{s['max']} "
                f"gaps={s['gap_count']} in_orig={len(s['gaps_in_original_ids'])} "
                f"absent={len(s['gaps_absent_from_source'])} merges={s['merge_rows']}"
            )

    for logical, arg in (
        ("text_cwwl", args.source_text_cwwl),
        ("text_cwwn", args.source_text_cwwn),
        ("text_others", args.source_text_others),
    ):
        paths = resolve_jsonl_paths(arg)
        if not paths:
            print(f"跳过 {logical}：找不到源（{arg}）")
            report["indices"][logical] = {"skipped": str(arg)}
            continue
        # 各抽 5 篇：取出现最多的前 5 个 message_key 太慢；先扫一遍只记 key 计数再详析
        print(f"{logical} 源文件 {len(paths)} 个；抽 5 篇…")
        counts: Counter[str] = Counter()
        for row in iter_rows(paths):
            cid = str(row.get("chunk_id") or "")
            if cid:
                counts[message_key_of(row, logical)] += 1
        top5 = [k for k, _ in counts.most_common(5)]
        # 再扫一次只收这 5 篇
        by: dict[str, list] = defaultdict(list)
        want = set(top5)
        for row in iter_rows(paths):
            mk = message_key_of(row, logical)
            if mk not in want:
                continue
            by[mk].append(row)
        # 复用 analyze：写临时结构
        fake_paths_note = {"files": len(paths), "sample_keys": top5}
        samples = {}
        with_gaps = 0
        for mk in top5:
            docs_raw = by.get(mk) or []
            docs = []
            for row in docs_raw:
                cid = str(row.get("chunk_id") or "")
                n = trailing_int(cid)
                if n is None:
                    continue
                docs.append(
                    {
                        "chunk_id": cid,
                        "n": n,
                        "chars": len(str(row.get("text") or "")),
                        "original_ids": list(row.get("original_ids") or []),
                        "paragraph_type": row.get("paragraph_type"),
                    }
                )
            nums = sorted(d["n"] for d in docs)
            covered = set()
            for d in docs:
                for oid in d["original_ids"]:
                    t = trailing_int(str(oid))
                    if t is not None:
                        covered.add(t)
            gaps = sorted(set(range(nums[0], nums[-1] + 1)) - set(nums)) if nums else []
            if gaps:
                with_gaps += 1
            samples[mk] = {
                "fetched": len(docs),
                "min": nums[0] if nums else None,
                "max": nums[-1] if nums else None,
                "orders": nums,
                "gap_count": len(gaps),
                "gaps": gaps,
                "gaps_in_original_ids": [g for g in gaps if g in covered],
                "gaps_absent_from_source": [g for g in gaps if g not in covered],
                "segments": [{"n": d["n"], "chunk_id": d["chunk_id"], "chars": d["chars"]} for d in sorted(docs, key=lambda x: x["n"])],
                "merge_rows": sum(1 for d in docs if len(d["original_ids"]) > 1),
            }
            print(
                f"  {mk}: n={len(docs)} gaps={len(gaps)} "
                f"in_orig={len(samples[mk]['gaps_in_original_ids'])} "
                f"absent={len(samples[mk]['gaps_absent_from_source'])}"
            )
        report["indices"][logical] = {
            **fake_paths_note,
            "messages_sampled": len(top5),
            "messages_with_gaps_in_sample": with_gaps,
            "samples": samples,
        }

    args.out.mkdir(parents=True, exist_ok=True)
    out = args.out / f"check_text_life_gaps_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"OUT={out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
