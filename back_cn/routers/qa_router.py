# -*- coding: utf-8 -*-
"""CN 站 QA 路由（路径保持 /api/qa/*，鉴权与配额走 back_cn.auth）。"""
import json
import os
import re
import unicodedata
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Request, HTTPException, Depends, UploadFile, File
from fastapi.responses import JSONResponse, Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field, field_validator
from sse_starlette.sse import EventSourceResponse

from back_qa.qa.rate_limit import check_rate_limit, check_prompt_injection
from back_cn.auth import (
    check_and_increment_daily_usage,
    get_current_user,
    quota_exceeded_message,
    _check_admin_access,
    verify_admin_access,
)

router = APIRouter()
_bearer = HTTPBearer()


# ---------- 请求 / 响应模型 ----------


class HistoryTurn(BaseModel):
    question: str
    answer: str


class DebugParams(BaseModel):
    bm25_top_k: int = 30
    dense_top_k: int = 30
    expansion_top_n: int = 5
    rerank_top_n: int = 20


class QueryRequest(BaseModel):
    question: str
    skip_cache: bool = False
    debug: bool = False
    params: DebugParams = DebugParams()
    history: list[HistoryTurn] = Field(default_factory=list)

    @field_validator("question")
    @classmethod
    def validate_question(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("question 不能为空")
        if len(v) > 500:
            raise ValueError("question 不能超过 500 字")
        return v


class QueryResponse(BaseModel):
    request_id: str
    answer: str
    sources: list[str]
    concepts: list[str]
    found: bool
    cache_hit: bool
    total_elapsed_ms: int
    total_cost_usd: float
    bibliography: list[str] | None = None
    verse: dict[str, Any] | None = None
    intent: str | None = None
    debug: dict[str, Any] | None = None


class FeedbackRequest(BaseModel):
    request_id: str
    question: str
    answer: str
    rating: int  # 1 或 -1


class TranslateRequest(BaseModel):
    text: str
    sources: list[str] = Field(default_factory=list)
    target_lang: str
    question: str = ""
    cache_key: str = ""

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        v = v or ""
        if not v.strip():
            raise ValueError("text 不能为空")
        if len(v) > 20000:
            raise ValueError("text 过长（超过 20000 字符）")
        return v

    @field_validator("target_lang")
    @classmethod
    def validate_target_lang(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if v not in ("zh_tw", "en"):
            raise ValueError("target_lang 仅支持 zh_tw / en")
        return v


class TTSRequest(BaseModel):
    text: str
    lang: str = "zh"

    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        v = v or ""
        if not v.strip():
            raise ValueError("text 不能为空")
        if len(v) > 10000:
            raise ValueError("text 过长")
        return v

    @field_validator("lang")
    @classmethod
    def validate_lang(cls, v: str) -> str:
        if v not in ("zh", "zh_tw", "en"):
            raise ValueError("lang 仅支持 zh / zh_tw / en")
        return v


class TranslateResponse(BaseModel):
    answer: str
    sources: list[str]


# ---------- 工具函数 ----------

def _resolve_request_id(request: Request) -> str:
    """从 X-Request-ID 头读取，合法则复用，否则生成新 UUID。"""
    raw = request.headers.get("X-Request-ID", "")
    try:
        return str(uuid.UUID(raw))
    except (ValueError, AttributeError):
        return str(uuid.uuid4())


def _keep_char(c: str) -> bool:
    cat = unicodedata.category(c)
    if cat.startswith('L'):
        return True  # 字母
    if cat.startswith('N'):
        return True  # 数字
    if c in '\n\r\t ':
        return True  # 空白
    if c in '…—～·':
        return True  # 特殊标点
    # 只保留常用标点，排除数学括号(Ps/Pe)和数学符号(Sm/So/Sk)
    if cat in ('Po', 'Pd', 'Pi', 'Pf'):
        return True  # 普通/连字/引号标点
    if c in "，。！？、；：（）,.!?;:()'\"": 
        return True  # 明确保留的中英文标点
    return False


# 强制断句：把超过100字的连续非句末标点文本在逗号处截断，防止 Google TTS 报句子过长
def _force_break_long_sentences(text: str, max_len: int = 100) -> str:
    result = []
    for line in text.split('\n'):
        if len(line) <= max_len:
            result.append(line)
            continue
        # 在逗号、顿号、分号处插入换行
        broken = re.sub(r'([，、；,;])', r'\1\n', line)
        parts = [p for p in broken.split('\n') if p.strip()]
        result.extend(parts)
    return '\n'.join(result)


# ---------- 接口 ----------

@router.get("/liveness")
async def liveness():
    """轻量存活探针，仅检查进程。"""
    return {"status": "ok"}


@router.get("/readiness")
async def readiness(request: Request):
    """就绪探针：检查各依赖项状态与数据基线。"""
    from back_qa.qa.dependencies import get_es_client, get_redis_client
    from back_shared.version_manifest import PROMPT_VERSION, MODEL_PROFILE, FIREWALL_RULES_VERSION

    # Neo4j
    neo4j = getattr(request.app.state, "neo4j_client", None)
    neo4j_status = "connected" if neo4j and neo4j._available else "unavailable"

    # ES
    try:
        es = get_es_client()
        es.cluster.health(request_timeout=3)
        es_status = "connected"
    except Exception:
        es_status = "unavailable"

    # Redis
    try:
        r = get_redis_client()
        redis_status = "connected" if r is not None else "unavailable"
    except Exception:
        redis_status = "unavailable"

    overall = "ok" if all(
        s == "connected" for s in [neo4j_status, es_status, redis_status]
    ) else "degraded"

    baseline = getattr(request.app.state, "data_baseline", {})
    updated_at = getattr(request.app.state, "baseline_updated_at", "")

    return {
        "status": overall,
        "neo4j": neo4j_status,
        "elasticsearch": es_status,
        "redis": redis_status,
        "data_baseline": {
            "concept_total": baseline.get("concept_total", -1),
            "concept_with_greek_terms": baseline.get("concept_with_greek_terms", -1),
            "baseline_updated_at": updated_at,
            "prompt_version": PROMPT_VERSION,
            "model_profile": MODEL_PROFILE,
            "firewall_rules_version": FIREWALL_RULES_VERSION,
        },
    }


@router.post("/query", response_model=QueryResponse)
async def query(req: QueryRequest, request: Request):
    """提交问题，返回答案。流水线实现在 qa_service。"""
    from back_qa.qa.qa_service import run_pipeline
    from back_qa.qa.dependencies import get_redis_client

    get_current_user(request)
    _check_admin_access(request)
    if not check_rate_limit(request, get_redis_client()):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
    if not check_prompt_injection(req.question):
        raise HTTPException(status_code=400, detail="输入包含不支持的内容")

    request_id = _resolve_request_id(request)
    history_payload = [{"question": h.question, "answer": h.answer} for h in req.history]
    result = await run_pipeline(
        question=req.question,
        skip_cache=req.skip_cache,
        request_id=request_id,
        app=request.app,
        debug=req.debug,
        debug_params=req.params.model_dump(),
        history=history_payload,
    )
    return QueryResponse(**result)


@router.post("/stream")
async def stream_answer(req: QueryRequest, request: Request):
    """流式问答（SSE）。Steps 0–3 与 /query 一致；非缓存时 Step4 逐 token 推送。缓存命中仅返回一条 done。"""
    from back_qa.qa.qa_service import stream_query
    from back_qa.qa.dependencies import get_redis_client

    username = get_current_user(request)["username"]
    usage = check_and_increment_daily_usage(username, "qa")
    if not usage["allowed"]:
        raise HTTPException(
            status_code=429,
            detail=quota_exceeded_message("qa", usage["limit"]),
        )
    if not check_rate_limit(request, get_redis_client()):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
    if not check_prompt_injection(req.question):
        raise HTTPException(status_code=400, detail="输入包含不支持的内容")

    request_id = _resolve_request_id(request)
    history_payload = [{"question": h.question, "answer": h.answer} for h in req.history]

    async def event_generator():
        try:
            async for chunk in stream_query(
                question=req.question,
                skip_cache=req.skip_cache,
                request_id=request_id,
                app=request.app,
                history=history_payload,
                debug=req.debug,
                debug_params=req.params.model_dump(),
            ):
                yield {"data": json.dumps(chunk, ensure_ascii=False)}
        except Exception as e:
            yield {"data": json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False)}

    return EventSourceResponse(event_generator())


@router.post("/translate", response_model=TranslateResponse)
async def translate(req: TranslateRequest, request: Request):
    """按需翻译已生成的简体答案。
    - zh_tw：OpenCC + 术语表本地转换，毫秒级
    - en：Gemini 翻译正文；书目从 Redis 缓存 passages 按 source_zh 匹配 source_en（需传 cache_key）
    主要用作前端答案下方简/繁/EN 切换时的兜底。
    """
    from back_qa.qa.qa_service import translate_answer
    from back_qa.qa.dependencies import get_redis_client

    get_current_user(request)
    if not check_rate_limit(request, get_redis_client()):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")

    try:
        result = await translate_answer(
            text=req.text,
            sources=req.sources,
            target_lang=req.target_lang,
            question=req.question,
            cache_key=req.cache_key,
        )
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=500, detail="翻译失败，请稍后重试")
    return result


