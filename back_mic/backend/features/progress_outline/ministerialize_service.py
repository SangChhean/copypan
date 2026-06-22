# -*- coding: utf-8 -*-
"""进展纲目分段结果的职事化处理。"""
from __future__ import annotations

import logging
import re
from typing import Any

from kg_rag.kg_rag_service import ministerialize_outline

from es_config import es as _es

logger = logging.getLogger(__name__)

_ZH_DIGITS = [
    "〇", "一", "二", "三", "四", "五", "六", "七", "八", "九", "十",
    "十一", "十二", "十三", "十四", "十五", "十六", "十七", "十八", "十九", "二十",
    "二十一", "二十二", "二十三", "二十四", "二十五", "二十六", "二十七", "二十八", "二十九", "三十",
    "三十一", "三十二", "三十三", "三十四", "三十五", "三十六", "三十七", "三十八", "三十九", "四十",
    "四十一", "四十二", "四十三", "四十四", "四十五", "四十六", "四十七", "四十八", "四十九", "五十",
]


def _to_zh_num(n: int) -> str:
    if 0 <= n < len(_ZH_DIGITS):
        return _ZH_DIGITS[n]
    return str(n)


STAGE_FULL_TITLES = {
    1: "倪柝声弟兄职事",
    2: "李常受弟兄职事第一阶段（1932-1973）",
    3: "李常受弟兄职事第二阶段（1974-1984）",
    4: "李常受弟兄职事第三阶段（1985-1990）",
    5: "李常受弟兄职事第四阶段（1991-1997）",
}

# 节期纲目关键词，包含任一即过滤
FESTIVAL_KEYWORDS = [
    "国际华语特会",
    "春季长老训练",
    "秋季长老训练",
    "国殇节",
    "夏季训练",
    "夏训",
    "冬季训练",
    "冬训",
    "感恩节特会",
    "安那翰春季全时间训练",
    "安那翰秋季全时间训练",
    "全时间训练",
    "特会",
    "长老训练",
]

# 各阶段的年份范围
STAGE_YEAR_RANGES = {
    1: (1900, 1952),  # 倪柝声弟兄职事
    2: (1932, 1973),  # 李常受第一阶段
    3: (1974, 1984),  # 李常受第二阶段
    4: (1985, 1990),  # 李常受第三阶段
    5: (1991, 1997),  # 李常受第四阶段
}


def _is_valid_source(source: str, stage_no: int) -> bool:
    """
    判断出处是否在本阶段范围内且非节期纲目。
    支持复合出处（分号分隔），自动过滤节期子段后取剩余部分判断。
    返回 True 表示保留，False 表示整条过滤。
    """
    if not source or not source.strip():
        return False
    src_full = source.strip()

    # ── 复合出处拆分 ──
    # source 可能是「2017年国际华语特会，第二篇；李常受文集一九八一年第一册，…」
    # 先按分号拆开，过滤含节期关键词的子段，取剩余部分
    parts = [p.strip().strip("（）()「」『』") for p in re.split(r"[；;]", src_full)]
    valid_parts = [p for p in parts if p and not any(kw in p for kw in FESTIVAL_KEYWORDS)]
    if not valid_parts:
        return False
    # 用剩余有效子段重新组合，后续年份/阶段校验基于此
    src = "；".join(valid_parts)
    # 生命读经限制：仅阶段3/4/5可出现，阶段1/2过滤
    if stage_no in (1, 2) and "生命读经" in src:
        return False
    # ── 原有逻辑（src 变量已替换为过滤后内容）──
    src_clean = src.strip("（）()「」『』")

    years = [int(y) for y in re.findall(r"(\d{4})", src_clean)]
    for m in re.finditer(r"([一二三四五六七八九十〇零]{2,8})年", src_clean):
        try:
            import cn2an

            y = int(cn2an.cn2an(m.group(1), "smart"))
            if 1000 <= y <= 2100:
                years.append(y)
        except Exception:
            pass

    if years:
        year_min, year_max = STAGE_YEAR_RANGES.get(stage_no, (1900, 2000))
        if not any(year_min <= y <= year_max for y in years):
            return False

    if stage_no == 1:
        if "倪" not in src_clean and "柝声" not in src_clean:
            if years:
                return False

    return True


