# 生命读经修订 阶段2 汇总

> 2026-11-06T12:49:00；本机 `http://localhost:9200` / `panai4_outline_12490`；未碰服务器。

## 结论摘要

(1) **闸门 G1–G6 全部通过**；未停在任何一道。
(2) 重算块=**343**，字符=**136,866**，usage_tokens=**None**（`embedding_adapter` 未返回 usage），费用按 $0.002/千块 = **$0.0007**。
(3) V4 余弦：min=**0.917792** / p1=0.957122 / p5=0.971588 / p50=0.996735 / p95=0.999686 / max=0.999841；低于 0.80 的块数=**0**。
(4) 写入成功=**348**，失败=**0**。
(5) reconcile：R1 same=**55841** diff=**0**；R2 checked=**648**（348+300）mismatch=**0**；R3 |ES|=**55841** mk=**12328**；R4 10/10 top1=自身（score≈0.999）；R5 全部满足（见下）；R6 header_fail=**0**/200；R7 count=**55841** version_changed=**348**。
(6) ES count 写前=**55841** / 写后=**55841**。
(7) embedding_adapter 环境变量名：`OPENROUTER_API_KEY`、`OPENROUTER_BASE_URL`、`EMBEDDING_KG_MODEL`、`EMBEDDING_KG_DIMS`（只报名称）；`.env` 在 `.gitignore` 中=**是**（含 `.env` / `*.env`）。
(8) **提醒：服务器尚未改动；本机已改，服务器仍是旧数据。**

## 各闸门

| 闸门 | 阶段 | 结果 |
| --- | --- | --- |
| G1 | prepare | 通过（book_path 52；regen same=55841；P2 全过；embed_jobs=343） |
| G2 | embed | 通过（343 向量，1024 维，28.4s） |
| G3 | assemble→verify 改名 | 通过（`chunks_12490_vec.new.json`） |
| G4 | verify_vec | 通过（V1–V3；V4 min≥0.80） |
| G5 | write_local | 通过（348 index，fail=0，count=55841） |
| G6 | reconcile | 通过（R1–R6） |

## R5 冒烟数字

- `雅歌生命读经`：41 块 / 10 篇；`雅歌书生命读经`：0
- `约翰二书生命读经`：11 块 / 2 篇；`约翰二书生命读经_`：0
- `成熟的表显（七）` → 创世记 109（1 hit）；`保罗为他使徒权柄的表白（八）` → 林后 57（1 hit）
- 生命读经篇题含「─」：0；以斯帖 `message_number=3`：5 块
- 约 17/36/37：`干渴`/`于`/`于`，不含 `乾`/`於`
- `book_path` 含 `雅歌书生命读经` / `约翰二书生命读经_`：均为 0

## 最终验证

- 备份目录 SHA256 与 `SHA256SUMS.txt` 一致=**True**
- `G:\PanAI4.0专用\纲目JSON\` 快照仍为 **41 文件 / 4,733,504,505 字节**
- ES：只在本机、只对 `panai4_outline_12490` 按 `_id` 覆盖写 348 文档；无 create/delete 索引，未碰其他索引与服务器
- git status `back_mic/backend/panai4/`：仅 `apply_life_fix.py`（本轮扩展）与既有 `probe_*` 未跟踪文件；无改其他现有代码
- 密钥泄露检查（内存比对日志/报告/暂存文本 vs 环境变量值）：**通过**
- 回滚脚本已写好未运行：`G:\PanAI4.0专用\_staging_life_fix\rollback_local.py`

## 产物路径

- 暂存：`G:\PanAI4.0专用\_staging_life_fix\`（含 `chunks_12490.new.json`、`chunks_12490_vec.new.json`、`embed_jobs.jsonl`、`embed_results.jsonl` 等）
- 分阶段报告：`docs/panai4_es/archive/life_fix_stage2_{prepare,embed,assemble,verify_vec,write_local,reconcile,rollback_local}.md`
