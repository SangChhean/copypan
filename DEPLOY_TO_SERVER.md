# Copypan 服务器部署指南

将项目从本机部署到 Linux 服务器，实现 24 小时在线访问。

---

## 一、服务器要求

- **系统**：Ubuntu 20.04+ 或 CentOS 7+（推荐 Ubuntu）
- **配置**：至少 4GB 内存（ES 需约 2GB），20GB 硬盘
- **网络**：可访问外网（Claude API、npm 等）

---

## 二、部署步骤概览

1. 安装 Docker、Python、Node.js、Nginx
2. 在服务器上启动 ES 和 Redis
3. 迁移/上传项目代码
4. 迁移 ES 数据（或重新导入）
5. 配置并启动后端
6. 构建前端并配置 Nginx
7. 配置 CORS 和域名

---

## 三、详细步骤

### 1. 安装环境（Ubuntu 示例）

```bash
# 更新系统
sudo apt update && sudo apt upgrade -y

# 安装 Docker
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
# 重新登录使 docker 组生效

# 安装 Python 3.10+、pip、Node.js
sudo apt install -y python3 python3-pip nodejs npm nginx

# 可选：用 pyenv 或 venv 管理 Python 版本
```

### 2. 创建项目目录并上传代码

```bash
# 在服务器上创建目录
sudo mkdir -p /opt/copypan
sudo chown $USER:$USER /opt/copypan

# 方式 A：Git 拉取（若代码在 Git 仓库）
cd /opt/copypan
git clone <你的仓库地址> .

# 方式 B：本地上传
# 在本地执行 scp 或 rsync 将项目拷贝到服务器
# rsync -avz --exclude node_modules --exclude __pycache__ \
#   E:\copypan\ user@你的服务器IP:/opt/copypan/
```

### 3. 启动 Elasticsearch 和 Redis（Docker）

```bash
cd /opt/copypan

# 创建 ES 数据目录（持久化）
mkdir -p es_data

# 启动 Elasticsearch
docker run -d --name elasticsearch \
  -p 9200:9200 -p 9300:9300 \
  -e "discovery.type=single-node" \
  -e "ES_JAVA_OPTS=-Xms2g -Xmx2g" \
  -v /opt/copypan/es_data:/usr/share/elasticsearch/data \
  elasticsearch:7.17.9

# 安装 IK 分词（如需中文检索）
# docker exec -it elasticsearch bash
# bin/elasticsearch-plugin install https://github.com/medcl/elasticsearch-analysis-ik/releases/download/v7.17.9/elasticsearch-analysis-ik-7.17.9.zip
# exit
# docker restart elasticsearch

# 启动 Redis
docker run -d --name redis -p 6379:6379 redis:alpine

# 等待 ES 就绪（约 15-30 秒）
sleep 20
curl http://localhost:9200
```

### 4. 迁移 ES 数据

**方式 A：直接拷贝本机 es_data（推荐，数据完整）**

**本地 Windows 打包并上传：**

```powershell
# 在项目根目录 E:\copypan 执行
# 仅打包（ES 可继续运行）：
.\package_esdata.ps1

# 先停止 ES 再打包（数据更一致，打包后会自动启动 ES）：
.\package_esdata.ps1 -StopES

# 上传到服务器（替换 用户名 和 服务器IP）：
scp E:\copypan\es_data.zip 用户名@服务器IP:/opt/copypan/
```

**服务器上解压并挂载：**

```bash
cd /opt/copypan
# 先停止并删除现有 ES 容器
docker stop elasticsearch
docker rm elasticsearch

# 解压（会得到 es_data 目录）
unzip -o es_data.zip

# 重新启动 ES（-v 指向 /opt/copypan/es_data）
docker run -d --name elasticsearch \
  -p 9200:9200 -p 9300:9300 \
  -e "discovery.type=single-node" \
  -e "ES_JAVA_OPTS=-Xms2g -Xmx2g" \
  -v /opt/copypan/es_data:/usr/share/elasticsearch/data \
  elasticsearch:7.17.9
```

**方式 B：重新创建索引并导入**

若无法拷贝 es_data，可在管理端重新导入 JSON：

