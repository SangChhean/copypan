# -*- coding: utf-8 -*-
"""【新测试台】特殊标注：判定为“主要内容”时，直接输出现成的纲目，不走生成纲目流程（2026-11-12 老板定）。

和防火墙的不同：防火墙命中后是把资料放进生成纲目的 Prompt 当参考；这里命中“主要内容”后是直接把现成纲目当答案输出。
只是稍微提到、或题目不属于这些词的，都当没命中，照常生成纲目。

目前接了一种：
- 从历史进展的差异看高峰时期的内涵（high_peak，87 个词）：看对同一个真理的认识和陈明，怎样在不同职事阶段中继续往前；
  到了高峰阶段，往往出现更特有的意义、定义、说明和强调。资料读图谱词条上的 high_peak_content
  （每词一篇，按六阶段排；各点编号不连贯的问题待资料更正，换资料只要换 load_special_outlines 读的来源，流程不用改）。
之后要接：
- 生机关联的进展（organic，69 个词）：看真理本身内部的生命关系怎样发展；资料用另外作好的 69 篇 2～3 页纲目（不读原资料库）。

判断看题目＋负担说明（2026-11-15 用户要求先换回最早这一版，待和老板讨论；“只看题目＋两段定义”的那一版备份在 scratchpad）；几个词都对得上时只取最对应的一个。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from t35test.kg.llm_pricing import register_llm_usage

logger = logging.getLogger("t35test")

HIGH_PEAK_LABEL = "从历史进展的差异看高峰时期的内涵"
SPECIAL_MATCH_MODEL = "claude-opus-5-5"

_neo4j_client: Any = None
_high_peak: dict[str, dict[str, Any]] = {}  # 词名 → high_peak_content（dict）

HIGH_PEAK_MATCH_PROMPT = """以下是「从历史进展的差异看高峰时期的内涵」所收的 {count} 个词：
{words_block}

纲目题目：{query}
负担说明：{burden}

「从历史进展的差异看高峰时期的内涵」的意思：同一个真理，在不同的职事阶段（倪柝声弟兄职事，李常受弟兄职事第一、二、三、四阶段，高峰阶段）中被继续陈明，看对这个真理的认识和陈明怎样一步一步往前；到了高峰阶段，往往会出现更特有的意义、定义、说明和强调。
注意和「生机关联的进展」分清楚：生机关联的进展是看真理本身内部的生命关系怎样发展，那不算这里的命中。

请判断这篇纲目是不是要走「从历史进展的差异看高峰时期的内涵」：
- 命中（主要内容）：题目和负担说明主要就是要表达某一个真理的历史进展的差异——这个真理在不同职事阶段中怎样被继续陈明、到高峰阶段有什么更特有的意义；并且这个真理就是上面列出的某一个词。
- 不命中：只是稍微提到历史进展、职事阶段或高峰，主要内容不是要讲这个；或者题目所讲的真理不是上面的任何一个词。

