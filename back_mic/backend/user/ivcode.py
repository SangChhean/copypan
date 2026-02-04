import json
import random
import string
from pathlib import Path as pt

basedir = pt(__file__).parent
datadir = basedir / "iv.json"


def generate_license_key():
    characters = string.ascii_letters + string.digits
    key = "-".join("".join(random.choices(characters, k=4)) for _ in range(4))
    return key


def get_list():
    iv = json.loads(datadir.read_text("utf-8"))
    return [{"filename": k, "role": v, "del": ""} for k, v in iv.items()]


def add_new(role):
    iv = json.loads(datadir.read_text("utf-8"))
    new_key = generate_license_key()
    iv[new_key] = role
    datadir.write_text(json.dumps(iv, indent=2), "utf-8")
    return {"datalist": get_list(), "msg": "datalist"}


def del_iv(ivcode):
    ivs = json.loads(datadir.read_text("utf-8"))
    if ivcode not in ivs:
        return {"tip": "没有找到此内容"}
    del ivs[ivcode]
    datadir.write_text(json.dumps(ivs, indent=2), "utf-8")
    return {"datalist": get_list(), "msg": "datalist"}


def change_role(ivc, role):
    ivs = json.loads(datadir.read_text("utf-8"))
    if ivc not in ivs:
        return {"tip": "没有找到此内容"}
    ivs[ivc] = role
    datadir.write_text(json.dumps(ivs, indent=2), "utf-8")
    return {"datalist": get_list(), "msg": "datalist", "tip": "修改成功"}


def iv_opt(iv, role, action):
    if action == "getlist":
        return {"datalist": get_list(), "msg": "datalist"}
    elif action == "del":
        return del_iv(iv)
    elif action == "gen":
        return add_new("t2")
    elif action == "cgrole":
        return change_role(iv, role)
