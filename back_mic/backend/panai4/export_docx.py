# -*- coding: utf-8 -*-
"""按步骤导出 docx。不写入运行编号、费用或 Prompt 版本。"""
from __future__ import annotations

import io
import re
import zipfile
from urllib.parse import quote

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

from .pipeline import STEP_LABELS, extract_burden_body

EXPORT_STEPS = ("burden", "skeleton", "orig_skeleton", "diagnosis")
_FONT = "Microsoft YaHei"
_ILLEGAL = set('\\/:*?"<>|')


def safe_filename_part(text: str, limit: int | None = None) -> str:
    raw = (text or "").strip()
    if limit is not None:
        raw = raw[:limit]
    cleaned = []
    for char in raw:
        if char in _ILLEGAL or ord(char) < 32:
            cleaned.append("_")
        else:
            cleaned.append(char)
    name = "".join(cleaned).strip(" .")
    return name or "未命名"


def docx_filename(position: int, title: str, step: str) -> str:
    label = STEP_LABELS.get(step, step)
    return f"【{label}】第{position}篇_{safe_filename_part(title, 30)}.docx"


def article_folder(position: int, title: str) -> str:
    return f"第{position}篇_{safe_filename_part(title, 30)}"


def content_disposition(filename: str) -> str:
    encoded = quote(filename)
    return f"attachment; filename*=UTF-8''{encoded}"


def _set_run_font(run, size_pt: float, bold: bool = False) -> None:
    run.bold = bold
    run.font.size = Pt(size_pt)
    run.font.name = _FONT
    rpr = run._element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), _FONT)


def _set_paragraph_format(paragraph, *, align=None, heading: bool = False) -> None:
    fmt = paragraph.paragraph_format
    if heading:
        fmt.line_spacing_rule = WD_LINE_SPACING.SINGLE
        fmt.space_before = Pt(6)
        fmt.space_after = Pt(6)
    else:
        fmt.line_spacing_rule = WD_LINE_SPACING.EXACTLY
        fmt.line_spacing = Pt(20)
        fmt.space_before = Pt(2)
        fmt.space_after = Pt(2)
    if align is not None:
        paragraph.alignment = align


def _em_width(text: str) -> float:
    width = 0.0
    for char in text:
        width += 6.0 if ord(char) < 128 else 12.0
    return width


_HASH = re.compile(r"^(#{1,6})\s?")
_BULLET = re.compile(r"^[-*]\s+")
_BOLD = re.compile(r"\*\*(.+?)\*\*")
_NUMBERED = re.compile(r"^(\d+\.\s+)")
_PAREN_CN = re.compile(r"^([（(][一二三四五六七八九十]+[）)])")
_PAREN_NUM = re.compile(r"^([（(]\d+[）)])")
_LETTER = re.compile(r"^([A-Za-z])(?![A-Za-z])")
_MAJOR = re.compile(r"^([壹贰叁肆伍陆柒捌玖拾]+)")
_MINOR = re.compile(r"^([一二三四五六七八九十]+)")
_DIGIT = re.compile(r"^(\d+)")


def _bold_runs(text: str) -> list[tuple[str, bool]]:
    parts: list[tuple[str, bool]] = []
    pos = 0
    for match in _BOLD.finditer(text):
        if match.start() > pos:
            parts.append((text[pos : match.start()], False))
        parts.append((match.group(1), True))
        pos = match.end()
    if pos < len(text) or not parts:
        parts.append((text[pos:], False))
    return parts


def model_paragraphs(text: str, step: str) -> list[dict]:
    numbered = step in {"skeleton", "orig_skeleton"}
    number = 0
    paragraphs = []
    for line in _split_lines(text):
        heading = False
        hash_match = _HASH.match(line)
        if hash_match:
            line = line[hash_match.end() :]
            heading = True
        prefix = ""
        bullet = _BULLET.match(line)
        if bullet and not heading:
            line = line[bullet.end() :]
            if numbered:
                number += 1
                prefix = f"{number}. "
        elif line.strip():
            number = 0
            existing = _NUMBERED.match(line) if numbered else None
            if existing:
                prefix = existing.group(1)
                line = line[existing.end() :]
        runs = _bold_runs(line)
        if prefix:
            runs = [(prefix, False), *runs]
        if heading or (step == "diagnosis" and "".join(piece for piece, _bold in runs).startswith("【")):
            runs = [(piece, True) for piece, _bold in runs]
        paragraphs.append({"runs": runs, "hang": _em_width(prefix), "left": 0.0})
    return paragraphs


def format_outline_line(line: str) -> tuple[float, float, str]:
    """返回（层级左缩进磅值, 悬挂宽度磅值, 显示文字）。不删除、不改动非 Tab 的文字。"""
    if line == "":
        return 0.0, 0.0, ""
    for level, pattern in (
        (6, _PAREN_CN),
        (6, _PAREN_NUM),
        (6, _LETTER),
        (0, _MAJOR),
        (2, _MINOR),
        (4, _DIGIT),
    ):
        match = pattern.match(line)
        if not match:
            continue
        prefix = match.group(1)
        rest = line[match.end() :]
        if rest.startswith(("、", ".", "．")):
            prefix += rest[0]
            rest = rest[1:]
        if rest.startswith("\t"):
            rest = rest[1:]
            prefix += "\u3000"
        return float(level * 12), _em_width(prefix), prefix + rest
    return 0.0, 0.0, line


