# -*- coding: utf-8 -*-
"""normalize v2 补强（A–J）代表性用例；另含 scripture_format_cases_v2.csv 全量比对。"""

from __future__ import annotations

import csv
import unittest
from pathlib import Path

from scripture.normalize import (
    KIND_BOOK,
    KIND_CHAPTER,
    KIND_CHAPTER_RANGE,
    KIND_CROSS,
    KIND_VERSE,
    parse_refs,
    preprocess_ref_text,
)
from tests._helpers import BIBLE_DIR, bible

HAS_BIBLE = BIBLE_DIR.is_dir()
QA4 = Path(__file__).resolve().parents[2]
V2_CSV = QA4 / "notes" / "scripture_format_cases_v2.csv"


def _labels(text: str) -> list[str]:
    return [r.label() for r in parse_refs(text, bible=bible(), validate=True)]


def _kinds(text: str) -> list[str]:
    return [r.kind for r in parse_refs(text, bible=bible(), validate=True)]


@unittest.skipUnless(HAS_BIBLE, "qa4/data/bible_data 未就绪")
class TestNormalizeV2Rules(unittest.TestCase):
    # A 繁体
    def test_a_traditional_john(self):
        self.assertEqual(_labels("約三16"), ["约3:16"])

    def test_a_traditional_genesis(self):
        self.assertEqual(_labels("創世記一章一節"), ["创1:1"])

    # B 空白与书名号
    def test_b_book_marks(self):
        self.assertEqual(_labels("《创世记》1:1"), ["创1:1"])

    def test_b_spaces_and_nbsp(self):
        self.assertEqual(_labels("约三\u300016"), ["约3:16"])
        self.assertEqual(_labels("约三 16"), ["约3:16"])

    def test_b_two_refs_not_merged(self):
        self.assertEqual(_labels("约三16 罗八28"), ["约3:16", "罗8:28"])

    # C 别名
    def test_c_isaiah_alias(self):
        self.assertEqual(_labels("以赛亚五三5"), ["赛53:5"])

    def test_c_galatians_alias(self):
        self.assertEqual(_labels("加拉太二11"), ["加2:11"])

    def test_c_person_without_chapter(self):
        self.assertEqual(_labels("以赛亚说"), [])

    def test_c_john1_book_not_gospel(self):
        self.assertEqual(_labels("约一书一1"), ["约壹1:1"])

    # D 阿拉伯+章篇节
    def test_d_chapter_unit(self):
        self.assertEqual(_labels("创1章"), ["创1"])
        self.assertEqual(_kinds("创1章"), [KIND_CHAPTER])

    def test_d_chapter_verse_unit(self):
        self.assertEqual(_labels("约翰福音3章16节"), ["约3:16"])

    def test_d_range_unit(self):
        self.assertEqual(_labels("罗马书8章28-30节"), ["罗8:28-30"])

    # E 范围与跨章
    def test_e_same_chapter_zhi(self):
        self.assertEqual(_labels("腓二5至11"), ["腓2:5-11"])

    def test_e_cross_short(self):
        refs = parse_refs("太三1-四2", bible=bible())
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].kind, KIND_CROSS)
        self.assertEqual(refs[0].label(), "太3:1-4:2")

    def test_e_cross_colon(self):
        refs = parse_refs("创1:1-2:3", bible=bible())
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].kind, KIND_CROSS)
        self.assertEqual(refs[0].label(), "创1:1-2:3")

    def test_e_zhi_cross(self):
        refs = parse_refs("太三1至四2", bible=bible())
        self.assertEqual(refs[0].kind, KIND_CROSS)
        self.assertEqual(refs[0].label(), "太3:1-4:2")

    def test_e_cross_partial_endpoint_fallback(self):
        # 利5:26 不存在 → 只保留合法端 利1:1
        self.assertEqual(_labels("利一1~五26"), ["利1:1"])

    def test_e_cross_both_endpoints_valid(self):
        refs = parse_refs("利一1~五19", bible=bible())
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].kind, KIND_CROSS)
        self.assertEqual(refs[0].label(), "利1:1-5:19")

    # F 整章+单节合并
    def test_f_merge_di_jie(self):
        refs = parse_refs("创世记第一章第一节", bible=bible())
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].label(), "创1:1")

    def test_f_merge_keep_two_verses(self):
        self.assertEqual(_labels("创世记一章26节和二章7节"), ["创1:26", "创2:7"])

    # G 廿卅与口语百
    def test_g_nian(self):
        self.assertEqual(_labels("约廿一15"), ["约21:15"])

    def test_g_sa_out_of_range(self):
        self.assertEqual(_labels("太卅五1"), [])

    def test_g_colloquial_hundred_preprocess(self):
        # 口语改写在 preprocess；120:14 在 bible_data 不存在 → 解析为空（见 notes）
        self.assertIn("一百二十", preprocess_ref_text("诗一百二14"))

    # H 整卷与整章范围
    def test_h_whole_book(self):
        refs = parse_refs("创世记", bible=bible())
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].kind, KIND_BOOK)

    def test_h_person_bare_not_book(self):
        self.assertEqual(_labels("约翰"), [])
        self.assertEqual(_labels("雅各"), [])

    def test_h_chapter_range(self):
        refs = parse_refs("创一至三章", bible=bible())
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0].kind, KIND_CHAPTER_RANGE)
        self.assertEqual(refs[0].label(), "创1-3")

    def test_h_parallel_chapters(self):
        self.assertEqual(_labels("创一章和二章"), ["创1", "创2"])

    # I 英文
    def test_i_john_verse(self):
        self.assertEqual(_labels("John 3:16"), ["约3:16"])

    def test_i_cor_spaced_and_roman(self):
        self.assertEqual(_labels("1 Cor 13:4"), ["林前13:4"])
        self.assertEqual(_labels("I Cor. 13:4"), ["林前13:4"])

    def test_i_song_of_songs(self):
        self.assertEqual(_labels("Song of Songs 2:4"), ["歌2:4"])

    def test_i_en_dash(self):
        self.assertEqual(_labels("Matt. 5:3–12"), ["太5:3-12"])

    def test_i_whole_genesis_not_john(self):
        self.assertEqual(parse_refs("Genesis", bible=bible())[0].kind, KIND_BOOK)
        self.assertEqual(_labels("John"), [])

    def test_i_am_not_amos(self):
        self.assertEqual(_labels("I am 3 years old"), [])

    # J 越界章
    def test_j_out_of_range_chapter(self):
        self.assertEqual(_labels("太卅五1"), [])
        self.assertEqual(_labels("太三十五1"), [])

    # 其它回归
    def test_dot_as_colon(self):
        self.assertEqual(_labels("约3.16"), ["约3:16"])

    def test_philemon_verse(self):
        self.assertEqual(_labels("Philemon 6"), ["门1:6"])

    def test_topic_sentence_not_ref(self):
        self.assertEqual(_labels("约翰福音是谁写的"), [])

    def test_a_traditional_romans(self):
        self.assertEqual(_labels("羅馬書八章二十八節"), ["罗8:28"])

    def test_b_corner_quotes(self):
        self.assertEqual(_labels("『约三16』"), ["约3:16"])

    def test_c_tie_typo(self):
        self.assertEqual(_labels("贴后三1"), ["帖后3:1"])

    def test_d_psalm_pian(self):
        self.assertEqual(_kinds("诗篇23篇"), [KIND_CHAPTER])
        self.assertEqual(_labels("诗篇23篇"), ["诗23"])

    def test_e_same_chapter_cn_zhi(self):
        self.assertEqual(_labels("约翰福音三章十六节至十八节"), ["约3:16-18"])

    def test_f_merge_arabic_jie(self):
        self.assertEqual(_labels("罗马书八章28节"), ["罗8:28"])

    def test_h_english_whole_romans(self):
        self.assertEqual(parse_refs("Romans", bible=bible())[0].kind, KIND_BOOK)

    def test_i_psalms_plural(self):
        self.assertEqual(_labels("Psalms 23:1"), ["诗23:1"])

    def test_i_nested_in_sentence(self):
        self.assertEqual(_labels("Please explain John 3:16 to me"), ["约3:16"])


@unittest.skipUnless(HAS_BIBLE, "qa4/data/bible_data 未就绪")
class TestNormalizeV2Csv(unittest.TestCase):
    def test_format_cases_v2_all_match(self):
        if not V2_CSV.is_file():
            self.skipTest("scripture_format_cases_v2.csv 缺失")
        from tools.probe_scripture_formats import build_std_to_full, format_ref_expected_style

        std_to_full = build_std_to_full()
        bad = []
        with V2_CSV.open(encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        for row in rows:
            refs = parse_refs(row["input"], bible=bible(), validate=True)
            if not refs:
                actual = "无出处"
            else:
                actual = " ; ".join(format_ref_expected_style(r, std_to_full) for r in refs)
            if actual != row["expected"]:
                # 已知：诗120:14 在 bible_data 不存在
                if row["id"] in ("S117", "S278"):
                    continue
                bad.append((row["id"], row["input"], row["expected"], actual))
        self.assertEqual(bad, [], msg=f"mismatches={bad[:10]}")


if __name__ == "__main__":
    unittest.main()
