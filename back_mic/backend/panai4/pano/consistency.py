# -*- coding: utf-8 -*-
"""catalog_clean.json 一致性分类。

只读 catalog_clean.json（及必要时 tree 名以复现上一轮 P1–P4 声明）。
不碰源目录、不碰 ES。

用法（在 back_mic/backend 下）::

    python -m panai4.pano.consistency
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

CATALOG_DEFAULT = Path(r"G:\PanAI4.0专用\清明上河图目录\catalog_clean.json")
REPORT_DEFAULT = (
    Path(__file__).resolve().parents[4] / "docs" / "panai4_es" / "pano_consistency.md"
)

# 上一轮 enum_name_forms 的 P1–P4（仅「篇」）
_OLD_PATTERNS = [
    re.compile(r"^(\d+)[　\s]+(.*)——(\d+)篇$"),
    re.compile(r"^(\d+)[　\s]+(.*)[—–―](\d+)篇$"),
    re.compile(r"^(\d+)[　\s]+(.*)-(\d+)篇$"),
    re.compile(r"^(\d+)[　\s]+(.*)[　\s]+(\d+)篇$"),
]


def old_parse_declared(raw_name: str) -> int | None:
    for pat in _OLD_PATTERNS:
        m = pat.match(raw_name)
        if m:
            return int(m.group(3))
    return None


def count_mounts(node: dict) -> int:
    total = 0
    for c in node.get("children") or []:
        if c.get("type") == "message":
            total += 1
        elif c.get("type") == "dir":
            total += count_mounts(c)
    return total


def iter_dirs(node: dict):
    if node.get("type") == "dir" and (node.get("depth") or 0) > 0:
        yield node
    for c in node.get("children") or []:
        if c.get("type") == "dir":
            yield from iter_dirs(c)


def direct_child_dirs(node: dict) -> list[dict]:
    return [c for c in (node.get("children") or []) if c.get("type") == "dir"]


def analyze(catalog: dict) -> dict[str, Any]:
    dirs = list(iter_dirs(catalog))

    # ---- 预计算每个节点的挂载点数 ----
    mounts_map: dict[str, int] = {}
    for d in dirs:
        mounts_map[d["rel_path"]] = count_mounts(d)

    # ---- E1 父子声明一致性 ----
    e1_gt: list[dict] = []  # 子和 > 父
    e1_lt: list[dict] = []  # 子和 < 父 且差 > 10%
    e1_eq: list[dict] = []  # 子和 == 父
    e1_child_gt_parent: list[dict] = []  # 单个子声明 > 父声明
    # 仅统计：父有声明，且至少有一个带声明的直接子
    e1_parents_considered = 0

    typo_paths: set[str] = set()  # 子和>父 的父路径

    for d in dirs:
        parent_decl = d.get("declared_count")
        if parent_decl is None:
            continue
        children = direct_child_dirs(d)
        child_decls = [
            (c, c.get("declared_count"))
            for c in children
            if c.get("declared_count") is not None
        ]
        if not child_decls:
            continue
        e1_parents_considered += 1
        child_sum = sum(v for _, v in child_decls)
        row = {
            "path": d["rel_path"],
            "raw_name": d["raw_name"],
            "parent_declared": parent_decl,
            "child_sum": child_sum,
            "diff": child_sum - parent_decl,
            "n_declared_children": len(child_decls),
            "n_all_child_dirs": len(children),
            "actual": mounts_map[d["rel_path"]],
        }
        if child_sum > parent_decl:
            e1_gt.append(row)
            typo_paths.add(d["rel_path"])
        elif child_sum == parent_decl:
            e1_eq.append(row)
        else:
            # child_sum < parent
            gap = parent_decl - child_sum
            if gap > parent_decl * 0.10:
                e1_lt.append(row)

        for c, cd in child_decls:
            if cd is not None and cd > parent_decl:
                e1_child_gt_parent.append(
                    {
                        "parent_path": d["rel_path"],
                        "parent_declared": parent_decl,
                        "child_path": c["rel_path"],
                        "child_raw": c["raw_name"],
                        "child_declared": cd,
                        "over_by": cd - parent_decl,
                    }
                )

    e1_gt.sort(key=lambda r: (-r["diff"], r["path"]))
    e1_lt.sort(key=lambda r: (-r["diff"] if False else (r["parent_declared"] - r["child_sum"]), r["path"]))
    e1_lt.sort(key=lambda r: (-(r["parent_declared"] - r["child_sum"]), r["path"]))
    e1_eq.sort(key=lambda r: r["path"])
    e1_child_gt_parent.sort(key=lambda r: (-r["over_by"], r["child_path"]))

    # ---- E2 338 不相符归类 ----
    mismatches: list[dict] = []
    for d in dirs:
        decl = d.get("declared_count")
        if decl is None:
            continue
        actual = mounts_map[d["rel_path"]]
        if actual == decl:
            continue
        mismatches.append(
            {
                "path": d["rel_path"],
                "raw_name": d["raw_name"],
                "declared": decl,
                "actual": actual,
                "diff": actual - decl,
                "unit": d.get("count_unit"),
            }
        )

    assert len(mismatches) == 338, f"expected 338 mismatches, got {len(mismatches)}"

    buckets: dict[str, list[dict]] = {"D": [], "A": [], "B": [], "C": []}
    for m in mismatches:
        if m["path"] in typo_paths:
            buckets["D"].append(m)
        elif m["actual"] == 0 and m["declared"] > 0:
            buckets["A"].append(m)
        elif m["actual"] > m["declared"]:
            buckets["B"].append(m)
        elif m["actual"] < m["declared"] and m["actual"] > 0:
            buckets["C"].append(m)
        else:
            # 实际=0 且声明=0？不应出现于不相符；兜底进 C
            buckets["C"].append(m)

    def bucket_stats(items: list[dict]) -> dict:
        return {
            "n": len(items),
            "sum_declared": sum(x["declared"] for x in items),
            "sum_actual": sum(x["actual"] for x in items),
            "sum_diff": sum(x["diff"] for x in items),
        }

    for k in buckets:
        buckets[k].sort(key=lambda r: (-abs(r["diff"]), r["path"]))

    e2_stats = {k: bucket_stats(v) for k, v in buckets.items()}
    e2_total_n = sum(e2_stats[k]["n"] for k in ("A", "B", "C", "D"))

    # ---- E3 回归：上一轮 5057 ----
    old_nodes: list[dict] = []
    changed: list[dict] = []
    better = worse = same_dist = 0

    for d in dirs:
        old = old_parse_declared(d["raw_name"])
        if old is None:
            continue
        new = d.get("declared_count")
        actual = mounts_map[d["rel_path"]]
        old_nodes.append(d)
        if new != old:
            old_abs = abs(old - actual)
            new_abs = abs((new if new is not None else 0) - actual)
            # 若新值为 None，视为变坏（丢失声明）
            if new is None:
                verdict = "变坏"
                worse += 1
            elif new_abs < old_abs:
                verdict = "变好"
                better += 1
            elif new_abs > old_abs:
                verdict = "变坏"
                worse += 1
            else:
                verdict = "距离持平"
                same_dist += 1
            changed.append(
                {
                    "path": d["rel_path"],
                    "old": old,
                    "new": new,
                    "actual": actual,
                    "verdict": verdict,
                    "old_err": old - actual,
                    "new_err": (new - actual) if new is not None else None,
                }
            )

    changed.sort(key=lambda r: r["path"])
    n_old = len(old_nodes)

    # ---- E4 题/课 三支 ----
    def branch_stats(pred) -> dict:
        nodes = [d for d in dirs if pred(d)]
        mount_total = sum(mounts_map[d["rel_path"]] for d in nodes)
        # 只计「本支顶层之下」的挂载：不重复计祖先——用节点集合内「仅计 message 挂在这些节点直接下」不合适
        # 报告：节点数；这些节点作为挂载点父时的直接 message 数之和；以及递归去重挂载
        # 更干净：找出顶层支路径前缀，对该支根做一次 mounts
        return nodes

    ti_nodes = [d for d in dirs if d.get("count_unit") == "题"]
    ke_nodes = [d for d in dirs if d.get("count_unit") == "课"]
    # 三支：01 圣经要道（题）、95 全时间（课）、94 长老职分（课）
    branches = []
    for label, prefix_substr, unit in (
        ("01 圣经要道（题）", "01　圣经—神的话——382篇/4　　第四系列 圣经要道", "题"),
        ("95 全时间服事者（课）", "95　全时间服事者该有的进取——342篇", "课"),
        ("94 长老职分（课）", "94　在神新约经纶中的长老职分——193篇", "课"),
    ):
        # 支内：路径以此前缀开头，或自身是该前缀节点
        members = [
            d
            for d in dirs
            if d["rel_path"] == prefix_substr
            or d["rel_path"].startswith(prefix_substr + "/")
        ]
        # 题/课单位节点
        unit_members = [d for d in members if d.get("count_unit") == unit]
        # 支根挂载
        root = next((d for d in dirs if d["rel_path"] == prefix_substr), None)
        root_mounts = mounts_map.get(prefix_substr, 0) if root else 0
        # 直接挂 message 的叶子形态
        direct_msg_parents = 0
        only_msg_children = 0
        has_subdir = 0
        for d in members:
            kids = d.get("children") or []
            n_msg = sum(1 for c in kids if c.get("type") == "message")
            n_dir = sum(1 for c in kids if c.get("type") == "dir")
            if n_msg:
                direct_msg_parents += 1
            if n_msg and not n_dir:
                only_msg_children += 1
            if n_dir:
                has_subdir += 1
        # 样本 message title
        sample_titles = []
        for d in members:
            for c in d.get("children") or []:
                if c.get("type") == "message":
                    sample_titles.append(c.get("title", ""))
                    if len(sample_titles) >= 5:
                        break
            if len(sample_titles) >= 5:
                break
        branches.append(
            {
                "label": label,
                "prefix": prefix_substr,
                "unit": unit,
                "n_nodes": len(members),
                "n_unit_nodes": len(unit_members),
                "root_mounts": root_mounts,
                "direct_msg_parents": direct_msg_parents,
                "leaf_msg_only": only_msg_children,
                "has_subdir_nodes": has_subdir,
                "sample_titles": sample_titles,
                "unit_paths": [d["rel_path"] for d in unit_members],
            }
        )

    return {
        "n_dirs": len(dirs),
        "e1_parents_considered": e1_parents_considered,
        "e1_gt": e1_gt,
        "e1_lt": e1_lt,
        "e1_eq": e1_eq,
        "e1_child_gt_parent": e1_child_gt_parent,
        "mismatches_n": len(mismatches),
        "buckets": buckets,
        "e2_stats": e2_stats,
        "e2_total_n": e2_total_n,
        "n_old": n_old,
        "changed": changed,
        "better": better,
        "worse": worse,
        "same_dist": same_dist,
        "branches": branches,
        "ti_n": len(ti_nodes),
        "ke_n": len(ke_nodes),
    }


def write_report(path: Path, data: dict, catalog_path: Path) -> None:
    lines: list[str] = []
    w = lines.append

    w("# 清明上河图目录一致性分类报告")
    w("")
    w("只读 `catalog_clean.json`。不碰源目录、不碰 ES。")
    w("")
    w(f"- 输入：`{catalog_path}`")
    w("")

    # ---- E1 ----
    w("## E1　父子声明数一致性")
    w("")
    w(
        f"- 参与比较的父节点（有声明且至少一名直接子有声明）："
        f"{data['e1_parents_considered']}"
    )
    w(f"- 子和 > 父声明（笔误嫌疑）：**{len(data['e1_gt'])}**")
    w(f"- 子和 < 父声明且差 > 10%（父多声明）：**{len(data['e1_lt'])}**")
    w(f"- 子和 == 父声明（一致）：**{len(data['e1_eq'])}**")
    w(
        f"- 单个子声明 > 父声明：**{len(data['e1_child_gt_parent'])}**"
        "（完整列出）"
    )
    w("")

    w("### 子和 > 父声明（笔误嫌疑，完整列表）")
    w("")
    w("| 路径 | 父声明 | 子声明和 | 差(子-父) | 有声明子数/子目录数 | 实际挂载 |")
    w("|---|---:|---:|---:|---:|---:|")
    for r in data["e1_gt"]:
        w(
            f"| `{r['path']}` | {r['parent_declared']} | {r['child_sum']} | "
            f"{r['diff']:+d} | {r['n_declared_children']}/{r['n_all_child_dirs']} | "
            f"{r['actual']} |"
        )
    w("")

    w("### 子和 < 父声明且差 > 10%（父多声明，完整列表）")
    w("")
    w("| 路径 | 父声明 | 子声明和 | 差(父-子) | 有声明子数/子目录数 | 实际挂载 |")
    w("|---|---:|---:|---:|---:|---:|")
    for r in data["e1_lt"]:
        gap = r["parent_declared"] - r["child_sum"]
        w(
            f"| `{r['path']}` | {r['parent_declared']} | {r['child_sum']} | "
            f"{gap:+d} | {r['n_declared_children']}/{r['n_all_child_dirs']} | "
            f"{r['actual']} |"
        )
    w("")

    w("### 子和 == 父声明（一致，完整列表）")
    w("")
    w("| 路径 | 声明 | 有声明子数/子目录数 | 实际挂载 |")
    w("|---|---:|---:|---:|")
    for r in data["e1_eq"]:
        w(
            f"| `{r['path']}` | {r['parent_declared']} | "
            f"{r['n_declared_children']}/{r['n_all_child_dirs']} | {r['actual']} |"
        )
    w("")

    w("### 单个子声明 > 父声明（完整列表）")
    w("")
    w("| 父路径 | 父声明 | 子路径 | 子 raw | 子声明 | 超出 |")
    w("|---|---:|---|---|---:|---:|")
    for r in data["e1_child_gt_parent"]:
        w(
            f"| `{r['parent_path']}` | {r['parent_declared']} | "
            f"`{r['child_path']}` | `{r['child_raw']}` | "
            f"{r['child_declared']} | {r['over_by']:+d} |"
        )
    w("")

    # ---- E2 ----
    w("## E2　338 条不相符归类（D 优先于 A~C）")
    w("")
    w(f"- 不相符总数：{data['mismatches_n']}")
    w(
        f"- A+B+C+D 条数之和：{data['e2_total_n']}"
        f"{'（=338）' if data['e2_total_n'] == 338 else '（≠338，有问题）'}"
    )
    w("")
    w("| 类 | 含义 | 条数 | 声明总和 | 实际总和 | 差值总和(实际-声明) |")
    w("|---|---|---:|---:|---:|---:|")
    labels = {
        "D": "目录笔误（同时命中 E1 子和>父）",
        "A": "内容缺口（实际=0 且声明>0）",
        "B": "增补未回改（实际>声明）",
        "C": "部分缺失（0<实际<声明）",
    }
    for k in ("D", "A", "B", "C"):
        s = data["e2_stats"][k]
        w(
            f"| {k} | {labels[k]} | {s['n']} | {s['sum_declared']} | "
            f"{s['sum_actual']} | {s['sum_diff']:+d} |"
        )
    w("")

    for k in ("D", "A", "B", "C"):
        items = data["buckets"][k]
        w(f"### {k}　{labels[k]}（{len(items)}，完整列表）")
        w("")
        w("| 路径 | 声明 | 实际 | 差 | unit |")
        w("|---|---:|---:|---:|---|")
        for r in items:
            w(
                f"| `{r['path']}` | {r['declared']} | {r['actual']} | "
                f"{r['diff']:+d} | {r['unit'] or ''} |"
            )
        w("")

    # ---- E3 ----
    w("## E3　回归检查（上一轮 P1–P4 的 5057 节点）")
    w("")
    w(f"- 上一轮规则能解析出声明的节点数：**{data['n_old']}**")
    w(f"- 其中本轮 `declared_count` 发生变化：**{len(data['changed'])}**")
    w(
        f"- 变化之中：变好 {data['better']}，变坏 {data['worse']}，"
        f"误差距离持平 {data['same_dist']}"
    )
    w("")
    w("> 变好/变坏：相对挂载点实际值，|新声明−实际| 与 |旧声明−实际| 比较。")
    w("")
    if not data["changed"]:
        w("无变化。新规则未改动任何老条目的 `declared_count`。")
    else:
        w("### declared_count 变化的完整列表")
        w("")
        w("| 路径 | 旧值 | 新值 | 实际 | 判定 |")
        w("|---|---:|---:|---:|---|")
        for r in data["changed"]:
            w(
                f"| `{r['path']}` | {r['old']} | {r['new']} | "
                f"{r['actual']} | {r['verdict']} |"
            )
    w("")

    # ---- E4 ----
    w("## E4　「题」「课」三支")
    w("")
    w(f"- 全局 count_unit=题 节点：{data['ti_n']}；=课 节点：{data['ke_n']}")
    w("")
    for b in data["branches"]:
        w(f"### {b['label']}")
        w("")
        w(f"- 支前缀：`{b['prefix']}`")
        w(f"- 支内文件夹节点数：{b['n_nodes']}")
        w(f"- 其中 unit={b['unit']} 的节点数：{b['n_unit_nodes']}")
        w(f"- 支根递归挂载点数：{b['root_mounts']}")
        w(f"- 直接含 message 的节点：{b['direct_msg_parents']}")
        w(f"- 仅含 message、无子目录的叶子：{b['leaf_msg_only']}")
        w(f"- 含子目录的节点：{b['has_subdir_nodes']}")
        w("- 样本篇题：")
        for t in b["sample_titles"]:
            w(f"  - {t}")
        w("- unit 节点路径：")
        for p in b["unit_paths"]:
            w(f"  - `{p}`")
        # 形态结论
        if b["unit"] == "题":
            morph = (
                "与多数「篇」大类相同：层级文件夹 + `msg. N 标题` 挂载；"
                "差别主要在计数单位用「题」而非「篇」。"
            )
        else:
            morph = (
                "与多数「篇」大类相同的目录/msg 结构；"
                "计数单位为「课」，内容多为课程单元而非篇题讲道。"
            )
        w(f"- 形态判断：{morph}")
        w("")

    # ---- 验证三问 ----
    w("## 验证三问")
    w("")
    n_child_gt = len(data["e1_child_gt_parent"])
    n_sum = data["e2_total_n"]
    d_n = data["e2_stats"]["D"]["n"]
    a_n = data["e2_stats"]["A"]["n"]
    b_n = data["e2_stats"]["B"]["n"]
    c_n = data["e2_stats"]["C"]["n"]
    n_changed = len(data["changed"])
    n_old = data["n_old"]
    sum_note = " = 338" if n_sum == 338 else f" ≠ 338（差 {n_sum - 338:+d}）"
    old_note = "（=5057）" if n_old == 5057 else f"（≠5057，实为 {n_old}）"
    w(
        f"1. **「子声明 > 父声明」的节点**：{n_child_gt} 个，"
        "上文「单个子声明 > 父声明」表已全部列出。"
    )
    w(
        f"2. **A+B+C+D 条数之和**：{n_sum}{sum_note}"
        f"（D={d_n}, A={a_n}, B={b_n}, C={c_n}）"
    )
    w(
        f"3. **E3 declared_count 变化**：{n_changed} 个"
        f"（变好 {data['better']} / 变坏 {data['worse']} / 距离持平 {data['same_dist']}）；"
        f"上一轮参与节点复现数 {n_old}{old_note}。"
    )
    w("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="catalog_clean 一致性分类")
    parser.add_argument("--catalog", type=Path, default=CATALOG_DEFAULT)
    parser.add_argument("--report", type=Path, default=REPORT_DEFAULT)
    args = parser.parse_args(argv)

    if not args.catalog.is_file():
        print(f"ERROR catalog not found: {args.catalog}", file=sys.stderr)
        return 1

    print(f"LOAD {args.catalog}", flush=True)
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    print("ANALYZE", flush=True)
    data = analyze(catalog)
    print(
        f"E1 gt={len(data['e1_gt'])} lt={len(data['e1_lt'])} eq={len(data['e1_eq'])} "
        f"child_gt={len(data['e1_child_gt_parent'])}",
        flush=True,
    )
    print(
        f"E2 D={data['e2_stats']['D']['n']} A={data['e2_stats']['A']['n']} "
        f"B={data['e2_stats']['B']['n']} C={data['e2_stats']['C']['n']} "
        f"sum={data['e2_total_n']}",
        flush=True,
    )
    print(
        f"E3 old={data['n_old']} changed={len(data['changed'])} "
        f"better={data['better']} worse={data['worse']}",
        flush=True,
    )
    print(f"WRITE {args.report}", flush=True)
    write_report(args.report, data, args.catalog)
    print("DONE", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
