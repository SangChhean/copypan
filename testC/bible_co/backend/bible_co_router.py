import re
import os
from fastapi import APIRouter
from pydantic import BaseModel
from elasticsearch import Elasticsearch
from bible_co_prompts import BIBOOKS, BOOKMARKS, NAMESFULL, CN, EN

# ── ES 客户端 ──────────────────────────────────────────────
es = Elasticsearch(
    hosts=[f"http://{os.getenv('ES_HOST','localhost')}:{os.getenv('ES_PORT','9200')}"],
    basic_auth=("elastic", os.getenv("ES_PASSWORD", "")),
    request_timeout=60,
)

# ── 正则（完整照抄主站，不可删减）─────────────────────────
REGX = re.compile(
    r"(?:创世记|出埃及记|利未记|民数记|申命记|约书亚记|士师记|路得记|撒母耳记上|撒母耳记下|列王记上|列王记下|历代志上"
    r"|历代志下|以斯拉记|尼希米记|以斯帖记|约伯记|诗篇|箴言|传道书|雅歌|以赛亚书|耶利米书|耶利米哀歌|以西结书|但以理书|何西阿书|约珥书|阿摩司书"
    r"|俄巴底亚书|约拿书|弥迦书|那鸿书|哈巴谷书|西番雅书|哈该书|撒迦利亚书|玛拉基书|马太福音|马可福音|路加福音|约翰福音|使徒行传|罗马书|歌林多前书"
    r"|歌林多后书|加拉太书|以弗所书|腓利比书|歌罗西书|帖撒罗尼迦前书|帖撒罗尼迦后书|提摩太前书|提摩太后书|提多书|腓利门书|希伯来书|雅各书|彼得前书"
    r"|彼得后书|约翰一书|约翰二书|约翰三书|犹大书|启示录|出埃及|约书亚|以斯拉|尼希米|以斯帖|约伯|以赛亚|耶利米|以西结|但以理|何西阿|约珥|哈该"
    r"|撒迦利亚|玛拉基|马太|马可|路加|约翰|行传|罗马|加拉太|以弗所|腓利比|歌罗西|提多|腓利门|希伯来"
    r"|雅各|约壹|约贰|约叁|犹大"
    r"|创|出|利|民|申|书|士|得|撒上|撒下|王上|王下|代上|代下|拉|尼|斯|伯|诗|箴|传|歌|赛"
    r"|耶|哀|结|但|何|珥|摩|俄|拿|弥|鸿|哈|番|该|亚|玛|太|可|路|约|徒|罗|林前|林后|加|弗|腓|西"
    r"|帖前|帖后|提前|提后|多|门|来|雅|彼前|彼后|犹|启|到|直到|一直到)?[第一二三四五六七八九十〇\d这章]*[-~～:：、\d第至到一二三四五六七八九十〇节上下]*"
)

# ── 辅助函数 ───────────────────────────────────────────────
def get_ennum(cha):
    if not cha:
        return ""
    if cha.isdigit():
        return cha
    data = 0
    if len(cha) == 1:
        data = EN[CN.index(cha)]
    elif len(cha) == 2:
        if "十" in cha:
            if cha[0] == "十":
                data = "1" + EN[CN.index(cha[1])]
            else:
                data = EN[CN.index(cha[0])] + "0"
        else:
            data = EN[CN.index(cha[0])] + EN[CN.index(cha[1])]
    elif len(cha) == 3:
        if cha[1] == "十":
            data = EN[CN.index(cha[0])] + EN[CN.index(cha[2])]
        else:
            data = EN[CN.index(cha[0])] + EN[CN.index(cha[1])] + EN[CN.index(cha[2])]
    return data


def get_lines(text):
    items = []
    if "\n" not in text:
        items.append(text)
    else:
        for item in text.split("\n"):
            item = re.sub(r" +", " ", item)
            item = re.sub(r"(^ )|( $)", "", item)
            if item in ("\n", "", " "):
                pass
            else:
                items.append(item)
    return items


def rmup(mat):
    v = mat.group()
    v = re.sub("[上下]", "", v)
    return v


