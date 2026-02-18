"""
AI搜索服务 - 核心业务逻辑
负责Elasticsearch检索、Claude API调用、结果处理
"""
import os
import json
import hashlib
import logging
import time
import uuid
import warnings
from typing import Callable, Dict, List, Optional, Tuple
from datetime import datetime
from io import BytesIO
import re
import threading

# 抑制「Elasticsearch built-in security features are not enabled」的警告（本地开发常见）
try:
    from elasticsearch.exceptions import ElasticsearchWarning
    warnings.filterwarnings("ignore", category=ElasticsearchWarning)
except Exception:
    pass
warnings.filterwarnings("ignore", message=".*security features are not enabled.*")

from es_config import es
import anthropic
from dotenv import load_dotenv
from pathlib import Path

from .monitoring import get_monitoring

# 配置日志（必须在导入格式刷之前，因为导入失败时会使用 logger）
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ai_search")

# 加载环境变量（确保从 backend 目录加载 .env）
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# 导入格式刷函数（从 backend 目录导入）
try:
    import sys
    backend_dir = Path(__file__).resolve().parent.parent
    logger.debug(f"尝试导入格式刷模块，backend_dir: {backend_dir}")
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    from format_chinese_outline import format_chinese_outline_docx
    from format_english_outline import format_english_outline_docx
    logger.info("格式刷模块导入成功")
except ImportError as e:
    format_chinese_outline_docx = None
    format_english_outline_docx = None
    logger.warning(f"格式刷模块未找到，格式化功能将不可用: {e}", exc_info=True)
except Exception as e:
    format_chinese_outline_docx = None
    format_english_outline_docx = None
    logger.error(f"格式刷模块导入时发生错误: {e}", exc_info=True)

# 环境变量配置
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

# Redis 可选：未安装或连接失败时仅禁用缓存
redis_client = None
try:
    import redis
    redis_client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
    redis_client.ping()
    logger.info("Redis 连接成功，缓存已启用")
except Exception as e:
    logger.warning(f"Redis 未启用，将跳过缓存: {e}")

# Claude 客户端（需配置 CLAUDE_API_KEY）
try:
    claude_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY) if CLAUDE_API_KEY else None
    if claude_client:
        logger.info("Claude 客户端初始化成功")
except Exception as e:
    logger.error(f"Claude 客户端初始化失败: {e}")
    claude_client = None

# Gemini 客户端（用于中文纲目→英文纲目翻译，需配置 GEMINI_API_KEY；使用新 SDK google.genai）
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
gemini_client = None
_gemini_system_instruction_en2zh = None
if GEMINI_API_KEY:
    try:
        from google import genai
        from google.genai import types
        from .gemini_translation_instruction import GEMINI_TRANSLATION_SYSTEM_INSTRUCTION
        gemini_client = genai.Client(api_key=GEMINI_API_KEY)
        _gemini_system_instruction = GEMINI_TRANSLATION_SYSTEM_INSTRUCTION
        try:
            from .gemini_translation_instruction_en2zh import GEMINI_TRANSLATION_SYSTEM_INSTRUCTION_EN2ZH
            _gemini_system_instruction_en2zh = GEMINI_TRANSLATION_SYSTEM_INSTRUCTION_EN2ZH
        except Exception:
            _gemini_system_instruction_en2zh = None
        logger.info("Gemini 翻译模型初始化成功")
    except Exception as e:
        logger.error(f"Gemini 翻译模型初始化失败: {e}")
        gemini_client = None
        _gemini_system_instruction = None
        _gemini_system_instruction_en2zh = None
else:
    _gemini_system_instruction = None
    logger.info("Gemini 未配置: GEMINI_API_KEY 未设置（.env 路径: %s）", env_path)

# 并发限制：同时进行中的 Claude / Gemini 请求数，避免人多时触发 API 限流（429）
def _parse_concurrent_limit(env_key: str, default: int) -> int:
    try:
        v = int(os.getenv(env_key, str(default)))
        return max(1, v)  # 至少为 1，避免 Semaphore(0) 导致永久阻塞
    except (ValueError, TypeError):
        return default

CLAUDE_CONCURRENT_LIMIT = _parse_concurrent_limit("CLAUDE_CONCURRENT_LIMIT", 8)
GEMINI_CONCURRENT_LIMIT = _parse_concurrent_limit("GEMINI_CONCURRENT_LIMIT", 5)
CLAUDE_SEMAPHORE = threading.Semaphore(CLAUDE_CONCURRENT_LIMIT)
GEMINI_SEMAPHORE = threading.Semaphore(GEMINI_CONCURRENT_LIMIT)
logger.info("API 并发限制: Claude=%s, Gemini=%s", CLAUDE_CONCURRENT_LIMIT, GEMINI_CONCURRENT_LIMIT)

# 纲目翻译时与原文一起发送的 prompt（【需要翻译的文章】+ 以下说明）
OUTLINE_TRANSLATE_PROMPT_ZH2EN = (
    "请将文章翻译为英文，严格使用System instructions中的专用术语表进行翻译。"
    "格式要求：①中文序号为壹，翻译为英文I.，一翻译为A.，二翻译为B.，1翻译为1.，a翻译为a.，(一)翻译为1)，以此类推；②不要缩进，直接输出。"
)
OUTLINE_TRANSLATE_PROMPT_EN2ZH = (
    "请将文章翻译为中文，严格使用System instructions中的专用术语表进行翻译。"
    "格式要求：①读经格式为缩写，例如：罗一1；②英文序号为I.，翻译为中文壹，A.翻译为一，B.翻译为二，1.翻译为1，a.翻译为a，1)翻译为(一)，以此类推；注意，纲目层级之后只加空格，不加其他符号，如：壹 神爱世人，为世人舍了自己的独生子—约三16：；③不要缩进，直接输出。"
)

# 索引配置：索引名 -> 权重（用于每索引取数及排序加权）
# 按纲目性质（special_needs）选择不同权重
INDEXES_CONFIG_BY_NATURE = {
    "一般性": {
        "map_note": {"weight": 1.0},
        "map_dictionary": {"weight": 1.0},
        "map_7feasts": {"weight": 1.0},
        "map_pano": {"weight": 1.0},
        "cwwl": {"weight": 1.0},
        "cwwn": {"weight": 1.0},
        "life": {"weight": 1.0},
        "bib": {"weight": 1.0},
        "others": {"weight": 1.0},
    },
    "高真理浓度": {
        "map_note": {"weight": 1.0},
        "map_dictionary": {"weight": 1.0},
        "map_7feasts": {"weight": 1.0},
        "map_pano": {"weight": 1.0},
        "cwwl": {"weight": 1.0},  # 94-97 额外 1.5
        "cwwn": {"weight": 1.0},
        "life": {"weight": 1.0},
        "bib": {"weight": 1.0},
        "others": {"weight": 1.0},
    },
    "高生命浓度": {
        "map_note": {"weight": 1.0},
        "map_dictionary": {"weight": 1.0},
        "map_7feasts": {"weight": 1.0},
        "map_pano": {"weight": 1.0},
        "cwwl": {"weight": 1.0},
        "cwwn": {"weight": 1.5},
        "life": {"weight": 1.5},
        "bib": {"weight": 1.0},
        "others": {"weight": 1.0},
    },
    "重实行应用": {
        "map_note": {"weight": 1.0},
        "map_dictionary": {"weight": 1.0},
        "map_7feasts": {"weight": 1.0},
        "map_pano": {"weight": 1.0},
        "cwwl": {"weight": 1.0},  # 85-93 额外 1.5
        "cwwn": {"weight": 1.0},
        "life": {"weight": 1.0},
        "bib": {"weight": 1.0},
        "others": {"weight": 1.0},
    },
}
# 默认使用一般性
INDEXES_CONFIG = INDEXES_CONFIG_BY_NATURE["一般性"]

# 索引中文名，供后台统计页展示权重
INDEX_LABELS = {
    "map_note": "注解",
    "map_dictionary": "词典",
    "map_7feasts": "节期",
    "map_pano": "上河图",
    "cwwl": "李常受文集",
    "cwwn": "倪柝声文集",
    "life": "生命读经",
    "bib": "圣经",
    "others": "其他",
}

# 信息检索使用的索引（仅此 8 个，不含 bib）
INFO_RETRIEVAL_INDEXES = (
    "map_note",
    "map_dictionary",
    "map_7feasts",
    "map_pano",
    "cwwl",
    "cwwn",
    "life",
    "others",
)


def get_index_weights_for_display():
    """供后台统计页展示：各纲目性质对应的 AI 检索索引权重。"""
    out = {}
    for nature, config in INDEXES_CONFIG_BY_NATURE.items():
        out[nature] = {idx: config[idx]["weight"] for idx in config}
    out["_notes"] = {
        "高真理浓度": "cwwl 1994-1997 文集 ×1.5",
        "重实行应用": "cwwl 1985-1993 文集 ×1.5",
    }
    out["_labels"] = INDEX_LABELS
    return out


# cwwl 额外 ×1.5 的年份/范围
_CWWL_EXTRA_WEIGHT_PATTERNS_实行 = (  # 重实行应用：85–93，不含 94–97
    "cwwl_1985", "cwwl_1986", "cwwl_1987", "cwwl_1988", "cwwl_1989",
    "cwwl_1990", "cwwl_1991-92", "cwwl_1993",
)


