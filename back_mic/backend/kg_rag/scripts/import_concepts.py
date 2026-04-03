# -*- coding: utf-8 -*-
"""从 JSON 导入 Concept 节点与关系到 Neo4j（支持增量与可选清空）。"""
import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv

ALLOWED_RELATIONSHIP_TYPES = {
    "CONTAINS",
    "TYPIFIES",
    "OPPOSES",
    "LEADS_TO",
    "GOALS_FOR",
    "CORRESPONDS_TO",
    "EXPERIENCES",
    "PRACTICED_AS",
    "LOCATED_IN",
}


def _normalize_aliases(aliases: object) -> list[str]:
    """将 aliases 规范化为去重后的字符串列表。"""
    if not isinstance(aliases, list):
        return []
    out = []
    seen = set()
    for item in aliases:
        if item is None:
            continue
        s = str(item).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _create_driver(uri: str, user: str, password: str):
    """创建 Neo4j driver 并验证连接。"""
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    return driver


def _clear_all(session) -> bool:
    """按确认逻辑清空全部 Concept 节点与关系。"""
    confirm = input("确认要清空所有 Concept 节点和关系吗？(输入 yes 确认): ")
    if confirm.strip().lower() != "yes":
        print("已取消")
        return False
    try:
        session.run("MATCH (c:Concept) DETACH DELETE c")
        print("已清空所有 Concept 节点和关系")
        return True
    except Exception as e:
        print(f"[KG-RAG] 清空失败: {e}")
        return False


def import_concepts(session, concepts: list[dict]) -> tuple[int, int, int]:
    """导入 Concept 节点，返回 (created, updated, failed)。"""
    created = 0
    updated = 0
    failed = 0
    for idx, item in enumerate(concepts, start=1):
        try:
            name = str(item.get("name", "")).strip()
            aliases = _normalize_aliases(item.get("aliases", []))
            if not name:
                failed += 1
                print(f"[KG-RAG] Concept#{idx} 跳过：name 为空")
                continue

            rec = session.run(
                """
                OPTIONAL MATCH (c0:Concept {name: $name})
                WITH c0, c0 IS NOT NULL AS existed
                MERGE (c:Concept {name: $name})
                SET c.aliases = $aliases
                RETURN existed
                """,
                name=name,
                aliases=aliases,
            ).single()
            existed = bool(rec and rec.get("existed"))
            if existed:
                updated += 1
                print(f"[KG-RAG] Concept Updated: {name}")
            else:
                created += 1
                print(f"[KG-RAG] Concept Created: {name}")
        except Exception as e:
            failed += 1
            print(f"[KG-RAG] Concept 导入失败#{idx}: {e}")
    return created, updated, failed


def import_relations(session, relations: list[dict]) -> tuple[int, int]:
    """导入关系，返回 (created, skipped)。"""
    created = 0
    skipped = 0
    for idx, item in enumerate(relations, start=1):
        try:
            from_name = str(item.get("from", "")).strip()
            to_name = str(item.get("to", "")).strip()
            rel_type = str(item.get("type", "")).strip().upper()

            if not from_name or not to_name:
                skipped += 1
                print(f"[KG-RAG] Relation#{idx} 跳过：from/to 为空")
                continue
            if rel_type not in ALLOWED_RELATIONSHIP_TYPES:
                skipped += 1
                print(f"[KG-RAG] 跳过未知关系类型: {rel_type}")
                continue

            check = session.run(
                """
                MATCH (a:Concept {name: $from_name})
                MATCH (b:Concept {name: $to_name})
                RETURN count(a) > 0 AS has_a, count(b) > 0 AS has_b
                """,
                from_name=from_name,
                to_name=to_name,
            ).single()
            has_a = bool(check and check.get("has_a"))
            has_b = bool(check and check.get("has_b"))
            if not has_a or not has_b:
                skipped += 1
                print(f"[KG-RAG] Relation#{idx} 跳过：节点不存在 ({from_name} -> {to_name})")
                continue

            exists_query = f"""
            MATCH (a:Concept {{name: $from_name}})
            MATCH (b:Concept {{name: $to_name}})
            OPTIONAL MATCH (a)-[r:{rel_type}]->(b)
            RETURN count(r) > 0 AS existed
            """
            existed_rec = session.run(
                exists_query, from_name=from_name, to_name=to_name
            ).single()
            existed = bool(existed_rec and existed_rec.get("existed"))
            if existed:
                skipped += 1
                print(f"[KG-RAG] Relation Skipped(已存在): {from_name}-[{rel_type}]->{to_name}")
                continue

            create_query = f"""
            MATCH (a:Concept {{name: $from_name}})
            MATCH (b:Concept {{name: $to_name}})
            MERGE (a)-[r:{rel_type}]->(b)
            RETURN type(r) AS rel_type
            """
            session.run(create_query, from_name=from_name, to_name=to_name).single()
            created += 1
            print(f"[KG-RAG] Relation Created: {from_name}-[{rel_type}]->{to_name}")
        except Exception as e:
            skipped += 1
            print(f"[KG-RAG] Relation 导入失败#{idx}: {e}")
    return created, skipped


