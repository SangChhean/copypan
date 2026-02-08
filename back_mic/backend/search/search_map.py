import re
from es_config import es


def get_words(text):
    text = text.strip()
    if not text:
        return None
    return re.split(r"[ 　\s]+", text)


def get_index(index):
    indies = {
        "1": "bib",
        "2": "map_note",
        "3": "map_life",
        "4": "map_nee_bookname",
        "5": "map_nee_title",
        "6": "map_lee_bookname",
        "7": "map_lee_title",
        "8": "map_cont_bookname",
        "9": "map_cont_title",
        "10": "map_others",
        "11": "map_feasts_bookname",
        "12": "map_feasts_title",
        "15": "map_hymn",
        "16": "cws_nee",
        "17": "cws_lee",
        "18": "cws_cont",
        "19": "cws_life_titles",
        "20": "cws_nee_titles",
        "21": "cws_lee_titles",
        "22": "cws_cont_titles",
        "23": "cws_others_titles",
    }
    return indies[index]


def get_match(item):
    return {"match_phrase": {"text": item}}


def get_infos(input, fwds, index):
    matchs = {"must": [], "must_not": []}
    sindex = get_index(index)
    for item in input:
        matchs["must"].append(get_match(item))
    if fwds:
        for item in fwds:
            matchs["must_not"].append(get_match(item))
    else:
        del matchs["must_not"]
    return matchs, sindex


def clear_res(sres):
    hits = sres["hits"]["hits"]
    return hits


def get_bib_order(id):
    nums = re.findall(r"\d+", id)
    nums = [x.zfill(3) for x in nums]
    nums = "".join(nums)
    return int(nums)


def get_bib_source(source):
    source = source.split("，")[-1][:-1]
    return source


def get_data_bib(data):
    arr = []
    for item in data:
        arr.append(
            {
                "text": item["highlight"]["text"][0],
                "source": get_bib_source(item["_source"]["source"][0]),
                "sn": get_bib_order(item["_id"]),
            }
        )
    return arr


def get_data_map_note(data):
    arr = []
    for item in data:
        arr.append(
            {
                "sn": item["_source"]["sn"],
                "text": item["highlight"]["text"][0],
                "msg": item["_source"]["msg"],
                "source": item["_source"]["source"],
                "lab": "查看",
            }
        )
    return arr


def get_data(index, sres):
    data = clear_res(sres)
    if index == "1":
        data = get_data_bib(data)
    else:
        data = get_data_map_note(data)
    return data


def search_map(input, fwds, index):

    input = get_words(input)
    fwds = get_words(fwds)

    matchs, search_index = get_infos(input, fwds, index)
    setting = {
        "size": 10000,
        "query": {"bool": matchs},
        "highlight": {"number_of_fragments": 0, "fields": {"text": {}}},
    }

    sres = es.search(index=search_index, body=setting)

    res = get_data(index, sres)

    return res


def search_cwws(input, fwds, index):
    if index == "3":
        return search_map(input, fwds, "19")
    elif index == "4":
        return search_map(input, fwds, "16")
    elif index == "5":
        return search_map(input, fwds, "20")
    elif index == "6":
        return search_map(input, fwds, "17")
    elif index == "7":
        return search_map(input, fwds, "21")
    elif index == "8":
        return search_map(input, fwds, "18")
    elif index == "9":
        return search_map(input, fwds, "22")
    elif index == "10":
        return search_map(input, fwds, "23")
    else:
        return search_map(input, fwds, index)
