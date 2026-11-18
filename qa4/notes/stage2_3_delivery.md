# 阶段 2 + 阶段 3 交付报告

日期：2026-11-16  
工作区：`G:\copypan`（仅 `qa4/`）  
**声明：没有 git add / commit / push / stash / reset；没有联网调用 Anthropic / 嵌入 / 重排；没有连接真实 ES / Neo4j / Redis；没有读取或写入任何密钥 / `.env` 实值；没有修改 `back_qa` / `back_shared` / `back_mic`；没有在 qa4 中 import 3.0 包。**

---

## 1. 验证结果

### 单元测试

```
qa4\backend\.venv\Scripts\python.exe -m unittest discover -s qa4/backend/tests
Ran 171 tests in ~24s
OK
```

（补丁五：+8 左右；iter_json_rows / 检查 8 ids 取数。补丁四曾为 163。）
### `verify_stage2.py` 末行

```
STAGE2 OFFLINE: ALL PASS
```

### `verify_stage3.py` 末行

```
STAGE3 OFFLINE: ALL PASS
```

（五个场景：简单 / 追问缓存 / 拆分 / 诗歌定向 / 二次缓存；另抽查 live 占位 → 503。）

### 3a 整行解析（`stage2_scripture_report.py`）

| 指标 | 实际 | 期望 | 差 |
|------|------|------|----|
| 有读经行的词条 | 2365 | 2365 | 0 |
| 至少解析出一个出处 | 2360 | 2360 | 0 |
| 出处总数 | **23103** | 23102 | **+1** |
| 零出处行 | 5 | 5 | 0 |
| 疑似遗漏行 | 23 | 23 | 0 |
| 出处均能在 bible_data 找到 | 23103 | （期望全部） | 同实际 |

未硬凑。逐词对比（`tools/diff_3a_ref_counts.py` vs probe6 同形校验）：多出的 1 条来自词条 **「百合花」**，多出的 ref = **`诗45:1`**（flags「含标题」——qa4 默认打开诗篇第 0 节→第 1 节；probe6 校验不放行 verse=0，故少计 1）。CSV：`G:\PanAI4.0专用\logs\stage2\ref_counts_per_term.csv`。零出处词名：基甸、基督的活出、祭牲、西番雅书、洗脚。

---

## 2. 新增与修改文件

### 2.1 对「阶段 1 已有文件」的追加式修改

| 文件 | 改动 |
|------|------|
| `qa4/.gitignore` | 明确忽略 `/data/bible_data/`（`/data/` 本已覆盖） |
| `qa4/backend/main.py` | 注册 `/api/qa`；可选注入 `pipeline_deps`；`/readyz` 传 `prompts_info` / `llm_mode` |
| `qa4/backend/config/settings.py` | 追加 bible/embed/rerank/llm_mode/retrieval_mode/traces 等配置项 |
| `qa4/backend/core/ready.py` | `build_ready_report` 增加 `prompts_info`；fake 模式 llm 检查；prompts 降级项 |
| `qa4/backend/core/llm_fake.py` | **追加** `PipelineFakeLLM`（不改原 `FakeLLM` 行为）；第 8 步引用号取自材料 |
| `qa4/backend/core/redis_store.py` | （阶段 1b/2 已有）内存实现继续服务 fake 缓存/限流 |
| `qa4/backend/api/admin_routes.py` | 追加 `GET /traces`、`GET /traces/{id}` |
| `qa4/backend/requirements.txt` | 已有 pydantic/httpx；本阶段无强制新依赖 |
| `qa4/notes/qa4_backend_build_probe_5b.md` | Read-Host → `-AsSecureString` |
| `qa4/notes/qa4_backend_build_probe_5c.md` | 同上（顺带） |

### 2.2 阶段 2 主要新增

