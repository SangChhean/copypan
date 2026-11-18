# -*- coding: utf-8 -*-
"""不连库：假 session / 内存假图测快照、事务、幂等、回滚。"""
from __future__ import annotations

import unittest
from typing import Any, Optional

from fix_graph_20261116 import (
    AFFECTED_REFS,
    ALLOWED_REL_TYPE,
    EXPECT_ORGANIC_N,
    EXPECT_SCRIPTURE_AFTER,
    EXPECT_SCRIPTURE_BEFORE,
    MERGE_CASES,
    ORGANIC_REMOVE,
    ORGANIC_SET_TRUE,
    RENAME_CASES,
    NodeInfo,
    RelLink,
    apply_in_transaction,
    build_apply_ops,
    compute_rel_delta,
    compute_snapshot_hashes,
    evaluate_check,
    is_already_applied_state,
    mode_apply,
    run_rollback_in_transaction,
    _tx_apply,
)


class FakeResult:
    def __init__(self, rows: list[dict]):
        self._rows = rows

    def single(self) -> Optional[dict]:
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class FakeTx:
    def __init__(self, graph: Optional["FakeGraph"] = None):
        self.queries: list[tuple[str, dict]] = []
        self._scripture: dict[str, dict] = {}
        self._edges: set[tuple[str, str]] = set()
        self._organic: dict[str, Any] = {}
        self._graph = graph
        self.closed = False
        self.committed = False
        self.rolled_back = False
        if graph is not None:
            self._sync_from_graph()

    def _sync_from_graph(self) -> None:
        assert self._graph is not None
        self._scripture = {k: dict(v) for k, v in self._graph.scripture.items()}
        self._edges = set(self._graph.edges)
        self._organic = dict(self._graph.organic)
        self._tp = {k: dict(v) for k, v in self._graph.truth_points.items()}
        self._class_rels = list(self._graph.class_rels)

    def seed(
        self,
        scripture: dict[str, dict],
        edges: set[tuple[str, str]],
        organic: dict[str, Any],
    ) -> None:
        self._scripture = dict(scripture)
        self._edges = set(edges)
        self._organic = dict(organic)

    def run(self, query: str, params: Optional[dict] = None) -> FakeResult:
        params = params or {}
        self.queries.append((query, dict(params)))
        q = " ".join(query.split())

        if q.startswith(
            "MATCH (t:Truth_Point {name: $term}) MATCH (s:Scripture {ref: $to_ref}) MERGE"
        ):
            self._edges.add((params["term"], params["to_ref"]))
            return FakeResult([{"n": 1}])

        if "DELETE r" in q and "$from_ref" in q:
            self._edges.discard((params["term"], params["from_ref"]))
            return FakeResult([])

        if q.startswith(
            "MATCH (s:Scripture {ref: $ref}) OPTIONAL MATCH (s)-[r]-() RETURN count(r) AS rc"
        ):
            rc = sum(1 for _t, ref in self._edges if ref == params["ref"])
            return FakeResult([{"rc": rc}])

        if q == "MATCH (s:Scripture {ref: $ref}) DELETE s":
            self._scripture.pop(params["ref"], None)
            return FakeResult([])

        if "SET s.ref = $to_ref" in q and "$from_ref" in q:
            old = params["from_ref"]
            new = params["to_ref"]
            node = self._scripture.pop(old)
            node["ref"] = new
            self._scripture[new] = node
            moved = {(t, new) for (t, r) in self._edges if r == old}
            self._edges = {(t, r) for (t, r) in self._edges if r != old} | moved
            return FakeResult([])

        if "SET s.ref = $old" in q and "$new" in q:
            # rollback rename
            old_new = params["new"]
            back = params["old"]
            node = self._scripture.pop(old_new)
            node["ref"] = back
            self._scripture[back] = node
            moved = {(t, back) for (t, r) in self._edges if r == old_new}
            self._edges = {(t, r) for (t, r) in self._edges if r != old_new} | moved
            return FakeResult([])

        if "MATCH (s:Scripture {ref: $to_ref}) RETURN count(s) AS c" in q:
            c = 1 if params["to_ref"] in self._scripture else 0
            return FakeResult([{"c": c}])

        if "SET t.organic_advance = true" in q:
            self._organic[params["n"]] = True
            return FakeResult([])

        if "SET t.organic_advance = $v" in q:
            self._organic[params["n"]] = params["v"]
            return FakeResult([])

        if "REMOVE t.organic_advance" in q:
            self._organic.pop(params["n"], None)
            return FakeResult([])

        if "MERGE (s:Scripture {ref: $ref})" in q:
            if params["ref"] not in self._scripture:
                self._scripture[params["ref"]] = {
                    "ref": params["ref"],
                    "text": params.get("text") or "",
                    "props": {"ref": params["ref"], "text": params.get("text") or ""},
                }
            return FakeResult([])

        if "DELETE r" in q and "$ref" in params and "$name" in params:
            self._edges.discard((params["name"], params["ref"]))
            return FakeResult([])

        # ---- snapshot / assert queries ----
        if "MATCH (s:Scripture) RETURN s.ref AS ref, properties(s) AS props" in q:
            rows = []
            for ref, node in sorted(self._scripture.items()):
                props = dict(node.get("props") or {"ref": ref, "text": node.get("text", "")})
                rows.append({"ref": ref, "props": props})
            return FakeResult(rows)

        if "MATCH (t:Truth_Point)-[r:SUPPORTED_BY]->(s:Scripture)" in q and "from_name" in q:
            rows = [
                {
                    "from_name": t,
                    "to_ref": ref,
                    "rel_type": ALLOWED_REL_TYPE,
                    "props": {},
                }
                for t, ref in sorted(self._edges)
            ]
            return FakeResult(rows)

        if "WHERE t.organic_advance IS NOT NULL" in q:
            rows = [
                {"name": n, "v": v}
                for n, v in sorted(self._organic.items())
                if v is not None
            ]
            return FakeResult(rows)

        if "MATCH (n:`Truth_Point`)" in q or "MATCH (n:`Branch`)" in q or "MATCH (n:`Trunk`)" in q:
            label = "Truth_Point"
            if "Branch" in q:
                label = "Branch"
            elif "Trunk" in q:
                label = "Trunk"
            tp = getattr(self, "_tp", {})
            if label == "Truth_Point":
                rows = []
                for name, props in sorted(tp.items()):
                    rows.append({"name": name, "props": dict(props)})
                # also include organic names as TPs
                for name in self._organic:
                    if name not in tp:
                        rows.append({"name": name, "props": {"name": name}})
                rows.sort(key=lambda r: r["name"])
                return FakeResult(rows)
            return FakeResult([])

        if "MATCH (a)-[r]->(b)" in q and "Truth_Point OR a:Branch" in q:
            return FakeResult(list(getattr(self, "_class_rels", [])))

        if "MATCH (s:Scripture) RETURN count(s) AS c" in q:
            return FakeResult([{"c": len(self._scripture)}])

        if f"MATCH ()-[r:{ALLOWED_REL_TYPE}]->() RETURN count(r) AS c" in q or (
            "SUPPORTED_BY" in q and "count(r) AS c" in q and "Truth_Point" not in q
        ):
            return FakeResult([{"c": len(self._edges)}])

        if "WHERE s.ref CONTAINS $x" in q:
            x = params.get("x", "")
            refs = sorted(r for r in self._scripture if x in r)
            if "count(s)" in q:
                return FakeResult([{"c": len(refs)}])
            return FakeResult([{"ref": r} for r in refs])

        if "MATCH (s:Scripture {ref: $ref}) RETURN s.ref AS ref, s.text AS text" in q:
            node = self._scripture.get(params["ref"])
            if not node:
                return FakeResult([])
            return FakeResult(
                [{"ref": params["ref"], "text": node.get("text") or ""}]
            )

        if "MATCH (t:Truth_Point)-[r]->(s:Scripture {ref: $ref})" in q:
            rows = [
                {"term": t, "rel_type": ALLOWED_REL_TYPE}
                for t, ref in self._edges
                if ref == params["ref"]
            ]
            return FakeResult(rows)

        if "MATCH (s:Scripture {ref: $ref})-[r]->(t:Truth_Point)" in q:
            return FakeResult([])

        if "WHERE t.organic_advance = true" in q:
            n = sum(1 for v in self._organic.values() if v is True)
            return FakeResult([{"c": n}])

        if "MATCH (t:Truth_Point {name: $n}) RETURN t.organic_advance AS v" in q and "keys" not in q:
            if params["n"] in self._organic:
                return FakeResult([{"v": self._organic[params["n"]]}])
            return FakeResult([])

        if "MATCH (t:Truth_Point {name: $n}) RETURN" in q and "keys(t)" in q:
            if params["n"] in self._organic:
                return FakeResult(
                    [
                        {
                            "v": self._organic[params["n"]],
                            "ks": ["organic_advance", "name"],
                            "organic_advance": self._organic[params["n"]],
                        }
                    ]
                )
            # node may exist without key
            return FakeResult([{"v": None, "ks": ["name"], "organic_advance": None}])

        if "RETURN t.name AS name" in q and "SUPPORTED_BY" in q and "$ref" in q:
            rows = [
                {"name": t}
                for t, ref in self._edges
                if ref == params["ref"]
            ]
            return FakeResult(rows)

        return FakeResult([])

    def commit(self) -> None:
        if self._graph is not None:
            self._graph.scripture = {k: dict(v) for k, v in self._scripture.items()}
            self._graph.edges = set(self._edges)
            self._graph.organic = dict(self._organic)
        self.committed = True
        self.closed = True

    def rollback(self) -> None:
        if self._graph is not None:
            self._sync_from_graph()
        self.rolled_back = True
        self.closed = True


