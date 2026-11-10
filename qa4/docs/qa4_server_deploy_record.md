# qa4 服务器部署记录与交接状态（2026-11-09）

范围：PanAI 4.0 问答侧步骤 ①（独立图谱与 ES 容器）的服务器部分。时间戳除特别说明外，服务器日志为 UTC（北京/金边时间 = UTC+7）。

## 1. 结论

- 服务器上已有两个独立容器：`qa4-neo4j`（图谱）与 `qa4-es`（十个 `qa4_*` 索引，共 414,082 条）。
- 与本机已验证的版本一致：Neo4j 节点/关系/标签/约束/索引数相同；ES 文档数、IK 分词、BM25 命中数与最高分相同。
- 未改动任何现有服务与容器（旧 ES、neo4j、neo4j-v4、redis、back_mic/back_qa/back_cn、nginx）。
- 尚未做：两份图谱标注 JSON 放到仓库内对应相对路径；compose 项目名拆分；后端/前端；纲目侧同步机制。

## 2. 服务器环境事实

- 主机 core-buzz-1：Ubuntu 22.04，Docker 29.2.1，Compose v5.0.2，git 2.34，Python 3.10（系统已装 elasticsearch 客户端 8.19.3）。
- 内存 23G：部署前已用约 9.7G，swap 已用 3.2/4.0G（原本就紧）。磁盘 `/` 472G，部署前剩 130G，导入后剩约 111G。`vm.max_map_count=262144`。
- 现有容器：`elasticsearch8`（旧 ES，9201，开启认证，对 0.0.0.0 发布）、`neo4j`（7474/7687，0.0.0.0）、`neo4j-v4`（7475/7688，127.0.0.1）、`redis`、`nginx`（容器，未运行）。
- 现有服务由 systemd 管理：back-mic(8000)、back-qa(8001)、back-cn(8014)、anshifenliang(8020)、nginx(80/443)。代码目录 `/opt/pansearch/code`（copypan 的 clone，master，工作区有未提交改动，不要在其中做 qa4 的事）。
- **`/opt/copypan` 不是代码目录**：里面是旧 ES 的 `es8_config`、`es8_data`，不要动。
- `/opt/pansearch/deploy.sh`：在 `/opt/pansearch/code` 里 `git stash` → `git pull origin master` → `git stash pop`，构建三个前端并重启服务。不会清理未跟踪文件，不会遍历顶层目录，因此 `qa4/` 进入该目录无害。
- 隐患（非 qa4 造成）：ufw 只放行 22/80/443，但 Docker 发布的 9201/9301/7474/7687 绑在 0.0.0.0，Docker 会绕过 ufw，可能对外可达（旧 ES 无密码访问返回 401）。
- `deploy.sh` 第 65 行 `docker ps | grep -q "neo4j"` 过松（neo4j-v4 已让它失效）。

## 3. 部署产物

| 项 | 值 |
|---|---|
| 仓库 | `/opt/qa4_repo`（sparse clone，只含 `qa4/`），提交 `08b35a8a`，与 `/opt/pansearch/code` 完全分开 |
| 数据根 | `/opt/qa4_data/`：`es_data`（ES 数据）、`import_src`（数据包解压，约 8.4 GiB，154 文件）、`graph/neo4j.dump` |
| 日志 | `/opt/qa4_logs/`（解压、导入日志） |
| 传输目录 | `/opt/qa4_transfer/`：`es_pack_20261107.zip`、`neo4j.dump`、`organic_advance.json`、`truth_dictionary_3a3b.json` |
| qa4-neo4j | 镜像 neo4j:5.26.28；127.0.0.1:7476(http)、7689(bolt)；卷 `qa4_neo4j_data`（外部卷）、`qa4_neo4j_logs`；堆 1G、页缓存 512M、mem_limit=memswap=2g |
| qa4-es | 镜像 qa4-es:8.19.0-ik（基于本机已有 elasticsearch:8.19.0 构建）；127.0.0.1:9202；cluster_name=qa4；堆 2g；mem_limit=memswap=4g；数据绑定 `/opt/qa4_data/es_data`；IK 配置只读挂载自 `qa4/infra/ik_config` |
| `.env` | `/opt/qa4_repo/qa4/.env`（权限 600，只含非密码设置：堆、内存上限、数据/日志目录）。**密码不写入 `.env`，启动/导入时手动输入** |
| 网络 | compose 默认网络 `qa4_default` |

