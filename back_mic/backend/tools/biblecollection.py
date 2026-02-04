import re
from es_config import es


def Data(para):
    bibooks = [
        {"f": "创世记", "s": "创", "n": "0", "i": 1},
        {"f": "出埃及记", "s": "出", "n": "出埃及", "i": 2},
        {"f": "利未记", "s": "利", "n": "0", "i": 3},
        {"f": "民数记", "s": "民", "n": "0", "i": 4},
        {"f": "申命记", "s": "申", "n": "0", "i": 5},
        {"f": "约书亚记", "s": "书", "n": "约书亚", "i": 6},
        {"f": "士师记", "s": "士", "n": "0", "i": 7},
        {"f": "路得记", "s": "得", "n": "0", "i": 8},
        {"f": "撒母耳记上", "s": "撒上", "n": "撒上", "i": 9},
        {"f": "撒母耳记下", "s": "撒下", "n": "撒下", "i": 10},
        {"f": "列王记上", "s": "王上", "n": "王上", "i": 11},
        {"f": "列王记下", "s": "王下", "n": "王下", "i": 12},
        {"f": "历代志上", "s": "代上", "n": "代上", "i": 13},
        {"f": "历代志下", "s": "代下", "n": "代下", "i": 14},
        {"f": "以斯拉记", "s": "拉", "n": "以斯拉", "i": 15},
        {"f": "尼希米记", "s": "尼", "n": "尼希米", "i": 16},
        {"f": "以斯帖记", "s": "斯", "n": "以斯帖", "i": 17},
        {"f": "约伯记", "s": "伯", "n": "约伯", "i": 18},
        {"f": "诗篇", "s": "诗", "n": "0", "i": 19},
        {"f": "箴言", "s": "箴", "n": "箴言书", "i": 20},
        {"f": "传道书", "s": "传", "n": "0", "i": 21},
        {"f": "雅歌", "s": "歌", "n": "0", "i": 22},
        {"f": "以赛亚书", "s": "赛", "n": "以赛亚", "i": 23},
        {"f": "耶利米书", "s": "耶", "n": "耶利米", "i": 24},
        {"f": "耶利米哀歌", "s": "哀", "n": "0", "i": 25},
        {"f": "以西结书", "s": "结", "n": "以西结", "i": 26},
        {"f": "但以理书", "s": "但", "n": "但以理", "i": 27},
        {"f": "何西阿书", "s": "何", "n": "何西阿", "i": 28},
        {"f": "约珥书", "s": "珥", "n": "约珥", "i": 29},
        {"f": "阿摩司书", "s": "摩", "n": "阿摩司", "i": 30},
        {"f": "俄巴底亚书", "s": "俄", "n": "俄巴底亚", "i": 31},
        {"f": "约拿书", "s": "拿", "n": "约拿", "i": 32},
        {"f": "弥迦书", "s": "弥", "n": "弥迦", "i": 33},
        {"f": "那鸿书", "s": "鸿", "n": "那鸿", "i": 34},
        {"f": "哈巴谷书", "s": "哈", "n": "哈巴谷", "i": 35},
        {"f": "西番雅书", "s": "番", "n": "西番雅", "i": 36},
        {"f": "哈该书", "s": "该", "n": "哈该", "i": 37},
        {"f": "撒迦利亚书", "s": "亚", "n": "撒迦利亚", "i": 38},
        {"f": "玛拉基书", "s": "玛", "n": "玛拉基", "i": 39},
        {"f": "马太福音", "s": "太", "n": "马太", "i": 40},
        {"f": "马可福音", "s": "可", "n": "马可", "i": 41},
        {"f": "路加福音", "s": "路", "n": "路加", "i": 42},
        {"f": "约翰福音", "s": "约", "n": "约翰", "i": 43},
        {"f": "使徒行传", "s": "徒", "n": "行传", "i": 44},
        {"f": "罗马书", "s": "罗", "n": "罗马", "i": 45},
        {"f": "歌林多前书", "s": "林前", "n": "林前", "i": 46},
        {"f": "歌林多后书", "s": "林后", "n": "林后", "i": 47},
        {"f": "加拉太书", "s": "加", "n": "加拉太", "i": 48},
        {"f": "以弗所书", "s": "弗", "n": "以弗所", "i": 49},
        {"f": "腓利比书", "s": "腓", "n": "腓利比", "i": 50},
        {"f": "歌罗西书", "s": "西", "n": "歌罗西", "i": 51},
        {"f": "帖撒罗尼迦前书", "s": "帖前", "n": "帖前", "i": 52},
        {"f": "帖撒罗尼迦后书", "s": "贴后", "n": "贴后", "i": 53},
        {"f": "提摩太前书", "s": "提前", "n": "提前", "i": 54},
        {"f": "提摩太后书", "s": "提后", "n": "提后", "i": 55},
        {"f": "提多书", "s": "多", "n": "提多", "i": 56},
        {"f": "腓利门书", "s": "门", "n": "腓立门", "i": 57},
        {"f": "希伯来书", "s": "来", "n": "希伯来", "i": 58},
        {"f": "雅各书", "s": "雅", "n": "雅各", "i": 59},
        {"f": "彼得前书", "s": "彼前", "n": "彼前", "i": 60},
        {"f": "彼得后书", "s": "彼后", "n": "彼后", "i": 61},
        {"f": "约翰一书", "s": "约壹", "n": "约一", "i": 62},
        {"f": "约翰二书", "s": "约贰", "n": "约二", "i": 63},
        {"f": "约翰三书", "s": "约叁", "n": "约三", "i": 64},
        {"f": "犹大书", "s": "犹", "n": "犹大", "i": 65},
        {"f": "启示录", "s": "启", "n": "0", "i": 66},
    ]

    regx = re.compile(
        r"(?:创世记|出埃及记|利未记|民数记|申命记|约书亚记|士师记|路得记|撒母耳记上|撒母耳记下|列王记上|列王记下|历代志上|\
    |历代志下|以斯拉记|尼希米记|以斯帖记|约伯记|诗篇|箴言|传道书|雅歌|以赛亚书|耶利米书|耶利米哀歌|以西结书|但以理书|何西阿书|约珥书|阿摩司书|\
    |俄巴底亚书|约拿书|弥迦书|那鸿书|哈巴谷书|西番雅书|哈该书|撒迦利亚书|玛拉基书|马太福音|马可福音|路加福音|约翰福音|使徒行传|罗马书|歌林多前书|\
    |歌林多后书|加拉太书|以弗所书|腓利比书|歌罗西书|帖撒罗尼迦前书|帖撒罗尼迦后书|提摩太前书|提摩太后书|提多书|腓利门书|希伯来书|雅各书|彼得前书|\
    |彼得后书|约翰一书|约翰二书|约翰三书|犹大书|启示录|出埃及|约书亚|以斯拉|尼希米|以斯帖|约伯|以赛亚|耶利米|以西结|但以理|何西阿|约珥|哈该|\
    |撒迦利亚|玛拉基|马太|马可|路加|约翰|行传|罗马|加拉太|以弗所|腓利比|歌罗西|提多|腓利门|希伯来|\
    |雅各|约壹|约贰|约叁|犹大|\
    |创|出|利|民|申|书|士|得|撒上|撒下|王上|王下|代上|代下|拉|尼|斯|伯|诗|箴|传|歌|赛|\
    |耶|哀|结|但|何|珥|摩|俄|拿|弥|鸿|哈|番|该|亚|玛|太|可|路|约|徒|罗|林前|林后|加|弗|腓|西|\
    |帖前|帖后|提前|提后|多|门|来|雅|彼前|彼后|犹|启|到|直到|一直到)?[第一二三四五六七八九十〇\d这章]*[-~～:：、\d第至到一二三四五六七八九十〇节上下]*"
    )

    namesfull = [
        "创世记",
        "出埃及记",
        "利未记",
        "民数记",
        "申命记",
        "约书亚记",
        "士师记",
        "路得记",
        "撒母耳记上",
        "撒母耳记下",
        "列王记上",
        "列王记下",
        "历代志上",
        "历代志下",
        "以斯拉记",
        "尼希米记",
        "以斯帖记",
        "约伯记",
        "诗篇",
        "箴言",
        "传道书",
        "雅歌",
        "以赛亚书",
        "耶利米书",
        "耶利米哀歌",
        "以西结书",
        "但以理书",
        "何西阿书",
        "约珥书",
        "阿摩司书",
        "俄巴底亚书",
        "约拿书",
        "弥迦书",
        "那鸿书",
        "哈巴谷书",
        "西番雅书",
        "哈该书",
        "撒迦利亚书",
        "玛拉基书",
        "马太福音",
        "马可福音",
        "路加福音",
        "约翰福音",
        "使徒行传",
        "罗马书",
        "歌林多前书",
        "歌林多后书",
        "加拉太书",
        "以弗所书",
        "腓利比书",
        "歌罗西书",
        "帖撒罗尼迦前书",
        "帖撒罗尼迦后书",
        "提摩太前书",
        "提摩太后书",
        "提多书",
        "腓利门书",
        "希伯来书",
        "雅各书",
        "彼得前书",
        "彼得后书",
        "约翰一书",
        "约翰二书",
        "约翰三书",
        "犹大书",
        "启示录",
    ]

    bookmarks = [
        "创",
        "出",
        "利",
        "民",
        "申",
        "书",
        "士",
        "得",
        "撒上",
        "撒下",
        "王上",
        "王下",
        "代上",
        "代下",
        "拉",
        "尼",
        "斯",
        "伯",
        "诗",
        "箴",
        "传",
        "歌",
        "赛",
        "耶",
        "哀",
        "结",
        "但",
        "何",
        "珥",
        "摩",
        "俄",
        "拿",
        "弥",
        "鸿",
        "哈",
        "番",
        "该",
        "亚",
        "玛",
        "太",
        "可",
        "路",
        "约",
        "徒",
        "罗",
        "林前",
        "林后",
        "加",
        "弗",
        "腓",
        "西",
        "帖前",
        "帖后",
        "提前",
        "提后",
        "多",
        "门",
        "来",
        "雅",
        "彼前",
        "彼后",
        "约壹",
        "约贰",
        "约叁",
        "犹",
        "启",
    ]
    cn = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "〇"]
    en = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "0"]

    return locals()[para]


