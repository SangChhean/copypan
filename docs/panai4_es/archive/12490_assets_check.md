# panai4_outline_12490 构建资产只读检查

> ES：`http://localhost:9200`；纲目JSON：`G:\PanAI4.0专用\纲目JSON`；报告生成：2026-11-06T11:56:58；耗时 142.8s；日志：`G:\copypan\logs\12490_assets_20261106_115435.log`。

## 结论摘要

(1) **chunks / 向量**：均在 `G:\PanAI4.0专用\纲目JSON` — `chunks_12490.json`（55841 条，118.2 MB）、`chunks_12490_vec.json`（55841 条，1.39 GB）。齐全。
(2) **三向 id**：chunks=55841 vec=55841 es=55841；c−v=0 v−c=0 ∩=55841；c−e=0 e−c=0；v−e=0 e−v=0；dup c/v/e=0/0/0。
(3) **text**：相同=55841 不同=0 ES缺=0。
(4) **向量**：抽样 30 块；cosine>0.999 约 30；字段=`embedding`。
(5) **脚本能力**：可用现有 `*_vec.json` 经 `index_to_es --index/--input` 写入（不调嵌入）；`gen_embeddings` **不支持**指定 chunk_id 列表，仅断点跳过已有 id——局部重算需自写过滤或删掉目标行后重跑（会调 API）。本地 index 流程是 create+全量 bulk，不是增量补丁。
(6) **fix_final**：匹配 70 / 不匹配 0（合计 70 vs 70）；重算向量块≈315 / 篇≈69；头部可机械对齐率 100/100；book 类 old 出现在 message_key 内 12 条（改 book_title 不改 key/_id）。
(7) **九索引向量字段**：['embedding', 'text_vector']；明细见 §5（共 9 个 panai4_*）。
(8) **磁盘**：G: 剩余 620.52 GB / 总量 960.20 GB；PanAI4.0专用≈13.11 GB；方案A备份约需 1.63 GB。妨碍因素：本地 index 先删后建需全量；无官方「只重算指定 id」开关；book 改名后 message_key 路径仍含旧名（可接受因 _id 不变）。

## 1. 找文件

### 1.1 `G:\PanAI4.0专用\纲目JSON` 文件清单（41 个）

| 相对路径 | 大小 | mtime | 类型 |
|---|---:|---|---|
| `anomalies.json` | 5360518 | 2026-09-29T14:58:24 | .json |
| `chunks_12490.json` | 118171428 | 2026-09-29T22:24:23 | .json |
| `chunks_12490.json.bak` | 112030188 | 2026-09-29T15:57:32 | .bak |
| `chunks_12490_vec.json` | 1386787642 | 2026-09-29T23:36:37 | .json |
| `chunks_bible.json` | 7426387 | 2026-09-29T22:31:40 | .json |
| `chunks_bible_vec.json` | 91283031 | 2026-09-29T22:53:04 | .json |
| `chunks_feasts.json` | 26035954 | 2026-09-29T22:24:23 | .json |
| `chunks_feasts.json.bak` | 25043462 | 2026-09-29T15:57:32 | .bak |
| `chunks_feasts_vec.json` | 278483135 | 2026-09-29T23:05:27 | .json |
| `chunks_v01_20260929\chunks_12490.json` | 112068348 | 2026-09-29T16:22:45 | .json |
| `chunks_v01_20260929\chunks_12490_vec.json` | 1380769819 | 2026-09-29T20:13:02 | .json |
| `chunks_v01_20260929\chunks_feasts.json` | 25043462 | 2026-09-29T16:22:45 | .json |
| `chunks_v01_20260929\chunks_feasts_vec.json` | 277460512 | 2026-09-29T21:04:16 | .json |
| `conversion_report.md` | 218640 | 2026-09-29T21:17:41 | .md |
| `excluded_files.json` | 121195 | 2026-09-29T14:58:24 | .json |
| `outline_12490.json` | 121121694 | 2026-09-29T14:58:24 | .json |
| `outline_feasts.json` | 33155313 | 2026-09-29T14:58:24 | .json |
| `trial_vectors.json` | 2341931 | 2026-09-29T16:28:31 | .json |
| `trial_vectors_v2.json` | 11485569 | 2026-09-29T22:44:24 | .json |
| `v1_20260929\anomalies.json` | 9749042 | 2026-09-29T11:09:06 | .json |
| `v1_20260929\conversion_report.md` | 162285 | 2026-09-29T11:11:28 | .md |
| `v1_20260929\excluded_files.json` | 227337 | 2026-09-29T11:09:06 | .json |
| `v1_20260929\outline_12490.json` | 108383889 | 2026-09-29T11:09:06 | .json |
| `v1_20260929\outline_feasts.json` | 28725019 | 2026-09-29T11:09:06 | .json |
| `v2_before_candidates_20260929\excluded_files.json` | 227337 | 2026-09-29T12:27:18 | .json |
| `v2_before_candidates_20260929\outline_12490.json` | 108965575 | 2026-09-29T12:27:18 | .json |
| `v2_final_20260929\anomalies.json` | 8775446 | 2026-09-29T12:27:18 | .json |
| `v2_final_20260929\conversion_report.md` | 241627 | 2026-09-29T12:29:02 | .md |
| `v2_final_20260929\excluded_files.json` | 226221 | 2026-09-29T12:48:51 | .json |
| `v2_final_20260929\outline_12490.json` | 105402193 | 2026-09-29T12:48:51 | .json |
| `v2_final_20260929\outline_feasts.json` | 28767889 | 2026-09-29T12:27:18 | .json |
| `v3_partial_20260929\anomalies.json` | 5405166 | 2026-09-29T13:33:12 | .json |
| `v3_partial_20260929\conversion_report.md` | 2906 | 2026-09-29T13:34:35 | .md |
| `v3_partial_20260929\excluded_files.json` | 118979 | 2026-09-29T13:33:12 | .json |
| `v3_partial_20260929\outline_12490.json` | 121245218 | 2026-09-29T13:33:12 | .json |
| `v3_partial_20260929\outline_feasts.json` | 33058003 | 2026-09-29T13:33:12 | .json |
| `v4_20260929\anomalies.json` | 5360910 | 2026-09-29T14:47:28 | .json |
| `v4_20260929\conversion_report.md` | 193530 | 2026-09-29T14:47:45 | .md |
| `v4_20260929\excluded_files.json` | 121195 | 2026-09-29T14:47:28 | .json |
| `v4_20260929\outline_12490.json` | 120678507 | 2026-09-29T14:47:28 | .json |
| `v4_20260929\outline_feasts.json` | 33058003 | 2026-09-29T14:47:28 | .json |

