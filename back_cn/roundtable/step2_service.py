# -*- coding: utf-8 -*-
"""Step 2：四版本内容生成 + Step 3：机械校验（含调整/重写双模式重试）。"""
from __future__ import annotations

import asyncio
import json
import logging
import re

from back_cn.roundtable.claude_service import call_sonnet5_high
from back_cn.roundtable.prompts import VERSION_CONFIG

logger = logging.getLogger(__name__)

ADJUSTABLE_REASONS = ("word_count", "ratio", "verbatim")
REWRITE_REASONS = ("json_parse", "outline_count", "qa_count", "api_error")

ADJUST_PROMPT_TEMPLATE = """以下是你上一次生成的内容（JSON格式）。

{instruction}

【最高优先级原则，调整时同样必须遵守】
除过渡衔接词外，所有实质内容句子必须100%取自原文，不可改写、不可自行总结概括。
补充内容时，必须从上面提供的原文中摘取真实存在的句子，不可自创。

请基于这份已有内容进行局部调整，不要整篇重写：
- 如果需要精简：删除相对次要的段落或句子，保留最核心的内容，不要通过缩写/改写单句来凑字数
- 如果需要补充：从原文中额外摘取相关句子补充进已有段落，或者增加一个新的小标题段落，同样必须100%取自原文
- 如果需要调整真理/生命比例：优先在"需要增加的那一类"里补充句子，或者删减"过多的那一类"里相对次要的句子，不要两类都大改
- 保持原有的结构、标题划分方式不变，只调整内容量和比例

已有内容（上一版草稿）：
{previous_json}

请输出调整后的完整JSON（格式要求与之前完全一致，只输出JSON，不输出其他文字）。
"""


def _extract_json(text: str) -> dict:
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    return json.loads(cleaned)


def _collect_paragraphs(data: dict) -> list[dict]:
    """收集所有 section 里的段落（不含 outline），用于字数/比例/摘取校验"""
    paras = []
    for sec in data.get("sections", []):
        for sub in sec.get("subsections", []):
            for p in sub.get("paragraphs", []):
                paras.append(p)
    return paras


def _count_total_words(data: dict) -> int:
    """含小标题、段落正文、每篇出处，不含 outline"""
    total = 0
    for sec in data.get("sections", []):
        for sub in sec.get("subsections", []):
            total += len(sub.get("heading", ""))
            for p in sub.get("paragraphs", []):
                total += len(p.get("text", ""))
        total += len(sec.get("source_line", ""))
    return total


def _build_word_count_instruction(
    word_count: int,
    word_range: tuple[int, int],
    soft_lo: float,
    soft_hi: float,
) -> str:
    """按与目标中位的相对差距，生成分级调整指令（小修 vs 大幅增删）。"""
    lo, hi = word_range
    target_mid = (lo + hi) / 2

    if word_count < soft_lo:
        deficit = soft_lo - word_count
        severity = deficit / target_mid
        if severity > 0.25:
            return (
                f"总字数 {word_count} 字，远低于目标区间 {lo}-{hi} 字，"
                f"缺口较大（约 {deficit:.0f} 字）。"
                f"这次需要大幅补充，建议新增一到两个完整的小标题段落，"
                f"或者大量扩充现有段落的原文摘取内容，"
                f"不要只是零星补几句——差距这么大，小修小补不够，"
                f"需要实质性增加内容量。"
            )
        return (
            f"总字数 {word_count} 字，目标区间 {lo}-{hi} 字，字数不足，"
            f"还需要增加约 {deficit:.0f} 字。请在保持100%原文摘取的前提下，"
            f"从原文中补充摘取更多相关句子，可以适当增加每篇的段落数量或者"
            f"每段引用更多原文内容，不要改写现有内容来凑字数。"
        )

    if word_count > soft_hi:
        excess = word_count - soft_hi
        severity = excess / target_mid
        if severity > 0.25:
            return (
                f"总字数 {word_count} 字，远高于目标区间 {lo}-{hi} 字，"
                f"超出较多（约 {excess:.0f} 字）。"
                f"这次需要大幅精简，建议直接删除一到两个相对次要的小标题段落"
                f"（整段删除，不是逐句微调），"
                f"优先保留最核心、最能代表原文重点的内容——"
                f"差距这么大，需要实质性削减，不要只删一两句意思意思。"
            )
        return (
            f"总字数 {word_count} 字，目标区间 {lo}-{hi} 字，超出约 {excess:.0f} 字。"
            f"请精简，删减掉相对次要的句子/段落，优先保留最核心的内容，"
            f"不要用缩写或改写的方式压缩字数——删句子而不是改句子。"
        )

    return ""


