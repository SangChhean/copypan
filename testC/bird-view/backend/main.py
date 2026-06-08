# -*- coding: utf-8 -*-
# 启动（在 testC/bird-view/backend 目录）：
#     uvicorn main:app --host 0.0.0.0 --port 8023 --reload
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv(Path(__file__).resolve().parent / ".env")
load_dotenv(Path(__file__).resolve().parents[3] / "back_mic" / "backend" / ".env")

from bird_view_router import router

app = FastAPI(title="testC BirdView API")

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


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8023,
        reload=True,
    )
