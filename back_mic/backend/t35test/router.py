# -*- coding: utf-8 -*-
"""【3.5测试用】的独立接口：/api/t35test。

主站“AI纲目制作面板”用到的全部后端能力的完整副本，与主站 3.5（/api/kg_rag、/api/ai_search、/api/eval）
互不引用、互不影响：
  - KG-RAG 核心：query / generate_burden / extract_concepts / concepts/search / cache_translation
  - 翻译、繁体转换、格式化下载：translate_outline / outline_to_traditional / format_outline_only
  - 纲目评估：eval/outline
独立的 prompt、独立的缓存键前缀（t35test:）、独立的单例与监控（监控为空实现，不写入主站统计）。
共用的只有基础设施和数据：ES、Neo4j、Redis 服务本身，防火墙文档，登录校验。
"""
import asyncio
import base64
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from user.token import test_token
from t35test.common import get_monitoring
from t35test.kg.firewall import load_firewall
from t35test.kg.kg_rag_service import KgRagService
from t35test.kg.neo4j_client import Neo4jClient
from t35test.outline_eval.llm_evaluator import run_evaluation
from t35test.translate.service import translate_service

router = APIRouter(prefix="/api/t35test", tags=["t35test"], dependencies=[Depends(test_token)])
logger = logging.getLogger("t35test")

# 临时调试：T35_LOG=0 可关闭 INFO 输出
if os.environ.get("T35_LOG", "info").lower() not in ("0", "false", "no", "off"):
    logger.setLevel(logging.INFO)
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        _h = logging.StreamHandler()
        _h.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s"))
        logger.addHandler(_h)


# ---------------------------------------------------------------------------
# 模块级单例：KgRagService 与 Neo4jClient（t35test 自己的一份）
# ---------------------------------------------------------------------------
_service: Optional[KgRagService] = None
_neo4j: Optional[Neo4jClient] = None


def get_service() -> KgRagService:
    """获取 KgRagService 单例，首次调用时初始化（包含 ES 与 Neo4j）。"""
    global _service, _neo4j
    if _service is None:
        from es_config import es as es_client  # 基础设施：ES 连接配置

        _neo4j = Neo4jClient()
        try:
            _neo4j.startup()  # 连接失败时内部降级，不抛异常
        except Exception:
            pass
        if not _neo4j.is_available():
            try:
                get_monitoring().record_degradation(
                    source="neo4j_connection",
                    reason=_neo4j.get_last_connect_error() or "连接失败，原因未知",
                    extra=_neo4j.get_connection_info(),
                )
            except Exception as mon_e:
                logger.warning(f"[t35test] Neo4j 连接降级事件记录失败（不影响主流程）: {mon_e}")
        load_firewall()
        _service = KgRagService(es_client, _neo4j)
    return _service


def get_neo4j() -> Neo4jClient:
    if _neo4j is None:
        get_service()
    return _neo4j  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# 请求模型
# ---------------------------------------------------------------------------
# 【新测试台】后端统一用「综合性」（原来的「一般性」）；旧写法「一般性」「应用实行」进来时换成新写法。
NATURE_ALIAS = {"一般性": "综合性", "应用实行": "实行应用"}


def _norm_nature(v):
    t = (v or "").strip() if isinstance(v, str) else v
    return NATURE_ALIAS.get(t, t)


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="查询问题")
    params: Optional[dict] = Field(default=None, description="覆盖默认参数")
    mode: str = "3.0"


class CacheTranslationRequest(BaseModel):
    cache_key: str = Field(..., min_length=1, description="缓存 key（t35test:cache:...）")
    field: str = Field(..., description="要更新的字段：answer_en 或 answer_zh_tw")
    value: str = Field(..., min_length=1, description="翻译后文本")


class GenerateBurdenRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="纲目主题")
    outline_nature: str = Field(default="", description="纲目性质")
    audience: str = Field(default="", description="面对对象")
    reference_excerpt: str = Field(default="", description="负担的重点")
    model: str = Field(default="claude-opus-5-5", description="使用的模型，默认 claude-opus-5-5")


class ExtractConceptsRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="纲目主题")
    outline_nature: str = Field(default="综合性", description="纲目性质")
    burden_description: str = Field(default="", description="负担说明")
    audience: str = Field(default="", description="面对对象")
    mode: str = "3.0"


class TranslateOutlineRequest(BaseModel):
    chinese_outline: str = Field(..., min_length=1, max_length=100_000, description="中文纲目全文")
    outline_topic: Optional[str] = Field(None, max_length=200, description="纲目主题（用于翻译标题）")


