# -*- coding: utf-8 -*-
"""FastAPI 路由：/api/kg_rag。query / cache_translation / generate_step5 对已登录用户开放，其余仅管理员可访问。"""
import asyncio
import base64
import json
import logging
import os
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from user.token import require_admin, test_token
from kg_rag.firewall import load_firewall
from kg_rag.kg_rag_service import KgRagService, ministerialize_outline
from ai_search.ai_service import ai_service
from ai_search.monitoring import get_monitoring
from kg_rag.neo4j_client import Neo4jClient
from features.feast_outline_maker.feast_router import feast_router

router = APIRouter(prefix="/api/kg_rag", tags=["kg_rag"])
logger = logging.getLogger("kg_rag")

# 临时调试：KG_RAG_LOG=info（默认开启）输出 kg_rag INFO；完成后设 KG_RAG_LOG=0
if os.environ.get("KG_RAG_LOG", "info").lower() not in ("0", "false", "no", "off"):
    logger.setLevel(logging.INFO)
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        _kg_log_handler = logging.StreamHandler()
        _kg_log_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )
        logger.addHandler(_kg_log_handler)
# 可选：KG_RAG_DEBUG=1 时额外输出 DEBUG（默认关闭）
if os.environ.get("KG_RAG_DEBUG", "0").lower() in ("1", "true", "yes"):
    logger.setLevel(logging.DEBUG)


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
        if not _neo4j.is_available():
            # 进程级事件：整个服务运行期间只在启动时判定一次，不存在"重复记录"的问题。
            # Neo4jClient 本身不依赖 ai_search.monitoring（保持零业务依赖），
            # 由这里的调用方在 startup() 失败后自行上报，避免底层基础设施模块
            # 反向依赖上层业务监控模块。
            try:
                get_monitoring().record_degradation(
                    source="neo4j_connection",
                    reason=_neo4j.get_last_connect_error() or "连接失败，原因未知",
                    extra=_neo4j.get_connection_info(),
                )
            except Exception as mon_e:
                logger.warning(f"[KG-RAG] Neo4j 连接降级事件记录失败（不影响主流程）: {mon_e}")

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
    mode: str = "3.0"


class CacheTranslationRequest(BaseModel):
    """缓存翻译追加请求体。"""

    cache_key: str = Field(..., min_length=1, description="缓存 key（kg_rag:cache:...）")
    field: str = Field(..., description="要更新的字段：answer_en 或 answer_zh_tw")
    value: str = Field(..., min_length=1, description="翻译后文本")


class GenerateStep5Request(BaseModel):
    """仅执行 Step5：对已有 Step4 prompt 调用 LLM 生成纲目。"""

    prompt: str = Field(..., min_length=1, description="Step 4 构建的完整 prompt")
    model: str = "claude-sonnet-4-6"
    temperature: float = 0.3


class GenerateBurdenRequest(BaseModel):
    """负担说明生成：主题 + 纲目性质/面对对象/参考摘录（后三项选填）。"""

    query: str = Field(..., min_length=1, max_length=500, description="纲目主题")
    outline_nature: str = Field(default="", description="纲目性质")
    audience: str = Field(default="", description="面对对象")
    reference_excerpt: str = Field(default="", description="参考摘录")
    model: str = Field(default="claude-sonnet-4-6", description="使用的模型，默认 claude-sonnet-4-6")


class MinisterializeRequest(BaseModel):
    """纲目职事化：逐条检索并抽句。"""

    lines: List[str] = Field(..., min_length=1, max_length=500, description="纲目条目，每行一条")


class MinisterializeDocxLine(BaseModel):
    """职事化导出行：正文与出处。"""

    text: str = Field(..., description="纲目正文（含编号与经文后缀）")
    source: str = Field(default="", description="出处，来自检索 top1 的 source_zh")


class MinisterializeDocxRequest(BaseModel):
    """纲目职事化结果导出 DOCX。"""

    lines: List[MinisterializeDocxLine] = Field(
        ..., min_length=1, max_length=2000, description="职事化后的纲目条目"
    )
    header_lines: Optional[List[str]] = Field(
        default=None,
        description="文档开头标题行：系列名/总题/篇题/读经等，过滤空值后写入 DOCX",
    )
    title: Optional[str] = Field(
        default=None,
        max_length=200,
        description="下载文件名（篇题），不含 .docx 后缀",
    )
    with_source: bool = Field(
        default=False,
        description="为 True 时在每行末追加红色括号出处",
    )


# ---------------------------------------------------------------------------
# 路由实现
# ---------------------------------------------------------------------------


