# -*- coding: utf-8 -*-
"""全量联网验证：6 个 AI 各写 verify_{ai}.txt"""
import asyncio
import sys
from pathlib import Path

# 确保 backend 在 path 中
backend = Path(__file__).resolve().parent
sys.path.insert(0, str(backend))

from roundtable.ai_clients import call_ai

QUESTION = "请搜索2025年最新的因信称义神学研究，介绍一个具体的最新观点或论文，说明其主要论点。"
SYSTEM = "你是神学研究助手，请积极联网搜索最新资料。"
AIS = ["claude", "gpt", "gemini", "grok", "deepseek", "perplexity"]


async def test():
    for ai in AIS:
        print(f"Testing {ai}...")
        try:
            result = await call_ai(ai, QUESTION, SYSTEM)
            out_path = backend / f"verify_{ai}.txt"
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(result)
            print(f"{ai}: OK - {len(result)} chars")
        except Exception as e:
            print(f"{ai}: ERROR - {e}")


if __name__ == "__main__":
    asyncio.run(test())