- `qa4/data/bible_data/`（66 卷，gitignore）+ `qa4/data/bible_data.manifest.json`
- `scripture/`：`bible_text.py`、`normalize.py`、`reverse.py`、`vendor_get_vers_v21.py`（与桌面 `get_vers_v2.1.py` **字节级相同**，`shutil.copyfile`；来源说明见同目录 `vendor_get_vers_v21.SOURCE.md`）
- `config/scripture.json`、`config/retrieval.json`
- `core/embedding_client.py`、`core/rerank_client.py`（含 Fake）
- `retrieval/`：`config` / `es_search` / `fusion` / `dedupe` / `scope` / `service` / `targeted` / `fake` / `types`
- `lookups/definitions.py`、`lookups/year_table.py`
- `tools/build_bible_manifest.py`、`stage2_scripture_report.py`、`verify_stage2.py`、`verify_stage2_live.py`（只读，未运行 live）
- `tests/test_stage2_*.py` + `tests/fixtures/`（零出处/疑似遗漏/诗篇/假段落/假辩理）

### 2.3 阶段 3 主要新增

- `config/pipeline.json`、`step5_caps.json`、`generic_words.json`
- `prompts/registry.json` + `texts/step{2,3,4,5,7,8}_v1.0.txt`（占位）+ `loader.py`
- `pipeline/`：`schemas` / `context` / `deps` / `caps` / `cache` / `traces` / `citations` / `textutil` / `step01`…`step09` / **`orchestrator.py`**
- `api/qa.py`：`POST /api/qa/stream`（SSE）、`POST /api/qa/ask`
- `tools/verify_stage3.py`
- `tests/test_stage3_pipeline.py`

---

## 2.4 换行损坏排查（2026-11-16 晚间补记）

- **vendor 现状**：`vendor_get_vers_v21.py` 35645 字节，SHA256=`1A7C164F109CDBBF3CDAB757F49778396026B04B72E7D92E39CEDEE87969AB75`，CRCRLF=0（与桌面原件一致）。
- **CRCRLF 根因**：阶段 2 落地时用 Cursor **Write 工具**创建该文件（先读 CRLF 源再文本写出，并追加文件头）。Windows 文本模式把已含 `\r` 的行尾再转成 `\r\n` → `\r\r\n`（原文件 716 行各多一个 CR）。仓库内**没有**独立复制脚本写出该 vendor；`build_bible_manifest.py` 等只写 JSON。
- **3a 扫描**：`qa4/` 下文本文件（排除 `.venv`、`data/bible_data`）扫描 **249** 个，含 CRCRLF 的文件：**0**（修复 vendor 后）。
- **3b bible_data**：与 `back_qa/bible_data` 66 文件逐个 SHA256 **全部一致**；未重拷；manifest 章/节仍 1189 / 31103。
- **3c 本轮实际从外部复制的文件**：
  1. 桌面 `get_vers_v2.1.py` → `qa4/backend/scripture/vendor_get_vers_v21.py`（已字节级重拷，SHA 一致）
  2. `back_qa/bible_data/*.json`（66）→ `qa4/data/bible_data/`（SHA 全部一致）
  其余阶段 2/3 代码为改写/新写，非字节复制。

## 3. 3.0 嵌入与重排（只读代码，不抄 env）

| | 服务商 / 形态 | 模型 |
|--|----------------|------|
| 嵌入 | **OpenRouter**，OpenAI 兼容 `POST {base}/embeddings`（默认 base `https://openrouter.ai/api/v1`） | `qwen/qwen3-embedding-8b`，dimensions=**1024**，**无指令前缀** |
| 重排 | **Jina**，`POST https://api.jina.ai/v1/rerank` | `jina-reranker-v3`，请求体 `{model,query,documents,top_n}`，**无指令前缀**；失败降级原序 |

依据：`back_shared/embedding_adapter.py`、`back_shared/reranker_service.py`（只读）。

qa4 配置名：`QA4_EMBED_*` / `QA4_RERANK_*`（值仅环境变量，不进日志）。

---

## 4. 【暂定】项

