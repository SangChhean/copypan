# -*- coding: utf-8 -*-
"""职事信息问答系统 FastAPI 入口，端口 8001。"""
import logging
import os
import asyncio
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")

# 自动加载 back_mic/backend/.env（与 PanAI 共享同一份环境变量）
try:
    from dotenv import load_dotenv
    _env_path = Path(__file__).resolve().parents[1] / "back_mic" / "backend" / ".env"
    if _env_path.exists():
        load_dotenv(_env_path)
        print(f"[QA] 已加载环境变量: {_env_path}")
    else:
        print(f"[QA] .env 未找到，跳过: {_env_path}")
except ImportError:
    print("[QA] python-dotenv 未安装，跳过 .env 加载")

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse as _JSONResponse

from back_qa.qa.qa_router import router as qa_router
from back_qa.qa.bible_router import router as bible_router
from back_qa.qa.auth_router import router as auth_router
from back_qa.qa.bible_service import load_bible_data
from back_qa.qa.dependencies import get_neo4j_client


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动
    from back_qa.qa.auth import init_db

    init_db()

    bible_dir = Path(__file__).resolve().parent / "bible_data"
    load_bible_data(str(bible_dir))

    neo4j = get_neo4j_client()
    neo4j.startup()

    # 启动时查询数据基线，存入 app.state
    baseline = neo4j.get_baseline()
    app.state.neo4j_client = neo4j
    app.state.data_baseline = baseline
    app.state.baseline_updated_at = _utcnow()

    # 每 5 分钟刷新数据基线
    app.state._baseline_task = asyncio.create_task(_refresh_baseline_loop(app))

    yield

    # 关闭
    app.state._baseline_task.cancel()
    neo4j.shutdown()


async def _refresh_baseline_loop(app: FastAPI):
    """每 5 分钟刷新一次数据基线快照。"""
    while True:
        await asyncio.sleep(300)
        try:
            neo4j = app.state.neo4j_client
            app.state.data_baseline = neo4j.get_baseline()
            app.state.baseline_updated_at = _utcnow()
        except Exception as e:
            print(f"[QA] 数据基线刷新失败: {e}")


def _utcnow() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


app = FastAPI(title="职事信息问答系统", version="1.0.0", lifespan=lifespan)


class TimeoutMiddleware(BaseHTTPMiddleware):
    """单次请求最长 120 秒，超时返回 504。"""

    async def dispatch(self, request, call_next):
        import asyncio as _asyncio

        try:
            return await _asyncio.wait_for(call_next(request), timeout=120.0)
        except _asyncio.TimeoutError:
            return _JSONResponse(
                status_code=504,
                content={"detail": "请求超时，请稍后重试"},
            )


app.add_middleware(TimeoutMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(qa_router, prefix="/api/qa")
app.include_router(bible_router, prefix="/api/qa")
app.include_router(auth_router)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("QA_PORT", "8001"))
    uvicorn.run("back_qa.main:app", host="0.0.0.0", port=port, reload=True)
