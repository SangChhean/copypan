# qa4 独立容器准备——本机只读摸底

> 只读探测。未创建/停止/删除容器或卷；未改已有文件；未打开/打印 `.env`；未跑 `build_v4.py`。  
> Docker inspect 仅用 `--format` 取镜像/端口/挂载/`ES_JAVA_OPTS`。  
> 日期：2026-11-09。

---

## 1. 本机 Docker：容器 / 卷 / 端口

### 1.1 全部容器

证据：`docker ps -a --format "table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}"`

| 名称 | 镜像 | 状态 | 端口映射 |
|------|------|------|----------|
| neo4j-v4 | neo4j:5.26.28 | Up | `7475→7474`, `7688→7687` |
| elasticsearch8 | elasticsearch:8.19.0 | Up | `9200→9200`, `9300→9300` |
| neo4j | neo4j:5 | Up | `7474→7474`, `7687→7687` |
| copypan-redis | redis:7-alpine | Up | `6379→6379` |
| redis | redis:latest | Up | **无宿主端口映射**（仅容器内 6379） |

### 1.2 全部数据卷名

证据：`docker volume ls --format "{{.Name}}"`

| 卷名 | 备注（来自容器 Mounts --format） |
|------|----------------------------------|
| neo4j_v4_data | neo4j-v4 → `/data` |
| neo4j_v4_logs | neo4j-v4 → `/logs` |
| a13b864eaa478015d5efd8fd7c57c7cf178b2581cc2be79fa6c2376130710ed0 | neo4j → `/logs` |
| aa0f4698c4e79ef1c6d947646d55a2e681a70ff36a7fd3472efa4d39fdd15e8d | neo4j → `/data` |
| a1dc60d6eb20a9e100817eadae5f21e3b74b7a94f86ebf011eb62edc7e233a6e | copypan-redis → `/data` |
| 0002008efedde809cf3a366b80744b6ae8c37d59ecd7abc5cd57f7279dec2c46 | 未能确认归属容器（本次未对所有卷做反向查找） |

### 1.3 本机已占用端口（含常见开发口）

证据：`Get-NetTCPConnection -State Listen -LocalPort …`

| 端口 | 状态 | 对应（结合 docker ps） |
|------|------|------------------------|
| 6379 | LISTEN | copypan-redis |
| 7474 | LISTEN | neo4j |
| 7475 | LISTEN | neo4j-v4 HTTP |
| 7687 | LISTEN | neo4j Bolt |
| 7688 | LISTEN | neo4j-v4 Bolt |
| 9200 | LISTEN | elasticsearch8 HTTP |
| 9300 | LISTEN | elasticsearch8 transport |
| 8000 / 8001 | **FREE** | QA/后端未在听 |
| 5173 / 5174 | **FREE** | Vite 未在听 |
| 3000 / 5601 / 8080 / 5432 / 27017 | **FREE** | — |

另有系统口在听（如 135、445、5040 等），与 ES/Neo4j/Redis 无关，略。

---

## 2. 本机 ES（elasticsearch8）

### 2.1 容器 / 镜像 / 端口 / 挂载 / 堆内存

证据：`docker inspect elasticsearch8 --format …`（仅 Image/Ports/Mounts/`ES_JAVA_OPTS`）

| 项 | 值 |
|----|-----|
| 容器名 | elasticsearch8 |
| 镜像 | elasticsearch:8.19.0 |
| 对外端口 | 9200、9300 |
| 数据挂载 | **bind**：`G:/copypan/es_data` → `/usr/share/elasticsearch/data` |
| 堆内存 | `ES_JAVA_OPTS=-Xms2g -Xmx2g` |

未打印其它环境变量。

### 2.2 版本

证据：容器内 `curl -u elastic:$ELASTIC_PASSWORD http://localhost:9200/`（密码未输出）

- Elasticsearch **8.19.0**（lucene 9.12.2）

### 2.3 IK 插件

证据：

- `_cat/plugins`：`analysis-ik` **8.19.0**
- `plugin-descriptor.properties`：`version=8.19.0`，`elasticsearch.version=8.19.0`，`name=analysis-ik`
- 插件目录：`/usr/share/elasticsearch/plugins/analysis-ik/`（含 `elasticsearch-analysis-ik-8.19.0.jar` 等）

### 2.4 analysis-ik 配置目录文件清单

路径：`/usr/share/elasticsearch/config/analysis-ik/`  
证据：`docker exec … ls -1 …`

