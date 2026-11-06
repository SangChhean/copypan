# PanAI4 图谱上服务器 · 预检（只读）

日期：2026-11-06  
约束：未打开/打印 `.env` 内容值；报告与日志中**无密码/密钥值**（仅变量名）；未对服务器写入、未建容器、未改配置；未 dump、未停止本机容器；未运行 `build_v4.py`；未改脚本；未 git commit；未尝试连接服务器 Neo4j。

---

## 1. 本机图谱状态（`neo4j-v4`）

| 项 | 实况 |
|---|---|
| 容器名 | `neo4j-v4` |
| 镜像 | `neo4j:5.26.28` |
| 版本 / 版次 | Neo4j Kernel **5.26.28**，**community**（`CALL dbms.components()`） |
| 状态 | Up（本预检时运行中）；重启策略 `unless-stopped` |
| 数据卷 | 具名卷 `neo4j_v4_data` → 容器 `/data` |
| 日志卷 | 具名卷 `neo4j_v4_logs` → 容器 `/logs` |
| HTTP | 宿主机 **7475** → 容器 7474（绑定 `0.0.0.0`，即全网卡） |
| Bolt | 宿主机 **7688** → 容器 7687（绑定 `0.0.0.0`） |
| 库 | Community：业务库仅默认 **`neo4j`**（另有 `system`）；均为 online |
| 容器内相关环境变量名 | `NEO4J_AUTH`、`NEO4J_EDITION`、heap/pagecache 相关 `NEO4J_server_memory_*`（**值不记录**） |

同机另有旧容器 `neo4j`（镜像 `neo4j:5`，7474/7687）——那是 3.5，不是本次上架对象。

### 1.1 计数基线（本机只读查询，与预期一致）

| 口径 | 数量 |
|---|---:|
| 节点总数 | **7334** |
| Truth_Point | 2380 |
| Branch | 91 |
| Trunk | 12 |
| Scripture | 4851 |
| 关系总数 | **52426** |
| 关系类型种数 | 34（含分类 4 种、`SUPPORTED_BY`、29 种语义关系等） |

### 1.2 约束与索引

**约束（UNIQUENESS）**

| name | 标签 | 属性 |
|---|---|---|
| `truth_point_name` | Truth_Point | name |
| `scripture_ref` | Scripture | ref |
| `trunk_name` | Trunk | name |
| `branch_name` | Branch | name |

**索引**：上述四者各有配套 RANGE 索引（ONLINE）；另有节点/关系 LOOKUP 各 1。至少具备任务要求的 `truth_point_name`、`scripture_ref`。

### 1.3 磁盘与 dump 体量（只描述，未 dump）

| 项 | 大小 |
|---|---|
| 卷 `neo4j_v4_data`（Docker 口径） | ~549 MB |
| 其中 `databases/` | ~9.6 MB |
| 其中 `transactions/` | ~514 MB |
| 卷 `neo4j_v4_logs` | ~0.8 MB |

说明：`neo4j-admin database dump` 导出的是**数据库存储**，不是整卷（事务日志体积不会原样进 dump）。按当前 `databases/` 约 10 MB 粗估，**dump 文件多半在十几 MB 量级**（压缩后常更小）；保守可按 **≤50 MB** 预留传输与磁盘。整卷 ~550 MB 是「复制 volume 目录」的量级，不是 dump 量级。

本步**未**停止容器、**未**执行 dump。

---

## 2. 服务器侧：仓库与环境能摸到什么（只读，未连服务器）

### 2.1 ES 推送怎么连服务器（对照，非 Neo4j）

| 脚本 | 方式 | 环境变量名（仅名） |
|---|---|---|
| `panai4/push_remote_v2.py` | **直连**远程 Elasticsearch HTTP（`Elasticsearch(hosts=[http://HOST:PORT], basic_auth=…)`），无 SSH 隧道代码 | `ES_REMOTE_HOST`、`ES_REMOTE_PORT`、`ES_REMOTE_USERNAME`、`ES_REMOTE_PASSWORD` |
| `panai4/hymns/push_remote.py` | 同上，直连 | 同上 |

仓库内**没有**为 Neo4j 写的对等 `NEO4J_REMOTE_*` 推送脚本。

### 2.2 文档里关于服务器 Neo4j / 部署的记载

主要来源：`docs/PanAI4.0_新系统框架实施方案.md`（勘探日期写明 **2026.09.25** 等；部分规格相对当前本地已过时）。

文档可判断 / 不可判断：