def _clean_source(source: str) -> str:
    """
    清洗出处字段：
    1. 去掉末尾「，第X段」「，第X、Y段」「，第X至Y段」「，第X～Y段」等段落标注
    2. 去掉末尾年份季节标注（如「，1993冬」「，1985夏」「，1986年」）
    3. 去掉末尾星号
    """
    if not source:
        return source
    # 去掉末尾段落标注（含多段：第X、Y、Z段 / 第X至Y段 / 第X～Y段）
    source = re.sub(
        r"，第[一二三四五六七八九十百千\d]+(?:[、][一二三四五六七八九十百千\d]+)+段\*{0,2}\s*$",
        "",
        source,
    )
    source = re.sub(
        r"，第[一二三四五六七八九十百千\d]+[、至～~][一二三四五六七八九十百千\d]+段\*{0,2}\s*$",
        "",
        source,
    )
    source = re.sub(
        r"，第[一二三四五六七八九十百千\d]+段\*{0,2}\s*$",
        "",
        source,
    )
    # 去掉末尾年份季节标注（「，1993冬」「，1985夏」「，1986年」「，1974年夏」）
    source = re.sub(
        r"，\d{4}年?[春夏秋冬]?\s*$",
        "",
        source,
    )
    # 去掉末尾星号
    source = source.rstrip("*").strip()
    return source


_BIBLE_READING_RE = re.compile(r"^读经[：:]")


def parse_outline_text(text: str) -> dict[str, Any]:
    """解析纲目文本：首行读经 + 其余纲目行。"""
    bible_reading = ""
    outline_lines: list[str] = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        if not bible_reading and _BIBLE_READING_RE.match(line):
            bible_reading = re.sub(r"^读经[：:]\s*", "", line).strip()
            continue
        outline_lines.append(line)
    return {"bible_reading": bible_reading, "outline_lines": outline_lines}


def build_header_lines(
    series_title: str,
    stage_no: int,
    article_no: int,
    article_title: str,
    bible_reading: str,
) -> list[str]:
    """构建 Word 页眉四行。"""
    import re as _re

    _has_prefix = bool(
        _re.match(
            r"^第[一二三四五六七八九十百千万亿\d]+篇[\u3000\s]",
            (article_title or "").strip(),
        )
    )
    _line3 = (
        article_title.strip()
        if _has_prefix
        else f"第{_to_zh_num(article_no)}篇\u3000{article_title.strip()}"
    )
    return [
        "主恢复中神圣启示的进展",
        f"{series_title}\n{STAGE_FULL_TITLES.get(stage_no, '')}",
        _line3,
        f"读经：{bible_reading or ''}",
    ]