def _add_heading(document: Document, text: str, size_pt: float, align=None) -> None:
    paragraph = document.add_paragraph()
    _set_paragraph_format(paragraph, align=align, heading=True)
    run = paragraph.add_run(text)
    _set_run_font(run, size_pt, True)


def _add_body(document: Document, runs: list[tuple[str, bool]], *, left: float = 0, hang: float = 0) -> None:
    paragraph = document.add_paragraph()
    _set_paragraph_format(paragraph, heading=False)
    if hang or left:
        paragraph.paragraph_format.left_indent = Pt(left + hang)
        paragraph.paragraph_format.first_line_indent = Pt(-hang)
    if not runs:
        runs = [("", False)]
    for text, bold in runs:
        run = paragraph.add_run(text)
        _set_run_font(run, 12, bold)


def _prepare_document() -> Document:
    document = Document()
    section = document.sections[0]
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.2)
    section.bottom_margin = Cm(2.0)
    section.left_margin = Cm(2.2)
    section.right_margin = Cm(2.2)
    section.gutter = Cm(0)
    section.header.is_linked_to_previous = False
    section.header.paragraphs[0].text = ""
    section.footer.is_linked_to_previous = False
    footer = section.footer.paragraphs[0]
    footer.text = ""
    _add_page_number(footer)
    normal = document.styles["Normal"]
    normal.font.name = _FONT
    normal.font.size = Pt(12)
    rpr = normal.element.get_or_add_rPr()
    rfonts = rpr.find(qn("w:rFonts"))
    if rfonts is None:
        rfonts = OxmlElement("w:rFonts")
        rpr.append(rfonts)
    for attr in ("w:ascii", "w:hAnsi", "w:eastAsia", "w:cs"):
        rfonts.set(qn(attr), _FONT)
    return document


_LIST_MARK = re.compile(r"^(?:[-*•]\s+|•|\d+[.、．)]\s*|\d+\s+)")


def number_skeleton(text: str) -> str:
    """只用于显示和导出。不写回数据库。"""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    listed = any(line.strip() and _LIST_MARK.match(line) for line in lines)
    if listed:
        number = 0
        out = []
        for line in lines:
            if not line.strip() or _HASH.match(line):
                out.append(line)
                continue
            number += 1
            out.append(f"{number}. {_LIST_MARK.sub('', line, count=1)}")
        return "\n".join(out)
    paragraphs = []
    current = []
    for line in lines:
        if not line.strip():
            if current:
                paragraphs.append(current)
                current = []
        else:
            current.append(line)
    if current:
        paragraphs.append(current)
    out = []
    for index, paragraph in enumerate(paragraphs, start=1):
        if out:
            out.append("")
        first, *rest = paragraph
        out.append(f"{index}. {first}")
        out.extend(rest)
    return "\n".join(out)


def build_docx(title: str, step: str, body: str, appendix: str | None = None, position: int = 1) -> bytes:
    document = _prepare_document()
    if step in {"skeleton", "orig_skeleton"}:
        body = number_skeleton(body)
    _add_heading(document, f"第{position}篇\u3000{title}", 16, WD_ALIGN_PARAGRAPH.CENTER)
    _add_heading(document, STEP_LABELS.get(step, step), 14)
    for paragraph in model_paragraphs(body, step):
        _add_body(document, paragraph["runs"], left=paragraph["left"], hang=paragraph["hang"])
    if appendix is not None:
        _add_heading(document, "附：原纲目全文", 14)
        for line in _split_lines(appendix):
            left, hang, text = format_outline_line(line)
            _add_body(document, [(text, False)], left=left, hang=hang)
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()


def _add_page_number(paragraph) -> None:
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER

    def _holder():
        run = paragraph.add_run()
        _set_run_font(run, 12, False)
        return run._r

    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    separate = OxmlElement("w:fldChar")
    separate.set(qn("w:fldCharType"), "separate")
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    _holder().append(begin)
    _holder().append(instr)
    tail = _holder()
    tail.append(separate)
    tail.append(end)


def _split_lines(text: str) -> list[str]:
    normalized = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    if normalized == "":
        return [""]
    return normalized.split("\n")


def step_body(step: str, output_text: str, original_outline: str | None) -> tuple[str, str | None]:
    if step == "burden":
        return extract_burden_body(output_text or ""), None
    if step == "orig_skeleton":
        return output_text or "", original_outline or ""
    return output_text or "", None


def build_step_docx(item: dict, step_row: dict) -> tuple[str, bytes]:
    step = step_row["step"]
    body, appendix = step_body(step, step_row.get("output_text") or "", item.get("original_outline"))
    filename = docx_filename(item["position"], item["title"], step)
    return filename, build_docx(item["title"], step, body, appendix, item["position"])


def completed_export_steps(steps: list[dict]) -> list[dict]:
    return [step for step in steps if step.get("step") in EXPORT_STEPS and step.get("status") == "done"]


def build_article_zip(item: dict, steps: list[dict]) -> tuple[str, bytes]:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for step in completed_export_steps(steps):
            name, data = build_step_docx(item, step)
            archive.writestr(name, data)
    filename = f"{article_folder(item['position'], item['title'])}.zip"
    return filename, buffer.getvalue()


def build_run_zip(items: list[tuple[dict, list[dict]]]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for item, steps in items:
            folder = article_folder(item["position"], item["title"])
            for step in completed_export_steps(steps):
                name, data = build_step_docx(item, step)
                archive.writestr(f"{folder}/{name}", data)
    return buffer.getvalue()