### JSON/JSONL 结构
- `anomalies.json`：kind=jsonl n=13684 top_keys=[]
  - 记录1字段类型：`{'type': 'str', 'batch': 'str', 'id': 'str', 'path': 'str', 'para_no': 'NoneType', 'detail': 'str'}`
  - 记录2字段类型：`{'type': 'str', 'batch': 'str', 'id': 'str', 'path': 'str', 'para_no': 'NoneType', 'detail': 'str'}`
- `chunks_12490.json`：kind=jsonl n=55841 top_keys=[]
  - 记录1字段类型：`{'chunk_id': 'str', 'message_key': 'str', 'source_path': 'str', 'batch': 'str', 'text': 'str', 'book_title': 'str', 'book_path': 'list', 'message_title': 'str', 'message_number': 'int', 'author': 'str', 'year': 'NoneType', 'year_end': 'NoneType', 'paragraph_type': 'str', 'tokens': 'int', 'min_level': 'int', 'point_count': 'int', 'chunk_index': 'int', 'chunk_total': 'int', 'para_nos': 'list', 'part_no': 'NoneType', 'part_name': 'NoneType', 'conference': 'NoneType', 'month': 'NoneType'}`
  - 记录2字段类型：`{'chunk_id': 'str', 'message_key': 'str', 'source_path': 'str', 'batch': 'str', 'text': 'str', 'book_title': 'str', 'book_path': 'list', 'message_title': 'str', 'message_number': 'int', 'author': 'str', 'year': 'NoneType', 'year_end': 'NoneType', 'paragraph_type': 'str', 'tokens': 'int', 'min_level': 'int', 'point_count': 'int', 'chunk_index': 'int', 'chunk_total': 'int', 'para_nos': 'list', 'part_no': 'NoneType', 'part_name': 'NoneType', 'conference': 'NoneType', 'month': 'NoneType'}`
- `chunks_12490_vec.json`：kind=jsonl n=55841 top_keys=None
  - 记录1字段类型：`{'chunk_id': 'str', 'message_key': 'str', 'source_path': 'str', 'batch': 'str', 'text': 'str', 'book_title': 'str', 'book_path': 'list', 'message_title': 'str', 'message_number': 'int', 'author': 'str', 'year': 'NoneType', 'year_end': 'NoneType', 'paragraph_type': 'str', 'tokens': 'int', 'min_level': 'int', 'point_count': 'int', 'chunk_index': 'int', 'chunk_total': 'int', 'para_nos': 'list', 'part_no': 'NoneType', 'part_name': 'NoneType', 'conference': 'NoneType', 'month': 'NoneType', 'embedding': 'list'}`
  - 记录2字段类型：`{'chunk_id': 'str', 'message_key': 'str', 'source_path': 'str', 'batch': 'str', 'text': 'str', 'book_title': 'str', 'book_path': 'list', 'message_title': 'str', 'message_number': 'int', 'author': 'str', 'year': 'NoneType', 'year_end': 'NoneType', 'paragraph_type': 'str', 'tokens': 'int', 'min_level': 'int', 'point_count': 'int', 'chunk_index': 'int', 'chunk_total': 'int', 'para_nos': 'list', 'part_no': 'NoneType', 'part_name': 'NoneType', 'conference': 'NoneType', 'month': 'NoneType', 'embedding': 'list'}`
- `chunks_bible.json`：kind=jsonl n=3691 top_keys=[]
  - 记录1字段类型：`{'chunk_id': 'str', 'message_key': 'str', 'batch': 'str', 'chunk_type': 'str', 'text': 'str', 'book_title': 'str', 'book_no': 'int', 'message_title': 'str', 'message_number': 'NoneType', 'author': 'str', 'verse_range': 'NoneType', 'outline_path': 'list', 'outline_level': 'NoneType', 'paragraph_type': 'str', 'tokens': 'int', 'chunk_index': 'int', 'chunk_total': 'int', 'split_rule': 'str', 'source_keys': 'list'}`
  - 记录2字段类型：`{'chunk_id': 'str', 'message_key': 'str', 'batch': 'str', 'chunk_type': 'str', 'text': 'str', 'book_title': 'str', 'book_no': 'int', 'message_title': 'str', 'message_number': 'int', 'author': 'str', 'verse_range': 'str', 'outline_path': 'list', 'outline_level': 'int', 'paragraph_type': 'str', 'tokens': 'int', 'chunk_index': 'int', 'chunk_total': 'int', 'split_rule': 'str', 'source_keys': 'list'}`
- `chunks_bible_vec.json`：kind=jsonl n=3691 top_keys=[]
  - 记录1字段类型：`{'chunk_id': 'str', 'message_key': 'str', 'batch': 'str', 'chunk_type': 'str', 'text': 'str', 'book_title': 'str', 'book_no': 'int', 'message_title': 'str', 'message_number': 'int', 'author': 'str', 'verse_range': 'str', 'outline_path': 'list', 'outline_level': 'int', 'paragraph_type': 'str', 'tokens': 'int', 'chunk_index': 'int', 'chunk_total': 'int', 'split_rule': 'str', 'source_keys': 'list', 'embedding': 'list'}`
  - 记录2字段类型：`{'chunk_id': 'str', 'message_key': 'str', 'batch': 'str', 'chunk_type': 'str', 'text': 'str', 'book_title': 'str', 'book_no': 'int', 'message_title': 'str', 'message_number': 'int', 'author': 'str', 'verse_range': 'str', 'outline_path': 'list', 'outline_level': 'int', 'paragraph_type': 'str', 'tokens': 'int', 'chunk_index': 'int', 'chunk_total': 'int', 'split_rule': 'str', 'source_keys': 'list', 'embedding': 'list'}`
- `chunks_feasts.json`：kind=jsonl n=11110 top_keys=[]
  - 记录1字段类型：`{'chunk_id': 'str', 'message_key': 'str', 'source_path': 'str', 'batch': 'str', 'text': 'str', 'book_title': 'str', 'book_path': 'list', 'message_title': 'str', 'message_number': 'int', 'author': 'NoneType', 'year': 'int', 'year_end': 'int', 'paragraph_type': 'str', 'tokens': 'int', 'min_level': 'int', 'point_count': 'int', 'chunk_index': 'int', 'chunk_total': 'int', 'para_nos': 'list', 'part_no': 'NoneType', 'part_name': 'NoneType', 'conference': 'str', 'month': 'int'}`
  - 记录2字段类型：`{'chunk_id': 'str', 'message_key': 'str', 'source_path': 'str', 'batch': 'str', 'text': 'str', 'book_title': 'str', 'book_path': 'list', 'message_title': 'str', 'message_number': 'int', 'author': 'NoneType', 'year': 'int', 'year_end': 'int', 'paragraph_type': 'str', 'tokens': 'int', 'min_level': 'int', 'point_count': 'int', 'chunk_index': 'int', 'chunk_total': 'int', 'para_nos': 'list', 'part_no': 'NoneType', 'part_name': 'NoneType', 'conference': 'str', 'month': 'int'}`
