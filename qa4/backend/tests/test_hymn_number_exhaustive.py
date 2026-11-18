# -*- coding: utf-8 -*-
"""诗歌首数中文数字穷举：1..1005 多种写法只测号码读对（不测存在性、不依赖 ES）。"""

from __future__ import annotations

import unittest

from hymn.catalog import HymnCatalog
from hymn.numbers import (
    int_to_cn_digit_reading,
    int_to_cn_nian,
    int_to_cn_omit_yi_shi,
    int_to_cn_standard,
    parse_hymn_number,
    to_fullwidth_digits,
)
from hymn.parse import parse_hymn_refs


class _DummyCatalog(HymnCatalog):
    """存在性全真，只测号码。"""

    def ensure_loaded(self, **kwargs):  # noqa: ANN003
        self._nums = {
            "big": set(range(0, 2001)),
            "sup": set(range(0, 2001)),
            "fu": set(range(0, 20)),
        }
        self._source = "dummy"

    def exists(self, series: str, number: int) -> bool:
        return True


def _forms_for(n: int) -> list[str]:
    forms = [str(n), to_fullwidth_digits(str(n)), int_to_cn_standard(n), int_to_cn_digit_reading(n)]
    omit = int_to_cn_omit_yi_shi(n)
    if omit:
        forms.append(omit)
    nian = int_to_cn_nian(n)
    if nian:
        forms.append(nian)
    # 去重保序
    out, seen = [], set()
    for f in forms:
        if f not in seen:
            seen.add(f)
            out.append(f)
    return out


class TestHymnNumberExhaustive(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cat = _DummyCatalog()
        cls.cat.ensure_loaded()

    def test_parse_hymn_number_roundtrip_1_to_1005(self):
        bad = []
        for n in range(1, 1006):
            for form in _forms_for(n):
                got = parse_hymn_number(form)
                if got != n:
                    bad.append((n, form, got))
        self.assertEqual(bad, [], msg=f"parse_hymn_number 失败 {len(bad)} 例，前 20：{bad[:20]}")

    def test_parse_hymn_refs_poetry_and_sup_forms(self):
        bad = []
        for n in range(1, 1006):
            for form in _forms_for(n):
                for prefix in ("诗歌第", "补充本第"):
                    text = f"{prefix}{form}首"
                    refs = parse_hymn_refs(text, catalog=self.cat)
                    if len(refs) != 1 or refs[0].number != n:
                        bad.append((text, n, [r.number for r in refs]))
        self.assertEqual(bad, [], msg=f"parse_hymn_refs 失败 {len(bad)} 例，前 20：{bad[:20]}")

    def test_thousand_smoke(self):
        self.assertEqual(parse_hymn_number("一千"), 1000)
        self.assertEqual(parse_hymn_number("一千零五"), 1005)
        self.assertEqual(parse_hymn_number("一千零五十"), 1050)
        self.assertEqual(parse_hymn_number("一千五"), 1500)
        self.assertEqual(parse_hymn_number("一〇〇五"), 1005)


if __name__ == "__main__":
    unittest.main()