class FormatOutlineRequest(BaseModel):
    direction: Literal["zh2en", "en2zh", "zh_cn2tw", "zh_tw2cn"] = Field(..., description="zh2en=英文纲目, 其余=中文纲目")
    translated_text: str = Field(..., min_length=1, max_length=100_000, description="已翻译/转换的纲目全文")
    output_format: Literal["docx", "pdf"] = Field("docx", description="输出格式")
    is_outline: bool = Field(True, description="True=纲目格式刷，False=通用平铺格式刷")


class OutlineToTraditionalRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000, description="简体纲目全文")


class EvalRequest(BaseModel):
    answer: str
    query: str
    outline_nature: str
    burden_description: str = ""
    revelation: list[str] = []
    experience: list[str] = []
    practice: list[str] = []
    skeleton: list[dict[str, Any]] = []
    answer_v1: str | None = None
    eval_v1: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# KG-RAG 核心
# ---------------------------------------------------------------------------
@router.post("/query")
async def full_query(req: QueryRequest):
    """全流程查询 Step 1→5。"""
    service = get_service()
    try:
        params = dict(req.params or {})
        if "outline_nature" in params:
            params["outline_nature"] = _norm_nature(params["outline_nature"])
        return await service.full_query(req.query, params, mode=req.mode)
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/generate_burden")
async def generate_burden(req: GenerateBurdenRequest):
    """根据主题与上下文生成负担说明（有负担的重点 → 单条 / 没有负担的重点 → 三候选）。"""
    service = get_service()
    try:
        logger.info(
            "[t35test BURDEN] /generate_burden req: query_len=%s outline=%r excerpt_len=%s model=%s",
            len((req.query or "").strip()),
            _norm_nature(req.outline_nature or ""),
            len((req.reference_excerpt or "").strip()),
            req.model,
        )
        result = await service.generate_burden_description(
            req.query,
            outline_nature=_norm_nature(req.outline_nature),
            audience=req.audience,
            reference_excerpt=req.reference_excerpt,
            model=req.model,
        )
        _record_burden_trial(req, result)
        return result
    except Exception as e:
        logger.exception("[t35test BURDEN] /generate_burden exception")
        return JSONResponse(status_code=500, content={"error": str(e)})


def _record_burden_trial(req: "GenerateBurdenRequest", result: dict) -> None:
    """【新测试台】每次生成负担说明自动记一条（含完整的要点依据），存在 logs/inner_trial/burden-日期.jsonl。"""
    try:
        _INNER_TRIAL_DIR.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        usage = (result or {}).get("llm_usage") or {}
        row = {
            "time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "query": req.query,
            "outline_nature": req.outline_nature,
            "outline_nature_used": _norm_nature(req.outline_nature),
            "reference_excerpt": req.reference_excerpt,
            "audience": req.audience,
            "scenario": (result or {}).get("scenario"),
            "result": (result or {}).get("result"),
            "candidates": (result or {}).get("candidates"),
            "points_basis": (result or {}).get("reasoning", ""),  # 要点依据（原文；页面显示时把"摘录"显示为"负担的重点"）
            "error": (result or {}).get("error"),
            "model": (result or {}).get("model") or req.model,
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "cost_usd": usage.get("cost_usd"),
        }
        path = _INNER_TRIAL_DIR / f"burden-{now.strftime('%Y%m%d')}.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("[t35test BURDEN] 记录负担说明失败（不影响返回）: %s", e)


