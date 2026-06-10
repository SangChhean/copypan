# -*- coding: utf-8 -*-
"""检索模块：BM25、Dense、RRF、Reranker、路3 骨架扩展检索。供 kg_rag_service 编排调用，不负责流程编排。"""
import asyncio
import logging
from typing import Any

logger = logging.getLogger("kg_rag")

# ES 客户端由调用方传入；embedding 与 reranker 从项目现有模块导入
try:
    from embedding_adapter import get_embedding
except ImportError:
    import sys
    from pathlib import Path
    _backend = str(Path(__file__).resolve().parents[2])
    if _backend not in sys.path:
        sys.path.insert(0, _backend)
    from embedding_adapter import get_embedding


async def bm25_search(
    es: Any,
    query: str,
    index: str,
    top_k: int = 30,
) -> list[dict[str, Any]]:
    """
    路1：BM25 关键词检索。
    :param es: 已初始化的 Elasticsearch 客户端实例（同步）
    :param query: 查询字符串
    :param index: 索引名
    :param top_k: 返回条数（≤0 时不请求 ES，返回空列表）
    :return: [{"chunk_id", "text", "score", "source": "bm25", ...metadata}, ...]
    """
    if top_k <= 0:
        return []
    body = {
        "query": {
            "match": {
                "text": {"query": query, "analyzer": "ik_smart"},
            }
        },
        "size": top_k,
        "_source": [
            "chunk_id",
            "text",
            "en",
            "book_title",
            "author",
            "source_zh",
            "source_en",
            "source",
            "message_number",
            "message_title",
            "section_title",
            "paragraph_type",
            "tokens",
        ],
    }
    try:
        resp = await asyncio.to_thread(es.search, index=index, body=body)
    except Exception as e:
        print(f"[KG-RAG] BM25 检索失败: {e}")
        return []
    out = []
    for hit in (resp.get("hits") or {}).get("hits") or []:
        src = (hit.get("_source") or {}).copy()
        src["score"] = hit.get("_score") or 0.0
        src["retrieval_route"] = "bm25"
        src["_index"] = hit.get("_index") or ""
        src.setdefault("chunk_id", hit.get("_id", ""))
        out.append(src)
    return out


async def dense_search(
    es: Any,
    query_text: str,
    index: str,
    top_k: int = 30,
    num_candidates: int = 100,
) -> list[dict[str, Any]]:
    """
    路2：向量 kNN 检索。使用 embedding_adapter.get_embedding(profile="kg_rag") 生成查询向量。
    :param es: Elasticsearch 客户端实例
    :param query_text: 查询文本（改写后的 Query，会记录到每条结果的 rewritten_query 字段）
    :param index: 索引名
    :param top_k: 返回条数（≤0 时不请求 ES，返回空列表）
    :param num_candidates: kNN 候选数
    :return: [{"chunk_id", "text", "score", "source": "dense", "rewritten_query": query_text, ...metadata}, ...]
    """
    if top_k <= 0:
        return []
    try:
        query_vector = await get_embedding(query_text, profile="kg_rag")
    except Exception as e:
        print(f"[KG-RAG] Embedding 失败: {e}")
        return []
    # ES 全局 size 默认 10；不设 size 时即使 knn.k=30，hits 仍可能被截成 10 条
    body = {
        "size": top_k,
        "knn": {
            "field": "embedding",
            "query_vector": query_vector,
            "k": top_k,
            "num_candidates": num_candidates,
        },
        "_source": [
            "chunk_id",
            "text",
            "en",
            "book_title",
            "author",
            "source_zh",
            "source_zh",
            "message_number",
            "message_title",
            "section_title",
            "paragraph_type",
            "tokens",
        ],
    }
    try:
        resp = await asyncio.to_thread(es.search, index=index, body=body)
    except Exception as e:
        print(f"[KG-RAG] kNN 检索失败: {e}")
        return []
    out = []
    for hit in (resp.get("hits") or {}).get("hits") or []:
        src = (hit.get("_source") or {}).copy()
        src["score"] = float(hit.get("_score") or 0.0)
        src["source"] = "dense"
        src["rewritten_query"] = query_text
        src["_index"] = hit.get("_index") or ""
        src.setdefault("chunk_id", hit.get("_id", ""))
        out.append(src)
    return out


