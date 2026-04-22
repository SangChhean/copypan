# -*- coding: utf-8 -*-
"""Neo4j 连接、概念名列表加载与图谱查询（back_shared 版）。"""
import os
from typing import Any

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")

MIN_HOPS, MAX_HOPS = 1, 5


class Neo4jClient:
    """Neo4j 图谱客户端。
    核心原则：图谱是增强层而非前置依赖。
    Neo4j 不可用或图谱为空时，所有方法返回空结果，不抛异常。
    """

    def __init__(self) -> None:
        self._uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        self._user = os.environ.get("NEO4J_USER", "neo4j")
        self._password = os.environ.get("NEO4J_PASSWORD", "")
        self._driver = None
        self._concept_names: list[str] = []
        self._available: bool = False

    def startup(self) -> None:
        """尝试连接 Neo4j；成功则刷新概念名列表，失败则不抛异常。"""
        try:
            from neo4j import GraphDatabase
            driver = GraphDatabase.driver(
                self._uri,
                auth=(self._user, self._password),
            )
            driver.verify_connectivity()
            self._driver = driver
            self._available = True
            self.refresh_concept_names()
        except Exception as e:
            print(f"[QA] Neo4j 连接失败，图谱功能将降级为空: {e}")
            self._available = False
            self._concept_names = []
            if getattr(self, "_driver", None) is not None:
                try:
                    self._driver.close()
                except Exception:
                    pass
                self._driver = None

    def shutdown(self) -> None:
        """关闭 driver 连接。"""
        if self._driver is not None:
            try:
                self._driver.close()
            except Exception:
                pass
            self._driver = None
        self._available = False

    def refresh_concept_names(self) -> None:
        """从 Neo4j 查询所有 Concept 的 name，构建供 Step 1 Prompt 使用的概念名列表。"""
        if not self._available or self._driver is None:
            return
        try:
            with self._driver.session() as session:
                result = session.run(
                    "MATCH (c:Concept) RETURN c.name AS name ORDER BY c.name"
                )
                names: list[str] = []
                for record in result:
                    name = record.get("name")
                    if name is None:
                        continue
                    name_str = str(name).strip()
                    if not name_str:
                        continue
                    names.append(name_str)
                self._concept_names = names
                print(f"[QA] Concept name 列表已加载: {len(self._concept_names)} 个概念节点")
        except Exception as e:
            print(f"[QA] 加载 Concept name 列表失败: {e}")
            self._concept_names = []

    def get_concept_names(self) -> list[str]:
        """返回 Concept name 列表副本，供 Step 1 Prompt 注入。"""
        return list(self._concept_names)

    def get_greek_terms(self, concept_names: list[str]) -> dict[str, str]:
        """查询概念列表对应的希腊／希伯来原文。
        输入：概念名称列表
        输出：{ concept_name: greek_terms_string }
        无 greek_terms 的概念不出现在结果中（静默跳过）。
        不可用时返回空 dict，不抛异常。
        """
        if not self._available or self._driver is None or not concept_names:
            return {}
        names = [str(x).strip() for x in concept_names if str(x).strip()]
        if not names:
            return {}
        try:
            with self._driver.session() as session:
                result = session.run(
                    "MATCH (c:Concept) "
                    "WHERE c.name IN $names "
                    "  AND c.greek_terms IS NOT NULL "
                    "  AND c.greek_terms <> '' "
                    "  AND c.greek_terms <> [] "
                    "RETURN c.name AS concept, c.greek_terms AS greek_terms",
                    names=names,
                )
                out: dict[str, str] = {}
                for record in result:
                    concept = record.get("concept")
                    greek = record.get("greek_terms")
                    if not concept:
                        continue
                    # greek_terms 可能是字符串或列表，统一转为字符串
                    if isinstance(greek, list):
                        greek_str = "、".join(str(g).strip() for g in greek if str(g).strip())
                    else:
                        greek_str = str(greek).strip() if greek else ""
                    if not greek_str:
                        continue
                    out[str(concept)] = greek_str
                return out
        except Exception as e:
            print(f"[QA] get_greek_terms 失败: {e}")
            return {}

    def get_key_verses(self, concept_names: list[str]) -> dict[str, list[tuple[str, str]]]:
        """查询概念列表通过 SUPPORTED_BY 关系连接的 Scripture 节点。
        返回 {概念名: [(id, text), ...]}。
        无结果或不可用时返回空 dict。
        """
        if not self._available or self._driver is None or not concept_names:
            return {}
        names = [str(x).strip() for x in concept_names if str(x).strip()]
        if not names:
            return {}
        try:
            with self._driver.session() as session:
                result = session.run(
                    "MATCH (c:Concept)-[:SUPPORTED_BY]->(s:Scripture) "
                    "WHERE c.name IN $names "
                    "RETURN c.name AS concept, s.id AS sid, s.text AS stext",
                    names=names,
                )
                out: dict[str, list[tuple[str, str]]] = {}
                for record in result:
                    concept = record.get("concept")
                    stext = (record.get("stext") or "").strip()
                    sid = (record.get("sid") or "").strip()
                    if not concept or not stext:
                        continue
                    out.setdefault(concept, []).append((sid, stext))
                return out
        except Exception as e:
            print(f"[QA] get_key_verses 失败: {e}")
            return {}

    def get_baseline(self) -> dict[str, Any]:
        """查询数据基线：concept_total 与 concept_with_greek_terms。
        供 readiness 接口使用，不可用时返回 -1。
        """
        if not self._available or self._driver is None:
            return {"concept_total": -1, "concept_with_greek_terms": -1}
        try:
            with self._driver.session() as session:
                result = session.run(
                    "MATCH (c:Concept) "
                    "RETURN "
                    "  count(c) AS total, "
                    "  sum(CASE WHEN c.greek_terms IS NOT NULL "
                    "            AND c.greek_terms <> '' "
                    "            AND c.greek_terms <> [] "
                    "       THEN 1 ELSE 0 END) AS has_greek_terms"
                )
                record = result.single()
                if record:
                    return {
                        "concept_total": int(record["total"]),
                        "concept_with_greek_terms": int(record["has_greek_terms"]),
                    }
                return {"concept_total": -1, "concept_with_greek_terms": -1}
        except Exception as e:
            print(f"[QA] get_baseline 失败: {e}")
            return {"concept_total": -1, "concept_with_greek_terms": -1}
