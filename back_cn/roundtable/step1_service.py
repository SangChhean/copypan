# -*- coding: utf-8 -*-
"""Step 1：统一字段生成（标题 / 出处 / 读经经节 / 诗歌推荐）。"""
from __future__ import annotations

import json
import re

from back_cn.roundtable.bible_loader import get_verse_safe
from back_cn.roundtable.claude_service import call_sonnet5_high
from back_cn.roundtable.hymn_history import get_recent_hymns, record_hymn_used
from back_cn.roundtable.hymns_service import verify_hymn

_STEP1_COMMON = """你是一个资深的圣经研究学者，专精李常受生命读经信息的整理与摘要工作。

任务：根据提供的当周生命读经原文，生成下列字段，只输出JSON，不输出任何其他文字、不输出markdown代码块标记。

字段说明：

verses：读经经节，固定2节。每节包含：
   - book：卷号（数字）
   - chapter：章号（数字）
   - verse：节号（数字）
   - 这2节可以是同一范围内的连续节，也可以是不连续的2节，由你根据本周原文内容判断选哪2节最合适

hymn：诗歌推荐
   - source：只能是"大本"或"补充"这两个值之一
   - no：诗歌编号（数字）
   - 只需要编号，不要输出歌词
   - 必须给出一首真实存在的诗歌（source 与 no 不能为空），但要认真比对歌词内容和本周原文主题的关联性，不要因为某首诗歌泛用、放在任何主题下都说得过去，就图省事选它——这类"万能诗歌"往往不是真正最贴切的选择。请优先寻找歌词内容与本周主题有具体呼应的诗歌。
"""

_STEP1_SINGLE = (
    _STEP1_COMMON
    + """
注意：题目（title）与整体出处已由系统确定，不要输出 title、overall_source 字段。
系统会在最终标题前自动加上「第X周」前缀，你不需要输出周次。

输出格式示例：
{
  "verses": [
    {"book": 1, "chapter": 1, "verse": 1},
    {"book": 1, "chapter": 1, "verse": 26}
  ],
  "hymn": {"source": "大本", "no": 1}
}
"""
)

_STEP1_MULTI = (
    _STEP1_COMMON
    + """
另需输出 title：由本周全部原文各篇的题目自然结合为一个通顺的标题（只写题目本身，不要带「第X周」前缀，也不要带「第X篇」）。
注意：整体出处已由系统确定，不要输出 overall_source 字段。

输出格式示例：
{
  "title": "...",
  "verses": [
    {"book": 49, "chapter": 5, "verse": 18},
    {"book": 49, "chapter": 5, "verse": 20}
  ],
  "hymn": {"source": "大本", "no": 1}
}
"""
)


def _build_step1_system(num_messages: int) -> str:
    if num_messages <= 1:
        return _STEP1_SINGLE
    return _STEP1_MULTI


def _extract_cn_numeral(title: str) -> str:
    """从 '第十五篇　神呼召的盼望...' 这样的标题里提取中文数字部分 '十五'"""
    m = re.match(r"^第(.+?)篇", title)
    if not m:
        raise ValueError(f"无法从标题提取篇号：{title}")
    return m.group(1)


def _extract_topic(title: str) -> str:
    """从 '第十五篇　神呼召的盼望...' 提取题目部分 '神呼召的盼望...'"""
    m = re.match(r"^第.+?篇[　\s]*(.*)$", title.strip())
    if not m:
        return title.strip()
    topic = (m.group(1) or "").strip()
    return topic if topic else title.strip()


def compute_topic_and_source(messages: list[dict]) -> tuple[str | None, str]:
    """
    纯代码计算，不调用 Claude。
    返回 (topic, overall_source)：
    - 单卷单篇：topic 为去掉「第X篇」后的题目，overall_source 直接算出
    - 单卷多篇 / 跨卷：topic 返回 None（仍需模型合成标题），overall_source 直接算出
    """
    # 按书卷分组，保持原有顺序，把连续同卷的消息归到一组
    groups: list[tuple[str, list[dict]]] = []
    for m in messages:
        if groups and groups[-1][0] == m["book_name"]:
            groups[-1][1].append(m)
        else:
            groups.append((m["book_name"], [m]))

    # 单卷单篇：原有逻辑不变
    if len(groups) == 1 and len(messages) == 1:
        numeral = _extract_cn_numeral(messages[0]["title"])
        topic = _extract_topic(messages[0]["title"])
        overall_source = f"（摘自{messages[0]['book_name']}，第{numeral}篇）"
        return topic, overall_source

    # 单卷多篇：原有逻辑不变
    if len(groups) == 1:
        book_name = groups[0][0]
        first_numeral = _extract_cn_numeral(messages[0]["title"])
        last_numeral = _extract_cn_numeral(messages[-1]["title"])
        overall_source = f"（摘自{book_name}，第{first_numeral}~{last_numeral}篇）"
        return None, overall_source

    # 跨卷：每组各自算出范围，用顿号连接
    parts = []
    for book_name, group_msgs in groups:
        if len(group_msgs) == 1:
            numeral = _extract_cn_numeral(group_msgs[0]["title"])
            parts.append(f"{book_name}，第{numeral}篇")
        else:
            first_numeral = _extract_cn_numeral(group_msgs[0]["title"])
            last_numeral = _extract_cn_numeral(group_msgs[-1]["title"])
            parts.append(f"{book_name}，第{first_numeral}~{last_numeral}篇")
    overall_source = "（摘自" + "；".join(parts) + "）"
    return None, overall_source


