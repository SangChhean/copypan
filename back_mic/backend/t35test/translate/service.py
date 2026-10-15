# -*- coding: utf-8 -*-
"""【3.5测试用】独立的翻译 / 繁体转换 / 格式化服务。

由主站 ai_search/ai_service.py 中的 translate_outline、outline_to_traditional、
format_outline_only（及其依赖）原样复制而来；与主站互不引用，缓存键前缀为 t35test:。
"""
import hashlib
import json
import logging
import os
import re
import threading
import time
import warnings
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from t35test.common import get_monitoring, redis_client

logger = logging.getLogger("t35test")

# 格式刷（t35test 自己的副本）
try:
    from t35test.translate.formatters.format_chinese_outline import format_chinese_outline_docx
    from t35test.translate.formatters.format_english_outline import format_english_outline_docx, format_plain_docx
except Exception as e:  # pragma: no cover
    format_chinese_outline_docx = None
    format_english_outline_docx = None
    format_plain_docx = None
    logger.warning(f"格式刷模块导入失败，格式化功能将不可用: {e}", exc_info=True)

# Gemini（用于中文纲目→英文纲目翻译）
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
GEMINI_TRANSLATION_FALLBACK_MODEL = os.getenv("GEMINI_TRANSLATION_FALLBACK_MODEL", "gemini-2.5-pro")
gemini_client = None
types = None
_gemini_system_instruction = None
if GEMINI_API_KEY:
    try:
        from google import genai
        from google.genai import types
        from t35test.translate.gemini_translation_instruction import GEMINI_TRANSLATION_SYSTEM_INSTRUCTION

        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        _gemini_system_instruction = GEMINI_TRANSLATION_SYSTEM_INSTRUCTION
        logger.info("[t35test] Gemini 翻译模型初始化成功")
    except Exception as e:
        logger.error(f"[t35test] Gemini 翻译模型初始化失败: {e}")
        gemini_client = None
        _gemini_system_instruction = None
else:
    logger.info("[t35test] Gemini 未配置: GEMINI_API_KEY 未设置")

try:
    from t35test.translate.gemini_response_utils import (
        extract_translatable_text,
        gemini_translation_generate_config,
        translation_max_output_tokens,
    )
except ImportError:
    gemini_translation_generate_config = None
    extract_translatable_text = None
    translation_max_output_tokens = None  # type: ignore[misc, assignment]

def _parse_concurrent_limit(env_key: str, default: int) -> int:
    try:
        v = int(os.getenv(env_key, str(default)))
        return max(1, v)  # 至少为 1，避免 Semaphore(0) 导致永久阻塞
    except (ValueError, TypeError):
        return default

GEMINI_CONCURRENT_LIMIT = _parse_concurrent_limit("GEMINI_CONCURRENT_LIMIT", 10)

GEMINI_SEMAPHORE = threading.Semaphore(GEMINI_CONCURRENT_LIMIT)

