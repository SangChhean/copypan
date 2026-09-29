# KG-RAG 全量语料 Chunking 方案 v7（执行完成）

> **日期：** 2026-03-26
> **状态：** ✅ 全部完成（chunking + 建索引 + embedding 生成 + 检索适配）
> **原始方案版本：** v6（2026-03-25），v7 新增三个 map 类数据源
> **v7 变更：**
> - 新增三个数据源：map_7feasts / map_pano / map_dictionary
> - `extract_scripture_refs` 新增破折号模式（`_DASH_REF_RE`），与括号模式合并去重，兼容纲目类经文引用格式
> - 三个新函数均添加 doc_id 去重（源数据有重复 ID，自动追加 `_d2/_d3` 后缀）
> - 总索引从 6 个扩展为 9 个，总 chunks 从 285,375 增至 378,598

---

## 一、数据源

### 1.1 文件位置

```
输入目录：E:\12490_with_bib\
输出目录：E:\12490_with_bib\

输入文件：life.json, cwwl.json, cwwn.json, others.json, bib.json, map_note.json,
          map_7feasts.json, map_pano.json, map_dictionary.json
输出文件：kg-rag_{life,cwwl,cwwn,others,bib,map_note,7feasts,pano,dictionary}_chunks.json
```

### 1.2 数据规模

| 文件 | 大小 | 总文档数 | 进入 chunking 的数量 |
|------|------|---------|---------------------|
| life.json | 950 MB | 79,924 | 55,024（text 类型） |
| cwwl.json | 3.2 GB | 319,753 | ~257,000（text 类型，估算） |
| cwwn.json | 707 MB | 53,082 | 40,356（text 类型） |
| others.json | 373 MB | 34,776 | 21,479（text 类型） |
| bib.json | 40 MB | ~40,000 | ~40,000（全部，无 type 字段） |
| map_note.json | 28 MB | 3,500 docs / 89,668 msg | 16,000（ot1 段落数） |
| map_7feasts.json | 41 MB | 2,538 | 12,529（ot1 段落数） |
| map_pano.json | 186 MB | 16,111 | 68,964（ot1 段落数） |
| map_dictionary.json | 26 MB | 1,852 | 14,893（ot1 段落数） |

### 1.3 原始 text 段落 Token 分布

| 索引 | text 数 | min | max | avg | median |
|------|--------|-----|-----|-----|--------|
| life | 55,024 | 1 | 716 | 108.8 | 97 |
| cwwn | 39,923 | 0 | 1,792 | 132.1 | 114 |
| others | 21,479 | 1 | 1,280 | 107.3 | 99 |
| cwwl | ~257,000 | 未测 | 未测 | ~110（估算） | ~100（估算） |
| map_note（按 ot1 合并后） | 16,000 | 5 | 1,386 | 245.7 | 225 |
| map_7feasts（按 ot1 合并后） | 12,529 | — | — | 469 | — |
| map_pano（按 ot1 合并后，合并前） | 68,964 | — | 1,818 | 40（单条ot） | — |
| map_dictionary（按 ot1 合并后） | 14,893 | — | — | 212 | — |

### 1.4 原始 JSON 格式

**职事类（life / cwwl / cwwn / others）统一格式：**

```json
{
  "id": "life_60-12-25",
  "text": "中文正文...",
  "zh": "（与 text 相同，跳过）",
  "en": "English text...",
  "title": "彼得前书生命读经，第十二篇　三一神完全的救恩及其结果（七）",
  "type": "text",
  "tags": [["查看整篇", "life_60-12"], ["只看标题", "life_60-12-heading"]],
  "source": ["（彼得前书生命读经，第十二篇，第二十四段）", "(Life-study of 1 Peter, msg. 12)"],
  "embedding": [512 维旧向量，跳过]
}
```

**bib 格式：**

```json
{
  "id": "bib_23-18-3",
  "text": "世上一切的居民...",
  "zh": "（与 text 相同，跳过）",
  "en": "All you inhabitants...",
  "title": "圣经，以赛亚书，第十八章",
  "order": 18001,
  "tags": [["查看整章", "bib_23-18"]],
  "source": ["（圣经恢复本，赛十八3）", "(Holy Bible Recovery Version, Isa. 18:3)"],
  "_id": "bib_23-18-3"
}
```

**map_note 格式（嵌套结构）：**

```json
{
  "index": ["map_note"],
  "id": "map_note_75-1-1",
  "text": "第一篇　更美之约",
  "source": "圣经真理题库，第一系列　圣经—神的话，旧约与新约的关联",
  "msg": [
    { "text": "圣经真理题库", "type": "bookname" },
    { "text": "第一篇　更美之约", "type": "title" },
    { "text": "读经：可十四24...", "type": "b_read" },
    { "text": "壹　奴仆救主...", "type": "ot1", "source": "（恢复本圣经，可十四24，注1）" },
    { "text": "一　神在出埃及记...", "type": "ot2", "source": "（恢复本圣经，可十四24，注1）" }
  ]
}
```