def filter_mats(mats):
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
        mat = re.sub(r"\d+[节]?[上下]", rmup, mat)

        if mat in NAMESFULL:
            book = BOOKMARKS[NAMESFULL.index(mat)]
            data.append({"b": book})
            continue

        if "章" in mat and not re.search(r"[到至]", mat):
            matt = re.search(
                r"(.*?)?([一二三四五六七八九十〇]*)章([一二三四五六七八九十〇\d节]*)?$",
                mat,
            )
            if not matt:
                continue
            temp = ""
            mat_tpye = ""
            if matt.group(1):
                bookn = matt.group(1)
                for item in BIBOOKS:
                    if bookn == item["f"] or bookn == item["n"]:
                        book = item["s"]
                    elif book == "零":
                        continue
                temp += book
                mat_tpye += "b"
            if matt.group(2):
                temp += matt.group(2)
                mat_tpye += "c"
            if matt.group(3):
                verse = matt.group(3)
                verse = re.sub(r"节", "", verse)
                verse = get_ennum(verse)
                temp += str(verse)
                mat_tpye += "v"
            data.append({mat_tpye: temp})

        elif "节" in mat:
            if re.search(r"[至到]", mat):
                mat = re.sub(r"[至到]", "-", mat)
                if "章" in mat:
                    matt = re.search(
                        r"(.*?)?([一二三四五六七八九十〇]*)章([一二三四五六七八九十〇\d节-]*)?$",
                        mat,
                    )
                    if not matt:
                        continue
                    temp = ""
                    mat_tpye = ""
                    if matt.group(1):
                        bookn = matt.group(1)
                        for item in BIBOOKS:
                            if bookn == item["f"] or bookn == item["n"]:
                                book = item["s"]
                            elif book == "零":
                                continue
                        temp += book
                        mat_tpye += "b"
                    if matt.group(2):
                        temp += matt.group(2)
                        mat_tpye += "c"
                    if matt.group(3):
                        verse = matt.group(3)
                        verse = re.sub(r"节", "", verse)
                        v_list = verse.split("-")
                        s = get_ennum(v_list[0])
                        e = get_ennum(v_list[1])
                        temp += f"{s}-{e}"
                        mat_tpye += "v"
                    data.append({mat_tpye: temp})
                else:
                    matt = re.search(r"[一二三四五六七八九十〇\d节-]*$", mat)
                    if not matt:
                        continue
                    verse = matt.group()
                    verse = re.sub(r"节", "", verse)
                    v_list = verse.split("-")
                    s = get_ennum(v_list[0])
                    e = get_ennum(v_list[1])
                    temp = f"{s}-{e}"
                    data.append({"v": temp})
            else:
                mat = mat.replace("节", "")
                matt = re.findall(r"[一二三四五六七八九十〇]+", mat)
                if matt:
                    for item in matt:
                        repl = get_ennum(item)
                        mat = mat.replace(item, repl)
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


def get_sources(line):
    mats = re.findall(REGX, line)
    if mats:
        return filter_mats(mats)
    return []


def reorder_s(data):
    if not data:
        return []
    global bim, cim, vim
    reorder = []
    for item in data:
        if "b" in item:
            bim = item["b"]
        elif "c" in item:
            cim = item["c"]
        elif "bc" in item:
            item = item["bc"]
            mat = re.search(r"[一二三四五六七八九十〇]+", item)
            s = mat.span()[0]
            bim = item[:s]
            cim = item[s:]
        elif "bcv" in item:
            item = item["bcv"]
            if item == "路西弗":
                continue
            mat = re.search(r"(.*?)([一二三四五六七八九十〇\d]+).*?", item)
            if not mat:
                continue
            bim = mat.group(1)
            cim = mat.group(2)
            reorder.append(item)
        elif "cv" in item:
            cv_val = item["cv"]
            colon_pos = cv_val.find(":")
            if colon_pos > 0:
                cim = cv_val[:colon_pos]
            item = bim + cv_val
            reorder.append(item)
        elif "v" in item:
            item = bim + cim + ":" + item["v"]
            reorder.append(item)
    return reorder


def get_verses(para):
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


def get_sids(reo):
    sids = []
    if not reo:
        return sids
    for item in reo:
        item = re.sub(r"[：。；:]+$", "", item)
        mat_cn  = re.search(r"^(.*?)([一二三四五六七八九十〇]+)([-~～:、\d]*)$", item)
        mat_num = re.search(r"^(.*?)(\d+)([-~～:、\d]*)$", item)
        mat = mat_cn if mat_cn else mat_num
        if not mat:
            continue
        if mat.group(1) != "零":
            try:
                b = BOOKMARKS.index(mat.group(1)) + 1
            except ValueError:
                continue
        else:
            b = "0"
        c = get_ennum(mat.group(2))
        vs = get_verses(mat.group(3))
        for v in vs:
            sids.append(f"{b}-{c}-{v}")
    return sids


def get_ver_by_id(sid):
    ver = {}
    try:
        res = es.get(index="bib", id=f"bib_{sid}")["_source"]
        ver["text"]   = res["text"].strip().replace("\r\n", " ").replace("\n", " ").replace("\r", " ")
        ver["source"] = re.sub(r"[（）]|圣经恢复本，", "", res["source"][0]).strip()
    except Exception:
        return ver
    return ver


def get_res(sids):
    return [get_ver_by_id(sid) for sid in sids]


# ── API ────────────────────────────────────────────────────
router = APIRouter(prefix="/api/testc/bible_co")

class BibleCoRequest(BaseModel):
    text: str

@router.post("/process")
def process(req: BibleCoRequest):
    global bim, cim, vim
    bim = "零"
    cim = "零"
    vim = "零"
    data = []
    lines = get_lines(req.text)
    for line in lines:
        if line == "　":
            continue
        sources = get_sources(line)
        reo     = reorder_s(sources)
        sids    = get_sids(reo)
        sids    = list(dict.fromkeys(sids))
        vers    = [v for v in get_res(sids) if v]
        data.append({"text": line, "vers": vers})
    return data
