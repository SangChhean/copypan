# -*- coding: utf-8 -*-
"""Compare claude-opus-4-6 vs claude-opus-4-7 on a short Step1-style prompt."""
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[2] / "back_mic" / "backend" / ".env")

import anthropic

api_key = os.environ.get("CLAUDE_API_KEY", "")
if not api_key:
    raise SystemExit("CLAUDE_API_KEY missing")
client = anthropic.Anthropic(api_key=api_key)

prompt = """你是一位深研圣经与职事文献的神学助手。

用户提问：
神的经纶的中心是什么？

以下是职事信息概念词表（仅示例）：
- 神的经纶
- 基督
- 生命

请从上方词表中，识别出与该问题最相关的神学概念（1-5 个）。
只输出 JSON：{"concepts": ["概念A"], "reasoning": "说明"}"""

for model in ["claude-opus-4-6", "claude-opus-4-7"]:
    try:
        kwargs = dict(
            model=model,
            max_tokens=512,
            system="你是一位专业助手，只输出JSON。",
            messages=[{"role": "user", "content": prompt}],
        )
        if not model.startswith("claude-opus-4-7"):
            kwargs["temperature"] = 0
        msg = client.messages.create(**kwargs)
        print(f"{model}: stop={msg.stop_reason} blocks={[b.type for b in msg.content]}")
        for b in msg.content:
            if hasattr(b, "text"):
                print(f"  text={b.text[:200]!r}")
    except Exception as e:
        print(f"{model}: ERROR {e}")
