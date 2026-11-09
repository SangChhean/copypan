# qa4-es 镜像与部署脚本报告（C-1）

> 构建镜像 `qa4-es:8.19.0-ik`，**未** `compose up` qa4-es，**未**创建卷。  
> 对 `elasticsearch8` 仅只读（`docker cp` / `exec` ls·cat·sha256sum·curl GET）。  
> 未打开/打印 `.env`；未改根 `.gitignore`；未碰其它容器运行状态。  
> 日期：2026-11-09。

---

## 1. elasticsearch8 勘察（只读）

### 1.1 环境变量名

```
ELASTIC_CONTAINER
ELASTIC_PASSWORD          ← 名存在；值未打印
ES_JAVA_OPTS
HOME
HOSTNAME
PATH
PWD
SHELL
SHLVL
_
discovery.type
xpack.security.enabled
```

（含 PASSWORD 的变量按约束只列名；其余敏感类未出现。）

### 1.2 允许打印值的变量

| 变量 | 值 |
|------|-----|
| `ES_JAVA_OPTS` | `-Xms2g -Xmx2g` |
| `discovery.type` | `single-node` |
| `xpack.security.enabled` | `true` |
| `xpack.security.http.ssl.enabled` | **未设置** |

### 1.3 `config/elasticsearch.yml` 全文

```yaml
cluster.name: "docker-cluster"
network.host: 0.0.0.0
```

（无 password/secret 行。）

### 1.4 config 目录文件

`analysis-ik/`、`elasticsearch-plugins.example.yml`、`elasticsearch.keystore`、`elasticsearch.yml`、`jvm.options`、`jvm.options.d/`（空）、`log4j2.file.properties`、`log4j2.properties`、`role_mapping.yml`、`roles.yml`、`users`、`users_roles`

### 1.5 `_cluster/settings`

```json
{ "persistent": {}, "transient": {} }
```

### 1.6 复制决策

| 项 | 处理 | 原因 |
|----|------|------|
| `discovery.type=single-node` | **复制**到 compose | 与现网一致，单节点 |
| `xpack.security.enabled=true` | **复制** | 与现网一致 |
| `xpack.security.http.ssl.enabled=false` | **显式设置** | 现网未设但 HTTP:9200+Basic 可用；任务要求关闭 HTTP SSL |
| `ES_JAVA_OPTS` 堆 2g | **复制口径** → `QA4_ES_HEAP` 默认 `2g` | 与现网 `-Xms2g -Xmx2g` 对齐 |
| `network.host=0.0.0.0` | **复制** | 来自 yml，容器内监听需要 |
| `cluster.name` | **不复制** `docker-cluster`，改为 `qa4` | 任务指定独立集群名 |
| `node.name` | 设为 `qa4-es` | 任务指定 |
| `elasticsearch.keystore` / users / roles | **不复制** | 密钥与账号；qa4 用 `ELASTIC_PASSWORD=${QA4_ES_PASSWORD}` 初始化 |
| 端口 9300 | **不发布** | 任务要求只发 9202→9200 |
| IK 插件目录 | **COPY 进镜像** | 与现网 jar/插件一致 |
| IK 词典 config/analysis-ik | **运行时 :ro 挂载** | 便于改词典不重建镜像 |

### 1.7 IK 源目录权限（`ls -ln`）

- `plugins/analysis-ik`：文件 **uid=0 gid=0 mode=755**
- `config/analysis-ik`：多数 **666**；`pansearch.dic` **644**；属主 0:0  
  Dockerfile 对插件目录复现 **0:0 / 755**。

---

## 2. 产物清单

| 路径 | 说明 |
|------|------|
| `qa4/infra/ik_plugin/analysis-ik/` | 9 个插件文件（含 jar） |
| `qa4/infra/ik_config/` | 13 个词典/配置（含 `pansearch.dic`、`IKAnalyzer.cfg.xml`） |
| `qa4/infra/SHA256SUMS_ik_plugin.txt` | 插件哈希清单 |
| `qa4/infra/SHA256SUMS_ik_config.txt` | 配置哈希清单 |
| `qa4/infra/Dockerfile.es` | `FROM elasticsearch:8.19.0` + COPY 插件 |
| `qa4/infra/docker-compose.es.yml` | `name: qa4`；仅 `qa4-es`（与 neo4j 文件拆分） |
| `qa4/infra/docker-compose.neo4j.yml` | `name: qa4`；仅 `qa4-neo4j`；卷 `qa4_neo4j_data` external |
| `qa4/data_prep/es_start.ps1` / `es_check_ik.ps1` | UTF-8 BOM |
| `.env.example` | 增 `QA4_ES_HEAP`、`QA4_ES_DATA_DIR` |

---

## 3. 验证结果

### 3.1 取出文件 vs elasticsearch8

| 对照 | 文件数 | 差异 |
|------|--------|------|
| plugins/analysis-ik：容器 ↔ 本地 | 9 | **0** |
| config/analysis-ik：容器 ↔ 本地 | 13 | **0** |

