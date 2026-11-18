# -*- coding: utf-8 -*-
"""只读 Neo4j 客户端。"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger("qa4.neo4j")


class Neo4jClient:
    def __init__(self, uri: str, user: str = "", password: str = "") -> None:
        self.uri = uri
        self.user = user
        self._driver = None
        if uri:
            try:
                from neo4j import GraphDatabase, READ_ACCESS

                self._READ = READ_ACCESS
                self._driver = GraphDatabase.driver(uri, auth=(user, password))
            except Exception as e:
                logger.warning("Neo4j 客户端初始化失败: %s", type(e).__name__)
                self._driver = None
        password = ""

    def close(self) -> None:
        if self._driver:
            self._driver.close()
            self._driver = None

    def ping(self) -> bool:
        if not self._driver:
            return False
        try:
            self._driver.verify_connectivity()
            return True
        except Exception as e:
            logger.warning("Neo4j ping 失败: %s", type(e).__name__)
            return False

    def label_counts(self, labels: list[str]) -> dict[str, Optional[int]]:
        out: dict[str, Optional[int]] = {}
        if not self._driver:
            return {lb: None for lb in labels}
        try:
            with self._driver.session(default_access_mode=self._READ) as session:
                for lb in labels:
                    # 标签名白名单：仅字母数字下划线
                    if not lb.replace("_", "").isalnum():
                        out[lb] = None
                        continue
                    rows = session.run(f"MATCH (n:`{lb}`) RETURN count(n) AS c")
                    rec = rows.single()
                    out[lb] = int(rec["c"]) if rec else 0
        except Exception as e:
            logger.warning("Neo4j 计数失败: %s", type(e).__name__)
            return {lb: None for lb in labels}
        return out

    def supported_by(self, term: str) -> list[str]:
        """阶段 2 新增：词条的 SUPPORTED_BY 经节 ref 列表（只读）。失败返回空。"""
        if not self._driver or not term:
            return []
        try:
            with self._driver.session(default_access_mode=self._READ) as session:
                rows = session.run(
                    "MATCH (t:Truth_Point {name: $n})-[:SUPPORTED_BY]->(s:Scripture) "
                    "RETURN s.ref AS ref ORDER BY ref",
                    {"n": term},
                )
                return [str(r["ref"]) for r in rows if r["ref"]]
        except Exception as e:
            logger.warning("Neo4j supported_by 失败: %s", type(e).__name__)
            return []

    def scripture_refs(self, limit: int = 100000) -> list[str]:
        """阶段 2 在线检查用：全部 Scripture.ref。"""
        if not self._driver:
            return []
        with self._driver.session(default_access_mode=self._READ) as session:
            rows = session.run(
                "MATCH (s:Scripture) RETURN s.ref AS ref LIMIT $n", {"n": int(limit)}
            )
            return [str(r["ref"]) for r in rows if r["ref"]]

    def truth_points_with_devine(self, limit: int = 100000) -> list[dict[str, Any]]:
        """Truth_Point 上非空 devine_argument：[{name, devine_argument}, ...]。"""
        if not self._driver:
            return []
        try:
            with self._driver.session(default_access_mode=self._READ) as session:
                rows = session.run(
                    "MATCH (n:Truth_Point) WHERE n.devine_argument IS NOT NULL "
                    "AND toString(n.devine_argument) <> '' "
                    "RETURN n.name AS name, n.devine_argument AS devine_argument "
                    "LIMIT $n",
                    {"n": int(limit)},
                )
                out = []
                for r in rows:
                    if r.get("name") is None:
                        continue
                    out.append({"name": str(r["name"]), "devine_argument": r.get("devine_argument")})
                return out
        except Exception as e:
            logger.warning("Neo4j truth_points_with_devine 失败: %s", type(e).__name__)
            return []

    def devine_for_names(self, names: list[str]) -> list[dict[str, Any]]:
        """按词条名取 devine_argument（只读）。"""
        if not self._driver or not names:
            return []
        try:
            with self._driver.session(default_access_mode=self._READ) as session:
                rows = session.run(
                    "MATCH (n:Truth_Point) WHERE n.name IN $names "
                    "AND n.devine_argument IS NOT NULL AND toString(n.devine_argument) <> '' "
                    "RETURN n.name AS name, n.devine_argument AS devine_argument",
                    {"names": list(names)},
                )
                return [
                    {"name": str(r["name"]), "devine_argument": r.get("devine_argument")}
                    for r in rows
                    if r.get("name") is not None
                ]
        except Exception as e:
            logger.warning("Neo4j devine_for_names 失败: %s", type(e).__name__)
            return []


class FakeNeo4jClient(Neo4jClient):
    def __init__(
        self,
        counts: Optional[dict[str, int]] = None,
        *,
        reachable: bool = True,
        scripture_links: Optional[dict[str, list[str]]] = None,
        devine_by_name: Optional[dict[str, Any]] = None,
    ):
        self.uri = "fake"
        self._driver = object() if reachable else None
        self._counts = counts or {}
        self._reachable = reachable
        self._links = scripture_links or {}
        self._devine = dict(devine_by_name or {})

    def supported_by(self, term: str) -> list[str]:
        if not self._reachable:
            return []
        return list(self._links.get(term, []))

    def scripture_refs(self, limit: int = 100000) -> list[str]:
        out: list[str] = []
        for refs in self._links.values():
            out.extend(refs)
        return out[:limit]

    def truth_points_with_devine(self, limit: int = 100000) -> list[dict[str, Any]]:
        if not self._reachable:
            return []
        rows = [{"name": k, "devine_argument": v} for k, v in self._devine.items()]
        return rows[:limit]

    def devine_for_names(self, names: list[str]) -> list[dict[str, Any]]:
        if not self._reachable:
            return []
        return [{"name": n, "devine_argument": self._devine[n]} for n in names if n in self._devine]

    def close(self) -> None:
        return

    def ping(self) -> bool:
        return self._reachable

    def label_counts(self, labels: list[str]) -> dict[str, Optional[int]]:
        if not self._reachable:
            return {lb: None for lb in labels}
        return {lb: int(self._counts.get(lb, 0)) for lb in labels}
