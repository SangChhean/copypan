# -*- coding: utf-8 -*-
"""清明上河图目录名 / 文件名解析，并产出清洗层级 JSON。

只读 tree.json。不碰源目录、不碰 ES、不向量。

用法（在 back_mic/backend 下）::

    python -m panai4.pano.parse_names
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

TREE_DEFAULT = Path(r"G:\PanAI4.0专用\清明上河图目录\tree.json")
OUT_JSON_DEFAULT = Path(r"G:\PanAI4.0专用\清明上河图目录\catalog_clean.json")
REPORT_DEFAULT = (
    Path(__file__).resolve().parents[4] / "docs" / "panai4_es" / "pano_clean_report.md"
)

EXPECT_SOURCE_VERSIONS = 29711
PREV_RATE_B = 94.32

# ---------------------------------------------------------------------------
# 数字转换
# ---------------------------------------------------------------------------

_FW_TO_HW = str.maketrans("０１２３４５６７８９", "0123456789")

_CN_SIMPLE = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "壹": 1,
    "贰": 2,
    "叁": 3,
    "肆": 4,
    "伍": 5,
    "陆": 6,
    "柒": 7,
    "捌": 8,
    "玖": 9,
    "拾": 10,
}


def fw_digits_to_int(s: str) -> int:
    return int(s.translate(_FW_TO_HW))


def cn_ordinal_to_int(s: str) -> int | None:
    """中文 / 大写中文数字 → int；转不了返回 None。"""
    if not s:
        return None
    if s in _CN_SIMPLE:
        return _CN_SIMPLE[s]
    # 十一..十九
    if len(s) == 2 and s[0] == "十" and s[1] in _CN_SIMPLE and _CN_SIMPLE[s[1]] < 10:
        return 10 + _CN_SIMPLE[s[1]]
    if len(s) == 2 and s[0] == "拾" and s[1] in _CN_SIMPLE and _CN_SIMPLE[s[1]] < 10:
        return 10 + _CN_SIMPLE[s[1]]
    # 二十 / 廿? 二〇 等：二十、二十一
    if "十" in s or "拾" in s:
        sep = "十" if "十" in s else "拾"
        parts = s.split(sep, 1)
        if len(parts) == 2:
            left, right = parts
            tens = _CN_SIMPLE.get(left, None) if left else 1
            ones = _CN_SIMPLE.get(right, 0) if right else 0
            if tens is not None and ones is not None and ones < 10:
                return tens * 10 + ones
    return None


# ---------------------------------------------------------------------------
# D1 文件夹：从右向左剥
# ---------------------------------------------------------------------------

# 括注：右端成对括号（不含再嵌套括号）
_ANNOT_RIGHT = re.compile(r"(\s*)([（(])([^（）()]*)([）)])(\s*)$")

# 计数：右端
_COUNT_RIGHT = re.compile(
    r"([-—–―　\s]*)([0-9０-９]+)(\s*)([篇题课])(\s*)$"
)

# 序号：左端（阿拉伯/全角数字 / 小写中文数字 / 大写中文数字）+ 空白
_ORD_ARABIC = re.compile(r"^([0-9０-９]+)([　 \t]+)(.*)$", re.DOTALL)
_ORD_CN = re.compile(
    r"^([一二三四五六七八九十]+)([　 \t]+)(.*)$",
    re.DOTALL,
)
_ORD_CN_UPPER = re.compile(
    r"^([壹贰叁肆伍陆柒捌玖拾]+)([　 \t]+)(.*)$",
    re.DOTALL,
)


def parse_folder_name(raw_name: str) -> dict[str, Any]:
    """从右向左剥文件夹名。返回解析字段 + 反拼所需分隔符。"""
    s = raw_name

    # --- 第1步：括注（从右反复剥；最终 annotations 按原文出现顺序 = 剥取逆序）---
    annot_chunks: list[dict[str, str]] = []  # 供反拼，右→左剥取顺序
    while True:
        m = _ANNOT_RIGHT.search(s)
        if not m:
            break
        lead_ws, open_b, text, close_b, trail_ws = m.groups()
        annot_chunks.append(
            {
                "lead_ws": lead_ws,
                "open": open_b,
                "text": text,
                "close": close_b,
                "trail_ws": trail_ws,
            }
        )
        s = s[: m.start()]

    annotations = [c["text"] for c in reversed(annot_chunks)]

    # --- 第2步：计数 ---
    count_sep = ""
    count_digits_raw = ""
    count_mid_ws = ""
    count_unit: str | None = None
    count_trail_ws = ""
    declared_count: int | None = None

    m = _COUNT_RIGHT.search(s)
    if m:
        count_sep, count_digits_raw, count_mid_ws, count_unit, count_trail_ws = m.groups()
        declared_count = fw_digits_to_int(count_digits_raw)
        s = s[: m.start()]

    # --- 第3步：序号（「第N系列/辑」不算 —— 左端是「第」时不剥）---
    ordinal_raw: str | None = None
    ordinal_num: int | None = None
    ordinal_sep = ""

    if not s.startswith("第"):
        for pat, kind in (
            (_ORD_ARABIC, "arabic"),
            (_ORD_CN_UPPER, "cn_upper"),
            (_ORD_CN, "cn"),
        ):
            m = pat.match(s)
            if not m:
                continue
            ordinal_raw, ordinal_sep, rest = m.groups()
            if kind == "arabic":
                ordinal_num = fw_digits_to_int(ordinal_raw)
            else:
                ordinal_num = cn_ordinal_to_int(ordinal_raw)
            s = rest
            break

    # --- 第4步：剩余 ---
    name_lead_ws = s[: len(s) - len(s.lstrip(" 　\t"))] if s else ""
    name_trail_ws = s[len(s.rstrip(" 　\t")) :] if s else ""
    name = s.strip(" 　\t")

    return {
        "raw_name": raw_name,
        "ordinal_raw": ordinal_raw,
        "ordinal_num": ordinal_num,
        "name": name,
        "declared_count": declared_count,
        "count_unit": count_unit,
        "annotations": annotations,
        # 反拼私货（写入 catalog 前可剔除，验证时保留）
        "_recon": {
            "ordinal_sep": ordinal_sep,
            "name_lead_ws": name_lead_ws,
            "name_trail_ws": name_trail_ws,
            "count_sep": count_sep,
            "count_digits_raw": count_digits_raw,
            "count_mid_ws": count_mid_ws,
            "count_trail_ws": count_trail_ws,
            "annot_chunks": annot_chunks,  # 右→左
        },
    }


def reconstruct_folder_name(parsed: dict[str, Any]) -> str:
    r = parsed["_recon"]
    parts: list[str] = []
    if parsed["ordinal_raw"] is not None:
        parts.append(parsed["ordinal_raw"])
        parts.append(r["ordinal_sep"])
    parts.append(r["name_lead_ws"])
    parts.append(parsed["name"])
    parts.append(r["name_trail_ws"])
    if parsed["count_unit"] is not None:
        parts.append(r["count_sep"])
        parts.append(r["count_digits_raw"])
        parts.append(r["count_mid_ws"])
        parts.append(parsed["count_unit"])
        parts.append(r["count_trail_ws"])
    # annot_chunks 是右→左剥取，反拼时按剥取逆序（即再 reverse）接到末尾
    # 剥取时每次从当前串右端取走，故 chunks[0] 是原文最右侧；反拼应先拼左侧 annot
    for c in reversed(r["annot_chunks"]):
        parts.append(c["lead_ws"])
        parts.append(c["open"])
        parts.append(c["text"])
        parts.append(c["close"])
        parts.append(c["trail_ws"])
    return "".join(parts)


def roundtrip_ok(raw_name: str) -> tuple[bool, str, dict[str, Any]]:
    parsed = parse_folder_name(raw_name)
    rebuilt = reconstruct_folder_name(parsed)
    return rebuilt == raw_name, rebuilt, parsed


# ---------------------------------------------------------------------------
# D2 docx
# ---------------------------------------------------------------------------

_FORMATTED_PREFIX = re.compile(r"^Formatted\s+", re.IGNORECASE)
_MSG = re.compile(r"^msg\.\s*(\d+)\s*(.+)$", re.IGNORECASE)
# 四种括号变体 + 可选前后空白
_CHUCHU = re.compile(
    r"(\s*)([（(])\s*纲目带出处\s*([）)])\s*$"
)
_CHUCHU_EXPECT = EXPECT_SOURCE_VERSIONS


def parse_docx_filename(raw_filename: str) -> dict[str, Any]:
    raw = raw_filename
    ext = ""
    stem = raw
    if "." in raw:
        # 只剥最后扩展名
        dot = raw.rfind(".")
        ext = raw[dot + 1 :]
        stem = raw[:dot]

    stripped_formatted = False
    m_fmt = _FORMATTED_PREFIX.match(stem)
    if m_fmt:
        stem = stem[m_fmt.end() :]
        stripped_formatted = True

    msg_number: int | None = None
    title = stem
    msg_matched = False
    had_space_after_num = False
    no_space_after_num = False

    m = _MSG.match(stem)
    if m:
        msg_matched = True
        msg_number = int(m.group(1))
        title = m.group(2)
        # 检测原串数字后是否有空白（用于报告「无空格修正」）
        m2 = re.match(r"^msg\.\s*(\d+)(\s*)(.*)$", stem, re.IGNORECASE)
        if m2:
            if m2.group(2) == "":
                no_space_after_num = True
            else:
                had_space_after_num = True

    has_source_version = False
    m_cc = _CHUCHU.search(title)
    if m_cc:
        has_source_version = True
        title = title[: m_cc.start()].rstrip(" 　\t")

    return {
        "raw_filename": raw_filename,
        "msg_number": msg_number,
        "title": title,
        "has_source_version": has_source_version,
        "ext": ext,
        "_meta": {
            "stripped_formatted": stripped_formatted,
            "msg_matched": msg_matched,
            "no_space_after_num": no_space_after_num,
            "had_space_after_num": had_space_after_num,
        },
    }


# ---------------------------------------------------------------------------
# 树 → catalog
# ---------------------------------------------------------------------------


def _role(has_subdir: bool, has_docx: bool, has_declared_count: bool) -> dict[str, bool]:
    return {
        "has_subdir": has_subdir,
        "has_docx": has_docx,
        "has_declared_count": has_declared_count,
    }


def _merge_messages(docx_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同一父下按 (msg_number, title) 归并；不跨父。"""
    groups: dict[tuple[Any, str], dict[str, Any]] = {}
    order: list[tuple[Any, str]] = []
    for d in docx_nodes:
        key = (d["msg_number"], d["title"])
        if key not in groups:
            groups[key] = {
                "type": "message",
                "msg_number": d["msg_number"],
                "title": d["title"],
                "has_source_version": bool(d["has_source_version"]),
                "raw_filenames": [d["raw_filename"]],
                "ext": d["ext"],
            }
            order.append(key)
        else:
            g = groups[key]
            g["has_source_version"] = g["has_source_version"] or bool(d["has_source_version"])
            g["raw_filenames"].append(d["raw_filename"])
    return [groups[k] for k in order]