| 问题 | 文档结论 | 备注 |
|---|---|---|
| 服务器是否已有 Neo4j | **有（3.5）**：`neo4j:5.26.23` Community，匿名卷，未限内存，`unless-stopped` | 这是旧库，不是本次 `neo4j-v4` 数据 |
| 服务器是否已有 `neo4j-v4` 容器 | **不知道（文档只写了本地/计划规格）** | 计划：容器名 `neo4j-v4`，端口 7475/7688，卷 `neo4j_v4_data`/`neo4j_v4_logs` |
| 计划镜像版本 | 文档写 `neo4j:5.26.23` | **本机现为 5.26.28**，上架时需对齐版本策略 |
| 服务器 OS | **不知道**（文档未写发行版） | — |
| 服务器内存 / 磁盘（当时） | 内存约 23G、可用约 14G；磁盘剩约 141G | 为 2026-09-25 快照，**现在不知** |
| SSH | 文档提到 root SSH 曾为密码登录、拟改密钥 | **不知当前是否仍如此**；仓库无 `SSH_HOST` 等变量 |
| 传文件方式 | 文档未规定 scp/rsync/对象存储 | **不知道**现行运维习惯 |
| `deploy.sh` | 存在；文档称当时主要 `docker start neo4j`（3.5），并计划给 `neo4j-v4` 加未运行则 start | 未在本预检中改脚本、未在服务器执行 |

另：文档曾写端口「对外开放，靠密码保护」——与下文安全建议冲突，上架时应改为**不绑公网**。

### 2.3 环境变量名存在性（本机 `.env` 经 dotenv 加载后只判空/非空）

| 变量名 | 状态 |
|---|---|
| `NEO4J_V4_URI` / `NEO4J_V4_USER` / `NEO4J_V4_PASSWORD` | **存在** |
| `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` | **存在**（3.5） |
| `NEO4J_REMOTE_*`（URI/USER/PASSWORD/HOST/PORT） | **均不存在** |
| `ES_REMOTE_HOST` / `PORT` / `USERNAME` / `PASSWORD` | **存在** |
| `SSH_HOST` / `SSH_USER` / `SERVER_HOST` / `DEPLOY_HOST` | **均不存在** |

`NEO4J_V4_URI` 形态分类：**localhost/loopback**，端口提示 **7688**（即指向本机 `neo4j-v4`，不是服务器）。  
**能否把同一组 `NEO4J_V4_*` 改成指向服务器？** 变量名可以复用，但：

- 当前值指向本机；改成服务器等于切换写入目标，有误连风险；
- 现有 graph 脚本多处要求 `NEO4J_V4_URI ≠ NEO4J_URI`，**不会**自动区分「本机 v4」与「服务器 v4」；
- **本预检未尝试连接服务器。**

`.env.example` 目前只有 `NEO4J_URI/USER/PASSWORD`（3.5），**未见** `NEO4J_V4_*` 示例行。

---

## 3. 应用对 neo4j-v4 / 旁路 JSON 的依赖

### 3.1 后端是否在线读取 neo4j-v4

| 范围 | 结论 |
|---|---|
| `main.py` | **无** Neo4j / `NEO4J_V4` 引用 |
| `kg_rag/` | **无** `NEO4J_V4` / `neo4j-v4` / 7688 / 7475；在线走 `NEO4J_URI`（3.5，默认 7687） |
| `back_shared/neo4j_client.py` | 仅 `NEO4J_URI` 等 3.5 变量 |
| `panai4/graph_client.py` | **不存在**（方案文档曾规划，未落地） |
| `panai4/graph/*.py` | **离线建图/导入/盘点脚本**连接 `NEO4J_V4_*`；不是 FastAPI 请求路径 |
| 已拆除的测试台 `panai4/sc/` | 已删除；历史盘点曾提到 `sc/stage1.py` 读 v4，**现已不在仓库** |

**结论（预期相符）：当前服务器上的 Web 应用没有必须连上 neo4j-v4 才能启动的代码路径。**  
上架图谱现阶段主要是 **数据到位**（备份/备灾/后续 4.0 检索）；**不是**「今天上线后主站立刻读 v4」。若日后接检索，再配服务器侧 `NEO4J_V4_*` 与只读账号。

### 3.2 `panai4/data/graph_annotations/` 两个大 JSON

| 文件 | 大小 | git |
|---|---:|---|
| `organic_advance.json` | 38,800,482（~38.8 MB） | 不进 git（需另传） |
| `truth_dictionary_3a3b.json` | 31,627,640（~31.6 MB） | 不进 git（需另传） |

相对仓库根目标路径（README 已写明）：

`back_mic/backend/panai4/data/graph_annotations/`

**谁读它们（代码检索）**

- 写入/复制：`import_annotation_v4.py`、`import_general_annotation.py`（建图批次）。
- 文案/盘点提及：`inventory_v4_pre.py`、目录内 `README.md`。
- **未见** `main.py` / `kg_rag` / 其它在线服务在运行时 `open()` 这两份文件。

含义：图谱节点上只有布尔标记（如 `organic_advance=true`、`definition_3a=true`）；**正文在 JSON**。现在应用还不读，但 README 要求服务器同路径保留——否则将来做「按 name 取正文」会缺文件。dump/load **不会**带上这两份 JSON，必须**单独传输**。

---

## 4. 方案对比与安全要点

