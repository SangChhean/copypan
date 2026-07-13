# -*- coding: utf-8 -*-
"""中国站 FastAPI 入口（back_cn），默认端口 8014。"""
from __future__ import annotations

import logging
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_repo_root))
sys.path.insert(0, str(_repo_root / "back_mic" / "backend"))

from dotenv import load_dotenv

load_dotenv(_repo_root / "back_mic" / "backend" / ".env")
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)

if not os.getenv("CN_JWT_SECRET", "").strip():
    raise RuntimeError("未配置 CN_JWT_SECRET")

logging.basicConfig(level=logging.INFO, format="%(message)s")

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware


def _ensure_backend_on_path() -> None:
    """使 back_mic/backend 可被 import（kg_rag.firewall 等）。"""
    backend = _repo_root / "back_mic" / "backend"
    s = str(backend)
    if s not in sys.path:
        sys.path.insert(0, s)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # a. ES / Neo4j
    try:
        from back_qa.qa.dependencies import get_es_client, get_neo4j_client

        es = get_es_client()
        neo4j = get_neo4j_client()
        neo4j.startup()
        app.state.es_client = es
        app.state.neo4j_client = neo4j
        app.state.data_baseline = neo4j.get_baseline()
        from datetime import datetime, timezone

        app.state.baseline_updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        print("[CN] a. ES / Neo4j 客户端就绪")
    except Exception as e:
        print(f"[CN] a. ES / Neo4j 初始化失败: {e}")
        raise

    # b. KgRagService
    try:
        from kg_rag.kg_rag_service import KgRagService

        app.state.kg_rag_service = KgRagService(es, neo4j)
        print("[CN] b. KgRagService 就绪")
    except Exception as e:
        print(f"[CN] b. KgRagService 初始化失败: {e}")
        raise

    # c. 防火墙
    try:
        _ensure_backend_on_path()
        from kg_rag.firewall import load_firewall

        load_firewall()
        print("[CN] c. Firewall 规则加载完成")
    except Exception as e:
        print(f"[CN] c. Firewall 加载失败: {e}")
        raise

    # d. 圣经数据
    try:
        from back_qa.qa.bible_service import load_bible_data

        load_bible_data(str(_repo_root / "back_qa" / "bible_data"))
        print("[CN] d. Bible data 加载完成")
    except Exception as e:
        print(f"[CN] d. Bible data 加载失败: {e}")
        raise

    # e. Redis
    try:
        from back_qa.qa.dependencies import get_redis_client

        app.state.redis_client = get_redis_client()
        print("[CN] e. Redis 客户端就绪")
    except Exception as e:
        print(f"[CN] e. Redis 初始化失败: {e}")
        raise

    # 用户库（CN 独立鉴权）
    try:
        from back_cn.auth import init_db

        init_db()
        print("[CN] auth DB 初始化完成")
    except Exception as e:
        print(f"[CN] auth DB 初始化失败: {e}")
        raise

    yield


app = FastAPI(title="Pansearch 中国站", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

from back_cn.routers.auth_router import router as auth_router
from back_cn.routers.qa_router import router as qa_router
from back_cn.routers.bible_router import router as bible_router
from back_cn.routers.tools_router import router as tools_router
from back_cn.routers.panai_router import router as panai_router
from back_cn.routers.materials_router import router as materials_router
from back_cn.routers.guide_router import router as guide_router
from back_cn.routers.roundtable_router import router as roundtable_router

app.include_router(auth_router)
app.include_router(qa_router, prefix="/api/qa")
app.include_router(bible_router, prefix="/api/qa")
app.include_router(tools_router)
app.include_router(panai_router)
app.include_router(materials_router)
app.include_router(guide_router)
app.include_router(roundtable_router)


@app.get("/api/cn/liveness")
async def liveness():
    return {"status": "ok"}


@app.get("/api/cn/readiness")
async def readiness(request: Request):
    from back_qa.qa.dependencies import get_es_client, get_redis_client
    from back_qa.qa import bible_service

    neo4j = getattr(request.app.state, "neo4j_client", None)
    neo4j_status = "connected" if neo4j and neo4j._available else "unavailable"

    try:
        es = get_es_client()
        es.cluster.health(request_timeout=3)
        es_status = "connected"
    except Exception:
        es_status = "unavailable"

    try:
        r = get_redis_client()
        redis_status = "connected" if r is not None else "unavailable"
    except Exception:
        redis_status = "unavailable"

    kg_ready = getattr(request.app.state, "kg_rag_service", None) is not None
    bible_books = len(bible_service._bible)

    overall = "ok" if all(
        s == "connected" for s in [neo4j_status, es_status, redis_status]
    ) and kg_ready and bible_books > 0 else "degraded"

    return {
        "status": overall,
        "neo4j": neo4j_status,
        "elasticsearch": es_status,
        "redis": redis_status,
        "kg_rag_service": "ready" if kg_ready else "unavailable",
        "bible_data": {"books": bible_books},
    }


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("CN_PORT", "8014"))
    uvicorn.run("back_cn.main:app", host="127.0.0.1", port=port, reload=True)
