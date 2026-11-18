# -*- coding: utf-8 -*-
"""阶段 2 离线验证（只读、可重复）。逐项 PASS/FAIL，最后一行「STAGE2 OFFLINE: ALL PASS」或列出失败项。

用法：python qa4/backend/tools/verify_stage2.py
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

QA4_ROOT = _BACKEND.parent
FIX = _BACKEND / "tests" / "fixtures"

FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def main() -> int:
    # 1 配置文件
    cfg_dir = _BACKEND / "config"
    for name in ("retrieval.json", "scripture.json", "index_map.json", "expected_counts.json"):
        p = cfg_dir / name
        try:
            json.loads(p.read_text(encoding="utf-8"))
            check(f"config/{name} 合法", True)
        except Exception as e:
            check(f"config/{name} 合法", False, type(e).__name__)
    try:
        from retrieval.config import retrieval_cfg

        rc = retrieval_cfg()
        idx = rc.get("indices") or {}
        check("retrieval.json 十个索引", len(idx) == 10, f"n={len(idx)}")
        need = {"bm25_size", "knn_k", "knn_num_candidates", "rrf_k", "rerank_top", "per_subquestion_cap", "whole_question_cap", "unsplit_question_cap", "per_message_cap"}
        check("retrieval.json 检索参数齐全", need <= set(rc.get("params") or {}), str(sorted(need - set(rc.get("params") or {}))))
        check("pano_catalog 不参与检索", (idx.get("pano_catalog") or {}).get("searchable") is False)
        ds = set(rc.get("default_scope") or [])
        check("默认库不含 bible/hymns/pano_catalog", not ({"bible", "hymns", "pano_catalog"} & ds))
    except Exception as e:
        check("retrieval.json 结构", False, type(e).__name__)

    # 2 manifest 与 bible_data
    bible_dir = QA4_ROOT / "data" / "bible_data"
    man_path = QA4_ROOT / "data" / "bible_data.manifest.json"
    try:
        sys.path.insert(0, str(_BACKEND / "tools"))
        bm = importlib.import_module("build_bible_manifest")
        fails = bm.check(bible_dir, man_path)
        check("manifest 与 bible_data 一致（SHA256）", not fails, "; ".join(fails[:3]))
        man = json.loads(man_path.read_text(encoding="utf-8"))
        t = man.get("totals") or {}
        check("manifest 66 文件 / 1189 章 / 31103 节", (t.get("files"), t.get("chapters"), t.get("verses")) == (66, 1189, 31103), json.dumps(t))
        from scripture.bible_text import BibleText

        tot = BibleText(bible_dir).totals()
        check("bible_data 实读 66 卷 / 1189 章 / 31103 节", (tot["books"], tot["chapters"], tot["verses"]) == (66, 1189, 31103), json.dumps(tot))
    except Exception as e:
        check("manifest / bible_data", False, f"{type(e).__name__}")

    # 3 scripture 夹具
    try:
        from scripture.bible_text import BibleText
        from scripture.normalize import heuristic_miss, parse_refs

        b = BibleText(bible_dir)
        ps = json.loads((FIX / "psalm_title_samples.json").read_text(encoding="utf-8"))["samples"]
        on_ok = all(len(parse_refs(s["raw"], bible=b, psalm_title=True)) == 1 for s in ps)
        off_fail = all(parse_refs(s["raw"], bible=b, psalm_title=False) == [] for s in ps)
        check(f"诗篇夹具（{len(ps)} 例）开关开可解析且含标题", on_ok)
        check("诗篇夹具开关关按失败处理", off_fail)
        zero = json.loads((FIX / "reading_lines_zero.json").read_text(encoding="utf-8"))
        check(
            "零出处夹具仍为零（normalize v2 后 1 行）",
            len(zero) == 1 and all(parse_refs(r["line"], bible=b) == [] for r in zero),
        )
        miss = json.loads((FIX / "reading_lines_miss.json").read_text(encoding="utf-8"))
        miss_ok = len(miss) == 22 and all(
            heuristic_miss(r["line"], len(parse_refs(r["line"], bible=b))) for r in miss
        )
        check("疑似遗漏夹具现状不变（normalize v2 后 22 行）", miss_ok)

        # 旧路径覆盖：旧出处须被新出处严格包含（允许 3 条假整章白名单）
        from tools.diff_3a_normalize_v2 import parse_refs_old
        from scripture.normalize import reading_line_of, KIND_CHAPTER, KIND_CHAPTER_RANGE, KIND_CROSS, KIND_BOOK

        td_path = QA4_ROOT / "data" / "graph_annotations" / "truth_dictionary_3a3b.json"
        whitelist = {
            ("保罗书信中真理的要点", "弗2"),
            ("利未人", "申10"),
            ("珍赏", "歌5"),
        }

        def _endpoints(r):
            if r.kind == KIND_BOOK:
                return (0, 0), (10_000, 10_000)
            if r.kind == KIND_CHAPTER_RANGE:
                return (r.chapter, 1), (r.end_chapter, 10_000)
            if r.kind == KIND_CHAPTER:
                return (r.chapter, 1), (r.chapter, 10_000)
            if r.kind == KIND_CROSS:
                return (r.chapter, r.v_start), (r.end_chapter, r.v_end)
            return (r.chapter, r.v_start), (r.chapter, r.v_end)

        def _covers(new_r, old_r) -> bool:
            if new_r.book_no != old_r.book_no:
                return False
            ns, ne = _endpoints(new_r)
            os_, oe = _endpoints(old_r)
            return ns <= os_ and ne >= oe

        uncovered: list[str] = []
        if td_path.is_file():
            for row in json.loads(td_path.read_text(encoding="utf-8")):
                title = row.get("title") or ""
                line = reading_line_of(row.get("content_3a") or "")
                if line is None:
                    continue
                old_refs = parse_refs_old(line, bible=b)
                new_refs = parse_refs(line, bible=b)
                for o in old_refs:
                    lab = o.label()
                    if (title, lab) in whitelist:
                        continue
                    if not any(_covers(n, o) for n in new_refs):
                        uncovered.append(f"{title}:{lab}")
                        if len(uncovered) >= 20:
                            break
                if len(uncovered) >= 20:
                    break
            check(
                "旧路径覆盖（除 3 条假整章白名单）",
                not uncovered,
                f"未覆盖 n={len(uncovered)} 样例={uncovered[:5]}",
            )
        else:
            check("旧路径覆盖（缺 3a3b.json，跳过）", True)
    except Exception as e:
        check("scripture 夹具", False, type(e).__name__)

    # 4 模块可导入
    mods = [
        "scripture.vendor_get_vers_v21",
        "scripture.bible_text",
        "scripture.normalize",
        "scripture.reverse",
        "core.embedding_client",
        "core.rerank_client",
        "retrieval.config",
        "retrieval.scope",
        "retrieval.es_search",
        "retrieval.fusion",
        "retrieval.dedupe",
        "retrieval.service",
        "retrieval.targeted",
        "retrieval.fake",
        "lookups.definitions",
        "lookups.year_table",
    ]
    for m in mods:
        try:
            importlib.import_module(m)
            check(f"导入 {m}", True)
        except Exception as e:
            check(f"导入 {m}", False, type(e).__name__)

    # 5 verified=false 字段数
    try:
        from retrieval.config import unverified_fields

        uv = unverified_fields()
        print(f"INFO retrieval.json 中 verified=false 的配置项：{len(uv)}")
        for u in uv:
            print(f"     - {u}")
        check("verified=false 字段已列出", True, f"n={len(uv)}")
    except Exception as e:
        check("verified=false 统计", False, type(e).__name__)

    if FAILS:
        print("STAGE2 OFFLINE: FAIL — " + "；".join(FAILS))
        return 1
    print("STAGE2 OFFLINE: ALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