@router.post("/tts")
async def text_to_speech(req: TTSRequest, request: Request):
    """TTS：调用 Gemini 3.1 Flash TTS，整段合成，返回 MP3。
    zh/zh_tw: 普通话女声 Leda
    en: 英文女声 Aoede
    """
    import httpx
    import base64
    import struct
    get_current_user(request)

    gemini_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not gemini_key:
        raise HTTPException(status_code=500, detail="GEMINI_API_KEY 未配置")

    # 音色选择：中文用 Achernar，英文用 Aoede
    voice_name = "Aoede" if req.lang == "en" else "Achernar"

    clean_text = req.text
    # 去除 Markdown 标记
    clean_text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', clean_text)
    clean_text = re.sub(r'#{1,6}\s*', '', clean_text)
    clean_text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', clean_text)
    clean_text = re.sub(r'`{1,3}[^`]*`{1,3}', '', clean_text)
    clean_text = clean_text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="清洗后文本为空")

    # 语言提示（帮助 Gemini 识别语言）
    lang_hint = {
        "zh": "请用标准普通话朗读以下文字，语调自然流畅：\n",
        "zh_tw": "請用標準普通話朗讀以下文字，語調自然流暢：\n",
        "en": "Please read the following text in natural English:\n",
    }
    prompt = lang_hint.get(req.lang, lang_hint["zh"]) + clean_text

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": voice_name}
                }
            }
        }
    }

    async def audio_stream():
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-3.1-flash-tts-preview:generateContent?key={gemini_key}"
        )
        print(f"[TTS Gemini] lang={req.lang} voice={voice_name} len={len(clean_text)}")
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code != 200:
                print(f"[TTS Gemini error]: {resp.text[:300]}")
                raise HTTPException(status_code=500, detail=f"Gemini TTS 失败：{resp.text[:200]}")
            data = resp.json()
            # 提取 PCM audio data
            try:
                b64_audio = (
                    data["candidates"][0]["content"]["parts"][0]
                    ["inlineData"]["data"]
                )
            except (KeyError, IndexError) as e:
                raise HTTPException(status_code=500, detail=f"Gemini TTS 响应解析失败：{e}")
            pcm_bytes = base64.b64decode(b64_audio)
            # PCM 转 WAV（24kHz 16bit mono）
            sample_rate = 24000
            num_channels = 1
            bits_per_sample = 16
            byte_rate = sample_rate * num_channels * bits_per_sample // 8
            block_align = num_channels * bits_per_sample // 8
            data_size = len(pcm_bytes)
            wav_header = struct.pack(
                '<4sI4s4sIHHIIHH4sI',
                b'RIFF', 36 + data_size, b'WAVE',
                b'fmt ', 16, 1, num_channels, sample_rate,
                byte_rate, block_align, bits_per_sample,
                b'data', data_size
            )
            wav_bytes = wav_header + pcm_bytes
            chunk_size = 4096
            for i in range(0, len(wav_bytes), chunk_size):
                yield wav_bytes[i:i + chunk_size]

    return StreamingResponse(audio_stream(), media_type="audio/wav")


