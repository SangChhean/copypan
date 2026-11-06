# text_life 修订预检（T0）— 暂停点

> 2026-11-06T15:29:32；log=`G:\copypan\logs\text_life_fix_20261106_152405.log`

## 摘要

(1) 受影响块=**5054** / 篇=**268**（dirty 63 篇·1363 块 + rename-only 3691 块）；清单字段行=11471（book_title 5054 + message_title 1363 + text 5054）
(2) 重算向量块=**5054**；新 text 字符合计≈1,364,355；费用上限=$0.0101（$0.002/千块）
(3) confidence：**auto=5054 块 / needs_review=0**（`text_life_fix_review.csv` 仅表头）
(4) 脏书名 **63 篇** vs 12490（去「第N篇」后 NFKC 归一）：**相同=62 / 包含=1 / 不同=0**；包含篇=诗篇生命读经·33（new 含「第三十三篇　」前缀后 stem 包含 12490）。块级对照同规则：相同_12490=1338 / 包含_12490=25 / 不同=0
(5) 服务器预检：count=39463；`text_vector` 1024 cosine int8_hnsw；affected mget vs `es_local_before` **same=5054 diff=0**；非受影响字段抽样 diff=0；随机 100 非受影响向量 mismatch=0
(6) 四方 id 集合 equal；rendered vs 本机 ES text **same=39463**；render 复现 **same=39463 diff=0**
(7) 好文档 message_title 形态：带「第N篇」前缀=**1921 篇**；不带=**63 篇**（恰为脏书名篇）→ 还原规则套「第N篇　+frag+mt」成立
(8) **暂停：等你回复「写」**；needs_review=0，无需额外决定即可按清单全量 auto 写

## 资产
- raw `G:\PanAI4.0专用\12490原文JSONL\kg-rag_life.jsonl` n=39463 size=80157004
- rendered `G:\PanAI4.0专用\12490原文JSONL\rendered\kg-rag_life.jsonl` n=39463
- vectors shards=20 ×≈2000
- 备份 `G:\PanAI4.0专用\备份_text_life修订前_20261106`；清单 `text_life_fix_list.csv`；review `text_life_fix_review.csv`

## 渲染规则
- {'header': 'build_header: book/message/section 去空、相邻去重、U+3000 连接；>120 截断 section', 'chars': 'len(new_text)', 'es_vector_field': 'text_vector', 'es_id': 'chunk_id', 'shard_size': 2000, 'embed_input': 'text 本身'}

## 脏数据样例（前 10）
- `列王记生命读经，第一篇` → clean=`列王纪生命读经` frag=`` mt=`介言` mno=1`
- `撒母耳记生命读经，第一篇` → clean=`撒母耳记生命读经` frag=`` mt=`介言` mno=1`
- `路得记生命读经，第一篇` → clean=`路得记生命读经` frag=`` mt=`介言` mno=1`
- `约书亚记生命读经，第一篇` → clean=`约书亚记生命读经` frag=`` mt=`介言` mno=1`
- `哈巴谷书生命读经，第一篇` → clean=`哈巴谷书生命读经` frag=`` mt=`介言以及申言者与耶和华之间第一次和第二次的对话` mno=1`
- `弥迦书生命读经，第一篇` → clean=`弥迦书生命读经` frag=`` mt=`介言以及耶和华对以色列的责备` mno=1`
- `撒迦利亚书生命读经，第一篇` → clean=`撒迦利亚书生命读经` frag=`` mt=`介言` mno=1`
- `以弗所书生命读经，第六十一篇` → clean=`以弗所书生命读经` frag=`` mt=`第五章中劝勉的摘要` mno=61`
- `约翰福音生命读经，第一篇` → clean=`约翰福音生命读经` frag=`` mt=`前言` mno=1`
- `约翰福音生命读经，第二篇　生命与建造的` → clean=`约翰福音生命读经` frag=`生命与建造的` mt=`引言（一）` mno=2`

## 不同对照（needs_review 候选）

## 密钥泄露检查：通过（内存比对）

