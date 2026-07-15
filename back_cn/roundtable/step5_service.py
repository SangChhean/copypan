# -*- coding: utf-8 -*-
"""Step 5：套用正式模版生成各版本 Word 文档。"""
from __future__ import annotations

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
    base_name = f"第{week_number}周_{label}" if week_number else label
    docx_name = f"{base_name}.docx"
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
