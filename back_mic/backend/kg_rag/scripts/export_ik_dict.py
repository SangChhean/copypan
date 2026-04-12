# -*- coding: utf-8 -*-
"""从 Neo4j Concept 节点导出 name 为 IK 自定义词典文件。"""
import argparse
import os
from pathlib import Path


def export_from_neo4j(driver) -> tuple[list[str], int]:
    """
    从 Neo4j 查询所有 Concept 的 name，去重、过滤空值、排序后返回 (词条列表, Concept 节点数)。
    空图谱或查询失败时返回 ([], 0)。
    """
    try:
        with driver.session() as session:
            result = session.run(
                "MATCH (c:Concept) RETURN c.name AS name"
            )
            words = set()
            concept_count = 0
            for record in result:
                name = record.get("name")
                if name is not None:
                    s = str(name).strip()
                    if s:
                        words.add(s)
                        concept_count += 1
            return (sorted(words), concept_count)
    except Exception as e:
        print(f"[KG-RAG] export_from_neo4j 查询失败: {e}")
        return ([], 0)


def main() -> None:
    """入口：连接 Neo4j、取词、写入词典文件。连接失败或空图谱时导出空文件并正常退出。"""
    parser = argparse.ArgumentParser(
        description="Neo4j Concept name → IK 自定义词典文件"
    )
    parser.add_argument(
        "--output",
        type=str,
        required=True,
        help="输出词典文件路径（.dic 或 .txt，必填）",
    )
    parser.add_argument(
        "--neo4j-uri",
        type=str,
        default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
        help="Neo4j 地址（默认从 NEO4J_URI 或 bolt://localhost:7687）",
    )
    parser.add_argument(
        "--neo4j-user",
        type=str,
        default=os.environ.get("NEO4J_USER", "neo4j"),
        help="Neo4j 用户名（默认从 NEO4J_USER 或 neo4j）",
    )
    parser.add_argument(
        "--neo4j-password",
        type=str,
        default=os.environ.get("NEO4J_PASSWORD", ""),
        help="Neo4j 密码（默认从 NEO4J_PASSWORD 或空）",
    )
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    driver = None
    try:
        from neo4j import GraphDatabase
        driver = GraphDatabase.driver(
            args.neo4j_uri,
            auth=(args.neo4j_user, args.neo4j_password),
        )
        driver.verify_connectivity()
    except Exception as e:
        print(f"[KG-RAG] Neo4j 连接失败: {e}")
        print("[KG-RAG] 已导出空词典文件，ES 可正常运行（无自定义分词增强）。")
        with open(output_path, "w", encoding="utf-8") as f:
            pass
        print("统计：")
        print("  Concept 节点数: 0")
        print("  导出词条数（去重）: 0")
        print(f"  输出文件: {output_path.resolve()}")
        return

    try:
        words, concept_count = export_from_neo4j(driver)
    finally:
        try:
            driver.close()
        except Exception:
            pass

    if not words:
        print("[KG-RAG] 图谱为空，已导出空词典文件。")
        with open(output_path, "w", encoding="utf-8") as f:
            pass
    else:
        with open(output_path, "w", encoding="utf-8") as f:
            for w in words:
                f.write(w + "\n")

    print("统计：")
    print(f"  Concept 节点数: {concept_count}")
    print(f"  导出词条数（去重）: {len(words)}")
    print(f"  输出文件: {output_path.resolve()}")


if __name__ == "__main__":
    main()
