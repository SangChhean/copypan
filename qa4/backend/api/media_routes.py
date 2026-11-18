# -*- coding: utf-8 -*-
"""三语翻译、朗读 TTS、语音 ASR（对照 3.0 /api/qa/translate|tts*|asr）。"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from api.deps import require_user

logger = logging.getLogger("qa4.media")

router = APIRouter(prefix="/api", tags=["media"])


class TranslateRequest(BaseModel):
    text: str = ""
    sources: list[str] = Field(default_factory=list)
    target_lang: str  # zh_tw | en
    question: str = ""
    cache_key: str = ""


class TTSRequest(BaseModel):
    text: str
    lang: str = "zh"  # zh | zh_tw | en


def _clean_tts_text(text: str) -> str:
    clean = text or ""
    clean = re.sub(r"\*{1,3}([^*]+)\*{1,3}", r"\1", clean)
    clean = re.sub(r"#{1,6}\s*", "", clean)
    clean = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", clean)
    clean = re.sub(r"`{1,3}[^`]*`{1,3}", "", clean)
    return clean.strip()


@router.post("/translate")
def translate(req: TranslateRequest, username: str = Depends(require_user)):
    from core.translate import translate_answer

    lang = (req.target_lang or "").strip()
    if lang not in {"zh_tw", "en"}:
        raise HTTPException(status_code=400, detail={"message": "target_lang 须为 zh_tw 或 en"})
    try:
        return translate_answer(text=req.text, sources=req.sources, target_lang=lang)
    except ValueError as e:
        raise HTTPException(status_code=400, detail={"message": str(e)}) from e
    except RuntimeError as e:
        # 缺 key 等
        raise HTTPException(status_code=503, detail={"message": str(e)}) from e
    except Exception:
        logger.exception("translate failed")
        raise HTTPException(status_code=500, detail={"message": "翻译失败，请稍后重试"})


@router.post("/tts/minimax")
async def tts_minimax(req: TTSRequest, username: str = Depends(require_user)):
    """MiniMax 朗读（3.0 默认开启的引擎）。依赖 MINIMAX_API_KEY + MINIMAX_GROUP_ID。"""
    import httpx

    api_key = (os.environ.get("MINIMAX_API_KEY") or os.environ.get("QA4_MINIMAX_API_KEY") or "").strip()
    group_id = (os.environ.get("MINIMAX_GROUP_ID") or os.environ.get("QA4_MINIMAX_GROUP_ID") or "").strip()
    if not api_key or not group_id:
        raise HTTPException(
            status_code=503,
            detail={"message": "MINIMAX_API_KEY 或 MINIMAX_GROUP_ID 未配置"},
        )

    clean_text = _clean_tts_text(req.text)
    if not clean_text:
        raise HTTPException(status_code=400, detail={"message": "清洗后文本为空"})

    voice_id = "English_Graceful_Lady" if req.lang == "en" else "Chinese (Mandarin)_Kind-hearted_Antie"
    payload = {
        "model": "speech-02-hd",
        "text": clean_text,
        "stream": False,
        "voice_setting": {"voice_id": voice_id, "speed": 1.0, "vol": 1.0, "pitch": 0},
        "audio_setting": {"sample_rate": 32000, "bitrate": 128000, "format": "mp3"},
    }

    async def audio_stream():
        url = f"https://api-uw.minimax.io/v1/t2a_v2?GroupId={group_id}"
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json=payload,
            )
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=500,
                    detail={"message": f"MiniMax TTS 失败：{resp.text[:200]}"},
                )
            data = resp.json()
            hex_audio = data.get("data", {}).get("audio", "")
            if not hex_audio:
                raise HTTPException(status_code=500, detail={"message": "MiniMax 响应无音频数据"})
            audio_bytes = bytes.fromhex(hex_audio)
            for i in range(0, len(audio_bytes), 4096):
                yield audio_bytes[i : i + 4096]

    return StreamingResponse(audio_stream(), media_type="audio/mpeg")


@router.post("/asr")
async def asr_transcribe(
    username: str = Depends(require_user),
    file: UploadFile = File(...),
):
    """浏览器 MediaRecorder 上传 → gpt-4o-transcribe。依赖 OPENAI_API_KEY。"""
    from core import asr_service

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail={"message": "空音频"})
    try:
        text = await asr_service.transcribe(content, file.filename or "audio.webm")
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail={"message": str(e)}) from e
    except Exception as e:
        logger.exception("asr failed")
        raise HTTPException(status_code=500, detail={"message": f"识别失败：{type(e).__name__}"}) from e
    return {"text": text}
