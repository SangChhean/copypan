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
