# -*- coding: utf-8 -*-
"""阶段 0 查表核对：逐项 PASS / FAIL。"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from lookups.loader import LookupStoreError, load_lookups  # noqa: E402

EXPECT = {
    "lexicon_expanded": 2380,
    "lexicon_main": 2372,
    "zui": 133,
    "other": 2239,
    "wenji_year": 42,
    "no_year_titles": 61,
    "no_year_chunks": 5551,
    "volume": 1293,
    "life": 63,
    "cwwn": 106,
    "others": 3,
    "feasts": 259,
    "hymn_overlap": 398,
    "authors": 3,
    "tier_最内在": 133,
    "tier_外在": 1658,
    "tier_内在": 497,
    "tier_显出为外在": 84,
    "tier_exp_最内在": 133,
    "tier_exp_外在": 1661,
    "tier_exp_内在": 499,
    "tier_exp_显出为外在": 87,
}


def _load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def _pass(name: str, actual, expect) -> bool:
    ok = actual == expect
    status = "PASS" if ok else "FAIL"
    print(f"{status} {name}: 实际={actual} 期望={expect}")
    return ok


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--lookup-dir",
        default=str(Path(__file__).resolve().parents[2] / "data" / "lookups"),
    )
    args = parser.parse_args()
    root = Path(args.lookup_dir)
    if not root.is_dir():
        print(f"FAIL lookup 目录不存在：{root}")
        return 1

    ok_all = True
    man_path = root / "MANIFEST.json"
    if not man_path.is_file():
        print("FAIL 缺少 MANIFEST.json")
        return 1
    manifest = _load(man_path)
    missing = manifest.get("missing_sources") or []
    if missing:
        print(f"INFO 缺来源项：{missing}")

    try:
        store = load_lookups(root)
        print("PASS loader 启动核对（条数与 SHA256）")
    except LookupStoreError as e:
        print(f"FAIL loader：{e}")
        return 1

    lex = store.lexicon
    main = [e for e in lex if not e.get("same_as")]
    ok_all &= _pass("lexicon_main", len(main), EXPECT["lexicon_main"])
    ok_all &= _pass("lexicon_expanded", len(lex), EXPECT["lexicon_expanded"])

    from collections import Counter

    t_main = Counter(e["tier"] for e in main)
    t_exp = Counter(e["tier"] for e in lex)
    for tier in ("最内在", "外在", "内在", "显出为外在"):
        ok_all &= _pass(f"tier_main/{tier}", t_main[tier], EXPECT[f"tier_{tier}"])
        ok_all &= _pass(f"tier_exp/{tier}", t_exp[tier], EXPECT[f"tier_exp_{tier}"])

    ok_all &= _pass("zui_neizai_133", len(store.zui_neizai), EXPECT["zui"])
    ok_all &= _pass("other_2239", len(store.other_2239), EXPECT["other"])
    ok_all &= _pass(
        "zui+other",
        len(store.zui_neizai) + len(store.other_2239),
        EXPECT["lexicon_main"],
    )
    inter = set(store.zui_neizai) & set(store.other_2239)
    ok_all &= _pass("zui∩other", len(inter), 0)

    year = _load(root / "wenji_year_table.json")
    ok_all &= _pass("wenji_year_table", len(year), EXPECT["wenji_year"])
    no_year = _load(root / "no_year_titles.json")
    ok_all &= _pass(
        "no_year_titles", no_year.get("title_count"), EXPECT["no_year_titles"]
    )
    ok_all &= _pass(
        "no_year_chunks", no_year.get("chunk_count"), EXPECT["no_year_chunks"]
    )

    # volume csv
    import csv

    with (root / "wenji_volume_table.csv").open(encoding="utf-8-sig", newline="") as f:
        vol_n = sum(1 for _ in csv.DictReader(f))
    ok_all &= _pass("wenji_volume_table", vol_n, EXPECT["volume"])

    ok_all &= _pass("life_books", len(_load(root / "life_books.json")), EXPECT["life"])
    ok_all &= _pass("cwwn_books", len(_load(root / "cwwn_books.json")), EXPECT["cwwn"])
    ok_all &= _pass(
        "others_books", len(_load(root / "others_books.json")), EXPECT["others"]
    )
    ok_all &= _pass("feasts", len(_load(root / "feasts.json")), EXPECT["feasts"])
    hymns = _load(root / "hymn_series.json")
    ok_all &= _pass(
        "hymn_overlap",
        hymns.get("daben_buchong_number_overlap"),
        EXPECT["hymn_overlap"],
    )
    ok_all &= _pass("authors", len(_load(root / "authors.json")), EXPECT["authors"])

    # 别名抽查
    term = store.get_term("路得马丁")
    ok_all &= _pass(
        "alias 路得马丁→路德马丁",
        term["name"] if term else None,
        "路德马丁",
    )
    ignored = store.get_term("城市")
    ok_all &= _pass("ignore 城市", ignored, None)

    print("=== summary ===")
    print("ALL PASS" if ok_all else "HAS FAIL")
    return 0 if ok_all else 1


if __name__ == "__main__":
    raise SystemExit(main())