class FakeGraph:
    def __init__(self) -> None:
        self.scripture: dict[str, dict] = {}
        self.edges: set[tuple[str, str]] = set()
        self.organic: dict[str, Any] = {}
        self.truth_points: dict[str, dict] = {}
        self.class_rels: list[dict] = []


class FakeSession:
    def __init__(self, graph: FakeGraph):
        self.graph = graph
        self.txs: list[FakeTx] = []
        self.begin_calls = 0

    def begin_transaction(self) -> FakeTx:
        self.begin_calls += 1
        tx = FakeTx(self.graph)
        self.txs.append(tx)
        return tx

    def run(self, query: str, params: Optional[dict] = None) -> FakeResult:
        # 只读路径：临时 tx 视图
        tx = FakeTx(self.graph)
        return tx.run(query, params)


def _mini_graph_rows(*, after_rename: bool = False) -> dict[str, list]:
    """合并+改名小图的原始行（供 compute_snapshot_hashes）。"""
    keep_ref = "约三16"
    merge_wrong = MERGE_CASES[0]["wrong"]  # 贴后三5
    merge_ok = MERGE_CASES[0]["correct"]  # 帖后三5
    ren_wrong = RENAME_CASES[0]["wrong"]  # 贴后二3
    ren_ok = RENAME_CASES[0]["correct"]  # 帖后二3

    if after_rename:
        sc = [
            {"ref": keep_ref, "props": {"ref": keep_ref, "text": "keep"}},
            {"ref": merge_ok, "props": {"ref": merge_ok, "text": "m"}},
            {"ref": ren_ok, "props": {"ref": ren_ok, "text": "r"}},
        ]
        sb = [
            {"from_name": "爱神", "to_ref": keep_ref, "rel_type": ALLOWED_REL_TYPE, "props": {}},
            {"from_name": "爱神", "to_ref": merge_ok, "rel_type": ALLOWED_REL_TYPE, "props": {}},
            {"from_name": "方法", "to_ref": ren_ok, "rel_type": ALLOWED_REL_TYPE, "props": {}},
        ]
    else:
        sc = [
            {"ref": keep_ref, "props": {"ref": keep_ref, "text": "keep"}},
            {"ref": merge_wrong, "props": {"ref": merge_wrong, "text": "mw"}},
            {"ref": merge_ok, "props": {"ref": merge_ok, "text": "m"}},
            {"ref": ren_wrong, "props": {"ref": ren_wrong, "text": "r"}},
        ]
        sb = [
            {"from_name": "爱神", "to_ref": keep_ref, "rel_type": ALLOWED_REL_TYPE, "props": {}},
            {"from_name": "爱神", "to_ref": merge_wrong, "rel_type": ALLOWED_REL_TYPE, "props": {}},
            {"from_name": "方法", "to_ref": ren_wrong, "rel_type": ALLOWED_REL_TYPE, "props": {}},
        ]

    organic = [
        {"name": "其它词", "v": True},
        {"name": ORGANIC_SET_TRUE, "v": None},
        {"name": ORGANIC_REMOVE, "v": True},
    ]
    # organic_rows 仅含有属性者
    organic_rows = [r for r in organic if r["v"] is not None]
    if after_rename:
        organic_rows = [
            {"name": "其它词", "v": True},
            {"name": ORGANIC_SET_TRUE, "v": True},
        ]

    go_nodes = [
        {"label": "Truth_Point", "name": "爱神", "props": {"name": "爱神"}},
        {"label": "Truth_Point", "name": "方法", "props": {"name": "方法"}},
        {"label": "Truth_Point", "name": "其它词", "props": {"name": "其它词"}},
        {
            "label": "Truth_Point",
            "name": ORGANIC_SET_TRUE,
            "props": {"name": ORGANIC_SET_TRUE},
        },
        {
            "label": "Truth_Point",
            "name": ORGANIC_REMOVE,
            "props": {"name": ORGANIC_REMOVE},
        },
    ]
    go_rels: list[dict] = []
    return {
        "scripture_nodes": sc,
        "supported_by": sb,
        "organic_rows": organic_rows,
        "graph_other_nodes": go_nodes,
        "graph_other_rels": go_rels,
    }


