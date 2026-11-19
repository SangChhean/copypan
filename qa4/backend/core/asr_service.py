# -*- coding: utf-8 -*-
"""语音转写：OpenAI gpt-4o-transcribe + Haiku 保守校对。

改写自 3.0 back_qa/qa/asr_service.py；不 import back_qa。
依赖：OPENAI_API_KEY；校对用 QA4_ANTHROPIC_API_KEY / ANTHROPIC_API_KEY / CLAUDE_API_KEY。
"""

from __future__ import annotations

import io
import json
import logging
import os
from pathlib import Path

logger = logging.getLogger("qa4.asr")

_client = None
_CORRECTIONS = Path(__file__).resolve().parents[1] / "asr_corrections.json"


def _get_openai():
    global _client
    if _client is None:
        # 先查密钥再 import：缺 key 时返回明确 RuntimeError（路由 → 503），
        # 避免本机未装 openai 包时变成 ModuleNotFoundError → 500。
        api_key = (os.environ.get("OPENAI_API_KEY") or os.environ.get("QA4_OPENAI_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError("未配置 OPENAI_API_KEY")
        from openai import AsyncOpenAI

        _client = AsyncOpenAI(api_key=api_key)
    return _client


def _build_prompt() -> str:
    prefix = "以下是简体中文内容。"
    if not _CORRECTIONS.is_file():
        return prefix
    try:
        data = json.loads(_CORRECTIONS.read_text(encoding="utf-8"))
    except Exception:
        return prefix
    hints = data.get("hints", [])
    if not isinstance(hints, list):
        return prefix
    words = [str(x).strip() for x in hints if str(x).strip()]
    return prefix + "、".join(words) if words else prefix


async def correct_transcript(text: str) -> str:
    if not text.strip():
        return text
    prompt = f"""你是语音转写文本的保守校对助手。你的核心原则是：**不确定就不改**。

请对以下语音转写文本进行校对，只允许：繁体改简体；有把握的同音字/专有词修正。
严格禁止猜测改写、扩写、润色。不确定则原样保留。
只返回校对后的文本，不要解释。

待校对文本：{text}"""
    try:
        from anthropic import AsyncAnthropic

        api_key = (
            os.environ.get("QA4_ANTHROPIC_API_KEY")
            or os.environ.get("ANTHROPIC_API_KEY")
            or os.environ.get("CLAUDE_API_KEY")
            or ""
        ).strip()
        if not api_key:
            return text
        client = AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        corrected = (response.content[0].text or "").strip()
        return corrected if corrected else text
    except Exception as e:
        logger.warning("ASR 校对失败: %s", e)
        return text


async def transcribe(audio_bytes: bytes, filename: str) -> str:
    client = _get_openai()
    prompt = _build_prompt()
    file_obj = io.BytesIO(audio_bytes)
    file_obj.name = filename or "audio.webm"
    response = await client.audio.transcriptions.create(
        model="gpt-4o-transcribe",
        file=file_obj,
        language="zh",
        prompt=prompt,
    )
    result = response.text.strip() if hasattr(response, "text") else str(response).strip()
    if prompt and len(result) > 10:
        if result.startswith("以下是简体中文内容"):
            raise ValueError("ASR 输出异常，疑似返回提示词")
    corrected = await correct_transcript(result)
    return corrected
