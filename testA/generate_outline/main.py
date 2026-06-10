# -*- coding: utf-8 -*-
import sys
import os
import asyncio
import json
import logging

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'back_mic', 'backend')))

from dotenv import load_dotenv
load_dotenv(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'back_mic', 'backend', '.env')))

import anthropic
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from elasticsearch import Elasticsearch

from back_shared.retrieval import bm25_search, dense_search, rrf_merge, rerank
from back_shared.neo4j_client import Neo4jClient
from back_mic.backend.kg_rag.retrieval import skeleton_route_search

from testA.generate_outline.prompts import (
    STEP5_GENERATION_FLAT,
    STEP1_CONCEPT_EXTRACTION,
    QUERY_REWRITE,
    QUERY_REWRITE_SYSTEM,
    BURDEN_DESCRIPTION_PROMPT,
    BURDEN_DESCRIPTION_SYSTEM,
    STEP2_SKELETON_BUILD,
    STEP5_GENERATION,
)
from testA.generate_outline.outline_utils import (
    _parse_step1_layers,
    _parse_json_array,
    _apply_outline_nature_weight,
    _parse_burden_generation_output,
    _parse_step2_skeleton,
    _build_skeleton_bound_prompt_block,
    _format_paths_text,
    _format_key_verses_text,
    _format_chunk_line,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('generate_outline')

INDEX_20 = 'galatians'
INDICES_35 = ','.join([
    'kg-rag_life', 'kg-rag_cwwl', 'kg-rag_cwwn',
    'kg-rag_others', 'kg-rag_bib', 'kg-rag_map_note', 'kg-rag_7feasts',
])

es = Elasticsearch(
    ['http://localhost:9200'],
    basic_auth=('elastic', 'qwSD4AF2Dcv')
)

neo4j_client = Neo4jClient()
concept_list_text: str = ''

app = FastAPI(title='PanAI Generate Outline')
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_methods=['*'],
    allow_headers=['*'],
)

@app.on_event('startup')
async def startup():
    global concept_list_text
    neo4j_client.startup()
    names = neo4j_client.get_concept_names()
    concept_list_text = '、'.join(names)
    logger.info(f'Neo4j 概念数：{len(names)}，concept_list_text 长度：{len(concept_list_text)}')

@app.on_event('shutdown')
async def shutdown():
    neo4j_client.shutdown()

async def call_claude(prompt: str, system: str = None, max_tokens: int = 4096, temperature: float = 1.0) -> str:
    def _sync():
        client = anthropic.Anthropic(api_key=os.environ.get('CLAUDE_API_KEY'))
        kwargs = dict(
            model='claude-sonnet-4-6',
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[{'role': 'user', 'content': prompt}],
        )
        if system:
            kwargs['system'] = system
        msg = client.messages.create(**kwargs)
        return msg.content[0].text or ''
    return await asyncio.to_thread(_sync)

class QueryRequest(BaseModel):
    query: str
    outline_nature: str = '一般性'
    burden_description: str = ''
    audience: str = ''

class Query35Request(BaseModel):
    query: str
    outline_nature: str = '一般性'
    burden_description: str = ''
    audience: str = ''
    preset_revelation: list[str] = []
    preset_experience: list[str] = []
    preset_practice: list[str] = []

class BurdenRequest(BaseModel):
    query: str
    outline_nature: str = ''
    audience: str = ''
    reference_excerpt: str = ''

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

def chunk_to_dict(c: dict) -> dict:
    return {
        'chunk_id':       c.get('chunk_id', ''),
        'book_title':     c.get('book_title', ''),
        'message_number': c.get('message_number', ''),
        'message_title':  c.get('message_title', ''),
        'text':           c.get('text', ''),
        'source':         c.get('source', ''),
        'expanded_from':  c.get('expanded_from', ''),
    }

