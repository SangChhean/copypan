# AI 搜索模块部署步骤（服务器）

## 1. SSH 连接服务器

```bash
ssh root@104.225.159.174
```

## 2. 进入项目目录

```bash
cd /opt/pansearch/code
```

## 3. 拉取最新代码

```bash
git pull origin master
```

## 4. 安装新依赖

```bash
cd back_mic/backend
pip install anthropic python-dotenv redis --break-system-packages
```

> 若使用系统自带的 Python 且遇权限问题，可加 `--break-system-packages`。若用虚拟环境则不需要该参数。

## 5. 配置环境变量

```bash
nano .env
```

在 `.env` 中**新增**一行（将下面的占位符换成你的真实密钥，切勿提交到 Git）：

```env
CLAUDE_API_KEY=你的Claude_API_Key
```

可选（Redis 缓存，默认连本机 6379）：

```env
REDIS_HOST=localhost
REDIS_PORT=6379
```

保存退出：`Ctrl+O` 回车，`Ctrl+X`。

## 6. 重启服务

```bash
/opt/pansearch/deploy.sh
```

## 7. 验证

健康检查（应返回 ES / Redis / Claude 状态）：

```bash
curl http://localhost:8000/api/ai_search/health
```

AI 搜索接口测试（需替换为你的认证方式，例如 Cookie 或 Token）：

```bash
curl -X POST http://localhost:8000/api/ai_search \
  -H "Content-Type: application/json" \
  -d '{"question": "圣经如何定义爱？", "max_results": 5}'
```

---

**安全提醒：** 不要把 `CLAUDE_API_KEY` 写进文档或代码，仅保存在服务器 `.env` 中，并确保 `.env` 已在 `.gitignore` 中。