- `chunks_feasts_vec.json`：kind=jsonl n=11110 top_keys=[]
  - 记录1字段类型：`{'chunk_id': 'str', 'message_key': 'str', 'source_path': 'str', 'batch': 'str', 'text': 'str', 'book_title': 'str', 'book_path': 'list', 'message_title': 'str', 'message_number': 'int', 'author': 'NoneType', 'year': 'int', 'year_end': 'int', 'paragraph_type': 'str', 'tokens': 'int', 'min_level': 'int', 'point_count': 'int', 'chunk_index': 'int', 'chunk_total': 'int', 'para_nos': 'list', 'part_no': 'NoneType', 'part_name': 'NoneType', 'conference': 'str', 'month': 'int', 'embedding': 'list'}`
  - 记录2字段类型：`{'chunk_id': 'str', 'message_key': 'str', 'source_path': 'str', 'batch': 'str', 'text': 'str', 'book_title': 'str', 'book_path': 'list', 'message_title': 'str', 'message_number': 'int', 'author': 'NoneType', 'year': 'int', 'year_end': 'int', 'paragraph_type': 'str', 'tokens': 'int', 'min_level': 'int', 'point_count': 'int', 'chunk_index': 'int', 'chunk_total': 'int', 'para_nos': 'list', 'part_no': 'NoneType', 'part_name': 'NoneType', 'conference': 'str', 'month': 'int', 'embedding': 'list'}`
- `chunks_v01_20260929\chunks_12490.json`：kind=jsonl n=55841 top_keys=[]
  - 记录1字段类型：`{'chunk_id': 'str', 'message_key': 'str', 'source_path': 'str', 'batch': 'str', 'text': 'str', 'book_title': 'str', 'book_path': 'list', 'message_title': 'str', 'message_number': 'int', 'author': 'str', 'year': 'NoneType', 'year_end': 'NoneType', 'paragraph_type': 'str', 'tokens': 'int', 'min_level': 'int', 'point_count': 'int', 'chunk_index': 'int', 'chunk_total': 'int', 'para_nos': 'list', 'part_no': 'NoneType', 'part_name': 'NoneType', 'conference': 'NoneType', 'month': 'NoneType'}`
  - 记录2字段类型：`{'chunk_id': 'str', 'message_key': 'str', 'source_path': 'str', 'batch': 'str', 'text': 'str', 'book_title': 'str', 'book_path': 'list', 'message_title': 'str', 'message_number': 'int', 'author': 'str', 'year': 'NoneType', 'year_end': 'NoneType', 'paragraph_type': 'str', 'tokens': 'int', 'min_level': 'int', 'point_count': 'int', 'chunk_index': 'int', 'chunk_total': 'int', 'para_nos': 'list', 'part_no': 'NoneType', 'part_name': 'NoneType', 'conference': 'NoneType', 'month': 'NoneType'}`
- `chunks_v01_20260929\chunks_12490_vec.json`：kind=jsonl n=55841 top_keys=None
  - 记录1字段类型：`{'chunk_id': 'str', 'message_key': 'str', 'source_path': 'str', 'batch': 'str', 'text': 'str', 'book_title': 'str', 'book_path': 'list', 'message_title': 'str', 'message_number': 'int', 'author': 'str', 'year': 'NoneType', 'year_end': 'NoneType', 'paragraph_type': 'str', 'tokens': 'int', 'min_level': 'int', 'point_count': 'int', 'chunk_index': 'int', 'chunk_total': 'int', 'para_nos': 'list', 'part_no': 'NoneType', 'part_name': 'NoneType', 'conference': 'NoneType', 'month': 'NoneType', 'embedding': 'list'}`
  - 记录2字段类型：`{'chunk_id': 'str', 'message_key': 'str', 'source_path': 'str', 'batch': 'str', 'text': 'str', 'book_title': 'str', 'book_path': 'list', 'message_title': 'str', 'message_number': 'int', 'author': 'str', 'year': 'NoneType', 'year_end': 'NoneType', 'paragraph_type': 'str', 'tokens': 'int', 'min_level': 'int', 'point_count': 'int', 'chunk_index': 'int', 'chunk_total': 'int', 'para_nos': 'list', 'part_no': 'NoneType', 'part_name': 'NoneType', 'conference': 'NoneType', 'month': 'NoneType', 'embedding': 'list'}`
- `chunks_v01_20260929\chunks_feasts.json`：kind=jsonl n=11110 top_keys=[]
  - 记录1字段类型：`{'chunk_id': 'str', 'message_key': 'str', 'source_path': 'str', 'batch': 'str', 'text': 'str', 'book_title': 'str', 'book_path': 'list', 'message_title': 'str', 'message_number': 'int', 'author': 'NoneType', 'year': 'int', 'year_end': 'int', 'paragraph_type': 'str', 'tokens': 'int', 'min_level': 'int', 'point_count': 'int', 'chunk_index': 'int', 'chunk_total': 'int', 'para_nos': 'list', 'part_no': 'NoneType', 'part_name': 'NoneType', 'conference': 'str', 'month': 'int'}`
  - 记录2字段类型：`{'chunk_id': 'str', 'message_key': 'str', 'source_path': 'str', 'batch': 'str', 'text': 'str', 'book_title': 'str', 'book_path': 'list', 'message_title': 'str', 'message_number': 'int', 'author': 'NoneType', 'year': 'int', 'year_end': 'int', 'paragraph_type': 'str', 'tokens': 'int', 'min_level': 'int', 'point_count': 'int', 'chunk_index': 'int', 'chunk_total': 'int', 'para_nos': 'list', 'part_no': 'NoneType', 'part_name': 'NoneType', 'conference': 'str', 'month': 'int'}`
- `chunks_v01_20260929\chunks_feasts_vec.json`：kind=jsonl n=11110 top_keys=[]
  - 记录1字段类型：`{'chunk_id': 'str', 'message_key': 'str', 'source_path': 'str', 'batch': 'str', 'text': 'str', 'book_title': 'str', 'book_path': 'list', 'message_title': 'str', 'message_number': 'int', 'author': 'NoneType', 'year': 'int', 'year_end': 'int', 'paragraph_type': 'str', 'tokens': 'int', 'min_level': 'int', 'point_count': 'int', 'chunk_index': 'int', 'chunk_total': 'int', 'para_nos': 'list', 'part_no': 'NoneType', 'part_name': 'NoneType', 'conference': 'str', 'month': 'int', 'embedding': 'list'}`
  - 记录2字段类型：`{'chunk_id': 'str', 'message_key': 'str', 'source_path': 'str', 'batch': 'str', 'text': 'str', 'book_title': 'str', 'book_path': 'list', 'message_title': 'str', 'message_number': 'int', 'author': 'NoneType', 'year': 'int', 'year_end': 'int', 'paragraph_type': 'str', 'tokens': 'int', 'min_level': 'int', 'point_count': 'int', 'chunk_index': 'int', 'chunk_total': 'int', 'para_nos': 'list', 'part_no': 'NoneType', 'part_name': 'NoneType', 'conference': 'str', 'month': 'int', 'embedding': 'list'}`
