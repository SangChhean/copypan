import logging
import os
import threading
import time
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

from gemini_response_utils import (
    extract_translatable_text,
    gemini_translation_generate_config,
    translation_max_output_tokens,
)
from translation_instructions import (
    GEMINI_TRANSLATION_SYSTEM_INSTRUCTION,
    GEMINI_TRANSLATION_SYSTEM_INSTRUCTION_EN2ZH,
)

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("translate_service")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
GEMINI_TRANSLATION_FALLBACK_MODEL = os.getenv(
    "GEMINI_TRANSLATION_FALLBACK_MODEL", "gemini-2.5-flash"
)

gemini_client = None
_gemini_system_instruction = None
_gemini_system_instruction_en2zh = None
types = None

if GEMINI_API_KEY:
    try:
        from google import genai
        from google.genai import types as genai_types

        types = genai_types
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        _gemini_system_instruction = GEMINI_TRANSLATION_SYSTEM_INSTRUCTION
        _gemini_system_instruction_en2zh = GEMINI_TRANSLATION_SYSTEM_INSTRUCTION_EN2ZH
        logger.info("Gemini 翻译模型初始化成功")
    except Exception as e:
        logger.error("Gemini 翻译模型初始化失败: %s", e)
        gemini_client = None
        _gemini_system_instruction = None
        _gemini_system_instruction_en2zh = None
else:
    logger.info("Gemini 未配置: GEMINI_API_KEY 未设置")

if gemini_client and translation_max_output_tokens:
    try:
        logger.info(
            "纲目翻译输出 token 上限（GEMINI_TRANSLATION_MAX_OUTPUT_TOKENS）: %s",
            translation_max_output_tokens(),
        )
    except Exception:
        pass


def _parse_concurrent_limit(env_key: str, default: int) -> int:
    try:
        v = int(os.getenv(env_key, str(default)))
        return max(1, v)
    except (ValueError, TypeError):
        return default


GEMINI_CONCURRENT_LIMIT = _parse_concurrent_limit("GEMINI_CONCURRENT_LIMIT", 10)
GEMINI_SEMAPHORE = threading.Semaphore(GEMINI_CONCURRENT_LIMIT)
logger.info("API 并发限制: Gemini=%s", GEMINI_CONCURRENT_LIMIT)

OUTLINE_TRANSLATE_PROMPT_ZH2EN = (
    "请将文章翻译为英文，严格使用System instructions中的专用术语表进行翻译。"
    "格式要求：①中文序号为壹，翻译为英文I.，一翻译为A.，二翻译为B.，1翻译为1.，a翻译为a.，(一)翻译为1)，以此类推；"
    "②不要缩进，直接输出；"
    "③纲目标题末尾的读经标注保持缩写格式，例如：—约三16： → —John 3:16:；"
    "④纲目正文句子中出现的经文引用，须翻译为标准英文缩写格式，例如：罗马书一章一节→Rom. 1:1，约翰福音三章十六节→John 3:16，不可译为Roman chapter 1 verse 1等展开形式。"
)
OUTLINE_TRANSLATE_PROMPT_EN2ZH = (
    "请将文章翻译为中文，严格使用System instructions中的专用术语表进行翻译。"
    "格式要求："
    "①纲目标题末尾的读经标注保持缩写格式，例如：—Rom. 3:16: → —罗三16：；"
    "②英文序号为I.，翻译为中文壹，A.翻译为一，B.翻译为二，1.翻译为1，a.翻译为a，1)翻译为(一)，以此类推；注意，纲目层级之后只加空格，不加其他符号，如：壹 神爱世人，为世人舍了自己的独生子—约三16：；"
    "③不要缩进，直接输出；"
    "④纲目正文句子中出现的经文引用（如Rom. 1:1、John 3:16），须翻译为中文完整形式，例如：Rom. 1:1→罗马书一章一节，John 3:16→约翰福音三章十六节，不可保留英文缩写或冒号数字格式。"
)


