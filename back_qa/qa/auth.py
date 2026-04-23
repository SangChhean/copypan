# -*- coding: utf-8 -*-
"""QA 用户与鉴权数据层（SQLite + JWT）。"""

from __future__ import annotations

import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import bcrypt
from jose import JWTError, jwt

DB_PATH = Path(__file__).resolve().parent / "qa_users.db"
JWT_ALGORITHM = "HS256"
TOKEN_EXPIRE_DAYS = 7

JWT_SECRET = os.environ.get("QA_JWT_SECRET", "").strip()
if not JWT_SECRET:
    raise RuntimeError("未配置 QA_JWT_SECRET")

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
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                hashed_password TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
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
        conn.commit()


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


def create_user(username: str, password: str) -> bool:
    username = (username or "").strip()
    password = password or ""
    if not username or not password:
        return False
    hashed = _hash_password(password)
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO users(username, hashed_password) VALUES(?, ?)",
                (username, hashed),
            )
            conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


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
    now = datetime.now(timezone.utc)
    payload: dict[str, Any] = {
        "sub": username,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=TOKEN_EXPIRE_DAYS)).timestamp()),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> str | None:
    token = (token or "").strip()
    if not token:
        return None
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        sub = payload.get("sub")
        return str(sub) if isinstance(sub, str) and sub.strip() else None
    except JWTError:
        return None


def list_users() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, username, created_at
            FROM users
            ORDER BY id DESC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def delete_user(username: str) -> bool:
    """删除用户，不存在返回 False。"""
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


# 模块加载即确保表存在（满足“启动时自动建表”）
init_db()

