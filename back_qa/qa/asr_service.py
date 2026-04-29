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
2. 修正明显的同音字错误，前提是你对正确写法有把握，例如：
   - 圣经书卷名（旧约）：创世记、出埃及记、利未记、民数记、申命记、约书亚记、士师记、路得记、撒母耳记上、撒母耳记下、列王记上、列王记下、历代志上、历代志下、以斯拉记、尼希米记、以斯帖记、约伯记、诗篇、箴言、传道书、雅歌、以赛亚书、耶利米书、耶利米哀歌、以西结书、但以理书、何西阿书、约珥书、阿摩司书、俄巴底亚书、约拿书、弥迦书、那鸿书、哈巴谷书、西番雅书、哈该书、撒迦利亚书、玛拉基书
   - 圣经书卷名（新约）：马太福音、马可福音、路加福音、约翰福音、使徒行传、罗马书、哥林多前书、哥林多后书、加拉太书、以弗所书、腓立比书、歌罗西书、帖撒罗尼迦前书、帖撒罗尼迦后书、提摩太前书、提摩太后书、提多书、腓利门书、希伯来书、雅各书、彼得前书、彼得后书、约翰壹书、约翰贰书、约翰叁书、犹大书、启示录
   - 人名：亚伯拉罕、以撒、雅各、约瑟、摩西、约书亚、大卫、所罗门、以利亚、以利沙、以赛亚、耶利米、以西结、但以理、约拿、彼得、保罗、约翰、马太、马可、路加、雅各、巴拿巴、提摩太、提多、腓利门、倪柝声、李常受
   - 地名：耶路撒冷、伯大尼、迦南、西乃山、橄榄山、约但河、加利利、伯利恒、大马色、以弗所、哥林多、腓立比、帖撒罗尼迦、以弗所、士每拿、别迦摩、推雅推喇、撒狄、非拉铁非、老底嘉
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
