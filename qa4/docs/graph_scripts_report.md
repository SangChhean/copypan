# qa4-neo4j 部署脚本编写报告

> 只写文件，未创建/启动/停止/删除任何容器或卷；未打开/打印 `.env`；未改 `panai4/`。  
> 日期：2026-11-09。

## 已写入文件

| 路径 | 说明 |
|------|------|
| `qa4/infra/docker-compose.neo4j.yml` | 服务 `qa4-neo4j`，镜像 `neo4j:5.26.28`，端口 `127.0.0.1:7476/7689`，卷 `qa4_neo4j_data` / `qa4_neo4j_logs`（与 ES compose 拆分） |
| `qa4/data_prep/graph_load.ps1` | dump SHA 校验 + 一次性 load（UTF-8 BOM） |
| `qa4/data_prep/graph_start.ps1` | SecureString 交互密码 + compose up + 等 Started（UTF-8 BOM） |
| `qa4/data_prep/graph_verify.py` | 只读比对 + `--self-test` |
| `qa4/data_prep/README.md` | 运行顺序 load → start → verify |
| `qa4/docs/DATA_MANIFEST.md` | 补全 zip / JSON SHA256 |
| `qa4/.gitignore` | `/data/`；`!eval/**/*.jsonl` |
| `qa4/data/graph_annotations/*.json` | 两份外置大 JSON 副本（gitignore） |

---

## 验证

### 1. docker compose config（临时假密码，仅该命令）

```powershell
# 仅为 compose config 设置临时假密码（值不入库、不写入本文）
$env:QA4_NEO4J_PASSWORD = ([guid]::NewGuid().ToString())
docker compose -f qa4/infra/docker-compose.neo4j.yml --project-directory qa4/infra config
Remove-Item Env:QA4_NEO4J_PASSWORD
```

结果：**通过**。解析要点：

| 项 | 值 |
|----|-----|
| 镜像 | `neo4j:5.26.28` |
| 端口 | `127.0.0.1:7476→7474`，`127.0.0.1:7689→7687` |
| 卷 | `qa4_neo4j_data`→`/data`，`qa4_neo4j_logs`→`/logs`（`name:` 显式） |
| 堆/页缓存默认 | `1G` / `512M` |

**密码字面量**：对 `qa4/infra`、`qa4/data_prep` 脚本与 yml 检查 `NEO4J_AUTH: neo4j/${QA4_NEO4J_PASSWORD}` 仅为变量引用；`graph_start.ps1` / `graph_verify.py` 仅交互输入。未发现硬编码密码。  
（对全文粗扫时，历史报告里路径片段如 `neo4j/es/redis`、`/var/lib/neo4j/bin` 会误匹配 `neo4j/`，**不是**密码。）

### 2. 语法检查（必须用 Windows PowerShell 5.1 / `powershell.exe`）

执行宿主：`C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe`，`PSVersion=5.1.26100.9711`（Desktop）。**未使用 pwsh 7。**

| 文件 | 结果 |
|------|------|
| `graph_load.ps1` | `[Parser]::ParseFile` errors=**0** |
| `graph_start.ps1` | `[Parser]::ParseFile` errors=**0** |
| `graph_verify.py` | `python -m py_compile` **通过**；文件 I/O 约定 `encoding="utf-8"`（哈希 `raw.encode("utf-8")`） |

### 2b. UTF-8 BOM（PowerShell 5.1 必需）

用 `powershell.exe` 读取每个 `.ps1` 前三字节：

| 文件 | 前三字节 | UTF-8 BOM |
|------|----------|-----------|
| `qa4/data_prep/graph_load.ps1` | `EF BB BF` | 是 |
| `qa4/data_prep/graph_start.ps1` | `EF BB BF` | 是 |

说明：无 BOM 时 PS 5.1 会按系统 ANSI(GBK) 解码 UTF-8 源文件，中文与引号会损坏；上述文件均带 BOM，且在 **powershell.exe 5.1** 下 Parser 通过，AST 可匹配到源中的「找不到」等中文。

### 2c. 参数/前置条件拒绝（不载入 dump、不启动容器）

