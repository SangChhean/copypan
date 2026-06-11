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

# 圆桌专用模型环境变量与默认值（Claude 复用现有可用型号）
ROUNDTABLE_CLAUDE_MODEL = os.getenv("ROUNDTABLE_CLAUDE_MODEL", "claude-sonnet-4-6")
ROUNDTABLE_GPT_MODEL = os.getenv("ROUNDTABLE_GPT_MODEL", "gpt-5.4")
ROUNDTABLE_GEMINI_MODEL = os.getenv("ROUNDTABLE_GEMINI_MODEL", "gemini-2.5-pro")
ROUNDTABLE_GROK_MODEL = os.getenv("ROUNDTABLE_GROK_MODEL", "grok-4-1-fast-reasoning")
ROUNDTABLE_DEEPSEEK_MODEL = os.getenv("ROUNDTABLE_DEEPSEEK_MODEL", "deepseek-chat")
ROUNDTABLE_PERPLEXITY_MODEL = os.getenv("ROUNDTABLE_PERPLEXITY_MODEL", "sonar-deep-research")

# 场景④ 顶级模型思考：三选一
ROUNDTABLE_SCENE4_CLAUDE_MODEL = os.getenv("ROUNDTABLE_SCENE4_CLAUDE_MODEL", "claude-opus-4-6")
# 官方 API：gpt-5.4 标准版，gpt-5.4-pro 为高阶推理版，见 https://developers.openai.com/api/docs/models/gpt-5.4-pro
ROUNDTABLE_SCENE4_GPT_MODEL = os.getenv("ROUNDTABLE_SCENE4_GPT_MODEL", "gpt-5.4-pro")
# 官方 API 名称为 gemini-3.1-pro-preview，见 https://ai.google.dev/gemini-api/docs/models/gemini-3.1-pro-preview
ROUNDTABLE_SCENE4_GEMINI_MODEL = os.getenv("ROUNDTABLE_SCENE4_GEMINI_MODEL", "gemini-3.1-pro-preview")

SUPPORTED_AIS = ["claude", "gpt", "gemini", "grok", "deepseek", "perplexity"]
SUPPORTED_AIS_SCENE4 = ["claude_opus", "gpt_pro", "gemini_pro"]

MAX_RETRIES = 2
RETRY_DELAYS = [2, 6]  # 秒
CLIENT_ERROR_CODES = (400, 401, 403, 404, 422)

# 圆桌各AI单价（美元/百万token，2026年3月）
ROUNDTABLE_PRICES = {
    "claude": {"input": 3.00, "output": 15.00},
    "gpt": {"input": 2.50, "output": 15.00},
    "gemini": {"input": 1.25, "output": 10.00},
    "grok": {"input": 0.20, "output": 0.50},
    "deepseek": {"input": 0.28, "output": 0.42},
    "perplexity_sonar_pro": {"input": 3.00, "output": 15.00},
    "perplexity_deep_research": {"input": 2.00, "output": 8.00},
}
PERPLEXITY_REQUEST_FEE = 0.005  # $5/1000次请求 = $0.005/次


def _calc_roundtable_cost(
    ai_name: str, input_tokens: int, output_tokens: int, scene_type: str = "scene_two"
) -> float:
    if ai_name == "perplexity":
        key = "perplexity_deep_research" if scene_type == "scene_one" else "perplexity_sonar_pro"
    else:
        key = ai_name
    price = ROUNDTABLE_PRICES.get(key, {"input": 0, "output": 0})
    cost = (input_tokens * price["input"] + output_tokens * price["output"]) / 1_000_000
    if ai_name == "perplexity":
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
        super().__init__(f"[{ai_name}] {reason}")


def _call_claude_sync(prompt_or_bytes, system_prompt_or_bytes, scene_type: str = "scene_two") -> tuple:
    """返回 (content, input_tokens, output_tokens)。"""
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
    # 场景④ 使用 Opus 4.6 + 官方「扩展思考」：同一模型 claude-opus-4-6，通过 thinking 参数开启
    claude_model = ROUNDTABLE_SCENE4_CLAUDE_MODEL if scene_type == "scene_four" else ROUNDTABLE_CLAUDE_MODEL
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
        kwargs["thinking"] = {"type": "adaptive"}  # Opus 4.6 推荐：自适应扩展思考，无单独 thinking 模型 ID
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
    """返回 (content, input_tokens, output_tokens)。model 为空时使用 ROUNDTABLE_GPT_MODEL。场景④ gpt-5.4-pro 推理较慢，需更长 timeout。"""
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
    使用 sonar-deep-research 模型，最多轮询 60 次（5 分钟）。
    """
    import httpx
    svc = _get_ai_service()
    api_key = svc.get("PERPLEXITY_API_KEY") or os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        raise RoundTableAIError("perplexity", "PERPLEXITY_API_KEY 未配置", is_client_error=True)
    messages = []
    if system_prompt and system_prompt.strip():
        messages.append({"role": "system", "content": system_prompt.strip()})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "request": {
            "model": "sonar-deep-research",
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
    Perplexity Sonar Pro：同步调用 chat/completions，model=sonar-pro，供场景②使用。
    """
    svc = _get_ai_service()
    api_key = svc.get("PERPLEXITY_API_KEY") or os.getenv("PERPLEXITY_API_KEY")
    if not api_key:
        raise RoundTableAIError("perplexity", "PERPLEXITY_API_KEY 未配置", is_client_error=True)
    return _call_openai_compat_sync(
        "perplexity",
        prompt,
        system_prompt.strip() or "",
        api_key,
        "sonar-pro",
        "https://api.perplexity.ai",
        False,
    )


