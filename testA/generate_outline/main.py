# -*- coding: utf-8 -*-
import sys
import os
import asyncio
import logging

# 路径设置：加入仓库根目录和 back_mic/backend/
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'back_mic', 'backend')))

# 加载 .env
from dotenv import load_dotenv
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'back_mic', 'backend', '.env')))

import anthropic
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from elasticsearch import Elasticsearch

from back_shared.retrieval import bm25_search, dense_search, rrf_merge, rerank
from testA.generate_outline.prompts import STEP5_GENERATION_FLAT

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("generate_outline")

# ES 连接
es = Elasticsearch(
    ['http://localhost:9200'],
    basic_auth=('elastic', 'qwSD4AF2Dcv')
)

# FastAPI app
app = FastAPI(title="PanAI 2.0 - Generate Outline")

# CORS（必须在路由之前）
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

# 请求体
class QueryRequest(BaseModel):
    query: str
    outline_nature: str = '一般性'
    burden_description: str = ''
    audience: str = ''

# format_chunks 函数
def format_chunks(chunks: list) -> str:
    out = []
    for c in chunks:
        chunk_id  = c.get('chunk_id', '')
        book      = c.get('book_title', '')
        msg       = c.get('message_number', '')
        msg_title = c.get('message_title', '')
        text      = c.get('text', '')
        line1 = f'[{chunk_id}] {book}'
        if msg:
            line1 += f' 第{msg}篇'
        if msg_title:
            line1 += f' {msg_title}'
        out.append(line1)
        out.append(text.strip())
        out.append('---')
    return '\n'.join(out)

# 主接口
@app.post('/api/testa/generate_outline/query')
async def generate_outline(req: QueryRequest):
    logger.info(f"收到请求：query={req.query}")

    # 第一步：并发 BM25 + Dense 检索
    bm25_results, dense_results = await asyncio.gather(
        bm25_search(es, req.query, 'galatians', top_k=30),
        dense_search(es, req.query, 'galatians', top_k=30),
    )
    logger.info(f"BM25: {len(bm25_results)} 条，Dense: {len(dense_results)} 条")

    # 第二步：RRF 融合（直接传入两路，由 RRF 处理重叠）
    merged = await rrf_merge(bm25_results, dense_results)
    logger.info(f"RRF 融合后：{len(merged)} 条")

    # 第三步：Rerank 精排 top20
    final_results = await rerank(merged, req.query, top_n=20)
    logger.info(f"Rerank 后：{len(final_results)} 条")

    # 第四步：格式化 chunks
    chunks_text = format_chunks(final_results)

    # 第五步：构建 metadata_block
    metadata_lines = []
    if req.audience.strip():
        metadata_lines.append(f'面对对象：{req.audience.strip()}')
    if req.burden_description.strip():
        metadata_lines.append(f'负担说明：{req.burden_description.strip()}')
    metadata_block = '\n'.join(metadata_lines)

    # 第六步：拼 Prompt
    prompt = STEP5_GENERATION_FLAT.format(
        query=req.query,
        metadata_block=metadata_block,
        chunks=chunks_text,
    )

    # 第七步：调 Claude Sonnet
    client = anthropic.Anthropic(api_key=os.environ.get('CLAUDE_API_KEY'))
    message = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=4096,
        messages=[{'role': 'user', 'content': prompt}],
    )
    answer = message.content[0].text
    logger.info("Claude 生成完成")

    return {
        'answer': answer,
        'chunks_used': len(final_results),
        'chunks': [
            {
                'chunk_id': c.get('chunk_id', ''),
                'book_title': c.get('book_title', ''),
                'message_number': c.get('message_number', ''),
                'message_title': c.get('message_title', ''),
                'text': c.get('text', ''),
            }
            for c in final_results
        ],
    }

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('testA.generate_outline.main:app', host='0.0.0.0', port=8007, reload=True)
