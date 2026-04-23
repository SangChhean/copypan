# QA 系统部署指南（服务器）

本文用于部署 `back_qa`（QA 后端 + QA 前端）到服务器，并与现有 PanAI 共存。

- 服务器代码路径：`/opt/pansearch/code`
- Python 安装方式：系统 Python + `--break-system-packages`（无虚拟环境）
- QA 后端端口：`8001`
- QA 日志：`/opt/pansearch/logs/qa_backend.log`
- QA 前端构建目录：`/opt/pansearch/code/front_qa/dist`

---

## 1. 首次部署步骤

### 1.1 拉取代码

```bash
cd /opt/pansearch/code
git pull origin master
```

### 1.2 安装依赖（无虚拟环境）

> 先安装 PanAI 后端依赖（QA 复用其大部分依赖），再安装 `back_shared` 和 `back_qa`。

```bash
cd /opt/pansearch/code/back_mic/backend
pip install -r requirements.txt --break-system-packages

cd /opt/pansearch/code
pip install -e ./back_shared --break-system-packages

# 可选：若 back_qa/requirements.txt 存在额外包（当前通常很少）
if [ -f /opt/pansearch/code/back_qa/requirements.txt ]; then
  pip install -r /opt/pansearch/code/back_qa/requirements.txt --break-system-packages
fi
```

### 1.3 配置 `.env`

`back_qa/main.py` 默认加载：`/opt/pansearch/code/back_mic/backend/.env`  
因此可复用 PanAI 原有 `.env`，只需补齐 QA 变量（见第 2 节）。

```bash
nano /opt/pansearch/code/back_mic/backend/.env
```

### 1.4 启动后端（nohup）

```bash
mkdir -p /opt/pansearch/logs

# 若已有旧进程，先停掉
pkill -f "uvicorn back_qa.main:app" || true

cd /opt/pansearch/code
nohup python -m uvicorn back_qa.main:app --host 0.0.0.0 --port 8001 \
  > /opt/pansearch/logs/qa_backend.log 2>&1 &
```

### 1.5 构建 QA 前端

```bash
cd /opt/pansearch/code/front_qa
npm ci --silent 2>/dev/null || npm install --silent
npm run build
```

构建产物位于：

```text
/opt/pansearch/code/front_qa/dist
```

### 1.6 配置 Nginx（独立 server block）

将第 3 节的 server block 保存为独立站点配置（例如 `qa.conf`），并启用：

```bash
sudo ln -s /etc/nginx/sites-available/qa.conf /etc/nginx/sites-enabled/qa.conf
sudo nginx -t
sudo systemctl reload nginx
```

---

## 2. `.env` 变量清单

以下变量建议放在：`/opt/pansearch/code/back_mic/backend/.env`（QA 复用该文件）。

### 2.1 复用现有变量（PanAI/共享）

- `CLAUDE_API_KEY`：Claude 调用密钥（QA Step1/3/4 需要）
- `ES_HOST`：Elasticsearch 主机（默认 `localhost`）
- `ES_PORT`：Elasticsearch 端口（默认 `9200`）
- `ES_USERNAME`：ES 用户名（默认 `elastic`）
- `ES_PASSWORD`：ES 密码
- `REDIS_HOST`：Redis 主机（默认 `localhost`）
- `REDIS_PORT`：Redis 端口（默认 `6379`）
- `REDIS_DB`：Redis DB（默认 `0`）
- `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD`：`back_shared` Neo4j 客户端连接参数（按你现网配置）

### 2.2 QA 独有变量

- `QA_PORT`：QA 服务端口（建议 `8001`）
- `QA_ADMIN_TOKEN`：管理后台 Token（`/api/qa/stats`、`/api/qa/cache/clear` 需要）
- `QA_STEP1_MODEL`：Step1 模型覆盖（默认 `claude-opus-4-6`）
- `QA_ES_INDEX`：QA 检索索引列表（默认内置多索引）
- `QA_REDIS_PREFIX`：QA 缓存前缀（默认 `qa:cache:`）
- `QA_CACHE_TTL`：QA 缓存 TTL 秒数（默认 `259200`）
- `QA_RATE_LIMIT_PER_MINUTE`：限流阈值（默认 `15`）

---

## 3. Nginx server block 完整示例（QA 独立站点）

> 重点：`/api/qa/` 反代到 `127.0.0.1:8001`，并设置超时 `120s`。

```nginx
server {
    listen 80;
    server_name qa.example.com;  # 替换为你的域名或 IP

    root /opt/pansearch/code/front_qa/dist;
    index index.html;

    # QA 前端（Vue hash/history 路由兜底）
    location / {
        try_files $uri $uri/ /index.html;
    }

    # QA API
    location /api/qa/ {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 120s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }
}
```

---

## 4. systemd service 示例（备用方案，替代 nohup）

当你准备从 nohup 迁移到 systemd，可使用如下模板：

文件：`/etc/systemd/system/qa-backend.service`

```ini
[Unit]
Description=Pansearch QA Backend
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/pansearch/code
ExecStart=/usr/bin/python3 -m uvicorn back_qa.main:app --host 0.0.0.0 --port 8001
Restart=always
RestartSec=5
StandardOutput=append:/opt/pansearch/logs/qa_backend.log
StandardError=append:/opt/pansearch/logs/qa_backend.log

[Install]
WantedBy=multi-user.target
```

启用：

```bash
sudo systemctl daemon-reload
sudo systemctl enable qa-backend
sudo systemctl start qa-backend
sudo systemctl status qa-backend
```

---

## 5. 日常更新步骤

```bash
# 1) 拉代码
cd /opt/pansearch/code
git pull origin master

# 2)（如有依赖变更）更新依赖
cd /opt/pansearch/code/back_mic/backend
pip install -r requirements.txt --break-system-packages
cd /opt/pansearch/code
pip install -e ./back_shared --break-system-packages
if [ -f /opt/pansearch/code/back_qa/requirements.txt ]; then
  pip install -r /opt/pansearch/code/back_qa/requirements.txt --break-system-packages
fi

# 3) 重启 QA 后端（nohup）
pkill -f "uvicorn back_qa.main:app" || true
cd /opt/pansearch/code
nohup python -m uvicorn back_qa.main:app --host 0.0.0.0 --port 8001 \
  > /opt/pansearch/logs/qa_backend.log 2>&1 &

# 4) 重建 QA 前端
cd /opt/pansearch/code/front_qa
npm ci --silent 2>/dev/null || npm install --silent
npm run build

# 5) 重载 Nginx
sudo nginx -t && sudo systemctl reload nginx
```

---

## 6. 验证清单

### 6.1 QA 后端健康与就绪

```bash
curl http://127.0.0.1:8001/api/qa/liveness
curl http://127.0.0.1:8001/api/qa/readiness
```

期望：
- `liveness` 返回 `{"status":"ok"}`
- `readiness.status` 为 `ok` 或至少可解释的 `degraded`（看 ES/Redis/Neo4j）

### 6.2 前端访问

- 打开 QA 站点域名（对应第 3 节 server_name）
- 首页可正常提问，接口走 `/api/qa/query`

### 6.3 管理后台

- 访问 `#/admin`
- 输入 `QA_ADMIN_TOKEN` 后可加载统计
- 可执行缓存清理、查看调试 Tab

### 6.4 日志检查

```bash
tail -f /opt/pansearch/logs/qa_backend.log
```

重点观察：
- 启动是否报错（依赖、环境变量、连接）
- 查询链路日志是否正常（Step1/2/3/4、定向查询、防火墙）

