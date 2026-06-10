"""
test_B 节期纲目后端入口。

启动（在 test_B/feast-outline/backend 目录）：
    uvicorn main:app --host 0.0.0.0 --port 8025 --reload
"""
import logging

from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[3] / "back_mic" / "backend" / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from feast_outline_router import router as feast_outline_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="[test_B] FeastOutline API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(feast_outline_router)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8025, reload=True)
