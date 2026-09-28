# 3.5 图谱盘点

本报告由 `back_mic/backend/panai4/graph/inventory_35.py` 生成。对 3.5 只执行了 MATCH / SHOW，经 `execute_read` 提交。报告不含密码。

- 连接地址：`bolt://localhost:7687`
- 用户：`neo4j`
- 服务器：Neo4j/5.26.28

## 1. 节点标签

节点总数：**2588**

| 标签组合 | 数量 |
|---|---:|
| Scripture | 1493 |
| Concept | 1095 |

## 2. 关系类型

关系总数：**44429**（有向，按起点→终点计数）

| 关系类型 | 数量 |
|---|---:|
| CONTAINS | 6360 |
| EXPERIENCES | 8210 |
| LEADS_TO | 14912 |
| LOCATED_IN | 600 |
| OPPOSES | 3638 |
| PRACTICED_AS | 7914 |
| SUPPORTED_BY | 2795 |

| 关系类型 | 起点标签 | 终点标签 | 数量 |
|---|---|---|---:|
| CONTAINS | Concept | Concept | 6360 |
| EXPERIENCES | Concept | Concept | 8210 |
| LEADS_TO | Concept | Concept | 14912 |
| LOCATED_IN | Concept | Concept | 600 |
| OPPOSES | Concept | Concept | 3638 |
| PRACTICED_AS | Concept | Concept | 7914 |
| SUPPORTED_BY | Concept | Scripture | 2795 |

关系上的标注键：

- 所有关系都没有标注。

## 3. Concept 与 Scripture 的标注键

「有值」指不是 null、不是空字符串、不是空列表。

### Concept

| 标注 | 出现该键的节点数 | 其中有值的节点数 |
|---|---:|---:|
| greek_terms | 1046 | 1046 |
| name | 1095 | 1095 |

### Scripture

Scripture 的正文不拉回本地。下表来自库内聚合。「有值」已排除 null 和空字符串。

| 标注 | 出现该键的节点数 | 其中有值的节点数 |
|---|---:|---:|
| id | 1493 | 1493 |
| text | 1493 | 1493 |

## 4. Concept.name

- 节点数：**1095**
- 不同 name：**1095**
- name 为空（null）：**0**
- name 为空白字符串：**0**
- 重复的 name：**0** → 通过
- 首尾有空格或全角空格：**0**
- （无）
- 含半角括号 `()`：**0**
- （无）
- 含全角括号 `（）`：**0**
- （无）
- 全角与半角括号混用：**0**
- （无）
- 内部含连续空格或全角空格：**0**
- （无）

库内约束（SHOW CONSTRAINTS，只读）：

- 没有约束。name 的唯一性只来自数据，没有数据库约束。

库内索引（SHOW INDEXES，只读）：

- index_343aff4e：type=LOOKUP，entity=NODE，labels=None，properties=None
- index_f7700477：type=LOOKUP，entity=RELATIONSHIP，labels=None，properties=None

## 5. Scripture.id

- 节点数：**1493**
- 不同 id：**1493**
- id 为空（null）：**0**
- id 为空白字符串：**0**
- 重复的 id：**0** → 通过
- 首尾有空格：**0**
- （无）

## 6. 迁移预估（只读，未写入）

依据 `docs/panai4_graph/concept_mapping_35_to_40.csv`。
Concept 一端：处理方式为「一致」或「改名」视为能对应，新名用 CSV 的「新名」；「删除」和「未归类」不能对应。
Scripture 一端：全部保留，身份用 `id`（本库 Scripture 不在删除名单里）。
「会重复」指两端都对应上之后，同一关系类型、同一新起点、同一新终点出现多于一次。下表「会重复的关系数」是多出来的条数（每组保留 1 条后的余数），不是组数。

| 关系类型 | 3.5 原有 | 两端都能对应 | 因某一端被删除而舍弃 | 无法判定 | 会重复的关系数 | 重复组数 |
|---|---:|---:|---:|---:|---:|---:|
| CONTAINS | 6360 | 5977 | 383 | 0 | 0 | 0 |
| EXPERIENCES | 8210 | 7725 | 485 | 0 | 0 | 0 |
| LEADS_TO | 14912 | 14140 | 772 | 0 | 0 | 0 |
| LOCATED_IN | 600 | 528 | 72 | 0 | 0 | 0 |
| OPPOSES | 3638 | 3372 | 266 | 0 | 0 | 0 |
| PRACTICED_AS | 7914 | 7431 | 483 | 0 | 0 | 0 |
| SUPPORTED_BY | 2795 | 2686 | 109 | 0 | 0 | 0 |

## 7. neo4j-v4 连接测试

- 连接地址：`bolt://localhost:7688`
- 用户：`neo4j`
- 能否连上：**能**
- Neo4j 版本：Neo4j/5.26.28
- 现有节点数：**2483**
- 现有关系数：**45699**

