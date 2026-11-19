# -*- coding: utf-8 -*-
"""书目英译三路径：source_en / 规则 / 保留中文。"""

from __future__ import annotations

import unittest
from unittest import mock

from core import translate as tr


class TestTranslateSourcesEn(unittest.TestCase):
    def test_uses_source_en_strip_parens_and_trailing(self):
        line, path = tr.resolve_source_en_line(
            {
                "n": 1,
                "zh": "[1] 列王记生命读经 第六篇",
                "en": "(Life-study of Kings, msg. 6, par. 3)",
            }
        )
        self.assertEqual(path, "source_en")
        self.assertEqual(line, "[1] Life-study of Kings, msg. 6")

    def test_rule_recovery_version_footnote(self):
        line, path = tr.resolve_source_en_line(
            {
                "n": 2,
                "zh": "[2] 恢复本圣经 约三16 注2",
                "en": "",
                "source_zh": "恢复本圣经，约三16，注2",
            }
        )
        self.assertEqual(path, "rule")
        self.assertEqual(
            line,
            "[2] Holy Bible Recovery Version, John 3:16, footnote 2",
        )

    def test_rule_feast_from_book_title_and_message_number(self):
        line, path = tr.resolve_source_en_line(
            {
                "n": 1,
                "zh": "[1] 2015年冬季训练 某某篇题",
                "en": "",
                "book_title": "2015年冬季训练",
                "message_number": 3,
            }
        )
        self.assertEqual(path, "rule")
        self.assertEqual(line, "[1] 2015 WT, msg. 3")

    def test_keep_chinese_when_no_en_no_rule(self):
        line, path = tr.resolve_source_en_line(
            {
                "n": 3,
                "zh": "[3] 生命课程 第一课",
                "en": "",
                "book_title": "生命课程",
            }
        )
        self.assertEqual(path, "zh")
        self.assertEqual(line, "[3] 生命课程 第一课")

    def test_translate_answer_en_sources_paths(self):
        sources = [
            {"n": 1, "zh": "[1] 甲", "en": "(Life-study of Romans, msg. 1, par. 2)"},
            {"n": 2, "zh": "[2] 注", "en": "", "source_zh": "恢复本圣经，罗一16，注1"},
            {"n": 3, "zh": "[3] 生命课程 一", "en": ""},
        ]
        with mock.patch.object(tr, "gemini_translate_en", return_value="Body[1]"):
            out = tr.translate_answer(text="正文[1]", sources=sources, target_lang="en")
        self.assertEqual(out["answer"], "Body[1]")
        self.assertNotIn("[References]", out["answer"])
        self.assertEqual(
            out["sources"],
            [
                "[1] Life-study of Romans, msg. 1",
                "[2] Holy Bible Recovery Version, Rom. 1:16, footnote 1",
                "[3] 生命课程 一",
            ],
        )

    def test_old_string_sources_still_ok(self):
        """旧缓存/旧前端只传中文字符串：无规则或保留中文，不报错。"""
        lines = tr.translate_sources_to_en(
            [
                "[1] 2014年国殇节特会，第一篇",
                "[2] 倪柝声文集第一辑第一册，灵修指微",
            ]
        )
        self.assertEqual(lines[0], "[1] 2014 MDC, msg. 1")
        self.assertEqual(lines[1], "[2] 倪柝声文集第一辑第一册，灵修指微")

    def test_map_note_source_zh_rule_en(self):
        """map_note：前端送来的 zh/source_zh 为恢复本注释 → 规则英译。"""
        line, path = tr.resolve_source_en_line(
            {
                "n": 1,
                "zh": "[1] 恢复本圣经，来八6，注2",
                "en": "",
                "source_zh": "（恢复本圣经，来八6，注2）",
                "book_title": "圣经真理题库，第一系列　圣经—神的话",
            }
        )
        self.assertEqual(path, "rule")
        self.assertEqual(line, "[1] Holy Bible Recovery Version, Heb. 8:6, footnote 2")

    def test_map_note_empty_source_zh_keeps_quiz_title(self):
        line, path = tr.resolve_source_en_line(
            {
                "n": 2,
                "zh": "[2] 圣经真理题库，空出处系列 某一篇",
                "en": "",
                "source_zh": "",
                "book_title": "圣经真理题库，空出处系列",
            }
        )
        self.assertEqual(path, "zh")
        self.assertEqual(line, "[2] 圣经真理题库，空出处系列 某一篇")


if __name__ == "__main__":
    unittest.main()
