# -*- coding: utf-8 -*-
# 启动：cd D:\copypan && python -m uvicorn testC.PanAI20.backend.main:app --host 0.0.0.0 --port 8009 --reload
import os
import sys

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.abspath(os.path.join(_BACKEND_DIR, "..", "..", ".."))
_BACK_MIC_BACKEND = os.path.join(_REPO_ROOT, "back_mic", "backend")

for p in (_REPO_ROOT, _BACK_MIC_BACKEND):
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from testC.PanAI20.backend import kg_rag_router

app = FastAPI(title="PanAI 2.0 Practice")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(kg_rag_router.router)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "testC.PanAI20.backend.main:app",
        host="0.0.0.0",
        port=8009,
        reload=True,
    )
