# PanAI 4.0 数据包导出报告

> 只读现有 ES / 图谱 / 本地向量文件；未改源码与现有索引/图谱；未打开/打印 `.env`；未跑 `build_v4.py`；未 git commit。  
> 日期：2026-11-07

## 结论摘要

- **拆成两个包**（ES 压缩后约 **2.64 GB > 1.5 GB**，按约定拆分）：
  - `G:\PanAI4.0专用\数据包\PanAI4.0_ES数据包_20261107.zip`（**2,764,415,696** bytes ≈ **2.64 GB**）
  - `G:\PanAI4.0专用\数据包\PanAI4.0_图谱数据包_20261107.zip`（**29,298,212** bytes ≈ **27.9 MB**）
- 十个索引本机文档数与包内向量/导出文档数 **全部一致**；图谱 dump SHA 与本机 neo4j-v4 **7334 / 52426 / Scripture 4851 / 4 约束**一致，**复用**既有 dump。
- 验证：**全部通过**（解压 SHA、dry-run、`__verify` 全量导入、原索引与图谱不变、包内无真实密钥）。

---

## 一、盘点

### 1.1 ES 文档数 vs 本地向量文件

| 索引 | 本机 ES | 本地向量/数据 | 本地路径形态 | 字节 | 相等 |
|------|---------|---------------|--------------|------|------|
| panai4_outline_12490 | 55841 | 55841 | `03_向量/chunks_12490_vec.new.json` | 1,386,795,176 | 是 |
| panai4_outline_feasts | 11110 | 11110 | `03_向量/chunks_feasts_vec.json` | 278,483,135 | 是 |
| panai4_bible | 3691 | 3691 | `03_向量/chunks_bible_vec.json` | 91,283,031 | 是 |
| panai4_hymns | 9154 | 9154 | `03_向量/chunks_hymns_vec.json` | 214,410,176 | 是 |
| panai4_text_life | 39463 | 39463 | `03_向量/shards/*.jsonl`（20） | 982,971,035 | 是 |
| panai4_text_cwwl | 178107 | 178107 | `03_向量/shards/*.jsonl`（90） | 4,475,183,876 | 是 |
| panai4_text_cwwn | 32032 | 32032 | `03_向量/shards/*.jsonl`（17） | 806,282,342 | 是 |
| panai4_text_others | 15481 | 15481 | `03_向量/shards/*.jsonl`（8） | 385,268,164 | 是 |
| panai4_map_note | 16052 | 16052 | `03_向量/shards/*.jsonl`（9） | 391,960,028 | 是 |
| panai4_pano_catalog | 53151 | 53151 | 无向量；`catalog_clean.json` flatten → 包内 `docs.jsonl` | （导出 JSONL） | 是 |

ES 版本：**8.19.0**。原始向量合计约 **9.04 GB**。

### 1.2 Mapping（本机）

| 索引 | 向量字段 | dims | similarity | index_options |
|------|----------|------|------------|---------------|
| outline_12490 / feasts / bible / hymns | `embedding` | 1024 | cosine | int8_hnsw（m=16, ef_construction=100） |
| text_life / cwwl / cwwn / others / map_note | `text_vector` | 1024 | cosine | int8_hnsw |
| pano_catalog | mapping 预留 `text_vector`，文档**不写向量** | 1024 | cosine | int8_hnsw |

可复用逻辑（仅抽取进包内脚本，未改业务代码）：

- `panai4/outline/index_to_es.py`：`OUTLINE_MAPPING` / `BIBLE_MAPPING` + bulk
- `panai4/hymns/config.py`：`mapping_body()`
- `panai4/inherit/index_to_es.py`：`build_mapping` + `to_es_doc`（`embedding`→`text_vector`）
- `panai4/pano/index_to_es.py`：`PANO_MAPPING` + `flatten` / bulk（`_id=node_id`）

### 1.3 图谱

| 项 | 值 |
|----|-----|
| 容器 / 镜像 | `neo4j-v4` / `neo4j:5.26.28` |
| Bolt | `7688`（`NEO4J_V4_URI`） |
| 节点 / 关系 / Scripture / 约束 | **7334 / 52426 / 4851 / 4** |
| dump 路径 | `G:\PanAI4.0专用\图谱上线\neo4j.dump`（10,507,204 bytes） |
| dump SHA256 | `B5B0C10C657E0FF03309A6D21603DC11B3152D66037F499EAD266948721089C4` |
| 与预期 | **一致 → 直接复用 dump，未重新 dump** |

约束名：`branch_name` / `scripture_ref` / `trunk_name` / `truth_point_name`。

### 1.4 两个大 JSON

| 文件 | 路径 | 大小 |
|------|------|------|
| organic_advance.json | `back_mic/backend/panai4/data/graph_annotations/` | 38,800,482 |
| truth_dictionary_3a3b.json | 同上 | 31,627,640 |

### 1.5 体积估算