- `excluded_files.json`：kind=dict n=1 top_keys=['candidates', 'excluded']
- `outline_12490.json`：kind=jsonl n=12328 top_keys=[]
  - 记录1字段类型：`{'id': 'str', 'batch': 'str', 'meta': 'dict', 'doc_header': 'dict', 'points': 'list', 'stats': 'dict'}`
  - 记录2字段类型：`{'id': 'str', 'batch': 'str', 'meta': 'dict', 'doc_header': 'dict', 'points': 'list', 'stats': 'dict'}`
- `outline_feasts.json`：kind=jsonl n=2630 top_keys=[]
  - 记录1字段类型：`{'id': 'str', 'batch': 'str', 'meta': 'dict', 'doc_header': 'dict', 'points': 'list', 'stats': 'dict'}`
  - 记录2字段类型：`{'id': 'str', 'batch': 'str', 'meta': 'dict', 'doc_header': 'dict', 'points': 'list', 'stats': 'dict'}`
- `trial_vectors.json`：kind=jsonl n=102 top_keys=[]
  - 记录1字段类型：`{'chunk_id': 'str', 'message_key': 'str', 'batch': 'str', 'role': 'str', 'dim': 'int', 'embedding': 'list'}`
  - 记录2字段类型：`{'chunk_id': 'str', 'message_key': 'str', 'batch': 'str', 'role': 'str', 'dim': 'int', 'embedding': 'list'}`
- `trial_vectors_v2.json`：kind=jsonl n=500 top_keys=[]
  - 记录1字段类型：`{'chunk_id': 'str', 'message_key': 'str', 'batch': 'str', 'source': 'str', 'dim': 'int', 'embedding': 'list'}`
  - 记录2字段类型：`{'chunk_id': 'str', 'message_key': 'str', 'batch': 'str', 'source': 'str', 'dim': 'int', 'embedding': 'list'}`
- `v1_20260929\anomalies.json`：kind=jsonl n=25250 top_keys=[]
  - 记录1字段类型：`{'type': 'str', 'batch': 'str', 'id': 'str', 'path': 'str', 'para_no': 'NoneType', 'detail': 'str'}`
  - 记录2字段类型：`{'type': 'str', 'batch': 'str', 'id': 'str', 'path': 'str', 'para_no': 'NoneType', 'detail': 'str'}`
- `v1_20260929\excluded_files.json`：kind=dict n=1 top_keys=['candidates', 'excluded']
- `v1_20260929\outline_12490.json`：kind=jsonl n=12121 top_keys=[]
  - 记录1字段类型：`{'id': 'str', 'batch': 'str', 'meta': 'dict', 'doc_header': 'dict', 'points': 'list', 'stats': 'dict'}`
  - 记录2字段类型：`{'id': 'str', 'batch': 'str', 'meta': 'dict', 'doc_header': 'dict', 'points': 'list', 'stats': 'dict'}`
- `v1_20260929\outline_feasts.json`：kind=jsonl n=2630 top_keys=[]
  - 记录1字段类型：`{'id': 'str', 'batch': 'str', 'meta': 'dict', 'doc_header': 'dict', 'points': 'list', 'stats': 'dict'}`
  - 记录2字段类型：`{'id': 'str', 'batch': 'str', 'meta': 'dict', 'doc_header': 'dict', 'points': 'list', 'stats': 'dict'}`
- `v2_before_candidates_20260929\excluded_files.json`：kind=dict n=1 top_keys=['candidates', 'excluded']
- `v2_before_candidates_20260929\outline_12490.json`：kind=jsonl n=12121 top_keys=[]
  - 记录1字段类型：`{'id': 'str', 'batch': 'str', 'meta': 'dict', 'doc_header': 'dict', 'points': 'list', 'stats': 'dict'}`
  - 记录2字段类型：`{'id': 'str', 'batch': 'str', 'meta': 'dict', 'doc_header': 'dict', 'points': 'list', 'stats': 'dict'}`
- `v2_final_20260929\anomalies.json`：kind=jsonl n=22900 top_keys=[]
  - 记录1字段类型：`{'type': 'str', 'batch': 'str', 'id': 'str', 'path': 'str', 'para_no': 'NoneType', 'detail': 'str'}`
  - 记录2字段类型：`{'type': 'str', 'batch': 'str', 'id': 'str', 'path': 'str', 'para_no': 'NoneType', 'detail': 'str'}`
- `v2_final_20260929\excluded_files.json`：kind=dict n=1 top_keys=['candidates', 'excluded']
- `v2_final_20260929\outline_12490.json`：kind=jsonl n=12066 top_keys=[]
  - 记录1字段类型：`{'id': 'str', 'batch': 'str', 'meta': 'dict', 'doc_header': 'dict', 'points': 'list', 'stats': 'dict'}`
  - 记录2字段类型：`{'id': 'str', 'batch': 'str', 'meta': 'dict', 'doc_header': 'dict', 'points': 'list', 'stats': 'dict'}`
- `v2_final_20260929\outline_feasts.json`：kind=jsonl n=2630 top_keys=[]
  - 记录1字段类型：`{'id': 'str', 'batch': 'str', 'meta': 'dict', 'doc_header': 'dict', 'points': 'list', 'stats': 'dict'}`
  - 记录2字段类型：`{'id': 'str', 'batch': 'str', 'meta': 'dict', 'doc_header': 'dict', 'points': 'list', 'stats': 'dict'}`
- `v3_partial_20260929\anomalies.json`：kind=jsonl n=13812 top_keys=[]
  - 记录1字段类型：`{'type': 'str', 'batch': 'str', 'id': 'str', 'path': 'str', 'para_no': 'NoneType', 'detail': 'str'}`
  - 记录2字段类型：`{'type': 'str', 'batch': 'str', 'id': 'str', 'path': 'str', 'para_no': 'NoneType', 'detail': 'str'}`
- `v3_partial_20260929\excluded_files.json`：kind=dict n=1 top_keys=['candidates', 'excluded']
- `v3_partial_20260929\outline_12490.json`：kind=jsonl n=12347 top_keys=[]
  - 记录1字段类型：`{'id': 'str', 'batch': 'str', 'meta': 'dict', 'doc_header': 'dict', 'points': 'list', 'stats': 'dict'}`
  - 记录2字段类型：`{'id': 'str', 'batch': 'str', 'meta': 'dict', 'doc_header': 'dict', 'points': 'list', 'stats': 'dict'}`
