import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../back_mic/backend')))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../back_shared')))
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../back_mic/backend/.env')))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio, anthropic, json
from elasticsearch import Elasticsearch
from back_shared.retrieval import bm25_search, dense_search, rrf_merge, rerank
from utils import (
    _parse_step1_layers, _parse_json_array, _apply_outline_nature_weight,
    _parse_burden_generation_output,
    _parse_step2_skeleton, _build_skeleton_bound_prompt_block,
    _format_paths_text, _format_key_verses_text, _format_chunk_line
)
from prompts import (
    STEP5_GENERATION_FLAT, STEP1_CONCEPT_EXTRACTION,
    QUERY_REWRITE, QUERY_REWRITE_SYSTEM,
    BURDEN_DESCRIPTION_PROMPT, BURDEN_DESCRIPTION_SYSTEM,
    STEP2_SKELETON_BUILD, STEP5_GENERATION
)
from neo4j_client import Neo4jClient
from kg_rag.retrieval import skeleton_route_search

INDICES = ','.join([
    'kg-rag_life',
    'kg-rag_cwwl',
    'kg-rag_cwwn',
    'kg-rag_others',
    'kg-rag_bib',
    'kg-rag_map_note',
    'kg-rag_7feasts',
])

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])

es = Elasticsearch(['http://localhost:9200'], basic_auth=('elastic', 'qwSD4AF2Dcv'))

# Neo4j：构造器读取环境变量（NEO4J_URI/USER/PASSWORD），需先 startup() 才能取概念名
os.environ.setdefault('NEO4J_URI', 'bolt://localhost:7687')
os.environ.setdefault('NEO4J_USER', 'neo4j')
os.environ.setdefault('NEO4J_PASSWORD', 'KgRag2026')
neo4j_client = Neo4jClient()
neo4j_client.startup()
concept_names = neo4j_client.get_concept_names()
concept_list_text = '、'.join(concept_names)


async def call_claude(prompt: str, system: str | None = None, max_tokens: int = 4096,
                      temperature: float | None = None,
                      model: str = 'claude-sonnet-4-6') -> str:
    """调用 Claude，放线程池执行避免阻塞事件循环；支持可选 system、temperature。"""
    def _run() -> str:
        client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY') or os.getenv('CLAUDE_API_KEY'))
        kwargs = {
            'model': model,
            'max_tokens': max_tokens,
            'messages': [{'role': 'user', 'content': prompt}],
        }
        if system:
            kwargs['system'] = system
        if temperature is not None:
            kwargs['temperature'] = temperature
        message = client.messages.create(**kwargs)
        return message.content[0].text
    return await asyncio.to_thread(_run)


class QueryRequest(BaseModel):
    query: str
    outline_nature: str = '一般性'
    burden_description: str = ''
    audience: str = ''
    expanded_nodes: list[str] = []
    rewritten_queries: list[str] = []


class AnalyzeRequest(BaseModel):
    query: str
    outline_nature: str = '一般性'
    burden_description: str = ''


class BurdenRequest(BaseModel):
    query: str
    outline_nature: str = ''
    audience: str = ''
    reference_excerpt: str = ''


async def run_step1_and_rewrite(query: str, outline_nature: str, burden_description: str):
    """并发执行 Step1 概念抽取 + Query Rewrite，返回解析后的结果。"""
    burden_line = f'信息负担说明：{burden_description}' if burden_description else ''
    step1_prompt = STEP1_CONCEPT_EXTRACTION.format(
        query=query,
        outline_nature=outline_nature,
        burden_line=burden_line,
        concept_list=concept_list_text,
    )
    rewrite_input = query
    if burden_description:
        rewrite_input += f'\n负担方向：{burden_description}'
    rewrite_prompt = QUERY_REWRITE.format(query=rewrite_input)

    step1_raw, rewrite_raw = await asyncio.gather(
        call_claude(step1_prompt),
        call_claude(rewrite_prompt, system=QUERY_REWRITE_SYSTEM),
    )

    revelation, experience, practice, reasoning = _parse_step1_layers(step1_raw, outline_nature)
    rewritten_queries = _parse_json_array(rewrite_raw)
    if not rewritten_queries:
        rewritten_queries = []
    expanded_nodes = list(dict.fromkeys(revelation + experience + practice))
    return revelation, experience, practice, reasoning, rewritten_queries, expanded_nodes


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