**map_7feasts 格式（嵌套结构，source 在顶层）：**

```json
{
  "index": ["map_7feasts"],
  "id": "map_7feasts_1997-02-1",
  "text": "第一篇 使徒们生活的最高点—活出新耶路撒冷(一)(复合的纲目)",
  "source": "1997年春季长老训练，第一篇",
  "sn": 1,
  "msg": [
    { "text": "一九九七年春季长老训练", "type": "bookname" },
    { "text": "第一篇 使徒们生活的最高点...", "type": "title" },
    { "text": "读经：启二一2...", "type": "b_read" },
    { "text": "序言 我们需要被带到使徒生活的这最高点...", "type": "ot1" },
    { "text": "一 在新耶路撒冷里...", "type": "ot2" },
    { "text": "1 使徒的教训...", "type": "ot3" }
  ]
}
```

**map_pano 格式（嵌套结构，source 在顶层和各 msg 条目）：**

```json
{
  "index": ["map_pano"],
  "id": "map_pano-1-1",
  "text": "第一篇 圣经的本质",
  "source": "圣经—神的话，第一系列 圣经，壹　介绍",
  "sn": 1,
  "msg": [
    { "text": "圣经—神的话", "type": "bookname" },
    { "text": "第一篇 圣经的本质", "type": "title" },
    { "text": "读经：提后三16...", "type": "b_read" },
    { "text": "壹 圣经的来源...", "type": "ot1", "source": "真理课程—第一级（卷一），第一课" },
    { "text": "一 圣经是神的呼出...", "type": "ot2", "source": "真理课程—第一级（卷一），第一课" }
  ]
}
```

**map_dictionary 格式（嵌套结构，无顶层 source，有 a/b 分册后缀）：**

```json
{
  "index": ["map_dictionary"],
  "id": "map_dictionary-1-a",
  "text": "爱",
  "sn": 1,
  "msg": [
    { "text": "主恢复真理的词典", "type": "bookname" },
    { "text": "3a　职事信息的鸟瞰", "type": "bookname" },
    { "text": "爱", "type": "title" },
    { "text": "读经：约三16...", "type": "b_read" },
    { "text": "壹 神是爱的神...", "type": "ot1", "source": "（李常受文集一九三二至一九四九年第一册，...）" },
    { "text": "一 神预定我们...", "type": "ot2", "source": "（李常受文集一九九四至一九九七年第五册，...）" }
  ]
}
```

### 1.5 跳过的字段

所有索引统一跳过：`embedding`（512 维旧向量）、`zh`（与 text 相同）、`tags`（message_key 已覆盖）

### 1.6 ID 格式

```
life:           life_{书号}-{篇号}-{段序号}                  例: life_60-12-25
cwwl:           cwwl_{年份}-{册号}-{书序号}#{章号}-{段序号}    例: cwwl_1963-1-10#4-13
cwwn:           cwwn_{辑号}-{册号}#{篇号}-{段序号}            例: cwwn_2-21#11-16
others:         others_{系列标识}_{篇号}-{段序号}             例: others_1_138-29
bib:            bib_{书号}-{章号}-{节号}                     例: bib_23-18-3
map_note:       map_note_{系列号}-{组号}-{篇序号}             例: map_note_75-1-1
map_7feasts:    map_7feasts_{年份}-{月份}-{篇序号}            例: map_7feasts_1997-02-1
map_pano:       map_pano-{系列号}-{篇序号}                   例: map_pano-1-1
map_dictionary: map_dictionary-{数字}-{a或b}                例: map_dictionary-1-a
```

---

## 二、输出 Mapping

每条 chunk 记录共 **17 个字段**（不含后续生成的 embedding）：

| 字段 | 类型 | 说明 |
|------|------|------|
| chunk_id | string | 主键 |
| text | string | 中文正文 |
| en | string | 英文正文（合并段落时拼接；map 类留空） |
| book_title | string | 书名 |
| author | string | 作者 |
| year | int \| null | 出版年份（cwwl 从 id 提取，其他留空） |
| message_key | string | 篇/章唯一标识（如 life_60-12） |
| message_number | int | 篇号/章号 |
| message_title | string | 篇/章标题 |
| section_title | string \| null | 小节标题（从 heading 收集；map 类为 null） |
| paragraph_type | string | "text" / "verse"（bib） / "note"（map 类） |
| scripture_refs | list[string] | 经节引用（括号内 + 破折号后正则提取，合并去重） |
| source_zh | string | 中文出处 |
| source_en | string | 英文出处（map 类留空） |
| tokens | int | token 估算（len(text) / 1.5） |
| original_ids | list[string] | 合并前的原始 id 列表 |

---

## 三、Type 处理规则

### 3.1 统一规则

