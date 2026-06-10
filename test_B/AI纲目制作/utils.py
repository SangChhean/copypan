import json
import re
from typing import Any, Optional, Callable

def _extract_cwwl_year(chunk_id: str) -> int | None:
    """从 cwwl chunk_id 提取年份。格式：cwwl_{年份}-{册号}-{书序号}#{章号}-{段序号}"""
    if not chunk_id.startswith("cwwl_"):
        return None
    try:
        return int(chunk_id.split("_")[1].split("-")[0])
    except (IndexError, ValueError):
        return None


def _is_cwwl_year_range(chunk_id: str, start: int, end: int) -> bool:
    year = _extract_cwwl_year(chunk_id)
    return year is not None and start <= year <= end


OUTLINE_NATURE_WEIGHTS: dict[str, list[tuple[Callable[[str, str], bool], float]]] = {
    "一般性": [
        (lambda idx, cid: _is_cwwl_year_range(cid, 1994, 1997), 1.1),
    ],
    "真理启示": [
        (lambda idx, cid: _is_cwwl_year_range(cid, 1994, 1997), 1.5),
    ],
    "生命经历": [
        (lambda idx, cid: idx in ("kg-rag_cwwn", "kg-rag_life"), 1.5),
    ],
    "应用实行": [
        (lambda idx, cid: _is_cwwl_year_range(cid, 1985, 1993), 1.5),
    ],
}


def _apply_outline_nature_weight(
    results: list[dict],
    outline_nature: str,
    *,
    log_full_list: bool = False,
) -> list[dict]:
    """根据纲目性质对检索结果加权重排序（BM25/Dense/路3 返回后调用；不叠乘，取匹配规则中的最大倍数）。"""
    rules = OUTLINE_NATURE_WEIGHTS.get(outline_nature, [])
    if not results:
        return results
    if not rules:
        for doc in results:
            s = float(doc.get("score", 0) or 0)
            doc["weighted_score"] = s
            doc["weight_multiplier"] = 1.0
        return results

    before_order = [d.get("chunk_id", "?") for d in results] if log_full_list else []

    for doc in results:
        idx = doc.get("_index", "") or ""
        cid = doc.get("chunk_id", "") or ""
        original_score = float(doc.get("score", 0) or 0)
        multiplier = 1.0
        for condition, weight in rules:
            try:
                if condition(idx, cid):
                    multiplier = max(multiplier, float(weight))
            except Exception:
                continue
        doc["weighted_score"] = original_score * multiplier
        doc["weight_multiplier"] = multiplier

    results.sort(key=lambda x: float(x.get("weighted_score", 0) or 0), reverse=True)

    if log_full_list:
        lines = []
        for rank, doc in enumerate(results, 1):
            cid = doc.get("chunk_id", "?")
            idx = doc.get("_index", "?")
            sc = float(doc.get("score", 0) or 0)
            wsc = float(doc.get("weighted_score", 0) or 0)
            mult = float(doc.get("weight_multiplier", 1.0) or 1.0)
            old_rank = before_order.index(cid) + 1 if cid in before_order else "?"
            change = f"({old_rank}→{rank})" if old_rank != rank else "(不变)"
            mult_str = f"×{mult}" if mult != 1.0 else ""
            lines.append(f"  #{rank}{change} {cid} [{idx}] score={sc:.4f} weighted={wsc:.4f} {mult_str}".rstrip())

    return results


def _parse_json_array(text: str) -> list[Any]:
    """从 Claude 返回文本解析 JSON 数组，支持被截断的 JSON 修复。"""
    if not text or not text.strip():
        return []
    s = text.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        s = "\n".join(lines[1:-1] if len(lines) > 2 and lines[-1].strip() == "```" else lines[1:])
    try:
        arr = json.loads(s)
        return arr if isinstance(arr, list) else []
    except json.JSONDecodeError as e:
        last_brace = s.rfind("}")
        if last_brace > 0:
            truncated = s[: last_brace + 1] + "]"
            try:
                arr = json.loads(truncated)
                if isinstance(arr, list):
                    return arr
            except json.JSONDecodeError:
                pass
        return []


