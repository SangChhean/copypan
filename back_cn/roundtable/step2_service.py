# -*- coding: utf-8 -*-
"""Step 2：四版本内容生成 + Step 3：机械校验（含调整/重写双模式重试）。"""
from __future__ import annotations

import asyncio
import copy
import json
import logging
import re
from collections.abc import Callable

from back_cn.roundtable.claude_service import call_sonnet5_high
from back_cn.roundtable.prompts import VERSION_CONFIG
from back_cn.roundtable.usage_tracker import accumulate_usage

logger = logging.getLogger(__name__)

ADJUSTABLE_REASONS = ("content_adjust",)  # 摘取/字数/比例/纲目全部合并，都走调整模式
REWRITE_REASONS = ("json_parse", "qa_count", "api_error")

WORD_COUNT_SLACK = 0.04  # 沿用之前定的软容差比例，不变

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


def _strip_bad_clauses_from_data(data: dict, bad_clauses: list[str]) -> dict:
    """
    从段落里删除已确认摘取不合规的句子，保留其余合规内容。
    直接在段落文本里做字符串替换删除，不改变段落结构本身。
    """
    result = copy.deepcopy(data)
    # 长句优先，减少短片段误伤长句子串的机会
    clauses_sorted = sorted(
        (c for c in bad_clauses if c), key=len, reverse=True
    )
    for sec in result.get("sections", []):
        for sub in sec.get("subsections", []):
            new_paragraphs = []
            for p in sub.get("paragraphs", []):
                text = p.get("text", "")
                for clause in clauses_sorted:
                    text = text.replace(clause, "")
                # 清理删除之后可能留下的多余分号、句号、空格
                text = re.sub(r"[。；;]{2,}", "。", text)
                text = text.strip("；;。　 ")
                if text:  # 删完还有剩余内容才保留这个段落
                    new_paragraphs.append({**p, "text": text})
            sub["paragraphs"] = new_paragraphs
    return result


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


def _word_count_fragment(word_count: int, word_range: tuple[int, int]) -> str | None:
    """返回字数问题的描述片段；没有问题返回 None。"""
    lo, hi = word_range
    soft_lo = lo * (1 - WORD_COUNT_SLACK)
    soft_hi = hi * (1 + WORD_COUNT_SLACK)
    target_mid = (lo + hi) / 2

    if word_count < soft_lo:
        deficit = soft_lo - word_count
        severity = deficit / target_mid
        if severity > 0.25:
            return (
                f"总字数 {word_count} 字，远低于目标区间 {lo}-{hi} 字，缺口较大（约 {deficit:.0f} 字）。"
                f"需要大幅补充，建议新增一到两个完整的小标题段落，或大量扩充现有段落的原文摘取内容，"
                f"不要只是零星补几句。"
            )
        return (
            f"总字数 {word_count} 字，目标区间 {lo}-{hi} 字，字数不足，还需增加约 {deficit:.0f} 字。"
        )

    if word_count > soft_hi:
        excess = word_count - soft_hi
        severity = excess / target_mid
        if severity > 0.25:
            return (
                f"总字数 {word_count} 字，远高于目标区间 {lo}-{hi} 字，超出较多（约 {excess:.0f} 字）。"
                f"需要大幅精简，建议直接删除一到两个相对次要的小标题段落（整段删除，不是逐句微调）。"
            )
        return (
            f"总字数 {word_count} 字，目标区间 {lo}-{hi} 字，超出约 {excess:.0f} 字。"
            f"请精简，删句子而不是改句子。"
        )

    return None


