# PanAI4 图谱上服务器 · 本机 dump 与验证

日期：2026-11-06  
约束：未打开/打印 `.env` 值；密码仅内存/环境变量（临时校验容器随机密码用后清除）；未连接服务器、未传文件；未运行 `build_v4.py`；未改脚本；未 commit；未碰 3.5 容器 `neo4j`。

上线包目录：`G:\PanAI4.0专用\图谱上线\`

---

## 1. 停库前基线（只读）

| 项 | 值 |
|---|---:|
| 节点总数 | **7334** |
| 关系总数 | **52426** |
| Truth_Point | 2380 |
| Branch | 91 |
| Trunk | 12 |
| Scripture | 4851 |

### 关系类型计数（34）

| type | n | type | n |
|---|---:|---|---:|
| BECOMES | 470 | INDWELLS | 1194 |
| BELONGS_TO_TRUNK | 2380 | IS_A | 226 |
| BUILT_INTO | 451 | LEADS_TO | 2797 |
| BY_MEANS_OF | 2044 | LOCATED_IN | 657 |
| CAUSES | 1097 | MINGLED_WITH | 295 |
| COINHERES_WITH | 278 | OF_BRANCH_DIRECTLY | 2380 |
| CONSUMMATED_IN | 190 | OF_BRANCH_INDIRECTLY | 1676 |
| CONTAINS | 491 | OPPOSES_CONTRASTS_WITH | 733 |
| CO_WITH | 1376 | OUT_OF | 728 |
| DISPENSED_INTO | 2155 | PRACTICED_AS | 3668 |
| EMBODIED_IN_REALIZED_AS | 196 | PROCESSED_THROUGH | 532 |
| EQUIVALENT_TO | 1189 | REVEALS | 1385 |
| EXPERIENCES_ENJOYS | 7854 | SIMULTANEOUS_WITH | 220 |
| EXPRESSES | 2174 | SPREADS | 904 |
| GRAFTING | 91 | SUPPORTED_BY | 9803 |
| IN | 1059 | TYPIFIES | 663 |
| INCORPORATED_WITH | 141 | UNITED_WITH | 929 |

其中分类 4 种 + `SUPPORTED_BY` + **29** 种语义关系。

### 约束

| name | 标签 | 属性 |
|---|---|---|
| truth_point_name | Truth_Point | name |
| scripture_ref | Scripture | ref |
| trunk_name | Trunk | name |
| branch_name | Branch | name |

### Truth_Point 标注属性非空数

| 属性 | 非空数 |
|---|---:|
| name | 2380 |
| name_en | 2380 |
| definition_3a | 2380 |
| definition_3b | 2070 |
| intrinsic_significance | 2380 |
| greek_terms | 2265 |
| hebrew_terms | 1527 |
| high_peak_content | 87 |
| mutuality | 116 |
| organic_advance | 69 |
| same_as | 8 |
| devine_argument | 189 |

基线与预期 7334 / 52426 **一致**。

---

## 2. dump 与本机恢复

| 事件 | 时刻（本地 +07） |
|---|---|
| `docker stop neo4j-v4` | **2026-11-06T23:41:52.763+07:00** |
| dump 完成并 `docker start neo4j-v4` | **2026-11-06T23:42:09.938+07:00** |
| Bolt 再次可用并完成复计 | **2026-11-06T23:42:28.534+07:00** |

| 时长口径 | 秒 |
|---|---:|
| 停容器 → 再 start | **≈17.2 s** |
| 停容器 → Bolt 可用且复计通过 | **≈35.8 s**（总停机/不可用窗口） |

### dump 命令（已执行）

- 停库后：临时容器镜像 `neo4j:5.26.28`，`--rm`
- 挂载：`neo4j_v4_data` → `/data`；`G:\PanAI4.0专用\图谱上线` → `/dump`
- 命令：`neo4j-admin database dump neo4j --to-path=/dump`
- 结果：成功；产物 `neo4j.dump`

| dump 文件 | 值 |
|---|---|
| 路径 | `G:\PanAI4.0专用\图谱上线\neo4j.dump` |
| 字节 | **10,507,204**（约 10.0 MiB） |
| SHA256 | `B5B0C10C657E0FF03309A6D21603DC11B3152D66037F499EAD266948721089C4` |

### 恢复后复计

节点 / 关系 / 各标签 / 各关系类型 / 约束名 / Truth_Point 标注非空数：**与基线完全一致**（`POST_OK True`）。  
3.5 容器 `neo4j` 全程未停（仍 Up）。

---

## 3. 临时容器校验 dump（一次性）

| 项 | 做法 |
|---|---|
| 临时卷 | `neo4j_v4_dump_verify_tmp`（新建） |
| load | `neo4j-admin database load neo4j --from-path=/dump --overwrite-destination=true` |
| 临时容器 | `neo4j-v4-dump-verify`，镜像 `neo4j:5.26.28` |
| 端口 | 宿主机 **17474 / 17687**（避开 7474/7475/7687/7688） |
| 密码 | 内存随机生成 → 仅注入容器 `NEO4J_AUTH` 与进程环境变量；**未打印、未写入报告/磁盘**；验证后清除 |

### 逐项结果（相对基线）

| 检查 | 结果 |
|---|---|
| 节点总数 7334 | 通过 |
| 关系总数 52426 | 通过 |
| 标签计数 | 通过 |
| 全部关系类型计数 | 通过 |
| 四唯一约束存在 | 通过 |
| Truth_Point 标注非空数 | 通过 |
| `SUPPORTED_BY` 计数 | 通过 |
| 29 种语义关系按类型计数 | 通过 |
| 抽样 20 个 Truth_Point 全属性（含 `organic_advance`、`high_peak_content`） | 通过 |

### 清理

- `docker rm -f neo4j-v4-dump-verify` → 无残留  
- `docker volume rm neo4j_v4_dump_verify_tmp` → 无残留  
- 临时密码环境变量已清除  

---

## 4. 上线包整理

目录：`G:\PanAI4.0专用\图谱上线\`

| 文件 | 说明 |
|---|---|
| `neo4j.dump` | 本机 dump |
| `SHA256SUMS.txt` | dump + 两个 JSON 的 SHA256 与字节；JSON **未复制**，只引用仓库内 `graph_annotations` 原路径 |
| `UPLOAD.ps1` | 上传命令清单；主机为 `root@<服务器IP>` 占位 |

两个 JSON 引用源：

- `G:\copypan\back_mic\backend\panai4\data\graph_annotations\organic_advance.json`（38,800,482；SHA `63A23205…FB8178`）
- `G:\copypan\back_mic\backend\panai4\data\graph_annotations\truth_dictionary_3a3b.json`（31,627,640；SHA `98721FD0…E7DAC1`）

`UPLOAD.ps1` 将 dump 传到 `/opt/pansearch/graph_deploy/`，JSON 传到 `/opt/pansearch/code/back_mic/backend/panai4/data/graph_annotations/`，并在服务器 `sha256sum` 核对。

**未生成**服务器 load / 起容器命令（等服务器现状后再定）。

---

## 5. 结尾声明

- 未碰服务器、未传任何文件  
- 未改任何脚本、未 git commit、未运行 `build_v4.py`  
- 未操作 3.5 容器 `neo4j`  
- 临时校验资源已删除  
- 密码检查通过：报告与日志无密码/密钥值  