def _check_word_count_soft(
    word_count: int,
    word_range: tuple[int, int],
    slack: float = 0.04,
) -> tuple[bool, str]:
    """
    字数软区间校验：在硬目标 [lo, hi] 外侧各放宽 slack（默认 4%）。
    落在软区间内即通过；超出则按差距大小给出分级调整指令。
    """
    lo, hi = word_range
    soft_lo = float(round(lo * (1 - slack)))
    soft_hi = float(round(hi * (1 + slack)))
    if soft_lo <= word_count <= soft_hi:
        return True, ""
    return False, _build_word_count_instruction(
        word_count, word_range, soft_lo, soft_hi
    )


def _check_ratio(
    paras: list[dict],
    target: tuple[int, int],
    tolerance: float = 0.15,
) -> tuple[bool, str]:
    """真理/生命字数比例校验，允许一定容差（这个比例本来就是模糊目标，不是硬性等式）"""
    truth_chars = sum(len(p["text"]) for p in paras if p.get("type") == "真理")
    life_chars = sum(len(p["text"]) for p in paras if p.get("type") == "生命")
    total = truth_chars + life_chars
    if total == 0:
        return False, "没有任何段落标注 type"
    actual_ratio = truth_chars / total
    target_ratio = target[0] / (target[0] + target[1])
    if abs(actual_ratio - target_ratio) > tolerance:
        direction = (
            "增加真理句、减少生命句"
            if actual_ratio < target_ratio
            else "减少真理句、增加生命句"
        )
        return (
            False,
            f"真理:生命 实际约 {truth_chars}:{life_chars}，"
            f"目标比例约 {target[0]}:{target[1]}，请{direction}的篇幅占比",
        )
    return True, ""


def _build_ratio_instruction(
    truth_chars: int,
    life_chars: int,
    target: tuple[int, int],
    current_word_count: int,
) -> str:
    target_ratio = target[0] / (target[0] + target[1])
    total = truth_chars + life_chars
    actual_ratio = truth_chars / total if total else 0
    direction = (
        "增加真理句、减少生命句"
        if actual_ratio < target_ratio
        else "减少真理句、增加生命句"
    )
    return (
        f"真理:生命 实际约 {truth_chars}:{life_chars}，"
        f"目标比例约 {target[0]}:{target[1]}，请{direction}的篇幅占比。"
        f"当前总字数 {current_word_count} 字已经符合要求区间，调整比例时请做等量替换——"
        "增加某一类内容的同时，同步删减大致相当字数的另一类内容，"
        "确保调整后总字数基本保持不变，不要只做加法导致总字数又超标。"
    )


def _build_verbatim_instruction(bad_clauses: list[str]) -> str:
    examples = "\n".join(f"- 「{c[:60]}」" for c in bad_clauses[:5])
    return (
        "以下这些片段经核查，不是逐字摘自原文（可能被改写或概括了），"
        "必须逐一替换成原文中真实存在、意思相近的句子：\n"
        f"{examples}\n\n"
        "只替换上面列出的这些片段，不要改动草稿里其他部分"
        "（保持已经调好的总字数和真理/生命比例基本不变，"
        "替换时尽量选用字数相近的原文句子）。"
        "如果原文里实在找不到意思对应的句子，可以直接删掉这部分内容，"
        "不要保留改写版本凑数。"
    )


def _check_outline_count(outline: dict, max_items: int) -> tuple[bool, str]:
    count = 0
    for mp in outline.get("major_points", []):
        count += 1
        count += len(mp.get("minor_points", []))
    if count > max_items:
        return (
            False,
            f"鸟瞰纲目大点+中点合计当前 {count} 条，需要精简到不超过 {max_items} 条；"
            f"优先删除内容上有重叠或者相对次要的中点",
        )
    return True, ""