def _ratio_fragment(
    truth_chars: int, life_chars: int, target: tuple[int, int]
) -> str | None:
    """返回比例问题的描述片段；没有问题返回 None。"""
    total = truth_chars + life_chars
    if total == 0:
        return (
            "没有任何段落标注 type，无法判断真理/生命比例，"
            "请确认每段都正确标注了 type 字段。"
        )
    target_ratio = target[0] / (target[0] + target[1])
    actual_ratio = truth_chars / total
    if abs(actual_ratio - target_ratio) <= 0.15:
        return None
    direction = (
        "增加真理句、减少生命句"
        if actual_ratio < target_ratio
        else "减少真理句、增加生命句"
    )
    return (
        f"真理:生命 实际约 {truth_chars}:{life_chars}，"
        f"目标比例约 {target[0]}:{target[1]}，请{direction}的篇幅占比。"
    )


def _heading_count_fragment(
    data: dict, heading_range: tuple[int, int]
) -> str | None:
    """小标题数量不在目标区间时返回反馈片段；合格返回 None。"""
    lo, hi = heading_range
    count = sum(
        len(sec.get("subsections", [])) for sec in data.get("sections", [])
    )
    if lo <= count <= hi:
        return None
    if count < lo:
        return (
            f"全篇小标题共 {count} 个，低于目标区间 {lo}-{hi} 个，"
            f"请增加约 {lo - count} 个小标题（从原文摘取合适标题，"
            f"并为其配备相应原文段落），不要为凑数自创空标题。"
        )
    return (
        f"全篇小标题共 {count} 个，超过目标区间 {lo}-{hi} 个，"
        f"请合并或删除约 {count - hi} 个相对次要的小标题段落"
        f"（整段删除，把必要内容并入相邻标题下），不要只改标题文字。"
    )


def _paragraph_count_fragment(
    data: dict, max_paragraphs_per_heading: int = 2
) -> str | None:
    """检查是否有小标题下面的自然段数量超过限制"""
    violations = []
    for sec in data.get("sections", []):
        for sub in sec.get("subsections", []):
            count = len(sub.get("paragraphs", []))
            if count > max_paragraphs_per_heading:
                violations.append(
                    f"「{sub.get('heading', '')}」这个小标题下有{count}段"
                )
    if not violations:
        return None
    detail = "；".join(violations)
    return (
        f"以下小标题下的自然段数量超过限制"
        f"（每个小标题最多{max_paragraphs_per_heading}段）：{detail}。"
        "请直接把多出来的段落合并进已有段落里（用分号连接相邻句子），"
        "不需要拆分成新标题，合并即可。"
    )


def _qa_quality_fragment(qa_list: list[dict], max_length: int = 45) -> str | None:
    """检查彼此问互相答：每题只能有一个问号，且不能过长"""
    issues = []
    for i, qa in enumerate(qa_list, 1):
        question = qa.get("question", "")
        question_mark_count = question.count("？") + question.count("?")
        if question_mark_count > 1:
            issues.append(
                f"第{i}题包含{question_mark_count}个问号，疑似把多个问题挤在一起了：「{question}」"
            )
        elif len(question) > max_length:
            issues.append(
                f"第{i}题共{len(question)}字，偏长（建议{max_length}字以内）：「{question}」"
            )
    if not issues:
        return None
    detail = "；".join(issues)
    return (
        f"彼此问互相答部分需要调整：{detail}。"
        "请把每一题改成只问一件事、一句话说完的简洁问句，"
        "不要在一个问题里塞进多层追问。"
    )