**只有 type="text" 的文档进入 chunking，其余全部跳过。**

- bib 无 type 字段，全部进入 chunking。
- map 类（map_note / 7feasts / pano / dictionary）是嵌套结构，按 ot1 分组合并（见第四节）。

### 3.2 各索引 type 清单

| 索引 | 进入 chunking 的 type | 跳过的 type |
|------|----------------------|------------|
| life | text | title, heading |
| cwwl | text | title, heading, heading_1~4, preface_heading |
| cwwn | text | title, heading（部分有前导空格，需 trim） |
| others | text | title, heading, heading_2, bookname, bible_reading, ot1, ot2, ot3 |
| bib | 全部（无 type 字段） | — |
| map_note | ot1 + 下属 ot2/ot3/ot4 | bookname, title, b_read |
| map_7feasts | ot1 + 下属 ot2/ot3/ot4/ot5/ot6/otn | bookname, title, b_read |
| map_pano | ot1 + 下属 ot2/ot3/ot4/ot5/ot6/ot7/otn | bookname, title, b_read |
| map_dictionary | ot1 + 下属 ot2/ot3/ot4/ot5 | bookname, title, b_read |

### 3.3 Heading 判断逻辑（职事类）

```python
doc_type = doc.get("type", "").strip()
is_heading = "heading" in doc_type or doc_type == "preface_heading"
is_title = doc_type == "title"
is_text = doc_type == "text"
# 其余 type（bookname, bible_reading, ot1, ot2, ot3）直接跳过
```

heading 的 text 内容记入 section_title，供后续 text 段落使用。多级 heading 时取最近的一个（后面覆盖前面）。

---

## 四、Chunking 策略

### 4.1 职事类（life / cwwl / cwwn / others）

#### 分组与排序

1. 从 id 解析分组键（按篇/章分组）
2. **组内按段序号升序排列，所有数字必须转为 int 排序**

**各索引分组键和排序键：**

```
life:
  id: life_60-12-25
  分组键: "life_60-12"（书号-篇号）
  排序键: (60, 12, 25) 全部 int
  message_key: "life_60-12"
  message_number: 12

cwwl:
  id: cwwl_1963-1-10#4-13
  分组键: "cwwl_1963-1-10#4"（年份-册号-书序号#章号）
  排序键: (1963, 1, 10, 4, 13) 全部 int
  message_key: "cwwl_1963-1-10#4"
  message_number: 4
  year: 1963

cwwn:
  id: cwwn_2-21#11-16
  分组键: "cwwn_2-21#11"（辑号-册号#篇号）
  排序键: (2, 21, 11, 16) 全部 int
  message_key: "cwwn_2-21#11"
  message_number: 11

others:
  id 以最后一个 _ 分割，前面是系列标识，后面是 {篇号}-{段序号}
  id: others_1_138-29 → 分组键 "others_1_138"，message_number=138，段序号=29
  id: others_2-1_1-3  → 分组键 "others_2-1_1"，message_number=1，段序号=3
  排序键: 段序号 int
```

#### Chunking 参数

| 参数 | 值 |
|------|---|
| 合并阈值 | < 150 tokens |
| 拆分阈值 | > 800 tokens |
| Token 估算 | len(text) / 1.5 |
| 拆分断句标点 | 。！？； |

#### Chunking 规则

1. 排序后按顺序遍历每组内的文档
2. title 类型 → 跳过
3. heading 类型 → 跳过正文，text 记入当前 section_title
4. 其他非 text 类型 → 跳过
5. text 类型 → 进入合并/拆分逻辑：
   - 当前段 tokens < 150 → 累积到缓冲区，继续
   - 当前段 tokens ≥ 150 且 ≤ 800 → 如果缓冲区非空，先 flush 缓冲区为一个 chunk；当前段独立成一个 chunk
   - 当前段 tokens > 800 → flush 缓冲区；按标点断句拆分当前段
   - 遇到 heading → flush 缓冲区（不跨 heading 边界合并）
   - 组结束 → flush 缓冲区
6. 合并段落时：text 拼接、en 拼接、original_ids 记录所有原始 id
7. 拆分段落时：chunk_id 加 _p1/_p2 后缀

#### chunk_id 规则（职事类）

| 情况 | chunk_id |
|------|---------|
| 单段落（未合并未拆分） | 沿用原始 id |
| 合并段落 | 取首段 id |
| 拆分段落 | 原始 id + "_p1", "_p2"... |

### 4.2 bib（圣经）

| 参数 | 值 |
|------|---|
| 合并目标区间 | 150-300 tokens |
| 合并上限 | 当前累计 + 下一节 > 300 时切为一个 chunk |
| 不跨章 | 章末不足 150 tokens 也独立成 chunk |
| 不拆分单节 | 单节 > 300 tokens 独立成 chunk |

**bib 分组与排序：**
```
id: bib_23-18-3
分组键: "bib_23-18"（书号-章号）
排序键: (23, 18, 3) 全部 int
message_key: "bib_23-18"
message_number: 18
```

