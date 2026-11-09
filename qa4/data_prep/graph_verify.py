# -*- coding: utf-8 -*-
"""只读比对 neo4j-v4 与 qa4-neo4j 图谱内容是否完全相同。

用法:
  python graph_verify.py              # 交互输入两个库密码后比对
  python graph_verify.py --self-test  # 不连库，用内存数据验证比对逻辑

约束: 图谱数据查询仅用 MATCH；约束列表使用 SHOW CONSTRAINTS（schema，无法用 MATCH）。
密码仅 getpass 交互输入，不写文件、不打印。
文件读写（若新增）一律显式 encoding="utf-8"；哈希等字节转换亦用 UTF-8。
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import json
import sys
from collections import Counter
from typing import Any

# 本模块约定：凡 open / Path.read_text / write_text 必须传 encoding="utf-8"。

URI_V4 = "bolt://localhost:7688"
URI_QA4 = "bolt://localhost:7689"
USER = "neo4j"

# 唯一键：标签 -> 属性名
UNIQUE_KEYS: dict[str, str] = {
    "Truth_Point": "name",
    "Branch": "name",
    "Trunk": "name",
    "Scripture": "ref",
}

ANNOTATION_FIELDS: tuple[str, ...] = (
    "name_en",
    "greek_terms",
    "hebrew_terms",
    "intrinsic_significance",
    "devine_argument",
    "mutuality",
    "organic_advance",
    "high_peak_content",
    "definition_3a",
    "definition_3b",
    "same_as",
)


def _norm_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint_annotations(props: dict[str, Any]) -> str:
    """对标注字段做键排序 JSON，再 sha256。缺省字段不纳入。"""
    payload: dict[str, Any] = {}
    for k in ANNOTATION_FIELDS:
        if k in props and props[k] is not None:
            payload[k] = props[k]
    raw = _norm_json(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def node_key(label: str, props: dict[str, Any]) -> str | None:
    attr = UNIQUE_KEYS.get(label)
    if not attr:
        return None
    val = props.get(attr)
    if val is None:
        return None
    return f"{label}|{val}"


def compare_counters(
    name: str, a: dict[str, int], b: dict[str, int]
) -> list[str]:
    diffs: list[str] = []
    keys = sorted(set(a) | set(b))
    for k in keys:
        av, bv = a.get(k, 0), b.get(k, 0)
        if av != bv:
            diffs.append(f"{name}[{k!r}]: v4={av} qa4={bv}")
    return diffs


def compare_fingerprints(
    a: dict[str, str], b: dict[str, str]
) -> tuple[list[str], list[str], list[str]]:
    """返回 (缺失于 qa4, 多余于 qa4, 内容不同)。"""
    missing = sorted(set(a) - set(b))
    extra = sorted(set(b) - set(a))
    different = sorted(k for k in (set(a) & set(b)) if a[k] != b[k])
    return missing, extra, different


def compare_rel_multisets(
    a: Counter[tuple[str, str, str]], b: Counter[tuple[str, str, str]]
) -> list[str]:
    diffs: list[str] = []
    keys = sorted(set(a) | set(b))
    for k in keys:
        av, bv = a.get(k, 0), b.get(k, 0)
        if av != bv:
            diffs.append(f"rel {k}: v4={av} qa4={bv}")
    return diffs


def run_self_tests() -> int:
    """不连数据库：构造缺失/多余/内容不同/关系重复与全同五组用例。"""
    print("=== graph_verify self-test ===")
    failed = 0

    # 1) 节点指纹：缺失
    a = {"Truth_Point|A": "h1", "Truth_Point|B": "h2"}
    b = {"Truth_Point|A": "h1"}
    missing, extra, different = compare_fingerprints(a, b)
    if missing == ["Truth_Point|B"] and not extra and not different:
        print("PASS 缺失节点")
    else:
        print("FAIL 缺失节点", missing, extra, different)
        failed += 1

    # 2) 多余
    missing, extra, different = compare_fingerprints(b, a)
    if extra == ["Truth_Point|B"] and not missing and not different:
        print("PASS 多余节点")
    else:
        print("FAIL 多余节点", missing, extra, different)
        failed += 1

    # 3) 内容不同
    a2 = {"Truth_Point|A": "h1"}
    b2 = {"Truth_Point|A": "h9"}
    missing, extra, different = compare_fingerprints(a2, b2)
    if different == ["Truth_Point|A"] and not missing and not extra:
        print("PASS 内容不同")
    else:
        print("FAIL 内容不同", missing, extra, different)
        failed += 1

    # 4) 关系重复（多重集合计数）
    ra: Counter[tuple[str, str, str]] = Counter(
        {("Truth_Point|A", "LEADS_TO", "Truth_Point|B"): 1}
    )
    rb: Counter[tuple[str, str, str]] = Counter(
        {("Truth_Point|A", "LEADS_TO", "Truth_Point|B"): 2}
    )
    rd = compare_rel_multisets(ra, rb)
    if len(rd) == 1 and "v4=1" in rd[0] and "qa4=2" in rd[0]:
        print("PASS 关系重复")
    else:
        print("FAIL 关系重复", rd)
        failed += 1

    # 5) 全同
    same_fp = {"Truth_Point|A": fingerprint_annotations({"name_en": "x", "greek_terms": ["g"]})}
    missing, extra, different = compare_fingerprints(same_fp, dict(same_fp))
    same_rel: Counter[tuple[str, str, str]] = Counter(
        {("Truth_Point|A", "LEADS_TO", "Truth_Point|B"): 2}
    )
    rd2 = compare_rel_multisets(same_rel, Counter(same_rel))
    lab = compare_counters("label", {"Truth_Point": 1}, {"Truth_Point": 1})
    if not missing and not extra and not different and not rd2 and not lab:
        print("PASS 全同")
    else:
        print("FAIL 全同", missing, extra, different, rd2, lab)
        failed += 1

    # fingerprint 稳定性
    h1 = fingerprint_annotations({"name_en": "a", "greek_terms": ["x", "y"]})
    h2 = fingerprint_annotations({"greek_terms": ["x", "y"], "name_en": "a"})
    if h1 == h2:
        print("PASS 标注 JSON 键排序稳定")
    else:
        print("FAIL 标注 JSON 键排序稳定")
        failed += 1

    if failed:
        print(f"SELF-TEST FAILED count={failed}")
        return 1
    print("SELF-TEST ALL PASSED")
    return 0


def _fetch_snapshot(driver) -> dict[str, Any]:
    """从已打开的 driver 拉取比对所需快照（MATCH + SHOW CONSTRAINTS）。"""
    label_counts: dict[str, int] = {}
    rel_type_counts: dict[str, int] = {}
    fingerprints: dict[str, str] = {}
    rel_multiset: Counter[tuple[str, str, str]] = Counter()
    annotation_presence: dict[str, int] = {f: 0 for f in ANNOTATION_FIELDS}
    rel_with_props = 0
    constraints: list[str] = []

    with driver.session() as session:
        # 各标签节点数
        rows = session.run(
            "MATCH (n) UNWIND labels(n) AS label RETURN label, count(*) AS c ORDER BY label"
        )
        for r in rows:
            label_counts[str(r["label"])] = int(r["c"])

        # 各关系类型数量
        rows = session.run(
            "MATCH ()-[r]->() RETURN type(r) AS t, count(*) AS c ORDER BY t"
        )
        for r in rows:
            rel_type_counts[str(r["t"])] = int(r["c"])

        # 约束名（schema；无法用 MATCH）
        rows = session.run("SHOW CONSTRAINTS YIELD name RETURN name ORDER BY name")
        constraints = [str(r["name"]) for r in rows]

        # 节点指纹 + 标注非空计数
        for label, attr in UNIQUE_KEYS.items():
            q = (
                f"MATCH (n:{label}) "
                f"RETURN n.{attr} AS key, properties(n) AS props"
            )
            for r in session.run(q):
                key_val = r["key"]
                props = dict(r["props"] or {})
                if key_val is None:
                    continue
                nk = f"{label}|{key_val}"
                fingerprints[nk] = fingerprint_annotations(props)
                for f in ANNOTATION_FIELDS:
                    v = props.get(f)
                    if v is None:
                        continue
                    if isinstance(v, str) and v.strip() == "":
                        continue
                    if isinstance(v, (list, dict)) and len(v) == 0:
                        continue
                    annotation_presence[f] += 1

        # 关系：属性检查 + 多重集合
        # 起点/终点键：按已知唯一标签取值
        rows = session.run(
            """
            MATCH (a)-[r]->(b)
            RETURN type(r) AS t,
                   properties(r) AS rprops,
                   labels(a) AS alabels,
                   properties(a) AS aprops,
                   labels(b) AS blabels,
                   properties(b) AS bprops
            """
        )
        for r in rows:
            rprops = r["rprops"] or {}
            if rprops:
                rel_with_props += 1
            a_key = None
            b_key = None
            for lab in r["alabels"] or []:
                a_key = node_key(str(lab), dict(r["aprops"] or {}))
                if a_key:
                    break
            for lab in r["blabels"] or []:
                b_key = node_key(str(lab), dict(r["bprops"] or {}))
                if b_key:
                    break
            if a_key and b_key:
                rel_multiset[(a_key, str(r["t"]), b_key)] += 1

    return {
        "label_counts": label_counts,
        "rel_type_counts": rel_type_counts,
        "constraints": constraints,
        "fingerprints": fingerprints,
        "rel_multiset": rel_multiset,
        "annotation_presence": annotation_presence,
        "rel_with_props": rel_with_props,
    }


def compare_snapshots(v4: dict[str, Any], qa4: dict[str, Any]) -> list[str]:
    diffs: list[str] = []

    diffs.extend(compare_counters("label_count", v4["label_counts"], qa4["label_counts"]))
    diffs.extend(
        compare_counters("rel_type_count", v4["rel_type_counts"], qa4["rel_type_counts"])
    )

    if len(v4["constraints"]) != len(qa4["constraints"]):
        diffs.append(
            f"constraint_count: v4={len(v4['constraints'])} qa4={len(qa4['constraints'])}"
        )
    if v4["constraints"] != qa4["constraints"]:
        diffs.append(
            f"constraint_names: v4={v4['constraints']} qa4={qa4['constraints']}"
        )

    missing, extra, different = compare_fingerprints(
        v4["fingerprints"], qa4["fingerprints"]
    )
    for k in missing[:50]:
        diffs.append(f"node_missing_in_qa4: {k}")
    if len(missing) > 50:
        diffs.append(f"node_missing_in_qa4: ... 另有 {len(missing) - 50} 条")
    for k in extra[:50]:
        diffs.append(f"node_extra_in_qa4: {k}")
    if len(extra) > 50:
        diffs.append(f"node_extra_in_qa4: ... 另有 {len(extra) - 50} 条")
    for k in different[:50]:
        diffs.append(f"node_fingerprint_diff: {k}")
    if len(different) > 50:
        diffs.append(f"node_fingerprint_diff: ... 另有 {len(different) - 50} 条")

    if v4["rel_with_props"] != 0 or qa4["rel_with_props"] != 0:
        diffs.append(
            f"rel_with_properties: v4={v4['rel_with_props']} qa4={qa4['rel_with_props']}（期望均为 0）"
        )

    diffs.extend(compare_rel_multisets(v4["rel_multiset"], qa4["rel_multiset"]))

    # 标注非空数：并列打印（不预设期望）；不同则记入 diffs
    print("--- 标注非空节点数（并列）---")
    print(f"{'field':24} {'v4':>8} {'qa4':>8}")
    for f in ANNOTATION_FIELDS:
        av = int(v4["annotation_presence"].get(f, 0))
        bv = int(qa4["annotation_presence"].get(f, 0))
        print(f"{f:24} {av:8d} {bv:8d}")
        if av != bv:
            diffs.append(f"annotation_presence[{f}]: v4={av} qa4={bv}")

    return diffs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="比对 neo4j-v4 与 qa4-neo4j")
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="不连库，运行内存比对自测",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_tests()

    try:
        from neo4j import GraphDatabase
    except ImportError:
        print("需要安装 neo4j 驱动: pip install neo4j", file=sys.stderr)
        return 2

    pw_v4 = getpass.getpass(f"密码 neo4j-v4 ({URI_V4}) user={USER}: ")
    pw_qa4 = getpass.getpass(f"密码 qa4-neo4j ({URI_QA4}) user={USER}: ")

    driver_v4 = GraphDatabase.driver(URI_V4, auth=(USER, pw_v4))
    driver_qa4 = GraphDatabase.driver(URI_QA4, auth=(USER, pw_qa4))
    # 尽快丢弃明文引用
    pw_v4 = ""
    pw_qa4 = ""

    try:
        driver_v4.verify_connectivity()
        driver_qa4.verify_connectivity()
        print("连接成功，拉取快照…")
        snap_v4 = _fetch_snapshot(driver_v4)
        snap_qa4 = _fetch_snapshot(driver_qa4)
    finally:
        driver_v4.close()
        driver_qa4.close()

    print("--- 标签节点数 ---")
    labels = sorted(set(snap_v4["label_counts"]) | set(snap_qa4["label_counts"]))
    for lab in labels:
        print(
            f"  {lab}: v4={snap_v4['label_counts'].get(lab, 0)} "
            f"qa4={snap_qa4['label_counts'].get(lab, 0)}"
        )

    print("--- 关系类型数量 ---")
    types = sorted(set(snap_v4["rel_type_counts"]) | set(snap_qa4["rel_type_counts"]))
    for t in types:
        print(
            f"  {t}: v4={snap_v4['rel_type_counts'].get(t, 0)} "
            f"qa4={snap_qa4['rel_type_counts'].get(t, 0)}"
        )

    print(
        f"--- 约束 --- v4={len(snap_v4['constraints'])} {snap_v4['constraints']} | "
        f"qa4={len(snap_qa4['constraints'])} {snap_qa4['constraints']}"
    )

    diffs = compare_snapshots(snap_v4, snap_qa4)
    if diffs:
        print(f"\nFAILED 差异数={len(diffs)}")
        for d in diffs[:200]:
            print(" ", d)
        if len(diffs) > 200:
            print(f"  ... 另有 {len(diffs) - 200} 条")
        return 1

    print("\nOK 两库内容完全相同")
    print(
        f"汇总: labels={len(snap_v4['label_counts'])} "
        f"rel_types={len(snap_v4['rel_type_counts'])} "
        f"constraints={len(snap_v4['constraints'])} "
        f"nodes_fp={len(snap_v4['fingerprints'])} "
        f"rel_edges={sum(snap_v4['rel_multiset'].values())}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
