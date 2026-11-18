# -*- coding: utf-8 -*-
"""【3.5测试用】的独立接口：/api/t35test。

主站“AI纲目制作面板”用到的全部后端能力的完整副本，与主站 3.5（/api/kg_rag、/api/ai_search、/api/eval）
互不引用、互不影响：
  - KG-RAG 核心：query / generate_burden / extract_concepts / concepts/search / cache_translation
  - 翻译、繁体转换、格式化下载：translate_outline / outline_to_traditional / format_outline_only
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

from contextlib import contextmanager

from fastapi import Header
from user.token import require_admin, test_token
from t35test import usage_store
from t35test.effort import normalize_effort, reset_effort, set_effort
from t35test.common import get_monitoring
from t35test.kg.firewall import load_firewall
from t35test.kg.kg_rag_service import KgRagService, strip_outline_tail
from t35test.kg.neo4j_client import Neo4jClient
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
        load_firewall(_neo4j)  # 【4.0】防火墙改读图谱 neo4j-v4 的「神圣的辩理」标注
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


# ---------------------------------------------------------------------------
# 【4.0】作纲目费用统计：一篇纲目一个「本篇编号」（请求头 X-T35-Outline-Session），
# 负担说明 / 推荐重点 / 生成纲目每次请求都记下实际花的钱（t35test/usage_store.py）。
# ---------------------------------------------------------------------------
class OutlineCtx(BaseModel):
    session_id: str = ""
    loaded: bool = False
    device: str = ""
    username: str = ""
    effort: Optional[str] = None  # 页面「思考程度」：low = Opus 5.5 用低；None = 预设（中）


@contextmanager
def _effort_scope(ctx: "OutlineCtx"):
    """这次请求里所有 Opus 5.5 调用都用 ctx.effort（None 时什么都不送，和原来一样）。"""
    token = set_effort(ctx.effort)
    try:
        yield
    finally:
        reset_effort(token)


def _outline_ctx(
    userinfo: dict = Depends(test_token),
    x_t35_outline_session: Optional[str] = Header(default=None),
    x_t35_outline_loaded: Optional[str] = Header(default=None),
    x_t35_device: Optional[str] = Header(default=None),
    x_t35_effort: Optional[str] = Header(default=None),
) -> OutlineCtx:
    def _clean(v: Optional[str]) -> str:
        v = (v or "").strip()
        return v if (len(v) <= 64 and all(c.isalnum() or c == "-" for c in v)) else ""

    return OutlineCtx(
        session_id=_clean(x_t35_outline_session),
        loaded=(x_t35_outline_loaded or "").strip() == "1",
        device=_clean(x_t35_device),
        username=userinfo.get("username", ""),
        effort=normalize_effort(x_t35_effort),
    )


async def _record_usage(ctx: OutlineCtx, kind: str, query: str, nature: str, elapsed_ms: float, calls: list, cached: bool = False) -> None:
    """记一次请求实际花的钱；没有本篇编号（旧页面）也照记，只是不能按篇加总。出错不影响返回。"""
    try:
        await asyncio.to_thread(
            usage_store.record_request,
            session_id=ctx.session_id or f"nosession-{int(datetime.now().timestamp() * 1000)}",
            kind=kind,
            username=ctx.username,
            device=ctx.device,
            query=query,
            outline_nature=nature,
            loaded=ctx.loaded,
            cached=cached,
            elapsed_ms=elapsed_ms,
            calls=calls,
            effort=ctx.effort or "",
        )
    except Exception as e:
        logger.warning("[t35test usage] 记录费用失败（不影响返回）: %s", e)


def _now_ms() -> float:
    return datetime.now().timestamp() * 1000


class QueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=500, description="查询问题")
    params: Optional[dict] = Field(default=None, description="覆盖默认参数")
    mode: str = "4.0"  # 【4.0】只为兼容保留，后端一律走 4.0


class CacheTranslationRequest(BaseModel):
    cache_key: str = Field(..., min_length=1, description="缓存 key（panai4:cache:...）")
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
    mode: str = "4.0"  # 【4.0】只为兼容保留，后端一律走 4.0


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


# ---------------------------------------------------------------------------
# KG-RAG 核心
# ---------------------------------------------------------------------------
@router.post("/query")
async def full_query(req: QueryRequest, ctx: OutlineCtx = Depends(_outline_ctx)):
    """全流程查询 Step 1→5。"""
    service = get_service()
    try:
        params = dict(req.params or {})
        if "outline_nature" in params:
            params["outline_nature"] = _norm_nature(params["outline_nature"])
        t0 = _now_ms()
        with _effort_scope(ctx):
            result = await service.full_query(req.query, params, mode=req.mode)
        cached = bool((result or {}).get("cached"))
        if isinstance(result, dict):
            result["effort"] = ctx.effort or ""  # 页面显示这篇用的思考程度
        await _record_usage(
            ctx, "outline", req.query, params.get("outline_nature") or "", _now_ms() - t0,
            [] if cached else (((result or {}).get("llm_usage") or {}).get("calls") or []),
            cached=cached,
        )
        return result
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})


@router.post("/generate_burden")
async def generate_burden(req: GenerateBurdenRequest, ctx: OutlineCtx = Depends(_outline_ctx)):
    """根据主题与上下文生成负担说明（有负担的重点 → 单条 / 没有负担的重点 → 三候选）。"""
    service = get_service()
    try:
        t0 = _now_ms()
        logger.info(
            "[t35test BURDEN] /generate_burden req: query_len=%s outline=%r excerpt_len=%s model=%s",
            len((req.query or "").strip()),
            _norm_nature(req.outline_nature or ""),
            len((req.reference_excerpt or "").strip()),
            req.model,
        )
        with _effort_scope(ctx):
            result = await service.generate_burden_description(
                req.query,
                outline_nature=_norm_nature(req.outline_nature),
                audience=req.audience,
                reference_excerpt=req.reference_excerpt,
                model=req.model,
            )
        _record_burden_trial(req, result)
        bu = (result or {}).get("llm_usage")
        await _record_usage(
            ctx, "burden", req.query, _norm_nature(req.outline_nature or ""), _now_ms() - t0,
            [{**bu, "step": "generate_burden"}] if isinstance(bu, dict) else [],
        )
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
async def extract_concepts(req: ExtractConceptsRequest, ctx: OutlineCtx = Depends(_outline_ctx)):
    """独立执行 Step 1 概念抽取，返回 revelation / experience / practice 候选列表，供人工筛选。"""
    service = get_service()
    try:
        t0 = _now_ms()
        with _effort_scope(ctx):
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
        await _record_usage(
            ctx, "concepts", req.query, _norm_nature(req.outline_nature), _now_ms() - t0,
            ((result or {}).get("llm_usage") or {}).get("calls") or [],
        )
        return {
            "revelation": s1.get("revelation", []),
            "inner": s1.get("inner", []),
            "experience": s1.get("experience", []),
            "practice": s1.get("practice", []),
            "summary": s1.get("summary", ""),  # 小结（原 reasoning）
            "key_verses": s1.get("key_verses", []),  # 关键圣经节（可选）
            "thinking_text": s1.get("thinking_text", ""),
            "thinking_text_zh": s1.get("thinking_text_zh", ""),
            "dropped": s1.get("dropped", []),
            "truncated": s1.get("truncated", []),
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
            "summary": s1.get("summary", ""),
            "key_verses": s1.get("key_verses", []),
            "thinking_text": s1.get("thinking_text", ""),
            "thinking_text_zh": s1.get("thinking_text_zh", ""),
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


@router.get("/concepts/search_v4")
async def search_truth_points(
    q: str = Query("", description="词条关键词"),
    limit: int = Query(20, ge=1, le=100, description="返回数量上限"),
):
    """「搜索图谱中重点」：按关键词搜索 neo4j-v4 的 2,372 个词条名称。"""
    key = (q or "").strip()
    if not key:
        return {"results": []}
    return {"results": get_neo4j().search_truth_points_by_name(key, limit=limit)}


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
            strip_outline_tail(request.translated_text),  # 【新测试台】刷格式下载前去掉最后的参考与参读、说明
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

# 【4.0】纲目评估（/eval/outline 与 t35test/outline_eval）已于 2026-11-11 按用户要求删除；主站 3.0 的评估不受影响。


# ---------------------------------------------------------------------------
# 「暂时保存」历史记录：存在服务器上，按电脑分开（t35test/history_store.py）
# 前端每台电脑的浏览器生成一个本机编号，放在请求头 X-T35-Device；同一台电脑的几个窗口共用、同步，
# 别的电脑的记录看不到也动不到。
# ---------------------------------------------------------------------------
from t35test import history_store  # noqa: E402


def _device(x_t35_device: Optional[str] = Header(default=None)) -> str:
    d = (x_t35_device or "").strip()
    if not (8 <= len(d) <= 64) or not all(c.isalnum() or c == "-" for c in d):
        raise HTTPException(status_code=400, detail="缺少本机编号，请刷新页面再试")
    return d


class HistoryCreateRequest(BaseModel):
    record: dict[str, Any]


class HistoryImportRequest(BaseModel):
    records: list[dict[str, Any]] = Field(default_factory=list)


class HistoryUpdateRequest(BaseModel):
    fields: dict[str, Any]


@router.get("/history")
def history_list(device: str = Depends(_device)):
    """本机的历史记录（新的在前；不带思考过程、纲目全文等大字段）。"""
    try:
        return {"records": history_store.list_records(device, light=True)}
    except Exception as e:
        logger.error(f"[t35test history] 读取失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"读取历史记录失败：{e}")


@router.post("/history")
def history_create(req: HistoryCreateRequest, userinfo: dict = Depends(test_token), device: str = Depends(_device)):
    """新增一条（记在本机编号下）；返回实际使用的 id（若撞号会换一个）。"""
    try:
        rid = history_store.create_record(req.record, userinfo.get("username", ""), device)
        return {"id": rid}
    except Exception as e:
        logger.error(f"[t35test history] 新增失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"保存历史记录失败：{e}")


@router.post("/history/import")
def history_import(req: HistoryImportRequest, userinfo: dict = Depends(test_token), device: str = Depends(_device)):
    """把本机浏览器里原有的旧记录搬上来，记在本机编号下（id 已有的跳过，不会重复）。"""
    try:
        res = history_store.import_records(req.records, userinfo.get("username", ""), device)
        logger.info("[t35test history] 导入旧记录 user=%s %s", userinfo.get("username"), res)
        return res
    except Exception as e:
        logger.error(f"[t35test history] 导入失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"导入旧记录失败：{e}")


@router.patch("/history/{rid}")
def history_update(rid: int, req: HistoryUpdateRequest, userinfo: dict = Depends(test_token), device: str = Depends(_device)):
    """只改传进来的字段；只能改本机的记录。"""
    try:
        ok = history_store.update_record(rid, req.fields, userinfo.get("username", ""), device)
    except Exception as e:
        logger.error(f"[t35test history] 修改失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"修改历史记录失败：{e}")
    if not ok:
        raise HTTPException(status_code=404, detail="这条记录已不存在（可能已被别的窗口删除）")
    return {"ok": True}


@router.delete("/history/{rid}")
def history_delete(rid: int, device: str = Depends(_device)):
    """只能删本机的记录。"""
    try:
        history_store.delete_record(rid, device)
        return {"ok": True}
    except Exception as e:
        logger.error(f"[t35test history] 删除失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"删除历史记录失败：{e}")


# ---------------------------------------------------------------------------
# 【4.0】作纲目费用：页面查本篇完整费用；后台「4.0作纲目」统计（t35test/usage_store.py）
# ---------------------------------------------------------------------------
@router.get("/usage/session/{session_id}")
def usage_session(session_id: str):
    """这一篇从头做到尾的完整费用（负担说明、推荐重点、生成纲目，重做的也都算进去）和各步骤明细。"""
    try:
        s = usage_store.session_summary(session_id)
    except Exception as e:
        logger.error(f"[t35test usage] 读取本篇费用失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"读取本篇费用失败：{e}")
    if not s:
        raise HTTPException(status_code=404, detail="找不到这一篇的费用记录")
    return s


@router.get("/usage/stats", dependencies=[Depends(require_admin)])
def usage_stats(days: int = Query(7, ge=1, le=3650)):
    """后台「4.0作纲目」使用统计（只给管理员）。"""
    try:
        return usage_store.stats(days)
    except Exception as e:
        logger.error(f"[t35test usage] 统计失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"统计失败：{e}")