**bib chunk_id：** `bib_{书号}-{章号}-{起始节号}_{结束节号}`
- 多节合并：bib_23-18-3_7（赛十八3-7）
- 单节 chunk：bib_23-18-3_3

**bib 合并时：** text 拼接、en 拼接、original_ids 记录所有原始 id、source_zh 取首节

### 4.3 map_note（注解纲目）

#### 数据结构

每个 doc 包含一个 msg 数组，msg 条目有 type：bookname / title / b_read / ot1 / ot2 / ot3 / ot4。

#### Chunking 规则

1. 遍历 doc 的 msg 数组
2. bookname → 跳过（用于解析 book_title）
3. title → 跳过（用于解析 message_title）
4. b_read → 跳过
5. ot1 → 开始新的 chunk：flush 之前的缓冲区，将 ot1 text 写入新缓冲区
6. ot2 / ot3 / ot4 → 追加到当前缓冲区（拼接到当前 ot1 的 chunk）
7. doc 结束 → flush 缓冲区

**即：每个 ot1 + 其下属 ot2/ot3/ot4 合并为一个 chunk，不跨 ot1 合并。**

#### 超长和极短处理

| 区间 | 数量 | 占比 | 处理 |
|------|------|------|------|
| < 150 tokens | 3,952 | 24.7% | 保持原样（独立语义单元，不跨 ot1 合并） |
| 150-800 tokens | 11,996 | 75% | 正常 chunk |
| > 800 tokens | 52 | 0.3% | 按标点拆分（同职事类） |

#### chunk_id 规则（map_note）

```
doc id: map_note_75-1-1
该 doc 有 3 个 ot1 → 生成 3 个 chunk:

chunk_id: map_note_75-1-1_c1   （第 1 个 ot1 + 下属）
chunk_id: map_note_75-1-1_c2   （第 2 个 ot1 + 下属）
chunk_id: map_note_75-1-1_c3   （第 3 个 ot1 + 下属）

超长拆分时：map_note_75-1-1_c1_p1, map_note_75-1-1_c1_p2
```

### 4.4 map_7feasts（节期特会纲目）

#### 数据特点

- type 清单：bookname / title / b_read / ot1 / ot2 / ot3 / ot4 / ot5 / ot6 / otn
- ot5/ot6/otn 与 ot2/ot3/ot4 性质相同，均为正文内容，追加到缓冲区
- source 在顶层 doc，不在 msg 条目里
- 全部 doc 的顶层 source 均非 null

#### Chunking 规则

与 map_note 一致，**不跨 ot1 合并**：
1. ot1 → flush 缓冲区，开始新 chunk
2. ot2 / ot3 / ot4 / ot5 / ot6 / otn → 追加到当前缓冲区
3. bookname / title / b_read → 跳过
4. 合并后 > 800 tokens → 按 `。！？；` 断句拆分，加 `_p1/_p2`

#### Token 分布

| 区间 | 数量 | 占比 |
|------|------|------|
| < 150 tokens | 2,323 | 18.5% |
| 150-800 tokens | 8,167 | 65.1% |
| > 800 tokens | 2,039 | 16.3% |
| avg tokens | — | 394 |

超长比例较高（16.3%），原因是纲目层级深、下属条目多，单个 ot1 本身平均只有 36 tokens。

#### 字段解析

| 字段 | 来源 |
|------|------|
| chunk_id | doc_id + _c{序号}，超长加 _p1/_p2 |
| book_title | doc.source 逗号前部分，如 `"1997年春季长老训练"` |
| author | 固定 `"李常受"` |
| year | null |
| message_key | doc_id 最后一个 `-` 前，如 `"map_7feasts_1997-02"` |
| message_number | doc_id 最后一段数字转 int |
| message_title | doc.text |
| section_title | null |
| paragraph_type | `"note"` |
| source_zh | doc.source 完整字符串 |
| source_en | `""` |
| en | `""` |
| original_ids | `[doc_id]` |

### 4.5 map_pano（全景鸟瞰真理课程）

#### 数据特点

- type 清单：bookname / title / b_read / ot1 / ot2 / ot3 / ot4 / ot5 / ot6 / ot7 / otn
- source 同时存在于顶层 doc 和各 msg 条目（两者是不同信息）
- 顶层 doc.source = 书名路径（用于 book_title）
- msg 条目 source = 具体来源出处（用于 source_zh）
- 2,959 个 ot1 的 source 为 null（约 4.3%）
- author 需动态解析（含"倪柝声"的约占 8.9%）

#### Chunking 规则（跨 ot1 合并）

与其他 map 类不同，map_pano 因短 chunk 比例高（63.9%），**采用跨 ot1 合并策略**：

