# -*- coding: utf-8 -*-
"""第 2 步测试用 Prompt。正式四份 Prompt 在第 3 步替换。"""

VERSIONS = {
    "v0.1": {
        "system": "",
        "user_template": "请用一句话复述以下主题：{topic}",
    }
}
CURRENT = "v0.1"
NAME = "prompt_test"