1. **Ref 键**：`(卷, 章, 起节, 止章, 止节)`——同章时止章=章，多一位以容纳跨章。  
2. **诗篇第 0 节**：开关 `scripture.json.psalm_verse0_as_title` 默认开 → 按第 1 节 + flags「含标题」。  
3. **反找经文后备**：图谱+3a 去重后少于 `reverse.bible_vector_when_below`（默认 3）才查 bible 向量。  
4. **text_* 段序**：`chunk_id` 末尾数字作 order（verified=false）。  
5. **缓存别名键**：未知题型时用「问题+提示词版本+模型配置」别名指向完整键。  
6. **降级结果不缓存**。  
7. **引文核对不过**：标 `unverified` + 正文小标记 `〔未核实〕`，不自动重生成。  
8. **第 5 步固定前缀格式**：内在素质一行 + 按主干分组的其余词。  
9. **截断顺序**：先裁上限最小的层里排最后的词。  
10. **定向取全（已按数据驱动修订）**：见下文「定向取篇完整性」；纲目/节期 `orders_base=1`（`{1..chunk_total}`）；text_* 无 total → `unknown_total`；节期按 `message_number` 分组。  
11. **假模型【拆】**：2 个实质子问题 + 1 个综合依赖子问题（综合不检索）。  
12. **比较类 layer1 上限**：`layer1_per_subquestion_compare=4`【暂定】。  
13. **比较对象未覆盖**：`warning=compare_object_uncovered`，把关「够」最多降为「部分够」【暂定】。

---

## 4b. 收尾补丁二（2026-11-16）

### Trace 存储（方案 A）

- 配置：`config/pipeline.json` → `traces.store_question_text`（默认 true）、`traces.retention_days`（默认 90）。
- 库列：`question_text` / `history_json`（第 2 步实际送出的最近 3 轮，答截 300 字）/ `rewritten_question`；保留 `question_hash`、`question_len`。旧表 `ALTER TABLE ADD COLUMN` 平滑升级。
- 清理：`TraceStore` 启动时清一次；写入路径上每天最多清一次（无后台线程）。
- 访问：仅管理令牌；列表 `question_preview`≤60 字，详情全文。
- 日志 / Redis 监控列表 / usage_sink：**仍不含原文**（监控条仅哈希前 8 位、长度、耗时、缓存命中等）。

### 比较类强制

- `SubQuestion.compare_objects`；假模型 `【比较】` / 「比较…与…」补齐。
- 第 4 步强制两对象进第 1 层（非词条也保留）；第 5 步 `object_of` + 截断不删某对象仅剩词；未覆盖则 warning，第 7 步降为部分够。
- `step5_caps.json` 比较条 `_note` 已去掉「程序未强制」。

### 新增测试（`tests/test_stage3_patch2.py`）

- Trace：存读/预览/401、store_question_text=false、保留期、旧库升级、日志与监控无原文。
- YearTable：重叠命中、无年份 61 永不命中。
- Step4：括号映射与丢词、兜底排除泛词、个数上限、比较非词条对象保留。
- Step5：截断保两边、未覆盖 warning、名单外/133/去重、全不合格只留第 1 层。
- Step7：放宽恰一次后仍不够→没有找到；核实说法不重试。

（既有 `test_stage3_pipeline` 中「trace 不含原文」断言已改为方案 A 存原文——行为变更，非放宽。）

---

## 4c. 定向取篇完整性判定规则（2026-11-16 在线检查跟进）

依据笔记：`qa4/notes/stage2_targeted_notes.md`。

| status | 含义 |
|--------|------|
| `ok` | 有 `chunk_total` 时取回数=期望，序号恰为 `orders_base .. orders_base+total-1`，无缺无多无重复；且未被 size 截断 |
| `incomplete` | 有明确缺口（`missing_orders` / `extra_orders` / 重复 / 截断） |
| `unknown_total` | 无总段数字段（典型 text_*）：只按命中数核对；**不把段号断档当 incomplete** |

