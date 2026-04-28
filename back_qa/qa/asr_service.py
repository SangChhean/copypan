# -*- coding: utf-8 -*-
"""ASR service: OpenAI Whisper transcription."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path

from openai import AsyncOpenAI

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        if not api_key:
            raise RuntimeError("未配置 OPENAI_API_KEY")
        _client = AsyncOpenAI(api_key=api_key)
    return _client


def _build_prompt() -> str:
    prefix = "以下是简体中文内容。"
    cfg_path = Path(__file__).resolve().parents[1] / "asr_corrections.json"
    if not cfg_path.exists():
        return prefix
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
    except Exception:
        return prefix
    hints = data.get("hints", [])
    if not isinstance(hints, list):
        return prefix
    words = [str(x).strip() for x in hints if str(x).strip()]
    return prefix + "、".join(words) if words else prefix


async def transcribe(audio_bytes: bytes, filename: str) -> str:
    client = _get_client()
    prompt = _build_prompt()

    file_obj = io.BytesIO(audio_bytes)
    file_obj.name = filename or "audio.webm"

    response = await client.audio.transcriptions.create(
        model="whisper-1",
        file=file_obj,
        language="zh",
        prompt=prompt,
    )
    return (getattr(response, "text", "") or "").strip()
