# -*- coding: utf-8 -*-
"""【新测试台】负担说明要读的最内在词库（133 个词）。

有负担的重点、没有负担的重点：正式流程每次都读（见 kg_rag_service.generate_burden_description）。

词库单独存放在 burden_compare_terms.json，程序每次随请求发给模型（不靠模型自己去查）。
发送前把实际要发的文字拆开重新数一遍，数量或类别不对就报错、不调用模型，
绝不会退回成"没有词库"的结果。
"""
import json
import re
from pathlib import Path
from typing import Any

_TERMS_PATH = Path(__file__).resolve().parent / "burden_compare_terms.json"

INNER_CATEGORY = "最内在"
INNER_COUNT = 133

# 有负担的重点："负担的重点篇幅较短……"这一条里多一个参考的资料库
_EXCERPT_CLAUSE_OLD = "与负担的重点的方向展开，补充倪柝声"
_EXCERPT_CLAUSE_NEW = "与负担的重点的方向展开，并参考「参考词库」中的词条，补充倪柝声"

# 没有负担的重点：第 1 步多一个参考的资料库
_NO_EXCERPT_CLAUSE_OLD = "1. 根据篇题/主题与纲目性质，构建该主题的核心负担："
_NO_EXCERPT_CLAUSE_NEW = "1. 根据篇题/主题与纲目性质，并参考「参考词库」中的词条，构建该主题的核心负担："

_LIB_LINE = re.compile(r"^【([^】]+)】（(\d+)）(.*)$")


class LibraryError(RuntimeError):
    """词库文件或实发内容核对不通过。"""


def load_inner_terms() -> list[str]:
    """每次都从文件读，保证用的是磁盘上当前这一份。读不到或数量不对直接报错。"""
    try:
        data = json.loads(_TERMS_PATH.read_text(encoding="utf-8"))
    except Exception as e:
        raise LibraryError(f"词库文件读取失败：{e}") from e
    words = data.get(INNER_CATEGORY) or []
    if len(words) != INNER_COUNT:
        raise LibraryError(f"词库文件里【{INNER_CATEGORY}】应有 {INNER_COUNT} 个词，实际 {len(words)} 个")
    return words


def build_library_text(words: list[str]) -> str:
    return "\n".join(["【参考词库】", f"【{INNER_CATEGORY}】（{len(words)}）" + "、".join(words)])


def verify_library_text(text: str) -> dict[str, Any]:
    """把实际要发的文字拆开重新数：类别和词数都要对上，否则报错。"""
    by_cat: dict[str, int] = {}
    for line in text.split("\n")[1:]:
        m = _LIB_LINE.match(line)
        if not m:
            raise LibraryError("词库格式异常")
        by_cat[m.group(1)] = len([w for w in m.group(3).split("、") if w])
    if list(by_cat) != [INNER_CATEGORY]:
        raise LibraryError(f"实发类别不对：{list(by_cat)}")
    if by_cat[INNER_CATEGORY] != INNER_COUNT:
        raise LibraryError(f"【{INNER_CATEGORY}】实发 {by_cat[INNER_CATEGORY]} 个，应为 {INNER_COUNT} 个")
    return {"total": by_cat[INNER_CATEGORY], "by_category": by_cat}


def load_verified_library() -> tuple[str, dict[str, Any], list[str]]:
    """返回（要发给模型的词库文字，核对结果，词表）。"""
    words = load_inner_terms()
    text = build_library_text(words)
    return text, verify_library_text(text), words


def _replace_once(prompt: str, old: str, new: str, what: str) -> str:
    n = prompt.count(old)
    if n != 1:
        raise LibraryError(f"Prompt 中要修改的{what}命中 {n} 次（应为 1 次）")
    return prompt.replace(old, new)


def apply_excerpt_clause(prompt: str) -> str:
    """有负担的重点：改"负担的重点篇幅较短……"这一条；必须恰好命中一次，否则报错。"""
    return _replace_once(prompt, _EXCERPT_CLAUSE_OLD, _EXCERPT_CLAUSE_NEW, "「负担的重点篇幅较短」这一条")


def apply_no_excerpt_clause(prompt: str) -> str:
    """没有负担的重点：改第 1 步；必须恰好命中一次，否则报错。"""
    return _replace_once(prompt, _NO_EXCERPT_CLAUSE_OLD, _NO_EXCERPT_CLAUSE_NEW, "第 1 步")
