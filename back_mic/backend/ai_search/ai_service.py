"""
AI搜索服务 - 核心业务逻辑
负责Elasticsearch检索、Claude API调用、结果处理
"""
import os
import json
import hashlib
import logging
import time
from typing import Dict, List, Optional
from datetime import datetime

from es_config import es
import anthropic
from dotenv import load_dotenv

from .monitoring import get_monitoring

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("ai_search")

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

# 索引配置：索引名 -> 权重（用于每索引取数及排序加权）
INDEXES_CONFIG = {
    "life": {"weight": 1.3},    # 生命读经
    "cwwl": {"weight": 1.5},    # 李常受文集
    "cwwn": {"weight": 1.3},    # 倪柝声文集
    "bib": {"weight": 1.2},     # 圣经
    "others": {"weight": 1.0},  # 其他
    "hymn": {"weight": 0.8}     # 诗歌
}


class AISearchService:
    """AI智能搜索服务"""

    def __init__(self):
        self.es = es
        self.redis = redis_client
        self.claude = claude_client
        self.cache_ttl = 3600  # 缓存1小时

        logger.info("AISearchService初始化完成")

    def search(self, question: str, max_results: int = 30) -> Dict:
        """
        AI智能搜索主函数

        Args:
            question: 用户问题
            max_results: 最多返回结果数

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

            # 2. 检查缓存
            cache_key = self._get_cache_key(question)
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
                    )
                except Exception as _e:
                    logger.debug(f"监控记录失败: {_e}")
                return cached_result

            # 3. 搜索Elasticsearch（至少取 100 条给 AI 上下文，引用来源最多 50 条）
            search_start = time.time()
            fetch_size = max(100, max_results * 2)  # 至少 100 条供 AI 使用
            search_results = self._multi_index_search(question, fetch_size)
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
            ai_response = self._generate_answer(question, search_results)
            ai_time = (time.time() - ai_start) * 1000

            logger.info(f"AI生成完成: 耗时{ai_time:.0f}ms")

            # 5. 构造返回结果（引用来源最多 50 条）
            result = {
                "answer": ai_response["answer"],
                "sources": self._extract_sources(search_results[:50]),
                "cached": False,
                "tokens": ai_response.get("tokens"),
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

    def _multi_index_search(self, query: str, size: int) -> List[Dict]:
        """
        多索引搜索并按权重排序

        Args:
            query: 搜索关键词
            size: 返回结果数量

        Returns:
            加权排序后的搜索结果列表
        """
        all_results = []

        for index_name, config in INDEXES_CONFIG.items():
            weight = config["weight"]
            try:
                # 构建搜索查询
                search_body = {
                    "query": {
                        "bool": {
                            "should": [
                                # 精确短语匹配（最高权重）；项目 mapping 主字段为 text，无 content
                                {
                                    "match_phrase": {
                                        "text": {
                                            "query": query,
                                            "boost": 2.5
                                        }
                                    }
                                },
                                # 多字段匹配（text 为主；content/outline 若数据有则参与）
                                {
                                    "multi_match": {
                                        "query": query,
                                        "fields": [
                                            "text^4",       # 正文权重最高
                                            "content^2.5",
                                            "msg^2",
                                            "outline^2",    # 大纲
                                            "title^1.5"     # 降低标题（避免标题党）
                                        ],
                                        "type": "best_fields",
                                        "fuzziness": "AUTO",  # 模糊匹配
                                        "boost": 2.0
                                    }
                                }
                            ],
                            "minimum_should_match": 1
                        }
                    },
                    "size": int(size * weight * 1.2),  # 每索引取数：如 100*1.0*1.2=120
                    "_source": [
                        "book", "chapter", "verse",
                        "content", "text", "msg", "outline", "title"
                    ]
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
                    hit['_weighted_score'] = hit['_score'] * weight
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

    def _generate_answer(self, question: str, search_results: List[Dict]) -> Dict:
        """
        调用Claude生成答案

        Args:
            question: 用户问题
            search_results: ES搜索结果

        Returns:
            {"answer": str, "tokens": dict}
        """
        # 构建上下文：最多使用前100条给 Claude 生成答案
        context_parts = []
        for i, hit in enumerate(search_results[:100], 1):
            source = hit['_source']
            reference = self._format_reference(source)

            # 提取内容（尝试多个可能的字段）
            content = (
                source.get('content') or
                source.get('text') or
                source.get('msg') or
                source.get('outline') or
                ''
            )

            # 限制每条内容长度，避免Token超限
            if len(content) > 300:
                content = content[:300] + "..."

            # 标注来源类型
            index_name = hit.get('_index_name', '')
            source_type = self._get_source_type(index_name)

            context_parts.append(f"{i}. {source_type} {reference}\n{content}\n")

        context = "\n".join(context_parts)

        # 构建prompt
        system_prompt = """你是一个资深的圣经研究学者，更是一位专业的倪柝声、李常受神学的研究者，请基于提供的内容回答问题。