class TestPureLogic(unittest.TestCase):
    def test_rel_delta_with_duplicate(self):
        wrong_links = {
            "贴后三5": ["爱神", "神的爱"],
            "贴后三17": ["记号"],
            "贴后二13": ["那灵的圣别"],
        }
        correct_links = {
            "帖后三5": {"爱神"},
            "帖后三17": set(),
            "帖后二13": {"那灵的圣别"},
        }
        delta, dups = compute_rel_delta(MERGE_CASES, wrong_links, correct_links)
        self.assertEqual(delta, -2)
        self.assertEqual(len(dups), 2)

    def test_rel_delta_no_dup(self):
        wrong_links = {c["wrong"]: list(c["terms"]) for c in MERGE_CASES}
        correct_links = {c["correct"]: set() for c in MERGE_CASES}
        delta, dups = compute_rel_delta(MERGE_CASES, wrong_links, correct_links)
        self.assertEqual(delta, 0)
        self.assertEqual(dups, [])

    def test_already_applied(self):
        self.assertTrue(
            is_already_applied_state(
                tiehou_refs=[],
                scripture_n=EXPECT_SCRIPTURE_AFTER,
                organic_true_n=EXPECT_ORGANIC_N,
                cross_has_organic=True,
                death_has_organic=False,
                all_correct_exist=True,
            )
        )
        self.assertFalse(
            is_already_applied_state(
                tiehou_refs=["贴后三5"],
                scripture_n=EXPECT_SCRIPTURE_BEFORE,
                organic_true_n=EXPECT_ORGANIC_N,
                cross_has_organic=False,
                death_has_organic=True,
                all_correct_exist=False,
            )
        )

    def test_evaluate_check_ok(self):
        wrong_nodes = {}
        for case in MERGE_CASES + RENAME_CASES:
            links = [
                RelLink(term=t, ref=case["wrong"], rel_type=ALLOWED_REL_TYPE)
                for t in case["terms"]
            ]
            wrong_nodes[case["wrong"]] = NodeInfo(
                ref=case["wrong"],
                text="经文内容示例足够长",
                exists=True,
                links=links,
                rel_types=[ALLOWED_REL_TYPE] * len(links),
            )
        correct_merge = {
            c["correct"]: NodeInfo(
                ref=c["correct"], text="ok", exists=True, links=[], rel_types=[]
            )
            for c in MERGE_CASES
        }
        rename_absent = {c["correct"]: True for c in RENAME_CASES}
        plan = evaluate_check(
            wrong_nodes=wrong_nodes,
            correct_merge_nodes=correct_merge,
            correct_rename_absent=rename_absent,
            scripture_n=EXPECT_SCRIPTURE_BEFORE,
            supported_by_n=9768,
            organic_true_n=69,
            organic_cross=None,
            organic_death=True,
            same_as_info={ORGANIC_SET_TRUE: False, ORGANIC_REMOVE: False},
        )
        self.assertTrue(plan.ok)
        self.assertFalse(plan.already_applied)
        self.assertEqual(plan.expect_scripture_after, EXPECT_SCRIPTURE_AFTER)
        ops = build_apply_ops(plan)
        kinds = [o["op"] for o in ops]
        self.assertIn("merge_supported_by", kinds)
        self.assertIn("detach_delete_scripture", kinds)
        self.assertIn("rename_ref", kinds)
        self.assertEqual(kinds.count("set_organic_true"), 1)
        self.assertEqual(kinds.count("remove_organic"), 1)
        first_rename = kinds.index("rename_ref")
        last_delete = max(
            i for i, k in enumerate(kinds) if k == "detach_delete_scripture"
        )
        self.assertLess(last_delete, first_rename)
        self.assertEqual(kinds[-2:], ["set_organic_true", "remove_organic"])

    def test_evaluate_check_fails_missing_wrong(self):
        wrong_nodes = {
            ref: NodeInfo(ref, "", False)
            for ref in [c["wrong"] for c in MERGE_CASES + RENAME_CASES]
        }
        correct_merge = {
            c["correct"]: NodeInfo(c["correct"], "", True) for c in MERGE_CASES
        }
        plan = evaluate_check(
            wrong_nodes=wrong_nodes,
            correct_merge_nodes=correct_merge,
            correct_rename_absent={c["correct"]: True for c in RENAME_CASES},
            scripture_n=EXPECT_SCRIPTURE_BEFORE,
            supported_by_n=9768,
            organic_true_n=69,
            organic_cross=None,
            organic_death=True,
            same_as_info={ORGANIC_SET_TRUE: False, ORGANIC_REMOVE: False},
        )
        self.assertFalse(plan.ok)
        self.assertTrue(any("缺「贴后」" in f for f in plan.fails))

    def test_evaluate_check_rejects_other_rel(self):
        case = MERGE_CASES[0]
        wrong_nodes = {
            c["wrong"]: NodeInfo(c["wrong"], "t", True, [], [ALLOWED_REL_TYPE])
            for c in MERGE_CASES + RENAME_CASES
        }
        wrong_nodes[case["wrong"]] = NodeInfo(
            case["wrong"],
            "t",
            True,
            [RelLink("爱神", case["wrong"], "OTHER")],
            ["OTHER"],
        )
        for c in MERGE_CASES[1:] + RENAME_CASES:
            wrong_nodes[c["wrong"]] = NodeInfo(
                c["wrong"],
                "t",
                True,
                [RelLink(c["terms"][0], c["wrong"], ALLOWED_REL_TYPE)],
                [ALLOWED_REL_TYPE],
            )
        plan = evaluate_check(
            wrong_nodes=wrong_nodes,
            correct_merge_nodes={
                c["correct"]: NodeInfo(c["correct"], "", True) for c in MERGE_CASES
            },
            correct_rename_absent={c["correct"]: True for c in RENAME_CASES},
            scripture_n=EXPECT_SCRIPTURE_BEFORE,
            supported_by_n=9768,
            organic_true_n=69,
            organic_cross=None,
            organic_death=True,
            same_as_info={ORGANIC_SET_TRUE: False, ORGANIC_REMOVE: False},
        )
        self.assertFalse(plan.ok)
        self.assertTrue(any("非 SUPPORTED_BY" in f for f in plan.fails))

    def test_affected_refs_has_twelve(self):
        self.assertEqual(len(AFFECTED_REFS), 12)
        for c in MERGE_CASES + RENAME_CASES:
            self.assertIn(c["wrong"], AFFECTED_REFS)
            self.assertIn(c["correct"], AFFECTED_REFS)


