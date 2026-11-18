# -*- coding: utf-8 -*-
"""账号、邀请码、用量、反馈（SQLite + JWT）。改造自 3.0 back_qa/qa/auth.py。"""

from __future__ import annotations

import hmac
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional
from zoneinfo import ZoneInfo

import bcrypt
from jose import JWTError, jwt

JWT_ALGORITHM = "HS256"


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


class AuthStore:
    def __init__(
        self,
        db_path: Path,
        *,
        jwt_secret: str,
        jwt_expire_days: int = 7,
        daily_limit_default: int = 30,
        tz_name: str = "UTC",
        admin_token: str = "",
    ) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.jwt_secret = jwt_secret
        self.jwt_expire_days = jwt_expire_days
        self.daily_limit_default = daily_limit_default
        self.tz_name = tz_name
        self.admin_token = admin_token or ""
        self.init_db()

    def _tz(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.tz_name)
        except Exception:
            return ZoneInfo("UTC")

    def today_str(self) -> str:
        return datetime.now(self._tz()).strftime("%Y-%m-%d")

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now')),
                    daily_limit INTEGER NOT NULL DEFAULT 30,
                    disabled INTEGER NOT NULL DEFAULT 0,
                    is_admin INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS invite_codes (
                    code TEXT PRIMARY KEY,
                    note TEXT NOT NULL DEFAULT '',
                    max_uses INTEGER NOT NULL DEFAULT 1,
                    used_count INTEGER NOT NULL DEFAULT 0,
                    expires_at TEXT,
                    disabled INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL DEFAULT (datetime('now'))
                );
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    request_id TEXT NOT NULL,
                    rating INTEGER NOT NULL,
                    comment TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );
                CREATE TABLE IF NOT EXISTS usage (
                    day TEXT NOT NULL,
                    user_id INTEGER NOT NULL,
                    count INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (day, user_id),
                    FOREIGN KEY(user_id) REFERENCES users(id)
                );
                """
            )
            conn.commit()

    # ---- invite ----
    def create_invite(
        self,
        code: str,
        *,
        note: str = "",
        max_uses: int = 1,
        expires_at: Optional[str] = None,
    ) -> bool:
        code = (code or "").strip()
        if not code or max_uses < 1:
            return False
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO invite_codes(code, note, max_uses, used_count, expires_at, disabled)
                    VALUES(?, ?, ?, 0, ?, 0)
                    """,
                    (code, note or "", max_uses, expires_at),
                )
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def list_invites(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT code, note, max_uses, used_count, expires_at, disabled, created_at
                FROM invite_codes ORDER BY created_at DESC
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def disable_invite(self, code: str) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE invite_codes SET disabled = 1 WHERE code = ?",
                ((code or "").strip(),),
            )
            conn.commit()
            return cur.rowcount > 0

    def _invite_usable(self, conn: sqlite3.Connection, code: str) -> bool:
        row = conn.execute(
            "SELECT max_uses, used_count, expires_at, disabled FROM invite_codes WHERE code = ?",
            (code,),
        ).fetchone()
        if not row:
            return False
        if int(row["disabled"]) != 0:
            return False
        if int(row["used_count"]) >= int(row["max_uses"]):
            return False
        exp = row["expires_at"]
        if exp:
            try:
                exp_dt = datetime.fromisoformat(str(exp).replace("Z", "+00:00"))
                if exp_dt.tzinfo is None:
                    exp_dt = exp_dt.replace(tzinfo=timezone.utc)
                if datetime.now(timezone.utc) > exp_dt:
                    return False
            except Exception:
                return False
        return True

    def use_invite(self, code: str) -> bool:
        code = (code or "").strip()
        if not code:
            return False
        with self._connect() as conn:
            if not self._invite_usable(conn, code):
                return False
            cur = conn.execute(
                """
                UPDATE invite_codes
                SET used_count = used_count + 1
                WHERE code = ? AND disabled = 0 AND used_count < max_uses
                """,
                (code,),
            )
            conn.commit()
            return cur.rowcount > 0

    # ---- users ----
    def create_user(self, username: str, password: str, *, daily_limit: Optional[int] = None) -> bool:
        username = (username or "").strip()
        password = password or ""
        if not username or not password:
            return False
        limit = self.daily_limit_default if daily_limit is None else int(daily_limit)
        hashed = _hash_password(password)
        try:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO users(username, password_hash, daily_limit, disabled, is_admin)
                    VALUES(?, ?, ?, 0, 0)
                    """,
                    (username, hashed, limit),
                )
                conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def register(self, invite_code: str, username: str, password: str) -> tuple[bool, str]:
        if not self.use_invite(invite_code):
            return False, "邀请码无效或已使用"
        if not self.create_user(username, password):
            return False, "用户名已存在"
        return True, ""

    def verify_user(self, username: str, password: str) -> bool:
        username = (username or "").strip()
        password = password or ""
        if not username or not password:
            return False
        with self._connect() as conn:
            row = conn.execute(
                "SELECT password_hash, disabled FROM users WHERE username = ?",
                (username,),
            ).fetchone()
        if not row or int(row["disabled"]) != 0:
            return False
        return _verify_password(password, row["password_hash"])

    def get_user(self, username: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT id, username, created_at, daily_limit, disabled, is_admin
                FROM users WHERE username = ?
                """,
                ((username or "").strip(),),
            ).fetchone()
        return dict(row) if row else None

    def list_users(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, username, created_at, daily_limit, disabled, is_admin
                FROM users ORDER BY id DESC
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def set_daily_limit(self, username: str, daily_limit: int) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE users SET daily_limit = ? WHERE username = ?",
                (int(daily_limit), (username or "").strip()),
            )
            conn.commit()
            return cur.rowcount > 0

    def set_disabled(self, username: str, disabled: bool) -> bool:
        with self._connect() as conn:
            cur = conn.execute(
                "UPDATE users SET disabled = ? WHERE username = ?",
                (1 if disabled else 0, (username or "").strip()),
            )
            conn.commit()
            return cur.rowcount > 0

    def delete_user(self, username: str) -> bool:
        """删除用户（对照 3.0）；不存在返回 False。"""
        username = (username or "").strip()
        if not username:
            return False
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id FROM users WHERE username = ?", (username,)
            ).fetchone()
            if not row:
                return False
            uid = int(row["id"])
            conn.execute("DELETE FROM usage WHERE user_id = ?", (uid,))
            conn.execute("UPDATE feedback SET user_id = NULL WHERE user_id = ?", (uid,))
            cur = conn.execute("DELETE FROM users WHERE id = ?", (uid,))
            conn.commit()
            return cur.rowcount > 0

    # ---- usage ----
    def check_and_increment_usage(self, username: str) -> dict:
        user = self.get_user(username)
        if not user or int(user["disabled"]) != 0:
            return {"allowed": False, "used": 0, "limit": 0}
        day = self.today_str()
        uid = int(user["id"])
        limit = int(user["daily_limit"])
        with self._connect() as conn:
            row = conn.execute(
                "SELECT count FROM usage WHERE day = ? AND user_id = ?",
                (day, uid),
            ).fetchone()
            used = int(row["count"]) if row else 0
            if used >= limit:
                return {"allowed": False, "used": used, "limit": limit}
            if row:
                conn.execute(
                    "UPDATE usage SET count = count + 1 WHERE day = ? AND user_id = ?",
                    (day, uid),
                )
            else:
                conn.execute(
                    "INSERT INTO usage(day, user_id, count) VALUES(?, ?, 1)",
                    (day, uid),
                )
            conn.commit()
            return {"allowed": True, "used": used + 1, "limit": limit}

    def get_usage(self, username: str) -> dict:
        user = self.get_user(username)
        if not user:
            return {"used": 0, "limit": 0, "day": self.today_str()}
        day = self.today_str()
        with self._connect() as conn:
            row = conn.execute(
                "SELECT count FROM usage WHERE day = ? AND user_id = ?",
                (day, int(user["id"])),
            ).fetchone()
        return {
            "used": int(row["count"]) if row else 0,
            "limit": int(user["daily_limit"]),
            "day": day,
        }

    def usage_stats(self, day: Optional[str] = None) -> list[dict]:
        day = day or self.today_str()
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT u.username, COALESCE(x.count, 0) AS count, u.daily_limit
                FROM users u
                LEFT JOIN usage x ON x.user_id = u.id AND x.day = ?
                ORDER BY u.username
                """,
                (day,),
            ).fetchall()
        return [{"day": day, **dict(r)} for r in rows]

    # ---- feedback ----
    def add_feedback(
        self,
        *,
        user_id: Optional[int],
        request_id: str,
        rating: int,
        comment: str = "",
    ) -> int:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO feedback(user_id, request_id, rating, comment, created_at)
                VALUES(?, ?, ?, ?, ?)
                """,
                (user_id, request_id, int(rating), comment or "", now),
            )
            conn.commit()
            return int(cur.lastrowid)

    def list_feedback(self, limit: int = 50) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT f.id, f.user_id, u.username, f.request_id, f.rating, f.comment, f.created_at
                FROM feedback f
                LEFT JOIN users u ON u.id = f.user_id
                ORDER BY f.id DESC
                LIMIT ?
                """,
                (int(limit),),
            ).fetchall()
        return [dict(r) for r in rows]

    def feedback_stats(self) -> dict[str, Any]:
        """对照 3.0 get_feedback_stats：👍/👎/好评率 + 最近差评。"""
        with self._connect() as conn:
            up = conn.execute(
                "SELECT COUNT(1) AS c FROM feedback WHERE rating = 1"
            ).fetchone()
            down = conn.execute(
                "SELECT COUNT(1) AS c FROM feedback WHERE rating = -1"
            ).fetchone()
            rows = conn.execute(
                """
                SELECT f.request_id, u.username, f.comment, f.created_at
                FROM feedback f
                LEFT JOIN users u ON u.id = f.user_id
                WHERE f.rating = -1
                ORDER BY f.id DESC
                LIMIT 20
                """
            ).fetchall()
        thumbs_up = int(up["c"] if up else 0)
        thumbs_down = int(down["c"] if down else 0)
        total = thumbs_up + thumbs_down
        rate = round(thumbs_up / total, 4) if total else 0.0
        recent_down = []
        for r in rows:
            recent_down.append(
                {
                    "request_id": r["request_id"],
                    "username": r["username"] or "",
                    "question": r["comment"] or "",  # qa4 反馈表无原文；用 comment 占位
                    "answer": "",
                    "created_at": r["created_at"],
                }
            )
        return {
            "thumbs_up": thumbs_up,
            "thumbs_down": thumbs_down,
            "rate": rate,
            "recent_down": recent_down,
        }

    # ---- JWT / admin ----
    def create_token(self, username: str) -> str:
        username = (username or "").strip()
        if not username:
            raise ValueError("username 不能为空")
        now = datetime.now(timezone.utc)
        payload: dict[str, Any] = {
            "sub": username,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(days=self.jwt_expire_days)).timestamp()),
        }
        return jwt.encode(payload, self.jwt_secret, algorithm=JWT_ALGORITHM)

    def verify_token(self, token: str) -> Optional[str]:
        token = (token or "").strip()
        if not token:
            return None
        try:
            payload = jwt.decode(token, self.jwt_secret, algorithms=[JWT_ALGORITHM])
            sub = payload.get("sub")
            return str(sub) if isinstance(sub, str) and sub.strip() else None
        except JWTError:
            return None

    def check_admin_token(self, provided: str) -> bool:
        expected = self.admin_token or ""
        if not expected:
            return False
        a = (provided or "").encode("utf-8")
        b = expected.encode("utf-8")
        if len(a) != len(b):
            # 仍做一次 compare 防时序；长度不同直接 False
            hmac.compare_digest(a, a)
            return False
        return hmac.compare_digest(a, b)
