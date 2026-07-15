# -*- coding: utf-8 -*-
"""Step 5：套用正式模版生成各版本 Word 文档。"""
from __future__ import annotations

import re
from pathlib import Path

from back_cn.roundtable.docx_builder import VERSION_TEMPLATE_FILES, generate_docx

TEMPLATES_DIR = Path("/opt/pansearch/data/cn_roundtable/templates")
OUTPUT_DIR = Path("/tmp/cn_roundtable_output")

VERSION_LABELS = {
    "truth": "真理加强版",
    "gospel": "福音加强版",
    "life": "生命加强版",
    "elderly": "年长放大版",
}

_WINDOWS_FORBIDDEN = re.compile(r'[\\/:*?"<>|]')


def _safe_filename_part(text: str) -> str:
    """去掉 Windows 文件名不允许的字符。"""
    cleaned = _WINDOWS_FORBIDDEN.sub("", text or "").strip()
    return cleaned or "未命名"


def _extract_topic(unified_fields: dict) -> str:
    """优先用 step1 返回的纯题目 topic；缺失时再从完整 title 剥掉「第X周　」前缀。"""
    topic = (unified_fields.get("topic") or "").strip()
    if topic:
        return topic
    title = (unified_fields.get("title") or "").strip()
    return re.sub(r"^第.+?周[　\s]*", "", title).strip() or title


def build_version_file(
    version_key: str,
    unified_fields: dict,
    version_data: dict,
    week_number: str | None,
) -> Path:
    """为一个版本生成 Word 文档。"""
    template_path = TEMPLATES_DIR / VERSION_TEMPLATE_FILES[version_key]
    if not template_path.exists():
        raise FileNotFoundError(f"模版文件未找到：{template_path}，请确认服务器路径")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    label = VERSION_LABELS[version_key]
    topic = _safe_filename_part(_extract_topic(unified_fields))
    if week_number:
        base_name = f"第{week_number}周　{topic}（{label}）"
    else:
        base_name = f"{topic}（{label}）"
    docx_name = f"{_safe_filename_part(base_name)}.docx"
    docx_path = generate_docx(
        version_key,
        unified_fields,
        version_data,
        template_path,
        OUTPUT_DIR / docx_name,
    )

    # 边框已经预先烧进模版文件本身，这一步不再需要
    # add_border_for_version(docx_path, version_key, BORDERS_DIR)

    return docx_path
