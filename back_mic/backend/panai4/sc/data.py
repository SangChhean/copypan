# -*- coding: utf-8 -*-
"""加载三档名单、3a 定义、参考文本；构建默认提示词。"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from panai4.prompts import load_template

from .config import (
    PLAIN_NEW,
    PLAIN_OLD,
    TIER_ORDER,
    export_3a_path,
    prompts_dir,
    ref_dir,
    tiers_json_path,
)
from .prompt_v3 import (
    build_plain_prompt_default_v3,
    build_ref_prompt_default_v2,
    build_ref_prompt_default_v3,
)


@dataclass
class ScData:
    tiers: dict[str, list[str]]
    tier_of: dict[str, str]
    content_3a: dict[str, str | None]
    names: list[str]
    ch1: str
    def_wai: str
    def_nei: str
    def_zui: str
    select_prompt_default: str
    plain_prompt_default: str
    ref_prompt_default: str
    ref_block_template: str
    mismatch: dict = field(default_factory=dict)
    load_error: str | None = None


_cache: ScData | None = None


def _read_txt(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _fill(template: str, mapping: dict[str, str]) -> str:
    out = template
    for key, value in mapping.items():
        out = out.replace("{" + key + "}", value)
    return out


def _exact_replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}：目标原句出现 {count} 次（期望 1），拒绝生成加词条定义版默认值")
    return text.replace(old, new, 1)


def build_ref_prompt_v1_block_only(plain_v03: str, ref_block: str) -> str:
    """只加参考块 + PLAIN 原句替换（v1 留档，无第二步/依据类型两处改动）。"""
    patched = _exact_replace_once(plain_v03, PLAIN_OLD, PLAIN_NEW, label="Prompt1 v0.3 PLAIN 原句")
    return ref_block + patched


def build_ref_prompt_default_v2_outline(plain_v03: str, ref_block: str) -> str:
    """参考优先版（v2）留档：v1 + 第二步四轮 + 依据类型四种。"""
    return build_ref_prompt_default_v2(plain_v03, ref_block)


def build_ref_prompt_default(plain_v03: str, ref_block: str) -> str:
    """直写版（v3）加词条定义版默认模板。"""
    return build_ref_prompt_default_v3(plain_v03, ref_block)


def ensure_ref_prompt_v1_archive(plain_v03: str, ref_block: str) -> Path:
    """把 v1（仅参考块）写入 prompts/ref_prompt_v1_block_only.txt（不存在或内容过期则覆写）。"""
    path = prompts_dir() / "ref_prompt_v1_block_only.txt"
    content = build_ref_prompt_v1_block_only(plain_v03, ref_block)
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        path.write_text(content, encoding="utf-8")
    return path


def ensure_ref_prompt_v2_archive(plain_v03: str, ref_block: str) -> Path:
    """把 v2（参考优先版）写入 prompts/ref_prompt_v2_outline.txt 留档。"""
    path = prompts_dir() / "ref_prompt_v2_outline.txt"
    content = build_ref_prompt_default_v2_outline(plain_v03, ref_block)
    if not path.exists() or path.read_text(encoding="utf-8") != content:
        path.write_text(content, encoding="utf-8")
    return path


def load_sc_data(*, force: bool = False) -> ScData:
    global _cache
    if _cache is not None and not force:
        return _cache

    tiers_path = tiers_json_path()
    a3_path = export_3a_path()
    rdir = ref_dir()
    missing = [str(p) for p in (tiers_path, a3_path, rdir / "ch1.txt", rdir / "def_外在.txt", rdir / "def_内在.txt", rdir / "def_最内在.txt") if not p.exists()]
    if missing:
        data = ScData(
            tiers={t: [] for t in TIER_ORDER},
            tier_of={},
            content_3a={},
            names=[],
            ch1="",
            def_wai="",
            def_nei="",
            def_zui="",
            select_prompt_default="",
            plain_prompt_default="",
            ref_prompt_default="",
            ref_block_template="",
            load_error="缺少数据文件：\n" + "\n".join(missing),
        )
        _cache = data
        return data

    tiers_raw = json.loads(tiers_path.read_text(encoding="utf-8-sig"))
    tiers = {k: list(tiers_raw.get(k) or []) for k in ("外在", "内在", "最内在")}
    # API / meta 用 最内在→内在→外在 展示顺序，但 JSON 键是 外在/内在/最内在
    tier_of: dict[str, str] = {}
    for tier in ("外在", "内在", "最内在"):
        for name in tiers[tier]:
            tier_of[name] = tier
    names = list(tier_of.keys())

    rows = json.loads(a3_path.read_text(encoding="utf-8-sig"))
    content_3a: dict[str, str | None] = {}
    for row in rows:
        title = str(row.get("title") or "").strip()
        raw = row.get("content_3a")
        if raw is None or (isinstance(raw, str) and raw.strip() == ""):
            content_3a[title] = None
        else:
            content_3a[title] = raw if isinstance(raw, str) else str(raw)

    set_tiers = set(names)
    set_3a = set(content_3a)
    mismatch = {
        "only_tiers": sorted(set_tiers - set_3a),
        "only_3a": sorted(set_3a - set_tiers),
        "equal": set_tiers == set_3a,
    }

    ch1 = _read_txt(rdir / "ch1.txt")
    def_wai = _read_txt(rdir / "def_外在.txt")
    def_nei = _read_txt(rdir / "def_内在.txt")
    def_zui = _read_txt(rdir / "def_最内在.txt")

    plain_v03 = load_template("burden", "v0.3")
    select_tpl = _read_txt(prompts_dir() / "select_prompt.txt")
    ref_block = _read_txt(prompts_dir() / "ref_block.txt")
    ensure_ref_prompt_v1_archive(plain_v03, ref_block)
    ensure_ref_prompt_v2_archive(plain_v03, ref_block)
    select_default = select_tpl  # keep all placeholders
    plain_default = build_plain_prompt_default_v3(plain_v03)
    ref_default = build_ref_prompt_default(plain_v03, ref_block)  # still has {DEF_*} {TERM_DEFS} {query}

    data = ScData(
        tiers=tiers,
        tier_of=tier_of,
        content_3a=content_3a,
        names=sorted(names),
        ch1=ch1,
        def_wai=def_wai,
        def_nei=def_nei,
        def_zui=def_zui,
        select_prompt_default=select_default,
        plain_prompt_default=plain_default,
        ref_prompt_default=ref_default,
        ref_block_template=ref_block,
        mismatch=mismatch,
        load_error=None,
    )
    _cache = data
    return data


def list_lines(names: list[str]) -> str:
    return "\n".join(names)


def fill_select_prompt(template: str, topic: str, data: ScData) -> str:
    return _fill(
        template,
        {
            "CH1": data.ch1.rstrip("\n"),
            "DEF_WAI": data.def_wai.rstrip("\n"),
            "DEF_NEI": data.def_nei.rstrip("\n"),
            "DEF_ZUINEI": data.def_zui.rstrip("\n"),
            "LIST_ZUINEI": list_lines(data.tiers["最内在"]),
            "LIST_NEI": list_lines(data.tiers["内在"]),
            "LIST_WAI": list_lines(data.tiers["外在"]),
            "query": topic,
        },
    )


def build_term_defs(
    final_terms: list[str], data: ScData
) -> tuple[str, list[str], list[str], int, int]:
    """返回 (TERM_DEFS, skipped, merged, defs_chars, defs_sent_count)。

    最内在 / 内在：〔档〕名 + content_3a（null 跳过；同内容合并）。
    外在：不取 3a，末尾单独一行「另选的外在词条（仅名，无定义）：A、B、C……」。
    defs_chars / defs_sent_count 只计实际送入定义的内在+最内在块。
    """
    skipped: list[str] = []
    merged: list[str] = []
    by_tier: dict[str, list[str]] = {t: [] for t in TIER_ORDER}
    for name in final_terms:
        tier = data.tier_of.get(name)
        if tier in by_tier:
            by_tier[tier].append(name)
        else:
            skipped.append(name)

    blocks: list[str] = []
    seen_content: dict[str, str] = {}  # content -> first name
    for tier in ("最内在", "内在"):
        for name in by_tier[tier]:
            content = data.content_3a.get(name)
            if content is None or not str(content).strip():
                skipped.append(name)
                continue
            if content in seen_content:
                merged.append(name)
                continue
            seen_content[content] = name
            blocks.append(f"〔{tier}〕{name}\n{content}")

    parts: list[str] = []
    if blocks:
        parts.append("\n\n".join(blocks))
    outer_names = by_tier["外在"]
    if outer_names:
        parts.append("另选的外在词条（仅名，无定义）：" + "、".join(outer_names))
    text = "\n\n".join(parts)
    if text:
        text += "\n"
    defs_body = ("\n\n".join(blocks) + "\n") if blocks else ""
    return text, skipped, merged, len(defs_body), len(blocks)


def fill_ref_prompt(template: str, topic: str, term_defs: str, data: ScData) -> str:
    return _fill(
        template,
        {
            "DEF_WAI": data.def_wai.rstrip("\n"),
            "DEF_NEI": data.def_nei.rstrip("\n"),
            "DEF_ZUINEI": data.def_zui.rstrip("\n"),
            "TERM_DEFS": term_defs.rstrip("\n"),
            "query": topic,
        },
    )


def fill_plain_prompt(template: str, topic: str) -> str:
    return template.replace("{query}", topic)


def remaining_placeholders(text: str) -> list[str]:
    import re

    return sorted(set(re.findall(r"\{([A-Za-z_]+)\}", text)))


def check_sc_placeholders(kind: str, template: str) -> dict:
    """kind: select | plain | ref"""
    required = {
        "select": ("query", "LIST_ZUINEI", "LIST_NEI", "LIST_WAI"),
        "plain": ("query",),
        "ref": ("TERM_DEFS", "query"),
    }[kind]
    problems = []
    for name in required:
        token = "{" + name + "}"
        n = template.count(token)
        if n == 0:
            problems.append(f"缺少 {token}")
        elif n > 1:
            problems.append(f"{token} 出现 {n} 次，只能 1 次")
    return {"ok": not problems, "problems": problems, "required": list(required)}
