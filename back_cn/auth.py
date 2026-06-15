# -*- coding: utf-8 -*-
"""CN 站用户与鉴权数据层（SQLite + JWT），与 back_qa 用户体系隔离。"""
from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import bcrypt
from fastapi import Request
from jose import JWTError, jwt

DB_PATH = Path(__file__).resolve().parent / "cn_users.db"
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 7

FEATURES = ("outline", "translate", "qa", "burden", "asr")

FEATURE_LABELS: dict[str, str] = {
    "outline": "纲目制作",
    "translate": "翻译",
    "qa": "职事问答",
    "burden": "负担说明",
    "asr": "语音识别",
}

JWT_SECRET = os.environ.get("CN_JWT_SECRET", "").strip()
if not JWT_SECRET:
    raise RuntimeError("未配置 CN_JWT_SECRET")


def _default_limits() -> dict[str, int]:
    return {
        "outline": int(os.getenv("CN_DAILY_LIMIT_OUTLINE", "3")),
        "translate": int(os.getenv("CN_DAILY_LIMIT_TRANSLATE", "3")),
        "qa": int(os.getenv("CN_DAILY_LIMIT_QA", "3")),
        "burden": int(os.getenv("CN_DAILY_LIMIT_BURDEN", "20")),
        "asr": int(os.getenv("CN_DAILY_LIMIT_ASR", "20")),
    }


def _today() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d")


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """初始化数据库与表结构（不存在则创建）。"""
    limits = _default_limits()
    with _connect() as conn:
        conn.execute(
            f"""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                hashed_password TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                daily_date TEXT NOT NULL DEFAULT '2000-01-01',
                count_outline INTEGER NOT NULL DEFAULT 0,
                limit_outline INTEGER NOT NULL DEFAULT {limits['outline']},
                count_translate INTEGER NOT NULL DEFAULT 0,
                limit_translate INTEGER NOT NULL DEFAULT {limits['translate']},
                count_qa INTEGER NOT NULL DEFAULT 0,
                limit_qa INTEGER NOT NULL DEFAULT {limits['qa']},
                count_burden INTEGER NOT NULL DEFAULT 0,
                limit_burden INTEGER NOT NULL DEFAULT {limits['burden']},
                count_asr INTEGER NOT NULL DEFAULT 0,
                limit_asr INTEGER NOT NULL DEFAULT {limits['asr']},
                is_admin INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS invite_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                used INTEGER NOT NULL DEFAULT 0,
                used_by TEXT,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        try:
            conn.execute(
                "ALTER TABLE users ADD COLUMN is_admin INTEGER NOT NULL DEFAULT 0"
            )
        except sqlite3.OperationalError:
            pass
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS material_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                dir_name TEXT NOT NULL UNIQUE,
                sort_order INTEGER DEFAULT 0,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS materials (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category_id INTEGER NOT NULL REFERENCES material_categories(id),
                display_name TEXT NOT NULL,
                stored_name TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        conn.commit()
    print("[CN] materials tables ready")


def check_and_increment_daily_usage(username: str, feature: str) -> dict:
    """
    检查并递增指定功能的每日用量。
    feature ∈ {outline, translate, qa, burden, asr}
    返回 {"allowed", "used", "limit", "feature"}
    """
    if feature not in FEATURES:
        raise ValueError(f"未知 feature: {feature!r}")

    today = _today()
    count_col = f"count_{feature}"
    limit_col = f"limit_{feature}"
    conn = _connect()
    try:
        row = conn.execute(
            f"""
            SELECT daily_date,
                   count_outline, limit_outline,
                   count_translate, limit_translate,
                   count_qa, limit_qa,
                   count_burden, limit_burden,
                   count_asr, limit_asr
            FROM users WHERE username = ?
            """,
            (username,),
        ).fetchone()
        if not row:
            return {"allowed": False, "used": 0, "limit": 0, "feature": feature}

        date_str = row["daily_date"]
        counts = {f: row[f"count_{f}"] for f in FEATURES}
        limits = {f: row[f"limit_{f}"] for f in FEATURES}

        if date_str != today:
            counts = {f: 0 for f in FEATURES}
            date_str = today

        used = counts[feature]
        limit = limits[feature]

        if limit != -1 and used >= limit:
            return {"allowed": False, "used": used, "limit": limit, "feature": feature}

        counts[feature] = used + 1
        conn.execute(
            """
            UPDATE users SET
                daily_date = ?,
                count_outline = ?, count_translate = ?, count_qa = ?,
                count_burden = ?, count_asr = ?
            WHERE username = ?
            """,
            (
                date_str,
                counts["outline"],
                counts["translate"],
                counts["qa"],
                counts["burden"],
                counts["asr"],
                username,
            ),
        )
        conn.commit()
        return {
            "allowed": True,
            "used": counts[feature],
            "limit": limit,
            "feature": feature,
        }
    finally:
        conn.close()


def get_daily_usage(username: str) -> dict:
    """只返回 outline / translate / qa 三组用量，不递增。"""
    today = _today()
    conn = _connect()
    try:
        row = conn.execute(
            """
            SELECT daily_date,
                   count_outline, limit_outline,
                   count_translate, limit_translate,
                   count_qa, limit_qa
            FROM users WHERE username = ?
            """,
            (username,),
        ).fetchone()
        if not row:
            return {
                "outline": {"used": 0, "limit": 0},
                "translate": {"used": 0, "limit": 0},
                "qa": {"used": 0, "limit": 0},
            }

        reset = row["daily_date"] != today
        result = {}
        for feat in ("outline", "translate", "qa"):
            used = 0 if reset else row[f"count_{feat}"]
            result[feat] = {"used": used, "limit": row[f"limit_{feat}"]}
        return result
    finally:
        conn.close()


def create_invite_code(code: str) -> bool:
    code = (code or "").strip()
    if not code:
        return False
    try:
        with _connect() as conn:
            conn.execute("INSERT INTO invite_codes(code, used) VALUES(?, 0)", (code,))
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def use_invite_code(code: str, username: str) -> bool:
    code = (code or "").strip()
    username = (username or "").strip()
    if not code or not username:
        return False
    with _connect() as conn:
        cur = conn.execute(
            """
            UPDATE invite_codes
            SET used = 1, used_by = ?
            WHERE code = ? AND used = 0
            """,
            (username, code),
        )
        conn.commit()
        return cur.rowcount > 0


def get_user(username: str) -> dict[str, Any] | None:
    username = (username or "").strip()
    if not username:
        return None
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, username, created_at, is_admin
            FROM users WHERE username = ?
            """,
            (username,),
        ).fetchone()
    if not row:
        return None
    return {
        "id": row["id"],
        "username": row["username"],
        "created_at": row["created_at"],
        "is_admin": bool(row["is_admin"]),
    }


