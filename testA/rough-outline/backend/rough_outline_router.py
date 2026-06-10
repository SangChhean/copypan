# -*- coding: utf-8 -*-
import os
import asyncio
import time
import logging
from fastapi import APIRouter
from pydantic import BaseModel
from rough_outline_prompts import AI_CONFIGS, PROMPT_TEMPLATES

logger = logging.getLogger("rough_outline")
router = APIRouter(prefix="/api/testa/rough_outline")

# ── 环境变量 ──────────────────────────────────────────────
CLAUDE_API_KEY     = os.environ.get("CLAUDE_API_KEY", "")
GEMINI_API_KEY     = os.environ.get("GEMINI_API_KEY", "")
DEEPSEEK_API_KEY   = os.environ.get("DEEPSEEK_API_KEY", "")
PERPLEXITY_API_KEY = os.environ.get("PERPLEXITY_API_KEY", "")
OPENAI_API_KEY     = os.environ.get("OPENAI_API_KEY", "")
XAI_API_KEY        = os.environ.get("XAI_API_KEY", "")

# ── Claude ────────────────────────────────────────────────
async def call_claude(prompt: str, model: str = "claude-sonnet-4-6", max_tokens: int = 8192) -> tuple[str, str]:
    def _sync():
        import anthropic
        client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)
        msg = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return msg.content[0].text or ""
    result = await asyncio.to_thread(_sync)
    return (result, "Claude Sonnet 4.6")

# ── Gemini（含 pro → flash 回退）────────────────────────
def _gemini_generate_sync(model: str, prompt: str, max_tokens: int, max_retries: int = 0) -> str | None:
    backoff = (8, 15)
    for attempt in range(max_retries + 1):
        try:
            from google import genai
            from google.genai import types
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model=model,
                contents=prompt,
                config=types.GenerateContentConfig(max_output_tokens=max_tokens),
            )
            if hasattr(response, "text") and response.text:
                return response.text
            if hasattr(response, "candidates") and response.candidates:
                return response.candidates[0].content.parts[0].text
            return None
        except Exception as e:
            retryable = "503" in str(e) or "429" in str(e)
            if retryable and attempt < max_retries:
                wait = backoff[attempt] if attempt < len(backoff) else 40
                logger.warning("Gemini 暂时不可用，%s 秒后重试 (%s/%s)", wait, attempt + 1, max_retries)
                time.sleep(wait)
            else:
                logger.error("Gemini 调用失败 (model=%s): %s", model, e)
                return None
    return None

async def call_gemini(prompt: str, model: str = "gemini-3.1-pro-preview", max_tokens: int = 16384) -> tuple[str, str]:
    primary = model
    fallback = "gemini-2.5-pro"
    result = await asyncio.to_thread(_gemini_generate_sync, primary, prompt, max_tokens, 0)
    if result:
        return (result, "Gemini 3.1 Pro")
    if fallback != primary:
        logger.warning("Gemini 3.1 Pro 不可用，改用备用模型: %s", fallback)
        result = await asyncio.to_thread(_gemini_generate_sync, fallback, prompt, max_tokens, 2)
        if result:
            return (result, "Gemini 2.5 Pro")
    raise RuntimeError("Gemini 所有模型均不可用")

# ── OpenAI 兼容（DeepSeek / Perplexity / ChatGPT / Grok）──
async def call_openai_compatible(
    api_key: str,
    prompt: str,
    model: str,
    max_tokens: int = 8192,
    base_url: str | None = None,
    model_name: str = "",
    use_max_completion_tokens: bool = False,
) -> tuple[str, str]:
    def _sync():
        from openai import OpenAI
        kwargs = {"api_key": api_key, "timeout": 120.0}
        if base_url:
            kwargs["base_url"] = base_url
        client = OpenAI(**kwargs)
        create_kw = {"model": model, "messages": [{"role": "user", "content": prompt}]}
        if use_max_completion_tokens:
            create_kw["max_completion_tokens"] = max_tokens
        else:
            create_kw["max_tokens"] = max_tokens
        r = client.chat.completions.create(**create_kw)
        if r.choices and r.choices[0].message.content:
            return r.choices[0].message.content
        raise RuntimeError("返回内容为空")
    result = await asyncio.to_thread(_sync)
    return (result, model_name)

