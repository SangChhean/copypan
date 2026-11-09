# data_prep

存放面向 **qa4 一侧** 的装库、核对与同步脚本。不操作现有 `panai4_*` / 现网 QA 容器（除非脚本明确写明且经人工确认）。

## 图谱：qa4-neo4j 部署脚本

与 11-06 服务器上线一致：先用 dump 载入命名卷，再启动正式容器，最后与本机 `neo4j-v4` 只读比对。

| 顺序 | 脚本 | 用途 |
|------|------|------|
| 1 | `graph_load.ps1` | 核对 dump SHA256 后，用一次性 `neo4j:5.26.28` 容器执行 `neo4j-admin database load`，写入卷 `qa4_neo4j_data`。不需要密码。已有非空卷或已有容器时需 `-Force`。 |
| 2 | `graph_start.ps1` | 交互输入密码（`Read-Host -AsSecureString`），仅在本进程设置 `QA4_NEO4J_PASSWORD`，`docker compose` 启动 `qa4-neo4j`，等待日志出现 `Started` 后清除环境变量。 |
| 3 | `graph_verify.py` | 只读比对 `bolt://localhost:7688`（neo4j-v4）与 `bolt://localhost:7689`（qa4-neo4j）。两库密码均 `getpass` 交互输入。`python graph_verify.py --self-test` 可不连库自测比对逻辑。 |
| — | `es_start.ps1` | 交互密码 + `QA4_ES_DATA_DIR`，`compose up -d --build qa4-es`，轮询 `_cluster/health` 至 green/yellow。 |
| — | `es_check_ik.ps1` | qa4-es 启动后：与 `elasticsearch8` 对照 IK 文件 sha256 与 `_analyze` 分词结果。 |
| — | `es_unpack_pack.ps1` | 核对 zip SHA256 后解压到 `qa4_import_src`，并按包内 `SHA256SUMS.txt` 逐文件核对（不连 ES）。 |
| — | `es_import.py` / `es_import_run.ps1` | 将 `panai4_*` 数据导入本机 `qa4-es` 为 `qa4_*`（不重算向量）。密码仅经 `QA4_ES_PASSWORD`。 |

推荐命令（在仓库根或本目录执行，**本阶段请勿擅自跑 load/start/真实解压导入**，等你确认后再执行）：

```powershell
cd qa4\data_prep
.\graph_load.ps1
.\graph_start.ps1
python graph_verify.py
```

### ES 数据包：解压 → 导入

在独立 PowerShell 窗口按顺序运行（长任务）：

```powershell
cd qa4\data_prep
.\es_unpack_pack.ps1
# 先试跑两个小索引
.\es_import_run.ps1 -Only panai4_hymns,panai4_bible
# 再导入其余八个（可省略 -Only，或显式列出）
.\es_import_run.ps1
```

离线看计划（不连 ES）：

```powershell
python es_import.py --data-root "G:\PanAI4.0专用\数据包\_stage_es\es\data" --offline --dry-run
```

### ES 只读对照：qa4_* ↔ panai4_*

导入完成后，在独立 PowerShell 窗口运行（只读，不改任何索引）：

```powershell
cd qa4\data_prep
.\es_verify_run.ps1 -OldUser elastic
# 可选：-Only hymns,bible  -SkipBm25  -SkipKnn
```

离线自测（不连 ES）：

```powershell
python es_verify.py --self-test
```

报告写到 `G:\PanAI4.0专用\logs\qa4_verify_<时间戳>.md` 与 `.json`。固定 BM25 查询见 `qa4/eval/es_verify_queries.json`（校验用，非评测集）。

若 content/knn/bm25 出现 FAIL，只读深挖：

```powershell
.\es_verify_diag_run.ps1 -OldUser elastic
python es_verify_diag.py --self-test
```

诊断报告：`G:\PanAI4.0专用\logs\qa4_verify_diag_<时间戳>.md` / `.json`。

正式容器定义：

- Neo4j：`qa4/infra/docker-compose.neo4j.yml`（端口 `127.0.0.1:7476` / `127.0.0.1:7689`，卷名 `qa4_neo4j_data` / `qa4_neo4j_logs`）
- ES：`qa4/infra/docker-compose.es.yml`（端口 `127.0.0.1:9202`，必填 `QA4_ES_DATA_DIR`）

两文件拆分，互不牵连 compose 变量。

### Windows PowerShell 5.1 注意

- 本目录所有 `.ps1` 必须为 **UTF-8 带 BOM**（`EF BB BF`），否则 PS 5.1 会按 ANSI/GBK 误读中文。
- 请用 `powershell.exe`（5.1）运行；不要假设只有 pwsh 7。
- `graph_verify.py` 凡文件读写须 `encoding="utf-8"`。