def create_user(username: str, password: str, *, is_admin: bool = False) -> bool:
    username = (username or "").strip()
    password = password or ""
    if not username or not password:
        return False
    limits = _default_limits()
    hashed = _hash_password(password)
    admin_flag = 1 if is_admin else 0
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO users(
                    username, hashed_password, is_admin,
                    limit_outline, limit_translate, limit_qa, limit_burden, limit_asr
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    username,
                    hashed,
                    admin_flag,
                    limits["outline"],
                    limits["translate"],
                    limits["qa"],
                    limits["burden"],
                    limits["asr"],
                ),
            )
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def set_admin(username: str, is_admin: bool) -> bool:
    username = (username or "").strip()
    if not username:
        return False
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE users SET is_admin = ? WHERE username = ?",
            (1 if is_admin else 0, username),
        )
        conn.commit()
        return cur.rowcount > 0


def set_user_daily_limit(username: str, feature: str, daily_limit: int) -> bool:
    """设置指定用户某功能的每日上限。"""
    if feature not in FEATURES:
        raise ValueError(f"未知 feature: {feature!r}")
    limit_col = f"limit_{feature}"
    with _connect() as conn:
        cur = conn.execute(
            f"UPDATE users SET {limit_col} = ? WHERE username = ?",
            (daily_limit, username),
        )
        conn.commit()
        return cur.rowcount > 0


