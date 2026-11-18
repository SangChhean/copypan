# -*- coding: utf-8 -*-
"""阶段 0 unittest（不依赖 pytest）。"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from lookups.loader import LookupStoreError, load_lookups  # noqa: E402
from lookups.name_norm import NameNorm  # noqa: E402


LOOKUP_DIR = Path(__file__).resolve().parents[2] / "data" / "lookups"
ALIASES = _BACKEND / "lookups" / "aliases.json"


@unittest.skipUnless(LOOKUP_DIR.is_dir(), "lookups 尚未生成")
class TestStage0Lookups(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.store = load_lookups(LOOKUP_DIR)

    def test_alias_lude(self):
        term = self.store.get_term("路得马丁")
        self.assertIsNotNone(term)
        self.assertEqual(term["name"], "路德马丁")

    def test_ignore_city_logged(self):
        norm = NameNorm.from_aliases_file(ALIASES)
        self.assertIsNone(norm.normalize("城市", context="test"))
        self.assertTrue(any(x.get("action") == "ignore" for x in norm.logs))

    def test_zui_other_partition(self):
        zui = self.store.zui_neizai
        other = self.store.other_2239
        self.assertEqual(len(zui), 133)
        self.assertEqual(len(other), 2239)
        self.assertEqual(len(zui) + len(other), 2372)
        self.assertEqual(len(set(zui) & set(other)), 0)

    def test_paren_expand_2380(self):
        self.assertEqual(len(self.store.lexicon), 2380)
        inners = [e for e in self.store.lexicon if e.get("same_as")]
        self.assertEqual(len(inners), 8)
        # 括号内 → 外
        self.assertEqual(self.store.resolve_outer("晨兴"), "晨晨复兴")

    def test_loader_rejects_bad_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            # 复制必要文件
            for p in LOOKUP_DIR.iterdir():
                if p.is_file():
                    shutil.copy2(p, tmp_path / p.name)
            # 篡改 lexicon
            lex_path = tmp_path / "lexicon.json"
            data = json.loads(lex_path.read_text(encoding="utf-8"))
            data.append({"name": "__tamper__", "tier": "外在"})
            lex_path.write_text(
                json.dumps(data, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(LookupStoreError):
                load_lookups(tmp_path)


class TestNameNormUnit(unittest.TestCase):
    def test_alias_and_ignore(self):
        norm = NameNorm.from_aliases_file(ALIASES)
        self.assertEqual(norm.normalize("路得马丁"), "路德马丁")
        self.assertIsNone(norm.normalize("城市"))
        actions = [x["action"] for x in norm.logs]
        self.assertIn("alias", actions)
        self.assertIn("ignore", actions)


if __name__ == "__main__":
    unittest.main()