## 4. 数据哈希（均已在服务器核对）

- ES 数据包 zip：`A61457CDBFAF33EA34F082A0014A0DB6673CAF0CDEC509EAD6B2A4A59C8FD21B`（2,764,415,696 B）
- neo4j.dump：`B5B0C10C657E0FF03309A6D21603DC11B3152D66037F499EAD266948721089C4`（10,507,204 B）
- organic_advance.json：`63A2320504C535E5B54D6AC8B33E0F76CAFDFA5D330EDFE9CCBBAA15ABFB8178`
- truth_dictionary_3a3b.json：`98721FD096CBDB1E10080089D22FEDBA3A7973EB0F2C7B2F9BC14B66F3E7DAC1`
- 数据包解压：154 条，SHA256SUMS 核对 153 项，不一致 0（总字节 9,063,068,065）。
- IK 配置 13/13、IK 插件 9/9 与清单逐字节一致。

## 5. 执行顺序（摘要）

1. 服务器只读检查（环境、端口、内存、现有服务、deploy.sh）。
2. `git clone --filter=blob:none --sparse` 到 `/opt/qa4_repo`，`sparse-checkout set qa4`。
3. 本机 scp 上传数据包、dump、两份 JSON（使用 ASCII 文件名）；服务器核对哈希。
4. 创建 `.env`（非密码），`chmod 600`。
5. `data_prep/linux/graph_load.sh /opt/qa4_data/graph` → `graph_start.sh`（提示输入 Neo4j 密码，首次启动时写入库，之后必须一致）。
6. `es_unpack_pack.sh <zip> /opt/qa4_data/import_src <SHA256>`（zip 已改名，必须传第 3 个参数）。
7. `es_start.sh`（提示输入 ES 密码）。
8. 导入：`nohup python3 es_import.py --data-root /opt/qa4_data/import_src/es/data --only ...`，分两批（先 bible+hymns，再其余八个）。服务器无 tmux/screen，用 nohup；密码用 `read -rs` 放入环境变量后立刻 `unset`。

## 6. 验证结果

**图谱（服务器 = 本机）：** 节点 7334，关系 52426；Branch 91、Scripture 4851、Trunk 12、Truth_Point 2380；约束 4；索引 6 个全部 ONLINE。

**ES（日志与 `_cat/indices`，全部 green，docs.deleted=0，bulk_err=0）：**

| 索引 | 文档数 | 导入耗时 |
|---|---|---|
| qa4_bible | 3,691 | 14.7s |
| qa4_hymns | 9,154 | 25.9s |
| qa4_outline_12490 | 55,841 | 203.8s |
| qa4_outline_feasts | 11,110 | 33.6s |
| qa4_text_life | 39,463 | 134.8s |
| qa4_text_cwwl | 178,107 | 711.3s |
| qa4_text_cwwn | 32,032 | 111.4s |
| qa4_text_others | 15,481 | 53.1s |
| qa4_map_note | 16,052 | 60.2s |
| qa4_pano_catalog | 53,151 | 14.0s |
| 合计 | 414,082 | 第二批约 23 分钟 |

**抽查（与本机验证值逐项一致）：** `ik_smart` 对「神的经纶与基督的身体」→ 神的经纶 / 与 / 基督的身体；字段分词 → 神的经纶、经纶、与、基督的身体、基督、的、身体；hymns 的「奇异恩典」命中 433，最高分 5.898026；「十字架」命中 237，最高分 6.4432893。

**资源（导入后）：** qa4-es 约 2.8 GiB/4 GiB，qa4-neo4j 约 1.35 GiB/2 GiB，系统可用内存约 9.6G，容器未重启。

## 7. 本次发现并修正的问题

