# -*- coding: utf-8 -*-
"""neo4j-v4 标注导入 v2：在 import_annotation 之上增加本轮所需闸门与校验。

不修改 import_annotation.py。差异见 --help / 报告第 (8) 项：
  · 基线核对可声明「已有标注」非空数（如 devine_argument=187）
  · 检测 content_1…content_6 全空（仍可能有 series/stages）并闸门停止
  · verify：其他已有标注逐节点 SHA256 不变；可自定义抽样名
  · 报告路径与摘要字段适配 high_peak_content 等

用法（在 back_mic/backend 下）:
    python -m panai4.graph.import_annotation_v2 --stage check \\
        --file "..." --name high_peak_content \\
        --expect-anno devine_argument=187 \\
        --report docs/panai4_graph/import_high_peak_content.md
"""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from neo4j import READ_ACCESS, WRITE_ACCESS, GraphDatabase

from panai4.graph import import_annotation as v1

_REPO = v1._REPO
_LOG_DIR = v1._LOG_DIR
_PROP_NAME_RE = v1._PROP_NAME_RE
_BATCH = v1._BATCH
_PAREN_PAIRS = v1._PAREN_PAIRS


def _sha_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _parse_expect_anno(items: list[str]) -> dict[str, int]:
    out = {}
    for item in items:
        if "=" not in item:
            raise SystemExit(f"--expect-anno 格式应为 name=count，收到: {item}")
        name, raw = item.split("=", 1)
        name = name.strip()
        if not _PROP_NAME_RE.fullmatch(name):
            raise SystemExit(f"标注名不合法: {name}")
        out[name] = int(raw.strip())
    return out


def _anno_nonempty(session, prop: str) -> int:
    return v1._run(
        session,
        f"MATCH (n:Truth_Point) WHERE n.{prop} IS NOT NULL RETURN count(n) AS c",
    )[0]["c"]


def _fetch_anno_map(session, prop: str) -> dict[str, str]:
    rows = v1._run(
        session,
        f"""
        MATCH (n:Truth_Point)
        WHERE n.{prop} IS NOT NULL
        RETURN n.name AS name, n.{prop} AS value
        """,
    )
    return {r["name"]: r["value"] for r in rows}


def _content_stage_stats(records: list[dict]) -> dict[str, Any]:
    counts = {}
    for i in range(1, 7):
        k = f"content_{i}"
        counts[k] = sum(1 for r in records if r.get(k))
    all_empty = []
    for r in records:
        if all(not r.get(f"content_{i}") for i in range(1, 7)):
            all_empty.append(r["name"])
    key_union: set[str] = set()
    for r in records:
        key_union |= set(r.keys())
    expected_keys = {
        "name",
        "series",
        "stages",
        "content_1",
        "content_2",
        "content_3",
        "content_4",
        "content_5",
        "content_6",
    }
    series_vals = Counter(json.dumps(r.get("series"), ensure_ascii=False) for r in records)
    stages_vals = Counter(json.dumps(r.get("stages"), ensure_ascii=False) for r in records)
    return {
        "key_union": sorted(key_union),
        "extra_keys": sorted(key_union - expected_keys),
        "content_nonempty": counts,
        "all_six_empty": all_empty,
        "series_kinds": len(series_vals),
        "series_values": [
            {"value": v1._trunc(json.loads(k) if k != "null" else None, 80), "count": c}
            for k, c in series_vals.most_common()
        ],
        "stages_kinds": len(stages_vals),
        "stages_values_head": [
            {"value": v1._trunc(json.loads(k) if k != "null" else None, 80), "count": c}
            for k, c in stages_vals.most_common(3)
        ],
    }


