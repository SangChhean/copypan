# 恢复本圣经建块

从恢复本 sqlite 只读建块：纲目区间 → 三级细分 → 渲染 → JSONL。规则见 `docs/panai4_es/bible_index_plan.md`。本步**不**生成向量、**不**建 ES 索引。

数据源只读打开，绝不写入。只用五张表：`outline_all_gb_25` / `verse_all_final_gb_26` / `verse_all_paragraph_08` / `volume_all_gb_22` / `topic_all_gb_24`。

## 运行

在 `back_mic/backend` 下：

```bash
python -m panai4.bible.build_chunks
```

## 参数

| 参数 | 默认 | 含义 |
|---|---|---|
| `--db` | `G:\audio-app\Bible\assets\Bible20240820.sqlite` | 只读 sqlite |
| `--out` | `C:\Users\28121\Desktop\纲目JSON` | 产出目录 |
| `--report` | `docs/panai4_es/bible_chunking_report.md` | 建块报告 |

## 产出

- `chunks_bible.json`：JSONL，每行一块，共约 3,691 条（经文块 3,625 + 卷首块 66）
- `bible_chunking_report.md`：覆盖、块数、诗篇 119、抽样、sqlite 未改动校验

## 模块

| 文件 | 职责 |
|---|---|
| `config.py` | 表名、坐标规则、阈值、中文数字、索引名 |
| `read_sqlite.py` | 只读取数 |
| `build_chunks.py` | 区间形成 + 三级细分 + 渲染 + 字段 |

不要改动 `panai4/outline/`。