def get_lines(text):
    items = []
    if "\n" not in text:
        items.append(text)
    else:
        inputxt = text.split("\n")
        for item in inputxt:
            item = re.sub(r" +", " ", item)
            item = re.sub(r"(^ )|( $)", "", item)
            if item == "\n" or item == "" or item == " ":
                pass
            else:
                items.append(item)

    return items


def get_ennum(cha):
    """
    将中文数字或阿拉伯数字章节号转换为标准阿拉伯数字
    支持：一、二、十、十一、11 等格式
    """
    # 如果是空字符串或None，返回空
    if not cha:
        return ""
    
    # 如果已经全是阿拉伯数字，直接返回
    if cha.isdigit():
        return cha
    
    cn = Data("cn")
    en = Data("en")
    data = 0

    if len(cha) == 1:
        data = en[cn.index(cha)]
    elif len(cha) == 2:
        if "十" in cha:
            if cha[0] == "十":
                data = "1" + en[cn.index(cha[1])]
            else:
                data = en[cn.index(cha[0])] + "0"
        else:
            data = en[cn.index(cha[0])] + en[cn.index(cha[1])]
    elif len(cha) == 3:
        if cha[1] == "十":
            data = en[cn.index(cha[0])] + en[cn.index(cha[2])]
        else:
            data = en[cn.index(cha[0])] + en[cn.index(cha[1])] + en[cn.index(cha[2])]
    return data


