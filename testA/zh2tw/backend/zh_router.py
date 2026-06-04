# 简繁互转路由
from fastapi import APIRouter
from pydantic import BaseModel, Field
import json
import re
import opencc
from pathlib import Path

router = APIRouter()

# ── 术语表路径 ──────────────────────────────────────────
TERMS_PATH = Path(__file__).resolve().parents[3] / "shared" / "zh_tw_terms.json"

# ── 启动时加载术语表 ────────────────────────────────────
def _load_terms() -> dict:
    with open(TERMS_PATH, encoding="utf-8") as f:
        return json.load(f)


TERMS: dict = _load_terms()

# 按简体词长度降序排列，避免短词先替换导致长词漏匹配
SORTED_TERMS = sorted(TERMS.keys(), key=len, reverse=True)

POST_TRAD_PAIRS: list[tuple[str, str]] = sorted(
    [
        ("預", "豫"),
        ("顆樹", "棵樹"),
        ("秘", "祕"),
        ("才是", "纔是"),
        ("才會", "纔會"),
        ("什", "甚"),
        ("台", "臺"),
        ("意象", "異象"),
        ("兇", "凶"),
        ("份", "分"),
        ("吃", "喫"),
        ("吧", "罷"),
        ("恒", "恆"),
        ("唇", "脣"),
        ("做人", "作人"),
        ("做事", "作事"),
        ("做工", "作工"),
        ("啊", "阿"),
        ("唯", "惟"),
        ("唸", "念"),
        ("夠", "彀"),
        ("証 ", "證"),
        ("腊", "臘"),
        ("嗎？", "麼？"),
        ("裡", "裏"),
        ("葯", "藥"),
        ("嘆", "歎"),
        ("摻", "攙"),
        ("燄", "焰"),
        ("嚐", "嘗"),
        ("餵", "餧"),
        ("鎗", "槍"),
        ("效忠", "効忠"),
        ("計劃", "計畫"),
        ("提醒", "題醒"),
        ("借著", "藉著"),
        ("口喫", "口吃"),
        ("撒旦", "撒但"),
        ("形象", "形像"),
        ("翻譯", "繙譯"),
        ("對像", "對象"),
        ("創世紀", "創世記"),
        ("複習", "復習"),
        ("重覆", "重複"),
        ("撲倒", "仆倒"),
    ],
    key=lambda kv: len(kv[0]),
    reverse=True,
)

# 加载自定义词典
_CUSTOM_DICT_PATH = Path(__file__).resolve().parent / "custom_dict.json"
_custom_dict_raw = json.load(open(_CUSTOM_DICT_PATH, encoding="utf-8"))
CUSTOM_DICT: list[tuple[str, str]] = sorted(
    [(item["simp"], item["trad"]) for item in _custom_dict_raw],
    key=lambda x: len(x[0]),
    reverse=True,
)

# ── OpenCC 转换器（s2t：简体→繁体）──────────────────────
converter = opencc.OpenCC("s2t")


def apply_custom_dict(text: str) -> tuple[str, list[str]]:
    """左优先匹配自定义词典，命中词用占位符保护，返回处理后文本和替换列表"""
    replacements: list[str] = []
    result: list[str] = []
    i = 0
    n = len(text)
    while i < n:
        matched = None
        for simp, trad in CUSTOM_DICT:
            if simp and text.startswith(simp, i):
                matched = (simp, trad)
                break
        if matched:
            idx = len(replacements)
            result.append(f"__PROT_{idx}__")
            replacements.append(matched[1])
            i += len(matched[0])
        else:
            result.append(text[i])
            i += 1
    return "".join(result), replacements


def restore_placeholders(text: str, replacements: list[str]) -> str:
    for idx, trad in enumerate(replacements):
        text = text.replace(f"__PROT_{idx}__", trad)
    return text


def apply_post_trad(text: str) -> str:
    for fr, to in POST_TRAD_PAIRS:
        if fr:
            text = text.replace(fr, to)
    return text


# 加载易错字表
_ERROR_CHARS_PATH = Path(__file__).resolve().parent / "error_chars.txt"
_error_words_raw = [
    line.strip()
    for line in _ERROR_CHARS_PATH.read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.startswith("#")
]
_error_words_raw.sort(key=len, reverse=True)
_ERROR_PATTERN = re.compile("|".join(re.escape(w) for w in _error_words_raw if w))


def scan_errors(text: str) -> list[dict]:
    """扫描易错字，返回命中列表"""
    if not _ERROR_PATTERN.search(text):
        return []
    sentence_pattern = re.compile(
        r"[。！？，,\.!\?；;：:…—–\-\t\n\r\u3001]+"
    )
    sentences = [s.strip() for s in sentence_pattern.split(text) if s.strip()]
    results = []
    for sentence in sentences:
        for m in _ERROR_PATTERN.finditer(sentence):
            marked = _ERROR_PATTERN.sub(lambda x: f"【【{x.group(0)}】】", sentence)
            results.append(
                {
                    "word": m.group(0),
                    "sentence": marked,
                }
            )
            break  # 每句只记录一次
    return results


def convert_zh2tw(text: str) -> tuple[str, list[dict]]:
    # 第一步：自定义词典占位保护
    protected, replacements = apply_custom_dict(text)
    # 第二步：OpenCC s2t
    converted = converter.convert(protected)
    # 第三步：还原占位符
    restored = restore_placeholders(converted, replacements)
    # 第四步：后处理替换
    result = apply_post_trad(restored)
    # 第五步：扫描易错字
    errors = scan_errors(result)
    return result, errors


def convert_tw2zh(text: str) -> str:
    """繁→简：直接用 OpenCC t2s，不走术语表"""
    return opencc.OpenCC("t2s").convert(text)


# ── 请求 / 响应模型 ─────────────────────────────────────
class ZhConvertRequest(BaseModel):
    content: str = Field(..., min_length=1, max_length=100_000)


class ZhConvertResponse(BaseModel):
    result: str = ""
    errors: list[dict] = []
    error: str = ""


# ── API 路由 ────────────────────────────────────────────
@router.post("/api/testa/zh_convert", response_model=ZhConvertResponse)
def zh_convert(request: ZhConvertRequest):
    try:
        result, errors = convert_zh2tw(request.content)
        return ZhConvertResponse(result=result, errors=errors)
    except Exception as e:
        return ZhConvertResponse(result="", errors=[], error=str(e))


@router.post("/api/testa/tw_convert", response_model=ZhConvertResponse)
def tw_convert(request: ZhConvertRequest):
    try:
        result = convert_tw2zh(request.content)
        return ZhConvertResponse(result=result, errors=[])
    except Exception as e:
        return ZhConvertResponse(result="", errors=[], error=str(e))
