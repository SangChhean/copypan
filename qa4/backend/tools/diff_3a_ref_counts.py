# -*- coding: utf-8 -*-
"""只读：逐词对比 qa4 parse_refs 与 probe6 口径（桌面 v2.1 + 与 probe6 同形的 bible 校验）的出处数。

输出 CSV：G:\\PanAI4.0专用\\logs\\stage2\\ref_counts_per_term.csv（词名,出处数）—— qa4 现状。
不 import back_*：用 qa4 BibleText 建校验索引（与 probe6 的「节是否存在」同口径）。
"""

from __future__ import annotations

import csv
import importlib.util
import json
import sys
from collections import Counter
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
QA4 = _BACKEND.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

OUT_CSV = Path(r"G:\PanAI4.0专用\logs\stage2\ref_counts_per_term.csv")
TD = QA4 / "data" / "graph_annotations" / "truth_dictionary_3a3b.json"
V21 = Path(r"C:\Users\28121\Desktop\get_vers_v2.1.py")


def load_v21():
    spec = importlib.util.spec_from_file_location("get_vers_v21_diff", V21)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def parse_line_probe6(mod, line, validate):
    vp = mod.VerseParser(validate=validate)
    vp.start_paragraph()
    toks: list[str] = []
    for g in vp.parse_text(line):
        for part in (g.get("verses") or "").split("，"):
            part = part.strip()
            if part:
                toks.append(part)
    return toks


def main() -> int:
    from scripture.bible_text import BibleText, STD2IDX
    from scripture.normalize import parse_refs, reading_line_of

    bible = BibleText(QA4 / "data" / "bible_data")
    mod = load_v21()

    # probe6 校验：不放行诗篇第 0 节（与 qa4 默认开关打开时不同）
    def validate(std, chap, verse=None):
        bno = STD2IDX.get(std)
        if bno is None:
            return False
        try:
            chap = int(chap)
        except Exception:
            return False
        if not bible.chapter_exists(bno, chap):
            return False
        if verse is None:
            return True
        try:
            verse = int(verse)
        except Exception:
            return False
        return bible.verse_exists(bno, chap, verse)

    rows = json.loads(TD.read_text(encoding="utf-8"))
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    qa4_rows: list[tuple[str, int]] = []
    diffs: list[dict] = []
    total_qa4 = total_p6 = 0

    for row in rows:
        title = str(row.get("title") or "")
        line = reading_line_of(row.get("content_3a") or "")
        if line is None:
            continue
        qa4_refs = parse_refs(line, bible=bible)  # 默认诗篇 0→1
        p6_toks = parse_line_probe6(mod, line, validate)
        n_q, n_p = len(qa4_refs), len(p6_toks)
        total_qa4 += n_q
        total_p6 += n_p
        qa4_rows.append((title, n_q))
        if n_q != n_p:
            q_labels = [r.label() for r in qa4_refs]
            cq, cp = Counter(q_labels), Counter(p6_toks)
            diffs.append(
                {
                    "title": title,
                    "qa4_n": n_q,
                    "probe6_n": n_p,
                    "extra_refs": list((cq - cp).elements()),
                    "missing_refs": list((cp - cq).elements()),
                    "qa4_flags": [list(r.flags) for r in qa4_refs if r.flags],
                }
            )

    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["词名", "出处数"])
        for title, n in qa4_rows:
            w.writerow([title, n])

    print("qa4_total", total_qa4, "probe6_like_total", total_p6, "delta", total_qa4 - total_p6)
    print("n_terms_with_reading", len(qa4_rows))
    print("diff_terms", len(diffs))
    print("csv", OUT_CSV)
    for d in diffs:
        print(json.dumps(d, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
