"""
test_B 增强式翻译后端入口。

启动（在 test_B/enhanced_translate/backend 目录）：
    uvicorn main:app --host 0.0.0.0 --port 8061 --reload
"""
import logging
import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../../../back_mic/backend/.env"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from enhanced_translate_router import router as enhanced_translate_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="test_B Enhanced Translate API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(enhanced_translate_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8061, reload=True)
