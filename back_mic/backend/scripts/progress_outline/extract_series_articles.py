# -*- coding: utf-8 -*-
"""从终稿篇目 docx 读取篇题列表，在 Books 中定位并复制对应篇目 docx。"""
from __future__ import annotations

import re
import shutil
import sys
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path

from docx import Document

_SCRIPT_DIR = Path(__file__).resolve().parent
if str(_SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR))

from build_ministry_catalog import (  # noqa: E402
    LEE_ROOT,
    NI_ROOT,
    STAGE_LABELS,
    parse_volume_folder,
    stage_for_lee,
    strip_index_prefix,
    to_zh_num,
    vol_sort_key,
)

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SOURCE_DIR = Path(r"D:\workspace\启示进展研究\补充系列\抓取篇题内容")
OUT_BASE = SOURCE_DIR

SERIES_DOCX: dict[str, str] = {
    "基督的身位与工作": "基督的身位与工作_46.docx",
    "青少年儿童工作": "青少年儿童工作_44.docx",
    "新妇": "新妇_47.docx",
    "召会生活": "召会生活_100.docx",
}

STAGE_ZH = ["", "壹", "贰", "叁", "肆", "伍", "陆"]
STAGE_FROM_ZH = {v: i for i, v in enumerate(STAGE_ZH) if v}

BOOK_HEADER_RE = re.compile(
    r"^([一二三四五六七八九十百千万]+)[\u3000\s]+(.+?)(?:——|—)"
)
VOLUME_IN_PARENS_RE = re.compile(r"（([^）]+)）\s*$")
ARTICLE_LINE_RE = re.compile(
    r"^(?:【筛除】\s*)?"
    r"第([一二三四五六七八九十百千万〇零\d]+)[篇章节][\u3000\s]+"
    r"(.+?)(?:（其中有一?个标题：.+）)?\s*$"
)
CN_DIGITS = "〇一二三四五六七八九"


def clean_book_name(book: str) -> str:
    return re.sub(r"^[壹贰貳叁參叄肆伍陆陸柒捌玖拾][\u3000\s]+", "", book.strip())


def norm_text(text: str) -> str:
    return re.sub(r"[\s\u3000]+", "", text)


def cn_to_int(text: str) -> int | None:
    text = text.strip()
    if text.isdigit():
        return int(text)
    if text in CN_DIGITS:
        return CN_DIGITS.index(text)
    if text == "十":
        return 10
    if text.startswith("十") and len(text) == 2 and text[1] in CN_DIGITS:
        return 10 + CN_DIGITS.index(text[1])
    if "十" in text:
        left, _, right = text.partition("十")
        tens = CN_DIGITS.index(left) if left else 1
        ones = CN_DIGITS.index(right) if right else 0
        return tens * 10 + ones
    return None


def parse_volume_book(line: str) -> tuple[str, str] | None:
    line = line.strip()
    m = BOOK_HEADER_RE.match(line)
    if not m:
        return None
    book = clean_book_name(m.group(2).strip())
    vm = VOLUME_IN_PARENS_RE.search(line)
    if not vm:
        return None
    volume = vm.group(1).strip()
    if "，" in volume and volume.count("，") == 1:
        # 如「李常受文集一九九四至一九九七年第二册，圣经的内在启示」
        vol_part, book_part = volume.split("，", 1)
        if book_part and book_part in book:
            volume = vol_part.strip()
        elif book_part and book not in book_part:
            book = book_part.strip()
    return volume, book


def parse_stage_heading(text: str) -> int | None:
    text = text.strip()
    zh = text[:1]
    if zh in STAGE_FROM_ZH:
        return STAGE_FROM_ZH[zh]
    return None


@dataclass
class CatalogEntry:
    stage: int
    volume: str
    book: str
    title_line: str
    article_no: int | None
    core_title: str


@dataclass
class BookArticle:
    stage: int
    volume: str
    book: str
    article_no: int
    title: str
    path: Path


