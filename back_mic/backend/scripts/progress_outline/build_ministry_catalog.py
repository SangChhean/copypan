# -*- coding: utf-8 -*-
"""从 Books 文件夹生成按六阶段归类的册名、书名、篇题目录。"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterator

try:
    import cn2an
except ImportError:
    cn2an = None  # type: ignore

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

SCRIPT_DIR = Path(__file__).resolve().parent
CATALOG_MD = SCRIPT_DIR / "ministry_catalog_by_stage.md"
BOOKNAMES_TXT = SCRIPT_DIR / "ministry_booknames_by_stage.txt"

NI_ROOT = Path(r"D:/workspace/Books/1 倪柝声文集")
LEE_ROOT = Path(r"D:/workspace/Books/2 李常受文集")

STAGE_LABELS = {
    1: "倪柝声弟兄职事",
    2: "李常受弟兄职事第一阶段（1932-1960）",
    3: "李常受弟兄职事第二阶段（1961-1973）",
    4: "李常受弟兄职事第三阶段（1974-1984）",
    5: "李常受弟兄职事第四阶段（1985-1990）",
    6: "李常受弟兄职事第五阶段（1991-1997）",
}

STAGE_YEAR_RANGES = {
    2: (1932, 1960),
    3: (1961, 1973),
    4: (1974, 1984),
    5: (1985, 1990),
    6: (1991, 1997),
}

SUPPLEMENT_VOL_KEYS = ("圣经笔记与诗歌", "信函与拾遗")

MSG_RE = re.compile(r"^msg\.?\s*(\d+)\s+(.+)$", re.I)
INDEX_PREFIX_RE = re.compile(r"^\d+\s+(.+)$")


def strip_index_prefix(name: str) -> str:
    m = INDEX_PREFIX_RE.match(name.strip())
    return m.group(1) if m else name.strip()


def cn_year(text: str) -> int | None:
    if not cn2an:
        return None
    try:
        y = int(cn2an.cn2an(text, "smart"))
        return y if 1000 <= y <= 2100 else None
    except Exception:
        return None


def parse_years(text: str) -> list[int]:
    years = [int(y) for y in re.findall(r"(19\d{2}|20\d{2})", text)]
    for m in re.finditer(r"([一二三四五六七八九十〇零]{2,12})年", text):
        y = cn_year(m.group(1))
        if y:
            years.append(y)
    for m in re.finditer(r"([一二三四五六七八九十〇零]{2,8})至([一二三四五六七八九十〇零]{2,8})年", text):
        a, b = cn_year(m.group(1)), cn_year(m.group(2))
        if a:
            years.append(a)
        if b:
            years.append(b)
    return years


def stage_for_lee(volume_name: str) -> int | None:
    for key in SUPPLEMENT_VOL_KEYS:
        if key in volume_name:
            return 6
    years = parse_years(volume_name)
    if not years:
        return None
    y_min, y_max = min(years), max(years)
    for sn, (lo, hi) in STAGE_YEAR_RANGES.items():
        if y_min <= hi and y_max >= lo:
            return sn
    return None


def parse_volume_folder(vol_dir: Path) -> tuple[str, str | None]:
    """返回 (册名, 无子文件夹时的默认书名)。"""
    full = strip_index_prefix(vol_dir.name)
    if "，" in full:
        volume_name, default_book = full.split("，", 1)
        return volume_name.strip(), default_book.strip()
    return full, None


def parse_msg(stem: str) -> tuple[int, str] | None:
    m = MSG_RE.match(stem.strip())
    if not m:
        return None
    return int(m.group(1)), m.group(2).strip()


def to_zh_num(n: int) -> str:
    digits = "〇一二三四五六七八九"
    if n < 10:
        return digits[n]
    if n < 20:
        return "十" + (digits[n % 10] if n % 10 else "")
    if n < 100:
        tens, ones = divmod(n, 10)
        text = digits[tens] + "十"
        if ones:
            text += digits[ones]
        return text
    return str(n)


def vol_sort_key(vol_dir: Path) -> int:
    m = re.match(r"^(\d+)", vol_dir.name)
    return int(m.group(1)) if m else 0


def iter_articles(vol_dir: Path) -> Iterator[tuple[str, str, int, str]]:
    """
    遍历一册内全部篇目。
    册名：卷文件夹名（逗号前，或整段无逗号时全文）
    书名：msg 父文件夹名（去编号）；若 docx 直接在卷根目录，则用逗号后书名或册名
    """
    volume_name, default_book = parse_volume_folder(vol_dir)
    for docx in sorted(vol_dir.rglob("*.docx")):
        if docx.name.startswith("~"):
            continue
        parsed = parse_msg(docx.stem)
        if not parsed:
            continue
        article_no, article_title = parsed
        if docx.parent == vol_dir:
            book_name = default_book or volume_name
        else:
            book_name = strip_index_prefix(docx.parent.name)
        yield volume_name, book_name, article_no, article_title


def collect_stage_records() -> dict[int, list[dict]]:
    records: dict[int, list[dict]] = defaultdict(list)

    for vol_dir in sorted(NI_ROOT.iterdir(), key=vol_sort_key):
        if not vol_dir.is_dir():
            continue
        for volume_name, book_name, article_no, article_title in iter_articles(vol_dir):
            records[1].append(
                {
                    "volume": volume_name,
                    "book": book_name,
                    "article_no": article_no,
                    "title": f"第{to_zh_num(article_no)}篇　{article_title}",
                }
            )

    for vol_dir in sorted(LEE_ROOT.iterdir(), key=vol_sort_key):
        if not vol_dir.is_dir():
            continue
        volume_name, _ = parse_volume_folder(vol_dir)
        sn = stage_for_lee(volume_name)
        if sn is None:
            continue
        for volume_name, book_name, article_no, article_title in iter_articles(vol_dir):
            records[sn].append(
                {
                    "volume": volume_name,
                    "book": book_name,
                    "article_no": article_no,
                    "title": f"第{to_zh_num(article_no)}篇　{article_title}",
                }
            )

    for sn in records:
        records[sn].sort(
            key=lambda r: (r["volume"], r["book"], r["article_no"])
        )
    return records


def write_catalog_md(records: dict[int, list[dict]]) -> None:
    lines = [
        "# 倪文集与李文集：按六阶段书目与篇题目录",
        "",
        "数据来源：`D:\\\\workspace\\\\Books\\\\1 倪柝声文集`、`D:\\\\workspace\\\\Books\\\\2 李常受文集`",
        "",
        "字段说明：",
        "- **册名**：文集卷文件夹名（如「李常受文集一九六一至一九六二年第二册」）",
        "- **书名**：msg 文件所在最后一层子文件夹名；若无子文件夹，则为卷名逗号后的书名",
        "- **篇题**：msg 文件名中的篇目名称",
        "",
    ]

    for sn in range(1, 7):
        items = records.get(sn, [])
        if not items:
            continue
        lines.append(f"## {sn}. {STAGE_LABELS[sn]}")
        lines.append("")
        books = {(r["volume"], r["book"]) for r in items}
        lines.append(f"共 **{len(books)}** 个书名，**{len(items)}** 篇。")
        lines.append("")

        cur_volume = None
        cur_book = None
        for r in items:
            if r["volume"] != cur_volume:
                cur_volume = r["volume"]
                cur_book = None
                lines.append(f"### 册：{cur_volume}")
                lines.append("")
            if r["book"] != cur_book:
                cur_book = r["book"]
                lines.append(f"#### {cur_book}")
                lines.append("")
            lines.append(f"- {r['title']}")
        lines.append("")

    CATALOG_MD.write_text("\n".join(lines), encoding="utf-8")


def write_booknames_txt(records: dict[int, list[dict]]) -> None:
    lines: list[str] = []
    for sn in range(1, 7):
        items = records.get(sn, [])
        if not items:
            continue
        lines.append(f"## {sn}. {STAGE_LABELS[sn]}")
        books = sorted({(r["volume"], r["book"]) for r in items})
        lines.append(f"共 **{len(books)}** 个书名，**{len(items)}** 篇。")
        lines.append("")
        for volume, book in books:
            lines.append(f"{volume}，{book}")
        lines.append("")
    BOOKNAMES_TXT.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    if not NI_ROOT.is_dir() or not LEE_ROOT.is_dir():
        raise SystemExit(f"Books 目录不存在: {NI_ROOT} / {LEE_ROOT}")

    records = collect_stage_records()
    write_catalog_md(records)
    write_booknames_txt(records)

    for sn in range(1, 7):
        items = records.get(sn, [])
        books = len({(r["volume"], r["book"]) for r in items})
        print(f"阶段{sn}: {books} 书名, {len(items)} 篇")
    print(f"已写入 {CATALOG_MD}")
    print(f"已写入 {BOOKNAMES_TXT}")


if __name__ == "__main__":
    main()