OUTLINE_TRANSLATE_PROMPT_ZH2EN = (
    "请将文章翻译为英文，严格使用System instructions中的专用术语表进行翻译。"
    "格式要求：①中文序号为壹，翻译为英文I.，一翻译为A.，二翻译为B.，1翻译为1.，a翻译为a.，(一)翻译为1)，以此类推；"
    "②不要缩进，直接输出；"
    "③纲目标题末尾的读经标注保持缩写格式，例如：—约三16： → —John 3:16:；"
    "④纲目正文句子中出现的经文引用，须翻译为标准英文缩写格式，例如：罗马书一章一节→Rom. 1:1，约翰福音三章十六节→John 3:16，不可译为Roman chapter 1 verse 1等展开形式。"
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

_ERROR_CHAR_PAIRS: List[Tuple[str, str]] = [
    ("預", "豫"), ("顆樹", "棵樹"), ("秘", "祕"), ("才是", "纔是"),
    ("才會", "纔會"), ("什", "甚"), ("台", "臺"), ("意象", "異象"),
    ("兇", "凶"), ("份", "分"), ("吃", "喫"), ("吧", "罷"),
    ("恒", "恆"), ("唇", "脣"), ("做人", "作人"), ("做事", "作事"),
    ("做工", "作工"), ("啊", "阿"), ("唯", "惟"), ("唸", "念"),
    ("卡喳", "咔喳"), ("夠", "彀"), ("証 ", "證"), ("腊", "臘"),
    ("嗎？", "麼？"), ("裡", "裏"), ("葯", "藥"), ("嘆", "歎"),
    ("摻", "攙"), ("燄", "焰"), ("嚐", "嘗"), ("餵", "餧"),
    ("鎗", "槍"), ("顋", "腮"), ("效忠", "効忠"), ("抱雛", "菢雛"),
    ("計劃", "計畫"), ("提醒", "題醒"), ("借著", "藉著"),
    ("口喫", "口吃"), ("撒旦", "撒但"), ("形象", "形像"), ("峯", "峰"),
    ("翻譯", "繙譯"), ("對像", "對象"), ("psrp", "禱、研、背、講"),
    ("bnpb", "生、養、教、建"), ("創世紀", "創世記"), ("了結以往", "了結已往"),
    ("景像", "景象"), ("掛慮", "罣慮"), ("束板", "豎板"), ("先軀", "先驅"),
    ("深遂", "深邃"), ("喜悦", "喜悅"), ("才知道", "纔知道"),
    ("複習", "復習"), ("重覆", "重複"), ("撲倒", "仆倒"),
    ("必像必肖", "畢像畢肖"), ("罪於死的律", "罪與死的律"), ("發芽結石", "發芽結實"),
]


class TranslateService:
    def __init__(self):
        self.redis = redis_client

    def translate_outline(
        self,
        chinese_outline: str,
        outline_topic: Optional[str] = None,
        use_cache: bool = True,
    ) -> Dict:
        """
        将中文纲目翻译为英文纲目（调用 Gemini）。
        若未配置 GEMINI_API_KEY 返回 error；失败时重试 1 次。
        use_cache=True（如 AI 纲目流程）时按中文内容 hash 缓存 24 小时；use_cache=False（如工具箱 - 纲目翻译）时不缓存。
        同时翻译纲目主题作为英文标题（若提供 outline_topic）。
        """
        MAX_OUTLINE_LENGTH = 100_000
        TRANSLATE_CACHE_TTL = 86400  # 24 小时

        outline = (chinese_outline or "").strip()
        if not outline:
            return {"answer_en": None, "title_en": None, "error": "中文纲目为空"}
        if len(outline) > MAX_OUTLINE_LENGTH:
            return {"answer_en": None, "title_en": None, "error": f"中文纲目过长（最多 {MAX_OUTLINE_LENGTH} 字）"}

        cache_key = f"t35test:translate:{hashlib.sha256(outline.encode()).hexdigest()[:32]}"
        if use_cache and self.redis:
            try:
                cached = self.redis.get(cache_key)
                if cached:
                    data = json.loads(cached)
                    cached_answer = data.get("answer_en")
                    cached_title = data.get("title_en")
                    if cached_answer:
                        if outline_topic and outline_topic.strip() and not cached_title:
                            topic = outline_topic.strip()
                            _cache_title_404 = [False]
                            _cache_title_retryable = [False]
                            _cache_title_empty = [False]

                            def _title_cfg_cache(model_name: str):
                                if gemini_translation_generate_config:
                                    return gemini_translation_generate_config(
                                        _gemini_system_instruction, model_name=model_name
                                    )
                                return types.GenerateContentConfig(system_instruction=_gemini_system_instruction)

                            def _translate_title_for_cache(
                                retry_count: int = 0, model: Optional[str] = None
                            ) -> Optional[str]:
                                use_model = model or GEMINI_MODEL
                                with GEMINI_SEMAPHORE:
                                    try:
                                        title_response = gemini_client.models.generate_content(
                                            model=use_model,
                                            contents=topic,
                                            config=_title_cfg_cache(use_model),
                                        )
                                        log_tc = f"[Gemini翻译-缓存标题] model={use_model}"
                                        if extract_translatable_text:
                                            raw_title = extract_translatable_text(title_response, log_tc)
                                        else:
                                            rt = getattr(title_response, "text", None) if title_response else None
                                            raw_title = rt.strip() if isinstance(rt, str) and rt.strip() else None
                                        if raw_title:
                                            title_en_clean = raw_title
                                            prefixes_to_remove = [
                                                "Translation:", "English:", "翻译：", "英文：",
                                                "The translation is:", "Here is the translation:",
                                                "Title:", "标题："
                                            ]
                                            for prefix in prefixes_to_remove:
                                                if title_en_clean.lower().startswith(prefix.lower()):
                                                    title_en_clean = title_en_clean[len(prefix):].strip()
                                            title_en_clean = title_en_clean.strip('"\'')
                                            try:
                                                usage_meta = getattr(title_response, "usage_metadata", None)
                                                in_tok = int(getattr(usage_meta, "prompt_token_count", 0) or 0)
                                                out_tok = int(getattr(usage_meta, "candidates_token_count", 0) or 0)
                                                cost = (in_tok * 1.25 + out_tok * 10) / 1_000_000
                                                logger.info(
                                                    "[Gemini翻译-缓存标题] model=%s | 输入=%d tokens | 输出=%d tokens | 费用=$%.6f",
                                                    use_model, in_tok, out_tok, cost,
                                                )
                                                if self.redis:
                                                    get_monitoring(self.redis).record_tool_usage(
                                                        "translation_cache_title", use_model, in_tok, out_tok, cost
                                                    )
                                            except Exception:
                                                pass
                                            return title_en_clean
                                        _cache_title_empty[0] = True
                                        logger.warning("缓存标题翻译返回空响应（重试次数: %s）", retry_count)
                                    except Exception as e:
                                        error_msg = str(e)
                                        if "404" in error_msg or "NOT_FOUND" in error_msg or "is not found" in error_msg.lower():
                                            _cache_title_404[0] = True
                                        is_retryable = _gemini_error_is_retryable(error_msg)
                                        if is_retryable:
                                            _cache_title_retryable[0] = True
                                        if is_retryable and retry_count == 0:
                                            logger.warning("缓存标题翻译调用失败（可重试）: %s，等待2秒后重试...", e)
                                            time.sleep(2)
                                        else:
                                            logger.warning("缓存标题翻译调用失败（重试次数: %s）: %s", retry_count, e)
                                return None

                            cached_title = _translate_title_for_cache(retry_count=0)
                            if cached_title is None:
                                cached_title = _translate_title_for_cache(retry_count=1)
                            if cached_title is None and (
                                _cache_title_404[0] or _cache_title_retryable[0] or _cache_title_empty[0]
                            ) and GEMINI_TRANSLATION_FALLBACK_MODEL != GEMINI_MODEL:
                                cached_title = _translate_title_for_cache(
                                    retry_count=0, model=GEMINI_TRANSLATION_FALLBACK_MODEL
                                )
                                if cached_title is None:
                                    cached_title = _translate_title_for_cache(
                                        retry_count=1, model=GEMINI_TRANSLATION_FALLBACK_MODEL
                                    )
                            if cached_title:
                                logger.info("缓存标题翻译成功: '%s' -> '%s'", topic, cached_title)
                            else:
                                logger.warning("缓存标题翻译失败（已重试1次）: '%s'", topic)
                        return {"answer_en": cached_answer, "title_en": cached_title}
            except Exception as e:
                logger.debug("翻译缓存读取失败: %s", e)

        if not gemini_client:
            return {"answer_en": None, "error": "英文翻译服务未配置（请设置 GEMINI_API_KEY）"}

        # 发送内容 = 需要翻译的文章 + 格式与术语说明（中翻英）
        contents_zh2en = outline + "\n\n" + OUTLINE_TRANSLATE_PROMPT_ZH2EN
        _last_error_model_not_found = [False]  # 404 / model not found
        _last_error_retryable = [False]         # 503 / 429 / timeout 等临时性失败
        _last_error_empty = [False]             # 调用成功但无可翻译正文
        zh2en_api_errors: List[str] = []

        def _is_model_not_found(err: str) -> bool:
            return "404" in err or "NOT_FOUND" in err or "is not found" in err.lower()

        def _zh2en_config(model_name: str):
            if gemini_translation_generate_config:
                return gemini_translation_generate_config(
                    _gemini_system_instruction, model_name=model_name
                )
            return types.GenerateContentConfig(system_instruction=_gemini_system_instruction)

        def _call_gemini(retry_count: int = 0, model: Optional[str] = None) -> Optional[tuple]:
            use_model = model or GEMINI_MODEL
            with GEMINI_SEMAPHORE:
                try:
                    response = gemini_client.models.generate_content(
                        model=use_model,
                        contents=contents_zh2en,
                        config=_zh2en_config(use_model),
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
                            logger.info(f"[Gemini翻译] model={use_model} | 输入={in_tok} tokens | 输出={out_tok} tokens | 费用=${cost:.6f}")
                            if self.redis:
                                get_monitoring(self.redis).record_tool_usage("translation_zh2en", use_model, in_tok, out_tok, cost)
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
                        logger.warning(f"Gemini 模型不可用(404): {e}，将尝试备用模型 {GEMINI_TRANSLATION_FALLBACK_MODEL}")
                    is_retryable = _gemini_error_is_retryable(error_msg)
                    if is_retryable:
                        _last_error_retryable[0] = True
                    if is_retryable and retry_count == 0:
                        logger.warning(f"Gemini 翻译调用失败（可重试）: {e}，等待2秒后重试...")
                        time.sleep(2)
                    else:
                        logger.warning(f"Gemini 翻译调用失败（重试次数: {retry_count}）: {e}")
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
            _last_error_model_not_found[0] or _last_error_retryable[0] or _last_error_empty[0]
        ) and GEMINI_TRANSLATION_FALLBACK_MODEL != GEMINI_MODEL:
            _fb_reason = (
                "模型不存在"
                if _last_error_model_not_found[0]
                else "主模型返回空正文"
                if _last_error_empty[0]
                else "主模型负载过高/暂不可用"
            )
            logger.info("使用备用模型进行中翻英: %s（原因: %s）", GEMINI_TRANSLATION_FALLBACK_MODEL, _fb_reason)
            result = _call_gemini(retry_count=0, model=GEMINI_TRANSLATION_FALLBACK_MODEL)
            if result is not None:
                answer_en, tokens_zh2en = result[0], result[1]
            if answer_en is None:
                result = _call_gemini(retry_count=1, model=GEMINI_TRANSLATION_FALLBACK_MODEL)
                if result is not None:
                    answer_en, tokens_zh2en = result[0], result[1]
        
        # 翻译标题（如果提供）- 独立执行，即使纲目内容翻译失败也尝试翻译标题
        title_en = None
        if outline_topic and outline_topic.strip():
            topic = outline_topic.strip()
            _title_model_not_found = [False]
            _title_retryable = [False]
            _title_empty = [False]

            def _title_cfg_main(model_name: str):
                if gemini_translation_generate_config:
                    return gemini_translation_generate_config(
                        _gemini_system_instruction, model_name=model_name
                    )
                return types.GenerateContentConfig(system_instruction=_gemini_system_instruction)

            def _translate_title(retry_count: int = 0, model: Optional[str] = None) -> Optional[str]:
                """翻译标题，带重试逻辑；model 为空则用 GEMINI_MODEL"""
                use_model = model or GEMINI_MODEL
                with GEMINI_SEMAPHORE:
                    try:
                        title_response = gemini_client.models.generate_content(
                            model=use_model,
                            contents=topic,
                            config=_title_cfg_main(use_model),
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
                                "Translation:", "English:", "翻译：", "英文：",
                                "The translation is:", "Here is the translation:",
                                "Title:", "标题："
                            ]
                            for prefix in prefixes_to_remove:
                                if title_en_clean.lower().startswith(prefix.lower()):
                                    title_en_clean = title_en_clean[len(prefix):].strip()
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
                            logger.warning(f"标题翻译调用失败（可重试）: {e}，等待2秒后重试...")
                            time.sleep(2)
                        else:
                            logger.warning(f"标题翻译调用失败（重试次数: {retry_count}）: {e}")
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
                logger.info(f"标题翻译成功: '{topic}' -> '{title_en}'")
            else:
                logger.warning(f"标题翻译失败（已重试1次）: '{topic}'")
        
        # 如果纲目内容翻译失败，返回错误（但标题翻译结果仍会返回）
        if answer_en is None:
            return {
                "answer_en": None,
                "title_en": title_en,
                "error": _user_facing_translate_error(zh2en_api_errors, _last_error_empty[0]),
            }

        if use_cache and self.redis:
            try:
                cache_data = {"answer_en": answer_en}
                if title_en:
                    cache_data["title_en"] = title_en
                self.redis.setex(
                    cache_key,
                    TRANSLATE_CACHE_TTL,
                    json.dumps(cache_data, ensure_ascii=False),
                )
            except Exception as e:
                logger.debug("翻译缓存写入失败: %s", e)

        return {"answer_en": answer_en, "title_en": title_en, "tokens": tokens_zh2en or {"input": 0, "output": 0, "cost": 0}}

    def outline_to_traditional(self, content: str) -> Dict[str, Optional[str]]:
        """
        将简体纲目转为繁体：先按术语表替换，再 OpenCC s2t（失败回退 zhconv zh-hant）。
        用于 AI 纲目制作「同时生成繁体纲目」。
        
        Args:
            content: 简体中文纲目全文
        
        Returns:
            {"answer_zh_tw": str} 成功时；{"answer_zh_tw": None, "error": str} 失败时
        """
        if not (content or "").strip():
            return {"answer_zh_tw": None, "error": "内容为空"}
        text = (content or "").strip()
        try:
            # 1. 加载台湾繁简术语表（简体 -> 繁体）
            terms_path = Path(__file__).resolve().parents[4] / "shared" / "zh_tw_terms.json"
            placeholders: List[tuple] = []  # (placeholder_str, target_value)
            if terms_path.exists():
                terms = json.loads(terms_path.read_text(encoding="utf-8"))
                # 按键长降序，先替换长词避免短词截断
                sorted_keys = sorted(terms.keys(), key=len, reverse=True)
                for idx, simp in enumerate(sorted_keys):
                    trad = terms[simp]
                    if simp and trad is not None:
                        # 用占位符替换，避免 zhconv 把术语表结果再改掉（如「了解」→「瞭解」）
                        ph = f"__TW_{idx}__"
                        placeholders.append((ph, trad))
                        text = text.replace(simp, ph)
            else:
                logger.warning("繁简术语表不存在: %s，仅做通用简繁转换", terms_path)
            # 2. 通用简→繁体（优先 OpenCC s2t，占位符为 ASCII 不会被改动）
            try:
                from opencc import OpenCC
                cc = OpenCC("s2t")
                text = cc.convert(text)
            except Exception:
                try:
                    import zhconv
                    text = zhconv.convert(text, "zh-hant")
                except ImportError:
                    logger.warning("OpenCC/zhconv 未安装，无法做通用简繁转换")
                    return {"answer_zh_tw": None, "error": "繁简转换依赖未安装（opencc 或 zhconv）"}
            # 3. 把占位符还原为术语表里的目标用字
            for ph, trad in placeholders:
                text = text.replace(ph, trad)
            # 4. 静默替换易错字（_ERROR_CHAR_PAIRS，无需用户确认）
            for wrong, right in _ERROR_CHAR_PAIRS:
                text = text.replace(wrong, right)
            return {"answer_zh_tw": text}
        except Exception as e:
            logger.error("简转繁失败: %s", e, exc_info=True)
            return {"answer_zh_tw": None, "error": str(e)}

    def _convert_docx_to_pdf(self, docx_path: str) -> Optional[bytes]:
        """
        将 DOCX 文件转换为 PDF bytes。
        优先使用 LibreOffice（Linux），回退到 docx2pdf（Windows/Mac）。
        
        Args:
            docx_path: DOCX 文件路径
        
        Returns:
            PDF bytes，失败时返回 None
        """
        import tempfile
        import os
        import subprocess
        import platform
        
        # 检查 DOCX 文件是否存在
        if not os.path.exists(docx_path):
            logger.error(f"DOCX 文件不存在: {docx_path}")
            return None
        
        # 创建临时 PDF 文件
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp_pdf:
            pdf_path = tmp_pdf.name
        
        logger.info(f"开始转换 DOCX 到 PDF: {docx_path} -> {pdf_path}")
        
        # 方法1: 尝试使用 LibreOffice（Linux）
        try:
            # 检查 LibreOffice 是否可用
            result = subprocess.run(
                ["which", "libreoffice"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # 使用 LibreOffice 转换
                # 获取输出目录（PDF 文件所在目录）
                output_dir = os.path.dirname(pdf_path)
                # LibreOffice 会生成文件名，我们需要指定完整路径
                # 先转换，然后重命名
                temp_output_dir = output_dir
                temp_output_name = os.path.splitext(os.path.basename(docx_path))[0] + ".pdf"
                
                # 使用 PDF/A-2b 导出，会嵌入全部字体，避免移动端打开乱码
                pdf_export_opts = 'pdf:writer_pdf_Export:{"SelectPdfVersion":{"type":"long","value":"2"}}'
                convert_result = subprocess.run(
                    [
                        "libreoffice",
                        "--headless",
                        "--convert-to", pdf_export_opts,
                        "--outdir", temp_output_dir,
                        docx_path
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                
                if convert_result.returncode == 0:
                    # LibreOffice 会在输出目录生成 PDF，文件名基于输入文件名
                    generated_pdf = os.path.join(temp_output_dir, temp_output_name)
                    if os.path.exists(generated_pdf):
                        # 移动到目标位置
                        if generated_pdf != pdf_path:
                            os.rename(generated_pdf, pdf_path)
                        
                        # 检查 PDF 文件是否生成成功
                        if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                            # 读取 PDF bytes
                            with open(pdf_path, "rb") as f:
                                pdf_bytes = f.read()
                            
                            logger.info(f"PDF 转换成功（LibreOffice）: 大小 {len(pdf_bytes)} bytes")
                            
                            # 清理临时文件
                            try:
                                os.unlink(pdf_path)
                            except Exception:
                                pass
                            
                            return pdf_bytes
        except FileNotFoundError:
            logger.debug("LibreOffice 未找到，尝试其他方法")
        except subprocess.TimeoutExpired:
            logger.warning("LibreOffice 转换超时")
        except Exception as e:
            logger.warning(f"LibreOffice 转换失败: {e}")
        
        # 方法2: 回退到 docx2pdf（Windows/Mac，或 Linux 上如果安装了 MS Word）
        # Windows 下 win32com 要求当前线程已调用 CoInitialize，否则报「尚未调用 CoInitialize」
        import sys
        if sys.platform == "win32":
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except Exception:
                pass
        try:
            from docx2pdf import convert
            convert(docx_path, pdf_path)
            
            # 检查 PDF 文件是否生成成功
            if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                # 读取 PDF bytes
                with open(pdf_path, "rb") as f:
                    pdf_bytes = f.read()
                
                logger.info(f"PDF 转换成功（docx2pdf）: 大小 {len(pdf_bytes)} bytes")
                
                # 清理临时文件
                try:
                    os.unlink(pdf_path)
                except Exception:
                    pass
                
                return pdf_bytes
        except NotImplementedError as e:
            logger.error(f"DOCX 转 PDF 失败: {e}")
        except Exception as e:
            logger.error(f"DOCX 转 PDF 失败: {e}", exc_info=True)
        
        # 清理临时文件
        try:
            if os.path.exists(pdf_path):
                os.unlink(pdf_path)
        except Exception:
            pass
        
        return None

    def format_outline_only(
        self,
        direction: str,
        translated_text: str,
        output_format: str = "docx",
        is_outline: bool = True,
    ) -> Dict:
        """
        仅格式化已翻译的纲目文本（不调用翻译 API）。
        
        Args:
            direction: "zh2en" 或 "en2zh"（用于确定使用哪个模板和格式刷函数）
            translated_text: 已翻译的纲目文本
            output_format: "docx" 或 "pdf"，默认 "docx"
            is_outline: True=纲目格式刷，False=通用平铺格式刷（末尾无标点→居中加粗，其余→paragraph 样式）
        
        Returns:
            {
                "docx_bytes": bytes | None,  # DOCX bytes（output_format="docx" 时）
                "pdf_bytes": bytes | None,  # PDF bytes（output_format="pdf" 时）
                "filename": str | None,  # 建议的文件名
                "error": str | None,  # 错误信息
            }
        """
        import shutil
        import tempfile
        from docx import Document

        # 根据方向确定模板和格式刷函数
        if direction == "zh2en":
            template_name = "英文纲目模板.docx"
            format_func = format_english_outline_docx if is_outline else format_plain_docx
            default_filename = "outline_en.docx"
        elif direction == "en2zh":
            template_name = "中文纲目模板.docx"
            format_func = format_chinese_outline_docx if is_outline else format_plain_docx
            default_filename = "outline_zh.docx"
        elif direction in ("zh_cn2tw", "zh_tw2cn"):
            # 简繁转换：都使用中文模板和中文格式刷
            template_name = "中文纲目模板.docx"
            format_func = format_chinese_outline_docx if is_outline else format_plain_docx
            default_filename = "outline_zh.docx"
        else:
            return {
                "docx_bytes": None,
                "pdf_bytes": None,
                "filename": None,
                "error": f"无效的方向: {direction}",
            }

        # 检查格式刷函数是否可用
        if format_func is None:
            logger.warning("格式刷函数未导入，无法格式化")
            return {
                "docx_bytes": None,
                "pdf_bytes": None,
                "filename": default_filename,
                "error": "格式刷函数未导入",
            }

        # 复制模板并写入翻译结果
        # 模板文件在 back_mic/backend/（本文件在 backend/t35test/translate/ 下，需往上两层）
        backend_dir = Path(__file__).resolve().parents[2]
        template_path = backend_dir / template_name
        if not template_path.exists():
            logger.error(f"模板文件不存在: {template_path}")
            return {
                "docx_bytes": None,
                "pdf_bytes": None,
                "filename": default_filename,
                "error": f"模板文件不存在: {template_name}",
            }

        try:
            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp_file:
                temp_docx_path = tmp_file.name

            # 复制模板
            shutil.copy2(template_path, temp_docx_path)

            # 打开文档并写入翻译结果
            doc = Document(temp_docx_path)
            
            # 策略：清空所有段落，将翻译结果按行添加为新段落
            # 这样格式刷函数可以正确识别并应用样式
            for para in list(doc.paragraphs):
                p_element = para._element
                p_element.getparent().remove(p_element)
            
            # 将翻译结果按行分割并添加为段落
            lines = translated_text.split("\n")
            for line in lines:
                if line.strip() or len(doc.paragraphs) == 0:  # 保留空行或至少有一个段落
                    doc.add_paragraph(line)

            # 保存
            doc.save(temp_docx_path)

            # 调用格式刷（中文纲目且 zh_cn2tw 时使用繁体引号 『』「」）
            try:
                if format_func is format_chinese_outline_docx:
                    format_func(temp_docx_path, traditional_quotes=(direction == "zh_cn2tw"))
                else:
                    format_func(temp_docx_path)
            except Exception as e:
                logger.error(f"格式刷失败: {e}", exc_info=True)
                # 格式刷失败时仍返回未格式化的文档
                pass

            # 读取为 bytes
            with open(temp_docx_path, "rb") as f:
                docx_bytes = f.read()

            # 生成文件名（基于题目：中文纲目取读经前最后一段，英文纲目取 Scripture reading 前最后一段）
            # 回退逻辑：如果没有读经/Scripture reading，则以第一个大点位置判断题目
            filename = default_filename
            if lines:
                title_line = None
                if direction in ("en2zh", "zh_cn2tw", "zh_tw2cn"):
                    # 中文纲目：优先找"读经："所在行，取它前面一行作为题目
                    scripture_idx = None
                    for idx, line in enumerate(lines):
                        if '读经：' in line or '讀經：' in line:
                            scripture_idx = idx
                            break
                    
                    if scripture_idx is not None:
                        # 找到读经，取读经前一行
                        if scripture_idx > 0:
                            title_line = lines[scripture_idx - 1].strip()
                    else:
                        # 没找到读经，找第一个以"壹"开头的行（第一个大点），取它前面一行
                        for idx, line in enumerate(lines):
                            if line.strip().startswith('壹'):
                                if idx > 0:
                                    title_line = lines[idx - 1].strip()
                                break
                
                elif direction == "zh2en":
                    # 英文纲目：优先找"Scripture reading:"所在行，取它前面一行作为题目
                    scripture_idx = None
                    for idx, line in enumerate(lines):
                        if line.strip().lower().startswith("scripture reading:"):
                            scripture_idx = idx
                            break
                    
                    if scripture_idx is not None:
                        # 找到 Scripture reading，取它前面一行
                        if scripture_idx > 0:
                            title_line = lines[scripture_idx - 1].strip()
                    else:
                        # 没找到 Scripture reading，找第一个罗马数字开头的行（第一个大点，如 "I. "），取它前面一行
                        re_roman = re.compile(r'^([IVXL]+)\.\s')
                        for idx, line in enumerate(lines):
                            if re_roman.match(line.strip()):
                                if idx > 0:
                                    title_line = lines[idx - 1].strip()
                                break
                
                # 如果找到题目行，使用题目；否则回退到第一行
                if title_line:
                    title_text = title_line[:50]
                else:
                    title_text = lines[0].strip()[:50]
                
                if title_text:
                    safe_name = re.sub(r'[\/:*?"<>|]', '_', title_text)
                    if output_format == "pdf":
                        filename = f"{safe_name}.pdf"
                    else:
                        filename = f"{safe_name}.docx"

            # 根据输出格式处理
            if output_format == "pdf":
                # 转换为 PDF
                pdf_bytes = self._convert_docx_to_pdf(temp_docx_path)
                # 清理临时 DOCX 文件
                try:
                    os.unlink(temp_docx_path)
                except Exception:
                    pass
                if pdf_bytes:
                    return {
                        "docx_bytes": None,
                        "pdf_bytes": pdf_bytes,
                        "filename": filename,
                        "error": None,
                    }
                else:
                    # PDF 转换失败，返回 DOCX
                    return {
                        "docx_bytes": docx_bytes,
                        "pdf_bytes": None,
                        "filename": filename.replace(".pdf", ".docx"),
                        "error": "PDF 转换失败，已返回 DOCX 文件",
                    }
            else:
                # 返回 DOCX
                # 清理临时文件
                try:
                    os.unlink(temp_docx_path)
                except Exception:
                    pass
                return {
                    "docx_bytes": docx_bytes,
                    "pdf_bytes": None,
                    "filename": filename,
                    "error": None,
                }

        except Exception as e:
            logger.error(f"格式化失败: {e}", exc_info=True)
            # 清理临时文件
            try:
                if "temp_docx_path" in locals():
                    os.unlink(temp_docx_path)
            except Exception:
                pass
            return {
                "docx_bytes": None,
                "pdf_bytes": None,
                "filename": default_filename,
                "error": f"格式化失败: {str(e)}",
            }


translate_service = TranslateService()
