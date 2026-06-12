# 启动命令：uvicorn main:app --host 0.0.0.0 --port 8062 --reload
import os
from dotenv import load_dotenv

_ENV_PATH = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "..", "..", "back_mic", "backend", ".env")
)
load_dotenv(_ENV_PATH)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from enhanced_translate_router import router as enhanced_translate_router

app = FastAPI(title="testC Enhanced Translate API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(enhanced_translate_router)


@app.get("/health")
def health():
    return {"status": "ok"}
