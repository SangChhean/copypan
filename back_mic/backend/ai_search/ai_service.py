"""
AI搜索服务 - 核心业务逻辑
负责Elasticsearch检索、Claude API调用、结果处理
"""
import asyncio
import os
import json
import hashlib
import logging
import time
import uuid
import warnings
from typing import Any, Callable, Dict, List, Optional, Tuple
from datetime import datetime
from io import BytesIO
import re
import threading
from concurrent.futures import ThreadPoolExecutor

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

# 双路检索 + Reranker（USE_VECTOR_SEARCH=true 时使用）
try:
    from .embedding_service import get_embeddings as _get_embeddings_async
    from .vector_search import knn_search_multi
    from .rrf import rrf_merge, apply_index_weight
    from .reranker_service import rerank as _rerank_docs
except ImportError as e:
    logger.warning("混合检索依赖未就绪: %s", e)
    _get_embeddings_async = None
    knn_search_multi = None
    rrf_merge = None
    apply_index_weight = None
    _rerank_docs = None


def _is_burden_valid(burden: str) -> bool:
    """负担说明有效性校验：去除空白、标点、特殊字符后实质内容必须大于5个字"""
    if not burden:
        return False
    meaningful = re.sub(r"[\s\W]", "", burden, flags=re.UNICODE)
    return len(meaningful) > 5


