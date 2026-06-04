"""
test_B/zh2tw 独立后端入口。
启动（在 test_B/zh2tw/backend 目录）：
    uvicorn main:app --host 0.0.0.0 --port 8005 --reload

前端 UI（在 test_B/zh2tw/frontend 目录）：
    npm install && npm run dev
    浏览器打开 http://localhost:8008
"""
import logging
from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).resolve().parents[3] / "back_mic" / "backend" / ".env")
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from zh_router import router as zh_router

logging.basicConfig(level=logging.INFO)
app = FastAPI(title="test_B ZhConvert API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(zh_router)

@app.get("/health")
def health():
    return {"status": "ok"}