@router.post("/tts/minimax")
async def text_to_speech_minimax(req: TTSRequest, request: Request):
    """MiniMax TTS：中文用 Kind-hearted Antie，英文用 Graceful Lady"""
    import httpx
    get_current_user(request)

    api_key = os.environ.get("MINIMAX_API_KEY", "").strip()
    group_id = os.environ.get("MINIMAX_GROUP_ID", "").strip()
    if not api_key or not group_id:
        raise HTTPException(status_code=500, detail="MINIMAX_API_KEY 或 MINIMAX_GROUP_ID 未配置")

    voice_id = "English_Graceful_Lady" if req.lang == "en" else "Chinese (Mandarin)_Kind-hearted_Antie"

    clean_text = req.text
    clean_text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', clean_text)
    clean_text = re.sub(r'#{1,6}\s*', '', clean_text)
    clean_text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', clean_text)
    clean_text = re.sub(r'`{1,3}[^`]*`{1,3}', '', clean_text)
    clean_text = clean_text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="清洗后文本为空")

    payload = {
        "model": "speech-02-hd",
        "text": clean_text,
        "stream": False,
        "voice_setting": {
            "voice_id": voice_id,
            "speed": 1.0,
            "vol": 1.0,
            "pitch": 0,
        },
        "audio_setting": {
            "sample_rate": 32000,
            "bitrate": 128000,
            "format": "mp3",
        },
    }

    async def audio_stream():
        url = f"https://api-uw.minimax.io/v1/t2a_v2?GroupId={group_id}"
        print(f"[TTS MiniMax] lang={req.lang} voice={voice_id} len={len(clean_text)}")
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            if resp.status_code != 200:
                print(f"[TTS MiniMax error]: {resp.text[:300]}")
                raise HTTPException(status_code=500, detail=f"MiniMax TTS 失败：{resp.text[:200]}")
            data = resp.json()
            hex_audio = data.get("data", {}).get("audio", "")
            if not hex_audio:
                raise HTTPException(status_code=500, detail="MiniMax 响应无音频数据")
            audio_bytes = bytes.fromhex(hex_audio)
            chunk_size = 4096
            for i in range(0, len(audio_bytes), chunk_size):
                yield audio_bytes[i:i + chunk_size]

    return StreamingResponse(audio_stream(), media_type="audio/mpeg")