def verify_user(username: str, password: str) -> bool:
    username = (username or "").strip()
    password = password or ""
    if not username or not password:
        return False
    with _connect() as conn:
        row = conn.execute(
            "SELECT hashed_password FROM users WHERE username = ?",
            (username,),
        ).fetchone()
    if not row:
        return False
    return _verify_password(password, row["hashed_password"])


def create_token(username: str) -> str:
    username = (username or "").strip()
    if not username:
        raise ValueError("username 不能为空")
    user = get_user(username)
    if not user:
        raise ValueError("用户不存在")
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": username,
        "is_admin": user["is_admin"],
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=TOKEN_EXPIRE_DAYS)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict[str, Any] | None:
    """解析 JWT 并返回当前用户对象（is_admin 以数据库为准）。"""
    token = (token or "").strip()
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        sub = payload.get("sub")
        if not isinstance(sub, str) or not sub.strip():
            return None
        return get_user(sub.strip())
    except JWTError:
        return None


def get_current_user_optional(request: Request) -> dict[str, Any] | None:
    """FastAPI 依赖：JWT 可选，无效或缺失时返回 None。"""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth.split(" ", 1)[1].strip()
    return verify_token(token)


def get_current_user(request: Request) -> dict[str, Any]:
    """FastAPI 依赖：从 Authorization Bearer 解析 CN JWT，返回用户 dict。"""
    from fastapi import HTTPException

    user = get_current_user_optional(request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录或 token 无效或已过期")
    return user


def _check_admin_access(
    request: Request,
    x_admin_token: str | None = None,
    current_user: dict[str, Any] | None = None,
) -> bool:
    """管理员鉴权核心：X-Admin-Token 或 is_admin JWT 二选一（OR）。"""
    from fastapi import HTTPException

    if current_user is None:
        current_user = get_current_user_optional(request)
    if x_admin_token is None:
        x_admin_token = request.headers.get("X-Admin-Token")

    admin_token = os.environ.get("CN_ADMIN_TOKEN", "")
    if x_admin_token and admin_token and x_admin_token == admin_token:
        return True
    if current_user and current_user.get("is_admin"):
        return True
    raise HTTPException(status_code=403, detail="需要管理员权限")


def _make_verify_admin_access_dep():
    from fastapi import Depends, Header

    def _dep(
        request: Request,
        x_admin_token: str | None = Header(None),
        current_user: dict[str, Any] | None = Depends(get_current_user_optional),
    ) -> bool:
        return _check_admin_access(
            request,
            x_admin_token=x_admin_token,
            current_user=current_user,
        )

    return _dep


# FastAPI 路由使用 Depends(verify_admin_access)
verify_admin_access = _make_verify_admin_access_dep()


def quota_exceeded_message(feature: str, limit: int) -> str:
    label = FEATURE_LABELS.get(feature, feature)
    return f"今日{label}次数已达上限（{limit}次），请明天再来"


def list_users() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, username, created_at, is_admin
            FROM users
            ORDER BY id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def get_user_feature_limits(username: str) -> dict[str, Any] | None:
    """返回指定用户五组功能的 limit 与当日 usage（管理员用）。"""
    username = (username or "").strip()
    if not username:
        return None
    today = _today()
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT daily_date,
                   count_outline, limit_outline,
                   count_translate, limit_translate,
                   count_qa, limit_qa,
                   count_burden, limit_burden,
                   count_asr, limit_asr
            FROM users WHERE username = ?
            """,
            (username,),
        ).fetchone()
    if not row:
        return None
    reset = row["daily_date"] != today
    limits: dict[str, int] = {}
    usage: dict[str, dict[str, int]] = {}
    for feat in FEATURES:
        lim = row[f"limit_{feat}"]
        used = 0 if reset else row[f"count_{feat}"]
        limits[feat] = lim
        usage[feat] = {"used": used, "limit": lim}
    return {"username": username, "limits": limits, "usage": usage}


def delete_user(username: str) -> bool:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.commit()
        return cur.rowcount > 0


def list_invite_codes() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, code, used, used_by, created_at
            FROM invite_codes
            ORDER BY id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]