在 `powershell.exe` 5.1 下实际运行脚本的失败路径，输出捕获为 UTF-8 日志核对中文：

| 脚本 | 触发条件 | 退出码 | 中文提示（原文） | 是否触碰 docker load/up |
|------|----------|--------|------------------|-------------------------|
| `graph_load.ps1` | `-DumpDir` 指向空目录（无 `neo4j.dump`） | 1 | `找不到 dump: …\neo4j.dump` | 否（在 SHA/load 之前退出） |
| `graph_start.ps1` | 临时移走 `docker-compose.neo4j.yml` | 1 | `找不到 compose 文件: …\docker-compose.neo4j.yml` | 否（在密码/up 之前退出） |

运行后 `docker ps -a` / `docker volume ls` 仍无 `qa4-neo4j` / `qa4_neo4j_*`。

### 3. graph_verify `--self-test`（不连库）

```
PASS 缺失节点
PASS 多余节点
PASS 内容不同
PASS 关系重复
PASS 全同
PASS 标注 JSON 键排序稳定
SELF-TEST ALL PASSED
```

退出码 0。

### 4. 任务前后 Docker 状态对照

**任务前**与**任务后**均为：

容器：

```
neo4j-v4|neo4j:5.26.28|Up|0.0.0.0:7475->7474, 0.0.0.0:7688->7687
copypan-redis|redis:7-alpine|Up|0.0.0.0:6379->6379
elasticsearch8|elasticsearch:8.19.0|Up|0.0.0.0:9200->9200, 0.0.0.0:9300->9300
neo4j|neo4j:5|Up|0.0.0.0:7474->7474, 0.0.0.0:7687->7687
redis|redis:latest|Up|6379/tcp（无宿主映射）
```

卷名集合相同：

```
0002008efedde809cf3a366b80744b6ae8c37d59ecd7abc5cd57f7279dec2c46
a1dc60d6eb20a9e100817eadae5f21e3b74b7a94f86ebf011eb62edc7e233a6e
a13b864eaa478015d5efd8fd7c57c7cf178b2581cc2be79fa6c2376130710ed0
aa0f4698c4e79ef1c6d947646d55a2e681a70ff36a7fd3472efa4d39fdd15e8d
neo4j_v4_data
neo4j_v4_logs
```

**未出现** `qa4-neo4j` / `qa4_neo4j_data` / `qa4_neo4j_logs`（本任务未启动、未建卷）。

### 5. git status / check-ignore

`git status --short`：

```
?? docs/panai4_graph/export_pack.md
?? docs/panai4_graph/git_merge_conflict.md
?? docs/panai4_graph/git_merge_resolve.md
?? qa4/
```

与任务前相比仅 `qa4/` 内容增多（仍整体 `??`）；`docs/panai4_graph/*` 不变；已跟踪文件无改动。

| 路径 | `git check-ignore -q` 退出码 | 含义 |
|------|------------------------------|------|
| `qa4/data/a` | 0 | **被忽略**（`/data/`） |
| `qa4/eval/x.jsonl` | 1 | **不被忽略**（`!eval/**/*.jsonl`） |
| `qa4/backend/data/x` | 1 | **不被忽略**（不再用 `**/data/`） |

### 6. 大 JSON 复制 SHA256

| 文件 | 源 SHA256 | 副本 SHA256 | 一致 |
|------|-----------|-------------|------|
| organic_advance.json | `63A2320504C535E5B54D6AC8B33E0F76CAFDFA5D330EDFE9CCBBAA15ABFB8178` | 同左 | 是 |
| truth_dictionary_3a3b.json | `98721FD096CBDB1E10080089D22FEDBA3A7973EB0F2C7B2F9BC14B66F3E7DAC1` | 同左 | 是 |

源：`back_mic/backend/panai4/data/graph_annotations/`  
副本：`qa4/data/graph_annotations/`

---

## 下一步（需你确认后再执行）

1. `qa4/data_prep/graph_load.ps1`  
2. `qa4/data_prep/graph_start.ps1`（交互设密码）  
3. `python qa4/data_prep/graph_verify.py`  
