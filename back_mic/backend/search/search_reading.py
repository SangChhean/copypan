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
        "13": "map_pano_bookname",
        "14": "map_pano_title",
        "15": "map_hymn",
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


def search_reading(refid):

    sres = es.get(index="pan_reading", id=refid)

    return sres