# ── PanAI 2.0 ────────────────────────────────────────────
@app.post('/api/testa/generate_outline/query')
async def generate_outline(req: QueryRequest):
    logger.info(f'[2.0] query={req.query}')
    bm25_results, dense_results = await asyncio.gather(
        bm25_search(es, req.query, INDEX_20, top_k=30),
        dense_search(es, req.query, INDEX_20, top_k=30),
    )
    merged = await rrf_merge(bm25_results, dense_results)
    final_results = await rerank(merged, req.query, top_n=20)
    chunks_text = format_chunks(final_results)
    metadata_lines = []
    if req.audience.strip():
        metadata_lines.append(f'面对对象：{req.audience.strip()}')
    if req.burden_description.strip():
        metadata_lines.append(f'负担说明：{req.burden_description.strip()}')
    metadata_block = '\n'.join(metadata_lines)
    prompt = STEP5_GENERATION_FLAT.format(
        query=req.query,
        metadata_block=metadata_block,
        chunks=chunks_text,
    )
    answer = await call_claude(prompt)
    logger.info('[2.0] 生成完成')
    return {
        'answer': answer,
        'chunks_used': len(final_results),
        'chunks': [chunk_to_dict(c) for c in final_results],
    }

# ── Step1 单独测试 ────────────────────────────────────────
@app.post('/api/testa/generate_outline/step1')
async def extract_concepts(req: QueryRequest):
    if not concept_list_text:
        return {'error': 'Neo4j 未连接或概念列表为空'}
    burden_line = f'信息负担说明：{req.burden_description}' if req.burden_description.strip() else ''
    prompt = STEP1_CONCEPT_EXTRACTION.format(
        query=req.query,
        outline_nature=req.outline_nature,
        burden_line=burden_line,
        concept_list=concept_list_text,
    )
    raw = await call_claude(prompt, system=None, max_tokens=2000)
    revelation, experience, practice, reasoning = _parse_step1_layers(raw, req.outline_nature)
    return {
        'revelation': revelation,
        'experience': experience,
        'practice': practice,
        'reasoning': reasoning,
    }

# ── 负担说明生成 ──────────────────────────────────────────
@app.post('/api/testa/generate_outline/generate_burden')
async def generate_burden(req: BurdenRequest):
    logger.info(f'[burden] query={req.query}')
    prompt = BURDEN_DESCRIPTION_PROMPT.format(
        query=req.query,
        outline_nature=req.outline_nature or '（未填）',
        audience=req.audience or '（未填）',
        reference_excerpt=req.reference_excerpt or '（空）',
    )
    raw = await call_claude(
        prompt,
        system=BURDEN_DESCRIPTION_SYSTEM,
        max_tokens=1200,
        temperature=0.3,
    )
    result = _parse_burden_generation_output(raw)
    return result