def _parse_step1_layers(
    text: str, outline_nature: str = "一般性"
) -> tuple[list[str], list[str], list[str], str]:
    """解析 Step 1 返回的 JSON（含 reasoning、revelation、experience、practice）。reasoning 仅写入 Step1 结果，不传入 Step2。"""
    if not text or not text.strip():
        return ([], [], [], "")
    s = text.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        s = "\n".join(lines[1:-1] if len(lines) > 2 and lines[-1].strip() == "```" else lines[1:])
    obj: Optional[dict] = None
    try:
        parsed = json.loads(s)
        if isinstance(parsed, dict):
            obj = parsed
    except json.JSONDecodeError:
        pass
    if obj is None:
        recovered = _safe_parse_json(s)
        obj = recovered if recovered else None
    if not obj:
        return ([], [], [], "")
    r_raw = obj.get("reasoning", "")
    reasoning = str(r_raw).strip() if r_raw is not None else ""
    revelation_raw = obj.get("revelation", [])
    experience_raw = obj.get("experience", [])
    practice_raw = obj.get("practice", [])
    revelation = [str(x).strip() for x in revelation_raw if str(x).strip()] if isinstance(revelation_raw, list) else []
    experience = [str(x).strip() for x in experience_raw if str(x).strip()] if isinstance(experience_raw, list) else []
    practice = [str(x).strip() for x in practice_raw if str(x).strip()] if isinstance(practice_raw, list) else []
    nature = (outline_nature or "一般性").strip()
    if nature == "真理启示":
        max_rev, max_exp, max_prac = 8, 4, 4
    elif nature == "生命经历":
        max_rev, max_exp, max_prac = 4, 8, 4
    elif nature == "应用实行":
        max_rev, max_exp, max_prac = 4, 4, 8
    else:
        max_rev, max_exp, max_prac = 6, 5, 5

    experience = experience[:max_exp]
    practice = practice[:max_prac]
    max_revelation = min(max_rev, 16 - len(experience) - len(practice))
    revelation = revelation[:max_revelation]
    return (revelation, experience, practice, reasoning)


def _safe_parse_json(text: str) -> dict:
    """尽量稳健地解析 JSON 对象；失败返回空 dict。"""
    if not text or not text.strip():
        return {}
    s = text.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        s = "\n".join(lines[1:-1] if len(lines) > 2 and lines[-1].strip() == "```" else lines[1:])
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError as e:
        last_brace = s.rfind("}")
        if last_brace > 0:
            try:
                obj = json.loads(s[: last_brace + 1])
                return obj if isinstance(obj, dict) else {}
            except json.JSONDecodeError:
                return {}
        return {}


def _parse_burden_generation_output(raw: str) -> dict[str, Any]:
    """解析负担说明 LLM 输出：情境 A（负担说明：）或情境 B（候选一～三）。"""
    text = (raw or "").strip()
    if not text:
        return {"scenario": "B", "candidates": [], "error": "解析失败", "debug": {"reason": "empty_raw"}}
    if "候选一" in text:
        candidates: list[str] = []
        for label in ("候选一", "候选二", "候选三"):
            # 候选一：… 或 候选一（侧重…）：…
            pat = rf"{re.escape(label)}(?:（侧重[^）]*）)?[：:]\s*(.+?)(?=\n\s*候选[一二三]|$)"
            m = re.search(pat, text, re.DOTALL)
            if m:
                candidates.append(re.sub(r"\s+", " ", m.group(1).strip()))
            else:
                candidates.append("")
        if not any(c.strip() for c in candidates):
            return {"scenario": "B", "candidates": [], "error": "解析失败", "debug": {"reason": "b_candidates_all_empty"}}
        while len(candidates) < 3:
            candidates.append("")
        return {
            "scenario": "B",
            "candidates": candidates[:3],
            "debug": {"reason": "matched_b", "candidate_lens": [len(c or "") for c in candidates[:3]]},
        }
    if "负担说明" in text:
        m = re.search(r"负担说明[：:]\s*(.+)", text, re.DOTALL)
        if m:
            # 保留整段，避免只取首行导致前端看起来“被截断”
            line = re.sub(r"\s+", " ", m.group(1).strip())
            if line:
                return {"scenario": "A", "result": line, "debug": {"reason": "matched_a", "result_len": len(line)}}
    return {"scenario": "B", "candidates": [], "error": "解析失败", "debug": {"reason": "no_pattern_matched"}}


def _format_chunk_line(c: dict, max_text: int = 300) -> str:
    """单条段落格式化为一行摘要。"""
    chunk_id = c.get("chunk_id", "")
    book = c.get("book_title", "")
    msg = c.get("message_number", "")
    msg_title = c.get("message_title", "")
    text = (c.get("text") or "").strip()
    header = f"[{chunk_id}] {book}"
    if msg:
        header += f" 第{msg}篇"
    if msg_title:
        header += f" {msg_title}"
    preview = text if len(text) <= max_text else text[:max_text] + "…"
    return f"{header}\n{preview}"


def _build_skeleton_bound_prompt_block(
    skeleton: list[dict],
    expanded_results: list[dict],
    deep: list[str],
    main_results: list[dict],
) -> str:
    """将骨架步骤与 expanded_results 按 deep_indices 绑定，构建结构化的 Prompt 文本块。

    每步输出：
        【第N步】{step}
          支撑段落：
            [段落] ...
    末尾追加补充段落（main_results）。
    """
    used_expanded_ids: set[str] = set()
    sections: list[str] = []

    for idx, sk_item in enumerate(skeleton):
        step_text = sk_item.get("step", "")
        deep_indices = sk_item.get("deep_indices", [])
        target_concepts = {deep[i] for i in deep_indices if 0 <= i < len(deep)}

        bound_chunks = []
        for c in expanded_results:
            if c.get("expanded_from") in target_concepts:
                bound_chunks.append(c)
                used_expanded_ids.add(c.get("chunk_id", ""))

        lines = [f"【第{idx + 1}步】{step_text}"]
        if bound_chunks:
            lines.append("  支撑段落：")
            for c in bound_chunks:
                lines.append(f"    {_format_chunk_line(c)}")
                lines.append("    ---")
        else:
            lines.append("  支撑段落：（无绑定段落）")
        sections.append("\n".join(lines))

    leftover_expanded = [
        c for c in expanded_results if c.get("chunk_id", "") not in used_expanded_ids
    ]

    supplement_lines = ["【补充段落】（来自 BM25 与向量检索，适用于任何大点）"]
    for c in main_results:
        supplement_lines.append(f"  {_format_chunk_line(c)}")
        supplement_lines.append("  ---")
    if leftover_expanded:
        for c in leftover_expanded:
            supplement_lines.append(f"  {_format_chunk_line(c)}")
            supplement_lines.append("  ---")
    sections.append("\n".join(supplement_lines))

    return "\n\n".join(sections)