def _user_facing_translate_error(api_errors: List[str], empty_body: bool) -> str:
    """将 Gemini 异常摘要为前端可展示的中文（不泄露密钥）。"""
    if empty_body and not api_errors:
        return "模型未返回正文，可尝试缩短内容或稍后重试"
    blob = " ".join(api_errors)
    bl = blob.lower()
    if any(
        x in bl
        for x in (
            "api key",
            "api_key",
            "unauthorized",
            "401",
            "invalid authentication",
            "permission_denied",
            "permission denied",
        )
    ):
        return "Gemini API 密钥无效或未授权，请检查 .env 中的 GEMINI_API_KEY"
    if any(
        x in bl
        for x in (
            "429",
            "resource_exhausted",
            "quota",
            "rate limit",
            "too many requests",
            "exhausted",
        )
    ):
        return "调用频率或配额已达上限，请稍后再试或提高 Gemini 配额"
    if any(x in bl for x in ("404", "not_found", "is not found", "not supported for generatecontent")):
        return "当前 GEMINI_MODEL 不可用，请在 .env 中更换模型或调整 GEMINI_TRANSLATION_FALLBACK_MODEL"
    if any(
        x in bl
        for x in (
            "503",
            "unavailable",
            "500",
            "internal",
            "deadline_exceeded",
            "timeout",
            "temporary",
            "connection",
            "reset",
        )
    ):
        return "翻译服务暂时不稳定，请稍后重试"
    if any(x in bl for x in ("safety", "blocked", "recitation", "prohibited", "harmful")):
        return "内容触发安全策略未返回译文，请删减或改写后重试"
    if "max_tokens" in bl or "max token" in bl or "output_token" in bl or "length limit" in bl:
        return "译文长度达到模型输出上限，请缩短原文或分段翻译，或提高 GEMINI_TRANSLATION_MAX_OUTPUT_TOKENS"
    if api_errors:
        tail = (api_errors[-1] or "")[:280]
        return f"翻译失败：{tail}"
    return "纲目内容翻译失败，请稍后重试"


def _gemini_error_is_retryable(error_msg: str) -> bool:
    em = error_msg.lower()
    return (
        "503" in error_msg
        or "unavailable" in em
        or "429" in error_msg
        or "timeout" in em
        or "temporary" in em
        or "deadline_exceeded" in em
        or "500" in error_msg
        or "internal" in em
        or "resource_exhausted" in em
    )