async def call_deepseek(prompt: str, model: str = "deepseek-chat", max_tokens: int = 8192) -> tuple[str, str]:
    if not DEEPSEEK_API_KEY:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")
    return await call_openai_compatible(
        DEEPSEEK_API_KEY, prompt, model, max_tokens,
        base_url="https://api.deepseek.com", model_name="DeepSeek"
    )

async def call_perplexity(prompt: str, model: str = "sonar-pro", max_tokens: int = 8192) -> tuple[str, str]:
    if not PERPLEXITY_API_KEY:
        raise RuntimeError("PERPLEXITY_API_KEY 未配置")
    return await call_openai_compatible(
        PERPLEXITY_API_KEY, prompt, model, max_tokens,
        base_url="https://api.perplexity.ai", model_name="Perplexity"
    )

async def call_chatgpt(prompt: str, model: str = "gpt-5.4", max_tokens: int = 8192) -> tuple[str, str]:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY 未配置")
    return await call_openai_compatible(
        OPENAI_API_KEY, prompt, model, max_tokens,
        model_name="ChatGPT", use_max_completion_tokens=True
    )

async def call_grok(prompt: str, model: str = "grok-4-1-fast-reasoning", max_tokens: int = 8192) -> tuple[str, str]:
    if not XAI_API_KEY:
        raise RuntimeError("XAI_API_KEY 未配置")
    return await call_openai_compatible(
        XAI_API_KEY, prompt, model, max_tokens,
        base_url="https://api.x.ai/v1", model_name="Grok"
    )

# ── 分派函数 ──────────────────────────────────────────────
async def call_ai(ai_config: dict, prompt: str) -> tuple[str, str]:
    ai_type  = ai_config.get("type", "")
    model    = ai_config.get("model", "")
    max_tokens = ai_config.get("max_tokens", 8192)
    name     = ai_config.get("name", ai_type)
    if ai_type == "claude":
        return await call_claude(prompt, model=model, max_tokens=max_tokens)
    elif ai_type == "gemini":
        return await call_gemini(prompt, model=model, max_tokens=max_tokens)
    elif ai_type == "deepseek":
        real_model = "deepseek-chat" if model == "deepseek-v3.2" else model
        return await call_deepseek(prompt, model=real_model, max_tokens=max_tokens)
    elif ai_type == "perplexity":
        real_model = "sonar-pro" if not model or "pplx-" in model else model
        return await call_perplexity(prompt, model=real_model, max_tokens=max_tokens)
    elif ai_type == "chatgpt":
        return await call_chatgpt(prompt, model=model, max_tokens=max_tokens)
    elif ai_type == "grok":
        return await call_grok(prompt, model=model, max_tokens=max_tokens)
    else:
        raise ValueError(f"不支持的 AI 类型: {ai_type}")

# ── Config 接口 ───────────────────────────────────────────
@router.get("/config")
async def get_config():
    return {k: len(v) for k, v in AI_CONFIGS.items()}

# ── 生成接口 ──────────────────────────────────────────────
class GenerateRequest(BaseModel):
    outline_type: str
    content: str
    ai_index: int = 0

@router.post("/generate")
async def generate(req: GenerateRequest):
    if req.outline_type not in AI_CONFIGS:
        return {"error": f"不支持的类型: {req.outline_type}"}
    if not req.content.strip():
        return {"error": "原始纲目内容不能为空"}
    configs = AI_CONFIGS[req.outline_type]
    if req.ai_index < 0 or req.ai_index >= len(configs):
        return {"error": f"ai_index 超出范围，该类型共 {len(configs)} 个 AI"}
    config = configs[req.ai_index]
    prompt_key = config.get("prompt_key") or req.outline_type
    template = PROMPT_TEMPLATES.get(prompt_key)
    if not template:
        return {"error": f"找不到 prompt_key: {prompt_key}"}
    prompt = template.format(content=req.content)
    try:
        content, model_name = await call_ai(config, prompt)
        return {
            "type": req.outline_type,
            "content": content,
            "ai_model": model_name,
            "ai_index": req.ai_index,
        }
    except Exception as e:
        logger.error("生成失败: %s", e, exc_info=True)
        return {"error": str(e), "type": req.outline_type, "ai_index": req.ai_index}