- `v3_partial_20260929\outline_feasts.json`：kind=jsonl n=2630 top_keys=[]
  - 记录1字段类型：`{'id': 'str', 'batch': 'str', 'meta': 'dict', 'doc_header': 'dict', 'points': 'list', 'stats': 'dict'}`
  - 记录2字段类型：`{'id': 'str', 'batch': 'str', 'meta': 'dict', 'doc_header': 'dict', 'points': 'list', 'stats': 'dict'}`
- `v4_20260929\anomalies.json`：kind=jsonl n=13685 top_keys=[]
  - 记录1字段类型：`{'type': 'str', 'batch': 'str', 'id': 'str', 'path': 'str', 'para_no': 'NoneType', 'detail': 'str'}`
  - 记录2字段类型：`{'type': 'str', 'batch': 'str', 'id': 'str', 'path': 'str', 'para_no': 'NoneType', 'detail': 'str'}`
- `v4_20260929\excluded_files.json`：kind=dict n=1 top_keys=['candidates', 'excluded']
- `v4_20260929\outline_12490.json`：kind=jsonl n=12328 top_keys=[]
  - 记录1字段类型：`{'id': 'str', 'batch': 'str', 'meta': 'dict', 'doc_header': 'dict', 'points': 'list', 'stats': 'dict'}`
  - 记录2字段类型：`{'id': 'str', 'batch': 'str', 'meta': 'dict', 'doc_header': 'dict', 'points': 'list', 'stats': 'dict'}`
- `v4_20260929\outline_feasts.json`：kind=jsonl n=2630 top_keys=[]
  - 记录1字段类型：`{'id': 'str', 'batch': 'str', 'meta': 'dict', 'doc_header': 'dict', 'points': 'list', 'stats': 'dict'}`
  - 记录2字段类型：`{'id': 'str', 'batch': 'str', 'meta': 'dict', 'doc_header': 'dict', 'points': 'list', 'stats': 'dict'}`