def _extract_json(text: str) -> dict:
    """去掉可能存在的 markdown 代码块围栏后解析 JSON"""
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    return json.loads(cleaned)


def _split_ref(ref_gb: str) -> tuple[str, int]:
    """把 '创一1' 拆成 ('创一', 1)，'弗一18' 拆成 ('弗一', 18)"""
    m = re.match(r"^(.+?)(\d+)$", ref_gb)
    if not m:
        raise ValueError(f"无法解析经文引用格式：{ref_gb}")
    return m.group(1), int(m.group(2))


def _build_display(verse1_data: dict, verse2_data: dict) -> str:
    """
    根据两节经文的 ref_gb 字段，按 SOP 规则算出正确的连接符：
    - 同卷同章且节号连续（v2 = v1 + 1）：用 '~'，格式如 '弗一18~19'
    - 同卷同章但不连续：用 '、'，格式如 '弗一18、20'
    - 不同章或不同卷：用 '，'，格式如 '弗一18，加二12'（两节各自完整引用）
    """
    prefix1, num1 = _split_ref(verse1_data["ref_gb"])
    prefix2, num2 = _split_ref(verse2_data["ref_gb"])

    if prefix1 == prefix2:
        if num2 == num1 + 1:
            return f"{prefix1}{num1}~{num2}"
        else:
            return f"{prefix1}{num1}、{num2}"
    else:
        return f"{prefix1}{num1}，{prefix2}{num2}"


async def generate_unified_fields(
    original_texts: list[dict],
    week_number: str | None = None,
    max_retries: int = 2,
) -> dict:
    """
    original_texts: life_text_service.get_messages() 返回的列表
    week_number: 可选周次文案（如「三」「十五」）；有则标题为「第X周　题目」，无则只用题目
    返回: title / week_number / topic / overall_source / verses / hymn / usage
    """
    if week_number is not None:
        week_number = str(week_number).strip() or None

    computed_topic, overall_source = compute_topic_and_source(original_texts)
    system = _build_step1_system(len(original_texts))

    # 用拼接而非 .format()，避免 JSON 示例里的花括号与 format 冲突
    recent = get_recent_hymns(limit=10)
    if recent:
        recent_desc = "、".join(f"{h['source']}{h['no']}" for h in recent)
        system = (
            system
            + "\n最近已经推荐过这些诗歌，请尽量避免再次选择这几首："
            + f"{recent_desc}。"
        )

    combined_text = "\n\n".join(
        f"【{t['book_name']} {t['title']}】\n" + "\n".join(t["paragraphs"])
        for t in original_texts
    )

    last_error = None
    last_usage: dict | None = None
    for attempt in range(max_retries + 1):
        task_note = (
            f"上一次生成有问题：{last_error}\n请重新生成。"
            if last_error
            else "请根据以上原文生成统一字段。"
        )
        raw, usage = await call_sonnet5_high(
            prompt=task_note,
            system=system,
            max_tokens=4000,
            effort="medium",
            cacheable_prefix=combined_text,
        )
        last_usage = usage
        print(f"[Step1] attempt {attempt + 1} usage: {usage}")
        try:
            data = _extract_json(raw)
        except json.JSONDecodeError as e:
            last_error = f"JSON解析失败：{e}"
            continue

        # 校验经文是否真实存在
        resolved_verses = []
        verse_ok = True
        for v in data.get("verses", []):
            verse_data = get_verse_safe(v["book"], v["chapter"], v["verse"])
            if verse_data is None:
                verse_ok = False
                last_error = (
                    f"经文不存在：book={v['book']} chapter={v['chapter']} "
                    f"verse={v['verse']}，请重新选择真实存在的经节"
                )
                break
            resolved_verses.append(
                {
                    **v,
                    "text": verse_data.get("text_gb_plain")
                    or verse_data.get("text_gb"),
                    "ref_gb": verse_data.get("ref_gb"),
                }
            )

        if not verse_ok:
            continue

        if len(resolved_verses) != 2:
            last_error = f"经文数量须为2节，实际为 {len(resolved_verses)}"
            continue

        display = _build_display(resolved_verses[0], resolved_verses[1])
        resolved_verses[0]["display"] = ""
        resolved_verses[1]["display"] = display

        # 校验诗歌：必须给出真实存在的一首
        hymn = data.get("hymn") or {}
        if not hymn.get("source") or not hymn.get("no"):
            last_error = "必须推荐一首真实存在的诗歌（source 与 no 不能为空）"
            continue
        hymn_data = verify_hymn(hymn["source"], hymn["no"])
        if hymn_data is None:
            last_error = (
                f"诗歌不存在：source={hymn['source']} no={hymn['no']}，"
                f"请重新推荐一首真实存在的诗歌"
            )
            continue
        resolved_hymn = hymn_data

        if computed_topic is not None:
            final_topic = computed_topic
        else:
            final_topic = (data.get("title") or "").strip()
            if not final_topic:
                last_error = "多篇情况下模型未返回 title"
                continue
            # 防御：模型若误带「第X周」前缀则剥掉
            final_topic = (
                re.sub(r"^第.+?周[　\s]*", "", final_topic).strip() or final_topic
            )

        title = f"第{week_number}周　{final_topic}" if week_number else final_topic

        record_hymn_used(resolved_hymn["source"], resolved_hymn["no"])

        return {
            "title": title,
            "week_number": week_number,
            "topic": final_topic,
            "overall_source": overall_source,
            "verses": resolved_verses,
            "hymn": resolved_hymn,
            "usage": last_usage,
        }

    raise RuntimeError(
        f"Step 1 生成失败，已重试 {max_retries} 次，最后错误：{last_error}"
    )
