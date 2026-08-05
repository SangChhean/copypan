"""
圆桌会议统一 AI 调用封装
复用 ai_search.ai_service 中的底层函数，按 ai_name 分发；超时 120 秒，出错抛 RoundTableAIError。
支持各 AI 联网能力：Claude web_search、GPT web_search_preview、Gemini Google Search、Grok 实时搜索、Perplexity Deep Research。
"""
import os
import asyncio
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 与 ai_service 一致：从 backend 目录加载 .env
_env_path = Path(__file__).resolve().parent.parent.parent / ".env"
if _env_path.exists():
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_env_path)

# 圆桌专用模型环境变量与默认值（仅本文件使用，勿与 KG-RAG / 翻译等模块共享默认值）
ROUNDTABLE_CLAUDE_MODEL = os.getenv("ROUNDTABLE_CLAUDE_MODEL", "claude-sonnet-5")
ROUNDTABLE_GPT_MODEL = os.getenv("ROUNDTABLE_GPT_MODEL", "gpt-5.5")
ROUNDTABLE_GEMINI_MODEL = os.getenv("ROUNDTABLE_GEMINI_MODEL", "gemini-3.1-pro-preview")
ROUNDTABLE_GROK_MODEL = os.getenv("ROUNDTABLE_GROK_MODEL", "grok-4.5")
ROUNDTABLE_DEEPSEEK_MODEL = os.getenv("ROUNDTABLE_DEEPSEEK_MODEL", "deepseek-v4-flash")
# 若设置则覆盖 Perplexity 型号；未设置时按场景 fallback（① sonar-deep-research，其它 sonar-pro）
ROUNDTABLE_PERPLEXITY_MODEL = (os.getenv("ROUNDTABLE_PERPLEXITY_MODEL") or "").strip()

# 场景无关「顶级档」型号（场景③等可混搭；env 可覆盖）
ROUNDTABLE_CLAUDE_TOP_MODEL = os.getenv("ROUNDTABLE_CLAUDE_TOP_MODEL", "claude-fable-5")
ROUNDTABLE_GPT_TOP_MODEL = os.getenv("ROUNDTABLE_GPT_TOP_MODEL", "gpt-5.6-sol")
ROUNDTABLE_GEMINI_TOP_MODEL = os.getenv(
    "ROUNDTABLE_GEMINI_TOP_MODEL", "gemini-3.1-pro-preview"
)
ROUNDTABLE_GROK_TOP_MODEL = os.getenv("ROUNDTABLE_GROK_TOP_MODEL", "grok-4.5")
ROUNDTABLE_DEEPSEEK_TOP_MODEL = os.getenv("ROUNDTABLE_DEEPSEEK_TOP_MODEL", "deepseek-v4-pro")
ROUNDTABLE_PERPLEXITY_TOP_MODEL = os.getenv(
    "ROUNDTABLE_PERPLEXITY_TOP_MODEL", "sonar-reasoning-pro"
)

# 场景④ 顶级模型思考：三选一（历史 key 名保留，底层已对齐顶级档）
ROUNDTABLE_SCENE4_CLAUDE_MODEL = os.getenv("ROUNDTABLE_SCENE4_CLAUDE_MODEL", "claude-fable-5")
ROUNDTABLE_SCENE4_GPT_MODEL = os.getenv("ROUNDTABLE_SCENE4_GPT_MODEL", "gpt-5.6-sol")
ROUNDTABLE_SCENE4_GEMINI_MODEL = os.getenv(
    "ROUNDTABLE_SCENE4_GEMINI_MODEL", "gemini-3.1-pro-preview"
)

SUPPORTED_AIS = ["claude", "gpt", "gemini", "grok", "deepseek", "perplexity"]
SUPPORTED_AIS_SCENE4 = ["claude_opus", "gpt_pro", "gemini_pro"]
SUPPORTED_AIS_TOP = [
    "claude_top",
    "gpt_top",
    "gemini_top",
    "grok_top",
    "deepseek_top",
    "perplexity_top",
]

