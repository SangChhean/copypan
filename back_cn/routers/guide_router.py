# -*- coding: utf-8 -*-
"""CN 站使用说明 PDF：单文件上传 / 替换 / 读取。"""
from __future__ import annotations

import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from back_cn.auth import verify_admin_access

_repo_root = Path(__file__).resolve().parents[2]
# 与 cn_materials 同级：生产 /opt/pansearch/data/cn_guide，本地默认 back_cn/uploads/cn_guide
_raw_dir = os.getenv("CN_GUIDE_DIR", "back_cn/uploads/cn_guide")
GUIDE_DIR = Path(_raw_dir) if Path(_raw_dir).is_absolute() else _repo_root / _raw_dir
GUIDE_PATH = GUIDE_DIR / "user_guide.pdf"

router = APIRouter(prefix="/api/cn/guide", tags=["guide"])


@router.post("/upload")
async def upload_guide(
    file: UploadFile = File(...),
    _: bool = Depends(verify_admin_access),
):
    filename = (file.filename or "").lower()
    if not filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="只支持 PDF 文件")
    GUIDE_DIR.mkdir(parents=True, exist_ok=True)
    with open(GUIDE_PATH, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"success": True}


@router.get("/pdf")
async def get_guide():
    if not GUIDE_PATH.exists():
        raise HTTPException(status_code=404, detail="使用说明尚未上传")
    return FileResponse(GUIDE_PATH, media_type="application/pdf")


@router.get("/exists")
async def guide_exists():
    return {"exists": GUIDE_PATH.exists()}