def get_cnnum(num):
    cn = ["一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "〇"]
    en = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "0"]
    if len(num) == 1:
        cnum = cn[en.index(num)]
    elif len(num) == 2:
        a = num[0]
        b = num[1]
        if b == "0":
            if a == "1":
                cnum = "十"
            else:
                cnum = f"{cn[en.index(a)]}十"
        elif a == "1":
            cnum = "十" + cn[en.index(b)]
        else:
            cnum = cn[en.index(a)] + cn[en.index(b)]
    elif len(num) == 3:
        cnum = ""
        for i in num:
            cnum += cn[en.index(i)]
    else:
        cnum = f"没找到章节信息：{num}"

    return cnum


def get_bookcn(item):
    bookmarks = Data("bookmarks")

    mat = re.search(r"(.*?)-(.*?)-(.*?)$", item)
    index = int(mat.group(1))

    if index == 0:
        c = get_cnnum(mat.group(2))
        return f"[卷名缺失]{c}{mat.group(3)}"

    else:
        b = bookmarks[index - 1]
        c = get_cnnum(mat.group(2))
        v = mat.group(3)

        return b + c + v


def rmup(mat):
    v = mat.group()
    v = re.sub("[上下]", "", v)
    return v


def filter_mats(mats):
    namesfull = Data("namesfull")
    bookmarks = Data("bookmarks")
    bibooks = Data("bibooks")
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

        if mat in namesfull:
            book = bookmarks[namesfull.index(mat)]
            data.append({"b": book})
            continue

        if "章" in mat and not re.search(r"[到至]", mat):
            matt = re.search(
                r"(.*?)?([一二三四五六七八九十〇]*)章([一二三四五六七八九十〇\d节]*)?$",
                mat,
            )
            temp = ""
            mat_tpye = ""
            if matt.group(1):
                bookn = matt.group(1)
                for item in bibooks:
                    if bookn == item["f"] or bookn == item["n"]:
                        book = item["s"]
                    elif book == "零":
                        continue
                # book = bookmarks[namesfull.index(matt.group(1))]
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
                    temp = ""
                    mat_tpye = ""
                    if matt.group(1):
                        bookn = matt.group(1)
                        for item in bibooks:
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
                        verse_en = f"{s}-{e}"
                        temp += verse_en
                        mat_tpye += "v"

                    data.append({mat_tpye: temp})
                else:
                    matt = re.search(r"[一二三四五六七八九十〇\d节-]*$", mat)
                    verse = matt.group()
                    verse = re.sub(r"节", "", verse)
                    v_list = verse.split("-")
                    s = get_ennum(v_list[0])
                    e = get_ennum(v_list[1])
                    verse_en = f"{s}-{e}"
                    temp = verse_en
                    mat_tpye = "v"

                    data.append({mat_tpye: temp})
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
                    data.append({"v": mat})
                else:
                    data.append({"bcv": mat})

    return data