### 1.2 名称匹配（PanAI 除原文/清明上河图）：39；docs/panai4_es：22；repo其它：159
#### PanAI
- [dir] `G:\PanAI4.0专用\panai4_backup_20260930_2116\outline` size=0 mtime=2026-09-30T21:12:33
- [file] `G:\PanAI4.0专用\panai4_backup_20260930_2116\bible\build_chunks.py` size=30780 mtime=2026-09-29T22:31:34
- [file] `G:\PanAI4.0专用\panai4_backup_20260930_2116\bible\__pycache__\build_chunks.cpython-310.pyc` size=25027 mtime=2026-09-29T22:31:39
- [file] `G:\PanAI4.0专用\panai4_backup_20260930_2116\inherit\check_vectors.py` size=12919 mtime=2026-09-30T15:19:02
- [file] `G:\PanAI4.0专用\panai4_backup_20260930_2116\inherit\gen_embeddings.py` size=19678 mtime=2026-09-30T09:43:07
- [file] `G:\PanAI4.0专用\panai4_backup_20260930_2116\inherit\__pycache__\check_vectors.cpython-310.pyc` size=10352 mtime=2026-09-30T15:19:06
- [file] `G:\PanAI4.0专用\panai4_backup_20260930_2116\inherit\__pycache__\gen_embeddings.cpython-310.pyc` size=17001 mtime=2026-09-30T10:12:17
- [file] `G:\PanAI4.0专用\panai4_backup_20260930_2116\outline\build_chunks.py` size=34629 mtime=2026-09-29T22:23:50
- [file] `G:\PanAI4.0专用\panai4_backup_20260930_2116\outline\convert_outline.py` size=65295 mtime=2026-09-29T21:17:41
- [file] `G:\PanAI4.0专用\panai4_backup_20260930_2116\outline\gen_embeddings.py` size=61122 mtime=2026-09-30T21:11:52
- [file] `G:\PanAI4.0专用\panai4_backup_20260930_2116\outline\__pycache__\build_chunks.cpython-310.pyc` size=26732 mtime=2026-09-29T22:24:01
- [file] `G:\PanAI4.0专用\panai4_backup_20260930_2116\outline\__pycache__\convert_outline.cpython-310.pyc` size=49902 mtime=2026-09-29T14:55:37
- [file] `G:\PanAI4.0专用\panai4_backup_20260930_2116\outline\__pycache__\gen_embeddings.cpython-310.pyc` size=47234 mtime=2026-09-30T21:12:49
- [dir] `G:\PanAI4.0专用\纲目JSON\chunks_v01_20260929` size=0 mtime=2026-09-29T22:22:42
- [file] `G:\PanAI4.0专用\纲目JSON\chunks_12490.json` size=118171428 mtime=2026-09-29T22:24:23
- [file] `G:\PanAI4.0专用\纲目JSON\chunks_12490.json.bak` size=112030188 mtime=2026-09-29T15:57:32
- [file] `G:\PanAI4.0专用\纲目JSON\chunks_12490_vec.json` size=1386787642 mtime=2026-09-29T23:36:37
- [file] `G:\PanAI4.0专用\纲目JSON\chunks_bible.json` size=7426387 mtime=2026-09-29T22:31:40
- [file] `G:\PanAI4.0专用\纲目JSON\chunks_bible_vec.json` size=91283031 mtime=2026-09-29T22:53:04
- [file] `G:\PanAI4.0专用\纲目JSON\chunks_feasts.json` size=26035954 mtime=2026-09-29T22:24:23
- [file] `G:\PanAI4.0专用\纲目JSON\chunks_feasts.json.bak` size=25043462 mtime=2026-09-29T15:57:32
- [file] `G:\PanAI4.0专用\纲目JSON\chunks_feasts_vec.json` size=278483135 mtime=2026-09-29T23:05:27
- [file] `G:\PanAI4.0专用\纲目JSON\outline_12490.json` size=121121694 mtime=2026-09-29T14:58:24
- [file] `G:\PanAI4.0专用\纲目JSON\outline_feasts.json` size=33155313 mtime=2026-09-29T14:58:24
- [file] `G:\PanAI4.0专用\纲目JSON\trial_vectors.json` size=2341931 mtime=2026-09-29T16:28:31
- [file] `G:\PanAI4.0专用\纲目JSON\trial_vectors_v2.json` size=11485569 mtime=2026-09-29T22:44:24
- [file] `G:\PanAI4.0专用\纲目JSON\chunks_v01_20260929\chunks_12490.json` size=112068348 mtime=2026-09-29T16:22:45
- [file] `G:\PanAI4.0专用\纲目JSON\chunks_v01_20260929\chunks_12490_vec.json` size=1380769819 mtime=2026-09-29T20:13:02
- [file] `G:\PanAI4.0专用\纲目JSON\chunks_v01_20260929\chunks_feasts.json` size=25043462 mtime=2026-09-29T16:22:45
- [file] `G:\PanAI4.0专用\纲目JSON\chunks_v01_20260929\chunks_feasts_vec.json` size=277460512 mtime=2026-09-29T21:04:16
- [file] `G:\PanAI4.0专用\纲目JSON\v1_20260929\outline_12490.json` size=108383889 mtime=2026-09-29T11:09:06
- [file] `G:\PanAI4.0专用\纲目JSON\v1_20260929\outline_feasts.json` size=28725019 mtime=2026-09-29T11:09:06
- [file] `G:\PanAI4.0专用\纲目JSON\v2_before_candidates_20260929\outline_12490.json` size=108965575 mtime=2026-09-29T12:27:18
- [file] `G:\PanAI4.0专用\纲目JSON\v2_final_20260929\outline_12490.json` size=105402193 mtime=2026-09-29T12:48:51
- [file] `G:\PanAI4.0专用\纲目JSON\v2_final_20260929\outline_feasts.json` size=28767889 mtime=2026-09-29T12:27:18
- [file] `G:\PanAI4.0专用\纲目JSON\v3_partial_20260929\outline_12490.json` size=121245218 mtime=2026-09-29T13:33:12
- [file] `G:\PanAI4.0专用\纲目JSON\v3_partial_20260929\outline_feasts.json` size=33058003 mtime=2026-09-29T13:33:12
- [file] `G:\PanAI4.0专用\纲目JSON\v4_20260929\outline_12490.json` size=120678507 mtime=2026-09-29T14:47:28
- [file] `G:\PanAI4.0专用\纲目JSON\v4_20260929\outline_feasts.json` size=33058003 mtime=2026-09-29T14:47:28
#### docs
- [file] `G:\copypan\docs\panai4_es\chunks_es_plan.md` size=21836 mtime=2026-10-26T17:46:29
- [file] `G:\copypan\docs\panai4_es\archive\bible_outline_probe.md` size=214191 mtime=2026-09-29T17:14:26
- [file] `G:\copypan\docs\panai4_es\archive\embedding_report_v2.md` size=6311 mtime=2026-09-29T23:38:27
- [file] `G:\copypan\docs\panai4_es\archive\inherit_embedding_report.md` size=1017 mtime=2026-09-30T15:20:10
- [file] `G:\copypan\docs\panai4_es\archive\life_12490_fix_final.csv` size=17908 mtime=2026-11-06T11:38:48
- [file] `G:\copypan\docs\panai4_es\archive\life_12490_fix_list.csv` size=103846 mtime=2026-11-06T10:14:33
- [file] `G:\copypan\docs\panai4_es\archive\life_12490_fix_list.md` size=69780 mtime=2026-11-06T10:14:33
- [file] `G:\copypan\docs\panai4_es\archive\life_12490_fix_list_v2.csv` size=138199 mtime=2026-11-06T11:21:03
- [file] `G:\copypan\docs\panai4_es\archive\life_12490_fix_list_v2.md` size=22489 mtime=2026-11-06T11:21:03
- [file] `G:\copypan\docs\panai4_es\archive\life_12490_fix_list_v3.csv` size=108795 mtime=2026-11-06T11:38:48
- [file] `G:\copypan\docs\panai4_es\archive\life_12490_fix_list_v3.md` size=23115 mtime=2026-11-06T11:38:48
- [file] `G:\copypan\docs\panai4_es\archive\life_12490_fix_review.csv` size=2674 mtime=2026-11-06T11:38:48
- [file] `G:\copypan\docs\panai4_es\archive\life_in_12490_check.md` size=28752 mtime=2026-11-06T09:42:05
- [file] `G:\copypan\docs\panai4_es\archive\life_in_12490_check2.md` size=42311 mtime=2026-11-06T09:59:59
- [file] `G:\copypan\docs\panai4_es\archive\life_outline_pairing.csv` size=574876 mtime=2026-11-06T09:17:42
- [file] `G:\copypan\docs\panai4_es\archive\life_outline_probe.md` size=66750 mtime=2026-11-06T08:56:31
- [file] `G:\copypan\docs\panai4_es\archive\life_outline_probe2.md` size=180763 mtime=2026-11-06T09:19:42
- [file] `G:\copypan\docs\panai4_es\archive\vectors_integrity.md` size=1676 mtime=2026-09-30T15:28:23
- [file] `G:\copypan\docs\panai4_es\_trash\embedding_report.md` size=3322 mtime=2026-09-29T21:05:16
- [file] `G:\copypan\docs\panai4_es\_trash\embedding_trial_report.md` size=3721 mtime=2026-09-29T16:28:31
- [file] `G:\copypan\docs\panai4_es\_trash\embedding_trial_v2.md` size=5804 mtime=2026-09-29T22:44:49
- [file] `G:\copypan\docs\panai4_es\_trash\inherit_embedding_trial.md` size=1866 mtime=2026-09-30T10:19:35
#### repo
- [file] `G:\copypan\back_mic\backend\EMBEDDING_RULES.md` size=1035 mtime=2026-06-02T19:18:54
- [file] `G:\copypan\back_mic\backend\ai_search\embedding_service.py` size=1712 mtime=2026-06-02T19:18:54
- [file] `G:\copypan\back_mic\backend\ai_search\__pycache__\feast_outline_prompts.cpython-310.pyc` size=16315 mtime=2026-06-08T18:57:00
- [file] `G:\copypan\back_mic\backend\ai_search\__pycache__\rough_outline_prompts.cpython-310.pyc` size=15829 mtime=2026-06-11T11:05:16
- [dir] `G:\copypan\back_mic\backend\features\feast_outline` size=0 mtime=2026-06-11T11:16:31
- [dir] `G:\copypan\back_mic\backend\features\feast_outline_maker` size=0 mtime=2026-06-11T10:48:47
- [dir] `G:\copypan\back_mic\backend\features\outline_eval` size=0 mtime=2026-06-22T09:11:21
- [dir] `G:\copypan\back_mic\backend\features\outline_translate` size=0 mtime=2026-06-11T11:16:31
- [dir] `G:\copypan\back_mic\backend\features\progress_outline` size=0 mtime=2026-06-22T09:24:35
- [dir] `G:\copypan\back_mic\backend\features\rough_outline` size=0 mtime=2026-08-25T09:19:00
- [file] `G:\copypan\back_mic\backend\formatters\format_chinese_outline.py` size=23765 mtime=2026-06-02T19:18:54
- [file] `G:\copypan\back_mic\backend\formatters\format_english_outline.py` size=11630 mtime=2026-06-08T20:22:31
- [file] `G:\copypan\back_mic\backend\formatters\__pycache__\format_chinese_outline.cpython-310.pyc` size=13375 mtime=2026-06-11T10:17:14
- [file] `G:\copypan\back_mic\backend\formatters\__pycache__\format_english_outline.cpython-310.pyc` size=8714 mtime=2026-06-11T10:17:14
- [file] `G:\copypan\back_mic\backend\kg_rag\embedding_adapter.py` size=3358 mtime=2026-09-30T13:13:38
- [file] `G:\copypan\back_mic\backend\kg_rag\embedding_adapter.py.bak` size=3231 mtime=2026-06-02T19:18:54
- [file] `G:\copypan\back_mic\backend\kg_rag\scripts\generate_embeddings.py` size=9015 mtime=2026-06-11T10:17:09
- [file] `G:\copypan\back_mic\backend\kg_rag\__pycache__\embedding_adapter.cpython-310.pyc` size=3334 mtime=2026-09-30T13:13:50
- [dir] `G:\copypan\back_mic\backend\panai4\outline` size=0 mtime=2026-11-06T11:54:26
- [file] `G:\copypan\back_mic\backend\panai4\bible\build_chunks.py` size=30780 mtime=2026-10-26T17:46:29
- [file] `G:\copypan\back_mic\backend\panai4\bible\__pycache__\build_chunks.cpython-310.pyc` size=25027 mtime=2026-09-29T22:31:39
- [file] `G:\copypan\back_mic\backend\panai4\inherit\check_vectors.py` size=12909 mtime=2026-10-26T17:46:29
- [file] `G:\copypan\back_mic\backend\panai4\inherit\gen_embeddings.py` size=19668 mtime=2026-10-26T17:46:29
- [file] `G:\copypan\back_mic\backend\panai4\inherit\__pycache__\check_vectors.cpython-310.pyc` size=10352 mtime=2026-09-30T15:19:06
- [file] `G:\copypan\back_mic\backend\panai4\inherit\__pycache__\gen_embeddings.cpython-310.pyc` size=16991 mtime=2026-09-30T21:17:17
- [file] `G:\copypan\back_mic\backend\panai4\outline\build_chunks.py` size=34629 mtime=2026-10-26T17:46:29
- [file] `G:\copypan\back_mic\backend\panai4\outline\convert_outline.py` size=65295 mtime=2026-10-26T17:46:29
- [file] `G:\copypan\back_mic\backend\panai4\outline\gen_embeddings.py` size=61122 mtime=2026-10-26T17:46:29
- [file] `G:\copypan\back_mic\backend\panai4\outline\probe_12490_assets.py` size=42822 mtime=2026-11-06T11:54:33
- [file] `G:\copypan\back_mic\backend\panai4\outline\probe_life_in_12490.py` size=40857 mtime=2026-11-06T09:40:48
- [file] `G:\copypan\back_mic\backend\panai4\outline\probe_life_in_12490_r2.py` size=63534 mtime=2026-11-06T09:59:56
- [file] `G:\copypan\back_mic\backend\panai4\outline\probe_life_outline.py` size=65932 mtime=2026-11-06T08:56:28
- [file] `G:\copypan\back_mic\backend\panai4\outline\probe_life_outline2.py` size=70406 mtime=2026-11-06T09:20:03
- [file] `G:\copypan\back_mic\backend\panai4\outline\__pycache__\build_chunks.cpython-310.pyc` size=26732 mtime=2026-09-29T22:24:01
- [file] `G:\copypan\back_mic\backend\panai4\outline\__pycache__\convert_outline.cpython-310.pyc` size=49902 mtime=2026-09-29T14:55:37
- [file] `G:\copypan\back_mic\backend\panai4\outline\__pycache__\gen_embeddings.cpython-310.pyc` size=47234 mtime=2026-09-30T21:12:49
- [file] `G:\copypan\back_mic\backend\panai4\outline\__pycache__\probe_12490_assets.cpython-310.pyc` size=33967 mtime=2026-11-06T11:54:35
- [file] `G:\copypan\back_mic\backend\panai4\outline\__pycache__\probe_life_in_12490.cpython-310.pyc` size=32609 mtime=2026-11-06T09:40:53
- [file] `G:\copypan\back_mic\backend\panai4\outline\__pycache__\probe_life_in_12490_r2.cpython-310.pyc` size=47026 mtime=2026-11-06T09:59:01
- [file] `G:\copypan\back_mic\backend\panai4\outline\__pycache__\probe_life_outline.cpython-310.pyc` size=50017 mtime=2026-11-06T08:55:10