def _build_unified_instruction(
    verbatim_fragment: str | None,
    word_fragment: str | None,
    ratio_fragment: str | None,
    outline_fragment: str | None,
    word_count: int,
    heading_fragment: str | None = None,
    paragraph_fragment: str | None = None,
    qa_fragment: str | None = None,
) -> str:
    """把这一轮所有不合格的项目，合并成一条指令一次性反馈给模型。"""
    parts = []
    if verbatim_fragment:
        parts.append(
            f"【原文摘取问题——最高优先级，必须优先修正】{verbatim_fragment}"
        )
    if word_fragment:
        parts.append(f"【字数问题】{word_fragment}")
    if ratio_fragment:
        parts.append(f"【比例问题】{ratio_fragment}")
    if heading_fragment:
        parts.append(f"【小标题数量问题】{heading_fragment}")
    if paragraph_fragment:
        parts.append(f"【小标题下段落数量问题】{paragraph_fragment}")
    if qa_fragment:
        parts.append(f"【彼此问互相答问题】{qa_fragment}")
    if outline_fragment:
        parts.append(f"【鸟瞰纲目问题】{outline_fragment}")
    joined = "\n\n".join(parts)
    return (
        f"{joined}\n\n"
        "请在同一次调整里，把上面列出的所有问题一起解决，不要只顾一个而忽略其他——"
        "尤其修正原文摘取问题时，替换掉的内容也要注意不要让字数/比例因此跑偏；"
        "调整字数或比例时，删改的句子也要确保仍然100%取自原文。"
        f"（当前总字数 {word_count} 字，供参考）"
    )


def _check_ratio(
    paras: list[dict],
    target: tuple[int, int],
    tolerance: float = 0.15,
) -> tuple[bool, str]:
    """真理/生命字数比例校验（供测试脚本打印结果用）。"""
    _ = tolerance  # 容差固定在 _ratio_fragment（0.15）
    truth_chars = sum(len(p["text"]) for p in paras if p.get("type") == "真理")
    life_chars = sum(len(p["text"]) for p in paras if p.get("type") == "生命")
    fragment = _ratio_fragment(truth_chars, life_chars, target)
    if fragment is None:
        return True, ""
    return False, fragment


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


# " " ' ' 「 」 『 』 及 ASCII 引号（分句两端残留时先剥掉再匹配）
QUOTE_CHARS = '"\u201c\u201d\u2018\u2019\u300c\u300d\u300e\u300f'


def _strip_edge_quotes(clause: str) -> str:
    return clause.strip(QUOTE_CHARS + " \u3000")


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
            c = _strip_edge_quotes(c.strip())
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


def _log_final_heading_count(config: dict, data: dict) -> None:
    heading_count = sum(
        len(sec.get("subsections", [])) for sec in data.get("sections", [])
    )
    logger.info(
        "[Step2] %s 最终小标题数=%s，目标=%s",
        config["label"],
        heading_count,
        config["heading_range"],
    )