```bash
# 1. 运行 es_init 创建空索引（需 Python 已安装依赖）
cd /opt/copypan/back_mic/backend
pip install elasticsearch
python -c "
import sys
sys.path.insert(0, '.')
from es_init import *
"
# 或直接运行项目中已有的 es_init 逻辑

# 2. 将本地 database/upload 下的 JSON 或原始数据上传到服务器
# 3. 登录管理端，在「已上传文件管理」中逐个导入
```

### 5. 配置后端

```bash
cd /opt/copypan/back_mic/backend

# 创建虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate   # Linux
# Windows: venv\Scripts\activate

# 安装依赖
pip install fastapi uvicorn elasticsearch anthropic python-dotenv redis pydantic pyjwt python-multipart

# 创建 requirements.txt 便于后续维护（可选）
# pip freeze > requirements.txt

# 配置 .env
nano .env
```

`.env` 内容示例：

```env
CLAUDE_API_KEY=你的Claude_API_Key
REDIS_HOST=localhost
REDIS_PORT=6379
```

**修改 CORS（允许前端域名访问）**：

编辑 `main.py`，在 `_CORS_ORIGINS` 中添加你的域名：

```python
_CORS_ORIGINS = [
    "http://localhost",
    "http://127.0.0.1",
    # ... 原有 ...
    "https://你的域名.com",      # 例如 https://aipansearch.org
    "http://你的域名.com",
    "http://服务器IP",           # 若用 IP 直接访问
]
```

**es_config.py**：后端和 ES 同机部署时，保持 `localhost:9200` 即可，无需修改。

### 6. 启动后端（测试）

```bash
cd /opt/copypan/back_mic/backend
source venv/bin/activate
uvicorn main:app --host 0.0.0.0 --port 8000
# 测试通过后 Ctrl+C 停止，改用 systemd 或 nohup 常驻
```

验证：

```bash
curl http://localhost:8000/api/ai_search/health
```

### 7. 构建前端

```bash
cd /opt/copypan/front_mic/frontend

# 安装依赖
npm install

# 构建（若通过同一域名访问，VITE_API_BASE 可留空）
npm run build
# 产物在 dist/
```

### 8. 配置 Nginx

```bash
sudo nano /etc/nginx/sites-available/copypan
```

写入（替换 `你的域名` 和路径）：

```nginx
server {
    listen 80;
    server_name 你的域名.com;   # 或 服务器IP

    root /opt/copypan/front_mic/frontend/dist;
    index index.html;

    location / {
        try_files $uri $uri/ /index.html;
    }

    # AI 生成答案接口耗时 20–30+ 秒，需加长超时，否则在线会显示「AI搜索失败」但后端已返回
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 120s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }

    location /ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

启用站点并重载：

```bash
sudo ln -s /etc/nginx/sites-available/copypan /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 9. 使用 systemd 保持后端常驻

```bash
sudo nano /etc/systemd/system/copypan.service
```

```ini
[Unit]
Description=Copypan Backend
After=network.target

[Service]
User=你的用户名
WorkingDirectory=/opt/copypan/back_mic/backend
ExecStart=/opt/copypan/back_mic/backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable copypan
sudo systemctl start copypan
sudo systemctl status copypan
```

---

## 四、HTTPS（可选）

使用 Let's Encrypt 免费证书：

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d 你的域名.com
```

证书会自动续期，Nginx 会改用 443 端口。

---

## 五、上传数据存储位置

部署到服务器后，管理端上传的文件会保存在：

```
/opt/copypan/back_mic/backend/database/upload/YYYYMMDD/
```

与本地逻辑一致，只是路径在服务器上。

---

## 六、快速检查清单

| 项目 | 检查命令 |
|------|----------|
| ES | `curl http://localhost:9200` |
| Redis | `docker exec redis redis-cli ping` |
| 后端 | `curl http://localhost:8000/api/ai_search/health` |
| 前端 | 浏览器访问 `http://你的域名` |
| 登录 | 默认 admin / Pass2Pansearch |

---

## 七、故障排查

- **502 Bad Gateway**：后端未启动或端口错误，检查 `systemctl status copypan`
- **ES 连接失败**：确认 ES 容器运行，`curl localhost:9200`
- **AI 搜索报错**：检查 `.env` 中 `CLAUDE_API_KEY`，以及 Redis 是否运行
- **CORS 错误**：确认 `main.py` 中已添加前端访问的域名

---

## 八、自动化部署脚本

项目根目录已有 `deploy.sh`，可适配你的服务器路径后使用。部署前请根据本指南完成首次环境搭建和数据迁移。
