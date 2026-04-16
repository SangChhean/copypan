# -*- coding: utf-8 -*-
"""FastAPI 路由：/api/kg_rag。query / cache_translation 对已登录用户开放，其余仅管理员可访问。"""
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from user.token import require_admin, test_token
from kg_rag.firewall import load_firewall
from kg_rag.kg_rag_service import KgRagService
from kg_rag.neo4j_client import Neo4jClient

router = APIRouter(prefix="/api/kg_rag", tags=["kg_rag"])


# ---------------------------------------------------------------------------
# 模块级单例：KgRagService 与 Neo4jClient
# ---------------------------------------------------------------------------
_service: Optional[KgRagService] = None
_neo4j: Optional[Neo4jClient] = None


def get_service() -> KgRagService:
    """获取 KgRagService 单例，首次调用时初始化（包含 ES 与 Neo4j）。"""
    global _service, _neo4j
    if _service is None:
        from es_config import es as es_client  # 复用现有 ES 配置（ES_HOST/ES_PORT/ES_USERNAME/ES_PASSWORD）

        _neo4j = Neo4jClient()
        try:
            _neo4j.startup()  # 同步方法，连接失败时内部降级不抛异常
        except Exception:
            pass

        load_firewall()
        _service = KgRagService(es_client, _neo4j)
    return _service


def get_neo4j() -> Neo4jClient:
    """获取 Neo4jClient 单例。"""
    global _neo4j
    if _neo4j is None:
        get_service()
    return _neo4j  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Pydantic 请求模型
# ---------------------------------------------------------------------------


class QueryRequest(BaseModel):
    """通用查询请求体。"""

    query: str = Field(..., min_length=1, max_length=500, description="查询问题")
    params: Optional[dict] = Field(default=None, description="覆盖默认参数")


class CacheTranslationRequest(BaseModel):
    """缓存翻译追加请求体。"""

    cache_key: str = Field(..., min_length=1, description="缓存 key（kg_rag:cache:...）")
    field: str = Field(..., description="要更新的字段：answer_en 或 answer_zh_tw")
    value: str = Field(..., min_length=1, description="翻译后文本")


# ---------------------------------------------------------------------------
# 路由实现
# ---------------------------------------------------------------------------


@router.post("/query", dependencies=[Depends(test_token)])
async def full_query(req: QueryRequest):
    """模块1：全流程查询 Step 1→5。"""
    service = get_service()
    try:
        result = await service.full_query(req.query, req.params or {})
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/prompt_preview", dependencies=[Depends(require_admin)])
async def prompt_preview(req: QueryRequest):
    """模块4：生成 Step 4 Prompt 预览，不调用 LLM。"""
    service = get_service()
    try:
        result = await service.build_prompt_preview(req.query, req.params or {})
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/graph/explore", dependencies=[Depends(require_admin)])
async def graph_explore(
    concept: str = Query(..., min_length=1, description="概念名称"),
    hops: int = Query(1, ge=1, le=5, description="跳数（当前仅支持 1 跳）"),
):
    """模块2：图谱浏览，单概念 N 跳邻居（Phase 1 仅 1 跳）。"""
    neo4j = get_neo4j()
    try:
        neighbors = neo4j.get_neighbors(concept)
        resp = {"concept": concept, "hops": hops, "neighbors": neighbors}
        if hops > 1:
            resp["note"] = "当前版本仅支持 1 跳邻居，多跳查询将在后续版本支持。"
        return resp
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/graph/path", dependencies=[Depends(require_admin)])
async def graph_path(
    concept_a: str = Query(..., min_length=1, description="起点概念"),
    concept_b: str = Query(..., min_length=1, description="终点概念"),
    max_hops: int = Query(3, ge=1, le=5, description="最大跳数"),
):
    """模块2：两概念间路径/最短路径查询。"""
    neo4j = get_neo4j()
    try:
        paths = neo4j.get_paths(concept_a, concept_b, max_hops)
        shortest = neo4j.get_shortest_path(concept_a, concept_b, max_hops)
        count = neo4j.get_path_count(concept_a, concept_b, max_hops)
        return {
            "concept_a": concept_a,
            "concept_b": concept_b,
            "max_hops": max_hops,
            "path_count": count,
            "paths": paths,
            "shortest_path": shortest,
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/graph/stats", dependencies=[Depends(require_admin)])
async def graph_stats():
    """模块2：图谱统计（节点数、关系数、关系类型分布）。"""
    neo4j = get_neo4j()
    try:
        stats = neo4j.get_stats()
        return stats
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/cache_translation", dependencies=[Depends(test_token)])
async def cache_translation(req: CacheTranslationRequest):
    """追加/更新缓存中的英文或繁体纲目翻译。"""
    if req.field not in ("answer_en", "answer_zh_tw"):
        return JSONResponse(status_code=400, content={"error": "field must be answer_en or answer_zh_tw"})
    ok = KgRagService.update_cache_translation(req.cache_key, req.field, req.value)
    return {"ok": ok, "cache_key": req.cache_key, "field": req.field}


class ExtractConceptsRequest(BaseModel):
    """概念抽取请求体。"""
    query: str = Field(..., min_length=1, max_length=500, description="纲目主题")
    outline_nature: str = Field(default="一般性", description="纲目性质")
    burden_description: str = Field(default="", description="负担说明")
    audience: str = Field(default="", description="面对对象")


@router.post("/extract_concepts", dependencies=[Depends(test_token)])
async def extract_concepts(req: ExtractConceptsRequest):
    """独立执行 Step 1 概念抽取，返回 surface + deep 候选列表，供人工筛选。"""
    service = get_service()
    try:
        result = await service.full_query(req.query, {
            "burden_description": req.burden_description,
            "audience": req.audience,
            "outline_nature": req.outline_nature,
            "stop_after_step1": True,
            "skip_cache": True,
        })
        s1 = (result.get("steps") or {}).get("step1") or {}
        return {
            "surface": s1.get("surface", []),
            "deep_candidates": s1.get("deep", []),
            "reasoning": s1.get("reasoning", ""),
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


class TestFirewallRequest(BaseModel):
    """防火墙独立测试请求体。"""
    query: str = Field(..., min_length=1, max_length=500, description="纲目主题")


@router.post("/test_firewall", dependencies=[Depends(require_admin)])
async def test_firewall(req: TestFirewallRequest):
    """独立测试防火墙命中：输入主题，返回是否命中及精粹内容。"""
    from kg_rag.firewall import match_firewall
    from kg_rag.kg_rag_service import _call_kg_rag_llm
    try:
        doc = await match_firewall(req.query.strip(), _call_kg_rag_llm)
        if doc:
            return {"matched": doc["title"], "note": doc["note"]}
        return {"matched": None, "note": None}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/health", dependencies=[Depends(require_admin)])
async def health():
    """健康检查：Neo4j / ES 等依赖可用性。"""
    try:
        service = get_service()
        neo4j = get_neo4j()
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

    # 检查 ES
    es_ok = False
    try:
        es_ok = bool(service.es.ping())
    except Exception:
        es_ok = False

    # Neo4j 状态与概念数
    neo4j_stats = {}
    try:
        neo4j_stats = neo4j.get_stats()
    except Exception:
        neo4j_stats = {}

    return {
        "status": "ok" if es_ok else "degraded",
        "elasticsearch": {"available": es_ok, "index": getattr(service, "index", None)},
        "neo4j": {
            "available": neo4j_stats.get("available", False),
            "concept_count": neo4j_stats.get("concept_count", 0),
        },
    }
