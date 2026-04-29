# -*- coding: utf-8 -*-
"""ASR service: OpenAI Whisper transcription."""

from __future__ import annotations

import io
import json
import logging
import os
from pathlib import Path

from openai import AsyncOpenAI

_client: AsyncOpenAI | None = None
logger = logging.getLogger("qa")


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


async def correct_transcript(text: str) -> str:
    if not text.strip():
        return text
    prompt = f"""你是语音转写文本的保守校对助手。你的核心原则是：**不确定就不改**。

请对以下语音转写文本进行校对，只允许做以下修改：
1. 将繁体字统一改为简体字
2. 修正明显的同音字错误，前提是你对正确写法有把握，例如圣经书卷名、人名、地名等
3. 修正领域专有词，例如：「那灵」「经纶」「召会」「活力排」「职事」「擘饼」「李常受」「倪柝声」「恢复本圣经」「生命读经」「晨兴圣言」「爱有效能」「膏油」「吃基督」「享受基督」「神圣罗曼史」「雷玛」「吗哪」「成为一灵」「生机的救恩」「法理的救赎」「生命之灵的律」「总括时期」「末后的亚当」「高峰真理」等

严格禁止：
- 不得根据语义猜测并改写词组，例如不能将「火力牌」改为「召会牧养」
- 不得将专有词组改写为看似通顺的普通表达，例如不能将「爱有效能」改为「爱的功效」
- 不得补充、扩写、润色任何内容
- 不得调整语序
- 如果不确定某个词是否需要修改，原样保留

如果文本已经正确，原样返回；如果文本无法理解，原样返回原文，不要任何解释。
只返回校对后的文本，不要任何解释或前缀。

待校对文本：{text}"""
    try:
        import os
        from anthropic import AsyncAnthropic

        api_key = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("CLAUDE_API_KEY")
        client = AsyncAnthropic(api_key=api_key)
        response = await client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )
        corrected = (response.content[0].text or "").strip()
        logging.info(f"[ASR] Haiku 校对完成：{corrected[:50]}...")
        return corrected if corrected else text
    except Exception as e:
        logging.warning(f"[ASR] transcript correction failed: {e}")
        return text


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
    raw_text = (getattr(response, "text", "") or "").strip()
    logging.info(f"[ASR] Whisper 转写成功：{raw_text[:50]}...")
    corrected_text = await correct_transcript(raw_text)
    return corrected_text