返回字段（每部分）：`fetched`、`hits_total`、`expected_total`、`orders_base`、`missing_orders`、`extra_orders`、`duplicate_orders`、`orders_contiguous`、`chunk_totals`、`status`。

- **纲目 / 节期**：`order_base=1`（`chunks_es_plan.md:198,361`）。  
- **节期仅「年+月」**：按 `message_number` 分组各自判定；整体取各篇最差 status；`feasts.json` 无篇数字段 → `expected_message_count=null`。  
- **诗歌**：默认 `series=诗歌`；重叠号靠 series 区分（probe_4：398）。

### 检查 4 map_note：与探测 5 的差因（代码层）

1. **母体**：探测 5 = jsonl 上可抽取 mid 的集合；原 live = ES `random_score` 抽 raw `source_zh`（未先滤可抽取）。现 live 已改为 ES 收集 → extract → `Random(20261116).sample(2000)`，与探测 5 算法对齐，母体仍可能因 ES↔jsonl 不完全一致。  
2. **成功口径**：探测 5 = 对 **mid** 跑原始 v2.1；包装层 `map_note_key` = 对剥注后的 **body**（常仍含「恢复本圣经」）做 `parse_refs`。  
3. 故 1946/2000 vs 1999/2000 **不能**直接对比；须看 live 拆开的 `raw_v21_ok` 与 `wrapper_ok`（失败前 30 条入 JSON）。

---

## 5. 「未完成」与 `verified: false`

### 未完成 / 降级说明

- **辩理材料 live 源**：`DevineProvider` 在 live 返回空并注明尚未接入 qa4；fake 用 `tests/fixtures/fake_devine.json`。  
- **提示词**：全部 `placeholder: true`；live 下 `/api/qa/*` → **503「提示词尚未就绪」**。  
- **`verify_stage2_live.py`**：已加强（缺密码跳过、检查4拆口径、检查5诊断、汇总 PASS/FAIL/跳过）；**本次未跑 live**（需你设环境变量后自跑）。  
- **出处总数**：23103 vs 期望 23102（多 1），未改解析器硬凑。

### `retrieval.json` 中 `verified: false`（2 项）

1. `outline_feasts.feast_locate.book_title_equals_feast_name`  
2. `hymns.full_unit_type`  

（text_life / text_cwwl 的 order 已在补丁三改为 verified=true：断档为源编号特性。详见 `stage2_patch3_notes.md`。）

（bible_data **有脚注**；按经节取注解已实现，非 not_supported。）

### 补丁三（2026-11-16）

- text_* 断档：源编号特性（heading/空段/合并）；工具 `check_text_life_gaps.py`；在线检查 8。  
- map_note「十〇二」→ 包装层预处理；检查 4b 全量。  
- DevineProvider live（图谱）；检查 9/10/11/6b。  
- 详情：`qa4/notes/stage2_patch3_notes.md`。

### 补丁四（2026-11-16）

- 依据：`es_import.row_to_action` 仅跳过缺 id / 非法 1024 维向量；**无**文本哈希去重；导入日志 cwwl `178107/178107` bulk_err=0。  
- 源副本：`qa4_import_src` ↔ `数据包\_stage_es` 五索引 shards **SHA 全一致**。  
- 离线：`analyze_source_dupes` — 五索引均无 chunk_id 重复；`cwwl_1994-1997-2` 整册 1714 段、跨册同文 **0**；单篇 `#1` 452 段同文亦 0 → 不能用「重复去重」解释缺 367。  
- 在线工具：`check_source_vs_es.py`（Srey 跑）；检查 8 可附 top3 缺失册（`--source-vs-es-json`）。  
- 小修：`preprocess_ref_text` 制表符/全角冒号/阿拉伯章:节；`map_note_invalid_refs.md` 13 条。  
- 详情：`qa4/notes/stage2_patch4_notes.md`。

### 补丁五（2026-11-17）

