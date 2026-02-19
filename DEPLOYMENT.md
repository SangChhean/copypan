# 服务器部署指南

## 1. 上传代码到服务器

### 方法一：使用 Git（推荐）

```bash
# SSH 连接到服务器
ssh user@your-server-ip

# 克隆或拉取代码
git clone <your-repo-url>
# 或如果已存在，更新代码
cd copypan
git pull
```

### 方法二：使用 SCP 上传

```bash
# 在本地电脑执行（Windows PowerShell 或 Linux/Mac）
scp -r back_mic user@your-server-ip:/path/to/destination/
```

### 方法三：使用 SFTP 工具
- Windows: WinSCP, FileZilla
- Mac: Cyberduck, FileZilla
- 上传整个项目文件夹到服务器

## 2. 在服务器上安装依赖

### 步骤 1: 连接到服务器

```bash
ssh user@your-server-ip
cd /path/to/copypan/back_mic/backend
```

### 步骤 2: 检查 Python 和 pip

```bash
# 检查 Python 版本（需要 Python 3.8+）
python3 --version

# 检查 pip
python3 -m pip --version

# 如果没有 pip，安装 pip
python3 -m ensurepip --upgrade
# 或
curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
python3 get-pip.py
```

### 步骤 3: 创建虚拟环境（推荐）

```bash
# 安装 virtualenv（如果未安装）
python3 -m pip install virtualenv

# 创建虚拟环境
python3 -m venv venv

# 激活虚拟环境
# Linux/Mac:
source venv/bin/activate
# Windows (如果服务器是 Windows):
venv\Scripts\activate
```

### 步骤 4: 安装依赖

```bash
# 确保在虚拟环境中（命令行前应该有 (venv) 标识）
# 升级 pip
pip install --upgrade pip

# 安装所有依赖
pip install -r requirements.txt

# 如果遇到编码问题（Windows），可以尝试：
pip install -r requirements.txt --no-cache-dir
```

### 步骤 5: 验证安装

```bash
# 检查关键包是否安装成功
python3 -c "import fastapi; print('FastAPI OK')"
python3 -c "import anthropic; print('Anthropic OK')"
python3 -c "import google.genai; print('Google GenAI OK')"
python3 -c "import redis; print('Redis OK')"
python3 -c "import elasticsearch; print('Elasticsearch OK')"
```

## 3. 配置环境变量

```bash
# 创建或编辑 .env 文件
cd /path/to/copypan/back_mic/backend
nano .env  # 或使用 vi, vim, emacs

# 添加必要的环境变量
CLAUDE_API_KEY=your-claude-api-key
GEMINI_API_KEY=your-gemini-api-key
REDIS_HOST=localhost
REDIS_PORT=6379
```

## 4. 启动服务

```bash
# 确保在虚拟环境中
source venv/bin/activate  # Linux/Mac

# 启动服务
uvicorn main:app --host 0.0.0.0 --port 8000

# 或使用后台运行（使用 nohup）
nohup uvicorn main:app --host 0.0.0.0 --port 8000 > app.log 2>&1 &

# 或使用 systemd 服务（推荐生产环境）
# 创建服务文件：/etc/systemd/system/copypan.service
```

## 5. 常见问题解决

### 问题 1: pip 安装失败 - 编码错误
```bash
# 设置环境变量
export LC_ALL=en_US.UTF-8
export LANG=en_US.UTF-8
pip install -r requirements.txt
```

### 问题 2: 缺少编译工具（Linux）
```bash
# Ubuntu/Debian
sudo apt-get update
sudo apt-get install python3-dev build-essential

# CentOS/RHEL
sudo yum install python3-devel gcc gcc-c++
```

### 问题 3: 某些包安装失败
```bash
# 单独安装失败的包
pip install package-name --no-cache-dir

# 或使用国内镜像源（如果网络慢）
pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 问题 4: docx2pdf 需要系统依赖
```bash
# Ubuntu/Debian - 需要 LibreOffice
sudo apt-get install libreoffice

# CentOS/RHEL
sudo yum install libreoffice
```

## 6. 使用 systemd 管理服务（生产环境推荐）

创建服务文件：`/etc/systemd/system/copypan.service`

```ini
[Unit]
Description=Copypan Backend Service
After=network.target

[Service]
Type=simple
User=your-username
WorkingDirectory=/path/to/copypan/back_mic/backend
Environment="PATH=/path/to/copypan/back_mic/backend/venv/bin"
ExecStart=/path/to/copypan/back_mic/backend/venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

启用和启动服务：
```bash
sudo systemctl daemon-reload
sudo systemctl enable copypan
sudo systemctl start copypan
sudo systemctl status copypan
```

## 7. 查看日志

```bash
# 如果使用 nohup
tail -f app.log

# 如果使用 systemd
sudo journalctl -u copypan -f
```