1. ot1 处理逻辑：
   - 若当前缓冲区 tokens < 150 → **不 flush**，将新 ot1 追加到当前缓冲区（跨 ot1 合并）
   - 若当前缓冲区 tokens ≥ 150 → flush 当前缓冲区，开始新 chunk
2. ot2 / ot3 / ot4 / ot5 / ot6 / ot7 / otn → 追加到当前缓冲区
3. bookname / title / b_read → 跳过
4. doc 结束 → flush 缓冲区（不跨 doc 边界合并）
5. 合并后 > 800 tokens → 按 `。！？；` 断句拆分，加 `_p1/_p2`

#### Token 分布（合并前 ot1 粒度）

| 区间 | 数量 | 占比 |
|------|------|------|
| < 150 tokens | 88,089 | 63.9% |
| 150-800 tokens | 47,417 | 34.4% |
| > 800 tokens | 2,422 | 1.8% |
| avg tokens | — | 171 |

#### 字段解析

| 字段 | 来源 |
|------|------|
| chunk_id | doc_id + _c{最终chunk序号}，超长加 _p1/_p2 |
| book_title | doc.source 完整字符串，如 `"圣经—神的话，第一系列 圣经，壹　介绍"` |
| author | 动态：首个 ot1.source 含"倪柝声"→`"倪柝声"`，否则→`"李常受"`，null→`"李常受"` |
| year | null |
| message_key | doc_id 最后一个 `-` 前，如 `"map_pano-1"` |
| message_number | doc_id 最后一段数字转 int |
| message_title | doc.text |
| section_title | null |
| paragraph_type | `"note"` |
| source_zh | 首个 ot1.source（可 null） |
| source_en | `""` |
| en | `""` |
| original_ids | `[doc_id]` |

### 4.6 map_dictionary（主恢复真理词典）

#### 数据特点

- type 清单：bookname / title / b_read / ot1 / ot2 / ot3 / ot4 / ot5
- 每个 doc 固定 2 个 bookname：第一个是 `"主恢复真理的词典"`，第二个区分 a/b 分册
- ID 后缀有 a 和 b 两种，同一数字的 a/b 是同一词条的不同分册，各自独立处理
- 顶层 doc.source 全部为 null，book_title 从 msg 的 bookname 拼接
- ot1.source 带全角括号，如 `"（李常受文集...）"`，存入时去掉外层括号
- author 需动态解析（含"倪柝声"的约占 3%）

#### Chunking 规则

与 map_note 一致，**不跨 ot1 合并**（词典每个 ot1 是独立的神学词条论点）：
1. ot1 → flush 缓冲区，开始新 chunk
2. ot2 / ot3 / ot4 / ot5 → 追加到当前缓冲区
3. bookname / title / b_read → 跳过
4. 合并后 > 800 tokens → 按 `。！？；` 断句拆分，加 `_p1/_p2`

#### Token 分布

| 区间 | 数量 | 占比 |
|------|------|------|
| < 150 tokens | 4,765 | 32% |
| 150-800 tokens | 10,073 | 67.6% |
| > 800 tokens | 55 | 0.4% |
| avg tokens | — | 212 |

#### 字段解析

| 字段 | 来源 |
|------|------|
| chunk_id | doc_id + _c{序号}，超长加 _p1/_p2 |
| book_title | msg 中两个 bookname 拼接，如 `"主恢复真理的词典，3a　职事信息的鸟瞰"` |
| author | 动态：ot1.source 含"倪柝声"→`"倪柝声"`，否则→`"李常受"`，null→`"李常受"` |
| year | null |
| message_key | 完整 doc_id，如 `"map_dictionary-1-a"`（保留 a/b 后缀） |
| message_number | doc_id 中间数字转 int，如 `1` |
| message_title | doc.text（词条名，如 `"爱"`） |
| section_title | null |
| paragraph_type | `"note"` |
| source_zh | ot1.source 去掉外层全角括号 `strip('（）')`（可 null） |
| source_en | `""` |
| en | `""` |
| original_ids | `[doc_id]` |

---

## 五、元数据解析

### 5.1 title 切分规则（book_title / message_title）—— 职事类专用

**两层解析策略：**

**第一层：正则匹配（覆盖 ~95% 的文档）**

在 title 中找最后一个匹配的位置，该位置之前为 book_title，该位置起为 message_title：

```python
import re

# 主模式：篇/章/题/课/问/期
pattern_main = r'第[一二三四五六七八九十百零〇\d]+[篇题课章问期]'

# 特殊标识
pattern_special = r'(介言|附录|自序|序|说明|引言|内容提要|前言|开头的话)'

# 优先用 pattern_main，找最后一个匹配
matches = list(re.finditer(pattern_main, title))
if matches:
    pos = matches[-1].start()
    book_title = title[:pos].rstrip('，').rstrip()
    message_title = title[pos:]
elif re.search(pattern_special, title):
    match = re.search(pattern_special, title)
    pos = match.start()
    book_title = title[:pos].rstrip('，').rstrip()
    message_title = title[pos:]
else:
    # 兜底
    ...
```