要求：
1. 严格要求你所回答的每一句话，都必须从所提供给你的原文文章中直接提取句子来构建，这是必须的。
2. 你的回答不可改写原文，不可使用自己总结的话，不可使用自己概括的话，不可以通过概括或重述的方式改写，所有回答的内容必须完全从所提供的原文当中直接提取。
3. 不是简单的按照顺序列出，要综合文章的所有点，给出关于用户所提的问题来回答，内容全面，结构清晰，逻辑合理。
4. 如果所提供的内容不足以回答问题，请诚实说明，而不是编造答案。
5. 若需要列出纲目的层级序号，请严格按照：壹的下一级是一，一的下一级是1，1 的下一级是 a，即一级序号为壹、贰，以此类推，二级为一、二以此类推，三级为 1、2 以此类推，四级为 a、b 以此类推，注意，纲目层级后面不是加、而是全角空格。
6. 请用纯文本作答，不要使用 Markdown 格式：不要使用 #、*、** 等符号，不要用井号当标题、不要用星号加粗，层级与强调仅用序号（壹、一、1、a）和换行区分即可。
7. 在回答末尾，另起一段列出最相关的10条引用的出处，每条一行（引用出处：1. xxx \\n 2. xxx），不要给出处加引号，不要出现多余的 ""。"""

        user_prompt = f"""用户的问题：{question}

参考内容：
{context}

请基于以上内容回答问题："""

        # 调用Claude API
        try:
            message = self.claude.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=4000,
                temperature=0.3,  # 降低温度提高准确性
                system=system_prompt,
                messages=[
                    {"role": "user", "content": user_prompt}
                ]
            )

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

            logger.info(f"Claude调用成功: Token={tokens['total']}, 费用=${tokens['cost']}")

            return {
                "answer": answer,
                "tokens": tokens
            }

        except anthropic.RateLimitError as e:
            logger.error(f"API限流: {e}")
            return {
                "answer": "请求过于频繁，请稍后再试。",
                "tokens": {"error": str(e)}
            }
        except anthropic.APIError as e:
            logger.error(f"API错误: {e}")
            return {
                "answer": "AI服务暂时不可用，请稍后重试。",
                "tokens": {"error": str(e)}
            }
        except Exception as e:
            logger.error(f"生成答案失败: {e}")
            raise

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
            "hymn": "[诗歌]",
            "bib": "[圣经]"
        }
        return type_map.get(index_name, "[未分类]")

    def _extract_sources(self, search_results: List[Dict]) -> List[Dict]:
        """提取引用来源"""
        sources = []

        for hit in search_results:
            source = hit['_source']

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

            sources.append({
                "reference": self._format_reference(source),
                "content": preview,
                "score": round(hit.get('_weighted_score', hit.get('_score', 0)), 2),
                "type": self._get_source_type(hit.get('_index_name', ''))
            })

        return sources

    def _get_cache_key(self, question: str) -> str:
        """生成缓存key"""
        # 使用MD5哈希问题生成唯一key
        question_hash = hashlib.md5(question.encode()).hexdigest()
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
            # 移除不需要缓存的字段
            cache_data = result.copy()
            cache_data.pop("cached", None)

            self.redis.setex(
                cache_key,
                self.cache_ttl,
                json.dumps(cache_data, ensure_ascii=False)
            )
            return True
        except Exception as e:
            logger.warning(f"保存缓存失败: {e}")
            return False

    def health_check(self) -> Dict:
        """健康检查"""
        status = {
            "elasticsearch": False,
            "redis": False,
            "claude": False,
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

        # 核心依赖为 ES + Claude；Redis 为可选（未启用时仍可为 healthy）
        status["overall"] = status["elasticsearch"] and status["claude"]

        return status


# 创建全局服务实例
ai_service = AISearchService()
