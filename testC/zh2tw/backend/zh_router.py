# 简繁互转路由
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
from opencc import OpenCC
import json

ERROR_CHARS_PATH = Path(__file__).resolve().parents[3] / 'shared' / 'error_chars.txt'

def load_error_chars() -> list:
    try:
        text = ERROR_CHARS_PATH.read_text(encoding='utf-8')
        chars = [line.strip() for line in text.splitlines() if line.strip()]
        return sorted(set(chars), key=len, reverse=True)
    except Exception:
        return []

CANDIDATES_PATH = Path(__file__).resolve().parents[3] / 'shared' / 'error_chars_candidates.json'

def load_candidates() -> dict:
    try:
        return json.loads(CANDIDATES_PATH.read_text(encoding='utf-8'))
    except Exception:
        return {}

router = APIRouter(prefix="/api/testc")

# ── 转换函数 ──────────────────────────────────────────
def convert_to_traditional(content: str) -> dict:
    """简体转繁体：先用术语表保护职事词汇，再用 OpenCC 通用转换，最后还原术语"""
    try:
        # 读取术语表
        terms_path = Path(__file__).resolve().parents[3] / "shared" / "zh_tw_terms.json"
        if terms_path.exists():
            with open(terms_path, encoding="utf-8") as f:
                terms = json.load(f)
        else:
            terms = {}

        # 按键长降序排列，长词优先匹配
        sorted_terms = sorted(terms.items(), key=lambda x: len(x[0]), reverse=True)

        # 第一步：把简体术语替换为占位符
        placeholders = {}
        text = content
        for i, (zh, tw) in enumerate(sorted_terms):
            placeholder = f"__TW_{i}__"
            if zh in text:
                text = text.replace(zh, placeholder)
                placeholders[placeholder] = tw

        # 第二步：OpenCC 通用简转繁
        cc = OpenCC("s2t")
        text = cc.convert(text)

        # 第三步：把占位符还原为正确繁体词
        for placeholder, tw in placeholders.items():
            text = text.replace(placeholder, tw)

        return {'answer_zh_tw': text, '_terms': terms}

    except Exception as e:
        return {"answer_zh_tw": None, "error": str(e)}


def get_candidates_from_dict(error_char: str, terms: dict) -> list:
    """优先从候选词表查，找不到再从词典反查"""
    candidates_map = load_candidates()
    if error_char in candidates_map:
        return candidates_map[error_char]
    # 词典反查兜底
    source_chars = set()
    for simplified, traditional in terms.items():
        if error_char in traditional:
            idx = traditional.find(error_char)
            if idx < len(simplified):
                source_chars.add(simplified[idx:idx + len(error_char)])
    if not source_chars:
        return []
    candidates = set()
    for src in source_chars:
        for simplified, traditional in terms.items():
            if src in simplified:
                idx = simplified.find(src)
                if idx < len(traditional):
                    candidates.add(traditional[idx:idx + len(src)])
    if len(candidates) <= 1:
        return []
    return sorted(candidates)

def check_error_chars(text: str, terms: dict) -> list:
    """扫描繁体结果，找出易错字，反查词典候选词，返回命中列表"""
    error_chars = load_error_chars()
    results = []
    covered = set()
    for ec in error_chars:
        start = 0
        while True:
            pos = text.find(ec, start)
            if pos == -1:
                break
            positions = set(range(pos, pos + len(ec)))
            if not positions & covered:
                covered |= positions
                ctx_start = max(0, pos - 5)
                ctx_end = min(len(text), pos + len(ec) + 5)
                context_str = text[ctx_start:ctx_end]
                local_pos = pos - ctx_start
                marked = (
                    context_str[:local_pos]
                    + '【' + ec + '】'
                    + context_str[local_pos + len(ec):]
                )
                candidates = get_candidates_from_dict(ec, terms)
                results.append({
                    'char': ec,
                    'position': pos,
                    'context': marked,
                    'candidates': candidates
                })
            start = pos + 1
    results.sort(key=lambda x: x['position'])
    return results


def convert_to_simplified(content: str) -> dict:
    """繁体转简体：用 OpenCC t2s 通用转换"""
    try:
        cc = OpenCC("t2s")
        text = cc.convert(content)
        return {"answer_zh_tw": text}
    except Exception as e:
        return {"answer_zh_tw": None, "error": str(e)}


# ── 请求模型 ──────────────────────────────────────────
class ZhConvertRequest(BaseModel):
    content: str
    direction: str = "zh2tw"  # 默认简转繁


# ── 路由 ─────────────────────────────────────────────
@router.post("/zh_convert")
async def zh_convert(req: ZhConvertRequest):
    if not req.content or not req.content.strip():
        raise HTTPException(status_code=400, detail="content 不能为空")
    if req.direction == "tw2zh":
        return convert_to_simplified(req.content)
    else:
        result = convert_to_traditional(req.content)
        terms = result.pop('_terms', {})
        if 'answer_zh_tw' in result and result['answer_zh_tw']:
            result['error_check'] = check_error_chars(result['answer_zh_tw'], terms)
        else:
            result['error_check'] = []
        return result