def _normalize_for_match(text: str) -> str:
    """把可能被换成分号的句号统一还原，方便做子串匹配"""
    return text.replace("；", "。").replace(";", "。")


def _check_verbatim(
    paras: list[dict],
    original_text: str,
    threshold: float = 0.85,
) -> tuple[bool, str, list[str]]:
    """
    返回值第三项：未匹配的完整片段列表（供调整模式使用，不是用来展示的截断预览）
    """
    original_normalized = _normalize_for_match(original_text)
    total_clauses = 0
    matched_clauses = 0
    bad_clauses: list[str] = []

    for p in paras:
        text = p.get("text", "")
        clauses = re.split(r"[。；]", text)
        for c in clauses:
            c = c.strip()
            if not c:
                continue
            total_clauses += 1
            if c in original_normalized or c in original_text:
                matched_clauses += 1
            else:
                bad_clauses.append(c)

    if total_clauses == 0:
        return False, "没有可校验的内容", []

    match_rate = matched_clauses / total_clauses
    if match_rate < threshold:
        preview = "；".join(bad_clauses[:3])[:120]
        return (
            False,
            f"原文摘取匹配率 {match_rate:.0%}，低于阈值 {threshold:.0%}，"
            f"例如未匹配到原文的片段：{preview}",
            bad_clauses,
        )
    return True, "", []