class TestSnapshotKeep(unittest.TestCase):
    def test_keep_equal_after_merge_rename(self):
        before = compute_snapshot_hashes(**_mini_graph_rows(after_rename=False))
        after = compute_snapshot_hashes(**_mini_graph_rows(after_rename=True))
        self.assertEqual(before["scripture_keep_sha"], after["scripture_keep_sha"])
        self.assertEqual(
            before["supported_by_keep_sha"], after["supported_by_keep_sha"]
        )
        self.assertEqual(before["organic_keep_sha"], after["organic_keep_sha"])
        self.assertEqual(before["graph_other_sha"], after["graph_other_sha"])
        # all 应变化（节点集合变了）
        self.assertNotEqual(before["scripture_all_sha"], after["scripture_all_sha"])

    def test_keep_unequal_if_rename_target_omitted(self):
        """确认：若受影响集合漏掉改名目标 ref，则 keep 哈希改前改后不等（缺陷二）。"""
        rename_targets = {c["correct"] for c in RENAME_CASES}
        buggy = set(AFFECTED_REFS) - rename_targets
        before = compute_snapshot_hashes(
            **_mini_graph_rows(after_rename=False), affected_refs=buggy
        )
        after = compute_snapshot_hashes(
            **_mini_graph_rows(after_rename=True), affected_refs=buggy
        )
        self.assertNotEqual(
            before["scripture_keep_sha"], after["scripture_keep_sha"]
        )
        self.assertNotEqual(
            before["supported_by_keep_sha"], after["supported_by_keep_sha"]
        )


