"""
test_B 纲目职事化后端入口。

启动（在 test_B/ministerialize/backend 目录）：
    uvicorn main:app --host 0.0.0.0 --port 8031 --reload
"""
import logging
import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../../../back_mic/backend/.env"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ministerialize_router import router as ministerialize_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="test_B Ministerialize API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ministerialize_router)  # reload


@app.get("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8031, reload=True)