def translate_outline(
    chinese_outline: str,
    outline_topic: Optional[str] = None,
) -> Dict:
    """
    将中文纲目翻译为英文纲目（调用 Gemini）。
    若未配置 GEMINI_API_KEY 返回 error；失败时重试 1 次。
    同时翻译纲目主题作为英文标题（若提供 outline_topic）。
    """
    MAX_OUTLINE_LENGTH = 100_000

    outline = (chinese_outline or "").strip()
    if not outline:
        return {"answer_en": None, "title_en": None, "error": "中文纲目为空"}
    if len(outline) > MAX_OUTLINE_LENGTH:
        return {
            "answer_en": None,
            "title_en": None,
            "error": f"中文纲目过长（最多 {MAX_OUTLINE_LENGTH} 字）",
        }

    if not gemini_client:
        return {"answer_en": None, "error": "英文翻译服务未配置（请设置 GEMINI_API_KEY）"}

    contents_zh2en = outline + "\n\n" + OUTLINE_TRANSLATE_PROMPT_ZH2EN
    _last_error_model_not_found = [False]
    _last_error_retryable = [False]
    _last_error_empty = [False]
    zh2en_api_errors: List[str] = []

    def _is_model_not_found(err: str) -> bool:
        return "404" in err or "NOT_FOUND" in err or "is not found" in err.lower()

    def _zh2en_config():
        if gemini_translation_generate_config:
            return gemini_translation_generate_config(_gemini_system_instruction)
        return types.GenerateContentConfig(system_instruction=_gemini_system_instruction)

    def _call_gemini(retry_count: int = 0, model: Optional[str] = None) -> Optional[tuple]:
        use_model = model or GEMINI_MODEL
        with GEMINI_SEMAPHORE:
            try:
                response = gemini_client.models.generate_content(
                    model=use_model,
                    contents=contents_zh2en,
                    config=_zh2en_config(),
                )
                log_p = f"[Gemini翻译] model={use_model}"
                if extract_translatable_text:
                    text = extract_translatable_text(response, log_p)
                else:
                    rt = getattr(response, "text", None) if response else None
                    text = rt.strip() if isinstance(rt, str) and rt.strip() else None
                if text:
                    tokens_zh2en = None
                    try:
                        usage_meta = response.usage_metadata
                        in_tok = int(getattr(usage_meta, "prompt_token_count", 0) or 0)
                        out_tok = int(getattr(usage_meta, "candidates_token_count", 0) or 0)
                        cost = (in_tok * 1.25 + out_tok * 10) / 1_000_000
                        logger.info(
                            "[Gemini翻译] model=%s | 输入=%d tokens | 输出=%d tokens | 费用=$%.6f",
                            use_model,
                            in_tok,
                            out_tok,
                            cost,
                        )
                        tokens_zh2en = {"input": in_tok, "output": out_tok, "cost": cost}
                    except Exception:
                        pass
                    return (text, tokens_zh2en)
                _last_error_empty[0] = True
                logger.warning("Gemini 翻译返回空响应（重试次数: %s）", retry_count)
            except Exception as e:
                error_msg = str(e)
                zh2en_api_errors.append(error_msg)
                if _is_model_not_found(error_msg):
                    _last_error_model_not_found[0] = True
                    logger.warning(
                        "Gemini 模型不可用(404): %s，将尝试备用模型 %s",
                        e,
                        GEMINI_TRANSLATION_FALLBACK_MODEL,
                    )
                is_retryable = _gemini_error_is_retryable(error_msg)
                if is_retryable:
                    _last_error_retryable[0] = True
                if is_retryable and retry_count == 0:
                    logger.warning("Gemini 翻译调用失败（可重试）: %s，等待2秒后重试...", e)
                    time.sleep(2)
                else:
                    logger.warning("Gemini 翻译调用失败（重试次数: %s）: %s", retry_count, e)
        return None

    result = _call_gemini(retry_count=0)
    if result is not None:
        answer_en, tokens_zh2en = result[0], result[1]
    else:
        answer_en, tokens_zh2en = None, None
    if answer_en is None:
        result = _call_gemini(retry_count=1)
        if result is not None:
            answer_en, tokens_zh2en = result[0], result[1]
    if answer_en is None and (
        _last_error_model_not_found[0]
        or _last_error_retryable[0]
        or _last_error_empty[0]
    ) and GEMINI_TRANSLATION_FALLBACK_MODEL != GEMINI_MODEL:
        _fb_reason = (
            "模型不存在"
            if _last_error_model_not_found[0]
            else "主模型返回空正文"
            if _last_error_empty[0]
            else "主模型负载过高/暂不可用"
        )
        logger.info(
            "使用备用模型进行中翻英: %s（原因: %s）",
            GEMINI_TRANSLATION_FALLBACK_MODEL,
            _fb_reason,
        )
        result = _call_gemini(retry_count=0, model=GEMINI_TRANSLATION_FALLBACK_MODEL)
        if result is not None:
            answer_en, tokens_zh2en = result[0], result[1]
        if answer_en is None:
            result = _call_gemini(retry_count=1, model=GEMINI_TRANSLATION_FALLBACK_MODEL)
            if result is not None:
                answer_en, tokens_zh2en = result[0], result[1]

    title_en = None
    if outline_topic and outline_topic.strip():
        topic = outline_topic.strip()
        _title_model_not_found = [False]
        _title_retryable = [False]
        _title_empty = [False]

        def _title_cfg_main():
            if gemini_translation_generate_config:
                return gemini_translation_generate_config(_gemini_system_instruction)
            return types.GenerateContentConfig(system_instruction=_gemini_system_instruction)

        def _translate_title(retry_count: int = 0, model: Optional[str] = None) -> Optional[str]:
            use_model = model or GEMINI_MODEL
            with GEMINI_SEMAPHORE:
                try:
                    title_response = gemini_client.models.generate_content(
                        model=use_model,
                        contents=topic,
                        config=_title_cfg_main(),
                    )
                    log_tm = f"[Gemini标题] model={use_model}"
                    if extract_translatable_text:
                        raw_title = extract_translatable_text(title_response, log_tm)
                    else:
                        rt = getattr(title_response, "text", None) if title_response else None
                        raw_title = rt.strip() if isinstance(rt, str) and rt.strip() else None
                    if raw_title:
                        title_en_clean = raw_title
                        prefixes_to_remove = [
                            "Translation:",
                            "English:",
                            "翻译：",
                            "英文：",
                            "The translation is:",
                            "Here is the translation:",
                            "Title:",
                            "标题：",
                        ]
                        for prefix in prefixes_to_remove:
                            if title_en_clean.lower().startswith(prefix.lower()):
                                title_en_clean = title_en_clean[len(prefix) :].strip()
                        title_en_clean = title_en_clean.strip('"\'')
                        return title_en_clean
                    _title_empty[0] = True
                    logger.warning("标题翻译返回空响应（重试次数: %s）", retry_count)
                except Exception as e:
                    error_msg = str(e)
                    if _is_model_not_found(error_msg):
                        _title_model_not_found[0] = True
                    is_retryable = _gemini_error_is_retryable(error_msg)
                    if is_retryable:
                        _title_retryable[0] = True
                    if is_retryable and retry_count == 0:
                        logger.warning("标题翻译调用失败（可重试）: %s，等待2秒后重试...", e)
                        time.sleep(2)
                    else:
                        logger.warning("标题翻译调用失败（重试次数: %s）: %s", retry_count, e)
            return None

        title_en = _translate_title(retry_count=0)
        if title_en is None:
            title_en = _translate_title(retry_count=1)
        if title_en is None and (
            _title_model_not_found[0] or _title_retryable[0] or _title_empty[0]
        ) and GEMINI_TRANSLATION_FALLBACK_MODEL != GEMINI_MODEL:
            title_en = _translate_title(retry_count=0, model=GEMINI_TRANSLATION_FALLBACK_MODEL)
            if title_en is None:
                title_en = _translate_title(retry_count=1, model=GEMINI_TRANSLATION_FALLBACK_MODEL)

        if title_en:
            logger.info("标题翻译成功: '%s' -> '%s'", topic, title_en)
        else:
            logger.warning("标题翻译失败（已重试1次）: '%s'", topic)

    if answer_en is None:
        return {
            "answer_en": None,
            "title_en": title_en,
            "error": _user_facing_translate_error(zh2en_api_errors, _last_error_empty[0]),
        }

    return {
        "answer_en": answer_en,
        "title_en": title_en,
        "tokens": tokens_zh2en or {"input": 0, "output": 0, "cost": 0},
    }


