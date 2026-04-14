# -*- coding: utf-8 -*-
"""读取 seed_scriptures.json，将 Scripture 节点和 SUPPORTED_BY 关系写入 Neo4j。

每个概念：
  1. MERGE Scripture 节点（id 唯一键，设 text 属性）
  2. MATCH Concept → MERGE SUPPORTED_BY 关系
  3. 若 greek_terms 非空，SET Concept.greek_terms 属性
"""
import argparse
import json
import os
from pathlib import Path

from dotenv import load_dotenv


def _create_driver(uri: str, user: str, password: str):
    from neo4j import GraphDatabase

    driver = GraphDatabase.driver(uri, auth=(user, password))
    driver.verify_connectivity()
    return driver


def import_one(session, item: dict, *, dry_run: bool = False) -> None:
    concept = str(item.get("concept", "")).strip()
    greek_terms = item.get("greek_terms") or []
    scriptures = item.get("scriptures") or []

    if not concept:
        print("  [跳过] concept 为空")
        return

    # 检查 Concept 节点是否存在
    rec = session.run(
        "MATCH (c:Concept {name: $name}) RETURN count(c) AS cnt",
        name=concept,
    ).single()
    concept_exists = bool(rec and rec["cnt"] > 0)

    if not concept_exists:
        print(f"  ⚠ 概念节点不存在: {concept}（经文仍将创建，但关系无法建立）")

    if dry_run:
        print(
            f"  [dry-run] {concept}  "
            f"concept_exists={concept_exists}  "
            f"scriptures={len(scriptures)}  "
            f"greek_terms={len(greek_terms)}"
        )
        return

    for sc in scriptures:
        sid = str(sc.get("id", "")).strip()
        text = str(sc.get("text", "")).strip()
        if not sid:
            continue
        session.run(
            "MERGE (s:Scripture {id: $sid}) SET s.text = $text",
            sid=sid,
            text=text,
        )
        if concept_exists:
            session.run(
                "MATCH (c:Concept {name: $concept}) "
                "MATCH (s:Scripture {id: $sid}) "
                "MERGE (c)-[:SUPPORTED_BY]->(s)",
                concept=concept,
                sid=sid,
            )

    if greek_terms and concept_exists:
        session.run(
            "MATCH (c:Concept {name: $concept}) SET c.greek_terms = $terms",
            concept=concept,
            terms=greek_terms,
        )

    print(
        f"  ✓ {concept}  "
        f"scriptures={len(scriptures)}  "
        f"greek_terms={len(greek_terms)}  "
        f"concept_exists={concept_exists}"
    )


def main() -> None:
    load_dotenv()

    parser = argparse.ArgumentParser(description="导入 seed_scriptures.json 到 Neo4j")
    parser.add_argument("--input", type=str, default="seed_scriptures.json", help="输入 JSON 路径")
    parser.add_argument("--dry-run", action="store_true", help="只打印不写入")
    parser.add_argument(
        "--neo4j-uri", type=str,
        default=os.environ.get("NEO4J_URI", "bolt://localhost:7687"),
    )
    parser.add_argument(
        "--neo4j-user", type=str,
        default=os.environ.get("NEO4J_USER", "neo4j"),
    )
    parser.add_argument(
        "--neo4j-password", type=str,
        default=os.environ.get("NEO4J_PASSWORD", ""),
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        raise SystemExit(f"输入文件不存在: {input_path}")

    data = json.loads(input_path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise SystemExit("JSON 格式错误：顶层应为数组")

    print(f"共 {len(data)} 个概念条目，dry_run={args.dry_run}\n")

    if args.dry_run:
        driver = None
        try:
            driver = _create_driver(args.neo4j_uri, args.neo4j_user, args.neo4j_password)
        except Exception as e:
            print(f"Neo4j 连接失败（dry-run 将跳过节点存在性检查）: {e}")

        if driver:
            with driver.session() as session:
                for item in data:
                    import_one(session, item, dry_run=True)
            driver.close()
        else:
            for item in data:
                concept = str(item.get("concept", "")).strip()
                scriptures = item.get("scriptures") or []
                greek_terms = item.get("greek_terms") or []
                print(
                    f"  [dry-run/offline] {concept}  "
                    f"scriptures={len(scriptures)}  "
                    f"greek_terms={len(greek_terms)}"
                )
    else:
        try:
            driver = _create_driver(args.neo4j_uri, args.neo4j_user, args.neo4j_password)
        except Exception as e:
            raise SystemExit(f"Neo4j 连接失败: {e}") from e

        with driver.session() as session:
            for item in data:
                import_one(session, item, dry_run=False)
        driver.close()

    print("\n完成。")


if __name__ == "__main__":
    main()
