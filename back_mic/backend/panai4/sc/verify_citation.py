# -*- coding: utf-8 -*-
"""SC 引用统计验证。不调用真实 API。写入 logs/sc_citation.log。"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

from docx import Document

from panai4 import db as panai4_db
from panai4.sc import store
from panai4.sc.citation import compute_citation_stats
from panai4.sc.data import load_sc_data
from panai4.sc.export_sc import build_sc_docx

_REPO = Path(__file__).resolve().parents[4]
_LOG = _REPO / "logs" / "sc_citation.log"
_lines: list[str] = []


def log(msg: str = "") -> None:
    _lines.append(msg)
    try:
        print(msg)
    except UnicodeEncodeError:
        print(msg.encode("utf-8", errors="replace").decode("ascii", errors="replace"))


def check(cond: bool, ok: str, fail: str) -> int:
    if cond:
        log(f"PASS: {ok}")
        return 0
    log(f"FAIL: {fail}")
    return 1


MOCK_OUTPUT = """【职事界定】
1. 某条。（依据：参考材料·甲、乙；出三6｜原用语）
2. 另一条。（依据：参考材料·括号甲｜原用语）

【真理脉络】
0. 核心命题……
1. A→B。（参考材料：乙；经文明文：罗四17）
2. C→D。（经文明文：加六16；参考材料：丙、丁）
3. E→F。（参考材料：未选词X）

【负担说明】
这段里写了参考材料·负担里的词，不应计入。
"""

MOCK_TERMS = [
    {"name": "甲", "tier": "最内在", "has_3a": True},
    {"name": "乙", "tier": "内在", "has_3a": True},
    {"name": "丙", "tier": "外在", "has_3a": True},
    {"name": "丁", "tier": "外在", "has_3a": True},
    {"name": "括号甲", "tier": "内在", "has_3a": True},
    {"name": "括号乙", "tier": "内在", "has_3a": True},
    {"name": "无3a词", "tier": "外在", "has_3a": False},
]

MOCK_CONTENT = {
    "甲": "定义甲",
    "乙": "定义乙",
    "丙": "定义丙",
    "丁": "定义丁",
    "括号甲": "同一括号定义",
    "括号乙": "同一括号定义",
    "无3a词": None,
}


def main() -> int:
    fails = 0
    log("=== SC CITATION VERIFY ===")

    log("--- 1 mock 样例 ---")
    stats = compute_citation_stats(
        ref_output=MOCK_OUTPUT,
        final_terms=MOCK_TERMS,
        skipped=["无3a词"],
        merged=["括号乙"],
        content_3a=MOCK_CONTENT,
    )
    log(json.dumps(stats, ensure_ascii=False, indent=2))
    fails += check(stats["sent_total"] == 5, f"基数={stats['sent_total']}（6有3a-1合并=5）", f"基数={stats['sent_total']}")
    by_name = {t["name"]: t for t in stats["terms"]}
    fails += check(by_name["甲"]["status"] == "defs_only", "甲 仅界定", f"甲={by_name.get('甲')}")
    fails += check(by_name["乙"]["status"] == "in_outline", "乙 入脉络", f"乙={by_name.get('乙')}")
    fails += check(by_name["丙"]["status"] == "in_outline", "丙 入脉络", f"丙={by_name.get('丙')}")
    fails += check(by_name["丁"]["status"] == "in_outline", "丁 入脉络", f"丁={by_name.get('丁')}")
    fails += check(
        by_name["括号甲"]["status"] == "defs_only" and by_name["括号乙"]["status"] == "defs_only",
        "括号对：只引括号甲 → 两个都仅界定",
        f"括号甲/乙={by_name.get('括号甲')}/{by_name.get('括号乙')}",
    )
    fails += check("无3a词" not in by_name, "无3a 不在清单", "无3a 被计入")
    fails += check(
        any(u["name"] == "未选词X" for u in stats["unknown_cited"]),
        "未选词X 在 unknown_cited",
        f"unknown={stats['unknown_cited']}",
    )
    fails += check(
        1 in (by_name["甲"]["def_items"] or []) and 1 in (by_name["乙"]["outline_items"] or []),
        "序号：甲界定1、乙脉络1",
        f"甲def={by_name['甲'].get('def_items')} 乙out={by_name['乙'].get('outline_items')}",
    )

    log("--- 2 负担说明中的参考材料不计 ---")
    burden_only = """【职事界定】
1. 无引用。

【真理脉络】
1. 无引用。

