import json
from pathlib import Path as pt


basedir = pt(__file__).parent
datadir = basedir / "users.json"
ivdir = basedir / "iv.json"


def get_user_list():
    users = json.loads(datadir.read_text("utf-8"))
    return [
        {"filename": x, "role": y["role"]}
        for x, y in users.items()
        if x not in ["stephen"]
    ]


def change_role(username, role):
    users = json.loads(datadir.read_text("utf-8"))
    if username not in users:
        return {"tip": f"没有此用户：{username}"}
    users[username]["role"] = role
    datadir.write_text(json.dumps(users, indent=2), "utf-8")
    return {"datalist": get_user_list(), "msg": "datalist", "tip": "修改成功"}


def del_user(username):
    users = json.loads(datadir.read_text("utf-8"))
    if username not in users:
        return {"tip": f"没有此用户：{username}"}
    del users[username]
    datadir.write_text(json.dumps(users, indent=2), "utf-8")
    return {"datalist": get_user_list(), "msg": "datalist", "tip": "删除成功"}


def user_opt(username, opt, role):
    if opt == "getlist":
        return {"datalist": get_user_list(), "msg": "datalist"}
    elif opt == "cgrole":
        return change_role(username, role)
    elif opt == "del":
        return del_user(username)

    return