# 场景无关：高阶/顶级 key → (厂商基座 actual_ai, 型号字符串)
# 在 call_ai 入口解析，不再仅绑定 scene_four
def _premium_key_map():
    return {
        "claude_opus": ("claude", ROUNDTABLE_SCENE4_CLAUDE_MODEL),
        "gpt_pro": ("gpt", ROUNDTABLE_SCENE4_GPT_MODEL),
        "gemini_pro": ("gemini", ROUNDTABLE_SCENE4_GEMINI_MODEL),
        "claude_top": ("claude", ROUNDTABLE_CLAUDE_TOP_MODEL),
        "gpt_top": ("gpt", ROUNDTABLE_GPT_TOP_MODEL),
        "gemini_top": ("gemini", ROUNDTABLE_GEMINI_TOP_MODEL),
        "grok_top": ("grok", ROUNDTABLE_GROK_TOP_MODEL),
        "deepseek_top": ("deepseek", ROUNDTABLE_DEEPSEEK_TOP_MODEL),
        "perplexity_top": ("perplexity", ROUNDTABLE_PERPLEXITY_TOP_MODEL),
    }


MAX_RETRIES = 2
RETRY_DELAYS = [2, 6]  # 秒
CLIENT_ERROR_CODES = (400, 401, 403, 404, 422)

# 圆桌各AI单价（美元/百万token）
# claude（sonnet-5）：Anthropic 限时优惠 $2/$10，截止 2026-08-31；
# 2026-09-01 起请改回标准价 $3.00/$15.00。
# grok-4.5：https://docs.x.ai/developers/models/grok-4.5 标准档 <200k $2/$6
# gemini_top 与 gemini_pro 共用价目；grok_top 与 grok 共用价目
ROUNDTABLE_PRICES = {
    "claude": {"input": 2.00, "output": 10.00},  # 优惠至 2026-08-31；其后改回 3.00/15.00
    "gpt": {"input": 2.50, "output": 15.00},
    "gemini": {"input": 1.25, "output": 10.00},
    "grok": {"input": 2.00, "output": 6.00},
    "deepseek": {"input": 0.28, "output": 0.42},
    "perplexity_sonar_pro": {"input": 3.00, "output": 15.00},
    "perplexity_deep_research": {"input": 2.00, "output": 8.00},
    "claude_opus": {"input": 10.00, "output": 50.00},  # claude-fable-5（场景④）
    "gpt_pro": {"input": 5.00, "output": 30.00},  # gpt-5.6-sol（场景④；OpenAI 标准短上下文）
    "gemini_pro": {"input": 2.00, "output": 12.00},
    "claude_top": {"input": 10.00, "output": 50.00},  # claude-fable-5
    "gpt_top": {"input": 5.00, "output": 30.00},  # gpt-5.6-sol
    "deepseek_top": {"input": 0.435, "output": 0.87},  # deepseek-v4-pro
    "perplexity_top": {"input": 2.00, "output": 8.00},  # sonar-reasoning-pro
}
PERPLEXITY_REQUEST_FEE = 0.005  # $5/1000次请求 = $0.005/次


def _calc_roundtable_cost(
    ai_name: str, input_tokens: int, output_tokens: int, scene_type: str = "scene_two"
) -> float:
    """按调用 key 计费；gemini_top→gemini_pro，grok_top→grok。"""
    if ai_name == "gemini_top":
        key = "gemini_pro"
    elif ai_name == "grok_top":
        key = "grok"
    elif ai_name == "perplexity":
        key = "perplexity_deep_research" if scene_type == "scene_one" else "perplexity_sonar_pro"
    else:
        key = ai_name
    price = ROUNDTABLE_PRICES.get(key, {"input": 0, "output": 0})
    cost = (input_tokens * price["input"] + output_tokens * price["output"]) / 1_000_000
    if ai_name in ("perplexity", "perplexity_top") or key.startswith("perplexity"):
        cost += PERPLEXITY_REQUEST_FEE
    return cost

