# -*- coding: utf-8 -*-
"""检索模块：BM25、Dense、RRF、Reranker。供 qa_service 编排调用，不负责流程编排。"""
import asyncio
import logging
from typing import Any

logger = logging.getLogger("qa")

from back_shared.embedding_adapter import get_embedding
import back_shared.reranker_service as reranker_service


async def bm25_search(
    es: Any,
    query: str,
    index: str,
    top_k: int = 30,
) -> list[dict[str, Any]]:
    """
    BM25 关键词检索。
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
            "book_title",
            "author",
            "source_zh",
            "message_number",
            "message_title",
            "section_title",
            "paragraph_type",
            "tokens",
            "en",
            "source_en",
        ],
    }
    try:
        resp = await asyncio.to_thread(es.search, index=index, body=body)
    except Exception as e:
        logger.warning("[QA] BM25 检索失败: %s", e)
        return []
    out = []
    for hit in (resp.get("hits") or {}).get("hits") or []:
        src = (hit.get("_source") or {}).copy()
        src["score"] = hit.get("_score") or 0.0
        src["source"] = "bm25"
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
    向量 kNN 检索。
    :param es: Elasticsearch 客户端实例
    :param query_text: 查询文本
    :param index: 索引名
    :param top_k: 返回条数（≤0 时不请求 ES，返回空列表）
    :param num_candidates: kNN 候选数
    :return: [{"chunk_id", "text", "score", "source": "dense", ...metadata}, ...]
    """
    if top_k <= 0:
        return []
    try:
        query_vector = await get_embedding(query_text)
    except Exception as e:
        logger.warning("[QA] Embedding 失败: %s", e)
        return []
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
            "book_title",
            "author",
            "source_zh",
            "message_number",
            "message_title",
            "section_title",
            "paragraph_type",
            "tokens",
            "en",
            "source_en",
        ],
    }
    try:
        resp = await asyncio.to_thread(es.search, index=index, body=body)
    except Exception as e:
        logger.warning("[QA] kNN 检索失败: %s", e)
        return []
    out = []
    for hit in (resp.get("hits") or {}).get("hits") or []:
        src = (hit.get("_source") or {}).copy()
        src["score"] = float(hit.get("_score") or 0.0)
        src["source"] = "dense"
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
    RRF 融合路1与路2。
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
    使用 back_shared.reranker_service 精排，取 Top-N。
    失败时降级为按原 RRF 顺序截断。
    ⚠️ 注意：此函数与 reranker_service.rerank 同名但签名不同。
       调用方必须使用模块限定调用：import back_shared.retrieval as retrieval; retrieval.rerank(...)
       禁止：from back_shared.retrieval import rerank
    """
    if not results:
        return []
    texts = [d.get("text") or "" for d in results]
    try:
        indices, degraded = await reranker_service.rerank(query, texts, top_n=top_n)
        if degraded:
            logger.info("[QA] Reranker degraded=True（原序或解析失败）")
    except Exception as e:
        logger.warning("[QA] Reranker 调用异常，降级为 RRF 排序: %s", e)
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
