# -*- coding: utf-8 -*-
"""测试共用：路径、bible 单例、静音日志。"""

from __future__ import annotations

import json
import logging
import sys
from functools import lru_cache
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

QA4_ROOT = BACKEND.parent
FIXTURES = Path(__file__).resolve().parent / "fixtures"
BIBLE_DIR = QA4_ROOT / "data" / "bible_data"
TD_PATH = QA4_ROOT / "data" / "graph_annotations" / "truth_dictionary_3a3b.json"
LOOKUP_DIR = QA4_ROOT / "data" / "lookups"


def fixture(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def bible():
    from scripture.bible_text import BibleText

    return BibleText(BIBLE_DIR)


def quiet(*names: str) -> None:
    for n in names:
        logging.getLogger(n).setLevel(logging.CRITICAL)