### 3.2 镜像 `qa4-es:8.19.0-ik`

- `docker build` **成功**
- `docker run --rm --entrypoint … sha256sum`：插件 9 文件与 elasticsearch8 **全部相同**
- `ls -ln`：属主 **0:0**，文件 **755**，与源一致

### 3.3 `docker compose config`

临时设置假 `QA4_NEO4J_PASSWORD` / `QA4_ES_PASSWORD` / `QA4_ES_DATA_DIR`：**通过**。

解析到的端口：

- `127.0.0.1:9202→9200`（qa4-es）
- `127.0.0.1:7476→7474`、`127.0.0.1:7689→7687`（qa4-neo4j）
- **无 9300**

挂载：

- `${QA4_ES_DATA_DIR}` → `/usr/share/elasticsearch/data`
- `./ik_config` → `/usr/share/elasticsearch/config/analysis-ik`（ro）
- `qa4_neo4j_data`（external）→ `/data`；`qa4_neo4j_logs` → `/logs`

环境变量名（qa4-es）：`node.name`、`cluster.name`、`network.host`、`discovery.type`、`xpack.security.enabled`、`xpack.security.http.ssl.enabled`、`ELASTIC_PASSWORD`、`ES_JAVA_OPTS`。

**不设 `QA4_ES_DATA_DIR` 时失败**（exit≠0），错误含：

```text
error while interpolating services.qa4-es.volumes.[]: required variable QA4_ES_DATA_DIR is missing a value: 请设置 QA4_ES_DATA_DIR
```

### 3.4 密码字面量

对 `qa4/` 脚本/yml 扫描：compose/脚本仅为 `${QA4_*_PASSWORD}` 变量引用。  
文档中历史「compose_config_dummy_only」与路径片段 `neo4j/es` 等误匹配，**非真实密钥**。

### 3.5 新 `.ps1`（powershell.exe 5.1）

| 文件 | 前三字节 | Parser |
|------|----------|--------|
| `es_start.ps1` | `EF BB BF` | errors=0 |
| `es_check_ik.ps1` | `EF BB BF` | errors=0 |

拒绝路径：临时移走 compose 后运行 `es_start.ps1` → 输出 `找不到 compose 文件: …`，exit=1；**未启动任何容器**；compose 已恢复。

### 3.6 中文 stdin 不变形

```text
docker run --rm -i --entrypoint sh qa4-es:8.19.0-ik -c cat
```

输入/输出 SHA256 相同：`7dceb22a95928d735ed005e07de67808f61c586e9e884032bf8e7b90b455b2b1`（len=43）。

### 3.7 任务前后 Docker 对照

| 类别 | 结果 |
|------|------|
| 容器列表 | **相同**（含既有 `qa4-neo4j`；**无** `qa4-es` 容器） |
| 卷列表 | **相同**（无新建 qa4-es 卷） |
| 镜像 | **仅新增** `qa4-es:8.19.0-ik` |

### 3.8 git

- `git status --short`：仍为 `?? qa4/`（及既有 `docs/panai4_graph/*`）；已跟踪文件未改。
- `git check-ignore`：`ik_plugin` 下 `.jar`、`ik_config` 下 `.dic` → **exit=1（不被忽略）**，可被 git 跟踪。根 `.gitignore` 未改。

### 3.9 目录体积

| 目录 | 文件数 | 总字节 |
|------|--------|--------|
| `qa4/infra/ik_plugin` | 9 | 1,565,204（≈1.49 MiB） |
| `qa4/infra/ik_config` | 13 | 8,443,961（≈8.05 MiB） |

---

## 4. 下一步（需你确认后再执行）

```powershell
cd qa4\data_prep
.\es_start.ps1
.\es_check_ik.ps1
```

---

## 5. es_check_ik.ps1 修复与首次实测（2026-11-09）

### 5.1 现象与根因

Windows PowerShell 5.1 下 `Get-FileHashMap` 原写法：

