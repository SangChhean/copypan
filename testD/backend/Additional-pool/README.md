# Additional Pool

本地增强式翻译缓存，文件为 `pool.jsonl`（每行一条 JSON）。

## 记录格式

```json
{
  "zh": "一\t生命",
  "en": "A.\tLife",
  "norm_zh": "一生命",
  "saved_at": "2026-06-01T10:00:00+00:00",
  "prompt_version": "",
  "source": "enhanced_translate"
}
```

- `zh`：原始中文行（含序号、读经后缀）
- `en`：对应英文行
- `norm_zh`：查询键，`normalize_zh(zh)` 的结果
- `source`：`enhanced_translate`（自动写入）或 `manual`（手动导入）

## 工具脚本

在仓库根目录执行：

```bash
# 查询
python testD/backend/Additional-pool/tools/lookup.py "一\t生命"

# 条数统计
python testD/backend/Additional-pool/tools/stats.py

# 校验完整性
python testD/backend/Additional-pool/tools/validate.py

# 从 API 响应导出 draft
python testD/backend/Additional-pool/tools/export_draft.py --response response.json -o draft.jsonl

# 合并 draft 进 pool
python testD/backend/Additional-pool/tools/append.py draft.jsonl
```

## 自动回写

翻译完成后，服务默认将新译文写入 Pool（可通过环境变量 `ENHANCED_TRANSLATE_AUTO_APPEND=0` 关闭）。
