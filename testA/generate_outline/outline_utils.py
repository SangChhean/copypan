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


def _format_chunk_line(c: dict, max_text: int = 300) -> str:
    chunk_id = c.get('chunk_id', '')
    book = c.get('book_title', '')
    msg = c.get('message_number', '')
    msg_title = c.get('message_title', '')
    text = (c.get('text') or '').strip()
    header = f'[{chunk_id}] {book}'
    if msg:
        header += f' 第{msg}篇'
    if msg_title:
        header += f' {msg_title}'
    preview = text if len(text) <= max_text else text[:max_text] + '…'
    return f'{header}\n{preview}'


def _build_skeleton_bound_prompt_block(
    skeleton: list[dict],
    expanded_results: list[dict],
    deep: list[str],
    main_results: list[dict],
) -> str:
    used_expanded_ids: set[str] = set()
    sections: list[str] = []

    for idx, sk_item in enumerate(skeleton):
        step_text = sk_item.get('step', '')
        deep_indices = sk_item.get('deep_indices', [])
        target_concepts = {deep[i] for i in deep_indices if 0 <= i < len(deep)}

        bound_chunks = []
        for c in expanded_results:
            if c.get('expanded_from') in target_concepts:
                bound_chunks.append(c)
                used_expanded_ids.add(c.get('chunk_id', ''))

        lines = [f'【第{idx + 1}步】{step_text}']
        if bound_chunks:
            lines.append('  支撑段落：')
            for c in bound_chunks:
                lines.append(f'    {_format_chunk_line(c)}')
                lines.append('    ---')
        else:
            lines.append('  支撑段落：（无绑定段落）')
        sections.append('\n'.join(lines))

    leftover_expanded = [
        c for c in expanded_results if c.get('chunk_id', '') not in used_expanded_ids
    ]

    supplement_lines = ['【补充段落】（来自 BM25 与向量检索，适用于任何大点）']
    for c in main_results:
        supplement_lines.append(f'  {_format_chunk_line(c)}')
        supplement_lines.append('  ---')
    if leftover_expanded:
        for c in leftover_expanded:
            supplement_lines.append(f'  {_format_chunk_line(c)}')
            supplement_lines.append('  ---')
    sections.append('\n'.join(supplement_lines))

    return '\n\n'.join(sections)


def _parse_burden_generation_output(raw: str) -> dict[str, Any]:
    text = (raw or '').strip()
    if not text:
        return {'scenario': 'B', 'candidates': [], 'error': '解析失败'}
    if '候选一' in text:
        candidates: list[str] = []
        for label in ('候选一', '候选二', '候选三'):
            pat = rf'{re.escape(label)}(?:（侧重[^）]*）)?[：:]\s*(.+?)(?=\n\s*候选[一二三]|$)'
            m = re.search(pat, text, re.DOTALL)
            if m:
                candidates.append(re.sub(r'\s+', ' ', m.group(1).strip()))
            else:
                candidates.append('')
        if not any(c.strip() for c in candidates):
            return {'scenario': 'B', 'candidates': [], 'error': '解析失败'}
        while len(candidates) < 3:
            candidates.append('')
        return {'scenario': 'B', 'candidates': candidates[:3]}
    if '负担说明' in text:
        m = re.search(r'负担说明[：:]\s*(.+)', text, re.DOTALL)
        if m:
            line = re.sub(r'\s+', ' ', m.group(1).strip())
            if line:
                return {'scenario': 'A', 'result': line}
    return {'scenario': 'B', 'candidates': [], 'error': '解析失败'}


def _format_paths_text(paths: list[dict]) -> str:
    if not paths:
        return '暂无已知路径'
    lines = []
    for p in paths:
        from_name = p.get('from', '')
        relation = p.get('relation', '')
        to_name = p.get('to', '')
        via = p.get('via')
        hops = p.get('hops', '')
        if via and int(hops or 0) == 2:
            rel_parts = [x.strip() for x in str(relation).split('→')]
            via_name = str(via).strip()
            if len(rel_parts) == 2 and via_name:
                lines.append(
                    f'{from_name} ──{rel_parts[0]}──► {via_name} ──{rel_parts[1]}──► {to_name}'
                )
            else:
                lines.append(f'{from_name} ──{relation}──► {to_name}')
        elif via and int(hops or 0) == 3:
            rel_parts = [x.strip() for x in str(relation).split('→')]
            via_parts = [x.strip() for x in str(via).split('→')]
            if len(rel_parts) == 3 and len(via_parts) == 2:
                lines.append(
                    f'{from_name} ──{rel_parts[0]}──► {via_parts[0]} ──{rel_parts[1]}──► {via_parts[1]} ──{rel_parts[2]}──► {to_name}'
                )
            else:
                lines.append(f'{from_name} ──{relation}──► {to_name}')
        else:
            lines.append(f'{from_name} ──{relation}──► {to_name}')
    return '\n'.join(lines)


def _format_key_verses_text(raw: dict[str, list[tuple[str, str]]]) -> str:
    if not raw:
        return '（无）'
    lines_out: list[str] = []
    for concept, pairs in raw.items():
        parts: list[str] = []
        for vid, vtext in pairs:
            vtext = (vtext or '').strip()
            vid = (vid or '').strip()
            if not vtext:
                continue
            clean_text = vtext.replace('"', "'").replace('"', "'")
            if vid:
                parts.append(f'{vid}「{clean_text}」')
            else:
                parts.append(f'「{clean_text}」')
        if parts:
            lines_out.append(f'- {concept}：{"；".join(parts)}')
    return '\n'.join(lines_out) if lines_out else '（无）'


def _parse_step2_skeleton(text: str) -> list[dict] | None:
    text = text.strip()
    if text.startswith('```'):
        text = re.sub(r'^```[a-zA-Z]*\n?', '', text)
        text = re.sub(r'\n?```$', '', text)
        text = text.strip()
    obj = _safe_parse_json(text or '')
    if not obj:
        return None
    sk = obj.get('skeleton')
    if sk is None:
        return None
    if isinstance(sk, list):
        result = []
        for x in sk:
            if isinstance(x, dict) and 'step' in x:
                step = str(x.get('step', '')).strip()
                indices = x.get('deep_indices', [])
                if not isinstance(indices, list):
                    indices = []
                indices = [i for i in indices if isinstance(i, int)]
                pe_raw = x.get('path_evidence')
                path_evidence = str(pe_raw).strip() if pe_raw and str(pe_raw).strip() else None
                sa_raw = x.get('scripture_anchor')
                scripture_anchor = str(sa_raw).strip() if sa_raw and str(sa_raw).strip() else None
                if step:
                    if scripture_anchor is not None:
                        pos = scripture_anchor.find('「')
                        if pos != -1:
                            scripture_id = scripture_anchor[:pos].strip()
                            if scripture_id:
                                step = f'{step}（{scripture_id}）'
                    result.append({
                        'step': step,
                        'deep_indices': indices,
                        'path_evidence': path_evidence,
                        'scripture_anchor': scripture_anchor,
                    })
            elif isinstance(x, str) and x.strip():
                result.append({
                    'step': x.strip(),
                    'deep_indices': [],
                    'path_evidence': None,
                    'scripture_anchor': None,
                })
        return result if result else None
    return None