def stage_check(
    env: dict,
    log: v1.Logger,
    file_path: Path,
    anno_name: str,
    fields: list[str] | None,
    report_path: Path,
    expect_anno: dict[str, int],
    sample_names: list[str],
) -> int:
    log.log(f"v2 stage=check file={file_path} name={anno_name} expect_anno={expect_anno}")
    sha_before = v1._sha_import_dir()
    log.log(f"sha_before n={sha_before['n']} bytes={sha_before['bytes']}")

    # parse with v1 plan, then overlay stage-empty detection (exclude all-empty from write)
    plan = v1.parse_and_plan(file_path, fields)
    raw = json.loads(file_path.read_text(encoding="utf-8-sig"))
    stage_info = _content_stage_stats(raw)

    # rebuild write list: drop discard_inners AND all_six_empty
    all_empty_set = set(stage_info["all_six_empty"])
    write_rows = []
    payloads = {}
    for r in raw:
        name = r["name"]
        if name in plan["discard_inners"]:
            continue
        if name in all_empty_set:
            continue
        payload = v1.payload_of(r, fields)
        if not payload:
            continue
        value = v1.serialize_payload(payload)
        write_rows.append({"name": name, "value": value, "length": len(value)})
        payloads[name] = payload
    lengths = sorted(w["length"] for w in write_rows)
    len_stats = {
        "min": lengths[0] if lengths else None,
        "median": int(statistics.median(lengths)) if lengths else None,
        "max": lengths[-1] if lengths else None,
        "total_chars": sum(lengths),
        "over_32000": sum(1 for x in lengths if x > 32000),
    }

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            base = v1.snapshot_graph(session)
            base_fails = v1.gate_baseline(base)
            # expected existing annotations
            existing_hashes: dict[str, dict[str, str]] = {}
            for prop, expected_n in expect_anno.items():
                actual_n = _anno_nonempty(session, prop)
                if actual_n != expected_n:
                    base_fails.append(f"已有标注 {prop} 非空 {actual_n} ≠ 预期 {expected_n}")
                amap = _fetch_anno_map(session, prop)
                existing_hashes[prop] = {n: _sha_text(v) for n, v in amap.items()}
            # annotation key presence
            tp_keys = {r["key"]: r["nonempty"] for r in base["node_keys"]["Truth_Point"]}
            if "devine_argument" in expect_anno and tp_keys.get("devine_argument") != expect_anno["devine_argument"]:
                base_fails.append(
                    f"Truth_Point.devine_argument nonempty {tp_keys.get('devine_argument')} "
                    f"≠ {expect_anno['devine_argument']}"
                )
            match = v1.match_names(session, plan["names"])
    except Exception as exc:
        raise SystemExit("check 失败: " + v1._redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    sha_after = v1._sha_import_dir()
    sha_ok = sha_before["hashes"] == sha_after["hashes"]

    fails = list(base_fails)
    if plan["dup_names"]:
        fails.append(f"JSON name 重复: {plan['dup_names']}")
    if stage_info["extra_keys"]:
        fails.append(f"JSON 有额外键: {stage_info['extra_keys']}")
    if match["missing_n"] or match["multi"]:
        fails.append(f"匹配失败 missing={match['missing']} multi={match['multi']}")
    if plan["need_decision"]:
        fails.append(f"括号词条需决定: {len(plan['need_decision'])} 项")
    if stage_info["all_six_empty"]:
        fails.append(
            f"六个阶段全空 {len(stage_info['all_six_empty'])} 条: {stage_info['all_six_empty']}"
        )
    if not sha_ok:
        fails.append("可导入资料 SHA256 盘点前后不一致")

    state = {
        "version": 2,
        "check_ok": not fails,
        "fails": fails,
        "anno_name": anno_name,
        "file": str(file_path),
        "fields": fields,
        "expect_anno": expect_anno,
        "sample_names": sample_names,
        "v2_diff": [
            "基线可声明已有标注非空数（--expect-anno）并快照 SHA256",
            "检测 content_1…6 全空并闸门停止（不写入这些 name）",
            "verify 校验其他标注 SHA256 不变；抽样名可配置",
            "报告增加 series/stages 取值与全空名单",
        ],
        "baseline": {k: v for k, v in base.items() if k != "tp_props"},
        "tp_props": base["tp_props"],
        "existing_anno_sha256": existing_hashes,
        "stage_info": stage_info,
        "plan_summary": {
            "n_records": plan["n_records"],
            "dup_names": plan["dup_names"],
            "extra_keys": stage_info["extra_keys"],
            "content_counts": stage_info["content_nonempty"],
            "has_city": plan["has_city"],
            "paren_rows": plan["paren_rows"],
            "discard_inners": plan["discard_inners"],
            "all_six_empty": stage_info["all_six_empty"],
            "need_decision": plan["need_decision"],
            "write_count": len(write_rows),
            "write_names": [w["name"] for w in write_rows],
            "len_stats": len_stats,
            "null_or_empty_values": sum(1 for w in write_rows if not w["value"]),
            "series_kinds": stage_info["series_kinds"],
            "stages_kinds": stage_info["stages_kinds"],
            "series_values": stage_info["series_values"],
            "stages_values_head": stage_info["stages_values_head"],
            "key_union": stage_info["key_union"],
        },
        "match": {
            "found_n": match["found_n"],
            "missing_n": match["missing_n"],
            "missing": match["missing"],
            "multi": match["multi"],
        },
        "payloads": payloads,
        "write_rows": write_rows,
        "sha_before": sha_before,
        "sha_after_check": sha_after,
        "sha_ok": sha_ok,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    v1.save_state(anno_name, state)
    write_report_v2(state, None, None, env, log.path, report_path, None if not fails else "check")

    for f in fails:
        log.log("GATE FAIL: " + f)
    if fails:
        log.log("闸门未通过，停止。未进入 import。")
        return 2
    log.log(
        f"闸门通过。拟写入 {len(write_rows)}（丢弃括号内 {plan['discard_inners']}；"
        f"全空未写入 {stage_info['all_six_empty']}）；len={len_stats}"
    )
    return 0


def stage_import(env: dict, log: v1.Logger, file_path: Path, anno_name: str, report_path: Path) -> int:
    state = v1.load_state(anno_name)
    if state.get("version") != 2:
        log.log("状态文件不是 v2 check 产物，拒绝 import")
        return 2
    if not state.get("check_ok"):
        log.log("check 未通过，拒绝 import")
        return 2
    if Path(state["file"]).resolve() != file_path.resolve():
        log.log(f"文件路径与 check 不一致")
        return 2
    base = state["baseline"]
    write_rows = state["write_rows"]
    expect_anno = state.get("expect_anno") or {}
    log.log(f"v2 stage=import 拟写入 {len(write_rows)}")

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    written = 0
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=WRITE_ACCESS) as session:
            now = v1.snapshot_graph(session)
            light_now = {k: now[k] for k in ("nodes_total", "labels", "rels_total", "by_type", "same_as_n")}
            light_base = {k: base[k] for k in ("nodes_total", "labels", "rels_total", "by_type", "same_as_n")}
            if light_now != light_base:
                log.log(f"I1 失败：基线变化")
                write_report_v2(
                    state,
                    {"aborted": True, "reason": "I1 baseline mismatch"},
                    None,
                    env,
                    log.path,
                    report_path,
                    "import-I1",
                )
                return 2
            for prop, expected_n in expect_anno.items():
                actual_n = _anno_nonempty(session, prop)
                if actual_n != expected_n:
                    log.log(f"I1 失败：已有标注 {prop} {actual_n}≠{expected_n}")
                    write_report_v2(
                        state,
                        {"aborted": True, "reason": f"anno {prop} changed"},
                        None,
                        env,
                        log.path,
                        report_path,
                        "import-I1",
                    )
                    return 2
            log.log("I1 通过")
            for i in range(0, len(write_rows), _BATCH):
                batch = write_rows[i : i + _BATCH]
                rows = [{"name": r["name"], "value": r["value"]} for r in batch]
                updated = session.execute_write(v1._set_batch, anno_name, rows)
                if updated != len(batch):
                    log.log(f"GATE FAIL: 批次更新数 {updated} ≠ {len(batch)}")
                    write_report_v2(
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

    info = {
        "aborted": False,
        "written": written,
        "failed": 0,
        "expected": len(write_rows),
        "discarded_inners": state["plan_summary"]["discard_inners"],
        "skipped_all_six_empty": state["plan_summary"]["all_six_empty"],
    }
    state["import"] = info
    v1.save_state(anno_name, state)
    write_report_v2(state, info, None, env, log.path, report_path, None)
    log.log(f"import 完成 written={written} failed=0")
    return 0


def stage_verify(env: dict, log: v1.Logger, file_path: Path, anno_name: str, report_path: Path) -> int:
    state = v1.load_state(anno_name)
    if state.get("version") != 2:
        log.log("状态文件不是 v2，拒绝 verify")
        return 2
    base = state["baseline"]
    plan = state["plan_summary"]
    payloads = state["payloads"]
    write_names = set(plan["write_names"])
    expected_write = plan["write_count"]
    expect_anno = state.get("expect_anno") or {}
    existing_sha = state.get("existing_anno_sha256") or {}
    sample_names = list(state.get("sample_names") or [])
    sha_before = state["sha_before"]
    log.log("v2 stage=verify")

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            now = v1.snapshot_graph(session)
            anno_count = _anno_nonempty(session, anno_name)
            inner_anno = v1._run(
                session,
                f"""
                MATCH (n:Truth_Point)
                WHERE n.same_as IS NOT NULL AND toString(n.same_as) <> ''
                  AND n.{anno_name} IS NOT NULL
                RETURN count(n) AS c, collect(n.name) AS names
                """,
            )[0]
            without = v1._run(
                session,
                f"MATCH (n:Truth_Point) WHERE n.{anno_name} IS NULL RETURN count(n) AS c",
            )[0]["c"]
            stored = v1._run(
                session,
                f"""
                MATCH (n:Truth_Point)
                WHERE n.{anno_name} IS NOT NULL
                RETURN n.name AS name, n.{anno_name} AS value
                ORDER BY name
                """,
            )
            # enrich samples: max content_5 char length among payloads
            if payloads:
                def c5_len(p):
                    return len(json.dumps(p.get("content_5") or [], ensure_ascii=False))

                max_c5 = max(payloads.items(), key=lambda kv: c5_len(kv[1]))[0]
                if max_c5 not in sample_names:
                    sample_names.append(max_c5)
                # many / few stages content by total content chars
                scored = []
                for n, p in payloads.items():
                    total = sum(
                        len(json.dumps(p.get(f"content_{i}") or [], ensure_ascii=False))
                        for i in range(1, 7)
                    )
                    scored.append((total, n))
                scored.sort()
                for _, n in scored[:2]:
                    if n not in sample_names:
                        sample_names.append(n)
                for _, n in scored[-2:]:
                    if n not in sample_names:
                        sample_names.append(n)

            samples = []
            for name in sample_names:
                rows = v1._run(
                    session,
                    f"MATCH (n:Truth_Point {{name: $name}}) RETURN n.{anno_name} AS value",
                    {"name": name},
                )
                if not rows:
                    samples.append({"name": name, "present": False})
                    continue
                val = rows[0]["value"]
                samples.append(
                    {
                        "name": name,
                        "present": val is not None,
                        "length": len(val) if isinstance(val, str) else None,
                        "head80": v1._trunc(val, 80) if isinstance(val, str) else None,
                    }
                )

            # other annotations sha
            other_sha_check = {}
            for prop, before_map in existing_sha.items():
                now_map = _fetch_anno_map(session, prop)
                now_sha = {n: _sha_text(v) for n, v in now_map.items()}
                other_sha_check[prop] = {
                    "before_n": len(before_map),
                    "now_n": len(now_map),
                    "count_ok": len(now_map) == len(before_map) == expect_anno.get(prop, len(before_map)),
                    "sha_mismatch": sum(
                        1 for n, h in before_map.items() if now_sha.get(n) != h
                    ),
                    "only_before": sorted(set(before_map) - set(now_map))[:20],
                    "only_now": sorted(set(now_map) - set(before_map))[:20],
                }
    except Exception as exc:
        raise SystemExit("verify 失败: " + v1._redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    sha_now = v1._sha_import_dir()
    fails = []

    if anno_count != expected_write:
        fails.append(f"V1 标注非空 {anno_count} ≠ {expected_write}")
    if inner_anno["c"] != 0:
        fails.append(f"V1 括号内仍有标注: {inner_anno}")

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
        if not chk["count_ok"] or chk["sha_mismatch"] or chk["only_before"] or chk["only_now"]:
            fails.append(f"V2 已有标注 {prop} 变化: {chk}")

    content_diff = 0
    content_diff_names = []
    stored_map = {r["name"]: r["value"] for r in stored}
    for name, payload in payloads.items():
        if name not in write_names:
            continue
        expected = v1.serialize_payload(payload)
        got = stored_map.get(name)
        if got != expected:
            try:
                same = json.loads(got) == payload if isinstance(got, str) else False
            except Exception:
                same = False
            # also check key order via dumps
            if not same or (isinstance(got, str) and got != expected):
                # prefer exact string match for order
                if got != expected:
                    content_diff += 1
                    if len(content_diff_names) < 20:
                        content_diff_names.append(name)
    if content_diff:
        fails.append(f"V3 内容不一致 {content_diff}: {content_diff_names}")

    expect_without = v1._EXPECTED["Truth_Point"] - expected_write
    # note: all_six_empty intentionally remain without this annotation
    if without != expect_without:
        fails.append(f"V4/无本标注节点 {without} ≠ {expect_without}")

    tp_keys = {r["key"] for r in now["node_keys"]["Truth_Point"]}
    expect_keys = {"name", "same_as", anno_name} | set(expect_anno)
    if tp_keys != expect_keys:
        fails.append(f"V4 Truth_Point 标注名 {tp_keys} ≠ {expect_keys}")
    for lab in ("Trunk", "Branch"):
        keys = {r["key"] for r in now["node_keys"][lab]}
        if keys != {"name"}:
            fails.append(f"V4 {lab} 标注 {keys}")

    if sha_now["hashes"] != sha_before["hashes"]:
        fails.append("V5 SHA256 变化")

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
        "without": without,
        "expect_without": expect_without,
        "content_diff": content_diff,
        "content_diff_names": content_diff_names,
        "name_same_as_diff": diff_props,
        "other_anno_sha": other_sha_check,
        "samples": samples,
        "node_keys": now["node_keys"],
        "nodes_total": now["nodes_total"],
        "labels": now["labels"],
        "rels_total": now["rels_total"],
        "by_type": now["by_type"],
        "sha_ok": sha_now["hashes"] == sha_before["hashes"],
        "sha_now": {"n": sha_now["n"], "bytes": sha_now["bytes"]},
    }
    state["verify"] = verify
    v1.save_state(anno_name, state)
    write_report_v2(
        state,
        state.get("import"),
        verify,
        env,
        log.path,
        report_path,
        None if not fails else "verify",
    )
    for f in fails:
        log.log("VERIFY FAIL: " + f)
    if fails:
        return 2
    log.log("verify 全部通过")
    return 0


def write_report_v2(
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
    match = state["match"]
    anno = state["anno_name"]
    lines: list[str] = []
    a = lines.append
    a(f"# neo4j-v4 导入标注 `{anno}` 报告（v2）")
    a("")
    a(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}；脚本：`panai4.graph.import_annotation_v2`。")
    a(f"源文件：`{state['file']}`。只 SET `n.{anno}`；未运行 build_v4.py；未打印密码。")
    a("")
    a("## 摘要")
    a("")
    a(
        f"1. **基线**：节点={base['nodes_total']} labels={base['labels']}；关系={base['rels_total']} "
        f"by_type={base['by_type']}；same_as={base['same_as_n']}/{base['no_same_as_n']}；"
        f"已有标注预期={state.get('expect_anno')}；TP keys={base['node_keys']['Truth_Point']}。"
    )
    a(
        f"2. **JSON**：记录={plan['n_records']}；键集合={plan.get('key_union')}；额外键={plan['extra_keys'] or '无'}；"
        f"series 种类={plan.get('series_kinds')} values={plan.get('series_values')}；"
        f"stages 种类={plan.get('stages_kinds')}；content 非空={plan['content_counts']}；城市={plan['has_city']}。"
    )
    a(f"3. **匹配**：找到 {match['found_n']}；找不到 {match['missing_n']} → {match['missing'] or '无'}。")
    paren_brief = [
        f"{r['outer']}/{r['inner']}: {r.get('comparison')} → {r.get('action')}"
        for r in plan["paren_rows"]
        if r.get("outer_in_json") or r.get("inner_in_json")
    ]
    a(f"4. **括号**：{paren_brief or '未出现'}；丢弃内={plan['discard_inners']}。")
    if import_info and not import_info.get("aborted"):
        a(
            f"5. **写入**：写入={import_info.get('written')}；丢弃括号内={import_info.get('discarded_inners')}；"
            f"跳过全空={import_info.get('skipped_all_six_empty')}；失败={import_info.get('failed')}。"
        )
    elif import_info:
        a(f"5. **写入中止**：{import_info}")
    else:
        a(
            f"5. **写入**：尚未 import；拟写入={plan['write_count']}；丢弃括号内={plan['discard_inners']}；"
            f"六阶段全空（未写入、等决定）={plan.get('all_six_empty')}。"
        )
    if verify:
        a(
            f"6. **验证**：ok={verify['ok']}；标注非空={verify['anno_count']}；括号内={verify['inner_anno']['c']}；"
            f"无本标注={verify['without']}；内容差={verify['content_diff']}；其他标注SHA={verify.get('other_anno_sha')}；"
            f"fails={verify['fails'] or '无'}。"
        )
    else:
        a("6. **验证**：尚未 verify。")
    a(f"7. **长度**：{plan['len_stats']}。")
    a(f"8. **脚本**：使用 import_annotation_v2（复用 v1 函数）。差异：{state.get('v2_diff')}。")
    a(
        f"9. **待决**：六阶段全空={plan.get('all_six_empty') or '无'}；括号需决定={plan.get('need_decision') or '无'}；"
        f"stopped={stopped}；check_ok={state.get('check_ok')}；fails={state.get('fails') or '无'}。"
    )
    a("")

    a("## C. check 明细")
    a(f"- 基线节点/关系如上；SHA n={state['sha_before']['n']} bytes={state['sha_before']['bytes']} ok={state.get('sha_ok')}")
    a(f"- 全空名单：{plan.get('all_six_empty')}")
    a(f"- 拟写入 {plan['write_count']}；丢弃括号内 {plan['discard_inners']}")
    for r in plan["paren_rows"]:
        if r.get("outer_in_json") or r.get("inner_in_json"):
            a(f"- 括号 {r['outer']}/{r['inner']}: {r.get('comparison')} / {r.get('action')}")
    a(f"- 闸门：{state.get('fails') or '无'}")
    a("")
    a("## I. import")
    a("未执行。" if not import_info else f"```json\n{json.dumps(import_info, ensure_ascii=False, indent=2)}\n```")
    a("")
    a("## V. verify")
    if not verify:
        a("未执行。")
    else:
        a(f"- {json.dumps({k: verify[k] for k in verify if k not in ('samples', 'node_keys')}, ensure_ascii=False, default=str)[:4000]}")
        a("- 抽样：")
        for s in verify.get("samples") or []:
            a(f"  - {s}")
    a("")
    a("## 最终验证")
    draft = "\n".join(lines)
    leaked = bool(env["pass4"] and env["pass4"] in draft)
    log_text = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    leaked_log = bool(env["pass4"] and env["pass4"] in log_text)
    a("- 只做了 SET 指定标注：是（若已 import）")
    a("- 未运行 build_v4.py：是")
    a(f"- 报告密码检查：{'不通过' if leaked else '通过'}；日志：{'不通过' if leaked_log else '通过'}")
    a("- 未修改 import_annotation.py；本轮使用 import_annotation_v2.py")
    a("")

    text = "\n".join(lines) + "\n"
    if env["pass4"] and env["pass4"] in text:
        raise SystemExit("中止：报告含密码")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8")


# ---------------------------------------------------------------------------
# category-words 模式：标注值 = category 字符串；合并名 / 别名映射
# ---------------------------------------------------------------------------

_EXPECTED_CATEGORIES = {
    "外在": 1658,
    "内在": 497,
    "最内在": 133,
    "显出为外在": 84,
}
_PAREN_OUTER_TO_INNER = {o: i for o, i in _PAREN_PAIRS}
_PAREN_COMBINED = {f"{o}（{i}）": o for o, i in _PAREN_PAIRS}
_DEFAULT_ALIASES = {"路得马丁": "路德马丁"}
_CATEGORY_BATCH = 200


def _parse_aliases(items: list[str]) -> dict[str, str]:
    out = dict(_DEFAULT_ALIASES)
    for item in items:
        if "=" not in item:
            raise SystemExit(f"--alias 格式应为 旧=新，收到: {item}")
        a, b = item.split("=", 1)
        out[a.strip()] = b.strip()
    return out


def write_definitions_doc(categories: list[dict], path: Path) -> None:
    lines = [
        "# 标注 `intrinsic_significance` 取值说明",
        "",
        "来源：可导入资料 `【intrinsic_significance】2372词条内在意义分类.json` 的 `categories`。",
        "图谱节点上该标注的值取下列档次名之一（中文原样）。",
        "",
    ]
    present = {c.get("name") for c in categories}
    for cat in categories:
        name = cat.get("name")
        lines.append(f"## {name}")
        lines.append("")
        lines.append(f"- count：{cat.get('count')}")
        lines.append(f"- ratio：{cat.get('ratio')}")
        lines.append("- definition：")
        lines.append("")
        lines.append(cat.get("definition") or "")
        lines.append("")
    for expected_name in _EXPECTED_CATEGORIES:
        if expected_name not in present:
            lines.append(f"## {expected_name}")
            lines.append("")
            lines.append("- count：（待补）")
            lines.append("- ratio：（待补）")
            lines.append("- definition：**待补**（源文件 `categories` 中无此档次定义）")
            lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def category_check(
    env: dict,
    log: v1.Logger,
    file_path: Path,
    anno_name: str,
    report_path: Path,
    defs_path: Path,
    expect_anno: dict[str, int],
    aliases: dict[str, str],
) -> int:
    log.log(f"v2 category-words check file={file_path} name={anno_name}")
    sha_before = v1._sha_import_dir()
    data = json.loads(file_path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or "words" not in data or "categories" not in data:
        raise SystemExit("顶层须为含 categories/words 的 dict")
    categories = data["categories"]
    words = data["words"]
    write_definitions_doc(categories, defs_path)
    log.log(f"wrote definitions {defs_path}")

    cat_info = []
    for c in categories:
        cat_info.append(
            {
                "name": c.get("name"),
                "count": c.get("count"),
                "ratio": c.get("ratio"),
                "definition_len": len(c.get("definition") or ""),
            }
        )
    extra_keys = sorted(
        set().union(*(set(w.keys()) for w in words)) - {"no", "name", "category"}
    )
    cat_counts = Counter(w.get("category") for w in words)
    dup_names = [n for n, c in Counter(w["name"] for w in words).items() if c > 1]
    has_city = any(w["name"] == "城市" for w in words)

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            base = v1.snapshot_graph(session)
            fails = v1.gate_baseline(base)
            # annotation keys: only name, same_as, + expect_anno (no high_peak)
            tp_keys = {r["key"]: r["nonempty"] for r in base["node_keys"]["Truth_Point"]}
            expect_keys = {"name", "same_as"} | set(expect_anno)
            if set(tp_keys) != expect_keys:
                fails.append(f"基线 Truth_Point 标注名 {set(tp_keys)} ≠ {expect_keys}")
            existing_hashes: dict[str, dict[str, str]] = {}
            for prop, expected_n in expect_anno.items():
                actual_n = _anno_nonempty(session, prop)
                if actual_n != expected_n:
                    fails.append(f"已有标注 {prop} 非空 {actual_n} ≠ {expected_n}")
                amap = _fetch_anno_map(session, prop)
                existing_hashes[prop] = {n: _sha_text(v) for n, v in amap.items()}
            if tp_keys.get("name") != 2380 or base["same_as_n"] != 8:
                fails.append(f"name/same_as 非空异常 name={tp_keys.get('name')} same_as={base['same_as_n']}")

            # load graph name maps
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
            no_same = {r["name"] for r in tp_rows if r["same_as"] is None}
            has_same = {r["name"] for r in tp_rows if r["same_as"] is not None}

            # match each word
            direct = []
            merged = []
            aliased = []
            hit_inner = []
            missing = []
            target_to_sources: dict[str, list[str]] = {}
            write_map: dict[str, str] = {}  # target_name -> category

            for w in words:
                src = w["name"]
                cat = w["category"]
                kind = None
                target = None
                if src in aliases:
                    target = aliases[src]
                    kind = "别名"
                elif src in _PAREN_COMBINED:
                    outer = _PAREN_COMBINED[src]
                    # verify pair
                    # src is outer（inner）
                    inner = src[src.index("（") + 1 : -1] if src.endswith("）") and "（" in src else None
                    if outer not in _PAREN_OUTER_TO_INNER or _PAREN_OUTER_TO_INNER[outer] != inner:
                        missing.append({"name": src, "reason": "合并名不是 8 对之一"})
                        continue
                    target = outer
                    kind = "合并名→括号外"
                elif src in by_name:
                    if by_name[src]["same_as"] is not None:
                        hit_inner.append({"name": src, "same_as": by_name[src]["same_as"], "category": cat})
                        continue
                    target = src
                    kind = "直接"
                else:
                    missing.append({"name": src, "reason": "找不到 Truth_Point"})
                    continue

                # resolve target node
                if target not in by_name:
                    missing.append({"name": src, "reason": f"映射目标不存在: {target}"})
                    continue
                if by_name[target]["same_as"] is not None:
                    hit_inner.append({"name": src, "mapped_to": target, "same_as": by_name[target]["same_as"], "category": cat})
                    continue
                # count match uniqueness already by name unique constraint
                target_to_sources.setdefault(target, []).append(src)
                if kind == "直接":
                    direct.append(src)
                elif kind == "合并名→括号外":
                    merged.append({"src": src, "target": target, "category": cat})
                elif kind == "别名":
                    aliased.append({"src": src, "target": target, "category": cat})
                write_map[target] = cat

            multi = {t: srcs for t, srcs in target_to_sources.items() if len(srcs) > 1}
            write_names = set(write_map)
            only_graph = sorted(no_same - write_names)
            only_json = sorted(write_names - no_same)
            # also: JSON targets that somehow have same_as shouldn't be in write_map

            cat_write_counts = Counter(write_map.values())
    except Exception as exc:
        raise SystemExit("category check 失败: " + v1._redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    sha_after = v1._sha_import_dir()
    sha_ok = sha_before["hashes"] == sha_after["hashes"]

    # C2 category gates
    if set(cat_counts) != set(_EXPECTED_CATEGORIES):
        fails.append(f"category 取值 {dict(cat_counts)} ≠ 预期 { _EXPECTED_CATEGORIES}")
    for k, v in _EXPECTED_CATEGORIES.items():
        if cat_counts.get(k) != v:
            fails.append(f"category「{k}」计数 {cat_counts.get(k)} ≠ {v}")
    if sum(cat_counts.values()) != 2372:
        fails.append(f"words 合计 {sum(cat_counts.values())} ≠ 2372")
    if None in cat_counts or "" in cat_counts:
        fails.append("category 有空值")
    if dup_names:
        fails.append(f"name 重复: {dup_names[:20]}")
    if extra_keys:
        fails.append(f"words 额外键: {extra_keys}")

    # C3/C4 gates
    if missing:
        fails.append(f"找不到/无效映射 {len(missing)}: {missing[:50]}")
    if hit_inner:
        fails.append(f"映射到括号内节点 {len(hit_inner)}: {hit_inner}")
    if multi:
        fails.append(f"多对一 {len(multi)}: { {k:v for i,(k,v) in enumerate(multi.items()) if i<20} }")
    if only_graph:
        fails.append(f"图谱无 same_as 独有 {len(only_graph)}: {only_graph}")
    if only_json:
        fails.append(f"写入目标独有（不在无 same_as 集合）{len(only_json)}: {only_json}")
    if len(write_map) != 2372:
        fails.append(f"拟写入节点数 {len(write_map)} ≠ 2372")
    for k, v in _EXPECTED_CATEGORIES.items():
        if cat_write_counts.get(k) != v:
            fails.append(f"拟写入档次「{k}」{cat_write_counts.get(k)} ≠ {v}")
    # bracket inners must not be written
    written_inners = sorted(write_names & has_same)
    if written_inners:
        fails.append(f"拟写入含括号内: {written_inners}")
    if not sha_ok:
        fails.append("SHA256 变化")

    write_rows = [{"name": n, "value": c} for n, c in sorted(write_map.items())]
    state = {
        "version": 2,
        "mode": "category-words",
        "check_ok": not fails,
        "fails": fails,
        "anno_name": anno_name,
        "file": str(file_path),
        "expect_anno": expect_anno,
        "aliases": aliases,
        "v2_diff": [
            "mode=category-words：标注值=category 字符串（非整条 JSON）",
            "合并名 X（Y）→ 括号外 X；别名表（默认 路得马丁→路德马丁）",
            "只写无 same_as 的 Truth_Point；括号内不写",
            "另写档次定义 md；batch=200",
        ],
        "baseline": {k: v for k, v in base.items() if k != "tp_props"},
        "tp_props": base["tp_props"],
        "existing_anno_sha256": existing_hashes,
        "categories_info": cat_info,
        "plan_summary": {
            "n_records": len(words),
            "dup_names": dup_names,
            "extra_keys": extra_keys,
            "category_counts": dict(cat_counts),
            "has_city": has_city,
            "match_direct_n": len(direct),
            "match_merged_n": len(merged),
            "match_alias_n": len(aliased),
            "merged_detail": merged,
            "alias_detail": aliased,
            "hit_inner": hit_inner,
            "missing": missing,
            "multi": multi,
            "only_graph": only_graph,
            "only_json": only_json,
            "write_count": len(write_rows),
            "write_names": [r["name"] for r in write_rows],
            "write_category_counts": dict(cat_write_counts),
            "discard_inners": sorted(has_same),
        },
        "write_rows": write_rows,
        "payloads": {r["name"]: r["value"] for r in write_rows},  # name->category str
        "sha_before": sha_before,
        "sha_after_check": sha_after,
        "sha_ok": sha_ok,
        "defs_path": str(defs_path),
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    # match stub for report helpers
    state["match"] = {
        "found_n": len(direct) + len(merged) + len(aliased),
        "missing_n": len(missing),
        "missing": [m["name"] for m in missing],
        "multi": multi,
    }
    v1.save_state(anno_name, state)
    write_report_category(state, None, None, env, log.path, report_path, None if not fails else "check")
    for f in fails:
        log.log("GATE FAIL: " + f)
    if fails:
        log.log("闸门未通过，停止。未进入 import。")
        return 2
    log.log(
        f"闸门通过。拟写入 {len(write_rows)}；直接={len(direct)} 合并={len(merged)} 别名={len(aliased)}；"
        f"档次={dict(cat_write_counts)}"
    )
    return 0


def category_import(env: dict, log: v1.Logger, file_path: Path, anno_name: str, report_path: Path) -> int:
    state = v1.load_state(anno_name)
    if state.get("mode") != "category-words" or not state.get("check_ok"):
        log.log("category check 未通过或不匹配，拒绝 import")
        return 2
    if Path(state["file"]).resolve() != file_path.resolve():
        log.log("文件路径与 check 不一致")
        return 2
    base = state["baseline"]
    write_rows = state["write_rows"]
    expect_anno = state.get("expect_anno") or {}
    log.log(f"category import 拟写入 {len(write_rows)}")

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
                write_report_category(state, {"aborted": True, "reason": "I1"}, None, env, log.path, report_path, "import-I1")
                return 2
            for prop, expected_n in expect_anno.items():
                if _anno_nonempty(session, prop) != expected_n:
                    log.log(f"I1 失败：{prop} 非空变化")
                    write_report_category(state, {"aborted": True, "reason": prop}, None, env, log.path, report_path, "import-I1")
                    return 2
            log.log("I1 通过")
            for i in range(0, len(write_rows), _CATEGORY_BATCH):
                batch = write_rows[i : i + _CATEGORY_BATCH]
                rows = [{"name": r["name"], "value": r["value"]} for r in batch]
                updated = session.execute_write(v1._set_batch, anno_name, rows)
                if updated != len(batch):
                    log.log(f"GATE FAIL: 批次 {updated}≠{len(batch)}")
                    write_report_category(
                        state,
                        {"aborted": True, "written": written, "failed_batch_start": i,
                         "failed_names": [r["name"] for r in batch]},
                        None, env, log.path, report_path, "import-batch",
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
    write_report_category(state, info, None, env, log.path, report_path, None)
    log.log(f"import 完成 written={written}")
    return 0


def category_verify(env: dict, log: v1.Logger, file_path: Path, anno_name: str, report_path: Path) -> int:
    state = v1.load_state(anno_name)
    if state.get("mode") != "category-words":
        log.log("状态不是 category-words")
        return 2
    base = state["baseline"]
    plan = state["plan_summary"]
    payloads = state["payloads"]  # name -> category
    expected_write = plan["write_count"]
    expect_anno = state.get("expect_anno") or {}
    existing_sha = state.get("existing_anno_sha256") or {}
    sha_before = state["sha_before"]
    log.log("category verify")

    sample_names = [
        "晨晨复兴", "产生男孩子", "妇人", "挂虑", "火湖", "扩大", "扩增", "那灵的浇灌",
        "路德马丁", "神", "基督",
    ]
    # 2 per category
    by_cat: dict[str, list[str]] = {}
    for n, c in payloads.items():
        by_cat.setdefault(c, []).append(n)
    for c, names in by_cat.items():
        sample_names.extend(names[:2])

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            now = v1.snapshot_graph(session)
            anno_count = _anno_nonempty(session, anno_name)
            inner_anno = v1._run(
                session,
                f"""
                MATCH (n:Truth_Point)
                WHERE n.same_as IS NOT NULL AND toString(n.same_as) <> ''
                  AND n.{anno_name} IS NOT NULL
                RETURN count(n) AS c, collect(n.name) AS names
                """,
            )[0]
            cat_rows = v1._run(
                session,
                f"""
                MATCH (n:Truth_Point)
                WHERE n.{anno_name} IS NOT NULL
                RETURN n.{anno_name} AS cat, count(*) AS c
                """,
            )
            cat_now = {r["cat"]: r["c"] for r in cat_rows}
            stored = _fetch_anno_map(session, anno_name)
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
                    samples.append({"name": name, "value": rows[0]["value"]})
            city = v1._run(session, "MATCH (n:Truth_Point {name:'城市'}) RETURN n.name AS name")
            other_sha_check = {}
            for prop, before_map in existing_sha.items():
                now_map = _fetch_anno_map(session, prop)
                now_sha = {n: _sha_text(v) for n, v in now_map.items()}
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
    for k, v in _EXPECTED_CATEGORIES.items():
        if cat_now.get(k) != v:
            fails.append(f"V1 档次「{k}」{cat_now.get(k)}≠{v}")

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
    for name, cat in payloads.items():
        if stored.get(name) != cat:
            content_diff += 1
            if len(content_diff_names) < 20:
                content_diff_names.append((name, stored.get(name), cat))
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
            out.append({k: r.get(k) for k in ("name", "type", "entityType", "labelsOrTypes", "properties", "state") if k in r})
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
        "cat_now": cat_now,
        "content_diff": content_diff,
        "content_diff_names": content_diff_names,
        "other_anno_sha": other_sha_check,
        "samples": samples,
        "city_nodes": city,
        "node_keys": now["node_keys"],
        "nodes_total": now["nodes_total"],
        "labels": now["labels"],
        "rels_total": now["rels_total"],
        "by_type": now["by_type"],
        "sha_ok": sha_now["hashes"] == sha_before["hashes"],
    }
    state["verify"] = verify
    v1.save_state(anno_name, state)
    write_report_category(state, state.get("import"), verify, env, log.path, report_path, None if not fails else "verify")
    for f in fails:
        log.log("VERIFY FAIL: " + f)
    if fails:
        return 2
    log.log("verify 全部通过")
    return 0


def write_report_category(
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
    a(f"# neo4j-v4 导入标注 `{anno}` 报告（v2 / category-words）")
    a("")
    a(f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}；脚本：`panai4.graph.import_annotation_v2 --mode category-words`。")
    a(f"源文件：`{state['file']}`。只 SET `n.{anno}` = 档次字符串；未运行 build_v4.py；未打印密码。")
    a("")
    a("## 摘要")
    a("")
    a(f"1. **基线**：节点={base['nodes_total']} {base['labels']}；关系={base['rels_total']} {base['by_type']}；"
      f"same_as={base['same_as_n']}/{base['no_same_as_n']}；TP keys={base['node_keys']['Truth_Point']}；"
      f"expect_anno={state.get('expect_anno')}。")
    a(f"2. **JSON**：words={plan['n_records']}；category 计数={plan['category_counts']}；"
      f"categories 简表={state.get('categories_info')}；额外键={plan['extra_keys'] or '无'}；城市={plan['has_city']}。")
    a(f"3. **匹配**：直接={plan['match_direct_n']}；合并名={plan['match_merged_n']}；别名={plan['match_alias_n']}；"
      f"找不到={len(plan['missing'])}；映射到括号内={len(plan['hit_inner'])}；多对一={len(plan['multi'])}。")
    a(f"4. **合并名明细**：{plan['merged_detail']}；**别名**：{plan['alias_detail']}。")
    if import_info and not import_info.get("aborted"):
        a(f"5. **写入**：写入={import_info.get('written')}；失败={import_info.get('failed')}。")
    elif import_info:
        a(f"5. **写入中止**：{import_info}")
    else:
        a(f"5. **写入**：尚未 import；拟写入={plan['write_count']}；档次={plan['write_category_counts']}。")
    if verify:
        a(f"6. **验证**：ok={verify['ok']}；非空={verify['anno_count']}；括号内={verify['inner_anno']['c']}；"
          f"档次={verify['cat_now']}；内容差={verify['content_diff']}；其他标注SHA={verify.get('other_anno_sha')}；"
          f"fails={verify['fails'] or '无'}。")
    else:
        a("6. **验证**：尚未 verify。")
    a(f"7. **脚本**：import_annotation_v2 --mode category-words（复用 v1）。差异：{state.get('v2_diff')}。")
    a(f"8. **待决**：missing={plan['missing'] or '无'}；hit_inner={plan['hit_inner'] or '无'}；"
      f"only_graph={plan['only_graph'] or '无'}；only_json={plan['only_json'] or '无'}；"
      f"stopped={stopped}；check_ok={state.get('check_ok')}；fails={state.get('fails') or '无'}。")
    a(f"- 档次定义文档：`{state.get('defs_path')}`")
    a("")
    a("## C / I / V 明细")
    a(f"- SHA ok={state.get('sha_ok')} n={state['sha_before']['n']}")
    a(f"- 对账 only_graph={plan['only_graph']} only_json={plan['only_json']}")
    a("## I. import")
    a("未执行。" if not import_info else f"```json\n{json.dumps(import_info, ensure_ascii=False, indent=2)}\n```")
    a("## V. verify")
    if not verify:
        a("未执行。")
    else:
        a(f"- samples: {verify.get('samples')}")
        a(f"- city_nodes: {verify.get('city_nodes')}")
        a(f"- node_keys: {verify.get('node_keys')}")
    a("")
    a("## 最终验证")
    draft = "\n".join(lines)
    leaked = bool(env["pass4"] and env["pass4"] in draft)
    log_text = log_path.read_text(encoding="utf-8") if log_path.exists() else ""
    leaked_log = bool(env["pass4"] and env["pass4"] in log_text)
    a("- 只做了 SET intrinsic_significance：是（若已 import）")
    a("- 未运行 build_v4.py：是")
    a(f"- 报告密码检查：{'不通过' if leaked else '通过'}；日志：{'不通过' if leaked_log else '通过'}")
    a("- 未修改 import_annotation.py")
    a("")
    text = "\n".join(lines) + "\n"
    if env["pass4"] and env["pass4"] in text:
        raise SystemExit("中止：报告含密码")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(text, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="导入 Truth_Point 标注到 neo4j-v4（v2）")
    parser.add_argument("--stage", required=True, choices=["check", "import", "verify"])
    parser.add_argument("--file", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--fields", default="")
    parser.add_argument("--report", default="")
    parser.add_argument(
        "--mode",
        default="json-record",
        choices=["json-record", "category-words"],
        help="json-record=整条除 name 外 JSON 字符串；category-words=words[].category 字符串",
    )
    parser.add_argument(
        "--expect-anno",
        action="append",
        default=[],
        help="已有标注非空预期，可重复：devine_argument=187",
    )
    parser.add_argument(
        "--sample",
        action="append",
        default=[],
        help="verify 抽样 name，可重复（json-record 模式）",
    )
    parser.add_argument(
        "--alias",
        action="append",
        default=[],
        help="别名 旧=新，可重复；默认已含 路得马丁=路德马丁",
    )
    parser.add_argument(
        "--defs",
        default="",
        help="档次定义 md 路径（category-words）",
    )
    args = parser.parse_args()

    if not _PROP_NAME_RE.fullmatch(args.name):
        raise SystemExit(f"标注名必须是合法标识符: {args.name}")
    file_path = Path(args.file)
    if not file_path.is_file():
        raise SystemExit(f"文件不存在: {file_path}")
    fields = [x.strip() for x in args.fields.split(",") if x.strip()] or None
    report_path = Path(args.report) if args.report else v1.default_report(args.name)
    expect_anno = _parse_expect_anno(args.expect_anno)
    sample_names = args.sample or ["神的话", "圣经", "结晶意义"]
    aliases = _parse_aliases(args.alias)
    defs_path = (
        Path(args.defs)
        if args.defs
        else _REPO / "docs" / "panai4_graph" / "annotation_intrinsic_significance_definitions.md"
    )

    env = v1._load_env()
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = v1.Logger(_LOG_DIR / f"import_annotation_v2_{args.name}_{v1._now()}.log", env["pass4"])
    log.log(f"stage={args.stage} name={args.name} mode={args.mode}（v2；密码不记录）")

    if args.mode == "category-words":
        if args.stage == "check":
            return category_check(env, log, file_path, args.name, report_path, defs_path, expect_anno, aliases)
        if args.stage == "import":
            return category_import(env, log, file_path, args.name, report_path)
        return category_verify(env, log, file_path, args.name, report_path)

    if args.stage == "check":
        return stage_check(env, log, file_path, args.name, fields, report_path, expect_anno, sample_names)
    if args.stage == "import":
        return stage_import(env, log, file_path, args.name, report_path)
    return stage_verify(env, log, file_path, args.name, report_path)


if __name__ == "__main__":
    sys.exit(main())