@app.post('/api/panai2/step1')
async def test_step1(query: str, outline_nature: str = '一般性'):
    prompt = STEP1_CONCEPT_EXTRACTION.format(
        query=query,
        outline_nature=outline_nature,
        burden_line='',
        concept_list=concept_list_text,
    )
    raw = await call_claude(prompt)
    revelation, experience, practice, reasoning = _parse_step1_layers(raw, outline_nature)
    return {
        'revelation': revelation,
        'experience': experience,
        'practice': practice,
        'reasoning': reasoning,
    }


@app.post('/api/panai2/analyze')
async def panai2_analyze(req: AnalyzeRequest):
    revelation, experience, practice, reasoning, rewritten_queries, expanded_nodes = \
        await run_step1_and_rewrite(req.query, req.outline_nature, req.burden_description)
    return {
        'concepts': {
            'revelation': revelation,
            'experience': experience,
            'practice': practice,
            'reasoning': reasoning,
        },
        'rewritten_queries': rewritten_queries,
        'expanded_nodes': expanded_nodes,
    }


@app.post('/api/panai2/generate_burden')
async def generate_burden(req: BurdenRequest):
    prompt = BURDEN_DESCRIPTION_PROMPT.format(
        query=req.query,
        outline_nature=req.outline_nature or '（未填）',
        audience=req.audience or '（未填）',
        reference_excerpt=req.reference_excerpt or '（空）',
    )
    raw = await call_claude(prompt, system=BURDEN_DESCRIPTION_SYSTEM, temperature=0.3, max_tokens=1200)
    result = _parse_burden_generation_output(raw)
    return result