| 部分 | 原始约 | 压缩后 |
|------|--------|--------|
| ES 十索引 | ~9.0 GB | **~2.64 GB**（单包超 1.5GB → 拆包） |
| 图谱 dump + 两 JSON | ~80 MB | **~27.9 MB** |

---

## 二、导入脚本

位置（在 ES 包内，**不在**业务代码目录）：

`es/import_to_local_es.py`

能力：`--es-url`（默认 `http://localhost:9200`）、`--user/--password` 或 `ES_USER`/`ES_PASSWORD`（兼容 `ES_USERNAME`）、内置十索引 mapping、JSONL bulk、`_id=chunk_id`（pano 为 `node_id`）、已存在则跳过、`--force` 先提示再删、结束对照 MANIFEST、`--only`、`--dry-run`、`--index-suffix`（测试）、非 8.x 主版本拒绝。

inherit 类：文件字段 `embedding` → ES `text_vector`。

---

## 三、打包结果

### 3.1 路径与哈希

| 包 | 路径 | 大小 | SHA256 |
|----|------|------|--------|
| ES | `G:\PanAI4.0专用\数据包\PanAI4.0_ES数据包_20261107.zip` | 2764415696 | `A61457CDBFAF33EA34F082A0014A0DB6673CAF0CDEC509EAD6B2A4A59C8FD21B` |
| 图谱 | `G:\PanAI4.0专用\数据包\PanAI4.0_图谱数据包_20261107.zip` | 29298212 | `4803ADB9E8EDECCA06F4DA7F76066BCD2A473F5C67AC7BBA4E1A5B6C27ACAAA9` |

未生成单体 `PanAI4.0_数据包_20261107.zip`（压缩后 ES 已超 1.5GB）。

### 3.2 ES 包结构（154 文件）

- `README.md` / `MANIFEST.md` / `MANIFEST.json` / `SHA256SUMS.txt`
- `es/import_to_local_es.py`
- `es/data/<索引>/…`（单文件 JSONL 或 `shards/*.jsonl`；pano 为 `docs.jsonl`）

### 3.3 图谱包结构（8 文件）

- `README.md` / `MANIFEST.md` / `SHA256SUMS.txt`
- `graph/neo4j.dump`
- `graph/graph_annotations/organic_advance.json`
- `graph/graph_annotations/truth_dictionary_3a3b.json`
- `graph/load_graph.ps1` / `graph/load_graph.sh`（密码仅读 `NEO4J_V4_PASSWORD`；已有同名容器/volume 则停止）

---

## 四、验证结果

### 4.1 解压 + SHA256SUMS

解压到 `G:\PanAI4.0专用\数据包\_verify_extract\`：

| 包 | ok | bad | missing |
|----|----|----|---------|
| ES | 153 | 0 | 0 |
| 图谱 | 7 | 0 | 0 |

### 4.2 dry-run

`python import_to_local_es.py --dry-run --sha-file ..\SHA256SUMS.txt`：SHA 通过；十索引 file_docs == manifest **全部 True**。

### 4.3 本机 `__verify` 真实导入

- 使用 `--index-suffix __verify --force`
- 十个临时索引文档数全部 == MANIFEST（IMPORT_RC=0，约 38.6 分钟）
- 抽样（bible / text_life / hymns 各 3 条）：`_id == chunk_id`，向量维 **1024**；pano：`_id == node_id`，无 `text_vector` 内容
- **仅删除** `panai4_*__verify`；原 `panai4_*` 十索引文档数与导入前 baseline **完全一致**
- neo4j-v4：7334 / 52426 / 4851 / 4 约束，**未变**

### 4.4 包内容扫描

- 无 `.env` 文件
- 无 Bearer / api_key 字面量
- 无真实 IP（文档仅示例 `localhost`）
- README 中有占位符 `你的密码` / `你自己设的密码`（**非真实密钥**），用于教同事自设密码

---

## 五、给同事时注意

1. ES 需 **8.x + analysis-ik**。
2. 新测试台/图谱业务代码另发；本包只含数据与导入脚本。
3. 图谱脚本默认容器名 `neo4j-v4`、volume `neo4j_v4_data`、端口 7475/7688；冲突时需同事自行处理（脚本不自动删）。
4. 两 JSON 需手工放到 `back_mic/backend/panai4/data/graph_annotations/`。

## 六、无把握 / 需你决定的点

1. **拆包命名**：未提供单体 zip；若你希望再加一个仅含 README 索引的「总说明」小 zip，可以另做。
2. **pano**：包内是 flatten 后的 `docs.jsonl`（53151 行），不是原始 `catalog_clean.json` 树——导入更稳，但与「索引数据」目录原始形态不同。
3. **IK 插件**：若同事 ES 无 IK，创建索引会失败；README 已写明，未做「无 IK 降级 mapping」分支。
4. **load 脚本 volume 名** `neo4j_v4_data`：若你方服务器习惯其它名字，可再改一版脚本（当前包已按本机习惯写好）。
