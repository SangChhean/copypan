# -*- coding: utf-8 -*-
"""手动测试 Step 2 + Step 3（四版本生成与机械校验）。"""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

_repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo_root))
load_dotenv(_repo_root / "back_mic" / "backend" / ".env")
load_dotenv(_repo_root / "back_cn" / ".env", override=True)

logging.basicConfig(level=logging.INFO, format="%(message)s")

from back_cn.roundtable.life_text_service import (
    get_messages_by_selection,
    resolve_cross_book_selection,
)
from back_cn.roundtable.prompts import VERSION_CONFIG
from back_cn.roundtable.step1_service import generate_unified_fields
from back_cn.roundtable.step2_service import (
    _check_ratio,
    _collect_paragraphs,
    generate_all_versions,
)


def _heading_count(data: dict) -> int:
    return sum(len(sec.get("subsections", [])) for sec in data.get("sections", []))


def _print_result(key: str, r: dict) -> None:
    cfg = VERSION_CONFIG[key]
    if isinstance(r, Exception) or (isinstance(r, dict) and r.get("error")):
        print(f"\n=== {cfg['label']} ===")
        print("生成失败:", r if isinstance(r, Exception) else r.get("error"))
        return

    print(f"\n=== {r['label']} ===")
    print(
        "字数:",
        r["word_count"],
        f"（要求 {cfg['word_range'][0]}-{cfg['word_range'][1]}）",
    )
    print("尝试次数:", r["attempts"])
    hc = _heading_count(r["data"])
    lo, hi = cfg["heading_range"]
    in_range = lo <= hc <= hi
    print(f"小标题数: {hc}（目标 {lo}-{hi}） 校验={'通过' if in_range else '超标/不足'}")
    if r.get("fallback_stripped"):
        print("摘取兜底: 已生效（删除不合规片段后收尾）")
    if r["retry_log"]:
        print("重试原因:")
        for msg in r["retry_log"]:
            print("  -", msg[:240] + ("…" if len(msg) > 240 else ""))
    print(
        "段落数:",
        sum(
            len(sub["paragraphs"])
            for sec in r["data"]["sections"]
            for sub in sec["subsections"]
        ),
    )
    paras = _collect_paragraphs(r["data"])
    if cfg["ratio"]:
        ok, msg = _check_ratio(paras, cfg["ratio"])
        truth_n = sum(len(p["text"]) for p in paras if p.get("type") == "真理")
        life_n = sum(len(p["text"]) for p in paras if p.get("type") == "生命")
        print(f"比例: 真理{truth_n}:生命{life_n}  校验={'通过' if ok else msg}")
    print(f"原文摘取匹配率: {r.get('verbatim_match_rate')}")
    if r["data"].get("outline"):
        count = len(r["data"]["outline"]["major_points"]) + sum(
            len(mp.get("minor_points", []))
            for mp in r["data"]["outline"]["major_points"]
        )
        print("纲目条数:", count, "（上限 11）")
    print("QA题数:", len(r["data"].get("qa", [])))
    print("--- 小标题列表 ---")
    for sec in r["data"]["sections"]:
        for sub in sec.get("subsections", []):
            print(f"  ◆ {sub.get('heading', '')}")


async def main() -> None:
    import time

    selection = resolve_cross_book_selection(32, 1, 2)
    texts = get_messages_by_selection(selection)
    versions = ["truth", "gospel", "life", "elderly"]

    t0 = time.perf_counter()
    unified = await generate_unified_fields(texts, week_number=None)
    print("统一字段完成，标题:", unified["title"])
    print("出处:", unified["overall_source"])
    print(f"Step1 耗时: {time.perf_counter() - t0:.1f}s")
    print(f"测试参数: selection={selection} versions={versions}")

    t1 = time.perf_counter()
    results = await generate_all_versions(texts, unified, version_keys=versions)
    print(f"\nStep2 总耗时: {time.perf_counter() - t1:.1f}s")
    for key in versions:
        item = results[key]
        if isinstance(item, Exception):
            print(f"\n=== {VERSION_CONFIG[key]['label']} ===")
            print("生成失败:", item)
        else:
            _print_result(key, item)


if __name__ == "__main__":
    asyncio.run(main())
