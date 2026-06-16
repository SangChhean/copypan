# pool_tools

主站 `data/enhanced_translate/pool.jsonl` 维护脚本。在 `back_mic/backend` 目录下运行。

| 脚本 | 用途 |
|------|------|
| `stats.py` | 打印 pool 路径与条目数 |
| `lookup.py` | 按中文行查询英文译文 |
| `validate.py` | 校验 JSON、重复 norm_zh |
| `append.py` | 合并 draft.jsonl 进 pool |
| `export_draft.py` | 从 API 响应或中英对照文本导出 draft |

示例：

```bash
python scripts/pool_tools/stats.py
python scripts/pool_tools/lookup.py "末后的亚当"
python scripts/pool_tools/validate.py
```
