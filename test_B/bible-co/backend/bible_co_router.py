# -*- coding: utf-8 -*-
from fastapi import APIRouter
from pydantic import BaseModel
import os, re
from elasticsearch import Elasticsearch
from bible_co_prompts import BOOK_MAP, FULLNAME_MAP, BOOKMARKS, NAMESFULL

es = Elasticsearch(
    hosts=[f"http://{os.getenv('ES_HOST','localhost')}:{os.getenv('ES_PORT','9200')}"],
    basic_auth=("elastic", os.getenv("ES_PASSWORD", "")),
    request_timeout=60,
)

router = APIRouter(prefix="/api/testb/bible_co")

# ── 正则（完整从主站 biblecollection.py 的 regx 复制） ──
REGX = re.compile(
    r"(?:创世记|出埃及记|利未记|民数记|申命记|约书亚记|士师记|路得记|撒母耳记上|撒母耳记下|列王记上|列王记下|历代志上|"
    r"历代志下|以斯拉记|尼希米记|以斯帖记|约伯记|诗篇|箴言|传道书|雅歌|以赛亚书|耶利米书|耶利米哀歌|以西结书|但以理书|何西阿书|约珥书|阿摩司书|"
    r"俄巴底亚书|约拿书|弥迦书|那鸿书|哈巴谷书|西番雅书|哈该书|撒迦利亚书|玛拉基书|马太福音|马可福音|路加福音|约翰福音|使徒行传|罗马书|歌林多前书|"
    r"歌林多后书|加拉太书|以弗所书|腓利比书|歌罗西书|帖撒罗尼迦前书|帖撒罗尼迦后书|提摩太前书|提摩太后书|提多书|腓利门书|希伯来书|雅各书|彼得前书|"
    r"彼得后书|约翰一书|约翰二书|约翰三书|犹大书|启示录|出埃及|约书亚|以斯拉|尼希米|以斯帖|约伯|以赛亚|耶利米|以西结|但以理|何西阿|约珥|哈该|"
    r"撒迦利亚|玛拉基|马太|马可|路加|约翰|行传|罗马|加拉太|以弗所|腓利比|歌罗西|提多|腓利门|希伯来|"
    r"雅各|约壹|约贰|约叁|犹大|"
    r"创|出|利|民|申|书|士|得|撒上|撒下|王上|王下|代上|代下|拉|尼|斯|伯|诗|箴|传|歌|赛|"
    r"耶|哀|结|但|何|珥|摩|俄|拿|弥|鸿|哈|番|该|亚|玛|太|可|路|约|徒|罗|林前|林后|加|弗|腓|西|"
    r"帖前|帖后|提前|提后|多|门|来|雅|彼前|彼后|犹|启|到|直到|一直到)?[第一二三四五六七八九十〇\d这章]*[-~～:：、\d第至到一二三四五六七八九十〇节上下]*"
)

# ── 中文数字转换 ──────────────────────────────────────────────────
_CN = ["〇","一","二","三","四","五","六","七","八","九","十"]
_EN = ["0","1","2","3","4","5","6","7","8","9","10"]

def get_ennum(cha: str) -> str:
    if not cha:
        return ""
    if cha.isdigit():
        return cha
    data = ""
    if len(cha) == 1:
        if cha in _CN:
            data = _EN[_CN.index(cha)]
    elif len(cha) == 2:
        if "十" in cha:
            if cha[0] == "十":
                data = "1" + _EN[_CN.index(cha[1])]
            else:
                data = _EN[_CN.index(cha[0])] + "0"
        else:
            data = _EN[_CN.index(cha[0])] + _EN[_CN.index(cha[1])]
    elif len(cha) == 3:
        if cha[1] == "十":
            data = _EN[_CN.index(cha[0])] + _EN[_CN.index(cha[2])]
        else:
            data = _EN[_CN.index(cha[0])] + _EN[_CN.index(cha[1])] + _EN[_CN.index(cha[2])]
    return data

def get_verses(para: str) -> list[str]:
    verses = []
    para = re.sub(r"^[:：]+", "", para)
    para = re.sub(r"[~～]", "-", para)
    para = re.sub(r"[，、.]", ",", para)
    if "," in para or "-" in para:
        spli = para.split(",")
        for item in spli:
            if "-" in item:
                conti = item.split("-")
                s = conti[0].strip()
                e = conti[1].strip() if len(conti) > 1 else ""
                if s and s.isdigit():
                    for i in range(int(s), 1000):
                        verses.append(str(i))
                        if e and e.isdigit():
                            if i == int(e):
                                break
            else:
                item = item.strip()
                if item:
                    verses.append(item)
    else:
        para = para.strip()
        if para:
            verses.append(para)
    return verses

def _rmup(mat):
    return re.sub("[上下]", "", mat.group())

