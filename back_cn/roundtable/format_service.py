# -*- coding: utf-8 -*-
"""Step 4：把结构化 JSON 转成可读纯文本 / HTML 预览（供人工确认）。"""
from __future__ import annotations

import html


def _reading_and_hymn_line(unified_fields: dict) -> str:
    verses = unified_fields["verses"]
    verse_display = (
        verses[1]["display"]
        if len(verses) > 1 and verses[1].get("display")
        else verses[0].get("display", "")
    )
    hymn = unified_fields.get("hymn")
    if hymn:
        hymn_line = f"诗歌：{hymn['source']}{hymn['no']}"
    else:
        # 正常情况不应该走到：Step1 已要求必须给出有效诗歌，重试用尽会直接报错。
        # 若仍出现，说明诗歌重试机制失效或上游传入了残缺 unified_fields，需要排查。
        hymn_line = "诗歌：（未找到贴合主题的推荐）"
    return f"读经：{verse_display}　　{hymn_line}"


def format_version_preview(unified_fields: dict, version_result: dict) -> str:
    """
    把 Step1 统一字段 + Step2 某个版本的结构化结果，拼成 SOP 要求的纯文本格式：
    标题 → 整体出处 → 读经(经节+诗歌) → 经文全文 → [鸟瞰纲目，仅真理版] → 各篇摘要 → 彼此问互相答

    不输出「【鸟瞰纲目】」「【篇标题】」这类方括号标记行。
    """
    lines: list[str] = []
    lines.append(unified_fields["title"])
    lines.append(unified_fields["overall_source"])
    lines.append("")

    lines.append(_reading_and_hymn_line(unified_fields))
    lines.append("")

    verses = unified_fields["verses"]
    for v in verses:
        ref = v.get("ref_gb") or v.get("display") or ""
        lines.append(f"{ref}　{v['text']}")
    lines.append("")

    data = version_result["data"]

    if data.get("outline"):
        cn_major = "壹贰叁肆伍陆柒捌玖拾"
        cn_minor = "一二三四五六七八九十"
        for i, mp in enumerate(data["outline"]["major_points"]):
            major_num = cn_major[i] if i < len(cn_major) else str(i + 1)
            lines.append(f"{major_num}\t{mp['text']}")
            for j, minp in enumerate(mp.get("minor_points", [])):
                minor_num = cn_minor[j] if j < len(cn_minor) else str(j + 1)
                lines.append(f"\t{minor_num}\t{minp['text']}")
        lines.append("")

    for sec in data.get("sections", []):
        for sub in sec.get("subsections", []):
            lines.append(sub["heading"])
            for p in sub.get("paragraphs", []):
                lines.append(p["text"])
        # source_line 紧跟最后一段正文，中间不插空行
        lines.append(sec.get("source_line", ""))

    lines.append("")
    lines.append("彼此问互相答：")
    for i, qa in enumerate(data.get("qa", []), 1):
        lines.append(f"{i}. {qa['question']}")

    return "\n".join(lines)


def format_version_preview_html(unified_fields: dict, version_result: dict) -> str:
    """
    与 format_version_preview 同结构的 HTML 预览：
    标题 / 整体出处居中加粗；小标题加粗；正文普通；无方括号标记行。
    source_line 紧跟最后一段正文 <p>，不加额外空标签或 margin-top。
    """
    esc = html.escape
    parts: list[str] = []

    parts.append(
        '<p style="text-align:center;font-weight:bold;margin:0 0 0.4em 0;">'
        f"{esc(unified_fields['title'])}</p>"
    )
    parts.append(
        '<p style="text-align:center;font-weight:bold;margin:0 0 1em 0;">'
        f"{esc(unified_fields['overall_source'])}</p>"
    )
    parts.append(
        f'<p style="margin:0 0 0.6em 0;">{esc(_reading_and_hymn_line(unified_fields))}</p>'
    )

    verses = unified_fields["verses"]
    for v in verses:
        ref = v.get("ref_gb") or v.get("display") or ""
        line = f"{ref}　{v['text']}"
        parts.append(f'<p style="margin:0 0 0.35em 0;">{esc(line)}</p>')
    parts.append('<p style="margin:0 0 0.8em 0;">&nbsp;</p>')

    data = version_result["data"]

    if data.get("outline"):
        cn_major = "壹贰叁肆伍陆柒捌玖拾"
        cn_minor = "一二三四五六七八九十"
        for i, mp in enumerate(data["outline"]["major_points"]):
            major_num = cn_major[i] if i < len(cn_major) else str(i + 1)
            parts.append(
                '<p style="margin:0 0 0.35em 0;font-weight:bold;">'
                f"{esc(major_num)}\t{esc(mp['text'])}</p>"
            )
            for j, minp in enumerate(mp.get("minor_points", [])):
                minor_num = cn_minor[j] if j < len(cn_minor) else str(j + 1)
                parts.append(
                    '<p style="margin:0 0 0.35em 0;padding-left:1.5em;">'
                    f"{esc(minor_num)}\t{esc(minp['text'])}</p>"
                )
        parts.append('<p style="margin:0 0 0.8em 0;">&nbsp;</p>')

    for sec in data.get("sections", []):
        for sub in sec.get("subsections", []):
            parts.append(
                '<p style="margin:0.6em 0 0.35em 0;font-weight:bold;">'
                f"{esc(sub['heading'])}</p>"
            )
            for p in sub.get("paragraphs", []):
                parts.append(
                    f'<p style="margin:0 0 0.35em 0;">{esc(p["text"])}</p>'
                )
        source_line = sec.get("source_line", "") or ""
        # 紧跟正文，不另加 margin-top / 空标签
        parts.append(f'<p style="margin:0;">{esc(source_line)}</p>')

    parts.append(
        '<p style="margin:1em 0 0.35em 0;font-weight:bold;">彼此问互相答：</p>'
    )
    for i, qa in enumerate(data.get("qa", []), 1):
        qline = f"{i}. {qa['question']}"
        parts.append(f'<p style="margin:0 0 0.35em 0;">{esc(qline)}</p>')

    return "\n".join(parts)
