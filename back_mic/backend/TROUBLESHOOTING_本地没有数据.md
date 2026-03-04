# 本地开发「没有数据」排查说明

当访问 http://localhost:5173/#/ 出现没有数据、白屏或搜索无结果时，按下面顺序检查。

## 1. 确认后端与代理

- **后端**需在 **8000** 端口运行，前端 Vite 会把 `/api` 代理到 `http://localhost:8000`。
- 在项目根目录执行：
  ```bash
  cd back_mic/backend
  uvicorn main:app --host 0.0.0.0 --port 8000
  ```
- 浏览器访问：http://localhost:5173 → 若未登录会跳到 `#/login`，登录后再回首页应能看到搜索页。

## 2. 健康检查（是否连上 ES）

在浏览器或命令行访问：

```
http://localhost:8000/api/ai_search/health
```

或（需先登录拿到 token，或暂时去掉该接口的鉴权再试）：

```powershell
curl -s http://localhost:8000/api/ai_search/health
```

看返回里 `services.elasticsearch` 是否为 `true`。若为 `false`，说明当前后端连不上 Elasticsearch。

## 3. Elasticsearch 端口与连接

- 后端通过 **`es_config.py`** 连接 ES，读取环境变量：`ES_HOST`、**`ES_PORT`**、`ES_USERNAME`、`ES_PASSWORD`。
- 默认 `ES_PORT=9200`。若你的 **ES 8.19** 映射在 **9201**（与 7.17.9 的 9200 区分），必须在 **`back_mic/backend/.env`** 里设置：
  ```env
  ES_PORT=9201
  ```
- 若未设置 `ES_PORT`，后端会连 9200；若此时只有 ES 8.19 在 9201 上跑，就会连错或连不上，导致「没有数据」。

## 4. ES 8.x 安全与密码

- Elasticsearch 8.x 默认开启安全，会生成初始密码（首次启动日志或 `docker exec` 容器内可查）。
- 在 **`.env`** 中配置（若 ES 需要认证）：
  ```env
  ES_USERNAME=elastic
  ES_PASSWORD=你的ES密码
  ```
- 若密码错误或未填，ES 会返回 401，后端拿不到数据，表现也是「没有数据」。

## 5. 数据在哪个 ES 上

- 若你**两个 ES 同时存在**（7.17.9 与 8.19.0），数据目前只在一侧（通常是原先的 7.17.9）。
- 后端当前连的端口由 **`.env` 的 `ES_PORT`** 决定：
  - `ES_PORT=9200` → 连 7.17.9（若该容器映射 9200），一般有数据。
  - `ES_PORT=9201` → 连 8.19.0；若 8.19 从未导入数据，索引为空，搜索也会「没有数据」。

**建议**：若尚未向 ES 8.19 迁数据，先把 **`ES_PORT=9200`**（或删除该行用默认），让后端继续连有数据的 7.17.9，保证网站有数据。

## 6. 快速检查 ES 连接（本机）

在 `back_mic/backend` 目录下执行（会读取当前目录 `.env`）：

```powershell
cd back_mic\backend
python -c "from es_config import es; print('ES ping:', es.ping())"
```

- 输出 `ES ping: True` 表示连接正常。
- 若报错 `ConnectionError` 或 `401`，请核对 `.env` 中的 `ES_HOST`、`ES_PORT`、`ES_USERNAME`、`ES_PASSWORD` 以及实际运行的 ES 容器端口。

## 小结

| 现象           | 可能原因                     | 处理 |
|----------------|------------------------------|------|
| 白屏 / 一直转 | 后端未启动或未开 8000        | 启动 `uvicorn main:app --port 8000` |
| 跳到登录       | 未登录或 token 失效          | 正常登录后再访问首页 |
| 搜索无结果     | ES 连错端口或连不上          | 设置 `.env` 的 `ES_PORT`（及认证） |
| 搜索无结果     | 连的是没有数据的 ES 8.19      | 暂时改回 `ES_PORT=9200` 连 7.17.9 |
