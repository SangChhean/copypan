"""
并发 kNN 向量检索
段落型/经文型查原索引；纲目型查 *_chunks，命中后回查父文档取 title + b_read。
"""
import asyncio
import logging
import os

from elasticsearch import AsyncElasticsearch

from es_config import (
    ES_HOST,
    ES_PASSWORD,
    ES_PORT,
    ES_REQUEST_TIMEOUT,
    ES_USERNAME,
)

logger = logging.getLogger(__name__)

# 从 es_config 复用连接参数，使用异步客户端（端口由 ES_PORT 控制，如 9201）
_es_client: AsyncElasticsearch | None = None


def _get_async_es() -> AsyncElasticsearch:
    global _es_client
    if _es_client is None:
        _es_client = AsyncElasticsearch(
            hosts=[f"http://{ES_HOST}:{ES_PORT}"],
            basic_auth=(ES_USERNAME, ES_PASSWORD),
            request_timeout=ES_REQUEST_TIMEOUT,
        )
    return _es_client


async def close_async_es() -> None:
    """关闭 AsyncElasticsearch 连接（应用 shutdown 时调用）。"""
    global _es_client
    if _es_client is not None:
        try:
            await _es_client.close()
        except Exception as e:
            logger.warning("Async ES close: %s", e)
        _es_client = None


# 索引分类（硬编码常量）
PARAGRAPH_INDICES = ["cwwl", "cwwn", "life", "others"]
BIB_INDICES = ["bib"]
MAP_CHUNK_INDICES = [
    "map_note_chunks",
    "map_7feasts_chunks",
    "map_pano_chunks",
    "map_dictionary_chunks",
]
MAP_CHUNK_TO_PARENT: dict[str, str] = {
    "map_note_chunks": "map_note",
    "map_7feasts_chunks": "map_7feasts",
    "map_pano_chunks": "map_pano",
    "map_dictionary_chunks": "map_dictionary",
}

NUM_CANDIDATES = 100


def _is_map_chunk_index(index: str) -> bool:
    return index in MAP_CHUNK_TO_PARENT


def _get_text_from_source(index: str, source: dict) -> str:
    """从 _source 取正文：段落型 zh/text，经文型 zh/text，纲目型 text。"""
    if _is_map_chunk_index(index):
        return (source.get("text") or "").strip()
    # 段落型、经文型：优先 zh，否则 text
    return (source.get("zh") or source.get("text") or "").strip()


def _dedup_key(hit: dict) -> tuple:
    """去重键：纲目型用 chunk_id，其余用 (_index, _id)。"""
    idx = hit.get("_index", "")
    if _is_map_chunk_index(idx):
        cid = (hit.get("_source") or {}).get("chunk_id") or hit.get("_id")
        return ("chunk_id", cid)
    return ("doc", idx, hit.get("_id"))


async def _fetch_parent_title_bread(parent_index: str, parent_ids: list[str]) -> dict[str, str]:
    """批量回查父文档，返回 parent_id -> source_label（title + b_read）。"""
    if not parent_ids:
        return {}
    es = _get_async_es()
    labels: dict[str, str] = {}
    # mget 父文档
    try:
        resp = await es.mget(index=parent_index, body={"ids": parent_ids}, _source=["msg"])
    except Exception as e:
        logger.error("回查父文档 mget 失败: %s", e)
        raise
    for doc in resp.get("docs") or []:
        if not doc.get("found"):
            continue
        pid = doc.get("_id", "")
        src = doc.get("_source") or {}
        msg_list = src.get("msg") or []
        title = ""
        b_read = ""
        for m in msg_list:
            if not isinstance(m, dict):
                continue
            t = (m.get("type") or "").strip()
            text = (m.get("text") or "").strip()
            if t == "title":
                title = text
            elif t == "b_read":
                b_read = text
        parts = [p for p in [title, b_read] if p]
        labels[pid] = "；".join(parts) if parts else ""
    return labels


async def knn_search_single(
    index: str,
    vector: list[float],
    k: int = 60,
) -> list[dict]:
    """
    对单个索引执行 kNN 检索，返回命中列表，每条含 _id, _index, _score, text, source_label。
    纲目型会回查父文档填充 source_label（title + b_read）。
    """
    if not vector or k <= 0:
        return []
    es = _get_async_es()
    body = {
        "knn": {
            "field": "embedding",
            "query_vector": vector,
            "k": k,
            "num_candidates": NUM_CANDIDATES,
        },
        "size": k,
        "_source": True,
    }
    # 按索引类型限定 _source 字段，减少流量
    if _is_map_chunk_index(index):
        body["_source"] = ["chunk_id", "parent_id", "text"]
    elif index in BIB_INDICES:
        body["_source"] = ["zh", "text", "book", "chapter", "verse"]
    else:
        body["_source"] = ["zh", "text", "id", "title"]

    try:
        resp = await es.search(index=index, body=body, request_timeout=30)
    except Exception as e:
        logger.error("kNN 检索失败 index=%s: %s", index, e)
        raise

    hits = resp.get("hits", {}).get("hits") or []
    out: list[dict] = []
    if not _is_map_chunk_index(index):
        for h in hits:
            src = h.get("_source") or {}
            out.append({
                "_id": h.get("_id"),
                "_index": h.get("_index"),
                "_score": float(h.get("_score") or 0),
                "text": _get_text_from_source(index, src),
                "source_label": "",
                "id": src.get("id") or h.get("_id") or "",
                "title": src.get("title") or "",
                "book": src.get("book") or "",
                "chapter": src.get("chapter") or "",
                "verse": src.get("verse") or "",
            })
        return out

    # 纲目型：收集 parent_id，批量回查父文档
    parent_index = MAP_CHUNK_TO_PARENT.get(index, index)
    parent_ids = list({(h.get("_source") or {}).get("parent_id") for h in hits if (h.get("_source") or {}).get("parent_id")})
    parent_labels = await _fetch_parent_title_bread(parent_index, parent_ids)

    for h in hits:
        src = h.get("_source") or {}
        pid = src.get("parent_id", "")
        out.append({
            "_id": h.get("_id"),
            "_index": h.get("_index"),
            "_score": float(h.get("_score") or 0),
            "text": _get_text_from_source(index, src),
            "source_label": parent_labels.get(pid, ""),
        })
    return out


async def knn_search_multi(
    vectors: list[list[float]],
    indices: list[str],
    k: int = 60,
) -> list[dict]:
    """
    并发执行所有 (index, vector) 组合的 kNN 检索，合并去重后返回。
    段落型/经文型按 (_index, _id) 去重，纲目型按 chunk_id 去重。
    """
    if not vectors or not indices or k <= 0:
        return []
    tasks = [
        knn_search_single(index=idx, vector=vec, k=k)
        for vec in vectors
        for idx in indices
    ]
    try:
        results_per_task = await asyncio.gather(*tasks, return_exceptions=True)
    except Exception as e:
        logger.error("knn_search_multi gather 失败: %s", e)
        raise

    seen: set[tuple] = set()
    out: list[dict] = []
    for i, r in enumerate(results_per_task):
        if isinstance(r, BaseException):
            logger.error("knn_search_multi 单路失败: %s", r)
            raise r
        for hit in r:
            key = _dedup_key(hit)
            if key in seen:
                continue
            seen.add(key)
            out.append(hit)
    return out
