# -*- coding: utf-8 -*-
import asyncio
import os
from pathlib import Path
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
import anthropic
import google.generativeai as genai
from openai import OpenAI

_ENV_PATH = Path(__file__).resolve().parents[3] / "back_mic" / "backend" / ".env"
load_dotenv(_ENV_PATH)

from rough_outline_prompts import AI_CONFIGS, PROMPT_TEMPLATES

router = APIRouter(prefix="/api/testc/rough_outline")

# ── AI 调用函数 ────────────────────────────────────────────────

async def call_claude(prompt: str) -> tuple[str, str]:
    def _sync():
        client = anthropic.Anthropic(api_key=os.environ["CLAUDE_API_KEY"])
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text
    result = await asyncio.to_thread(_sync)
    return (result, "Claude Sonnet 4.6")

async def call_gemini(prompt: str) -> tuple[str, str]:
    def _sync():
        api_key = os.getenv("GEMINI_API_KEY")
        genai.configure(api_key=api_key)
        for model_name in ["gemini-2.5-pro", "gemini-2.5-flash"]:
            try:
                model = genai.GenerativeModel(model_name)
                response = model.generate_content(prompt)
                return response.text
            except Exception:
                if model_name == "gemini-2.5-flash":
                    raise
                continue
    result = await asyncio.to_thread(_sync)
    return (result, "Gemini 2.5 Pro")

async def call_deepseek(prompt: str) -> tuple[str, str]:
    def _sync():
        client = OpenAI(
            api_key=os.getenv("DEEPSEEK_API_KEY"),
            base_url="https://api.deepseek.com",
        )
        response = client.chat.completions.create(
            model="deepseek-chat",
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    result = await asyncio.to_thread(_sync)
    return (result, "DeepSeek")

async def call_perplexity(prompt: str) -> tuple[str, str]:
    def _sync():
        client = OpenAI(
            api_key=os.getenv("PERPLEXITY_API_KEY"),
            base_url="https://api.perplexity.ai",
        )
        response = client.chat.completions.create(
            model="sonar-pro",
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    result = await asyncio.to_thread(_sync)
    return (result, "Perplexity")

async def call_chatgpt(prompt: str) -> tuple[str, str]:
    def _sync():
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        response = client.chat.completions.create(
            model="gpt-4o",
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    result = await asyncio.to_thread(_sync)
    return (result, "ChatGPT GPT-4o")

async def call_grok(prompt: str) -> tuple[str, str]:
    def _sync():
        client = OpenAI(
            api_key=os.getenv("XAI_API_KEY"),
            base_url="https://api.x.ai/v1",
        )
        response = client.chat.completions.create(
            model="grok-3",
            max_tokens=8192,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.choices[0].message.content
    result = await asyncio.to_thread(_sync)
    return (result, "Grok 3")

async def call_ai(ai_name: str, prompt: str) -> tuple[str, str]:
    dispatch = {
        "claude":     call_claude,
        "gemini":     call_gemini,
        "deepseek":   call_deepseek,
        "perplexity": call_perplexity,
        "chatgpt":    call_chatgpt,
        "grok":       call_grok,
    }
    if ai_name not in dispatch:
        raise ValueError(f"未知 AI: {ai_name}")
    return await dispatch[ai_name](prompt)

# ── 请求体 ─────────────────────────────────────────────────────

class GenerateRequest(BaseModel):
    outline_type: str = Field(..., description="polish / beginner / youth / truth / sharing")
    content: str = Field(..., min_length=1, description="原始纲目全文")
    ai_index: int = Field(0, description="该类型下第几个 AI（0起）")

# ── 接口 ───────────────────────────────────────────────────────

@router.get("/config")
async def get_config():
    return {k: len(v) for k, v in AI_CONFIGS.items()}

@router.post("/generate")
async def generate(req: GenerateRequest):
    if req.outline_type not in AI_CONFIGS:
        raise HTTPException(status_code=400, detail=f"无效的 outline_type: {req.outline_type}")
    configs = AI_CONFIGS[req.outline_type]
    if req.ai_index < 0 or req.ai_index >= len(configs):
        raise HTTPException(status_code=400, detail=f"ai_index 超出范围，该类型共 {len(configs)} 个 AI")
    config = configs[req.ai_index]
    prompt_key = config["prompt_key"]
    if prompt_key not in PROMPT_TEMPLATES:
        raise HTTPException(status_code=500, detail=f"Prompt 模板不存在: {prompt_key}")
    prompt = PROMPT_TEMPLATES[prompt_key].format(content=req.content)
    try:
        result, model_name = await call_ai(config["ai"], prompt)
        return {
            "type": req.outline_type,
            "content": result,
            "ai_model": model_name,
            "ai_index": req.ai_index,
            "error": None,
        }
    except Exception as e:
        return {
            "type": req.outline_type,
            "content": None,
            "ai_model": None,
            "ai_index": req.ai_index,
            "error": str(e),
        }
