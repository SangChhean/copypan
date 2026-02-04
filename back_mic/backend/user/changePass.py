from user.add_user import open_users, update_users
from response.excptions import ERR_403


def change_pass(username, old_password, new_password):
    try:
        users = open_users()
        if username in users and users[username]["pass"] == old_password:
            users[username]["pass"] = new_password
            update_users(users)
            return {"msg": "密码修改成功，请重新登录", "code": "1"}
        return {"msg": "用户名或密码错误", "code": "0"}
    except Exception as e:
        raise ERR_403
