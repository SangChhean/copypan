# -*- coding: utf-8 -*-
"""只读勘探清明上河图备份目录树。

- 源目录只读：禁止任何写入 / 重命名 / 移动 / 删除
- 不读 docx 内容，不转换，不建索引
- 产出 tree.json / tree.txt / 报告

用法（在 back_mic/backend 下）::

    python -m panai4.pano.probe_tree
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

from dotenv import load_dotenv

ROOT_DEFAULT = Path(r"G:\PanAI用\Pansearch数据备份\map_pano制作\备份")
OUT_DIR_DEFAULT = Path(r"G:\PanAI4.0专用\清明上河图目录")
REPORT_DEFAULT = Path(__file__).resolve().parents[4] / "docs" / "panai4_es" / "map_pano_tree_probe.md"
ES_INDEX = "kg-rag_map_note"

# 类名可含「—」；贪婪吃到最后一个「——」
TOP_FOLDER_RE = re.compile(r"^(\d+)\s+(.*)——(\d+)篇$")

# 不可见 / 异常字符（不含普通空白；前后空格单独查）
_INVISIBLE_CATS = {"Cc", "Cf", "Zl", "Zp"}
_VISIBLE_SPACE_OK = {" ", "\t"}  # 中间空格/制表可接受；前后空格仍标异常


def _backend_env() -> str:
    return str(Path(__file__).resolve().parents[2] / ".env")


def is_real_docx(name: str) -> bool:
    return name.lower().endswith(".docx") and not name.startswith("~$")


def is_temp_file(name: str) -> bool:
    return name.startswith("~$")


def has_abnormal_name(name: str) -> list[str]:
    """返回异常原因列表；空列表表示正常。"""
    reasons: list[str] = []
    if name != name.strip(" \t"):
        reasons.append("前后空格")
    if "\n" in name or "\r" in name:
        reasons.append("含换行")
    invis = []
    for ch in name:
        if ch in _VISIBLE_SPACE_OK or ch == "\u3000":
            continue
        cat = unicodedata.category(ch)
        if cat in _INVISIBLE_CATS or ch in ("\u200b", "\u200c", "\u200d", "\ufeff", "\u00a0"):
            invis.append(f"U+{ord(ch):04X}")
    if invis:
        reasons.append("不可见字符:" + ",".join(sorted(set(invis))))
    return reasons


def walk_tree(root: Path) -> tuple[dict, dict]:
    """一次遍历：嵌套树 + 统计。不读文件内容。"""
    stats: dict = {
        "docx_paths": [],  # rel posix
        "dir_paths": [],  # rel posix，含根 ''
        "non_docx": [],  # (rel, ext_or_temp)
        "empty_dirs": [],
        "name_to_paths": defaultdict(list),  # docx basename -> [rel]
        "long_paths": [],  # abs path > 240
        "abnormal_names": [],  # {kind, name, rel_path, reasons}
        "depth_dirs": Counter(),
        "depth_docx": Counter(),
        "max_depth": 0,
        "docx_with_chuchu": 0,
        "docx_without_chuchu": 0,
    }

    root = root.resolve()

    def rec(abs_dir: Path, depth: int, rel: str) -> dict:
        name = root.name if depth == 0 else abs_dir.name
        node = {
            "name": name,
            "type": "dir",
            "depth": depth,
            "rel_path": rel,
            "children": [],
        }
        stats["dir_paths"].append(rel)
        stats["depth_dirs"][depth] += 1
        stats["max_depth"] = max(stats["max_depth"], depth)

        abs_str = str(abs_dir)
        if len(abs_str) > 240:
            stats["long_paths"].append(abs_str)

        reasons = has_abnormal_name(name)
        if reasons and depth > 0:
            stats["abnormal_names"].append(
                {"kind": "dir", "name": name, "rel_path": rel, "reasons": reasons}
            )

        try:
            entries = list(abs_dir.iterdir())
        except OSError as e:
            print(f"WARN cannot list {abs_dir}: {e}", flush=True)
            stats["empty_dirs"].append(rel or ".")
            return node

        entries.sort(key=lambda p: (0 if p.is_dir() else 1, p.name))
        child_count = 0

        for entry in entries:
            child_rel = entry.name if not rel else f"{rel}/{entry.name}"
            child_rel = child_rel.replace("\\", "/")
            abs_child = str(entry)
            if len(abs_child) > 240:
                stats["long_paths"].append(abs_child)

            if entry.is_dir():
                child = rec(entry, depth + 1, child_rel)
                node["children"].append(child)
                child_count += 1
                continue

            # 文件
            fname = entry.name
            reasons = has_abnormal_name(fname)
            if reasons:
                stats["abnormal_names"].append(
                    {
                        "kind": "file",
                        "name": fname,
                        "rel_path": child_rel,
                        "reasons": reasons,
                    }
                )

            if is_temp_file(fname):
                stats["non_docx"].append((child_rel, "~$"))
                child_count += 1
                continue

            if is_real_docx(fname):
                d_depth = depth + 1
                docx_node = {
                    "name": fname,
                    "type": "docx",
                    "depth": d_depth,
                    "rel_path": child_rel,
                }
                node["children"].append(docx_node)
                stats["docx_paths"].append(child_rel)
                stats["depth_docx"][d_depth] += 1
                stats["max_depth"] = max(stats["max_depth"], d_depth)
                stats["name_to_paths"][fname].append(child_rel)
                if "（纲目带出处）" in fname:
                    stats["docx_with_chuchu"] += 1
                else:
                    stats["docx_without_chuchu"] += 1
                child_count += 1
                continue

            # 其它文件
            suf = entry.suffix.lower() or "(noext)"
            stats["non_docx"].append((child_rel, suf))
            child_count += 1

        if child_count == 0:
            stats["empty_dirs"].append(rel or ".")

        return node

    tree = rec(root, 0, "")
    return tree, stats


def render_txt(node: dict, lines: list[str], indent: int = 0) -> None:
    prefix = "  " * indent
    if node["type"] == "dir":
        label = node["name"] if indent > 0 or node["rel_path"] else node["name"]
        lines.append(f"{prefix}{label}/")
        for child in node.get("children") or []:
            render_txt(child, lines, indent + 1)
    else:
        lines.append(f"{prefix}{node['name']} [docx]")


def count_docx_under(node: dict) -> int:
    if node["type"] == "docx":
        return 1
    return sum(count_docx_under(c) for c in node.get("children") or [])


def subtree_txt_lines(node: dict, limit: int = 20) -> list[str]:
    lines: list[str] = []
    render_txt(node, lines, 0)
    return lines[:limit]


def deepest_docx_paths(stats: dict, n: int = 3) -> list[str]:
    paths = stats["docx_paths"]
    scored = sorted(paths, key=lambda p: (-p.count("/"), -len(p), p))
    return scored[:n]


def parse_top_folders(tree: dict) -> list[dict]:
    rows = []
    for child in tree.get("children") or []:
        if child["type"] != "dir":
            continue
        name = child["name"]
        m = TOP_FOLDER_RE.match(name)
        actual = count_docx_under(child)
        if m:
            seq, cls, declared = m.group(1), m.group(2), int(m.group(3))
            rows.append(
                {
                    "name": name,
                    "seq": seq,
                    "class": cls,
                    "declared": declared,
                    "actual": actual,
                    "match": declared == actual,
                    "parse_ok": True,
                    "node": child,
                }
            )
        else:
            rows.append(
                {
                    "name": name,
                    "seq": None,
                    "class": None,
                    "declared": None,
                    "actual": actual,
                    "match": False,
                    "parse_ok": False,
                    "node": child,
                }
            )
    # 按序号数字排序；解析失败的放后
    def sort_key(r):
        if r["parse_ok"] and r["seq"] is not None:
            return (0, int(r["seq"]), r["name"])
        return (1, 0, r["name"])

    rows.sort(key=sort_key)
    return rows


def fetch_map_note_sources() -> tuple[list[str], str | None, str | None]:
    """从本机 ES 取 kg-rag_map_note 顶层分类字段去重。

    源 JSON 字段名是 ``source``（形如「圣经真理题库，第一系列　圣经—神的话，…」）；
    当前本机 chunks 索引里同形值在 ``book_title``，``source_zh`` 是经文出处注。
    返回 (values, field_used, err)。
    """
    try:
        from elasticsearch import Elasticsearch
    except ImportError:
        return [], None, "elasticsearch 包未安装"

    load_dotenv(_backend_env())
    host = os.getenv("ES_HOST", "localhost")
    port = os.getenv("ES_PORT", "9200")
    user = os.getenv("ES_USERNAME", "elastic")
    password = os.getenv("ES_PASSWORD", "")
    es = Elasticsearch(
        hosts=[f"http://{host}:{port}"],
        basic_auth=(user, password),
        request_timeout=120,
    )
    if not es.ping():
        return [], None, f"无法连接 ES {host}:{port}"

    # 探测样本文档，决定用哪个字段
    try:
        sample = es.search(
            index=ES_INDEX,
            size=5,
            _source=["source", "book_title", "source_zh"],
            query={"match_all": {}},
        )
    except Exception as e:
        return [], None, f"抽样失败: {e}"

    hits = sample.get("hits", {}).get("hits", [])
    field_used: str | None = None
    for cand in ("source", "book_title"):
        for h in hits:
            val = (h.get("_source") or {}).get(cand)
            if isinstance(val, str) and "圣经真理题库" in val:
                field_used = cand
                break
            if isinstance(val, str) and "，" in val and len(val) > 10:
                field_used = cand
                break
        if field_used:
            break
    if not field_used:
        # 退化：看哪个非空更多
        for cand in ("source", "book_title"):
            if any((h.get("_source") or {}).get(cand) for h in hits):
                field_used = cand
                break
    if not field_used:
        return [], None, "文档中找不到 source / book_title 顶层分类字段"

    sources: set[str] = set()
    try:
        resp = es.search(
            index=ES_INDEX,
            size=1000,
            scroll="2m",
            _source=[field_used],
            query={"match_all": {}},
        )
        sid = resp.get("_scroll_id")
        while True:
            page = resp.get("hits", {}).get("hits", [])
            if not page:
                break
            for h in page:
                src = (h.get("_source") or {}).get(field_used)
                if src is not None and str(src).strip() != "":
                    sources.add(str(src))
            resp = es.scroll(scroll_id=sid, scroll="2m")
            sid = resp.get("_scroll_id")
        if sid:
            try:
                es.clear_scroll(scroll_id=sid)
            except Exception:
                pass
        return sorted(sources), field_used, None
    except Exception as e:
        return [], field_used, f"scroll 失败: {e}"


def compare_classes(folder_classes: list[str], sources: list[str]) -> dict:
    """类名 vs map_note source：精确相等 + 类名作为子串出现在 source 中。"""
    class_set = list(dict.fromkeys(folder_classes))  # 保序去重
    source_set = list(dict.fromkeys(sources))

    exact_matched_classes = []
    exact_matched_sources = []
    substr_matched_classes = []
    substr_matched_sources = set()

    source_set_lookup = set(source_set)
    for cls in class_set:
        if cls in source_set_lookup:
            exact_matched_classes.append(cls)
            exact_matched_sources.append(cls)
        hits = [s for s in source_set if cls in s]
        if hits:
            substr_matched_classes.append(cls)
            substr_matched_sources.update(hits)

    only_classes_exact = [c for c in class_set if c not in source_set_lookup]
    only_sources_exact = [s for s in source_set if s not in set(class_set)]

    only_classes_substr = [c for c in class_set if c not in set(substr_matched_classes)]
    only_sources_substr = [s for s in source_set if s not in substr_matched_sources]

    return {
        "n_classes": len(class_set),
        "n_sources": len(source_set),
        "exact_n": len(exact_matched_classes),
        "exact_classes": exact_matched_classes,
        "only_classes_exact": only_classes_exact,
        "only_sources_exact": only_sources_exact,
        "substr_n": len(substr_matched_classes),
        "substr_classes": substr_matched_classes,
        "only_classes_substr": only_classes_substr,
        "only_sources_substr": only_sources_substr,
        "substr_source_hit_n": len(substr_matched_sources),
    }


def write_report(
    report_path: Path,
    root: Path,
    tree: dict,
    stats: dict,
    top_rows: list[dict],
    cmp: dict | None,
    es_err: str | None,
    es_field: str | None = None,
) -> None:
    n_docx = len(stats["docx_paths"])
    # 文件夹总数不含根？任务说「文件夹总数」——含顶层及以下所有 dir，不含根更直观；
    # 这里报「含子目录总数（不含根）」与「含根」两数，主数字用不含根（= len(dir_paths)-1）
    n_dirs_incl_root = len(stats["dir_paths"])
    n_dirs = n_dirs_incl_root - 1
    max_depth = stats["max_depth"]

    depths = sorted(set(stats["depth_dirs"]) | set(stats["depth_docx"]))
    docx_depths = sorted(d for d, c in stats["depth_docx"].items() if c > 0)

    declared_ok = [r for r in top_rows if r["parse_ok"]]
    declared_fail = [r for r in top_rows if not r["parse_ok"]]
    declared_sum = sum(r["declared"] for r in declared_ok)
    match_ok = [r for r in declared_ok if r["match"]]
    match_bad = [r for r in declared_ok if not r["match"]]

    # 非 docx 按扩展名
    ext_counter: Counter = Counter()
    ext_samples: dict[str, list[str]] = defaultdict(list)
    for rel, ext in stats["non_docx"]:
        ext_counter[ext] += 1
        if len(ext_samples[ext]) < 5:
            ext_samples[ext].append(rel)

    dupes = {
        name: paths
        for name, paths in stats["name_to_paths"].items()
        if len(paths) > 1
    }

    deep_paths = deepest_docx_paths(stats, 3)
    sample_tops = top_rows[:3]

    lines: list[str] = []
    w = lines.append

    w("# 清明上河图目录树勘探报告")
    w("")
    w("只读勘探。不读 docx 内容，不做转换，不建索引。")
    w("")
    w(f"- 根目录：`{root}`")
    w(f"- 产出：`tree.json` / `tree.txt` → `G:\\PanAI4.0专用\\清明上河图目录\\`")
    w("")
    w("## 【规模】")
    w("")
    w(f"- **docx 总数**：{n_docx}")
    w(f"- **文件夹总数**（不含根）：{n_dirs}；含根：{n_dirs_incl_root}")
    w(f"- **最大深度**：{max_depth}（根为 0）")
    w("")
    w("### 各深度文件夹数与 docx 数")
    w("")
    w("| depth | 文件夹数 | docx 数 |")
    w("|---:|---:|---:|")
    for d in depths:
        w(
            f"| {d} | {stats['depth_dirs'].get(d, 0)} | {stats['depth_docx'].get(d, 0)} |"
        )
    w("")
    w("### docx 出现在哪些深度")
    w("")
    if len(docx_depths) == 1:
        w(f"- 全部 docx 集中在 **depth={docx_depths[0]}**（同一层）。")
    else:
        w(f"- docx **散布在多层**：{docx_depths}")
        for d in docx_depths:
            w(f"  - depth={d}：{stats['depth_docx'][d]} 个")
    w("")
    w("## 【顶层校验】")
    w("")
    w("解析规则：`^(\\d+)\\s+(.*)——(\\d+)篇$`（类名贪婪到最后一个 `——`）。")
    w("")
    w(f"- 顶层文件夹数：{len(top_rows)}")
    w(f"- 解析成功：{len(declared_ok)}；解析失败：{len(declared_fail)}")
    w(f"- 声明篇数总和：{declared_sum}")
    w(f"- 实际 docx 总数：{n_docx}")
    w(
        f"- 其中文件名含「（纲目带出处）」：{stats['docx_with_chuchu']}；"
        f"不含：{stats['docx_without_chuchu']}"
    )
    w(
        f"- 声明总和 vs 不含出处 docx：声明 {declared_sum} / 不含出处 "
        f"{stats['docx_without_chuchu']} "
        f"（差 {stats['docx_without_chuchu'] - declared_sum:+d}）"
    )
    w(
        f"- 声明总和 vs 实际全部 docx：{'相符' if declared_sum == n_docx else f'不相符（差 {n_docx - declared_sum:+d}）'}"
    )
    w(f"- 逐个相符（声明==实际全部 docx）：{len(match_ok)} / {len(declared_ok)}；不相符：{len(match_bad)}")
    w("")
    w(
        "> 说明：文件夹名声明的是「篇」数；目录里多数篇同时有普通版与"
        "「（纲目带出处）」两份 docx，故实际 docx 数通常大于声明篇数。"
        "上表「相符」严格按声明篇数 == 递归 docx 文件数判定。"
    )
    w("")
    w("### 逐个顶层文件夹")
    w("")
    w("| 原始名 | 序号 | 类名 | 声明篇数 | 实际 docx | 相符 |")
    w("|---|---:|---|---:|---:|:---:|")
    for r in declared_ok:
        flag = "是" if r["match"] else "否"
        w(
            f"| {r['name']} | {r['seq']} | {r['class']} | {r['declared']} | {r['actual']} | {flag} |"
        )
    w("")
    if declared_fail:
        w("### 解析失败的文件夹（未猜测）")
        w("")
        for r in declared_fail:
            w(f"- `{r['name']}`（实际递归 docx={r['actual']}）")
        w("")
    else:
        w("解析失败的文件夹：无。")
        w("")

    if match_bad:
        w("### 声明篇数 ≠ 实际 docx 的顶层（摘要）")
        w("")
        w("| 序号 | 类名 | 声明 | 实际 | 差（实际-声明） |")
        w("|---:|---|---:|---:|---:|")
        for r in match_bad:
            w(
                f"| {r['seq']} | {r['class']} | {r['declared']} | {r['actual']} | {r['actual'] - r['declared']:+d} |"
            )
        w("")

    w("## 【与 map_note 比对】")
    w("")
    if es_err:
        w(f"ES 读取失败：{es_err}")
        w("")
    elif cmp is None:
        w("未执行比对。")
        w("")
    else:
        field_note = es_field or "source"
        if es_field == "book_title":
            w(
                f"- 字段说明：源 JSON 叫 `source`；本机 `kg-rag_map_note` chunks 索引中"
                f"同形值在 **`book_title`**（`source_zh` 是经文出处，已排除）。"
            )
        w(f"- 实际读取字段：`{field_note}`")
        w(f"- map_note 不重复顶层分类数：**{cmp['n_sources']}**")
        w(f"- 本目录不重复顶层类名数：**{cmp['n_classes']}**")
        w("")
        w("### 精确相等")
        w("")
        w(f"- 能对上：**{cmp['exact_n']}**")
        w(f"- 仅目录有、map_note 无：{len(cmp['only_classes_exact'])}")
        if cmp["only_classes_exact"]:
            for c in cmp["only_classes_exact"][:30]:
                w(f"  - {c}")
            if len(cmp["only_classes_exact"]) > 30:
                w(f"  - … 另有 {len(cmp['only_classes_exact']) - 30} 个")
        w(f"- 仅 map_note 有、目录无：{len(cmp['only_sources_exact'])}")
        if cmp["only_sources_exact"]:
            for s in cmp["only_sources_exact"][:30]:
                w(f"  - {s}")
            if len(cmp["only_sources_exact"]) > 30:
                w(f"  - … 另有 {len(cmp['only_sources_exact']) - 30} 个")
        w("")
        w("### 子串包含（类名出现在某条 map_note 顶层串中）")
        w("")
        w(f"- 能对上的类名：**{cmp['substr_n']}** / {cmp['n_classes']}")
        w(f"- 被命中的 map_note 条数：{cmp['substr_source_hit_n']} / {cmp['n_sources']}")
        w(f"- 对不上的类名（{len(cmp['only_classes_substr'])}）：")
        if cmp["only_classes_substr"]:
            for c in cmp["only_classes_substr"]:
                w(f"  - {c}")
        else:
            w("  - （无）")
        w("")
        w(f"- 对不上的 map_note（前 50 条，共 {len(cmp['only_sources_substr'])}）：")
        if cmp["only_sources_substr"]:
            for s in cmp["only_sources_substr"][:50]:
                w(f"  - {s}")
            if len(cmp["only_sources_substr"]) > 50:
                w(f"  - … 另有 {len(cmp['only_sources_substr']) - 50} 条")
        else:
            w("  - （无）")
        w("")
        # 结论
        if cmp["exact_n"] == cmp["n_classes"] == cmp["n_sources"] and cmp["n_classes"] > 0:
            conclusion = "是同一套分类体系（精确一一对应）。"
        elif cmp["substr_n"] == cmp["n_classes"] and cmp["substr_n"] > 0:
            conclusion = (
                "不是同一套顶层命名：目录类名偏短主题标签，map_note 是"
                "「题库，系列，子题」长串；但每个目录类名都能在某条 map_note 中找到，"
                "属于相关/从属关系，而非同一套顶层键。"
            )
        elif cmp["substr_n"] > 0:
            conclusion = (
                f"不是同一套分类体系：仅 {cmp['substr_n']}/{cmp['n_classes']} 个类名"
                f"能在 map_note 顶层串中找到，其余对不上。"
            )
        else:
            conclusion = "不是同一套分类体系：顶层类名与 map_note 无精确或子串对应。"
        w(f"**结论**：{conclusion}")
        w("")

    w("## 【数据卫生】")
    w("")
    w("### 非 docx 文件（按扩展名 / ~$）")
    w("")
    if not ext_counter:
        w("无。")
    else:
        w("| 分组 | 数量 | 样例（最多 5） |")
        w("|---|---:|---|")
        for ext, cnt in sorted(ext_counter.items(), key=lambda x: (-x[1], x[0])):
            samples = "<br>".join(ext_samples[ext])
            w(f"| `{ext}` | {cnt} | {samples} |")
    w("")
    w(f"### 空文件夹（{len(stats['empty_dirs'])}）")
    w("")
    if not stats["empty_dirs"]:
        w("无。")
    else:
        for p in stats["empty_dirs"][:200]:
            w(f"- `{p}`")
        if len(stats["empty_dirs"]) > 200:
            w(f"- … 另有 {len(stats['empty_dirs']) - 200} 个")
    w("")
    w(f"### 同名 docx（{len(dupes)} 个文件名）")
    w("")
    if not dupes:
        w("无。")
    else:
        # 可能很多；先按出现次数降序，列出全部文件名+路径（若过多截断说明）
        items = sorted(dupes.items(), key=lambda x: (-len(x[1]), x[0]))
        show = items[:100]
        for name, paths in show:
            w(f"- **{name}**（{len(paths)} 处）")
            for p in paths:
                w(f"  - `{p}`")
        if len(items) > 100:
            w(f"- … 另有 {len(items) - 100} 个同名文件名未展开")
    w("")
    w(f"### 路径总长 > 240（{len(stats['long_paths'])}）")
    w("")
    if not stats["long_paths"]:
        w("无。")
    else:
        for p in stats["long_paths"][:100]:
            w(f"- ({len(p)}) `{p}`")
        if len(stats["long_paths"]) > 100:
            w(f"- … 另有 {len(stats['long_paths']) - 100} 条")
    w("")
    w(f"### 异常字符名（{len(stats['abnormal_names'])}）")
    w("")
    if not stats["abnormal_names"]:
        w("无。")
    else:
        for a in stats["abnormal_names"][:100]:
            w(
                f"- [{a['kind']}] `{a['name']}` @ `{a['rel_path']}` — {', '.join(a['reasons'])}"
            )
        if len(stats["abnormal_names"]) > 100:
            w(f"- … 另有 {len(stats['abnormal_names']) - 100} 条")
    w("")

    w("## 【样本】")
    w("")
    w("### 3 条最深路径（根 → docx）")
    w("")
    for i, p in enumerate(deep_paths, 1):
        parts = [root.name] + p.split("/")
        w(f"{i}. " + " → ".join(parts))
    w("")
    w("### 3 个顶层文件夹子树前 20 行")
    w("")
    for r in sample_tops:
        w(f"#### {r['name']}")
        w("")
        w("```")
        for line in subtree_txt_lines(r["node"], 20):
            w(line)
        w("```")
        w("")

    w("## 【P4 三问】")
    w("")
    w(f"1. **docx 总数**：{n_docx}")
    same_layer = "是，都在同一层" if len(docx_depths) == 1 else f"否，散布在 {docx_depths}"
    w(f"2. **目录一共几层 / docx 是否同层**：最大深度 {max_depth}（根=0）；docx {same_layer}（depths={docx_depths}）")
    if len(match_ok) == len(declared_ok) and not declared_fail and declared_sum == n_docx:
        q3 = "是，每一个顶层声明篇数都与实际递归 docx 数相符，且总和一致。"
    else:
        q3 = (
            f"否。解析成功 {len(declared_ok)} 个中仅 {len(match_ok)} 个相符；"
            f"声明总和 {declared_sum}，实际 docx {n_docx}"
            f"（含出处 {stats['docx_with_chuchu']}，不含 {stats['docx_without_chuchu']}）。"
        )
    w(f"3. **顶层声明篇数是否个个对得上**：{q3}")
    w("")

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="只读勘探清明上河图目录树")
    parser.add_argument("--root", type=Path, default=ROOT_DEFAULT)
    parser.add_argument("--out-dir", type=Path, default=OUT_DIR_DEFAULT)
    parser.add_argument("--report", type=Path, default=REPORT_DEFAULT)
    parser.add_argument("--skip-es", action="store_true", help="跳过 map_note ES 比对")
    args = parser.parse_args(argv)

    root: Path = args.root
    out_dir: Path = args.out_dir
    report_path: Path = args.report

    if not root.is_dir():
        print(f"ERROR root not found: {root}", file=sys.stderr)
        return 1

    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"WALK_START {root}", flush=True)
    tree, stats = walk_tree(root)
    print(
        f"WALK_DONE dirs={len(stats['dir_paths'])} docx={len(stats['docx_paths'])} "
        f"max_depth={stats['max_depth']}",
        flush=True,
    )

    json_path = out_dir / "tree.json"
    txt_path = out_dir / "tree.txt"

    print(f"WRITE {json_path}", flush=True)
    json_path.write_text(
        json.dumps(tree, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"WRITE {txt_path}", flush=True)
    txt_lines: list[str] = []
    render_txt(tree, txt_lines, 0)
    txt_path.write_text("\n".join(txt_lines) + "\n", encoding="utf-8")

    top_rows = parse_top_folders(tree)
    # 报告里不要塞 node 对象的循环引用问题——write_report 只用到 node 抽样本，写完可丢
    cmp = None
    es_err = None
    es_field = None
    if args.skip_es:
        es_err = "已 --skip-es"
    else:
        print(f"ES_FETCH {ES_INDEX} sources", flush=True)
        sources, es_field, es_err = fetch_map_note_sources()
        if es_err is None:
            classes = [r["class"] for r in top_rows if r["parse_ok"] and r["class"]]
            cmp = compare_classes(classes, sources)
            print(
                f"ES_DONE field={es_field} sources={cmp['n_sources']} "
                f"classes={cmp['n_classes']} exact={cmp['exact_n']} "
                f"substr={cmp['substr_n']}",
                flush=True,
            )
        else:
            print(f"ES_ERR {es_err}", flush=True)

    print(f"WRITE {report_path}", flush=True)
    write_report(
        report_path, root, tree, stats, top_rows, cmp, es_err, es_field=es_field
    )

    print("DONE", flush=True)
    print(f"  tree.json = {json_path}", flush=True)
    print(f"  tree.txt  = {txt_path}", flush=True)
    print(f"  report    = {report_path}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