@router.post("/query", dependencies=[Depends(test_token)])
async def full_query(req: QueryRequest):
    """模块1：全流程查询 Step 1→5。"""
    service = get_service()
    try:
        result = await service.full_query(req.query, req.params or {}, mode=req.mode)
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/generate_step5", dependencies=[Depends(test_token)])
async def generate_step5(req: GenerateStep5Request):
    """仅调用 Step5 LLM：输入 Step4 prompt，返回生成文本与估算费用、耗时。"""
    from kg_rag.kg_rag_service import _call_kg_rag_llm
    from kg_rag.llm_pricing import register_llm_usage

    t0 = asyncio.get_event_loop().time()
    try:
        gen, usage = await _call_kg_rag_llm(
            req.prompt,
            req.model,
            temperature=req.temperature,
            max_tokens=4096,
            system=None,
        )
        elapsed_ms = round((asyncio.get_event_loop().time() - t0) * 1000, 1)
        sn = register_llm_usage(
            [], step="generate_step5", request_model=req.model, usage=usage
        )
        cost_usd = float(sn["cost_usd"]) if sn else 0.0
        text = (gen or "").strip()
        return {
            "answer": text if text else None,
            "model": req.model,
            "cost_usd": cost_usd,
            "elapsed_ms": elapsed_ms,
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/ministerialize", dependencies=[Depends(test_token)])
async def ministerialize(req: MinisterializeRequest):
    """纲目职事化：对每条纲目检索职事书摘录并抽取贴近原文。"""
    try:
        return await ministerialize_outline(req.lines)
    except Exception as e:
        logger.exception("ministerialize 失败")
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/ministerialize_docx", dependencies=[Depends(test_token)])
async def ministerialize_docx(req: MinisterializeDocxRequest):
    """纲目职事化结果刷格式并导出 DOCX（初信版模板）。"""
    content_lines = [
        {"text": (item.text or "").strip(), "source": (item.source or "").strip()}
        for item in req.lines
        if (item.text or "").strip()
    ]
    if not content_lines:
        raise HTTPException(status_code=400, detail="内容不能为空")
    try:
        header_lines = [ln.strip() for ln in (req.header_lines or []) if (ln or "").strip()]
        logger.debug(
            "[ministerialize_docx] lines received: count=%s with_source=%s",
            len(content_lines),
            req.with_source,
        )
        result = await asyncio.to_thread(
            ai_service.format_rough_outline_docx,
            "beginner",
            [],
            header_lines or None,
            content_lines,
            req.with_source,
        )
        logger.debug(
            f"[ministerialize_docx] docx generated, filename={result.get('filename')}, "
            f"error={result.get('error')}"
        )
        if result.get("error") and not result.get("docx_bytes"):
            raise HTTPException(status_code=400, detail=result.get("error"))
        if not result.get("docx_bytes"):
            raise HTTPException(status_code=400, detail=result.get("error") or "生成 DOCX 失败")
        title = (req.title or "").strip()
        filename = f"{title}.docx" if title else "纲目职事化.docx"
        return {
            "docx_base64": base64.b64encode(result["docx_bytes"]).decode("utf-8"),
            "filename": filename,
            "error": result.get("error"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("ministerialize_docx 失败")
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/generate_burden", dependencies=[Depends(test_token)])
async def generate_burden(req: GenerateBurdenRequest):
    """根据主题与上下文生成负担说明（情境 A 单条 / 情境 B 三候选）。"""
    service = get_service()
    try:
        logger.info(
            "[KG-RAG BURDEN DEBUG] /generate_burden req: query_len=%s outline=%r audience=%r excerpt_len=%s",
            len((req.query or "").strip()),
            (req.outline_nature or "").strip(),
            (req.audience or "").strip(),
            len((req.reference_excerpt or "").strip()),
        )
        result = await service.generate_burden_description(
            req.query,
            outline_nature=req.outline_nature,
            audience=req.audience,
            reference_excerpt=req.reference_excerpt,
            model=req.model,
        )
        logger.info(
            "[KG-RAG BURDEN DEBUG] /generate_burden resp: scenario=%s has_error=%s",
            result.get("scenario"),
            bool(result.get("error")),
        )
        return result
    except Exception as e:
        logger.exception("[KG-RAG BURDEN DEBUG] /generate_burden exception")
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


@router.post("/cache/clear", dependencies=[Depends(require_admin)])
async def clear_kg_rag_cache():
    """清理 KG-RAG Redis 缓存（kg_rag:cache:*）。"""
    service = get_service()
    redis_client = getattr(service, "redis", None)
    if not redis_client:
        return {"deleted": 0, "error": "Redis unavailable"}
    try:
        keys = redis_client.keys("kg_rag:cache:*")
        if keys:
            redis_client.delete(*keys)
        return {"deleted": len(keys)}
    except Exception as e:
        return JSONResponse(status_code=500, content={"deleted": 0, "error": str(e)})


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


@router.get("/concepts/search", dependencies=[Depends(test_token)])
async def search_concepts(
    q: str = Query("", description="概念关键词"),
    limit: int = Query(20, ge=1, le=100, description="返回数量上限"),
):
    """按关键词搜索图谱概念名称，已登录用户可用。"""
    key = (q or "").strip()
    if not key:
        return {"results": []}
    neo4j = get_neo4j()
    results = neo4j.search_concepts_by_name(key, limit=limit)
    return {"results": results}


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
    mode: str = "3.0"


@router.post("/extract_concepts", dependencies=[Depends(test_token)])
async def extract_concepts(req: ExtractConceptsRequest):
    """独立执行 Step 1 概念抽取，返回 revelation / experience / practice 候选列表，供人工筛选。"""
    service = get_service()
    try:
        result = await service.full_query(
            req.query,
            {
                "burden_description": req.burden_description,
                "audience": req.audience,
                "outline_nature": req.outline_nature,
                "stop_after_step1": True,
                "skip_cache": True,
            },
            mode=req.mode,
        )
        s1 = (result.get("steps") or {}).get("step1") or {}
        logger.info(
            "[KG-RAG DEBUG] extract_concepts step1 summary: revelation=%s experience=%s practice=%s reasoning_len=%s raw_response_len=%s error=%s",
            s1.get("revelation", []),
            s1.get("experience", []),
            s1.get("practice", []),
            len(str(s1.get("reasoning", "") or "")),
            len(str(s1.get("raw_response", "") or "")),
            s1.get("error"),
        )
        return {
            "revelation": s1.get("revelation", []),
            "experience": s1.get("experience", []),
            "practice": s1.get("practice", []),
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


# ── 词典-鸟瞰纲目 ─────────────────────────────────────────
class BirdViewSkeletonRequest(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., description="ministry 或 feast")
    content: str = Field(..., min_length=1)


class BirdViewOutlineRequest(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., description="ministry 或 feast")
    content: str = Field(..., min_length=1)
    skeleton: str = Field(..., min_length=1)


@router.post("/bird_view/skeleton", dependencies=[Depends(test_token)])
async def bird_view_skeleton(req: BirdViewSkeletonRequest):
    service = get_service()
    try:
        result = await service.generate_bird_view_skeleton(
            keyword=req.keyword,
            content_type=req.type,
            content=req.content,
        )
        return result
    except Exception as e:
        logger.error(f"[bird_view_skeleton] error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/bird_view/outline", dependencies=[Depends(test_token)])
async def bird_view_outline(req: BirdViewOutlineRequest):
    service = get_service()
    try:
        result = await service.generate_bird_view_outline(
            keyword=req.keyword,
            content_type=req.type,
            content=req.content,
            skeleton=req.skeleton,
        )
        return result
    except Exception as e:
        logger.error(f"[bird_view_outline] error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class BirdViewSourceRequest(BaseModel):
    keyword: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., description="ministry 或 feast")
    content: str = Field(..., min_length=1)
    outline: str = Field(..., min_length=1)


@router.post("/bird_view/source", dependencies=[Depends(test_token)])
async def bird_view_source(req: BirdViewSourceRequest):
    service = get_service()
    try:
        result = await service.generate_bird_view_with_source(
            keyword=req.keyword,
            content_type=req.type,
            content=req.content,
            outline=req.outline,
        )
        return result
    except Exception as e:
        logger.error(f"[bird_view_source] error: {e}")
        raise HTTPException(status_code=500, detail=str(e))


def _build_health_payload():
    """Neo4j / ES 依赖可用性（供 liveness 与 admin health 共用）。"""
    service = get_service()
    neo4j = get_neo4j()

    es_ok = False
    try:
        es_ok = bool(service.es.ping())
    except Exception:
        es_ok = False

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


@router.get("/liveness")
async def liveness():
    """无需鉴权：依赖可用性探测（供前端状态条使用）。"""
    try:
        return _build_health_payload()
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.get("/health", dependencies=[Depends(require_admin)])
async def health():
    """管理员健康检查（与 liveness 相同，保留供脚本/运维）。"""
    try:
        return _build_health_payload()
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})