### 1.3 脚本默认路径与能力

- `config.DEFAULT_OUT_DIR` = `G:\PanAI4.0专用\纲目JSON`（config.py:340）
- **build_chunks.py**：读 `outline_*.json`，写 `chunks_*.json` JSONL；`chunk_id_of` = `sha1(message_key)[:12]`（153–155, 186）；`render_header` = book_title+U+3000+message_title（83–89）；`--out` 默认 DEFAULT_OUT_DIR（310）。
- **gen_embeddings.py**：`_embed_input` = `record['text']`（89–91）；输出 `chunks_*_vec.json`；批大小 50；支持断点续跑 `_read_done_ids`（840+）；**无** `--chunk-ids`；**必须**调嵌入接口补缺失；`--out/--inputs/--concurrency`（1480–1496）。
- **index_to_es.py**：向量字段名 `embedding`（65–70）；`_id = chunk_id`（473）；`--index/--input` 可单索引（1729–1731）；本地 create 后全量 bulk；remote 可 `skip_existing` 增量跳过已有 _id（1594–1596）；**不能**「无向量文件只写元数据」。

### 1.4 纲目线资产表

| 资产 | 路径 | 状态 | 大小 | mtime | 记录数 |
|---|---|---|---:|---|---:|
| outline JSON (12490) | `G:\PanAI4.0专用\纲目JSON\outline_12490.json` | 存在 | 121121694 | 2026-09-29T14:58:24 | 12328 |
| chunks JSON (12490) | `G:\PanAI4.0专用\纲目JSON\chunks_12490.json` | 存在 | 118171428 | 2026-09-29T22:24:23 | 55841 |
| 向量文件 (12490) | `G:\PanAI4.0专用\纲目JSON\chunks_12490_vec.json` | 存在 | 1386787642 | 2026-09-29T23:36:37 | 55841 |
| 排除清单 | `G:\PanAI4.0专用\纲目JSON\excluded_files.json` | 存在 | 121195 | 2026-09-29T14:58:24 | 1 |
| 异常清单 | `G:\PanAI4.0专用\纲目JSON\anomalies.json` | 存在 | 5360518 | 2026-09-29T14:58:24 | 13684 |
| outline JSON (feasts) | `G:\PanAI4.0专用\纲目JSON\outline_feasts.json` | 存在 | 33155313 | 2026-09-29T14:58:24 | 2630 |
| chunks JSON (feasts) | `G:\PanAI4.0专用\纲目JSON\chunks_feasts.json` | 存在 | 26035954 | 2026-09-29T22:24:23 | 11110 |
| 向量文件 (feasts) | `G:\PanAI4.0专用\纲目JSON\chunks_feasts_vec.json` | 存在 | 278483135 | 2026-09-29T23:05:27 | 11110 |
| chunks JSON (bible) | `G:\PanAI4.0专用\纲目JSON\chunks_bible.json` | 存在 | 7426387 | 2026-09-29T22:31:40 | 3691 |
| 向量文件 (bible) | `G:\PanAI4.0专用\纲目JSON\chunks_bible_vec.json` | 存在 | 91283031 | 2026-09-29T22:53:04 | 3691 |