| 文件名 |
|--------|
| IKAnalyzer.cfg.xml |
| extra_main.dic |
| extra_single_word.dic |
| extra_single_word_full.dic |
| extra_single_word_low_freq.dic |
| extra_stopword.dic |
| main.dic |
| **pansearch.dic**（存在） |
| preposition.dic |
| quantifier.dic |
| stopword.dic |
| suffix.dic |
| surname.dic |

`IKAnalyzer.cfg.xml` 中 `ext_dict` = `pansearch.dic`。

---

## 3. 本机 ES：`panai4_*` 十索引文档数

证据：容器内  
`curl … "_cat/indices/panai4_*?h=index,docs.count&s=index"`（只读 _cat）

| 索引 | docs.count |
|------|------------|
| panai4_bible | 3,691 |
| panai4_hymns | 9,154 |
| panai4_map_note | 16,052 |
| panai4_outline_12490 | 55,841 |
| panai4_outline_feasts | 11,110 |
| panai4_pano_catalog | 53,151 |
| panai4_text_cwwl | 178,107 |
| panai4_text_cwwn | 32,032 |
| panai4_text_life | 39,463 |
| panai4_text_others | 15,481 |
| **合计** | **414,082** |

与期望 **414,082** **一致**。

---

## 4. 本机 Neo4j `neo4j-v4`

证据：

- 容器：`docker ps` / `docker inspect neo4j-v4 --format` → 镜像 `neo4j:5.26.28`；卷 `neo4j_v4_data`→`/data`，`neo4j_v4_logs`→`/logs`；端口 7475/7688
- 统计：容器内 `/var/lib/neo4j/bin/cypher-shell`（凭据取自容器环境变量，**未打印**）

| 指标 | 实测 | 期望 | 结果 |
|------|------|------|------|
| 节点数 | 7,334 | 7,334 | 一致 |
| 关系数 | 52,426 | 52,426 | 一致 |
| Scripture | 4,851 | 4,851 | 一致 |
| 约束数 | 4 | 4 | 一致 |

---

## 5. 图谱 dump

路径：`G:\PanAI4.0专用\图谱上线\neo4j.dump`  
证据：`Test-Path` + `Get-Item.Length` + `Get-FileHash -Algorithm SHA256`

| 项 | 实测 | 对照（`docs/panai4_graph/export_pack.md`） |
|----|------|---------------------------------------------|
| 大小 | **10,507,204** 字节 | 10,507,204 | **一致** |
| SHA256 | `B5B0C10C657E0FF03309A6D21603DC11B3152D66037F499EAD266948721089C4` | 以 `B5B0C10C` 开头、以 `721089C4` 结尾；全文同文档记录 | **一致** |

---

## 6. 数据包（读 `docs/panai4_graph/export_pack.md` + 本机核对）

### 6.1 是否已生成

**是。** 文档写明拆成两个 zip；本机文件存在且大小一致。

证据：`Test-Path` + `Get-ChildItem G:\PanAI4.0专用\数据包`

| 包 | 路径 | 大小（字节） |
|----|------|--------------|
| ES | `G:\PanAI4.0专用\数据包\PanAI4.0_ES数据包_20261107.zip` | 2,764,415,696 |
| 图谱 | `G:\PanAI4.0专用\数据包\PanAI4.0_图谱数据包_20261107.zip` | 29,298,212 |

### 6.2 内容清单（文档 + zip 列表核对）

**ES 包**（zip 内 154 文件；顶层）：

- `README.md` / `MANIFEST.md` / `MANIFEST.json` / `SHA256SUMS.txt`
- `es/import_to_local_es.py`
- `es/data/<十个 panai4_* 索引>/…`

**图谱包**（8 文件）：

- `README.md` / `MANIFEST.md` / `SHA256SUMS.txt`
- `graph/neo4j.dump`
- `graph/graph_annotations/organic_advance.json`
- `graph/graph_annotations/truth_dictionary_3a3b.json`
- `graph/load_graph.ps1` / `graph/load_graph.sh`

### 6.3 `import_to_local_es.py` 是否存在

| 位置 | 存在 |
|------|------|
| 业务仓库 `g:\copypan` 内 | **否**（Glob 无匹配） |
| ES zip 内 `es/import_to_local_es.py` | **是** |
| 暂存目录 `G:\PanAI4.0专用\数据包\_stage_es\es\import_to_local_es.py` | **是** |