def filter_mats(mats: list[str]) -> list[dict]:
    data = []
    book = "零"
    for mat in mats:
        if len(mat) > 1:
            if mat[0] == "这":
                continue
            elif mat[0] == "第" and len(mat) == 2:
                continue
            elif "节" not in mat and re.search(r"[到至]", mat):
                continue
        else:
            continue
        mat = re.sub(r"[这第]", "", mat)
        mat = re.sub(r"[-~～]", "-", mat)
        mat = re.sub(r"\d+[节]?[上下]", _rmup, mat)
        if mat in NAMESFULL:
            book = BOOKMARKS[NAMESFULL.index(mat)]
            data.append({"b": book})
            continue
        if "章" in mat and not re.search(r"[到至]", mat):
            matt = re.search(
                r"(.*?)?([一二三四五六七八九十〇]*)章([一二三四五六七八九十〇\d节]*)?$", mat)
            if not matt:
                continue
            temp = ""
            mat_type = ""
            if matt.group(1):
                bookn = matt.group(1)
                if bookn in BOOKMARKS:
                    book = bookn
                elif FULLNAME_MAP.get(bookn) and FULLNAME_MAP[bookn] in BOOKMARKS:
                    book = FULLNAME_MAP[bookn]
                temp += book
                mat_type += "b"
            if matt.group(2):
                temp += matt.group(2)
                mat_type += "c"
            if matt.group(3):
                verse = re.sub(r"节", "", matt.group(3))
                temp += str(get_ennum(verse))
                mat_type += "v"
            data.append({mat_type: temp})
        elif "节" in mat:
            if re.search(r"[至到]", mat):
                mat = re.sub(r"[至到]", "-", mat)
                if "章" in mat:
                    matt = re.search(
                        r"(.*?)?([一二三四五六七八九十〇]*)章([一二三四五六七八九十〇\d节-]*)?$", mat)
                    if not matt:
                        continue
                    temp = ""
                    mat_type = ""
                    if matt.group(1):
                        bookn = matt.group(1)
                        if bookn in BOOKMARKS:
                            book = bookn
                        elif FULLNAME_MAP.get(bookn) and FULLNAME_MAP[bookn] in BOOKMARKS:
                            book = FULLNAME_MAP[bookn]
                        temp += book
                        mat_type += "b"
                    if matt.group(2):
                        temp += matt.group(2)
                        mat_type += "c"
                    if matt.group(3):
                        verse = re.sub(r"节", "", matt.group(3))
                        v_list = verse.split("-")
                        s = get_ennum(v_list[0])
                        e = get_ennum(v_list[1]) if len(v_list) > 1 else ""
                        temp += f"{s}-{e}"
                        mat_type += "v"
                    data.append({mat_type: temp})
                else:
                    matt = re.search(r"[一二三四五六七八九十〇\d节-]*$", mat)
                    if not matt:
                        continue
                    verse = re.sub(r"节", "", matt.group())
                    v_list = verse.split("-")
                    s = get_ennum(v_list[0])
                    e = get_ennum(v_list[1]) if len(v_list) > 1 else ""
                    data.append({"v": f"{s}-{e}"})
            else:
                mat = mat.replace("节", "")
                for it in re.findall(r"[一二三四五六七八九十〇]+", mat):
                    mat = mat.replace(it, get_ennum(it))
                data.append({"v": mat})
        else:
            if re.match(r"[一二三四五六七八九十]", mat[0]):
                if re.search(r"\d", mat):
                    data.append({"cv": mat})
            elif re.search(r"\d", mat):
                if mat[0].isdigit():
                    if ":" in mat or "：" in mat:
                        data.append({"cv": mat})
                    else:
                        data.append({"v": mat})
                else:
                    data.append({"bcv": mat})
    return data

def extract_refs(line: str) -> list[dict]:
    mats = REGX.findall(line)
    return filter_mats(mats)

def refs_to_sids(refs: list[dict]) -> list[str]:
    sids = []
    seen: set[str] = set()
    book = "零"
    chapter = ""   # 记住上一次解析成功的章号，供纯节号片段继承

    for item in refs:
        # 纯书卷标记（如全名书卷单独出现）
        if "b" in item and len(item) == 1:
            book = item["b"]
            continue

        val = list(item.values())[0]
        key = list(item.keys())[0]
        val = re.sub(r"[：。；:]+$", "", val)

        # 纯节号片段（如「57」「16、17」）——继承上一次的书卷+章号
        if key == "v":
            if book == "零" or not chapter:
                continue
            try:
                b = BOOKMARKS.index(book) + 1
            except ValueError:
                continue
            vs = get_verses(val)
            for v in vs:
                sid = f"{b}-{chapter}-{v}"
                if sid not in seen:
                    seen.add(sid)
                    sids.append(sid)
            continue

        # 含章节的片段（bcv / cv / bcv 等）
        mat_cn = re.search(r"^(.*?)([一二三四五六七八九十〇]+)([-:、，,\d]*)$", val)
        mat_num = re.search(r"^(.*?)(\d+)([-:、，,\d]*)$", val)
        mat = mat_cn if mat_cn else mat_num
        if not mat:
            continue

        book_raw = mat.group(1)
        if book_raw:
            if book_raw in BOOKMARKS:
                book = book_raw
            elif FULLNAME_MAP.get(book_raw) in BOOKMARKS:
                book = FULLNAME_MAP[book_raw]
            else:
                continue

        if book == "零":
            continue

        try:
            b = BOOKMARKS.index(book) + 1
        except ValueError:
            continue

        c = get_ennum(mat.group(2))
        if c:
            chapter = c   # 更新已知章号

        vs = get_verses(mat.group(3))
        for v in vs:
            sid = f"{b}-{chapter}-{v}"
            if sid not in seen:
                seen.add(sid)
                sids.append(sid)

    return sids

def get_verse(sid: str) -> dict:
    try:
        res = es.get(index="bib", id=f"bib_{sid}")["_source"]
        return {
            "source": re.sub(r"[（）]|圣经恢复本，", "", res["source"][0]).strip(),
            "text": res["text"].strip().replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        }
    except Exception:
        return {}

class BibleCoRequest(BaseModel):
    text: str

@router.post("/process")
async def process(req: BibleCoRequest):
    lines = req.text.split("\n")
    result = []
    for line in lines:
        refs = extract_refs(line)
        sids = refs_to_sids(refs)
        vers = [v for v in (get_verse(s) for s in sids) if v]
        result.append({"text": line, "vers": vers})
    return result

@router.get("/ping")
async def ping():
    return {"status": "ok"}