@app.post('/api/panai2/query')
async def panai2_query(req: QueryRequest):
    if req.expanded_nodes:
        # 用传入的概念词和改写句，跳过 Step1 + Query Rewrite
        expanded_nodes = req.expanded_nodes
        rewritten_queries = req.rewritten_queries or []
        revelation, experience, practice = [], [], []
        reasoning = ''
    else:
        # 原有逻辑：并发跑 Step1 + Query Rewrite
        revelation, experience, practice, reasoning, rewritten_queries, expanded_nodes = \
            await run_step1_and_rewrite(req.query, req.outline_nature, req.burden_description)

    # Step2：骨架构建
    skeleton = None
    deep = []
    if expanded_nodes:
        # Neo4j 查询（字段映射：rel → relation）
        paths_raw = neo4j_client.get_concept_relations(expanded_nodes)
        paths = [{"from": p["from"], "relation": p["rel"], "to": p["to"]} for p in paths_raw]
        key_verses_raw = neo4j_client.get_key_verses(revelation + experience + practice)

        # 构建 deep 列表（顺序固定：revelation + experience + practice，不去重）
        deep = revelation + experience + practice

        # 构建 Step2 Prompt
        bd = (req.burden_description or '').strip()
        intrinsic_burden_text = bd if bd else '（未填写负担说明）'
        step2_prompt = STEP2_SKELETON_BUILD.format(
            query=req.query,
            outline_nature=req.outline_nature,
            intrinsic_burden_text=intrinsic_burden_text,
            revelation_json=json.dumps(revelation, ensure_ascii=False),
            experience_json=json.dumps(experience, ensure_ascii=False),
            practice_json=json.dumps(practice, ensure_ascii=False),
            paths_text=_format_paths_text(paths),
            key_verses_text=_format_key_verses_text(key_verses_raw),
        )

        # 调 Claude 生成骨架
        step2_raw = await call_claude(step2_prompt, temperature=0, max_tokens=2048)
        skeleton = _parse_step2_skeleton(step2_raw)

    # Dense 检索用原始 query + 四个改写句（共最多5路）
    dense_query_list = [req.query] + rewritten_queries[:4]

    # 路1：BM25（原始 query）
    bm25_task = bm25_search(es, req.query, INDICES, top_k=30)

    # 路2：Dense 多路（原始 query + 四个改写句，共最多5路）
    dense_tasks = [
        dense_search(es, rq, INDICES, top_k=10)
        for rq in dense_query_list
    ]

    # 路3：每个概念词跑一次 skeleton_route_search（全部并发）
    route3_tasks = [
        skeleton_route_search(es, node, req.query, INDICES, top_k=5, outline_nature=req.outline_nature)
        for node in expanded_nodes
    ]

    # 全部并发执行
    all_results = await asyncio.gather(
        bm25_task, *dense_tasks, *route3_tasks
    )

    # 拆分结果
    bm25_results = all_results[0]
    dense_results_list = all_results[1:1 + len(dense_tasks)]
    route3_results_list = all_results[1 + len(dense_tasks):]

    # 合并所有 Dense 结果
    dense_combined = []
    for dr in dense_results_list:
        dense_combined.extend(dr)

    # BM25 + Dense 合并做 RRF，得到 main_results
    merged = await rrf_merge(bm25_results, dense_combined)
    weighted = _apply_outline_nature_weight(merged, req.outline_nature)
    reranked = await rerank(weighted, req.query, top_n=20)
    main_results = reranked
    for doc in main_results:
        doc['source'] = 'main'
        doc['expanded_from'] = ''

    # 路3结果合并去重（chunk_id 不在 main_results 里才加入）
    main_ids = {r['chunk_id'] for r in main_results}
    expanded_results = []
    seen_ids = set(main_ids)
    for batch in route3_results_list:
        for doc in batch:
            if doc['chunk_id'] not in seen_ids:
                seen_ids.add(doc['chunk_id'])
                doc['expanded_from'] = doc.get('expanded_from', '')
                doc['source'] = 'skeleton_route'
                expanded_results.append(doc)

    # 最终 chunks = main_results + expanded_results
    final_results = main_results + expanded_results
    metadata_lines = []
    if req.burden_description.strip():
        metadata_lines.append(f'负担说明：{req.burden_description.strip()}')
    metadata_block = '\n'.join(metadata_lines)

    # 有骨架走 STEP5_GENERATION（骨架绑定段落），无骨架退回 STEP5_GENERATION_FLAT
    if skeleton:
        skeleton_with_chunks = _build_skeleton_bound_prompt_block(
            skeleton, expanded_results, deep, main_results
        )
        prompt = STEP5_GENERATION.format(
            query=req.query,
            metadata_block=metadata_block,
            skeleton_with_chunks=skeleton_with_chunks,
        )
    else:
        all_chunks = main_results + expanded_results
        chunks_text = format_chunks(all_chunks)
        prompt = STEP5_GENERATION_FLAT.format(
            query=req.query,
            metadata_block=metadata_block,
            chunks=chunks_text,
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
        'concepts': {
            'revelation': revelation,
            'experience': experience,
            'practice': practice,
        },
        'rewritten_queries': rewritten_queries,
        'expanded_nodes_count': len(expanded_nodes),
        'expanded_results_count': len(expanded_results),
        'has_skeleton': skeleton is not None,
        'skeleton_steps': len(skeleton) if skeleton else 0,
        'skeleton_preview': [s.get('step', '') for s in skeleton] if skeleton else [],
        'chunks': [
            {
                'chunk_id': c.get('chunk_id', ''),
                'book_title': c.get('book_title', ''),
                'message_number': c.get('message_number', ''),
                'message_title': c.get('message_title', ''),
                'text': c.get('text', ''),
                'source': c.get('source', 'main'),
                'expanded_from': c.get('expanded_from', '')
            }
            for c in final_results
        ]
    }


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='0.0.0.0', port=8008, reload=True)