```powershell
docker exec $Container find $Dir -type f -exec sha256sum {} `;
```

裸 `{}` 被 PS 当作脚本块，并额外带上 `-inputFormat` 等参数，导致容器内 `find: unknown predicate '-inputFormat'`。

### 5.2 修复内容

**检查的文件（qa4/data_prep 全部 .ps1）：**

| 文件 | 检查结果 | 改动 |
|------|----------|------|
| `es_check_ik.ps1` | 含 `find -exec` 与裸 `{}`；多处 docker 输出捕获在 Stop 下 | **已改**：`docker exec ... sh -c "find $Dir -type f -print0 | xargs -0 sha256sum"`；新增 `Invoke-NativeCapture`（临时 `Continue` + `$LASTEXITCODE`）；`docker inspect` / `head` 同此 |
| `es_start.ps1` | 无裸 `{}`；`compose up` 与 `docker exec` 管道写文件在 Stop 下 | **已改**：上述两处临时 `Continue`，用本地 exit code 变量 |
| `graph_start.ps1` | 无裸 `{}`；`compose up`；`docker logs 2>&1` 在 Stop 下 | **已改**：临时 `Continue`；去掉 Stop 下的 `2>&1`，改为 `docker logs | Out-String` |
| `graph_load.ps1` | 无裸 `{}`；多处 docker 赋值与 `2>$null` | **已改**：`Invoke-NativeCapture`；volume/container 检查与 load/`rm`/`create` 均临时 `Continue` |

四个脚本均保持 UTF-8 BOM；Parser `errors=0`。

### 5.3 首次实测（powershell.exe 5.1，qa4-es 已在运行；只读，未重启任何容器）

完整输出（无密码）：

```text
==== 文件 SHA256 对照 ====
-- plugins/analysis-ik
OK   commons-codec-1.11.jar
OK   commons-logging-1.2.jar
OK   elasticsearch-analysis-ik-8.19.0.jar
OK   entitlement-policy.yaml
OK   httpclient-4.5.13.jar
OK   httpcore-4.4.13.jar
OK   ik-core-1.0.jar
OK   plugin-descriptor.properties
OK   plugin-security.policy
-- config/analysis-ik
OK   extra_main.dic
OK   extra_single_word.dic
OK   extra_single_word_full.dic
OK   extra_single_word_low_freq.dic
OK   extra_stopword.dic
OK   IKAnalyzer.cfg.xml
OK   main.dic
OK   pansearch.dic
OK   preposition.dic
OK   quantifier.dic
OK   stopword.dic
OK   suffix.dic
OK   surname.dic
文件哈希全部一致。
==== 分词对照 (_analyze) ====
analyzer=ik_smart
TOKEN_OK analyzer=ik_smart count=66
analyzer=ik_max_word
TOKEN_OK analyzer=ik_max_word count=179
IK 文件哈希与分词结果全部一致。
```

结果：plugins/analysis-ik 9 文件、config/analysis-ik 13 文件全部 **OK**；**文件哈希全部一致**；`ik_smart` / `ik_max_word` 均为 **TOKEN_OK**。exit=0。

---

## 6. compose 拆分（避免 ES 必填变量牵连 Neo4j）

### 6.1 变更

| 动作 | 路径 |
|------|------|
| 删除 | `qa4/infra/docker-compose.yml` |
| 新增 | `qa4/infra/docker-compose.neo4j.yml`（仅 qa4-neo4j + 卷） |
| 新增 | `qa4/infra/docker-compose.es.yml`（仅 qa4-es；仍含 `${QA4_ES_DATA_DIR:?…}`） |
| 脚本 | `graph_start.ps1` → neo4j 文件；`es_start.ps1` → es 文件 |
| 文档 | `infra/README.md`、`data_prep/README.md`、`qa4/README.md`、`es_infra_report` / `graph_scripts_report` |

两者顶层均 `name: qa4`。全仓已无对旧 `docker-compose.yml` 的引用。

### 6.2 拆分前后 `docker compose config` 对照（假密码/假数据目录仅限该命令）

对合并文件快照与拆分后各自 `config` 做**整段服务块逐行对比**：**MATCH**。

| 项 | qa4-neo4j（前=后） | qa4-es（前=后） |
|----|-------------------|----------------|
| 镜像 | `neo4j:5.26.28` | `qa4-es:8.19.0-ik` |
| 构建 | （无） | context=`qa4/infra`，dockerfile=`Dockerfile.es` |
| 端口 | `127.0.0.1:7476→7474`，`127.0.0.1:7689→7687` | `127.0.0.1:9202→9200`（无 9300） |
| 卷 | `qa4_neo4j_data`→`/data`（external），`qa4_neo4j_logs`→`/logs` | 数据 bind=`QA4_ES_DATA_DIR`；`ik_config`→`…/analysis-ik`（ro） |
| 环境变量名 | `NEO4J_AUTH`，`NEO4J_server_memory_heap_initial__size`，`NEO4J_server_memory_heap_max__size`，`NEO4J_server_memory_pagecache_size` | `ELASTIC_PASSWORD`，`ES_JAVA_OPTS`，`cluster.name`，`discovery.type`，`network.host`，`node.name`，`xpack.security.enabled`，`xpack.security.http.ssl.enabled` |

### 6.3 牵连解除证明

1. **拆分前**：对合并 `docker-compose.yml` 仅设 `QA4_NEO4J_PASSWORD`、**不设** `QA4_ES_DATA_DIR` → `config` **失败**（必填变量牵连整文件）。
2. **拆分后**：对 `docker-compose.neo4j.yml` 仅设 `QA4_NEO4J_PASSWORD`、**不设**任何 `QA4_ES_*` → `config` **成功**（exit=0）。
3. 对 `docker-compose.es.yml` 不设 `QA4_ES_DATA_DIR` → 仍失败，提示「请设置 QA4_ES_DATA_DIR」（仅影响 ES 文件）。

未执行 compose up/down；未改动任何容器运行状态。