**第二层：兜底（正则全不匹配时）**

```python
if '，' in title:
    parts = title.split('，', 1)
    book_title = parts[0]
    message_title = parts[1]
else:
    book_title = title
    message_title = ""
```

**各索引匹配率：**

| 索引 | 总 title 数 | 正则匹配 | 兜底 |
|------|-----------|---------|------|
| life | ~1,984 | ~1,983 (99.9%) | 1 |
| cwwl | ~5,000 | ~4,960 (99.2%) | ~40 |
| cwwn | 1,432 | ~1,017 (71%) | ~415 |
| others | ~500 | 500 (100%) | 0 |

### 5.2 各索引字段解析汇总

**life：**

| 字段 | 来源 |
|------|------|
| book_title | title 切分 |
| author | 固定 "李常受" |
| year | null |
| message_key | 从 id 去掉段序号："life_60-12" |
| message_number | 从 id 取篇号：12 |
| message_title | title 切分 |
| source_zh | source[0] |
| source_en | source[1] |

**cwwl：**

| 字段 | 来源 |
|------|------|
| book_title | title 切分 |
| author | 固定 "李常受" |
| year | 从 id 取年份：1963 |
| message_key | 从 id 去掉段序号："cwwl_1963-1-10#4" |
| message_number | 从 id 取 # 后章号：4 |
| message_title | title 切分 |
| source_zh | source[0] |
| source_en | source[1] |

**cwwn：**

| 字段 | 来源 |
|------|------|
| book_title | title 切分 |
| author | 固定 "倪柝声" |
| year | null |
| message_key | 从 id 去掉段序号："cwwn_2-21#11" |
| message_number | 从 id 取 # 后篇号：11 |
| message_title | title 切分 |
| source_zh | source[0] |
| source_en | source[1] |

**others：**

| 字段 | 来源 |
|------|------|
| book_title | title 切分 |
| author | 固定 "李常受" |
| year | null |
| message_key | 从 id 以最后一个 _ 分割取前部分："others_1_138" |
| message_number | 从 id 取篇号：138 |
| message_title | title 切分 |
| source_zh | source[0] |
| source_en | source[1] |

**bib：**

| 字段 | 来源 |
|------|------|
| book_title | 从 title 解析书名（"圣经，{书名}，第X章" → 书名） |
| author | 固定 "圣经" |
| year | null |
| message_key | "bib_{书号}-{章号}"，如 "bib_23-18" |
| message_number | 从 id 取章号：18 |
| message_title | 从 title 取章标题，如 "第十八章" |
| paragraph_type | 固定 "verse" |
| chunk_id | bib_{书号}-{章号}-{起始节号}_{结束节号} |
| source_zh | 首节 source[0] |
| source_en | 首节 source[1] |

**map_note：**

| 字段 | 来源 |
|------|------|
| book_title | doc.source（书名路径） |
| author | 固定 "李常受" |
| year | null |
| message_key | doc id 去掉末尾篇序号，如 "map_note_75-1" |
| message_number | doc id 最后一段数字 |
| message_title | doc.text（篇标题） |
| paragraph_type | 固定 "note" |
| chunk_id | doc_id + "_c{ot1序号}" |
| source_zh | ot1 的 source 字段 |
| source_en | 留空 "" |
| en | 留空 "" |

**map_7feasts：** 详见 4.4 节字段解析表

**map_pano：** 详见 4.5 节字段解析表

**map_dictionary：** 详见 4.6 节字段解析表

### 5.3 scripture_refs 提取

从 text 中提取经节引用，**两种模式合并去重**（v7 新增破折号模式）：

```python
BOOK_NAMES = [
    "创", "出", "利", "民", "申", "书", "士", "得", "撒上", "撒下",
    "王上", "王下", "代上", "代下", "拉", "尼", "斯", "伯", "诗",
    "箴", "传", "歌", "赛", "耶", "哀", "结", "但", "何", "珥",
    "摩", "俄", "拿", "弥", "鸿", "哈", "番", "该", "亚", "玛",
    "太", "可", "路", "约", "徒", "罗", "林前", "林后", "加", "弗",
    "腓", "西", "帖前", "帖后", "提前", "提后", "多", "门", "来",
    "雅", "彼前", "彼后", "约壹", "约贰", "约叁", "犹", "启"
]

# 模式1：括号内经节（职事类为主）
_BRACKET_REF_RE = r'[（(]([^）)]*?(?:' + '|'.join(BOOK_NAMES) + r')[^）)]*?)[）)]'

# 模式2：破折号后经节（纲目类为主）
_DASH_REF_RE = r'[—－]([^—－\n]*?(?:' + '|'.join(BOOK_NAMES) + r')[^—－\n]*?)(?=$|\n|。|；)'

def extract_scripture_refs(text):
    bracket_refs = re.findall(_BRACKET_REF_RE, text)
    dash_refs = re.findall(_DASH_REF_RE, text)
    all_refs = bracket_refs + dash_refs
    return list(dict.fromkeys(all_refs))  # 去重保序
```

