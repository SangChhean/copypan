# qa4 Linux 服务器部署脚本

面向 Ubuntu 22.04（与现有服务同机）。所有容器名以 `qa4` 开头；不改动非 qa4 容器。

## 依赖

| 组件 | 说明 |
|------|------|
| Docker / Compose | 已安装；可用镜像 `elasticsearch:8.19.0`、`neo4j:5.26.28` |
| Python 3.10 | 系统自带即可 |
| `elasticsearch` PyPI | **第三方库**（非标准库），服务器已有 `8.19.3` 可用；`es_import.py` 仅额外依赖此包 |
| 本仓库 `qa4/` | 含 `infra/` 镜像构建与 IK 配置 |

## 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `QA4_DATA_ROOT` | `/opt/qa4_data` | 绝对路径；脚本创建 `es_data` / `import_src`（Neo4j 用命名卷） |
| `QA4_LOG_DIR` | `/opt/qa4_logs` | 导入/解压/校验日志（`es_import.py` / `es_verify*.py` 会读此变量） |
| `QA4_ES_DATA_DIR` | `$QA4_DATA_ROOT/es_data` | ES 数据绑定挂载 |
| `QA4_ES_HEAP` | `2g`（compose 默认） | ES 堆 |
| `QA4_ES_MEM_LIMIT` | **必须设置**（如 `4g`） | 空/`0` 拒绝启动；测试可设 `QA4_ALLOW_NO_MEM_LIMIT=1` |
| `QA4_NEO4J_HEAP` | `1G` | Neo4j 堆 |
| `QA4_NEO4J_PAGECACHE` | `512M` | 页缓存 |
| `QA4_NEO4J_MEM_LIMIT` | **必须设置**（如 `2g`） | 空/`0` 拒绝启动；测试可设 `QA4_ALLOW_NO_MEM_LIMIT=1` |
| `EXPECTED_ZIP_ENTRIES` | `154` | 解压时 zip 文件条目数期望 |
| `EXPECTED_SUMS_ENTRIES` | `153` | SHA256SUMS.txt 有效行数期望 |

`.env`（`qa4/.env` 或 `qa4/infra/.env`）权限必须为 **600**。脚本只安全读取 `QA4_[A-Z0-9_]+=` 行，**不 source**；已在环境中的变量优先；含 `PASSWORD` 的键一律忽略（若值非空会警告）。

服务器建议 `.env` **只放非密码设置**：

```bash
QA4_ES_HEAP=2g
QA4_ES_MEM_LIMIT=4g
QA4_NEO4J_HEAP=1G
QA4_NEO4J_PAGECACHE=512M
QA4_NEO4J_MEM_LIMIT=2g
QA4_DATA_ROOT=/opt/qa4_data
QA4_LOG_DIR=/opt/qa4_logs
```

密码在 `es_start` / `graph_start` / `es_import_run` 交互输入。Neo4j 的 `NEO4J_AUTH` **仅对尚未初始化的数据卷生效**；dump load 后请使用当初设库密码。

## 完整执行顺序

在 `qa4/data_prep/linux` 下用 `bash ./xxx.sh` 执行。

### 0. 准备目录与 .env

```bash
sudo mkdir -p /opt/qa4_data /opt/qa4_logs
cp ../../.env.example ../../.env
# 编辑 .env：只填堆/mem_limit/数据根等，不要写密码
chmod 600 ../../.env
```

验证：

```bash
stat -c '%a %n' ../../.env    # 期望 600
```

### 1. 解压 ES 数据包

zip **改名**后无法从 DATA_MANIFEST 按文件名匹配时，必须传第 3 个参数（期望 SHA256）：

```bash
bash ./es_unpack_pack.sh /path/to/PanAI4.0_ES数据包_xxxx.zip
# 改名示例：
bash ./es_unpack_pack.sh /path/to/es_pack.zip /opt/qa4_data/import_src A61457CDBFAF33EA34F082A0014A0DB6673CAF0CDEC509EAD6B2A4A59C8FD21B
```

验证：

```bash
test -f /opt/qa4_data/import_src/SHA256SUMS.txt
grep -E 'zip 文件条目数=154|核对文件数=153|解压与 SHA 核对全部通过' /opt/qa4_logs/qa4_unpack_*.log | tail -n 5
```

### 2. 构建并启动 qa4-es

```bash
bash ./es_start.sh
```

验证：

```bash
docker ps --filter name=^/qa4-es$ --format '{{.Names}} {{.Status}}'
# 宿主机健康检查勿把密码放进 argv；可在容器内：
docker exec qa4-es bash -c 'printf "user = \"elastic:%s\"\n" "$ELASTIC_PASSWORD" | curl -s -K - http://localhost:9200/_cluster/health'
docker ps --format '{{.Names}}' | grep -v '^qa4' | head
```

### 3. 导入 ES 索引

```bash
bash ./es_import_run.sh
# 可先：bash ./es_import_run.sh --offline --dry-run
```

验证：

```bash
ls -lt /opt/qa4_logs/qa4_import_*.log | head
```

### 4. 加载 Neo4j dump

先单独准备 dump 目录（**不要**把含 2.7GB ES zip 的目录挂给 `graph_load`）：

```bash
mkdir -p /opt/qa4_data/graph
cp /path/to/neo4j.dump /opt/qa4_data/graph/
bash ./graph_load.sh /opt/qa4_data/graph
# 若需重建：bash ./graph_load.sh /opt/qa4_data/graph --force
```

验证：

```bash
docker volume ls | grep qa4_neo4j_data
docker run --rm -v qa4_neo4j_data:/data:ro neo4j:5.26.28 ls /data | head
```

### 5. 启动 qa4-neo4j

```bash
bash ./graph_start.sh
```

验证：

```bash
docker ps --filter name=^/qa4-neo4j$ --format '{{.Names}} {{.Status}}'
docker logs qa4-neo4j 2>&1 | grep -F Started | tail -n 1
# Browser http://127.0.0.1:7476  Bolt bolt://127.0.0.1:7689
```

## 保护逻辑摘要

- 只操作 `qa4*` 容器名；外项目占用同名则拒绝。
- 端口 9202 / 7476 / 7689：若已被占用且对应 qa4 容器未运行 → 拒绝。
- `QA4_*_MEM_LIMIT` 为空/`0` → 拒绝（除非 `QA4_ALLOW_NO_MEM_LIMIT=1`）。
- 解压目标非空 → 拒绝；dump/卷非空且无 `--force` → 拒绝。
- 密码仅 `read -rs` → 环境变量；健康检查用容器内 `curl -K -`，不进宿主机 argv。
- `.env` 非 600 → 拒绝；密码键不从 `.env` 加载。

## 与 Windows 脚本对应

| Linux | Windows (`qa4/data_prep/`) |
|-------|----------------------------|
| `es_start.sh` | `es_start.ps1` |
| `graph_start.sh` | `graph_start.ps1` |
| `graph_load.sh` | `graph_load.ps1` |
| `es_unpack_pack.sh` | `es_unpack_pack.ps1` |
| `es_import_run.sh` | `es_import_run.ps1` |
