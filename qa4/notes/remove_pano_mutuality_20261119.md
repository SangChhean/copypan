# 2026-11-19 本机删除 qa4_pano_catalog 与 mutuality

## 已做（仅 qa4-es / qa4-neo4j）

- 删除索引 `qa4_pano_catalog`（53151）→ 九索引合计 **360931**
- `REMOVE n.mutuality`：非空 116 → 0；节点 7331 / 关系 52426 / Scripture 4848 不变
- 配置与校验已同步到九索引 / 无 mutuality（见 expected_counts、index_map、retrieval、es_import、es_verify、stats_report、graph_verify 等）

## 服务器（2026-11-19 已同步）

- 同样删除 `qa4_pano_catalog` 与 `mutuality`；图谱用本机 dump（SHA256 `5D82F1735EB3A0FC675EB43FF07139707DA1C0ADB524956AFFC7DDCD8736B695`）重载。
- 核对：nodes 7331 / rels 52426 / Scripture 4848 / 4 约束 / 索引 ONLINE；指纹 vs 本机 `fp_now2.json` → **0 差异**（`fp_server_after_graph_20261119.json`）。
- Dump：`/opt/qa4_data/graph` 仍有 11-09 原版（另有 `neo4j.dump.20261109.bak`）；新 dump 在 `/opt/qa4_data/graph_20261119b`。
- **`qa4_outline_12490` 暂留**（`targeted.py` 的 `life_study()` 仍依赖）。

## 未改

- `back_mic` 下旧导入脚本与文档仍写 mutuality / pano（有意保留）
- 旧容器 `elasticsearch8`、`neo4j`、`neo4j-v4` 未触碰

## 指纹差异（before → after）

- `neo4j.prop_nonempty.mutuality`: 116 → 0
- `es.indices_set`: 去掉 `qa4_pano_catalog`（同批操作；若只比图谱则仅 mutuality 一项）

文件：`fp_before_mutuality_20261119.json` / `fp_after_mutuality_20261119.json`