def translate_outline_en2zh(english_outline: str) -> Dict:
    """
    将英文纲目翻译为中文纲目（调用 Gemini，使用英翻中 instruction）。
    失败时重试 1 次。
    """
    MAX_OUTLINE_LENGTH = 100_000
    outline = (english_outline or "").strip()
    if not outline:
        return {"answer_zh": None, "error": "英文纲目为空"}
    if len(outline) > MAX_OUTLINE_LENGTH:
        return {"answer_zh": None, "error": f"英文纲目过长（最多 {MAX_OUTLINE_LENGTH} 字）"}

    if not gemini_client:
        return {"answer_zh": None, "error": "英文翻译服务未配置（请设置 GEMINI_API_KEY）"}
    if not _gemini_system_instruction_en2zh:
        return {"answer_zh": None, "error": "英翻中 instruction 未配置"}

    contents_en2zh = outline + "\n\n" + OUTLINE_TRANSLATE_PROMPT_EN2ZH
    _last_error_model_not_found = [False]
    _last_error_retryable = [False]
    _last_error_empty = [False]
    en2zh_api_errors: List[str] = []

    def _is_model_not_found(err: str) -> bool:
        return "404" in err or "NOT_FOUND" in err or "is not found" in err.lower()

    def _en2zh_config():
        if gemini_translation_generate_config:
            return gemini_translation_generate_config(_gemini_system_instruction_en2zh)
        return types.GenerateContentConfig(system_instruction=_gemini_system_instruction_en2zh)

    def _call_gemini(retry_count: int = 0, model: Optional[str] = None) -> Optional[tuple]:
        use_model = model or GEMINI_MODEL
        with GEMINI_SEMAPHORE:
            try:
                response = gemini_client.models.generate_content(
                    model=use_model,
                    contents=contents_en2zh,
                    config=_en2zh_config(),
                )
                log_p = f"[Gemini英翻中] model={use_model}"
                if extract_translatable_text:
                    text = extract_translatable_text(response, log_p)
                else:
                    rt = getattr(response, "text", None) if response else None
                    text = rt.strip() if isinstance(rt, str) and rt.strip() else None
                if text:
                    tokens_en2zh = None
                    try:
                        usage_meta = response.usage_metadata
                        in_tok = int(getattr(usage_meta, "prompt_token_count", 0) or 0)
                        out_tok = int(getattr(usage_meta, "candidates_token_count", 0) or 0)
                        cost = (in_tok * 1.25 + out_tok * 10) / 1_000_000
                        logger.info(
                            "[Gemini英翻中] model=%s | 输入=%d tokens | 输出=%d tokens | 费用=$%.6f",
                            use_model,
                            in_tok,
                            out_tok,
                            cost,
                        )
                        tokens_en2zh = {"input": in_tok, "output": out_tok, "cost": cost}
                    except Exception:
                        pass
                    return (text, tokens_en2zh)
                _last_error_empty[0] = True
                logger.warning("Gemini 英翻中返回空响应（重试次数: %s）", retry_count)
            except Exception as e:
                error_msg = str(e)
                en2zh_api_errors.append(error_msg)
                if _is_model_not_found(error_msg):
                    _last_error_model_not_found[0] = True
                    logger.warning(
                        "Gemini 模型不可用(404): %s，将尝试备用模型 %s",
                        e,
                        GEMINI_TRANSLATION_FALLBACK_MODEL,
                    )
                is_retryable = _gemini_error_is_retryable(error_msg)
                if is_retryable:
                    _last_error_retryable[0] = True
                if is_retryable and retry_count == 0:
                    logger.warning("Gemini 英翻中调用失败（可重试）: %s，等待2秒后重试...", e)
                    time.sleep(2)
                else:
                    logger.warning("Gemini 英翻中调用失败（重试次数: %s）: %s", retry_count, e)
        return None

    result = _call_gemini(retry_count=0)
    if result is not None:
        answer_zh, tokens_en2zh = result[0], result[1]
    else:
        answer_zh, tokens_en2zh = None, None
    if answer_zh is None:
        result = _call_gemini(retry_count=1)
        if result is not None:
            answer_zh, tokens_en2zh = result[0], result[1]
    if answer_zh is None and (
        _last_error_model_not_found[0]
        or _last_error_retryable[0]
        or _last_error_empty[0]
    ) and GEMINI_TRANSLATION_FALLBACK_MODEL != GEMINI_MODEL:
        _fb_reason_e2z = (
            "模型不存在"
            if _last_error_model_not_found[0]
            else "主模型返回空正文"
            if _last_error_empty[0]
            else "主模型负载过高/暂不可用"
        )
        logger.info(
            "使用备用模型进行英翻中: %s（原因: %s）",
            GEMINI_TRANSLATION_FALLBACK_MODEL,
            _fb_reason_e2z,
        )
        result = _call_gemini(retry_count=0, model=GEMINI_TRANSLATION_FALLBACK_MODEL)
        if result is not None:
            answer_zh, tokens_en2zh = result[0], result[1]
        if answer_zh is None:
            result = _call_gemini(retry_count=1, model=GEMINI_TRANSLATION_FALLBACK_MODEL)
            if result is not None:
                answer_zh, tokens_en2zh = result[0], result[1]
    if answer_zh is None:
        return {
            "answer_zh": None,
            "error": _user_facing_translate_error(en2zh_api_errors, _last_error_empty[0]),
        }
    return {
        "answer_zh": answer_zh,
        "tokens": tokens_en2zh or {"input": 0, "output": 0, "cost": 0},
    }
