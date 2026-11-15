"""PanAI 新测试台的独立后端入口（与主站 3.5 分开跑，互不影响）。

只挂新测试台的接口（前缀 /api/t35test）；登录仍在主站完成，这里只校验 token
（user.token.test_token 读同一份用户名单和密钥，所以主站登录后两边通用）。

启动（在 back_mic/backend 下）：
    python run_backend.py --app main_t35test:app --port 8001 --log-prefix t35test
nginx 把 /api/t35test/ 转发到 8001，其余 /api 仍转发到主站 8000。
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from t35test.router import router as t35test_router

app = FastAPI(title="PanAI 新测试台")

# 与主站 main.py 相同的跨域来源（携带 cookie 时不能用 "*"）
_CORS_ORIGINS = [
    "http://localhost",
    "http://127.0.0.1",
    "http://localhost:80",
    "http://localhost:5173",
    "http://localhost:5182",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5182",
    "http://127.0.0.1:3000",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Retrieval-Log"],
)

app.include_router(t35test_router)


# 【并发】调用模型、查 ES、排版等都用 asyncio.to_thread 丢到背景线程执行，每次模型调用会占一条线程直到回来（生成纲目常要一两分钟）。
# Python 默认线程池只有 min(32, CPU数+4) 条（这台 4 核电脑只有 8 条），三四个人同时生成就会排队、前端超时。
# 启动时把默认线程池加大；数量可用环境变量 T35TEST_THREADS 调整（默认 64）。
@app.on_event("startup")
async def _enlarge_thread_pool() -> None:
    import asyncio
    import logging
    import os
    from concurrent.futures import ThreadPoolExecutor

    n = int(os.getenv("T35TEST_THREADS", "64"))
    asyncio.get_running_loop().set_default_executor(ThreadPoolExecutor(max_workers=n, thread_name_prefix="t35test"))
    logging.getLogger("t35test").info("[并发] 背景线程池：%s 条", n)
