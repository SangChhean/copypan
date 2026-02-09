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

    def search(self, question: str, max_results: int = 30, depth: str = "general") -> Dict:
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
            cache_key = self._get_cache_key(question, depth)
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

            # 3. 搜索Elasticsearch（根据深度参数决定上下文数量）
            search_start = time.time()
            # 根据深度参数决定上下文数量：一般50条，深度200条
            context_size = 50 if depth == "general" else 200
            fetch_size = context_size  # 直接使用设定的上下文数量
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
            ai_response = self._generate_answer(question, search_results, context_size)
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

    def search_only(self, question: str, depth: str = "general") -> Dict:
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
            cache_key = self._get_cache_key(question, depth)
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
                    )
                except Exception as _e:
                    logger.debug(f"监控记录失败: {_e}")
                return cached

            context_size = 50 if depth == "general" else 200
            search_start = time.time()
            search_results = self._multi_index_search(question, context_size)
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

    def generate_only(self, question: str, search_id: str, max_results: int = 30) -> Dict:
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
            cache_key = self._get_cache_key(question or stored_question, stored_depth)
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
            ai_response = self._generate_answer(question or stored_question, search_results, context_size)
            ai_time = (time.time() - ai_start) * 1000

            sources = self._extract_sources(search_results[:max_results])
            total_time = (time.time() - start_time) * 1000

            result = {
                "answer": ai_response["answer"],
                "sources": sources,
                "cached": False,
                "tokens": ai_response.get("tokens"),
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
                                # 单字段匹配（仅 text，与 index mapping 一致）
                                {
                                    "match": {
                                        "text": {
                                            "query": query,
                                            "fuzziness": "AUTO",
                                            "boost": 2.0
                                        }
                                    }
                                }
                            ],
                            "minimum_should_match": 1
                        }
                    },
                    "size": int(size * weight * 1.2),  # 每索引取数：如 100*1.0*1.2=120
                    "_source": [
                        "book", "chapter", "verse",
                        "text", "title"
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

    def _generate_answer(self, question: str, search_results: List[Dict], context_size: int = 200) -> Dict:
        """
        调用Claude生成答案

        Args:
            question: 用户问题
            search_results: ES搜索结果
            context_size: 使用的上下文数量（默认200条）

        Returns:
            {"answer": str, "tokens": dict}
        """
        # 构建上下文：根据context_size参数决定使用多少条
        context_parts = []
        for i, hit in enumerate(search_results[:context_size], 1):
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

【最高优先级原则】
逐字引用（verbatim quotes）是最核心的要求，优先级高于所有其他要求。当任何要求与"逐字引用"冲突时，优先保证逐字引用。特别注意：大纲（壹、贰、叁）最容易被总结改写，必须严格遵守逐字引用原则。

要求：
1. 你的回答必须以原文的 verbatim quotes（逐字引用）为核心内容，所有实质性观点、论述和纲目都必须直接从原文提取，不可改写、总结、概括或重述。
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
    - 文集类：倪柝声/李常受文集[年份][册数]，[书名/主题]，第[X]章
      示例：李常受文集一九九四至一九九七年第二册，神人，第四章
    - 生命读经类：[书卷名]生命读经，第[X]篇
      示例：启示录生命读经，第五十九篇
    - 专书类：[书名]，第[X]章
      示例：属灵的实际，第四章
    
    输出格式：
    参考与参读资料：
    1. 李常受文集一九九四至一九九七年第二册，神人，第四章
    2. 启示录生命读经，第五十九篇
    3. 属灵的实际，第四章

18. 纲目的逻辑顺序应符合原文的神学论述逻辑，而非仅按原文出现的先后顺序排列。

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
    3. 生命的经历，第五篇

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

    def _get_cache_key(self, question: str, depth: str = "general") -> str:
        """生成缓存key（包含问题和深度参数）"""
        # 使用MD5哈希问题和深度生成唯一key
        cache_content = f"{question}:{depth}"
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
