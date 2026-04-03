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

`/api/ai_search/health` **无需登录**，可直接检查依赖是否正常：

```
http://localhost:8000/api/ai_search/health
```

或：

```powershell
curl -s http://localhost:8000/api/ai_search/health
```

看返回里 `services.elasticsearch` 是否为 `true`。若为 `false`，说明当前后端连不上 Elasticsearch。

## 3. Elasticsearch 端口与连接

- 后端通过 **`es_config.py`** 连接 ES，读取环境变量：`ES_HOST`、**`ES_PORT`**、`ES_USERNAME`、`ES_PASSWORD`。
- 与 `start_all.bat` 一致时：容器 **`elasticsearch8`** 映射 **9200:9200**，数据目录 **`es8_data`**，此时 **`.env` 中可不写 `ES_PORT`**（默认 9200）。
- 若你把 ES 映射到其他宿主机端口，在 **`back_mic/backend/.env`** 中设置：
  ```env
  ES_PORT=你的端口
  ```

## 4. ES 8.x 安全与密码

- Elasticsearch 8.x 默认开启安全（如使用 `xpack.security.enabled=true` 与 `ELASTIC_PASSWORD` 启动容器）。
- 在 **`.env`** 中配置（与容器一致）：
  ```env
  ES_USERNAME=elastic
  ES_PASSWORD=你的ES密码
  ```
- 若密码错误或未填，ES 会返回 401，后端拿不到数据，表现也是「没有数据」。

## 5. 数据与索引

- 确认 **`es8_data`** 目录已包含迁移/导入后的索引数据；若为新装 ES 且从未导入，索引为空时搜索会无结果。
- 可在管理端「已上传文件管理」等处重新导入，或按部署文档迁移数据目录。

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
| 搜索无结果     | ES 连错端口或连不上          | 核对 `.env` 的 `ES_PORT`（及认证） |
| 搜索无结果     | 索引为空或未导入数据         | 导入数据或迁移 `es8_data` |
