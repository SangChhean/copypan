# -*- coding: utf-8 -*-
"""经文数字穷举：诗篇章 1..150、诗 119 节 1..176。

阿拉伯章+节只用 scripture_format_cases_v2.csv 里出现过的分隔符（: / ： / .），
不用无分隔连写。失败写日志目录并令测试失败；不改 vendor。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from _helpers import BIBLE_DIR, bible, quiet
from hymn.numbers import int_to_cn_digit_reading, int_to_cn_standard
from scripture.normalize import KIND_CHAPTER, parse_refs

quiet("qa4.scripture")

OUT_DIR = Path(r"G:\PanAI4.0专用\logs\formats")

# 来自 scripture_format_cases_v2.csv 中「阿拉伯章+节」实际出现的分隔符（: 53、： 2、. 1）
ARABIC_CHAPTER_VERSE_SEPS = (":", "：", ".")


def _chapter_forms(n: int) -> list[tuple[str, str]]:
    """(form_kind, 完整输入「诗…1」)。"""
    items: list[tuple[str, str]] = [
        ("cn_standard", f"诗{int_to_cn_standard(n)}1"),
        ("cn_digit_zero", f"诗{int_to_cn_digit_reading(n, zero_char='〇')}1"),
    ]
    for sep in ARABIC_CHAPTER_VERSE_SEPS:
        items.append((f"arabic_sep:{sep}", f"诗{n}{sep}1"))
    out, seen = [], set()
    for kind, text in items:
        if text not in seen:
            seen.add(text)
            out.append((kind, text))
    return out


def _expect_verse(refs, book: str, chapter: int, verse: int) -> bool:
    return (
        len(refs) == 1
        and refs[0].book == book
        and refs[0].chapter == chapter
        and refs[0].v_start == verse
        and refs[0].v_end == verse
    )


def _write_fails(name: str, bad: list[dict]) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / name
    path.write_text(json.dumps({"n_fail": len(bad), "fails": bad}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


@unittest.skipUnless(BIBLE_DIR.is_dir(), "bible_data 未就绪")
class TestScriptureNumberExhaustive(unittest.TestCase):
    def test_psalm_chapters_1_to_150(self):
        """中文标准、〇逐位、阿拉伯带分隔符；任一类失败即失败。"""
        b = bible()
        bad: list[dict] = []
        by_kind: dict[str, int] = {}
        for ch in range(1, 151):
            for kind, text in _chapter_forms(ch):
                refs = parse_refs(text, bible=b, validate=True)
                if not _expect_verse(refs, "诗", ch, 1):
                    by_kind[kind] = by_kind.get(kind, 0) + 1
                    bad.append(
                        {
                            "input": text,
                            "want_chapter": ch,
                            "form_kind": kind,
                            "labels": [r.label() for r in refs],
                            "keys": [list(r.key()) for r in refs],
                            "kinds": [r.kind for r in refs],
                        }
                    )
        path = _write_fails("scripture_psalm_chapter_fails.json", bad)
        print(f"\nSCRIPTURE_CHAPTER_FAILS n={len(bad)} by_kind={by_kind} out={path}")
        self.assertEqual(
            bad,
            [],
            msg=f"诗篇章穷举失败 {len(bad)} 条 by_kind={by_kind}；明细 {path}",
        )

    def test_psalm_119_verses_1_to_176(self):
        """诗一一九{n}，节号阿拉伯；任一条失败即失败。"""
        b = bible()
        bad: list[dict] = []
        for v in range(1, 177):
            text = f"诗一一九{v}"
            refs = parse_refs(text, bible=b, validate=True)
            if not _expect_verse(refs, "诗", 119, v):
                bad.append(
                    {
                        "input": text,
                        "want_verse": v,
                        "labels": [r.label() for r in refs],
                        "keys": [list(r.key()) for r in refs],
                        "kinds": [r.kind for r in refs],
                    }
                )
        path = _write_fails("scripture_ps119_fails.json", bad)
        print(f"\nSCRIPTURE_PS119_FAILS n={len(bad)} out={path}")
        self.assertEqual(bad, [], msg=f"诗119节穷举失败 {len(bad)} 条；明细 {path}")

    def test_arabic_concat_ambiguity_status_quo(self):
        """无分隔连写：诗11=整章；诗151=空（现状记录，不是缺陷）。"""
        b = bible()
        refs11 = parse_refs("诗11", bible=b, validate=True)
        self.assertEqual(len(refs11), 1)
        self.assertEqual(refs11[0].kind, KIND_CHAPTER)
        self.assertEqual(refs11[0].book, "诗")
        self.assertEqual(refs11[0].chapter, 11)
        self.assertEqual(refs11[0].label(), "诗11")

        refs151 = parse_refs("诗151", bible=b, validate=True)
        self.assertEqual(refs151, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
