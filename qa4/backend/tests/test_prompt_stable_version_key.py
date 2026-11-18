# -*- coding: utf-8 -*-
"""固定 stable 通道 version_key（缓存键），防止草稿登记误改 CURRENT。"""

from __future__ import annotations

import os
import unittest

from prompts.loader import PromptRegistry


# 改前稳定通道形如 channel=stable;step2=v1.0;...（含全部 CURRENT=v1.0）
EXPECTED_STABLE_VERSION_KEY = (
    "channel=stable;"
    "step2=v1.0;step3=v1.0;step4=v1.0;step5=v1.0;step7=v1.0;step8=v1.0"
)


class TestStableVersionKey(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("QA4_PROMPT_CHANNEL", None)

    def test_stable_version_key_unchanged(self):
        os.environ.pop("QA4_PROMPT_CHANNEL", None)
        reg = PromptRegistry(channel="stable")
        self.assertEqual(reg.version_key(), EXPECTED_STABLE_VERSION_KEY)
        # 与仅 versions 体（无 channel 前缀）的旧观感对照：逐步仍为 v1.0
        self.assertEqual(
            reg.versions(),
            {s: "v1.0" for s in ("step2", "step3", "step4", "step5", "step7", "step8")},
        )


if __name__ == "__main__":
    unittest.main()
