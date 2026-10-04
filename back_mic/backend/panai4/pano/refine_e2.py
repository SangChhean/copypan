# -*- coding: utf-8 -*-
"""修正 E2 分类口径（F1–F4）。

只读 catalog_clean.json，复用上一轮 consistency 的桶划分逻辑。
不碰源目录、不碰 ES。

用法（在 back_mic/backend 下）::

    python -m panai4.pano.refine_e2
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from panai4.pano.consistency import (
    analyze,
    count_mounts,
    direct_child_dirs,
    iter_dirs,
)

CATALOG_DEFAULT = Path(r"G:\PanAI4.0专用\清明上河图目录\catalog_clean.json")
DOCS = Path(__file__).resolve().parents[4] / "docs" / "panai4_es"
REPORT_DEFAULT = DOCS / "pano_e2_refine.md"
RENAME_DEFAULT = DOCS / "pano_fix_names.md"
GAPS_DEFAULT = DOCS / "pano_gaps.md"


def child_declared_sum(node: dict) -> int:
    """直接子目录声明数之和（无声明的子不计）。"""
    total = 0
    for c in direct_child_dirs(node):
        v = c.get("declared_count")
        if v is not None:
            total += v
    return total


def has_empty_subdir(node: dict) -> bool:
    """该节点下是否有空子目录（无子 dir、无 message）。"""
    for c in direct_child_dirs(node):
        kids = c.get("children") or []
        if not kids:
            return True
        # 也把「只有空孙目录」算空？任务说「空子目录」——直接子为空即可
    return False


def top_category(path: str) -> str:
    return path.split("/")[0] if path else ""


def enrich(row: dict, node_by_path: dict[str, dict]) -> dict:
    node = node_by_path[row["path"]]
    child_sum = child_declared_sum(node)
    out = dict(row)
    out["child_sum"] = child_sum
    out["parent_declared"] = row["declared"]
    out["sub_consistent"] = child_sum == row["actual"]
    out["child_actual_diff"] = abs(row["actual"] - child_sum)
    out["has_empty_subdir"] = has_empty_subdir(node)
    return out


def refine(catalog: dict) -> dict[str, Any]:
    base = analyze(catalog)
    node_by_path = {d["rel_path"]: d for d in iter_dirs(catalog)}

    A = [enrich(r, node_by_path) for r in base["buckets"]["A"]]
    B0 = [enrich(r, node_by_path) for r in base["buckets"]["B"]]
    C0 = [enrich(r, node_by_path) for r in base["buckets"]["C"]]
    D0 = [enrich(r, node_by_path) for r in base["buckets"]["D"]]

    assert len(A) == 15 and len(B0) == 124 and len(C0) == 176 and len(D0) == 23

    # ---- F1 重判 D ----
    B_from_D: list[dict] = []
    D2: list[dict] = []
    D_true: list[dict] = []
    for r in D0:
        if r["actual"] == r["child_sum"]:
            r = dict(r)
            r["sub_consistent"] = True
            r["refine_from"] = "D→B"
            B_from_D.append(r)
        elif abs(r["actual"] - r["child_sum"]) <= 5:
            r = dict(r)
            r["refine_from"] = "D→D2"
            D2.append(r)
        else:
            r = dict(r)
            r["refine_from"] = "D"
            D_true.append(r)

    B = list(B0)
    for r in B:
        r["refine_from"] = "B"
        r["sub_consistent"] = bool(r.get("sub_consistent"))
    B.extend(B_from_D)

    # ---- F2 拆 C ----
    C1: list[dict] = []
    C2: list[dict] = []
    for r in C0:
        if r["actual"] == r["child_sum"]:
            r = dict(r)
            r["refine_from"] = "C→C1"
            r["sub_consistent"] = True
            C1.append(r)
        else:
            r = dict(r)
            r["refine_from"] = "C→C2"
            C2.append(r)

    buckets = {
        "A": sorted(A, key=lambda x: (-abs(x["diff"]), x["path"])),
        "B": sorted(B, key=lambda x: (-abs(x["diff"]), x["path"])),
        "C1": sorted(C1, key=lambda x: (-abs(x["diff"]), x["path"])),
        "C2": sorted(C2, key=lambda x: (-abs(x["diff"]), x["path"])),
        "D": sorted(D_true, key=lambda x: (-abs(x["diff"]), x["path"])),
        "D2": sorted(D2, key=lambda x: (-abs(x["diff"]), x["path"])),
    }

    total_n = sum(len(v) for v in buckets.values())
    assert total_n == 338, f"sum={total_n} != 338"

    # ---- F3 / G1 缺口：剔除 D 真异常子树；G2 移走 76 题库 ----
    d_true_paths = {r["path"] for r in D_true}

    def under_d_true(path: str) -> bool:
        if path in d_true_paths:
            return True
        for p in d_true_paths:
            if path.startswith(p + "/"):
                return True
        return False

    MOVE_TO_RENAME = "76　圣经真理题库——3819篇"
    MOVE_NOTE = (
        "本机 kg-rag_map_note 索引 doc 数 = 3500，与目录实际挂载数 3500 完全一致，"
        "两个独立来源互证，故 3819 为过时声明数，非内容缺失。"
    )

    gap_nodes: list[dict] = []
    moved_to_rename: list[dict] = []
    excluded_gaps = []
    for key in ("A", "C2"):
        for r in buckets[key]:
            if under_d_true(r["path"]):
                excluded_gaps.append(r)
                continue
            if r["path"] == MOVE_TO_RENAME or r["path"].startswith(MOVE_TO_RENAME + "/"):
                rr = dict(r)
                rr["refine_from"] = "C2→rename(76)"
                rr["move_note"] = MOVE_NOTE
                moved_to_rename.append(rr)
                continue
            gap_nodes.append(dict(r))

    gap_path_set = {r["path"] for r in gap_nodes}
    gap_by_path = {r["path"]: r for r in gap_nodes}
    node_by_path = {d["rel_path"]: d for d in iter_dirs(catalog)}

    for r in gap_nodes:
        r["gap"] = r["declared"] - r["actual"]
        # H1：有缺口子孙 → 不计入 deepest_gap
        r["has_gap_descendant"] = any(
            p != r["path"] and p.startswith(r["path"] + "/") for p in gap_path_set
        )

    def first_gap_descendants_under(path: str) -> list[dict]:
        """path 下、中间不再隔着其它缺口节点的缺口子孙。"""
        out = []
        for gp, gr in gap_by_path.items():
            if gp == path or not gp.startswith(path + "/"):
                continue
            rel = gp[len(path) + 1 :]
            parts = rel.split("/")
            blocked = False
            for i in range(len(parts) - 1):
                anc = path + "/" + "/".join(parts[: i + 1])
                if anc in gap_by_path:
                    blocked = True
                    break
            if not blocked:
                out.append(gr)
        return out

    def child_gap_sum(path: str) -> int:
        """直接子节点缺口之和。

        子在缺口清单 → 用其缺口；
        子不在清单（声明=实际的中间层，如「伍　基督」）→ 取其下第一层缺口子孙之和。
        不做全树递归累加。
        """
        node = node_by_path.get(path)
        if not node:
            return 0
        total = 0
        for c in direct_child_dirs(node):
            cp = c["rel_path"]
            if cp in gap_by_path:
                total += gap_by_path[cp]["gap"]
            else:
                total += sum(g["gap"] for g in first_gap_descendants_under(cp))
        return total

    for r in gap_nodes:
        cg = child_gap_sum(r["path"])
        r["child_gap_sum"] = cg
        r["residual"] = max(0, r["gap"] - cg)

    # 顶层节点 lookup（100 大类）
    top_nodes = {
        c["rel_path"]: c
        for c in (catalog.get("children") or [])
        if c.get("type") == "dir"
    }
    mounts_all = {d["rel_path"]: count_mounts(d) for d in iter_dirs(catalog)}

    def net_top_of(cat: str) -> int | None:
        n = top_nodes.get(cat)
        if not n or n.get("declared_count") is None:
            return None
        return n["declared_count"] - mounts_all.get(cat, 0)

    # 按大类
    cats_in_gaps = sorted({top_category(r["path"]) for r in gap_nodes})
    by_cat: dict[str, dict] = {}
    for cat in cats_in_gaps:
        members = [r for r in gap_nodes if top_category(r["path"]) == cat]
        deepest = [r for r in members if not r["has_gap_descendant"]]
        # residual 只加在非最深节点上，避免与 deepest_gap 双计
        residual_sum = sum(
            r["residual"] for r in members if r["has_gap_descendant"]
        )
        deepest_gap = sum(r["gap"] for r in deepest)
        total_gap = deepest_gap + residual_sum
        net_top = net_top_of(cat)
        offset = None if net_top is None else total_gap - net_top
        by_cat[cat] = {
            "net_top": net_top,
            "deepest_gap": deepest_gap,
            "residual_sum": residual_sum,
            "total_gap": total_gap,
            "offset": offset,
            "node_count": len(deepest),
            "members": members,
            "deepest": deepest,
        }

    # 全库
    all_deepest = [r for r in gap_nodes if not r["has_gap_descendant"]]
    residual_sum_global = sum(
        r["residual"] for r in gap_nodes if r["has_gap_descendant"]
    )
    deepest_gap_global = sum(r["gap"] for r in all_deepest)
    total_gap_global = deepest_gap_global + residual_sum_global

    net_top_global = 0
    net_top_global_n = 0
    for cat, node in top_nodes.items():
        if node.get("declared_count") is None:
            continue
        net_top_global += node["declared_count"] - mounts_all.get(cat, 0)
        net_top_global_n += 1

    global_stats = {
        "net_top": net_top_global,
        "net_top_n": net_top_global_n,
        "deepest_gap": deepest_gap_global,
        "residual_sum": residual_sum_global,
        "total_gap": total_gap_global,
        "offset": total_gap_global - net_top_global,
        "node_count": len(all_deepest),
        "round1_overlap": 1725,
        "round2_shallow": 466,
        "round3_deepest": 563,
    }

    # I4 硬检查
    cat06 = "06　结晶读经——2638篇"
    cat100 = "100　圣经中的人名与地名——1135篇"
    st06 = by_cat.get(cat06)
    st100 = by_cat.get(cat100)
    i4_ok = True
    i4_msgs = []
    if not st06 or st06["total_gap"] != 184 or st06["residual_sum"] != 0:
        i4_ok = False
        got = st06["total_gap"] if st06 else None
        rsum = st06["residual_sum"] if st06 else None
        i4_msgs.append(f"06 结晶读经 total_gap={got} residual_sum={rsum}（期望 184 / 0）")
    if not st100 or not (70 <= st100["total_gap"] <= 80):
        i4_ok = False
        got = st100["total_gap"] if st100 else None
        i4_msgs.append(f"100 人名地名 total_gap={got}（期望约 76）")

    top15 = sorted(
        by_cat.items(),
        key=lambda x: (-x[1]["total_gap"], x[0]),
    )[:15]
    all_cats = sorted(by_cat.items(), key=lambda x: (-x[1]["total_gap"], x[0]))

    offset_ranked = sorted(
        [(cat, st) for cat, st in by_cat.items() if st["offset"] is not None],
        key=lambda x: (-x[1]["offset"], x[0]),
    )
    offset_negative = [(cat, st) for cat, st in offset_ranked if st["offset"] < 0]

    a_hard = sorted(
        [r for r in gap_nodes if r["actual"] == 0],
        key=lambda r: (-r["gap"], r["path"]),
    )

    placeholder_deep = [r for r in all_deepest if r["has_empty_subdir"]]
    scattered_deep = [r for r in all_deepest if not r["has_empty_subdir"]]

    return {
        "buckets": buckets,
        "counts": {k: len(v) for k, v in buckets.items()},
        "total_n": total_n,
        "B_from_D_n": len(B_from_D),
        "D0_n": 23,
        "C0_n": 176,
        "gap_nodes": gap_nodes,
        "excluded_gaps": excluded_gaps,
        "moved_to_rename": moved_to_rename,
        "move_note": MOVE_NOTE,
        "by_cat": by_cat,
        "global_stats": global_stats,
        "top15": top15,
        "all_cats": all_cats,
        "offset_ranked": offset_ranked,
        "offset_negative": offset_negative,
        "a_hard": a_hard,
        "all_deepest": all_deepest,
        "placeholder_deep": placeholder_deep,
        "scattered_deep": scattered_deep,
        "d_true_paths": sorted(d_true_paths),
        "top_nodes": top_nodes,
        "mounts_all": mounts_all,
        "i4_ok": i4_ok,
        "i4_msgs": i4_msgs,
    }


def _stats_line(items: list[dict]) -> str:
    sd = sum(x["declared"] for x in items)
    sa = sum(x["actual"] for x in items)
    sc = sum(x["child_sum"] for x in items)
    return f"条数={len(items)}；声明和={sd}；实际和={sa}；子声明和={sc}"


def _table(items: list[dict], extra_cols: bool = True) -> list[str]:
    lines = []
    if extra_cols:
        lines.append("| 路径 | 声明 | 子声明和 | 实际 | 差(实-声) | sub_consistent |")
        lines.append("|---|---:|---:|---:|---:|:---:|")
        for r in items:
            sc = "是" if r.get("sub_consistent") else "否"
            lines.append(
                f"| `{r['path']}` | {r['declared']} | {r['child_sum']} | "
                f"{r['actual']} | {r['diff']:+d} | {sc} |"
            )
    else:
        lines.append("| 路径 | 声明 | 实际 | 差 |")
        lines.append("|---|---:|---:|---:|")
        for r in items:
            lines.append(
                f"| `{r['path']}` | {r['declared']} | {r['actual']} | {r['diff']:+d} |"
            )
    return lines


def write_refine_report(path: Path, data: dict, catalog_path: Path) -> None:
    lines: list[str] = []
    w = lines.append
    c = data["counts"]

    w("# 清明上河图 E2 分类口径修正")
    w("")
    w("只读 `catalog_clean.json` + 上一轮 consistency 分桶。不碰源目录、不碰 ES。")
    w("")
    w(f"- 输入：`{catalog_path}`")
    w(
        f"- 重分后条数：A={c['A']} B={c['B']} C1={c['C1']} C2={c['C2']} "
        f"D={c['D']} D2={c['D2']}；**合计 {data['total_n']}**"
        f"{'（=338）' if data['total_n'] == 338 else '（≠338）'}"
    )
    w(
        f"- 其中原 D(23) → B:{data['B_from_D_n']} / D2:{c['D2']} / D真异常:{c['D']}"
    )
    w(
        f"- 其中原 C(176) → C1:{c['C1']} / C2:{c['C2']}"
    )
    w("")

    w("## F1　原 D(23) 重判")
    w("")
    w("### D→B（实际 == 子声明和；父数字过时，sub_consistent=true）")
    w("")
    b_from_d = [r for r in data["buckets"]["B"] if r.get("refine_from") == "D→B"]
    w(_stats_line(b_from_d))
    w("")
    lines.extend(_table(b_from_d))
    w("")

    w("### D2　父数字过时（待人工确认）（|实际−子和|≤5）")
    w("")
    w(_stats_line(data["buckets"]["D2"]))
    w("")
    lines.extend(_table(data["buckets"]["D2"]))
    w("")

    w("### D　真异常（其余）")
    w("")
    w(_stats_line(data["buckets"]["D"]))
    w("")
    lines.extend(_table(data["buckets"]["D"]))
    w("")

    w("## F2　原 C(176) 拆分")
    w("")
    w("### C1　实际 == 子和（数字旧，非内容缺失）")
    w("")
    w(_stats_line(data["buckets"]["C1"]))
    w("")
    lines.extend(_table(data["buckets"]["C1"]))
    w("")

    w("### C2　真部分缺失")
    w("")
    w(_stats_line(data["buckets"]["C2"]))
    w("")
    lines.extend(_table(data["buckets"]["C2"]))
    w("")

    w("## F3 / I　缺口口径（total_gap = deepest_gap + residual）")
    w("")
    gs = data["global_stats"]
    if not data["i4_ok"]:
        w("### ⚠ I4 未通过")
        w("")
        for m in data["i4_msgs"]:
            w(f"- {m}")
        w("")
    w("### 全库四轮对照")
    w("")
    w("| 轮次 | 口径 | 数值 |")
    w("|---|---|---:|")
    w(f"| 一 | 父子重复累加 | {gs['round1_overlap']} |")
    w(f"| 二 | 保留最浅 | {gs['round2_shallow']} |")
    w(f"| 三 | deepest_gap | {gs['round3_deepest']} |")
    w(f"| **四** | **total_gap** | **{gs['total_gap']}** |")
    w("")
    w(
        f"- total_gap={gs['total_gap']}；deepest_gap={gs['deepest_gap']}；"
        f"residual_sum={gs['residual_sum']}；net_top={gs['net_top']}；"
        f"offset={gs['offset']}"
    )
    w(
        f"- offset 为负的大类：{len(data['offset_negative'])}"
    )
    w("")

    w("## 验证")
    w("")
    w(
        f"- F1+F2 各类之和：{data['total_n']}"
        f"{' = 338 ✓' if data['total_n'] == 338 else ' ≠ 338'}"
    )
    w(f"- 全库 total_gap = {gs['total_gap']}")
    st06 = data["by_cat"].get("06　结晶读经——2638篇")
    st100 = data["by_cat"].get("100　圣经中的人名与地名——1135篇")
    if st06:
        w(
            f"- 06 total_gap={st06['total_gap']} residual_sum={st06['residual_sum']}"
            f"{' ✓' if st06['total_gap']==184 and st06['residual_sum']==0 else ' ✗'}"
        )
    if st100:
        w(
            f"- 100 total_gap={st100['total_gap']}"
            f"{' ✓' if 70 <= st100['total_gap'] <= 80 else ' ✗'}"
        )
    w("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _path_depth(path: str) -> int:
    return path.count("/") + 1


def _indent_path(path: str) -> str:
    """按 depth-1 缩进，父浅子深。"""
    d = _path_depth(path)
    return ("　" * (d - 1)) + path


def _suggest_rename(r: dict, key: str) -> str:
    n = r["actual"]
    m = r.get("child_sum", 0)
    if key == "D":
        return "三值不一致，勿自动改；先核子树"
    if key == "D2":
        return f"倾向改为 {m} 或 {n}（|实际−子和|≤5，请确认）"
    if r.get("move_note"):
        # 76 题库等专条
        if m == n:
            return f"改为 {n}（子和与实际一致）；{r['move_note']}"
        if m == 0:
            return f"改为 {n}（依实际挂载数）；{r['move_note']}"
        return (
            f"改为 {n}（依实际挂载数；子和为 {m}，不一致，请留意）；"
            f"{r['move_note']}"
        )
    if m == n:
        return f"改为 {n}（子和与实际一致）"
    if m == 0:
        return f"改为 {n}（依实际挂载数）"
    return f"改为 {n}（依实际挂载数；子和为 {m}，不一致，请留意）"


def write_rename_list(path: Path, data: dict) -> None:
    """B + C1 + D2 + D + 移入的 76 → 改文件夹名。"""
    lines: list[str] = []
    w = lines.append
    w("# 清明上河图 — 需改文件夹名清单（交人工）")
    w("")
    w(
        "来源：E2 重分后的 **B + C1 + D2 + D**，外加从缺口移入的 "
        "`76　圣经真理题库`（过时声明，非内容缺失）。"
    )
    w("")

    sections = [
        (
            "B",
            "父数字过时（实际 ≥ 声明；含原 B，以及 D→B 且 sub_consistent）",
            list(data["buckets"]["B"]),
        ),
        ("C1", "父数字过时（实际 < 声明，但实际 == 子声明和）", list(data["buckets"]["C1"])),
        ("D2", "父数字过时（待人工确认，|实际−子和|≤5）", list(data["buckets"]["D2"])),
        ("D", "真异常（父子/实际三值纠缠，需人工看）", list(data["buckets"]["D"])),
        (
            "移入",
            "原列缺口、现改判为过时声明（76 题库）",
            list(data["moved_to_rename"]),
        ),
    ]

    inconsistent_n = 0
    total = 0
    for key, title, items in sections:
        items_sorted = sorted(items, key=lambda r: r["path"])
        total += len(items_sorted)
        w(f"## {key}　{title}（{len(items_sorted)}）")
        w("")
        w("| # | depth | 路径 | 声明 | 子声明和 | 实际 | 建议 |")
        w("|---:|---:|---|---:|---:|---:|---|")
        for i, r in enumerate(items_sorted, 1):
            tip = _suggest_rename(r, key if key != "移入" else "B")
            if "不一致，请留意" in tip:
                inconsistent_n += 1
            depth = _path_depth(r["path"])
            disp = _indent_path(r["path"])
            w(
                f"| {i} | {depth} | `{disp}` | {r['declared']} | {r['child_sum']} | "
                f"{r['actual']} | {tip} |"
            )
        w("")
    w(f"合计：**{total}** 条。")
    w(f"其中建议含「子和与实际不一致」：**{inconsistent_n}** 条。")
    w("")
    data["fix_inconsistent_n"] = inconsistent_n
    data["fix_total_n"] = total
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_gaps_list(path: Path, data: dict) -> None:
    """A + C2 → 真内容缺口；主口径 total_gap = deepest_gap + residual_sum。"""
    lines: list[str] = []
    w = lines.append
    gs = data["global_stats"]
    w("# 清明上河图 — 真内容缺口清单（交人工）")
    w("")
    w(
        "来源：E2 重分后的 **A + C2**（已排除 D 真异常子树；"
        "已移走 `76　圣经真理题库` 至改名清单）。"
    )
    w("")
    w(
        "主口径：**total_gap = deepest_gap + residual_sum**。"
        "residual = max(0, 本节点缺口 − 直接子缺口和)；"
        "直接子若本身不在缺口清单，则取其下第一层缺口子孙（穿过声明=实际的中间层）。"
    )
    w("")

    if not data["i4_ok"]:
        w("## ⚠ I4 自检未通过 — 已停下")
        w("")
        for m in data["i4_msgs"]:
            w(f"- {m}")
        w("")

    w("### 全库合计（四轮对照）")
    w("")
    w("| 轮次 | 口径 | 数值 |")
    w("|---|---|---:|")
    w(f"| 第一轮 | 父子重复累加（高估） | {gs['round1_overlap']} |")
    w(f"| 第二轮 | 保留最浅 gross_leaf（低估） | {gs['round2_shallow']} |")
    w(f"| 第三轮 | deepest_gap（保留最深） | {gs['round3_deepest']} |")
    w(f"| **第四轮** | **total_gap（deepest + residual）** | **{gs['total_gap']}** |")
    w("")
    w(f"- **total_gap**：{gs['total_gap']}")
    w(f"- **deepest_gap**：{gs['deepest_gap']}（node_count={gs['node_count']}）")
    w(f"- **residual_sum**：{gs['residual_sum']}")
    w(f"- **net_top**：{gs['net_top']}（{gs['net_top_n']} 个顶层有声明）")
    w(f"- **offset**（total_gap − net_top）：{gs['offset']}")
    w("")

    w("### I3　offset 为负的大类")
    w("")
    if not data["offset_negative"]:
        w("无。全部大类 offset ≥ 0。")
    else:
        w(f"**仍有 {len(data['offset_negative'])} 个大类 offset < 0**（未改公式，原样列出）：")
        w("")
        w("| 大类 | total_gap | net_top | offset |")
        w("|---|---:|---:|---:|")
        for cat, st in data["offset_negative"]:
            w(f"| `{cat}` | {st['total_gap']} | {st['net_top']} | {st['offset']} |")
    w("")

    w("### 缺口榜前 15（按 total_gap 降序）")
    w("")
    w("| # | 大类 | total_gap | deepest_gap | residual_sum | net_top | offset |")
    w("|---:|---|---:|---:|---:|---:|---:|")
    for i, (cat, st) in enumerate(data["top15"], 1):
        nt = "—" if st["net_top"] is None else str(st["net_top"])
        off = "—" if st["offset"] is None else str(st["offset"])
        w(
            f"| {i} | `{cat}` | {st['total_gap']} | {st['deepest_gap']} | "
            f"{st['residual_sum']} | {nt} | {off} |"
        )
    w("")

    w("### offset 最大的大类")
    w("")
    w("| # | 大类 | total_gap | net_top | offset |")
    w("|---:|---|---:|---:|---:|")
    for i, (cat, st) in enumerate(data["offset_ranked"][:10], 1):
        w(
            f"| {i} | `{cat}` | {st['total_gap']} | {st['net_top']} | "
            f"{st['offset']} |"
        )
    w("")

    w("### A 类：完全空但声明有内容（最硬缺口）")
    w("")
    w(f"共 **{len(data['a_hard'])}** 条，按缺口降序。")
    w("")
    w("| # | 缺 | 声明 | 路径 |")
    w("|---:|---:|---:|---|")
    for i, r in enumerate(data["a_hard"], 1):
        w(f"| {i} | {r['gap']} | {r['declared']} | `{r['path']}` |")
    w("")

    w("---")
    w("")
    w("## 各大类明细")
    w("")
    w(
        "> `has_gap_descendant=是` 者不计入 deepest_gap；"
        "其 residual 计入 residual_sum。"
    )
    w("")

    by_cat = data["by_cat"]
    for cat, st in sorted(
        by_cat.items(),
        key=lambda x: (-x[1]["total_gap"], x[0]),
    ):
        nt = "—" if st["net_top"] is None else str(st["net_top"])
        off = "—" if st["offset"] is None else str(st["offset"])
        w(
            f"## {cat}（total_gap={st['total_gap']} / deepest_gap={st['deepest_gap']} / "
            f"residual_sum={st['residual_sum']} / net_top={nt} / offset={off}）"
        )
        w("")
        items_sorted = sorted(st["members"], key=lambda r: r["path"])
        w(
            "| depth | 路径 | 类 | 声明 | 实际 | 缺 | residual | "
            "has_gap_descendant |"
        )
        w("|---:|---|---|---:|---:|---:|---:|:---:|")
        for r in items_sorted:
            kind = "A" if r["actual"] == 0 else "C2"
            hd = "是" if r["has_gap_descendant"] else "否"
            disp = _indent_path(r["path"])
            w(
                f"| {_path_depth(r['path'])} | `{disp}` | {kind} | "
                f"{r['declared']} | {r['actual']} | {r['gap']} | "
                f"{r['residual']} | {hd} |"
            )
        w("")

    w("## 验证三问")
    w("")
    w(f"1. **全库 total_gap**：{gs['total_gap']}")
    w(
        f"2. **offset 为负的大类**：{len(data['offset_negative'])} 个"
        + (
            "（见上文 I3）"
            if data["offset_negative"]
            else "（无）"
        )
    )
    st06 = by_cat.get("06　结晶读经——2638篇")
    st100 = by_cat.get("100　圣经中的人名与地名——1135篇")
    ok06 = st06 and st06["total_gap"] == 184
    ok100 = st100 and 70 <= st100["total_gap"] <= 80
    w(
        f"3. **06 = 184？** {st06['total_gap'] if st06 else '—'}（{'是' if ok06 else '否'}）；"
        f"**100 ≈ 76？** {st100['total_gap'] if st100 else '—'}（{'是' if ok100 else '否'}）"
    )
    w("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="修正 E2 分类口径")
    parser.add_argument("--catalog", type=Path, default=CATALOG_DEFAULT)
    parser.add_argument("--report", type=Path, default=REPORT_DEFAULT)
    parser.add_argument("--rename", type=Path, default=RENAME_DEFAULT)
    parser.add_argument("--gaps", type=Path, default=GAPS_DEFAULT)
    parser.add_argument(
        "--skip-rename",
        action="store_true",
        help="不改写 pano_fix_names.md",
    )
    args = parser.parse_args(argv)

    if not args.catalog.is_file():
        print(f"ERROR catalog not found: {args.catalog}", file=sys.stderr)
        return 1

    print(f"LOAD {args.catalog}", flush=True)
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    print("REFINE", flush=True)
    data = refine(catalog)
    c = data["counts"]
    gs = data["global_stats"]
    print(
        f"COUNTS A={c['A']} B={c['B']} C1={c['C1']} C2={c['C2']} "
        f"D={c['D']} D2={c['D2']} sum={data['total_n']}",
        flush=True,
    )
    print(
        f"TOTAL_GAP={gs['total_gap']} deepest={gs['deepest_gap']} "
        f"residual={gs['residual_sum']} net_top={gs['net_top']} "
        f"offset={gs['offset']}",
        flush=True,
    )
    st06 = data["by_cat"].get("06　结晶读经——2638篇")
    st100 = data["by_cat"].get("100　圣经中的人名与地名——1135篇")
    if st06:
        print(
            f"06 total={st06['total_gap']} residual={st06['residual_sum']}",
            flush=True,
        )
    if st100:
        print(f"100 total={st100['total_gap']}", flush=True)
    print(f"OFFSET_NEG={len(data['offset_negative'])}", flush=True)
    print("TOP5 total_gap:", flush=True)
    for cat, st in data["top15"][:5]:
        print(f"  {st['total_gap']:4d}  {cat}", flush=True)

    write_refine_report(args.report, data, args.catalog)
    if not args.skip_rename:
        write_rename_list(args.rename, data)
        print(f"WRITE {args.rename}", flush=True)
    else:
        print("SKIP rename list", flush=True)
    write_gaps_list(args.gaps, data)
    print(f"WRITE {args.report}", flush=True)
    print(f"WRITE {args.gaps}", flush=True)

    if not data["i4_ok"]:
        print("I4_FAIL", *data["i4_msgs"], flush=True)
        print("STOPPED", flush=True)
        return 2

    print("DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
