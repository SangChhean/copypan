"""
AI 搜索监控模块

功能：
- 使用 Redis 存储 AI 查询统计与错误记录
- 统计项：总查询数、缓存命中率、平均响应时间、总费用（按 Claude Sonnet 4.5 定价）
- 支持按日汇总，每日数据 30 天后自动过期

Redis 数据结构：
- Hash ai_monitoring:stats：全局累计（total_queries, cache_hits, total_response_time_ms, total_input_tokens, total_output_tokens, total_cost）
- Hash ai_monitoring:daily:YYYY-MM-DD：当日统计（同上），设置 TTL=30 天
- List ai_monitoring:errors：最近错误列表，每项为 JSON，最多保留 200 条
"""
import os
import json
import logging
import time
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("ai_search.monitoring")

# 环境变量：Redis 连接
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))

# Claude Sonnet 4.5 定价（美元/百万 token）
PRICE_INPUT_PER_MILLION = 3.0
PRICE_OUTPUT_PER_MILLION = 15.0

# Redis 键前缀与常量
KEY_STATS = "ai_monitoring:stats"  # 全局统计 hash
KEY_DAILY_PREFIX = "ai_monitoring:daily:"  # 每日统计 hash，格式 ai_monitoring:daily:YYYY-MM-DD
KEY_ERRORS = "ai_monitoring:errors"  # 最近错误 list
KEY_RETRIEVAL_LOG = "ai_monitoring:retrieval_log"  # 检索统计日志 list
MAX_ERRORS = 200  # 最多保留错误条数
MAX_RETRIEVAL_LOG = 100  # 检索日志最多保留条数
DAILY_TTL_DAYS = 30  # 每日统计保留天数
DAILY_TTL_SECONDS = 30 * 24 * 3600  # 每日 key 的 TTL（秒）


def _get_redis_client():
    """获取 Redis 客户端（与 ai_service 一致，decode_responses=True）。"""
    try:
        import redis
        client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)
        client.ping()
        return client
    except Exception as e:
        logger.warning(f"Redis 未启用，监控将不可用: {e}")
        return None