def get_graph_counts(session) -> tuple[int, int]:
    """返回当前图谱 Concept 节点数与关系数。"""
    try:
        node_count = session.run(
            "MATCH (c:Concept) RETURN count(c) AS cnt"
        ).single()
        rel_count = session.run(
            "MATCH (:Concept)-[r]->(:Concept) RETURN count(r) AS cnt"
        ).single()
        return int(node_count["cnt"] if node_count else 0), int(rel_count["cnt"] if rel_count else 0)
    except Exception as e:
        print(f"[KG-RAG] 统计图谱数量失败: {e}")
        return 0, 0


def main() -> None:
    """命令行入口：读取 JSON，执行可选清空，然后导入节点与关系并打印统计。"""
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="KG-RAG 种子概念导入（Neo4j）"
    )
    parser.add_argument(
        "--input",
        type=str,
        required=True,
        help="输入 JSON 文件路径（必填）",
    )
    parser.add_argument(
        "--neo4j-uri",
        type=str,
        default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        help="Neo4j URI（默认 NEO4J_URI 或 bolt://localhost:7687）",
    )
    parser.add_argument(
        "--neo4j-user",
        type=str,
        default=os.environ.get("NEO4J_USER", "neo4j"),
        help="Neo4j 用户名（默认 NEO4J_USER 或 neo4j）",
    )
    parser.add_argument(
        "--neo4j-password",
        type=str,
        default=os.environ.get("NEO4J_PASSWORD", ""),
        help="Neo4j 密码（默认 NEO4J_PASSWORD 或空）",
    )
    parser.add_argument(
        "--clear",
        action="store_true",
        help="导入前清空所有 Concept 节点和关系（危险操作）",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"输入文件不存在: {input_path}")

    try:
        data = json.loads(input_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise SystemExit(f"读取 JSON 失败: {e}") from e

    concepts = data.get("concepts", [])
    relations = data.get("relations", [])
    if not isinstance(concepts, list) or not isinstance(relations, list):
        raise SystemExit("输入 JSON 格式错误：concepts/relations 必须是数组")

    driver = None
    try:
        driver = _create_driver(args.neo4j_uri, args.neo4j_user, args.neo4j_password)
    except Exception as e:
        raise SystemExit(f"Neo4j 连接失败: {e}") from e

    try:
        with driver.session() as session:
            if args.clear:
                ok = _clear_all(session)
                if not ok:
                    return

            concept_created, concept_updated, concept_failed = import_concepts(session, concepts)
            rel_created, rel_skipped = import_relations(session, relations)
            total_nodes, total_rels = get_graph_counts(session)

            print("\n统计：")
            print(f"  概念：新建 {concept_created}，更新 {concept_updated}，失败 {concept_failed}")
            print(f"  关系：新建 {rel_created}，跳过 {rel_skipped}")
            print(f"  当前图谱总节点数: {total_nodes}")
            print(f"  当前图谱总关系数: {total_rels}")
            print("导入完成。请重启后端服务以刷新概念词表缓存，或调用 /api/kg_rag/health 触发刷新。")
    except Exception as e:
        raise SystemExit(f"导入失败: {e}") from e
    finally:
        try:
            if driver is not None:
                driver.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
