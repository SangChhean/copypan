# -*- coding: utf-8 -*-
"""第 1 步：入口。沿用阶段 1 的登录、日限额、IP 限流、注入过滤；无历史的问题用原问题查缓存。

缓存命中是否计限额：照 3.0 现行做法（back_qa/qa/qa_router.py stream_answer 先 check_and_increment_daily_usage 再查缓存）
→ 照常计。3.0 的非流式 /query 不扣限额；qa4 两个路由都扣（见报告）。
"""

from __future__ import annotations

from typing import Any, Optional

from core.input_guard import check_prompt_injection
from core.rate_limit import check_rate_limit


def entry_checks(request: Any, *, auth: Any, store: Any, username: str, question: str, rate_limit: int) -> Optional[tuple[int, str]]:
    """返回 (HTTP 状态码, 中文原因) 表示拒绝；None 表示放行。顺序同 3.0：限额 → 限流 → 注入。"""
    usage = auth.check_and_increment_usage(username)
    if not usage.get("allowed"):
        return 429, f"今日问答次数已达上限（{usage.get('limit')}次），请明天再来"
    if not check_rate_limit(request, store, limit=rate_limit):
        return 429, "请求过于频繁，请稍后再试"
    if not check_prompt_injection(question):
        return 400, "输入包含不支持的内容"
    return None


def cache_lookup(ctx: Any, deps: Any) -> Optional[dict[str, Any]]:
    """无历史时用原问题查缓存。"""
    if ctx.history:
        return None
    return deps.cache.lookup(ctx.question_orig)
