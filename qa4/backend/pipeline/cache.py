# -*- coding: utf-8 -*-
"""答案缓存。

缓存键 = 规范化问题 + 题型与限定 + 提示词版本 + 模型配置（不含数据版本号、不含对话历史）。
第 1/2 步时还不知道题型，所以另存一个「别名键」= 规范化问题 + 提示词版本 + 模型配置 → 指向完整键【暂定】。
「未找到」只在放宽重试后仍不够时缓存，TTL 1 天；取具体对象不缓存。
键都在 store 前缀（qa4:）下，管理接口 /api/admin/cache/clear 的 SCAN 前缀删除可清掉。
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Optional

from pipeline.textutil import normalize_question


def _h(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


class AnswerCache:
    def __init__(self, store: Any, cfg: dict[str, Any], *, prompt_version: str, model_config: dict[str, Any]) -> None:
        self.store = store
        self.cfg = cfg
        self.prompt_version = prompt_version
        self.model_config = dict(model_config)
        self.prefix = str(cfg.get("cache_prefix", "cache:"))
        self.alias_prefix = str(cfg.get("cache_alias_prefix", "cache_alias:"))

    def alias_key(self, question: str) -> str:
        return self.alias_prefix + _h(
            {"q": normalize_question(question), "pv": self.prompt_version, "mc": self.model_config}
        )

    def full_key(self, question: str, main_type: str, restrictions: list[dict[str, Any]]) -> str:
        return self.prefix + _h(
            {
                "q": normalize_question(question),
                "t": main_type,
                "r": sorted(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in restrictions),
                "pv": self.prompt_version,
                "mc": self.model_config,
            }
        )

    def lookup(self, question: str) -> Optional[dict[str, Any]]:
        if self.store is None:
            return None
        full = self.store.get(self.alias_key(question))
        if not full:
            return None
        raw = self.store.get(full)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except Exception:
            return None

    def save(
        self,
        question: str,
        main_type: str,
        restrictions: list[dict[str, Any]],
        payload: dict[str, Any],
        *,
        not_found: bool,
        targeted: bool,
    ) -> Optional[str]:
        if self.store is None or targeted:
            return None
        ttl = int(self.cfg.get("cache_not_found_ttl_s" if not_found else "cache_ttl_s", 86400))
        full = self.full_key(question, main_type, restrictions)
        self.store.set(full, json.dumps(payload, ensure_ascii=False), ttl=ttl)
        self.store.set(self.alias_key(question), full, ttl=ttl)
        return full

    def ttl_for(self, *, not_found: bool) -> int:
        return int(self.cfg.get("cache_not_found_ttl_s" if not_found else "cache_ttl_s", 86400))