# 延迟导入，避免循环依赖与 ai_service 启动时的重量级初始化在 import 时全部执行
def _get_ai_service():
    from ai_search.ai_service import (
        claude_client,
        _call_claude_messages_sync,
        AISearchService,
        gemini_client,
        GEMINI_SEMAPHORE,
        CLAUDE_API_KEY,
        DEEPSEEK_API_KEY,
        PERPLEXITY_API_KEY,
        OPENAI_API_KEY,
        XAI_API_KEY,
    )
    return {
        "claude_client": claude_client,
        "call_claude": _call_claude_messages_sync,
        "AISearchService": AISearchService,
        "gemini_client": gemini_client,
        "GEMINI_SEMAPHORE": GEMINI_SEMAPHORE,
        "CLAUDE_API_KEY": CLAUDE_API_KEY,
        "DEEPSEEK_API_KEY": DEEPSEEK_API_KEY,
        "PERPLEXITY_API_KEY": PERPLEXITY_API_KEY,
        "OPENAI_API_KEY": OPENAI_API_KEY,
        "XAI_API_KEY": XAI_API_KEY,
    }


class RoundTableAIError(Exception):
    def __init__(self, ai_name: str, reason: str, is_client_error: bool = False):
        self.ai_name = ai_name
        self.reason = reason
        self.is_client_error = is_client_error
        self.attempts = None  # 最终失败时由 call_ai 填入已尝试次数（1-based）
        super().__init__(f"[{ai_name}] {reason}")


def _call_claude_sync(
    prompt_or_bytes,
    system_prompt_or_bytes,
    scene_type: str = "scene_two",
    model_override: Optional[str] = None,
) -> tuple:
    """返回 (content, input_tokens, output_tokens)。model_override 优先于默认/场景④型号。"""
    svc = _get_ai_service()
    client = svc["claude_client"]
    if not client:
        raise RoundTableAIError("claude", "CLAUDE_API_KEY 未配置", is_client_error=True)
    prompt = prompt_or_bytes.decode("utf-8") if isinstance(prompt_or_bytes, bytes) else prompt_or_bytes
    system_prompt = system_prompt_or_bytes.decode("utf-8") if isinstance(system_prompt_or_bytes, bytes) else (system_prompt_or_bytes or "")
    try:
        import anthropic
        client_120 = anthropic.Anthropic(
            api_key=svc["CLAUDE_API_KEY"],
            timeout=600.0,
        )
    except Exception as e:
        raise RoundTableAIError("claude", str(e), is_client_error=True)
    old_model = os.environ.get("CLAUDE_MODEL")
    if model_override:
        claude_model = model_override
    elif scene_type == "scene_four":
        claude_model = ROUNDTABLE_SCENE4_CLAUDE_MODEL
    else:
        claude_model = ROUNDTABLE_CLAUDE_MODEL
    os.environ["CLAUDE_MODEL"] = claude_model
    # 场景①研究/结论内容长；场景④顶级思考给足上限
    max_tokens = 16000 if scene_type == "scene_one" else (16000 if scene_type == "scene_four" else 8192)
    kwargs = {
        "model": claude_model,
        "max_tokens": max_tokens,
        "system": system_prompt or "",
        "messages": [{"role": "user", "content": prompt}],
        "tools": [{"type": "web_search_20250305", "name": "web_search"}],
    }
    if scene_type == "scene_four":
        kwargs["thinking"] = {"type": "adaptive"}  # Opus 自适应扩展思考
    try:
        try:
            msg = client_120.messages.create(**kwargs)
        except Exception as api_err:
            status = getattr(api_err, "status_code", None) or getattr(api_err, "http_status", None)
            is_client = status in CLIENT_ERROR_CODES if status is not None else False
            raise RoundTableAIError("claude", str(api_err), is_client_error=is_client)
        parts = []
        thinking_parts = []
        for block in (msg.content or []):
            btype = getattr(block, "type", None)
            if btype == "text":
                t = getattr(block, "text", None)
                if t and str(t).strip():
                    parts.append(str(t).strip())
            elif scene_type == "scene_four" and btype == "thinking":
                t = getattr(block, "thinking", None)
                if t and str(t).strip():
                    thinking_parts.append(str(t).strip())
        if scene_type == "scene_four" and thinking_parts:
            text = "【思考过程】\n\n" + "\n\n".join(thinking_parts) + "\n\n【回答】\n\n" + "\n\n".join(parts) if parts else "\n\n".join(thinking_parts)
        else:
            text = "\n\n".join(parts) if parts else ""
        usage = getattr(msg, "usage", None)
        in_tok = int(getattr(usage, "input_tokens", 0) or 0)
        out_tok = int(getattr(usage, "output_tokens", 0) or 0)
    finally:
        if old_model is None:
            os.environ.pop("CLAUDE_MODEL", None)
        else:
            os.environ["CLAUDE_MODEL"] = old_model
    if not (text and text.strip()):
        raise RoundTableAIError("claude", "返回为空", is_client_error=False)
    return (text.strip(), in_tok, out_tok)


