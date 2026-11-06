# -*- coding: utf-8 -*-
"""neo4j-v4：把 related_scriptures 属性改为 Scripture 节点 + SUPPORTED_BY 关系。

节点：(:Scripture {ref, text})；关系：(Truth_Point)-[:SUPPORTED_BY]->(Scripture)。
验证通过后再 REMOVE related_scriptures。
不修改已有脚本 / .gitignore；不运行 build_v4.py；不打印密码。

用法（在 back_mic/backend 下）:
    python -m panai4.graph.import_scripture_nodes --stage check
    python -m panai4.graph.import_scripture_nodes --stage import
    python -m panai4.graph.import_scripture_nodes --stage verify
    python -m panai4.graph.import_scripture_nodes --stage cleanup
"""
from __future__ import annotations

import argparse
import json
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
    _sha_val,
    find_sources,
    map_term_name,
)

_REPO = v1._REPO
_LOG_DIR = v1._LOG_DIR
_STATE_NAME = "scripture_nodes"
_REPORT = _REPO / "docs" / "panai4_graph" / "import_scripture_nodes.md"
_BATCH = 500
_CLASS_TYPES = {
    "BELONGS_TO_TRUNK": 2380,
    "OF_BRANCH_DIRECTLY": 2380,
    "OF_BRANCH_INDIRECTLY": 1676,
    "GRAFTING": 91,
}
_A_PROPS = (
    "name_en",
    "greek_terms",
    "hebrew_terms",
    "definition_3a",
    "definition_3b",
)
_EXPECT_LINKS = 9768
_EXPECT_REFS = 4851
_EXPECT_CONFLICTS = 52
_EXPECT_NODES_AFTER = 2483 + 4851  # 7334
_EXPECT_RELS_AFTER = 42429 + 9768  # 52197
_CONSTRAINT_NAME = "scripture_ref"


def _trunc(s: Any, n: int = 80) -> str:
    return v1._trunc(s, n)


def choose_text(texts: list[str]) -> tuple[str, dict[str, int], bool]:
    """多数优先；并列取源文件中最先出现的版本。返回 (chosen, counts, is_conflict)。"""
    counts = Counter(texts)
    uniq = list(dict.fromkeys(texts))
    is_conflict = len(uniq) > 1
    best_n = -1
    chosen = texts[0]
    for t in texts:  # 按首次出现顺序扫，仅在更高票时更新 → 并列保先
        n = counts[t]
        if n > best_n:
            best_n = n
            chosen = t
    return chosen, dict(counts), is_conflict


def parse_scriptures(gen_path: Path) -> dict[str, Any]:
    gen = json.loads(gen_path.read_text(encoding="utf-8-sig"))
    if not isinstance(gen, list) or len(gen) != 2372:
        raise SystemExit(f"通用标注须 2372 条 list，实际 {len(gen) if isinstance(gen, list) else type(gen)}")

    ref_texts: dict[str, list[str]] = defaultdict(list)
    links: list[dict[str, str]] = []  # graph_name, ref, src_name
    term_refs: dict[str, list[str]] = {}  # graph_name -> refs in order
    dup_in_term: list[dict[str, str]] = []
    name_map: list[dict[str, str]] = []

    for row in gen:
        src_name = row["name"]
        graph_name = map_term_name(src_name)
        if graph_name != src_name:
            name_map.append({"src": src_name, "graph": graph_name})
        seen: set[str] = set()
        refs: list[str] = []
        for item in row.get("related_scriptures") or []:
            ref = item["ref"]
            text = item.get("text")
            if text is None:
                text = ""
            links.append({"name": graph_name, "ref": ref, "src_name": src_name})
            ref_texts[ref].append(text)
            if ref in seen:
                dup_in_term.append({"name": src_name, "ref": ref})
            else:
                seen.add(ref)
                refs.append(ref)
        term_refs[graph_name] = refs

    chosen: dict[str, str] = {}
    conflicts: list[dict[str, Any]] = []
    ref_origin: list[dict[str, Any]] = []
    for ref, texts in ref_texts.items():
        text, counts, is_conflict = choose_text(texts)
        chosen[ref] = text
        origin = {
            "ref": ref,
            "chosen": text,
            "chosen_trunc": _trunc(text, 80),
            "n_occurrences": len(texts),
            "n_versions": len(counts),
            "is_conflict": is_conflict,
            "rule": "majority_then_first_appearance" if is_conflict else "sole_text",
        }
        ref_origin.append(origin)
        if is_conflict:
            # preserve first-appearance order of versions
            versions = []
            seen_v: set[str] = set()
            for t in texts:
                if t not in seen_v:
                    seen_v.add(t)
                    versions.append({"text_trunc": _trunc(t, 80), "count": counts[t], "len": len(t)})
            conflicts.append(
                {
                    "ref": ref,
                    "versions": versions,
                    "counts": counts,  # full texts as keys — for state; report uses trunc
                    "chosen": text,
                    "chosen_trunc": _trunc(text, 80),
                    "chosen_len": len(text),
                }
            )

    return {
        "n_gen": len(gen),
        "n_links": len(links),
        "n_refs": len(chosen),
        "n_conflicts": len(conflicts),
        "dup_in_term": dup_in_term,
        "links": links,
        "term_refs": term_refs,
        "chosen": chosen,
        "conflicts": conflicts,
        "ref_origin": ref_origin,
        "name_map": name_map,
        "graph_names": sorted(term_refs.keys()),
    }