async def generate_version(
    version_key: str,
    original_texts: list[dict],
    unified_fields: dict,
    max_retries: int = 5,
) -> dict:
    config = VERSION_CONFIG[version_key]
    combined_original = "\n\n".join(
        f"【{t['book_name']} {t['title']}】\n" + "\n".join(t["paragraphs"])
        for t in original_texts
    )

    unified_block = f"""统一字段（已确定，不要重新生成）：
标题：{unified_fields['title']}
整体出处：{unified_fields['overall_source']}
"""

    last_error = None
    last_error_type = None
    previous_data = None
    previous_word_count: int | None = None
    retry_log: list[str] = []
    last_match_rate: float | None = None

    for attempt in range(max_retries + 1):
        use_adjust = (
            previous_data is not None and last_error_type in ADJUSTABLE_REASONS
        )
        if last_error is None:
            mode_label = "初写"
        elif use_adjust:
            mode_label = "调整"
        else:
            mode_label = "重写"

        print(
            f"[Step2] {config['label']} attempt {attempt + 1}/{max_retries + 1} "
            f"使用模式: {mode_label}, 触发原因: {last_error}"
        )
        if use_adjust:
            print(
                f"[Step2] {config['label']} attempt {attempt + 1} "
                f"调整模式使用的上版草稿字数: {previous_word_count}"
            )

        if use_adjust:
            task_text = ADJUST_PROMPT_TEMPLATE.format(
                instruction=last_error,
                previous_json=json.dumps(
                    previous_data, ensure_ascii=False, indent=2
                ),
            )
        else:
            task_text = unified_block
            if last_error:
                task_text += (
                    f"\n上一次生成有问题，请重新生成并修正：{last_error}\n"
                )
            else:
                task_text += "\n请根据以上原文生成本版本内容。\n"

        logger.info(
            "[Step2] %s attempt %s/%s mode=%s error_type=%s",
            config["label"],
            attempt + 1,
            max_retries + 1,
            mode_label,
            last_error_type,
        )

        try:
            raw, usage = await call_sonnet5_high(
                prompt=task_text,
                system=config["system"],
                max_tokens=16000,
                effort="medium",
                cacheable_prefix=combined_original,
            )
            print(
                f"[Step2] {config['label']} attempt {attempt + 1} usage: {usage}"
            )
        except RuntimeError as e:
            last_error = str(e)
            last_error_type = "api_error"
            retry_log.append(last_error)
            logger.warning("[Step2] %s API/内容异常: %s", config["label"], e)
            continue

        try:
            data = _extract_json(raw)
        except json.JSONDecodeError as e:
            last_error = f"JSON解析失败：{e}"
            last_error_type = "json_parse"
            retry_log.append(last_error)
            continue

        # 只要解析成功，就保留作为下一次可能的调整基底
        previous_data = data
        paras = _collect_paragraphs(data)
        word_count = _count_total_words(data)
        previous_word_count = word_count
        lo, hi = config["word_range"]
        print(
            f"[Step2] {config['label']} attempt {attempt + 1} "
            f"字数={word_count} 目标={lo}-{hi} mode={mode_label}"
        )

        word_ok, word_msg = _check_word_count_soft(word_count, config["word_range"])
        if not word_ok:
            last_error = word_msg
            last_error_type = "word_count"
            retry_log.append(last_error)
            continue

        if config["ratio"]:
            truth_chars = sum(
                len(p["text"]) for p in paras if p.get("type") == "真理"
            )
            life_chars = sum(
                len(p["text"]) for p in paras if p.get("type") == "生命"
            )
            total_tl = truth_chars + life_chars
            if total_tl == 0:
                last_error = "没有任何段落标注 type"
                last_error_type = "ratio"
                retry_log.append(last_error)
                continue
            target_ratio = config["ratio"][0] / (
                config["ratio"][0] + config["ratio"][1]
            )
            actual_ratio = truth_chars / total_tl
            if abs(actual_ratio - target_ratio) > 0.15:
                last_error = _build_ratio_instruction(
                    truth_chars, life_chars, config["ratio"], word_count
                )
                last_error_type = "ratio"
                retry_log.append(last_error)
                continue

        if config["has_outline"]:
            outline = data.get("outline", {})
            if not outline.get("major_points"):
                last_error = "缺少鸟瞰纲目"
                last_error_type = "outline_count"
                retry_log.append(last_error)
                continue
            outline_ok, outline_msg = _check_outline_count(
                outline, config["max_outline_items"]
            )
            if not outline_ok:
                last_error = outline_msg
                last_error_type = "outline_count"
                retry_log.append(last_error)
                continue

        verbatim_ok, verbatim_msg, bad_clauses = _check_verbatim(
            paras, combined_original
        )
        if not verbatim_ok:
            last_error = (
                _build_verbatim_instruction(bad_clauses)
                if bad_clauses
                else verbatim_msg
            )
            last_error_type = "verbatim"
            retry_log.append(last_error)
            continue
        last_match_rate = 1.0

        if len(data.get("qa", [])) != 3:
            last_error = "彼此问互相答数量不是3题"
            last_error_type = "qa_count"
            retry_log.append(last_error)
            continue

        return {
            "version_key": version_key,
            "label": config["label"],
            "data": data,
            "word_count": word_count,
            "attempts": attempt + 1,
            "retry_log": retry_log,
            "verbatim_match_rate": last_match_rate,
        }

    raise RuntimeError(
        f"{config['label']} 生成失败，已重试 {max_retries} 次，最后错误：{last_error}"
    )


async def generate_all_versions(
    original_texts: list[dict],
    unified_fields: dict,
    version_keys: list[str] | None = None,
) -> dict:
    """
    version_keys: 要生成的版本 key 列表（'truth'/'gospel'/'life'/'elderly'），
    传 None 时默认生成全部四个（保持向后兼容，之前的测试脚本不用改）。
    指定版本可并发生成，互不依赖；单个失败不掩盖其他版本结果。
    """
    keys_to_generate = (
        list(version_keys) if version_keys else list(VERSION_CONFIG.keys())
    )
    invalid = [k for k in keys_to_generate if k not in VERSION_CONFIG]
    if invalid:
        raise ValueError(f"未知的版本 key：{invalid}")

    settled = await asyncio.gather(
        *[
            generate_version(key, original_texts, unified_fields)
            for key in keys_to_generate
        ],
        return_exceptions=True,
    )
    results: dict = {}
    errors: list[str] = []
    for key, item in zip(keys_to_generate, settled):
        if isinstance(item, Exception):
            errors.append(f"{VERSION_CONFIG[key]['label']}: {item}")
        else:
            results[key] = item
    if errors:
        ok_labels = [results[k]["label"] for k in results]
        raise RuntimeError(
            "部分版本生成失败。\n"
            f"成功: {ok_labels or '无'}\n"
            f"失败:\n- " + "\n- ".join(errors)
        )
    return results