def _call_openai_compat_sync(
    ai_name: str,
    prompt: str,
    system_prompt: str,
    api_key: str,
    model: str,
    base_url: Optional[str],
    use_max_completion_tokens: bool,
) -> tuple:
    """返回 (content, input_tokens, output_tokens)。直接使用 openai 客户端，不再依赖 ai_search。"""
    if not api_key:
        raise RoundTableAIError(ai_name, "API Key 未配置", is_client_error=True)
    full_prompt = (system_prompt.strip() + "\n\n" + prompt) if system_prompt.strip() else prompt
    from openai import OpenAI
    client = OpenAI(api_key=api_key, base_url=base_url)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": full_prompt}],
            max_tokens=8192,
        )
    except Exception as api_err:
        status = getattr(api_err, "status_code", None)
        is_client = status in CLIENT_ERROR_CODES if status is not None else False
        raise RoundTableAIError(ai_name, str(api_err), is_client_error=is_client)
    text = (response.choices[0].message.content or "") if response.choices else ""
    usage = getattr(response, "usage", None)
    in_tok = int(getattr(usage, "prompt_tokens", 0) or 0)
    out_tok = int(getattr(usage, "completion_tokens", 0) or 0)
    if not (text and text.strip()):
        raise RoundTableAIError(ai_name, "返回为空", is_client_error=False)
    return (text.strip(), in_tok, out_tok)


def _call_gpt_with_responses_sync(
    prompt: str, system_prompt: str, model: Optional[str] = None, timeout: float = 120.0
) -> tuple:
    """返回 (content, input_tokens, output_tokens)。model 为空时使用 ROUNDTABLE_GPT_MODEL。场景④ gpt-5.5-pro 推理较慢，需更长 timeout。"""
    svc = _get_ai_service()
    api_key = svc.get("OPENAI_API_KEY")
    if not api_key:
        raise RoundTableAIError("gpt", "OPENAI_API_KEY 未配置", is_client_error=True)
    from openai import OpenAI
    client = OpenAI(api_key=api_key, timeout=timeout)
    gpt_model = model or ROUNDTABLE_GPT_MODEL
    try:
        response = client.responses.create(
            model=gpt_model,
            instructions=system_prompt.strip() if (system_prompt and system_prompt.strip()) else None,
            input=prompt,
            tools=[{"type": "web_search_preview"}],
        )
    except Exception as api_err:
        status = getattr(api_err, "status_code", None)
        is_client = status in CLIENT_ERROR_CODES if status is not None else False
        raise RoundTableAIError("gpt", str(api_err), is_client_error=is_client)
    text = getattr(response, "output_text", None)
    if text is not None:
        text = str(text).strip()
    if not text:
        raise RoundTableAIError("gpt", "返回为空", is_client_error=False)
    usage = getattr(response, "usage", None)
    in_tok = int(getattr(usage, "input_tokens", 0) or 0)
    out_tok = int(getattr(usage, "output_tokens", 0) or 0)
    return (text, in_tok, out_tok)


