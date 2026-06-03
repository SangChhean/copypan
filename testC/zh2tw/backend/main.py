# 启动命令：uvicorn main:app --host 0.0.0.0 --port 8006 --reload
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from zh_router import router as zh_router

app = FastAPI(title="testC ZhConvert API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(zh_router)

@app.get("/health")
def health():
    return {"status": "ok"}