---

## 7. 导入脚本：索引名 / mapping / settings；改 `qa4_` 前缀

### 7.1 包内 `es/import_to_local_es.py`（从 zip 只读解析，未改文件）

| 内容 | 定义位置 |
|------|----------|
| **索引名** | `INDEX_SPECS` 字典的 **10 个 key**（约 L222–303），全部硬编码为 `panai4_*` |
| **mapping + settings** | 同文件内常量：`OUTLINE_MAPPING`、`BIBLE_MAPPING`、`HYMNS_MAPPING`、`PANO_MAPPING`、`inherit_mapping(...)`；每个 dict 内含 `"settings": {number_of_shards, number_of_replicas}` 与 `"mappings"` |
| 创建索引 | `es.indices.create(index=target, body=deepcopy(spec["mapping"]))`，`target = f"{index}{index_suffix}"` |
| 数据路径 | `resolve_files`：`data_root / index / …` → 依赖包内目录名 `es/data/panai4_*` |
| MANIFEST | `MANIFEST.json` → `indices[].name` 亦为 `panai4_*` |

**是否写死 `panai4_`：是**（`INDEX_SPECS` 十 key + 文档示例 L7–L8；`--index-suffix` **只能追加后缀**，例如 `__verify`，**不能**改前缀）。

### 7.2 若要从该脚本导入为 `qa4_*`（只写结论，不改）

最少需要动：

1. **`INDEX_SPECS` 的 10 个 key**：`panai4_` → `qa4_`（否则创建出的索引名仍是 panai4_*）。
2. **数据目录对齐**（二选一）：  
   - 把包内 `es/data/panai4_*` 目录改名为 `qa4_*`；或  
   - 改 `resolve_files`（约 L332–344）增加「逻辑索引名 → 目录名」映射（只改 key 不改目录会 `FileNotFoundError`）。
3. **`MANIFEST.json` 的 10 个 `indices[].name`**（若走 `load_manifest_expect` 校验；否则会回退到 `INDEX_SPECS["expect"]`，但仍建议一致）。
4. 文档示例中的 `--only panai4_bible`（L7–L8，非运行必需）。

**结论：核心硬编码处 = INDEX_SPECS 10 处 key；为跑通还需处理数据目录（或 resolve_files）+ 建议同步 MANIFEST 10 处 name。仅改 `--index-suffix` 不够。**

### 7.3 业务仓 `panai4/*/index_to_es.py`（备选路径，非包内脚本）

| 模块 | 索引名 | mapping/settings |
|------|--------|------------------|
| `panai4/outline/index_to_es.py` | JOB 内 `"index": "panai4_outline_12490|feasts|bible"`；另有 `ALLOWED_REMOTE_PREFIX = "panai4_"` | `OUTLINE_MAPPING` / `BIBLE_MAPPING`（含 settings） |
| `panai4/hymns/config.py` + `index_to_es.py` | `INDEX_NAME = "panai4_hymns"` | `mapping_body()` |
| `panai4/inherit/index_to_es.py` | 配置表 5 个 `"index": "panai4_text_*|map_note"` | `build_mapping(...)` |
| `panai4/pano/index_to_es.py` | `INDEX_NAME = "panai4_pano_catalog"` | `PANO_MAPPING` |

若走业务脚本而非包内导入器，硬编码 `panai4_` 散布更多（config、JOB、校验、远程前缀等），改动面显著大于包内 `INDEX_SPECS`。

---

## 8. 向量与源数据（清洗 JSON）