def _call_gemini_sync(prompt: str, system_prompt: str, model: Optional[str] = None) -> tuple:
    """返回 (content, input_tokens, output_tokens)。model 为空时使用 ROUNDTABLE_GEMINI_MODEL。"""
    svc = _get_ai_service()
    client = svc["gemini_client"]
    if not client:
        raise RoundTableAIError("gemini", "GEMINI_API_KEY 未配置或客户端初始化失败", is_client_error=True)
    from google.genai import types
    from google.genai.types import Tool, GoogleSearch
    gemini_model = model or ROUNDTABLE_GEMINI_MODEL
    with svc["GEMINI_SEMAPHORE"]:
        try:
            response = client.models.generate_content(
                model=gemini_model,
                contents=prompt,
                config=types.GenerateContentConfig(
                    max_output_tokens=8192,
                    system_instruction=system_prompt.strip() or None,
                    tools=[Tool(google_search=GoogleSearch())],
                ),
            )
        except Exception as api_err:
            status = getattr(api_err, "status_code", None)
            is_client = status in CLIENT_ERROR_CODES if status is not None else False
            raise RoundTableAIError("gemini", str(api_err), is_client_error=is_client)
    text = None
    if getattr(response, "text", None):
        text = response.text
    elif getattr(response, "candidates", None) and response.candidates:
        text = response.candidates[0].content.parts[0].text
    if not (text and str(text).strip()):
        raise RoundTableAIError("gemini", "返回为空", is_client_error=False)
    um = getattr(response, "usage_metadata", None)
    in_tok = int(getattr(um, "prompt_token_count", 0) or 0)
    out_tok = int(getattr(um, "candidates_token_count", 0) or 0)
    return (str(text).strip(), in_tok, out_tok)


