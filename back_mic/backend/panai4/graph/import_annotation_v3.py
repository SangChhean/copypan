# -*- coding: utf-8 -*-
"""neo4j-v4 标注导入 v3：按 words[] 指定字段取字符串作为标注值。

不修改 import_annotation.py / import_annotation_v2.py。
复用 v1 连接/快照/SET，以及 v2 的 expect-anno SHA 工具。

与 v2 category-words 的差异：
  · --value-field 指定取值字段（如 phrasing），不写死 category
  · 不要求 categories / 四档计数闸门
  · 可选写出顶层说明文档（--meta-doc）
  · batch 默认 50

用法（在 back_mic/backend 下）:
    python -m panai4.graph.import_annotation_v3 --stage check \\
        --file "..." --name mutuality --value-field phrasing \\
        --expect-anno devine_argument=187 --expect-anno intrinsic_significance=2372 \\
        --meta-doc docs/panai4_graph/annotation_mutuality_definition.md \\
        --report docs/panai4_graph/import_mutuality.md
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from neo4j import READ_ACCESS, WRITE_ACCESS, GraphDatabase

from panai4.graph import import_annotation as v1
from panai4.graph import import_annotation_v2 as v2

_REPO = v1._REPO
_LOG_DIR = v1._LOG_DIR
_PROP_NAME_RE = v1._PROP_NAME_RE
_BATCH = 50
_PAREN_INNERS = {inner for _o, inner in v1._PAREN_PAIRS}
_DEFAULT_ALIASES = {"路得马丁": "路德马丁"}


def _parse_aliases(items: list[str]) -> dict[str, str]:
    out = dict(_DEFAULT_ALIASES)
    for item in items:
        if "=" not in item:
            raise SystemExit(f"--alias 格式应为 旧=新，收到: {item}")
        a, b = item.split("=", 1)
        out[a.strip()] = b.strip()
    return out


def write_meta_doc(data: dict, path: Path, anno_name: str, value_field: str) -> None:
    lines = [
        f"# 标注 `{anno_name}` 说明",
        "",
        f"来源：可导入资料中对应 JSON 的顶层说明字段。标注值取各词条的 `{value_field}`。",
        "含斜杠的说法原样保存、未拆分；顶层说明没有放入图谱节点。",
        "",
    ]
    for key in ("tag", "definition", "note", "count"):
        if key not in data:
            continue
        lines.append(f"## {key}")
        lines.append("")
        val = data[key]
        if isinstance(val, str):
            lines.append(val)
        else:
            lines.append(str(val))
        lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_report(
    state: dict,
    import_info: dict | None,
    verify: dict | None,
    env: dict,
    log_path: Path,
    report_path: Path,
    stopped: str | None,
) -> None:
    base = state["baseline"]
    plan = state["plan_summary"]
    anno = state["anno_name"]
    lines: list[str] = []
    a = lines.append
    a(f"# neo4j-v4 导入标注 `{anno}` 报告（v3 / field-words）")
    a("")
    a(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}；脚本：`panai4.graph.import_annotation_v3`。")
    a(f"源文件：`{state['file']}`。只 SET `n.{anno}` = `{state['value_field']}` 字符串；未运行 build_v4.py；未打印密码。")
    a("")
    a("## 摘要")
    a("")
    a(
        f"1. **基线**：节点={base['nodes_total']} {base['labels']}；关系={base['rels_total']} {base['by_type']}；"
        f"same_as={base['same_as_n']}/{base['no_same_as_n']}；TP keys={base['node_keys']['Truth_Point']}；"
        f"expect_anno={state.get('expect_anno')}。"
    )
    a(
        f"2. **JSON**：words={plan['n_records']}；顶层 count={plan.get('top_count')}；相等={plan.get('count_eq')}；"
        f"含斜杠={plan.get('slash_n')} 前10={plan.get('slash_sample')}；phrasing 长度={plan.get('len_stats')}；"
        f"空值={plan.get('empty_values')}；城市={plan.get('has_city')}；额外键={plan.get('extra_keys') or '无'}。"
    )
    a(
        f"3. **匹配**：找到={plan['found_n']}；找不到={plan['missing']}；括号内={plan['hit_inner']}；"
        f"多对一={plan['multi'] or '无'}；别名={plan.get('alias_detail') or '无'}。"
    )
    if import_info and not import_info.get("aborted"):
        a(f"4. **写入**：写入={import_info.get('written')}；失败={import_info.get('failed')}。")
    elif import_info:
        a(f"4. **写入中止**：{import_info}")
    else:
        a(f"4. **写入**：尚未 import；拟写入={plan['write_count']}。")
    if verify:
        a(
            f"5. **验证**：ok={verify['ok']}；非空={verify['anno_count']}；括号内={verify['inner_anno']['c']}；"
            f"内容差={verify['content_diff']}；其他标注SHA={verify.get('other_anno_sha')}；fails={verify['fails'] or '无'}。"
        )
    else:
        a("5. **验证**：尚未 verify。")
    a(f"6. **脚本**：新建 import_annotation_v3（复用 v1/v2）。差异：{state.get('v3_diff')}。")
    a(
        f"7. **待决**：stopped={stopped}；check_ok={state.get('check_ok')}；fails={state.get('fails') or '无'}。"
    )
    if state.get("meta_doc"):
        a(f"- 说明文档：`{state['meta_doc']}`")
    a("")
    a("## 明细")
    a(f"- SHA ok={state.get('sha_ok')} n={state['sha_before']['n']}")
    a("## I. import")
    a("未执行。" if not import_info else f"```json\n{json.dumps(import_info, ensure_ascii=False, indent=2)}\n```")
    a("## V. verify")
    if not verify:
        a("未执行。")
    else:
        a(f"- samples: {verify.get('samples')}")
        a(f"- node_keys: {verify.get('node_keys')}")
    a("")
    a("## 最终验证")
    draft = "\n".join(lines)
    leaked = bool(env["pass4"] and env["pass4"] in draft)
    log_text = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    leaked_log = bool(env["pass4"] and env["pass4"] in log_text)
    a(f"- 只做了 SET {anno}：是（若已 import）")
    a("- 未运行 build_v4.py：是")
    a(f"- 报告密码检查：{'不通过' if leaked else '通过'}；日志：{'不通过' if leaked_log else '通过'}")
    a("- 未修改 import_annotation.py / import_annotation_v2.py")
    a("")
    text = "\n".join(lines) + "\n"
    if env["pass4"] and env["pass4"] in text:
        raise SystemExit("中止：报告含密码")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8")


def stage_check(
    env: dict,
    log: v1.Logger,
    file_path: Path,
    anno_name: str,
    value_field: str,
    report_path: Path,
    meta_doc: Path | None,
    expect_anno: dict[str, int],
    aliases: dict[str, str],
) -> int:
    log.log(f"v3 check file={file_path} name={anno_name} value_field={value_field}")
    sha_before = v1._sha_import_dir()
    data = json.loads(file_path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or "words" not in data:
        raise SystemExit("顶层须为含 words 的 dict")
    words = data["words"]
    if not isinstance(words, list):
        raise SystemExit("words 须为 list")

    if meta_doc is not None:
        write_meta_doc(data, meta_doc, anno_name, value_field)
        log.log(f"wrote meta doc {meta_doc}")

    top_keys = list(data.keys())
    top_count = data.get("count")
    count_eq = top_count == len(words)
    extra_keys = sorted(set().union(*(set(w.keys()) for w in words if isinstance(w, dict))) - {"no", "name", value_field})
    dup_names = [n for n, c in Counter(w.get("name") for w in words).items() if c > 1]
    empty_values = [w.get("name") for w in words if not str(w.get(value_field) or "").strip()]
    slash_items = [
        {"name": w["name"], "value": w.get(value_field)}
        for w in words
        if isinstance(w.get(value_field), str) and "/" in w[value_field]
    ]
    lengths = [len(str(w.get(value_field) or "")) for w in words]
    lengths_sorted = sorted(lengths)
    len_stats = {
        "min": lengths_sorted[0] if lengths_sorted else None,
        "median": int(statistics.median(lengths_sorted)) if lengths_sorted else None,
        "max": lengths_sorted[-1] if lengths_sorted else None,
    }
    has_city = any(w.get("name") == "城市" for w in words)

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            base = v1.snapshot_graph(session)
            fails = v1.gate_baseline(base)
            tp_keys = {r["key"]: r["nonempty"] for r in base["node_keys"]["Truth_Point"]}
            expect_keys = {"name", "same_as"} | set(expect_anno)
            if set(tp_keys) != expect_keys:
                fails.append(f"基线 Truth_Point 标注名 {set(tp_keys)} ≠ {expect_keys}")
            existing_hashes: dict[str, dict[str, str]] = {}
            for prop, expected_n in expect_anno.items():
                actual_n = v2._anno_nonempty(session, prop)
                if actual_n != expected_n:
                    fails.append(f"已有标注 {prop} 非空 {actual_n} ≠ {expected_n}")
                amap = v2._fetch_anno_map(session, prop)
                existing_hashes[prop] = {n: v2._sha_text(v) for n, v in amap.items()}

            tp_rows = v1._run(
                session,
                """
                MATCH (n:Truth_Point)
                RETURN n.name AS name,
                       CASE WHEN n.same_as IS NULL OR toString(n.same_as)='' THEN null
                            ELSE n.same_as END AS same_as
                """,
            )
            by_name = {r["name"]: r for r in tp_rows}

            found = []
            missing = []
            hit_inner = []
            alias_detail = []
            target_to_sources: dict[str, list[str]] = {}
            write_rows = []

            for w in words:
                src = w.get("name")
                raw_val = w.get(value_field)
                value = raw_val if isinstance(raw_val, str) else ("" if raw_val is None else str(raw_val))
                target = aliases.get(src, src)
                used_alias = src in aliases and aliases[src] != src
                if target not in by_name:
                    missing.append(src)
                    continue
                if by_name[target]["same_as"] is not None:
                    hit_inner.append({"name": src, "target": target, "same_as": by_name[target]["same_as"]})
                    continue
                # also reject if source name itself is an inner without alias remap needed - already covered
                target_to_sources.setdefault(target, []).append(src)
                if used_alias:
                    alias_detail.append({"src": src, "target": target, "value": value})
                found.append(src)
                write_rows.append({"name": target, "value": value, "source_name": src})

            multi = {t: srcs for t, srcs in target_to_sources.items() if len(srcs) > 1}
    except Exception as exc:
        raise SystemExit("check 失败: " + v1._redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    sha_after = v1._sha_import_dir()
    sha_ok = sha_before["hashes"] == sha_after["hashes"]

    if not count_eq:
        fails.append(f"count {top_count} ≠ words 记录数 {len(words)}")
    if empty_values:
        fails.append(f"{value_field} 空值 {len(empty_values)}: {empty_values[:20]}")
    if dup_names:
        fails.append(f"name 重复: {dup_names}")
    if missing:
        fails.append(f"找不到 {len(missing)}: {missing}")
    if hit_inner:
        fails.append(f"括号内节点 {len(hit_inner)}: {hit_inner}")
    if multi:
        fails.append(f"多对一 {len(multi)}: {multi}")
    if any(not r["value"].strip() for r in write_rows):
        fails.append("拟写入含空字符串")
    if not sha_ok:
        fails.append("SHA256 变化")

    # dedupe write_rows by target name (should be 1:1)
    write_map = {r["name"]: r["value"] for r in write_rows}
    final_rows = [{"name": n, "value": v} for n, v in sorted(write_map.items())]

    state = {
        "version": 3,
        "mode": "field-words",
        "check_ok": not fails,
        "fails": fails,
        "anno_name": anno_name,
        "value_field": value_field,
        "file": str(file_path),
        "expect_anno": expect_anno,
        "aliases": aliases,
        "meta_doc": str(meta_doc) if meta_doc else None,
        "v3_diff": [
            "新建 v3：--value-field 指定 words[] 字段作为标注字符串",
            "不写死 category；无四档计数闸门",
            "可选 --meta-doc 写出顶层 tag/definition/note/count",
            "batch 默认 50；复用 v1 SET 与 v2 expect-anno SHA",
        ],
        "baseline": {k: v for k, v in base.items() if k != "tp_props"},
        "tp_props": base["tp_props"],
        "existing_anno_sha256": existing_hashes,
        "plan_summary": {
            "top_keys": top_keys,
            "top_count": top_count,
            "n_records": len(words),
            "count_eq": count_eq,
            "extra_keys": extra_keys,
            "dup_names": dup_names,
            "empty_values": empty_values,
            "slash_n": len(slash_items),
            "slash_sample": slash_items[:10],
            "len_stats": len_stats,
            "has_city": has_city,
            "found_n": len(found),
            "missing": missing,
            "hit_inner": hit_inner,
            "multi": multi,
            "alias_detail": alias_detail,
            "write_count": len(final_rows),
            "write_names": [r["name"] for r in final_rows],
        },
        "write_rows": final_rows,
        "payloads": {r["name"]: r["value"] for r in final_rows},
        "sha_before": sha_before,
        "sha_after_check": sha_after,
        "sha_ok": sha_ok,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    v1.save_state(anno_name, state)
    write_report(state, None, None, env, log.path, report_path, None if not fails else "check")
    for f in fails:
        log.log("GATE FAIL: " + f)
    if fails:
        log.log("闸门未通过，停止。未进入 import。")
        return 2
    log.log(f"闸门通过。拟写入 {len(final_rows)}；slash={len(slash_items)}；len={len_stats}")
    return 0


def stage_import(env: dict, log: v1.Logger, file_path: Path, anno_name: str, report_path: Path) -> int:
    state = v1.load_state(anno_name)
    if state.get("version") != 3 or state.get("mode") != "field-words" or not state.get("check_ok"):
        log.log("v3 check 未通过或不匹配，拒绝 import")
        return 2
    if Path(state["file"]).resolve() != file_path.resolve():
        log.log("文件路径与 check 不一致")
        return 2
    base = state["baseline"]
    write_rows = state["write_rows"]
    expect_anno = state.get("expect_anno") or {}
    log.log(f"v3 import 拟写入 {len(write_rows)}")

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    written = 0
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=WRITE_ACCESS) as session:
            now = v1.snapshot_graph(session)
            light_now = {k: now[k] for k in ("nodes_total", "labels", "rels_total", "by_type", "same_as_n")}
            light_base = {k: base[k] for k in ("nodes_total", "labels", "rels_total", "by_type", "same_as_n")}
            if light_now != light_base:
                log.log("I1 失败：基线变化")
                write_report(state, {"aborted": True, "reason": "I1"}, None, env, log.path, report_path, "import-I1")
                return 2
            for prop, expected_n in expect_anno.items():
                if v2._anno_nonempty(session, prop) != expected_n:
                    log.log(f"I1 失败：{prop} 非空变化")
                    write_report(state, {"aborted": True, "reason": prop}, None, env, log.path, report_path, "import-I1")
                    return 2
            log.log("I1 通过")
            for i in range(0, len(write_rows), _BATCH):
                batch = write_rows[i : i + _BATCH]
                rows = [{"name": r["name"], "value": r["value"]} for r in batch]
                updated = session.execute_write(v1._set_batch, anno_name, rows)
                if updated != len(batch):
                    log.log(f"GATE FAIL: 批次 {updated}≠{len(batch)}")
                    write_report(
                        state,
                        {
                            "aborted": True,
                            "written": written,
                            "failed_batch_start": i,
                            "failed_names": [r["name"] for r in batch],
                        },
                        None,
                        env,
                        log.path,
                        report_path,
                        "import-batch",
                    )
                    return 2
                written += updated
                log.log(f"batch {i}-{i+len(batch)-1} updated={updated} cumulative={written}")
    except Exception as exc:
        raise SystemExit("import 失败: " + v1._redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    info = {"aborted": False, "written": written, "failed": 0, "expected": len(write_rows)}
    state["import"] = info
    v1.save_state(anno_name, state)
    write_report(state, info, None, env, log.path, report_path, None)
    log.log(f"import 完成 written={written}")
    return 0


def stage_verify(env: dict, log: v1.Logger, file_path: Path, anno_name: str, report_path: Path) -> int:
    state = v1.load_state(anno_name)
    if state.get("version") != 3 or state.get("mode") != "field-words":
        log.log("状态不是 v3 field-words")
        return 2
    base = state["baseline"]
    plan = state["plan_summary"]
    payloads = state["payloads"]
    expected_write = plan["write_count"]
    expect_anno = state.get("expect_anno") or {}
    existing_sha = state.get("existing_anno_sha256") or {}
    sha_before = state["sha_before"]
    log.log("v3 verify")

    # samples
    slash_names = [x["name"] for x in plan.get("slash_sample") or []][:3]
    sample_names = list(slash_names)
    for n in ("爱", "爱弟兄"):
        if n not in sample_names:
            sample_names.append(n)
    # longest 2
    scored = sorted(((len(v), n) for n, v in payloads.items()), reverse=True)
    for _, n in scored[:2]:
        if n not in sample_names:
            sample_names.append(n)

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            now = v1.snapshot_graph(session)
            anno_count = v2._anno_nonempty(session, anno_name)
            inner_anno = v1._run(
                session,
                f"""
                MATCH (n:Truth_Point)
                WHERE n.same_as IS NOT NULL AND toString(n.same_as) <> ''
                  AND n.{anno_name} IS NOT NULL
                RETURN count(n) AS c, collect(n.name) AS names
                """,
            )[0]
            stored = v2._fetch_anno_map(session, anno_name)
            samples = []
            for name in sample_names:
                rows = v1._run(
                    session,
                    f"MATCH (n:Truth_Point {{name:$name}}) RETURN n.{anno_name} AS value",
                    {"name": name},
                )
                if not rows:
                    samples.append({"name": name, "present": False})
                else:
                    val = rows[0]["value"]
                    samples.append(
                        {
                            "name": name,
                            "value": v1._trunc(val, 80) if isinstance(val, str) else val,
                            "length": len(val) if isinstance(val, str) else None,
                        }
                    )
            other_sha_check = {}
            for prop, before_map in existing_sha.items():
                now_map = v2._fetch_anno_map(session, prop)
                now_sha = {n: v2._sha_text(v) for n, v in now_map.items()}
                other_sha_check[prop] = {
                    "before_n": len(before_map),
                    "now_n": len(now_map),
                    "sha_mismatch": sum(1 for n, h in before_map.items() if now_sha.get(n) != h),
                    "only_before": sorted(set(before_map) - set(now_map))[:10],
                    "only_now": sorted(set(now_map) - set(before_map))[:10],
                }
    except Exception as exc:
        raise SystemExit("verify 失败: " + v1._redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    sha_now = v1._sha_import_dir()
    fails = []
    if anno_count != expected_write:
        fails.append(f"V1 非空 {anno_count}≠{expected_write}")
    if inner_anno["c"] != 0:
        fails.append(f"V1 括号内有标注 {inner_anno}")

    if now["nodes_total"] != base["nodes_total"] or now["labels"] != base["labels"]:
        fails.append("V2 节点变化")
    if now["rels_total"] != base["rels_total"] or now["by_type"] != base["by_type"]:
        fails.append("V2 关系变化")
    base_map = {r["name"]: r.get("same_as") for r in state["tp_props"]}
    now_map = {r["name"]: r.get("same_as") for r in now["tp_props"]}
    diff_props = sum(1 for k, v in base_map.items() if now_map.get(k) != v)
    if diff_props or set(base_map) != set(now_map):
        fails.append(f"V2 name/same_as 不同={diff_props}")
    for prop, chk in other_sha_check.items():
        if chk["sha_mismatch"] or chk["only_before"] or chk["only_now"] or chk["now_n"] != chk["before_n"]:
            fails.append(f"V2 已有标注 {prop} 变化 {chk}")
        if expect_anno.get(prop) is not None and chk["now_n"] != expect_anno[prop]:
            fails.append(f"V2 {prop} 非空 {chk['now_n']}≠{expect_anno[prop]}")

    content_diff = 0
    content_diff_names = []
    for name, val in payloads.items():
        if stored.get(name) != val:
            content_diff += 1
            if len(content_diff_names) < 20:
                content_diff_names.append((name, stored.get(name), val))
    if content_diff:
        fails.append(f"V3 不一致 {content_diff}: {content_diff_names}")

    tp_keys = {r["key"] for r in now["node_keys"]["Truth_Point"]}
    expect_keys = {"name", "same_as", anno_name} | set(expect_anno)
    if tp_keys != expect_keys:
        fails.append(f"V4 标注名 {tp_keys} ≠ {expect_keys}")
    for lab in ("Trunk", "Branch"):
        if {r["key"] for r in now["node_keys"][lab]} != {"name"}:
            fails.append(f"V4 {lab} 标注异常")

    if sha_now["hashes"] != sha_before["hashes"]:
        fails.append("V5 SHA 变化")

    def _ci_sig(rows):
        out = []
        for r in rows:
            out.append(
                {
                    k: r.get(k)
                    for k in ("name", "type", "entityType", "labelsOrTypes", "properties", "state")
                    if k in r
                }
            )
        return sorted(out, key=lambda x: str(x.get("name")))

    if _ci_sig(now["constraints"]) != _ci_sig(base["constraints"]):
        fails.append("V5 CONSTRAINTS 变化")
    if _ci_sig(now["indexes"]) != _ci_sig(base["indexes"]):
        fails.append("V5 INDEXES 变化")

    verify = {
        "ok": not fails,
        "fails": fails,
        "anno_count": anno_count,
        "inner_anno": inner_anno,
        "content_diff": content_diff,
        "content_diff_names": content_diff_names,
        "other_anno_sha": other_sha_check,
        "samples": samples,
        "node_keys": now["node_keys"],
        "nodes_total": now["nodes_total"],
        "labels": now["labels"],
        "rels_total": now["rels_total"],
        "by_type": now["by_type"],
        "sha_ok": sha_now["hashes"] == sha_before["hashes"],
    }
    state["verify"] = verify
    v1.save_state(anno_name, state)
    write_report(state, state.get("import"), verify, env, log.path, report_path, None if not fails else "verify")
    for f in fails:
        log.log("VERIFY FAIL: " + f)
    if fails:
        return 2
    log.log("verify 全部通过")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="导入 Truth_Point 标注到 neo4j-v4（v3 field-words）")
    parser.add_argument("--stage", required=True, choices=["check", "import", "verify"])
    parser.add_argument("--file", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--value-field", required=True, help="words[] 中作为标注值的字段，如 phrasing")
    parser.add_argument("--report", default="")
    parser.add_argument("--meta-doc", default="", help="顶层说明文档路径")
    parser.add_argument("--expect-anno", action="append", default=[])
    parser.add_argument("--alias", action="append", default=[])
    args = parser.parse_args()

    if not _PROP_NAME_RE.fullmatch(args.name):
        raise SystemExit(f"标注名必须是合法标识符: {args.name}")
    file_path = Path(args.file)
    if not file_path.is_file():
        raise SystemExit(f"文件不存在: {file_path}")
    report_path = Path(args.report) if args.report else v1.default_report(args.name)
    meta_doc = Path(args.meta_doc) if args.meta_doc else None
    expect_anno = v2._parse_expect_anno(args.expect_anno)
    aliases = _parse_aliases(args.alias)

    env = v1._load_env()
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = v1.Logger(_LOG_DIR / f"import_annotation_v3_{args.name}_{v1._now()}.log", env["pass4"])
    log.log(f"stage={args.stage} name={args.name} value_field={args.value_field}（v3；密码不记录）")

    if args.stage == "check":
        return stage_check(
            env, log, file_path, args.name, args.value_field, report_path, meta_doc, expect_anno, aliases
        )
    if args.stage == "import":
        return stage_import(env, log, file_path, args.name, report_path)
    return stage_verify(env, log, file_path, args.name, report_path)


if __name__ == "__main__":
    sys.exit(main())
