# -*- coding: utf-8 -*-
"""qa4 后端应用工厂。"""

from __future__ import annotations

import logging
import sys
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

_BACKEND = Path(__file__).resolve().parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from api import admin_routes, auth_routes, feedback_routes, media_routes, qa as qa_routes
from config import Settings, assert_dev_autologin_safe, get_settings
from core.auth import AuthStore
from core.es_client import EsClient
from core.neo4j_client import Neo4jClient
from core.ready import build_ready_report
from core.redis_store import create_store

logger = logging.getLogger("qa4.main")


def create_app(
    settings: Optional[Settings] = None,
    *,
    redis_store: Any = None,
    es_client: Any = None,
    neo4j_client: Any = None,
    auth_store: Any = None,
    pipeline_deps: Any = None,
) -> FastAPI:
    settings = settings or get_settings(require_runtime=False)
    assert_dev_autologin_safe(settings)
    if getattr(settings, "dev_autologin", False):
        logger.warning("****************************************")
        logger.warning("* 本机免登录已开启（QA4_DEV_AUTOLOGIN）*")
        logger.warning("* 仅 127.0.0.1 绑定 + 本机请求生效   *")
        logger.warning("****************************************")

    app = FastAPI(title="qa4", version="0.1.0-stage3")

    # 依赖注入
    store = redis_store if redis_store is not None else create_store(
        settings.redis_url, settings.redis_prefix
    )
    auth = auth_store or AuthStore(
        settings.data_dir / "qa4_users.db",
        jwt_secret=settings.jwt_secret,
        jwt_expire_days=settings.jwt_expire_days,
        daily_limit_default=settings.daily_limit_default,
        tz_name=settings.tz_name,
        admin_token=settings.admin_token,
    )
    es = es_client if es_client is not None else EsClient(
        settings.es_url,
        settings.es_user,
        settings.es_secret,
        verify=settings.es_verify,
        index_map=settings.index_map,
    )
    neo = neo4j_client if neo4j_client is not None else Neo4jClient(
        settings.neo4j_uri, settings.neo4j_user, settings.neo4j_secret
    )

    app.state.settings = settings
    app.state.redis_store = store
    app.state.auth = auth
    app.state.es = es
    app.state.neo4j = neo

    # 阶段 3：流水线依赖（可注入；默认按 QA4_LLM_MODE / QA4_RETRIEVAL_MODE 装配）
    if pipeline_deps is not None:
        app.state.pipeline_deps = pipeline_deps
    else:
        try:
            from pipeline.deps import build_deps

            app.state.pipeline_deps = build_deps(
                settings, store=store, es=es, neo4j=neo
            )
        except Exception:
            app.state.pipeline_deps = None

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        request.state.request_id = rid
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response

    def _message_from_detail(detail: Any) -> str:
        if isinstance(detail, dict) and "message" in detail:
            return str(detail["message"])
        if isinstance(detail, list):
            return "请求参数无效"
        return str(detail)

    @app.exception_handler(HTTPException)
    async def http_exc_handler(request: Request, exc: HTTPException):
        rid = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=exc.status_code,
            content={"message": _message_from_detail(exc.detail), "request_id": rid},
        )

    @app.exception_handler(RequestValidationError)
    async def validation_handler(request: Request, exc: RequestValidationError):
        rid = getattr(request.state, "request_id", None)
        return JSONResponse(
            status_code=422,
            content={"message": "请求参数无效", "request_id": rid},
        )

    @app.get("/healthz")
    def healthz():
        return {"ok": True}

    @app.get("/readyz")
    def readyz(request: Request):
        s = request.app.state.settings
        policy = getattr(s, "llm_policy", None) or None
        if isinstance(policy, dict) and policy.get("_load_error"):
            policy = None
        deps = getattr(request.app.state, "pipeline_deps", None)
        prompts_info = None
        if deps is not None:
            try:
                prompts_info = {
                    "mode": getattr(deps, "llm_mode", getattr(s, "llm_mode", "live")),
                    **deps.prompts.status(),
                }
            except Exception as e:
                prompts_info = {"ready": False, "message": type(e).__name__}
        report = build_ready_report(
            redis_store=request.app.state.redis_store,
            es_client=request.app.state.es,
            neo4j_client=request.app.state.neo4j,
            lookup_dir=s.lookup_dir,
            expected=s.expected_counts,
            index_map=s.index_map,
            llm_settings={
                "key_present": bool(getattr(s, "anthropic_api_key", "") or ""),
                "model_haiku": getattr(s, "model_haiku", "") or s.model_fast,
                "model_sonnet": getattr(s, "model_sonnet", "") or s.model_main,
                "policy": policy,
                "llm_mode": getattr(s, "llm_mode", "live"),
            },
            prompts_info=prompts_info,
        )
        status = report["status"]
        code = 200 if status in {"ok", "degraded"} else 503
        return JSONResponse(status_code=code, content=report)

    app.include_router(auth_routes.router)
    app.include_router(feedback_routes.router)
    app.include_router(admin_routes.router)
    app.include_router(qa_routes.router)
    app.include_router(media_routes.router)

    return app


app = create_app()


if __name__ == "__main__":
    import uvicorn

    s = get_settings(require_runtime=False)
    assert_dev_autologin_safe(s)
    uvicorn.run("main:app", host=s.bind_host or "0.0.0.0", port=s.port, reload=False)
