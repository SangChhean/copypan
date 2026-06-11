import os
import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import anthropic
from google import genai
from google.genai import types as genai_types
from openai import AsyncOpenAI
from rough_outline_prompts import AI_CONFIGS, PROMPT_TEMPLATES, get_prompt_template

router = APIRouter(prefix="/api/testb/rough_outline")


async def call_claude(prompt: str, model: str, max_tokens: int) -> tuple[str, str]:
    api_key = os.getenv("CLAUDE_API_KEY")
    client = anthropic.Anthropic(api_key=api_key)

    def _run():
        resp = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0,
            messages=[{"role": "user", "content": prompt}],
        )
        return "".join(block.text for block in resp.content if getattr(block, "type", "") == "text")

    content = await asyncio.to_thread(_run)
    return content, model


async def call_gemini(prompt: str, model: str, max_tokens: int) -> tuple[str, str]:
    api_key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=api_key)

    def _run_once(model_name: str, tokens: int, contents) -> tuple[str, bool]:
        """
        返回 (生成的文字, 是否被截断)
        """
        resp = client.models.generate_content(
            model=model_name,
            contents=contents,
            config=genai_types.GenerateContentConfig(
                max_output_tokens=tokens,
                temperature=0,
            ),
        )
        candidate = resp.candidates[0]
        try:
            text = "".join(
                part.text
                for part in candidate.content.parts
                if hasattr(part, "text")
            )
        except Exception:
            text = resp.text or ""
        truncated = candidate.finish_reason.value == "MAX_TOKENS"
        return text, truncated

    async def _generate_with_retry(model_name: str, tokens: int) -> str:
        """
        最多续写3次，把所有片段拼接成完整内容
        """
        all_parts = []
        # 第一次：用原始 prompt
        contents = prompt
        for attempt in range(4):  # 最多4次（1次初始 + 3次续写）
            text, truncated = await asyncio.to_thread(_run_once, model_name, tokens, contents)
            all_parts.append(text)
            if not truncated:
                break
            if attempt < 3:
                # 续写：把原始 prompt + 已生成内容拼在一起，让模型接续
                contents = [
                    {"role": "user", "parts": [{"text": prompt}]},
                    {"role": "model", "parts": [{"text": "".join(all_parts)}]},
                    {"role": "user", "parts": [{"text": "请继续完成上面未写完的内容，直接接续，不要重复已有内容。"}]},
                ]
        return "".join(all_parts)

    # 首选传入模型，失败或内容为空则降级到 gemini-2.5-pro
    try:
        content = await _generate_with_retry(model, max_tokens)
        if content.strip():
            return content, model
        raise ValueError("empty response")
    except Exception:
        fallback = "gemini-2.5-pro"
        content = await _generate_with_retry(fallback, 8192)
        return content, fallback


async def call_deepseek(prompt: str, model: str, max_tokens: int) -> tuple[str, str]:
    api_key = os.getenv("DEEPSEEK_API_KEY")
    client = AsyncOpenAI(api_key=api_key, base_url="https://api.deepseek.com")
    actual_model = "deepseek-v4-pro"
    resp = await client.chat.completions.create(
        model=actual_model,
        max_tokens=max_tokens,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    content = resp.choices[0].message.content or ""
    return content, actual_model


async def call_perplexity(prompt: str, model: str, max_tokens: int) -> tuple[str, str]:
    api_key = os.getenv("PERPLEXITY_API_KEY")
    client = AsyncOpenAI(api_key=api_key, base_url="https://api.perplexity.ai")
    resp = await client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    content = resp.choices[0].message.content or ""
    return content, model


async def call_chatgpt(prompt: str, model: str, max_tokens: int) -> tuple[str, str]:
    api_key = os.getenv("OPENAI_API_KEY")
    client = AsyncOpenAI(api_key=api_key)
    resp = await client.chat.completions.create(
        model=model,
        max_completion_tokens=max_tokens,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    content = resp.choices[0].message.content or ""
    return content, model


async def call_grok(prompt: str, model: str, max_tokens: int) -> tuple[str, str]:
    api_key = os.getenv("XAI_API_KEY")
    client = AsyncOpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
    resp = await client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    content = resp.choices[0].message.content or ""
    return content, model


async def call_ai(ai_type: str, prompt: str, model: str, max_tokens: int) -> tuple[str, str]:
    if ai_type == "claude":
        return await call_claude(prompt, model, max_tokens)
    if ai_type == "gemini":
        return await call_gemini(prompt, model, max_tokens)
    if ai_type == "deepseek":
        return await call_deepseek(prompt, model, max_tokens)
    if ai_type == "perplexity":
        return await call_perplexity(prompt, model, max_tokens)
    if ai_type == "chatgpt":
        return await call_chatgpt(prompt, model, max_tokens)
    if ai_type == "grok":
        return await call_grok(prompt, model, max_tokens)
    raise ValueError(f"未知的 AI 类型: {ai_type}")


@router.get("/config")
async def get_config():
    return {t: len(AI_CONFIGS[t]) for t in AI_CONFIGS}


class GenerateRequest(BaseModel):
    outline_type: str
    content: str
    ai_index: int = 0
    line1: str = ""
    line2: str = ""
    line3: str = ""


@router.post("/generate")
async def generate(req: GenerateRequest):
    if req.outline_type not in AI_CONFIGS:
        raise HTTPException(status_code=422, detail=f"未知的纲目类型: {req.outline_type}")
    if not req.content or not req.content.strip():
        raise HTTPException(status_code=422, detail="content 不能为空")

    configs = AI_CONFIGS[req.outline_type]
    if req.ai_index < 0 or req.ai_index >= len(configs):
        raise HTTPException(status_code=422, detail=f"ai_index 超出范围: {req.ai_index}")

    config = configs[req.ai_index]
    prompt_key = config.get("prompt_key", req.outline_type)
    prompt_template = get_prompt_template(req.outline_type, prompt_key)
    prompt = prompt_template.format(content=req.content)

    try:
        result, model_name = await call_ai(
            config["type"], prompt, config["model"], config["max_tokens"]
        )
        return {
            "type": req.outline_type,
            "content": result,
            "ai_model": model_name,
            "ai_index": req.ai_index,
        }
    except Exception as e:
        return {
            "type": req.outline_type,
            "content": "",
            "ai_model": config.get("name", ""),
            "ai_index": req.ai_index,
            "error": str(e),
        }
