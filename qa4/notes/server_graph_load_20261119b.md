# 服务器载入本机 dump `qa4_neo4j_dump_20261119b`（只写步骤，未在服务器执行）

本机现状：Scripture 4848、mutuality 已删、节点 7331、关系 52426。

本机 dump（20261119b）：

| 项 | 值 |
|---|---|
| 目录 | `G:\PanAI4.0专用\图谱上线\qa4_neo4j_dump_20261119b\` |
| 文件 | `neo4j.dump`（10,518,667 bytes） |
| SHA256 | `5D82F1735EB3A0FC675EB43FF07139707DA1C0ADB524956AFFC7DDCD8736B695` |

## 0. `graph_load.sh` 是否适用于「卷已存在、覆盖载入」

脚本：`qa4/data_prep/linux/graph_load.sh`

| 情况 | 行为 |
|---|---|
| 无 `--force`，且已有容器 `qa4-neo4j` 或卷 `qa4_neo4j_data` 非空 | **直接拒绝**，不删不载 |
| `--force` | `docker rm -f qa4-neo4j` → **`docker volume rm qa4_neo4j_data`** → 重建空卷 → `neo4j-admin database load … --overwrite-destination=true` |

**结论：** 对已有服务器数据，**只能走 `--force`**。它不是「就地覆盖卷内文件」，而是**删卷再建再 load**。  
**风险：**

1. 服务器上当前 `qa4_neo4j_data` 整卷销毁（含 11-09 以来若有改动）；回滚需另备 dump。
2. 脚本内硬编码 `EXPECTED_SHA=B5B0C10C…`（11-09 原始 dump）。**载入 20261119b 前必须把该常量改成新 dump 的 SHA256**，否则 SHA 核对失败中止。
3. `--force` 删卷后首次 `graph_start.sh` 会按你输入的密码初始化认证；须与日后使用密码一致（沿用原密码即可）。
4. 未碰旧容器 `neo4j` / `neo4j-v4`（脚本只允许 `qa4*` 名）。

## 1. 本机 → 服务器传输

```bash
# 本机（占位符）
scp "G:/PanAI4.0专用/图谱上线/qa4_neo4j_dump_20261119b/neo4j.dump" USER@HOST:/opt/qa4_transfer/neo4j_20261119b.dump
scp "G:/PanAI4.0专用/图谱上线/qa4_neo4j_dump_20261119b/SHA256SUMS.txt" USER@HOST:/opt/qa4_transfer/neo4j_20261119b.SHA256SUMS.txt
```

服务器核对：

```bash
cd /opt/qa4_transfer
sha256sum -c neo4j_20261119b.SHA256SUMS.txt
# 或: sha256sum neo4j_20261119b.dump
```

放到 load 目录（`graph_load.sh` 默认读 `$QA4_DATA_ROOT/graph/neo4j.dump`）：

```bash
# 先备份服务器上现有的 11-09 dump（回滚用，勿覆盖）
cp -a /opt/qa4_data/graph/neo4j.dump /opt/qa4_data/graph/neo4j.dump.20261109.bak
cp /opt/qa4_transfer/neo4j_20261119b.dump /opt/qa4_data/graph/neo4j.dump
```

## 2. 改 `EXPECTED_SHA` 后 load

```bash
cd /opt/qa4_repo/qa4/data_prep/linux
# 编辑 graph_load.sh：把 EXPECTED_SHA 改为
# 5D82F1735EB3A0FC675EB43FF07139707DA1C0ADB524956AFFC7DDCD8736B695
# 然后：
./graph_load.sh --force
# 等价于指定目录：
# ./graph_load.sh /opt/qa4_data/graph --force
```

> `graph_load.sh` 本身会 `docker rm -f qa4-neo4j`（`--force` 时），无需另写 `docker stop`；载入完成后再 `./graph_start.sh`。

## 3. 启动（沿用同一密码）

```bash
./graph_start.sh
# 提示输入 QA4_NEO4J_PASSWORD（不可见）→ 输入与原先 qa4-neo4j 相同的密码
# 等待日志出现 Started
```

## 4. 载入后核对

```bash
read -rs QA4_NEO4J_PASSWORD; echo
docker exec -i qa4-neo4j cypher-shell -u neo4j -p "$QA4_NEO4J_PASSWORD" -d neo4j --format plain \
  "MATCH (n) RETURN count(n) AS nodes;"
# 期望 nodes=7331
docker exec -i qa4-neo4j cypher-shell -u neo4j -p "$QA4_NEO4J_PASSWORD" -d neo4j --format plain \
  "MATCH ()-[r]->() RETURN count(r) AS rels;"
# 期望 rels=52426
docker exec -i qa4-neo4j cypher-shell -u neo4j -p "$QA4_NEO4J_PASSWORD" -d neo4j --format plain \
  "MATCH (n:Scripture) RETURN count(n) AS scripture;"
# 期望 scripture=4848
docker exec -i qa4-neo4j cypher-shell -u neo4j -p "$QA4_NEO4J_PASSWORD" -d neo4j --format plain \
  "MATCH (n) WHERE n.mutuality IS NOT NULL AND toString(n.mutuality)<>'' RETURN count(n) AS mutuality;"
# 期望 mutuality=0
docker exec -i qa4-neo4j cypher-shell -u neo4j -p "$QA4_NEO4J_PASSWORD" -d neo4j --format plain \
  "SHOW CONSTRAINTS YIELD name, type RETURN name, type ORDER BY name;"
docker exec -i qa4-neo4j cypher-shell -u neo4j -p "$QA4_NEO4J_PASSWORD" -d neo4j --format plain \
  "SHOW INDEXES YIELD name, type, state RETURN name, type, state ORDER BY name;"
# 期望：4 约束；索引均 ONLINE
unset QA4_NEO4J_PASSWORD
```

## 5. 回滚（回到 11-09 原始 dump + 再删 mutuality）

```bash
cp -a /opt/qa4_data/graph/neo4j.dump.20261109.bak /opt/qa4_data/graph/neo4j.dump
# 把 graph_load.sh 的 EXPECTED_SHA 改回 B5B0C10C657E0FF03309A6D21603DC11B3152D66037F499EAD266948721089C4
cd /opt/qa4_repo/qa4/data_prep/linux
./graph_load.sh --force
./graph_start.sh   # 同一密码
# 然后 REMOVE mutuality（服务器原 7334/4851 基数）：
read -rs QA4_NEO4J_PASSWORD; echo
docker exec -i qa4-neo4j cypher-shell -u neo4j -p "$QA4_NEO4J_PASSWORD" -d neo4j --format plain \
  "MATCH (n) WHERE n.mutuality IS NOT NULL REMOVE n.mutuality RETURN count(n) AS removed;"
unset QA4_NEO4J_PASSWORD
```
