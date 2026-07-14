# -*- coding: utf-8 -*-
"""Step 5：套用正式模版生成各版本 docx / pdf。"""
from __future__ import annotations

from pathlib import Path

from back_cn.roundtable.border_service import add_border_for_version
from back_cn.roundtable.docx_builder import VERSION_TEMPLATE_FILES, generate_docx
from back_cn.roundtable.docx_to_pdf import convert_docx_to_pdf

TEMPLATES_DIR = Path("/opt/pansearch/data/cn_roundtable/templates")
BORDERS_DIR = Path("/opt/pansearch/data/cn_roundtable/borders")
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
    file_format: str,
    week_number: str | None,
) -> Path:
    """file_format: 'docx' 或 'pdf'"""
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

    # 边框是硬性条件，每次都加，不做用户开关
    add_border_for_version(docx_path, version_key, BORDERS_DIR)

    if file_format == "docx":
        return docx_path

    pdf_path = convert_docx_to_pdf(docx_path, OUTPUT_DIR)
    docx_path.unlink(missing_ok=True)  # pdf 模式下中间产物 docx 不保留
    return pdf_path
