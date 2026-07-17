# -*- coding: utf-8 -*-
"""Step 5：套用正式模版生成各版本 Word 文档。"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

from back_cn.roundtable.docx_builder import VERSION_TEMPLATE_FILES, generate_docx

# 服务器默认路径；本地开发用 env 或仓库内 data/cn_roundtable/templates 回退
_SERVER_TEMPLATES = Path("/opt/pansearch/data/cn_roundtable/templates")
_LOCAL_TEMPLATES = (
    Path(__file__).resolve().parent.parent / "data" / "cn_roundtable" / "templates"
)


def _resolve_templates_dir() -> Path:
    env = os.getenv("CN_ROUNDTABLE_TEMPLATES_DIR", "").strip()
    if env:
        return Path(env)
    if _SERVER_TEMPLATES.is_dir():
        return _SERVER_TEMPLATES
    return _LOCAL_TEMPLATES


def _resolve_output_dir() -> Path:
    env = os.getenv("CN_ROUNDTABLE_OUTPUT_DIR", "").strip()
    if env:
        return Path(env)
    if os.name == "nt":
        return Path(tempfile.gettempdir()) / "cn_roundtable_output"
    return Path("/tmp/cn_roundtable_output")


TEMPLATES_DIR = _resolve_templates_dir()
OUTPUT_DIR = _resolve_output_dir()

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
    templates_dir = _resolve_templates_dir()
    output_dir = _resolve_output_dir()
    template_path = templates_dir / VERSION_TEMPLATE_FILES[version_key]
    if not template_path.exists():
        raise FileNotFoundError(
            f"模版文件未找到：{template_path}。"
            f"请将模版放到该目录，或设置环境变量 CN_ROUNDTABLE_TEMPLATES_DIR"
        )
    output_dir.mkdir(parents=True, exist_ok=True)

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
        output_dir / docx_name,
    )

    # 边框已经预先烧进模版文件本身，这一步不再需要
    # add_border_for_version(docx_path, version_key, BORDERS_DIR)

    return docx_path
