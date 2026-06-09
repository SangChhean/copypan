# -*- coding: utf-8 -*-
import json
import re
from typing import Any, Optional

# ── 辅助函数 ──────────────────────────────────────────────

def _safe_parse_json(text: str) -> Optional[dict]:
    """尝试从文本中提取并解析第一个合法 JSON 对象。"""
    s = (text or '').strip()
    start = s.find('{')
    end = s.rfind('}')
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(s[start:end + 1])
    except json.JSONDecodeError:
        return None


def _is_cwwl_year_range(chunk_id: str, start: int, end: int) -> bool:
    """判断 chunk_id 是否在 CWWL 指定年份范围内。"""
    m = re.search(r'cwwl[_-](\d{4})', chunk_id or '', re.IGNORECASE)
    if not m:
        return False
    try:
        year = int(m.group(1))
        return start <= year <= end
    except ValueError:
        return False


# ── 纲目性质加权 ──────────────────────────────────────────

OUTLINE_NATURE_WEIGHTS = {
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
    results: list,
    outline_nature: str,
) -> list:
    """根据纲目性质对检索结果加权重排序。"""
    rules = OUTLINE_NATURE_WEIGHTS.get(outline_nature, [])
    if not results:
        return results
    if not rules:
        for doc in results:
            s = float(doc.get('score', 0) or 0)
            doc['weighted_score'] = s
            doc['weight_multiplier'] = 1.0
        return results
    for doc in results:
        idx = doc.get('_index', '') or ''
        cid = doc.get('chunk_id', '') or ''
        original_score = float(doc.get('score', 0) or 0)
        multiplier = 1.0
        for condition, weight in rules:
            try:
                if condition(idx, cid):
                    multiplier = max(multiplier, float(weight))
            except Exception:
                continue
        doc['weighted_score'] = original_score * multiplier
        doc['weight_multiplier'] = multiplier
    results.sort(key=lambda x: float(x.get('weighted_score', 0) or 0), reverse=True)
    return results


# ── JSON 解析 ─────────────────────────────────────────────

def _parse_json_array(text: str) -> list:
    """从 Claude 返回文本解析 JSON 数组，支持被截断的 JSON 修复。"""
    if not text or not text.strip():
        return []
    s = text.strip()
    if s.startswith('```'):
        lines = s.split('\n')
        s = '\n'.join(lines[1:-1] if len(lines) > 2 and lines[-1].strip() == '```' else lines[1:])
    try:
        arr = json.loads(s)
        return arr if isinstance(arr, list) else []
    except json.JSONDecodeError:
        last_brace = s.rfind('}')
        if last_brace > 0:
            truncated = s[:last_brace + 1] + ']'
            try:
                arr = json.loads(truncated)
                if isinstance(arr, list):
                    return arr
            except json.JSONDecodeError:
                pass
        return []


def _parse_step1_layers(
    text: str, outline_nature: str = '一般性'
) -> tuple:
    """解析 Step1 返回的 JSON，返回 (revelation, experience, practice, reasoning)。"""
    if not text or not text.strip():
        return ([], [], [], '')
    s = text.strip()
    if s.startswith('```'):
        lines = s.split('\n')
        s = '\n'.join(lines[1:-1] if len(lines) > 2 and lines[-1].strip() == '```' else lines[1:])
    obj = None
    try:
        parsed = json.loads(s)
        if isinstance(parsed, dict):
            obj = parsed
    except json.JSONDecodeError:
        pass
    if obj is None:
        obj = _safe_parse_json(s)
    if not obj:
        return ([], [], [], '')
    reasoning = str(obj.get('reasoning', '') or '').strip()
    revelation = [str(x).strip() for x in obj.get('revelation', []) if str(x).strip()]
    experience = [str(x).strip() for x in obj.get('experience', []) if str(x).strip()]
    practice   = [str(x).strip() for x in obj.get('practice', []) if str(x).strip()]
    nature = (outline_nature or '一般性').strip()
    if nature == '真理启示':
        max_rev, max_exp, max_prac = 8, 4, 4
    elif nature == '生命经历':
        max_rev, max_exp, max_prac = 4, 8, 4
    elif nature == '应用实行':
        max_rev, max_exp, max_prac = 4, 4, 8
    else:
        max_rev, max_exp, max_prac = 6, 5, 5
    experience = experience[:max_exp]
    practice   = practice[:max_prac]
    max_revelation = min(max_rev, 16 - len(experience) - len(practice))
    revelation = revelation[:max_revelation]
    return (revelation, experience, practice, reasoning)
