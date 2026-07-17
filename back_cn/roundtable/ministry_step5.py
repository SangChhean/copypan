# -*- coding: utf-8 -*-
"""职事书报追求材料制作：Word 文档生成（无版本标签文件名）。"""
from __future__ import annotations

from pathlib import Path

from back_cn.roundtable.docx_builder import generate_docx
from back_cn.roundtable.step5_service import (
    _resolve_output_dir,
    _resolve_templates_dir,
    _safe_filename_part,
)

TRUTH_TEMPLATE = "真理加强版.docx"
VERSION_KEY = "truth"


def build_ministry_file(
    unified_fields: dict,
    version_data: dict,
    week_number: str | None,
) -> Path:
    """生成追求纲要 Word 文档，文件名不含内部版本标签。"""
    templates_dir = _resolve_templates_dir()
    output_dir = _resolve_output_dir()
    template_path = templates_dir / TRUTH_TEMPLATE
    if not template_path.exists():
        raise FileNotFoundError(
            f"模版文件未找到：{template_path}。"
            f"请将「真理加强版.docx」放到该目录，或设置环境变量 CN_ROUNDTABLE_TEMPLATES_DIR"
        )
    output_dir.mkdir(parents=True, exist_ok=True)

    topic = _safe_filename_part((unified_fields.get("topic") or "").strip())
    if week_number:
        base_name = f"第{week_number}周　{topic}"
    else:
        base_name = topic
    docx_name = f"{_safe_filename_part(base_name)}.docx"
    return generate_docx(
        VERSION_KEY,
        unified_fields,
        version_data,
        template_path,
        output_dir / docx_name,
    )
