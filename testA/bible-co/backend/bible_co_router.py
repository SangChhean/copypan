from fastapi import APIRouter
from pydantic import BaseModel
import re, os
from elasticsearch import Elasticsearch
from bible_co_prompts import BOOK_MAP, FULLNAME_MAP, CN_NUM

# ES 客户端
es = Elasticsearch(
    hosts=[f"http://{os.getenv('ES_HOST','localhost')}:{os.getenv('ES_PORT','9200')}"],
    basic_auth=("elastic", os.getenv("ES_PASSWORD", "")),
    request_timeout=60
)


def cn_to_int(s: str) -> int:
    return CN_NUM.get(s, 0)


def expand_verses(verse_str: str) -> list:
    """展开节号：单节/范围/列举，返回整数列表"""
    verse_str = verse_str.strip().rstrip("上下节")
    if not verse_str:
        return []
    # 范围：16-18 或 16～18
    if re.search(r"[-～~]", verse_str):
        parts = re.split(r"[-～~]", verse_str)
        try:
            start, end = int(parts[0]), int(parts[-1])
            return list(range(start, min(end, start + 50) + 1))
        except Exception:
            return []
    # 列举：16、17 或 16,17
    if re.search(r"[、,，]", verse_str):
        parts = re.split(r"[、,，]", verse_str)
        result = []
        for p in parts:
            try:
                result.append(int(p.strip()))
            except Exception:
                pass
        return result
    # 单节
    try:
        return [int(verse_str)]
    except Exception:
        return []


def resolve_book(raw: str):
    """书卷名解析：简称/全名/别名 → 标准简称，找不到返回 None"""
    if raw in BOOK_MAP:
        return raw
    if raw in FULLNAME_MAP:
        return FULLNAME_MAP[raw]
    return None


# 正则：书卷名部分，全名在前（按长度从长到短），简称在后
_fullnames = sorted(FULLNAME_MAP.keys(), key=len, reverse=True)
_shortnames = sorted(BOOK_MAP.keys(), key=len, reverse=True)
_book_pattern = "|".join(re.escape(k) for k in _fullnames + _shortnames)

# 7种格式正则（按优先级排列，含章节字的格式在前）
REGX = re.compile(
    r"(?:" + _book_pattern + r")"
    r"[一二三四五六七八九十〇百]+"
    r"章"
    r"[一二三四五六七八九十〇百\d]+"
    r"(?:[-～~][一二三四五六七八九十〇百\d]+)?"
    r"节?[上下]?"
    r"|"
    r"(?:" + _book_pattern + r")"
    r"[一二三四五六七八九十〇百]+"
    r"\d+"
    r"(?:[-～~]\d+|[、,，]\d+)*"
    r"节?[上下]?"
)


def extract_refs(line: str) -> list:
    """从一行纲目文字提取所有经文引用片段"""
    matches = REGX.findall(line)
    return [m for m in matches if m and len(m) >= 2]


def refs_to_sids(refs: list) -> list:
    """引用片段列表 → sid列表（去重）"""
    sids = []
    seen = set()
    for ref in refs:
        # 去掉末尾「上」「下」
        ref_clean = re.sub(r"[上下]$", "", ref.rstrip("节"))
        # 格式5/6：含「章」字
        m = re.match(
            r"^(.*?)([一二三四五六七八九十〇百]+)章([一二三四五六七八九十〇百\d]+(?:[-～~][一二三四五六七八九十〇百\d]+)?)节?$",
            ref_clean
        )
        if m:
            book_raw, chap_cn, verse_str = m.group(1), m.group(2), m.group(3)
            book = resolve_book(book_raw)
            chap = cn_to_int(chap_cn)
            if book and chap:
                b = BOOK_MAP[book]
                for v in expand_verses(verse_str):
                    sid = f"{b}-{chap}-{v}"
                    if sid not in seen:
                        seen.add(sid)
                        sids.append(sid)
            continue
        # 格式1/2/9：简称/全名 + 中文章 + 阿拉伯节
        m = re.match(
            r"^(.*?)([一二三四五六七八九十〇百]+)(\d+(?:[-～~,、，]\d+)*)$",
            ref_clean
        )
        if m:
            book_raw, chap_cn, verse_str = m.group(1), m.group(2), m.group(3)
            book = resolve_book(book_raw)
            chap = cn_to_int(chap_cn)
            if book and chap:
                b = BOOK_MAP[book]
                for v in expand_verses(verse_str):
                    sid = f"{b}-{chap}-{v}"
                    if sid not in seen:
                        seen.add(sid)
                        sids.append(sid)
    return sids


def clean_source(raw: str) -> str:
    """去掉出处前缀，如「圣经恢复本，」「新标点和合本，」等，只保留书卷章节部分"""
    # 去掉「（XXX，」或「XXX，」形式的前缀，保留最后一个「，」之后的内容
    if '，' in raw:
        raw = raw.rsplit('，', 1)[-1]
    # 去掉残余的括号
    raw = raw.strip('（）()')
    return raw.strip()


def get_verse(sid: str) -> dict:
    """用 sid 查 bib 索引，返回 {source, text}，查不到返回 {}"""
    try:
        res = es.get(index="bib", id=f"bib_{sid}")["_source"]
        raw_source = res["source"][0].strip()
        return {
            "source": clean_source(raw_source),
            "text": res["text"].strip()
        }
    except Exception:
        return {}


router = APIRouter(prefix="/api/testa/bible_co")


class BibleCoRequest(BaseModel):
    text: str


@router.get("/health")
def health():
    return {"status": "ok"}


@router.post("/process")
def process(req: BibleCoRequest):
    lines = [l for l in req.text.split("\n") if l.strip()]
    results = []
    for line in lines:
        refs = extract_refs(line)
        sids = refs_to_sids(refs)
        vers = [v for v in (get_verse(sid) for sid in sids) if v]
        results.append({"text": line, "vers": vers})
    return results