def build_catalog(tree: dict) -> tuple[dict, dict]:
    """返回 (catalog_root, stats)。"""
    stats: dict[str, Any] = {
        "recon_failures": [],  # {raw_name, rel_path, rebuilt}
        "n_dirs": 0,
        "n_docx": 0,
        "n_source_versions": 0,
        "n_formatted": 0,
        "n_no_space_msg": 0,
        "n_msg_matched": 0,
        "count_unit_folders": {"篇": [], "题": [], "课": []},
        "role_counts": Counter(),
        "role_samples": defaultdict(list),
        "empty_declared": [],  # rel_path
        "mixed_nodes": [],
        "mount_points": 0,
        "check_n": 0,
        "match_b": 0,
        "mismatch_b": [],
        "by_depth": defaultdict(lambda: {"n": 0, "match_b": 0}),
    }

    def convert(node: dict, is_root: bool = False) -> dict:
        if node.get("type") == "docx":
            raise RuntimeError("docx should be handled by parent")

        children = node.get("children") or []
        subdir_raw = [c for c in children if c.get("type") == "dir"]
        docx_raw = [c for c in children if c.get("type") == "docx"]

        out_children: list[dict] = []
        # 子文件夹
        for sd in subdir_raw:
            out_children.append(convert(sd, is_root=False))

        # docx → 解析 → 归并
        parsed_docs = []
        for d in docx_raw:
            stats["n_docx"] += 1
            pd = parse_docx_filename(d["name"])
            if pd["has_source_version"]:
                stats["n_source_versions"] += 1
            meta = pd["_meta"]
            if meta["stripped_formatted"]:
                stats["n_formatted"] += 1
            if meta["msg_matched"]:
                stats["n_msg_matched"] += 1
            if meta["no_space_after_num"]:
                stats["n_no_space_msg"] += 1
            clean_doc = {k: v for k, v in pd.items() if k != "_meta"}
            # 挂 depth / rel_path
            clean_doc["depth"] = d.get("depth")
            clean_doc["rel_path"] = d.get("rel_path")
            parsed_docs.append(clean_doc)

        merged = _merge_messages(parsed_docs)
        stats["mount_points"] += len(merged)
        out_children.extend(merged)

        has_subdir = any(c.get("type") == "dir" for c in out_children)
        has_docx = any(c.get("type") == "message" for c in out_children)

        if is_root:
            out = {
                "type": "dir",
                "raw_name": node["name"],
                "ordinal_raw": None,
                "ordinal_num": None,
                "name": node["name"],
                "declared_count": None,
                "count_unit": None,
                "annotations": [],
                "depth": node.get("depth", 0),
                "rel_path": node.get("rel_path", ""),
                "role": _role(has_subdir, has_docx, False),
                "children": out_children,
            }
            return out

        stats["n_dirs"] += 1
        ok, rebuilt, parsed = roundtrip_ok(node["name"])
        if not ok:
            stats["recon_failures"].append(
                {
                    "raw_name": node["name"],
                    "rel_path": node.get("rel_path", ""),
                    "rebuilt": rebuilt,
                }
            )

        has_declared = parsed["declared_count"] is not None
        role = _role(has_subdir, has_docx, has_declared)
        role_key = (role["has_subdir"], role["has_docx"], role["has_declared_count"])
        stats["role_counts"][role_key] += 1
        if len(stats["role_samples"][role_key]) < 3:
            stats["role_samples"][role_key].append(node.get("rel_path", ""))

        if has_subdir and has_docx:
            stats["mixed_nodes"].append(node.get("rel_path", ""))
        if has_declared and (not has_subdir) and (not has_docx):
            stats["empty_declared"].append(
                {
                    "rel_path": node.get("rel_path", ""),
                    "raw_name": node["name"],
                    "declared_count": parsed["declared_count"],
                    "count_unit": parsed["count_unit"],
                }
            )

        unit = parsed["count_unit"]
        if unit in stats["count_unit_folders"]:
            stats["count_unit_folders"][unit].append(node.get("rel_path", ""))

        # 口径 B：声明 vs 归并后挂载点数（每挂载点一篇，已去重出处版）
        if has_declared:
            # 递归统计本节点下全部 message 挂载点
            def count_mounts(n: dict) -> int:
                total = 0
                for c in n.get("children") or []:
                    if c.get("type") == "message":
                        total += 1
                    elif c.get("type") == "dir":
                        total += count_mounts(c)
                return total

            # 先构造节点再数——下面 out 尚未建，用 out_children
            tmp = {"children": out_children}
            mounts = count_mounts(tmp)
            declared = parsed["declared_count"]
            depth = node.get("depth", -1)
            stats["check_n"] += 1
            stats["by_depth"][depth]["n"] += 1
            if declared == mounts:
                stats["match_b"] += 1
                stats["by_depth"][depth]["match_b"] += 1
            else:
                stats["mismatch_b"].append(
                    {
                        "path": node.get("rel_path", ""),
                        "declared": declared,
                        "actual": mounts,
                        "diff": mounts - declared,
                        "abs": abs(mounts - declared),
                    }
                )

        out = {
            "type": "dir",
            "raw_name": parsed["raw_name"],
            "ordinal_raw": parsed["ordinal_raw"],
            "ordinal_num": parsed["ordinal_num"],
            "name": parsed["name"],
            "declared_count": parsed["declared_count"],
            "count_unit": parsed["count_unit"],
            "annotations": parsed["annotations"],
            "depth": node.get("depth"),
            "rel_path": node.get("rel_path"),
            "role": role,
            "children": out_children,
        }
        return out

    catalog = convert(tree, is_root=True)
    stats["mixed_nodes"].sort()
    stats["mismatch_b"].sort(key=lambda r: (-r["abs"], r["path"]))
    stats["empty_declared"].sort(key=lambda r: r["rel_path"])
    return catalog, stats