async def _call_perplexity_deep_research(prompt: str, system_prompt: str) -> str:
    """
    Perplexity Deep Research：POST 提交异步任务，轮询 GET 直到 COMPLETED，返回 response.choices[0].message.content。
    型号优先 ROUNDTABLE_PERPLEXITY_MODEL，否则 sonar-deep-research；最多轮询 60 次（5 分钟）。
    """
    import httpx
    svc = _get_ai_service()
    api_key = svc.get("PERPLEXITY_API_KEY") or os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        raise RoundTableAIError("perplexity", "PERPLEXITY_API_KEY 未配置", is_client_error=True)
    model = ROUNDTABLE_PERPLEXITY_MODEL or "sonar-deep-research"
    messages = []
    if system_prompt and system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt.strip()})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "request": {
            "model": model,
            "messages": messages,
        }
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(
            "https://api.perplexity.ai/async/chat/completions",
            json=payload,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        )
        try:
            r.raise_for_status()
        except httpx.HTTPStatusError as e:
            status = e.response.status_code if e.response is not None else None
            is_client = status in CLIENT_ERROR_CODES if status is not None else False
            raise RoundTableAIError("perplexity", str(e), is_client_error=is_client)
        data = r.json()
    task_id = data.get("id")
    if not task_id:
        raise RoundTableAIError("perplexity", "异步任务未返回 id", is_client_error=False)
    for _ in range(60):
        await asyncio.sleep(5)
        async with httpx.AsyncClient(timeout=30.0) as client:
            poll_r = await client.get(
                f"https://api.perplexity.ai/async/chat/completions/{task_id}",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            try:
                poll_r.raise_for_status()
            except httpx.HTTPStatusError as e:
                status = e.response.status_code if e.response is not None else None
                is_client = status in CLIENT_ERROR_CODES if status is not None else False
                raise RoundTableAIError("perplexity", str(e), is_client_error=is_client)
            poll_data = poll_r.json()
        status = poll_data.get("status")
        if status == "COMPLETED":
            resp = poll_data.get("response")
            if not resp:
                raise RoundTableAIError("perplexity", "COMPLETED 但无 response", is_client_error=False)
            choices = resp.get("choices") or []
            if not choices:
                raise RoundTableAIError("perplexity", "response 中无 choices", is_client_error=False)
            msg = choices[0].get("message") or {}
            content = msg.get("content")
            if content is None:
                raise RoundTableAIError("perplexity", "返回 content 为空", is_client_error=False)
            usage = resp.get("usage") or {}
            in_tok = int(usage.get("prompt_tokens", 0) or 0)
            out_tok = int(usage.get("completion_tokens", 0) or 0)
            return (str(content).strip(), in_tok, out_tok)
        if status == "FAILED":
            err = poll_data.get("error_message") or poll_data.get("error") or "未知错误"
            raise RoundTableAIError("perplexity", f"Deep Research 失败: {err}", is_client_error=False)
    raise RoundTableAIError("perplexity", "Deep Research 超时（5 分钟）", is_client_error=False)


def _call_perplexity_sonar_pro(prompt: str, system_prompt: str) -> str:
    """
    Perplexity Sonar Pro：同步调用 chat/completions；型号优先 ROUNDTABLE_PERPLEXITY_MODEL，否则 sonar-pro。
    """
    svc = _get_ai_service()
    api_key = svc.get("PERPLEXITY_API_KEY") or os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        raise RoundTableAIError("perplexity", "PERPLEXITY_API_KEY 未配置", is_client_error=True)
    model = ROUNDTABLE_PERPLEXITY_MODEL or "sonar-pro"
    return _call_openai_compat_sync(
        "perplexity",
        prompt,
        system_prompt.strip() or "",
        api_key,
        model,
        "https://api.perplexity.ai",
        False,
    )


async def call_ai(ai_name: str, prompt: str, system_prompt: str = "", scene_type: str = "scene_two") -> tuple[str, float]:
    """
    统一调用接口。
    ai_name：基础档 SUPPORTED_AIS；场景④ SUPPORTED_AIS_SCENE4；
    场景③还可混搭 SUPPORTED_AIS_TOP（*_top）。
    返回 (content, cost)，cost 为美元；计费按原始 ai_name。
    """
    premium = _premium_key_map()
    model_override: Optional[str] = None

    if scene_type == "scene_four":
        if ai_name not in SUPPORTED_AIS_SCENE4:
            raise RoundTableAIError(ai_name, f"场景④ 仅支持: {SUPPORTED_AIS_SCENE4}", is_client_error=True)
        actual_ai, model_override = premium[ai_name]
    elif scene_type == "scene_three":
        allowed = set(SUPPORTED_AIS) | set(SUPPORTED_AIS_TOP)
        if ai_name not in allowed:
            raise RoundTableAIError(
                ai_name, f"场景③ 仅支持: {sorted(allowed)}", is_client_error=True
            )
        if ai_name in premium:
            actual_ai, model_override = premium[ai_name]
        else:
            actual_ai = ai_name
    else:
        if ai_name not in SUPPORTED_AIS:
            raise RoundTableAIError(ai_name, f"不支持的 AI，可选: {SUPPORTED_AIS}", is_client_error=True)
        actual_ai = ai_name

    loop = asyncio.get_event_loop()
    svc = _get_ai_service()
    # 高阶 GPT / Claude 给更长超时
    long_timeout = scene_type == "scene_four" or ai_name in (
        "claude_top",
        "gpt_top",
        "claude_opus",
        "gpt_pro",
    )

    async def _do_call() -> tuple:
        """返回 (content, input_tokens, output_tokens)。"""
        if actual_ai == "claude":
            p_b = prompt.encode("utf-8")
            s_b = (system_prompt or "").encode("utf-8")
            out = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda _p=p_b, _s=s_b, _st=scene_type, _m=model_override: _call_claude_sync(
                        _p, _s, _st, _m
                    ),
                ),
                timeout=600.0,
            )
            return out
        if actual_ai == "gemini":
            gemini_model = model_override or (
                ROUNDTABLE_SCENE4_GEMINI_MODEL if scene_type == "scene_four" else None
            )
            out = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: _call_gemini_sync(prompt, system_prompt, gemini_model),
                ),
                timeout=120.0,
            )
            return out
        if actual_ai == "gpt":
            gpt_model = model_override or (
                ROUNDTABLE_SCENE4_GPT_MODEL if scene_type == "scene_four" else None
            )
            gpt_timeout = 600.0 if long_timeout else 120.0
            out = await asyncio.wait_for(
                asyncio.to_thread(
                    _call_gpt_with_responses_sync, prompt, system_prompt, gpt_model, gpt_timeout
                ),
                timeout=gpt_timeout,
            )
            return out
        if actual_ai == "deepseek":
            ds_model = model_override or ROUNDTABLE_DEEPSEEK_MODEL
            out = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: _call_openai_compat_sync(
                        "deepseek",
                        prompt,
                        system_prompt,
                        svc["DEEPSEEK_API_KEY"],
                        ds_model,
                        "https://api.deepseek.com",
                        False,
                    ),
                ),
                timeout=120.0,
            )
            return out
        if actual_ai == "perplexity":
            if model_override:
                # 顶级档等：显式型号走同步兼容接口
                out = await asyncio.wait_for(
                    loop.run_in_executor(
                        None,
                        lambda: _call_openai_compat_sync(
                            "perplexity",
                            prompt,
                            system_prompt.strip() or "",
                            svc.get("PERPLEXITY_API_KEY") or os.getenv("PERPLEXITY_API_KEY") or "",
                            model_override,
                            "https://api.perplexity.ai",
                            False,
                        ),
                    ),
                    timeout=120.0,
                )
                return out
            if scene_type == "scene_one":
                out = await asyncio.wait_for(
                    _call_perplexity_deep_research(prompt, system_prompt),
                    timeout=320.0,
                )
                return out
            out = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: _call_perplexity_sonar_pro(prompt, system_prompt),
                ),
                timeout=120.0,
            )
            return out
        if actual_ai == "grok":
            grok_model = model_override or ROUNDTABLE_GROK_MODEL
            grok_system = (system_prompt or "").strip()
            grok_system += "\n\n你可以使用实时搜索能力获取最新资料，请积极搜索相关神学资料以支撑你的论点。"
            out = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: _call_openai_compat_sync(
                        "grok",
                        prompt,
                        grok_system,
                        svc["XAI_API_KEY"],
                        grok_model,
                        "https://api.x.ai/v1",
                        False,
                    ),
                ),
                timeout=120.0,
            )
            return out
        raise RoundTableAIError(ai_name, "未实现", is_client_error=True)

    for attempt in range(MAX_RETRIES + 1):
        try:
            content, in_tok, out_tok = await _do_call()
            cost = _calc_roundtable_cost(ai_name, in_tok, out_tok, scene_type)
            logger.info(
                "[RoundTable] %s | 输入=%d tokens | 输出=%d tokens | 费用=$%.6f",
                ai_name, in_tok, out_tok, cost
            )
            return (content, cost)
        except RoundTableAIError as e:
            e.attempts = attempt + 1
            if e.is_client_error:
                raise
            if attempt == MAX_RETRIES:
                raise
            await asyncio.sleep(RETRY_DELAYS[attempt])
            logger.warning(
                "[RoundTable] %s 第%d次失败，%d秒后重试：%s",
                e.ai_name, attempt + 1, RETRY_DELAYS[attempt], e.reason,
            )
        except asyncio.TimeoutError as e:
            if attempt == MAX_RETRIES:
                err = RoundTableAIError(ai_name, f"请求超时: {e}", is_client_error=False)
                err.attempts = attempt + 1
                raise err
            await asyncio.sleep(RETRY_DELAYS[attempt])
            logger.warning(
                "[RoundTable] %s 第%d次失败，%d秒后重试：请求超时",
                ai_name, attempt + 1, RETRY_DELAYS[attempt],
            )
