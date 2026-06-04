import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../back_mic/backend')))

from dotenv import load_dotenv
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../back_mic/backend/.env')))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio, anthropic
from elasticsearch import Elasticsearch
from back_shared.retrieval import bm25_search, dense_search, rrf_merge, rerank
from test_B.AI纲目制作.prompts import STEP5_GENERATION_FLAT

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])

es = Elasticsearch(['http://localhost:9200'], basic_auth=('elastic', 'qwSD4AF2Dcv'))


class QueryRequest(BaseModel):
    query: str
    outline_nature: str = '一般性'
    burden_description: str = ''


def format_chunks(chunks):
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


@app.post('/api/panai2/query')
async def panai2_query(req: QueryRequest):
    bm25_results, dense_results = await asyncio.gather(
        bm25_search(es, req.query, 'ephesians-test', top_k=30),
        dense_search(es, req.query, 'ephesians-test', top_k=30)
    )
    merged = await rrf_merge(bm25_results, dense_results)
    final_results = await rerank(merged, req.query, top_n=20)
    chunks_text = format_chunks(final_results)
    metadata_lines = []
    if req.burden_description.strip():
        metadata_lines.append(f'负担说明：{req.burden_description.strip()}')
    metadata_block = '\n'.join(metadata_lines)
    prompt = STEP5_GENERATION_FLAT.format(
        query=req.query,
        metadata_block=metadata_block,
        chunks=chunks_text
    )
    client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY'))
    message = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=4096,
        messages=[{'role': 'user', 'content': prompt}]
    )
    answer = message.content[0].text
    return {
        'answer': answer,
        'chunks_used': len(final_results),
        'chunks': [
            {
                'chunk_id': c.get('chunk_id', ''),
                'book_title': c.get('book_title', ''),
                'message_number': c.get('message_number', ''),
                'message_title': c.get('message_title', ''),
                'text': c.get('text', '')
            }
            for c in final_results
        ]
    }


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8008, reload=True)