class TestFakeTxApply(unittest.TestCase):
    def test_apply_ops_order_and_idempotent_state(self):
        tx = FakeTx()
        scripture = {
            c["wrong"]: {"ref": c["wrong"], "text": "x"}
            for c in MERGE_CASES + RENAME_CASES
        }
        for c in MERGE_CASES:
            scripture[c["correct"]] = {"ref": c["correct"], "text": "y"}
        edges = set()
        for c in MERGE_CASES + RENAME_CASES:
            for t in c["terms"]:
                edges.add((t, c["wrong"]))
        edges.add(("爱神", "帖后三5"))
        organic = {ORGANIC_REMOVE: True}
        tx.seed(scripture, edges, organic)

        wrong_nodes = {}
        for c in MERGE_CASES + RENAME_CASES:
            links = [
                RelLink(term=t, ref=c["wrong"], rel_type=ALLOWED_REL_TYPE)
                for t in c["terms"]
            ]
            wrong_nodes[c["wrong"]] = NodeInfo(
                c["wrong"], "x", True, links, [ALLOWED_REL_TYPE] * len(links)
            )
        plan = evaluate_check(
            wrong_nodes=wrong_nodes,
            correct_merge_nodes={
                c["correct"]: NodeInfo(
                    c["correct"],
                    "y",
                    True,
                    [RelLink("爱神", "帖后三5", ALLOWED_REL_TYPE)]
                    if c["correct"] == "帖后三5"
                    else [],
                    [ALLOWED_REL_TYPE] if c["correct"] == "帖后三5" else [],
                )
                for c in MERGE_CASES
            },
            correct_rename_absent={c["correct"]: True for c in RENAME_CASES},
            scripture_n=EXPECT_SCRIPTURE_BEFORE,
            supported_by_n=100,
            organic_true_n=69,
            organic_cross=None,
            organic_death=True,
            same_as_info={ORGANIC_SET_TRUE: False, ORGANIC_REMOVE: False},
        )
        ops = build_apply_ops(plan)
        _tx_apply(tx, ops)

        for c in MERGE_CASES:
            self.assertNotIn(c["wrong"], tx._scripture)
            self.assertIn(c["correct"], tx._scripture)
        for c in RENAME_CASES:
            self.assertNotIn(c["wrong"], tx._scripture)
            self.assertIn(c["correct"], tx._scripture)
        self.assertEqual(tx._organic.get(ORGANIC_SET_TRUE), True)
        self.assertNotIn(ORGANIC_REMOVE, tx._organic)
        texts = [q for q, _ in tx.queries]
        self.assertTrue(any("MERGE (t)-[r:SUPPORTED_BY]->(s)" in q for q in texts))
        idx_remove = next(
            i for i, q in enumerate(texts) if "REMOVE t.organic_advance" in q
        )
        idx_set = next(
            i for i, q in enumerate(texts) if "SET t.organic_advance = true" in q
        )
        self.assertLess(idx_set, idx_remove)
        self.assertTrue(
            is_already_applied_state(
                tiehou_refs=[],
                scripture_n=EXPECT_SCRIPTURE_AFTER,
                organic_true_n=EXPECT_ORGANIC_N,
                cross_has_organic=True,
                death_has_organic=False,
                all_correct_exist=True,
            )
        )