class AISearchService:
    """AI智能搜索服务"""

    def __init__(self):
        self.es = es
        self.redis = redis_client
        self.claude = claude_client
        self.cache_ttl = 3600  # 缓存1小时

        logger.info("AISearchService初始化完成")

    def search(
        self,
        question: str,
        max_results: int = 30,
        depth: str = "general",
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict:
        """
        AI智能搜索主函数

        Args:
            question: 用户问题
            max_results: 最多返回结果数
            depth: 搜索深度，"general"(一般，50条上下文)或"deep"(深度，200条上下文)

        Returns:
            {
                "answer": "AI生成的答案",
                "sources": [...],  # 引用来源
                "cached": False,   # 是否来自缓存
                "tokens": {...},   # Token使用统计
                "search_time": 123, # 搜索耗时(ms)
                "ai_time": 456     # AI生成耗时(ms)
            }
        """
        start_time = time.time()

        try:
            # 1. 输入验证
            validation_result = self._validate_input(question, max_results)
            if not validation_result["valid"]:
                return {
                    "answer": validation_result["message"],
                    "sources": [],
                    "cached": False,
                    "error": True
                }

            question = question.strip()
            logger.info(f"收到问题: {question}")

            # 2. 检查缓存（缓存key包含问题和深度参数）
            normalized_metadata = self._normalize_metadata(metadata)
            cache_key = self._get_cache_key(question, depth, normalized_metadata)
            cached_result = self._get_from_cache(cache_key)
            if cached_result:
                logger.info("缓存命中")
                cached_result["cached"] = True
                # 监控：记录缓存命中
                try:
                    response_time_ms = (time.time() - start_time) * 1000
                    tokens = cached_result.get("tokens") or {}
                    get_monitoring(self.redis).record_query(
                        question=question[:500],
                        response_time_ms=response_time_ms,
                        cache_hit=True,
                        input_tokens=int(tokens.get("input", 0) or 0),
                        output_tokens=int(tokens.get("output", 0) or 0),
                        cost=tokens.get("cost"),
                        special_needs=normalized_metadata.get("special_needs"),
                    )
                except Exception as _e:
                    logger.debug(f"监控记录失败: {_e}")
                return cached_result

            # 3. 搜索Elasticsearch（根据深度参数决定上下文数量）
            search_start = time.time()
            # 根据深度参数决定上下文数量：一般50条，深度200条
            context_size = 50 if depth == "general" else 200
            fetch_size = context_size  # 直接使用设定的上下文数量
            outline_nature = (normalized_metadata or {}).get("special_needs", "")
            search_results = self._multi_index_search(question, fetch_size, outline_nature)
            search_time = (time.time() - search_start) * 1000

            if not search_results:
                return {
                    "answer": "抱歉，没有找到相关的经文内容。建议：\n1. 尝试使用不同的关键词\n2. 检查是否有拼写错误\n3. 使用更具体的描述",
                    "sources": [],
                    "cached": False,
                    "search_time": search_time
                }

            logger.info(f"ES检索完成: {len(search_results)}条结果, 耗时{search_time:.0f}ms")

            # 4. 调用Claude生成答案
            if not self.claude:
                return {
                    "answer": "AI 服务未配置（请设置 CLAUDE_API_KEY）。",
                    "sources": self._extract_sources(search_results[:50]),
                    "cached": False,
                    "search_time": round(search_time, 0),
                    "error": True
                }
            ai_start = time.time()
            context_items = self._build_context_from_hits(search_results, context_size)
            if not context_items:
                context_items = self._fallback_context_from_hits(search_results, context_size)
            ai_response = self._generate_answer(
                question,
                context_items,
                context_size,
                normalized_metadata
            )
            ai_time = (time.time() - ai_start) * 1000

            logger.info(f"AI生成完成: 耗时{ai_time:.0f}ms")

            # 5. 构造返回结果（引用来源最多 50 条）
            result = {
                "answer": ai_response["answer"],
                "sources": self._extract_sources_from_context(context_items[:50]),
                "cached": False,
                "tokens": ai_response.get("tokens"),
                "claude_payload": ai_response.get("claude_payload"),
                "search_time": round(search_time, 0),
                "ai_time": round(ai_time, 0),
                "total_time": round((time.time() - start_time) * 1000, 0),
                "timestamp": datetime.now().isoformat()
            }

            # 6. 写入缓存
            self._save_to_cache(cache_key, result)

            # 监控：记录成功查询（未命中缓存）
            try:
                tokens = result.get("tokens") or {}
                input_tok = int(tokens.get("input", 0) or 0)
                output_tok = int(tokens.get("output", 0) or 0)
                if not input_tok and not output_tok:
                    answer_text = result.get("answer", "") or ""
                    input_tok = int((len(question) + len(answer_text)) * 1.3)
                    output_tok = int(len(answer_text) * 1.3)
                get_monitoring(self.redis).record_query(
                    question=question[:500],
                    response_time_ms=result["total_time"],
                    cache_hit=False,
                    input_tokens=input_tok,
                    output_tokens=output_tok,
                    cost=tokens.get("cost"),
                    special_needs=normalized_metadata.get("special_needs"),
                )
            except Exception as _e:
                logger.debug(f"监控记录失败: {_e}")

            logger.info(f"搜索完成: 总耗时{result['total_time']}ms")
            return result

        except Exception as e:
            logger.error(f"搜索失败: {e}", exc_info=True)
            # 监控：记录错误
            try:
                get_monitoring(self.redis).record_error(
                    str(e),
                    extra={"question": (question[:200] if question else "")},
                )
            except Exception as _e:
                logger.debug(f"监控记录失败: {_e}")
            return {
                "answer": f"搜索出错: {str(e)}\n请稍后重试或联系管理员。",
                "sources": [],
                "cached": False,
                "error": True
            }

    def search_only(
        self,
        question: str,
        depth: str = "general",
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict:
        """
        方案A - 第一步：仅执行ES搜索，返回引用来源，将完整结果存入Redis供generate使用。
        若缓存命中，直接返回完整结果（含 answer），前端无需再调 generate。

        Returns:
            {"sources": [...], "search_id": str, "search_time": float} 或
            {"sources": [...], "answer": str, "tokens": {...}, "cached": True} 缓存命中时
        """
        try:
            if not self.redis:
                return {"error": True, "message": "Redis 未启用，无法使用分步搜索"}
            if not question or len(question.strip()) < 2:
                return {"error": True, "message": "问题太短，请输入至少2个字符"}
            if len(question) > 500:
                return {"error": True, "message": "问题过长（最多500字符）"}

            question = question.strip()
            depth = depth or "general"

            # 检查缓存（与一步接口共用）
            normalized_metadata = self._normalize_metadata(metadata)
            cache_key = self._get_cache_key(question, depth, normalized_metadata)
            cached = self._get_from_cache(cache_key)
            if cached:
                logger.info("search_only 缓存命中")
                cached["cached"] = True
                try:
                    get_monitoring(self.redis).record_query(
                        question=question[:500],
                        response_time_ms=50,
                        cache_hit=True,
                        input_tokens=int(cached.get("tokens", {}).get("input", 0) or 0),
                        output_tokens=int(cached.get("tokens", {}).get("output", 0) or 0),
                        cost=cached.get("tokens", {}).get("cost"),
                        special_needs=normalized_metadata.get("special_needs"),
                    )
                except Exception as _e:
                    logger.debug(f"监控记录失败: {_e}")
                return cached

            context_size = 50 if depth == "general" else 200
            search_start = time.time()
            outline_nature = (normalized_metadata or {}).get("special_needs", "")
            search_results = self._multi_index_search(question, context_size, outline_nature)
            search_time = (time.time() - search_start) * 1000

            if not search_results:
                return {
                    "sources": [],
                    "search_id": None,
                    "search_time": round(search_time, 0),
                    "error": True,
                    "message": "没有找到相关的经文内容"
                }

            search_id = str(uuid.uuid4())
            context_key = f"ai_search:context:{search_id}"
            context_data = {
                "question": question,
                "depth": depth,
                "search_results": search_results,
                "context_size": context_size,
                "metadata": normalized_metadata,
            }
            self.redis.setex(
                context_key,
                300,  # 5分钟过期
                json.dumps(context_data, ensure_ascii=False, default=str)
            )

            sources = self._extract_sources(search_results[:50])
            logger.info(f"search_only 完成: search_id={search_id}, {len(sources)}条来源, 耗时{search_time:.0f}ms")
            return {
                "sources": sources,
                "search_id": search_id,
                "search_time": round(search_time, 0),
            }
        except Exception as e:
            logger.error(f"search_only 失败: {e}", exc_info=True)
            return {"error": True, "message": str(e)}

    def generate_only(
        self,
        question: str,
        search_id: str,
        max_results: int = 30,
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict:
        """
        方案A - 第二步：从Redis获取上下文，调用Claude生成答案。
        若缓存命中，直接返回，不调用 Claude。

        Returns:
            与 search() 相同的返回格式
        """
        start_time = time.time()
        try:
            if not self.redis:
                return {"answer": "Redis 未启用", "sources": [], "cached": False, "error": True}
            if not self.claude:
                return {"answer": "AI 服务未配置", "sources": [], "cached": False, "error": True}

            context_key = f"ai_search:context:{search_id}"
            raw = self.redis.get(context_key)
            if not raw:
                return {
                    "answer": "搜索会话已过期，请重新提问",
                    "sources": [],
                    "cached": False,
                    "error": True
                }

            ctx = json.loads(raw)
            search_results = ctx.get("search_results", [])
            stored_question = ctx.get("question", "")
            stored_depth = ctx.get("depth", "general")
            context_size = ctx.get("context_size", 200)

            # 检查缓存
            ctx_metadata = ctx.get("metadata") or {}
            normalized_metadata = self._normalize_metadata(metadata or ctx_metadata)
            cache_key = self._get_cache_key(
                question or stored_question,
                stored_depth,
                normalized_metadata
            )
            cached = self._get_from_cache(cache_key)
            if cached:
                logger.info("generate_only 缓存命中")
                cached["cached"] = True
                try:
                    self.redis.delete(context_key)
                except Exception:
                    pass
                try:
                    get_monitoring(self.redis).record_query(
                        question=(question or stored_question)[:500],
                        response_time_ms=int((time.time() - start_time) * 1000),
                        cache_hit=True,
                        input_tokens=int(cached.get("tokens", {}).get("input", 0) or 0),
                        output_tokens=int(cached.get("tokens", {}).get("output", 0) or 0),
                        cost=cached.get("tokens", {}).get("cost"),
                        special_needs=normalized_metadata.get("special_needs"),
                    )
                except Exception as _e:
                    logger.debug(f"监控记录失败: {_e}")
                return cached

            if not search_results:
                return {
                    "answer": "未找到相关上下文",
                    "sources": [],
                    "cached": False,
                    "error": True
                }

            ai_start = time.time()
            context_items = self._build_context_from_hits(search_results, context_size)
            if not context_items:
                context_items = self._fallback_context_from_hits(search_results, context_size)
            ai_response = self._generate_answer(
                question or stored_question,
                context_items,
                context_size,
                normalized_metadata
            )
            ai_time = (time.time() - ai_start) * 1000

            sources = self._extract_sources_from_context(context_items[:max_results])
            total_time = (time.time() - start_time) * 1000

            result = {
                "answer": ai_response["answer"],
                "sources": sources,
                "cached": False,
                "tokens": ai_response.get("tokens"),
                "claude_payload": ai_response.get("claude_payload"),
                "search_time": 0,
                "ai_time": round(ai_time, 0),
                "total_time": round(total_time, 0),
                "timestamp": datetime.now().isoformat()
            }

            # 写入缓存（与一步接口共用 key）
            self._save_to_cache(cache_key, result)

            try:
                self.redis.delete(context_key)
            except Exception:
                pass

            try:
                tokens = result.get("tokens") or {}
                get_monitoring(self.redis).record_query(
                    question=(question or stored_question)[:500],
                    response_time_ms=result["total_time"],
                    cache_hit=False,
                    input_tokens=int(tokens.get("input", 0) or 0),
                    output_tokens=int(tokens.get("output", 0) or 0),
                    cost=tokens.get("cost"),
                    special_needs=normalized_metadata.get("special_needs"),
                )
            except Exception as _e:
                logger.debug(f"监控记录失败: {_e}")

            return result
        except Exception as e:
            logger.error(f"generate_only 失败: {e}", exc_info=True)
            return {"answer": f"生成失败: {str(e)}", "sources": [], "cached": False, "error": True}

    def _validate_input(self, question: str, max_results: int) -> Dict:
        """
        输入验证

        Returns:
            {"valid": bool, "message": str}
        """
        if not question or len(question.strip()) < 2:
            return {
                "valid": False,
                "message": "问题太短，请输入至少2个字符"
            }

        if len(question) > 500:
            return {
                "valid": False,
                "message": "问题过长（最多500字符），请简化您的问题"
            }

        if max_results < 1 or max_results > 50:
            return {
                "valid": False,
                "message": "max_results必须在1-50之间"
            }

        return {"valid": True, "message": ""}

    def _multi_index_search(
        self, query: str, size: int, outline_nature: str = ""
    ) -> List[Dict]:
        """
        多索引搜索并按权重排序

        Args:
            query: 搜索关键词
            size: 返回结果数量
            outline_nature: 纲目性质（高真理浓度/高生命浓度/重实行应用），影响各索引权重

        Returns:
            加权排序后的搜索结果列表
        """
        indexes_config = INDEXES_CONFIG_BY_NATURE.get(
            outline_nature, INDEXES_CONFIG_BY_NATURE["一般性"]
        )
        all_results = []

        for index_name, config in indexes_config.items():
            weight = config["weight"]
            try:
                if index_name in self._MAP_LIKE_INDICES:
                    # map_note/map_7feasts/map_dictionary/map_pano：检索 msg 中 text/type + 外层 text
                    # 若命中来自外层 text（无 inner_hits），则发送全篇内容
                    search_body = {
                        "query": {
                            "bool": {
                                "should": [
                                    {
                                        "nested": {
                                            "path": "msg",
                                            "query": {
                                                "bool": {
                                                    "should": [
                                                        {"match_phrase": {"msg.text": {"query": query, "boost": 2.5}}},
                                                        {"match": {"msg.text": {"query": query, "fuzziness": "AUTO", "boost": 2.0}}},
                                                        {"match": {"msg.type": {"query": query, "boost": 1.5}}}
                                                    ],
                                                    "minimum_should_match": 1,
                                                    "filter": [
                                                        {"terms": {"msg.type": list(self._MAP_NOTE_MSG_TYPES)}}
                                                    ]
                                                }
                                            },
                                            "inner_hits": {
                                                "name": "matched_msg",
                                                "size": 50
                                            }
                                        }
                                    },
                                    {
                                        "bool": {
                                            "should": [
                                                {"match_phrase": {"text": {"query": query, "boost": 2.5}}},
                                                {"match": {"text": {"query": query, "fuzziness": "AUTO", "boost": 2.0}}}
                                            ],
                                            "minimum_should_match": 1
                                        }
                                    }
                                ],
                                "minimum_should_match": 1
                            }
                        },
                        "size": int(size * weight),
                        "_source": ["id", "text", "msg", "source", "sn", "bookname", "title", "bookname2"]
                    }
                else:
                    # 其他索引：查顶层 text
                    search_body = {
                        "query": {
                            "bool": {
                                "should": [
                                    {"match_phrase": {"text": {"query": query, "boost": 2.5}}},
                                    {"match": {"text": {"query": query, "fuzziness": "AUTO", "boost": 2.0}}}
                                ],
                                "minimum_should_match": 1
                            }
                        },
                        "size": int(size * weight),
                        "_source": ["id", "type", "book", "chapter", "verse", "text", "title"]
                    }

                # 执行搜索（使用项目统一 es，忽略不可用索引）
                response = self.es.search(
                    index=index_name,
                    body=search_body,
                    request_timeout=10,
                    ignore_unavailable=True
                )

                hits = response['hits']['hits']

                # 为每条结果添加加权分数
                for hit in hits:
                    score = hit['_score'] * weight
                    # cwwl 特殊年份再加权 1.5
                    if index_name == "cwwl":
                        doc_id = (hit.get("_source") or {}).get("id") or hit.get("_id") or ""
                        if outline_nature == "重实行应用":
                            # 重实行应用：1985-1993 年份文集加权（94-97 不加权）
                            if any(p in doc_id for p in _CWWL_EXTRA_WEIGHT_PATTERNS_实行):
                                score *= 1.5
                        elif outline_nature == "高真理浓度":
                            # 高真理浓度：仅 1994-1997
                            if "cwwl_1994-1997" in doc_id:
                                score *= 1.5
                    hit['_weighted_score'] = score
                    hit['_index_name'] = index_name
                    all_results.append(hit)

                logger.debug(f"索引{index_name}: {len(hits)}条结果")

            except Exception as e:
                logger.warning(f"搜索索引{index_name}失败: {e}")
                continue

        # 按加权分数排序
        all_results.sort(key=lambda x: x['_weighted_score'], reverse=True)

        # 检索统计：总检索条数、使用条数、浪费率，打日志并写入监控供后台展示
        total = len(all_results)
        used = min(size, total)
        waste_rate = round((total - used) / total * 100, 1) if total else 0.0
        question_preview = (query[:30] + "…") if len(query) > 30 else query
        logger.info(f"检索统计 - 问题:{question_preview} | 总检索:{total}条 | 使用:{used}条 | 浪费率:{waste_rate}%")
        try:
            get_monitoring(self.redis).record_retrieval_stats(question_preview, total, used, waste_rate)
        except Exception as _e:
            logger.debug(f"记录检索统计失败: {_e}")

        return all_results[:size]

    # 按 type 分类：取整节 / 只取该段 / 不取
    _HEADING_TYPES = frozenset({"heading", "heading_1", "heading_2", "heading_3", "heading_4"})
    _SINGLE_PARAGRAPH_TYPES = frozenset({"text", "ot1", "ot2", "ot3", "ot4"})
    # map_note / map_7feasts / map_dictionary：nested msg 结构，参与检索的纲目层级
    _MAP_NOTE_MSG_TYPES = frozenset({"ot1", "ot2", "ot3", "ot4"})
    _MAP_LIKE_INDICES = frozenset({"map_note", "map_7feasts", "map_dictionary", "map_pano"})

    def _get_map_note_section_range(
        self, msg: List[Dict], start_idx: int
    ) -> tuple:
        """
        根据命中的 msg 项索引，返回该小节在 msg 中的 (start, end) 范围。
        ot1: 到下一个 ot1 之前；ot2: 到下一个 ot2/ot1 或非 ot 之前；ot3/ot4 同理。
        """
        if start_idx >= len(msg):
            return (start_idx, start_idx)
        item_type = msg[start_idx].get("type", "")
        if item_type not in self._MAP_NOTE_MSG_TYPES:
            return (start_idx, start_idx + 1)
        if item_type == "ot1":
            stop_at = {"ot1"}
        elif item_type == "ot2":
            stop_at = {"ot1", "ot2"}
        elif item_type == "ot3":
            stop_at = {"ot1", "ot2", "ot3"}
        else:  # ot4
            stop_at = {"ot1", "ot2", "ot3", "ot4"}
        end_idx = start_idx + 1
        while end_idx < len(msg):
            t = msg[end_idx].get("type", "")
            if t in stop_at or t not in self._MAP_NOTE_MSG_TYPES:
                break
            end_idx += 1
        return (start_idx, end_idx)

    def _get_map_note_full_content(self, source: Dict) -> str:
        """
        获取 map 类文档的全篇内容：优先用外层 text，否则拼接所有 ot1~ot4。
        当命中来自外层 text 相关度高时，用于发送全篇给 Claude。
        """
        outer_text = (source.get("text") or "").strip()
        if outer_text:
            return outer_text
        msg_list = source.get("msg") or []
        parts = []
        for m in msg_list:
            if m.get("type") in self._MAP_NOTE_MSG_TYPES and m.get("text"):
                parts.append(m["text"])
        return "\n".join(parts)

    def _extract_map_note_sections_from_inner_hits(
        self, source: Dict, hit: Dict
    ) -> str:
        """
        从 inner_hits 获取命中的 msg 索引，按小节提取并拼接，多个 ot1 小节分别提取后拼接。
        若无 inner_hits（命中来自外层 text）：返回全篇内容，供 Claude 使用。
        """
        msg_list = source.get("msg") or []
        if not msg_list:
            return source.get("text", "")

        inner = hit.get("inner_hits", {}).get("matched_msg", {})
        inner_hits_list = inner.get("hits", {}).get("hits", [])

        if not inner_hits_list:
            # 无 inner_hits：命中来自外层 text，相关度够高，发送全篇内容
            return self._get_map_note_full_content(source)

        matched_indices = set()
        for ih in inner_hits_list:
            nested = ih.get("_nested", {})
            offset = nested.get("offset")
            if isinstance(offset, int) and 0 <= offset < len(msg_list):
                matched_indices.add(offset)

        if not matched_indices:
            parts = []
            for m in msg_list:
                if m.get("type") in self._MAP_NOTE_MSG_TYPES and m.get("text"):
                    parts.append(m["text"])
            return "\n".join(parts)

        ranges = []
        for idx in matched_indices:
            s, e = self._get_map_note_section_range(msg_list, idx)
            ranges.append((s, e))

        ranges.sort(key=lambda x: x[0])
        merged = []
        for s, e in ranges:
            if merged and s <= merged[-1][1]:
                merged[-1] = (merged[-1][0], max(merged[-1][1], e))
            else:
                merged.append((s, e))

        parts = []
        for s, e in merged:
            for i in range(s, e):
                m = msg_list[i]
                if m.get("type") in self._MAP_NOTE_MSG_TYPES and m.get("text"):
                    parts.append(m["text"])

        return "\n".join(parts) if parts else source.get("text", "")

    def _parse_doc_id(self, doc_id: str) -> tuple:
        """解析文档 id，提取 message 前缀和段号。如 others_1_1-4 -> (others_1_1-, 4)"""
        if not doc_id or "-" not in doc_id:
            return ("", 0)
        last_dash = doc_id.rfind("-")
        prefix = doc_id[: last_dash + 1]
        try:
            seg = int(doc_id[last_dash + 1 :])
        except ValueError:
            seg = 0
        return (prefix, seg)

    def _fetch_message_docs(self, index_name: str, message_prefix: str) -> List[Dict]:
        """从 ES 获取同一篇（message）内的所有文档，按段号排序"""
        try:
            resp = self.es.search(
                index=index_name,
                body={
                    "query": {"prefix": {"id": message_prefix}},
                    "size": 500,
                    "_source": ["id", "type", "text", "title", "book", "chapter", "verse"],
                },
                request_timeout=10,
            )
            hits = resp.get("hits", {}).get("hits", [])
            docs = []
            for h in hits:
                src = h.get("_source", {})
                pid, seg = self._parse_doc_id(src.get("id", ""))
                docs.append((seg, src))
            docs.sort(key=lambda x: x[0])
            return [d[1] for d in docs]
        except Exception as e:
            logger.warning(f"获取 message 文档失败: {e}")
            return []

    def _get_section_from_heading(
        self, docs: List[Dict], heading_idx: int
    ) -> tuple:
        """
        从 heading 起，取到下一个非 text 的文档为止。
        返回 (拼接后的内容, 本 section 内所有 doc 的 id 列表)
        """
        if heading_idx >= len(docs):
            return ("", [])
        section_ids = []
        parts = []
        for i in range(heading_idx, len(docs)):
            doc = docs[i]
            doc_id = doc.get("id", "")
            dtype = doc.get("type", "")
            text = doc.get("text", "")
            if not text:
                continue
            if i == heading_idx:
                section_ids.append(doc_id)
                parts.append(text)
                continue
            if dtype == "text":
                section_ids.append(doc_id)
                parts.append(text)
            else:
                break
        return ("\n".join(parts), section_ids)

    def _build_context_from_hits(
        self, search_results: List[Dict], context_size: int
    ) -> List[Dict]:
        """
        根据 type 规则构建上下文：heading 取整节，text/ot1-4 只取该段，其他不取。
        去重：已被整节覆盖的段落不再单独加入。
        返回 [{"reference": str, "content": str, "source_type": str, "score": float}, ...]
        """
        included_ids = set()
        context_items = []
        seen_sections = set()
        # 深度模式：限制单条内容长度，防止总 tokens 超限（Claude API 1M 限制）
        # 实测发现中文 token 转换率约 1:1.5（1字≈1.5 tokens）
        # 深度模式(200条)：每条1000字 ≈ 1500 tokens，总计约300K tokens（高价区，可接受）
        # 一般模式(50条)：每条2500字 ≈ 3750 tokens，总计约187K tokens（标准区）
        max_content_length = 1000 if context_size >= 150 else 2500

        for hit in search_results:
            if len(context_items) >= context_size:
                break
            source = hit.get("_source", {})
            doc_id = source.get("id") or hit.get("_id", "")
            dtype = source.get("type", "")
            index_name = hit.get("_index_name", hit.get("_index", ""))
            score = hit.get("_weighted_score", hit.get("_score", 0))

            if doc_id in included_ids:
                continue

            # map_note / map_7feasts / map_dictionary：按 inner_hits 定位命中的 msg 项，提取对应小节
            if index_name in self._MAP_LIKE_INDICES:
                content = self._extract_map_note_sections_from_inner_hits(source, hit)
                if not content:
                    continue
                # 限制单条长度
                if len(content) > max_content_length:
                    content = content[:max_content_length] + "..."
                ref = self._get_map_note_reference_from_hit(source, hit, index_name)
                context_items.append({
                    "reference": ref,
                    "content": content,
                    "source_type": self._get_source_type(index_name),
                    "score": score,
                })
                included_ids.add(doc_id)
                continue

            if dtype in self._HEADING_TYPES:
                prefix, seg = self._parse_doc_id(doc_id)
                if not prefix:
                    continue
                section_key = (index_name, prefix)
                if section_key in seen_sections:
                    continue
                docs = self._fetch_message_docs(index_name, prefix)
                if not docs:
                    continue
                heading_idx = next(
                    (i for i, d in enumerate(docs) if d.get("id") == doc_id),
                    -1,
                )
                if heading_idx < 0:
                    continue
                content, section_ids = self._get_section_from_heading(
                    docs, heading_idx
                )
                if not content:
                    continue
                # 限制单条长度
                if len(content) > max_content_length:
                    content = content[:max_content_length] + "..."
                seen_sections.add(section_key)
                for sid in section_ids:
                    included_ids.add(sid)
                ref = self._format_reference(docs[0] if docs else source)
                context_items.append({
                    "reference": ref,
                    "content": content,
                    "source_type": self._get_source_type(index_name),
                    "score": score,
                })
                continue

            if dtype in self._SINGLE_PARAGRAPH_TYPES:
                text = source.get("text", "")
                if not text:
                    continue
                # 限制单条长度
                if len(text) > max_content_length:
                    text = text[:max_content_length] + "..."
                ref = self._format_reference(source)
                context_items.append({
                    "reference": ref,
                    "content": text,
                    "source_type": self._get_source_type(index_name),
                    "score": score,
                })
                included_ids.add(doc_id)

        return context_items

    def _fallback_context_from_hits(
        self, search_results: List[Dict], context_size: int
    ) -> List[Dict]:
        """当 _build_context_from_hits 无结果时回退：按原逻辑取 text 构建上下文（如 bib/hymn 等）"""
        items = []
        # 深度模式限制单条长度，防止总 tokens 超限（实测中文约 1字≈1.5 tokens）
        max_content_length = 1000 if context_size >= 150 else 2500
        
        for hit in search_results[:context_size]:
            source = hit.get("_source", {})
            index_name = hit.get("_index_name", hit.get("_index", ""))
            if index_name in self._MAP_LIKE_INDICES:
                # map 类：用 inner_hits 按小节提取；若无则回退为全部 ot1~ot4
                text = self._extract_map_note_sections_from_inner_hits(source, hit)
            else:
                text = source.get("text", "")
            if not text:
                continue
            # 限制单条长度
            if len(text) > max_content_length:
                text = text[:max_content_length] + "..."
            ref = self._get_map_note_reference_from_hit(source, hit, index_name) if index_name in self._MAP_LIKE_INDICES else self._format_reference(source)
            items.append({
                "reference": ref,
                "content": text,
                "source_type": self._get_source_type(
                    hit.get("_index_name", hit.get("_index", ""))
                ),
                "score": hit.get("_weighted_score", hit.get("_score", 0)),
            })
        return items

    def _extract_sources_from_context(
        self, context_items: List[Dict]
    ) -> List[Dict]:
        """从 context_items 提取引用来源（供前端展示）"""
        sources = []
        for item in context_items:
            content = item.get("content", "")
            preview = content[:150] + "..." if len(content) > 150 else content
            sources.append({
                "reference": item.get("reference", ""),
                "content": preview,
                "score": round(item.get("score", 0), 2),
                "type": item.get("source_type", ""),
            })
        return sources

    def _generate_answer(
        self,
        question: str,
        context_items: List[Dict],
        context_size: int = 200,
        metadata: Optional[Dict[str, str]] = None,
    ) -> Dict:
        """
        调用Claude生成答案

        Args:
            question: 用户问题
            context_items: 上下文项列表 [{"reference", "content", "source_type"}, ...]
            context_size: 最多使用的条数

        Returns:
            {"answer": str, "tokens": dict}
        """
        context_parts = []
        for i, item in enumerate(context_items[:context_size], 1):
            ref = item.get("reference", "")
            content = item.get("content", "")
            stype = item.get("source_type", "")
            if not content:
                continue
            context_parts.append(f"{i}. {stype} {ref}\n{content}\n")

        context = "\n".join(context_parts)

        # 构建prompt
        system_prompt = """你是一个资深的圣经研究学者，更是一位专业的倪柝声、李常受神学的研究者，请基于提供的内容，生成一篇纲目。

【最高优先级原则】
逐字引用（verbatim quotes）是最核心的要求，优先级高于所有其他要求。当任何要求与"逐字引用"冲突时，优先保证逐字引用。特别注意：大纲（壹、贰、叁）最容易被总结改写，必须严格遵守逐字引用原则。

要求：
1. 你的回答必须以原文的 verbatim quotes（逐字引用）为核心内容，所有实质性观点、论述和纲目都必须直接从原文提取，不可改写、总结、概括或重述。verbatim quote（逐字引用）比例越高越好。
    【可以做的】：
    - 从原文中选择哪些句子
    - 调整句子的排列顺序
    - 添加极简的连接词（如"而"、"并"）

    【绝对不可以做的】：
    - 改变原文的任何用词
    - 用自己的话"换一种说法"
    - 合并多个句子的意思成一句话
    - 提炼、归纳、概括原文的意思
    - 添加原文中没有的解释

    【检查方法】：
    生成纲目后，每一条纲目都应该能在原文中找到完全对应的句子。

2. 可以使用最简短的连接语来组织结构（如"而"、"并且"、"所以"等），但尽量减少使用，除非到了不加关联词无法表述的情况，才加关联词，且不可改写原文的实质内容。

3. 纲目层级序号规则：
    - 第一级使用大写中文数字：壹、贰、叁（不可用"参"）、肆、伍、陆、柒、捌、玖、拾、拾壹、拾贰、拾叁、拾肆、拾伍、拾陆、拾柒、拾捌、拾玖、贰壹、贰贰、贰叁……贰玖、叁壹、叁贰……
    （说明：21写作"贰壹"而非"贰拾壹"或"二十一"）
    - 第二级使用小写中文数字：一、二、三、四、五、六、七、八、九、十、十一、十二、十三、十四、十五、十六、十七、十八、十九、二一、二二、二三……二九、三一、三二……
    （说明：21写作"二一"而非"二十一"）
    - 第三级使用阿拉伯数字：1、2、3、4……
    - 第四级使用小写英文字母：a、b、c、d……
    
    【缩进与换行规则】：
    - 第一级（壹、贰、叁）：顶格，无缩进
    - 第二级（一、二、三）：一个 Tab 键缩进
    - 第三级（1、2、3）：两个 Tab 键缩进
    - 第四级（a、b、c）：三个 Tab 键缩进
    - 序号与纲目内容之间用一个 Tab 键连接
    - 每条纲目之间不要空行，紧密排列
    - 每条纲目结束后直接换行，不要额外的空行
    
    格式示例：
    壹	第一条大纲内容—创一1：
    	一	第一条中纲内容—创一2：
    		1	第一条小纲内容—创一3：
    			a	第四级纲目内容—创一4。
    			b	第四级纲目内容—创一5。
    		2	第二条小纲内容—创一6。
    	二	第二条中纲内容—创一7。
    贰	第二条大纲内容—创一8。

4. 每个纲目必须是一个完整的阐述，不可用短句。每一个大纲和中纲不可太短，要有大约一行的长度。
    
    【特别强调：大纲的逐字引用原则】
    大纲（壹、贰、叁等）最容易被改写总结，必须特别注意：
    - 大纲必须直接从原文中提取完整句子，不可为了"概括下级纲目"而自己总结
    - 大纲应该选择原文中最核心、最能统领该主题的一句话，而不是自己归纳
    - 宁可选用原文的长句作为大纲，也不要自己编写简短的总结句
    - 如果原文中没有合适的统领性句子，可以选择该部分开头或结尾的关键句

    示例：
    ❌ 错误：壹	神将生命分赐给人的过程—创一1
    ✅ 正确：壹	神的生命是永远的生命，就是神自己分赐到我们里面，作我们的生命和生命的供应—约一4，十10

5. 每个纲目如果有下一级纲目，下一级纲目至少需要 2 个。

6. 纲目的标点符号规则：
    - 每个纲目的内容之后用—连接圣经经节出处
    - 若该纲目有下一级纲目，则在经节出处之后加冒号
    - 若该纲目无下一级纲目，则在经节出处之后加句号
    
    格式示例：
    有下级：壹	纲目内容—创一1：
    无下级：一	纲目内容—创一1。

7. 圣经经节格式规则：
    - 每条纲目后面只能加圣经经节出处，不可加文集、生命读经等参考资料出处
    - 经节格式：创世记一章一节为"创一1"，其他书卷依次类推
    - 同一书卷多个出处应合并，如"启三1，四7"，同章不同节用顿号隔开
    - 所有纲目层级（壹、一、1、a）都需要加经节出处
    
    【重要】纲目后的出处规则：
    ✅ 正确：壹	召会是基督的身体—弗一22～23：
    ❌ 错误：壹	召会是基督的身体—李常受文集一九五〇至一九五一年第一册，在于灵不在于字句，第七章：
    ❌ 错误：一	基督的扩大就是召会—弗一23，李常受文集第一册：
    
    说明：文集、生命读经等出处只在最后"参考与参读资料"部分列出，不加在纲目后面。

8. 在整个纲目最前面写出"读经：........"，从目标文章中提取 8～10 个重要的经节出处，按圣经书卷顺序排列，同一书卷内按章节顺序。同一书卷的经节用顿号隔开，不同书卷用逗号隔开。
   示例：读经：创一1，26～28，二7，约一1，14，罗八2，29，启二一2

9. 纲目中不可使用双引号。所有单引号必须用中文状态下的单引号，不可用英文状态下的单引号。

10. 纲目句中若有句号，需将句号改成分号。

11. 两个数字之间需要用全角的～连接。

12. 输出的纲目中不可有重复内容，不可出现两条一样的纲目。

13. 回答需综合文章的所有相关要点，结构清晰，逻辑合理，不是简单按顺序罗列。
    
    【内容选择原则】
    虽然必须逐字引用，但在选择引用哪些句子时，应优先选择：
    - 具有神学深度和启示性的句子
    - 表达核心真理和关键经历的句子
    - 带有属灵亮光和生命供应的句子
    - 能够摸着读者灵和带来生命感觉的句子

    示例对比：
    ❌ 枯燥：壹	神有生命—约一4
    ✅ 精彩：壹	神的生命是永远的生命，就是神自己分赐到我们里面，作我们的生命和生命的供应，使我们在生命和性情上与神一样—约一4，十10，彼后一4

    原则：在保持逐字引用的前提下，要选择原文中最有"分量"、最能供应生命的句子。

14. 如果所提供的内容不足以回答问题，请诚实说明，而不是编造答案。

15. 用纯文本作答，不使用 Markdown 格式（不用 #、*、** 等符号）。

16. 请不要写 python 代码来生成纲目，不要生成 txt 或 docx，而是直接生成纲目。

17. 在回答末尾，另起段落列出"参考与参读资料"，5～10条，每条一行。若同一书有多篇，必须分开列出，不可合并。参考资料格式规则：
    参考与参读资料：
    1. 李常受文集一九九四至一九九七年第二册，神人，第四章
    2. 启示录生命读经，第五十九篇
    3. 恢复本圣经，创一1，注1
    4. 主恢复真理的词典，爱，3a　职事信息的鸟瞰
    5. 2025年秋季长老训练，第六篇
    6. ......
    
18. 纲目的逻辑顺序应符合原文的神学论述逻辑，而非仅按原文出现的先后顺序排列。

19. 纲目中涉及主观经历的条目数量占比约15%的篇幅；涉及实行应用的条目数量占比约15%的篇幅。

20. 纲目篇幅严格限制为A4纸一页半(必须在35~38行之间)

【完整格式示例】

    读经：创一1，26～28，二7，约一1，14，罗八2，29

    壹	神的生命是永远的生命，就是神自己分赐到我们里面，作我们的生命和生命的供应—约一4，十10：
        一	生命就是三一神分赐到我们里面，使我们与神有生机的联结—约一4：
            1	神的生命使我们在生命和性情上与神一样，却无分于神格—彼后一4。
            2	这生命是非受造的，是永远、神圣、属灵的生命—约壹五11～12。
        二	我们需要天天经历基督作生命树，使我们在生命里长大—启二7：
            1	生命树表征三一神在基督里作我们的生命和生命的供应—启二二2，14。
            2	我们借着吃基督作生命树，就能在神圣的生命里长大成熟—来五12～14。
    贰	基督作为赐生命的灵，住在我们的灵里，作我们的生命—罗八2，10：
        一	那灵就是基督自己在复活里成为赐生命的灵—林前十五45下。
        二	我们需要操练灵，接触这位是灵的基督—提后四22，罗八4。

    参考与参读资料：
    1. 约翰福音生命读经，第一篇
    2. 约翰福音生命读经，第二篇
    3. 

【最后检查清单】
    生成纲目后，请确认：
    ✓ 每条纲目都能在原文中找到对应的原句
    ✓ 大纲（壹、贰、叁）没有被总结改写
    ✓ 所有经节格式正确（如"创一1"）
    ✓ 序号格式正确（壹贰叁、一二三、123、abc）
    ✓ 缩进正确（第一级顶格，第二级1个Tab，第三级2个Tab，第四级3个Tab）
    ✓ 标点符号正确（有下级用冒号，无下级用句号）
    ✓ 纲目之间无空行，紧密排列 
"""

        metadata_lines = []
        if metadata:
            label_map = {
                "outline_topic": "纲目主题",
                "burden_description": "负担说明",
                "special_needs": "纲目性质",
                "audience": "面对对象",
            }
            for key, label in label_map.items():
                value = metadata.get(key)
                if value:
                    metadata_lines.append(f"{label}：{value}")
        metadata_text = "\n".join(metadata_lines)
        metadata_block = f"\n{metadata_text}" if metadata_text else ""

        user_prompt = f"""{metadata_block}

参考内容：
{context}

请基于以上内容，生成一篇纲目："""

        claude_payload = {
            "system_prompt": system_prompt,
            "user_prompt": user_prompt,
        }

        # 调用Claude API（并发限制：超出时排队等待，减少 429）
        estimated_input_tokens = int((len(system_prompt) + len(user_prompt)) * 0.7)
        context_count = len(context_items[:context_size])
        logger.info(f"准备调用 Claude - 上下文数: {context_count}条, 预估输入tokens: {estimated_input_tokens}")

        with CLAUDE_SEMAPHORE:
            try:
                # 硬性上限 1M tokens（超过会失败），保守提示 900K
                if estimated_input_tokens > 900000:
                    logger.warning(f"⚠️ 输入可能超过1M上限！预估: {estimated_input_tokens} tokens")
                elif estimated_input_tokens > 200000:
                    logger.info(f"ℹ️ 输入超过200K，将使用高价区定价: ${estimated_input_tokens / 1000000 * 6:.3f}")

                message = self.claude.messages.create(
                    model="claude-sonnet-4-20250514",
                    max_tokens=4000,
                    temperature=0.3,  # 降低温度提高准确性
                    system=system_prompt,
                    messages=[
                        {"role": "user", "content": user_prompt}
                    ]
                )

                if not message.content or not getattr(message.content[0], "text", None):
                    logger.warning("Claude 返回空 content，视为异常")
                    return {
                        "answer": "AI 返回内容为空，请稍后重试。",
                        "tokens": {"error": "empty_content"}
                    }
                answer = message.content[0].text
                tokens = {
                    "input": message.usage.input_tokens,
                    "output": message.usage.output_tokens,
                    "total": message.usage.input_tokens + message.usage.output_tokens
                }

                # 计算费用
                cost = (tokens["input"] / 1_000_000) * 3 + \
                       (tokens["output"] / 1_000_000) * 15
                tokens["cost"] = round(cost, 6)

                logger.info(f"Claude调用成功: 实际输入={tokens['input']} tokens, 总计={tokens['total']}, 费用=${tokens['cost']}")

                return {
                    "answer": answer,
                    "tokens": tokens,
                    "claude_payload": claude_payload
                }

            except anthropic.RateLimitError as e:
                logger.error(f"API限流: {e}")
                return {
                    "answer": "请求过于频繁，请稍后再试。",
                    "tokens": {"error": str(e)}
                }
            except anthropic.APIError as e:
                # 详细记录错误信息
                error_msg = str(e)
                estimated_tokens = len(system_prompt) // 3 + len(user_prompt) // 3
                logger.error(f"❌ Claude API错误: {error_msg}")
                logger.error(f"详细 - 预估tokens: {estimated_tokens}, 上下文数: {context_count}条, system长度: {len(system_prompt)}, user长度: {len(user_prompt)}")

                # 判断是否为 token 超限错误
                if any(keyword in error_msg.lower() for keyword in ["too long", "token", "context", "limit", "exceed"]):
                    return {
                        "answer": f"输入内容过长，超过 Claude API 限制。\n\n详细信息：\n- 预估输入: {estimated_tokens:,} tokens\n- 上下文条数: {context_count}条\n- Claude API 上限: 1,000,000 tokens\n\n建议：切换为「一般模式」（50条上下文）后重试。",
                        "tokens": {"error": str(e), "estimated_tokens": estimated_tokens, "context_count": context_count}
                    }

                return {
                    "answer": f"AI服务暂时不可用，请稍后重试。\n\n错误信息: {error_msg}",
                    "tokens": {"error": str(e)}
                }
            except Exception as e:
                logger.error(f"生成答案失败: {e}", exc_info=True)
                raise

    def _get_map_note_reference_from_hit(self, source: Dict, hit: Dict, index_name: str = "") -> str:
        """
        map 类索引的引用：去掉括号，只保留文本。
        - map_note：msg 项内有 source，优先从命中的 msg 项取
        - map_7feasts：用文档外层 source
        - map_dictionary：用文档外层 text
        """
        def _strip_parens(t) -> str:
            t = str(t or "").strip()
            for left, right in [("（", "）"), ("(", ")")]:
                if t.startswith(left) and t.endswith(right):
                    t = t[len(left):-len(right)].strip()
            return t

        # map_dictionary：引用 = 第一个bookname + ", " + title + ", " + 第二个bookname（从 msg 中取）
        if index_name == "map_dictionary":
            msg_list = source.get("msg") or []
            booknames = [str(m.get("text") or "").strip() for m in msg_list if (m.get("type") or "") == "bookname"]
            titles = [str(m.get("text") or "").strip() for m in msg_list if (m.get("type") or "") == "title"]
            b1 = booknames[0] if len(booknames) >= 1 else ""
            t = titles[0] if titles else ""
            b2 = booknames[1] if len(booknames) >= 2 else ""
            parts = [p for p in [b1, t, b2] if p]
            if parts:
                return "，".join(parts)
            s = _strip_parens(source.get("text") or "")
            if s:
                return s
            return _strip_parens(source.get("id") or source.get("_id") or "") or "未知来源"

        # map_pano：清明上河图，+ 外层 text
        if index_name == "map_pano":
            t = str(source.get("text") or "").strip()
            if t:
                return f"清明上河图，{t}"
            s = _strip_parens(source.get("source") or "")
            if s:
                return f"清明上河图，{s}"
            return _strip_parens(source.get("id") or source.get("_id") or "") or "清明上河图"

        # map_7feasts：msg 内无 source，用文档级 source
        if index_name == "map_7feasts":
            s = _strip_parens(source.get("source") or "")
            if s:
                return s
            return _strip_parens(source.get("id") or source.get("_id") or "") or "未知来源"

        # map_note：圣经真理题库，+ 外层 text
        if index_name == "map_note":
            t = str(source.get("text") or "").strip()
            if t:
                return f"圣经真理题库，{t}"
            return "圣经真理题库"

        # 其他 map 类回退
        inner = hit.get("inner_hits", {}).get("matched_msg", {})
        msg_list = source.get("msg") or []
        for ih in inner.get("hits", {}).get("hits", []):
            s = _strip_parens(ih.get("_source", {}).get("source") or "")
            if s:
                return s
            offset = (ih.get("_nested") or {}).get("offset")
            if isinstance(offset, int) and 0 <= offset < len(msg_list):
                s = _strip_parens(msg_list[offset].get("source") or "")
                if s:
                    return s
        s = _strip_parens(source.get("source") or "")
        if s:
            return s
        return _strip_parens(source.get("id") or source.get("_id") or "") or "未知来源"

    def _format_reference(self, source: Dict) -> str:
        """格式化经文引用"""
        # 尝试多种可能的字段名
        book = source.get('book') or source.get('title') or source.get('bookname') or ''
        chapter = source.get('chapter') or source.get('chap') or ''
        verse = source.get('verse') or source.get('vs') or ''
        
        # 尝试获取其他标识信息
        volume = source.get('volume') or source.get('vol') or ''
        page = source.get('page') or source.get('pg') or ''
        section = source.get('section') or source.get('sec') or ''
        
        # 优先使用书卷+章节+节
        if book and chapter and verse:
            return f"{book} {chapter}:{verse}"
        elif book and chapter:
            return f"{book} {chapter}"
        elif book:
            return book
        
        # 尝试使用卷+页
        if volume and page:
            return f"卷{volume} 第{page}页"
        elif volume:
            return f"卷{volume}"
        
        # 尝试使用章节信息
        if section:
            return f"第{section}节"
        
        # 最后尝试ID或其他标识
        doc_id = source.get('id') or source.get('_id') or ''
        if doc_id:
            return f"文档 {doc_id}"
        
        return "未知来源"

    def _get_source_type(self, index_name: str) -> str:
        """获取来源类型标签"""
        type_map = {
            "cwwl": "[李常受文集]",
            "cwwn": "[倪柝声文集]",
            "life": "[生命读经]",
            "others": "[其他]",
            "bib": "[圣经]",
            "map_note": "[注解]",
            "map_7feasts": "[复合节期]",
            "map_dictionary": "[词典]",
            "map_pano": "[上河图]",
        }
        return type_map.get(index_name, "[未分类]")

    def _extract_sources(self, search_results: List[Dict]) -> List[Dict]:
        """提取引用来源"""
        sources = []

        for hit in search_results:
            source = hit['_source']
            index_name = hit.get('_index_name', '')

            # 提取内容预览
            content = (
                source.get('content') or
                source.get('text') or
                source.get('msg') or
                source.get('outline') or
                ''
            )

            # 限制预览长度
            preview = content[:150] + "..." if len(content) > 150 else content

            ref = self._get_map_note_reference_from_hit(source, hit, index_name) if index_name in self._MAP_LIKE_INDICES else self._format_reference(source)
            sources.append({
                "reference": ref,
                "content": preview,
                "score": round(hit.get('_weighted_score', hit.get('_score', 0)), 2),
                "type": self._get_source_type(hit.get('_index_name', ''))
            })

        return sources

    def _normalize_metadata(self, metadata: Optional[Dict[str, str]]) -> Dict[str, str]:
        """去除空白并统一元数据"""
        if not metadata:
            return {}
        normalized = {}
        for key, value in metadata.items():
            if value is None:
                continue
            text = str(value).strip()
            if text:
                normalized[key] = text
        return normalized

    def _get_cache_key(
        self,
        question: str,
        depth: str = "general",
        metadata: Optional[Dict[str, str]] = None
    ) -> str:
        """生成缓存key（包含问题和深度参数）"""
        # 使用MD5哈希问题、深度及元数据生成唯一key
        cache_content = f"{question}:{depth}"
        if metadata:
            meta_items = sorted(metadata.items())
            meta_str = "|".join(f"{k}={v}" for k, v in meta_items)
            cache_content = f"{cache_content}:{meta_str}"
        question_hash = hashlib.md5(cache_content.encode()).hexdigest()
        return f"ai_search:{question_hash}"

    def _get_from_cache(self, cache_key: str) -> Optional[Dict]:
        """从Redis获取缓存"""
        if not self.redis:
            return None
        try:
            cached = self.redis.get(cache_key)
            if cached:
                return json.loads(cached)
            return None
        except Exception as e:
            logger.warning(f"读取缓存失败: {e}")
            return None

    def _save_to_cache(self, cache_key: str, result: Dict) -> bool:
        """保存到Redis缓存"""
        if not self.redis:
            return False
        try:
            # 移除不需要缓存的字段（claude_payload 体积大，不缓存）
            cache_data = result.copy()
            cache_data.pop("cached", None)
            cache_data.pop("claude_payload", None)

            self.redis.setex(
                cache_key,
                self.cache_ttl,
                json.dumps(cache_data, ensure_ascii=False)
            )
            return True
        except Exception as e:
            logger.warning(f"保存缓存失败: {e}")
            return False

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

        cache_key = f"ai_search:translate:{hashlib.sha256(outline.encode()).hexdigest()[:32]}"
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

                            def _translate_title_for_cache(retry_count: int = 0) -> Optional[str]:
                                with GEMINI_SEMAPHORE:
                                    try:
                                        title_response = gemini_client.models.generate_content(
                                            model=GEMINI_MODEL,
                                            contents=topic,
                                            config=types.GenerateContentConfig(
                                                system_instruction=_gemini_system_instruction,
                                            ),
                                        )
                                        if title_response and getattr(title_response, "text", None):
                                            raw_title = title_response.text.strip()
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
                                        else:
                                            logger.warning("缓存标题翻译返回空响应（重试次数: %s）", retry_count)
                                    except Exception as e:
                                        error_msg = str(e)
                                        is_retryable = (
                                            "503" in error_msg or "UNAVAILABLE" in error_msg or "429" in error_msg
                                            or "timeout" in error_msg.lower() or "temporary" in error_msg.lower()
                                        )
                                        if is_retryable and retry_count == 0:
                                            logger.warning("缓存标题翻译调用失败（可重试）: %s，等待2秒后重试...", e)
                                            time.sleep(2)
                                        else:
                                            logger.warning("缓存标题翻译调用失败（重试次数: %s）: %s", retry_count, e)
                                return None

                            cached_title = _translate_title_for_cache(retry_count=0)
                            if cached_title is None:
                                cached_title = _translate_title_for_cache(retry_count=1)
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

        def _call_gemini(retry_count: int = 0) -> Optional[str]:
            with GEMINI_SEMAPHORE:
                try:
                    response = gemini_client.models.generate_content(
                        model=GEMINI_MODEL,
                        contents=contents_zh2en,
                        config=types.GenerateContentConfig(
                            system_instruction=_gemini_system_instruction,
                        ),
                    )
                    if response and getattr(response, "text", None):
                        return response.text.strip()
                    else:
                        logger.warning(f"Gemini 翻译返回空响应（重试次数: {retry_count}）")
                except Exception as e:
                    error_msg = str(e)
                    # 检查是否是503或其他可重试的错误
                    is_retryable = (
                        "503" in error_msg or 
                        "UNAVAILABLE" in error_msg or 
                        "429" in error_msg or  # Rate limit
                        "timeout" in error_msg.lower() or
                        "temporary" in error_msg.lower()
                    )
                    if is_retryable and retry_count == 0:
                        logger.warning(f"Gemini 翻译调用失败（可重试）: {e}，等待2秒后重试...")
                        time.sleep(2)  # 等待2秒后重试
                    else:
                        logger.warning(f"Gemini 翻译调用失败（重试次数: {retry_count}）: {e}")
            return None

        answer_en = _call_gemini(retry_count=0)
        if answer_en is None:
            answer_en = _call_gemini(retry_count=1)  # 重试 1 次
        
        # 翻译标题（如果提供）- 独立执行，即使纲目内容翻译失败也尝试翻译标题
        title_en = None
        if outline_topic and outline_topic.strip():
            topic = outline_topic.strip()
            
            def _translate_title(retry_count: int = 0) -> Optional[str]:
                """翻译标题，带重试逻辑"""
                with GEMINI_SEMAPHORE:
                    try:
                        title_response = gemini_client.models.generate_content(
                            model=GEMINI_MODEL,
                            contents=topic,
                            config=types.GenerateContentConfig(
                                system_instruction=_gemini_system_instruction,
                            ),
                        )
                        if title_response and getattr(title_response, "text", None):
                            raw_title = title_response.text.strip()
                            # 清理可能的提示词前缀
                            title_en_clean = raw_title
                            # 移除常见的提示词前缀
                            prefixes_to_remove = [
                                "Translation:", "English:", "翻译：", "英文：",
                                "The translation is:", "Here is the translation:",
                                "Title:", "标题："
                            ]
                            for prefix in prefixes_to_remove:
                                if title_en_clean.lower().startswith(prefix.lower()):
                                    title_en_clean = title_en_clean[len(prefix):].strip()
                            # 移除引号（如果 Gemini 加了引号）
                            title_en_clean = title_en_clean.strip('"\'')
                            return title_en_clean
                        else:
                            logger.warning(f"标题翻译返回空响应（重试次数: {retry_count}）")
                    except Exception as e:
                        error_msg = str(e)
                        is_retryable = (
                            "503" in error_msg or 
                            "UNAVAILABLE" in error_msg or 
                            "429" in error_msg or
                            "timeout" in error_msg.lower() or
                            "temporary" in error_msg.lower()
                        )
                        if is_retryable and retry_count == 0:
                            logger.warning(f"标题翻译调用失败（可重试）: {e}，等待2秒后重试...")
                            time.sleep(2)  # 等待2秒后重试
                        else:
                            logger.warning(f"标题翻译调用失败（重试次数: {retry_count}）: {e}")
                return None
            
            # 尝试翻译标题，失败时重试1次（带延迟）
            title_en = _translate_title(retry_count=0)
            if title_en is None:
                title_en = _translate_title(retry_count=1)  # 重试1次
            
            if title_en:
                logger.info(f"标题翻译成功: '{topic}' -> '{title_en}'")
            else:
                logger.warning(f"标题翻译失败（已重试1次）: '{topic}'")
        
        # 如果纲目内容翻译失败，返回错误（但标题翻译结果仍会返回）
        if answer_en is None:
            return {"answer_en": None, "title_en": title_en, "error": "纲目内容翻译失败，请稍后重试"}

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

        return {"answer_en": answer_en, "title_en": title_en}

    def translate_outline_en2zh(self, english_outline: str) -> Dict:
        """
        将英文纲目翻译为中文纲目（调用 Gemini，使用英翻中 instruction）。
        用于工具箱「纲目翻译」- 英翻中。失败时重试 1 次。
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

        # 发送内容 = 需要翻译的文章 + 格式与术语说明（英翻中）
        contents_en2zh = outline + "\n\n" + OUTLINE_TRANSLATE_PROMPT_EN2ZH

        def _call_gemini(retry_count: int = 0) -> Optional[str]:
            with GEMINI_SEMAPHORE:
                try:
                    response = gemini_client.models.generate_content(
                        model=GEMINI_MODEL,
                        contents=contents_en2zh,
                        config=types.GenerateContentConfig(
                            system_instruction=_gemini_system_instruction_en2zh,
                        ),
                    )
                    if response and getattr(response, "text", None):
                        return response.text.strip()
                    logger.warning("Gemini 英翻中返回空响应（重试次数: %s）", retry_count)
                except Exception as e:
                    error_msg = str(e)
                    is_retryable = (
                        "503" in error_msg or "UNAVAILABLE" in error_msg or "429" in error_msg
                        or "timeout" in error_msg.lower() or "temporary" in error_msg.lower()
                    )
                    if is_retryable and retry_count == 0:
                        logger.warning("Gemini 英翻中调用失败（可重试）: %s，等待2秒后重试...", e)
                        time.sleep(2)
                    else:
                        logger.warning("Gemini 英翻中调用失败（重试次数: %s）: %s", retry_count, e)
            return None

        answer_zh = _call_gemini(retry_count=0)
        if answer_zh is None:
            answer_zh = _call_gemini(retry_count=1)
        if answer_zh is None:
            return {"answer_zh": None, "error": "纲目翻译失败，请稍后重试"}
        return {"answer_zh": answer_zh}

    def translate_and_format_outline(
        self,
        direction: str,
        content: str,
        outline_topic: Optional[str] = None,
    ) -> Dict:
        """
        翻译纲目并格式化下载 DOCX。
        
        Args:
            direction: "zh2en" 或 "en2zh"
            content: 待翻译的纲目全文
            outline_topic: 纲目主题（仅中翻英时可选，用于翻译标题）
        
        Returns:
            {
                "result": str,  # 翻译后的文本
                "docx_bytes": bytes | None,  # 格式化后的 DOCX bytes（失败时为 None）
                "filename": str | None,  # 建议的文件名
                "error": str | None,  # 错误信息
            }
        """
        import shutil
        import tempfile
        from docx import Document

        # 1. 先翻译
        if direction == "zh2en":
            trans_result = self.translate_outline(content, outline_topic, use_cache=False)
            translated_text = trans_result.get("answer_en")
            error = trans_result.get("error")
            template_name = "英文纲目模板.docx"
            format_func = format_english_outline_docx
            default_filename = "outline_en.docx"
        elif direction == "en2zh":
            trans_result = self.translate_outline_en2zh(content)
            translated_text = trans_result.get("answer_zh")
            error = trans_result.get("error")
            template_name = "中文纲目模板.docx"
            format_func = format_chinese_outline_docx
            default_filename = "outline_zh.docx"
        else:
            return {
                "result": None,
                "docx_bytes": None,
                "filename": None,
                "error": f"无效的翻译方向: {direction}",
            }

        if error or not translated_text:
            return {
                "result": translated_text,
                "docx_bytes": None,
                "filename": None,
                "error": error or "翻译失败",
            }

        # 2. 检查格式刷函数是否可用
        if format_func is None:
            logger.warning("格式刷函数未导入，返回未格式化的翻译结果")
            return {
                "result": translated_text,
                "docx_bytes": None,
                "filename": default_filename,
                "error": None,
            }

        # 3. 复制模板并写入翻译结果
        backend_dir = Path(__file__).resolve().parent.parent
        template_path = backend_dir / template_name
        if not template_path.exists():
            logger.error(f"模板文件不存在: {template_path}")
            return {
                "result": translated_text,
                "docx_bytes": None,
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

            # 4. 调用格式刷
            try:
                format_func(temp_docx_path)
            except Exception as e:
                logger.error(f"格式刷失败: {e}", exc_info=True)
                # 格式刷失败时仍返回未格式化的文档
                pass

            # 5. 读取为 bytes
            with open(temp_docx_path, "rb") as f:
                docx_bytes = f.read()

            # 6. 生成文件名（基于题目：中文纲目取读经前最后一段，英文纲目取 Scripture reading 前最后一段）
            # 回退逻辑：如果没有读经/Scripture reading，则以第一个大点位置判断题目
            filename = default_filename
            if lines:
                title_line = None
                if direction == "en2zh":
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
                    filename = f"{safe_name}.docx"

            # 清理临时文件
            try:
                os.unlink(temp_docx_path)
            except Exception:
                pass

            return {
                "result": translated_text,
                "docx_bytes": docx_bytes,
                "filename": filename,
                "error": None,
            }

        except Exception as e:
            logger.error(f"翻译并格式化失败: {e}", exc_info=True)
            # 清理临时文件
            try:
                if "temp_docx_path" in locals():
                    os.unlink(temp_docx_path)
            except Exception:
                pass
            return {
                "result": translated_text,
                "docx_bytes": None,
                "filename": default_filename,
                "error": f"格式化失败: {str(e)}",
            }

    def info_retrieval_export(
        self,
        keyword: str,
        exclude_keywords: str = "",
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> Tuple[Optional[bytes], Optional[str], str]:
        """
        信息检索：多关键词 AND、排除关键词 OR。单文件上限 40MB，超出则拆成多个 DOCX（-1、-2…）并打包为 ZIP。
        有结果时：单文件返回 (docx_bytes, filename, log_message)，多文件返回 ([(bytes, filename), ...], None, log_message)；无结果时返回 (None, None, log_message)。
        若提供 progress_callback，会在检索过程中实时回调进度文案。
        """
        def _progress(msg: str) -> None:
            if progress_callback:
                progress_callback(msg)

        raw_keyword = (keyword or "").strip()
        keywords = [k.strip() for k in raw_keyword.split() if k.strip()]
        if not keywords:
            log_message = "请输入至少一个搜索关键词（当前为空或仅空格）。"
            return (None, None, log_message)

        exclude_list = [e.strip() for e in (exclude_keywords or "").split() if e.strip()]
        max_bytes = 40 * 1024 * 1024  # 固定 40MB，超出则拆成多个 DOCX
        _progress(f"开始检索，共 {len(INFO_RETRIEVAL_INDEXES)} 个索引")

        # 用于 wildcard 的转义：* \ ? 需转义
        def _escape_wildcard(s: str) -> str:
            for c, rep in [("\\", "\\\\"), ("*", "\\*"), ("?", "\\?")]:
                s = s.replace(c, rep)
            return s

        # 文件名：仅保留安全字符
        def _safe_filename(s: str) -> str:
            s = re.sub(r'[/\\:*?"<>|]', "_", s)
            return (s.strip() or "export")[:100]

        def _item_bytes(label: str, title: str, content: str) -> int:
            return len((label + title + content).encode("utf-8"))

        def _flush_batch():
            if current_batch:
                batches.append(list(current_batch))
                current_batch.clear()
            return 0

        batches = []  # List[List[(label, title, content)]], 每批 ≤40MB
        current_batch = []
        current_size = 0
        seen_prefix = set()  # (index_name, prefix) 或 (index_name, doc_id) 去重
        seen_map_id = set()  # (index_name, doc_id) map 类去重

        for index_name in INFO_RETRIEVAL_INDEXES:
            index_label = INDEX_LABELS.get(index_name, index_name)
            _progress(f"正在检索 {index_label}…")
            try:
                if index_name in self._MAP_LIKE_INDICES:
                    # map 类：单关键词用 match_phrase（短语相邻），多关键词用 match AND（避免「珍赏职事」拆成「珍赏」「职事」分散命中）
                    if len(keywords) == 1:
                        must_clauses = [{"match_phrase": {"text": keywords[0]}}]
                    else:
                        must_clauses = [{"match": {"text": kw}} for kw in keywords]
                    q = {"bool": {"must": must_clauses}}
                    if exclude_list:
                        q["bool"]["must_not"] = [{"match_phrase": {"text": ex}} for ex in exclude_list]
                    body = {
                        "query": q,
                        "size": 10000,
                        "_source": ["id", "text", "msg", "source", "sn", "bookname", "title", "bookname2"],
                    }
                else:
                    # 非 map：title wildcard 多关键词 AND，排除词 OR
                    must_clauses = [{"wildcard": {"title": "*%s*" % _escape_wildcard(kw)}} for kw in keywords]
                    q = {"bool": {"must": must_clauses}}
                    if exclude_list:
                        q["bool"]["must_not"] = [{"wildcard": {"title": "*%s*" % _escape_wildcard(ex)}} for ex in exclude_list]
                    body = {
                        "query": q,
                        "size": 10000,
                        "_source": ["id", "type", "text", "title", "book", "chapter", "verse"],
                    }
                resp = self.es.search(
                    index=index_name,
                    body=body,
                    request_timeout=60,
                    ignore_unavailable=True,
                )
            except Exception as e:
                logger.warning(f"信息检索索引 {index_name} 查询失败: {e}")
                _progress(f"索引 {index_label} 查询失败")
                continue

            hits = resp.get("hits", {}).get("hits", [])

            if index_name in self._MAP_LIKE_INDICES:
                for h in hits:
                    source = h.get("_source", {})
                    doc_id = str(source.get("id") or h.get("_id") or "")
                    if (index_name, doc_id) in seen_map_id:
                        continue
                    seen_map_id.add((index_name, doc_id))
                    # 返回同 id 文档的 msg 中所有 text 的拼接
                    msg_list = source.get("msg") or []
                    parts = [t for m in msg_list for t in [str(m.get("text") or "").strip()] if t]
                    content = "\n".join(parts)
                    if not content.strip():
                        continue
                    # 标题与 AI 搜索引用来源一致
                    title = self._get_map_note_reference_from_hit(source, h, index_name)
                    # 多关键词时只保留篇题同时包含所有关键词的结果（真 AND）
                    if len(keywords) > 1 and not all(kw in title for kw in keywords):
                        continue
                    label = INDEX_LABELS.get(index_name, index_name)
                    item_size = _item_bytes(label, title, content)
                    if current_size + item_size > max_bytes and current_batch:
                        _flush_batch()
                        current_size = 0
                    current_batch.append((label, title, content))
                    current_size += item_size
            else:
                for h in hits:
                    source = h.get("_source", {})
                    doc_id = str(source.get("id") or h.get("_id", ""))
                    prefix, _ = self._parse_doc_id(doc_id)
                    if prefix:
                        if (index_name, prefix) in seen_prefix:
                            continue
                        seen_prefix.add((index_name, prefix))
                        docs = self._fetch_message_docs(index_name, prefix)
                        if not docs:
                            continue
                        parts = []
                        for d in docs:
                            t = str(d.get("text") or "").strip()
                            if t:
                                parts.append(t)
                        content = "\n".join(parts)
                        doc_title = self._format_reference(docs[0])
                    else:
                        # id 无 "-" 时视为单条文档，不按 prefix 拉整篇
                        if (index_name, doc_id) in seen_prefix:
                            continue
                        seen_prefix.add((index_name, doc_id))
                        content = str(source.get("text") or "").strip()
                        doc_title = self._format_reference(source)
                    if not content.strip():
                        continue
                    # 多关键词时只保留篇题同时包含所有关键词的结果（真 AND）
                    if len(keywords) > 1 and not all(kw in doc_title for kw in keywords):
                        continue
                    label = INDEX_LABELS.get(index_name, index_name)
                    item_size = _item_bytes(label, doc_title, content)
                    if current_size + item_size > max_bytes and current_batch:
                        _flush_batch()
                        current_size = 0
                    current_batch.append((label, doc_title, content))
                    current_size += item_size
            total_items = sum(len(b) for b in batches) + len(current_batch)
            _progress(f"完成 {index_label}，命中 {len(hits)} 条，当前累计 {total_items} 条")

        if current_batch:
            batches.append(current_batch)

        if not batches:
            log_message = "未找到匹配的文档。请检查关键词或排除词，或稍后重试（部分索引可能暂时不可用）。"
            return (None, None, log_message)

        _progress("正在生成 DOCX…")
        try:
            from docx import Document
            from docx.oxml.ns import qn
        except ImportError:
            raise RuntimeError("请安装 python-docx: pip install python-docx")

        name_base = "_".join(keywords) if keywords else raw_keyword
        if exclude_list:
            name_base += "（过滤" + "、".join(exclude_list) + "）"
        base_name = _safe_filename(name_base)

        # 中文字体名，用于 DOCX 正文与标题，避免手机等设备打开时缺字出现方框乱码
        _DOCX_CJK_FONT = "Microsoft YaHei"

        def _set_docx_cjk_font(doc: "Document") -> None:
            """为文档的 Normal 与 Heading 1 设置支持中文的字体（含东亚 w:eastAsia），减少手机打开时方框乱码。"""
            for style_name in ("Normal", "Heading 1"):
                style = doc.styles[style_name]
                style.font.name = _DOCX_CJK_FONT
                try:
                    if style._element.rPr is not None and style._element.rPr.rFonts is not None:
                        style._element.rPr.rFonts.set(qn("w:eastAsia"), _DOCX_CJK_FONT)
                except (AttributeError, Exception):
                    pass

        def _make_docx(items_batch: List[Tuple[str, str, str]]) -> bytes:
            doc = Document()
            _set_docx_cjk_font(doc)
            for i, (label, title, content) in enumerate(items_batch):
                doc.add_heading(f"[{label}] {title}", level=1)
                doc.add_paragraph(content)
                if i < len(items_batch) - 1:
                    doc.add_paragraph()
            buf = BytesIO()
            doc.save(buf)
            buf.seek(0)
            return buf.getvalue()

        total_items = sum(len(b) for b in batches)
        if len(batches) == 1:
            filename = base_name + ".docx"
            log_message = f"共导出 {total_items} 条，已生成 {filename}"
            return (_make_docx(batches[0]), filename, log_message)

        # 多文件：返回 [(bytes, filename), ...]，由路由以 JSON 返回，前端逐个下载
        files_list = [
            (_make_docx(batch), f"{base_name}-{i}.docx")
            for i, batch in enumerate(batches, start=1)
        ]
        log_message = f"共导出 {total_items} 条，已生成 {len(batches)} 个文件：{base_name}-1.docx ～ {base_name}-{len(batches)}.docx"
        return (files_list, None, log_message)

    def clear_cache(self) -> Dict:
        """清空 AI 搜索 Redis 缓存（所有 ai_search:* 键）。返回删除的键数量。"""
        if not self.redis:
            return {"cleared": 0, "message": "Redis 未启用"}
        try:
            keys = self.redis.keys("ai_search:*")
            if keys:
                self.redis.delete(*keys)
            count = len(keys)
            logger.info(f"AI 搜索缓存已清理，删除 {count} 条")
            return {"cleared": count, "message": f"已清理 {count} 条缓存" if count else "缓存为空，无需清理"}
        except Exception as e:
            logger.warning(f"清理缓存失败: {e}")
            return {"cleared": 0, "message": str(e)}

    def health_check(self) -> Dict:
        """健康检查"""
        status = {
            "elasticsearch": False,
            "redis": False,
            "claude": False,
            "gemini": False,
            "overall": False
        }

        try:
            # 检查ES
            status["elasticsearch"] = self.es.ping()
        except Exception:
            pass

        try:
            # 检查Redis
            if self.redis:
                status["redis"] = self.redis.ping()
        except Exception:
            pass

        try:
            # 检查Claude（通过检查API key是否存在）
            status["claude"] = bool(CLAUDE_API_KEY)
        except Exception:
            pass

        try:
            # 检查Gemini（英文翻译，可选）
            status["gemini"] = bool(GEMINI_API_KEY and gemini_client)
        except Exception:
            pass

        # 核心依赖为 ES + Claude；Redis、Gemini 为可选
        status["overall"] = status["elasticsearch"] and status["claude"]

        return status


# 创建全局服务实例
ai_service = AISearchService()