---

## 六、特殊处理事项

### 6.1 cwwl.json 内存问题

cwwl.json 有 3.2 GB，不能用 `json.load()` 一次性加载。使用逐行读取 `_iter_cwwl_lines()` + `json.loads`（ijson 因含异常数据持续崩溃）。

### 6.2 cwwn heading 前导空格

cwwn 部分 heading 的 type 字段有前导空格（" heading"），解析时需先 `strip()`。

### 6.3 cwwn title 数据重复

部分 cwwn 的 title 字段内容重复（同一段文字出现两遍），不影响 chunking（title 类型跳过），但 book_title 解析时如果用兜底逻辑需注意。

### 6.4 排序必须用 int

从 id 解析出的所有数字部分必须转为 int 排序。字符串排序会导致 1, 11, 12, 2, 3...

### 6.5 others 的 ID 格式变体

others 的 id 有两种格式，以**最后一个 `_`** 分割：
```
others_1_138-29      → 系列标识="1", 篇号=138, 段序号=29
others_2-1_1-3       → 系列标识="2-1", 篇号=1, 段序号=3
```

### 6.6 空段和极短段处理

有 0-1 token 的段落（空段或单字符），合并时跳过或直接并入相邻段落。

### 6.7 map_note 的 ot1 source 可能为空

部分 ot1 可能没有 source 字段，source_zh 留空。

### 6.8 map 类数据源的 scripture_refs 提取

map 类（7feasts/pano/dictionary）纲目格式的经节引用在破折号后，如 `—约五39，提后三15`，括号模式无法匹配。v7 新增 `_DASH_REF_RE` 正则模式与括号模式并用，结果合并去重后存入 scripture_refs。

### 6.9 map_7feasts 的 ot5/ot6/otn

map_7feasts 比 map_note 多了 ot5、ot6、otn 三种 type，均为正文内容（更深层缩进或引用注释），追加到当前 ot1 缓冲区即可，处理逻辑与 ot2/ot3/ot4 完全一致。

### 6.10 map_pano 超长 chunk 边界情况

map_pano 有 2 条单句无标点的超长 chunk（max=1,440 tokens），`split_by_punctuation` 无法再拆，属预期行为。将来上下文扩展实现后不影响使用。

### 6.11 map_dictionary 的 a/b 后缀

`map_dictionary-1-a` 和 `map_dictionary-1-b` 是同一词条"爱"在不同分册（3a 职事信息鸟瞰 / 3b 节期纲目鸟瞰）的独立文档，message_key 需保留完整 doc_id（含 a/b 后缀），不能去掉后缀合并。

### 6.12 map 类 doc_id 重复处理

源数据中存在重复 ID，三个新函数均添加 doc_id 去重逻辑：发现重复时自动追加 `_d2/_d3` 后缀，确保 chunk_id 全局唯一。

---

## 七、执行计划

### 7.1 脚本

```
更新：back_mic/backend/kg_rag/scripts/chunking_full.py
新增函数：process_7feasts / process_pano / process_dictionary
更新函数：extract_scripture_refs（新增破折号模式）
新增 --source 参数值：7feasts / pano / dictionary
```

### 7.2 命令行接口

```bash
# 原有六个索引（同 v6，略）

# 新增三个索引
python -m kg_rag.scripts.chunking_full ^
  --input "E:\12490_with_bib\map_7feasts.json" ^
  --output "E:\12490_with_bib\kg-rag_7feasts_chunks.json" ^
  --source 7feasts

python -m kg_rag.scripts.chunking_full ^
  --input "E:\12490_with_bib\map_dictionary.json" ^
  --output "E:\12490_with_bib\kg-rag_dictionary_chunks.json" ^
  --source dictionary

python -m kg_rag.scripts.chunking_full ^
  --input "E:\12490_with_bib\map_pano.json" ^
  --output "E:\12490_with_bib\kg-rag_pano_chunks.json" ^
  --source pano
```

### 7.3 执行顺序

```
原有六个索引：life → cwwn → others → bib → map_note → cwwl
新增三个索引：dictionary → 7feasts → pano（从小到大验证）
```

### 7.4 验证要点

每个索引 chunking 完成后检查：
- chunk 总数是否合理
- token 分布（min / max / avg / median）
- book_title 覆盖率 ~100%
- message_key 和 message_number 正确性
- scripture_refs 提取合理性（map 类应有破折号模式命中）
- duplicate chunk_id = 0
- 空 token=0 的 chunk 数 = 0
- 抽样检查一条合并 chunk 和一条拆分 chunk 的完整 JSON

### 7.5 实际产出（执行结果）