@router.post("/tts/elevenlabs")
async def tts_elevenlabs(request: TTSRequest, current_user=Depends(get_current_user)):
    import httpx

    elevenlabs_api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    elevenlabs_voice_id = os.environ.get("ELEVENLABS_VOICE_ZH", "9lHjugDhwqoxA5MhX0az").strip()
    elevenlabs_model = os.environ.get("ELEVENLABS_MODEL", "eleven_v3").strip()
    if not elevenlabs_api_key:
        raise HTTPException(status_code=500, detail="ELEVENLABS_API_KEY 未配置")

    clean_text = request.text
    clean_text = re.sub(r'\*{1,3}([^*]+)\*{1,3}', r'\1', clean_text)
    clean_text = re.sub(r'#{1,6}\s*', '', clean_text)
    clean_text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', clean_text)
    clean_text = re.sub(r'`{1,3}[^`]*`{1,3}', '', clean_text)
    clean_text = clean_text.strip()
    if not clean_text:
        raise HTTPException(status_code=400, detail="清洗后文本为空")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{elevenlabs_voice_id}"
    payload = {
        "text": clean_text,
        "model_id": elevenlabs_model,
        "voice_settings": {
            "stability": 0.5,
            "similarity_boost": 0.75,
        },
    }
    headers = {
        "xi-api-key": elevenlabs_api_key,
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, headers=headers, json=payload)
        if resp.status_code != 200:
            print(f"[TTS ElevenLabs error] status={resp.status_code}: {resp.text[:500]}")
            raise HTTPException(status_code=500, detail="ElevenLabs TTS 失败")
        return Response(content=resp.content, media_type="audio/mpeg")
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[TTS ElevenLabs exception]: {type(e).__name__}: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail="ElevenLabs TTS 失败")


@router.post("/feedback")
async def submit_feedback(req: FeedbackRequest, request: Request):
    """提交答案质量反馈（需登录）。"""
    username = get_current_user(request)["username"]
    if req.rating not in (1, -1):
        raise HTTPException(status_code=400, detail="rating 只能是 1 或 -1")

    from back_qa.qa.auth import insert_feedback

    insert_feedback(
        request_id=(req.request_id or "").strip(),
        username=username,
        question=(req.question or "").strip(),
        answer=(req.answer or "").strip(),
        rating=req.rating,
    )
    return {"ok": True}