def _format_paths_text(paths: list[dict]) -> str:
    if not paths:
        return "暂无已知路径"
    lines = []
    for p in paths:
        from_name = p.get("from", "")
        relation = p.get("relation", "")
        to_name = p.get("to", "")
        via = p.get("via")
        hops = p.get("hops", "")
        if via and int(hops or 0) == 2:
            rel_parts = [x.strip() for x in str(relation).split("→")]
            via_name = str(via).strip()
            if len(rel_parts) == 2 and via_name:
                lines.append(
                    f"{from_name} ──{rel_parts[0]}──► {via_name} ──{rel_parts[1]}──► {to_name}"
                )
            else:
                lines.append(f"{from_name} ──{relation}──► {to_name}")
        elif via and int(hops or 0) == 3:
            rel_parts = [x.strip() for x in str(relation).split("→")]
            via_parts = [x.strip() for x in str(via).split("→")]
            if len(rel_parts) == 3 and len(via_parts) == 2:
                lines.append(
                    f"{from_name} ──{rel_parts[0]}──► {via_parts[0]} ──{rel_parts[1]}──► {via_parts[1]} ──{rel_parts[2]}──► {to_name}"
                )
            else:
                lines.append(f"{from_name} ──{relation}──► {to_name}")
        else:
            lines.append(f"{from_name} ──{relation}──► {to_name}")
    return "\n".join(lines)


def _format_key_verses_text(raw: dict[str, list[tuple[str, str]]]) -> str:
    """将 get_key_verses 结果格式化为 Step2 Prompt 块：每行「- 概念名：id「正文」；id「正文」…」。"""
    if not raw:
        return "（无）"
    lines_out: list[str] = []
    for concept, pairs in raw.items():
        parts: list[str] = []
        for vid, vtext in pairs:
            vtext = (vtext or "").strip()
            vid = (vid or "").strip()
            if not vtext:
                continue
            clean_text = vtext.replace("“", "'").replace("”", "'")
            if vid:
                parts.append(f"{vid}「{clean_text}」")
            else:
                parts.append(f"「{clean_text}」")
        if parts:
            lines_out.append(f"- {concept}：{'；'.join(parts)}")
    return "\n".join(lines_out) if lines_out else "（无）"


def _parse_step2_skeleton(text: str) -> list[dict] | None:
    """解析 Step 2 骨架 JSON，返回 [{"step": str, "deep_indices": list[int], "path_evidence": str|None, "scripture_anchor": str|None}, ...]；为 null 或失败时返回 None。
    若 scripture_anchor 含全角「，则将其前缀作为出处拼入 step：step +「（出处）」；scripture_anchor 字段原样保留。"""
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
        text = text.strip()
    try:
        obj = _safe_parse_json(text or "")
    except Exception:
        return None
    if not obj:
        return None
    sk = obj.get("skeleton")
    if sk is None:
        return None
    if isinstance(sk, list):
        result = []
        for x in sk:
            if isinstance(x, dict) and "step" in x:
                step = str(x.get("step", "")).strip()
                indices = x.get("deep_indices", [])
                if not isinstance(indices, list):
                    indices = []
                indices = [i for i in indices if isinstance(i, int)]
                pe_raw = x.get("path_evidence")
                path_evidence = str(pe_raw).strip() if pe_raw and str(pe_raw).strip() else None
                sa_raw = x.get("scripture_anchor")
                scripture_anchor = str(sa_raw).strip() if sa_raw and str(sa_raw).strip() else None
                if step:
                    if scripture_anchor is not None:
                        pos = scripture_anchor.find("「")
                        if pos != -1:
                            scripture_id = scripture_anchor[:pos].strip()
                            if scripture_id:
                                step = f"{step}（{scripture_id}）"
                    result.append(
                        {
                            "step": step,
                            "deep_indices": indices,
                            "path_evidence": path_evidence,
                            "scripture_anchor": scripture_anchor,
                        }
                    )
            elif isinstance(x, str) and x.strip():
                result.append(
                    {
                        "step": x.strip(),
                        "deep_indices": [],
                        "path_evidence": None,
                        "scripture_anchor": None,
                    }
                )
        return result if result else None
    return None
