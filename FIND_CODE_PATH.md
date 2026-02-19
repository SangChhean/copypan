# 查找代码路径指南

## 方法 1: 查找代码位置

```bash
# 查找 copypan 目录
find / -name "copypan" -type d 2>/dev/null

# 查找 requirements.txt 文件
find / -name "requirements.txt" 2>/dev/null | grep backend

# 查找 main.py（FastAPI 入口文件）
find / -name "main.py" 2>/dev/null | grep backend

# 查找 ai_service.py
find / -name "ai_service.py" 2>/dev/null
```

## 方法 2: 检查常见位置

```bash
# 检查用户目录
ls -la ~/
ls -la /home/
ls -la /var/www/
ls -la /opt/
ls -la /srv/
```

## 方法 3: 如果代码还没上传

### 选项 A: 使用 Git 克隆

```bash
# 创建项目目录
mkdir -p ~/copypan
cd ~/copypan

# 克隆代码（替换为你的实际仓库地址）
git clone <your-repo-url> .

# 或如果代码在子目录
git clone <your-repo-url> temp
mv temp/* .
mv temp/.* . 2>/dev/null
rmdir temp

cd back_mic/backend
```

### 选项 B: 使用 SCP 从本地电脑上传

**在本地电脑执行（Windows PowerShell 或 Linux/Mac）：**

```bash
# 上传整个 back_mic 目录
scp -r back_mic root@your-server-ip:/root/copypan/

# 然后 SSH 到服务器
ssh root@your-server-ip
cd ~/copypan/back_mic/backend
```

### 选项 C: 使用 SFTP

1. 使用 WinSCP (Windows) 或 FileZilla
2. 连接到服务器
3. 上传 `back_mic` 文件夹到 `/root/copypan/`
4. SSH 到服务器执行：`cd ~/copypan/back_mic/backend`

## 方法 4: 直接创建目录并上传

```bash
# 在服务器上创建目录
mkdir -p ~/copypan/back_mic/backend
cd ~/copypan/back_mic/backend

# 然后从本地电脑上传文件
# 在本地执行：
# scp requirements.txt root@your-server-ip:/root/copypan/back_mic/backend/
```
