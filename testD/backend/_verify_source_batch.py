# -*- coding: utf-8 -*-
"""出处批量验证：自动检查拼接与解析。"""
from __future__ import annotations

import asyncio
import json
import re
import sys

from testD.backend import _run_source_batch_test as batch
from testD.backend.source_translator import (
    bracket_has_star,
    format_source_en,
    format_source_zh,
    parse_source_from_line,
    translate_source_zh,
)


def _checks(rows: list[dict]) -> list[str]:
    errs: list[str] = []
    for row in rows:
        n = row["line"]
        final = row["final"]
        if "((" in final or final.count("(") != 1:
            errs.append(f"行{n}: 双层/多层括号: {final[:80]}")
        if re.search(r"Fall Full-[Tt]ime Training|FTTA-Spring|Anaheim Fall", final):
            errs.append(f"行{n}: 训练出处非标准 FTTA 格式: {final[:90]}")
        if n == 14 and ", p. 1" not in final:
            errs.append(f"行{n}: 缺 p. 1: {final}")
        if n == 25 and ", p. 29" not in final:
            errs.append(f"行{n}: 缺 p. 29: {final}")
        if n == 22 and ", p. 18" not in final:
            errs.append(f"行{n}: 缺 p. 18: {final}")
        if row["ref_zh"].count("；") + 1 != row["n_sources"] and "；" in row["ref_zh"]:
            exp = row["ref_zh"].count("；") + 1
            if exp != row["n_sources"]:
                errs.append(f"行{n}: 解析条数 {row['n_sources']} != 中文分号数+1 {exp}")
        if n in (19, 20, 21) and row["n_sources"] != 2:
            errs.append(f"行{n}: 历代志行应解析为2条出处，实际 {row['n_sources']}")
        if "；历代志" in row["ref_zh"] and row["n_sources"] == 1:
            errs.append(f"行{n}: 历代志未切开")
        if final and "; " not in final and row["n_sources"] > 1:
            errs.append(f"行{n}: 多条出处缺少 '; ' 分隔")
    return errs


async def main() -> int:
    rows: list[dict] = []
    for i, line in enumerate(batch._LINES, 1):
        stripped, sources = parse_source_from_line(line)
        ref_zh = format_source_zh(sources)
        has_star = bracket_has_star(ref_zh)
        final = await translate_source_zh(sources, [], has_star=has_star)
        rows.append({
            "line": i,
            "body": stripped,
            "ref_zh": ref_zh,
            "n_sources": len(sources),
            "has_star": has_star,
            "final": final,
        })

    from pathlib import Path
    out = Path(batch.__file__).resolve().parent / "_source_batch_result.json"
    out.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    errs = _checks(rows)
    print(f"共 {len(rows)} 行, 失败 {len(errs)} 项")
    for e in errs:
        print("FAIL:", e)
    if not errs:
        print("ALL PASS")
        for row in rows:
            print(f"行{row['line']}: {row['final']}")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
