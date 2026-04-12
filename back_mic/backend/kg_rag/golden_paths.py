# -*- coding: utf-8 -*-
"""黄金路径：预定义的概念路径加载与查询。"""
import json
import logging
from pathlib import Path

logger = logging.getLogger("kg_rag")

_backend_dir = Path(__file__).resolve().parents[1]
_golden_paths_path = _backend_dir / "golden_paths.json"

_golden_paths: list[dict] = []
_nodes_to_paths: dict[str, list[str]] = {}


def load_golden_paths() -> None:
    """启动时加载 golden_paths.json，构建路径列表和反向索引。"""
    global _golden_paths, _nodes_to_paths
    _golden_paths = []
    _nodes_to_paths = {}

    if not _golden_paths_path.is_file():
        logger.warning("[golden_paths] missing %s", _golden_paths_path)
        return

    try:
        with open(_golden_paths_path, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception as e:
        logger.warning("[golden_paths] failed to parse JSON: %s", e)
        return

    if not isinstance(raw, list):
        logger.warning("[golden_paths] expected list, got %s", type(raw).__name__)
        return

    for item in raw:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id", "")).strip()
        name = str(item.get("name", "")).strip()
        nodes = item.get("nodes", [])
        if not pid or not isinstance(nodes, list):
            continue
        _golden_paths.append({"id": pid, "name": name, "nodes": nodes})
        for node in nodes:
            n = str(node).strip()
            if n:
                _nodes_to_paths.setdefault(n, []).append(pid)

    logger.info("[golden_paths] loaded %s paths, %s node entries",
                len(_golden_paths), len(_nodes_to_paths))


def get_golden_paths() -> list[dict]:
    """返回完整路径列表。"""
    return list(_golden_paths)


def get_paths_for_nodes(concept_names: list[str]) -> dict[str, list[str]]:
    """输入概念名列表，返回每个概念出现在哪些路径上。"""
    out: dict[str, list[str]] = {}
    for name in concept_names:
        n = str(name).strip()
        if n and n in _nodes_to_paths:
            out[n] = list(_nodes_to_paths[n])
    return out