def write_report(path: Path, stats: dict, catalog_path: Path, tree_path: Path) -> None:
    lines: list[str] = []
    w = lines.append

    rate_b = (
        stats["match_b"] / stats["check_n"] * 100 if stats["check_n"] else 0.0
    )
    delta = rate_b - PREV_RATE_B

    w("# 清明上河图目录清洗报告")
    w("")
    w("只读 `tree.json`。不碰源目录、不碰 ES、不向量。")
    w("")
    w(f"- 输入：`{tree_path}`")
    w(f"- 产出：`{catalog_path}`")
    w(f"- 文件夹数（不含根）：{stats['n_dirs']}")
    w(f"- docx 数：{stats['n_docx']}")
    w("")

    # D1
    w("## D1　硬验证（反拼还原）")
    w("")
    w(f"- 不能还原条数：**{len(stats['recon_failures'])}**")
    w("")
    if not stats["recon_failures"]:
        w("全部文件夹名均可按原分隔符反拼还原。")
    else:
        w("### 不能还原的完整清单（不许省略）")
        w("")
        for row in stats["recon_failures"]:
            w(f"- raw: `{row['raw_name']}`")
            w(f"  - path: `{row['rel_path']}`")
            w(f"  - rebuilt: `{row['rebuilt']}`")
    w("")

    # D2
    w("## D2　docx 解析")
    w("")
    w(f"- 带出处识别数：**{stats['n_source_versions']}**（目标 {EXPECT_SOURCE_VERSIONS}）")
    if stats["n_source_versions"] != EXPECT_SOURCE_VERSIONS:
        w(
            f"- **未达目标**：差 {stats['n_source_versions'] - EXPECT_SOURCE_VERSIONS:+d}。"
            "按任务要求应停下报告。"
        )
    else:
        w("- 与目标 29711 **一致**。")
    w(f"- Formatted 前缀剥除数：{stats['n_formatted']}")
    w(f"- msg 匹配成功数：{stats['n_msg_matched']}")
    w(f"- msg 数字与标题之间无空格（靠 `\\s*` 修正）数：{stats['n_no_space_msg']}")
    w("")

    # count_unit 题/课
    w("## 计数单位「题」「课」")
    w("")
    for unit in ("题", "课"):
        paths = stats["count_unit_folders"][unit]
        # 顶层支（第一段）
        tops = Counter()
        for p in paths:
            tops[p.split("/")[0] if p else ""] += 1
        w(f"### {unit}（{len(paths)}）")
        w("")
        w("所在顶层支：")
        w("")
        for top, n in sorted(tops.items(), key=lambda x: (-x[1], x[0])):
            w(f"- `{top}` × {n}")
        w("")
        w("全部路径：")
        w("")
        for p in paths:
            w(f"- `{p}`")
        w("")

    # D3 roles
    w("## D3　role 八表")
    w("")
    w("| has_subdir | has_docx | has_declared_count | 数量 | 样本（≤3） |")
    w("|:---:|:---:|:---:|---:|---|")
    for key in sorted(stats["role_counts"].keys(), reverse=True):
        hs, hd, hc = key
        n = stats["role_counts"][key]
        samples = " <br> ".join(f"`{p}`" for p in stats["role_samples"][key][:3])
        w(f"| {hs} | {hd} | {hc} | {n} | {samples or '—'} |")
    w("")
    w(f"- role 组合种数：{len(stats['role_counts'])}")
    w("")

    w(f"### 声明了计数但完全为空（{len(stats['empty_declared'])}）")
    w("")
    w(
        "> 上一轮按 P1–P4 分桶时此项为 8；本轮右剥解析能认出更多计数"
        f"（含「课」、括注后缀、全角序号等），故为 {len(stats['empty_declared'])}。"
        "仍是内容缺口，只列不删。"
    )
    w("")
    w("| 路径 | raw_name | declared_count | unit |")
    w("|---|---|---:|---|")
    for row in stats["empty_declared"]:
        w(
            f"| `{row['rel_path']}` | `{row['raw_name']}` | "
            f"{row['declared_count']} | {row['count_unit']} |"
        )
    w("")

    w(f"### 混合节点（{len(stats['mixed_nodes'])}）")
    w("")
    for p in stats["mixed_nodes"]:
        w(f"- `{p}`")
    w("")

    # D4 / D5 校验
    w("## D4 / D5　归并与口径 B 校验")
    w("")
    w(f"- 归并后「篇-分类挂载点」总数：**{stats['mount_points']}**")
    w(
        f"- 口径 B（声明 vs 挂载点数）相符：**{stats['match_b']}** / {stats['check_n']}"
        f" = **{rate_b:.2f}%**"
    )
    w(
        f"- 相对上一轮 94.32%：{delta:+.2f} pp"
        f"（{'升' if delta > 0 else '降' if delta < 0 else '持平'}）"
    )
    w("")
    w("### 按深度分组")
    w("")
    w("| depth | 参与数 | 相符 | 相符率 |")
    w("|---:|---:|---:|---:|")
    for d in sorted(stats["by_depth"].keys()):
        bd = stats["by_depth"][d]
        r = bd["match_b"] / bd["n"] * 100 if bd["n"] else 0
        w(f"| {d} | {bd['n']} | {bd['match_b']} | {r:.2f}% |")
    w("")
    w("### 不相符 Top 50")
    w("")
    w("| 路径 | 声明 | 实际(挂载点) | 差 |")
    w("|---|---:|---:|---:|")
    for row in stats["mismatch_b"][:50]:
        w(f"| `{row['path']}` | {row['declared']} | {row['actual']} | {row['diff']:+d} |")
    w("")

    # 验证三问
    w("## 验证三问")
    w("")
    w(f"1. **反拼还原失败**：{len(stats['recon_failures'])} 条")
    w(
        f"2. **带出处 docx 识别数**：{stats['n_source_versions']}"
        f"{'（=29711）' if stats['n_source_versions'] == EXPECT_SOURCE_VERSIONS else '（≠29711）'}"
    )
    w(
        f"3. **挂载点总数** {stats['mount_points']}；口径 B 相符率 {rate_b:.2f}%"
        f"（上一轮 94.32%，本轮{'升' if delta > 0 else '降' if delta < 0 else '持平'} "
        f"{delta:+.2f} pp）"
    )
    w("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="解析并清洗清明上河图目录层级")
    parser.add_argument("--tree", type=Path, default=TREE_DEFAULT)
    parser.add_argument("--out", type=Path, default=OUT_JSON_DEFAULT)
    parser.add_argument("--report", type=Path, default=REPORT_DEFAULT)
    args = parser.parse_args(argv)

    if not args.tree.is_file():
        print(f"ERROR tree not found: {args.tree}", file=sys.stderr)
        return 1

    print(f"LOAD {args.tree}", flush=True)
    tree = json.loads(args.tree.read_text(encoding="utf-8"))

    print("BUILD catalog", flush=True)
    catalog, stats = build_catalog(tree)

    n_fail = len(stats["recon_failures"])
    n_cc = stats["n_source_versions"]
    print(
        f"RECON_FAIL {n_fail} SOURCE_VER {n_cc} "
        f"MOUNTS {stats['mount_points']} "
        f"RATE_B {stats['match_b']}/{stats['check_n']}",
        flush=True,
    )

    if n_cc != EXPECT_SOURCE_VERSIONS:
        print(
            f"STOP: source_version count {n_cc} != {EXPECT_SOURCE_VERSIONS}",
            flush=True,
        )
        # 仍写报告便于排查；不写 catalog
        write_report(args.report, stats, args.out, args.tree)
        print(f"WRITE report only {args.report}", flush=True)
        return 2

    print(f"WRITE {args.out}", flush=True)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(catalog, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"WRITE {args.report}", flush=True)
    write_report(args.report, stats, args.out, args.tree)

    print("DONE", flush=True)
    return 0 if n_fail == 0 else 0  # 失败清单写入报告；不因失败中断产出


if __name__ == "__main__":
    raise SystemExit(main())