# ---------------------------------------------------------------------------
# 管理接口（X-Admin-Token 或 is_admin JWT）
# ---------------------------------------------------------------------------


@router.post("/cache/clear")
async def cache_clear(_: bool = Depends(verify_admin_access)):
    from back_qa.qa.dependencies import get_redis_client

    r = get_redis_client()
    if r is None:
        raise HTTPException(status_code=503, detail="Redis 不可用")
    prefix = os.environ.get("QA_REDIS_PREFIX", "qa:cache:")
    keys = r.keys(f"{prefix}*")
    deleted = 0
    if keys:
        deleted = r.delete(*keys)
    return {"deleted": deleted, "prefix": prefix}


@router.post("/stats/clear")
async def stats_clear(request: Request, _: bool = Depends(verify_admin_access)):
    from back_qa.qa.dependencies import get_redis_client
    from back_qa.qa.qa_service import _MONITOR_KEY

    r = get_redis_client()
    if r is None:
        raise HTTPException(status_code=503, detail="Redis 不可用")
    deleted = r.delete(_MONITOR_KEY)
    return {"deleted": bool(deleted), "key": _MONITOR_KEY}


@router.get("/stats")
async def stats(_: bool = Depends(verify_admin_access)):
    from back_qa.qa.dependencies import get_redis_client
    from back_qa.qa.qa_service import _MONITOR_KEY

    r = get_redis_client()
    if r is None:
        raise HTTPException(status_code=503, detail="Redis 不可用")

    raw_records = r.lrange(_MONITOR_KEY, 0, -1)
    records = []
    for raw in raw_records:
        try:
            records.append(json.loads(raw))
        except Exception:
            pass

    total = len(records)
    cache_hits = sum(1 for rec in records if rec.get("cache_hit"))
    found_non_cache = [rec for rec in records if not rec.get("cache_hit")]
    found_count = sum(1 for rec in found_non_cache if rec.get("found"))
    step_fail = [rec for rec in found_non_cache if not rec.get("found")]

    total_cost = sum(rec.get("total_cost_usd", 0) for rec in found_non_cache)
    avg_elapsed = (
        sum(rec.get("total_elapsed_ms", 0) for rec in found_non_cache) / len(found_non_cache)
        if found_non_cache
        else 0
    )

    return {
        "total_requests": total,
        "cache_hit_rate": round(cache_hits / total, 4) if total else 0,
        "found_rate_new": round(found_count / len(found_non_cache), 4) if found_non_cache else 0,
        "total_cost_usd": round(total_cost, 4),
        "avg_elapsed_ms": round(avg_elapsed),
        "step_fail_records": step_fail[-20:],  # 最近 20 条未找到记录
    }


@router.get("/feedback/stats")
async def feedback_stats(_: bool = Depends(verify_admin_access)):
    from back_qa.qa.auth import get_feedback_stats

    return get_feedback_stats()


@router.post("/asr")
async def asr_transcribe(
    request: Request,
    file: UploadFile = File(...),
    _: HTTPAuthorizationCredentials = Depends(_bearer),
):
    username = get_current_user(request)["username"]
    usage = check_and_increment_daily_usage(username, "asr")
    if not usage["allowed"]:
        raise HTTPException(
            status_code=429,
            detail=quota_exceeded_message("asr", usage["limit"]),
        )

    allowed_prefixes = (
        "audio/webm",
        "audio/wav",
        "audio/mp4",
        "audio/mpeg",
        "audio/ogg",
        "audio/x-m4a",
        "audio/m4a",
    )
    content_type = (file.content_type or "").lower().strip()
    if not any(content_type.startswith(p) for p in allowed_prefixes):
        raise HTTPException(status_code=400, detail="不支持的音频格式")

    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件大小不能超过 10MB")

    from back_qa.qa import asr_service

    try:
        text = await asr_service.transcribe(content, file.filename or "audio.webm")
        return {"text": text}
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="语音识别失败，请重试")
