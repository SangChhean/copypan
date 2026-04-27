# -*- coding: utf-8 -*-
"""
将 life_gen.json 1:1 转换为 index_to_es_full.py 可入库的 chunks JSON。

规则：
- 仅处理 type == "text" 的记录
- 每条输入记录对应 1 条输出 chunk（不合并、不拆分）
- 输出字段对齐 kg_rag/scripts/index_to_es_full.py 的 WRITE_FIELDS
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


# 与 chunking_full.py 保持一致的书卷集合与经节匹配逻辑
_BOOK_SET: list[str] = sorted([
    # 旧约
    "创", "出", "利", "民", "申", "书", "士", "得",
    "撒上", "撒下", "王上", "王下", "代上", "代下",
    "拉", "尼", "斯", "伯", "诗", "箴", "传", "歌",
    "赛", "耶", "哀", "结", "但",
    "何", "珥", "摩", "俄", "拿", "弥", "鸿", "哈", "番", "该", "亚", "玛",
    # 新约
    "太", "可", "路", "约", "徒", "罗",
    "林前", "林后", "加", "弗", "腓", "西",
    "帖前", "帖后", "提前", "提后", "多", "门", "来", "雅",
    "彼前", "彼后", "约壹", "约贰", "约叁", "犹", "启",
], key=len, reverse=True)

_SCRIPTURE_REF_RE = re.compile(
    r"(?:" + "|".join(re.escape(b) for b in _BOOK_SET) + r")"
    r"[一二三四五六七八九十百千〇\d]"
)
_BRACKET_RE = re.compile(r"[（(]([^）)]{1,40})[）)]")
_DASH_REF_RE = re.compile(
    r"[—－]([^—－\n]*?(?:" + "|".join(re.escape(b) for b in _BOOK_SET)
    + r")[^—－\n]*?)(?=$|\n|。|；)"
)


def extract_scripture_refs(text: str) -> list[str]:
    """提取文本中含圣经书卷名+章节数字的经节引用，返回去重保序列表。"""
    refs: list[str] = []
    seen: set[str] = set()
    for m in _BRACKET_RE.finditer(text):
        content = m.group(1)
        if _SCRIPTURE_REF_RE.search(content):
            key = m.group(0)
            if key not in seen:
                seen.add(key)
                refs.append(key)
    for m in _DASH_REF_RE.finditer(text):
        content = m.group(1).strip()
        if content and _SCRIPTURE_REF_RE.search(content) and content not in seen:
            seen.add(content)
            refs.append(content)
    return refs


def _split_title(title: str) -> tuple[str, str]:
    """
    title 按第一个全角空格「　」拆成：
    - book_title: 前半
    - message_title: 后半
    """
    t = (title or "").strip()
    if "　" in t:
        left, right = t.split("　", 1)
        return left.strip(), right.strip()
    return t, ""


def _parse_message_fields(doc_id: str) -> tuple[str, int | None]:
    """
    从 id 提取：
    - message_key: 去掉最后一段，例如 life_1-1-66 -> life_1-1
    - message_number: 中间段数字，例如 life_1-1-66 -> 1
    """
    did = (doc_id or "").strip()
    parts = did.split("-")
    message_key = "-".join(parts[:-1]) if len(parts) >= 2 else did

    message_number: int | None = None
    # 规则：先取 "_" 后半段，再按 "-" 分割取第二段数字
    # 例：life_1-1-66 -> 后半段 1-1-66 -> 第二段 1
    #     life_1-120-5 -> 后半段 1-120-5 -> 第二段 120
    if "_" in did:
        tail = did.split("_", 1)[1]
        segs = tail.split("-")
        if len(segs) >= 2:
            try:
                message_number = int(segs[1])
            except ValueError:
                message_number = None
    return message_key, message_number


def _to_chunk(item: dict[str, Any]) -> dict[str, Any]:
    doc_id = str(item.get("id", "")).strip()
    text = str(item.get("text", "") or "")
    en = str(item.get("en", "") or "")
    title = str(item.get("title", "") or "")
    source = item.get("source") if isinstance(item.get("source"), list) else []

    source_zh = str(source[0]) if len(source) > 0 and source[0] is not None else ""
    source_en = str(source[1]) if len(source) > 1 and source[1] is not None else ""

    book_title, message_title = _split_title(title)
    message_key, message_number = _parse_message_fields(doc_id)

    return {
        "chunk_id": doc_id,
        "text": text,
        "en": en,
        "book_title": book_title,
        "author": "李常受",
        "year": None,
        "message_key": message_key,
        "message_number": message_number,
        "message_title": message_title,
        "section_title": None,
        "paragraph_type": "text",
        "scripture_refs": extract_scripture_refs(text),
        "source_zh": source_zh,
        "source_en": source_en,
        "tokens": int(len(text) / 1.5),
        "original_ids": [doc_id],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert life_gen.json to KG-RAG chunks (1:1)")
    parser.add_argument("--input", required=True, help="输入 JSON 路径（life_gen.json）")
    parser.add_argument("--output", required=True, help="输出 chunks JSON 路径")
    args = parser.parse_args()

    in_path = Path(args.input)
    out_path = Path(args.output)

    if not in_path.exists():
        raise SystemExit(f"输入文件不存在: {in_path}")

    with open(in_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise SystemExit("输入 JSON 顶层必须是数组")

    chunks: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        if str(item.get("type", "")).strip() != "text":
            continue
        chunks.append(_to_chunk(item))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, ensure_ascii=False, indent=2)

    print(f"总输出 chunk 数: {len(chunks)}")


if __name__ == "__main__":
    main()
