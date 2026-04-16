# -*- coding: utf-8 -*-
"""Neo4j 连接、概念名列表加载与图谱查询。"""
import os
from typing import Any

# 环境变量，合理默认
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")

# 跳数范围，用于 Cypher [*..N] 拼接前校验
MIN_HOPS, MAX_HOPS = 1, 5


class Neo4jClient:
    """Neo4j 图谱客户端，管理连接、概念名列表和图谱查询。

    核心原则：图谱是增强层而非前置依赖。
    Neo4j 不可用或图谱为空时，所有方法返回空结果，不抛异常，
    让流水线自然降级为纯双路 RAG。
    """

    def __init__(self) -> None:
        self._uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        self._user = os.environ.get("NEO4J_USER", "neo4j")
        self._password = os.environ.get("NEO4J_PASSWORD", "")
        self._driver = None
        self._concept_names: list[str] = []
        self._available: bool = False

    def startup(self) -> None:
        """尝试连接 Neo4j；成功则刷新概念名列表，失败则不抛异常并设 _available=False。同步方法，供 FastAPI 启动或 get_service 时调用。"""
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
            print(f"[KG-RAG] Neo4j 连接失败，图谱功能将降级为空: {e}")
            self._available = False
            self._concept_names = []
            if getattr(self, "_driver", None) is not None:
                try:
                    self._driver.close()
                except Exception:
                    pass
                self._driver = None

    def shutdown(self) -> None:
        """关闭 driver 连接（如果存在）。"""
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
                print(f"[KG-RAG] Concept name 列表已加载: {len(self._concept_names)} 个概念节点")
        except Exception as e:
            print(f"[KG-RAG] 加载 Concept name 列表失败: {e}")
            self._concept_names = []

    def get_concept_names(self) -> list[str]:
        """返回 Concept name 列表副本，供 Step 1 Prompt 注入。"""
        return list(self._concept_names)

    def get_neighbors(self, concept_name: str) -> list[dict[str, Any]]:
        """单概念 1 跳出边邻居（c → related），同一 neighbor 多条边时按类型合并。
        每条记录包含：
          neighbor      - 邻居概念名
          relations     - 出边关系字符串列表（完整，供显示用）
          relation_type - 所有关系类型用 ／ 拼接
        """
        if not self._available or self._driver is None:
            return []
        key = concept_name.strip()
        try:
            with self._driver.session() as session:
                out_result = session.run(
                    "MATCH (c:Concept {name: $name})-[r]->(related:Concept) "
                    "RETURN related.name AS neighbor, type(r) AS relation_type",
                    name=key,
                )
                out_rows = [
                    {
                        "neighbor": r["neighbor"],
                        "relation_type": r["relation_type"],
                        "relation_str": f"{key} ──{r['relation_type']}──► {r['neighbor']}",
                    }
                    for r in out_result
                    if r["neighbor"]
                ]
                merged: dict[str, dict] = {}
                for row in out_rows:
                    nb = row["neighbor"]
                    if nb not in merged:
                        merged[nb] = {
                            "neighbor": nb,
                            "relation_type": row["relation_type"],
                            "_rel_types": [row["relation_type"]],
                            "relations": [row["relation_str"]],
                        }
                    else:
                        if row["relation_str"] not in merged[nb]["relations"]:
                            merged[nb]["relations"].append(row["relation_str"])
                        if row["relation_type"] not in merged[nb]["_rel_types"]:
                            merged[nb]["_rel_types"].append(row["relation_type"])
                result = []
                for nb_data in merged.values():
                    rel_types = nb_data.pop("_rel_types")
                    nb_data["relation_type"] = " ／ ".join(rel_types)
                    result.append(nb_data)
                return result
        except Exception as e:
            print(f"[KG-RAG] get_neighbors 失败: {e}")
            return []

    def get_paths_between(self, concepts: list[str]) -> list[dict[str, Any]]:
        """查询给定概念集合内部的 1 跳直接路径。"""
        if not self._available or self._driver is None:
            return []
        if not concepts:
            return []
        names = [str(x).strip() for x in concepts if str(x).strip()]
        if len(names) < 2:
            return []
        try:
            with self._driver.session() as session:
                q1 = (
                    "MATCH (a:Concept)-[r]->(b:Concept) "
                    "WHERE a.name IN $names AND b.name IN $names AND a.name <> b.name "
                    "RETURN a.name AS from_name, type(r) AS relation, b.name AS to_name"
                )
                r1 = session.run(q1, names=names)
                out: list[dict[str, Any]] = []
                seen: set[tuple] = set()
                for row in r1:
                    f = row.get("from_name")
                    rel = row.get("relation")
                    t = row.get("to_name")
                    if not f or not rel or not t:
                        continue
                    key = (f, rel, t)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append({"from": f, "relation": rel, "to": t, "hops": 1})
                return out
        except Exception as e:
            print(f"[KG-RAG] get_paths_between 失败: {e}")
            return []

    def _clamp_hops(self, max_hops: int) -> int:
        """将 max_hops 限制在 [MIN_HOPS, MAX_HOPS]，用于 Cypher 拼接。"""
        try:
            n = int(max_hops)
        except (TypeError, ValueError):
            return MAX_HOPS
        if n < MIN_HOPS:
            return MIN_HOPS
        if n > MAX_HOPS:
            return MAX_HOPS
        return n

    def get_paths(
        self, concept_a: str, concept_b: str, max_hops: int = 3
    ) -> list[dict[str, Any]]:
        """两概念间 max_hops 内全部路径。
        relations 返回 [{"type": "...", "forward": bool}, ...]，
        forward=True 表示该边方向与路径遍历方向一致（path_nodes[i]→path_nodes[i+1]）。
        """
        if not self._available or self._driver is None:
            return []
        n = self._clamp_hops(max_hops)
        try:
            with self._driver.session() as session:
                query = (
                    f"MATCH path = (a:Concept {{name: $n1}})-[*..{n}]-(b:Concept {{name: $n2}}) "
                    "WITH path, [nd IN nodes(path) | nd.name] AS path_nodes "
                    "RETURN path_nodes, "
                    "[idx IN range(0, length(path)-1) | {"
                    "  type: type(relationships(path)[idx]),"
                    "  forward: startNode(relationships(path)[idx]).name = path_nodes[idx]"
                    "}] AS relations"
                )
                result = session.run(
                    query,
                    n1=concept_a.strip(),
                    n2=concept_b.strip(),
                )
                return [
                    {"path_nodes": record["path_nodes"], "relations": record["relations"]}
                    for record in result
                ]
        except Exception as e:
            print(f"[KG-RAG] get_paths 失败: {e}")
            return []

    def get_shortest_path(
        self, concept_a: str, concept_b: str, max_hops: int = 3
    ) -> dict[str, Any] | None:
        """shortestPath 查询，返回单条路径 dict 或 None。
        relations 返回 [{"type": "...", "forward": bool}, ...]，同 get_paths。
        """
        if not self._available or self._driver is None:
            return None
        n = self._clamp_hops(max_hops)
        try:
            with self._driver.session() as session:
                query = (
                    f"MATCH path = shortestPath((a:Concept {{name: $n1}})-[*..{n}]-(b:Concept {{name: $n2}})) "
                    "WITH path, [nd IN nodes(path) | nd.name] AS path_nodes "
                    "RETURN path_nodes, "
                    "[idx IN range(0, length(path)-1) | {"
                    "  type: type(relationships(path)[idx]),"
                    "  forward: startNode(relationships(path)[idx]).name = path_nodes[idx]"
                    "}] AS relations"
                )
                result = session.run(
                    query,
                    n1=concept_a.strip(),
                    n2=concept_b.strip(),
                )
                record = result.single()
                if record and record["path_nodes"]:
                    return {"path_nodes": record["path_nodes"], "relations": record["relations"]}
                return None
        except Exception as e:
            print(f"[KG-RAG] get_shortest_path 失败: {e}")
            return None

    def get_path_count(
        self, concept_a: str, concept_b: str, max_hops: int = 3
    ) -> int:
        """两概念间 max_hops 内路径总数。"""
        if not self._available or self._driver is None:
            return 0
        n = self._clamp_hops(max_hops)
        try:
            with self._driver.session() as session:
                query = (
                    f"MATCH path = (a:Concept {{name: $n1}})-[*..{n}]-(b:Concept {{name: $n2}}) "
                    "RETURN count(path) AS path_count"
                )
                result = session.run(
                    query,
                    n1=concept_a.strip(),
                    n2=concept_b.strip(),
                )
                record = result.single()
                if record and record["path_count"] is not None:
                    return int(record["path_count"])
                return 0
        except Exception as e:
            print(f"[KG-RAG] get_path_count 失败: {e}")
            return 0

    def get_key_verses(self, concept_names: list[str]) -> dict[str, list[str]]:
        """查询概念列表通过 SUPPORTED_BY 关系连接的 Scripture 节点。
        返回 {概念名: [text_short, ...]}，无结果或不可用时返回空 dict。
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
                    "RETURN c.name AS concept, s.text_short AS verse",
                    names=names,
                )
                out: dict[str, list[str]] = {}
                for record in result:
                    concept = record.get("concept")
                    verse = record.get("verse")
                    if not concept or not verse:
                        continue
                    out.setdefault(concept, []).append(verse)
                return out
        except Exception as e:
            print(f"[KG-RAG] get_key_verses 失败: {e}")
            return {}

    def create_scripture_node(
        self, concept_name: str, id: str, text_short: str, text_full: str
    ) -> bool:
        """创建 Scripture 节点（MERGE）并建立 Concept→SUPPORTED_BY→Scripture 关系。
        成功返回 True，失败或不可用返回 False。
        """
        if not self._available or self._driver is None:
            return False
        concept = concept_name.strip()
        sid = id.strip()
        if not concept or not sid:
            return False
        try:
            with self._driver.session() as session:
                session.run(
                    "MERGE (s:Scripture {id: $sid}) "
                    "SET s.text_short = $text_short, s.text_full = $text_full "
                    "WITH s "
                    "MATCH (c:Concept {name: $concept}) "
                    "MERGE (c)-[:SUPPORTED_BY]->(s)",
                    sid=sid,
                    text_short=text_short,
                    text_full=text_full,
                    concept=concept,
                )
                return True
        except Exception as e:
            print(f"[KG-RAG] create_scripture_node 失败: {e}")
            return False

    def get_stats(self) -> dict[str, Any]:
        """图谱统计：available、concept_count、relation_count、relation_types、concept_name_count。"""
        if not self._available or self._driver is None:
            return {
                "available": False,
                "concept_count": 0,
                "relation_count": 0,
                "relation_types": {},
                "concept_name_count": 0,
            }
        try:
            with self._driver.session() as session:
                r1 = session.run("MATCH (c:Concept) RETURN count(c) AS concept_count")
                concept_count = 0
                rec = r1.single()
                if rec and rec["concept_count"] is not None:
                    concept_count = int(rec["concept_count"])

                r2 = session.run(
                    "MATCH ()-[r]-() RETURN type(r) AS rel_type, count(r) AS cnt"
                )
                relation_count = 0
                relation_types = {}
                for record in r2:
                    t = record.get("rel_type")
                    c = record.get("cnt") or 0
                    if t is not None:
                        relation_types[str(t)] = int(c)
                        relation_count += int(c)

                return {
                    "available": True,
                    "concept_count": concept_count,
                    "relation_count": relation_count,
                    "relation_types": relation_types,
                    "concept_name_count": len(self._concept_names),
                }
        except Exception as e:
            print(f"[KG-RAG] get_stats 失败: {e}")
            return {
                "available": False,
                "concept_count": 0,
                "relation_count": 0,
                "relation_types": {},
                "concept_name_count": len(self._concept_names),
            }
