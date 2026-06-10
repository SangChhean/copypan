# -*- coding: utf-8 -*-
"""
testA 毛胚纲目后端入口，端口 8027
启动：cd testA/rough-outline/backend && python main.py
"""
import logging
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[3] / "back_mic" / "backend" / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from rough_outline_router import router as rough_outline_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="[testA] RoughOutline API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(rough_outline_router)

@app.get("/health")
def health():
    return {"status": "ok"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8027, reload=True)
