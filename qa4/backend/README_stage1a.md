# qa4 阶段 1a · 基础设施

账号限额、Redis、ES/Neo4j 只读客户端、探针、管理接口；不含模型/提示词/九步流水线/前端。

## 相对 3.0 的差异

| 项 | 3.0 | qa4 1a |
|----|-----|--------|
| 默认日限额 | 3（后可改） | **30**（`QA4_DAILY_LIMIT_DEFAULT`）；只认库内 `users.daily_limit` |
| 用量存储 | `users.daily_count/daily_date` | 独立表 `usage(day,user_id,count)` |
| 邀请码 | 单次 `used` 0/1 | `max_uses` / `used_count` / `expires_at` / `disabled` / `note` |
| 用户字段 | `hashed_password` | `password_hash`；另有 `disabled` / `is_admin` |
| 管理鉴权 | 字符串 `!=` | `hmac.compare_digest`；未配置 token → 503/拒绝 |
| API 前缀 | `/api/qa/auth/*` | `/api/auth/*`、`/api/admin/*`、`/api/feedback` |
| 错误体 | `detail` | 统一 `{"message","request_id"}` |
| Redis | 不可用则跳过限流 | `MemoryStore` 或进程内降级计数；`scan_delete` 禁 KEYS/FLUSH* |
| 日界线 | UTC | `QA4_TZ` 默认 **UTC**（同 3.0） |
| JWT | `QA_JWT_SECRET` | `QA4_JWT_SECRET`；过期默认 7 天 |

## 阶段 0 文件改动（本阶段）

- `config.py` → 包 `config/`（`settings.py` + `expected_counts.json` + `index_map.json`）
- `main.py` → `create_app` 工厂 + `/readyz` 等
- `.env.example` 增补 JWT/Admin/TZ/限流/ES_VERIFY
- `core/`、`api/` 由占位变为实现

## 虚拟环境与依赖

在仓库根目录：

```bash
python -m venv qa4/backend/.venv
# Windows
qa4\backend\.venv\Scripts\activate
# Linux/macOS
# source qa4/backend/.venv/bin/activate

pip install -r qa4/backend/requirements.txt
```

`.venv` 已在 `qa4/.gitignore`。

## 环境变量（只列名字）

| 变量 | 说明 |
|------|------|
| `QA4_ENV_FILE` | 可选外部 env 文件 |
| `QA4_PORT` | 默认 8030 |
| `QA4_DATA_DIR` | 用户库目录（运行时数据等）；默认 `qa4/data` |
| `QA4_LOOKUP_DIR` | 查表目录；**默认固定为仓库内 `qa4/data/lookups`，与 `QA4_DATA_DIR` 独立**；设了才覆盖 |
| `QA4_REDIS_URL` / `QA4_REDIS_PREFIX` | Redis；空 URL → MemoryStore |
| `QA4_ES_URL` / `QA4_ES_USER` / `QA4_ES_PASSWORD` / `QA4_ES_VERIFY` | ES；VERIFY 默认 1 |
| `QA4_NEO4J_URI` / `QA4_NEO4J_USER` / `QA4_NEO4J_PASSWORD` | Neo4j |
| `QA4_JWT_SECRET` / `QA4_JWT_EXPIRE_DAYS` | JWT（默认 7 天） |
| `QA4_ADMIN_TOKEN` | 管理接口；未配置则管理接口拒绝 |
| `QA4_DAILY_LIMIT_DEFAULT` | 默认 30 |
| `QA4_TZ` | 日界线时区，默认 UTC（与 3.0 一致） |
| `QA4_RATE_LIMIT_PER_MINUTE` | 默认 15 |
| `CLAUDE_API_KEY` / `OPENROUTER_API_KEY` | 本阶段可空 |
| `QA4_MODEL_FAST` / `QA4_MODEL_MAIN` / `QA4_FAKE_LLM` | 预留 |

模板：`qa4/backend/.env.example`（值留空）。

## 启动

```bash
# 1) Redis 容器
docker compose -f qa4/deploy/redis/docker-compose.yml up -d

# 2) 探针（可先 --dry-run）
python qa4/backend/tools/check_services.py --dry-run
# 设好口令类变量后：
python qa4/backend/tools/check_services.py

# 3) 应用（仓库根目录）
set QA4_JWT_SECRET=dev-secret
set QA4_ADMIN_TOKEN=dev-admin
set QA4_REDIS_URL=redis://127.0.0.1:6381/0
set QA4_DATA_DIR=qa4/data
rem 查表默认已是 qa4/data/lookups；仅当查表不在默认位置时设 QA4_LOOKUP_DIR
python -m uvicorn main:app --app-dir qa4/backend --host 127.0.0.1 --port 8030

# 4) 探针 HTTP
curl http://127.0.0.1:8030/healthz
curl http://127.0.0.1:8030/readyz
```

## 索引实际名与向量字段

见 `qa4/backend/config/index_map.json`：逻辑名 → `qa4_*` 实际索引；outline/bible/hymns 用 `embedding`，text_*/map_note 用 `text_vector`，pano_catalog 无向量。源包为 `panai4_*`，导入目标前缀 `qa4_`（`qa4/data_prep/es_import.py`）。

## 测试

```bash
python -m unittest discover -s qa4/backend/tests
```
