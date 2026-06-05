# 启动命令：uvicorn main:app --host 0.0.0.0 --port 8013 --reload
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from polish_router import router as polish_router

app = FastAPI(title="testC ArticlePolish API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(polish_router)

@app.get("/health")
def health():
    return {"status": "ok"}