class AIMonitoring:
    """
    AI 搜索监控类。
    使用 Redis hash 存储聚合统计与每日统计，使用 list 存储最近错误。
    """

    def __init__(self, redis_client=None):
        """
        初始化监控。
        :param redis_client: 可选，已连接的 Redis 客户端；为 None 时内部创建。
        """
        self.redis = redis_client if redis_client is not None else _get_redis_client()

    def _today_str(self) -> str:
        """当前日期字符串，用于每日统计键。"""
        return datetime.utcnow().strftime("%Y-%m-%d")

    def _cost_from_tokens(self, input_tokens: int, output_tokens: int) -> float:
        """
        根据 Claude Sonnet 4.5 定价计算费用（美元）。
        :param input_tokens: 输入 token 数
        :param output_tokens: 输出 token 数
        :return: 费用（美元）
        """
        return (
            (input_tokens / 1_000_000) * PRICE_INPUT_PER_MILLION
            + (output_tokens / 1_000_000) * PRICE_OUTPUT_PER_MILLION
        )

    NATURE_KEYS = ("一般性", "高真理浓度", "高生命浓度", "重实行应用")

    def _normalize_nature(self, special_needs: Optional[str]) -> str:
        """纲目性质归一化为四种之一，用于统计。"""
        if not special_needs or not isinstance(special_needs, str):
            return "一般性"
        s = special_needs.strip()
        return s if s in self.NATURE_KEYS else "一般性"

    def record_query(
        self,
        question: str,
        response_time_ms: float,
        cache_hit: bool,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost: Optional[float] = None,
        special_needs: Optional[str] = None,
    ) -> None:
        """
        记录一次 AI 查询。
        :param question: 用户问题（可截断存储，仅用于统计展示）
        :param response_time_ms: 响应时间（毫秒）
        :param cache_hit: 是否命中缓存
        :param input_tokens: 输入 token 数
        :param output_tokens: 输出 token 数
        :param cost: 费用（美元）；为 None 时根据 input/output tokens 计算
        :param special_needs: 纲目性质（一般性/高真理浓度/高生命浓度/重实行应用），用于统计占比
        """
        if not self.redis:
            return
        if cost is None:
            cost = self._cost_from_tokens(input_tokens, output_tokens)
        nature = self._normalize_nature(special_needs)
        try:
            # 全局统计：使用 hash 累加
            # 响应时间只记录非缓存命中（真实 AI 回答）的查询，否则平均响应时间不准确
            pipe = self.redis.pipeline()
            pipe.hincrby(KEY_STATS, "total_queries", 1)
            pipe.hincrby(KEY_STATS, f"nature_{nature}", 1)
            if cache_hit:
                pipe.hincrby(KEY_STATS, "cache_hits", 1)
            else:
                pipe.hincrbyfloat(KEY_STATS, "total_response_time_ms", response_time_ms)
            pipe.hincrby(KEY_STATS, "total_input_tokens", input_tokens)
            pipe.hincrby(KEY_STATS, "total_output_tokens", output_tokens)
            pipe.hincrbyfloat(KEY_STATS, "total_cost", round(cost, 6))
            # 每日统计
            day_key = KEY_DAILY_PREFIX + self._today_str()
            pipe.hincrby(day_key, "total_queries", 1)
            if cache_hit:
                pipe.hincrby(day_key, "cache_hits", 1)
            else:
                pipe.hincrbyfloat(day_key, "total_response_time_ms", response_time_ms)
            pipe.hincrby(day_key, "total_input_tokens", input_tokens)
            pipe.hincrby(day_key, "total_output_tokens", output_tokens)
            pipe.hincrbyfloat(day_key, "total_cost", round(cost, 6))
            pipe.expire(day_key, DAILY_TTL_SECONDS)
            pipe.execute()
        except Exception as e:
            logger.warning(f"记录查询统计失败: {e}")

    def record_error(self, error_message: str, extra: Optional[Dict[str, Any]] = None) -> None:
        """
        记录一条错误。
        :param error_message: 错误信息
        :param extra: 可选，额外上下文（如 question、traceback 等）
        """
        if not self.redis:
            return
        try:
            item = {
                "ts": datetime.utcnow().isoformat() + "Z",
                "message": error_message[:2000],
                **(extra or {}),
            }
            self.redis.lpush(KEY_ERRORS, json.dumps(item, ensure_ascii=False))
            self.redis.ltrim(KEY_ERRORS, 0, MAX_ERRORS - 1)
        except Exception as e:
            logger.warning(f"记录错误失败: {e}")

    def record_retrieval_stats(
        self,
        question_preview: str,
        total: int,
        used: int,
        waste_rate: float,
    ) -> None:
        """
        记录一次检索统计（总检索条数、使用条数、浪费率），用于后台展示。
        :param question_preview: 问题摘要（如前30字）
        :param total: 总检索条数
        :param used: 实际使用条数
        :param waste_rate: 浪费率（百分比）
        """
        if not self.redis:
            return
        try:
            item = {
                "ts": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                "question": question_preview,
                "total": total,
                "used": used,
                "waste_rate": waste_rate,
            }
            self.redis.lpush(KEY_RETRIEVAL_LOG, json.dumps(item, ensure_ascii=False))
            self.redis.ltrim(KEY_RETRIEVAL_LOG, 0, MAX_RETRIEVAL_LOG - 1)
        except Exception as e:
            logger.warning(f"记录检索统计失败: {e}")

    def get_recent_retrieval_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        获取最近检索统计日志。
        :param limit: 最多返回条数
        :return: 列表，每项含 ts、question、total、used、waste_rate
        """
        if not self.redis:
            return []
        try:
            raw_list = self.redis.lrange(KEY_RETRIEVAL_LOG, 0, limit - 1)
            result = []
            for s in raw_list:
                try:
                    result.append(json.loads(s))
                except json.JSONDecodeError:
                    result.append({"question": s, "ts": None, "total": 0, "used": 0, "waste_rate": 0})
            return result
        except Exception as e:
            logger.warning(f"获取检索日志失败: {e}")
            return []

    def get_stats(self, days: int = 7) -> Dict[str, Any]:
        """
        获取统计数据。
        :param days: 包含的最近天数（用于每日统计列表）
        :return: 总查询数、缓存命中率、平均响应时间、总费用、每日统计列表
        """
        if not self.redis:
            return {
                "total_queries": 0,
                "cache_hit_rate": 0.0,
                "avg_response_time_ms": 0.0,
                "total_cost": 0.0,
                "nature_counts": {k: 0 for k in AIMonitoring.NATURE_KEYS},
                "daily": [],
                "retrieval_log": [],
                "message": "Redis 未启用，无统计数据",
            }
        try:
            # 从 Redis Hash 读取全局统计
            raw = self.redis.hgetall(KEY_STATS)
            total_queries = int(raw.get("total_queries", 0) or 0)
            cache_hits = int(raw.get("cache_hits", 0) or 0)
            total_response_time_ms = float(raw.get("total_response_time_ms", 0) or 0)
            total_cost = float(raw.get("total_cost", 0) or 0)
            cache_hit_rate = (cache_hits / total_queries * 100) if total_queries else 0.0
            # 平均响应时间只按真实 AI 回答的查询计算，不含缓存命中
            non_cache_queries = total_queries - cache_hits
            avg_response_time_ms = (total_response_time_ms / non_cache_queries) if non_cache_queries > 0 else 0.0

            # 每日统计（最近 days 天）
            daily = []
            for i in range(days):
                d = datetime.utcnow().date() - timedelta(days=i)
                day_key = KEY_DAILY_PREFIX + d.strftime("%Y-%m-%d")
                day_raw = self.redis.hgetall(day_key)
                if not day_raw:
                    daily.append({"date": d.strftime("%Y-%m-%d"), "queries": 0, "cache_hits": 0, "avg_ms": 0, "cost": 0})
                    continue
                q = int(day_raw.get("total_queries", 0) or 0)
                ch = int(day_raw.get("cache_hits", 0) or 0)
                tr = float(day_raw.get("total_response_time_ms", 0) or 0)
                c = float(day_raw.get("total_cost", 0) or 0)
                nc = q - ch  # 非缓存命中的查询数
                daily.append({
                    "date": d.strftime("%Y-%m-%d"),
                    "queries": q,
                    "cache_hits": ch,
                    "avg_ms": round(tr / nc, 2) if nc > 0 else 0,
                    "cost": round(c, 4),
                })
            retrieval_log = self.get_recent_retrieval_log(limit=50)
            # 纲目性质统计：四种性质的查询次数
            nature_counts = {k: int(raw.get(f"nature_{k}", 0) or 0) for k in self.NATURE_KEYS}
            return {
                "total_queries": total_queries,
                "cache_hit_rate": round(cache_hit_rate, 2),
                "avg_response_time_ms": round(avg_response_time_ms, 2),
                "total_cost": round(total_cost, 4),
                "nature_counts": nature_counts,
                "daily": daily,
                "retrieval_log": retrieval_log,
            }
        except Exception as e:
            logger.warning(f"获取统计失败: {e}")
            return {
                "total_queries": 0,
                "cache_hit_rate": 0.0,
                "avg_response_time_ms": 0.0,
                "total_cost": 0.0,
                "daily": [],
                "nature_counts": {"一般性": 0, "高真理浓度": 0, "高生命浓度": 0, "重实行应用": 0},
                "retrieval_log": [],
                "error": str(e),
            }

    def get_recent_errors(self, limit: int = 50) -> List[Dict[str, Any]]:
        """
        获取最近的错误记录。
        :param limit: 最多返回条数
        :return: 错误列表，每项含 ts、message 及可能的 extra 字段
        """
        if not self.redis:
            return []
        try:
            raw_list = self.redis.lrange(KEY_ERRORS, 0, limit - 1)
            result = []
            for s in raw_list:
                try:
                    result.append(json.loads(s))
                except json.JSONDecodeError:
                    result.append({"message": s, "ts": None})
            return result
        except Exception as e:
            logger.warning(f"获取最近错误失败: {e}")
            return []

    def reset_stats(self) -> None:
        """重置所有统计（全局 + 每日 + 错误列表）。"""
        if not self.redis:
            return
        try:
            keys = [KEY_STATS, KEY_ERRORS, KEY_RETRIEVAL_LOG]
            # 删除最近 30 天内的每日键
            for i in range(DAILY_TTL_DAYS + 1):
                d = datetime.utcnow().date() - timedelta(days=i)
                keys.append(KEY_DAILY_PREFIX + d.strftime("%Y-%m-%d"))
            self.redis.delete(*keys)
            logger.info("AI 监控统计已重置")
        except Exception as e:
            logger.warning(f"重置统计失败: {e}")


# 单例，便于在 router 或 service 中复用
_monitoring_instance: Optional[AIMonitoring] = None


def get_monitoring(redis_client=None) -> AIMonitoring:
    """获取 AIMonitoring 单例。"""
    global _monitoring_instance
    if _monitoring_instance is None:
        _monitoring_instance = AIMonitoring(redis_client=redis_client)
    return _monitoring_instance
