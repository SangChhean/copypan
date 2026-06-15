# -*- coding: utf-8 -*-
"""CN 站资料下载：分类与 PDF 管理。"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from back_cn.auth import get_current_user, verify_admin_access

logger = logging.getLogger(__name__)

_repo_root = Path(__file__).resolve().parents[2]
_raw_dir = os.getenv("CN_MATERIALS_DIR", "back_cn/uploads/cn_materials")
MATERIALS_DIR = Path(_raw_dir) if Path(_raw_dir).is_absolute() else _repo_root / _raw_dir
MAX_MB = int(os.getenv("CN_MATERIALS_MAX_MB", "200"))
MAX_BYTES = MAX_MB * 1024 * 1024

router = APIRouter(prefix="/api/cn/materials", tags=["materials"])

_DIR_NAME_RE = re.compile(r"^[a-zA-Z0-9_-]+$")


def _db_path() -> Path:
    from back_cn.auth import DB_PATH

    return DB_PATH


def _connect():
    import sqlite3

    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _require_user(request: Request) -> dict:
    return get_current_user(request)


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    dir_name: str = Field(..., min_length=1, max_length=100)
    sort_order: int = 0


@router.get("/categories")
def list_categories(_user: dict = Depends(_require_user)):
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT mc.id, mc.name, mc.dir_name, mc.sort_order,
                   COUNT(m.id) AS files_count
            FROM material_categories mc
            LEFT JOIN materials m ON m.category_id = mc.id
            GROUP BY mc.id
            ORDER BY mc.sort_order, mc.id
            """
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("")
def list_materials(category_id: int, _user: dict = Depends(_require_user)):
    with _connect() as conn:
        cat = conn.execute(
            "SELECT id FROM material_categories WHERE id = ?", (category_id,)
        ).fetchone()
        if not cat:
            raise HTTPException(status_code=404, detail="分类不存在")
        rows = conn.execute(
            """
            SELECT id, display_name, size_bytes, created_at
            FROM materials
            WHERE category_id = ?
            ORDER BY created_at DESC
            """,
            (category_id,),
        ).fetchall()
    return [dict(r) for r in rows]


@router.get("/{material_id}/download")
def download_material(material_id: int, _user: dict = Depends(_require_user)):
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT m.display_name, m.stored_name, c.dir_name
            FROM materials m
            JOIN material_categories c ON c.id = m.category_id
            WHERE m.id = ?
            """,
            (material_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="文件不存在")

    file_path = MATERIALS_DIR / row["dir_name"] / row["stored_name"]
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件暂时不可用")

    display = row["display_name"] or "download"
    if not display.lower().endswith(".pdf"):
        display = f"{display}.pdf"

    # 本地开发：CN_MATERIALS_DIRECT_DOWNLOAD=1 时直接返回 PDF 实体；生产由 Nginx X-Accel-Redirect 传文件
    if os.getenv("CN_MATERIALS_DIRECT_DOWNLOAD", "").lower() in ("1", "true", "yes"):
        from fastapi.responses import FileResponse

        return FileResponse(
            path=file_path,
            media_type="application/pdf",
            filename=display,
        )

    # 生产由 Nginx internal location 处理实体传输；本地无 Nginx 时返回空 200 + 头，属预期
    return Response(
        status_code=200,
        headers={
            "X-Accel-Redirect": f"/protected_materials/{row['dir_name']}/{row['stored_name']}",
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(display)}",
            "Content-Type": "application/pdf",
        },
    )


@router.post("/categories", status_code=201)
def create_category(
    body: CategoryCreate,
    _: bool = Depends(verify_admin_access),
):
    name = body.name.strip()
    dir_name = body.dir_name.strip()
    if not _DIR_NAME_RE.match(dir_name):
        raise HTTPException(
            status_code=422,
            detail="dir_name 只允许 ASCII 字母数字下划线横线",
        )
    created_at = _utc_now()
    try:
        with _connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO material_categories(name, dir_name, sort_order, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (name, dir_name, body.sort_order, created_at),
            )
            conn.commit()
            cat_id = cur.lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="分类名或目录名已存在") from None

    cat_dir = MATERIALS_DIR / dir_name
    cat_dir.mkdir(parents=True, exist_ok=True)
    return {
        "id": cat_id,
        "name": name,
        "dir_name": dir_name,
        "sort_order": body.sort_order,
        "created_at": created_at,
        "files_count": 0,
    }


@router.delete("/categories/{category_id}")
def delete_category(category_id: int, _: bool = Depends(verify_admin_access)):
    with _connect() as conn:
        cat = conn.execute(
            "SELECT id, dir_name FROM material_categories WHERE id = ?", (category_id,)
        ).fetchone()
        if not cat:
            raise HTTPException(status_code=404, detail="分类不存在")
        cnt = conn.execute(
            "SELECT COUNT(*) AS n FROM materials WHERE category_id = ?", (category_id,)
        ).fetchone()["n"]
        if cnt > 0:
            raise HTTPException(status_code=400, detail="请先删除该分类下的所有文件")
        conn.execute("DELETE FROM material_categories WHERE id = ?", (category_id,))
        conn.commit()
        dir_name = cat["dir_name"]

    cat_dir = MATERIALS_DIR / dir_name
    try:
        cat_dir.rmdir()
    except OSError:
        pass
    return {"deleted": True}


@router.post("/upload")
async def upload_material(
    category_id: int = Form(...),
    file: UploadFile = File(...),
    _: bool = Depends(verify_admin_access),
):
    with _connect() as conn:
        cat = conn.execute(
            "SELECT id, dir_name FROM material_categories WHERE id = ?", (category_id,)
        ).fetchone()
    if not cat:
        raise HTTPException(status_code=404, detail="分类不存在")

    content_type = (file.content_type or "").lower()
    if not content_type.startswith("application/pdf"):
        raise HTTPException(status_code=422, detail="只允许上传 PDF 文件")

    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"文件超过 {MAX_MB}MB 限制",
        )

    stored_name = f"{uuid.uuid4()}.pdf"
    display_name = (file.filename or stored_name).strip() or stored_name
    dest_dir = MATERIALS_DIR / cat["dir_name"]
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / stored_name
    created_at = _utc_now()

    try:
        dest_path.write_bytes(content)
        with _connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO materials(category_id, display_name, stored_name, size_bytes, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (category_id, display_name, stored_name, len(content), created_at),
            )
            conn.commit()
            material_id = cur.lastrowid
    except Exception:
        try:
            if dest_path.exists():
                dest_path.unlink()
        except OSError:
            pass
        raise

    return {
        "id": material_id,
        "category_id": category_id,
        "display_name": display_name,
        "stored_name": stored_name,
        "size_bytes": len(content),
        "created_at": created_at,
    }


@router.delete("/{material_id}")
def delete_material(material_id: int, _: bool = Depends(verify_admin_access)):
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT m.stored_name, c.dir_name
            FROM materials m
            JOIN material_categories c ON c.id = m.category_id
            WHERE m.id = ?
            """,
            (material_id,),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="文件不存在")
        conn.execute("DELETE FROM materials WHERE id = ?", (material_id,))
        conn.commit()

    file_path = MATERIALS_DIR / row["dir_name"] / row["stored_name"]
    try:
        file_path.unlink(missing_ok=True)
    except OSError:
        pass
    return {"deleted": True}
