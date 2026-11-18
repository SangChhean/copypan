# -*- coding: utf-8 -*-
"""取经文：读取本地 bible_data（改写自 3.0 back_qa/qa/bible_service.py 的取经文部分）。

与 3.0 的差别：
- 去掉问答流水线依赖；按卷懒加载，只保留取经文需要的字段（中文、纯文本、出处、脚注、标题）。
- 目录走 settings.bible_dir（QA4_DATA_DIR 下的 bible_data）。
- 卷号 1–66 与标准简称（创…启）互转，简称表来自 vendor v2.1 的 STD_ORDER。
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Optional

from scripture.vendor_get_vers_v21 import STD2IDX, STD_ORDER

_KEEP_VERSE_KEYS = (
    "verse",
    "ref_gb",
    "ref_big5",
    "ref_en",
    "text_gb",
    "text_big5",
    "text_en",
    "text_gb_plain",
    "text_big5_plain",
    "footnotes",
    "crossrefs",
)


class BibleDataError(RuntimeError):
    pass


def book_no_of(std: str) -> Optional[int]:
    return STD2IDX.get(std)


def std_of(book_no: int) -> Optional[str]:
    if 1 <= int(book_no) <= len(STD_ORDER):
        return STD_ORDER[int(book_no) - 1]
    return None


@dataclass
class BookData:
    book_no: int
    name_gb: str
    abbr_gb: str
    chapters: dict[int, dict[int, dict[str, Any]]] = field(default_factory=dict)
    chapter_titles: dict[int, str] = field(default_factory=dict)


class BibleText:
    """本地圣经数据。线程安全的懒加载。"""

    def __init__(self, bible_dir: Path) -> None:
        self.bible_dir = Path(bible_dir)
        self._files: dict[int, Path] = {}
        self._books: dict[int, BookData] = {}
        self._lock = threading.Lock()
        self._scan()

    # ---------------- 加载 ----------------
    def _scan(self) -> None:
        if not self.bible_dir.is_dir():
            raise BibleDataError("bible_data 目录不存在：data/bible_data")
        for p in sorted(self.bible_dir.glob("*.json")):
            if p.name.lower() == "index.json":
                continue
            head = p.name.split("_", 1)[0]
            if head.isdigit():
                self._files[int(head)] = p

    @property
    def files(self) -> dict[int, Path]:
        return dict(self._files)

    def _load(self, book_no: int) -> Optional[BookData]:
        if book_no in self._books:
            return self._books[book_no]
        with self._lock:
            if book_no in self._books:
                return self._books[book_no]
            path = self._files.get(book_no)
            if path is None:
                return None
            raw = json.loads(path.read_text(encoding="utf-8"))
            bd = BookData(
                book_no=int(raw.get("book") or book_no),
                name_gb=str(raw.get("name_gb") or ""),
                abbr_gb=str(raw.get("abbr_gb") or ""),
            )
            for ch in raw.get("chapters") or []:
                if not isinstance(ch, dict) or ch.get("chapter") is None:
                    continue
                cnum = int(ch["chapter"])
                vmap: dict[int, dict[str, Any]] = {}
                for v in ch.get("verses") or []:
                    if not isinstance(v, dict) or v.get("verse") is None:
                        continue
                    slim = {k: v.get(k) for k in _KEEP_VERSE_KEYS}
                    slim["verse"] = int(v["verse"])
                    vmap[slim["verse"]] = slim
                bd.chapters[cnum] = vmap
                if ch.get("title_gb"):
                    bd.chapter_titles[cnum] = str(ch.get("title_gb"))
            self._books[book_no] = bd
            return bd

    # ---------------- 存在性 ----------------
    def chapter_exists(self, book_no: int, chapter: int) -> bool:
        bd = self._load(int(book_no))
        return bool(bd and int(chapter) in bd.chapters)

    def verse_exists(self, book_no: int, chapter: int, verse: int) -> bool:
        bd = self._load(int(book_no))
        if not bd:
            return False
        return int(verse) in bd.chapters.get(int(chapter), {})

    def verse_count(self, book_no: int, chapter: int) -> int:
        bd = self._load(int(book_no))
        if not bd:
            return 0
        return len(bd.chapters.get(int(chapter), {}))

    def chapter_count(self, book_no: int) -> int:
        bd = self._load(int(book_no))
        return len(bd.chapters) if bd else 0

    def book_name(self, book_no: int) -> str:
        bd = self._load(int(book_no))
        return bd.name_gb if bd else ""

    # ---------------- 取经文 ----------------
    def _decorate(self, bd: BookData, chapter: int, v: dict[str, Any]) -> dict[str, Any]:
        # book / name_gb：与 3.0 front BibleMessage 字段对齐
        return {
            **v,
            "book": bd.book_no,
            "book_no": bd.book_no,
            "chapter": chapter,
            "book_name": bd.name_gb,
            "name_gb": bd.name_gb,
            "abbr": bd.abbr_gb,
            "abbr_gb": bd.abbr_gb,
        }

    def get_verse(self, book_no: int, chapter: int, verse: int) -> Optional[dict[str, Any]]:
        bd = self._load(int(book_no))
        if not bd:
            return None
        v = bd.chapters.get(int(chapter), {}).get(int(verse))
        return self._decorate(bd, int(chapter), v) if v else None

    def get_range(
        self, book_no: int, chapter: int, v_start: int, v_end: int
    ) -> list[dict[str, Any]]:
        bd = self._load(int(book_no))
        if not bd:
            return []
        vs, ve = sorted((int(v_start), int(v_end)))
        vmap = bd.chapters.get(int(chapter), {})
        return [self._decorate(bd, int(chapter), vmap[n]) for n in sorted(vmap) if vs <= n <= ve]

    def get_chapter(self, book_no: int, chapter: int) -> list[dict[str, Any]]:
        bd = self._load(int(book_no))
        if not bd:
            return []
        vmap = bd.chapters.get(int(chapter), {})
        return [self._decorate(bd, int(chapter), vmap[n]) for n in sorted(vmap)]

    def get_cross(
        self, book_no: int, c1: int, v1: int, c2: int, v2: int
    ) -> list[dict[str, Any]]:
        """跨章范围：c1:v1 起至 c2:v2 止，按章节顺序。"""
        bd = self._load(int(book_no))
        if not bd:
            return []
        out: list[dict[str, Any]] = []
        for c in sorted(bd.chapters):
            if c < int(c1) or c > int(c2):
                continue
            vmap = bd.chapters[c]
            for n in sorted(vmap):
                if c == int(c1) and n < int(v1):
                    continue
                if c == int(c2) and n > int(v2):
                    continue
                out.append(self._decorate(bd, c, vmap[n]))
        return out

    def footnotes(self, book_no: int, chapter: int, verse: int) -> list[dict[str, Any]]:
        v = self.get_verse(book_no, chapter, verse)
        fn = (v or {}).get("footnotes")
        return list(fn) if isinstance(fn, list) else []

    # ---------------- 统计 ----------------
    def iter_books(self) -> Iterator[BookData]:
        for no in sorted(self._files):
            bd = self._load(no)
            if bd:
                yield bd

    def totals(self) -> dict[str, int]:
        books = chapters = verses = 0
        for bd in self.iter_books():
            books += 1
            chapters += len(bd.chapters)
            verses += sum(len(v) for v in bd.chapters.values())
        return {"books": books, "chapters": chapters, "verses": verses}


def file_stats(path: Path) -> dict[str, int]:
    """单文件章数、节数（不进缓存，供 manifest 生成/核对）。"""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    chs = [c for c in (raw.get("chapters") or []) if isinstance(c, dict)]
    return {
        "chapters": len(chs),
        "verses": sum(len([v for v in (c.get("verses") or []) if isinstance(v, dict)]) for c in chs),
    }


_DEFAULT: Optional[BibleText] = None
_DEFAULT_LOCK = threading.Lock()


def get_bible(bible_dir: Optional[Path] = None) -> BibleText:
    """进程级单例；bible_dir 缺省取 settings.bible_dir。"""
    global _DEFAULT
    if bible_dir is not None:
        return BibleText(bible_dir)
    if _DEFAULT is None:
        with _DEFAULT_LOCK:
            if _DEFAULT is None:
                from config import get_settings

                _DEFAULT = BibleText(get_settings(require_runtime=False).bible_dir)
    return _DEFAULT
