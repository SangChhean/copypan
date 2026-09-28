# -*- coding: utf-8 -*-
"""正式步骤使用四份定稿。测试 Prompt 仍保留，不接入这些步骤。"""
from __future__ import annotations

from pathlib import Path

from . import prompt1_burden, prompt2_skeleton, prompt3_orig_skeleton, prompt4_diagnosis, prompt_test

_REPO = Path(__file__).resolve().parents[4]
_EXTRACTED = _REPO / "docs" / "panai4_prompts" / "extracted"
_TEXTS = Path(__file__).resolve().parent / "texts"

REGISTRY = {
    "burden": prompt1_burden,
    "skeleton": prompt2_skeleton,
    "orig_skeleton": prompt3_orig_skeleton,
    "diagnosis": prompt4_diagnosis,
}

_OFFICIAL = (
    prompt1_burden,
    prompt2_skeleton,
    prompt3_orig_skeleton,
    prompt4_diagnosis,
)


def assert_prompt_texts_match() -> None:
    """texts/ 下的正文必须与已核对的 extracted/ 逐字节一致。"""
    for module in _OFFICIAL:
        left = (_TEXTS / module.VERSIONS[module.CURRENT]).read_bytes()
        right = (_EXTRACTED / module.EXTRACTED_NAME).read_bytes()
        if left != right:
            raise RuntimeError(
                f"{module.NAME} 正文与 docs/panai4_prompts/extracted/{module.EXTRACTED_NAME} 不一致"
            )


def load_template(step: str, version: str | None = None) -> str:
    module = REGISTRY[step]
    ver = version or module.CURRENT
    filename = module.VERSIONS[ver]
    return (_TEXTS / filename).read_text(encoding="utf-8")


def current_prompt(step: str) -> dict:
    module = REGISTRY[step]
    return {
        "name": module.NAME,
        "version": module.CURRENT,
        "system": "",
        "template": load_template(step),
        "source_docx": module.SOURCE_DOCX,
        "source_title": module.SOURCE_TITLE,
    }


PLACEHOLDERS = {
    "burden": ("query",),
    "skeleton": ("query", "burden"),
    "orig_skeleton": ("query", "original_outline"),
    "diagnosis": ("query", "original_skeleton", "generated_skeleton"),
}
_ALL_PLACEHOLDERS = ("query", "burden", "original_outline", "original_skeleton", "generated_skeleton")
OUTPUT_FORMAT_MARK = "【输出格式】"
BURDEN_MARK = "【负担说明】"


def check_placeholders(step: str, template: str) -> dict:
    """本步需要的填入位必须各出现一次；其他步骤的填入位不得出现。"""
    required = PLACEHOLDERS[step]
    counts = {name: template.count("{" + name + "}") for name in _ALL_PLACEHOLDERS}
    missing = [name for name in required if counts[name] == 0]
    repeated = [name for name in required if counts[name] > 1]
    unexpected = [name for name in _ALL_PLACEHOLDERS if name not in required and counts[name] > 0]
    problems = []
    for name in missing:
        problems.append(f"缺少 {{{name}}}")
    for name in repeated:
        problems.append(f"{{{name}}} 出现 {counts[name]} 次，只能 1 次")
    for name in unexpected:
        problems.append(f"多了 {{{name}}}（这份 Prompt 不用）")
    warnings = []
    if step == "burden":
        cut = template.rfind(OUTPUT_FORMAT_MARK)
        tail = template[cut:] if cut >= 0 else template
        if BURDEN_MARK not in tail:
            warnings.append("输出格式里没有【负担说明】：新生成的龙骨会因截取不到负担说明而失败。")
    return {
        "ok": not problems,
        "required": list(required),
        "counts": {name: counts[name] for name in required},
        "missing": missing,
        "repeated": repeated,
        "unexpected": unexpected,
        "problems": problems,
        "warnings": warnings,
    }


def _fill(template: str, values: dict[str, str]) -> str:
    text = template
    for key, value in values.items():
        token = "{" + key + "}"
        if token not in text:
            raise KeyError(token)
        text = text.replace(token, value)
    return text


def render_user(
    step: str,
    topic: str,
    original_outline: str = "",
    burden: str = "",
    original_skeleton: str = "",
    generated_skeleton: str = "",
    context_materials: str = "",
    template: str | None = None,
) -> str:
    """整份正文作为一条 user 消息。template 为空时用当前版。context_materials 预留，本步不插入。"""
    del context_materials
    if template is None:
        template = load_template(step)
    needed = {
        "burden": {"query": topic},
        "skeleton": {"query": topic, "burden": burden},
        "orig_skeleton": {"query": topic, "original_outline": original_outline},
        "diagnosis": {
            "query": topic,
            "original_skeleton": original_skeleton,
            "generated_skeleton": generated_skeleton,
        },
    }[step]
    return _fill(template, needed)


assert_prompt_texts_match()

# 测试 Prompt 保留，供对照，不进入 REGISTRY。
_ = prompt_test
