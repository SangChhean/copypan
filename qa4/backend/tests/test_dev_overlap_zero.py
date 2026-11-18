# -*- coding: utf-8 -*-
"""开发题集与草稿提示词例子重合必须为 0。"""

from __future__ import annotations

import unittest
from pathlib import Path

from tools.check_dev_overlap import find_overlaps, load_dev_questions, load_prompt_corpus


class TestDevOverlapZero(unittest.TestCase):
    def test_no_overlap(self):
        corpus = load_prompt_corpus()
        qs = load_dev_questions()
        self.assertGreaterEqual(len(qs), 50)
        hits = find_overlaps(qs, corpus)
        self.assertEqual(
            hits,
            [],
            msg="重合题：" + "; ".join(f"{h['id']}:{h['question']}" for h in hits),
        )


if __name__ == "__main__":
    unittest.main()
