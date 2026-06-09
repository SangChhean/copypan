"""
testA 文章润色练习后端入口。

启动（在 testA/article-polish/backend 目录）：
    uvicorn main:app --host 0.0.0.0 --port 8011 --reload
"""
import logging

from dotenv import load_dotenv
from pathlib import Path

load_dotenv(Path(__file__).resolve().parents[3] / "back_mic" / "backend" / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from polish_router import router as polish_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="testA ArticlePolish API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(polish_router)


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8011, reload=True)
