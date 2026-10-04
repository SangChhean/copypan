# -*- coding: utf-8 -*-
"""v0.3 转换报告。"""

import json
import os
import random
import re
from collections import Counter, defaultdict

from . import config
from .docx_parser import read_paragraphs

GOSPEL_PREFIX = "2 李常受文集纲目\\15 李常受文集一九五四年第三册\\3 福音题纲\\"
NOTES_PATH = "2 李常受文集纲目\\35 李常受文集一九六〇年第二册\\03 李常受弟兄个人笔记\\李常受弟兄个人笔记.docx"


def canon_level(label):
    from .docx_parser import level_of_label, normalize_label

    return level_of_label(normalize_label(label or ""))


def _pct(n, total):
    if not total:
        return "0.0%"
    return "{0:.1f}%".format(n / total * 100)


def _cell(text, limit=40):
    s = "" if text is None else str(text)
    s = s.replace("\t", "→").replace("\n", "⏎").replace("|", "\\|")
    if len(s) > limit:
        s = s[:limit]
    return s or "（空）"


def _bucket(ratio):
    if ratio is None:
        return None
    if ratio >= 1:
        return 9
    idx = int(ratio * 10)
    if idx < 0:
        idx = 0
    if idx > 9:
        idx = 9
    return idx


def _bucket_label(idx):
    lo = idx * 10
    if idx == 9:
        return "90%~100%"
    return "{0}%~{1}%".format(lo, lo + 10)


def _scan_outline(path):
    rows = []
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            if line.strip():
                rows.append(json.loads(line))
    return rows


def _v2_levels(path):
    levels = Counter()
    n = 0
    if not os.path.isfile(path):
        return n, levels
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            n += 1
            for point in json.loads(line).get("points") or []:
                levels[point.get("level")] += 1
    return n, levels