### 1.5 feasts / bible 清点
- outline JSON (feasts): status=存在 n=2630 size=33155313
- chunks JSON (feasts): status=存在 n=11110 size=26035954
- 向量文件 (feasts): status=存在 n=11110 size=278483135
- chunks JSON (bible): status=存在 n=3691 size=7426387
- 向量文件 (bible): status=存在 n=3691 size=91283031

## 2. id 对账

- 模式：三向
- chunks=55841 dup=0；vec=55841 dup=0；es=55841 dup=0
- chunks vs vec：仅chunks=0 仅vec=0 交=55841；闭合 chunks 0+55841=55841 vs 55841；vec 0+55841=55841 vs 55841
- chunks vs es：仅c=0 仅e=0 交=55841
- vec vs es：仅v=0 仅e=0 交=55841
- message_key：chunks=12328 es=12328 仅c=0 仅e=0 交=12328
- message_key 块数不一致：0

## 3. 内容一致性

- text 相同=55841 不同=0 ES缺块=0

### 3.2 头部行抽样 20
- chunks第一行==ES第一行：20/20
- chunks第一行==book+U+3000+title：20/20
- ES第一行==book+U+3000+title：20/20

### 3.3 向量抽样（只报数值）
- 读取含向量的文档数（file+ES合计计数）≈60
  - `gm12490_037fb28bd8de_c1` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_037fb28bd8de_c2` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_037fb28bd8de_c3` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_07b8b40dfdd1_c4` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_0ea75d8d60cf_c11` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_152444876e67_c3` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_2be6c6968379_c2` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_3276443d0da4_c1` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_359919716d07_c2` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_44c7c7e07975_c2` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_55514568644e_c2` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_573c6f6fc81b_c7` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_72843112100b_c4` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_7f63dcb9283b_c1` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_7f63dcb9283b_c2` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_7f63dcb9283b_c3` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_8441ebb1e24e_c1` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_8441ebb1e24e_c2` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_8441ebb1e24e_c3` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_8da527a6ef4a_c2` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_9f6a602e20ed_c6` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_a26123e50281_c3` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_a8fd7f6eeb7c_c3` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_aa98e70b8fe2_c2` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_b5ae727d02be_c3` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_c0bdaa3500ed_c1` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_c627c7977eba_c3` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_d7f36db492b9_c2` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_eb8a49f0675e_c6` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000
  - `gm12490_f571436ab19a_c1` dims=1024/1024 norm=1.0/1.0 max_abs=0.000000e+00 cos=1.00000000

### 3.4 embedding 输入
- `gen_embeddings._embed_input`：`return record.get("text") or ""`（gen_embeddings.py:89–91）。即向量对 **text 本身**。

## 4. 修订清单对齐

- fix_final 条数=70；匹配=70 不匹配=0；闭合=True
- 字段影响：title：改 message_title + text 第一行；message_key/chunk_id/source_path/book_path 不变。book：改 book_title + text 第一行；message_key 路径里可能仍含旧书名（如雅歌书/约翰二书_），但 chunk_id=sha1(message_key) 不变，与 ES _id 仍一致。number：只改 message_number，text 不变，无需重算向量。
- book 类 old 含子串于 message_key：12
- 需重算向量：块=315 篇=69
- 头部公式对齐抽样：100/100（text 正文无法仅凭 chunks 字段无 points 全量重建；头部可机械替换）

## 5. 九个索引向量字段

| 索引 | 向量字段 | dims | similarity | index_options.type |
|---|---|---:|---|---|
| panai4_bible | embedding | 1024 | cosine | int8_hnsw |
| panai4_map_note | text_vector | 1024 | cosine | int8_hnsw |
| panai4_outline_12490 | embedding | 1024 | cosine | int8_hnsw |
| panai4_outline_feasts | embedding | 1024 | cosine | int8_hnsw |
| panai4_pano_catalog | text_vector | 1024 | cosine | int8_hnsw |
| panai4_text_cwwl | text_vector | 1024 | cosine | int8_hnsw |
| panai4_text_cwwn | text_vector | 1024 | cosine | int8_hnsw |
| panai4_text_life | text_vector | 1024 | cosine | int8_hnsw |
| panai4_text_others | text_vector | 1024 | cosine | int8_hnsw |
- **字段名不一致**：['embedding', 'text_vector']。统一检索时必须按索引分支取不同字段名，不能写死单一字段。

## 6. 磁盘与风险

- G: free=620522631168 bytes (620.52 GB)；total=960.20 GB
- PanAI4.0专用 total≈13105296181 bytes (13.11 GB)
- 方案A完整备份（outline+chunks+vec+excluded+anomalies 粗算）≈1.63 GB
- 妨碍方案 A 的因素：
  1. `gen_embeddings` 无「只重算指定 chunk_id」参数；局部重算需自行过滤或删 vec 中对应行后重跑（会调 API）。
  2. 本地 `index_to_es` 默认 create+全量写入；要用文件重建需接受删建或改流程做 update-by-id。
  3. 可从已有 `*_vec.json` 写入且不调嵌入（index_to_es 读文件 bulk）——前提是 vec 文件已含更新后的 embedding。
  4. text 正文依赖纲目 points；改标题只需替换第一行，可用字段机械更新 text 头部。

## 验证

1. count 55841/55841 一致=True (55841=True)
2. 纲目JSON 快照 before_files=41 bytes=4733504505 after_files=41 bytes=4733504505 identical=True
3. 闭合：c=0+55841==55841 → True；v=0+55841==55841 → True；e 对 c：0+55841==55841 → True
4. fix 匹配+不匹配=70+0=70 vs 70=70
5. git:
```
?? back_mic/backend/panai4/outline/probe_12490_assets.py
?? back_mic/backend/panai4/outline/probe_life_fixlist.py
?? back_mic/backend/panai4/outline/probe_life_fixlist_v2.py
?? back_mic/backend/panai4/outline/probe_life_fixlist_v3.py
?? back_mic/backend/panai4/outline/probe_life_in_12490.py
?? back_mic/backend/panai4/outline/probe_life_in_12490_r2.py
?? back_mic/backend/panai4/outline/probe_life_outline.py
?? back_mic/backend/panai4/outline/probe_life_outline2.py
```
6. ES 只用 info/count/get_mapping/get(indices)/search/scroll/mget；除 3.3 外排除向量字段；3.3 读取向量文档计数≈60
7. 未运行 gen_embeddings / index_to_es / build_chunks。

