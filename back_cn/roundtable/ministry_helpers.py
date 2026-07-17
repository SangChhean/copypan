# -*- coding: utf-8 -*-
"""职事书报追求材料制作：字段映射与后处理（不改共享 Step1/Step2 代码）。"""
from __future__ import annotations

# 固定占位，仅供 compute_topic_and_source / 喂模型标题行绕开正则崩溃
PLACEHOLDER_TITLE = "第一篇"
# 书名为空时喂给模型的 book_name 占位（会进 combined_original，source_line 会被覆盖）
PLACEHOLDER_BOOK_NAME = "职事信息"

DISPLAY_LABEL = "职事书报追求纲要"


def build_original_texts(text: str, book_name: str) -> list[dict]:
    """构造单元素 original_texts。"""
    book = (book_name or "").strip() or PLACEHOLDER_BOOK_NAME
    return [
        {
            "book_name": book,
            "title": PLACEHOLDER_TITLE,
            "paragraphs": [text],
        }
    ]


def build_overall_source(book_name: str, chapter_info: str) -> str:
    """顶部整体出处行。"""
    book = (book_name or "").strip()
    chapter = (chapter_info or "").strip()
    if book and chapter:
        return f"（摘自{book}，{chapter}）"
    if book:
        return f"（摘自{book}）"
    if chapter:
        return f"（摘自{chapter}）"
    return ""


def build_section_source_line(book_name: str, chapter_info: str) -> str:
    """每篇摘要末尾出处小字。"""
    book = (book_name or "").strip()
    chapter = (chapter_info or "").strip()
    if book and chapter:
        return f"（{book}，{chapter}）"
    if book:
        return f"（{book}）"
    if chapter:
        return f"（{chapter}）"
    return ""


def apply_unified_field_overrides(
    unified_fields: dict,
    *,
    outline_title: str,
    week_number: str | None,
    book_name: str,
    chapter_info: str,
) -> None:
    """覆盖 Step1 算出的 title / topic / overall_source；verses / hymn 保留。"""
    topic = outline_title.strip()
    week = (week_number or "").strip() or None
    unified_fields["title"] = f"第{week}周　{topic}" if week else topic
    unified_fields["topic"] = topic
    unified_fields["overall_source"] = build_overall_source(book_name, chapter_info)


def patch_source_lines(data: dict, book_name: str, chapter_info: str) -> None:
    """覆盖 sections 里每篇的 source_line（须在生成预览之前调用）。"""
    source_line = build_section_source_line(book_name, chapter_info)
    for sec in data.get("sections", []):
        sec["source_line"] = source_line