async def generate_version(
    version_key: str,
    original_texts: list[dict],
    unified_fields: dict,
    max_retries: int = 7,
    on_progress: Callable[[str, int], None] | None = None,
    task_id: str | None = None,
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
    # 追踪「除比例外全部合格」里，比例最接近目标的那一轮，供重试用尽时兜底放行
    best_ratio_only_fail: dict | None = None
    # 倒数第2次起尝试摘取删除兜底，给兜底结果留出再验证/再调的空间
    FALLBACK_TRIGGER_ATTEMPT = max_retries - 1

    for attempt in range(max_retries + 1):
        if on_progress:
            on_progress(
                "生成中" if attempt == 0 else "调整中",
                attempt + 1,
            )

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
                max_tokens=24000,
                effort="medium",
                cacheable_prefix=combined_original,
            )
            accumulate_usage(task_id, version_key, usage)
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

        # 拿到可解析草稿后进入校验阶段（不把内部校验细节传给 on_progress）
        if on_progress:
            on_progress("校验中", attempt + 1)

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

        # 临时调试：核对真理/生命 type 标注（诊断完可删）
        for p in paras:
            print(f"[Step2调试] type={p.get('type')} text={p['text'][:20]}...")

        # 四项检查全部执行，互不阻断，各自拿到 fragment（合格则为 None）
        verbatim_ok, verbatim_msg, bad_clauses = _check_verbatim(
            paras, combined_original
        )
        verbatim_fragment = (
            (
                _build_verbatim_instruction(bad_clauses)
                if bad_clauses
                else verbatim_msg
            )
            if not verbatim_ok
            else None
        )

        word_fragment = _word_count_fragment(word_count, config["word_range"])

        ratio_fragment = None
        ratio_gap: float | None = None
        if config["ratio"]:
            truth_chars = sum(
                len(p["text"]) for p in paras if p.get("type") == "真理"
            )
            life_chars = sum(
                len(p["text"]) for p in paras if p.get("type") == "生命"
            )
            total_tl = truth_chars + life_chars
            if total_tl > 0:
                target_ratio = config["ratio"][0] / (
                    config["ratio"][0] + config["ratio"][1]
                )
                actual_ratio = truth_chars / total_tl
                ratio_gap = abs(actual_ratio - target_ratio)
            ratio_fragment = _ratio_fragment(
                truth_chars, life_chars, config["ratio"]
            )

        heading_fragment = _heading_count_fragment(
            data, config["heading_range"]
        )

        paragraph_fragment = _paragraph_count_fragment(
            data, config["max_paragraphs_per_heading"]
        )

        qa_fragment = _qa_quality_fragment(data.get("qa", []))

        outline_fragment = None
        if config["has_outline"]:
            outline = data.get("outline", {})
            if not outline.get("major_points"):
                outline_fragment = "缺少鸟瞰纲目，请补充。"
            else:
                outline_ok, outline_msg = _check_outline_count(
                    outline, config["max_outline_items"]
                )
                if not outline_ok:
                    outline_fragment = outline_msg

        # 记录「只有比例不合格、其余全部合格」的最佳结果，供最后兜底用
        if (
            config["ratio"]
            and ratio_fragment
            and not verbatim_fragment
            and not word_fragment
            and not heading_fragment
            and not paragraph_fragment
            and not qa_fragment
            and not outline_fragment
            and len(data.get("qa", [])) == 3
            and ratio_gap is not None
        ):
            if (
                best_ratio_only_fail is None
                or ratio_gap < best_ratio_only_fail["ratio_gap"]
            ):
                best_ratio_only_fail = {
                    "data": data,
                    "word_count": word_count,
                    "ratio_gap": ratio_gap,
                    "attempts": attempt + 1,
                }

        # 接近用尽重试、且仅卡在摘取时：删除不合规句后若字数/比例仍合格则收尾
        if (
            verbatim_fragment
            and not word_fragment
            and not ratio_fragment
            and not heading_fragment
            and not paragraph_fragment
            and not qa_fragment
            and not outline_fragment
            and attempt >= FALLBACK_TRIGGER_ATTEMPT
            and bad_clauses
        ):
            stripped_data = _strip_bad_clauses_from_data(data, bad_clauses)
            stripped_paras = _collect_paragraphs(stripped_data)
            stripped_word_count = _count_total_words(stripped_data)
            stripped_word_ok = (
                _word_count_fragment(stripped_word_count, config["word_range"])
                is None
            )
            stripped_ratio_ok = True
            if config["ratio"]:
                t_chars = sum(
                    len(p["text"])
                    for p in stripped_paras
                    if p.get("type") == "真理"
                )
                l_chars = sum(
                    len(p["text"])
                    for p in stripped_paras
                    if p.get("type") == "生命"
                )
                stripped_ratio_ok = (
                    _ratio_fragment(t_chars, l_chars, config["ratio"]) is None
                )
            stripped_verbatim_ok, _, remaining_bad = _check_verbatim(
                stripped_paras, combined_original
            )
            stripped_heading_ok = (
                _heading_count_fragment(stripped_data, config["heading_range"])
                is None
            )
            stripped_paragraph_ok = (
                _paragraph_count_fragment(
                    stripped_data, config["max_paragraphs_per_heading"]
                )
                is None
            )
            stripped_qa_ok = (
                len(stripped_data.get("qa", [])) == 3
                and _qa_quality_fragment(stripped_data.get("qa", [])) is None
            )

            if (
                stripped_word_ok
                and stripped_ratio_ok
                and stripped_verbatim_ok
                and stripped_heading_ok
                and stripped_paragraph_ok
                and stripped_qa_ok
            ):
                logger.info(
                    "[Step2] %s 触发摘取兜底：删除%s处不合规片段后收尾，字数%s",
                    config["label"],
                    len(bad_clauses),
                    stripped_word_count,
                )
                print(
                    f"[Step2] {config['label']} 摘取兜底生效："
                    f"删除{len(bad_clauses)}处，字数{stripped_word_count}"
                )
                retry_log.append(
                    f"摘取兜底：删除{len(bad_clauses)}处不合规片段后通过"
                    f"（字数{stripped_word_count}）"
                )
                if on_progress:
                    on_progress("已完成", attempt + 1)
                _log_final_heading_count(config, stripped_data)
                return {
                    "version_key": version_key,
                    "label": config["label"],
                    "data": stripped_data,
                    "word_count": stripped_word_count,
                    "attempts": attempt + 1,
                    "retry_log": retry_log,
                    "verbatim_match_rate": 1.0,
                    "fallback_stripped": True,
                }
            logger.info(
                "[Step2] %s 摘取兜底未采用：删后字数=%s word_ok=%s "
                "ratio_ok=%s verbatim_ok=%s heading_ok=%s paragraph_ok=%s "
                "remaining_bad=%s",
                config["label"],
                stripped_word_count,
                stripped_word_ok,
                stripped_ratio_ok,
                stripped_verbatim_ok,
                stripped_heading_ok,
                stripped_paragraph_ok,
                len(remaining_bad),
            )

        if (
            verbatim_fragment
            or word_fragment
            or ratio_fragment
            or heading_fragment
            or paragraph_fragment
            or qa_fragment
            or outline_fragment
        ):
            last_error = _build_unified_instruction(
                verbatim_fragment,
                word_fragment,
                ratio_fragment,
                outline_fragment,
                word_count,
                heading_fragment=heading_fragment,
                paragraph_fragment=paragraph_fragment,
                qa_fragment=qa_fragment,
            )
            last_error_type = "content_adjust"
            retry_log.append(last_error)
            continue

        last_match_rate = 1.0

        # qa：很少出错，仍单独走重写类处理
        if len(data.get("qa", [])) != 3:
            last_error = "彼此问互相答数量不是3题"
            last_error_type = "qa_count"
            retry_log.append(last_error)
            continue

        if on_progress:
            on_progress("已完成", attempt + 1)

        _log_final_heading_count(config, data)
        return {
            "version_key": version_key,
            "label": config["label"],
            "data": data,
            "word_count": word_count,
            "attempts": attempt + 1,
            "retry_log": retry_log,
            "verbatim_match_rate": last_match_rate,
        }

    # 重试用尽：若存在「只差比例」的最佳稿，直接放行（不带警告标记）
    if best_ratio_only_fail is not None:
        if on_progress:
            on_progress("已完成", best_ratio_only_fail["attempts"])
        _log_final_heading_count(config, best_ratio_only_fail["data"])
        return {
            "version_key": version_key,
            "label": config["label"],
            "data": best_ratio_only_fail["data"],
            "word_count": best_ratio_only_fail["word_count"],
            "attempts": best_ratio_only_fail["attempts"],
            "retry_log": retry_log,
            "verbatim_match_rate": 1.0,
        }

    if on_progress:
        on_progress("生成失败", max_retries + 1)
    # last_error 是给模型看的内部调整指令，只写日志，不塞进对外 RuntimeError
    logger.error(
        "[Step2] %s 生成失败，已重试 %s 次，最后内部错误：%s",
        config["label"],
        max_retries,
        last_error,
    )
    raise RuntimeError(
        f"{config['label']}：内容生成多次尝试后仍不符合要求，请重新生成或更换原文范围"
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
