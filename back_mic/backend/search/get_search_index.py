"""
搜索参数 args 的解析与默认值。

args 正确格式（5 段，用 "-" 连接）：
  "cat1-cat2-cat3-page-pageSize"

  示例: "a-a-a-1-10"

  各段含义：
  - cat1: 分类，取值 a/b/c 或 1~8（a=全部分类, b=含6/7, c=含8; 1~8 为单类）
  - cat2: 子类型，取值 a~m（a=无后缀, b~m 对应不同后缀如 _booknames 等）
  - cat3: 匹配模式，取值 a/b/c（a=模糊/or, b=平衡/and, c=全文）
  - page: 页码，正整数，默认 1
  - pageSize: 每页条数，1~100，默认 10

  若 args 为空、不是 5 段、或某段非法，则使用默认 "a-a-a-1-10"。
"""
import re
from response.excptions import ERR_403

DEFAULT_ARGS = "a-a-a-1-10"

# 合法取值，用于校验
VALID_CAT1 = frozenset("abc") | frozenset("12345678")
VALID_CAT2 = frozenset("abcdefghijklm")
VALID_CAT3 = frozenset("abc")

# cat1 单类对应的 ES 索引名（1 与 get_appendings i/j 组合成 bib、foo，故 1 用空串）
indies = {
    "1": "",
    "2": "life",
    "3": "cwwn",
    "4": "cwwl",
    "5": "others",
    "6": "hymn",
    "7": "feasts",
    "8": "pano",
}

# cat1='a' 查询 bib, foo, life, cwwn, cwwl, others；'b' 增加 hymn, feasts；'c' 增加 pano
cat_a = ["bib", "foo", "2", "3", "4", "5"]
cat_b = cat_a + ["6", "7"]
cat_c = cat_b + ["8"]
cats = {"a": cat_a, "b": cat_b, "c": cat_c}


def contains_chinese(text):
    pattern = re.compile(r"[\u4e00-\u9fa5]")
    return bool(pattern.search(text))


def get_appendings(idx):
    infos = {
        "a": "",
        "b": "_booknames",
        "c": "_booknames",
        "d": "_titles",
        "e": "_headings",
        "f": "_ot1",
        "g": "_msg",
        "h": "",
        "i": "bib",
        "j": "foo",
        "k": "_booknames",
        "l": "_outlines",
        "m": "",
    }
    return infos[idx]


def clear_idx(index):
    # 数据已全部导入，带后缀索引（headings, titles, booknames 等）均可用，不再移除
    return index


def get_index(cat1, cat2):
    index = []

    if cat1 == "1":
        if cat2 not in "ij":
            return index
    elif cat1 == "6":
        if cat2 != "h":
            return index
    elif cat2 in "ijh":
        return index

    if cat1 in "abc":
        for i in cats[cat1]:
            if len(i) == 1:
                index += get_index(i, cat2)
            else:
                index.append(i)
        if cat2 != "a":
            if "bib" in index:
                index.remove("bib")
            if "foo" in index:
                index.remove("foo")
    else:
        idx = indies[cat1]
        idx += get_appendings(cat2)
        index.append(idx)

    index = clear_idx(index)

    return index


def get_match_info(cat3, input):
    # 与前端约定：a=模糊(or), b=平衡(and), c=全文(text)
    operator = "or"
    if contains_chinese(input):
        field = "zh"
        if cat3 == "c":
            field = "text"
        elif cat3 == "b":
            operator = "and"   # 平衡：词条均需匹配
    else:
        field = "en"
        if cat3 in "bc":       # 平衡(b) 与 全文(c) 用 and
            operator = "and"
    return field, operator


def get_kws(input):
    inputs = re.split(r"[\n\t 　]+", input)
    return inputs


def _escape_wildcard(s):
    """转义 ES wildcard 中的 * ? \\ 以便用户输入作为字面量参与匹配"""
    if not s:
        return s
    return s.replace("\\", "\\\\").replace("*", "\\*").replace("?", "\\?")


def get_matchs(field, operator, input):
    """
    构建 ES 查询条件：同时查 zh、text、title，任一匹配即可。
    - zh/text/en 用 match；title 为 keyword 用 wildcard 支持包含匹配。
    """
    q = (input or "").strip()
    should = []

    # 主字段：zh / en / text
    if field == "text":
        kws = get_kws(q)
        if kws:
            should.append({"bool": {"must": [{"match_phrase": {"text": kw}} for kw in kws]}})
        else:
            should.append({"match": {"text": {"query": q, "operator": "or"}}})
    else:
        should.append({"match": {field: {"query": q, "operator": operator}}})

    # 全文 text 字段（与主字段不同时也查，operator 与主字段一致，平衡时才能真 and）
    if field != "text":
        should.append({"match": {"text": {"query": q, "operator": operator}}})

    # title 为 keyword，用 wildcard 做包含匹配
    if q:
        title_value = "*" + _escape_wildcard(q) + "*"
        should.append({"wildcard": {"title": title_value}})

    return should


def parse_args(args):
    """
    解析 args 字符串，格式应为 "cat1-cat2-cat3-page-pageSize"（5 段）。
    若为空、格式不对或某段非法，则使用默认值。
    返回 (cat1, cat2, cat3, page, pageSize)。
    """
    raw = (args or "").strip()
    parts = raw.split("-") if raw else []
    if len(parts) != 5:
        default_parts = DEFAULT_ARGS.split("-")
        return (
            default_parts[0],
            default_parts[1],
            default_parts[2],
            int(default_parts[3]),
            int(default_parts[4]),
        )
    cat1, cat2, cat3, cat4, cat5 = parts
    default_parts = DEFAULT_ARGS.split("-")
    if cat1 not in VALID_CAT1:
        cat1 = default_parts[0]
    if cat2 not in VALID_CAT2:
        cat2 = default_parts[1]
    if cat3 not in VALID_CAT3:
        cat3 = default_parts[2]
    try:
        page = int(cat4) if cat4 else 1
        page = max(1, page)
    except (ValueError, TypeError):
        page = 1
    try:
        page_size = int(cat5) if cat5 else 10
        page_size = max(1, min(page_size, 100))
    except (ValueError, TypeError):
        page_size = 10
    return (cat1, cat2, cat3, page, page_size)


def get_info(args, input):
    input = input.strip()
    if len(input) > 240:
        input = input[:240]
    cat1, cat2, cat3, cat4, cat5 = parse_args(args)
    index = get_index(cat1, cat2)
    field, operator = get_match_info(cat3, input)
    matchs = get_matchs(field, operator, input)
    return index, matchs, field, cat4, cat5
