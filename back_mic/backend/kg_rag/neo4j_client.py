# -*- coding: utf-8 -*-
"""Neo4j 连接、Hash 表加载与图谱查询。"""
import os
from typing import Any

# 环境变量，合理默认
NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "")

# 跳数范围，用于 Cypher [*..N] 拼接前校验
MIN_HOPS, MAX_HOPS = 1, 5


class Neo4jClient:
    """Neo4j 图谱客户端，管理连接、Hash 表和图谱查询。

    核心原则：图谱是增强层而非前置依赖。
    Neo4j 不可用或图谱为空时，所有方法返回空结果，不抛异常，
    让流水线自然降级为纯双路 RAG。
    """

    def __init__(self) -> None:
        self._uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        self._user = os.environ.get("NEO4J_USER", "neo4j")
        self._password = os.environ.get("NEO4J_PASSWORD", "")
        self._driver = None
        self._hash_table: dict[str, str] = {}
        self._available: bool = False

    def startup(self) -> None:
        """尝试连接 Neo4j；成功则刷新 Hash 表，失败则不抛异常并设 _available=False。同步方法，供 FastAPI 启动或 get_service 时调用。"""
        try:
            from neo4j import GraphDatabase
            driver = GraphDatabase.driver(
                self._uri,
                auth=(self._user, self._password),
            )
            driver.verify_connectivity()
            self._driver = driver
            self._available = True
            self.refresh_hash_table()
        except Exception as e:
            print(f"[KG-RAG] Neo4j 连接失败，图谱功能将降级为空: {e}")
            self._available = False
            self._hash_table = {}
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

    def refresh_hash_table(self) -> None:
        """从 Neo4j 查询所有 Concept 的 name/aliases，构建 name/alias → 标准 name 的 Hash 表。"""
        if not self._available or self._driver is None:
            return
        try:
            with self._driver.session() as session:
                result = session.run(
                    "MATCH (c:Concept) RETURN c.name AS name, c.aliases AS aliases"
                )
                self._hash_table = {}
                n_concepts = 0
                for record in result:
                    name = record.get("name")
                    aliases = record.get("aliases") or []
                    if name is None:
                        continue
                    name_str = str(name).strip()
                    if not name_str:
                        continue
                    n_concepts += 1
                    self._hash_table[name_str] = name_str
                    for a in aliases:
                        if a is not None:
                            alias_str = str(a).strip()
                            if alias_str:
                                self._hash_table[alias_str] = name_str
                print(f"[KG-RAG] Hash 表已加载: {len(self._hash_table)} 个映射条目（{n_concepts} 个概念节点）")
        except Exception as e:
            print(f"[KG-RAG] 加载 Hash 表失败: {e}")
            self._hash_table = {}

    def normalize_concepts(self, terms: list[str]) -> list[str]:
        """Step 1.5 概念规范化：对每个 term 查 Hash 表，命中转为标准 name，未命中丢弃；返回去重列表。不访问 Neo4j。"""
        if not self._hash_table:
            return []
        out = []
        seen = set()
        for t in terms:
            if not t or not isinstance(t, str):
                continue
            key = t.strip()
            if not key:
                continue
            standard = self._hash_table.get(key)
            if standard is not None and standard not in seen:
                seen.add(standard)
                out.append(standard)
        return out

    def get_neighbors(self, concept_name: str) -> list[dict[str, Any]]:
        """单概念 1 跳全部邻居，出边和入边分别查询后按 neighbor 合并去重。
        每条记录包含：neighbor, relations（带方向的关系字符串列表）, relation_type（首条，供 by_name 使用）
        """
        if not self._available or self._driver is None:
            return []
        key = concept_name.strip()
        try:
            with self._driver.session() as session:
                # 出边：key → neighbor
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
                    for r in out_result if r["neighbor"]
                ]
                # 入边：neighbor → key
                in_result = session.run(
                    "MATCH (c:Concept {name: $name})<-[r]-(related:Concept) "
                    "RETURN related.name AS neighbor, type(r) AS relation_type",
                    name=key,
                )
                in_rows = [
                    {
                        "neighbor": r["neighbor"],
                        "relation_type": r["relation_type"],
                        "relation_str": f"{r['neighbor']} ──{r['relation_type']}──► {key}",
                    }
                    for r in in_result if r["neighbor"]
                ]
                # 按 neighbor 合并去重
                merged: dict[str, dict] = {}
                for row in out_rows + in_rows:
                    nb = row["neighbor"]
                    if nb not in merged:
                        merged[nb] = {
                            "neighbor": nb,
                            "relation_type": row["relation_type"],
                            "relations": [row["relation_str"]],
                        }
                    else:
                        if row["relation_str"] not in merged[nb]["relations"]:
                            merged[nb]["relations"].append(row["relation_str"])
                return list(merged.values())
        except Exception as e:
            print(f"[KG-RAG] get_neighbors 失败: {e}")
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
        """两概念间 max_hops 内全部路径，返回 [{\"path_nodes\": [...], \"relations\": [...]}, ...]。"""
        if not self._available or self._driver is None:
            return []
        n = self._clamp_hops(max_hops)
        try:
            with self._driver.session() as session:
                query = (
                    f"MATCH path = (a:Concept {{name: $n1}})-[*..{n}]-(b:Concept {{name: $n2}}) "
                    "RETURN [n IN nodes(path) | n.name] AS path_nodes, "
                    "[r IN relationships(path) | type(r)] AS relations"
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
        """shortestPath 查询，返回单条路径 dict 或 None。"""
        if not self._available or self._driver is None:
            return None
        n = self._clamp_hops(max_hops)
        try:
            with self._driver.session() as session:
                query = (
                    f"MATCH path = shortestPath((a:Concept {{name: $n1}})-[*..{n}]-(b:Concept {{name: $n2}})) "
                    "RETURN [n IN nodes(path) | n.name] AS path_nodes, "
                    "[r IN relationships(path) | type(r)] AS relations"
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

    def get_stats(self) -> dict[str, Any]:
        """图谱统计：available、concept_count、relation_count、relation_types、hash_table_size。"""
        if not self._available or self._driver is None:
            return {
                "available": False,
                "concept_count": 0,
                "relation_count": 0,
                "relation_types": {},
                "hash_table_size": 0,
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
                    "hash_table_size": len(self._hash_table),
                }
        except Exception as e:
            print(f"[KG-RAG] get_stats 失败: {e}")
            return {
                "available": False,
                "concept_count": 0,
                "relation_count": 0,
                "relation_types": {},
                "hash_table_size": len(self._hash_table),
            }