- Srey 实况：五索引 source=es（39463/178107/32032/15481/16052），missing=extra=0；outline_12490 因 JSON Lines 被当整 JSON 解析而崩溃。  
- `check_source_vs_es`：格式自识别、坏行续跑、按索引捕获、增量写 JSON、`--resume-from`；探测打印 path/file_n/bytes。  
- 检查 8 假阳性：旧 ES 侧用 book_title+message_number，而 `cwwl_1994-1997-2#1` 跨 13 个 book_title（452→只命中 85）；改为 ids 精确查询；有全量 JSON 时不重读源。  
- `map_note_invalid_refs.md` 改为条目列表。

---

## 6. 新增依赖

**无新增第三方包。** SSE 用 FastAPI `StreamingResponse` 自写。  
沿用已有：`fastapi`、`pydantic>=2`、`httpx`、`anthropic`（live LLM）、等。

---

## 7. 指令未写明但做了的决定

1. 假检索：查询串包含 keywords 子串即命中（否则「什么是神的爱」无法命中关键词「神的爱」）。  
2. 缓存命中仍计日限额（与 3.0 `stream_answer` 先扣再查一致；非流式 `/query` 3.0 不扣；qa4 两路由都扣）。  
3. `create_app` 默认装配 `pipeline_deps`；测试可注入。  
4. 管理端 traces 只读列表/详情，走已有管理令牌。  
5. `/readyz` 在 live+占位时 `prompts` 为 degraded（不单独把整体打成 not_ready，避免掩盖其它检查）。  
6. 假模型 `【拆】` 附带综合子问题，便于测「综合不检索」。  
7. 顺带把 5c 报告的 Read-Host 也改成 SecureString。  
8. 收尾补丁二：假模型「比较」优先于含「比较」字样的【拆】题（先判【拆】）；监控列表单独 slim JSON，不复用含原文的 record_json。  
9. 补丁四：`preprocess` 把「书+阿拉伯章:节」改成 vendor C 型「书+中文章+阿拉伯节」（否则仅去空白仍无法解析 `腓1:5`）；检查 8 的 top3 册用 chunk_id 前缀边界（避免 `…-2` 吃到 `…-20`）。  
10. 补丁五：有 `--source-vs-es-json` 时检查 8 以索引级 missing/extra 与 top3 册报告判定（不再重读 6GB 源、也不再对样例做二次 ES 拉取）。

---

## 8. 你回来后建议命令

```powershell
# 离线
qa4\backend\.venv\Scripts\python.exe -m unittest discover -s qa4/backend/tests
qa4\backend\.venv\Scripts\python.exe qa4\backend\tools\verify_stage2.py
qa4\backend\.venv\Scripts\python.exe qa4\backend\tools\verify_stage3.py

# 3a 报告（需本机 truth_dictionary_3a3b.json）
qa4\backend\.venv\Scripts\python.exe qa4\backend\tools\stage2_scripture_report.py --out "G:\PanAI4.0专用\logs\stage2"

# 源 vs ES 全量（只读；需 QA4_ES_*；结果供检查 8 的 top3）
$env:QA4_SOURCE_ROOT="G:\PanAI4.0专用\qa4_import_src"
qa4\backend\.venv\Scripts\python.exe qa4\backend\tools\check_source_vs_es.py --out "G:\PanAI4.0专用\logs\stage2"

# 在线（你设好环境变量后；缺项会打印「跳过：缺少 XXX」）
qa4\backend\.venv\Scripts\python.exe qa4\backend\tools\verify_stage2_live.py --out "G:\PanAI4.0专用\logs\stage2" --source-vs-es-json "<上一步 OUT_JSON>"
```

fake 贯通本地问答：

```powershell
$env:QA4_LLM_MODE="fake"; $env:QA4_RETRIEVAL_MODE="fake"
# 另设 QA4_JWT_SECRET / QA4_ADMIN_TOKEN / QA4_DATA_DIR 等后启动 main
```
