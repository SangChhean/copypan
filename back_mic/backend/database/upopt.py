import json
from pathlib import Path as pt
from es_config import es

basedir = pt(__file__).parent
updir = basedir / "upload"


def get_all_json():
    return list(updir.rglob("*.json"))


def get_dict_filelist():
    filelist = {}
    for item in get_all_json():
        filelist[item.name] = item
    return filelist


def get_list():
    filelist = []
    for item in get_all_json():
        filelist.append(
            {
                "filename": item.name,
                "ins": "",
                "del": "",
            }
        )
    return filelist


def ins_data(filename):
    files = get_dict_filelist()
    if filename in files:
        jd = json.loads(files[filename].read_text("utf"))
        for item in jd:
            index = item.pop("index")
            idx = item["id"]
            es.index(index=index, id=idx, body=item)
        return True
    return False


def del_file(filename):
    files = get_dict_filelist()
    if filename in files:
        files[filename].unlink()
        return True
    return False


def opt(filename, action):
    if action == "getlist":
        return {"datalist": get_list(), "msg": "datalist"}
    elif action == "del":
        try:
            if del_file(filename):
                return {
                    "datalist": get_list(),
                    "msg": "datalist",
                    "tip": f"{filename} 已删除",
                }
        except Exception as e:
            return {"error": str(e)}
    elif action == "ins":
        if ins_data(filename):
            return {"tip": f"{filename} 已全部导入数据库"}

    return {"tip": "出错了，请检查"}
