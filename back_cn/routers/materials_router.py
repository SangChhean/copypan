# -*- coding: utf-8 -*-
"""CN 站资料下载：分类与 PDF 管理（支持树形分类）。"""
from __future__ import annotations

import io
import logging
import mimetypes
import os
import re

def _natural_sort_key(s: str):
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r"(\d+)", s)]

import sqlite3
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse
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
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    return conn


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _require_user(request: Request) -> dict:
    return get_current_user(request)


def _to_pinyin_dir(name: str) -> str:
    """将中文名转为拼音 dir_name，非 ASCII 字符用拼音替换，其余保留。"""
    try:
        from pypinyin import lazy_pinyin

        chars = lazy_pinyin(name)
        result = "_".join(chars)
    except ImportError:
        result = name
    result = re.sub(r"[^a-zA-Z0-9_-]", "_", result)
    result = re.sub(r"_+", "_", result).strip("_")
    return result or "_upload"


def _build_tree(rows: list[dict]) -> list[dict]:
    """将平铺分类列表构建为树形结构。"""
    by_id = {r["id"]: {**r, "children": []} for r in rows}
    roots = []
    for node in by_id.values():
        pid = node.get("parent_id")
        if pid and pid in by_id:
            by_id[pid]["children"].append(node)
        else:
            roots.append(node)

    def _sort_nodes(nodes: list[dict]) -> None:
        nodes.sort(
            key=lambda n: (
                n.get("sort_order") or 0,
                _natural_sort_key(n.get("name") or ""),
                n["id"],
            )
        )
        for n in nodes:
            if n["children"]:
                _sort_nodes(n["children"])

    _sort_nodes(roots)
    return roots


def _get_all_descendant_ids(category_id: int, conn) -> list[int]:
    """递归获取某分类及其所有子分类的 id 列表。"""
    result = [category_id]
    children = conn.execute(
        "SELECT id FROM material_categories WHERE parent_id = ?", (category_id,)
    ).fetchall()
    for child in children:
        result.extend(_get_all_descendant_ids(child["id"], conn))
    return result


def _ensure_category_path(path_parts: list[str], conn, type: str = "pastoral", parent_id: int | None = None) -> int:
    """
    按路径层级递归确保分类存在，返回最末层分类 id。
    path_parts: 如 ["旧约", "诗篇"]
    """
    cat_id = None
    for part in path_parts:
        part = part.strip()
        if not part:
            continue
        dir_name = _to_pinyin_dir(part)
        row = conn.execute(
            "SELECT id FROM material_categories WHERE dir_name = ? AND (parent_id IS ? OR parent_id = ?) AND type = ?",
            (dir_name, parent_id, parent_id, type),
        ).fetchone()
        if row:
            cat_id = row["id"]
        else:
            try:
                cur = conn.execute(
                    """
                    INSERT INTO material_categories(name, dir_name, parent_id, sort_order, created_at, type)
                    VALUES (?, ?, ?, 0, ?, ?)
                    """,
                    (part, dir_name, parent_id, _utc_now(), type),
                )
                conn.commit()
                cat_id = cur.lastrowid
            except sqlite3.IntegrityError:
                row = conn.execute(
                    "SELECT id FROM material_categories WHERE dir_name = ? AND (parent_id IS ? OR parent_id = ?) AND type = ?",
                    (dir_name, parent_id, parent_id, type),
                ).fetchone()
                cat_id = row["id"]
            physical_dir = MATERIALS_DIR / f"cat_{cat_id}"
            physical_dir.mkdir(parents=True, exist_ok=True)
        parent_id = cat_id
    return cat_id


# ── 读取接口 ──────────────────────────────────────────────


@router.get("/categories")
def list_categories(type: str | None = None, _user: dict = Depends(_require_user)):
    with _connect() as conn:
        if type:
            rows = conn.execute(
                """
                SELECT mc.id, mc.name, mc.dir_name, mc.parent_id, mc.sort_order,
                       mc.created_at, mc.type,
                       COUNT(m.id) AS files_count
                FROM material_categories mc
                LEFT JOIN materials m ON m.category_id = mc.id
                WHERE mc.type = ?
                GROUP BY mc.id
                ORDER BY mc.sort_order, mc.name COLLATE NOCASE, mc.id
                """,
                (type,),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT mc.id, mc.name, mc.dir_name, mc.parent_id, mc.sort_order,
                       mc.created_at, mc.type,
                       COUNT(m.id) AS files_count
                FROM material_categories mc
                LEFT JOIN materials m ON m.category_id = mc.id
                GROUP BY mc.id
                ORDER BY mc.sort_order, mc.name COLLATE NOCASE, mc.id
                """
            ).fetchall()
    flat = [dict(r) for r in rows]
    return _build_tree(flat)


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
            ORDER BY display_name COLLATE NOCASE ASC
            """,
            (category_id,),
        ).fetchall()
    rows_list = [dict(r) for r in rows]
    rows_list.sort(key=lambda x: _natural_sort_key(x.get("display_name") or ""))
    return rows_list


