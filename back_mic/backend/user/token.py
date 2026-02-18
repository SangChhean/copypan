import json
import logging
from typing import Optional
from utils.jwt_op import jwt_encode, jwt_decode
from datetime import datetime, timedelta, timezone
from pathlib import Path
from pydantic import BaseModel
from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from response.excptions import ERR_401, ERR_403

logger = logging.getLogger(__name__)


class Token(BaseModel):
    access_token: str
    token_type: str


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)


def get_token_from_header_or_cookie(
    request: Request, header_token: Optional[str] = Depends(oauth2_scheme)
):
    """从 Authorization Bearer 或 cookie 'session' 中获取 token，二选一即可。"""
    token = header_token
    if not token and request.cookies:
        token = request.cookies.get("session")
    if not token:
        raise ERR_401
    return token


def set_token(username: str, password: str, remember: str):
    USER_DIR = Path(__file__).parent / "users.json"
    try:
        logger.info(f"尝试登录: 用户名={username}, users.json路径={USER_DIR.absolute()}, 文件存在={USER_DIR.exists()}")
        USERS = json.loads(USER_DIR.read_text("utf-8"))
        logger.debug(f"users.json 加载成功，用户列表: {list(USERS.keys())}")
    except FileNotFoundError:
        logger.error(f"users.json 文件不存在: {USER_DIR.absolute()}")
        raise ERR_401
    except json.JSONDecodeError as e:
        logger.error(f"users.json JSON 解析失败: {e}, 文件路径: {USER_DIR.absolute()}")
        raise ERR_401
    except Exception as e:
        logger.error(f"读取 users.json 时发生未知错误: {e}, 文件路径: {USER_DIR.absolute()}", exc_info=True)
        raise ERR_401
    
    if remember == "true":
        exp_date = datetime.now(timezone.utc) + timedelta(days=30)
    else:
        exp_date = datetime.now(timezone.utc) + timedelta(hours=7)
    try:
        if username in USERS and USERS[username]["pass"] == password:
            # JWT 标准要求 exp 为 Unix 时间戳（数字）
            token = jwt_encode(
                {
                    "username": username,
                    "role": USERS[username]["role"],
                    "exp": int(exp_date.timestamp()),
                }
            )
            logger.info(f"登录成功: 用户名={username}, 角色={USERS[username]['role']}")
            return Token(access_token=token, token_type="Bearer")
        else:
            logger.warning(f"登录失败: 用户名={username}, 用户存在={username in USERS}, 密码匹配={username in USERS and USERS[username]['pass'] == password if username in USERS else False}")
            raise ERR_401
    except ERR_401:
        raise
    except Exception as e:
        logger.error(f"生成 token 时发生错误: {e}", exc_info=True)
        raise ERR_401


def test_token(token: str = Depends(get_token_from_header_or_cookie)):
    USER_DIR = Path(__file__).parent / "users.json"
    USERS = json.loads(USER_DIR.read_text("utf-8"))
    try:
        data = jwt_decode(token)
        username = data.get("username")
        role = data.get("role")
        exp = data.get("exp")
        if exp is None:
            raise ERR_401
        exp_dt = datetime.fromtimestamp(exp, tz=timezone.utc)
        now = datetime.now(timezone.utc)
        if username in USERS and role == USERS[username]["role"] and now < exp_dt:
            return {"username": username, "role": role}
        else:
            raise ERR_403
    except ERR_403:
        raise
    except Exception:
        raise ERR_401
