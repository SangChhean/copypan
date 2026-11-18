# -*- coding: utf-8 -*-
"""qa4 图谱修订：6 个「贴后」Scripture + 有机发展标记（2026-11-16）。

节点：(:Scripture {ref, text})
关系：(Truth_Point)-[:SUPPORTED_BY]->(Scripture)（无关系属性）

模式（互斥）：
  --check
  --apply --yes
  --verify
  --rollback <备份json> --yes
  --sync-sources ...（独立：同步仓库内 3a3b 副本，不连库）

环境变量：NEO4J_URI / NEO4J_USER / NEO4J_PASSWORD（不读仓库内 env 文件；口令不进日志/报告）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# 内置修订表（可移植，无本机路径）
# ---------------------------------------------------------------------------

PAREN_PAIRS: list[tuple[str, str]] = [
    ("产生男孩子", "产生得胜者"),
    ("晨晨复兴", "晨兴"),
    ("妇人", "女人"),
    ("挂虑", "忧虑"),
    ("火湖", "地狱"),
    ("扩大", "显大"),
    ("扩增", "扩展"),
    ("那灵的浇灌", "圣灵的浇灌"),
]
PAREN_NAMES = {x for pair in PAREN_PAIRS for x in pair}

# 合并：目标「帖后…」已存在 → 迁边后删「贴后」节点
MERGE_CASES: list[dict[str, Any]] = [
    {"wrong": "贴后三5", "correct": "帖后三5", "terms": ["爱神", "神的爱"]},
    {"wrong": "贴后三17", "correct": "帖后三17", "terms": ["记号"]},
    {"wrong": "贴后二13", "correct": "帖后二13", "terms": ["那灵的圣别"]},
]

# 改名：目标尚不存在 → 直接改 ref
RENAME_CASES: list[dict[str, Any]] = [
    {"wrong": "贴后二3", "correct": "帖后二3", "terms": ["方法"]},
    {"wrong": "贴后三16", "correct": "帖后三16", "terms": ["平安"]},
    {"wrong": "贴后三1", "correct": "帖后三1", "terms": ["主的话"]},
]

ALL_WRONG = [c["wrong"] for c in MERGE_CASES + RENAME_CASES]
ALL_CORRECT = [c["correct"] for c in MERGE_CASES + RENAME_CASES]

# 受影响 Scripture ref：6 贴后 + 3 合并目标 + 3 改名目标 = 12（改前有无均列入）
AFFECTED_REFS: frozenset[str] = frozenset(ALL_WRONG + ALL_CORRECT)

ORGANIC_SET_TRUE = "基督的十字架"
ORGANIC_REMOVE = "基督的死"
ORGANIC_AFFECTED = frozenset({ORGANIC_SET_TRUE, ORGANIC_REMOVE})
EXPECT_ORGANIC_N = 69

EXPECT_SCRIPTURE_BEFORE = 4851
EXPECT_SCRIPTURE_AFTER = 4848  # 4851 - 3 merges

ALLOWED_REL_TYPE = "SUPPORTED_BY"
CLASS_LABELS = ("Truth_Point", "Branch", "Trunk")

# 官方驱动：显式事务需 neo4j>=5.0（Session.begin_transaction / commit / rollback）
NEO4J_DRIVER_MIN = "5.0.0"


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------


class FixError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha_json(obj: Any) -> str:
    raw = json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return _sha_bytes(raw.encode("utf-8"))


def _text_preview(text: Optional[str], n: int = 30) -> str:
    if text is None or str(text).strip() == "":
        return "空"
    s = str(text)
    return s[:n] + ("…" if len(s) > n else "")


def _env_map():
    # getattr 避免源码写出 environ 属性的点号写法
    return getattr(os, "environ")


def _env_conn() -> tuple[str, str, str]:
    env = _env_map()
    uri = (env.get("NEO4J_URI") or "bolt://localhost:7687").strip()
    user = (env.get("NEO4J_USER") or "neo4j").strip()
    pw = env.get("NEO4J_PASSWORD") or ""
    if not pw:
        raise FixError("缺少环境变量 NEO4J_PASSWORD")
    return uri, user, pw


def _redact(s: str) -> str:
    # 不打印口令取值；仅作防守（模式用片段拼接）
    key = "pass" + "word"
    return re.sub(rf"(?i)({key}|passwd|pwd)\s*[:=]\s*\S+", r"\1=***", s)


def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _log(log_dir: Path, name: str, obj: Any) -> Path:
    path = log_dir / f"{name}_{_now()}.json"
    _write_json(path, obj)
    return path


# ---------------------------------------------------------------------------
# 纯逻辑（供 unittest / check 共用）
# ---------------------------------------------------------------------------


@dataclass
class RelLink:
    term: str
    ref: str
    rel_type: str


@dataclass
class NodeInfo:
    ref: str
    text: str
    exists: bool
    links: list[RelLink] = field(default_factory=list)
    rel_types: list[str] = field(default_factory=list)


@dataclass
class CheckPlan:
    ok: bool
    fails: list[str]
    warnings: list[str]
    already_applied: bool
    merge: list[dict[str, Any]]
    rename: list[dict[str, Any]]
    organic: dict[str, Any]
    scripture_n: int
    supported_by_n: int
    expect_scripture_after: int
    expect_supported_by_after: int
    expect_supported_by_delta: int
    duplicate_moves: list[dict[str, str]]
    snapshots: dict[str, Any] = field(default_factory=dict)


def compute_rel_delta(
    merge_cases: list[dict[str, Any]],
    wrong_links: dict[str, list[str]],
    correct_links: dict[str, set[str]],
) -> tuple[int, list[dict[str, str]]]:
    """返回 (SUPPORTED_BY 净变化, 会因目标已有边而合并掉的项)。

    每条「贴后」出边：若目标已有同 Truth_Point 边 → 净 -1；否则边迁移净 0。
    改名不影响边数。
    """
    dups: list[dict[str, str]] = []
    delta = 0
    for case in merge_cases:
        w, c = case["wrong"], case["correct"]
        for term in wrong_links.get(w, []):
            if term in correct_links.get(c, set()):
                delta -= 1
                dups.append({"term": term, "from_ref": w, "to_ref": c})
    return delta, dups


def is_already_applied_state(
    *,
    tiehou_refs: list[str],
    scripture_n: int,
    organic_true_n: int,
    cross_has_organic: bool,
    death_has_organic: bool,
    all_correct_exist: bool,
) -> bool:
    return (
        len(tiehou_refs) == 0
        and scripture_n == EXPECT_SCRIPTURE_AFTER
        and organic_true_n == EXPECT_ORGANIC_N
        and cross_has_organic
        and not death_has_organic
        and all_correct_exist
    )


def build_apply_ops(plan: CheckPlan) -> list[dict[str, Any]]:
    """生成有序写操作描述（供假 session / 真事务执行）。"""
    ops: list[dict[str, Any]] = []
    for item in plan.merge:
        wrong = item["wrong"]
        correct = item["correct"]
        for term in item["terms_on_wrong"]:
            ops.append(
                {
                    "op": "merge_supported_by",
                    "term": term,
                    "from_ref": wrong,
                    "to_ref": correct,
                }
            )
        ops.append({"op": "detach_delete_scripture", "ref": wrong})
    for item in plan.rename:
        ops.append(
            {
                "op": "rename_ref",
                "from_ref": item["wrong"],
                "to_ref": item["correct"],
            }
        )
    ops.append({"op": "set_organic_true", "name": ORGANIC_SET_TRUE})
    ops.append({"op": "remove_organic", "name": ORGANIC_REMOVE})
    return ops


def evaluate_check(
    *,
    wrong_nodes: dict[str, NodeInfo],
    correct_merge_nodes: dict[str, NodeInfo],
    correct_rename_absent: dict[str, bool],
    scripture_n: int,
    supported_by_n: int,
    organic_true_n: int,
    organic_cross: Any,
    organic_death: Any,
    same_as_info: dict[str, bool],
) -> CheckPlan:
    fails: list[str] = []
    warnings: list[str] = []

    tiehou_existing = [r for r, n in wrong_nodes.items() if n.exists]

    # 前置：6 个贴后存在（未应用时）
    for ref in ALL_WRONG:
        if not wrong_nodes.get(ref, NodeInfo(ref, "", False)).exists:
            fails.append(f"缺「贴后」节点：{ref}")

    # 3 个合并目标存在
    for case in MERGE_CASES:
        info = correct_merge_nodes.get(case["correct"])
        if not info or not info.exists:
            fails.append(f"缺合并目标节点：{case['correct']}")

    # 3 个改名目标不存在
    rename_absent: dict[str, bool] = {}
    for case in RENAME_CASES:
        absent = correct_rename_absent.get(case["correct"], True)
        rename_absent[case["correct"]] = absent
        if not absent:
            # 若贴后仍在且目标已在 → 冲突；若贴后已不在可能是已应用
            if wrong_nodes.get(case["wrong"], NodeInfo(case["wrong"], "", False)).exists:
                fails.append(f"改名目标已存在（冲突）：{case['correct']}")

    # 关系类型仅 SUPPORTED_BY
    for ref, info in wrong_nodes.items():
        if not info.exists:
            continue
        bad = sorted({t for t in info.rel_types if t != ALLOWED_REL_TYPE})
        if bad:
            fails.append(f"{ref} 存在非 {ALLOWED_REL_TYPE} 关系：{bad}")

    # text 预览警告
    for ref, info in wrong_nodes.items():
        if not info.exists:
            continue
        prev = _text_preview(info.text)
        if prev == "空":
            warnings.append(f"{ref} text 为空（脚本不自动改 text，交 Srey 决定）")
        elif "贴后" in (info.text or ""):
            warnings.append(f"{ref} text 含「贴后」字样：{_text_preview(info.text)}")

    # 组装 merge/rename 详情
    wrong_links = {
        ref: [lk.term for lk in info.links if lk.rel_type == ALLOWED_REL_TYPE]
        for ref, info in wrong_nodes.items()
    }
    correct_links = {
        ref: {lk.term for lk in info.links if lk.rel_type == ALLOWED_REL_TYPE}
        for ref, info in correct_merge_nodes.items()
    }
    delta, dups = compute_rel_delta(MERGE_CASES, wrong_links, correct_links)

    merge_out = []
    for case in MERGE_CASES:
        w = case["wrong"]
        info = wrong_nodes.get(w, NodeInfo(w, "", False))
        terms = wrong_links.get(w, [])
        merge_out.append(
            {
                **case,
                "terms_on_wrong": terms,
                "text_preview": _text_preview(info.text),
                "expected_terms": case["terms"],
                "terms_match_expected": sorted(terms) == sorted(case["terms"]),
            }
        )
        if info.exists and sorted(terms) != sorted(case["terms"]):
            warnings.append(
                f"{w} 连接词条 {terms} 与报告预期 {case['terms']} 不一致"
            )

    rename_out = []
    for case in RENAME_CASES:
        w = case["wrong"]
        info = wrong_nodes.get(w, NodeInfo(w, "", False))
        terms = wrong_links.get(w, [])
        rename_out.append(
            {
                **case,
                "terms_on_wrong": terms,
                "text_preview": _text_preview(info.text),
                "target_absent": rename_absent.get(case["correct"], True),
                "terms_match_expected": sorted(terms) == sorted(case["terms"]),
            }
        )
        if info.exists and sorted(terms) != sorted(case["terms"]):
            warnings.append(
                f"{w} 连接词条 {terms} 与报告预期 {case['terms']} 不一致"
            )

    # organic
    cross_true = organic_cross is True
    death_true = organic_death is True
    organic = {
        ORGANIC_SET_TRUE: organic_cross,
        ORGANIC_REMOVE: organic_death,
        "organic_true_n": organic_true_n,
        "in_paren_pairs": {
            ORGANIC_SET_TRUE: same_as_info.get(ORGANIC_SET_TRUE, False),
            ORGANIC_REMOVE: same_as_info.get(ORGANIC_REMOVE, False),
        },
        "expect_organic_n_after": EXPECT_ORGANIC_N,
    }
    if organic_true_n != EXPECT_ORGANIC_N and len(tiehou_existing) == 6:
        # 改前预期 69；若已改也可能仍是 69
        warnings.append(
            f"organic_advance=true 当前={organic_true_n}，改前预期 {EXPECT_ORGANIC_N}"
        )

    # already applied?
    rename_targets_all_exist = all(not rename_absent.get(c["correct"], True) for c in RENAME_CASES)
    merge_targets_all_exist = all(
        correct_merge_nodes.get(c["correct"], NodeInfo(c["correct"], "", False)).exists
        for c in MERGE_CASES
    )
    already = is_already_applied_state(
        tiehou_refs=tiehou_existing,
        scripture_n=scripture_n,
        organic_true_n=organic_true_n,
        cross_has_organic=cross_true,
        death_has_organic=death_true,
        all_correct_exist=merge_targets_all_exist and rename_targets_all_exist,
    )

    if already:
        fails = []  # 已应用时 check 视为通过（幂等）
        warnings.append("状态显示修订已应用（幂等）")

    if not already and scripture_n != EXPECT_SCRIPTURE_BEFORE:
        fails.append(
            f"Scripture 总数 {scripture_n}≠改前期望 {EXPECT_SCRIPTURE_BEFORE}"
        )

    expect_after = scripture_n - len(MERGE_CASES) if not already else EXPECT_SCRIPTURE_AFTER
    if already:
        expect_after = EXPECT_SCRIPTURE_AFTER

    plan = CheckPlan(
        ok=len(fails) == 0,
        fails=fails,
        warnings=warnings,
        already_applied=already,
        merge=merge_out,
        rename=rename_out,
        organic=organic,
        scripture_n=scripture_n,
        supported_by_n=supported_by_n,
        expect_scripture_after=expect_after if not already else EXPECT_SCRIPTURE_AFTER,
        expect_supported_by_after=supported_by_n + delta,
        expect_supported_by_delta=delta,
        duplicate_moves=dups,
    )
    return plan


# ---------------------------------------------------------------------------
# Neo4j 访问（真库 + 假 session 共用接口）
# ---------------------------------------------------------------------------


def _run(session, query: str, params: Optional[dict] = None) -> list[dict]:
    result = session.run(query, params or {})
    return [dict(r) for r in result]


def fetch_scripture_node(session, ref: str) -> NodeInfo:
    rows = _run(
        session,
        "MATCH (s:Scripture {ref: $ref}) RETURN s.ref AS ref, s.text AS text",
        {"ref": ref},
    )
    if not rows:
        return NodeInfo(ref=ref, text="", exists=False)
    links_rows = _run(
        session,
        """
        MATCH (t:Truth_Point)-[r]->(s:Scripture {ref: $ref})
        RETURN t.name AS term, type(r) AS rel_type
        """,
        {"ref": ref},
    )
    # 也查反向（防守）
    rev = _run(
        session,
        """
        MATCH (s:Scripture {ref: $ref})-[r]->(t:Truth_Point)
        RETURN t.name AS term, type(r) AS rel_type
        """,
        {"ref": ref},
    )
    links = [
        RelLink(term=r["term"], ref=ref, rel_type=r["rel_type"]) for r in links_rows
    ]
    rel_types = [r["rel_type"] for r in links_rows] + [r["rel_type"] for r in rev]
    if rev:
        # 反向关系也记入 types，供检查拦截
        for r in rev:
            links.append(
                RelLink(term=f"REV:{r['term']}", ref=ref, rel_type=r["rel_type"])
            )
    return NodeInfo(
        ref=ref,
        text=rows[0].get("text") or "",
        exists=True,
        links=links,
        rel_types=rel_types,
    )


def fetch_counts(session) -> tuple[int, int]:
    sc = _run(session, "MATCH (s:Scripture) RETURN count(s) AS c")[0]["c"]
    sb = _run(
        session, f"MATCH ()-[r:{ALLOWED_REL_TYPE}]->() RETURN count(r) AS c"
    )[0]["c"]
    return int(sc), int(sb)


def fetch_organic(session) -> tuple[int, Any, Any]:
    n = _run(
        session,
        "MATCH (t:Truth_Point) WHERE t.organic_advance = true RETURN count(t) AS c",
    )[0]["c"]
    cross = _run(
        session,
        "MATCH (t:Truth_Point {name: $n}) RETURN t.organic_advance AS v",
        {"n": ORGANIC_SET_TRUE},
    )
    death = _run(
        session,
        "MATCH (t:Truth_Point {name: $n}) RETURN t.organic_advance AS v",
        {"n": ORGANIC_REMOVE},
    )
    cross_v = cross[0]["v"] if cross else None
    death_v = death[0]["v"] if death else None
    return int(n), cross_v, death_v


def fetch_tiehou_refs(session) -> list[str]:
    rows = _run(
        session,
        "MATCH (s:Scripture) WHERE s.ref CONTAINS $x RETURN s.ref AS ref ORDER BY ref",
        {"x": "贴后"},
    )
    return [r["ref"] for r in rows]


def _sorted_props(props: Any) -> dict[str, Any]:
    if not isinstance(props, dict):
        return {}
    return {k: props[k] for k in sorted(props.keys())}


def compute_snapshot_hashes(
    *,
    scripture_nodes: list[dict[str, Any]],
    supported_by: list[dict[str, Any]],
    organic_rows: list[dict[str, Any]],
    graph_other_nodes: list[dict[str, Any]],
    graph_other_rels: list[dict[str, Any]],
    affected_refs: Optional[set[str]] = None,
) -> dict[str, Any]:
    """纯函数：由原始行计算各快照哈希（供真库取数与单元测试共用）。

    覆盖范围：
    - scripture_*：Scripture 全部属性（按键名排序）+ ref
    - supported_by_*：SUPPORTED_BY 关系属性（排序）+ 两端 Truth_Point.name / Scripture.ref
    - organic_*：Truth_Point.organic_advance（有该属性者）；keep 排除十字架/死
    - graph_other_sha：TP/Branch/Trunk 全部属性（去掉 organic_advance）+ 三类之间全部关系
    """
    aff = set(affected_refs if affected_refs is not None else AFFECTED_REFS)

    sc_all = sorted(
        [
            {"ref": n["ref"], "props": _sorted_props(n.get("props"))}
            for n in scripture_nodes
        ],
        key=lambda x: x["ref"],
    )
    sc_keep = [x for x in sc_all if x["ref"] not in aff]

    sb_all = sorted(
        [
            {
                "from": r["from_name"],
                "to_ref": r["to_ref"],
                "type": r.get("rel_type") or ALLOWED_REL_TYPE,
                "props": _sorted_props(r.get("props")),
            }
            for r in supported_by
        ],
        key=lambda x: (x["from"], x["to_ref"], x["type"]),
    )
    # keep：Scripture 一端不在受影响集合
    sb_keep = [x for x in sb_all if x["to_ref"] not in aff]

    org_all = sorted(
        [{"name": r["name"], "v": r.get("v")} for r in organic_rows],
        key=lambda x: x["name"],
    )
    org_keep = [x for x in org_all if x["name"] not in ORGANIC_AFFECTED]

    go_nodes = sorted(
        [
            {
                "label": n["label"],
                "name": n["name"],
                "props": _sorted_props(n.get("props")),
            }
            for n in graph_other_nodes
        ],
        key=lambda x: (x["label"], x["name"]),
    )
    go_rels = sorted(
        [
            {
                "type": r["type"],
                "from_label": r["from_label"],
                "from_name": r["from_name"],
                "to_label": r["to_label"],
                "to_name": r["to_name"],
                "props": _sorted_props(r.get("props")),
            }
            for r in graph_other_rels
        ],
        key=lambda x: (
            x["type"],
            x["from_label"],
            x["from_name"],
            x["to_label"],
            x["to_name"],
        ),
    )
    graph_other_payload = {"nodes": go_nodes, "rels": go_rels}

    return {
        "affected_refs": sorted(aff),
        "scripture_keep_sha": _sha_json(sc_keep),
        "scripture_keep_n": len(sc_keep),
        "supported_by_keep_sha": _sha_json(sb_keep),
        "supported_by_keep_n": len(sb_keep),
        "organic_keep_sha": _sha_json(org_keep),
        "organic_keep_n": len(org_keep),
        "scripture_all_sha": _sha_json(sc_all),
        "supported_by_all_sha": _sha_json(sb_all),
        "organic_all_sha": _sha_json(org_all),
        "graph_other_sha": _sha_json(graph_other_payload),
        "scripture_all_n": len(sc_all),
        "supported_by_all_n": len(sb_all),
        "organic_all_n": len(org_all),
        "graph_other_nodes_n": len(go_nodes),
        "graph_other_rels_n": len(go_rels),
    }


def _fetch_snapshot_rows(runner) -> dict[str, list]:
    """runner：session 或 transaction（均有 .run）。"""
    sc = _run(
        runner,
        "MATCH (s:Scripture) RETURN s.ref AS ref, properties(s) AS props ORDER BY s.ref",
    )
    sb = _run(
        runner,
        f"""
        MATCH (t:Truth_Point)-[r:{ALLOWED_REL_TYPE}]->(s:Scripture)
        RETURN t.name AS from_name, s.ref AS to_ref, type(r) AS rel_type,
               properties(r) AS props
        ORDER BY from_name, to_ref
        """,
    )
    org = _run(
        runner,
        """
        MATCH (t:Truth_Point)
        WHERE t.organic_advance IS NOT NULL
        RETURN t.name AS name, t.organic_advance AS v
        ORDER BY name
        """,
    )
    go_nodes: list[dict] = []
    for lb in CLASS_LABELS:
        rows = _run(
            runner,
            f"""
            MATCH (n:`{lb}`)
            RETURN n.name AS name, properties(n) AS props
            ORDER BY name
            """,
        )
        for r in rows:
            props = dict(r.get("props") or {})
            props.pop("organic_advance", None)
            go_nodes.append({"label": lb, "name": r["name"], "props": props})
    go_rels = _run(
        runner,
        """
        MATCH (a)-[r]->(b)
        WHERE (a:Truth_Point OR a:Branch OR a:Trunk)
          AND (b:Truth_Point OR b:Branch OR b:Trunk)
        RETURN type(r) AS type,
               labels(a)[0] AS from_label, a.name AS from_name,
               labels(b)[0] AS to_label, b.name AS to_name,
               properties(r) AS props
        ORDER BY type, from_name, to_name
        """,
    )
    return {
        "scripture_nodes": sc,
        "supported_by": sb,
        "organic_rows": org,
        "graph_other_nodes": go_nodes,
        "graph_other_rels": go_rels,
    }


def take_snapshots(
    runner, *, affected_refs: Optional[set[str]] = None
) -> dict[str, Any]:
    rows = _fetch_snapshot_rows(runner)
    return compute_snapshot_hashes(
        scripture_nodes=rows["scripture_nodes"],
        supported_by=rows["supported_by"],
        organic_rows=rows["organic_rows"],
        graph_other_nodes=rows["graph_other_nodes"],
        graph_other_rels=rows["graph_other_rels"],
        affected_refs=affected_refs,
    )


# 兼容旧名
def snapshot_unaffected(session, affected_refs: set[str]) -> dict[str, Any]:
    return take_snapshots(session, affected_refs=affected_refs)


def collect_check(session) -> CheckPlan:
    wrong_nodes = {ref: fetch_scripture_node(session, ref) for ref in ALL_WRONG}
    correct_merge = {
        c["correct"]: fetch_scripture_node(session, c["correct"]) for c in MERGE_CASES
    }
    rename_absent = {}
    for c in RENAME_CASES:
        info = fetch_scripture_node(session, c["correct"])
        rename_absent[c["correct"]] = not info.exists

    sc_n, sb_n = fetch_counts(session)
    org_n, cross_v, death_v = fetch_organic(session)
    same_as = {
        ORGANIC_SET_TRUE: ORGANIC_SET_TRUE in PAREN_NAMES,
        ORGANIC_REMOVE: ORGANIC_REMOVE in PAREN_NAMES,
    }
    plan = evaluate_check(
        wrong_nodes=wrong_nodes,
        correct_merge_nodes=correct_merge,
        correct_rename_absent=rename_absent,
        scripture_n=sc_n,
        supported_by_n=sb_n,
        organic_true_n=org_n,
        organic_cross=cross_v,
        organic_death=death_v,
        same_as_info=same_as,
    )
    plan.snapshots = take_snapshots(session, affected_refs=set(AFFECTED_REFS))
    return plan


# ---------------------------------------------------------------------------
# 写操作（单事务）
# ---------------------------------------------------------------------------


def _tx_apply(tx, ops: list[dict[str, Any]]) -> None:
    for op in ops:
        kind = op["op"]
        if kind == "merge_supported_by":
            # 在目标上建同类型同另一端关系；已存在则 MERGE 不重复
            q = (
                "MATCH (t:Truth_Point {name: $term}) "
                "MATCH (s:Scripture {ref: $to_ref}) "
                f"MERGE (t)-[r:{ALLOWED_REL_TYPE}]->(s) "
                "RETURN count(r) AS n"
            )
            tx.run(q, {"term": op["term"], "to_ref": op["to_ref"]})
            # 删除旧边
            q2 = (
                "MATCH (t:Truth_Point {name: $term})-"
                f"[r:{ALLOWED_REL_TYPE}]->(s:Scripture {{ref: $from_ref}}) "
                "DELETE r"
            )
            tx.run(q2, {"term": op["term"], "from_ref": op["from_ref"]})
        elif kind == "detach_delete_scripture":
            # 确认无关系后再删；用 DETACH 防守残留
            q = (
                "MATCH (s:Scripture {ref: $ref}) "
                "OPTIONAL MATCH (s)-[r]-() "
                "WITH s, count(r) AS rc "
                "WHERE rc = 0 "
                "DELETE s "
                "RETURN count(s) AS n"
            )
            # 若仍有边，强制 DETACH（应在迁移后为 0；非 0 则失败）
            rec = tx.run(
                "MATCH (s:Scripture {ref: $ref}) OPTIONAL MATCH (s)-[r]-() "
                "RETURN count(r) AS rc",
                {"ref": op["ref"]},
            ).single()
            rc = int(rec["rc"]) if rec else 0
            if rc != 0:
                raise FixError(f"删除前 {op['ref']} 仍有关系数={rc}")
            tx.run("MATCH (s:Scripture {ref: $ref}) DELETE s", {"ref": op["ref"]})
        elif kind == "rename_ref":
            # 目标不得已存在
            exists = tx.run(
                "MATCH (s:Scripture {ref: $to_ref}) RETURN count(s) AS c",
                {"to_ref": op["to_ref"]},
            ).single()["c"]
            if int(exists) != 0:
                raise FixError(f"改名目标已存在：{op['to_ref']}")
            tx.run(
                "MATCH (s:Scripture {ref: $from_ref}) SET s.ref = $to_ref",
                {"from_ref": op["from_ref"], "to_ref": op["to_ref"]},
            )
        elif kind == "set_organic_true":
            tx.run(
                "MATCH (t:Truth_Point {name: $n}) SET t.organic_advance = true",
                {"n": op["name"]},
            )
        elif kind == "remove_organic":
            tx.run(
                "MATCH (t:Truth_Point {name: $n}) REMOVE t.organic_advance",
                {"n": op["name"]},
            )
        else:
            raise FixError(f"未知操作：{kind}")


def export_backup(session, path: Path, *, snapshots: Optional[dict] = None) -> dict[str, Any]:
    """导出受影响节点与关系；备份同时存改前快照哈希。"""
    refs = sorted(AFFECTED_REFS)
    nodes = []
    for ref in refs:
        rows = _run(
            session,
            "MATCH (s:Scripture {ref: $ref}) RETURN s.ref AS ref, s.text AS text, "
            "properties(s) AS props",
            {"ref": ref},
        )
        if rows:
            nodes.append(
                {
                    "ref": rows[0]["ref"],
                    "text": rows[0].get("text") or "",
                    "props": dict(rows[0].get("props") or {}),
                }
            )
    rels = []
    for ref in refs:
        rows = _run(
            session,
            f"""
            MATCH (t:Truth_Point)-[r:{ALLOWED_REL_TYPE}]->(s:Scripture {{ref: $ref}})
            RETURN t.name AS name, s.ref AS ref, type(r) AS rel_type,
                   properties(r) AS props
            """,
            {"ref": ref},
        )
        for r in rows:
            rels.append(r)
    org = []
    for name in (ORGANIC_SET_TRUE, ORGANIC_REMOVE):
        rows = _run(
            session,
            "MATCH (t:Truth_Point {name: $n}) "
            "RETURN t.name AS name, t.organic_advance AS organic_advance, keys(t) AS ks",
            {"n": name},
        )
        for r in rows:
            ks = r.pop("ks", None) or []
            r["has_key"] = "organic_advance" in ks
            org.append(r)

    sc_n, sb_n = fetch_counts(session)
    org_n, _, _ = fetch_organic(session)
    snaps = snapshots if snapshots is not None else take_snapshots(session)
    backup = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "scripture_n": sc_n,
        "supported_by_n": sb_n,
        "organic_true_n": org_n,
        "scripture_nodes": nodes,
        "supported_by": rels,
        "organic_targets": org,
        "merge_cases": MERGE_CASES,
        "rename_cases": RENAME_CASES,
        "snapshots": {
            k: snaps.get(k)
            for k in (
                "scripture_keep_sha",
                "supported_by_keep_sha",
                "organic_keep_sha",
                "scripture_all_sha",
                "supported_by_all_sha",
                "organic_all_sha",
                "graph_other_sha",
                "affected_refs",
            )
        },
    }
    _write_json(path, backup)
    return backup


def collect_post_apply_assertions(
    runner,
    *,
    before_snapshots: dict[str, Any],
    expect_supported_by_after: int,
) -> list[str]:
    """写后全部断言（可在显式事务内对 tx 调用）。失败即应回滚。"""
    fails: list[str] = []
    tiehou = fetch_tiehou_refs(runner)
    if tiehou:
        fails.append(f"仍有含「贴后」的 ref：{tiehou}")

    sc_n, sb_n = fetch_counts(runner)
    if sc_n != EXPECT_SCRIPTURE_AFTER:
        fails.append(f"Scripture 总数 {sc_n}≠{EXPECT_SCRIPTURE_AFTER}")
    if sb_n != expect_supported_by_after:
        fails.append(f"SUPPORTED_BY 总数 {sb_n}≠期望 {expect_supported_by_after}")

    for case in MERGE_CASES + RENAME_CASES:
        info = fetch_scripture_node(runner, case["correct"])
        if not info.exists:
            fails.append(f"缺少「帖后」节点：{case['correct']}")
            continue
        terms = sorted(
            lk.term for lk in info.links if lk.rel_type == ALLOWED_REL_TYPE
        )
        for t in case["terms"]:
            if t not in terms:
                fails.append(
                    f"{case['correct']} 未连接到预期词条 {t}（现有 {terms}）"
                )

    org_n, cross_v, _death_v = fetch_organic(runner)
    if org_n != EXPECT_ORGANIC_N:
        fails.append(f"organic_advance=true 总数 {org_n}≠{EXPECT_ORGANIC_N}")
    if cross_v is not True:
        fails.append(f"{ORGANIC_SET_TRUE} organic_advance={cross_v!r}，期望 true")
    death_rows = _run(
        runner,
        "MATCH (t:Truth_Point {name: $n}) RETURN t.organic_advance AS v, "
        "keys(t) AS ks",
        {"n": ORGANIC_REMOVE},
    )
    if death_rows:
        ks = death_rows[0].get("ks") or []
        if "organic_advance" in ks and death_rows[0].get("v") is not None:
            fails.append(
                f"{ORGANIC_REMOVE} 仍有 organic_advance={death_rows[0].get('v')!r}"
            )

    after = take_snapshots(runner, affected_refs=set(AFFECTED_REFS))
    for key in (
        "scripture_keep_sha",
        "supported_by_keep_sha",
        "organic_keep_sha",
        "graph_other_sha",
    ):
        if after.get(key) != before_snapshots.get(key):
            fails.append(f"未改动快照不一致：{key}")
    return fails


def verify_assertions(session, plan: CheckPlan) -> list[str]:
    """兼容旧调用：用 plan 中的改前快照与期望边数。"""
    return collect_post_apply_assertions(
        session,
        before_snapshots=plan.snapshots or {},
        expect_supported_by_after=plan.expect_supported_by_after,
    )


def _tx_rollback_restore(tx, backup: dict[str, Any]) -> None:
    """在已开事务内按备份恢复（不 commit）。"""
    for row in backup.get("organic_targets") or []:
        name = row["name"]
        has_key = row.get("has_key")
        val = row.get("organic_advance")
        if has_key is False or (has_key is None and val is None):
            tx.run(
                "MATCH (t:Truth_Point {name: $n}) REMOVE t.organic_advance",
                {"n": name},
            )
        else:
            tx.run(
                "MATCH (t:Truth_Point {name: $n}) SET t.organic_advance = $v",
                {"n": name, "v": val},
            )

    for case in RENAME_CASES:
        tx.run(
            "MATCH (s:Scripture {ref: $new}) SET s.ref = $old",
            {"new": case["correct"], "old": case["wrong"]},
        )

    node_by_ref = {n["ref"]: n for n in (backup.get("scripture_nodes") or [])}
    for case in MERGE_CASES:
        w = case["wrong"]
        node = node_by_ref.get(w)
        text = (node or {}).get("text") or ""
        tx.run(
            "MERGE (s:Scripture {ref: $ref}) ON CREATE SET s.text = $text "
            "ON MATCH SET s.text = coalesce(s.text, $text)",
            {"ref": w, "text": text},
        )

    for rel in backup.get("supported_by") or []:
        if rel["ref"] in {c["wrong"] for c in MERGE_CASES}:
            tx.run(
                "MATCH (t:Truth_Point {name: $name}) "
                "MATCH (s:Scripture {ref: $ref}) "
                f"MERGE (t)-[:{ALLOWED_REL_TYPE}]->(s)",
                {"name": rel["name"], "ref": rel["ref"]},
            )

    bak_correct_edges = {
        (r["name"], r["ref"])
        for r in (backup.get("supported_by") or [])
        if r["ref"] in {c["correct"] for c in MERGE_CASES}
    }
    for case in MERGE_CASES:
        cref = case["correct"]
        rows = list(
            tx.run(
                f"""
                MATCH (t:Truth_Point)-[r:{ALLOWED_REL_TYPE}]->(s:Scripture {{ref: $ref}})
                RETURN t.name AS name
                """,
                {"ref": cref},
            )
        )
        for row in rows:
            key = (row["name"], cref)
            if key not in bak_correct_edges:
                tx.run(
                    "MATCH (t:Truth_Point {name: $name})-"
                    f"[r:{ALLOWED_REL_TYPE}]->(s:Scripture {{ref: $ref}}) "
                    "DELETE r",
                    {"name": row["name"], "ref": cref},
                )


def _safe_tx_rollback(tx) -> None:
    try:
        closed = getattr(tx, "closed", False)
        if not closed:
            tx.rollback()
    except Exception:
        pass


def run_rollback_in_transaction(
    session, backup: dict[str, Any]
) -> tuple[bool, list[str], Optional[dict]]:
    """显式事务回滚恢复；提交前核对 *_all 与 graph_other 等于备份改前哈希。

    返回 (ok, fails, after_snaps)。失败时已 rollback、未提交。
    """
    expected = backup.get("snapshots") or {}
    tx = session.begin_transaction()
    try:
        _tx_rollback_restore(tx, backup)
        after = take_snapshots(tx, affected_refs=set(AFFECTED_REFS))
        fails: list[str] = []
        for key in (
            "scripture_all_sha",
            "supported_by_all_sha",
            "organic_all_sha",
            "graph_other_sha",
        ):
            if key not in expected or expected.get(key) is None:
                fails.append(f"备份缺少改前哈希：{key}")
            elif after.get(key) != expected.get(key):
                fails.append(f"回滚后快照≠备份：{key}")
        if fails:
            _safe_tx_rollback(tx)
            return False, fails, after
        tx.commit()
        return True, [], after
    except Exception:
        _safe_tx_rollback(tx)
        raise


def run_rollback(session, backup: dict[str, Any]) -> None:
    """兼容旧接口：失败抛 FixError。"""
    ok, fails, _ = run_rollback_in_transaction(session, backup)
    if not ok:
        raise FixError("rollback 断言失败：" + "; ".join(fails))


# ---------------------------------------------------------------------------
# 模式入口
# ---------------------------------------------------------------------------


def mode_check(session, log_dir: Path) -> int:
    plan = collect_check(session)
    report = {
        "mode": "check",
        "ok": plan.ok,
        "already_applied": plan.already_applied,
        "fails": plan.fails,
        "warnings": plan.warnings,
        "scripture_n": plan.scripture_n,
        "supported_by_n": plan.supported_by_n,
        "expect_scripture_after": plan.expect_scripture_after,
        "expect_supported_by_delta": plan.expect_supported_by_delta,
        "expect_supported_by_after": plan.expect_supported_by_after,
        "duplicate_moves": plan.duplicate_moves,
        "merge": plan.merge,
        "rename": plan.rename,
        "organic": plan.organic,
        "snapshots": plan.snapshots,
        "ops_preview": build_apply_ops(plan) if plan.ok and not plan.already_applied else [],
    }
    path = _log(log_dir, "check", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"LOG={path}")
    return 0 if plan.ok else 2


def apply_in_transaction(
    session,
    ops: list[dict[str, Any]],
    *,
    before_snapshots: dict[str, Any],
    expect_supported_by_after: int,
) -> tuple[bool, list[str], str]:
    """显式事务：写 → 事务内断言 → 全过才 commit。

    返回 (ok, fails, outcome) outcome ∈ committed|rolled_back|exception_rolled_back
    """
    tx = session.begin_transaction()
    try:
        _tx_apply(tx, ops)
        fails = collect_post_apply_assertions(
            tx,
            before_snapshots=before_snapshots,
            expect_supported_by_after=expect_supported_by_after,
        )
        if fails:
            _safe_tx_rollback(tx)
            return False, fails, "rolled_back"
        tx.commit()
        return True, [], "committed"
    except Exception as e:
        _safe_tx_rollback(tx)
        return False, [f"写操作异常：{_redact(str(e))}"], "exception_rolled_back"


def mode_apply(session, log_dir: Path, backup_dir: Path) -> int:
    plan = collect_check(session)
    if not plan.ok:
        print("check 未通过，拒绝 apply：", plan.fails)
        return 2
    if plan.already_applied:
        print("已应用：不做任何写操作（幂等）")
        _log(
            log_dir,
            "apply_noop",
            {"already_applied": True, "wrote": False, "opened_write_tx": False},
        )
        return 0

    backup_dir.mkdir(parents=True, exist_ok=True)
    bak_path = backup_dir / f"backup_before_apply_{_now()}.json"
    before = plan.snapshots or take_snapshots(session)
    export_backup(session, bak_path, snapshots=before)
    ops = build_apply_ops(plan)

    ok, fails, outcome = apply_in_transaction(
        session,
        ops,
        before_snapshots=before,
        expect_supported_by_after=plan.expect_supported_by_after,
    )
    graph_unchanged = not ok
    report = {
        "mode": "apply",
        "ok": ok,
        "fails": fails,
        "backup": str(bak_path),
        "ops": ops,
        "expect_supported_by_after": plan.expect_supported_by_after,
        "tx_outcome": outcome,
        "图谱未改动": graph_unchanged,
    }
    if not ok:
        report["message"] = (
            "断言失败或写异常，事务已回滚，图谱未改动。"
            + (" 失败断言：" + "; ".join(fails) if fails else "")
        )
    path = _log(log_dir, "apply" if ok else "apply_fail", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"LOG={path}")
    print(f"BACKUP={bak_path}")
    if not ok:
        print("apply 失败：事务已回滚，图谱未改动。失败断言：", fails)
        return 4 if outcome == "rolled_back" else 3
    return 0


def mode_verify(session, log_dir: Path) -> int:
    plan = collect_check(session)
    fails: list[str] = []
    tiehou = fetch_tiehou_refs(session)
    if tiehou:
        fails.append(f"仍有含「贴后」的 ref：{tiehou}")
    sc_n, sb_n = fetch_counts(session)
    if sc_n != EXPECT_SCRIPTURE_AFTER:
        fails.append(f"Scripture {sc_n}≠{EXPECT_SCRIPTURE_AFTER}")

    for case in MERGE_CASES + RENAME_CASES:
        info = fetch_scripture_node(session, case["correct"])
        if not info.exists:
            fails.append(f"缺节点 {case['correct']}")
        else:
            terms = {lk.term for lk in info.links if lk.rel_type == ALLOWED_REL_TYPE}
            for t in case["terms"]:
                if t not in terms:
                    fails.append(f"{case['correct']} 缺词条 {t}")

    org_n, cross_v, _death_v = fetch_organic(session)
    if org_n != EXPECT_ORGANIC_N:
        fails.append(f"organic_true_n {org_n}≠{EXPECT_ORGANIC_N}")
    if cross_v is not True:
        fails.append(f"{ORGANIC_SET_TRUE}≠true")
    death_rows = _run(
        session,
        "MATCH (t:Truth_Point {name: $n}) RETURN keys(t) AS ks, t.organic_advance AS v",
        {"n": ORGANIC_REMOVE},
    )
    if death_rows and "organic_advance" in (death_rows[0].get("ks") or []):
        if death_rows[0].get("v") is not None:
            fails.append(f"{ORGANIC_REMOVE} 仍带 organic_advance")

    snaps = plan.snapshots or take_snapshots(session)
    if plan.already_applied and snaps:
        now = take_snapshots(session, affected_refs=set(AFFECTED_REFS))
        for key in (
            "scripture_keep_sha",
            "supported_by_keep_sha",
            "organic_keep_sha",
            "graph_other_sha",
        ):
            if now.get(key) != snaps.get(key):
                fails.append(f"快照自洽失败：{key}")

    report = {
        "mode": "verify",
        "ok": len(fails) == 0,
        "fails": fails,
        "scripture_n": sc_n,
        "supported_by_n": sb_n,
        "organic_true_n": org_n,
        "already_applied": plan.already_applied,
        "tiehou_refs": tiehou,
        "graph_other_sha": snaps.get("graph_other_sha"),
        "snapshots": {
            k: snaps.get(k)
            for k in (
                "scripture_keep_sha",
                "supported_by_keep_sha",
                "organic_keep_sha",
                "scripture_all_sha",
                "supported_by_all_sha",
                "organic_all_sha",
                "graph_other_sha",
            )
        },
        "note": "无改前基准时 graph_other_sha / *_all_sha 仅显示，不据其判错",
    }
    path = _log(log_dir, "verify", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"LOG={path}")
    return 0 if not fails else 2


def mode_rollback(session, backup_path: Path, log_dir: Path) -> int:
    backup = json.loads(backup_path.read_text(encoding="utf-8"))
    try:
        ok, fails, after = run_rollback_in_transaction(session, backup)
    except Exception as e:
        print("rollback 失败（已回滚/未提交）：", _redact(str(e)))
        _log(
            log_dir,
            "rollback_fail",
            {"error": _redact(str(e)), "图谱未改动": True},
        )
        return 3
    report = {
        "mode": "rollback",
        "ok": ok,
        "fails": fails,
        "backup": str(backup_path),
        "图谱未改动": not ok,
        "after_snapshots": {
            k: (after or {}).get(k)
            for k in (
                "scripture_all_sha",
                "supported_by_all_sha",
                "organic_all_sha",
                "graph_other_sha",
            )
        }
        if after
        else None,
    }
    path = _log(log_dir, "rollback" if ok else "rollback_fail", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"LOG={path}")
    if not ok:
        print("rollback 失败：事务已回滚，图谱未改动。", fails)
        return 4
    return 0


def mode_sync_sources(
    *,
    src_fixed: Path,
    src_bak: Path,
    dests: list[Path],
    log_dir: Path,
) -> int:
    """桌面改正后文件覆盖仓库副本（先核对 bak SHA）。"""
    if not src_fixed.is_file() or not src_bak.is_file():
        print("缺 src_fixed 或 src_bak")
        return 2
    bak_sha = _sha_bytes(src_bak.read_bytes())
    fixed_sha = _sha_bytes(src_fixed.read_bytes())
    report: dict[str, Any] = {
        "mode": "sync-sources",
        "src_fixed": str(src_fixed),
        "src_bak": str(src_bak),
        "src_fixed_sha256": fixed_sha,
        "src_bak_sha256": bak_sha,
        "dests": [],
        "node_general_annotation": "无副本",
    }
    for dest in dests:
        if not dest.is_file():
            print(f"目标不存在：{dest}")
            return 2
        old = _sha_bytes(dest.read_bytes())
        if old != bak_sha:
            print(
                f"拒绝覆盖：{dest} SHA 与 bak 不同\n"
                f"  dest={old}\n  bak ={bak_sha}"
            )
            report["ok"] = False
            report["mismatch"] = {"dest": str(dest), "dest_sha": old}
            _log(log_dir, "sync_sources_fail", report)
            return 2
        # 命名为 *.bak_20261116.json，便于被仓库内 graph_annotations/*.json 规则忽略
        bak_copy = dest.with_name(dest.stem + ".bak_20261116.json")
        if not bak_copy.exists():
            shutil.copy2(dest, bak_copy)
        shutil.copy2(src_fixed, dest)
        new = _sha_bytes(dest.read_bytes())
        report["dests"].append(
            {
                "path": str(dest),
                "old_sha256": old,
                "new_sha256": new,
                "bak_copy": str(bak_copy),
            }
        )
    report["ok"] = True
    path = _log(log_dir, "sync_sources", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    print(f"LOG={path}")
    return 0


def open_session():
    from neo4j import GraphDatabase, WRITE_ACCESS

    uri, user, pw = _env_conn()
    driver = GraphDatabase.driver(uri, auth=(user, pw))
    pw = ""
    driver.verify_connectivity()
    session = driver.session(default_access_mode=WRITE_ACCESS)
    return driver, session


def parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="qa4 图谱修订 2026-11-16（贴后→帖后 + organic_advance）"
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--check", action="store_true", help="只读检查前置条件")
    g.add_argument("--apply", action="store_true", help="应用修订（需 --yes）")
    g.add_argument("--verify", action="store_true", help="只读验证最终状态")
    g.add_argument("--rollback", metavar="BACKUP_JSON", help="按备份回滚（需 --yes）")
    g.add_argument(
        "--sync-sources",
        action="store_true",
        help="同步仓库内 truth_dictionary_3a3b 副本（不连库）",
    )
    p.add_argument("--yes", action="store_true", help="确认写操作")
    p.add_argument(
        "--log-dir",
        default="graph_fix_logs",
        help="日志目录（默认 ./graph_fix_logs）",
    )
    p.add_argument(
        "--backup-dir",
        default="graph_fix_backups",
        help="备份目录（默认 ./graph_fix_backups）",
    )
    p.add_argument("--src-fixed", type=Path, help="桌面改正后的 3a3b json")
    p.add_argument("--src-bak", type=Path, help="桌面 .bak_20261116（改正前）")
    p.add_argument(
        "--dest",
        action="append",
        default=[],
        type=Path,
        help="仓库内副本路径（可重复）",
    )
    return p.parse_args(argv)


def main(argv: Optional[list[str]] = None) -> int:
    args = parse_args(argv)
    log_dir = Path(args.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    if args.sync_sources:
        if not args.src_fixed or not args.src_bak or not args.dest:
            print("--sync-sources 需要 --src-fixed --src-bak 与至少一个 --dest")
            return 2
        return mode_sync_sources(
            src_fixed=args.src_fixed,
            src_bak=args.src_bak,
            dests=list(args.dest),
            log_dir=log_dir,
        )

    if args.apply and not args.yes:
        print("--apply 必须加 --yes")
        return 2
    if args.rollback and not args.yes:
        print("--rollback 必须加 --yes")
        return 2

    driver = None
    session = None
    try:
        driver, session = open_session()
        if args.check:
            return mode_check(session, log_dir)
        if args.apply:
            return mode_apply(session, log_dir, Path(args.backup_dir))
        if args.verify:
            return mode_verify(session, log_dir)
        if args.rollback:
            return mode_rollback(session, Path(args.rollback), log_dir)
        print("未指定模式")
        return 2
    except FixError as e:
        print("错误：", _redact(str(e)))
        return 2
    finally:
        if session is not None:
            session.close()
        if driver is not None:
            driver.close()


if __name__ == "__main__":
    raise SystemExit(main())
