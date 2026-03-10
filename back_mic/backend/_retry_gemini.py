# -*- coding: utf-8 -*-
import asyncio
from roundtable.ai_clients import call_ai

QUESTION = '请搜索2025年最新的因信称义神学研究，介绍一个具体的最新观点或论文，说明其主要论点。'
SYSTEM = '你是神学研究助手，请积极联网搜索最新资料。'

async def test():
    result = await call_ai('gemini', QUESTION, SYSTEM)
    with open('verify_gemini.txt', 'w', encoding='utf-8') as f:
        f.write(result)
    print(f'gemini: OK - {len(result)} chars')

if __name__ == '__main__':
    asyncio.run(test())