| 索引 | 预估 chunk 数 | 实际 chunk 数 | ES docs | avg tokens | 状态 |
|------|-------------|-------------|---------|------------|------|
| life | ~28,000 | 39,463 | 39,463 | 151.9 | ✅ |
| cwwl | ~115,000 | 178,107 | 178,107 | 155.2 | ✅ |
| cwwn | ~19,000 | 32,033 | 32,032 | 164.7 | ✅（过滤 1 条 token=0） |
| others | ~12,500 | 15,481 | 15,481 | 149.0 | ✅ |
| bib | ~8,000 | 4,239 | 4,239 | 174.3 | ✅ |
| map_note | ~16,000 | 16,052 | 16,052 | 244.9 | ✅ |
| 7feasts | ~12,500 | 14,925 | 14,925 | 394 | ✅ |
| pano | ~70,000-90,000 | 63,333 | 63,333 | 328 | ✅（2条单句超长属预期） |
| dictionary | ~14,893 | 14,966 | 14,966 | 210 | ✅ |
| **合计** | **~285,893** | **378,599** | **378,598** | | ✅ |

**实际 vs 预估差异说明：**
- life / cwwl / cwwn / others 实际 chunk 数比预估多 ~40%，因为 heading 密度高导致更多 flush
- bib 实际比预估少，因为很多短章合并后只产生 1-2 个 chunk
- 7feasts 实际比预估多，因为源数据有重复 ID 导致文档数实际更多
- pano 实际比预估少，跨 ot1 合并效果好，短 chunk 合并充分
- dictionary 与预估基本吻合，超长拆分后略增

**Embedding 生成（v7 新增三个索引）：**
- 三个索引 1024 维 embedding 全部生成完毕，覆盖率 100%
- dictionary（14,966 条）+ 7feasts（14,925 条）+ pano（63,333 条）= 93,224 条
- kNN 验证：查询"基督如何作信徒的生命"，新索引 top-5 全部来自 kg-rag_pano，最高 score=0.8635

**ES 索引总大小：** ~573 MB（原 416 MB + 新增 157 MB）

### 7.6 执行中遇到的问题与解决方案

| 问题 | 解决方案 |
|------|---------|
| cwwl.json（3.2 GB）ijson 流式解析持续崩溃 | 改用逐行读取 `_iter_cwwl_lines()` + `json.loads` |
| life.json 的 heading/title 集中在文件后半段，与 text 不交错 | 改为两遍扫描：Pass 1 收集 heading 映射，Pass 2 处理 text |
| cwwn 部分 heading 的 type 有前导空格（" heading"） | type 字段先 `.strip()` |
| cwwn 有 1 条 token=0 的空 chunk（单字"八"） | 建索引时过滤 `tokens==0` 的 chunk |
| `generate_embeddings.py` 的 `es.search(size=10000)` 无法一次处理大索引 | 改为 scroll API 全量处理 |
| 本地快照（5.5 GB）SCP 上传服务器极慢（~20 KB/s） | 待解决：压缩 chunks JSON 传服务器重跑，或找更好的传输方式 |
| map 类源数据存在重复 doc_id | 三个新函数统一添加 doc_id 去重，重复时追加 `_d2/_d3` 后缀 |
| map_pano 有 2 条单句无标点超长 chunk（max=1,440） | 属预期边界情况，`split_by_punctuation` 无法再拆，保持原样 |

---

## 附录：已知九个数据源处理规则速查

| 数据源 | 类型 | 策略 | author | paragraph_type | 特殊处理 |
|--------|------|------|--------|----------------|---------|
| life | 职事类 | 合并+拆分 | 李常受 | text | 两遍扫描 |
| cwwl | 职事类 | 合并+拆分 | 李常受 | text | 逐行读取（3.2GB）、year 从 id 提取 |
| cwwn | 职事类 | 合并+拆分 | 倪柝声 | text | type 前导空格需 trim |
| others | 职事类 | 合并+拆分 | 李常受 | text | 9 种 type、ID 变体格式 |
| bib | 经文类 | 经节合并 150-300 | 圣经 | verse | 无 type 字段、无 embedding |
| map_note | 纲目类 | ot1分组，不跨ot1合并 | 李常受 | note | 嵌套结构、无 en |
| 7feasts | 纲目类 | ot1分组，不跨ot1合并 | 李常受 | note | ot5/ot6/otn 追加；source_zh 取顶层 doc.source |
| pano | 纲目类 | 跨ot1合并（<150tokens） | 动态（含倪柝声→倪柝声） | note | ot5/ot6/ot7/otn 追加；book_title 取完整 doc.source；source_zh 取 ot1.source |
| dictionary | 纲目类 | ot1分组，不跨ot1合并 | 动态（含倪柝声→倪柝声） | note | a/b后缀保留进message_key；source_zh去全角括号；book_title拼接两个bookname |

---

*方案版本：v7 (执行完成) | 2026-03-26*
