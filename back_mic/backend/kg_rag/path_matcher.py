# -*- coding: utf-8 -*-
"""Step 1.5 路径匹配：将 Step 1 抽取的概念与黄金路径匹配。"""
import logging

from kg_rag.golden_paths import get_golden_paths, get_paths_for_nodes

logger = logging.getLogger("kg_rag")


def match_golden_paths(
    concept_names: list[str],
    threshold: int = 2,
) -> dict:
    """将概念列表与黄金路径匹配，返回命中数最高且 >= threshold 的一条作为强相关。

    返回格式: {"strong": {..., "hit_count": N} | None}
    """
    if not concept_names:
        return {"strong": None}

    node_map = get_paths_for_nodes(concept_names)
    if not node_map:
        return {"strong": None}

    all_paths = get_golden_paths()
    if not all_paths:
        return {"strong": None}

    path_by_id = {str(p["id"]): p for p in all_paths}

    hit_counts: dict[str, int] = {}
    for _concept, path_ids in node_map.items():
        for pid in path_ids:
            hit_counts[pid] = hit_counts.get(pid, 0) + 1

    best_id: str | None = None
    best_count = 0
    for pid, count in hit_counts.items():
        if count >= threshold and count > best_count:
            best_count = count
            best_id = pid

    if best_id is None or best_id not in path_by_id:
        logger.info(
            "[KG-RAG] Step1.5 golden_path: no match >= threshold=%s (top hit_count=%s)",
            threshold, max(hit_counts.values()) if hit_counts else 0,
        )
        return {"strong": None}

    path = path_by_id[best_id]
    logger.info(
        "[KG-RAG] Step1.5 golden_path: matched id=%s name=%r hit_count=%s/%s threshold=%s",
        best_id, path.get("name"), best_count, len(path.get("nodes", [])), threshold,
    )
    return {
        "strong": {
            "id": path["id"],
            "name": path["name"],
            "nodes": path["nodes"],
            "hit_count": best_count,
        }
    }
