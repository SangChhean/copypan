# 任务4 索引数据整理

> 2026-11-06T16:06:29；log=`G:\copypan\logs\task4_organize_20261106_160629.log`

## D3 磁盘
- G 盘剩余 **613.50 GB**；估算整理约 **10.70 GB**（1.7% of free）

## D1 盘点

### panai4_outline_12490
- 02 `outline_12490.new.json` {'path': 'G:\\PanAI4.0专用\\_staging_life_fix\\outline_12490.new.json', 'exists': True, 'size': 121122683, 'mtime': '2026-11-06T12:17:18', 'n': 12328}
- 02 `chunks_12490.new.json` {'path': 'G:\\PanAI4.0专用\\_staging_life_fix\\chunks_12490.new.json', 'exists': True, 'size': 118180101, 'mtime': '2026-11-06T12:38:47', 'n': 55841}
- 03 `chunks_12490_vec.new.json` size=1386795176
- D2 {'index': 'panai4_outline_12490', 'es_count': 55841, 'file_n': 55841, 'missing_in_file': 0, 'extra_in_file': 0, 'expect': 55841, 'text_sample_diff': 0, 'vec_sample_diff': 0}

### panai4_outline_feasts
- 02 `outline_feasts.json` {'path': 'G:\\PanAI4.0专用\\纲目JSON\\outline_feasts.json', 'exists': True, 'size': 33155313, 'mtime': '2026-09-29T14:58:24', 'n': 2630}
- 02 `chunks_feasts.json` {'path': 'G:\\PanAI4.0专用\\纲目JSON\\chunks_feasts.json', 'exists': True, 'size': 26035954, 'mtime': '2026-09-29T22:24:23', 'n': 11110}
- 03 `chunks_feasts_vec.json` size=278483135
- D2 {'index': 'panai4_outline_feasts', 'es_count': 11110, 'file_n': 11110, 'missing_in_file': 0, 'extra_in_file': 0, 'expect': 11110, 'text_sample_diff': 0, 'vec_sample_diff': 0}

### panai4_bible
- 02 `chunks_bible.json` {'path': 'G:\\PanAI4.0专用\\纲目JSON\\chunks_bible.json', 'exists': True, 'size': 7426387, 'mtime': '2026-09-29T22:31:40', 'n': 3691}
- 03 `chunks_bible_vec.json` size=91283031
- D2 {'index': 'panai4_bible', 'es_count': 3691, 'file_n': 3691, 'missing_in_file': 0, 'extra_in_file': 0, 'expect': 3691, 'text_sample_diff': 0, 'vec_sample_diff': 0}

### panai4_text_life
- 02 `life_rendered.new.jsonl` {'path': 'G:\\PanAI4.0专用\\_staging_text_life\\life_rendered.new.jsonl', 'exists': True, 'size': 85923381, 'mtime': '2026-11-06T15:37:19', 'n': 39463}
- 03 shards=20
- D2 {'index': 'panai4_text_life', 'es_count': 39463, 'file_n': 39463, 'missing_in_file': 0, 'extra_in_file': 0, 'expect': 39463, 'text_sample_diff': 0, 'vec_sample_diff': 0}

### panai4_text_cwwl
- 02 `kg-rag_cwwl.jsonl` {'path': 'G:\\PanAI4.0专用\\12490原文JSONL\\rendered\\kg-rag_cwwl.jsonl', 'exists': True, 'size': 426191428, 'mtime': '2026-09-30T10:11:33'}
- 03 shards=90
- D2 {'index': 'panai4_text_cwwl', 'es_count': 178107, 'file_n': 178107, 'missing_in_file': 0, 'extra_in_file': 0, 'expect': 178107, 'text_sample_diff': 0, 'vec_sample_diff': 0}

### panai4_text_cwwn
- 02 `kg-rag_cwwn.jsonl` {'path': 'G:\\PanAI4.0专用\\12490原文JSONL\\rendered\\kg-rag_cwwn.jsonl', 'exists': True, 'size': 78105967, 'mtime': '2026-09-30T10:11:36', 'n': 32032}
- 03 shards=17
- D2 {'index': 'panai4_text_cwwn', 'es_count': 32032, 'file_n': 32032, 'missing_in_file': 0, 'extra_in_file': 0, 'expect': 32032, 'text_sample_diff': 0, 'vec_sample_diff': 0}

