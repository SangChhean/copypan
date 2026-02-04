import json
from pathlib import Path as pt
from response.excptions import ERR_403
import random
import string


cwd = pt(__file__).parent


def generate_invite_code():
    characters = string.ascii_letters + string.digits
    invite_code = []
    for _ in range(4):
        invite_code.append("".join(random.choice(characters) for _ in range(4)))
    return "-".join(invite_code)


def open_iv():
    iv = (cwd / "iv.json").read_text("utf-8")
    return json.loads(iv)


def update_iv(iv):
    data = json.dumps(iv, indent=4)
    (cwd / "iv.json").write_text(data, "utf-8")


def open_users():
    users = (cwd / "users.json").read_text("utf-8")
    return json.loads(users)


def update_users(users):
    data = json.dumps(users, indent=4)
    (cwd / "users.json").write_text(data, "utf-8")


def get_iv(item):
    iv = open_iv()
    if item in iv:
        return iv[item]
    return None


def add_iv(role):
    iv = open_iv()
    iv_code = generate_invite_code()
    iv[iv_code] = role
    update_iv(iv)


def del_iv(item):
    iv = open_iv()
    del iv[item]
    update_iv(iv)


def get_user(username):
    users = open_users()
    if username in users:
        return users[username]
    return None


def add_user(username, password, role):
    users = open_users()
    users[username] = {"pass": password, "role": role}
    update_users(users)


def del_user(username):
    users = open_users()
    del users[username]
    update_users(users)


def signup(username: str, password: str, ivcode: str):
    try:
        role = get_iv(ivcode)
        if not role:
            return {"msg": "无效的邀请码", "code": "0"}
        if get_user(username):
            return {"msg": "用户名已存在", "code": "0"}
        add_user(username, password, role)
        del_iv(ivcode)
        return {"msg": "注册成功，请登录", "code": "1"}
    except Exception as e:
        raise ERR_403
