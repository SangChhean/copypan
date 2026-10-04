# -*- coding: utf-8 -*-
"""正式步骤 Prompt 定稿。测试 Prompt 仍保留，不接入这些步骤。"""
from __future__ import annotations

from pathlib import Path

from . import (
    prompt0_select,
    prompt1_burden,
    prompt2_skeleton,
    prompt3_orig_skeleton,
    prompt4_diagnosis,
    prompt_test,
)

_REPO = Path(__file__).resolve().parents[4]
_EXTRACTED = _REPO / "docs" / "panai4_prompts" / "extracted"
_TEXTS = Path(__file__).resolve().parent / "texts"

REGISTRY = {
    "select": prompt0_select,
    "burden": prompt1_burden,
    "skeleton": prompt2_skeleton,
    "orig_skeleton": prompt3_orig_skeleton,
    "diagnosis": prompt4_diagnosis,
}

# 版本页展示顺序（含未启用的 select）
PROMPT_LIST_ORDER = ("select", "burden", "skeleton", "orig_skeleton", "diagnosis")

PROMPT_LABELS = {
    "select": "选词",
    "burden": "负担说明",
    "skeleton": "新生成的龙骨",
    "orig_skeleton": "原纲目的龙骨",
    "diagnosis": "对比诊断",
}

_OFFICIAL = (
    prompt0_select,
    prompt1_burden,
    prompt2_skeleton,
    prompt3_orig_skeleton,
    prompt4_diagnosis,
)


def _extracted_map(module) -> dict[str, str]:
    by_ver = getattr(module, "EXTRACTED_BY_VERSION", None)
    if by_ver:
        return dict(by_ver)
    return {module.CURRENT: module.EXTRACTED_NAME}


def assert_prompt_texts_match() -> None:
    """texts/ 与 extracted/ 下各版本正文必须逐字节一致。"""
    for module in _OFFICIAL:
        extracted = _extracted_map(module)
        for ver, filename in module.VERSIONS.items():
            if ver not in extracted:
                raise RuntimeError(f"{module.NAME} 版本 {ver} 缺少 EXTRACTED_BY_VERSION 映射")
            left = (_TEXTS / filename).read_bytes()
            right = (_EXTRACTED / extracted[ver]).read_bytes()
            if left != right:
                raise RuntimeError(
                    f"{module.NAME} {ver} 正文与 docs/panai4_prompts/extracted/{extracted[ver]} 不一致"
                )


def load_template(step: str, version: str | None = None) -> str:
    module = REGISTRY[step]
    ver = version or module.CURRENT
    filename = module.VERSIONS[ver]
    return (_TEXTS / filename).read_text(encoding="utf-8")


def current_prompt(step: str) -> dict:
    module = REGISTRY[step]
    source = getattr(module, "SOURCE_BY_VERSION", {}).get(module.CURRENT, module.SOURCE_DOCX)
    return {
        "name": module.NAME,
        "version": module.CURRENT,
        "system": "",
        "template": load_template(step),
        "source_docx": source,
        "source_title": module.SOURCE_TITLE,
        "enabled": bool(getattr(module, "ENABLED", True)),
    }


def prompt_version_meta(step: str, version: str) -> dict:
    module = REGISTRY[step]
    if version not in module.VERSIONS:
        raise KeyError(version)
    is_current = version == module.CURRENT
    step_enabled = bool(getattr(module, "ENABLED", True))
    # 步骤未接入 runner，或非当前版：标注未启用
    enabled = bool(step_enabled and is_current)
    source = getattr(module, "SOURCE_BY_VERSION", {}).get(version, module.SOURCE_DOCX)
    return {
        "version": version,
        "is_current": is_current,
        "enabled": enabled,
        "note": None if enabled else "未启用",
        "source_docx": source,
        "filename": module.VERSIONS[version],
    }


# ----- 占位符：按步骤 + 版本 -----
# select 沿用 sc.check_sc_placeholders 的必填集合（不强制 CH1/DEF_* 进 required，
# 但仍禁止出现主线专用占位符）。
PLACEHOLDERS_BY_VERSION: dict[str, dict[str, tuple[str, ...]]] = {
    "select": {
        "v1.0": ("query", "LIST_ZUINEI", "LIST_NEI", "LIST_WAI"),
    },
    "burden": {
        "v0.3": ("query",),
        "v1.0": ("query", "TERM_DEFS", "DEF_WAI", "DEF_NEI", "DEF_ZUINEI"),
    },
    "skeleton": {
        "v0.1": ("query", "burden"),
        "v0.2": ("query", "burden"),
        "v1.0": ("query", "burden"),
    },
    "orig_skeleton": {
        "v0.1": ("query", "original_outline"),
        "v0.2": ("query", "original_outline"),
    },
    "diagnosis": {
        "v0.1": ("query", "original_skeleton", "generated_skeleton"),
    },
}

# 兼容旧调用：按当前版
PLACEHOLDERS = {step: PLACEHOLDERS_BY_VERSION[step][REGISTRY[step].CURRENT] for step in PLACEHOLDERS_BY_VERSION}

_MAINLINE_TOKENS = ("query", "burden", "original_outline", "original_skeleton", "generated_skeleton")
_SC_TOKENS = (
    "query",
    "burden",
    "TERM_DEFS",
    "DEF_WAI",
    "DEF_NEI",
    "DEF_ZUINEI",
    "LIST_ZUINEI",
    "LIST_NEI",
    "LIST_WAI",
    "CH1",
)
_ALL_PLACEHOLDERS = tuple(dict.fromkeys(_MAINLINE_TOKENS + _SC_TOKENS))

OUTPUT_FORMAT_MARK = "【输出格式】"
BURDEN_MARK = "【负担说明】"


def check_placeholders(step: str, template: str, version: str | None = None) -> dict:
    """本步本版需要的填入位必须各出现一次；其它已知占位符不得误入。"""
    module = REGISTRY[step]
    ver = version or module.CURRENT
    by_ver = PLACEHOLDERS_BY_VERSION.get(step) or {}
    if ver not in by_ver:
        return {
            "ok": False,
            "required": [],
            "counts": {},
            "missing": [],
            "repeated": [],
            "unexpected": [],
            "problems": [f"步骤 {step} 无版本 {ver} 的占位符规则"],
            "warnings": [],
            "version": ver,
        }
    required = by_ver[ver]
    counts = {name: template.count("{" + name + "}") for name in _ALL_PLACEHOLDERS}
    missing = [name for name in required if counts[name] == 0]
    repeated = [name for name in required if counts[name] > 1]
    unexpected = [name for name in _ALL_PLACEHOLDERS if name not in required and counts[name] > 0]
    # select：模板里还会有 CH1/DEF_*（由运行时注入），不算「多了」
    if step == "select":
        allowed_extra = {"CH1", "DEF_WAI", "DEF_NEI", "DEF_ZUINEI"}
        unexpected = [n for n in unexpected if n not in allowed_extra]
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
        "version": ver,
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
    # 旧主线四步保持原行为；select / burden v1.0 的完整填槽由后续步骤接入
    needed = {
        "burden": {"query": topic},
        "skeleton": {"query": topic, "burden": burden},
        "orig_skeleton": {"query": topic, "original_outline": original_outline},
        "diagnosis": {
            "query": topic,
            "original_skeleton": original_skeleton,
            "generated_skeleton": generated_skeleton,
        },
    }.get(step)
    if needed is None:
        raise KeyError(f"render_user 尚未支持步骤 {step}")
    return _fill(template, needed)


assert_prompt_texts_match()

# 测试 Prompt 保留，供对照，不进入 REGISTRY。
_ = prompt_test