### 方案 A：本机 dump → 传到服务器 → load（推荐方向）

**做法概要（Docker / Neo4j 5）**

1. 本机短暂停库或 `STOP DATABASE`（Community 常用：停容器或官方要求的 offline dump 流程）。
2. `docker exec` 进入工具环境，或用临时同版本镜像挂载同一 data 卷，执行：  
   `neo4j-admin database dump neo4j --to-path=...`
3. 将 `.dump` 拷到服务器（scp/rsync/对象存储等，见下方待决）。
4. 服务器起同大版本 Community 容器（建议 **5.26.28** 与本机一致，或文档计划的 5.26.x 并验证兼容），空库或新卷。
5. `neo4j-admin database load neo4j --from-path=... --overwrite-destination=true`（具体旗标以该小版本 `--help` 为准），再启动。
6. 只读核对：节点 7334、关系 52426、四约束存在。
7. 另传两个 `graph_annotations` JSON 到相同相对路径。

| 项 | 说明 |
|---|---|
| 停机多久 | 通常数分钟级（dump 小库很快；含停库+拷文件+load+启动）。精确未知，需你允许的窗口 |
| dump 预计大小 | **约十几 MB，保守 ≤50 MB**（远小于 550 MB 数据卷） |
| 传输可行方式 | scp/sftp、rsync、云盘/对象存储、经已有运维通道；仓库**未**规定一种 |
| 优点 | 一次快照，避免重跑长导入链与源文件依赖；计数易对账 |
| 缺点 | 需要短暂停本机 v4；服务器要准备同系版本容器与卷 |

### 方案 B：服务器上按顺序重跑导入脚本（不推荐）

需要本机已发生过的整条链（且依赖桌面「可导入资料」、3.5 只读库、多份 `docs/panai4_graph` 词表），大致顺序：

1. `build_v4.py`（基础节点 + 分类关系；历史上还迁过旧 6 种关系）  
2. `delete_old_relations.py`（删旧 6 种）  
3. 各标注导入：`import_annotation*.py` / `import_high_peak_content_v2.py` / `import_annotation_v4.py`（organic flag）等  
4. `import_general_annotation.py` + 复制 `truth_dictionary_3a3b.json`  
5. `import_relations_29.py`  
6. `import_scripture_nodes.py`  
7. `fix_scripture_text.py`  
8. `copy_to_bracket_inner.py`  

**更不推荐的原因**：步骤多、源文件散（桌面 JSON + 仓库 docs）、依赖本机 3.5、耗时长、任一步口径漂移会导致与本机 7334/52426 对不齐；且仍要单独处理 annotations JSON。不如 dump/load。

### 两方案共通安全要点

1. **Bolt（7687/映射端口）与 HTTP（7474/映射端口）不要对公网 `0.0.0.0` 裸奔**；只绑 `127.0.0.1` 或内网，经 SSH 隧道/反代访问。本机当前映射是 `0.0.0.0`——服务器不要照抄这个暴露方式。  
2. **服务器用新的强密码**，写入服务器环境变量（如 `NEO4J_V4_PASSWORD` / 容器 `NEO4J_AUTH`），**不要复用本机密码**，不要写进 git/报告。  
3. 与 3.5 容器/端口/密码隔离；脚本继续保证 `NEO4J_V4_URI ≠ NEO4J_URI`。  
4. dump/load 与 JSON 旁路文件分轨校验（SHA256）；load 后做计数与约束对账。  
5. 若暂时不需要浏览器 Browser，可不映射 7475。

---

## 5. 需要你决定的问题

1. **能不能 SSH 上服务器？** 账号形态（密钥 / 密码）、是否必须走跳板机？  
2. **传文件用哪条路？** scp、rsync、现有运维面板、对象存储，还是别的？  
3. **服务器上是否已有空的 / 旧的 `neo4j-v4`？** 若有，数据能否覆盖？镜像是否已是 5.26.x？  
4. **镜像版本钉哪一个？** 跟本机 `5.26.28`，还是文档旧述 `5.26.23`？  
5. **端口怎么开？** 仅本机回环 + SSH 隧道，还是内网网卡？是否映射 Browser 7475？  
6. **dump 期间本机 `neo4j-v4` 能否停几分钟？**（方案 A 需要）有无必须连本机 v4 的作业窗口要避开？  
7. **两个大 JSON（~70 MB）是否与 dump 同一批次传到服务器同相对路径？**  
8. **上架后是否立刻配置服务器应用的 `NEO4J_V4_*`？** 还是只落数据、应用暂不连？  
9. **是否接受方案 A（dump/load）为唯一实施路径？** 若否，是否仍要评估方案 B？

---

## 6. 结尾

- 未 dump、未停本机容器、未连接服务器、未传文件  
- 未运行 `build_v4.py`、未改脚本、未 commit  
- 密码/密钥：报告仅含变量名；**无值**  
- 本机基线已核对：7334 节点 / 52426 关系 / 四唯一约束齐全  