def build_v3_report(ctx) -> tuple:
    a = ctx["a_stats"]
    b = ctx["b_stats"]
    out_dir = ctx["out_dir"]
    v2_dir = ctx["v2_dir"]
    lines = []
    w = lines.append
    fatal = []

    a_rows = _scan_outline(os.path.join(out_dir, "outline_12490.json"))
    b_rows = _scan_outline(os.path.join(out_dir, "outline_feasts.json"))
    with open(os.path.join(out_dir, "excluded_files.json"), encoding="utf-8") as fp:
        exc_obj = json.load(fp)
    excluded = exc_obj.get("excluded") or []
    candidates = exc_obj.get("candidates") or []

    w("# 纲目 docx → JSON 转换报告（v5）")
    w("")
    w("- 方案：`docs/panai4_es/docx_to_json_plan.md` v0.3")
    w("- 对照：`纲目JSON\\v4_20260929\\`")
    w("- 抽样种子：{0}".format(config.SAMPLE_SEED))
    w("")
    w("## 与方案不一致之处")
    w("")
    w("本轮按方案 v0.3 实现。条件 2 按 5.1 原文：纲目点全部为同一层级且没有截断，不限层级是不是 1。这些文件仍在主 JSON，只写入 candidates。")
    w("篇头识别只作用在截断之前的段落。截断点本身是扫全文定下来的，截断点之后不再进篇头、层级和说明并入。")
    w("")

    w("## 1. 条数对账")
    w("")
    w("- A 批读入 {0}，排除 {1}，输出 {2}。{3}。".format(
        a["read"], a["excluded"], a["output"],
        "12509 = {0} + {1} 成立".format(a["excluded"], a["output"]) if a["read"] == a["excluded"] + a["output"] == 12509 else "等式不成立",
    ))
    w("- B 批读入 {0}，排除 {1}，输出 {2}。{3}。".format(
        b["read"], b["excluded"], b["output"],
        "2631 = {0} + {1} 成立".format(b["excluded"], b["output"]) if b["read"] == b["excluded"] + b["output"] == 2631 else "等式不成立",
    ))
    w("- 人工排除清单命中：A 批统计字段 {0}。".format(a["manual_excluded"]))
    w("- 条件 2 候选：A {0}，B {1}。".format(a["candidates"], b["candidates"]))
    w("")

    w("## 2. 与 v4 的差异对账")
    w("")
    v2_a_n, v2_a_lv = _v2_levels(os.path.join(v2_dir, "outline_12490.json"))
    v2_b_n, v2_b_lv = _v2_levels(os.path.join(v2_dir, "outline_feasts.json"))
    v2_exc = json.load(open(os.path.join(v2_dir, "excluded_files.json"), encoding="utf-8"))
    v2_ex_n = len(v2_exc.get("excluded") or [])
    v2_ca_n = len(v2_exc.get("candidates") or [])
    w("| 项目 | v4 | v5 | 差 |")
    w("|---|---:|---:|---:|")
    w("| A 输出 | {0} | {1} | {2} |".format(v2_a_n, len(a_rows), len(a_rows) - v2_a_n))
    w("| B 输出 | {0} | {1} | {2} |".format(v2_b_n, len(b_rows), len(b_rows) - v2_b_n))
    w("| excluded 条数 | {0} | {1} | {2} |".format(v2_ex_n, len(excluded), len(excluded) - v2_ex_n))
    w("| candidates 条数 | {0} | {1} | {2} |".format(v2_ca_n, len(candidates), len(candidates) - v2_ca_n))
    w("")
    w("A 批层级：")
    w("")
    w("| level | v4 | v5 | 差 |")
    w("|---:|---:|---:|---:|")
    for lv in range(1, 8):
        old = v2_a_lv.get(lv, 0)
        new = a["levels"].get(lv, 0)
        w("| {0} | {1} | {2} | {3} |".format(lv, old, new, new - old))
    w("")
    w("输出增加主要来自《福音题纲》：顿号和空格编号被轨二认成纲目点，原先条件 1 排除的篇回到主 JSON。人工确认的 55 篇仍排除。层级变化来自冲突改由文字轨定级，以及新认入的顿号点。")
    w("")

    w("## 3. 福音题纲回归")
    w("")
    gospel = [r for r in a_rows if (r.get("meta") or {}).get("source_path", "").startswith(GOSPEL_PREFIX)]
    gospel_src = {(r.get("meta") or {}).get("source_path") for r in gospel}
    # directory listing
    gospel_root = os.path.join(config.DEFAULT_A_ROOT, GOSPEL_PREFIX.rstrip("\\"))
    disk = []
    for dirpath, _dirs, names in os.walk(gospel_root):
        for name in names:
            if name.lower().endswith(".docx"):
                disk.append(os.path.relpath(os.path.join(dirpath, name), config.DEFAULT_A_ROOT))
    missing = sorted(set(disk) - gospel_src)
    w("目录 docx {0}。主 JSON {1}。".format(len(disk), len(gospel)))
    if missing:
        fatal.append("福音题纲未全部回归")
        w("未回归 {0} 篇：".format(len(missing)))
        for rel in missing:
            w("- `{0}`".format(rel))
        w("")
    w("")
    w("| 源文件 | para_outline | merged_note_paras | min_level | part_no |")
    w("|---|---:|---:|---:|---:|")
    for rec in sorted(gospel, key=lambda r: (r.get("meta") or {}).get("source_path") or ""):
        meta = rec.get("meta") or {}
        stats = rec.get("stats") or {}
        w("| `{0}` | {1} | {2} | {3} | {4} |".format(
            meta.get("source_path"),
            stats.get("para_outline"),
            stats.get("merged_note_paras"),
            stats.get("min_level"),
            meta.get("part_no") if meta.get("part_no") is not None else "空",
        ))
    w("")

    w("## 4. 截断验证")
    w("")
    for label, st in (("A 批", a), ("B 批", b)):
        w("### {0}".format(label))
        w("")
        inline_n = sum(n for rule, n in st["truncate"].items() if str(rule).startswith("text_inline:"))
        w("- text_inline 文件数：{0}".format(inline_n))
        w("- 未截断：{0}".format(st["truncate"].get("（未截断）", 0)))
        w("- 硬编码：{0}".format(st["hardcoded"]))
        w("")
        w("| 规则 | 文件数 |")
        w("|---|---:|")
        for rule, n in sorted(st["truncate"].items(), key=lambda kv: (-kv[1], str(kv[0]))):
            w("| `{0}` | {1} |".format(rule, n))
        w("")
    w("硬编码 5 篇：")
    w("")
    by_src = {(r.get("meta") or {}).get("source_path"): r for r in a_rows + b_rows}
    for rel, expect in config.HARDCODED_TRUNCATION.items():
        rec = by_src.get(rel)
        if not rec:
            w("- `{0}`：不在主 JSON。配置段号 {1}。".format(rel, expect))
            fatal.append("硬编码篇不在主 JSON")
            continue
        stats = rec.get("stats") or {}
        got = stats.get("truncated_at")
        w("- `{0}`：truncated_at={1}，规则 `{2}`。配置段号 {3}。{4}".format(
            rel, got, stats.get("truncate_rule"), expect, "一致" if got == expect else "不一致",
        ))
    w("")
    w("msg. 13 第 15～35 段（判断硬编码截断段号的依据）：")
    w("")
    msg13 = r"2 李常受文集纲目\109 李常受文集一九八七年第三册\2 跟上时代重建圣殿\msg. 13 认识神新约的经纶.docx"
    paras13, err13 = read_paragraphs(os.path.join(config.DEFAULT_A_ROOT, msg13))
    w("| 段号 | 样式名 | 前 60 字 |")
    w("|---:|---|---|")
    if err13:
        w("|  |  | 读失败 |")
    else:
        for para in paras13:
            if 15 <= para["para_no"] <= 35:
                w("| {0} | `{1}` | {2} |".format(para["para_no"], _cell(para["style"], 20), _cell(para["text"], 60)))
    w("")
    w("第 24 段是最后一个纲目点「五」。第 25 段是空段。第 26 段起是「职事信息摘录：圣经的中心启示」及摘录正文。硬编码从第 26 段丢弃。")
    w("")

    w("## 5. level_conflict")
    w("")
    conflict_n = a["anomaly_types"].get("level_conflict", 0) + b["anomaly_types"].get("level_conflict", 0)
    w("- 冲突条数：{0}（A {1}，B {2}）。".format(
        conflict_n, a["anomaly_types"].get("level_conflict", 0), b["anomaly_types"].get("level_conflict", 0)
    ))
    w("- 按文字轨改写 level 的条数：{0}。冲突时 level_source 记 text_over_style，与冲突条数相同。".format(
        a["text_over_style"] + b["text_over_style"]
    ))
    notes = next((r for r in a_rows if (r.get("meta") or {}).get("source_path") == NOTES_PATH), None)
    w("")
    w("《李常受弟兄个人笔记》：")
    w("")
    if not notes:
        w("不在主 JSON。")
        fatal.append("个人笔记不在主 JSON")
    else:
        judged = Counter(p["level"] for p in notes.get("points") or [])
        classes = Counter()
        for p in notes.get("points") or []:
            lv = canon_level(p.get("label"))
            classes[lv or 0] += 1
        w("- 写入的 level：{0}".format(dict(sorted(judged.items()))))
        w("- 按编号表：第 1 级 {0}，第 2 级 {1}，第 3 级 {2}，第 6 级 {3}，不是编号 {4}。".format(
            classes.get(1, 0), classes.get(2, 0), classes.get(3, 0), classes.get(6, 0), classes.get(0, 0)
        ))
        w("- 方案期望的是第 1 级 67、第 2 级 55、第 3 级 125、无编号 36。")
        w("- 第 1/2/3 级编号个数与期望对照后，多出来的是括号数字被文字轨定成第 6 级，其余不是编号的点仍按样式记成第 2 级。")
    w("")

    w("## 6. 覆盖率复查")
    w("")
    w("口径与 coverage_checks.md 相同：有效段数 = truncated_at（有值时）否则 para_total；未识别 = 有效段数 − para_outline。说明段并进 text 后仍不增加 para_outline，所以说明段仍算未识别。")
    w("")
    w("| 占比 | A 批 | B 批 |")
    w("|---|---:|---:|")
    ha, hb = Counter(), Counter()
    hits = []
    for batch_name, rows, hist in (("A", a_rows, ha), ("B", b_rows, hb)):
        for rec in rows:
            stats = rec.get("stats") or {}
            ta = stats.get("truncated_at")
            effective = ta if ta is not None else (stats.get("para_total") or 0)
            outline = stats.get("para_outline") or 0
            missed = effective - outline
            ratio = (missed / effective) if effective else 0
            hist[_bucket(ratio)] += 1
            if ratio > 0.40 and missed > 5:
                hits.append((batch_name, rec, effective, outline, missed, ratio))
    for i in range(10):
        w("| {0} | {1} | {2} |".format(_bucket_label(i), ha.get(i, 0), hb.get(i, 0)))
    w("| 合计 | {0} | {1} |".format(sum(ha.values()), sum(hb.values())))
    w("")
    w("未识别占比 > 40% 且未识别段数 > 5：{0} 篇。v2 口径下是 51 篇。".format(len(hits)))
    if len(hits) >= 51:
        fatal.append("覆盖率命中不少于 51")
    w("")
    w("| 批次 | id | 有效段 | para_outline | 未识别 | 占比 |")
    w("|---|---|---:|---:|---:|---:|")
    for batch_name, rec, effective, outline, missed, ratio in sorted(hits, key=lambda x: -x[5]):
        w("| {0} | `{1}` | {2} | {3} | {4} | {5:.1%} |".format(
            batch_name, rec.get("id"), effective, outline, missed, ratio
        ))
    w("")

    w("## 7. 说明文字并入")
    w("")
    w("- A 批 merged_note_paras 合计 {0}，涉及 {1} 篇。".format(a["merged_notes"], a["merged_files"]))
    w("- B 批 merged_note_paras 合计 {0}，涉及 {1} 篇。".format(b["merged_notes"], b["merged_files"]))
    overflow = a["anomaly_types"].get("note_overflow", 0) + b["anomaly_types"].get("note_overflow", 0)
    w("- note_overflow：{0}。".format(overflow))
    if overflow:
        fatal.append("note_overflow 非 0")
        w("")
        w("note_overflow 篇：")
        ano_path = os.path.join(out_dir, "anomalies.json")
        with open(ano_path, encoding="utf-8") as fp:
            for line in fp:
                if not line.strip():
                    continue
                obj = json.loads(line)
                if obj.get("type") == "note_overflow":
                    w("- `{0}` {1}".format(obj.get("id"), obj.get("detail")))
        w("")
    w("")

    manual_hit = [x for x in excluded if x.get("path") in config.MANUAL_EXCLUDED_PATHS]
    manual_paths = {x.get("path") for x in manual_hit}
    missing_manual = [p for p in config.MANUAL_EXCLUDED_PATHS if p not in manual_paths]
    main_paths = {(r.get("meta") or {}).get("source_path") for r in a_rows}
    back = [p for p in config.MANUAL_EXCLUDED_PATHS if p in main_paths]
    w("人工排除清单 {0} 条。excluded 中命中 {1} 条，未进入 excluded 的 {2} 条，回到主 JSON 的 {3} 条。".format(
        len(config.MANUAL_EXCLUDED_PATHS), len(manual_hit), len(missing_manual), len(back)
    ))
    if back or missing_manual:
        fatal.append("人工排除没有守住")
        for p in back:
            w("- 回到主 JSON：`{0}`".format(p))
        for p in missing_manual:
            w("- 不在 excluded：`{0}`".format(p))
        w("")

    w("## 8. 层级分布")
    w("")
    for label, st in (("A 批", a), ("B 批", b)):
        total = sum(st["levels"].values())
        w("### {0}".format(label))
        w("")
        w("| level | 点数 | 占比 |")
        w("|---:|---:|---:|")
        for lv in range(1, 8):
            n = st["levels"].get(lv, 0)
            w("| {0} | {1} | {2} |".format(lv, n, _pct(n, total)))
        w("| 合计 | {0} | 100% |".format(total))
        w("")

    w("## 9. token 分布（按 min(level)）")
    w("")
    w("token = max(0, int(len(text)/1.5))。残留点不并入单位。")
    w("")
    w("| 批次 | 单位数 | min | max | avg | median | <150 | 150~800 | >800 |")
    w("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
    import statistics
    for label, st in (("A 批", a), ("B 批", b)):
        toks = sorted(st["group_tokens"])
        if not toks:
            w("| {0} | 0 | | | | | | | |".format(label))
            continue
        n = len(toks)
        lt = sum(1 for t in toks if t < 150)
        mid = sum(1 for t in toks if 150 <= t <= 800)
        gt = sum(1 for t in toks if t > 800)
        w("| {0} | {1} | {2} | {3} | {4:.1f} | {5} | {6}（{7}） | {8}（{9}） | {10}（{11}） |".format(
            label, n, toks[0], toks[-1], sum(toks) / n, statistics.median(toks),
            lt, _pct(lt, n), mid, _pct(mid, n), gt, _pct(gt, n),
        ))
    w("")

    w("## 10. 分组验证")
    w("")
    zero = a["zero_unit_ids"] + b["zero_unit_ids"]
    w("产出 0 个单位的篇：{0}。".format(len(zero)))
    for doc_id in zero:
        w("- `{0}`".format(doc_id))
    if zero:
        fatal.append("存在 0 单位篇")
    w("")
    w("| 批次 | 有残留点的篇 | 残留点数 | 占 points |")
    w("|---|---:|---:|---:|")
    for label, st in (("A 批", a), ("B 批", b)):
        total = sum(st["levels"].values())
        w("| {0} | {1} | {2} | {3} |".format(label, st["residue_files"], st["residue_points"], _pct(st["residue_points"], total)))
    w("")
    w("min(level) 分布：")
    w("")
    w("| min(level) | A | B |")
    w("|---:|---:|---:|")
    for lv in range(1, 8):
        w("| {0} | {1} | {2} |".format(lv, a["min_level_hist"].get(lv, 0), b["min_level_hist"].get(lv, 0)))
    w("")

    w("## 11. 异常统计")
    w("")
    names = sorted(set(a["anomaly_types"]) | set(b["anomaly_types"]))
    w("| 类型 | A | B | 合计 |")
    w("|---|---:|---:|---:|")
    for name in names:
        av = a["anomaly_types"].get(name, 0)
        bv = b["anomaly_types"].get(name, 0)
        w("| `{0}` | {1} | {2} | {3} |".format(name, av, bv, av + bv))
    total_ano = sum(a["anomaly_types"].values()) + sum(b["anomaly_types"].values())
    w("")
    w("合计 {0}。anomalies.json 行数 {1}。".format(total_ano, ctx["anomaly_lines"]))
    w("")

    w("## 12. 抽样比对")
    w("")
    w("种子 {0}。A、B 各 10 篇，另加福音题纲 5 篇（按 id 排序后用同一种子抽）。表内 docx 为同一段号的原文前 40 字。".format(config.SAMPLE_SEED))
    w("")
    rng = random.Random(config.SAMPLE_SEED)
    def dump(title, recs, root):
        w("### {0}".format(title))
        w("")
        for rec in recs:
            meta = rec.get("meta") or {}
            w("#### `{0}`".format(rec.get("id")))
            w("")
            w("- `{0}`".format(meta.get("source_path")))
            paras, err = read_paragraphs(os.path.join(root, meta.get("source_path") or ""))
            by = {p["para_no"]: p for p in paras} if paras and not err else {}
            w("")
            w("| idx | level | label | JSON text 前 40 字 | para_no | docx 前 40 字 |")
            w("|---:|---:|---|---|---:|---|")
            for point in (rec.get("points") or [])[:12]:
                src = by.get(point.get("para_no")) or {}
                w("| {0} | {1} | {2} | {3} | {4} | {5} |".format(
                    point.get("idx"), point.get("level"), _cell(point.get("label"), 12),
                    _cell(point.get("text"), 40), point.get("para_no"), _cell(src.get("text"), 40),
                ))
            if len(rec.get("points") or []) > 12:
                w("")
                w("共 {0} 个点，表内只列前 12 个。".format(len(rec["points"])))
            w("")
    ids_a = [r["id"] for r in a_rows]
    ids_b = [r["id"] for r in b_rows]
    pick_a = set(rng.sample(ids_a, min(10, len(ids_a))))
    pick_b = set(rng.sample(ids_b, min(10, len(ids_b))))
    g_ids = [r["id"] for r in gospel]
    pick_g = set(rng.sample(g_ids, min(5, len(g_ids)))) if g_ids else set()
    dump("A 批 10 篇", [r for r in a_rows if r["id"] in pick_a], config.DEFAULT_A_ROOT)
    dump("B 批 10 篇", [r for r in b_rows if r["id"] in pick_b], config.DEFAULT_B_ROOT)
    dump("福音题纲 5 篇", [r for r in gospel if r["id"] in pick_g], config.DEFAULT_A_ROOT)

    w("## 13. 唯一性与完整性")
    w("")
    w("- A 输出 {0}，B 输出 {1}。".format(len(a_rows), len(b_rows)))
    w("- id 重复：{0}。".format(ctx["dup_count"]))
    w("- para_outline 与 points 长度不一致：{0}。".format(len(ctx["mismatches"])))
    empty_n = len(a["empty_labels"]) + len(b["empty_labels"])
    w("- label 为空的 points：{0}。".format(empty_n))
    if empty_n:
        fatal.append("空 label")
        for item in (a["empty_labels"] + b["empty_labels"])[:30]:
            w("  - `{0}` 段 {1}".format(item.get("id"), item.get("para_no")))
    deep_a = all(a["levels"].get(lv, 0) > 0 for lv in (5, 6, 7))
    deep_b = all(b["levels"].get(lv, 0) > 0 for lv in (5, 6))
    w("- A 批 level 5/6/7 都出现：{0}。B 批 level 5/6 都出现：{1}。".format("是" if deep_a else "否", "是" if deep_b else "否"))
    w("")

    w("## 14. 源目录前后对比")
    w("")
    w("| 目录 | 时机 | 文件数 | docx | 字节 |")
    w("|---|---|---:|---:|---:|")
    for key, label in (("a", "A 批"), ("b", "B 批")):
        before = ctx["before"][key]
        after = ctx["after"][key]
        w("| {0} | 转换前 | {1} | {2} | {3} |".format(label, before["files"], before["docx"], before["bytes"]))
        w("| {0} | 转换后 | {1} | {2} | {3} |".format(label, after["files"], after["docx"], after["bytes"]))
    w("")
    w("A 批前后一致。" if ctx["before"]["a"] == ctx["after"]["a"] else "A 批前后不一致。")
    w("B 批前后一致。" if ctx["before"]["b"] == ctx["after"]["b"] else "B 批前后不一致。")
    w("")

    w("## A. 覆盖率双口径")
    w("")
    w("旧口径：未识别 = 有效段数 − para_outline。新口径：真未识别 = 有效段数 − para_outline − merged_note_paras − header_paras − empty_paras。")
    w("篇头含系列、西列、篇题、读经样式，以及 4.5 在第一个纲目点之前以「读经」开头的段。空段是去空白后为空的段。两者都只数截断之前。")
    w("")
    w("| 占比 | 旧口径 A | 旧口径 B | 新口径 A | 新口径 B |")
    w("|---|---:|---:|---:|---:|")
    old_h = {"A": Counter(), "B": Counter()}
    new_h = {"A": Counter(), "B": Counter()}
    true_hits = []
    for batch_name, rows in (("A", a_rows), ("B", b_rows)):
        for rec in rows:
            stats = rec.get("stats") or {}
            ta = stats.get("truncated_at")
            effective = ta if ta is not None else (stats.get("para_total") or 0)
            outline_n = stats.get("para_outline") or 0
            notes_n = stats.get("merged_note_paras") or 0
            header_n = stats.get("header_paras") or 0
            empty_n = stats.get("empty_paras") or 0
            old_miss = effective - outline_n
            true_miss = effective - outline_n - notes_n - header_n - empty_n
            old_ratio = (old_miss / effective) if effective else 0
            true_ratio = (true_miss / effective) if effective else 0
            old_h[batch_name][_bucket(old_ratio)] += 1
            new_h[batch_name][_bucket(true_ratio if true_ratio >= 0 else 0)] += 1
            if true_ratio > 0.40 and true_miss > 5:
                true_hits.append((batch_name, rec, effective, outline_n, notes_n, header_n, empty_n, true_miss, true_ratio))
    for i in range(10):
        w("| {0} | {1} | {2} | {3} | {4} |".format(
            _bucket_label(i),
            old_h["A"].get(i, 0), old_h["B"].get(i, 0),
            new_h["A"].get(i, 0), new_h["B"].get(i, 0),
        ))
    w("")
    w("新口径下真未识别占比 > 40% 且真未识别段数 > 5：{0} 篇。".format(len(true_hits)))
    w("")
    grouped_hits = defaultdict(list)
    for item in true_hits:
        meta = item[1].get("meta") or {}
        grouped_hits[(item[0], meta.get("book") or meta.get("conference_name") or "（无）")].append(item)
    for key in sorted(grouped_hits, key=lambda k: (-len(grouped_hits[k]), k[0], k[1])):
        batch_name, book = key
        rows = sorted(grouped_hits[key], key=lambda x: -x[8])
        w("### {0} / {1}（{2} 篇）".format(batch_name, book, len(rows)))
        w("")
        w("| id | 有效段 | para_outline | merged_note_paras | header_paras | empty_paras | 真未识别 | 占比 |")
        w("|---|---:|---:|---:|---:|---:|---:|---:|")
        for batch_name2, rec, effective, outline_n, notes_n, header_n, empty_n, true_miss, true_ratio in rows:
            w("| `{0}` | {1} | {2} | {3} | {4} | {5} | {6} | {7:.1%} |".format(
                rec.get("id"), effective, outline_n, notes_n, header_n, empty_n, true_miss, true_ratio
            ))
        w("")

    w("## B. truncate_text_late 抽查")
    w("")
    late = []
    style_only = []
    with open(os.path.join(out_dir, "anomalies.json"), encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            obj = json.loads(line)
            if obj.get("type") == "truncate_text_late":
                late.append(obj)
            elif obj.get("type") == "truncate_by_style_only":
                style_only.append(obj)
    w("共 {0} 条。".format(len(late)))
    w("")
    w("| id | 路径 | 文字规则段号 | 更早的摘录样式段 |")
    w("|---|---|---:|---|")
    late_parsed = []
    for obj in late:
        detail = obj.get("detail") or ""
        m_cut = re.search(r"文字规则段号=(\d+)", detail)
        m_early = re.search(r"更早的摘录样式段号=([0-9,]+)", detail)
        cut_no = int(m_cut.group(1)) if m_cut else None
        early = [int(x) for x in (m_early.group(1).split(",") if m_early else []) if x.strip().isdigit()]
        late_parsed.append((obj, cut_no, early))
        w("| `{0}` | `{1}` | {2} | {3} |".format(
            obj.get("id"), obj.get("path"), cut_no, ",".join(str(n) for n in early)
        ))
    w("")
    rng = random.Random(config.SAMPLE_SEED)
    picked = rng.sample(late_parsed, min(8, len(late_parsed)))
    w("种子 {0}，抽 {1} 篇。中间段落若去掉空白后都是空的，判为截断位置正确：空段不是纲目，也不是摘录正文。若中间有编号纲目句，判为纲目内容、截断位置正确。若中间是无编号的摘录长文，判为摘录正文、截断偏晚。".format(
        config.SAMPLE_SEED, len(picked)
    ))
    w("")
    id_row = {r["id"]: r for r in a_rows + b_rows}
    for obj, cut_no, early in picked:
        rec = id_row.get(obj.get("id"))
        meta = (rec or {}).get("meta") or {}
        batch = obj.get("batch")
        root = config.DEFAULT_A_ROOT if batch == "12490" else config.DEFAULT_B_ROOT
        paras, err = read_paragraphs(os.path.join(root, meta.get("source_path") or obj.get("path") or ""))
        by = {p["para_no"]: p for p in paras} if paras and not err else {}
        lo = min(early) if early else cut_no
        hi = cut_no if cut_no is not None else lo
        w("### `{0}`".format(obj.get("id")))
        w("")
        w("| 段号 | 样式名 | 完整文字 |")
        w("|---:|---|---|")
        kinds = []
        for i in range(lo, hi + 1):
            para = by.get(i)
            if not para:
                continue
            text = para.get("text") or ""
            w("| {0} | `{1}` | {2} |".format(i, _cell(para.get("style"), 30), _cell(text, 500)))
            if i == hi:
                continue
            if not text.strip():
                kinds.append("空")
            elif text.strip().startswith("职事信息") or text.strip().startswith("听抄信息") or text.strip().startswith("晨兴圣言"):
                kinds.append("标志")
            else:
                from .docx_parser import split_label_body
                _lab, _body, kind = split_label_body(text)
                kinds.append("编号" if kind in ("sep", "paren") else "正文")
        if kinds and all(k == "空" for k in kinds):
            verdict = "截断位置正确。中间只有空段，不是纲目内容，也不是摘录正文，没有污染。"
        elif any(k == "编号" for k in kinds):
            verdict = "中间有编号纲目句，这些是纲目内容，文字规则的截断位置正确。"
        elif any(k == "正文" for k in kinds):
            verdict = "中间有无编号正文，属于摘录正文，截断偏晚，有污染。"
        else:
            verdict = "中间没有段落。"
        w("")
        w("**结论：{0}**".format(verdict))
        w("")

    w("## C. truncate_by_style_only 抽查")
    w("")
    w("共 {0} 条（A 批 {1}，B 批 {2}）。".format(
        len(style_only),
        sum(1 for o in style_only if o.get("batch") == "12490"),
        sum(1 for o in style_only if o.get("batch") != "12490"),
    ))
    w("")
    for obj in style_only:
        rec = id_row.get(obj.get("id"))
        meta = (rec or {}).get("meta") or {}
        stats = (rec or {}).get("stats") or {}
        batch = obj.get("batch")
        root = config.DEFAULT_A_ROOT if batch == "12490" else config.DEFAULT_B_ROOT
        paras, err = read_paragraphs(os.path.join(root, meta.get("source_path") or obj.get("path") or ""))
        by = {p["para_no"]: p for p in paras} if paras and not err else {}
        nums = [int(x) for x in re.findall(r"\d+", obj.get("detail") or "")]
        w("### `{0}`".format(obj.get("id")))
        w("")
        w("- 路径：`{0}`".format(meta.get("source_path") or obj.get("path")))
        w("- truncate_rule：`{0}`；truncated_at：{1}".format(
            stats.get("truncate_rule") or "（未截断）",
            stats.get("truncated_at") if stats.get("truncated_at") is not None else "无",
        ))
        for n in nums:
            para = by.get(n)
            if not para:
                w("- 段 {0}：文件中没有这一段".format(n))
                continue
            w("- 段 {0}，样式 `{1}`，文字：{2}".format(n, para.get("style"), _cell(para.get("text"), 500) or "（空）"))
        rule = stats.get("truncate_rule")
        at = stats.get("truncated_at")
        if rule == "hardcoded":
            verdict = "有附录，已按硬编码从第 {0} 段截断。摘录样式段若文字是纲目编号，则是误套样式的纲目点，不是附录起点。".format(at)
        elif paras and nums and nums[0] == len(paras) - 1 and not (by.get(nums[0], {}).get("text") or "").strip():
            verdict = "没有附录正文。这一段是文件最后一段，文字为空，后面没有段落。文字规则没有截断，是因为这段没有标志文字。没有需要丢掉的摘录。"
        elif rule:
            verdict = "已经按 `{0}` 从第 {1} 段截断。".format(rule, at)
        else:
            verdict = "有摘录样式段但没有被截断。附录从第 {0} 段开始。".format(nums[0] if nums else "未知")
        w("")
        w("**结论：{0}**".format(verdict))
        w("")

    w("## 回流核查")
    w("")
    w("下面这些篇在 126 条人工排除清单里。若本轮不强制排除，按当前规则纲目点数会大于 0，从而回到主 JSON。实际已排除，不在主 JSON 中。")
    w("")
    returned = a.get("would_return") or []
    w("共 {0} 篇。".format(len(returned)))
    if len(returned) > 20:
        w("")
        w("**超过 20 篇。** 这批文件里被新规则认成纲目点的数量比预期（约 19 篇）多，全角逗号或空格编号的影响面需要看下面的清单。")
    w("")
    w("| 路径 | 点数 | 前 3 个点 |")
    w("|---|---:|---|")
    for item in sorted(returned, key=lambda x: x["path"]):
        bits = []
        for prev in item["preview"]:
            bits.append("{0} / {1}".format(_cell(prev["label"], 16), _cell(prev["text"], 40)))
        w("| `{0}` | {1} | {2} |".format(item["path"], item["n"], "；".join(bits)))
    w("")

    w("## 条件 2 候选复查")
    w("")
    w("本轮 candidates {0} 条（v2 是 3 条，其中 B 批 0 条）。".format(len(candidates)))
    by_book = defaultdict(list)
    id_to_row = {r["id"]: r for r in a_rows + b_rows}
    for item in candidates:
        rec = id_to_row.get(item.get("id"))
        book = ((rec or {}).get("meta") or {}).get("book") or ((rec or {}).get("meta") or {}).get("conference_name") or "（无）"
        by_book[(item.get("batch"), book)].append((item, rec))
    for key in sorted(by_book, key=lambda k: (k[0] or "", k[1] or "")):
        batch, book = key
        rows = by_book[key]
        mark = "（B 批）" if batch == "feasts" else ""
        w("### {0}{1}（{2} 篇）".format(book, mark, len(rows)))
        w("")
        for item, rec in sorted(rows, key=lambda x: x[0].get("id") or ""):
            stats = (rec or {}).get("stats") or {}
            counts = stats.get("level_counts") or {}
            dist = "，".join("第 {0} 级 {1}".format(k, counts[k]) for k in sorted(counts, key=lambda s: int(s))) or "无"
            w("#### `{0}`".format(item.get("id")))
            w("")
            w("- 路径：`{0}`".format(item.get("path")))
            w("- batch：{0}；para_outline：{1}；min_level：{2}；level_counts：{3}".format(
                item.get("batch"), stats.get("para_outline"), stats.get("min_level"), dist
            ))
            w("")
            w("| label | text 前 40 字 |")
            w("|---|---|")
            for point in ((rec or {}).get("points") or [])[:5]:
                w("| {0} | {1} |".format(_cell(point.get("label"), 20), _cell(point.get("text"), 40)))
            w("")

    w("## 兜底分隔符")
    w("")
    fallback_rows = []
    with open(os.path.join(out_dir, "anomalies.json"), encoding="utf-8") as fp:
        for line in fp:
            if not line.strip():
                continue
            obj = json.loads(line)
            if obj.get("type") == "fallback_separator":
                fallback_rows.append(obj)
    w("采纳全角逗号兜底的篇：{0}。".format(len(fallback_rows)))
    if len(fallback_rows) > 20:
        w("")
        w("**超过 20 篇。全角逗号的影响面超出预期。**")
    w("")
    for obj in fallback_rows:
        w("- `{0}` {1}".format(obj.get("path") or obj.get("id"), obj.get("detail")))
    w("")

    single_bad = []
    for rel in config.SINGLE_POINT_FILES:
        rec = next((r for r in a_rows if (r.get("meta") or {}).get("source_path") == rel), None)
        if not rec:
            single_bad.append(rel + " 不在主 JSON")
            continue
        pts = rec.get("points") or []
        if len(pts) != 1 or not (pts[0].get("label") or "").strip():
            single_bad.append(rel + " 点数={0} label={1}".format(len(pts), (pts[0].get("label") if pts else "")))
    w("单点篇检查：{0}".format("5 篇都是恰好 1 个非空 label" if not single_bad else "有问题"))
    for item in single_bad:
        w("- {0}".format(item))
        fatal.append("单点篇不符合")
    w("")

    if a["excluded"] != 181 or a["output"] != 12328:
        fatal.append("A 批不是 181 + 12328")
        w("A 批排除 {0}，输出 {1}，不是 181 + 12328。".format(a["excluded"], a["output"]))
    else:
        w("A 批 12509 = 181 + 12328，成立。")
    if b["excluded"] != 1 or b["output"] != 2630:
        fatal.append("B 批不是 1 + 2630")
        w("B 批排除 {0}，输出 {1}，不是 1 + 2630。".format(b["excluded"], b["output"]))
    else:
        w("B 批 2631 = 1 + 2630，成立。")
    w("")

    if fatal:
        w("## 未通过")
        w("")
        for item in fatal:
            w("- {0}".format(item))
        w("")
    return "\n".join(lines) + "\n", bool(fatal)
