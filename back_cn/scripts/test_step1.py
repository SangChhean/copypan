# -*- coding: utf-8 -*-
"""手动测试 Step 1 统一字段生成。"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

_repo_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_repo_root))
load_dotenv(_repo_root / "back_mic" / "backend" / ".env")
load_dotenv(_repo_root / "back_cn" / ".env", override=True)

from back_cn.roundtable.life_text_service import get_messages
from back_cn.roundtable.step1_service import (
    compute_topic_and_source,
    generate_unified_fields,
)


def _print_result(label: str, texts: list[dict], result: dict) -> None:
    computed_topic, computed_source = compute_topic_and_source(texts)
    print(f"\n===== {label} =====")
    print("输入篇目:")
    for t in texts:
        print(f"  - {t['book_name']} | {t['title']}")
    print("代码预计算 topic:", computed_topic)
    print("代码预计算 overall_source:", computed_source)
    print("最终 title:", result["title"])
    print("最终 overall_source:", result["overall_source"])
    print(
        "topic 来源:",
        "代码" if computed_topic is not None else "模型合成",
    )
    print("overall_source 来源: 代码")
    print("经文:")
    for v in result["verses"]:
        print(" ", json.dumps(v, ensure_ascii=False))
    print("诗歌:")
    if result["hymn"]:
        h = result["hymn"]
        print(f"  {h['source']} {h['no']} | {h['title']}")
    else:
        print("  None")
    usage = result.get("usage")
    print("usage:", usage)


async def main() -> None:
    # 单篇
    texts1 = get_messages(1, [1])
    r1 = await generate_unified_fields(texts1, week_number="一")
    _print_result("单篇 get_messages(1, [1])", texts1, r1)

    # 多篇
    texts2 = get_messages(49, [15, 16])
    r2 = await generate_unified_fields(texts2, week_number="十五")
    _print_result("多篇 get_messages(49, [15, 16])", texts2, r2)


if __name__ == "__main__":
    asyncio.run(main())