根目录：`G:\PanAI4.0专用\索引数据\`（十个子目录均存在）。  
子目录命名（UTF-8 实测）：`01_源文件` / `02_清洗JSON` / `03_向量`。

| 索引目录 | 向量形态（`03_向量`） | 向量字节 | 清洗 JSON 字节（`02_清洗JSON`） |
|----------|----------------------|----------|----------------------------------|
| panai4_outline_12490 | `chunks_12490_vec.new.json` | 1,386,795,176 | 239,302,784 |
| panai4_outline_feasts | `chunks_feasts_vec.json` | 278,483,135 | 59,191,267 |
| panai4_bible | `chunks_bible_vec.json` | 91,283,031 | 7,426,387 |
| panai4_hymns | `chunks_hymns_vec.json` | 214,410,176 | 6,416,833 |
| panai4_text_life | `shards/*.jsonl`（20） | 982,972,015 | 85,923,381 |
| panai4_text_cwwl | `shards/*.jsonl`（90） | 4,475,200,016 | 426,191,428 |
| panai4_text_cwwn | `shards/*.jsonl`（17） | 806,285,328 | 78,105,967 |
| panai4_text_others | `shards/*.jsonl`（8） | 385,269,571 | 33,383,696 |
| panai4_map_note | `shards/*.jsonl`（9） | 391,961,608 | 27,101,558 |
| panai4_pano_catalog | 无向量（`NO_VECTOR.md` 58B）；清洗含 `catalog_clean.json` | 58 | 66,057,343 |
| **合计** | | **9,012,660,114**（≈8.39 GiB / 文档称约 9.04 GB） | **1,029,100,644** |
| **向量+清洗** | | **10,041,760,758** | |

说明：分片文件数含目录内全部文件（可能含非 jsonl）；与 `export_pack.md` 字节级略有出入属正常（打包后/本地增量），数量级一致。

---

## 9. 两个外置大 JSON

| 文件 | 当前路径 | 大小（字节） |
|------|----------|--------------|
| organic_advance.json | `G:\copypan\back_mic\backend\panai4\data\graph_annotations\organic_advance.json` | 38,800,482 |
| truth_dictionary_3a3b.json | `G:\copypan\back_mic\backend\panai4\data\graph_annotations\truth_dictionary_3a3b.json` | 31,627,640 |

另有同大小副本：`G:\PanAI4.0专用\数据包\_stage_graph\graph\graph_annotations\` 下各一份；图谱 zip 内亦含（`export_pack.md` / zip 列表）。

与 `export_pack.md` 记录大小 **一致**。

---

## 未能确认清单

1. 匿名卷 `0002008e…` 归属哪个（已删除？）容器——未做全量反向映射。
2. 宿主上 `redis`（无端口映射）与 `copypan-redis` 的用途分工——仅知状态，未读配置。
3. ES 安全凭据具体值——按约束未读 `.env`；仅用容器内环境变量调用 API（未打印）。
4. 业务仓是否计划以包内 `import_to_local_es.py` 还是 `panai4/*/index_to_es.py` 作为 qa4 导入主路径——未在代码外约定中确认。
5. 本地 `03_向量` 分片字节与 `export_pack.md` / `MANIFEST.json` 逐字节是否要求完全一致——本次以本机目录实测为准，未强制对齐到包内 MANIFEST 每一字节。

---

## 验证

### V1. git status

执行：`git status --short`（本任务完成后实测）：

```
?? docs/panai4_graph/export_pack.md
?? docs/panai4_graph/git_merge_conflict.md
?? docs/panai4_graph/git_merge_resolve.md
?? docs/qa4_data/
?? docs/qa4_survey/
```

说明：相对本任务开始前，**仅新增** `docs/qa4_data/`（本报告）。`docs/panai4_graph/*`、`docs/qa4_survey/` 为既有未跟踪项；已跟踪文件无改动。

### V2. 报告路径存在性

| 路径 | 存在 |
|------|------|
| docs/panai4_graph/export_pack.md | True |
| docs/qa4_data/probe_local.md | True（本文件） |
| G:\PanAI4.0专用\图谱上线\neo4j.dump | True |
| G:\PanAI4.0专用\数据包\PanAI4.0_ES数据包_20261107.zip | True |
| G:\PanAI4.0专用\数据包\PanAI4.0_图谱数据包_20261107.zip | True |
| G:\PanAI4.0专用\数据包\_stage_es\es\import_to_local_es.py | True |
| G:\PanAI4.0专用\索引数据\（及十个 panai4_* 子目录） | True |
| G:\copypan\es_data | True |
| back_mic/backend/panai4/data/graph_annotations/organic_advance.json | True |
| back_mic/backend/panai4/data/graph_annotations/truth_dictionary_3a3b.json | True |
| back_mic/backend/panai4/outline/index_to_es.py | True |
| back_mic/backend/panai4/hymns/index_to_es.py | True |
| back_mic/backend/panai4/hymns/config.py | True |
| back_mic/backend/panai4/inherit/index_to_es.py | True |
| back_mic/backend/panai4/pano/index_to_es.py | True |

### V3. 第 3 项文档数相加

```
3691 + 9154 + 16052 + 55841 + 11110 + 53151 + 178107 + 32032 + 39463 + 15481
= 414082
```

十个数见第 3 节表；**合计 414,082**。