def parse_review_docx(path: Path) -> list[CatalogEntry]:
    doc = Document(path)
    entries: list[CatalogEntry] = []
    stage = 0
    volume = ""
    book = ""

    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style = para.style.name

        if style == "Heading 2":
            sn = parse_stage_heading(text)
            if sn:
                stage = sn
            continue

        if style == "Normal":
            parsed = parse_volume_book(text)
            if parsed:
                volume, book = parsed
            continue

        if style != "List Number":
            continue

        if text.startswith("【筛除】"):
            continue

        parsed_book = parse_volume_book(text)
        if parsed_book:
            volume, book = parsed_book
            continue

        am = ARTICLE_LINE_RE.match(text)
        if not am or not volume or not book:
            continue

        article_no = cn_to_int(am.group(1))
        core_title = am.group(2).strip()
        entries.append(
            CatalogEntry(
                stage=stage,
                volume=volume,
                book=book,
                title_line=text,
                article_no=article_no,
                core_title=core_title,
            )
        )

    return entries


def build_books_index() -> list[BookArticle]:
    from build_ministry_catalog import parse_msg

    articles: list[BookArticle] = []
    for root, default_stage in ((NI_ROOT, 1), (LEE_ROOT, None)):
        if not root.is_dir():
            raise SystemExit(f"Books 目录不存在: {root}")
        for vol_dir in sorted(root.iterdir(), key=vol_sort_key):
            if not vol_dir.is_dir():
                continue
            volume_name, default_book = parse_volume_folder(vol_dir)
            stage = default_stage or stage_for_lee(volume_name) or 0
            for docx in sorted(vol_dir.rglob("*.docx")):
                if docx.name.startswith("~"):
                    continue
                parsed = parse_msg(docx.stem)
                if not parsed:
                    continue
                article_no, title = parsed
                if docx.parent == vol_dir:
                    book_name = default_book or volume_name
                else:
                    book_name = strip_index_prefix(docx.parent.name)
                articles.append(
                    BookArticle(
                        stage=stage,
                        volume=volume_name,
                        book=book_name,
                        article_no=article_no,
                        title=title,
                        path=docx,
                    )
                )
    return articles


def volume_match(a: str, b: str) -> bool:
    na, nb = norm_text(a), norm_text(b)
    return na in nb or nb in na


def book_match(a: str, b: str) -> bool:
    a, b = clean_book_name(a), clean_book_name(b)
    na, nb = norm_text(a), norm_text(b)
    if na == nb or na in nb or nb in na:
        return True
    a_base = re.sub(r"[（(].+[）)]", "", a)
    b_base = re.sub(r"[（(].+[）)]", "", b)
    return norm_text(a_base) in norm_text(b_base) or norm_text(b_base) in norm_text(a_base)


def title_similarity(a: str, b: str) -> float:
    na, nb = norm_text(a), norm_text(b)
    if na == nb:
        return 1.0
    if na in nb or nb in na:
        return 0.95
    return SequenceMatcher(None, na, nb).ratio()


def find_article(entry: CatalogEntry, index: list[BookArticle]) -> BookArticle | None:
    candidates = [
        art
        for art in index
        if volume_match(entry.volume, art.volume) and book_match(entry.book, art.book)
    ]

    if candidates and entry.article_no is not None:
        by_no = [a for a in candidates if a.article_no == entry.article_no]
        if len(by_no) == 1:
            return by_no[0]
        if by_no:
            candidates = by_no

    if candidates:
        scored = sorted(
            candidates,
            key=lambda art: title_similarity(entry.core_title, art.title),
            reverse=True,
        )
        best = scored[0]
        if title_similarity(entry.core_title, best.title) >= 0.55:
            return best

    # 终稿 docx 偶有册名/书名偏差，按阶段 + 篇题回退匹配
    stage_pool = [a for a in index if a.stage == entry.stage] if entry.stage else index
    scored = sorted(
        stage_pool,
        key=lambda art: title_similarity(entry.core_title, art.title),
        reverse=True,
    )
    if not scored:
        return None
    best = scored[0]
    if title_similarity(entry.core_title, best.title) >= 0.82:
        return best
    return None


