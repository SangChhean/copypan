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