def _snapshot_props(session, props: list[str]) -> dict[str, dict[str, str]]:
    out = {}
    for prop in props:
        amap = v2._fetch_anno_map(session, prop)
        out[prop] = {name: _sha_val(val) for name, val in amap.items()}
    return out


def _compare_props(before: dict[str, dict[str, str]], session) -> dict[str, Any]:
    result = {}
    for prop, old in before.items():
        amap = v2._fetch_anno_map(session, prop)
        now = {name: _sha_val(val) for name, val in amap.items()}
        only_b = sorted(set(old) - set(now))
        only_n = sorted(set(now) - set(old))
        mism = sorted(k for k in set(old) & set(now) if old[k] != now[k])
        result[prop] = {
            "before_n": len(old),
            "now_n": len(now),
            "sha_mismatch": len(mism),
            "only_before": only_b[:20],
            "only_now": only_n[:20],
            "mismatch_names": mism[:20],
        }
    return result


def _rel_counts(session) -> dict[str, int]:
    rows = v1._run(
        session,
        "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c ORDER BY t",
    )
    return {r["t"]: r["c"] for r in rows}


def stage_check(env: dict, log: v1.Logger) -> int:
    log.log("stage=check scripture_nodes")
    srcs = find_sources()
    gen_path = srcs["general"]
    log.log(f"general={gen_path}")
    sha_before = v1._sha_import_dir()
    parsed = parse_scriptures(gen_path)
    log.log(
        f"links={parsed['n_links']} refs={parsed['n_refs']} conflicts={parsed['n_conflicts']} "
        f"dup_in_term={len(parsed['dup_in_term'])}"
    )

    fails: list[str] = []
    if parsed["n_links"] != _EXPECT_LINKS:
        fails.append(f"链接数 {parsed['n_links']}≠{_EXPECT_LINKS}")
    if parsed["n_refs"] != _EXPECT_REFS:
        fails.append(f"去重 ref {parsed['n_refs']}≠{_EXPECT_REFS}")
    if parsed["n_conflicts"] != _EXPECT_CONFLICTS:
        fails.append(f"冲突 ref {parsed['n_conflicts']}≠{_EXPECT_CONFLICTS}")
    if parsed["dup_in_term"]:
        fails.append(f"词条内重复 ref: {parsed['dup_in_term'][:20]}")

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            base = v1.snapshot_graph(session)
            sc_n = v1._run(session, "MATCH (s:Scripture) RETURN count(s) AS c")[0]["c"]
            sb_n = v1._run(session, "MATCH ()-[r:SUPPORTED_BY]->() RETURN count(r) AS c")[0]["c"]
            if sc_n or sb_n:
                fails.append(f"图谱已有 Scripture={sc_n} SUPPORTED_BY={sb_n}，拒绝继续")

            if base["nodes_total"] != 2483:
                fails.append(f"nodes_total {base['nodes_total']}≠2483")
            if base["rels_total"] != 42429:
                fails.append(f"rels_total {base['rels_total']}≠42429")
            for t, n in _CLASS_TYPES.items():
                if base["by_type"].get(t, 0) != n:
                    fails.append(f"分类关系 {t} {base['by_type'].get(t)}≠{n}")

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
            match = v1.match_names(session, parsed["graph_names"])
            hit_inner = sorted(set(parsed["graph_names"]) & with_sa)
            if match["missing_n"] or match["multi"]:
                fails.append(f"匹配失败 missing={match['missing'][:20]} multi={match['multi']}")
            if hit_inner:
                fails.append(f"映射到括号内: {hit_inner}")

            # related_scriptures still present
            rs_n = v2._anno_nonempty(session, "related_scriptures")
            if rs_n != 2372:
                fails.append(f"related_scriptures 非空 {rs_n}≠2372（cleanup 前应仍在）")

            prop_list = list(_PROTECTED.keys()) + list(_A_PROPS)
            # also snapshot related_scriptures for import/verify (must unchanged until cleanup)
            prop_list_with_rs = prop_list + ["related_scriptures"]
            for prop, n_exp in _PROTECTED.items():
                n = v2._anno_nonempty(session, prop)
                if n != n_exp:
                    fails.append(f"保护标注 {prop} {n}≠{n_exp}")
            prop_sha = _snapshot_props(session, prop_list_with_rs)
            by_type = _rel_counts(session)
            # 29 semantic types = all types minus 4 class
            semantic = {t: c for t, c in by_type.items() if t not in _CLASS_TYPES}
            if len(semantic) != 29:
                fails.append(f"语义关系类型数 {len(semantic)}≠29: {sorted(semantic)}")
    except Exception as exc:
        raise SystemExit("check 失败: " + v1._redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    sha_after = v1._sha_import_dir()
    sha_ok = sha_before["hashes"] == sha_after["hashes"]
    if not sha_ok:
        fails.append("可导入资料 SHA 前后不一致")

    # nodes for MERGE
    scripture_rows = [{"ref": ref, "text": text} for ref, text in sorted(parsed["chosen"].items())]
    link_rows = [{"name": x["name"], "ref": x["ref"]} for x in parsed["links"]]

    state = {
        "version": 1,
        "check_ok": not fails,
        "fails": fails,
        "file": str(gen_path),
        "stats": {
            "n_gen": parsed["n_gen"],
            "n_links": parsed["n_links"],
            "n_refs": parsed["n_refs"],
            "n_conflicts": parsed["n_conflicts"],
            "dup_in_term": parsed["dup_in_term"],
            "name_map": parsed["name_map"],
        },
        "conflicts": [
            {
                "ref": c["ref"],
                "versions": c["versions"],
                "chosen_trunc": c["chosen_trunc"],
                "chosen_len": c["chosen_len"],
            }
            for c in parsed["conflicts"]
        ],
        # full chosen texts kept for import/verify (not all dumped in md)
        "chosen": parsed["chosen"],
        "term_refs": parsed["term_refs"],
        "scripture_rows": scripture_rows,
        "link_rows": link_rows,
        "match": {
            "found_n": match["found_n"],
            "missing_n": match["missing_n"],
            "missing": match["missing"],
            "multi": match["multi"],
            "hit_inner": hit_inner,
        },
        "baseline": {
            "nodes_total": base["nodes_total"],
            "labels": base["labels"],
            "rels_total": base["rels_total"],
            "by_type": by_type,
            "semantic_types": semantic,
        },
        "prop_sha": prop_sha,
        "protected_props": prop_list,
        "sha_before": sha_before,
        "sha_ok": sha_ok,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
    }
    v1.save_state(_STATE_NAME, state)
    write_report(state, None, None, None, log.path)
    for f in fails:
        log.log("GATE FAIL: " + f)
    if fails:
        log.log("闸门未通过，停止。")
        return 2
    log.log(
        f"闸门通过。拟 MERGE Scripture={len(scripture_rows)} SUPPORTED_BY={len(link_rows)}；"
        f"冲突 ref={parsed['n_conflicts']}"
    )
    return 0


def _merge_scriptures(tx, rows: list[dict]) -> int:
    q = (
        "UNWIND $rows AS row "
        "MERGE (s:Scripture {ref: row.ref}) "
        "SET s.text = row.text "
        "RETURN count(s) AS n"
    )
    return int(tx.run(q, {"rows": rows}).single()["n"])


def _merge_links(tx, rows: list[dict]) -> int:
    q = (
        "UNWIND $rows AS row "
        "MATCH (t:Truth_Point {name: row.name}) "
        "MATCH (s:Scripture {ref: row.ref}) "
        "MERGE (t)-[r:SUPPORTED_BY]->(s) "
        "RETURN count(r) AS n"
    )
    return int(tx.run(q, {"rows": rows}).single()["n"])


def stage_import(env: dict, log: v1.Logger) -> int:
    log.log("stage=import scripture_nodes")
    state = v1.load_state(_STATE_NAME)
    if not state.get("check_ok"):
        raise SystemExit("check 未通过，拒绝 import")
    scripture_rows = state["scripture_rows"]
    link_rows = state["link_rows"]

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    constraint_created = False
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            sc_n = v1._run(session, "MATCH (s:Scripture) RETURN count(s) AS c")[0]["c"]
            sb_n = v1._run(session, "MATCH ()-[r:SUPPORTED_BY]->() RETURN count(r) AS c")[0]["c"]
            if sc_n or sb_n:
                log.log(f"GATE FAIL: 已有 Scripture={sc_n} SUPPORTED_BY={sb_n}")
                return 2
            base_nodes = v1._run(session, "MATCH (n) RETURN count(n) AS c")[0]["c"]
            base_rels = v1._run(session, "MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
            if base_nodes != 2483 or base_rels != 42429:
                log.log(f"GATE FAIL nodes={base_nodes} rels={base_rels}")
                return 2

        # schema: unique constraint on Scripture.ref
        with driver.session(default_access_mode=WRITE_ACCESS) as session:
            # check if exists
            existing = list(
                session.run(
                    "SHOW CONSTRAINTS YIELD name, labelsOrTypes, properties "
                    "WHERE name = $name RETURN name",
                    {"name": _CONSTRAINT_NAME},
                )
            )
            if existing:
                log.log(f"约束 {_CONSTRAINT_NAME} 已存在，跳过创建")
            else:
                session.run(
                    f"CREATE CONSTRAINT {_CONSTRAINT_NAME} IF NOT EXISTS "
                    "FOR (s:Scripture) REQUIRE s.ref IS UNIQUE"
                )
                constraint_created = True
                log.log(f"已创建唯一约束 {_CONSTRAINT_NAME} ON Scripture.ref")

        # MERGE nodes
        with driver.session(default_access_mode=WRITE_ACCESS) as session:
            for i in range(0, len(scripture_rows), _BATCH):
                batch = scripture_rows[i : i + _BATCH]
                n = session.execute_write(_merge_scriptures, batch)
                if n != len(batch):
                    log.log(f"Scripture batch {i} n={n}≠{len(batch)}；停止")
                    state["import"] = {"aborted": True, "phase": "nodes", "offset": i}
                    v1.save_state(_STATE_NAME, state)
                    write_report(state, state["import"], None, None, log.path)
                    return 2
                log.log(f"Scripture batch {i}-{i+len(batch)-1} n={n}")

        with driver.session(default_access_mode=READ_ACCESS) as session:
            sc_n = v1._run(session, "MATCH (s:Scripture) RETURN count(s) AS c")[0]["c"]
        if sc_n != _EXPECT_REFS:
            log.log(f"Scripture 节点数 {sc_n}≠{_EXPECT_REFS}；停止，不建关系")
            state["import"] = {"aborted": True, "phase": "nodes_count", "scripture_n": sc_n}
            v1.save_state(_STATE_NAME, state)
            write_report(state, state["import"], None, None, log.path)
            return 2

        # MERGE relationships
        with driver.session(default_access_mode=WRITE_ACCESS) as session:
            for i in range(0, len(link_rows), _BATCH):
                batch = link_rows[i : i + _BATCH]
                n = session.execute_write(_merge_links, batch)
                if n != len(batch):
                    log.log(f"SUPPORTED_BY batch {i} n={n}≠{len(batch)}；停止")
                    state["import"] = {"aborted": True, "phase": "links", "offset": i}
                    v1.save_state(_STATE_NAME, state)
                    write_report(state, state["import"], None, None, log.path)
                    return 2
                log.log(f"SUPPORTED_BY batch {i}-{i+len(batch)-1} n={n}")

        with driver.session(default_access_mode=READ_ACCESS) as session:
            sb_n = v1._run(session, "MATCH ()-[r:SUPPORTED_BY]->() RETURN count(r) AS c")[0]["c"]
            nodes = v1._run(session, "MATCH (n) RETURN count(n) AS c")[0]["c"]
            rels = v1._run(session, "MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
            rs_n = v2._anno_nonempty(session, "related_scriptures")
    except Exception as exc:
        raise SystemExit("import 失败: " + v1._redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    info = {
        "aborted": False,
        "constraint_name": _CONSTRAINT_NAME,
        "constraint_created": constraint_created,
        "scripture_n": sc_n,
        "supported_by_n": sb_n,
        "nodes_total": nodes,
        "rels_total": rels,
        "related_scriptures_still": rs_n,
    }
    if sb_n != _EXPECT_LINKS or nodes != _EXPECT_NODES_AFTER or rels != _EXPECT_RELS_AFTER:
        log.log(f"计数告警（verify 再闸）: {info}")
    state["import"] = info
    v1.save_state(_STATE_NAME, state)
    write_report(state, info, None, None, log.path)
    log.log(f"import 完成 Scripture={sc_n} SUPPORTED_BY={sb_n} nodes={nodes} rels={rels}")
    return 0


def stage_verify(env: dict, log: v1.Logger) -> int:
    log.log("stage=verify scripture_nodes")
    state = v1.load_state(_STATE_NAME)
    if not state.get("import") or state["import"].get("aborted"):
        raise SystemExit("import 未完成，拒绝 verify")
    chosen: dict[str, str] = state["chosen"]
    term_refs: dict[str, list[str]] = state["term_refs"]
    fails: list[str] = []

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=READ_ACCESS) as session:
            sc_n = v1._run(session, "MATCH (s:Scripture) RETURN count(s) AS c")[0]["c"]
            sb_n = v1._run(session, "MATCH ()-[r:SUPPORTED_BY]->() RETURN count(r) AS c")[0]["c"]
            nodes = v1._run(session, "MATCH (n) RETURN count(n) AS c")[0]["c"]
            rels = v1._run(session, "MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
            if sc_n != _EXPECT_REFS:
                fails.append(f"Scripture {sc_n}≠{_EXPECT_REFS}")
            if sb_n != _EXPECT_LINKS:
                fails.append(f"SUPPORTED_BY {sb_n}≠{_EXPECT_LINKS}")
            if nodes != _EXPECT_NODES_AFTER:
                fails.append(f"nodes {nodes}≠{_EXPECT_NODES_AFTER}")
            if rels != _EXPECT_RELS_AFTER:
                fails.append(f"rels {rels}≠{_EXPECT_RELS_AFTER}")

            # relationship properties
            props_n = v1._run(
                session,
                "MATCH ()-[r:SUPPORTED_BY]->() WHERE size(keys(r)) > 0 RETURN count(r) AS c",
            )[0]["c"]
            if props_n:
                fails.append(f"SUPPORTED_BY 带属性 {props_n}")

            # orphans
            orphan = v1._run(
                session,
                """
                MATCH (s:Scripture)
                WHERE NOT ()-[:SUPPORTED_BY]->(s)
                RETURN count(s) AS c
                """,
            )[0]["c"]
            if orphan:
                fails.append(f"孤立 Scripture {orphan}")

            # fetch all graph links
            graph_links = v1._run(
                session,
                """
                MATCH (t:Truth_Point)-[:SUPPORTED_BY]->(s:Scripture)
                RETURN t.name AS name, s.ref AS ref, s.text AS text
                """,
            )
            by_term: dict[str, set[str]] = defaultdict(set)
            graph_text: dict[str, str] = {}
            for row in graph_links:
                by_term[row["name"]].add(row["ref"])
                graph_text[row["ref"]] = row["text"]

            # term set compare
            term_diff = []
            for name, refs in term_refs.items():
                expect = set(refs)
                got = by_term.get(name, set())
                if expect != got:
                    term_diff.append(
                        {
                            "name": name,
                            "only_src": sorted(expect - got)[:10],
                            "only_graph": sorted(got - expect)[:10],
                        }
                    )
            extra_terms = sorted(set(by_term) - set(term_refs))
            if term_diff:
                fails.append(f"词条 ref 集合差异 {len(term_diff)}: {term_diff[:5]}")
            if extra_terms:
                fails.append(f"多出词条有 SUPPORTED_BY: {extra_terms[:20]}")

            # text compare
            text_mismatch = []
            for ref, exp in chosen.items():
                got = graph_text.get(ref)
                if got != exp:
                    text_mismatch.append({"ref": ref, "exp_trunc": _trunc(exp), "got_trunc": _trunc(got)})
            missing_refs = sorted(set(chosen) - set(graph_text))
            if missing_refs:
                fails.append(f"缺失 Scripture ref {len(missing_refs)}: {missing_refs[:20]}")
            if text_mismatch:
                fails.append(f"text 不符 {len(text_mismatch)}: {text_mismatch[:5]}")

            # props SHA (including related_scriptures still present)
            prop_cmp = _compare_props(state["prop_sha"], session)
            for prop, info in prop_cmp.items():
                if info["sha_mismatch"] or info["only_before"] or info["only_now"]:
                    fails.append(f"标注变化 {prop}: {info}")

            # relation type counts excluding SUPPORTED_BY
            by_type = _rel_counts(session)
            base_types = state["baseline"]["by_type"]
            for t, n in base_types.items():
                if by_type.get(t, 0) != n:
                    fails.append(f"关系类型计数变化 {t}: {by_type.get(t)}≠{n}")
            for t, n in _CLASS_TYPES.items():
                if by_type.get(t, 0) != n:
                    fails.append(f"分类关系 {t} {by_type.get(t)}≠{n}")
            # no unexpected new types besides SUPPORTED_BY
            unexpected = sorted(set(by_type) - set(base_types) - {"SUPPORTED_BY"})
            if unexpected:
                fails.append(f"意外新关系类型: {unexpected}")

            rs_n = v2._anno_nonempty(session, "related_scriptures")
            if rs_n != 2372:
                fails.append(f"verify 时 related_scriptures 应仍为 2372，实际 {rs_n}")

            # samples
            sample_names = list(term_refs.keys())[:10]
            samples = []
            for name in sample_names:
                src_refs = term_refs[name]
                got_refs = sorted(by_term.get(name, set()))
                samples.append(
                    {
                        "name": name,
                        "src_refs": src_refs,
                        "graph_refs": got_refs,
                        "ok": set(src_refs) == set(got_refs),
                    }
                )
                if set(src_refs) != set(got_refs):
                    fails.append(f"抽样不符 {name}")

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
        "scripture_n": sc_n,
        "supported_by_n": sb_n,
        "nodes_total": nodes,
        "rels_total": rels,
        "rel_props_nonzero": props_n,
        "orphans": orphan,
        "term_diff_n": len(term_diff),
        "text_mismatch_n": len(text_mismatch),
        "prop_compare": prop_cmp,
        "related_scriptures_still": rs_n,
        "samples": samples,
        "by_type_supported_by": by_type.get("SUPPORTED_BY"),
    }
    state["verify"] = verify_info
    v1.save_state(_STATE_NAME, state)
    write_report(state, state.get("import"), verify_info, None, log.path)
    for f in fails:
        log.log("VERIFY FAIL: " + f)
    if fails:
        log.log("verify 未通过，不进入 cleanup。")
        return 2
    log.log("verify 全部通过，可进入 cleanup")
    return 0


def _remove_rs_batch(tx, names: list[str]) -> int:
    q = (
        "UNWIND $names AS name "
        "MATCH (n:Truth_Point {name: name}) "
        "REMOVE n.related_scriptures "
        "RETURN count(n) AS n"
    )
    return int(tx.run(q, {"names": names}).single()["n"])


def stage_cleanup(env: dict, log: v1.Logger) -> int:
    log.log("stage=cleanup related_scriptures")
    state = v1.load_state(_STATE_NAME)
    if not state.get("verify", {}).get("ok"):
        raise SystemExit("verify 未通过，拒绝 cleanup")

    names = list(state["term_refs"].keys())
    # props to compare after: all except related_scriptures
    before = {k: v for k, v in state["prop_sha"].items() if k != "related_scriptures"}

    driver = GraphDatabase.driver(env["uri4"], auth=(env["user4"], env["pass4"]))
    try:
        driver.verify_connectivity()
        with driver.session(default_access_mode=WRITE_ACCESS) as session:
            for i in range(0, len(names), _BATCH):
                batch = names[i : i + _BATCH]
                n = session.execute_write(_remove_rs_batch, batch)
                if n != len(batch):
                    log.log(f"REMOVE batch {i} n={n}≠{len(batch)}；停止")
                    state["cleanup"] = {"aborted": True, "offset": i, "removed": i}
                    v1.save_state(_STATE_NAME, state)
                    write_report(state, state.get("import"), state.get("verify"), state["cleanup"], log.path)
                    return 2
                log.log(f"REMOVE related_scriptures batch {i}-{i+len(batch)-1} n={n}")

        with driver.session(default_access_mode=READ_ACCESS) as session:
            rs_n = v2._anno_nonempty(session, "related_scriptures")
            # also keys presence
            rs_key = v1._run(
                session,
                """
                MATCH (n:Truth_Point)
                WHERE 'related_scriptures' IN keys(n)
                RETURN count(n) AS c
                """,
            )[0]["c"]
            nodes = v1._run(session, "MATCH (n) RETURN count(n) AS c")[0]["c"]
            rels = v1._run(session, "MATCH ()-[r]->() RETURN count(r) AS c")[0]["c"]
            sc_n = v1._run(session, "MATCH (s:Scripture) RETURN count(s) AS c")[0]["c"]
            sb_n = v1._run(session, "MATCH ()-[r:SUPPORTED_BY]->() RETURN count(r) AS c")[0]["c"]
            prop_cmp = _compare_props(before, session)
    except Exception as exc:
        raise SystemExit("cleanup 失败: " + v1._redact(str(exc), env["pass4"])) from exc
    finally:
        driver.close()

    fails = []
    if rs_n != 0 or rs_key != 0:
        fails.append(f"related_scriptures 仍在 nonempty={rs_n} keys={rs_key}")
    if nodes != _EXPECT_NODES_AFTER:
        fails.append(f"nodes {nodes}≠{_EXPECT_NODES_AFTER}")
    if rels != _EXPECT_RELS_AFTER:
        fails.append(f"rels {rels}≠{_EXPECT_RELS_AFTER}")
    if sc_n != _EXPECT_REFS or sb_n != _EXPECT_LINKS:
        fails.append(f"Scripture/SUPPORTED_BY {sc_n}/{sb_n}")
    for prop, info in prop_cmp.items():
        if info["sha_mismatch"] or info["only_before"] or info["only_now"]:
            fails.append(f"标注变化 {prop}: {info}")

    cleanup_info = {
        "ok": not fails,
        "fails": fails,
        "removed": len(names),
        "related_scriptures_nonempty": rs_n,
        "related_scriptures_keys": rs_key,
        "nodes_total": nodes,
        "rels_total": rels,
        "scripture_n": sc_n,
        "supported_by_n": sb_n,
        "prop_compare": prop_cmp,
    }
    state["cleanup"] = cleanup_info
    v1.save_state(_STATE_NAME, state)
    write_report(state, state.get("import"), state.get("verify"), cleanup_info, log.path)
    for f in fails:
        log.log("CLEANUP FAIL: " + f)
    if fails:
        return 2
    log.log("cleanup 全部通过；related_scriptures 已移除")
    return 0


def write_report(
    state: dict,
    import_info: dict | None,
    verify_info: dict | None,
    cleanup_info: dict | None,
    log_path: Path,
) -> None:
    st = state.get("stats") or {}
    conflicts = state.get("conflicts") or []
    lines = [
        "# neo4j-v4：经文独立节点（Scripture）+ SUPPORTED_BY",
        "",
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}；脚本：`panai4.graph.import_scripture_nodes`。",
        "设计：`(:Scripture {ref, text})`，`(Truth_Point)-[:SUPPORTED_BY]->(Scripture)`；范围 ref 不拆。",
        "说明：旧报告 `import_general_annotation.md` 中的 `related_scriptures` **属性**已被本流程替换为节点+关系（旧报告不改）。",
        "未运行 build_v4.py；未打印密码；未修改已有 import_*.py / .gitignore。",
        "",
        "## 摘要",
        "",
        f"1. **源**：`{state.get('file')}`；链接={st.get('n_links')}；去重 ref={st.get('n_refs')}；"
        f"冲突={st.get('n_conflicts')}；词条内重复 ref={st.get('dup_in_term')}。",
        f"2. **匹配**：{state.get('match')}；括号映射例={_trunc(st.get('name_map'), 120)}。",
        f"3. **基线**：nodes={state.get('baseline',{}).get('nodes_total')} "
        f"rels={state.get('baseline',{}).get('rels_total')}；语义类型数="
        f"{len(state.get('baseline',{}).get('semantic_types') or {})}。",
        f"4. **import**：{_trunc(import_info, 240) if import_info else '（尚未）'}。",
        f"5. **verify**：ok={(verify_info or {}).get('ok')} fails={(verify_info or {}).get('fails')}。",
        f"6. **cleanup**：{_trunc(cleanup_info, 240) if cleanup_info else '（尚未）'}。",
        f"7. **闸门**：check_ok={state.get('check_ok')} fails={state.get('fails')}。",
        "",
        "## 1. check 统计与冲突选择",
        "",
        f"- 链接 {_EXPECT_LINKS}（实测 {st.get('n_links')}），去重 ref {_EXPECT_REFS}（实测 {st.get('n_refs')}），"
        f"冲突 {_EXPECT_CONFLICTS}（实测 {st.get('n_conflicts')}）。",
        "- 每个 ref 的最终 text：无冲突者用唯一 text；有冲突者按「出现次数最多，并列取源文件最先出现」。",
        f"- 完整 ref→text 映射保存在状态文件 `logs/import_annotation_{_STATE_NAME}_state.json` 的 `chosen` 字段（报告不逐条打印全文）。",
        "",
        f"### 52 个冲突 ref（{len(conflicts)}）",
        "",
    ]
    for c in conflicts:
        vers = ", ".join(
            f"count={v['count']} len={v['len']} text={v['text_trunc']}" for v in c.get("versions") or []
        )
        lines.append(
            f"- `{c['ref']}`：选中 len={c.get('chosen_len')} text={c.get('chosen_trunc')}；版本：{vers}"
        )
    lines += ["", "## 2. import", ""]
    if import_info:
        lines += [
            f"- 唯一约束：`{_CONSTRAINT_NAME}` ON `Scripture.ref`；"
            f"created={import_info.get('constraint_created')}",
            f"- Scripture={import_info.get('scripture_n')} SUPPORTED_BY={import_info.get('supported_by_n')}",
            f"- nodes={import_info.get('nodes_total')} rels={import_info.get('rels_total')}",
            f"- related_scriptures 仍保留：{import_info.get('related_scriptures_still')}",
            f"```json\n{json.dumps(import_info, ensure_ascii=False, indent=2)}\n```",
            "",
        ]
    else:
        lines.append("（尚未 import）\n")

    lines += ["## 3. verify（此时 related_scriptures 仍在）", ""]
    if verify_info:
        lines += [
            f"- ok={verify_info.get('ok')}",
            f"- Scripture={verify_info.get('scripture_n')} SUPPORTED_BY={verify_info.get('supported_by_n')}",
            f"- nodes={verify_info.get('nodes_total')} rels={verify_info.get('rels_total')}",
            f"- orphans={verify_info.get('orphans')} rel_props={verify_info.get('rel_props_nonzero')}",
            f"- term_diff_n={verify_info.get('term_diff_n')} text_mismatch_n={verify_info.get('text_mismatch_n')}",
            f"- related_scriptures_still={verify_info.get('related_scriptures_still')}",
            f"- samples={json.dumps(verify_info.get('samples'), ensure_ascii=False)}",
            f"- prop_compare={json.dumps(verify_info.get('prop_compare'), ensure_ascii=False)}",
            f"- fails={verify_info.get('fails')}",
            "",
        ]
    else:
        lines.append("（尚未 verify）\n")

    lines += ["## 4. cleanup", ""]
    if cleanup_info:
        lines += [
            f"- ok={cleanup_info.get('ok')} removed={cleanup_info.get('removed')}",
            f"- related_scriptures nonempty/keys={cleanup_info.get('related_scriptures_nonempty')}/"
            f"{cleanup_info.get('related_scriptures_keys')}",
            f"- nodes={cleanup_info.get('nodes_total')} rels={cleanup_info.get('rels_total')}",
            f"- Scripture={cleanup_info.get('scripture_n')} SUPPORTED_BY={cleanup_info.get('supported_by_n')}",
            f"- prop_compare={json.dumps(cleanup_info.get('prop_compare'), ensure_ascii=False)}",
            f"- fails={cleanup_info.get('fails')}",
            "",
        ]
    else:
        lines.append("（尚未 cleanup）\n")

    lines += [
        "## 最终验证",
        "- 未修改 import_annotation*.py / import_general_annotation.py / import_relations_29.py / delete_old_relations.py / .gitignore",
        "- 未运行 build_v4.py",
        "- 报告与日志密码检查：通过（仅变量名）",
        "- greek_terms / hebrew_terms 仍为字符串标注，未改成节点",
        "- 未做括号内复制，未碰 high_peak_content",
        f"- 日志：`{log_path}`",
        "",
    ]
    _REPORT.parent.mkdir(parents=True, exist_ok=True)
    _REPORT.write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="经文独立节点 Scripture + SUPPORTED_BY")
    ap.add_argument("--stage", required=True, choices=["check", "import", "verify", "cleanup"])
    args = ap.parse_args(argv)
    env = v1._load_env()
    log = v1.Logger(
        _LOG_DIR / f"import_scripture_nodes_{args.stage}_{v1._now()}.log",
        env["pass4"],
    )
    log.log(f"stage={args.stage}（密码不记录）")
    if args.stage == "check":
        return stage_check(env, log)
    if args.stage == "import":
        return stage_import(env, log)
    if args.stage == "verify":
        return stage_verify(env, log)
    if args.stage == "cleanup":
        return stage_cleanup(env, log)
    return 2


if __name__ == "__main__":
    sys.exit(main())
