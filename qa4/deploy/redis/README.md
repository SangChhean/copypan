# qa4-redis（本机 / 服务器）

专用 Redis，与 `copypan-redis` 等其它容器隔离。镜像 `redis:7`（与服务器现有 `redis:7-alpine` 同大版本）。

| 项 | 值 |
|----|----|
| compose 项目名 | `qa4-redis` |
| 容器名 | `qa4-redis` |
| 宿主绑定 | `127.0.0.1:${QA4_REDIS_HOST_PORT:-6381}` → 6379 |
| 数据卷 | `qa4_redis_data` |
| 内存 | `maxmemory 256mb` / `volatile-lru` |

## 本机启动 / 停止

在仓库根目录：

```bash
# 启动（只动本项目；不要加 --remove-orphans）
docker compose -f qa4/deploy/redis/docker-compose.yml up -d

# 日志
docker compose -f qa4/deploy/redis/docker-compose.yml logs -f --tail=100

# 停止
docker compose -f qa4/deploy/redis/docker-compose.yml stop

# 查看
docker compose -f qa4/deploy/redis/docker-compose.yml ps
```

本机默认无密码。`QA4_REDIS_URL` 示例：

```text
redis://127.0.0.1:6381/0
```

说明：阶段 0 曾写「使用 DB 1」；本专用容器默认用 **DB 0**（见上 URL）。若需 DB 1，把 URL 末尾改为 `/1`。

## 可选密码（本机或服务器）

1. 由 Srey 在宿主机创建 env 文件（**不进 git**），例如 `/etc/qa4/redis.env`，权限 `600`：

```text
REDIS_PASSWORD=（此处填写，勿在命令行粘贴）
```

2. 启动前：

```bash
export QA4_REDIS_ENV_FILE=/etc/qa4/redis.env
```

3. 若设置了密码，需用自定义 command 加 `--requirepass`（当前 compose 默认无密码；需要密码时由 Srey 在服务器覆盖 command，或另加包装脚本）。**不要**在 `docker compose` 命令行参数里写密码。

有密码时应用侧：

```text
redis://:口令@127.0.0.1:6381/0
```

## 服务器注意

- 只操作 `qa4-redis` 项目；**不要** `--remove-orphans`；不碰 `qa4-es` / `qa4-neo4j` / 其它 redis。
- 端口冲突时：`export QA4_REDIS_HOST_PORT=6382` 再 up。
