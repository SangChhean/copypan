# qa4 ES 只读对比脚本报告（C-3）

> 只写脚本与离线 mock 自测；**未**连接 9200/9202；未改任何容器。  
> 日期：2026-11-09。

## 1. 产物

| 路径 | 说明 |
|------|------|
| `qa4/data_prep/es_verify.py` | 十索引对 a–i 只读对比；`ReadOnly` 包装强制拒绝写调用 |
| `qa4/data_prep/es_verify_run.ps1` | 双密码交互包装；报告写 `G:\PanAI4.0专用\logs\qa4_verify_<ts>.md/.json` |
| `qa4/eval/es_verify_queries.json` | BM25 固定查询（校验用，非评测集） |
| `qa4/data_prep/README.md` | 已补充运行顺序 |

对应关系：`panai4_<X>` ↔ `qa4_<X>`。密码环境变量：`QA4_ES_PASSWORD` / `OLD_ES_PASSWORD`；旧用户 `--old-user`。

## 2. `--self-test` 结果（不连真实 ES）

exit=0。假密码未出现在日志中。

要点摘录：

```text
WRITE_REJECT_OK: index
WRITE_REJECT_OK: PUT settings
CLUSTER_OK old=qa4 blocked
CLUSTER_OK new!=qa4 blocked
PASS_PATH hymns.{count,mapping,settings,ids,content,vectors,knn,bm25,analyze}=PASS
PASS_PATH pano_catalog.* = PASS/SKIP(vectors/knn)
DIFF_DETECT_OK: missing _id
DIFF_DETECT_OK: field diff
DIFF_DETECT_OK: vector bit diff
REDACT_OK
self-test PASS
```

人为差异：少一个 `_id` → ids/count FAIL；字段篡改 → content FAIL 并列出 `fields=['text']`；向量改一位 → vectors FAIL。

## 3. `es_verify_queries.json` 查询列表（供审阅）

文件头注明：校验用固定查询，不是评测集。

### outline（outline_12490 / outline_feasts）

神的经纶；基督的身体；生命的流；那灵的运行；召会的建造；主的恢复；真理的亮光；祷告的职事；成全圣徒；新耶路撒冷

### text_*（life / cwwl / cwwn / others）

三一神；神圣的生命；变化与成熟；经历基督；住在主里面；十字架的道路；内里的人；属灵的争战；供应生命；与主成为一灵

### map_note

约翰福音；罗马书；创世记；启示录；马太福音；以弗所书；诗篇；希伯来书；哥林多前书；使徒行传

### bible

起初神创造；道成了肉身；神爱世人；你们要去使万民作我的门徒；圣灵降临；因信称义；基督是头；新约的执事；生命树；羔羊的婚筵

### hymns

奇异恩典；主啊我心爱你；何等的大爱；跟随主；赞美我神；十字架；荣耀的呼召；安静主前；复兴我们；主你是我异象

### pano_catalog

生命课程；真理课程；成全训练；召会生活；福音；青年；全时间；圣经真理；属灵追求；服事

## 4. PowerShell 5.1

- `es_verify_run.ps1` BOM=`[239,187,191]`
- Parser `errors=0`（见下方验证命令输出）

## 5. Docker / git

任务前后 `docker ps -a` / `volume ls` / `images` 相同。  
`git status --short` 仍为未跟踪的 `qa4/`（及既有 `docs/panai4_graph/*`），无其它改动。

## 6. 检查项一览（真实运行时）

| 项 | 内容 | FAIL 策略 |
|----|------|-----------|
| a count | 两边 `_count` 相等；十索引合计 414082 | 记 FAIL，继续 |
| b mapping | properties 规范化后相等；向量 dims/similarity/int8_hnsw | 同上 |
| c settings | analysis 相等；报告 shards/replicas；忽略 uuid 等 | 同上 |
| d ids | scroll 全量 `_id` 流式 sha256 + 差集数量 | 同上 |
| e content | 排除 embedding/text_vector 后组合指纹；FAIL 列前 20 | 同上 |
| f vectors | 随机 500（bible/hymns 全量）逐位相等 | 同上 |
| g knn | 30 查询；报 self top-1、top-10 重合均值/最小；不设通过线 | 软 PASS（样本完成且 self top-1） |
| h bm25 | 固定查询 top-10 `_id` 序列与重合度 | 序列完全一致为 PASS |
| i analyze | 5 段中文 token 序列必须相同 | 同上 |

运行（由你在独立窗口执行）：

```powershell
cd qa4\data_prep
.\es_verify_run.ps1 -OldUser elastic
```

### 验证现场输出

`	ext
es_verify_run.ps1 errors=0
BOM=[239, 187, 191]
git status --short:
?? docs/panai4_graph/export_pack.md
?? docs/panai4_graph/git_merge_conflict.md
?? docs/panai4_graph/git_merge_resolve.md
?? qa4/
`

（docker 列表未改动；本任务未启动/停止任何容器。）
