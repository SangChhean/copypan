# -*- coding: utf-8 -*-
# 启动：cd D:\copypan && python -m uvicorn testC.rough_outline.backend.main:app --host 0.0.0.0 --port 8029 --reload
import os
import sys
from pathlib import Path

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_BACKEND_DIR, "..", "..", ".."))
for p in (_REPO_ROOT,):
    if p not in sys.path:
        sys.path.insert(0, p)

from dotenv import load_dotenv
_ENV_PATH = Path(__file__).resolve().parents[3] / "back_mic" / "backend" / ".env"
load_dotenv(_ENV_PATH)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from testC.rough_outline.backend.rough_outline_router import router

app = FastAPI(title="testC RoughOutline API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)

@app.get("/health")
def health():
    return {"status": "ok"}
