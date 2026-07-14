# -*- coding: utf-8 -*-
"""DOCX → PDF 转换（LibreOffice），供 Step 5 / 后续步骤复用。"""
from __future__ import annotations

import subprocess
from pathlib import Path

# 与 back_shared/format_utils/format_outline.py、ai_service 一致：用 PATH 里的 libreoffice
_PDF_EXPORT_OPTS = 'pdf:writer_pdf_Export:{"SelectPdfVersion":{"type":"long","value":"2"}}'


def convert_docx_to_pdf(docx_path: Path, output_dir: Path) -> Path:
    """
    用 libreoffice 把 docx 转成 pdf，返回生成的 pdf 路径。
    转换失败（未安装、超时等）会抛出异常，调用方需要处理。
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    which = subprocess.run(
        ["which", "libreoffice"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    if which.returncode != 0:
        raise RuntimeError("libreoffice 未安装或不在 PATH 中")

    result = subprocess.run(
        [
            "libreoffice",
            "--headless",
            "--convert-to",
            _PDF_EXPORT_OPTS,
            "--outdir",
            str(output_dir),
            str(docx_path),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if result.returncode != 0:
        raise RuntimeError(f"docx转pdf失败: {result.stderr or result.stdout}")
    pdf_path = output_dir / (docx_path.stem + ".pdf")
    if not pdf_path.exists():
        raise RuntimeError(f"转换后未找到预期的pdf文件: {pdf_path}")
    return pdf_path