def safe_filename(text: str, max_len: int = 120) -> str:
    name = re.sub(r'[<>:"/\\|?*]', "_", text)
    return name[:max_len].rstrip(" ._")


def copy_series(series_name: str, docx_name: str, index: list[BookArticle]) -> dict:
    src_docx = SOURCE_DIR / docx_name
    if not src_docx.is_file():
        raise FileNotFoundError(f"未找到篇目文档: {src_docx}")

    entries = parse_review_docx(src_docx)
    out_dir = OUT_BASE / series_name
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    copied: list[tuple[CatalogEntry, Path]] = []
    missing: list[CatalogEntry] = []

    for seq, entry in enumerate(entries, start=1):
        art = find_article(entry, index)
        if not art:
            missing.append(entry)
            continue

        stage_label = STAGE_LABELS.get(entry.stage, f"阶段{entry.stage}")
        stage_dir = out_dir / safe_filename(f"{STAGE_ZH[entry.stage]}_{stage_label}")
        stage_dir.mkdir(parents=True, exist_ok=True)

        book_dir = stage_dir / safe_filename(entry.book)
        book_dir.mkdir(parents=True, exist_ok=True)

        prefix = f"{seq:03d}_"
        if entry.article_no is not None:
            prefix += f"第{to_zh_num(entry.article_no)}篇_"
        dest_name = prefix + safe_filename(entry.core_title) + ".docx"
        dest = book_dir / dest_name
        shutil.copy2(art.path, dest)
        copied.append((entry, dest))

    missing_keys = {
        (e.stage, e.volume, e.book, e.title_line) for e in missing
    }

    index_path = out_dir / "_篇目目录.md"
    lines = [
        f"# {series_name}",
        "",
        f"来源：{docx_name}",
        f"共 {len(entries)} 篇，已复制 {len(copied)} 篇，未匹配 {len(missing)} 篇。",
        "",
    ]
    last_key = None
    for entry in entries:
        key = (entry.stage, entry.volume, entry.book)
        if key != last_key:
            lines.append(f"### {entry.book}（{entry.volume}）")
            lines.append("")
            last_key = key
        status = (
            "✗"
            if (entry.stage, entry.volume, entry.book, entry.title_line) in missing_keys
            else "✓"
        )
        lines.append(f"- [{status}] {entry.title_line}")
    if missing:
        lines.extend(["", "## 未匹配篇目", ""])
        for entry in missing:
            lines.append(
                f"- 阶段{entry.stage} | {entry.volume} | {entry.book} | {entry.title_line}"
            )
    index_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "series": series_name,
        "expected": len(entries),
        "copied": len(copied),
        "missing": missing,
        "out_dir": out_dir,
    }


def main() -> None:
    print("正在索引 Books …")
    index = build_books_index()
    print(f"Books 共 {len(index)} 篇")

    results = []
    for series_name, docx_name in SERIES_DOCX.items():
        print(f"\n处理系列：{series_name}")
        result = copy_series(series_name, docx_name, index)
        results.append(result)
        print(
            f"  篇目 {result['expected']}，复制 {result['copied']}，"
            f"未匹配 {len(result['missing'])}"
        )
        if result["missing"]:
            for entry in result["missing"][:5]:
                print(f"    ✗ {entry.book} / {entry.title_line}")
            if len(result["missing"]) > 5:
                print(f"    … 另有 {len(result['missing']) - 5} 篇")

    print("\n=== 汇总 ===")
    for r in results:
        print(
            f"{r['series']}: {r['copied']}/{r['expected']} -> {r['out_dir']}"
        )


if __name__ == "__main__":
    main()
