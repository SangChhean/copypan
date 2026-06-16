# -*- coding: utf-8 -*-
"""progress_outline 独立后端入口，端口 8051。"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))
sys.path.insert(0, str(ROOT))

load_dotenv(ROOT / ".env")
_back_mic = ROOT.parent.parent / "back_mic" / "backend" / ".env"
if _back_mic.is_file():
    load_dotenv(_back_mic, override=False)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from progress_router import entry_router, pano_router, router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")

app = FastAPI(title="Progress Outline API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)
app.include_router(pano_router)
app.include_router(entry_router)


@app.get("/health")
def health():
    return {"status": "ok", "service": "progress_outline"}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PROGRESS_OUTLINE_PORT", "8051"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