def get_sources(line):
    regx = Data("regx")
    mats = re.findall(regx, line)
    if mats:
        source = filter_mats(mats)
    else:
        source = []
    return source


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
            # 支持中文章号（太一1）和阿拉伯数字章号（太5:6）
            mat = re.search(r"(.*?)([一二三四五六七八九十〇\d]+).*?", item)
            if not mat:
                continue
            bim = mat.group(1)
            cim = mat.group(2)
            reorder.append(item)
        elif "cv" in item:
            mat = re.search(r"[一二三四五六七八九十〇]+", item["cv"])
            cim = mat.group()
            item = bim + item["cv"]
            reorder.append(item)
        elif "v" in item:
            item = bim + cim + item["v"]
            reorder.append(item)

    return reorder


def get_verses(para):
    """
    解析节号，支持范围（1-3）、列表（1,2,3）
    输入可能是：:6、:28-30、1-3、6 等格式
    """
    verses = []
    # 清理前导冒号和其他分隔符
    para = re.sub(r"^[:：]+", "", para)  # 去掉开头的冒号
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
    bookmarks = Data("bookmarks")
    if not reo:
        return sids

    for item in reo:
        temp = []
        # 先尝试匹配纯中文章号格式（太一1）：书卷+中文章+数字节
        mat_cn = re.search(r"^(.*?)([一二三四五六七八九十〇]+)([-:：、\d]*)$", item)
        # 再尝试匹配纯数字章号格式（太5:6）：书卷+数字章+节号
        mat_num = re.search(r"^(.*?)(\d+)([-:：、\d]*)$", item)
        
        # 优先使用中文章号匹配
        mat = mat_cn if mat_cn else mat_num
        
        if not mat:
            continue
        if mat.group(1) != "零":
            try:
                b = bookmarks.index(mat.group(1)) + 1
            except ValueError:
                # 书卷名不在列表中，跳过
                continue
        else:
            b = "0"
        c = get_ennum(mat.group(2))
        vs = get_verses(mat.group(3))

        for v in vs:
            v = f"{b}-{c}-{v}"
            sids.append(v)

    return sids


def subrepl(matchobj):
    v = matchobj.group()
    v = re.sub(r"[ ]+", "", v)
    v = re.sub(r"[,，]", "、", v)
    return v


def suboo(data):
    v = data.group()
    v = re.sub(r"[~～]", "，", v)
    return v


def get_ver_by_id(sid):
    ver = {}
    try:
        res = es.get(index="bib", id=f"bib_{sid}")["_source"]
        ver["text"] = res["text"]
        ver["source"] = re.sub(r"[（）]|圣经恢复本，", "", res["source"][0])
    except Exception:
        # 查询失败（文档不存在），返回空字典
        return ver
    return ver


def get_res(sids):
    res = []
    for sid in sids:
        res.append(get_ver_by_id(sid))
    return res


def main(text):
    global bim, cim, vim
    data = []
    bim = "零"
    cim = "零"
    vim = "零"
    text = re.sub(r"[ ]+", " ", text)
    text = re.sub(r"[\d上下]+[,， \d]+\d", subrepl, text)
    text = re.sub(r"\d[~～][一二三四五六七八九十]+[\d]", suboo, text)
    text = re.sub(r"[-~～][ ]+", "～", text)
    text = text.replace("○", "〇")
    lines = get_lines(text)
    for line in lines:
        if line == "　":
            continue
        sources = get_sources(line)
        reo = reorder_s(sources)
        sids = get_sids(reo)
        data.append({"text": line, "vers": get_res(sids)})
    return data


def biblecollection(text):
    res = main(text)
    return res
