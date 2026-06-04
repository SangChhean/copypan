# -*- coding: utf-8 -*-
"""testD 本地调试入口（方式 B），默认端口 8010。上线仍依赖主站 main.py 挂载路由。"""
import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from testD.backend.enhanced_translate_router import router

app = FastAPI(title="testD Enhanced Translate (debug)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("TESTD_PORT", "8010"))
    uvicorn.run("testD.backend.app:app", host="0.0.0.0", port=port, reload=True)
