# -*- coding: utf-8 -*-
"""问题规范化、哈希、引文核对用的归一化。日志只记长度与哈希前 8 位。"""

from __future__ import annotations

import hashlib
import re
import unicodedata

_TRAIL_PUNCT = "?？。.!！"
_STRIP_FOR_QUOTE = re.compile(r"[\s\u3000\W_]+", re.UNICODE)


def normalize_question(q: str) -> str:
    """缓存键用：NFKC（统一全半角）+ 去空白 + 去句末问号句号【暂定】。"""
    s = unicodedata.normalize("NFKC", q or "")
    s = re.sub(r"\s+", "", s)
    return s.rstrip(_TRAIL_PUNCT)


def qhash(q: str) -> str:
    return hashlib.sha256((q or "").encode("utf-8")).hexdigest()


def qmeta(q: str) -> dict:
    return {"len": len(q or ""), "sha8": qhash(q)[:8]}


def norm_for_quote(s: str) -> str:
    """去空白与标点、统一全半角，供引文核对。"""
    s = unicodedata.normalize("NFKC", s or "")
    return _STRIP_FOR_QUOTE.sub("", s)
