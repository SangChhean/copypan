# infra

4.0 问答的**容器与部署配置**（compose、Dockerfile、IK 插件与词典）。

## 组件

| 服务 | 镜像 | 端口（仅 127.0.0.1） | 数据 |
|------|------|----------------------|------|
| `qa4-neo4j` | `neo4j:5.26.28` | 7476→7474，7689→7687 | 外部卷 `qa4_neo4j_data` / `qa4_neo4j_logs` |
| `qa4-es` | `qa4-es:8.19.0-ik`（由 `Dockerfile.es` 构建） | **仅** 9202→9200（不发布 9300） | 宿主目录 `$QA4_ES_DATA_DIR`；词典 `./ik_config` 只读挂载 |

Compose 工程名：`qa4`（两个文件顶部均写 `name: qa4`）。

| 文件 | 内容 |
|------|------|
| `docker-compose.neo4j.yml` | 仅 `qa4-neo4j` 与其卷 |
| `docker-compose.es.yml` | 仅 `qa4-es`（含必填 `QA4_ES_DATA_DIR`） |

两服务**拆分**，避免 ES 必填变量牵连 Neo4j 的 `config` / `logs` / `ps` 等命令。

## ES 镜像与 IK

- **基础镜像**：`elasticsearch:8.19.0`（与本机 `elasticsearch8` 一致）
- **插件来源**：2026-11-09 从运行中的 `elasticsearch8` 只读 `docker cp`  
  `/usr/share/elasticsearch/plugins/analysis-ik` → `ik_plugin/analysis-ik/`（打进镜像）
- **词典/配置来源**：同日从同一容器  
  `/usr/share/elasticsearch/config/analysis-ik` → `ik_config/`（**不**打进镜像，运行时 `:ro` 挂载）
- 校验清单：`SHA256SUMS_ik_plugin.txt`、`SHA256SUMS_ik_config.txt`

## 数据目录要求

- 仅 **`docker-compose.es.yml`** 要求环境变量 **`QA4_ES_DATA_DIR`**（无默认值，防止数据误落仓库）。对 `docker-compose.neo4j.yml` 执行 compose 命令时**不需要**该变量。
- 建议本机：`G:\PanAI4.0专用\qa4_es_data`（`es_start.ps1` 默认值）。
- **Linux**：该目录须对容器内 elasticsearch 用户可写（通常 **uid 1000**）。

## 启动顺序

1. 图谱：`data_prep/graph_load.ps1` → `graph_start.ps1`（`-f docker-compose.neo4j.yml`）→（可选）`graph_verify.py`
2. ES：`data_prep/es_start.ps1`（`-f docker-compose.es.yml --build`）→（可选）`es_check_ik.ps1`
