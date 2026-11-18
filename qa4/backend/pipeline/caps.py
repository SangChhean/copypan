# -*- coding: utf-8 -*-
"""第 5 步各层上限与截断。

截断顺序【暂定】：先裁「上限最小的层」里排最后的词；上限相同时取层序靠后的层。
拆了子问题：第 2–5 层整题合计 ≤ complex_total_cap，每个子问题至少保留 complex_min_per_subquestion 个词。
比较类：永远不删某个对象在第 2–5 层仅剩的最后一个词（protect_last_for 映射词→对象）。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

from pipeline.schemas import Layers

LAYERS = ("revelation", "intrinsic", "experience", "practice")


@lru_cache(maxsize=1)
def caps_cfg() -> dict[str, Any]:
    from config import load_config_json

    return load_config_json("step5_caps.json")


def caps_for(qtype: str, cfg: dict[str, Any] | None = None) -> dict[str, int]:
    cfg = cfg or caps_cfg()
    c = (cfg.get("caps") or {}).get(qtype) or (cfg.get("caps") or {}).get("默认") or {}
    return {k: int(c.get(k, 0)) for k in (*LAYERS, "total")}


def _pick_layer(layers: Layers, caps: dict[str, int]) -> str | None:
    nonempty = [ln for ln in LAYERS if getattr(layers, ln)]
    if not nonempty:
        return None
    return sorted(nonempty, key=lambda ln: (caps.get(ln, 0), -LAYERS.index(ln)))[0]


def _object_counts(layers: Layers, object_of: dict[str, str], objects: list[str]) -> dict[str, int]:
    counts = {o: 0 for o in objects}
    for w in layers.recommended():
        o = object_of.get(w)
        if o in counts:
            counts[o] += 1
    return counts


def _can_pop(layers: Layers, ln: str, object_of: dict[str, str], objects: list[str]) -> bool:
    """若弹出该层最后一个词会让某对象在第 2–5 层归零，则不可弹。"""
    arr = getattr(layers, ln)
    if not arr:
        return False
    if not objects:
        return True
    w = arr[-1]
    o = object_of.get(w)
    if not o or o not in objects:
        return True
    counts = _object_counts(layers, object_of, objects)
    return counts.get(o, 0) > 1


def truncate_layers(
    layers: Layers,
    caps: dict[str, int],
    *,
    total_cap: int | None = None,
    min_keep: int = 0,
    object_of: Optional[dict[str, str]] = None,
    protect_objects: Optional[list[str]] = None,
) -> Layers:
    """先按各层上限截，再按合计上限裁；比较类保护各对象在 2–5 层至少留 1 词。"""
    out = layers.model_copy(deep=True)
    obj_of = dict(object_of or out.object_of or {})
    objs = list(protect_objects or [])

    def _ensure_objects_in_layer(full: list[str], capped: list[str], cap: int) -> list[str]:
        """层上限切片后，若某对象在本层原有词却被切光，挤回其最后一个词。"""
        if not objs or cap <= 0:
            return capped
        kept = list(capped)
        for o in objs:
            full_for_o = [w for w in full if obj_of.get(w) == o]
            if not full_for_o:
                continue
            if any(obj_of.get(w) == o for w in kept):
                continue
            w = full_for_o[-1]
            if len(kept) < cap:
                kept.append(w)
            else:
                # 挤掉一个非该对象、且挤掉后其对象仍有其它词（或无对象标注）的词
                for i in range(len(kept) - 1, -1, -1):
                    ow = obj_of.get(kept[i])
                    if ow == o:
                        continue
                    if ow and ow in objs:
                        others = sum(1 for x in kept if obj_of.get(x) == ow) - 1
                        if others < 1:
                            continue
                    kept[i] = w
                    break
                else:
                    kept[-1] = w
        return kept[:cap]

    for ln in LAYERS:
        full = list(getattr(out, ln))
        cap = max(0, caps.get(ln, 0))
        capped = full[:cap]
        setattr(out, ln, _ensure_objects_in_layer(full, capped, cap))
    limit = caps.get("total", 0) if total_cap is None else total_cap
    while out.total_2_5() > max(limit, min_keep):
        # 找可弹的层：优先上限最小；若该层末词受保护则换一层
        candidates = [ln for ln in LAYERS if getattr(out, ln)]
        if not candidates:
            break
        ordered = sorted(candidates, key=lambda ln: (caps.get(ln, 0), -LAYERS.index(ln)))
        popped = False
        for ln in ordered:
            if _can_pop(out, ln, obj_of, objs):
                getattr(out, ln).pop()
                popped = True
                break
        if not popped:
            break
    out.object_of = {w: obj_of[w] for w in out.recommended() if w in obj_of}
    return out


def truncate_complex(
    all_layers: list[Layers],
    caps_list: list[dict[str, int]],
    *,
    total_cap: int,
    min_per: int,
    object_ofs: Optional[list[dict[str, str]]] = None,
    protect_objects_list: Optional[list[list[str]]] = None,
) -> list[Layers]:
    object_ofs = object_ofs or [{} for _ in all_layers]
    protect_objects_list = protect_objects_list or [[] for _ in all_layers]
    out = [
        truncate_layers(l, c, object_of=of, protect_objects=po)
        for l, c, of, po in zip(all_layers, caps_list, object_ofs, protect_objects_list)
    ]
    while sum(l.total_2_5() for l in out) > total_cap:
        cand = [(i, l) for i, l in enumerate(out) if l.total_2_5() > min_per]
        if not cand:
            break
        i, l = max(cand, key=lambda x: (x[1].total_2_5(), x[0]))
        objs = protect_objects_list[i]
        of = object_ofs[i]
        ordered = sorted(
            [ln for ln in LAYERS if getattr(l, ln)],
            key=lambda ln: (caps_list[i].get(ln, 0), -LAYERS.index(ln)),
        )
        popped = False
        for ln in ordered:
            if _can_pop(l, ln, of, objs):
                getattr(l, ln).pop()
                popped = True
                break
        if not popped:
            # 无法在不伤对象覆盖的前提下再裁，停止
            break
        out[i].object_of = {w: of[w] for w in out[i].recommended() if w in of}
    return out
