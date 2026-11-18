# -*- coding: utf-8 -*-
"""文集年代表（lookups/wenji_year_table.json，42 行年标记 → text_cwwl 书名清单）。

区间与年标记只要有重叠就算命中；no_year_titles 的书名永不参与年代筛选。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

_YEAR_MARK_RE = re.compile(r"^\s*(\d{4})\s*(?:[–\-—～~至]\s*(\d{2,4}))?\s*$")


def parse_year_mark(mark: str) -> Optional[tuple[int, int]]:
    """「1931」→(1931,1931)；「1932–49」→(1932,1949)；「1994–97」→(1994,1997)。"""
    m = _YEAR_MARK_RE.match(str(mark or ""))
    if not m:
        return None
    y0 = int(m.group(1))
    if not m.group(2):
        return (y0, y0)
    tail = m.group(2)
    y1 = int(tail) if len(tail) == 4 else int(str(y0)[: 4 - len(tail)] + tail)
    return (y0, max(y0, y1))


@dataclass
class YearSelection:
    book_titles: list[str]
    marks: list[str]
    covered_range: Optional[tuple[int, int]]


class YearTable:
    def __init__(self, rows: list[dict[str, Any]], no_year_titles: Optional[set[str]] = None) -> None:
        self.rows = rows
        self.no_year = set(no_year_titles or set())

    @classmethod
    def from_lookup_dir(cls, lookup_dir: Path) -> "YearTable":
        rows = json.loads((Path(lookup_dir) / "wenji_year_table.json").read_text(encoding="utf-8"))
        ny_path = Path(lookup_dir) / "no_year_titles.json"
        no_year: set[str] = set()
        if ny_path.is_file():
            ny = json.loads(ny_path.read_text(encoding="utf-8"))
            no_year = {t.get("book_title") for t in (ny.get("titles") or []) if t.get("book_title")}
        return cls(rows, no_year)

    def select(self, start: int, end: int) -> YearSelection:
        if start > end:
            start, end = end, start
        titles: list[str] = []
        marks: list[str] = []
        lo: Optional[int] = None
        hi: Optional[int] = None
        for row in self.rows:
            rng = parse_year_mark(row.get("year_mark"))
            if rng is None:
                continue
            if rng[1] < start or rng[0] > end:
                continue
            marks.append(str(row.get("year_mark")))
            lo = rng[0] if lo is None else min(lo, rng[0])
            hi = rng[1] if hi is None else max(hi, rng[1])
            for t in row.get("text_cwwl_book_titles") or []:
                if t not in self.no_year and t not in titles:
                    titles.append(t)
        return YearSelection(titles, marks, (lo, hi) if lo is not None else None)
