# qa4 ES 验证诊断脚本报告（C-3b）

> 只写脚本与 mock 自测；**未**连接真实 ES 跑全量诊断（由你用 `es_verify_diag_run.ps1` 跑）。  
> 未改容器、未做 git 提交。日期：2026-11-09。

## 1. `fields=[]` 根因与修复

### 指纹怎么算

对每个文档去掉 `embedding` / `text_vector` 后：

```text
canonical_json = json.dumps(doc, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
```

再按 `_id` 排序拼进流式 SHA256。因此 **「键缺失」与「显式 `null`」在指纹上不同**（`{}` vs `{"year":null}`）。

### 旧差异字段怎么算（有盲区）

```python
bad = [k for k in keys if canonical_json(sa2.get(k)) != canonical_json(sb2.get(k))]
```

`.get(k)` 在键缺失时返回 `None`，与显式 `null` 一样，再 `canonical_json` 都是 `"null"` → **指纹已不同，但 `fields=[]`**。

这与真实验证报告 `qa4_verify_20261109_131736` 中 content FAIL 且每条 `fields=[]` 一致；最可能就是一侧有 `null`、另一侧缺键（或同类表示差）。

### 修复

`es_verify.py` 改为 `diff_document_fields`：用 `k in doc` 区分缺失/null，并标注类型（`null_vs_missing` / `type_int_vs_float` / `list_order_diff` 等）。指纹不同时必有非空 `fields` + `field_diffs`。

## 2. 产物

| 路径 | 说明 |
|------|------|
| `qa4/data_prep/es_verify.py` | 已修 content 差异字段报告 |
| `qa4/data_prep/es_verify_diag.py` | 只读深挖 content/knn/bm25 |
| `qa4/data_prep/es_verify_diag_run.ps1` | 双密码包装（UTF-8 BOM） |
| `qa4/data_prep/README.md` | 已补充诊断入口 |

真实诊断输出：`G:\PanAI4.0专用\logs\qa4_verify_diag_<时间戳>.md` / `.json`。

## 3. mock 自测（`--self-test`，exit=0）

```text
WRITE_REJECT_OK
CASE null_vs_missing: old_fields=[] new=[{field:year, kind:null_vs_missing, ...}]
NULL_MISSING_OK
CASE int_vs_float: kind=type_int_vs_float
INT_FLOAT_OK
CASE list_order: kind=list_order_diff
LIST_ORDER_OK
FP_DIFF d1/d2/d3: fields 非空且带 kinds
BM25_TIE tie_only=True；非并列 tie_only=False → BM25_TIE_OK
REDACT_OK
self-test PASS
```

假密码未进入日志。

## 4. 对真实验证 FAIL 的预判（供你跑 diag 核对）

依据 `qa4_verify_20261109_131736.json`（未再连 ES）：

### BM25（text_life / text_cwwl）

- 失败查询 **overlap=10**（同一批 `_id`），仅顺序不同。
- 例：`text_life` 中三档同分 `6.7527804` / `6.966105` 组内置换；`text_cwwl` 同分 `7.785831` 组内置换。
- **高度符合「并列分数导致顺序不稳定」**；diag 会输出 `tie_only` 与 `_cat` 的 `docs.count` / `docs.deleted` / segments。

### hymns kNN（self_top1=28/30）

- 报告里 `low_queries` 为空（旧条件偏「两边 top1 是否相同 / overlap&lt;5」，未收录「自身未进 top1」）。
- diag 会按同一随机种子重跑 30 样本，专列失败的 2 条：query `_id`、两边 top-3+分数、top1 向量是否等于查询向量（查重复/并列）、并对照旧 ES 是否同样非 self-top1。

### content

- 五索引 FAIL + `fields=[]` → 优先用新逻辑统计 **null_vs_missing** 等；并给出语义规范化（数值→float、去 null 键）后仍不同的文档数。

## 5. PowerShell / Docker / git

- `es_verify_diag_run.ps1` BOM=`[239,187,191]`；Parser `errors=0`
- docker ps/volume/images 未因本任务改变
- `git status --short` 仍主要为 `?? qa4/`（及既有 `docs/panai4_graph/*`）

## 6. 请你本地执行

```powershell
cd qa4\data_prep
.\es_verify_diag_run.ps1 -OldUser elastic
# 建议重跑完整校验（analyze/bm25 逻辑已更新）：
.\es_verify_run.ps1 -OldUser elastic
```

---

## 7. 补充修订（并入 C-3b）

### 7.1 analyze：强制走 IK

- 每索引两次：`field=text`（index 分析器 `ik_max_word`）与 `analyzer=ik_smart`。
- 探针句「神的经纶与基督的身体」必须产出含 **经纶 / 基督 / 身体** 的多字 token；若仍为单字 → FAIL（说明未走 IK）。
- mock 自测：`[analyze] … -> PASS`（指定 field/analyzer 后不再逐字切分）。

### 7.2 bm25：total + 并列无害

- 每条查询记录两边 `old_total` / `new_total`（`track_total_hits`）。
- 排序不同但属同分并列组 → 标签 **「并列排序差异（无害）」**，**不计 FAIL**。
- `_id` 集合不同或非并列顺序差 → FAIL；并记录 `max_rel_score_diff`。
- 据此，此前 `text_life` / `text_cwwl` 的 FAIL 在重跑后预期多为 PASS（无害并列）。

### 7.3 diag 额外统计

- 对 `outline_12490`、`text_life`：`docs.count` / `docs.deleted` / `segments` + match「神」的文档数对比。
- content：先打 **不一致比例**，再种类汇总；若 ≥95% 不同则给系统性表示差判断（结合语义规范化后仍不同数）。

### 7.4 自测

`es_verify.py --self-test` 与 `es_verify_diag.py --self-test` 均为 exit=0（2026-11-09 重跑）。