@router.post("/extract_concepts")
async def extract_concepts(req: ExtractConceptsRequest):
    """独立执行 Step 1 概念抽取，返回 revelation / experience / practice 候选列表，供人工筛选。"""
    service = get_service()
    try:
        result = await service.full_query(
            req.query,
            {
                "burden_description": req.burden_description,
                "audience": req.audience,
                "outline_nature": _norm_nature(req.outline_nature),
                "stop_after_step1": True,
                "skip_cache": True,
            },
            mode=req.mode,
        )
        s1 = (result.get("steps") or {}).get("step1") or {}
        _record_inner_trial(req, s1)
        return {
            "revelation": s1.get("revelation", []),
            "inner": s1.get("inner", []),
            "experience": s1.get("experience", []),
            "practice": s1.get("practice", []),
            "reasoning": s1.get("reasoning", ""),
            "thinking_text": s1.get("thinking_text", ""),
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


# 【新测试台】内在素质研究：每次推荐重点自动记一条，便于以后比较方案 A/B/C
_INNER_TRIAL_DIR = Path(__file__).resolve().parents[1] / "logs" / "inner_trial"


def _record_inner_trial(req: "ExtractConceptsRequest", s1: dict) -> None:
    try:
        _INNER_TRIAL_DIR.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        usage = s1.get("llm_usage") or {}
        row = {
            "time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "scheme": s1.get("inner_scheme"),
            "query": req.query,
            "outline_nature": req.outline_nature,
            "outline_nature_used": _norm_nature(req.outline_nature),
            "burden_description": req.burden_description,
            "revelation": s1.get("revelation", []),
            "inner": s1.get("inner", []),
            "experience": s1.get("experience", []),
            "practice": s1.get("practice", []),
            "reasoning": s1.get("reasoning", ""),
            "thinking_text": s1.get("thinking_text", ""),
            "dropped": s1.get("dropped", []),
            "truncated": s1.get("truncated", []),
            "inner_words_count": s1.get("inner_words_count"),
            "model": s1.get("model"),
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "cost_usd": usage.get("cost_usd"),
            "elapsed_ms": s1.get("elapsed_ms"),
            "error": s1.get("error"),
        }
        path = _INNER_TRIAL_DIR / f"inner-{now.strftime('%Y%m%d')}.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("[t35test INNER] 记录推荐结果失败（不影响返回）: %s", e)


@router.get("/concepts/search")
async def search_concepts(
    q: str = Query("", description="概念关键词"),
    limit: int = Query(20, ge=1, le=100, description="返回数量上限"),
):
    """按关键词搜索图谱概念名称。"""
    key = (q or "").strip()
    if not key:
        return {"results": []}
    return {"results": get_neo4j().search_concepts_by_name(key, limit=limit)}


@router.post("/cache_translation")
async def cache_translation(req: CacheTranslationRequest):
    """追加/更新缓存中的英文或繁体纲目翻译（t35test 自己的缓存键）。"""
    if req.field not in ("answer_en", "answer_zh_tw"):
        return JSONResponse(status_code=400, content={"error": "field must be answer_en or answer_zh_tw"})
    ok = KgRagService.update_cache_translation(req.cache_key, req.field, req.value)
    return {"ok": ok, "cache_key": req.cache_key, "field": req.field}


# ---------------------------------------------------------------------------
# 翻译 / 繁体 / 格式化
# ---------------------------------------------------------------------------
@router.post("/translate_outline", summary="将中文纲目翻译为英文纲目")
async def translate_outline(request: TranslateOutlineRequest):
    try:
        return await asyncio.to_thread(translate_service.translate_outline, request.chinese_outline, request.outline_topic)
    except Exception as e:
        logger.error(f"翻译纲目失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/outline_to_traditional", summary="简体纲目转台湾繁体")
async def outline_to_traditional(request: OutlineToTraditionalRequest):
    try:
        result = await asyncio.to_thread(translate_service.outline_to_traditional, request.content)
        if result.get("error") and result.get("answer_zh_tw") is None:
            raise HTTPException(status_code=400, detail=result.get("error"))
        return result
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"简转繁失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/format_outline_only", summary="仅格式化已翻译的纲目（不调用翻译 API）")
async def format_outline_only(request: FormatOutlineRequest):
    try:
        result = await asyncio.to_thread(
            translate_service.format_outline_only,
            request.direction,
            request.translated_text,
            request.output_format,
            request.is_outline,
        )
        if result.get("error") and not (result.get("docx_bytes") or result.get("pdf_bytes")):
            raise HTTPException(status_code=400, detail=result.get("error"))
        response_data = {"error": result.get("error")}
        if request.output_format == "pdf":
            if result.get("pdf_bytes"):
                response_data["pdf_base64"] = base64.b64encode(result["pdf_bytes"]).decode("utf-8")
                response_data["filename"] = result.get("filename", "outline.pdf")
            elif result.get("docx_bytes"):
                response_data["docx_base64"] = base64.b64encode(result["docx_bytes"]).decode("utf-8")
                response_data["filename"] = result.get("filename", "outline.docx").replace(".pdf", ".docx")
        else:
            if result.get("docx_bytes"):
                response_data["docx_base64"] = base64.b64encode(result["docx_bytes"]).decode("utf-8")
                response_data["filename"] = result.get("filename", "outline.docx")
        return response_data
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"format_outline_only 失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# 纲目评估
# ---------------------------------------------------------------------------
def _to_request_data(body: EvalRequest) -> dict[str, Any]:
    return {
        "answer": body.answer,
        "query": body.query,
        "outline_nature": _norm_nature(body.outline_nature),
        "burden_description": body.burden_description,
        "revelation": "\n".join(body.revelation),
        "experience": "\n".join(body.experience),
        "practice": "\n".join(body.practice),
        "skeleton": body.skeleton,
    }


@router.post("/eval/outline", summary="纲目品质评估（F1-F4 + T1-T4）")
async def evaluate_outline(body: EvalRequest) -> dict[str, Any]:
    try:
        is_second_eval = body.eval_v1 is not None
        return await run_evaluation(_to_request_data(body), is_second_eval=is_second_eval, eval_v1=body.eval_v1)
    except HTTPException:
        raise
    except Exception as e:
        logger.error("t35test outline_eval 失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e