def _call_claude_messages_sync(client, system_prompt: str, user_prompt: str, max_tokens: int = 1024) -> Tuple[str, Any]:
    """同步调用 Claude messages API，返回 (首条 content 的 text, usage 或 None)。"""
    if not client:
        return ("", None)
    msg = client.messages.create(
        model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6"),
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text = ""
    if msg.content and getattr(msg.content[0], "text", None):
        text = msg.content[0].text
    return (text, getattr(msg, "usage", None))


def _parse_json_array_from_text(text: str) -> List[str]:
    """从 Claude 返回文本中解析 JSON 数组，返回字符串列表。"""
    if not text or not isinstance(text, str):
        return []
    s = text.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        if len(lines) >= 2:
            s = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        arr = json.loads(s)
        if isinstance(arr, list):
            return [str(x).strip() for x in arr if str(x).strip()]
    except json.JSONDecodeError:
        pass
    return []


def _parse_skeleton_points(text: str) -> List[Dict]:
    """从 Claude 返回文本中解析摘要 points JSON：{"points": [{"title", "search_query", "sub_directions"}, ...]}。"""
    if not text or not isinstance(text, str):
        return []
    s = text.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        if len(lines) >= 2:
            s = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
    try:
        data = json.loads(s)
        if isinstance(data, dict) and "points" in data:
            pts = data["points"]
            if isinstance(pts, list):
                out = []
                for p in pts:
                    if not isinstance(p, dict):
                        continue
                    title = str(p.get("title") or "").strip()
                    sq = str(p.get("search_query") or "").strip()
                    subs = p.get("sub_directions")
                    if isinstance(subs, list):
                        sub_directions = [str(x).strip() for x in subs if str(x).strip()]
                    else:
                        sub_directions = []
                    if title or sq or sub_directions:
                        out.append({"title": title, "search_query": sq, "sub_directions": sub_directions})
                return out
    except json.JSONDecodeError:
        pass
    return []


# 配置日志（必须在导入格式刷之前，因为导入失败时会使用 logger）
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ai_search")

# 加载环境变量（确保从 backend 目录加载 .env）
env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

# 双路检索 + Reranker 开关（DESIGN_SPEC_V2）
USE_VECTOR_SEARCH = os.environ.get("USE_VECTOR_SEARCH", "false").lower() == "true"
USE_RERANK = os.environ.get("USE_RERANK", "true").lower() == "true"

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
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")
try:
    claude_client = anthropic.Anthropic(api_key=CLAUDE_API_KEY) if CLAUDE_API_KEY else None
    if claude_client:
        logger.info("Claude 客户端初始化成功")
except Exception as e:
    logger.error(f"Claude 客户端初始化失败: {e}")
    claude_client = None

# Gemini 客户端（用于中文纲目→英文纲目翻译，需配置 GEMINI_API_KEY；使用新 SDK google.genai）
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# 纲目翻译：默认 gemini-2.5-pro 保证可用；若 3.1 不可用(404) 会自动用 GEMINI_TRANSLATION_FALLBACK_MODEL
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
GEMINI_TRANSLATION_FALLBACK_MODEL = os.getenv("GEMINI_TRANSLATION_FALLBACK_MODEL", "gemini-2.5-pro")
# 毛胚纲目：主模型 3.1，备用模型 3.0。若 503 持续可设 ROUGH_OUTLINE_GEMINI_MODEL 优先用其他模型
ROUGH_OUTLINE_GEMINI_MODEL = os.getenv("ROUGH_OUTLINE_GEMINI_MODEL", "")
# 主模型重试全失败后尝试的备用模型，默认 gemini-2.5-pro
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-2.5-pro")
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

# 毛胚纲目 - 其他 API（.env 中填写对应 API Key 后启用）
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY")
DEEPSEEK_MODEL = os.getenv("DEEPSEEK_MODEL", "deepseek-v3.2")
PERPLEXITY_API_KEY = os.getenv("PERPLEXITY_API_KEY")
PERPLEXITY_MODEL = os.getenv("PERPLEXITY_MODEL", "sonar-pro")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4")
XAI_API_KEY = os.getenv("XAI_API_KEY")  # Grok
XAI_MODEL = os.getenv("XAI_MODEL", "grok-4-1-fast-reasoning")

# 毛胚纲目 OpenAI 兼容接口费用（美元/百万 token），按 provider 分别计算
ROUGH_OUTLINE_PRICES = {
    "chatgpt": {"in": 2.50, "out": 15.00},
    "grok": {"in": 0.20, "out": 0.50},
    "deepseek": {"in": 0.27, "out": 1.10},
    "perplexity": {"in": 3.00, "out": 15.00},  # sonar-pro
}

# 并发限制：同时进行中的 Claude / Gemini 请求数，避免人多时触发 API 限流（429）
def _parse_concurrent_limit(env_key: str, default: int) -> int:
    try:
        v = int(os.getenv(env_key, str(default)))
        return max(1, v)  # 至少为 1，避免 Semaphore(0) 导致永久阻塞
    except (ValueError, TypeError):
        return default

# Claude Tier 1 约 50 RPM，Gemini 免费/低阶约 5–15 RPM；20/10 在 Tier 2 与付费 Tier 1 下安全，可通过 .env 覆盖
CLAUDE_CONCURRENT_LIMIT = _parse_concurrent_limit("CLAUDE_CONCURRENT_LIMIT", 20)
GEMINI_CONCURRENT_LIMIT = _parse_concurrent_limit("GEMINI_CONCURRENT_LIMIT", 10)
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
        "一般性": "cwwl 1994-1997 文集 ×1.1",
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


def _strip_code_fence_for_outline(text: Optional[str]) -> Optional[str]:
    """
    若毛胚纲目 AI 返回的内容被 markdown 代码块包裹（如 ```text 或 ``` 开头、``` 结尾），
    剥掉首尾围栏，只保留正文，便于展示。若未包裹则原样返回。
    """
    if not text or not isinstance(text, str):
        return text
    s = text.strip()
    if not s.startswith("```"):
        return text
    lines = s.split("\n")
    if len(lines) < 2:
        return text
    lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip() if lines else text


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
                        mode=cached_result.get("mode") or ("新版方式一" if USE_VECTOR_SEARCH else "旧版"),
                        depth=depth,
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
            if USE_VECTOR_SEARCH:
                skeleton_raw = (normalized_metadata or {}).get("skeleton") or (normalized_metadata or {}).get("burden_description") or ""
                skeleton = skeleton_raw.strip() if isinstance(skeleton_raw, str) else ""
                if skeleton:
                    # 方式二：摘要框架，按大点检索后存 Redis，返回 search_id 供 generate 使用
                    try:
                        mode2_results = asyncio.run(
                            self._hybrid_search_mode2(question.strip(), skeleton, outline_nature, depth, burden_description=(normalized_metadata or {}).get("burden_description") or "")
                        )
                    except Exception as e:
                        logger.error("方式二混合检索失败: %s", e, exc_info=True)
                        mode2_results = []
                    search_time = (time.time() - search_start) * 1000
                    if not mode2_results:
                        return {
                            "answer": "抱歉，摘要解析或检索未得到结果，请检查摘要格式或稍后重试。",
                            "sources": [],
                            "cached": False,
                            "search_time": search_time
                        }
                    if self.redis:
                        search_id = str(uuid.uuid4())
                        skeleton_key = f"ai_search:{search_id}:skeleton_context"
                        skeleton_value = json.dumps(
                            {"mode": "skeleton", "points": mode2_results},
                            ensure_ascii=False,
                        )
                        self.redis.setex(skeleton_key, 300, skeleton_value)
                        sources_preview = self._extract_sources_from_mode2_points(mode2_results)
                        logger.info(f"方式二检索完成: {len(mode2_results)}个大点, search_id={search_id}, 耗时{search_time:.0f}ms")
                        return {
                            "sources": sources_preview,
                            "search_id": search_id,
                            "search_time": round(search_time, 0),
                        }
                    else:
                        # 无 Redis：方式二在同一请求内完成生成并返回
                        ai_start = time.time()
                        answer_text, mode2_payload, mode2_usage = asyncio.run(self._generate_mode2(question.strip(), mode2_results, skeleton=skeleton))
                        ai_time = (time.time() - ai_start) * 1000
                        sources_preview = self._extract_sources_from_mode2_points(mode2_results)
                        total_time = round((time.time() - start_time) * 1000, 0)
                        in_tok = int(getattr(mode2_usage, "input_tokens", 0) or 0) if mode2_usage else 0
                        out_tok = int(getattr(mode2_usage, "output_tokens", 0) or 0) if mode2_usage else 0
                        cost = (in_tok * 3 + out_tok * 15) / 1_000_000 if (in_tok or out_tok) else None
                        result = {
                            "answer": answer_text,
                            "sources": sources_preview,
                            "cached": False,
                            "tokens": {},
                            "search_time": round(search_time, 0),
                            "ai_time": round(ai_time, 0),
                            "total_time": total_time,
                            "timestamp": datetime.now().isoformat(),
                            "claude_payload": mode2_payload,
                            "mode": "新版方式二",
                        }
                        try:
                            get_monitoring(self.redis).record_query(
                                question=question[:500],
                                response_time_ms=total_time,
                                cache_hit=False,
                                input_tokens=in_tok,
                                output_tokens=out_tok,
                                cost=cost,
                                special_needs=normalized_metadata.get("special_needs"),
                                mode="新版方式二",
                                depth=depth,
                            )
                        except Exception as _e:
                            logger.debug(f"监控记录失败: {_e}")
                        return result
                try:
                    hybrid_docs = asyncio.run(
                        self._hybrid_search_mode1(question.strip(), outline_nature, depth, burden_description="")
                    )
                except Exception as e:
                    logger.error("方式一混合检索失败: %s", e, exc_info=True)
                    hybrid_docs = []
                search_time = (time.time() - search_start) * 1000
                if not hybrid_docs:
                    return {
                        "answer": "抱歉，没有找到相关的经文内容。建议：\n1. 尝试使用不同的关键词\n2. 检查是否有拼写错误\n3. 使用更具体的描述",
                        "sources": [],
                        "cached": False,
                        "search_time": search_time
                    }
                logger.info(f"混合检索完成: {len(hybrid_docs)}条结果, 耗时{search_time:.0f}ms")
                context_items = self._build_context_from_hybrid_docs(hybrid_docs, context_size, depth)
                search_results = hybrid_docs  # 供后续 _extract_sources 使用需为 list[dict]；hybrid 无 _source，用 _extract_sources_from_context
            else:
                burden_desc = (normalized_metadata or {}).get("burden_description") or ""
                search_results = self._multi_index_search(question, fetch_size, outline_nature, mode="旧版", depth=depth, burden="是" if _is_burden_valid(burden_desc) else "否")
                search_time = (time.time() - search_start) * 1000
                if not search_results:
                    return {
                        "answer": "抱歉，没有找到相关的经文内容。建议：\n1. 尝试使用不同的关键词\n2. 检查是否有拼写错误\n3. 使用更具体的描述",
                        "sources": [],
                        "cached": False,
                        "search_time": search_time
                    }
                logger.info(f"ES检索完成: {len(search_results)}条结果, 耗时{search_time:.0f}ms")
                context_items = self._build_context_from_hits(search_results, context_size, depth)
                if not context_items:
                    context_items = self._fallback_context_from_hits(search_results, context_size, depth)

            # 4. 调用Claude生成答案
            if not self.claude:
                return {
                    "answer": "AI 服务未配置（请设置 CLAUDE_API_KEY）。",
                    "sources": self._extract_sources_from_context(context_items[:50]) if context_items else [],
                    "cached": False,
                    "search_time": round(search_time, 0),
                    "error": True
                }
            ai_start = time.time()
            ai_response = self._generate_answer(
                question,
                context_items,
                context_size,
                normalized_metadata
            )
            ai_time = (time.time() - ai_start) * 1000

            logger.info(f"AI生成完成: 耗时{ai_time:.0f}ms")

            # 5. 构造返回结果（引用来源最多 50 条）
            mode = "新版方式一" if USE_VECTOR_SEARCH else "旧版"
            result = {
                "answer": ai_response["answer"],
                "sources": self._extract_sources_from_context(context_items[:50]),
                "cached": False,
                "tokens": ai_response.get("tokens"),
                "claude_payload": ai_response.get("claude_payload"),
                "search_time": round(search_time, 0),
                "ai_time": round(ai_time, 0),
                "total_time": round((time.time() - start_time) * 1000, 0),
                "timestamp": datetime.now().isoformat(),
                "mode": mode,
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
                    mode=mode,
                    depth=depth,
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

    async def search_async(
        self,
        question: str,
        max_results: int = 30,
        depth: str = "general",
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict:
        """
        一步接口的异步版本，供路由在 USE_VECTOR_SEARCH 时调用，避免 asyncio.run() 导致 Event loop is closed。
        与 search() 行为一致，方式一/方式二用 await，BM25 用 asyncio.to_thread。
        """
        start_time = time.time()
        try:
            validation_result = self._validate_input(question, max_results)
            if not validation_result["valid"]:
                return {"answer": validation_result["message"], "sources": [], "cached": False, "error": True}
            question = question.strip()
            logger.info(f"收到问题: {question}")
            normalized_metadata = self._normalize_metadata(metadata)
            cache_key = self._get_cache_key(question, depth, normalized_metadata)
            cached_result = self._get_from_cache(cache_key)
            if cached_result:
                logger.info("缓存命中")
                cached_result["cached"] = True
                try:
                    get_monitoring(self.redis).record_query(
                        question=question[:500], response_time_ms=(time.time() - start_time) * 1000,
                        cache_hit=True,
                        input_tokens=int((cached_result.get("tokens") or {}).get("input", 0) or 0),
                        output_tokens=int((cached_result.get("tokens") or {}).get("output", 0) or 0),
                        cost=(cached_result.get("tokens") or {}).get("cost"),
                        special_needs=normalized_metadata.get("special_needs"),
                        mode=cached_result.get("mode") or ("新版方式一" if USE_VECTOR_SEARCH else "旧版"),
                        depth=depth,
                    )
                except Exception as _e:
                    logger.debug(f"监控记录失败: {_e}")
                return cached_result

            search_start = time.time()
            context_size = 50 if depth == "general" else 200
            fetch_size = context_size
            outline_nature = (normalized_metadata or {}).get("special_needs", "")
            if USE_VECTOR_SEARCH:
                skeleton_raw = (normalized_metadata or {}).get("skeleton") or (normalized_metadata or {}).get("burden_description") or ""
                skeleton = skeleton_raw.strip() if isinstance(skeleton_raw, str) else ""
                if skeleton:
                    try:
                        mode2_results = await self._hybrid_search_mode2(question, skeleton, outline_nature, depth, burden_description=(normalized_metadata or {}).get("burden_description") or "")
                    except Exception as e:
                        logger.error("方式二混合检索失败: %s", e, exc_info=True)
                        mode2_results = []
                    search_time = (time.time() - search_start) * 1000
                    search_time = (time.time() - search_start) * 1000
                    if not mode2_results:
                        return {"answer": "抱歉，摘要解析或检索未得到结果，请检查摘要格式或稍后重试。", "sources": [], "cached": False, "search_time": search_time}
                    if self.redis:
                        search_id = str(uuid.uuid4())
                        self.redis.setex(f"ai_search:{search_id}:skeleton_context", 300, json.dumps({"mode": "skeleton", "points": mode2_results}, ensure_ascii=False))
                        sources_preview = self._extract_sources_from_mode2_points(mode2_results)
                        logger.info(f"方式二检索完成: {len(mode2_results)}个大点, search_id={search_id}, 耗时{search_time:.0f}ms")
                        return {"sources": sources_preview, "search_id": search_id, "search_time": round(search_time, 0)}
                    ai_start = time.time()
                    answer_text, mode2_payload, mode2_usage = await self._generate_mode2(question, mode2_results, skeleton=skeleton)
                    ai_time = (time.time() - ai_start) * 1000
                    total_time = round((time.time() - start_time) * 1000, 0)
                    in_tok = int(getattr(mode2_usage, "input_tokens", 0) or 0) if mode2_usage else 0
                    out_tok = int(getattr(mode2_usage, "output_tokens", 0) or 0) if mode2_usage else 0
                    cost = (in_tok * 3 + out_tok * 15) / 1_000_000 if (in_tok or out_tok) else None
                    result = {"answer": answer_text, "sources": self._extract_sources_from_mode2_points(mode2_results), "cached": False, "tokens": {}, "search_time": round(search_time, 0), "ai_time": round(ai_time, 0), "total_time": total_time, "timestamp": datetime.now().isoformat(), "claude_payload": mode2_payload, "mode": "新版方式二"}
                    try:
                        get_monitoring(self.redis).record_query(question=question[:500], response_time_ms=total_time, cache_hit=False, input_tokens=in_tok, output_tokens=out_tok, cost=cost, special_needs=normalized_metadata.get("special_needs"), mode="新版方式二", depth=depth)
                    except Exception as _e:
                        logger.debug(f"监控记录失败: {_e}")
                    return result
                try:
                    hybrid_docs = await self._hybrid_search_mode1(question, outline_nature, depth, burden_description="")
                except Exception as e:
                    logger.error("方式一混合检索失败: %s", e, exc_info=True)
                    hybrid_docs = []
                search_time = (time.time() - search_start) * 1000
                if not hybrid_docs:
                    return {"answer": "抱歉，没有找到相关的经文内容。建议：\n1. 尝试使用不同的关键词\n2. 检查是否有拼写错误\n3. 使用更具体的描述", "sources": [], "cached": False, "search_time": search_time}
                logger.info(f"混合检索完成: {len(hybrid_docs)}条结果, 耗时{search_time:.0f}ms")
                context_items = self._build_context_from_hybrid_docs(hybrid_docs, context_size, depth)
                search_results = hybrid_docs
            else:
                search_results = await asyncio.to_thread(self._multi_index_search, question, fetch_size, outline_nature)
                search_time = (time.time() - search_start) * 1000
                if not search_results:
                    return {"answer": "抱歉，没有找到相关的经文内容。建议：\n1. 尝试使用不同的关键词\n2. 检查是否有拼写错误\n3. 使用更具体的描述", "sources": [], "cached": False, "search_time": search_time}
                logger.info(f"ES检索完成: {len(search_results)}条结果, 耗时{search_time:.0f}ms")
                context_items = self._build_context_from_hits(search_results, context_size, depth)
                if not context_items:
                    context_items = self._fallback_context_from_hits(search_results, context_size, depth)

            if not self.claude:
                return {"answer": "AI 服务未配置（请设置 CLAUDE_API_KEY）。", "sources": self._extract_sources_from_context(context_items[:50]) if context_items else [], "cached": False, "search_time": round(search_time, 0), "error": True}
            ai_start = time.time()
            ai_response = self._generate_answer(question, context_items, context_size, normalized_metadata)
            ai_time = (time.time() - ai_start) * 1000
            logger.info(f"AI生成完成: 耗时{ai_time:.0f}ms")
            mode = "新版方式一" if USE_VECTOR_SEARCH else "旧版"
            result = {"answer": ai_response["answer"], "sources": self._extract_sources_from_context(context_items[:50]), "cached": False, "tokens": ai_response.get("tokens"), "claude_payload": ai_response.get("claude_payload"), "search_time": round(search_time, 0), "ai_time": round(ai_time, 0), "total_time": round((time.time() - start_time) * 1000, 0), "timestamp": datetime.now().isoformat(), "mode": mode}
            self._save_to_cache(cache_key, result)
            try:
                tokens = result.get("tokens") or {}
                input_tok = int(tokens.get("input", 0) or 0)
                output_tok = int(tokens.get("output", 0) or 0)
                if not input_tok and not output_tok:
                    answer_text = (result.get("answer") or "") or ""
                    input_tok = int((len(question) + len(answer_text)) * 1.3)
                    output_tok = int(len(answer_text) * 1.3)
                get_monitoring(self.redis).record_query(question=question[:500], response_time_ms=result["total_time"], cache_hit=False, input_tokens=input_tok, output_tokens=output_tok, cost=tokens.get("cost"), special_needs=normalized_metadata.get("special_needs"), mode=mode, depth=depth)
            except Exception as _e:
                logger.debug(f"监控记录失败: {_e}")
            logger.info(f"搜索完成: 总耗时{result['total_time']}ms")
            return result
        except Exception as e:
            logger.error(f"搜索失败: {e}", exc_info=True)
            try:
                get_monitoring(self.redis).record_error(str(e), extra={"question": (question[:200] if question else "")})
            except Exception as _e:
                logger.debug(f"监控记录失败: {_e}")
            return {"answer": f"搜索出错: {str(e)}\n请稍后重试或联系管理员。", "sources": [], "cached": False, "error": True}

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
            skeleton_visible = "有" if (normalized_metadata or {}).get("skeleton") else "无"
            logger.info("search_only 开始: question=%s | USE_VECTOR_SEARCH=%s | skeleton=%s",
                        question[:40] + "..." if len(question) > 40 else question,
                        USE_VECTOR_SEARCH, skeleton_visible)
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
                        mode=cached.get("mode") or ("新版方式一" if USE_VECTOR_SEARCH else "旧版"),
                        depth=depth,
                    )
                except Exception as _e:
                    logger.debug(f"监控记录失败: {_e}")
                return cached

            context_size = 50 if depth == "general" else 200
            search_start = time.time()
            outline_nature = (normalized_metadata or {}).get("special_needs", "")

            if USE_VECTOR_SEARCH:
                skeleton_raw = (normalized_metadata or {}).get("skeleton") or (normalized_metadata or {}).get("burden_description") or ""
                skeleton = skeleton_raw.strip() if isinstance(skeleton_raw, str) else ""
                if skeleton:
                    logger.info("检索模式: 方式二(摘要)，开始按大点检索...")
                    try:
                        mode2_results = asyncio.run(
                            self._hybrid_search_mode2(question, skeleton, outline_nature, depth, burden_description=(normalized_metadata or {}).get("burden_description") or "")
                        )
                    except Exception as e:
                        logger.error("方式二混合检索失败: %s", e, exc_info=True)
                        mode2_results = []
                    search_time = (time.time() - search_start) * 1000
                    if not mode2_results:
                        return {
                            "sources": [],
                            "search_id": None,
                            "search_time": round(search_time, 0),
                            "error": True,
                            "message": "摘要解析或检索未得到结果，请检查摘要格式或稍后重试。",
                        }
                    search_id = str(uuid.uuid4())
                    skeleton_key = f"ai_search:{search_id}:skeleton_context"
                    self.redis.setex(
                        skeleton_key,
                        300,
                        json.dumps({"mode": "skeleton", "points": mode2_results}, ensure_ascii=False),
                    )
                    sources_preview = self._extract_sources_from_mode2_points(mode2_results)
                    logger.info(f"方式二 search_only 完成: {len(mode2_results)}个大点, search_id={search_id}, 耗时{search_time:.0f}ms")
                    return {"sources": sources_preview, "search_id": search_id, "search_time": round(search_time, 0)}
                logger.info("检索模式: 方式一(双路混合)，开始 BM25+向量 RRF...")
                try:
                    hybrid_docs = asyncio.run(
                        self._hybrid_search_mode1(question, outline_nature, depth, burden_description="")
                    )
                except Exception as e:
                    logger.error("方式一混合检索失败: %s", e, exc_info=True)
                    hybrid_docs = []
                search_time = (time.time() - search_start) * 1000
                if not hybrid_docs:
                    return {
                        "sources": [],
                        "search_id": None,
                        "search_time": round(search_time, 0),
                        "error": True,
                        "message": "没有找到相关的经文内容",
                    }
                search_id = str(uuid.uuid4())
                context_key = f"ai_search:context:{search_id}"
                context_data = {
                    "mode": "hybrid",
                    "question": question,
                    "depth": depth,
                    "hybrid_docs": hybrid_docs,
                    "context_size": context_size,
                    "metadata": normalized_metadata,
                }
                self.redis.setex(
                    context_key,
                    300,
                    json.dumps(context_data, ensure_ascii=False, default=str),
                )
                context_items = self._build_context_from_hybrid_docs(hybrid_docs, context_size, depth)
                sources = self._extract_sources_from_context(context_items[:50])
                logger.info(f"方式一 search_only 完成: search_id={search_id}, {len(sources)}条来源, 深度模式: {depth}, 耗时{search_time:.0f}ms")
                return {"sources": sources, "search_id": search_id, "search_time": round(search_time, 0)}

            logger.info("检索模式: 原版(BM25)，开始多索引检索...")
            burden_desc = (normalized_metadata or {}).get("burden_description") or ""
            search_results = self._multi_index_search(question, context_size, outline_nature, mode="旧版", depth=depth, burden="是" if _is_burden_valid(burden_desc) else "否")
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

    async def search_only_async(
        self,
        question: str,
        depth: str = "general",
        metadata: Optional[Dict[str, str]] = None
    ) -> Dict:
        """
        方案A 第一步的异步版本，供路由在 USE_VECTOR_SEARCH 时调用，避免 asyncio.run() 导致子事件循环关闭、AsyncES 报 Event loop is closed。
        与 search_only 行为一致，但方式一/方式二使用 await，BM25 使用 asyncio.to_thread。
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

            normalized_metadata = self._normalize_metadata(metadata)
            skeleton_visible = "有" if (normalized_metadata or {}).get("skeleton") else "无"
            logger.info("search_only_async 开始: question=%s | USE_VECTOR_SEARCH=%s | skeleton=%s",
                        question[:40] + "..." if len(question) > 40 else question,
                        USE_VECTOR_SEARCH, skeleton_visible)
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
                        mode=cached.get("mode") or ("新版方式一" if USE_VECTOR_SEARCH else "旧版"),
                        depth=depth,
                    )
                except Exception as _e:
                    logger.debug(f"监控记录失败: {_e}")
                return cached

            context_size = 50 if depth == "general" else 200
            search_start = time.time()
            outline_nature = (normalized_metadata or {}).get("special_needs", "")

            if USE_VECTOR_SEARCH:
                skeleton_raw = (normalized_metadata or {}).get("skeleton") or (normalized_metadata or {}).get("burden_description") or ""
                skeleton = skeleton_raw.strip() if isinstance(skeleton_raw, str) else ""
                if skeleton:
                    logger.info("检索模式: 方式二(摘要)，开始按大点检索...")
                    try:
                        mode2_results = await self._hybrid_search_mode2(question, skeleton, outline_nature, depth, burden_description=(normalized_metadata or {}).get("burden_description") or "")
                    except Exception as e:
                        logger.error("方式二混合检索失败: %s", e, exc_info=True)
                        mode2_results = []
                    search_time = (time.time() - search_start) * 1000
                    if not mode2_results:
                        return {
                            "sources": [],
                            "search_id": None,
                            "search_time": round(search_time, 0),
                            "error": True,
                            "message": "摘要解析或检索未得到结果，请检查摘要格式或稍后重试。",
                        }
                    search_id = str(uuid.uuid4())
                    skeleton_key = f"ai_search:{search_id}:skeleton_context"
                    self.redis.setex(
                        skeleton_key,
                        300,
                        json.dumps({"mode": "skeleton", "points": mode2_results}, ensure_ascii=False),
                    )
                    sources_preview = self._extract_sources_from_mode2_points(mode2_results)
                    logger.info(f"方式二 search_only 完成: {len(mode2_results)}个大点, search_id={search_id}, 耗时{search_time:.0f}ms")
                    return {"sources": sources_preview, "search_id": search_id, "search_time": round(search_time, 0)}
                logger.info("检索模式: 方式一(双路混合)，开始 BM25+向量 RRF...")
                try:
                    hybrid_docs = await self._hybrid_search_mode1(question, outline_nature, depth, burden_description="")
                except Exception as e:
                    logger.error("方式一混合检索失败: %s", e, exc_info=True)
                    hybrid_docs = []
                search_time = (time.time() - search_start) * 1000
                if not hybrid_docs:
                    return {
                        "sources": [],
                        "search_id": None,
                        "search_time": round(search_time, 0),
                        "error": True,
                        "message": "没有找到相关的经文内容",
                    }
                search_id = str(uuid.uuid4())
                context_key = f"ai_search:context:{search_id}"
                context_data = {
                    "mode": "hybrid",
                    "question": question,
                    "depth": depth,
                    "hybrid_docs": hybrid_docs,
                    "context_size": context_size,
                    "metadata": normalized_metadata,
                }
                self.redis.setex(
                    context_key,
                    300,
                    json.dumps(context_data, ensure_ascii=False, default=str),
                )
                context_items = self._build_context_from_hybrid_docs(hybrid_docs, context_size, depth)
                sources = self._extract_sources_from_context(context_items[:50])
                logger.info(f"方式一 search_only 完成: search_id={search_id}, {len(sources)}条来源, 深度模式: {depth}, 耗时{search_time:.0f}ms")
                return {"sources": sources, "search_id": search_id, "search_time": round(search_time, 0)}

            logger.info("检索模式: 原版(BM25)，开始多索引检索...")
            burden_desc = (normalized_metadata or {}).get("burden_description") or ""
            search_results = await asyncio.to_thread(
                self._multi_index_search, question, context_size, outline_nature, "旧版", depth, "是" if _is_burden_valid(burden_desc) else "否"
            )
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
                300,
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
            logger.error(f"search_only_async 失败: {e}", exc_info=True)
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
            skeleton_key = f"ai_search:{search_id}:skeleton_context"
            skeleton_data = self.redis.get(skeleton_key)
            if skeleton_data:
                try:
                    data = json.loads(skeleton_data)
                    points = data.get("points") or []
                except Exception as e:
                    logger.warning("方式二 skeleton 数据解析失败: %s", e)
                    points = []
                try:
                    self.redis.delete(skeleton_key)
                except Exception:
                    pass
                if not points:
                    return {
                        "answer": "方式二上下文已过期或无效，请重新检索。",
                        "sources": [],
                        "cached": False,
                        "error": True
                    }
                logger.info("generate_only 模式: 方式二(摘要填充), 大点数=%s", len(points))
                q = (question or "").strip() or "纲目"
                ai_start = time.time()
                answer_text, mode2_payload, mode2_usage = asyncio.run(self._generate_mode2(q, points, skeleton=""))
                ai_time = (time.time() - ai_start) * 1000
                logger.info(f"[generate_only 完成] 方式二 | 大点数: {len(points)} | 总耗时: {int((time.time() - start_time) * 1000)}ms")
                sources_preview = self._extract_sources_from_mode2_points(points)
                total_time = (time.time() - start_time) * 1000
                normalized_meta = self._normalize_metadata(metadata or {})
                in_tok = int(getattr(mode2_usage, "input_tokens", 0) or 0) if mode2_usage else 0
                out_tok = int(getattr(mode2_usage, "output_tokens", 0) or 0) if mode2_usage else 0
                cost = (in_tok * 3 + out_tok * 15) / 1_000_000 if mode2_usage else None
                depth = (metadata or {}).get("depth") or "general"
                try:
                    get_monitoring(self.redis).record_query(
                        question=q[:500],
                        response_time_ms=round(total_time, 0),
                        cache_hit=False,
                        input_tokens=in_tok,
                        output_tokens=out_tok,
                        cost=cost,
                        special_needs=normalized_meta.get("special_needs"),
                        mode="新版方式二",
                        depth=depth,
                    )
                except Exception as _e:
                    logger.debug(f"监控记录失败: {_e}")
                return {
                    "answer": answer_text,
                    "sources": sources_preview,
                    "cached": False,
                    "tokens": {"input": in_tok, "output": out_tok, "cost": cost},
                    "search_time": 0,
                    "ai_time": round(ai_time, 0),
                    "total_time": round(total_time, 0),
                    "timestamp": datetime.now().isoformat(),
                    "claude_payload": mode2_payload,
                }
            if not raw:
                return {
                    "answer": "搜索会话已过期，请重新提问",
                    "sources": [],
                    "cached": False,
                    "error": True
                }

            ctx = json.loads(raw)
            stored_question = ctx.get("question", "")
            stored_depth = ctx.get("depth", "general")
            context_size = ctx.get("context_size", 200)
            gen_mode = "方式一(双路混合)" if ctx.get("mode") == "hybrid" else "原版(context)"
            logger.info("generate_only 模式: %s", gen_mode)

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
                        mode=cached.get("mode") or ("新版方式一" if USE_VECTOR_SEARCH else "旧版"),
                        depth=stored_depth,
                    )
                except Exception as _e:
                    logger.debug(f"监控记录失败: {_e}")
                return cached

            if ctx.get("mode") == "hybrid":
                hybrid_docs = ctx.get("hybrid_docs") or []
                if not hybrid_docs:
                    return {"answer": "未找到相关上下文", "sources": [], "cached": False, "error": True}
                context_items = self._build_context_from_hybrid_docs(hybrid_docs, context_size, stored_depth)
            else:
                search_results = ctx.get("search_results", [])
                if not search_results:
                    return {"answer": "未找到相关上下文", "sources": [], "cached": False, "error": True}
                context_items = self._build_context_from_hits(search_results, context_size, stored_depth)
                if not context_items:
                    context_items = self._fallback_context_from_hits(search_results, context_size, stored_depth)

            ai_start = time.time()
            ai_response = self._generate_answer(
                question or stored_question,
                context_items,
                context_size,
                normalized_metadata
            )
            ai_time = (time.time() - ai_start) * 1000

            logger.info(f"[generate_only 完成] {gen_mode} | 上下文条数: {len(context_items)} | 总耗时: {int((time.time() - start_time) * 1000)}ms")

            sources = self._extract_sources_from_context(context_items[:max_results])
            total_time = (time.time() - start_time) * 1000
            mode = "新版方式二" if "方式二" in gen_mode else ("新版方式一" if "方式一" in gen_mode else "旧版")
            result = {
                "answer": ai_response["answer"],
                "sources": sources,
                "cached": False,
                "tokens": ai_response.get("tokens"),
                "claude_payload": ai_response.get("claude_payload"),
                "search_time": 0,
                "ai_time": round(ai_time, 0),
                "total_time": round(total_time, 0),
                "timestamp": datetime.now().isoformat(),
                "mode": mode,
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
                    mode=mode,
                    depth=stored_depth,
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
        self, query: str, size: int, outline_nature: str = "",
        mode: str = "旧版", depth: str = "general", burden: str = "否"
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
                    # 其他索引（bib/cwwl/cwwn/life/others）：查 text + zh 字段
                    search_body = {
                        "query": {
                            "bool": {
                                "should": [
                                    {"match_phrase": {"text": {"query": query, "boost": 2.5}}},
                                    {"match": {"text": {"query": query, "fuzziness": "AUTO", "boost": 2.0}}},
                                    {"match_phrase": {"zh": {"query": query, "boost": 2.5}}},
                                    {"match": {"zh": {"query": query, "fuzziness": "AUTO", "boost": 2.0}}}
                                ],
                                "minimum_should_match": 1
                            }
                        },
                        "size": int(size * weight),
                        "_source": ["id", "type", "book", "chapter", "verse", "text", "zh", "title"]
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
                        elif outline_nature == "一般性":
                            # 一般性：cwwl 1994-1997 文集 ×1.1
                            if "cwwl_1994-1997" in doc_id:
                                score *= 1.1
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
            get_monitoring(self.redis).record_retrieval_stats(question_preview, total, used, waste_rate, mode=mode, depth=depth, burden=burden)
        except Exception as _e:
            logger.debug(f"记录检索统计失败: {_e}")

        return all_results[:size]

    def _bm25_hit_to_flat_doc(self, hit: Dict) -> Dict:
        """将 BM25 命中转为 RRF 所需的扁平格式：_id, _index, text, source_label。"""
        source = hit.get("_source") or {}
        index_name = hit.get("_index_name") or hit.get("_index") or ""
        doc_id = source.get("id") or hit.get("_id") or ""
        if index_name in self._MAP_LIKE_INDICES:
            text = self._extract_map_note_sections_from_inner_hits(source, hit)
            source_label = self._get_map_note_reference_from_hit(source, hit, index_name)
        else:
            text = (source.get("zh") or source.get("text") or "").strip()
            source_label = self._format_reference(source)
        return {
            "_id": doc_id,
            "_index": index_name,
            "text": text or "",
            "source_label": source_label or "",
        }

    async def _hybrid_search_mode1(
        self, question: str, special_needs: str, depth: str, burden_description: str = ""
    ) -> List[Dict]:
        """
        方式一：主题生成纲目 — 双路混合检索 + RRF + Reranker（可选）+ 索引加权。
        返回扁平文档列表，每条含 _id, _index, text, source_label, rrf_score, weighted_score。
        """
        if not question or not question.strip():
            return []
        if _get_embeddings_async is None or rrf_merge is None or apply_index_weight is None:
            logger.warning("混合检索依赖未就绪，请配置 OPENAI_API_KEY 并安装 ai_search 子模块")
            return []

        # 1. Claude 展开为 5 个短句主题
        system_expand = "你是一个资深的圣经研究学者，只输出 JSON，不输出其他任何内容。"
        burden_line = f"负担说明：{burden_description}\n" if _is_burden_valid(burden_description) else ""
        user_expand = (
            f"你是一个资深的圣经研究学者，更是一位专业的倪柝声、李常受神学的研究者。"
            f"请将以下主题，从【启示】【真理】【经历】【应用】四个角度各展开一个短句（每句15-25字），"
            f"模仿职事书报的语气（如：神圣的生命就是神自己分赐到我们里面作我们的享受）。"
            f"纲目性质为「{special_needs}」，展开时须偏重此性质。\n"
            f"{burden_line}"
            f"以JSON数组返回，例如[\"启示句\",\"真理句\",\"经历句\",\"应用句\"]，不输出其他内容。\n"
            f"主题：{question}"
        )
        try:
            expand_result, usage = await asyncio.to_thread(
                _call_claude_messages_sync,
                self.claude,
                system_expand,
                user_expand,
            )
            if usage is not None:
                logger.info(
                    f"[子主题展开] Claude调用成功: 输入={usage.input_tokens} tokens, "
                    f"输出={usage.output_tokens} tokens, "
                    f"总计={usage.input_tokens + usage.output_tokens} tokens, "
                    f"费用=${(usage.input_tokens * 3 + usage.output_tokens * 15) / 1_000_000:.5f}"
                )
        except Exception as e:
            logger.error("Claude 主题展开失败: %s", e)
            return []
        sub_topics = _parse_json_array_from_text(expand_result or "")
        if len(sub_topics) < 5:
            sub_topics = sub_topics + [question] * (5 - len(sub_topics))  # 不足 5 条用主题补齐
        else:
            sub_topics = sub_topics[:5]
        if _is_burden_valid(burden_description):
            sub_topics.append(burden_description)
        sub_topics = sub_topics[:6]

        logger.info(f"[子主题展开] 展开结果: {sub_topics}（共{len(sub_topics)}句）, 负担说明参与: {'是' if _is_burden_valid(burden_description) else '否'}")

        # 2. 批量 Embedding：question + 子主题（最多 6 条）
        all_texts = [question.strip()] + sub_topics
        try:
            vectors = await _get_embeddings_async(all_texts)
        except Exception as e:
            logger.error("Embedding 失败: %s", e)
            return []
        if not vectors or len(vectors) != len(all_texts):
            return []
        # vectors[0] 为主题，vectors[1:] 为子主题（含可选的负担说明一路）
        sub_vectors = vectors[1:]

        # 3. 并发：路1 BM25 / 路2 kNN，条数由 depth 控制
        all_indices = [
            "cwwl", "cwwn", "life", "others", "bib",
            "map_note_chunks", "map_7feasts_chunks", "map_pano_chunks", "map_dictionary_chunks",
        ]
        bm25_size = 400 if depth == "deep" else 200
        bm25_results = await asyncio.to_thread(
            self._multi_index_search, question.strip(), bm25_size, special_needs
        )
        bm25_flat = [self._bm25_hit_to_flat_doc(h) for h in bm25_results]
        # 过滤无正文的（避免 RRF/rerank 无效）
        bm25_flat = [d for d in bm25_flat if (d.get("text") or "").strip()]
        try:
            knn_k = 80 if depth == "deep" else 40
            knn_results = await knn_search_multi(sub_vectors, all_indices, k=knn_k)
        except Exception as e:
            logger.error("kNN 检索失败: %s", e)
            knn_results = []

        # 4. RRF 融合
        rrf_top_n = 400 if depth == "deep" else 200
        rrf_results = rrf_merge([bm25_flat, knn_results], k=60, top_n=rrf_top_n)
        if not rrf_results:
            return []

        # BM25 / kNN 占比统计
        bm25_ids = set(d.get("_id") or d.get("id") or "" for d in bm25_flat)
        knn_ids = set(d.get("_id") or d.get("id") or "" for d in knn_results)
        rrf_top_ids = [d.get("_id") or d.get("id") or "" for d in rrf_results]
        rrf_from_bm25 = sum(1 for did in rrf_top_ids if did in bm25_ids)
        rrf_from_knn = sum(1 for did in rrf_top_ids if did in knn_ids)
        rrf_from_both = sum(1 for did in rrf_top_ids if did in bm25_ids and did in knn_ids)
        rrf_total = len(rrf_top_ids)
        logger.info(
            f"RRF占比 - 总条数:{rrf_total} | "
            f"纯BM25:{rrf_from_bm25 - rrf_from_both} | "
            f"纯kNN:{rrf_from_knn - rrf_from_both} | "
            f"BM25+kNN都命中:{rrf_from_both} | "
            f"BM25占比:{round((rrf_from_bm25/rrf_total)*100, 1)}% | "
            f"kNN占比:{round((rrf_from_knn/rrf_total)*100, 1)}%"
        )

        # 5. Jina Reranker（若 USE_RERANK）
        reranker_top_n = 200 if depth == "deep" else 100
        if USE_RERANK and _rerank_docs is not None:
            texts = [d.get("text") or "" for d in rrf_results]
            try:
                indices = await _rerank_docs(question.strip(), texts, top_n=reranker_top_n)
            except Exception as e:
                logger.warning("Reranker 失败，使用 RRF 顺序: %s", e)
                indices = list(range(min(reranker_top_n, len(rrf_results))))
            reranked = [rrf_results[i] for i in indices if i < len(rrf_results)]
        else:
            reranked = rrf_results[:reranker_top_n]

        # 6. 索引加权
        weighted_top_n = 60 if depth == "deep" else 30
        weighted = apply_index_weight(reranked, special_needs, top_n=weighted_top_n)
        logger.info(f"[方式一检索] 深度模式: {depth} | Reranker后: {len(reranked)}条 | 最终送Claude: {len(weighted)}条")
        return weighted

    async def _search_one_point(
        self, point: Dict, special_needs: str, total_points: int = 3, depth: str = "general"
    ) -> Dict:
        """方式二单大点检索：BM25 + kNN → RRF → Reranker → 加权 per_point，条数由 depth 控制，返回 {title, context: [str]}。"""
        all_indices = [
            "cwwl", "cwwn", "life", "others", "bib",
            "map_note_chunks", "map_7feasts_chunks", "map_pano_chunks", "map_dictionary_chunks",
        ]
        search_query = (point.get("search_query") or "").strip() or (point.get("title") or "")
        sub_directions = point.get("sub_directions") or []
        if not isinstance(sub_directions, list):
            sub_directions = []
        title = str(point.get("title") or "").strip()

        bm25_size = 120 if depth == "deep" else 60
        bm25_results = await asyncio.to_thread(
            self._multi_index_search, search_query, bm25_size, special_needs
        )
        bm25_flat = [self._bm25_hit_to_flat_doc(h) for h in bm25_results]
        bm25_flat = [d for d in bm25_flat if (d.get("text") or "").strip()]

        if not sub_directions or _get_embeddings_async is None:
            sub_vectors = []
        else:
            try:
                sub_vectors = await _get_embeddings_async(sub_directions)
            except Exception:
                sub_vectors = []
        if sub_vectors:
            try:
                knn_k = 40 if depth == "deep" else 20
                knn_results = await knn_search_multi(sub_vectors, all_indices, k=knn_k)
            except Exception:
                knn_results = []
        else:
            knn_results = []

        rrf_top_n = 120 if depth == "deep" else 60
        rrf_results = rrf_merge([bm25_flat, knn_results], k=60, top_n=rrf_top_n)
        if not rrf_results:
            return {"title": title, "context": [], "context_details": []}

        # BM25 / kNN 占比统计
        bm25_ids = set(d.get("_id") or d.get("id") or "" for d in bm25_flat)
        knn_ids = set(d.get("_id") or d.get("id") or "" for d in knn_results)
        rrf_top_ids = [d.get("_id") or d.get("id") or "" for d in rrf_results]
        rrf_from_bm25 = sum(1 for did in rrf_top_ids if did in bm25_ids)
        rrf_from_knn = sum(1 for did in rrf_top_ids if did in knn_ids)
        rrf_from_both = sum(1 for did in rrf_top_ids if did in bm25_ids and did in knn_ids)
        rrf_total = len(rrf_top_ids)
        logger.info(
            f"[方式二] RRF占比 [{title}] - 总条数:{rrf_total} | "
            f"纯BM25:{rrf_from_bm25 - rrf_from_both} | "
            f"纯kNN:{rrf_from_knn - rrf_from_both} | "
            f"BM25+kNN都命中:{rrf_from_both} | "
            f"BM25占比:{round((rrf_from_bm25/rrf_total)*100, 1)}% | "
            f"kNN占比:{round((rrf_from_knn/rrf_total)*100, 1)}%"
        )

        reranker_top_n = 60 if depth == "deep" else 30
        if USE_RERANK and _rerank_docs is not None:
            texts = [d.get("text") or "" for d in rrf_results]
            try:
                indices = await _rerank_docs(search_query, texts, top_n=reranker_top_n)
            except Exception:
                indices = list(range(min(reranker_top_n, len(rrf_results))))
            reranked = [rrf_results[i] for i in indices if i < len(rrf_results)]
        else:
            reranked = rrf_results[:reranker_top_n]

        per_point = max(10, 90 // total_points) if depth == "deep" else max(6, 45 // total_points)
        weighted = apply_index_weight(reranked, special_needs, top_n=per_point)
        logger.info(f"[方式二检索] 大点「{title}」深度模式: {depth} | Reranker后: {len(reranked)}条 | 最终送Claude: {len(weighted)}条")
        context_details = []
        for d in weighted:
            text = str(d.get("text") or "").strip()
            if not text:
                continue
            source_label = (d.get("source_label") or "").strip()
            if not source_label:
                source_label = self._format_reference(d)
            context_details.append({
                "text": text,
                "reference": source_label,
                "type": self._get_source_type(d.get("_index") or ""),
            })
        context = [detail["text"] for detail in context_details]
        return {"title": title, "context": context, "context_details": context_details}

    async def _hybrid_search_mode2(
        self, question: str, skeleton: str, special_needs: str, depth: str = "general", burden_description: str = ""
    ) -> List[Dict]:
        """
        方式二：主题+摘要 — 解析摘要后每大点独立双路检索，返回 [{"title": str, "context": list[str]}, ...]。
        """
        if not skeleton or not skeleton.strip():
            return []
        if _get_embeddings_async is None or rrf_merge is None or apply_index_weight is None or knn_search_multi is None:
            logger.warning("混合检索依赖未就绪")
            return []

        system_parse = "你是一个资深的圣经研究学者，只输出 JSON，不输出其他任何内容。"
        burden_line = f"负担说明：{burden_description}\n" if _is_burden_valid(burden_description) else ""
        user_parse = (
                f"你是一个资深的圣经研究学者，更是一位专业的倪柝声、李常受神学的研究者。\n"
                f"以下是一个主题和相关摘要，请根据主题和摘要的内容，提炼出2~5个检索方向（point），每个方向包含：\n"
                f"1. title：该检索方向的简短标题（10字以内）\n"
                f"2. search_query：一句职事书报语气的自然语言句子（15-25字），用于语义检索，"
                f"模仿如：「神圣的生命就是神自己分赐到我们里面作我们的享受」\n"
                f"3. sub_directions：从【启示】【真理】【经历】【应用】四个角度各一句（每句15-25字），"
                f"模仿职事书报语气，只输出句子内容，不加「启示：」「真理：」等前缀标签\n"
                f"以 JSON 格式返回，结构如下：\n"
                f'{{"points": [{{"title": "...", "search_query": "...", "sub_directions": ["...", "...", "...", "..."]}}]}}\n'
                f"{burden_line}"
                f"主题：{question}\n"
                f"摘要：{skeleton.strip()}"
        )
        try:
            parse_result, usage = await asyncio.to_thread(
                _call_claude_messages_sync,
                self.claude,
                system_parse,
                user_parse,
            )
            if usage is not None:
                logger.info(
                    f"[摘要解析] Claude调用成功: 输入={usage.input_tokens} tokens, "
                    f"输出={usage.output_tokens} tokens, "
                    f"总计={usage.input_tokens + usage.output_tokens} tokens, "
                    f"费用=${(usage.input_tokens * 3 + usage.output_tokens * 15) / 1_000_000:.5f}"
                )
        except Exception as e:
            logger.error("Claude 摘要解析失败: %s", e)
            return []
        raw_debug = (parse_result or "").strip()
        if len(raw_debug) > 8000:
            logger.debug("[摘要解析] 原始返回(前8000字): %s ... [已截断]", raw_debug[:8000])
        else:
            logger.debug("[摘要解析] 原始返回: %s", raw_debug)
        points = _parse_skeleton_points(parse_result or "")
        if not points:
            raw = (parse_result or "").strip()
            if len(raw) > 4000:
                logger.warning("[摘要解析] 解析结果为空，原始返回(前4000字): %s ... [已截断]", raw[:4000])
            else:
                logger.warning("[摘要解析] 解析结果为空，原始返回: %s", raw)
            return []

        logger.info(f"[摘要解析] 提炼大点: {[p.get('title', '') for p in points]}（共{len(points)}个）, 负担说明参与: {'是' if _is_burden_valid(burden_description) else '否'}")

        total_points = len(points)
        tasks = [self._search_one_point(p, special_needs, total_points=total_points, depth=depth) for p in points]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        out = []
        for i, r in enumerate(results):
            if isinstance(r, BaseException):
                logger.warning("方式二单大点检索失败: %s", r)
                out.append({"title": points[i].get("title", ""), "context": []})
            else:
                out.append(r)
        return out

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
        self, search_results: List[Dict], context_size: int, depth: str = "general"
    ) -> List[Dict]:
        """
        根据 type 规则构建上下文：heading 取整节，text/ot1-4 只取该段，其他不取。
        去重：已被整节覆盖的段落不再单独加入。
        返回 [{"reference": str, "content": str, "source_type": str, "score": float}, ...]
        """
        included_ids = set()
        context_items = []
        seen_sections = set()
        # 单条截断长度：depth=="deep" 时 2000 字，否则 1000 字
        max_content_length = 2000 if depth == "deep" else 1000

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
        self, search_results: List[Dict], context_size: int, depth: str = "general"
    ) -> List[Dict]:
        """当 _build_context_from_hits 无结果时回退：按原逻辑取 text 构建上下文（如 bib/hymn 等）"""
        items = []
        # 单条截断长度：depth=="deep" 时 2000 字，否则 1000 字
        max_content_length = 2000 if depth == "deep" else 1000
        
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

    def _build_context_from_hybrid_docs(
        self, hybrid_docs: List[Dict], context_size: int, depth: str = "general"
    ) -> List[Dict]:
        """从方式一混合检索得到的扁平文档列表构建 context_items（reference=source_label, content=text）。"""
        items = []
        # 单条截断长度：depth=="deep" 时 2000 字，否则 1000 字
        max_content_length = 2000 if depth == "deep" else 1000
        for d in hybrid_docs[:context_size]:
            text = (d.get("text") or "").strip()
            if not text:
                continue
            if len(text) > max_content_length:
                text = text[:max_content_length] + "..."
            source_label = (d.get("source_label") or "").strip()
            if not source_label:
                source_label = self._format_reference(d)
            items.append({
                "reference": source_label,
                "content": text,
                "source_type": self._get_source_type(d.get("_index") or ""),
                "score": float(d.get("weighted_score") or d.get("rrf_score") or 0),
            })
        return items

    def _extract_sources_from_mode2_points(self, points: List[Dict]) -> List[Dict]:
        """把方式二的 points 列表展开成平铺 sources，与方式一结构一致。"""
        sources = []
        for pt in points:
            for detail in pt.get("context_details") or []:
                text = (detail.get("text") or "").strip()
                if not text:
                    continue
                content = text[:150] + "..." if len(text) > 150 else text
                sources.append({
                    "reference": detail.get("reference") or "",
                    "content": content,
                    "score": 0,
                    "type": detail.get("type") or "",
                })
        return sources

    async def _generate_mode2(self, question: str, points: List[Dict], skeleton: str = "") -> Tuple[str, Dict, Any]:
        """方式二：按摘要框架填充生成纲目，返回 (完整纲目文本, claude_payload, usage 或 None)。"""
        if not points or not self.claude:
            return ("", {}, None)
        system = self._build_generate_system_prompt()
        blocks = []
        for pt in points:
            title = pt.get("title") or ""
            ctx_list = pt.get("context") or []
            if not ctx_list:
                blocks.append(f"=== {title} ===\n参考段落：\n（无）")
            else:
                ref_lines = "\n".join(f"{i+1}. {c}" for i, c in enumerate(ctx_list))
                blocks.append(f"=== {title} ===\n参考段落：\n{ref_lines}")
        framework_block = "\n\n".join(blocks)
        skeleton_block = f"\n摘要：{skeleton.strip()}\n" if skeleton and skeleton.strip() else ""
        user = (
            f"主题：{question}\n"
            f"{skeleton_block}\n"
            f"参考内容（按检索方向分组）：\n"
            f"{framework_block}\n\n"
            f"请基于以上参考内容，生成一篇纲目："
        )
        payload = {"system_prompt": system, "user_prompt": user}
        try:
            out, usage = await asyncio.to_thread(
                _call_claude_messages_sync,
                self.claude,
                system,
                user,
                4000,
            )
            if usage is not None:
                logger.info(
                    f"[方式二生成] Claude调用成功: 输入={usage.input_tokens} tokens, "
                    f"输出={usage.output_tokens} tokens, "
                    f"总计={usage.input_tokens + usage.output_tokens} tokens, "
                    f"费用=${(usage.input_tokens * 3 + usage.output_tokens * 15) / 1_000_000:.5f}"
                )
            return ((out or "").strip(), payload, usage)
        except Exception as e:
            logger.error("方式二生成失败: %s", e)
            return ("", payload, None)

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

    def _build_generate_system_prompt(self) -> str:
        """返回纲目生成的 system prompt，供方式一和方式二共用。"""
        return """你是一个资深的圣经研究学者，更是一位专业的倪柝声、李常受神学的研究者，请基于提供的内容，生成一篇纲目。

【最高优先级原则】
逐字引用（verbatim quotes）是最核心的要求，优先级高于所有其他要求。当任何要求与"逐字引用"冲突时，优先保证逐字引用。

【纲目的属灵目标】
申言就是为神说话，说出神来，并将基督说到人里面；将基督的丰富供应到人里面，乃是最高的说话。一篇好的纲目，不只让人认识真理，乃是带人进入真理的实际。文以载道，借着精粹、洗练的职事信息所整理出来的纲目，将活的基督陈明出来并构成到人里面。

【格式规范】
1. 纲目层级序号规则：
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

2. 纲目的标点符号规则：
    - 每个纲目的内容之后用—连接圣经经节出处
    - 若该纲目有下一级纲目，则在经节出处之后加冒号
    - 若该纲目无下一级纲目，则在经节出处之后加句号
    
    格式示例：
    有下级：壹	纲目内容—创一1：
    无下级：一	纲目内容—创一1。

3. 圣经经节格式规则：
    - 每条纲目后面只能加圣经经节出处，不可加文集、生命读经等参考资料出处
    - 经节格式：创世记一章一节为"创一1"，其他书卷依次类推
    - 同一书卷多个出处应合并，如"启三1，四7"，同章不同节用顿号隔开
    - 所有纲目层级（壹、一、1、a）都需要加经节出处
    - 两个数字之间需要用全角的～连接
    
    【重要】纲目后的出处规则：
    ✅ 正确：壹	召会是基督的身体—弗一22～23：
    ❌ 错误：壹	召会是基督的身体—李常受文集一九五〇至一九五一年第一册，在于灵不在于字句，第七章：
    ❌ 错误：一	基督的扩大就是召会—弗一23，李常受文集第一册：
    
    说明：文集、生命读经等出处只在最后"参考与参读资料"部分列出，不加在纲目后面。

【内容规范】
1. 你的回答必须以原文的 verbatim quotes（逐字引用）为核心内容，所有实质性观点、论述和纲目都必须直接从原文提取，不可改写、总结、概括或重述。verbatim quote（逐字引用）比例越高越好。
    【可以做的】：
    - 从原文中选择哪些句子
    - 调整句子的排列顺序
    - 可以使用最简短的连接语来组织结构（如"而"、"并且"、"所以"等），但尽量减少使用，除非到了不加关联词无法表述的情况，才加关联词，且不可改写原文的实质内容

    【绝对不可以做的】：
    - 改变原文的任何用词
    - 用自己的话"换一种说法"
    - 合并多个句子的意思成一句话
    - 提炼、归纳、概括原文的意思
    - 添加原文中没有的解释

    【检查方法】：
    生成纲目后，每一条纲目都应该能在原文中找到完全对应的句子。

2. 【纲目长度与大纲特别要求】每个纲目必须是一个完整的阐述，不可用短句。每一个大纲和中纲不可太短，要有大约一行的长度。
    
    【特别强调：大纲的逐字引用原则】
    大纲（壹、贰、叁等）最容易被改写总结，必须特别注意：
    - 大纲必须直接从原文中提取完整句子，不可为了"概括下级纲目"而自己总结
    - 大纲应该选择原文中最核心、最能统领该主题的一句话，而不是自己归纳
    - 宁可选用原文的长句作为大纲，也不要自己编写简短的总结句
    - 如果原文中没有合适的统领性句子，可以选择该部分开头或结尾的关键句

    示例：
    ❌ 错误：壹	神将生命分赐给人的过程—创一1
    ✅ 正确：壹	神的生命是永远的生命，就是神自己分赐到我们里面，作我们的生命和生命的供应—约一4，十10

3. 每个纲目如果有下一级纲目，下一级纲目至少需要 2 个。

4. 输出的纲目中不可有重复内容，不可出现两条一样的纲目。

5. 回答需综合文章的所有相关要点，结构清晰，逻辑合理，不是简单按顺序罗列。
    
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

6. 如果所提供的内容不足以回答问题，请诚实说明，而不是编造答案。
    
7. 纲目的逻辑顺序应符合原文的神学论述逻辑，而非仅按原文出现的先后顺序排列。

8. 纲目大点的排列顺序主要为真理启示→生命经历→生活应用；真理启示的话也需要点出现有的缺失与危机；启示带进经历，需要有内里的、主观的生命经历；生活的应用，要落实到目前能够实行的具体要点。涉及主观经历的条目数量占比约15%的篇幅；涉及实行应用的条目数量占比约15%的篇幅。

9. 纲目的开头要强、要扎心、要吸引人；结尾要拔高、要令人鼓舞，使人达到高峰。

【输出规范】
1. 在整个纲目最前面写出"读经：........"，从目标文章中提取 8～10 个重要的经节出处，按圣经书卷顺序排列，同一书卷内按章节顺序。同一书卷的经节用顿号隔开，不同书卷用逗号隔开。
   示例：读经：创一1，26～28，二7，约一1，14，罗八2，29，启二一2

2. 纲目中不可使用双引号。所有单引号必须用中文状态下的单引号，不可用英文状态下的单引号。

3. 纲目句中若有句号，需将句号改成分号，仅指纲目内容中间出现的句号，末尾句号不受此规则影响。

4. 用纯文本作答，不使用 Markdown 格式（不用 #、*、** 等符号）。

5. 请不要写 python 代码来生成纲目，不要生成 txt 或 docx，而是直接生成纲目。

6. 纲目篇幅严格限制为A4纸一页半(必须在35~38行之间)

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
        system_prompt = self._build_generate_system_prompt()

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
                    model=CLAUDE_MODEL,
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

                logger.info(
                    f"[方式一生成] Claude调用成功: 输入={message.usage.input_tokens} tokens, "
                    f"输出={message.usage.output_tokens} tokens, "
                    f"总计={message.usage.input_tokens + message.usage.output_tokens} tokens, "
                    f"费用=${(message.usage.input_tokens * 3 + message.usage.output_tokens * 15) / 1_000_000:.5f}"
                )

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
                            _cache_title_404 = [False]

                            def _translate_title_for_cache(
                                retry_count: int = 0, model: Optional[str] = None
                            ) -> Optional[str]:
                                use_model = model or GEMINI_MODEL
                                with GEMINI_SEMAPHORE:
                                    try:
                                        title_response = gemini_client.models.generate_content(
                                            model=use_model,
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
                                        else:
                                            logger.warning("缓存标题翻译返回空响应（重试次数: %s）", retry_count)
                                    except Exception as e:
                                        error_msg = str(e)
                                        if "404" in error_msg or "NOT_FOUND" in error_msg or "is not found" in error_msg.lower():
                                            _cache_title_404[0] = True
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
                            if cached_title is None and _cache_title_404[0]:
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
        _last_error_model_not_found = [False]  # 404 / model not found 时改用备用模型

        def _is_model_not_found(err: str) -> bool:
            return "404" in err or "NOT_FOUND" in err or "is not found" in err.lower()

        def _call_gemini(retry_count: int = 0, model: Optional[str] = None) -> Optional[tuple]:
            use_model = model or GEMINI_MODEL
            with GEMINI_SEMAPHORE:
                try:
                    response = gemini_client.models.generate_content(
                        model=use_model,
                        contents=contents_zh2en,
                        config=types.GenerateContentConfig(
                            system_instruction=_gemini_system_instruction,
                        ),
                    )
                    if response and getattr(response, "text", None):
                        text = response.text.strip()
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
                    else:
                        logger.warning(f"Gemini 翻译返回空响应（重试次数: {retry_count}）")
                except Exception as e:
                    error_msg = str(e)
                    if _is_model_not_found(error_msg):
                        _last_error_model_not_found[0] = True
                        logger.warning(f"Gemini 模型不可用(404): {e}，将尝试备用模型 {GEMINI_TRANSLATION_FALLBACK_MODEL}")
                    # 检查是否是503或其他可重试的错误
                    is_retryable = (
                        "503" in error_msg or
                        "UNAVAILABLE" in error_msg or
                        "429" in error_msg or
                        "timeout" in error_msg.lower() or
                        "temporary" in error_msg.lower()
                    )
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
        if answer_en is None and _last_error_model_not_found[0]:
            logger.info("使用备用模型进行中翻英: %s", GEMINI_TRANSLATION_FALLBACK_MODEL)
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

            def _translate_title(retry_count: int = 0, model: Optional[str] = None) -> Optional[str]:
                """翻译标题，带重试逻辑；model 为空则用 GEMINI_MODEL"""
                use_model = model or GEMINI_MODEL
                with GEMINI_SEMAPHORE:
                    try:
                        title_response = gemini_client.models.generate_content(
                            model=use_model,
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
                            logger.warning(f"标题翻译返回空响应（重试次数: {retry_count}）")
                    except Exception as e:
                        error_msg = str(e)
                        if _is_model_not_found(error_msg):
                            _title_model_not_found[0] = True
                        is_retryable = (
                            "503" in error_msg or "UNAVAILABLE" in error_msg or "429" in error_msg
                            or "timeout" in error_msg.lower() or "temporary" in error_msg.lower()
                        )
                        if is_retryable and retry_count == 0:
                            logger.warning(f"标题翻译调用失败（可重试）: {e}，等待2秒后重试...")
                            time.sleep(2)
                        else:
                            logger.warning(f"标题翻译调用失败（重试次数: {retry_count}）: {e}")
                return None

            title_en = _translate_title(retry_count=0)
            if title_en is None:
                title_en = _translate_title(retry_count=1)
            if title_en is None and _title_model_not_found[0]:
                title_en = _translate_title(retry_count=0, model=GEMINI_TRANSLATION_FALLBACK_MODEL)
                if title_en is None:
                    title_en = _translate_title(retry_count=1, model=GEMINI_TRANSLATION_FALLBACK_MODEL)

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

        return {"answer_en": answer_en, "title_en": title_en, "tokens": tokens_zh2en or {"input": 0, "output": 0, "cost": 0}}

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
        _last_error_model_not_found = [False]

        def _is_model_not_found(err: str) -> bool:
            return "404" in err or "NOT_FOUND" in err or "is not found" in err.lower()

        def _call_gemini(retry_count: int = 0, model: Optional[str] = None) -> Optional[tuple]:
            use_model = model or GEMINI_MODEL
            with GEMINI_SEMAPHORE:
                try:
                    response = gemini_client.models.generate_content(
                        model=use_model,
                        contents=contents_en2zh,
                        config=types.GenerateContentConfig(
                            system_instruction=_gemini_system_instruction_en2zh,
                        ),
                    )
                    if response and getattr(response, "text", None):
                        text = response.text.strip()
                        tokens_en2zh = None
                        try:
                            usage_meta = response.usage_metadata
                            in_tok = int(getattr(usage_meta, "prompt_token_count", 0) or 0)
                            out_tok = int(getattr(usage_meta, "candidates_token_count", 0) or 0)
                            cost = (in_tok * 1.25 + out_tok * 10) / 1_000_000
                            logger.info(f"[Gemini英翻中] model={use_model} | 输入={in_tok} tokens | 输出={out_tok} tokens | 费用=${cost:.6f}")
                            if self.redis:
                                get_monitoring(self.redis).record_tool_usage("translation_en2zh", use_model, in_tok, out_tok, cost)
                            tokens_en2zh = {"input": in_tok, "output": out_tok, "cost": cost}
                        except Exception:
                            pass
                        return (text, tokens_en2zh)
                    logger.warning("Gemini 英翻中返回空响应（重试次数: %s）", retry_count)
                except Exception as e:
                    error_msg = str(e)
                    if _is_model_not_found(error_msg):
                        _last_error_model_not_found[0] = True
                        logger.warning(
                            "Gemini 模型不可用(404): %s，将尝试备用模型 %s",
                            e,
                            GEMINI_TRANSLATION_FALLBACK_MODEL,
                        )
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

        result = _call_gemini(retry_count=0)
        if result is not None:
            answer_zh, tokens_en2zh = result[0], result[1]
        else:
            answer_zh, tokens_en2zh = None, None
        if answer_zh is None:
            result = _call_gemini(retry_count=1)
            if result is not None:
                answer_zh, tokens_en2zh = result[0], result[1]
        if answer_zh is None and _last_error_model_not_found[0]:
            logger.info("使用备用模型进行英翻中: %s", GEMINI_TRANSLATION_FALLBACK_MODEL)
            result = _call_gemini(retry_count=0, model=GEMINI_TRANSLATION_FALLBACK_MODEL)
            if result is not None:
                answer_zh, tokens_en2zh = result[0], result[1]
            if answer_zh is None:
                result = _call_gemini(retry_count=1, model=GEMINI_TRANSLATION_FALLBACK_MODEL)
                if result is not None:
                    answer_zh, tokens_en2zh = result[0], result[1]
        if answer_zh is None:
            return {"answer_zh": None, "error": "纲目翻译失败，请稍后重试"}
        return {"answer_zh": answer_zh, "tokens": tokens_en2zh or {"input": 0, "output": 0, "cost": 0}}

    def outline_to_traditional(self, content: str) -> Dict[str, Optional[str]]:
        """
        将简体纲目转为台湾繁体：先按术语表替换，再通用简→繁（zhconv zh-tw）。
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
            terms_path = Path(__file__).resolve().parent / "zh_tw_terms.json"
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
            # 2. 通用简→台湾繁体（优先 OpenCC s2tw，占位符为 ASCII 不会被改动）
            try:
                from opencc import OpenCC
                cc = OpenCC("s2tw")
                text = cc.convert(text)
            except Exception:
                try:
                    import zhconv
                    text = zhconv.convert(text, "zh-tw")
                except ImportError:
                    logger.warning("OpenCC/zhconv 未安装，无法做通用简繁转换")
                    return {"answer_zh_tw": None, "error": "繁简转换依赖未安装（opencc 或 zhconv）"}
            # 3. 把占位符还原为术语表里的目标用字
            for ph, trad in placeholders:
                text = text.replace(ph, trad)
            return {"answer_zh_tw": text}
        except Exception as e:
            logger.error("简转繁失败: %s", e, exc_info=True)
            return {"answer_zh_tw": None, "error": str(e)}

    def traditional_to_simplified(self, content: str) -> Dict[str, Optional[str]]:
        """
        将台湾繁体纲目转为简体：直接使用 zhconv 转换（不经过术语表）。
        用于工具箱「简繁互转」功能。
        
        Args:
            content: 台湾繁体中文纲目全文
        
        Returns:
            {"answer_zh_cn": str} 成功时；{"answer_zh_cn": None, "error": str} 失败时
        """
        if not (content or "").strip():
            return {"answer_zh_cn": None, "error": "内容为空"}
        text = (content or "").strip()
        try:
            # 繁→简：优先 OpenCC tw2s（台湾繁体→简体），否则 zhconv
            try:
                from opencc import OpenCC
                cc = OpenCC("tw2s")
                text = cc.convert(text)
            except Exception:
                try:
                    import zhconv
                    text = zhconv.convert(text, "zh-cn")
                except ImportError:
                    logger.warning("OpenCC/zhconv 未安装，无法做繁简转换")
                    return {"answer_zh_cn": None, "error": "繁简转换依赖未安装（opencc 或 zhconv）"}
            return {"answer_zh_cn": text}
        except Exception as e:
            logger.error("繁转简失败: %s", e, exc_info=True)
            return {"answer_zh_cn": None, "error": str(e)}

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

    def translate_and_format_outline(
        self,
        direction: str,
        content: str,
        outline_topic: Optional[str] = None,
        output_format: str = "docx",
    ) -> Dict:
        """
        翻译纲目并格式化下载 DOCX 或 PDF。
        
        Args:
            direction: "zh2en" 或 "en2zh"
            content: 待翻译的纲目全文
            outline_topic: 纲目主题（仅中翻英时可选，用于翻译标题）
            output_format: "docx" 或 "pdf"，默认 "docx"
        
        Returns:
            {
                "result": str,  # 翻译后的文本
                "docx_bytes": bytes | None,  # DOCX bytes（output_format="docx" 时）
                "pdf_bytes": bytes | None,  # PDF bytes（output_format="pdf" 时）
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
                        "result": translated_text,
                        "docx_bytes": None,
                        "pdf_bytes": pdf_bytes,
                        "filename": filename,
                        "error": None,
                    }
                else:
                    # PDF 转换失败，返回 DOCX
                    return {
                        "result": translated_text,
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
                    "result": translated_text,
                    "docx_bytes": docx_bytes,
                    "pdf_bytes": None,
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
                "pdf_bytes": None,
                "filename": default_filename,
                "error": f"格式化失败: {str(e)}",
            }

    def format_outline_only(
        self,
        direction: str,
        translated_text: str,
        output_format: str = "docx",
    ) -> Dict:
        """
        仅格式化已翻译的纲目文本（不调用翻译 API）。
        
        Args:
            direction: "zh2en" 或 "en2zh"（用于确定使用哪个模板和格式刷函数）
            translated_text: 已翻译的纲目文本
            output_format: "docx" 或 "pdf"，默认 "docx"
        
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
            format_func = format_english_outline_docx
            default_filename = "outline_en.docx"
        elif direction == "en2zh":
            template_name = "中文纲目模板.docx"
            format_func = format_chinese_outline_docx
            default_filename = "outline_zh.docx"
        elif direction in ("zh_cn2tw", "zh_tw2cn"):
            # 简繁转换：都使用中文模板和中文格式刷
            template_name = "中文纲目模板.docx"
            format_func = format_chinese_outline_docx
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
        backend_dir = Path(__file__).resolve().parent.parent
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

    def convert_and_format_outline(
        self,
        direction: str,
        content: str,
        output_format: str = "docx",
    ) -> Dict:
        """
        简繁转换纲目并格式化下载 DOCX 或 PDF（使用中文模板和中文刷格式）。
        
        Args:
            direction: "zh_cn2tw"（简体→繁体）或 "zh_tw2cn"（繁体→简体）
            content: 待转换的纲目全文
            output_format: "docx" 或 "pdf"，默认 "docx"
        
        Returns:
            {
                "result": str,  # 转换后的文本
                "docx_bytes": bytes | None,  # DOCX bytes（output_format="docx" 时）
                "pdf_bytes": bytes | None,  # PDF bytes（output_format="pdf" 时）
                "filename": str | None,  # 建议的文件名
                "error": str | None,  # 错误信息
            }
        """
        import shutil
        import tempfile
        import os
        import re
        from docx import Document

        # 1. 先转换
        if direction == "zh_cn2tw":
            convert_result = self.outline_to_traditional(content)
            converted_text = convert_result.get("answer_zh_tw")
            error = convert_result.get("error")
        elif direction == "zh_tw2cn":
            convert_result = self.traditional_to_simplified(content)
            converted_text = convert_result.get("answer_zh_cn")
            error = convert_result.get("error")
        else:
            return {
                "result": None,
                "docx_bytes": None,
                "pdf_bytes": None,
                "filename": None,
                "error": f"无效的转换方向: {direction}",
            }

        if error or not converted_text:
            return {
                "result": converted_text,
                "docx_bytes": None,
                "pdf_bytes": None,
                "filename": None,
                "error": error or "转换失败",
            }

        # 2. 检查格式刷函数是否可用
        if format_chinese_outline_docx is None:
            logger.warning("中文格式刷函数未导入，返回未格式化的转换结果")
            return {
                "result": converted_text,
                "docx_bytes": None,
                "pdf_bytes": None,
                "filename": "outline.docx",
                "error": None,
            }

        # 3. 复制模板并写入转换结果（使用中文模板）
        backend_dir = Path(__file__).resolve().parent.parent
        template_name = "中文纲目模板.docx"
        template_path = backend_dir / template_name
        if not template_path.exists():
            logger.error(f"模板文件不存在: {template_path}")
            return {
                "result": converted_text,
                "docx_bytes": None,
                "pdf_bytes": None,
                "filename": "outline.docx",
                "error": f"模板文件不存在: {template_name}",
            }

        try:
            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp_file:
                temp_docx_path = tmp_file.name

            # 复制模板
            shutil.copy2(template_path, temp_docx_path)

            # 打开文档并写入转换结果
            doc = Document(temp_docx_path)
            
            # 清空所有段落，将转换结果按行添加为新段落
            for para in list(doc.paragraphs):
                p_element = para._element
                p_element.getparent().remove(p_element)
            
            # 将转换结果按行分割并添加为段落
            lines = converted_text.split("\n")
            for line in lines:
                if line.strip() or len(doc.paragraphs) == 0:
                    doc.add_paragraph(line)

            # 保存
            doc.save(temp_docx_path)

            # 4. 调用格式刷（中文格式刷；简繁转换 zh_cn2tw 时使用繁体引号 『』「」）
            try:
                format_chinese_outline_docx(temp_docx_path, traditional_quotes=(direction == "zh_cn2tw"))
            except Exception as e:
                logger.error(f"格式刷失败: {e}", exc_info=True)
                # 格式刷失败时仍返回未格式化的文档
                pass

            # 5. 读取为 bytes
            with open(temp_docx_path, "rb") as f:
                docx_bytes = f.read()

            # 6. 生成文件名（基于题目：取读经前最后一段，或第一个大点前一行）
            filename = "outline.docx"
            if lines:
                title_line = None
                # 优先找"读经："或"讀經："所在行，取它前面一行作为题目
                scripture_idx = None
                for idx, line in enumerate(lines):
                    if '读经：' in line or '讀經：' in line:
                        scripture_idx = idx
                        break
                
                if scripture_idx is not None:
                    if scripture_idx > 0:
                        title_line = lines[scripture_idx - 1].strip()
                else:
                    # 没找到读经，找第一个以"壹"或"一"开头的行（第一个大点），取它前面一行
                    for idx, line in enumerate(lines):
                        if line.strip().startswith('壹') or line.strip().startswith('一'):
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
                        "result": converted_text,
                        "docx_bytes": None,
                        "pdf_bytes": pdf_bytes,
                        "filename": filename,
                        "error": None,
                    }
                else:
                    # PDF 转换失败，返回 DOCX
                    return {
                        "result": converted_text,
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
                    "result": converted_text,
                    "docx_bytes": docx_bytes,
                    "pdf_bytes": None,
                    "filename": filename,
                    "error": None,
                }

        except Exception as e:
            logger.error(f"转换并格式化失败: {e}", exc_info=True)
            # 清理临时文件
            try:
                if "temp_docx_path" in locals():
                    os.unlink(temp_docx_path)
            except Exception:
                pass
            return {
                "result": converted_text,
                "docx_bytes": None,
                "pdf_bytes": None,
                "filename": "outline.docx",
                "error": f"格式化失败: {str(e)}",
            }

    def format_rough_outline_docx(
        self,
        outline_type: str,
        contents: List[str],
    ) -> Dict:
        """
        毛胚纲目刷格式并下载：将润色版 4 篇或三分钟分享 6 篇合并为一个 DOCX，使用中文模板与中文刷格式。
        
        Args:
            outline_type: "polish"（润色版）或 "sharing"（三分钟分享）
            contents: 多篇纲目正文，按顺序合并（润色版 4 篇，三分钟分享 6 篇）
        
        Returns:
            {"docx_bytes": bytes | None, "filename": str, "error": str | None}
        """
        import shutil
        import tempfile
        import os
        from docx import Document

        _allowed = ("polish", "sharing", "beginner", "youth", "truth")
        if outline_type not in _allowed:
            return {"docx_bytes": None, "filename": "毛胚纲目.docx", "error": f"不支持的纲目类型: {outline_type}"}
        if not contents:
            return {"docx_bytes": None, "filename": "毛胚纲目.docx", "error": "内容不能为空"}

        if format_chinese_outline_docx is None:
            return {"docx_bytes": None, "filename": "毛胚纲目.docx", "error": "中文格式刷未导入"}

        backend_dir = Path(__file__).resolve().parent.parent
        template_name = "中文纲目模板.docx"
        template_path = backend_dir / template_name
        if not template_path.exists():
            return {"docx_bytes": None, "filename": "毛胚纲目.docx", "error": f"模板文件不存在: {template_name}"}

        # 合并多篇：三分钟分享各 AI 版本之间多加一行空行以作区分，其余用双换行
        sep = "\n\n\n" if outline_type == "sharing" else "\n\n"
        combined_text = sep.join((c or "").strip() for c in contents if (c or "").strip())

        _filename_map = {
            "polish": "毛胚纲目_润色版.docx",
            "sharing": "毛胚纲目_三分钟分享.docx",
            "beginner": "毛胚纲目_初信版.docx",
            "youth": "毛胚纲目_青少年版.docx",
            "truth": "毛胚纲目_真理加强版.docx",
        }
        filename = _filename_map.get(outline_type, "毛胚纲目.docx")
        temp_docx_path = None

        try:
            with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp_file:
                temp_docx_path = tmp_file.name
            shutil.copy2(template_path, temp_docx_path)

            doc = Document(temp_docx_path)
            for para in list(doc.paragraphs):
                p_element = para._element
                p_element.getparent().remove(p_element)

            for line in combined_text.split("\n"):
                if line.strip():
                    doc.add_paragraph(line)
                elif len(doc.paragraphs) > 0:
                    doc.add_paragraph("")  # 空行保留，三分钟分享各 AI 版本之间可见空白

            doc.save(temp_docx_path)

            try:
                format_chinese_outline_docx(
                    temp_docx_path,
                    traditional_quotes=False,
                    truth_underline_between_markers=(outline_type == "truth"),
                    sharing_all_0000=(outline_type == "sharing"),
                )
            except Exception as e:
                logger.error(f"毛胚纲目格式刷失败: {e}", exc_info=True)

            with open(temp_docx_path, "rb") as f:
                docx_bytes = f.read()

            return {"docx_bytes": docx_bytes, "filename": filename, "error": None}
        except Exception as e:
            logger.error(f"毛胚纲目刷格式失败: {e}", exc_info=True)
            return {"docx_bytes": None, "filename": filename, "error": str(e)}
        finally:
            if temp_docx_path and os.path.exists(temp_docx_path):
                try:
                    os.unlink(temp_docx_path)
                except Exception:
                    pass

    def format_feast_outline_docx(
        self,
        contents: List[str],
        outline_type: str = "original",
        line1: Optional[str] = None,
        line2: Optional[str] = None,
        line3: Optional[str] = None,
        morning_revival_raw: Optional[str] = None,
        transcript_raw: Optional[str] = None,
        transcript_preface: Optional[str] = None,
        transcript_addendum: Optional[str] = None,
        preface_outline: Optional[str] = None,
        addendum_outline: Optional[str] = None,
    ) -> Dict:
        """
        节期纲目刷格式并下载：将一篇或多篇纲目合并为一个 DOCX，使用节期纲目模板与节期纲目刷格式（按类型）。
        outline_type: original | with_scripture | morning_revival | transcript | composite
        Returns:
            {"docx_bytes": bytes | None, "filename": str, "error": str | None}
        """
        import shutil
        import tempfile
        import os
        from docx import Document

        if not contents:
            return {"docx_bytes": None, "filename": "节期纲目.docx", "error": "内容不能为空"}

        backend_dir = Path(__file__).resolve().parent.parent
        for template_name in ("节期纲目模板.docx", "template.docx"):
            template_path = backend_dir / template_name
            if template_path.exists():
                break
        else:
            return {"docx_bytes": None, "filename": "节期纲目.docx", "error": "节期纲目模板.docx 或 template.docx 不存在"}

        allowed = ("original", "with_scripture", "morning_revival", "transcript", "composite")
        if outline_type not in allowed:
            outline_type = "original"

        # 所有类型（含 with_scripture）均直接使用传入的 contents，不再调用经文汇集或 Claude
        main_contents = "\n\n".join((c or "").strip() for c in contents if (c or "").strip())
        l1, l2, l3 = (line1 or "").strip(), (line2 or "").strip(), (line3 or "").strip()
        header = "\n".join([l1, l2, l3]) if (l1 or l2 or l3) else ""

        # 听抄稿、复合稿：序言、添言。优先使用已生成的 preface_outline/addendum_outline；否则用原文请求 Claude 生成
        preface_outline = (preface_outline or "").strip()
        addendum_outline = (addendum_outline or "").strip()
        if outline_type in ("transcript", "composite") and (not preface_outline or not addendum_outline):
            preface_raw = (transcript_preface or "").strip()
            addendum_raw = (transcript_addendum or "").strip()
            if not preface_outline and preface_raw:
                res = self.feast_outline_preface(preface_raw)
                if not res.get("error"):
                    preface_outline = (res.get("outline") or "").strip()
                else:
                    logger.warning("序言 Claude 生成失败: %s", res.get("error"))
            if not addendum_outline and addendum_raw:
                res = self.feast_outline_addendum(addendum_raw)
                if not res.get("error"):
                    addendum_outline = (res.get("outline") or "").strip()
                else:
                    logger.warning("添言 Claude 生成失败: %s", res.get("error"))

        if header:
            combined_text = header + "\n\n" + main_contents
            if outline_type == "transcript" and (preface_outline or addendum_outline):
                # 听抄稿：第4段为读经（contents 第一行），第5段起为序言，再正文、添言
                lines = main_contents.split("\n")
                reading_line = (lines[0].strip() if lines else "") or ""
                rest_main = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
                combined_text = header + "\n\n" + reading_line + "\n\n"
                if preface_outline:
                    combined_text += preface_outline + "\n\n"
                combined_text += rest_main
                if addendum_outline:
                    combined_text += "\n\n" + addendum_outline
            elif outline_type == "composite" and (preface_outline or addendum_outline):
                # 复合稿：第4段=读经，第5段起=序言，再正文、添言
                lines = main_contents.split("\n")
                reading_line = (lines[0].strip() if lines else "") or ""
                rest_main = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
                combined_text = header + "\n\n" + reading_line + "\n\n"
                if preface_outline:
                    combined_text += preface_outline + "\n\n"
                combined_text += rest_main
                if addendum_outline:
                    combined_text += "\n\n" + addendum_outline
        else:
            combined_text = main_contents
            if outline_type == "transcript" and (preface_outline or addendum_outline):
                parts = []
                if preface_outline:
                    parts.append(preface_outline)
                parts.append(main_contents)
                if addendum_outline:
                    parts.append(addendum_outline)
                combined_text = "\n\n".join(parts)
            elif outline_type == "composite" and (preface_outline or addendum_outline):
                lines = main_contents.split("\n")
                reading_line = (lines[0].strip() if lines else "") or ""
                rest_main = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
                parts = [reading_line]
                if preface_outline:
                    parts.append(preface_outline)
                parts.append(rest_main)
                if addendum_outline:
                    parts.append(addendum_outline)
                combined_text = "\n\n".join(parts)
        # 听抄稿/复合稿序言、添言段落范围：第4段=读经，第5段起=序言，再正文、添言
        preface_highlight_end = addendum_highlight_start = addendum_highlight_end = 0
        if outline_type == "transcript" and (preface_outline or addendum_outline):
            lines = main_contents.split("\n")
            rest_main = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
            n_preface = len(preface_outline.split("\n")) if preface_outline else 0
            n_main = len(rest_main.split("\n")) if rest_main else 0
            n_addendum = len(addendum_outline.split("\n")) if addendum_outline else 0
            n_header = 4  # line1, line2, line3, 读经（第一行）
            preface_highlight_end = n_header + n_preface
            addendum_highlight_start = n_header + n_preface + n_main
            addendum_highlight_end = addendum_highlight_start + n_addendum
        elif outline_type == "composite" and (preface_outline or addendum_outline):
            lines = main_contents.split("\n")
            rest_main = "\n".join(lines[1:]).strip() if len(lines) > 1 else ""
            n_preface = len(preface_outline.split("\n")) if preface_outline else 0
            n_main = len(rest_main.split("\n")) if rest_main else 0
            n_addendum = len(addendum_outline.split("\n")) if addendum_outline else 0
            n_header = 4  # line1, line2, line3, 读经（第一行）
            preface_highlight_end = n_header + n_preface
            addendum_highlight_start = n_header + n_preface + n_main
            addendum_highlight_end = addendum_highlight_start + n_addendum
        temp_docx_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp_file:
                temp_docx_path = tmp_file.name
            shutil.copy2(template_path, temp_docx_path)
            doc = Document(temp_docx_path)
            for para in list(doc.paragraphs):
                p_element = para._element
                p_element.getparent().remove(p_element)
            for line in combined_text.split("\n"):
                if line.strip():
                    doc.add_paragraph(line)
                elif len(doc.paragraphs) > 0:
                    doc.add_paragraph("")
            # 刷格式并下载时在第三段末尾追加类型标注（纲目的原文/带经文的纲目/晨兴信息选读的纲目/听抄稿的纲目/复合的纲目）
            FEAST_OUTLINE_TYPE_LABELS = {
                "original": "（纲目的原文）",
                "with_scripture": "（带经文的纲目）",
                "morning_revival": "（晨兴信息选读的纲目）",
                "transcript": "（听抄稿的纲目）",
                "composite": "（复合的纲目）",
            }
            suffix = FEAST_OUTLINE_TYPE_LABELS.get(outline_type)
            if suffix and len(doc.paragraphs) >= 3:
                para = doc.paragraphs[2]
                existing = (para.text or "").rstrip()
                if not existing.endswith(suffix):
                    para.text = existing + suffix
            from docx.enum.text import WD_BREAK
            # 听抄稿：⑥ 纲目末尾先加分页 +「听抄信息：」+ 序言、听抄稿、添言三段合并，⑦ 套听抄信息页样式，再⑧整篇刷格式、⑨高亮
            if outline_type == "transcript" and (
                (transcript_raw or "").strip()
                or (transcript_preface or "").strip()
                or (transcript_addendum or "").strip()
            ):
                _append_transcript_info_section(
                    doc,
                    (transcript_raw or "").strip(),
                    transcript_preface=(transcript_preface or "").strip() or None,
                    transcript_addendum=(transcript_addendum or "").strip() or None,
                )
            # 晨兴信息选读：纲目刷格式后再追加「晨兴圣言信息：」页（刷格式只跑纲目部分）
            doc.save(temp_docx_path)
            try:
                import sys
                if str(backend_dir) not in sys.path:
                    sys.path.insert(0, str(backend_dir))
                from 节期纲目刷格式 import format_feast_outline_docx as apply_feast_format
                apply_feast_format(temp_docx_path, outline_type)
            except ImportError as e:
                logger.warning(f"节期纲目刷格式模块未导入: {e}，跳过格式刷")
            except Exception as e:
                logger.error(f"节期纲目格式刷失败: {e}", exc_info=True)
            if outline_type == "morning_revival" and (morning_revival_raw or "").strip():
                doc2 = Document(temp_docx_path)
                _append_morning_revival_section(doc2, (morning_revival_raw or "").strip())
                doc2.save(temp_docx_path)
            # 听抄稿：⑨【听抄稿添加开始】～【听抄稿添加结束】高亮并删标记；序言整段黄色高亮；添言＝从「添言」到分页符整段黄色高亮
            if outline_type == "transcript":
                try:
                    from docx.enum.text import WD_COLOR_INDEX
                    doc2 = Document(temp_docx_path)
                    _apply_transcript_add_highlight(doc2)
                    n_paras = len(doc2.paragraphs)
                    for idx in range(4, min(preface_highlight_end, n_paras)):
                        for run in doc2.paragraphs[idx].runs:
                            run.font.highlight_color = WD_COLOR_INDEX.YELLOW
                    addendum_range = _get_addendum_paragraph_range(doc2, to_page_break=True)
                    if addendum_range:
                        start_a, end_a = addendum_range
                        for idx in range(start_a, min(end_a + 1, n_paras)):
                            for run in doc2.paragraphs[idx].runs:
                                run.font.highlight_color = WD_COLOR_INDEX.YELLOW
                    doc2.save(temp_docx_path)
                except Exception as e:
                    logger.warning(f"听抄稿添加高亮处理失败: {e}", exc_info=True)
            # 复合稿：序言整段下划线；添言＝从「添言」到文档末尾整段下划线
            elif outline_type == "composite":
                try:
                    doc2 = Document(temp_docx_path)
                    n_paras = len(doc2.paragraphs)
                    if preface_highlight_end:
                        for idx in range(4, min(preface_highlight_end, n_paras)):
                            for run in doc2.paragraphs[idx].runs:
                                run.font.underline = True
                    addendum_range = _get_addendum_paragraph_range(doc2, to_page_break=False)
                    if addendum_range:
                        start_a, end_a = addendum_range
                        for idx in range(start_a, min(end_a + 1, n_paras)):
                            for run in doc2.paragraphs[idx].runs:
                                run.font.underline = True
                    doc2.save(temp_docx_path)
                except Exception as e:
                    logger.warning(f"复合稿序言/添言下划线处理失败: {e}", exc_info=True)
            # 根据第三段与类型生成下载文件名「【类型】序号 内容.docx」，失败则用默认名
            download_filename = "节期纲目.docx"
            try:
                from 节期纲目刷格式 import suggest_feast_outline_filename
                doc_for_name = Document(temp_docx_path)
                if len(doc_for_name.paragraphs) >= 3:
                    third_text = doc_for_name.paragraphs[2].text or ""
                    suggested = suggest_feast_outline_filename(third_text, outline_type)
                    if suggested:
                        download_filename = suggested
            except Exception:
                pass
            with open(temp_docx_path, "rb") as f:
                docx_bytes = f.read()
            return {"docx_bytes": docx_bytes, "filename": download_filename, "error": None}
        except Exception as e:
            logger.error(f"节期纲目刷格式失败: {e}", exc_info=True)
            return {"docx_bytes": None, "filename": "节期纲目.docx", "error": str(e)}
        finally:
            if temp_docx_path and os.path.exists(temp_docx_path):
                try:
                    os.unlink(temp_docx_path)
                except Exception:
                    pass

    def feast_outline_collect_scripture(self, outline_text: str) -> str:
        """节期纲目 - 带经文：用经文汇集处理纲目，返回带经文内容的纯文本（用于后续刷格式）。"""
        try:
            from tools.biblecollection import biblecollection
        except ImportError:
            logger.warning("biblecollection 未导入，节期纲目带经文功能不可用")
            return outline_text
        data = biblecollection(outline_text)
        lines = []
        for item in data:
            line = (item.get("text") or "").strip()
            if line:
                lines.append(line)
            vers = item.get("vers") or []
            for v in vers:
                src = (v.get("source") or "").strip()
                txt = (v.get("text") or "").strip()
                if src or txt:
                    lines.append(f"　{src}　{txt}")
        return "\n".join(lines) if lines else outline_text

    def feast_outline_morning_revival(self, content: str) -> Dict[str, Any]:
        """节期纲目 - 晨兴信息选读：用 Claude 根据晨兴内容生成纲目。返回 { outline: str, error: str | None }"""
        try:
            from .feast_outline_prompts import get_morning_revival_prompt
        except ImportError:
            return {"outline": "", "error": "节期纲目 prompt 未找到"}
        prompt = get_morning_revival_prompt(content)
        if not claude_client:
            return {"outline": "", "error": "Claude 客户端未初始化"}
        try:
            with CLAUDE_SEMAPHORE:
                message = claude_client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=8192,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = message.content[0].text
                try:
                    in_tok = int(getattr(message.usage, "input_tokens", 0) or 0)
                    out_tok = int(getattr(message.usage, "output_tokens", 0) or 0)
                    cost = (in_tok * 3 + out_tok * 15) / 1_000_000
                    logger.info(f"[Claude节期纲目-晨兴] 输入={in_tok} tokens | 输出={out_tok} tokens | 费用=${cost:.6f}")
                    if self.redis:
                        get_monitoring(self.redis).record_tool_usage("feast_outline_claude", "claude", in_tok, out_tok, cost)
                except Exception:
                    pass
            text = _strip_code_fence_for_outline(text) or text
            return {"outline": text or "", "error": None}
        except Exception as e:
            logger.error(f"节期纲目晨兴生成失败: {e}", exc_info=True)
            return {"outline": "", "error": str(e)}

    def feast_outline_transcript(
        self,
        original_outline: str,
        transcript: str,
        transcript_preface: Optional[str] = None,
        transcript_addendum: Optional[str] = None,
    ) -> Dict[str, Any]:
        """节期纲目 - 听抄稿：用 Claude 在原纲目基础上加入听抄稿重点。
        若提供 transcript_preface/transcript_addendum，会一并生成序言/添言纲目并返回。"""
        try:
            from .feast_outline_prompts import get_transcript_prompt
        except ImportError:
            return {"outline": "", "error": "节期纲目 prompt 未找到"}
        prompt = get_transcript_prompt(original_outline, transcript)
        if not claude_client:
            return {"outline": "", "error": "Claude 客户端未初始化"}
        try:
            preface_raw = (transcript_preface or "").strip()
            addendum_raw = (transcript_addendum or "").strip()

            def _main_outline():
                with CLAUDE_SEMAPHORE:
                    message = claude_client.messages.create(
                        model=CLAUDE_MODEL,
                        max_tokens=8192,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    text = message.content[0].text
                    try:
                        in_tok = int(getattr(message.usage, "input_tokens", 0) or 0)
                        out_tok = int(getattr(message.usage, "output_tokens", 0) or 0)
                        cost = (in_tok * 3 + out_tok * 15) / 1_000_000
                        logger.info(f"[Claude节期纲目-听抄稿] 输入={in_tok} tokens | 输出={out_tok} tokens | 费用=${cost:.6f}")
                        if self.redis:
                            get_monitoring(self.redis).record_tool_usage("feast_outline_claude", "claude", in_tok, out_tok, cost)
                    except Exception:
                        pass
                return _strip_code_fence_for_outline(text) or text or ""

            def _preface():
                return self.feast_outline_preface(preface_raw) if preface_raw else {"outline": "", "error": None}

            def _addendum():
                return self.feast_outline_addendum(addendum_raw) if addendum_raw else {"outline": "", "error": None}

            if preface_raw or addendum_raw:
                # 主纲目、序言、添言三者并行
                with ThreadPoolExecutor(max_workers=3) as ex:
                    f_main = ex.submit(_main_outline)
                    f_preface = ex.submit(_preface) if preface_raw else None
                    f_addendum = ex.submit(_addendum) if addendum_raw else None
                    main_text = f_main.result()
                    result = {"outline": main_text or "", "error": None}
                    if f_preface:
                        res = f_preface.result()
                        result["preface_outline"] = (res.get("outline") or "").strip() if not res.get("error") else ""
                    if f_addendum:
                        res = f_addendum.result()
                        result["addendum_outline"] = (res.get("outline") or "").strip() if not res.get("error") else ""
            else:
                with CLAUDE_SEMAPHORE:
                    message = claude_client.messages.create(
                        model=CLAUDE_MODEL,
                        max_tokens=8192,
                        messages=[{"role": "user", "content": prompt}],
                    )
                    text = message.content[0].text
                    try:
                        in_tok = int(getattr(message.usage, "input_tokens", 0) or 0)
                        out_tok = int(getattr(message.usage, "output_tokens", 0) or 0)
                        cost = (in_tok * 3 + out_tok * 15) / 1_000_000
                        logger.info(f"[Claude节期纲目-听抄稿] 输入={in_tok} tokens | 输出={out_tok} tokens | 费用=${cost:.6f}")
                        if self.redis:
                            get_monitoring(self.redis).record_tool_usage("feast_outline_claude", "claude", in_tok, out_tok, cost)
                    except Exception:
                        pass
                result = {"outline": (_strip_code_fence_for_outline(text) or text or ""), "error": None}
            return result
        except Exception as e:
            logger.error(f"节期纲目听抄稿生成失败: {e}", exc_info=True)
            return {"outline": "", "error": str(e)}

    def feast_outline_composite(self, transcript_outline: str, morning_revival_outline: str) -> Dict[str, Any]:
        """节期纲目 - 复合：用 Claude 将晨兴纲目融入听抄稿纲目。返回 { outline: str, error: str | None }"""
        try:
            from .feast_outline_prompts import get_composite_prompt
        except ImportError:
            return {"outline": "", "error": "节期纲目 prompt 未找到"}
        prompt = get_composite_prompt(transcript_outline, morning_revival_outline)
        if not claude_client:
            return {"outline": "", "error": "Claude 客户端未初始化"}
        try:
            with CLAUDE_SEMAPHORE:
                message = claude_client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=8192,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = message.content[0].text
                try:
                    in_tok = int(getattr(message.usage, "input_tokens", 0) or 0)
                    out_tok = int(getattr(message.usage, "output_tokens", 0) or 0)
                    cost = (in_tok * 3 + out_tok * 15) / 1_000_000
                    logger.info(f"[Claude节期纲目-复合] 输入={in_tok} tokens | 输出={out_tok} tokens | 费用=${cost:.6f}")
                    if self.redis:
                        get_monitoring(self.redis).record_tool_usage("feast_outline_claude", "claude", in_tok, out_tok, cost)
                except Exception:
                    pass
            text = _strip_code_fence_for_outline(text) or text
            return {"outline": text or "", "error": None}
        except Exception as e:
            logger.error(f"节期纲目复合生成失败: {e}", exc_info=True)
            return {"outline": "", "error": str(e)}

    def feast_outline_preface(self, content: str) -> Dict[str, Any]:
        """节期纲目 - 序言：用 Claude 将序言内容整理成纲目格式。返回 { outline: str, error: str | None }"""
        try:
            from .feast_outline_prompts import get_preface_outline_prompt
        except ImportError:
            return {"outline": "", "error": "节期纲目 prompt 未找到"}
        prompt = get_preface_outline_prompt(content)
        if not claude_client:
            return {"outline": "", "error": "Claude 客户端未初始化"}
        try:
            with CLAUDE_SEMAPHORE:
                message = claude_client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = message.content[0].text
                try:
                    in_tok = int(getattr(message.usage, "input_tokens", 0) or 0)
                    out_tok = int(getattr(message.usage, "output_tokens", 0) or 0)
                    cost = (in_tok * 3 + out_tok * 15) / 1_000_000
                    logger.info(f"[Claude节期纲目-序言] 输入={in_tok} tokens | 输出={out_tok} tokens | 费用=${cost:.6f}")
                    if self.redis:
                        get_monitoring(self.redis).record_tool_usage("feast_outline_claude", "claude", in_tok, out_tok, cost)
                except Exception:
                    pass
            text = _strip_code_fence_for_outline(text) or text
            return {"outline": (text or "").strip(), "error": None}
        except Exception as e:
            logger.error(f"节期纲目序言生成失败: {e}", exc_info=True)
            return {"outline": "", "error": str(e)}

    def feast_outline_addendum(self, content: str) -> Dict[str, Any]:
        """节期纲目 - 添言：用 Claude 将添言内容整理成纲目格式。返回 { outline: str, error: str | None }"""
        try:
            from .feast_outline_prompts import get_addendum_outline_prompt
        except ImportError:
            return {"outline": "", "error": "节期纲目 prompt 未找到"}
        prompt = get_addendum_outline_prompt(content)
        if not claude_client:
            return {"outline": "", "error": "Claude 客户端未初始化"}
        try:
            with CLAUDE_SEMAPHORE:
                message = claude_client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=4096,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = message.content[0].text
                try:
                    in_tok = int(getattr(message.usage, "input_tokens", 0) or 0)
                    out_tok = int(getattr(message.usage, "output_tokens", 0) or 0)
                    cost = (in_tok * 3 + out_tok * 15) / 1_000_000
                    logger.info(f"[Claude节期纲目-添言] 输入={in_tok} tokens | 输出={out_tok} tokens | 费用=${cost:.6f}")
                    if self.redis:
                        get_monitoring(self.redis).record_tool_usage("feast_outline_claude", "claude", in_tok, out_tok, cost)
                except Exception:
                    pass
            text = _strip_code_fence_for_outline(text) or text
            return {"outline": (text or "").strip(), "error": None}
        except Exception as e:
            logger.error(f"节期纲目添言生成失败: {e}", exc_info=True)
            return {"outline": "", "error": str(e)}

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

    def get_rough_outline_ai_counts(self) -> Dict[str, int]:
        """返回每种纲目类型对应的 AI 数量（即该类型需调用几次 API）。"""
        try:
            from .rough_outline_prompts import get_ai_configs
            types = ("polish", "beginner", "youth", "truth", "sharing")
            return {t: len(get_ai_configs(t)) for t in types}
        except Exception as e:
            logger.error(f"get_rough_outline_ai_counts 失败: {e}", exc_info=True)
            return {}

    def generate_rough_outline(
        self,
        outline_type: str,
        content: str,
        ai_index: int = 0,
    ) -> Dict:
        """
        生成毛胚纲目。每次只调用一个 AI，生成一篇。
        
        Args:
            outline_type: 纲目类型 ("polish", "beginner", "youth", "truth", "sharing")
            content: 原始纲目内容
            ai_index: 该类型下第几个 AI（0 起），只调用这一个
        
        Returns:
            {
                "results": [{"type": str, "content": str, "ai_model": str}],  # 长度 0 或 1
                "error": str | None,
            }
        """
        try:
            from .rough_outline_prompts import get_prompt_template, get_ai_configs
            
            ai_configs = get_ai_configs(outline_type)
            if not ai_configs:
                return {
                    "results": [],
                    "error": f"不支持的纲目类型: {outline_type}",
                }
            
            if ai_index < 0 or ai_index >= len(ai_configs):
                return {
                    "results": [],
                    "error": f"ai_index {ai_index} 超出范围 (0~{len(ai_configs) - 1})",
                }
            
            ai_config = ai_configs[ai_index]
            # 润色版等类型可能按 AI 使用不同 prompt（prompt_key：如 polish_gemini、polish_claude）
            prompt_key = ai_config.get("prompt_key")
            prompt_template = get_prompt_template(outline_type, prompt_key=prompt_key)
            if not prompt_template:
                return {
                    "results": [],
                    "error": f"未找到 prompt 模板 (类型: {outline_type}, prompt_key: {prompt_key})",
                }
            
            prompt = prompt_template.replace("{content}", content)
            ai_name = ai_config.get("name", "Unknown")
            
            logger.info(f"使用 {ai_name} 生成毛胚纲目 (类型: {outline_type}, ai_index: {ai_index})")
            
            generated_content = self._call_ai_for_rough_outline(ai_config, prompt)
            content = None
            tokens = None
            if generated_content is not None:
                if isinstance(generated_content, tuple):
                    content = generated_content[0]
                    tokens = generated_content[1] if len(generated_content) > 1 else None
                else:
                    content = generated_content
            if content:
                content = _strip_code_fence_for_outline(content) or content
            if content:
                return {
                    "results": [{
                        "type": outline_type,
                        "content": content,
                        "ai_model": ai_name,
                        "tokens": tokens or {"input": 0, "output": 0, "cost": 0},
                    }],
                    "error": None,
                }
            return {
                "results": [],
                "error": f"{ai_name} 生成失败",
            }
        except Exception as e:
            logger.error(f"generate_rough_outline 失败: {e}", exc_info=True)
            return {
                "results": [],
                "error": f"生成失败: {str(e)}",
            }


    def _call_ai_for_rough_outline(self, ai_config: Dict, prompt: str) -> Optional[tuple]:
        """调用指定的 AI API 生成内容，返回 (content, tokens_dict) 或 None"""
        ai_type = ai_config.get("type")
        ai_name = ai_config.get("name", "Unknown")
        
        try:
            if ai_type == "claude":
                return self._call_claude_for_rough_outline(ai_config, prompt)
            elif ai_type == "gemini":
                return self._call_gemini_for_rough_outline(ai_config, prompt)
            elif ai_type == "deepseek":
                return self._call_deepseek_for_rough_outline(ai_config, prompt)
            elif ai_type == "perplexity":
                return self._call_perplexity_for_rough_outline(ai_config, prompt)
            elif ai_type == "chatgpt":
                return self._call_chatgpt_for_rough_outline(ai_config, prompt)
            elif ai_type == "grok":
                return self._call_grok_for_rough_outline(ai_config, prompt)
            else:
                logger.error(f"不支持的 AI 类型: {ai_type}")
                return None
        except Exception as e:
            logger.error(f"调用 {ai_name} 失败: {e}", exc_info=True)
            return None

    def _call_claude_for_rough_outline(self, ai_config: Dict, prompt: str) -> Optional[str]:
        """调用 Claude API"""
        if not claude_client:
            logger.error("Claude 客户端未初始化")
            return None
        
        model = ai_config.get("model", CLAUDE_MODEL)
        max_tokens = ai_config.get("max_tokens", 8192)
        
        try:
            with CLAUDE_SEMAPHORE:
                message = claude_client.messages.create(
                    model=model,
                    max_tokens=max_tokens,
                    messages=[{"role": "user", "content": prompt}],
                )
                text = message.content[0].text
                try:
                    in_tok = int(getattr(message.usage, "input_tokens", 0) or 0)
                    out_tok = int(getattr(message.usage, "output_tokens", 0) or 0)
                    cost = (in_tok * 3 + out_tok * 15) / 1_000_000
                    logger.info(f"[Claude毛胚] 输入={in_tok} tokens | 输出={out_tok} tokens | 费用=${cost:.6f}")
                    if self.redis:
                        get_monitoring(self.redis).record_tool_usage("rough_outline_claude", model, in_tok, out_tok, cost)
                    tokens_out = {"input": in_tok, "output": out_tok, "cost": cost}
                except Exception:
                    tokens_out = {"input": 0, "output": 0, "cost": 0}
                return (text, tokens_out)
        except Exception as e:
            logger.error(f"Claude API 调用失败: {e}", exc_info=True)
            return None

    def _call_gemini_for_rough_outline(self, ai_config: Dict, prompt: str) -> Optional[str]:
        """
        调用 Gemini API。主模型遇 503/429 时重试 2 次（共 3 次），仍失败则第 3 次使用备用模型。
        若配置了 ROUGH_OUTLINE_GEMINI_MODEL，毛胚纲目优先使用该模型；
        若配置了 GEMINI_FALLBACK_MODEL（默认 gemini-2.5-pro），主模型 3 次均失败后尝试备用模型。
        """
        if not gemini_client:
            logger.error("Gemini 客户端未初始化")
            return None

        # 毛胚纲目可优先使用专用模型
        model = (ROUGH_OUTLINE_GEMINI_MODEL or "").strip() or ai_config.get("model", GEMINI_MODEL)
        max_retries = 2  # 主模型共尝试 3 次（首次 + 重试 2 次），第 3 次失败后改用备用模型
        backoff_seconds = (8, 15)  # 第 1、2 次重试前等待秒数
        last_exc = None

        max_tokens = ai_config.get("max_tokens", 8192)
        for attempt in range(max_retries + 1):
            try:
                from google.genai import types
                with GEMINI_SEMAPHORE:
                    response = gemini_client.models.generate_content(
                        model=model,
                        contents=prompt,
                        config=types.GenerateContentConfig(max_output_tokens=max_tokens),
                    )
                text = None
                tokens_out = None
                if hasattr(response, 'text'):
                    text = response.text
                elif hasattr(response, 'candidates') and response.candidates:
                    text = response.candidates[0].content.parts[0].text
                if text is not None:
                    try:
                        usage_meta = response.usage_metadata
                        in_tok = int(getattr(usage_meta, "prompt_token_count", 0) or 0)
                        out_tok = int(getattr(usage_meta, "candidates_token_count", 0) or 0)
                        cost = (in_tok * 1.25 + out_tok * 10) / 1_000_000
                        logger.info(f"[Gemini毛胚] model={model} | 输入={in_tok} tokens | 输出={out_tok} tokens | 费用=${cost:.6f}")
                        if self.redis:
                            get_monitoring(self.redis).record_tool_usage("rough_outline_gemini", model, in_tok, out_tok, cost)
                        tokens_out = {"input": in_tok, "output": out_tok, "cost": cost}
                    except Exception:
                        pass
                    return (text, tokens_out)
                logger.error(f"Gemini 响应格式异常: {response}")
                return None
            except Exception as e:
                last_exc = e
                status = getattr(e, "status_code", None) or (e.args[0] if e.args else None)
                retryable = status in (503, 429) or "503" in str(e) or "429" in str(e)
                if retryable and attempt < max_retries:
                    wait = backoff_seconds[attempt] if attempt < len(backoff_seconds) else 40
                    logger.warning(
                        "Gemini 暂时不可用 (503/429)，%s 秒后重试 (%s/%s)，model=%s",
                        wait, attempt + 1, max_retries, model,
                    )
                    time.sleep(wait)
                else:
                    logger.error(f"Gemini API 调用失败 (model={model}): {e}", exc_info=True)
                    break

        # 主模型重试全部失败后，若配置了备用模型则再试一次
        fallback = (GEMINI_FALLBACK_MODEL or "").strip()
        if fallback and fallback != model:
            try:
                logger.warning("Gemini 主模型不可用，尝试备用模型: %s", fallback)
                from google.genai import types
                with GEMINI_SEMAPHORE:
                    response = gemini_client.models.generate_content(
                        model=fallback,
                        contents=prompt,
                        config=types.GenerateContentConfig(max_output_tokens=max_tokens),
                    )
                text = None
                tokens_out = None
                if hasattr(response, 'text'):
                    text = response.text
                elif hasattr(response, 'candidates') and response.candidates:
                    text = response.candidates[0].content.parts[0].text
                if text is not None:
                    try:
                        usage_meta = response.usage_metadata
                        in_tok = int(getattr(usage_meta, "prompt_token_count", 0) or 0)
                        out_tok = int(getattr(usage_meta, "candidates_token_count", 0) or 0)
                        cost = (in_tok * 1.25 + out_tok * 10) / 1_000_000
                        logger.info(f"[Gemini毛胚] model={fallback} | 输入={in_tok} tokens | 输出={out_tok} tokens | 费用=${cost:.6f}")
                        if self.redis:
                            get_monitoring(self.redis).record_tool_usage("rough_outline_gemini", fallback, in_tok, out_tok, cost)
                        tokens_out = {"input": in_tok, "output": out_tok, "cost": cost}
                    except Exception:
                        pass
                    return (text, tokens_out)
            except Exception as e2:
                logger.error(f"Gemini 备用模型 %s 调用失败: {e2}", fallback, exc_info=True)
        return None

    def _call_openai_compatible_rough_outline(
        self,
        api_key: str,
        prompt: str,
        model: str,
        max_tokens: int = 8192,
        base_url: Optional[str] = None,
        use_max_completion_tokens: bool = False,
    ) -> Optional[str]:
        """通用：OpenAI 兼容接口（Deep Seek / OpenAI / Perplexity / xAI Grok 均兼容）。OpenAI 新模型需传 max_completion_tokens。"""
        try:
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
            content = None
            if r.choices and len(r.choices) > 0 and getattr(r.choices[0].message, "content", None):
                content = r.choices[0].message.content
            tokens_out = None
            if content is not None:
                try:
                    in_tok = int(getattr(r.usage, "prompt_tokens", 0) or 0)
                    out_tok = int(getattr(r.usage, "completion_tokens", 0) or 0)
                    if "deepseek" in model.lower():
                        provider = "deepseek"
                    elif "grok" in model.lower() or "grok" in (base_url or "").lower():
                        provider = "grok"
                    elif "perplexity" in (base_url or "").lower() or "sonar" in (model or "").lower():
                        provider = "perplexity"
                    else:
                        provider = "chatgpt"
                    price = ROUGH_OUTLINE_PRICES.get(provider, {"in": 2.50, "out": 15.00})
                    cost = (in_tok * price["in"] + out_tok * price["out"]) / 1_000_000
                    logger.info(f"[OpenAI兼容毛胚] model={model} | 输入={in_tok} tokens | 输出={out_tok} tokens | 费用=${cost:.6f}")
                    if self.redis:
                        if provider == "deepseek":
                            tool = "rough_outline_deepseek"
                        elif provider == "grok":
                            tool = "rough_outline_grok"
                        elif provider == "perplexity":
                            tool = "rough_outline_perplexity"
                        else:
                            tool = "rough_outline_openai"
                        get_monitoring(self.redis).record_tool_usage(tool, model, in_tok, out_tok, cost)
                    tokens_out = {"input": in_tok, "output": out_tok, "cost": cost}
                except Exception:
                    pass
            if content is not None:
                return (content, tokens_out)
            return (None, None)
        except Exception as e:
            logger.error(f"OpenAI 兼容 API 调用失败 (model={model}): {e}", exc_info=True)
            return None

    def _call_deepseek_for_rough_outline(self, ai_config: Dict, prompt: str) -> Optional[str]:
        """调用 Deep Seek API（OpenAI 兼容，需在 .env 中配置 DEEPSEEK_API_KEY）"""
        if not DEEPSEEK_API_KEY:
            logger.warning("Deep Seek 未配置: 请在 .env 中填写 DEEPSEEK_API_KEY")
            return None
        model = ai_config.get("model", DEEPSEEK_MODEL)
        if model == "deepseek-v3.2":
            model = "deepseek-chat"
        max_tokens = ai_config.get("max_tokens", 8192)
        return self._call_openai_compatible_rough_outline(
            api_key=DEEPSEEK_API_KEY,
            prompt=prompt,
            model=model,
            max_tokens=max_tokens,
            base_url="https://api.deepseek.com",
        )

    def _call_perplexity_for_rough_outline(self, ai_config: Dict, prompt: str) -> Optional[str]:
        """调用 Perplexity API（OpenAI 兼容，需在 .env 中配置 PERPLEXITY_API_KEY）"""
        if not PERPLEXITY_API_KEY:
            logger.warning("Perplexity 未配置: 请在 .env 中填写 PERPLEXITY_API_KEY")
            return None
        model = ai_config.get("model", PERPLEXITY_MODEL)
        if model and "pplx-" in model:
            model = "sonar-pro"
        max_tokens = ai_config.get("max_tokens", 8192)
        return self._call_openai_compatible_rough_outline(
            api_key=PERPLEXITY_API_KEY,
            prompt=prompt,
            model=model or "sonar-pro",
            max_tokens=max_tokens,
            base_url="https://api.perplexity.ai",
        )

    def _call_chatgpt_for_rough_outline(self, ai_config: Dict, prompt: str) -> Optional[str]:
        """调用 OpenAI / ChatGPT API（需在 .env 中配置 OPENAI_API_KEY）。新模型使用 max_completion_tokens。"""
        if not OPENAI_API_KEY:
            logger.warning("OpenAI 未配置: 请在 .env 中填写 OPENAI_API_KEY")
            return None
        model = ai_config.get("model", OPENAI_MODEL)
        max_tokens = ai_config.get("max_tokens", 8192)
        return self._call_openai_compatible_rough_outline(
            api_key=OPENAI_API_KEY,
            prompt=prompt,
            model=model,
            max_tokens=max_tokens,
            base_url=None,
            use_max_completion_tokens=True,
        )

    def _call_grok_for_rough_outline(self, ai_config: Dict, prompt: str) -> Optional[str]:
        """调用 xAI Grok API（OpenAI 兼容，需在 .env 中配置 XAI_API_KEY）"""
        if not XAI_API_KEY:
            logger.warning("xAI Grok 未配置: 请在 .env 中填写 XAI_API_KEY")
            return None
        model = ai_config.get("model", XAI_MODEL)
        max_tokens = ai_config.get("max_tokens", 8192)
        return self._call_openai_compatible_rough_outline(
            api_key=XAI_API_KEY,
            prompt=prompt,
            model=model,
            max_tokens=max_tokens,
            base_url="https://api.x.ai/v1",
        )


def _paragraph_has_page_break(para) -> bool:
    """判断段落内是否包含分页符（任一 run 内有 w:br type=page）。"""
    try:
        from docx.oxml.ns import qn
        for run in para.runs:
            for child in run._element:
                if child.tag == qn("w:br") and child.get(qn("w:type")) == "page":
                    return True
    except Exception:
        pass
    return False


def _get_addendum_paragraph_range(doc: "Document", to_page_break: bool):
    """
    按内容定位「添言」：找到第一个包含「添言」的段落下标 start。
    to_page_break=True（听抄稿）时 end 为 start 之后第一个含分页符的段落的前一段（不含分页符段）；
    to_page_break=False（复合稿）时 end 为文档末尾。
    返回 (start, end) 或 None（未找到「添言」）。
    """
    start_idx = None
    for idx, para in enumerate(doc.paragraphs):
        if "添言" in (para.text or ""):
            start_idx = idx
            break
    if start_idx is None:
        return None
    n = len(doc.paragraphs)
    if to_page_break:
        # 听抄稿：到分页符前一段为止，分页符段落不高亮
        end_idx = n - 1
        for idx in range(start_idx + 1, n):
            if _paragraph_has_page_break(doc.paragraphs[idx]):
                end_idx = idx - 1
                break
    else:
        end_idx = n - 1
    return (start_idx, end_idx)


def _apply_transcript_add_highlight(doc: "Document") -> None:
    """
    听抄稿纲目：与工具箱-毛胚纲目-真理加强版同一逻辑，仅改为黄色高亮（真理加强版为下划线）。
    定位所有【听抄稿添加开始】与【听抄稿添加结束】配对（按出现顺序），
    对每对之间的段落整段黄色高亮，并删除所有标记段落。支持简繁体标记。
    """
    from docx.enum.text import WD_COLOR_INDEX

    start_marker_variants = ("【听抄稿添加开始】", "【聽抄稿添加開始】")
    end_marker_variants = ("【听抄稿添加结束】", "【聽抄稿添加結束】")
    start_indices = []
    pairs = []  # [(start_idx, end_idx), ...]
    for idx, para in enumerate(doc.paragraphs):
        text = para.text.strip()
        if any(m in text for m in start_marker_variants):
            start_indices.append(idx)
        if any(m in text for m in end_marker_variants):
            if start_indices:
                pairs.append((start_indices.pop(), idx))
    if not pairs:
        return
    # 从最后一对往第一对处理，删除段落时不会影响前面配对的下标
    for (start_idx, end_idx) in reversed(pairs):
        if start_idx >= end_idx:
            continue
        # 对两标记之间的段落整段黄色高亮
        for idx in range(start_idx + 1, end_idx):
            for run in doc.paragraphs[idx].runs:
                run.font.highlight_color = WD_COLOR_INDEX.YELLOW
        # 删除标记段落（先删结束，再删开始）
        end_el = doc.paragraphs[end_idx]._element
        start_el = doc.paragraphs[start_idx]._element
        end_el.getparent().remove(end_el)
        start_el.getparent().remove(start_el)


def _get_feast_body_style(doc: "Document"):
    """节期纲目模板正文段落样式：优先 0000模板，其次 9职事信息摘录，最后 Normal。"""
    for name in ("0000模板", "9职事信息摘录", "Normal"):
        try:
            return doc.styles[name]
        except KeyError:
            continue
    return None


def _append_morning_revival_section(doc: "Document", morning_revival_raw: str) -> None:
    """晨兴信息选读：按节期纲目刷格式逻辑，分页 +「晨兴圣言信息：」(9职事信息摘录) + 小标题(81级标题)/正文(0000模板)。"""
    from docx.enum.text import WD_BREAK

    body_style = _get_feast_body_style(doc)
    title_ends = ('。', '！', '？', '…', '"', '\'', '）', '：', '』')
    p_break = doc.add_paragraph()
    p_break.add_run().add_break(WD_BREAK.PAGE)
    title_para = doc.add_paragraph("晨兴圣言信息：")
    try:
        title_para.style = doc.styles["9职事信息摘录"]
    except KeyError:
        try:
            title_para.style = doc.styles["81级标题"]
        except KeyError:
            pass
    for line in morning_revival_raw.split("\n"):
        if line.strip():
            p = doc.add_paragraph(line)
            if not (line.rstrip().endswith(title_ends)):
                try:
                    p.style = doc.styles["81级标题"]
                except KeyError:
                    if body_style is not None:
                        p.style = body_style
            elif body_style is not None:
                p.style = body_style
        else:
            doc.add_paragraph("")


def _append_transcript_info_section(
    doc: "Document",
    transcript_raw: str,
    transcript_preface: Optional[str] = None,
    transcript_addendum: Optional[str] = None,
) -> None:
    """听抄稿：分页 +「听抄信息：」+ 序言、听抄稿、添言三段合并内容（按节期纲目刷格式逻辑套样式）。"""
    from docx.enum.text import WD_BREAK

    parts = []
    if (transcript_preface or "").strip():
        parts.append((transcript_preface or "").strip())
    if (transcript_raw or "").strip():
        parts.append((transcript_raw or "").strip())
    if (transcript_addendum or "").strip():
        parts.append((transcript_addendum or "").strip())
    combined = "\n\n".join(parts) if parts else ""

    body_style = _get_feast_body_style(doc)
    p_break = doc.add_paragraph()
    p_break.add_run().add_break(WD_BREAK.PAGE)
    title_para = doc.add_paragraph("听抄信息：")
    try:
        title_para.style = doc.styles["9职事信息摘录"]
    except KeyError:
        try:
            title_para.style = doc.styles["81级标题"]
        except KeyError:
            pass
    try:
        import sys
        from pathlib import Path
        _backend = Path(__file__).resolve().parent.parent
        if str(_backend) not in sys.path:
            sys.path.insert(0, str(_backend))
        from 节期纲目刷格式 import apply_custom_92_style
    except ImportError:
        apply_custom_92_style = None
    for line in combined.split("\n"):
        if line.strip():
            p = doc.add_paragraph(line)
            if '。' not in line and apply_custom_92_style is not None:
                apply_custom_92_style(p)
            elif body_style is not None:
                p.style = body_style
        else:
            doc.add_paragraph("")


# 创建全局服务实例
ai_service = AISearchService()