只返回 JSON：{{"main": true 或 false, "word": "命中的词（必须逐字是上面列出的词之一；不命中写 null）", "reason": "一句话理由"}}
几个词都对得上时，只选最对应的一个。不得有任何其他文字、解释或 markdown。"""


def load_special_outlines(neo4j_client: Any = None) -> None:
    """启动时读特殊标注的现成纲目；读不到不报错（本次不生效），match 时会再试一次。"""
    global _neo4j_client, _high_peak
    if neo4j_client is not None:
        _neo4j_client = neo4j_client
    _high_peak = {}
    if _neo4j_client is None:
        logger.warning("[特殊标注] no neo4j client, 高峰 0 个词")
        return
    for row in _neo4j_client.get_high_peak_contents():
        name = str(row.get("name") or "").strip()
        try:
            obj = json.loads(row.get("raw") or "{}")
        except (TypeError, json.JSONDecodeError):
            logger.warning("[特殊标注] high_peak_content JSON 解析失败：%r", name)
            continue
        if name and isinstance(obj, dict):
            # 六个阶段都没有内容的词（资料里有 7 个）不放进来，判断时也不列给模型
            if any(obj.get(f"content_{k}") for k in range(1, 7)):
                _high_peak[name] = obj
            else:
                logger.info("[特殊标注] 高峰资料是空的，不列入判断：%s", name)
    logger.info("[特殊标注] 高峰（%s）载入 %s 个词", HIGH_PEAK_LABEL, len(_high_peak))


# 【新测试台】2026-11-12 老板定：高峰纲目的版面和“生机关联的进展”一样——有资料的阶段作大点（壹贰叁…，文字是阶段名），
# 阶段底下所有的点（原来不论大点、中点、小点）一律作中点（一二三…，每阶段从一起），原编号去掉（资料原编号不连贯的问题由此解决）；
# 每一点后面的出处、年代去掉；读经只在最前面写一次。点的文字不改。
# 原编号：大写数字后面可能没有空格（“拾贰我们……”）；“〇”开头的是补充段落，也当编号去掉
_POINT_NUM = re.compile(
    r"^\s*(?:[壹贰叁肆伍陆柒捌玖拾]+[\t 　、．.]*|(?:[一二三四五六七八九十〇]+|[0-9０-９]+|[a-zａ-ｚ])[\t 　、．.]+)"
)
_STRONG_SOURCE = re.compile(
    r"文集|生命读经|恢复本|注解|训练|特会|结晶读经|真理课程|题库|新约总论|"
    r"第[一二三四五六七八九十百零〇0-9]+[篇章册课期]"
)
_NOTE_LINE = re.compile(r"^\s*(【[^】]*】|[·•])")  # 资料里编辑的备注行（如“【阶段待定……】”“· 其它有年份……”），不是纲目内容
_SOURCE_TAIL = re.compile(r"[（(][^（）()]*(?:[（(][^（）()]*[）)][^（）()]*)*[）)]\s*(?:〔[^〕]*〕)?\s*$")
_YEAR_TAIL = re.compile(r"\s*〔[^〕]*〕\s*$")
_SOURCE_WORDS = re.compile(r"文集|生命读经|注解|注\d|训练|课程|恢复本|特会|结晶读经|信息|册|篇|章|课")
_BIG_NUM = "壹贰叁肆伍陆柒捌玖拾"
_MID_NUM = "一二三四五六七八九十"


def _cn_num(n: int, digits: str) -> str:
    """正整数 → 中文编号（digits 为 一…十 或 壹…拾）。一个阶段可能超过一百点：一百以上一位一位写，0 写成〇，
    例：一〇一、一一〇、一一二（用户 2026-11-12 定）。"""
    ten = digits[9]
    if n >= 100:
        return "".join("〇" if c == "0" else digits[int(c) - 1] for c in str(n))
    if n <= 10:
        return digits[n - 1]
    if n < 20:
        return ten + digits[n - 11]
    return digits[n // 10 - 1] + ten + (digits[n % 10 - 1] if n % 10 else "")


def _strip_point(line: str) -> str:
    """去掉点前面的原编号和后面的出处、年代，其余文字不动。"""
    s = _POINT_NUM.sub("", line.strip(), count=1)
    m = _SOURCE_TAIL.search(s)
    if m and ("〔" in m.group(0) or _SOURCE_WORDS.search(m.group(0))):
        s = s[:m.start()].rstrip()
        # 出处可能连着两个括号：“（李常受文集……第二章）（标题）　〔补充段落·1953〕”，前一个是明确的出处才再去掉
        for _ in range(2):
            m = _SOURCE_TAIL.search(s)
            if not (m and _STRONG_SOURCE.search(m.group(0))):
                break
            s = s[:m.start()].rstrip()
    else:
        s = _YEAR_TAIL.sub("", s)
    return s.rstrip()


def format_high_peak(word: str) -> str | None:
    """把一个词的高峰纲目排成输出用的文字：读经（只写一次）＋有资料的阶段作大点＋底下的点全部作中点（去出处、年代）。"""
    obj = _high_peak.get(word)
    if not obj:
        return None
    stages = obj.get("stages") or {}
    reading = ""
    out: list[str] = []
    big = 0
    for k in range(1, 7):
        key = f"content_{k}"
        points: list[str] = []
        for item in obj.get(key) or []:
            for line in str((item or {}).get("outline") or "").split("\n"):
                if not line.strip():
                    continue
                if line.strip().startswith("读经"):
                    reading = reading or line.strip()  # 各阶段重复同一行读经，只留第一行
                    continue
                if _NOTE_LINE.match(line):
                    continue  # 编辑的备注行，不输出
                text = _strip_point(line)
                if text:
                    points.append(text)
        if not points:
            continue  # 没有资料的阶段不列
        big += 1
        out.append(f"{_cn_num(big, _BIG_NUM)}\t{stages.get(key) or key}")
        out += [f"\t{_cn_num(i, _MID_NUM)}\t{t}" for i, t in enumerate(points, 1)]
    if not out:
        return None
    return "\n".join(([reading] if reading else []) + out)


async def match_special_outline(
    query: str,
    burden: str,
    llm_caller: Any,
    *,
    llm_calls: list[dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    """判断要不要直接输出现成纲目。命中主要内容回传
    {"type", "label", "word", "reason", "answer"}；不命中或出错回传 None（照常生成纲目）。"""
    if not _high_peak and _neo4j_client is not None:
        load_special_outlines()
    if not _high_peak:
        logger.info("[特殊标注] 没有资料，跳过判断")
        return None
    words = sorted(_high_peak)
    prompt = HIGH_PEAK_MATCH_PROMPT.format(
        count=len(words),
        words_block="、".join(words),
        query=(query or "").strip(),
        burden=(burden or "").strip() or "（没有填写）",
    )
    try:
        raw, usage = await llm_caller(prompt, SPECIAL_MATCH_MODEL, temperature=0, max_tokens=400)
        if llm_calls is not None:
            register_llm_usage(llm_calls, step="special", request_model=SPECIAL_MATCH_MODEL, usage=usage)
        text = (raw or "").strip()
        if text.startswith("```"):
            text = text.strip("`").split("\n", 1)[-1]
        start, end = text.find("{"), text.rfind("}")
        obj = json.loads(text[start:end + 1]) if start >= 0 and end > start else {}
        logger.info("[特殊标注] 高峰判断：%s", json.dumps(obj, ensure_ascii=False)[:300])
        if not obj.get("main"):
            return None
        word = str(obj.get("word") or "").strip()
        answer = format_high_peak(word)
        if not answer:
            logger.info("[特殊标注] 判为命中但词不在 87 个词里（或没有纲目）：%r，照常生成", word)
            return None
        return {
            "type": "high_peak",
            "label": HIGH_PEAK_LABEL,
            "word": word,
            "reason": str(obj.get("reason") or "").strip(),
            "answer": answer,
        }
    except Exception as e:
        logger.warning("[特殊标注] 判断出错，照常生成纲目：%s", e)
        return None