async def rrf_merge(
    bm25_results: list[dict],
    dense_results: list[dict],
    k: int = 60,
    bm25_weight: float = 1.0,
    dense_weight: float = 1.0,
) -> list[dict[str, Any]]:
    """
    RRF（Reciprocal Rank Fusion）融合路1与路2。对每个文档 RRF_score = Σ (weight / (k + rank))。
    :param bm25_results: 路1 结果列表
    :param dense_results: 路2 结果列表
    :param k: RRF 常数（设计文档指定 60）
    :param bm25_weight: 路1 权重
    :param dense_weight: 路2 权重
    :return: 去重后按 RRF 分数降序的列表，每项 score 为 rrf_score，source 为 "rrf"，source_routes 为来源路列表
    """
    rrf_scores = {}
    doc_map = {}
    bm25_ids: set[str] = set()
    dense_ids: set[str] = set()
    for rank, doc in enumerate(bm25_results, 1):
        cid = doc.get("chunk_id") or doc.get("_id") or ""
        if not cid:
            continue
        rrf_scores[cid] = rrf_scores.get(cid, 0) + bm25_weight / (k + rank)
        doc_map[cid] = dict(doc)
        bm25_ids.add(cid)
    for rank, doc in enumerate(dense_results, 1):
        cid = doc.get("chunk_id") or doc.get("_id") or ""
        if not cid:
            continue
        rrf_scores[cid] = rrf_scores.get(cid, 0) + dense_weight / (k + rank)
        if cid not in doc_map:
            doc_map[cid] = dict(doc)
        dense_ids.add(cid)
    sorted_ids = sorted(rrf_scores.keys(), key=lambda x: rrf_scores[x], reverse=True)
    out = []
    for cid in sorted_ids:
        d = doc_map[cid]
        d["score"] = rrf_scores[cid]
        d["source"] = "rrf"
        routes: list[str] = []
        if cid in bm25_ids:
            routes.append("bm25")
        if cid in dense_ids:
            routes.append("dense")
        d["source_routes"] = routes
        out.append(d)
    return out


async def rerank(
    results: list[dict],
    query: str,
    top_n: int = 20,
) -> list[dict[str, Any]]:
    """
    使用项目现有的 Jina Reranker v3（ai_search.reranker_service）精排，取 Top-N。
    失败时降级为按原 RRF 顺序截断，并打印警告。
    :param results: RRF 融合后的文档列表（含 text、chunk_id 等）
    :param query: 原始查询
    :param top_n: 精排后保留条数
    :return: 精排后的列表，每项 source 为 "reranked"
    """
    if not results:
        return []
    texts = [d.get("text") or "" for d in results]
    try:
        from ai_search.reranker_service import rerank as _jina_rerank
        indices, degraded = await _jina_rerank(query, texts, top_n=top_n)
        if degraded:
            logger.info("[KG-RAG] Jina Reranker degraded=True（原序或解析失败）")
    except Exception as e:
        logger.warning("[KG-RAG] Jina Reranker 调用异常，降级为 RRF 排序: %s", e)
        out = results[:top_n]
        for d in out:
            d["source"] = "reranked"
        return out
    out = []
    for i in indices:
        if i < len(results):
            d = dict(results[i])
            d["source"] = "reranked"
            out.append(d)
    return out


async def skeleton_route_search(
    es: Any,
    node_name: str,
    original_query: str,
    index: str,
    top_k: int = 5,
    outline_nature: str = "一般性",
) -> list[dict[str, Any]]:
    """
    路3：为单个骨架扩展节点执行「原始 Query + 节点名」的 BM25 + Dense → RRF → 纲目加权截断 → Reranker → Top-K。
    检索阶段各取 top_k*3 条候选，加权排序后截断到 top_k，再送入 Reranker。
    :param es: Elasticsearch 客户端实例
    :param node_name: 扩展节点概念名
    :param original_query: 用户原始查询
    :param index: 索引名
    :param top_k: 返回条数
    :param outline_nature: 纲目性质，与主路 BM25/Dense 加权规则一致
    :return: 每条含 "expanded_from": node_name 和 "source": "skeleton_route"
    """
    combined_query = f"{original_query} {node_name}".strip()
    route3_fetch_size = top_k * 3
    bm25_hits = await bm25_search(es, combined_query, index, top_k=route3_fetch_size)
    dense_hits = await dense_search(
        es, combined_query, index, top_k=route3_fetch_size, num_candidates=min(300, route3_fetch_size * 3)
    )
    merged = await rrf_merge(bm25_hits, dense_hits)
    from kg_rag.kg_rag_service import _apply_outline_nature_weight

    weighted = _apply_outline_nature_weight(merged, outline_nature, log_full_list=False)
    truncated = weighted[:top_k]
    reranked = await rerank(truncated, combined_query, top_n=top_k)
    for doc in reranked:
        doc["expanded_from"] = node_name
        doc["source"] = "skeleton_route"
    return reranked