【负担说明】
正文参考材料·偷偷词不应计入。
"""
    s2 = compute_citation_stats(
        ref_output=burden_only,
        final_terms=[{"name": "偷偷词", "tier": "外在", "has_3a": True}],
        skipped=[],
        merged=[],
        content_3a={"偷偷词": "x"},
    )
    fails += check(
        s2.get("note") == "输出中没有参考材料标记，无法统计",
        f"note={s2.get('note')}",
        f"负担里的标记被误计: {s2}",
    )

    log("--- 3 缺标记 ---")
    s3 = compute_citation_stats(
        ref_output="【职事界定】\n1. 旧输出无标记。\n【真理脉络】\n1. 也无。\n【负担说明】\n正文。",
        final_terms=[{"name": "甲", "tier": "最内在", "has_3a": True}],
        content_3a={"甲": "a"},
    )
    fails += check(
        s3.get("note") == "输出中没有参考材料标记，无法统计",
        "缺标记返回 note",
        f"s3={s3}",
    )

    log("--- 4 run #19 真实存档 ---")
    store.ensure_tables()
    row = panai4_db.connect().execute(
        "SELECT id, cost_ref_usd, ref_result, final_terms_json, skipped_json, merged_json FROM sc_runs WHERE id=19"
    ).fetchone()
    if not row:
        fails += check(False, "", "找不到 run #19")
    else:
        run = dict(row)
        data = load_sc_data(force=True)
        terms = json.loads(run["final_terms_json"] or "[]")
        skipped = json.loads(run["skipped_json"] or "[]")
        merged = json.loads(run["merged_json"] or "[]")
        s19 = compute_citation_stats(
            ref_output=run["ref_result"],
            final_terms=terms,
            skipped=skipped,
            merged=merged,
            content_3a=data.content_3a,
            tier_of=data.tier_of,
        )
        in_o = sum(1 for t in s19["terms"] if t["status"] == "in_outline")
        # terms may list merge pairs twice; count unique by group via by_tier
        in_o_g = sum(s19["by_tier"][t]["in_outline"] for t in ("最内在", "内在", "外在"))
        defs_g = sum(s19["by_tier"][t]["defs_only"] for t in ("最内在", "内在", "外在"))
        unc_g = sum(s19["by_tier"][t]["uncited"] for t in ("最内在", "内在", "外在"))
        cited = in_o_g + defs_g
        log(f"cost_ref_usd={run['cost_ref_usd']}")
        log(f"sent_total={s19['sent_total']} by_tier={json.dumps(s19['by_tier'], ensure_ascii=False)}")
        log(f"入脉络(组)={in_o_g} 仅界定(组)={defs_g} 未引用(组)={unc_g} 被引用合计={cited}")
        log(f"unknown_cited={s19['unknown_cited']}")
        zui = [t for t in s19["terms"] if t["tier"] == "最内在" and t["status"] == "in_outline"]
        log(f"最内在入脉络: {[t['name'] for t in zui]}")
        defs_only_names = [t["name"] for t in s19["terms"] if t["status"] == "defs_only"]
        log(f"仅界定: {defs_only_names}")
        log("预期对照（不强制）：被引用≈14，入脉络≈13，仅界定≈1（加拉太书），最内在仅「变化」，unknown=0")
        log(
            f"实际对照：被引用={cited}，入脉络={in_o_g}，仅界定={defs_g}，"
            f"最内在入脉络={ [t['name'] for t in zui] }，unknown={len(s19['unknown_cited'])}"
        )
        for t in s19["terms"]:
            if t["status"] != "uncited":
                log(
                    f"  · {t['name']}〔{t['tier']}〕{t['status_label']} "
                    f"界定={t['def_items']} 脉络={t['outline_items']}"
                )

    log("--- 5 整体导出含引用统计页 ---")
    if row:
        run = dict(row)
        data = load_sc_data()
        terms = json.loads(run["final_terms_json"] or "[]")
        skipped = json.loads(run["skipped_json"] or "[]")
        merged = json.loads(run["merged_json"] or "[]")
        s19 = compute_citation_stats(
            ref_output=run["ref_result"],
            final_terms=terms,
            skipped=skipped,
            merged=merged,
            content_3a=data.content_3a,
            tier_of=data.tier_of,
        )
        blob = build_sc_docx(
            {
                "topic": "test",
                "final_terms": terms,
                "skipped": skipped,
                "merged": merged,
                "plain_result": "p",
                "ref_result": run["ref_result"],
                "citation_stats": s19,
            }
        )
        doc = Document(io.BytesIO(blob))
        texts = [p.text for p in doc.paragraphs]
        fails += check(
            any(t == "引用统计" for t in texts),
            "docx 含「引用统计」页标题",
            f"未找到引用统计，末段={texts[-8:]}",
        )
        fails += check(
            any("词条名｜状态｜职事界定序号｜真理脉络环序号" in t for t in texts),
            "docx 含表头",
            "缺表头",
        )
        # 抽查一个状态行与接口一致
        sample = next((t for t in s19["terms"] if t["status"] == "in_outline"), None)
        if sample:
            fails += check(
                any(sample["name"] in t and "入脉络" in t for t in texts),
                f"docx 含 {sample['name']} 入脉络",
                f"docx 缺 {sample['name']}",
            )

    log("--- 6 前端构建由外层执行 ---")
    log("(npm run build)")

    log("")
    log(f"=== RESULT fails={fails} ===")
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    _LOG.write_text("\n".join(_lines) + "\n", encoding="utf-8")
    log(f"wrote {_LOG}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