async def call_ai(ai_name: str, prompt: str, system_prompt: str = "", scene_type: str = "scene_two") -> tuple[str, float]:
    """
    统一调用接口。ai_name 取值：claude / gpt / gemini / grok / deepseek / perplexity；
    场景④ 时可为 claude_opus / gpt_pro / gemini_pro。
    返回 (content, cost)，cost 为美元。
    出错时抛出 RoundTableAIError(ai_name, reason)。
    """
    actual_ai = ai_name
    if scene_type == "scene_four":
        if ai_name not in SUPPORTED_AIS_SCENE4:
            raise RoundTableAIError(ai_name, f"场景④ 仅支持: {SUPPORTED_AIS_SCENE4}", is_client_error=True)
        if ai_name == "claude_opus":
            actual_ai = "claude"
        elif ai_name == "gpt_pro":
            actual_ai = "gpt"
        elif ai_name == "gemini_pro":
            actual_ai = "gemini"
    elif ai_name not in SUPPORTED_AIS:
        raise RoundTableAIError(ai_name, f"不支持的 AI，可选: {SUPPORTED_AIS}", is_client_error=True)
    loop = asyncio.get_event_loop()
    svc = _get_ai_service()

    async def _do_call() -> tuple:
        """返回 (content, input_tokens, output_tokens)。"""
        if actual_ai == "claude":
            p_b = prompt.encode("utf-8")
            s_b = (system_prompt or "").encode("utf-8")
            out = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda _p=p_b, _s=s_b, _st=scene_type: _call_claude_sync(_p, _s, _st),
                ),
                timeout=600.0,
            )
            return out
        if actual_ai == "gemini":
            gemini_model = ROUNDTABLE_SCENE4_GEMINI_MODEL if scene_type == "scene_four" else None
            out = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: _call_gemini_sync(prompt, system_prompt, gemini_model),
                ),
                timeout=120.0,
            )
            return out
        if actual_ai == "gpt":
            gpt_model = ROUNDTABLE_SCENE4_GPT_MODEL if scene_type == "scene_four" else None
            # 场景④ 使用 gpt-5.4-pro，官方文档称可能需数分钟，延长至 10 分钟
            gpt_timeout = 600.0 if scene_type == "scene_four" else 120.0
            out = await asyncio.wait_for(
                asyncio.to_thread(_call_gpt_with_responses_sync, prompt, system_prompt, gpt_model, gpt_timeout),
                timeout=gpt_timeout,
            )
            return out
        if actual_ai == "deepseek":
            out = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: _call_openai_compat_sync(
                        "deepseek", prompt, system_prompt,
                        svc["DEEPSEEK_API_KEY"], ROUNDTABLE_DEEPSEEK_MODEL,
                        "https://api.deepseek.com", False,
                    ),
                ),
                timeout=120.0,
            )
            return out
        if actual_ai == "perplexity":
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
            grok_system = (system_prompt or "").strip()
            grok_system += "\n\n你可以使用实时搜索能力获取最新资料，请积极搜索相关神学资料以支撑你的论点。"
            out = await asyncio.wait_for(
                loop.run_in_executor(
                    None,
                    lambda: _call_openai_compat_sync(
                        "grok", prompt, grok_system,
                        svc["XAI_API_KEY"], ROUNDTABLE_GROK_MODEL,
                        "https://api.x.ai/v1", False,
                    ),
                ),
                timeout=120.0,
            )
            return out
        raise RoundTableAIError(ai_name, "未实现", is_client_error=True)

    for attempt in range(MAX_RETRIES + 1):
        try:
            content, in_tok, out_tok = await _do_call()
            cost = _calc_roundtable_cost(actual_ai, in_tok, out_tok, scene_type)
            logger.info(
                "[RoundTable] %s | 输入=%d tokens | 输出=%d tokens | 费用=$%.6f",
                ai_name, in_tok, out_tok, cost
            )
            return (content, cost)
        except RoundTableAIError as e:
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
                raise RoundTableAIError(ai_name, f"请求超时: {e}", is_client_error=False)
            await asyncio.sleep(RETRY_DELAYS[attempt])
            logger.warning(
                "[RoundTable] %s 第%d次失败，%d秒后重试：请求超时",
                ai_name, attempt + 1, RETRY_DELAYS[attempt],
            )
