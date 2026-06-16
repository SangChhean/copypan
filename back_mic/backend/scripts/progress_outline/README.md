# progress_pano 入库脚本

将「主恢复中神圣启示的进展」系列 Word 纲目解析后写入 Elasticsearch 索引 `progress_pano`，供主站 **进展纲目** 功能（`/api/progress/pano/search`）检索使用。

## 索引结构 `progress_pano`

| 字段 | 类型 | 说明 |
|------|------|------|
| `series_no` | integer | 系列编号 |
| `series_title` | keyword | 系列标题 |
| `source_group_no` | integer | 阶段 1–6（倪柝声 / 李常受各阶段） |
| `source_group_title` | keyword | 阶段名称 |
| `article_no` | integer | 篇号（msg. N） |
| `title` | keyword | 篇题，如「第一篇　…」 |
| `metadata` | text | 读经前的元数据行 |
| `outline` | nested | `{ type, text }` 纲目行 |
| `ministry_excerpt` | nested | `{ text }` 职事摘录 |

文档 `_id` 格式：`progress_pano-{series_no}-{source_group_no}-{seq}`。

## 目录布局要求

`--source-dir` 指向 Word 根目录，典型结构：

```
<source-dir>/
  01 某系列标题——NN篇/
    倪柝声弟兄职事/…/msg. 1 主题.docx
    李常受弟兄职事第一阶段/…/msg. 2 主题.docx
    …
```

- 系列文件夹名需匹配：`数字 + 标题 + ——/— + N篇`
- 篇文件需匹配：`msg. N 主题.docx`（跳过文件名含「纲目带出处」的文件）

## 运行方式

在 `back_mic/backend` 目录下：

```bash
# 查看帮助
python scripts/progress_outline/ingest_pano.py --help

# 全量入库（默认重建索引）
python scripts/progress_outline/ingest_pano.py --source-dir "D:\path\to\进展Word根目录"

# 全量入库但不删除已有索引
python scripts/progress_outline/ingest_pano.py --source-dir "D:\path\to\根目录" --no-recreate

# 单篇重入库
python scripts/progress_outline/ingest_pano.py --source-dir "D:\path\to\根目录" --doc-id progress_pano-1-1-1
```

依赖：主站 `.env` 中的 ES 连接配置（`es_config`）、`python-docx`、`natsort`。

日志输出：`scripts/progress_outline/ingest_pano.log`。
