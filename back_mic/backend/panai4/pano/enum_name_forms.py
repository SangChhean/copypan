# -*- coding: utf-8 -*-
"""穷举清明上河图目录名 / 文件名形态，并做角色与篇数校验。

只读 tree.json。不碰源目录、不碰 ES、不向量、不建索引、不产出清洗 JSON。

用法（在 back_mic/backend 下）::

    python -m panai4.pano.enum_name_forms
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

TREE_DEFAULT = Path(r"G:\PanAI4.0专用\清明上河图目录\tree.json")
REPORT_DEFAULT = (
    Path(__file__).resolve().parents[4] / "docs" / "panai4_es" / "pano_name_forms.md"
)

# --- 文件夹候选模式（命中即归桶，按序） ---
# P2 单破折号：— U+2014 / – U+2013 / ― U+2015
P_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("P1", re.compile(r"^(\d+)[　\s]+(.*)——(\d+)篇$")),
    ("P2", re.compile(r"^(\d+)[　\s]+(.*)[—–―](\d+)篇$")),
    ("P3", re.compile(r"^(\d+)[　\s]+(.*)-(\d+)篇$")),
    ("P4", re.compile(r"^(\d+)[　\s]+(.*)[　\s]+(\d+)篇$")),
    ("P5", re.compile(r"^(\d+)[　\s]+(.+)$")),
]

Q1 = re.compile(r"^msg\.\s*(\d+)\s+(.+)$", re.IGNORECASE)

# 全角数字
FW_DIGIT_RE = re.compile(r"[０-９]")
# 半角/全角数字开头以便拆分隔符
LEADING_NUM_RE = re.compile(r"^([0-9０-９]+)([　 \t]+)(.*)$")

# 中文 / 圈号 / 全角字母序号（出现在名称前部时计入字符全集）
# 不含地支（避免「自己」「未」等误入）
CN_ORDINAL_CHARS = set(
    "零壹贰叁肆伍陆柒捌玖拾佰仟万一二三四五六七八九十百千两〇"
    "甲乙丙丁戊己庚辛壬癸"
)
FW_LETTER_CHARS = set(
    "ａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ"
    "ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺ"
)
# （一）类：全角/半角括号 + 中文数字
PAREN_ORDINAL_RE = re.compile(
    r"[（(]([一二三四五六七八九十百千零〇两]+|[0-9０-９]+|[ａ-ｚａｂｃ]|[a-zA-Z])[)）]"
)
# 名称开头常见「壹　」「一　」「（一）」前缀探测
LEADING_ORDINAL_RE = re.compile(
    r"^(?:"
    r"[（(][一二三四五六七八九十百千零〇两0-9０-９ａ-ｚa-zA-Z]+[)）]"
    r"|[壹贰叁肆伍陆柒捌玖拾佰仟]"
    r"|[一二三四五六七八九十]"
    r"|[ａ-ｚＡ-Ｚa-zA-Z]"
    r")"
)

# 括注含年月/地点的粗判
ANNOT_RE = re.compile(
    r"[（(][^）)]*(?:年|月|日|美国|台湾|台北|香港|日本|韩国|欧洲|加州|安那翰|"
    r"安纳翰|伦敦|巴黎|莫斯科|马尼拉|印尼|新加坡|马来|菲律宾|澳洲|纽西兰|"
    r"首尔|东京|大阪|京都|旧金山|洛杉矶|西雅图|波士顿|纽约|芝加哥|"
    r"冬季|夏季|秋|春|训|特会|训练|聚会)[^）)]*[)）]"
)

CHUCHU_MARK = "纲目带出处"


def walk_collect(tree: dict) -> tuple[list[dict], list[dict]]:
    """收集全部 dir（不含根）与全部 docx 节点，并附 parent 直属子统计所需字段。"""
    dirs: list[dict] = []
    docs: list[dict] = []

    def rec(node: dict) -> None:
        children = node.get("children") or []
        subdirs = [c for c in children if c.get("type") == "dir"]
        docxs = [c for c in children if c.get("type") == "docx"]
        node["_has_subdir"] = bool(subdirs)
        node["_has_docx"] = bool(docxs)
        node["_direct_docx"] = docxs
        node["_subdirs"] = subdirs

        if node.get("type") == "dir" and node.get("depth", 0) > 0:
            dirs.append(node)
        if node.get("type") == "docx":
            docs.append(node)
        for c in children:
            rec(c)

    rec(tree)
    return dirs, docs


def match_folder_bucket(name: str) -> tuple[str, re.Match[str] | None]:
    for label, pat in P_PATTERNS:
        m = pat.match(name)
        if m:
            return label, m
    return "P6", None


def parse_declared(name: str) -> int | None:
    """从名称解析篇数；P1–P4 命中才有。"""
    for label, pat in P_PATTERNS:
        if label == "P5":
            break
        m = pat.match(name)
        if m:
            try:
                return int(m.group(3))
            except (IndexError, ValueError):
                return None
    return None


def separator_stats(name: str) -> str | None:
    """返回序号与名称之间的分隔符原样串；无则 None。"""
    m = LEADING_NUM_RE.match(name)
    if not m:
        return None
    return m.group(2)


def describe_sep(sep: str) -> str:
    parts = []
    for ch in sep:
        if ch == "\u3000":
            parts.append("全角空格")
        elif ch == " ":
            parts.append("半角空格")
        elif ch == "\t":
            parts.append("Tab")
        else:
            parts.append(f"U+{ord(ch):04X}")
    # 压缩连续相同
    out = []
    i = 0
    while i < len(parts):
        j = i + 1
        while j < len(parts) and parts[j] == parts[i]:
            j += 1
        n = j - i
        out.append(parts[i] if n == 1 else f"{parts[i]}×{n}")
        i = j
    return "+".join(out)


def collect_ordinal_chars(title: str) -> set[str]:
    """从名称标题部分收集用到的中文/圈号/全角字母序号字符。

    只认「前缀位置」或「（一）」类括注，避免正文用字误入。
    """
    found: set[str] = set()
    t = title.lstrip("　 \t")
    if not t:
        return found
    m = LEADING_ORDINAL_RE.match(t)
    if m:
        for ch in m.group(0):
            if ch in CN_ORDINAL_CHARS or ch in FW_LETTER_CHARS:
                found.add(ch)
            elif "a" <= ch <= "z" or "A" <= ch <= "Z":
                found.add(ch)
    for m in PAREN_ORDINAL_RE.finditer(t):
        for ch in m.group(1):
            if ch in CN_ORDINAL_CHARS or ch in FW_LETTER_CHARS or ch.isdigit() or (
                "ａ" <= ch <= "ｚ" or "ａ" <= ch <= "ｚ"
            ):
                found.add(ch)
            elif "a" <= ch <= "z" or "A" <= ch <= "Z":
                found.add(ch)
            elif "0" <= ch <= "9" or "０" <= ch <= "９":
                found.add(ch)
    return found


def has_annotation(name: str) -> bool:
    return bool(ANNOT_RE.search(name))


def is_work_note(name: str) -> bool:
    keys = (
        "需要新增",
        "顺序待定",
        "待定",
        "待补",
        "待加",
        "工作笔记",
        "备注",
        "TODO",
        "todo",
        "暂存",
        "临时",
        "未完成",
        "待处理",
    )
    return any(k in name for k in keys)


def chuchu_variant(name: str) -> str | None:
    """若含纲目带出处，返回归一前的后缀变体键。"""
    if CHUCHU_MARK not in name:
        return None
    # 抓紧邻标记的括号与空白写法
    # 例：（纲目带出处） / (纲目带出处) / （ 纲目带出处 ） / 纲目带出处.docx 等
    stem = name
    if stem.lower().endswith(".docx"):
        stem = stem[:-5]
    # 从「纲目带出处」向两侧扩到括号/空白边界
    idx = stem.find(CHUCHU_MARK)
    left = stem[:idx]
    right = stem[idx + len(CHUCHU_MARK) :]
    # 找左侧最近开括号
    open_i = max(left.rfind("（"), left.rfind("("))
    close_i_candidates = [right.find("）"), right.find(")")]
    close_i_candidates = [c for c in close_i_candidates if c >= 0]
    if open_i >= 0 and close_i_candidates:
        close_rel = min(close_i_candidates)
        variant = stem[open_i : idx + len(CHUCHU_MARK) + close_rel + 1]
        return variant
    # 无完整括号：记「裸标记 + 紧邻空白/字符」
    # 取标记前后各最多 2 个空白字符
    lpad = ""
    for ch in reversed(left):
        if ch in " 　\t":
            lpad = ch + lpad
        else:
            break
        if len(lpad) >= 3:
            break
    rpad = ""
    for ch in right:
        if ch in " 　\t":
            rpad += ch
        else:
            break
        if len(rpad) >= 3:
            break
    return repr(lpad + CHUCHU_MARK + rpad)


def recursive_docx_counts(node: dict) -> tuple[int, int]:
    """返回 (全部 docx, 去掉纲目带出处后的 docx)。"""
    total = 0
    no_cc = 0

    def walk(n: dict) -> None:
        nonlocal total, no_cc
        if n.get("type") == "docx":
            total += 1
            if CHUCHU_MARK not in n.get("name", ""):
                no_cc += 1
            return
        for c in n.get("children") or []:
            walk(c)

    walk(node)
    return total, no_cc


def sample_paths(items: list[dict], n: int = 5) -> list[str]:
    out = []
    for it in items[:n]:
        out.append(it.get("rel_path") or it.get("name") or "")
    return out


def write_report(path: Path, data: dict) -> None:
    lines: list[str] = []
    w = lines.append

    w("# 清明上河图目录名形态穷举报告")
    w("")
    w("只读 `tree.json`。不碰源目录、不碰 ES、不向量、不建索引。本步**不**产出清洗 JSON。")
    w("")
    w(f"- 输入：`{data['tree_path']}`")
    w(f"- 文件夹数（不含根）：{data['n_dirs']}")
    w(f"- docx 数：{data['n_docs']}")
    w("")

    # ---- C2 文件夹桶 ----
    w("## C2　文件夹名形态分桶（P1→P6，命中即归）")
    w("")
    w("| 桶 | 数量 | 占比 |")
    w("|---|---:|---:|")
    for label in ["P1", "P2", "P3", "P4", "P5", "P6"]:
        n = data["folder_bucket_counts"][label]
        pct = n / data["n_dirs"] * 100 if data["n_dirs"] else 0
        w(f"| {label} | {n} | {pct:.2f}% |")
    w("")
    w("### 各桶样本（各 ≤5）")
    w("")
    for label in ["P1", "P2", "P3", "P4", "P5"]:
        samples = data["folder_bucket_samples"][label]
        w(f"#### {label}（{data['folder_bucket_counts'][label]}）")
        w("")
        if not samples:
            w("（无）")
        else:
            for s in samples:
                w(f"- `{s}`")
        w("")

    w("### P6　其余（全部原样列出，不许省略）")
    w("")
    w(f"共 **{data['folder_bucket_counts']['P6']}** 条：")
    w("")
    if not data["p6_all"]:
        w("（空）")
    else:
        for s in data["p6_all"]:
            w(f"- `{s}`")
    w("")

    # ---- C3 单独统计 ----
    w("## C3　单独统计（不合进上桶）")
    w("")
    w("### 全角数字")
    w("")
    w(f"- 篇数位含全角数字的文件夹：{data['fw_count_in_declared']}")
    w(f"- 序号位含全角数字的文件夹：{data['fw_count_in_seq']}")
    if data["fw_declared_samples"]:
        w("- 篇数全角样本：")
        for s in data["fw_declared_samples"]:
            w(f"  - `{s}`")
    if data["fw_seq_samples"]:
        w("- 序号全角样本：")
        for s in data["fw_seq_samples"]:
            w(f"  - `{s}`")
    w("")
    w("### 序号与名称之间的分隔符")
    w("")
    w("| 分隔形态 | 数量 |")
    w("|---|---:|")
    for k, v in data["sep_counts"].most_common():
        w(f"| `{k}` | {v} |")
    w("")
    w(f"- 无法拆出分隔符（无前导数字+空白）的文件夹：{data['sep_none']}")
    w("")
    w("### 名称里的中文/圈号/全角字母序号字符全集")
    w("")
    chars = data["ordinal_chars"]
    if not chars:
        w("（未检出）")
    else:
        w("".join(f"`{c}` " for c in chars))
        w("")
        w(f"- 字符种数：{len(chars)}")
        w(f"- 名称检出含此类前缀/序号的文件夹数：{data['ordinal_folder_n']}")
    w("")
    w("### 名称里带括注（年月/地点等）")
    w("")
    w(f"- 数量：{data['annot_n']}")
    w("- 样本（≤10）：")
    for s in data["annot_samples"]:
        w(f"  - `{s}`")
    w("")

    # ---- C4 docx ----
    w("## C4　docx 文件名形态")
    w("")
    w("| 桶 | 数量 | 占比 |")
    w("|---|---:|---:|")
    for label in ["Q1", "Q2"]:
        n = data["docx_bucket_counts"][label]
        pct = n / data["n_docs"] * 100 if data["n_docs"] else 0
        w(f"| {label} | {n} | {pct:.2f}% |")
    w("")
    w("### Q1 样本（≤5）")
    w("")
    for s in data["q1_samples"]:
        w(f"- `{s}`")
    w("")
    w("### Q2　其余（全部原样列出，不许省略）")
    w("")
    w(f"共 **{data['docx_bucket_counts']['Q2']}** 条：")
    w("")
    if not data["q2_all"]:
        w("（空）")
    else:
        for s in data["q2_all"]:
            w(f"- `{s}`")
    w("")
    w("### 「纲目带出处」后缀写法分计")
    w("")
    w(f"- 含「纲目带出处」的 docx 总数：{data['chuchu_total']}")
    w("")
    w("| 写法变体 | 数量 |")
    w("|---|---:|")
    for k, v in data["chuchu_variants"].most_common():
        w(f"| `{k}` | {v} |")
    w("")

    # ---- C5 roles ----
    w("## C5　文件夹层级角色（三布尔组合）")
    w("")
    w("role = (has_subdir, has_docx, has_declared_count)，不按 depth。")
    w("")
    w("| has_subdir | has_docx | has_declared_count | 数量 | 样本路径（≤3） |")
    w("|:---:|:---:|:---:|---:|---|")
    for key in sorted(data["role_counts"].keys(), reverse=True):
        hs, hd, hc = key
        n = data["role_counts"][key]
        samples = " <br> ".join(f"`{p}`" for p in data["role_samples"][key][:3])
        w(f"| {hs} | {hd} | {hc} | {n} | {samples or '—'} |")
    w("")
    w(f"- 出现过的 role 组合种数：**{len(data['role_counts'])}**")
    w("")
    w("### 混合节点（has_subdir ∧ has_docx）")
    w("")
    w(f"- 数量：**{len(data['mixed_nodes'])}**")
    w("")
    if data["mixed_nodes"]:
        for p in data["mixed_nodes"]:
            w(f"- `{p}`")
    else:
        w("（无）")
    w("")

    # ---- C6 ----
    w("## C6　非分类节点清单（只列不删）")
    w("")
    w(f"### 工作笔记型（{len(data['work_notes'])}）")
    w("")
    if not data["work_notes"]:
        w("（无）")
    else:
        for p in data["work_notes"]:
            w(f"- `{p}`")
    w("")
    w(f"### 声明 0 篇（{len(data['zero_declared'])}）")
    w("")
    if not data["zero_declared"]:
        w("（无）")
    else:
        for p in data["zero_declared"]:
            w(f"- `{p}`")
    w("")
    w(f"### 空文件夹（{len(data['empty_dirs'])}）按 role 归类")
    w("")
    w(
        "> 说明：本步只看 `tree.json`（仅 dir/docx）。此前勘探报 276 个空文件夹，"
        "是因为当时把仅含 `.doc` 等非 docx 的目录不算空；此处这些目录在树里"
        "没有子节点，故计入空文件夹，数量可能略高。"
    )
    w("")
    w("| has_subdir | has_docx | has_declared_count | 数量 |")
    w("|:---:|:---:|:---:|---:|")
    for key in sorted(data["empty_role_counts"].keys(), reverse=True):
        hs, hd, hc = key
        w(f"| {hs} | {hd} | {hc} | {data['empty_role_counts'][key]} |")
    w("")
    w("全部空文件夹路径：")
    w("")
    for p in data["empty_dirs"]:
        w(f"- `{p}`")
    w("")

    # ---- C7 ----
    w("## C7　逐层篇数校验（凡解析出篇数的文件夹）")
    w("")
    w(f"- 参与校验的文件夹数：{data['check_n']}")
    w(
        f"- 口径 A（声明 vs 递归全部 docx）相符：**{data['match_a']}** / {data['check_n']}"
        f" = **{data['rate_a']:.2f}%**"
    )
    w(
        f"- 口径 B（声明 vs 递归 docx 去掉「纲目带出处」）相符：**{data['match_b']}** / {data['check_n']}"
        f" = **{data['rate_b']:.2f}%**"
    )
    w("")
    w("### 口径 A 不相符 Top 50（按 |差| 降序）")
    w("")
    w("| 路径 | 声明 | 实际(全部) | 差 |")
    w("|---|---:|---:|---:|")
    for row in data["top_mismatch_a"]:
        w(f"| `{row['path']}` | {row['declared']} | {row['actual']} | {row['diff']:+d} |")
    w("")
    w("### 口径 B 不相符 Top 50（按 |差| 降序）")
    w("")
    w("| 路径 | 声明 | 实际(去出处) | 差 |")
    w("|---|---:|---:|---:|")
    for row in data["top_mismatch_b"]:
        w(f"| `{row['path']}` | {row['declared']} | {row['actual']} | {row['diff']:+d} |")
    w("")
    w("### 按深度分组的相符率")
    w("")
    w("| depth | 参与数 | 口径A相符 | 口径A率 | 口径B相符 | 口径B率 |")
    w("|---:|---:|---:|---:|---:|---:|")
    for d in sorted(data["by_depth"].keys()):
        bd = data["by_depth"][d]
        ra = bd["match_a"] / bd["n"] * 100 if bd["n"] else 0
        rb = bd["match_b"] / bd["n"] * 100 if bd["n"] else 0
        w(
            f"| {d} | {bd['n']} | {bd['match_a']} | {ra:.2f}% | "
            f"{bd['match_b']} | {rb:.2f}% |"
        )
    w("")

    # ---- C9 ----
    w("## C9　验证三问")
    w("")
    w(
        f"1. **P6 / Q2 条数与是否全部列出**：P6 = {data['folder_bucket_counts']['P6']} 条"
        f"（上文已全部原样列出）；Q2 = {data['docx_bucket_counts']['Q2']} 条"
        f"（上文已全部原样列出）。"
    )
    w(f"2. **出现过的 role 组合种数**：{len(data['role_counts'])}")
    w(
        f"3. **两种口径相符率**：口径 A = {data['rate_a']:.2f}%；"
        f"口径 B = {data['rate_b']:.2f}%"
    )
    w("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def analyze(tree: dict, tree_path: Path) -> dict:
    dirs, docs = walk_collect(tree)
    n_dirs = len(dirs)
    n_docs = len(docs)

    # ---- folders P buckets ----
    bucket_items: dict[str, list[dict]] = defaultdict(list)
    for d in dirs:
        label, _ = match_folder_bucket(d["name"])
        bucket_items[label].append(d)

    folder_bucket_counts = {k: len(bucket_items[k]) for k in ["P1", "P2", "P3", "P4", "P5", "P6"]}
    folder_bucket_samples = {
        k: [x["name"] for x in bucket_items[k][:5]] for k in ["P1", "P2", "P3", "P4", "P5", "P6"]
    }
    # P6：路径+名称都给出，便于定位；用户要「条目原样」——用 name，同时附 rel_path
    p6_all = [
        f"{d['rel_path']}" if d["rel_path"] == d["name"] else f"{d['name']}  @@  {d['rel_path']}"
        for d in sorted(bucket_items["P6"], key=lambda x: x["rel_path"])
    ]

    # ---- C3 ----
    fw_declared = []
    fw_seq = []
    sep_counter: Counter[str] = Counter()
    sep_none = 0
    ordinal_chars: set[str] = set()
    ordinal_folder_n = 0
    annot_list: list[str] = []

    for d in dirs:
        name = d["name"]
        # 全角数字：序号 / 篇数
        m_lead = re.match(r"^([0-9０-９]+)", name)
        if m_lead and FW_DIGIT_RE.search(m_lead.group(1)):
            fw_seq.append(name)
        # 篇数段：……——?digits篇
        m_cnt = re.search(r"[—–―\-——\s　]+([0-9０-９]+)篇$", name)
        if m_cnt and FW_DIGIT_RE.search(m_cnt.group(1)):
            fw_declared.append(name)

        sep = separator_stats(name)
        if sep is None:
            sep_none += 1
        else:
            sep_counter[describe_sep(sep)] += 1

        # 标题部分：去掉前导数字+分隔
        title = name
        m = LEADING_NUM_RE.match(name)
        if m:
            title = m.group(3)
        # 再去掉末尾篇数
        title_core = re.sub(r"(?:——|[—–―\-]|[　\s]+)[0-9０-９]+篇$", "", title)
        chars = collect_ordinal_chars(title_core)
        if chars:
            ordinal_chars |= chars
            ordinal_folder_n += 1

        if has_annotation(name):
            annot_list.append(d["rel_path"])

    # ---- docx Q ----
    q_items: dict[str, list[dict]] = {"Q1": [], "Q2": []}
    chuchu_variants: Counter[str] = Counter()
    chuchu_total = 0
    for doc in docs:
        name = doc["name"]
        if Q1.match(name):
            q_items["Q1"].append(doc)
        else:
            q_items["Q2"].append(doc)
        var = chuchu_variant(name)
        if var is not None:
            chuchu_total += 1
            chuchu_variants[var] += 1

    q2_all = [
        f"{d['name']}  @@  {d['rel_path']}"
        for d in sorted(q_items["Q2"], key=lambda x: x["rel_path"])
    ]

    # ---- C5 roles ----
    role_counts: Counter[tuple[bool, bool, bool]] = Counter()
    role_samples: dict[tuple[bool, bool, bool], list[str]] = defaultdict(list)
    mixed_nodes: list[str] = []

    for d in dirs:
        declared = parse_declared(d["name"])
        hs = bool(d["_has_subdir"])
        hd = bool(d["_has_docx"])
        hc = declared is not None
        key = (hs, hd, hc)
        role_counts[key] += 1
        if len(role_samples[key]) < 3:
            role_samples[key].append(d["rel_path"])
        if hs and hd:
            mixed_nodes.append(d["rel_path"])

    mixed_nodes.sort()

    # ---- C6 ----
    work_notes = sorted(
        d["rel_path"] for d in dirs if is_work_note(d["name"])
    )
    zero_declared = sorted(
        d["rel_path"]
        for d in dirs
        if (parse_declared(d["name"]) == 0)
    )
    empty_dirs = sorted(
        d["rel_path"]
        for d in dirs
        if (not d["_has_subdir"] and not d["_has_docx"])
    )
    empty_role_counts: Counter[tuple[bool, bool, bool]] = Counter()
    for d in dirs:
        if not d["_has_subdir"] and not d["_has_docx"]:
            declared = parse_declared(d["name"])
            empty_role_counts[(False, False, declared is not None)] += 1

    # ---- C7 ----
    mismatches_a: list[dict] = []
    mismatches_b: list[dict] = []
    match_a = match_b = 0
    check_n = 0
    by_depth: dict[int, dict] = defaultdict(lambda: {"n": 0, "match_a": 0, "match_b": 0})

    for d in dirs:
        declared = parse_declared(d["name"])
        if declared is None:
            continue
        check_n += 1
        total, no_cc = recursive_docx_counts(d)
        depth = d.get("depth", -1)
        by_depth[depth]["n"] += 1
        ok_a = declared == total
        ok_b = declared == no_cc
        if ok_a:
            match_a += 1
            by_depth[depth]["match_a"] += 1
        else:
            mismatches_a.append(
                {
                    "path": d["rel_path"],
                    "declared": declared,
                    "actual": total,
                    "diff": total - declared,
                    "abs": abs(total - declared),
                }
            )
        if ok_b:
            match_b += 1
            by_depth[depth]["match_b"] += 1
        else:
            mismatches_b.append(
                {
                    "path": d["rel_path"],
                    "declared": declared,
                    "actual": no_cc,
                    "diff": no_cc - declared,
                    "abs": abs(no_cc - declared),
                }
            )

    mismatches_a.sort(key=lambda r: (-r["abs"], r["path"]))
    mismatches_b.sort(key=lambda r: (-r["abs"], r["path"]))

    rate_a = match_a / check_n * 100 if check_n else 0.0
    rate_b = match_b / check_n * 100 if check_n else 0.0

    return {
        "tree_path": str(tree_path),
        "n_dirs": n_dirs,
        "n_docs": n_docs,
        "folder_bucket_counts": folder_bucket_counts,
        "folder_bucket_samples": folder_bucket_samples,
        "p6_all": p6_all,
        "fw_count_in_declared": len(fw_declared),
        "fw_count_in_seq": len(fw_seq),
        "fw_declared_samples": fw_declared[:5],
        "fw_seq_samples": fw_seq[:5],
        "sep_counts": sep_counter,
        "sep_none": sep_none,
        "ordinal_chars": sorted(ordinal_chars, key=lambda c: (ord(c), c)),
        "ordinal_folder_n": ordinal_folder_n,
        "annot_n": len(annot_list),
        "annot_samples": annot_list[:10],
        "docx_bucket_counts": {"Q1": len(q_items["Q1"]), "Q2": len(q_items["Q2"])},
        "q1_samples": [d["name"] for d in q_items["Q1"][:5]],
        "q2_all": q2_all,
        "chuchu_total": chuchu_total,
        "chuchu_variants": chuchu_variants,
        "role_counts": role_counts,
        "role_samples": role_samples,
        "mixed_nodes": mixed_nodes,
        "work_notes": work_notes,
        "zero_declared": zero_declared,
        "empty_dirs": empty_dirs,
        "empty_role_counts": empty_role_counts,
        "check_n": check_n,
        "match_a": match_a,
        "match_b": match_b,
        "rate_a": rate_a,
        "rate_b": rate_b,
        "top_mismatch_a": mismatches_a[:50],
        "top_mismatch_b": mismatches_b[:50],
        "by_depth": dict(by_depth),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="穷举清明上河图目录名形态")
    parser.add_argument("--tree", type=Path, default=TREE_DEFAULT)
    parser.add_argument("--report", type=Path, default=REPORT_DEFAULT)
    args = parser.parse_args(argv)

    if not args.tree.is_file():
        print(f"ERROR tree not found: {args.tree}", file=sys.stderr)
        return 1

    print(f"LOAD {args.tree}", flush=True)
    tree = json.loads(args.tree.read_text(encoding="utf-8"))
    print("ANALYZE", flush=True)
    data = analyze(tree, args.tree)
    print(
        f"DONE dirs={data['n_dirs']} docs={data['n_docs']} "
        f"P6={data['folder_bucket_counts']['P6']} Q2={data['docx_bucket_counts']['Q2']} "
        f"roles={len(data['role_counts'])} "
        f"rateA={data['rate_a']:.2f}% rateB={data['rate_b']:.2f}%",
        flush=True,
    )
    print(f"WRITE {args.report}", flush=True)
    write_report(args.report, data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