class TestTransactionGuards(unittest.TestCase):
    def _seed_applied_like_graph(self) -> FakeGraph:
        g = FakeGraph()
        # 已是最终态：无贴后，有帖后，organic 正确
        for c in MERGE_CASES + RENAME_CASES:
            g.scripture[c["correct"]] = {
                "ref": c["correct"],
                "text": "t",
                "props": {"ref": c["correct"], "text": "t"},
            }
            for t in c["terms"]:
                g.edges.add((t, c["correct"]))
                g.truth_points[t] = {"name": t}
        for i in range(EXPECT_SCRIPTURE_AFTER - len(g.scripture)):
            ref = f"填充{i}"
            g.scripture[ref] = {"ref": ref, "text": "x", "props": {"ref": ref, "text": "x"}}
        g.organic[ORGANIC_SET_TRUE] = True
        g.truth_points[ORGANIC_SET_TRUE] = {"name": ORGANIC_SET_TRUE}
        g.truth_points[ORGANIC_REMOVE] = {"name": ORGANIC_REMOVE}
        # 凑 organic=69
        for i in range(EXPECT_ORGANIC_N - 1):
            n = f"有机{i}"
            g.organic[n] = True
            g.truth_points[n] = {"name": n}
        return g

    def test_assert_fail_rolls_back_no_commit(self):
        g = FakeGraph()
        g.scripture["约三16"] = {
            "ref": "约三16",
            "text": "k",
            "props": {"ref": "约三16", "text": "k"},
        }
        g.edges.add(("其它", "约三16"))
        g.organic["其它词"] = True
        session = FakeSession(g)
        before = compute_snapshot_hashes(**{
            "scripture_nodes": [
                {"ref": "约三16", "props": {"ref": "约三16", "text": "k"}}
            ],
            "supported_by": [
                {
                    "from_name": "其它",
                    "to_ref": "约三16",
                    "rel_type": ALLOWED_REL_TYPE,
                    "props": {},
                }
            ],
            "organic_rows": [{"name": "其它词", "v": True}],
            "graph_other_nodes": [
                {"label": "Truth_Point", "name": "其它词", "props": {"name": "其它词"}}
            ],
            "graph_other_rels": [],
        })
        # 空 ops，但期望边数故意错误 → 断言失败
        ok, fails, outcome = apply_in_transaction(
            session,
            [],
            before_snapshots=before,
            expect_supported_by_after=99999,
        )
        self.assertFalse(ok)
        self.assertEqual(outcome, "rolled_back")
        self.assertTrue(any("SUPPORTED_BY" in f for f in fails))
        self.assertEqual(session.begin_calls, 1)
        self.assertTrue(session.txs[0].rolled_back)
        self.assertFalse(session.txs[0].committed)

    def test_write_exception_rolls_back(self):
        g = FakeGraph()
        # 改名目标已存在 → _tx_apply 抛 FixError
        g.scripture["贴后二3"] = {
            "ref": "贴后二3",
            "text": "a",
            "props": {"ref": "贴后二3", "text": "a"},
        }
        g.scripture["帖后二3"] = {
            "ref": "帖后二3",
            "text": "b",
            "props": {"ref": "帖后二3", "text": "b"},
        }
        session = FakeSession(g)
        ops = [{"op": "rename_ref", "from_ref": "贴后二3", "to_ref": "帖后二3"}]
        ok, fails, outcome = apply_in_transaction(
            session,
            ops,
            before_snapshots={},
            expect_supported_by_after=0,
        )
        self.assertFalse(ok)
        self.assertEqual(outcome, "exception_rolled_back")
        self.assertTrue(session.txs[0].rolled_back)
        self.assertFalse(session.txs[0].committed)
        self.assertTrue(any("写操作异常" in f for f in fails))

    def test_success_commits(self):
        g = self._seed_applied_like_graph()
        session = FakeSession(g)
        # 已是最终态：空写 + 正确期望 → 断言过 → commit
        # 先取 before（与 after 相同）
        tx0 = FakeTx(g)
        from fix_graph_20261116 import take_snapshots

        before = take_snapshots(tx0)
        ok, fails, outcome = apply_in_transaction(
            session,
            [],
            before_snapshots=before,
            expect_supported_by_after=len(g.edges),
        )
        self.assertTrue(ok, fails)
        self.assertEqual(outcome, "committed")
        self.assertTrue(session.txs[-1].committed)
        self.assertFalse(session.txs[-1].rolled_back)

    def test_idempotent_apply_no_write_tx(self):
        g = self._seed_applied_like_graph()
        session = FakeSession(g)

        class PlanSession(FakeSession):
            """mode_apply 用 session.run 做 collect_check；这里简化为 already_applied。"""

        # 直接测 mode_apply：用已应用判定路径
        # monkey: 构造返回 already_applied 的 plan 较重，改为调用 mode_apply 前 stub
        import fix_graph_20261116 as m
        import tempfile
        from pathlib import Path

        def fake_collect(_session):
            from fix_graph_20261116 import CheckPlan

            return CheckPlan(
                ok=True,
                fails=[],
                warnings=[],
                already_applied=True,
                merge={},
                rename={},
                organic={},
                scripture_n=EXPECT_SCRIPTURE_AFTER,
                supported_by_n=len(g.edges),
                expect_scripture_after=EXPECT_SCRIPTURE_AFTER,
                expect_supported_by_after=len(g.edges),
                expect_supported_by_delta=0,
                duplicate_moves=[],
                snapshots={},
            )

        old = m.collect_check
        m.collect_check = fake_collect  # type: ignore
        try:
            with tempfile.TemporaryDirectory() as td:
                code = mode_apply(session, Path(td), Path(td) / "bak")
            self.assertEqual(code, 0)
            self.assertEqual(session.begin_calls, 0)
        finally:
            m.collect_check = old

    def test_rollback_hash_mismatch_no_commit(self):
        g = self._seed_applied_like_graph()
        session = FakeSession(g)
        backup = {
            "organic_targets": [
                {"name": ORGANIC_SET_TRUE, "has_key": True, "organic_advance": True},
                {"name": ORGANIC_REMOVE, "has_key": False, "organic_advance": None},
            ],
            "scripture_nodes": [],
            "supported_by": [],
            "snapshots": {
                "scripture_all_sha": "deadbeef",
                "supported_by_all_sha": "deadbeef",
                "organic_all_sha": "deadbeef",
                "graph_other_sha": "deadbeef",
            },
        }
        ok, fails, _after = run_rollback_in_transaction(session, backup)
        self.assertFalse(ok)
        self.assertTrue(any("回滚后快照≠备份" in f for f in fails))
        self.assertTrue(session.txs[0].rolled_back)
        self.assertFalse(session.txs[0].committed)


if __name__ == "__main__":
    unittest.main()
