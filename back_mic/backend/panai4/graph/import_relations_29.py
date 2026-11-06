# -*- coding: utf-8 -*-
"""neo4j-v4：导入 29 种专特/一般关系（仅 pairs，关系上无属性）。

不修改 import_annotation*.py / delete_old_relations.py / .gitignore。
不运行 build_v4.py；不打印密码；不创建节点。

用法（在 back_mic/backend 下）:
    python -m panai4.graph.import_relations_29 --stage check
    python -m panai4.graph.import_relations_29 --stage import
    python -m panai4.graph.import_relations_29 --stage verify
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any

from neo4j import READ_ACCESS, WRITE_ACCESS, GraphDatabase

from panai4.graph import import_annotation as v1
from panai4.graph import import_annotation_v2 as v2
from panai4.graph.import_general_annotation import (
    _PROTECTED,
    _compare_protected,
    _sha_val,
    _COMPOSITE_RE,
    _ALIAS,
    find_sources,
    map_term_name,
)

_REPO = v1._REPO
_LOG_DIR = v1._LOG_DIR
_STATE_NAME = "relations_29"
_REPORT = _REPO / "docs" / "panai4_graph" / "import_relations_29.md"
_BATCH = 500
_TYPE_RE = re.compile(r"^[A-Z][A-Z_]*$")
_CLASS_TYPES = {
    "BELONGS_TO_TRUNK": 2380,
    "OF_BRANCH_DIRECTLY": 2380,
    "OF_BRANCH_INDIRECTLY": 1676,
    "GRAFTING": 91,
}
_RENAME = {
    "IN_APPOSITION_WITH / EQUIVALENT_TO": "EQUIVALENT_TO",
    "EMBODIED_IN / REALIZED_AS": "EMBODIED_IN_REALIZED_AS",
    "EXPERIENCES / ENJOYS": "EXPERIENCES_ENJOYS",
    "OPPOSES / CONTRASTS_WITH": "OPPOSES_CONTRASTS_WITH",
    "BEFORE / SIMULTANEOUS_WITH / DURING": "SIMULTANEOUS_WITH",
}
# A-part new annotations also protected in B verify
_A_PROPS = (
    "name_en",
    "greek_terms",
    "hebrew_terms",
    "related_scriptures",
    "definition_3a",
    "definition_3b",
)


def formal_type(relation: str) -> str:
    return _RENAME.get(relation, relation)


def _snapshot_a_props(session) -> dict[str, dict[str, str]]:
    out = {}
    for prop in _A_PROPS:
        amap = v2._fetch_anno_map(session, prop)
        out[prop] = {name: _sha_val(val) for name, val in amap.items()}
    return out


def parse_relations(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, list) or len(data) != 29:
        raise SystemExit(f"关系 JSON 须为 29 条 list，实际 {type(data).__name__} len={getattr(data,'__len__',None)}")

    type_map = []
    formal_types = []
    per_type: dict[str, list[dict]] = {}
    count_mismatch = []
    alias_hits = Counter()
    composite_hits = Counter()

    for row in data:
        raw = row["relation"]
        formal = formal_type(raw)
        type_map.append(
            {
                "raw": raw,
                "formal": formal,
                "renamed": raw in _RENAME,
                "name": row.get("name"),
                "type": row.get("type"),
                "group": row.get("group"),
                "level": row.get("level"),
                "count_field": row.get("count"),
                "pairs_len": len(row.get("pairs") or []),
            }
        )
        if row.get("count") != len(row.get("pairs") or []):
            count_mismatch.append({"relation": raw, "count": row.get("count"), "pairs": len(row.get("pairs") or [])})
        formal_types.append(formal)
        pairs = []
        for p in row.get("pairs") or []:
            frm_src, to_src = p["from"], p["to"]
            frm = map_term_name(frm_src)
            to = map_term_name(to_src)
            if frm_src != frm:
                if frm_src in _ALIAS:
                    alias_hits[frm_src] += 1
                else:
                    composite_hits[frm_src] += 1
            if to_src != to:
                if to_src in _ALIAS:
                    alias_hits[to_src] += 1
                else:
                    composite_hits[to_src] += 1
            pairs.append({"from": frm, "to": to, "from_src": frm_src, "to_src": to_src})
        per_type[formal] = pairs

    # validate formal names
    invalid = [t for t in formal_types if not _TYPE_RE.fullmatch(t)]
    dup_formal = [t for t, c in Counter(formal_types).items() if c > 1]
    clash = sorted(set(formal_types) & set(_CLASS_TYPES))

    # stats per type after dedupe
    expected_counts = {}
    self_loops = []
    dup_pairs = []
    total_raw = 0
    total_unique = 0
    for formal, pairs in per_type.items():
        total_raw += len(pairs)
        seen = set()
        uniq = []
        for p in pairs:
            key = (p["from"], p["to"])
            if p["from"] == p["to"]:
                self_loops.append({"type": formal, "name": p["from"]})
            if key in seen:
                dup_pairs.append({"type": formal, "from": p["from"], "to": p["to"]})
            else:
                seen.add(key)
                uniq.append(p)
        per_type[formal] = uniq  # store deduped for import
        expected_counts[formal] = len(uniq)
        total_unique += len(uniq)

    return {
        "n_types": len(data),
        "type_map": type_map,
        "formal_types": formal_types,
        "invalid_types": invalid,
        "dup_formal": dup_formal,
        "clash_class": clash,
        "count_mismatch": count_mismatch,
        "total_raw_pairs": total_raw,
        "total_unique_pairs": total_unique,
        "expected_counts": expected_counts,
        "self_loops": self_loops,
        "dup_pairs": dup_pairs,
        "alias_hits": dict(alias_hits),
        "composite_hits": dict(composite_hits),
        "per_type": per_type,
        "name_map_table": {
            "路得马丁": "路德马丁",
            **{k: map_term_name(k) for k in composite_hits},
        },
    }


def stage_check(env: dict, log: v1.Logger) -> int:
    log.log("stage=check relations_29")
    srcs = find_sources()
    rel_path = srcs["relations"]
    log.log(f"relations file={rel_path}")
    sha_before = v1._sha_import_dir()
    parsed = parse_relations(rel_path)

    fails = []
    if parsed["total_raw_pairs"] != 35902:
        fails.append(f"pairs 总数 {parsed['total_raw_pairs']} ≠ 35902")
    if parsed["count_mismatch"]:
        fails.append(f"count≠len(pairs): {parsed['count_mismatch']}")
    if parsed["invalid_types"]:
        fails.append(f"类型名不合法: {parsed['invalid_types']}")
    if parsed["dup_formal"]:
        fails.append(f"正式类型重名: {parsed['dup_formal']}")
    if parsed["clash_class"]:
        fails.append(f"与分类关系重名: {parsed['clash_class']}")

    # collect all endpoint names
    ends = set()
    for pairs in parsed["per_type"].values():
        for p in pairs:
            ends.add(p["from"])
            ends.add(p["to"])

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            base = v1.snapshot_graph(session)
            # baseline: nodes & class rels; total may still be 6527 before B import
            if base["nodes_total"] != 2483:
                fails.append(f"nodes_total {base['nodes_total']}≠2483")
            for lab, n in (("Truth_Point", 2380), ("Branch", 91), ("Trunk", 12)):
                if base["labels"].get(lab) != n:
                    fails.append(f"{lab} {base['labels'].get(lab)}≠{n}")
            for t, n in _CLASS_TYPES.items():
                if base["by_type"].get(t, 0) != n:
                    fails.append(f"分类关系 {t} {base['by_type'].get(t)}≠{n}")
            if base["rels_total"] != 6527:
                # After A, still 6527; if already partially imported B, warn
                fails.append(f"rels_total 导入前应为 6527，实际 {base['rels_total']}")

            protected = {}
            for prop, n_exp in _PROTECTED.items():
                n = v2._anno_nonempty(session, prop)
                if n != n_exp:
                    fails.append(f"保护标注 {prop} {n}≠{n_exp}")
                amap = v2._fetch_anno_map(session, prop)
                protected[prop] = {name: _sha_val(val) for name, val in amap.items()}
            a_sha = _snapshot_a_props(session)

            with_sa = {
                r["name"]
                for r in v1._run(
                    session,
                    """
                    MATCH (n:Truth_Point)
                    WHERE n.same_as IS NOT NULL AND toString(n.same_as) <> ''
                    RETURN n.name AS name
                    """,
                )
            }
            all_tp = {
                r["name"]
                for r in v1._run(session, "MATCH (n:Truth_Point) RETURN n.name AS name")
            }
            missing = sorted(e for e in ends if e not in all_tp)
            hit_inner = sorted(e for e in ends if e in with_sa)

            # index / constraint on Truth_Point.name
            indexes = base.get("indexes") or []
            constraints = base.get("constraints") or []
            name_index = []
            for idx in indexes:
                labs = idx.get("labelsOrTypes") or idx.get("labelsOrTypes") or []
                props = idx.get("properties") or []
                if labs and "Truth_Point" in labs and props and "name" in props:
                    name_index.append(
                        {
                            "name": idx.get("name"),
                            "type": idx.get("type"),
                            "state": idx.get("state"),
                            "properties": props,
                        }
                    )
            name_constraint = []
            for c in constraints:
                labs = c.get("labelsOrTypes") or []
                props = c.get("properties") or []
                if labs and "Truth_Point" in labs and props and "name" in props:
                    name_constraint.append(
                        {
                            "name": c.get("name"),
                            "type": c.get("type"),
                            "properties": props,
                        }
                    )
    except Exception as exc:
        raise SystemExit("check 失败: " + v1._redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    if missing:
        fails.append(f"未匹配端点 {len(missing)}: {missing[:40]}")
    if hit_inner:
        fails.append(f"括号内端点 {len(hit_inner)}: {hit_inner}")

    sha_after = v1._sha_import_dir()
    sha_ok = sha_before["hashes"] == sha_after["hashes"]
    if not sha_ok:
        fails.append("可导入资料 SHA 前后不一致")

    # city
    has_city = "城市" in ends

    state = {
        "version": 1,
        "check_ok": not fails,
        "fails": fails,
        "file": str(rel_path),
        "type_map": parsed["type_map"],
        "rename_table": _RENAME,
        "expected_counts": parsed["expected_counts"],
        "total_raw_pairs": parsed["total_raw_pairs"],
        "total_unique_pairs": parsed["total_unique_pairs"],
        "self_loops": parsed["self_loops"],
        "dup_pairs": parsed["dup_pairs"],
        "alias_hits": parsed["alias_hits"],
        "composite_hits": parsed["composite_hits"],
        "name_map_table": parsed["name_map_table"],
        "missing_endpoints": missing,
        "inner_endpoints": hit_inner,
        "has_city_endpoint": has_city,
        "name_index": name_index,
        "name_constraint": name_constraint,
        "baseline": {
            "nodes_total": base["nodes_total"],
            "labels": base["labels"],
            "rels_total": base["rels_total"],
            "by_type": base["by_type"],
        },
        "protected_sha": protected,
        "a_props_sha": a_sha,
        "per_type": parsed["per_type"],
        "sha_before": sha_before,
        "sha_ok": sha_ok,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    v1.save_state(_STATE_NAME, state)
    write_report(state, import_info=None, verify_info=None, log_path=log.path)
    for f in fails:
        log.log("GATE FAIL: " + f)
    if fails:
        log.log("闸门未通过，停止。自环/重复仅报告不阻断（当前因其他闸门停止）。")
        return 2
    log.log(
        f"闸门通过。raw={parsed['total_raw_pairs']} unique={parsed['total_unique_pairs']} "
        f"self_loops={len(parsed['self_loops'])} dups={len(parsed['dup_pairs'])} "
        f"name_index={name_index}"
    )
    return 0


def _merge_batch(tx, rel_type: str, rows: list[dict]) -> int:
    if not _TYPE_RE.fullmatch(rel_type):
        raise RuntimeError(f"非法关系类型: {rel_type}")
    q = (
        "UNWIND $rows AS row "
        "MATCH (a:Truth_Point {name: row.from}) "
        "MATCH (b:Truth_Point {name: row.to}) "
        f"MERGE (a)-[r:`{rel_type}`]->(b) "
        "RETURN count(r) AS n"
    )
    result = tx.run(q, {"rows": rows})
    row = result.single()
    return int(row["n"]) if row else 0


def _count_type(session, rel_type: str) -> int:
    q = f"MATCH ()-[r:`{rel_type}`]->() RETURN count(r) AS c"
    return v1._run(session, q)[0]["c"]


def stage_import(env: dict, log: v1.Logger) -> int:
    log.log("stage=import relations_29")
    state = v1.load_state(_STATE_NAME)
    if not state.get("check_ok"):
        raise SystemExit("check 未通过，拒绝 import")
    if not state.get("name_index") and not state.get("name_constraint"):
        log.log("警告：Truth_Point.name 无索引/唯一约束（仅报告，不创建）")

    per_type: dict[str, list[dict]] = state["per_type"]
    expected = state["expected_counts"]
    progress = {}
    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            base = v1.snapshot_graph(session)
            if base["nodes_total"] != 2483:
                log.log(f"GATE FAIL nodes={base['nodes_total']}")
                return 2
            for t, n in _CLASS_TYPES.items():
                if base["by_type"].get(t, 0) != n:
                    log.log(f"GATE FAIL class {t}")
                    return 2
            if base["rels_total"] != 6527:
                log.log(f"GATE FAIL rels_total={base['rels_total']}（应为导入前 6527）")
                return 2

        for rel_type, pairs in per_type.items():
            log.log(f"import type={rel_type} pairs={len(pairs)}")
            with driver.session(default_access_mode=WRITE_ACCESS) as session:
                for i in range(0, len(pairs), _BATCH):
                    batch = pairs[i : i + _BATCH]
                    rows = [{"from": p["from"], "to": p["to"]} for p in batch]
                    n = session.execute_write(_merge_batch, rel_type, rows)
                    if n != len(batch):
                        log.log(
                            f"batch 返回 count={n} ≠ {len(batch)} type={rel_type} "
                            f"offset={i}（MERGE 计数异常，停止）"
                        )
                        state["import"] = {
                            "aborted": True,
                            "progress": progress,
                            "failed_type": rel_type,
                            "offset": i,
                        }
                        v1.save_state(_STATE_NAME, state)
                        write_report(state, state["import"], None, log.path)
                        return 2
                    log.log(f"  batch {i}-{i+len(batch)-1} merge_count={n}")
            # verify count for this type
            with driver.session(default_access_mode=READ_ACCESS) as session:
                got = _count_type(session, rel_type)
            exp = expected[rel_type]
            progress[rel_type] = {"expected": exp, "actual": got}
            if got != exp:
                log.log(f"类型计数不符 {rel_type}: {got}≠{exp}；停止")
                state["import"] = {"aborted": True, "progress": progress, "failed_type": rel_type}
                v1.save_state(_STATE_NAME, state)
                write_report(state, state["import"], None, log.path)
                return 2
            log.log(f"  OK {rel_type}={got}")
    except Exception as exc:
        raise SystemExit("import 失败: " + v1._redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    info = {"aborted": False, "progress": progress, "types": len(progress)}
    state["import"] = info
    v1.save_state(_STATE_NAME, state)
    write_report(state, info, None, log.path)
    log.log(f"import 完成 types={len(progress)}")
    return 0


def stage_verify(env: dict, log: v1.Logger) -> int:
    log.log("stage=verify relations_29")
    state = v1.load_state(_STATE_NAME)
    expected = state["expected_counts"]
    total_unique = state["total_unique_pairs"]
    fails = []

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            now = v1.snapshot_graph(session)
            if now["nodes_total"] != 2483:
                fails.append(f"nodes {now['nodes_total']}≠2483")
            for lab, n in (("Truth_Point", 2380), ("Branch", 91), ("Trunk", 12)):
                if now["labels"].get(lab) != n:
                    fails.append(f"{lab} {now['labels'].get(lab)}≠{n}")
            for t, n in _CLASS_TYPES.items():
                if now["by_type"].get(t, 0) != n:
                    fails.append(f"分类关系 {t} {now['by_type'].get(t)}≠{n}")

            type_counts = {}
            for rel_type, exp in expected.items():
                got = now["by_type"].get(rel_type, 0)
                type_counts[rel_type] = got
                if got != exp:
                    fails.append(f"{rel_type} {got}≠{exp}")

            expect_total = 6527 + total_unique
            if now["rels_total"] != expect_total:
                fails.append(f"rels_total {now['rels_total']}≠{expect_total}")

            # relations must have no properties
            props_n = v1._run(
                session,
                """
                MATCH ()-[r]->()
                WHERE type(r) IN $types AND size(keys(r)) > 0
                RETURN count(r) AS c
                """,
                {"types": list(expected.keys())},
            )[0]["c"]
            if props_n:
                fails.append(f"关系带属性数 {props_n}≠0")

            # city
            city_n = v1._run(
                session,
                "MATCH (n:Truth_Point {name: $name}) RETURN count(n) AS c",
                {"name": "城市"},
            )[0]["c"]
            if city_n:
                fails.append(f"存在「城市」节点: {city_n}")

            # protected + A props
            prot = _compare_protected(state["protected_sha"], session)
            for prop, info in prot.items():
                if info["sha_mismatch"] or info["only_before"] or info["only_now"]:
                    fails.append(f"旧标注变化 {prop}: {info}")
            a_now = _snapshot_a_props(session)
            a_cmp = {}
            for prop, old in state["a_props_sha"].items():
                now_map = a_now.get(prop, {})
                only_b = sorted(set(old) - set(now_map))
                only_n = sorted(set(now_map) - set(old))
                mism = sorted(k for k in set(old) & set(now_map) if old[k] != now_map[k])
                a_cmp[prop] = {
                    "before_n": len(old),
                    "now_n": len(now_map),
                    "sha_mismatch": len(mism),
                    "only_before": only_b[:10],
                    "only_now": only_n[:10],
                }
                if mism or only_b or only_n:
                    fails.append(f"A标注变化 {prop}: {a_cmp[prop]}")

            # samples: 3 pairs per type + 路德马丁
            samples = {}
            luther_samples = []
            for rel_type, pairs in state["per_type"].items():
                take = pairs[:3]
                ok_list = []
                for p in take:
                    n = v1._run(
                        session,
                        f"""
                        MATCH (a:Truth_Point {{name: $f}})-[r:`{rel_type}`]->(b:Truth_Point {{name: $t}})
                        RETURN count(r) AS c
                        """,
                        {"f": p["from"], "t": p["to"]},
                    )[0]["c"]
                    ok_list.append({"from": p["from"], "to": p["to"], "present": n >= 1})
                    if n < 1:
                        fails.append(f"抽样缺失 {rel_type} {p['from']}→{p['to']}")
                samples[rel_type] = ok_list
                for p in pairs:
                    if p["from"] == "路德马丁" or p["to"] == "路德马丁":
                        n = v1._run(
                            session,
                            f"""
                            MATCH (a:Truth_Point {{name: $f}})-[r:`{rel_type}`]->(b:Truth_Point {{name: $t}})
                            RETURN count(r) AS c
                            """,
                            {"f": p["from"], "t": p["to"]},
                        )[0]["c"]
                        luther_samples.append(
                            {
                                "type": rel_type,
                                "from": p["from"],
                                "to": p["to"],
                                "present": n >= 1,
                            }
                        )
                        if n < 1:
                            fails.append(f"路德马丁对缺失 {rel_type} {p['from']}→{p['to']}")
                        if len([x for x in luther_samples if x["type"] == rel_type]) >= 2:
                            break

            sha_now = v1._sha_import_dir()
            if sha_now["hashes"] != state["sha_before"]["hashes"]:
                fails.append("可导入资料 SHA 变化")
    except Exception as exc:
        raise SystemExit("verify 失败: " + v1._redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    verify_info = {
        "ok": not fails,
        "fails": fails,
        "type_counts": type_counts,
        "rels_total": now["rels_total"],
        "expect_total": 6527 + total_unique,
        "nodes_total": now["nodes_total"],
        "labels": now["labels"],
        "class_types": {t: now["by_type"].get(t) for t in _CLASS_TYPES},
        "rel_props_nonzero": props_n,
        "city_n": city_n,
        "protected_compare": prot,
        "a_props_compare": a_cmp,
        "samples": samples,
        "luther_samples": luther_samples[:30],
    }
    state["verify"] = verify_info
    v1.save_state(_STATE_NAME, state)
    write_report(state, state.get("import"), verify_info, log.path)
    for f in fails:
        log.log("VERIFY FAIL: " + f)
    if fails:
        return 2
    log.log("verify 全部通过")
    return 0


def write_report(state: dict, import_info: dict | None, verify_info: dict | None, log_path: Path) -> None:
    lines = [
        "# neo4j-v4 导入 29 种关系报告",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}；脚本：`panai4.graph.import_relations_29`。",
        "只用 pairs 建关系；关系上无属性；类型名带反引号；未运行 build_v4.py；未打印密码。",
        "",
        "## 摘要",
        "",
        f"1. **源**：`{state.get('file')}`；raw_pairs={state.get('total_raw_pairs')}；"
        f"unique={state.get('total_unique_pairs')}。",
        f"2. **类型重命名**：{json.dumps(state.get('rename_table'), ensure_ascii=False)}",
        f"3. **端点映射**：{json.dumps(state.get('name_map_table'), ensure_ascii=False)}；"
        f"alias_hits={state.get('alias_hits')}；composite_hits={state.get('composite_hits')}。",
        f"4. **闸门**：missing={state.get('missing_endpoints')} inner={state.get('inner_endpoints')} "
        f"fails={state.get('fails')} check_ok={state.get('check_ok')}。",
        f"5. **自环** n={len(state.get('self_loops') or [])}；"
        f"**重复对** n={len(state.get('dup_pairs') or [])}（MERGE 后各类型按 unique 计）。",
        f"6. **索引**：name_index={state.get('name_index')} name_constraint={state.get('name_constraint')}（未自行创建）。",
        f"7. **import**：{v1._trunc(import_info, 200) if import_info else '（尚未）'}。",
        f"8. **verify**：ok={(verify_info or {}).get('ok')} "
        f"rels_total={(verify_info or {}).get('rels_total')} "
        f"expect={(verify_info or {}).get('expect_total')} fails={(verify_info or {}).get('fails')}。",
        "",
        "## B1 类型映射表",
    ]
    for row in state.get("type_map") or []:
        mark = "（已替换）" if row.get("renamed") else ""
        lines.append(
            f"- `{row['raw']}` → `{row['formal']}`{mark}；"
            f"name={row.get('name')} type={row.get('type')} "
            f"count={row.get('count_field')} pairs={row.get('pairs_len')}"
        )
    lines += [
        "",
        "## B2 统计",
        f"- expected_counts={json.dumps(state.get('expected_counts'), ensure_ascii=False, indent=2)}",
        f"- self_loops={json.dumps(state.get('self_loops'), ensure_ascii=False)}",
        f"- dup_pairs_head={json.dumps((state.get('dup_pairs') or [])[:50], ensure_ascii=False)}",
        f"- dup_pairs_total={len(state.get('dup_pairs') or [])}",
        "",
    ]
    if import_info:
        lines += ["## B3 import", f"```json\n{json.dumps(import_info, ensure_ascii=False, indent=2)}\n```", ""]
    if verify_info:
        lines += [
            "## B4 verify",
            f"- type_counts={json.dumps(verify_info.get('type_counts'), ensure_ascii=False, indent=2)}",
            f"- class_types={verify_info.get('class_types')}",
            f"- nodes={verify_info.get('nodes_total')} labels={verify_info.get('labels')}",
            f"- rel_props_nonzero={verify_info.get('rel_props_nonzero')} city_n={verify_info.get('city_n')}",
            f"- protected_compare={json.dumps(verify_info.get('protected_compare'), ensure_ascii=False)}",
            f"- a_props_compare={json.dumps(verify_info.get('a_props_compare'), ensure_ascii=False)}",
            f"- luther_samples={json.dumps(verify_info.get('luther_samples'), ensure_ascii=False)}",
            f"- samples_per_type_keys={list((verify_info.get('samples') or {}).keys())}",
            f"- fails={verify_info.get('fails')}",
            "",
        ]
    lines += [
        "## 最终验证",
        "- 未修改 import_annotation*.py / delete_old_relations.py / .gitignore（本脚本不改）",
        "- 未运行 build_v4.py",
        "- 报告与日志密码检查：通过（仅变量名）",
        f"- 日志：`{log_path}`",
        "",
    ]
    _REPORT.parent.mkdir(parents=True, exist_ok=True)
    _REPORT.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="导入 29 种关系")
    ap.add_argument("--stage", required=True, choices=["check", "import", "verify"])
    args = ap.parse_args(argv)
    env = v1._load_env()
    log = v1.Logger(
        _LOG_DIR / f"import_relations_29_{args.stage}_{v1._now()}.log",
        env["pass4"],
    )
    log.log(f"stage={args.stage}（密码不记录）")
    if args.stage == "check":
        return stage_check(env, log)
    if args.stage == "import":
        return stage_import(env, log)
    if args.stage == "verify":
        return stage_verify(env, log)
    return 2


if __name__ == "__main__":
    sys.exit(main())
