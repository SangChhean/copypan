# progress_pano 入库脚本

将「主恢复中神圣启示的进展」系列 Word 纲目（**纲目带出处**版）解析后写入 Elasticsearch 索引 `progress_pano`，供主站 **进展纲目** 功能（`/api/progress/pano/search`）检索使用。

## 阶段编号（`source_group_no` 1–5）

| no | 含义 | 入库文件夹匹配 |
|----|------|----------------|
| 1 | 倪柝声弟兄职事 | `倪柝声弟兄职事` |
| 2 | 李常受弟兄职事第一阶段（1932–1973，**一+二阶段合并按序收录**） | `李常受弟兄职事第一阶段`、`李常受弟兄职事第二阶段` |
| 3 | 李常受弟兄职事第三阶段 | `李常受弟兄职事第三阶段` |
| 4 | 李常受弟兄职事第四阶段 | `李常受弟兄职事第四阶段` |
| 5 | 李常受弟兄职事高峰阶段 | `李常受弟兄职事高峰阶段` |

写入 ES 的 `source_group_title` 使用 `SOURCE_GROUP_TITLE_CANONICAL`，与文件夹原名无关。

## 运行方式

在 `back_mic/backend` 目录下：

```bash
# Word → ES 全量入库
python scripts/progress_outline/ingest_pano.py --source-dir "D:\path\to\进展Word根目录"

# Word → JSON 导出
python scripts/progress_outline/ingest_pano.py --source-dir "D:\path\to\根目录" --export

# JSON → ES 导入（默认重建索引）
python scripts/progress_outline/import_pano_json.py scripts/progress_outline/progress_pano.json
```

依赖：主站 `.env` 中的 ES 连接配置（`es_config`）、`python-docx`、`natsort`。

日志输出：`scripts/progress_outline/ingest_pano.log`。

详细设计见 `features/progress_outline/DESIGN.md`。