### panai4_text_others
- 02 `kg-rag_others.jsonl` {'path': 'G:\\PanAI4.0专用\\12490原文JSONL\\rendered\\kg-rag_others.jsonl', 'exists': True, 'size': 33383696, 'mtime': '2026-09-30T10:11:37', 'n': 15481}
- 03 shards=8
- D2 {'index': 'panai4_text_others', 'es_count': 15481, 'file_n': 15481, 'missing_in_file': 0, 'extra_in_file': 0, 'expect': 15481, 'text_sample_diff': 0, 'vec_sample_diff': 0}

### panai4_map_note
- 02 `kg-rag_map_note.jsonl` {'path': 'G:\\PanAI4.0专用\\12490原文JSONL\\rendered\\kg-rag_map_note.jsonl', 'exists': True, 'size': 27101558, 'mtime': '2026-09-30T10:11:38', 'n': 16052}
- 03 shards=9
- D2 {'index': 'panai4_map_note', 'es_count': 16052, 'file_n': 16052, 'missing_in_file': 0, 'extra_in_file': 0, 'expect': 16052, 'text_sample_diff': 0, 'vec_sample_diff': 0}

### panai4_pano_catalog
- 02 `tree.json` {'path': 'G:\\PanAI4.0专用\\清明上河图目录\\tree.json', 'exists': True, 'size': 37355403, 'mtime': '2026-09-30T09:57:20', 'n': 512168}
- 02 `catalog_clean.json` {'path': 'G:\\PanAI4.0专用\\清明上河图目录\\catalog_clean.json', 'exists': True, 'size': 28664682, 'mtime': '2026-09-30T11:22:07', 'n': 634398}
- 02 `svo76.json` {'path': 'G:\\PanAI4.0专用\\清明上河图目录\\svo76.json', 'exists': True, 'size': 37258, 'mtime': '2026-09-30T15:16:15', 'n': 382}
- 03 无向量：pano_catalog 目录树索引，无 embedding/text_vector
- D2 es_count=53151（无标准 chunk 文件比对）

## D2 汇总
- {'index': 'panai4_outline_12490', 'es_count': 55841, 'file_n': 55841, 'missing_in_file': 0, 'extra_in_file': 0, 'expect': 55841, 'text_sample_diff': 0, 'vec_sample_diff': 0}
- {'index': 'panai4_outline_feasts', 'es_count': 11110, 'file_n': 11110, 'missing_in_file': 0, 'extra_in_file': 0, 'expect': 11110, 'text_sample_diff': 0, 'vec_sample_diff': 0}
- {'index': 'panai4_bible', 'es_count': 3691, 'file_n': 3691, 'missing_in_file': 0, 'extra_in_file': 0, 'expect': 3691, 'text_sample_diff': 0, 'vec_sample_diff': 0}
- {'index': 'panai4_text_life', 'es_count': 39463, 'file_n': 39463, 'missing_in_file': 0, 'extra_in_file': 0, 'expect': 39463, 'text_sample_diff': 0, 'vec_sample_diff': 0}
- {'index': 'panai4_text_cwwl', 'es_count': 178107, 'file_n': 178107, 'missing_in_file': 0, 'extra_in_file': 0, 'expect': 178107, 'text_sample_diff': 0, 'vec_sample_diff': 0}
- {'index': 'panai4_text_cwwn', 'es_count': 32032, 'file_n': 32032, 'missing_in_file': 0, 'extra_in_file': 0, 'expect': 32032, 'text_sample_diff': 0, 'vec_sample_diff': 0}
- {'index': 'panai4_text_others', 'es_count': 15481, 'file_n': 15481, 'missing_in_file': 0, 'extra_in_file': 0, 'expect': 15481, 'text_sample_diff': 0, 'vec_sample_diff': 0}
- {'index': 'panai4_map_note', 'es_count': 16052, 'file_n': 16052, 'missing_in_file': 0, 'extra_in_file': 0, 'expect': 16052, 'text_sample_diff': 0, 'vec_sample_diff': 0}
- {'index': 'panai4_pano_catalog', 'es_count': 53151, 'note': '无 chunk_id 文件或 pano'}

## D7 原位置快照
- 纲目JSON before=(41, 4733504505) after=(41, 4733504505) equal=True
- 12490原文JSONL before=(298, 8297200099) after=(298, 8297200099) equal=True
- scripts_snapshot files=94
- 耗时 1603.4s

## 密钥泄露检查：通过
