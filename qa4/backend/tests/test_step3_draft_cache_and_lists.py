# -*- coding: utf-8 -*-
"""step3 草稿：紧凑节期清单 + system cacheable 拆分（新增测试）。"""

from __future__ import annotations

import os
import unittest
from types import SimpleNamespace

from prompts.loader import PromptRegistry
from pipeline.context import RequestContext
from pipeline.step03_plan import (
    format_feast_list_compact,
    split_step3_system_user,
    _run_llm,
)


def _fake_feasts_259() -> list[dict]:
    """259 场：多年份 × 若干月份码，名称带年份前缀。"""
    month_names = {
        "01": "国际华语特会",
        "02": "春季长老训练",
        "04": "夏季训练",
        "07": "秋季长老训练",
        "10": "国殇节特会",
        "12": "冬季训练",
    }
    out: list[dict] = []
    year = 1984
    while len(out) < 259:
        for mc, base in month_names.items():
            if len(out) >= 259:
                break
            # 同码偶发别名，测去重
            name = f"{year}年{base}" if len(out) % 17 else f"{year}年{base}（别称）"
            out.append({"year": year, "month_code": mc, "name": name})
        year += 1
    return out


class TestFeastListCompact(unittest.TestCase):
    def test_compact_under_1500_tokens_with_259(self):
        feasts = _fake_feasts_259()
        self.assertEqual(len(feasts), 259)
        text = format_feast_list_compact(feasts)
        # 不应逐年逐行
        self.assertNotIn("1984-01-", text)
        self.assertIn("月份码对照", text)
        self.assertIn("年份范围：", text)
        # 注入到模板后，节期清单块本身 ≤ ~1500 token
        feast_tokens = len(text) * 1.2
        self.assertLessEqual(feast_tokens, 1500, msg=f"feast_list tokens={feast_tokens}")
        # 整段渲染（含生命读经假清单）也控制节期部分
        reg = PromptRegistry(channel="draft")
        tpl = reg.get("step3")
        life = "、".join(f"假书{i}生命读经" for i in range(80))
        rendered = tpl.render(
            question="q",
            rule_hits="[]",
            life_book_titles=life,
            feast_list=text,
            scope_options="outline_feasts",
        )
        # 截取节期特会段
        marker = "节期特会（紧凑）："
        i = rendered.index(marker)
        j = rendered.index("scope 可选值", i)
        block = rendered[i:j]
        self.assertLessEqual(len(block) * 1.2, 1500)


class TestStep3SystemCacheSplit(unittest.IsolatedAsyncioTestCase):
    def tearDown(self):
        os.environ.pop("QA4_PROMPT_CHANNEL", None)

    def test_split_helper_draft_vs_stable(self):
        raw = "固定规则\n清单\n\n# 本问线索\nrule\n\n# 用户问题\nq"
        sys_d, user_d = split_step3_system_user(raw, draft=True)
        self.assertIsInstance(sys_d, list)
        self.assertTrue(sys_d[0].get("cacheable"))
        self.assertIn("固定规则", sys_d[0]["text"])
        self.assertTrue(user_d.startswith("# 本问线索"))
        self.assertNotIn("固定规则", user_d)
        sys_s, user_s = split_step3_system_user(raw, draft=False)
        self.assertEqual(sys_s, "")
        self.assertEqual(user_s, raw)

    async def test_run_llm_draft_puts_fixed_in_system_cacheable(self):
        os.environ["QA4_PROMPT_CHANNEL"] = "draft"
        reg = PromptRegistry(channel="draft")
        tpl = reg.get("step3")
        self.assertTrue(tpl.draft)

        captured: dict = {}

        class FakeLLM:
            async def complete_json(self, role, system, messages, *, step, max_tokens=None, cache=None):
                captured["system"] = system
                captured["user"] = messages[0]["content"]
                data = {
                    "main_type": "默认",
                    "restrictions": [],
                    "complex": False,
                    "subquestions": [{"text": "试验问题", "qtype": "默认"}],
                    "sensitive": False,
                    "understanding": "ok",
                    "locator": None,
                    "source": "model",
                    "hymn_refs": [],
                }
                return data, SimpleNamespace(text="{}", usage={})

        deps = SimpleNamespace(
            prompts=reg,
            llm=FakeLLM(),
            cfg={"json_max_tokens": 500},
            life_books=[{"book_title": "罗马书生命读经"}],
            feasts=_fake_feasts_259()[:12],
            bible=None,
        )
        ctx = RequestContext(request_id="t", question_orig="试验问题")
        ctx.rule_hits = [{"kind": "scripture", "labels": ["约3:16"], "n": 1}]

        plan = await _run_llm(ctx, deps)
        self.assertEqual(plan.main_type, "默认")
        system = captured["system"]
        user = captured["user"]
        self.assertIsInstance(system, list)
        self.assertTrue(system[0].get("cacheable"))
        self.assertIn("输出字段", system[0]["text"])
        self.assertIn("生命读经书名", system[0]["text"])
        self.assertNotIn("试验问题", system[0]["text"])
        self.assertIn("# 本问线索", user)
        self.assertIn("试验问题", user)
        self.assertIn("rule_hits", user.lower() or "rule_hits")
        # 可变：rule_hits JSON 与问题在 user；固定规则不在 user 前半重复整段清单标题亦可
        self.assertNotIn("你是问答系统的「理解与计划」步骤", user)


if __name__ == "__main__":
    unittest.main()