def build_footnotes(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按出现顺序为出处编号，相同 source_zh 共用编号。"""
    source_to_no: dict[str, int] = {}
    footnotes: list[dict[str, Any]] = []
    next_no = 1

    for row in lines:
        source_zh = (row.get("source_zh") or "").strip()
        if not source_zh:
            row["footnote_no"] = None
            continue
        if source_zh not in source_to_no:
            source_to_no[source_zh] = next_no
            footnotes.append({"no": next_no, "source_zh": source_zh})
            next_no += 1
        row["footnote_no"] = source_to_no[source_zh]

    return footnotes


def _empty_usage() -> dict[str, float | int]:
    return {"cost_usd": 0.0, "haiku_input": 0, "haiku_output": 0}


async def ministerialize_one_article(
    article_no: int,
    article_title: str,
    text: str,
    series_title: str,
    stage_no: int,
) -> dict[str, Any]:
    """单篇纲目职事化。"""
    parsed = parse_outline_text(text)
    bible_reading = parsed["bible_reading"]
    outline_lines: list[str] = parsed["outline_lines"]

    if not outline_lines:
        return {
            "article_no": article_no,
            "article_title": article_title,
            "error": "无有效纲目行",
        }

    try:
        raw = await ministerialize_outline(outline_lines)
    except Exception:
        logger.exception(
            "[progress_outline] 职事化失败 article_no=%s title=%r",
            article_no,
            article_title,
        )
        return {
            "article_no": article_no,
            "article_title": article_title,
            "error": "职事化调用失败",
        }

    results = raw.get("results") or []
    usage_raw = raw.get("usage") or {}
    cost_usd = float(raw.get("cost_usd") or 0.0)

    lines: list[dict[str, Any]] = []
    for item in results:
        lines.append(
            {
                "original": item.get("original") or "",
                "result": item.get("result") or "",
                "status": item.get("status") or "",
                "source_zh": item.get("source") or "",
                "suggestion": item.get("suggestion") or "",
            }
        )

    footnotes = build_footnotes(lines)
    header_lines = build_header_lines(
        series_title,
        stage_no,
        article_no,
        article_title,
        bible_reading,
    )

    return {
        "article_no": article_no,
        "article_title": article_title,
        "bible_reading": bible_reading,
        "header_lines": header_lines,
        "lines": lines,
        "footnotes": footnotes,
        "usage": {
            "cost_usd": cost_usd,
            "haiku_input": int(usage_raw.get("haiku_input") or 0),
            "haiku_output": int(usage_raw.get("haiku_output") or 0),
        },
    }


def _merge_usage(total: dict[str, float | int], part: dict[str, Any]) -> None:
    usage = part.get("usage") or {}
    total["cost_usd"] = float(total["cost_usd"]) + float(usage.get("cost_usd") or 0.0)
    total["haiku_input"] = int(total["haiku_input"]) + int(usage.get("haiku_input") or 0)
    total["haiku_output"] = int(total["haiku_output"]) + int(usage.get("haiku_output") or 0)


def _strip_outline_line(text: str) -> str:
    """
    剥离纲目行的前缀序号和后缀经节出处，返回纯文字 body。
    例：
      "壹\t神圣属天的方庭是神在地上的居所—出二五8：" → "神圣属天的方庭是神在地上的居所"
      "一\t生命就是三一神分赐到我们里面—约一4。"  → "生命就是三一神分赐到我们里面"
    """
    t = text.strip()
    t = re.sub(r"^[壹贰叁肆伍陆柒捌玖拾一二三四五六七八九十\da-z]+[\t\u3000]", "", t)
    t = re.sub(r"[—－-][^—－\t-]+[。：:\.]\s*$", "", t)
    t = t.rstrip("。；：，、.;:,")
    return t.strip()


def _overlap_ratio(a: str, b: str) -> float:
    """
    计算两个字符串的重叠比例（以较短串长度为分母）。
    用于判断 Claude 生成行与原始 outline 行的相似度。
    """
    if not a or not b:
        return 0.0
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if shorter in longer:
        return 1.0
    best = 0
    for i in range(len(shorter)):
        for j in range(i + 4, len(shorter) + 1):
            sub = shorter[i:j]
            if sub in longer and j - i > best:
                best = j - i
    return best / len(shorter)


def match_source_from_outlines(
    generated_line: str,
    outline_sources: list[dict],
    threshold: float = 0.5,
    stage_no: int = 1,
) -> list[tuple[str, str]]:
    """
    将 Claude 生成的纲目行与原始 outline 条目做文字匹配。
    先整行匹配，匹配不到则按分号拆分后逐段匹配。
    返回：[(segment, source_zh), ...]
    每个 segment 对应一个出处（可能多个 segment 共用同一出处）
    无匹配的 segment 返回 ("segment", "")
    """
    body = _strip_outline_line(generated_line)
    if not body or len(body) < 4:
        return [(body, "")]

    best_ratio = 0.0
    best_source = ""
    for item in outline_sources:
        item_text = _strip_outline_line(item.get("text") or "")
        if not item_text:
            continue
        ratio = _overlap_ratio(body, item_text)
        if ratio > best_ratio:
            raw_src = (item.get("source") or "").strip()
            parts = [p.strip().strip("（）()「」『』") for p in re.split(r"[；;]", raw_src)]
            valid_parts = [p for p in parts if p and not any(kw in p for kw in FESTIVAL_KEYWORDS)]
            candidate = _clean_source(valid_parts[0]).strip() if valid_parts else ""
            if _is_valid_source(candidate, stage_no):
                best_ratio = ratio
                best_source = candidate

    if best_ratio >= threshold:
        return [(body, best_source)]

    segments = [s.strip() for s in re.split(r"[；;]", body) if s.strip() and len(s.strip()) >= 4]
    if not segments:
        return [(body, "")]

    results = []
    for seg in segments:
        seg_best_ratio = 0.0
        seg_best_source = ""
        for item in outline_sources:
            item_text = _strip_outline_line(item.get("text") or "")
            if not item_text:
                continue
            ratio = _overlap_ratio(seg, item_text)
            if ratio > seg_best_ratio:
                raw_src = (item.get("source") or "").strip()
                parts = [p.strip().strip("（）()「」『』") for p in re.split(r"[；;]", raw_src)]
                valid_parts = [p for p in parts if p and not any(kw in p for kw in FESTIVAL_KEYWORDS)]
                candidate = _clean_source(valid_parts[0]).strip() if valid_parts else ""
                if _is_valid_source(candidate, stage_no):
                    seg_best_ratio = ratio
                    seg_best_source = candidate
        results.append((seg, seg_best_source if seg_best_ratio >= threshold else ""))

    return results


async def ministerialize_one_article_pano(
    article_no: int,
    article_title: str,
    text: str,
    series_title: str,
    stage_no: int,
    outline_sources: list[dict],
) -> dict:
    """
    进展75系列专用：不调 Claude，直接用文字匹配从 outline_sources 提取 source。
    outline_sources: 该组所有 articles 的 outline 列表合并（含 text + source 字段）
    """
    parsed = parse_outline_text(text)
    bible_reading = parsed["bible_reading"]
    outline_lines = parsed["outline_lines"]

    if not outline_lines:
        return {
            "article_no": article_no,
            "article_title": article_title,
            "bible_reading": bible_reading,
            "header_lines": build_header_lines(
                series_title, stage_no, article_no, article_title, bible_reading
            ),
            "lines": [],
            "footnotes": [],
            "usage": {"cost_usd": 0, "haiku_input": 0, "haiku_output": 0},
            "error": "无有效纲目行",
        }

    lines = []
    for raw_line in outline_lines:
        match_results = match_source_from_outlines(
            raw_line, outline_sources, stage_no=stage_no
        )

        if len(match_results) == 1:
            _, source_zh = match_results[0]
            lines.append(
                {
                    "original": raw_line,
                    "result": raw_line,
                    "status": "original" if source_zh else "manual",
                    "source_zh": source_zh,
                    "suggestion": "",
                    "footnote_no": None,
                }
            )
        else:
            seen = []
            for _, src in match_results:
                if src and src not in seen:
                    seen.append(src)
            combined_source = seen[0] if seen else ""
            lines.append(
                {
                    "original": raw_line,
                    "result": raw_line,
                    "status": "original" if combined_source else "manual",
                    "source_zh": combined_source,
                    "suggestion": "",
                    "footnote_no": None,
                }
            )

    footnotes = build_footnotes(lines)
    header_lines = build_header_lines(
        series_title, stage_no, article_no, article_title, bible_reading
    )

    return {
        "article_no": article_no,
        "article_title": article_title,
        "bible_reading": bible_reading,
        "header_lines": header_lines,
        "lines": lines,
        "footnotes": footnotes,
        "usage": {"cost_usd": 0, "haiku_input": 0, "haiku_output": 0},
    }


def _get_global_article_offset(series_no: int, active_stage_no: int) -> int:
    """
    计算全局流水号偏移。
    全局流水号 = 1（介言）+ 阶段1篇数 + ... + 阶段(N-1)篇数 + 当前篇序号
    本函数返回偏移值 = 1 + 各前置阶段篇数之和
    """
    if not series_no or not active_stage_no:
        return 1  # 无法计算时退化为从1开始（不含介言偏移）
    offset = 2  # 介言固定占第1位，阶段1从第2号开始
    for stage in range(1, active_stage_no):
        try:
            resp = _es.count(
                index="progress_pano",
                body={
                    "query": {
                        "bool": {
                            "must": [
                                {"term": {"series_no": series_no}},
                                {"term": {"source_group_no": stage}},
                            ]
                        }
                    }
                },
            )
            offset += int(resp.get("count") or 0)
        except Exception:
            logger.warning(
                "[progress] _get_global_article_offset ES查询失败 series=%s stage=%s",
                series_no,
                stage,
            )
    return offset


async def ministerialize_segment(
    group_results: list[dict[str, Any]],
    series_title: str,
    stage_no: int,
    outline_sources: list[dict] | None = None,
    is_pano: bool = False,
    series_no: int | None = None,
    active_stage_no: int | None = None,
    global_article_offset: int | None = None,
) -> dict[str, Any]:
    """对分段生成结果逐篇串行职事化。"""
    articles: list[dict[str, Any]] = []
    total_usage = _empty_usage()
    if global_article_offset is not None:
        global_offset = global_article_offset
    else:
        global_offset = _get_global_article_offset(
            series_no or 0, active_stage_no or stage_no
        )
    article_no = 1

    for group in group_results or []:
        text = (group.get("text") or "").strip()
        if not text:
            continue
        parsed = parse_outline_text(text)
        if not parsed["outline_lines"]:
            continue

        title = (group.get("title") or "").strip() or f"分组 {article_no}"
        global_article_no = global_offset + article_no - 1

        try:
            if is_pano and outline_sources:
                result = await ministerialize_one_article_pano(
                    article_no=global_article_no,
                    article_title=group.get("title", ""),
                    text=group.get("text", ""),
                    series_title=series_title,
                    stage_no=stage_no,
                    outline_sources=outline_sources,
                )
            else:
                result = await ministerialize_one_article(
                    article_no=global_article_no,
                    article_title=title,
                    text=text,
                    series_title=series_title,
                    stage_no=stage_no,
                )
        except Exception:
            logger.exception(
                "[progress_outline] ministerialize_segment 单篇异常 article_no=%s",
                article_no,
            )
            article_no += 1
            continue

        articles.append(result)
        if "usage" in result and "error" not in result:
            _merge_usage(total_usage, result)
        article_no += 1

    return {
        "articles": articles,
        "total_ministerialize_usage": total_usage,
    }
