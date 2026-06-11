"""
test_B 毛胚纲目后端入口。

启动（在 test_B/rough-outline/backend 目录）：
    uvicorn main:app --host 0.0.0.0 --port 8028 --reload
"""
import logging
import os

from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "../../../back_mic/backend/.env"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from rough_outline_router import router as rough_outline_router

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="test_B RoughOutline API")

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
    uvicorn.run("main:app", host="0.0.0.0", port=8028, reload=True)
