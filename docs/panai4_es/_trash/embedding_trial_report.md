# 纲目 embedding 试跑

## 1. 环境变量

只读 `back_mic/backend/.env`，不记录变量值。

- OPENROUTER_API_KEY：存在
- EMBEDDING_KG_MODEL：存在
- EMBEDDING_KG_DIMS：存在

## 2. 调用方式

- 模型：`qwen/qwen3-embedding-8b`
- 适配层：`kg_rag/embedding_adapter.py`，`profile="kg_rag"`
- 请求的维度参数：1024
- 批大小：50
- embedding 输入：`message_title + 换行 + text`，只在请求里临时拼接，不写回 chunks。

## 3. 试跑结果

### 抽样

种子 20260929。同一个 `random.Random` 先抽 A 批再抽 B 批。
每批定额：<150 抽 16 条，150~800 抽 17 条，>800 抽 17 条。
某一档不够就全取，差额按 150~800、<150、>800 的顺序从还有剩余的档补。

| 批次 | 篇档条数 <150 / 150~800 / >800 | 实际抽到 |
|---|---|---|
| A | 19091 / 35655 / 1095 | 16 / 17 / 17（共 50） |
| B | 3192 / 7124 / 794 | 16 / 17 / 17（共 50） |

### 常规 100 条

#### A 批 50 条

- 条数：50
- 耗时：3.18 秒
- usage：prompt_tokens=26837，total_tokens=26837，cost=0.00026837，is_byok=False
- 返回维度：1024
- 报错：无

#### B 批 50 条

- 条数：50
- 耗时：4.80 秒
- usage：prompt_tokens=31169，total_tokens=31169，cost=0.00031169，is_byok=False
- 返回维度：1024
- 报错：无

### 最长的一条

方案里的「约 5,653」是切块前的估算。这里按 chunks 里的 `tokens` 字段取最大。

#### A 批

- message_key：`gm12490/2 李常受文集纲目/32 李常受文集一九五九年第四册/5 圣经纲领/msg. 1 旧约`
- 估算 tokens 字段：6436
- embedding 输入字符数：9657
- 耗时：5.51 秒
- usage：prompt_tokens=7618，total_tokens=7618，cost=7.618e-05，is_byok=False
- 返回维度：1024
- 报错：无

#### B 批

- message_key：`gmfeasts/2022-05 秋季长老训练/02/msg. 2 雅歌—个别信徒与基督爱的交通中进展的经历，为着预备基督的新妇`
- 估算 tokens 字段：2433
- embedding 输入字符数：3681
- 耗时：5.08 秒
- usage：prompt_tokens=2836，total_tokens=2836，cost=2.836e-05，is_byok=False
- 返回维度：1024
- 报错：无

### 边界检查

按 chunks 里的 `tokens` 字段，统计大于阈值的条数。

| 阈值 | A 批 | B 批 |
|---:|---:|---:|
| >2000 | 24 | 5 |
| >4000 | 5 | 0 |
| >8000 | 0 | 0 |

最长条都成功，没有测到拒绝上限，因此不另计「超过实测上限」的条数。

## 4. 结论

OpenRouter 接受了两批各自最长的一条。单条输入限制不低于这次最长的 embedding 输入：A 批 9657 字符（tokens 字段 6436），B 批 3681 字符（tokens 字段 2433）。
这个长度已经覆盖两批里最长的 chunk。两次调用都返回了向量，没有拒绝，所以没有更紧的失败上限。

## 5. 全量推算

全量 66951 条（A 55841 + B 11110）。单价按 OpenRouter 模型页标价 $0.01/百万 token。
全量 embedding 输入的估算 token（`int(len(message_title + 换行 + text) / 1.5)`）合计 18089550。
这次接口返回的 prompt_tokens 合计 68460，相对上述估算的比例是 1.155。按这个比例放大后的全量 token 约 20896860。
试跑这几次调用的标价成本约 $0.0007。
全量标价成本约 $0.21。
两次 50 条调用耗时 3.18 秒和 4.80 秒，平均 3.99 秒/批。
全量按每批 50 条、共 1340 批、不另加批间等待，约 89 分钟。

## 6. trial_vectors.json

- 条数：102
- 字节：2341931

## 7. chunks 文件

| 文件 | 试跑前 | 试跑后 |
|---|---:|---:|
| chunks_12490.json | 112068348 | 112068348 |
| chunks_feasts.json | 25043462 | 25043462 |

两个 chunks 文件的字节数在试跑前后一致。

返回了向量的条目，维度都是 1024。