1. **CRLF 被 git 转换：** 本机 git 提交时把 `ik_config` 里 10 个词典文件的 CRLF 转成 LF，服务器 clone 后与旧 ES 的原始字节不符（13 个中 10 个校验失败）。证实方式：服务器文件补回 CRLF 后哈希与清单完全一致。修复：`qa4/.gitattributes` 对 `infra/ik_config/**`、`infra/ik_plugin/**` 设 `-text`，重新 add；用暂存区内容（`git show :路径`）而不是工作区校验，13/13、9/9 全部匹配。教训：校验要对仓库里存的字节，不能只对工作区。
2. **解压脚本条目数：** Linux 版把 zip 条目数 154 当作清单行数比较（实际 153），会在解压后失败。已拆成 `EXPECTED_ZIP_ENTRIES=154`、`EXPECTED_SUMS_ENTRIES=153`，并用小 zip 测试通过/失败两种情形。
3. **`.env` 不被读取：** 原设计 compose 用 `--project-directory infra` 只读 `infra/.env`，README 却让用户建 `qa4/.env`，内存上限会静默失效。已改为 `_common.sh` 安全读取（只接受 `QA4_*=`，忽略 PASSWORD 键），启动时打印生效设置，内存上限为空/0 时拒绝启动（除非 `QA4_ALLOW_NO_MEM_LIMIT=1`）。
4. **健康检查泄露密码到进程参数：** 改为容器内 `printf … | curl -K -`。
5. **`es_verify*.py` 硬编码 Windows 日志路径：** 已改为 `QA4_LOG_DIR` 优先，Linux 默认 `/opt/qa4_logs`。
6. **操作失误提醒：** 把后续命令一起粘进密码提示会导致 401；终端窗口"卡住"不等于进程卡住（解压 3.5 分钟就完成了），先用 `ps`/日志/`du` 判断，不要 Ctrl+C。

## 8. 运维注意

- **不要对 qa4 项目使用 `docker compose up --remove-orphans`**：ES 与 Neo4j 两个 compose 同用项目名 `qa4`，互为"孤儿"，会误删 `qa4-neo4j` 容器。
- 导入或重建期间不要运行 `deploy.sh`（三个 `npm run build` 与导入争抢内存；服务器 swap 已很紧）。
- Neo4j 密码只在首次启动写入数据卷，之后重启必须输入同一密码；ES 密码同理由 `ELASTIC_PASSWORD` 在首次建库时确定。密码只存密码管理器。
- 所有 qa4 脚本只允许操作 `qa4*` 容器，不碰 `neo4j`、`neo4j-v4`、`elasticsearch8`。
- `qa4-neo4j` 空载已用约 1.35/2 GiB（含页缓存）；禁止 swap，超限会被杀并由 `restart: unless-stopped` 拉起。接入后端后视情况上调到 2.5–3g。
- 服务器 root 目前用密码 SSH 登录，建议改密钥并关闭密码登录。

## 9. 待办

1. 把两份图谱标注 JSON 放到 `/opt/qa4_repo/qa4/data/graph_annotations/`（目前只在 `/opt/qa4_transfer/`，`data/` 被 gitignore，必须手动放置并核对哈希）。
2. 拆分两个 compose 的项目名（如 `qa4-es`、`qa4-graph`），并让 compose 自己创建 `qa4_neo4j_logs` 卷（消除两条警告）。
3. 抽查通过后，经批准再清理 `/opt/qa4_data/import_src`（约 8.4 GiB）与 `/opt/qa4_transfer/` 的大文件。
4. 旧 ES/neo4j 对外暴露端口的处理（单独评估，避免影响线上）。
5. 4.0 问答后续：纲目→问答单向同步机制设计、评测集（Redis monitor 最近 5000 条、SQLite 反馈，注意用户数据）、4.0 流程设计与后端/前端落在 `qa4/`、等待 Samuel Liu 对流程方案的回复。

## 10. 相关提交

- `bd054851`：qa4 初版（独立 Neo4j/ES、导入与等价验证脚本及报告）。
- `08b35a8a`：Linux 服务器脚本、内存上限、IK 配置按原字节存储、`.gitattributes`、日志路径修正。
