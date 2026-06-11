# 启动命令：uvicorn main:app --host 0.0.0.0 --port 8032 --reload
import os
from dotenv import load_dotenv

# 必须在导入 router 之前加载 .env（指向主站的 .env，用绝对路径计算）
_ENV_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "back_mic", "backend", ".env")
)
load_dotenv(_ENV_PATH)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ministerialize_router import router as ministerialize_router

app = FastAPI(title="testC Ministerialize API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ministerialize_router)


@app.get("/health")
def health():
    return {"status": "ok"}