# ── PanAI 3.5 ────────────────────────────────────────────
@app.post('/api/testa/generate_outline/query35')
async def generate_outline_35(req: Query35Request):
    logger.info(f'[3.5] query={req.query}')

    # ── Step1 + Query Rewrite 并发 ────────────────────────
    use_preset = bool(req.preset_revelation or req.preset_experience or req.preset_practice)
    if use_preset:
        revelation = req.preset_revelation
        experience = req.preset_experience
        practice   = req.preset_practice
        rewritten_queries = [req.query]
        logger.info('[3.5] 使用预设概念，跳过 Step1')
    else:
        burden_line = f'信息负担说明：{req.burden_description}' if req.burden_description.strip() else ''
        step1_prompt = STEP1_CONCEPT_EXTRACTION.format(
            query=req.query,
            outline_nature=req.outline_nature,
            burden_line=burden_line,
            concept_list=concept_list_text,
        )
        rewrite_query = req.query
        if req.burden_description.strip():
            rewrite_query += f'，负担方向：{req.burden_description.strip()}'
        rewrite_prompt = QUERY_REWRITE.format(query=rewrite_query)
        step1_raw, rewrite_raw = await asyncio.gather(
            call_claude(step1_prompt, system=None, max_tokens=2000),
            call_claude(rewrite_prompt, system=QUERY_REWRITE_SYSTEM, max_tokens=500),
        )
        revelation, experience, practice, _ = _parse_step1_layers(step1_raw, req.outline_nature)
        rewritten_queries = _parse_json_array(rewrite_raw) or [req.query]

    expanded_nodes = list(dict.fromkeys(revelation + experience + practice))
    logger.info(f'[3.5] expanded_nodes={expanded_nodes}')
    logger.info(f'[3.5] rewritten_queries={rewritten_queries}')

    # ── Step2 骨架构建 ────────────────────────────────────
    if not expanded_nodes:
        skeleton = None
        deep = []
    else:
        raw_relations = neo4j_client.get_concept_relations(expanded_nodes)
        paths = [
            {"from": r["from"], "relation": r["rel"], "to": r["to"], "hops": 1}
            for r in raw_relations
        ]
        key_verses = neo4j_client.get_key_verses(revelation + experience + practice)
        deep = revelation + experience + practice
        step2_prompt = STEP2_SKELETON_BUILD.format(
            query=req.query,
            outline_nature=req.outline_nature,
            intrinsic_burden_text=req.burden_description or '（未填写负担说明）',
            revelation_json=json.dumps(revelation, ensure_ascii=False),
            experience_json=json.dumps(experience, ensure_ascii=False),
            practice_json=json.dumps(practice, ensure_ascii=False),
            paths_text=_format_paths_text(paths),
            key_verses_text=_format_key_verses_text(key_verses),
        )
        raw_skeleton = await call_claude(step2_prompt, system=None, max_tokens=2048, temperature=0)
        skeleton = _parse_step2_skeleton(raw_skeleton)
    logger.info(f'[3.5] has_skeleton={skeleton is not None}, steps={len(skeleton) if skeleton else 0}')

    # ── 三路并发检索 ──────────────────────────────────────
    dense_query_list = [req.query] + rewritten_queries[:4]
    bm25_task    = bm25_search(es, req.query, INDICES_35, top_k=30)
    dense_tasks  = [dense_search(es, q, INDICES_35, top_k=10) for q in dense_query_list]
    route3_tasks = [
        skeleton_route_search(es, node, req.query, INDICES_35, top_k=5, outline_nature=req.outline_nature)
        for node in expanded_nodes
    ]
    all_results = await asyncio.gather(bm25_task, *dense_tasks, *route3_tasks)
    bm25_results       = all_results[0]
    dense_results_list = list(all_results[1:1 + len(dense_tasks)])
    route3_batches     = list(all_results[1 + len(dense_tasks):])

    # ── 合并 Dense + BM25 → RRF → Rerank → main_results ──
    all_dense = []
    for batch in dense_results_list:
        all_dense.extend(batch)
    merged = await rrf_merge(bm25_results, all_dense)
    merged = _apply_outline_nature_weight(merged, req.outline_nature)
    main_results = await rerank(merged, req.query, top_n=20)
    logger.info(f'[3.5] main_results={len(main_results)}')

    # ── 路3去重 → expanded_results ───────────────────────
    seen_ids = {r['chunk_id'] for r in main_results}
    expanded_results = []
    for batch in route3_batches:
        for doc in batch:
            if doc['chunk_id'] not in seen_ids:
                seen_ids.add(doc['chunk_id'])
                expanded_results.append(doc)
    logger.info(f'[3.5] expanded_results={len(expanded_results)}')

    # ── 拼 Prompt ─────────────────────────────────────────
    metadata_lines = []
    if req.burden_description.strip():
        metadata_lines.append(f'负担说明：{req.burden_description.strip()}')
    metadata_block = '\n'.join(metadata_lines)

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

    # ── Claude 生成 ───────────────────────────────────────
    answer = await call_claude(prompt)
    logger.info('[3.5] 生成完成')

    return {
        'answer': answer,
        'chunks_used': len(main_results),
        'expanded_results_count': len(expanded_results),
        'has_skeleton': skeleton is not None,
        'skeleton_steps': len(skeleton) if skeleton else 0,
        'skeleton_preview': [
            {'step': s['step'], 'path_evidence': s.get('path_evidence')}
            for s in skeleton
        ] if skeleton else [],
        'concepts': {
            'revelation': revelation,
            'experience': experience,
            'practice':   practice,
        },
        'chunks': [chunk_to_dict(c) for c in main_results],
        'expanded_chunks': [chunk_to_dict(c) for c in expanded_results],
    }

if __name__ == '__main__':
    import uvicorn
    uvicorn.run('main:app', host='0.0.0.0', port=8007, reload=True)
