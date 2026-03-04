# -*- coding: utf-8 -*-
"""
RRF（Reciprocal Rank Fusion）融合与索引加权。
纯函数，无 IO，无异步，仅用标准库。
"""

# cwwl 年份/范围判断（与 ai_service 中 _CWWL_EXTRA_WEIGHT_PATTERNS_实行 一致）
CWWL_94_97 = "cwwl_1994-1997"
CWWL_EXTRA_WEIGHT_PATTERNS_实行 = (
    "cwwl_1985",
    "cwwl_1986",
    "cwwl_1987",
    "cwwl_1988",
    "cwwl_1989",
    "cwwl_1990",
    "cwwl_1991-92",
    "cwwl_1993",
)

# 纲目型 chunks 索引 → 父索引（用于加权时按父索引查表）
MAP_CHUNK_TO_PARENT = {
    "map_note_chunks": "map_note",
    "map_7feasts_chunks": "map_7feasts",
    "map_pano_chunks": "map_pano",
    "map_dictionary_chunks": "map_dictionary",
}


def _dedup_key(doc: dict) -> str:
    """去重键：有 chunk_id 用 chunk_id，否则用 _id。"""
    if doc.get("chunk_id") is not None:
        return str(doc["chunk_id"])
    return str(doc.get("_id", ""))


def rrf_merge(
    ranked_lists: list[list[dict]],
    k: int = 60,
    top_n: int = 60,
) -> list[dict]:
    """
    RRF 融合多个已排序列表，去重后按 RRF 分降序取前 top_n 条。
    score(d) = Σ 1/(k + rank_i(d))，rank 从 1 开始。
    返回的每条 dict 在原字段基础上附加 "rrf_score" 字段。
    """
    if not ranked_lists or top_n <= 0:
        return []
    # key -> (doc, rrf_score)
    scores: dict[str, tuple[dict, float]] = {}
    for lst in ranked_lists:
        for rank, doc in enumerate(lst, start=1):
            if not isinstance(doc, dict):
                continue
            key = _dedup_key(doc)
            add = 1.0 / (k + rank)
            if key in scores:
                prev_doc, prev_score = scores[key]
                scores[key] = (prev_doc, prev_score + add)
            else:
                # 复制一份，避免修改原 dict
                new_doc = dict(doc)
                new_doc["rrf_score"] = add
                scores[key] = (new_doc, add)
    # 统一写入 rrf_score（上面首次出现时已写，合并时只加了分数，需再写一次）
    out = []
    for key, (doc, score) in scores.items():
        doc["rrf_score"] = score
        out.append(doc)
    out.sort(key=lambda d: d["rrf_score"], reverse=True)
    return out[:top_n]


def _effective_index(doc: dict) -> str:
    """加权用索引：纲目型取父索引，其余取 _index。"""
    idx = doc.get("_index") or ""
    return MAP_CHUNK_TO_PARENT.get(idx, idx)


def _weight_multiplier(special_needs: str, effective_index: str, doc_id: str) -> float:
    """根据 special_needs 与索引、doc_id 返回权重系数。"""
    if special_needs == "一般性":
        if effective_index == "cwwl" and CWWL_94_97 in doc_id:
            return 1.1
        return 1.0
    if special_needs == "高真理浓度":
        if effective_index == "cwwl" and CWWL_94_97 in doc_id:
            return 1.5
        return 1.0
    if special_needs == "高生命浓度":
        if effective_index in ("cwwn", "life"):
            return 1.5
        return 1.0
    if special_needs == "重实行应用":
        if effective_index == "cwwl" and any(p in doc_id for p in CWWL_EXTRA_WEIGHT_PATTERNS_实行):
            return 1.5
        return 1.0
    return 1.0


def apply_index_weight(
    docs: list[dict],
    special_needs: str,
    top_n: int,
) -> list[dict]:
    """
    按 special_needs 对文档加权后重排，取前 top_n 条。
    每条附加 "weighted_score" 字段（原 rrf_score × 系数）。
    纲目型按父索引套用与段落型相同的规则。
    """
    if not docs or top_n <= 0:
        return []
    out = []
    for d in docs:
        doc = dict(d)
        base = float(doc.get("rrf_score") or 0.0)
        eff_idx = _effective_index(doc)
        doc_id = str(doc.get("_id") or "")
        w = _weight_multiplier(special_needs, eff_idx, doc_id)
        doc["weighted_score"] = base * w
        out.append(doc)
    out.sort(key=lambda x: x["weighted_score"], reverse=True)
    return out[:top_n]