@router.get("/{material_id}/download")
def download_material(material_id: int, _user: dict = Depends(_require_user)):
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT m.display_name, m.stored_name, c.id AS category_id
            FROM materials m
            JOIN material_categories c ON c.id = m.category_id
            WHERE m.id = ?
            """,
            (material_id,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="文件不存在")
    file_path = MATERIALS_DIR / f"cat_{row['category_id']}" / row["stored_name"]
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="文件暂时不可用")
    display = row["display_name"] or row["stored_name"] or "download"
    mime_type, _ = mimetypes.guess_type(display)
    if not mime_type:
        mime_type = "application/octet-stream"
    if os.getenv("CN_MATERIALS_DIRECT_DOWNLOAD", "").lower() in ("1", "true", "yes"):
        from fastapi.responses import FileResponse

        return FileResponse(path=file_path, media_type=mime_type, filename=display)
    return Response(
        status_code=200,
        headers={
            "X-Accel-Redirect": f"/protected_materials/cat_{row['category_id']}/{row['stored_name']}",
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(display)}",
            "Content-Type": mime_type,
        },
    )


@router.get("/categories/{category_id}/zip")
def download_category_zip(category_id: int, _user: dict = Depends(_require_user)):
    """打包下载某分类及其所有子分类下的全部 PDF。"""
    with _connect() as conn:
        cat = conn.execute(
            "SELECT name FROM material_categories WHERE id = ?", (category_id,)
        ).fetchone()
        if not cat:
            raise HTTPException(status_code=404, detail="分类不存在")
        cat_name = cat["name"]
        all_ids = _get_all_descendant_ids(category_id, conn)
        placeholders = ",".join("?" * len(all_ids))
        rows = conn.execute(
            f"""
            SELECT m.display_name, m.stored_name, c.id AS category_id, c.name as cat_name
            FROM materials m
            JOIN material_categories c ON c.id = m.category_id
            WHERE m.category_id IN ({placeholders})
            ORDER BY c.id, m.created_at
            """,
            all_ids,
        ).fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="该分类下没有文件")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for row in rows:
            file_path = MATERIALS_DIR / f"cat_{row['category_id']}" / row["stored_name"]
            if not file_path.is_file():
                continue
            display = row["display_name"] or row["stored_name"]
            arc_name = f"{row['cat_name']}/{display}"
            zf.write(file_path, arc_name)
    buf.seek(0)
    zip_name = quote(f"{cat_name}.zip")
    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{zip_name}"},
    )


# ── 写入接口（管理员）────────────────────────────────────


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    dir_name: str = Field("", max_length=100)
    parent_id: int | None = None
    sort_order: int = 0
    type: str = "pastoral"


class CategoryRename(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)


@router.post("/categories", status_code=201)
def create_category(body: CategoryCreate, _: bool = Depends(verify_admin_access)):
    name = body.name.strip()
    dir_name = body.dir_name.strip() if body.dir_name.strip() else _to_pinyin_dir(name)
    if not _DIR_NAME_RE.match(dir_name):
        raise HTTPException(status_code=422, detail="dir_name 只允许 ASCII 字母数字下划线横线")
    created_at = _utc_now()
    try:
        with _connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO material_categories(name, dir_name, parent_id, sort_order, created_at, type)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (name, dir_name, body.parent_id, body.sort_order, created_at, body.type),
            )
            conn.commit()
            cat_id = cur.lastrowid
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="同一父分类下已存在相同目录名") from None
    cat_dir = MATERIALS_DIR / f"cat_{cat_id}"
    cat_dir.mkdir(parents=True, exist_ok=True)
    return {
        "id": cat_id,
        "name": name,
        "dir_name": dir_name,
        "parent_id": body.parent_id,
        "sort_order": body.sort_order,
        "created_at": created_at,
        "files_count": 0,
        "children": [],
    }


@router.patch("/categories/{category_id}")
def rename_category(category_id: int, body: CategoryRename, _: bool = Depends(verify_admin_access)):
    name = body.name.strip()
    try:
        with _connect() as conn:
            row = conn.execute(
                "SELECT id FROM material_categories WHERE id = ?", (category_id,)
            ).fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="分类不存在")
            conn.execute(
                "UPDATE material_categories SET name = ? WHERE id = ?", (name, category_id)
            )
            conn.commit()
    except sqlite3.IntegrityError:
        raise HTTPException(status_code=409, detail="分类名已存在") from None
    return {"id": category_id, "name": name}


@router.delete("/categories/{category_id}")
def delete_category(category_id: int, _: bool = Depends(verify_admin_access)):
    with _connect() as conn:
        cat = conn.execute(
            "SELECT id FROM material_categories WHERE id = ?", (category_id,)
        ).fetchone()
        if not cat:
            raise HTTPException(status_code=404, detail="分类不存在")
        all_ids = _get_all_descendant_ids(category_id, conn)
        # 删除所有子分类下的文件（磁盘 + 数据库）
        for cid in all_ids:
            file_rows = conn.execute(
                "SELECT stored_name FROM materials WHERE category_id = ?", (cid,)
            ).fetchall()
            for f in file_rows:
                try:
                    (MATERIALS_DIR / f"cat_{cid}" / f["stored_name"]).unlink(missing_ok=True)
                except Exception:
                    pass
            conn.execute("DELETE FROM materials WHERE category_id = ?", (cid,))
        # 从子到父依次删除分类记录
        for cid in reversed(all_ids):
            conn.execute("DELETE FROM material_categories WHERE id = ?", (cid,))
            try:
                import shutil
                shutil.rmtree(MATERIALS_DIR / f"cat_{cid}", ignore_errors=True)
            except Exception:
                pass
        conn.commit()
    return {"deleted": True}


@router.post("/upload")
async def upload_material(
    category_id: int = Form(...),
    file: UploadFile = File(...),
    _: bool = Depends(verify_admin_access),
):
    with _connect() as conn:
        cat = conn.execute(
            "SELECT id FROM material_categories WHERE id = ?", (category_id,)
        ).fetchone()
    if not cat:
        raise HTTPException(status_code=404, detail="分类不存在")
    content = await file.read()
    if len(content) > MAX_BYTES:
        raise HTTPException(status_code=413, detail=f"文件超过 {MAX_MB}MB 限制")
    original_name = (file.filename or "upload").strip() or "upload"
    ext = os.path.splitext(original_name)[1] or ""
    stored_name = f"{uuid.uuid4()}{ext}"
    display_name = original_name
    dest_dir = MATERIALS_DIR / f"cat_{category_id}"
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


@router.post("/batch_upload")
async def batch_upload_materials(
    files: list[UploadFile] = File(...),
    type: str = Form("pastoral"),
    parent_category_id: int | None = Form(None),
    _: bool = Depends(verify_admin_access),
):
    """按 webkitRelativePath 还原完整路径层级，自动建立所有中间层分类。"""
    results = []
    errors = []
    with _connect() as conn:
        for file in files:
            filename = (file.filename or "").replace("\\", "/")
            parts = [p for p in filename.split("/") if p.strip()]
            if len(parts) < 1:
                errors.append({"file": filename, "error": "无效路径"})
                continue
            display_name = parts[-1]
            path_parts = parts[:-1] if len(parts) > 1 else ["_未分类"]
            content = await file.read()
            if len(content) > MAX_BYTES:
                errors.append({"file": filename, "error": f"超过 {MAX_MB}MB，已跳过"})
                continue
            try:
                cat_id = _ensure_category_path(path_parts, conn, type, parent_id=parent_category_id)
                ext = os.path.splitext(display_name)[1] or ""
                stored_name = f"{uuid.uuid4()}{ext}"
                dest_dir = MATERIALS_DIR / f"cat_{cat_id}"
                dest_dir.mkdir(parents=True, exist_ok=True)
                dest_path = dest_dir / stored_name
                dest_path.write_bytes(content)
                cur = conn.execute(
                    """
                    INSERT INTO materials(category_id, display_name, stored_name, size_bytes, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (cat_id, display_name, stored_name, len(content), _utc_now()),
                )
                conn.commit()
                results.append({"file": display_name, "id": cur.lastrowid})
            except Exception as e:
                errors.append({"file": filename, "error": str(e)})
    return {"uploaded": len(results), "errors": errors, "results": results}


@router.delete("/{material_id}")
def delete_material(material_id: int, _: bool = Depends(verify_admin_access)):
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT m.stored_name, c.id AS category_id
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
    file_path = MATERIALS_DIR / f"cat_{row['category_id']}" / row["stored_name"]
    try:
        file_path.unlink(missing_ok=True)
    except OSError:
        pass
    return {"deleted": True}
