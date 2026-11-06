# neo4j-v4 导入前只读盘点报告

生成时间：2026-11-06 16:48:57；脚本：`panai4.graph.inventory_v4_pre`。只读 Cypher；未运行 `build_v4.py`；未打印密码。

## 摘要（供主设计师过目）

1. **现有图谱**：节点 Truth_Point=2381 / Trunk=12 / Branch=91，合计 2484；关系按类型 {'BELONGS_TO_TRUNK': 2381, 'CONTAINS': 5977, 'EXPERIENCES': 7725, 'GRAFTING': 91, 'LEADS_TO': 14140, 'LOCATED_IN': 528, 'OF_BRANCH_DIRECTLY': 2381, 'OF_BRANCH_INDIRECTLY': 1676, 'OPPOSES': 3372, 'PRACTICED_AS': 7431}，合计 45702；节点标注主要为 `name`（+ Truth_Point 的 `same_as`×8）。
2. **旧 6 种**：合计 39173；明细 LEADS_TO=14140（括号内端点152，自环0，重复对0）；EXPERIENCES=7725（括号内端点41，自环0，重复对0）；PRACTICED_AS=7431（括号内端点51，自环0，重复对0）；CONTAINS=5977（括号内端点29，自环0，重复对0）；OPPOSES=3372（括号内端点53，自环0，重复对0）；LOCATED_IN=528（括号内端点3，自环0，重复对0）；孤立 Truth_Point=0。
3. **删旧 6 种后预期**：关系剩 6529（分类 6529 + 其他 0）；分类四型 {'BELONGS_TO_TRUNK': 2381, 'OF_BRANCH_DIRECTLY': 2381, 'OF_BRANCH_INDIRECTLY': 1676, 'GRAFTING': 91}；每个 TP 有 BELONGS_TO_TRUNK=2381/2381，OF_BRANCH_DIRECTLY=2381/2381。
4. **代码依赖**：连接 neo4j-v4 的文件 ['back_mic/backend/panai4/graph/README.md', 'back_mic/backend/panai4/graph/build_v4.py', 'back_mic/backend/panai4/graph/inventory_35.py', 'back_mic/backend/panai4/graph/inventory_v4_pre.py', 'back_mic/backend/panai4/sc/stage1.py', 'docs/PanAI4.0_新系统框架实施方案.md', 'docs/panai4_es/archive/es_inventory_35.md', 'docs/panai4_graph/neo4j_v4_inventory_pre.md', 'docs/panai4_graph/reports/35_inventory.md', 'docs/panai4_graph/reports/build_v4_report.md', 'docs/panai4_graph/reports/build_v4_report_dry_run.md']；在线/工具向读取 v4 的非建图文件 ['back_mic/backend/panai4/sc/stage1.py']；其中读取旧 6 种类型名的在线命中 0 条；kg_rag 读 v4 命中 0。结论：删除旧 6 种**不会**让当前在线服务因查询这些类型而报错（见 B2）。
5. **可导入资料**：文件 8 个、45767983 字节；关系 JSON 类型数=29、边数=35902；与现有对照：同名精确 ['CONTAINS', 'LEADS_TO', 'LOCATED_IN', 'PRACTICED_AS']；旧6重制映射 {'EXPERIENCES': ['EXPERIENCES / ENJOYS'], 'PRACTICED_AS': ['PRACTICED_AS'], 'CONTAINS': ['CONTAINS'], 'OPPOSES': ['OPPOSES / CONTRASTS_WITH'], 'LEADS_TO': ['LEADS_TO'], 'LOCATED_IN': ['LOCATED_IN']}；**目录内未见独立「一般标注」JSON**（一般性标注在桌面其他目录，见 C6）。
6. **节点匹配**：关系端点检查 found=71608 missing=196；括号内节点名出现=0，括号外节点名出现=0，未拆分的「外（内）」合并名出现=194（合并名无法直接匹配图谱拆开后的节点）。
7. **标注 JSON 覆盖**：特殊标注/【high_peak_content】从历史进展的差异看高峰时期的内涵.json: 记录87 匹配87 缺0；特殊标注/【intrinsic_significance】2372词条内在意义分类.json: 记录2372 匹配2363 缺9；特殊标注/【mutuality】彼此互相.json: 记录116 匹配116 缺0；特殊标注/【organic_advance】生机关联的进展.json: 记录69 匹配69 缺0；防火墙/【devine_argument】越进入高峰，真理越需要辨明得准确.json: 记录189 匹配189 缺0。
8. **待主设计师决定**：见文末「问题清单」（类型名含 `/`、括号内端点、找不到节点、同名重制方向、多值标注存放、一般标注 JSON 缺失等）。

## A. 图谱现状

### A1 连接
- 连通：是；用户变量 `NEO4J_V4_USER`；URI 变量 `NEO4J_V4_URI`（值不打印）。
- 数据库名：`neo4j`
- 组件：`[{"name": "Neo4j Kernel", "versions": ["5.26.28"], "edition": "community"}]`
- docker ps：`neo4j-v4	Up 8 hours	neo4j:5.26.28	0.0.0.0:7475->7474/tcp, [::]:7475->7474/tcp, 0.0.0.0:7688->7687/tcp, [::]:7688->7687/tcp`

### A2 节点按标签
| 标签 | 数量 |
|---|---:|
| Branch | 91 |
| Trunk | 12 |
| Truth_Point | 2381 |
| （标签计数之和） | 2484 |

### A3 节点标注
#### Truth_Point
- name 非空 2381/2381；name 去重 2381；无重复。
| 标注名 | 有该键的节点 | 非空 |
|---|---:|---:|
| name | 2381 | 2381 |
| same_as | 8 | 8 |

#### Trunk
- name 非空 12/12；name 去重 12；无重复。
| 标注名 | 有该键的节点 | 非空 |
|---|---:|---:|
| name | 12 | 12 |

#### Branch
- name 非空 91/91；name 去重 91；无重复。
| 标注名 | 有该键的节点 | 非空 |
|---|---:|---:|
| name | 91 | 91 |

#### same_as（8）
说明：下表「持有 same_as 的节点」= 括号内；`same_as` 指向名 = 括号外。与 2373 词表 `括号外（括号内）` 拆分一致。
| 括号内名（持有 same_as） | same_as → 括号外 | 括号外节点存在 |
|---|---|---|
| 产生得胜者 | 产生男孩子 | True |
| 圣灵的浇灌 | 那灵的浇灌 | True |
| 地狱 | 火湖 | True |
| 女人 | 妇人 | True |
| 忧虑 | 挂虑 | True |
| 扩展 | 扩增 | True |
| 显大 | 扩大 | True |
| 晨兴 | 晨晨复兴 | True |
- 对照词表合并名：产生男孩子（产生得胜者）, 晨晨复兴（晨兴）, 妇人（女人）, 挂虑（忧虑）, 火湖（地狱）, 扩大（显大）, 扩增（扩展）, 那灵的浇灌（圣灵的浇灌）

### A4 关系按类型
| 类型 | 数量 | 起止标签组合 |
|---|---:|---|
| BELONGS_TO_TRUNK | 2381 | Truth_Point→Trunk×2381 |
| CONTAINS | 5977 | Truth_Point→Truth_Point×5977 |
| EXPERIENCES | 7725 | Truth_Point→Truth_Point×7725 |
| GRAFTING | 91 | Branch→Trunk×91 |
| LEADS_TO | 14140 | Truth_Point→Truth_Point×14140 |
| LOCATED_IN | 528 | Truth_Point→Truth_Point×528 |
| OF_BRANCH_DIRECTLY | 2381 | Truth_Point→Branch×2381 |
| OF_BRANCH_INDIRECTLY | 1676 | Truth_Point→Branch×1676 |
| OPPOSES | 3372 | Truth_Point→Truth_Point×3372 |
| PRACTICED_AS | 7431 | Truth_Point→Truth_Point×7431 |
| 合计 | 45702 | |
- 全部类型：['BELONGS_TO_TRUNK', 'CONTAINS', 'EXPERIENCES', 'GRAFTING', 'LEADS_TO', 'LOCATED_IN', 'OF_BRANCH_DIRECTLY', 'OF_BRANCH_INDIRECTLY', 'OPPOSES', 'PRACTICED_AS']

### A5 关系上的标注
- `BELONGS_TO_TRUNK`：无关系标注（keys 为空）
- `CONTAINS`：无关系标注（keys 为空）
- `EXPERIENCES`：无关系标注（keys 为空）
- `GRAFTING`：无关系标注（keys 为空）
- `LEADS_TO`：无关系标注（keys 为空）
- `LOCATED_IN`：无关系标注（keys 为空）
- `OF_BRANCH_DIRECTLY`：无关系标注（keys 为空）
- `OF_BRANCH_INDIRECTLY`：无关系标注（keys 为空）
- `OPPOSES`：无关系标注（keys 为空）
- `PRACTICED_AS`：无关系标注（keys 为空）

### A6 旧 6 种明细
| 类型 | 数量 | 两端皆 Truth_Point | 涉及 same_as 节点 | 自环 | 重复(起点,终点)对数 | 重复多余边 |
|---|---:|---:|---:|---:|---:|---:|
| LEADS_TO | 14140 | 14140 | 152 | 0 | 0 | 0 |
| EXPERIENCES | 7725 | 7725 | 41 | 0 | 0 | 0 |
| PRACTICED_AS | 7431 | 7431 | 51 | 0 | 0 | 0 |
| CONTAINS | 5977 | 5977 | 29 | 0 | 0 | 0 |
| OPPOSES | 3372 | 3372 | 53 | 0 | 0 | 0 |
| LOCATED_IN | 528 | 528 | 3 | 0 | 0 | 0 |
- 旧 6 种合计：**39173**
- 孤立 Truth_Point（无任何关系）：**0**

### A7 删除预演（未删）
- 分类关系合计：6529 → {'BELONGS_TO_TRUNK': 2381, 'OF_BRANCH_DIRECTLY': 2381, 'OF_BRANCH_INDIRECTLY': 1676, 'GRAFTING': 91}
- 旧 6 种合计：39173
- 其他类型：无
- 删除后剩余关系：6529
- 校验：分类+旧6+其他 = 6529+39173+0 =? 关系总数 45702
- BELONGS_TO_TRUNK：{'points': 2381, 'has_belong': 2381, 'exactly_one': 2381, 'missing': 0}
- OF_BRANCH_DIRECTLY：{'points': 2381, 'has_direct': 2381, 'exactly_one': 2381, 'missing': 0}
- 仅分类关系预览：{'only_class_after_delete': 2381, 'no_class_no_other': 0, 'points': 2381}
- 括号内外分类是否一致：
| outer | inner | trunk_eq | direct_eq | indirect_eq |
|---|---|---|---|---|
| 产生男孩子 | 产生得胜者 | True | True | True |
| 晨晨复兴 | 晨兴 | True | True | True |
| 妇人 | 女人 | True | True | True |
| 挂虑 | 忧虑 | True | True | True |
| 火湖 | 地狱 | True | True | True |
| 扩大 | 显大 | True | True | True |
| 扩增 | 扩展 | True | True | True |
| 那灵的浇灌 | 圣灵的浇灌 | True | True | True |

### A8 约束与索引
#### CONSTRAINTS
```json
[
  {
    "id": 8,
    "name": "branch_name",
    "type": "UNIQUENESS",
    "entityType": "NODE",
    "labelsOrTypes": [
      "Branch"
    ],
    "properties": [
      "name"
    ],
    "ownedIndex": "branch_name",
    "propertyType": null
  },
  {
    "id": 6,
    "name": "trunk_name",
    "type": "UNIQUENESS",
    "entityType": "NODE",
    "labelsOrTypes": [
      "Trunk"
    ],
    "properties": [
      "name"
    ],
    "ownedIndex": "trunk_name",
    "propertyType": null
  },
  {
    "id": 4,
    "name": "truth_point_name",
    "type": "UNIQUENESS",
    "entityType": "NODE",
    "labelsOrTypes": [
      "Truth_Point"
    ],
    "properties": [
      "name"
    ],
    "ownedIndex": "truth_point_name",
    "propertyType": null
  }
]
```
#### INDEXES
```json
[
  {
    "id": 7,
    "name": "branch_name",
    "state": "ONLINE",
    "populationPercent": 100.0,
    "type": "RANGE",
    "entityType": "NODE",
    "labelsOrTypes": [
      "Branch"
    ],
    "properties": [
      "name"
    ],
    "indexProvider": "range-1.0",
    "owningConstraint": "branch_name",
    "lastRead": "2026-10-02T01:59:53.562000000+00:00",
    "readCount": 37890
  },
  {
    "id": 1,
    "name": "index_343aff4e",
    "state": "ONLINE",
    "populationPercent": 100.0,
    "type": "LOOKUP",
    "entityType": "NODE",
    "labelsOrTypes": null,
    "properties": null,
    "indexProvider": "token-lookup-1.0",
    "owningConstraint": null,
    "lastRead": "2026-11-06T09:48:33.655000000+00:00",
    "readCount": 151
  },
  {
    "id": 2,
    "name": "index_f7700477",
    "state": "ONLINE",
    "populationPercent": 100.0,
    "type": "LOOKUP",
    "entityType": "RELATIONSHIP",
    "labelsOrTypes": null,
    "properties": null,
    "indexProvider": "token-lookup-1.0",
    "owningConstraint": null,
    "lastRead": "2026-09-28T04:25:59.895000000+00:00",
    "readCount": 9
  },
  {
    "id": 5,
    "name": "trunk_name",
    "state": "ONLINE",
    "populationPercent": 100.0,
    "type": "RANGE",
    "entityType": "NODE",
    "labelsOrTypes": [
      "Trunk"
    ],
    "properties": [
      "name"
    ],
    "indexProvider": "range-1.0",
    "owningConstraint": "trunk_name",
    "lastRead": "2026-10-02T01:59:53.333000000+00:00",
    "readCount": 19808
  },
  {
    "id": 3,
    "name": "truth_point_name",
    "state": "ONLINE",
    "populationPercent": 100.0,
    "type": "RANGE",
    "entityType": "NODE",
    "labelsOrTypes": [
      "Truth_Point"
    ],
    "properties": [
      "name"
    ],
    "indexProvider": "range-1.0",
    "owningConstraint": "truth_point_name",
    "lastRead": "2026-11-06T09:48:33.658000000+00:00",
    "readCount": 708700
  }
]
```

### A9 规模
- 节点 2484；关系 45702
- 对账：A2 标签和=2484；A4 关系和=45702
- 数据卷：{"mount_names": ["neo4j_v4_data", "neo4j_v4_logs"], "df_lines": ["neo4j_v4_logs                                                      1         765.7kB", "neo4j_v4_data                                                      1         543.2MB"]}

## B. 依赖排查

### B1 命中分类（文件数）
- ①建图脚本：4 个文件 / 124 行
  - `back_mic/backend/panai4/graph/README.md` 行号：3, 16
  - `back_mic/backend/panai4/graph/build_v4.py` 行号：2, 4, 33, 55, 56, 57, 58, 59, 60, 63, 64, 65, 66, 67, 68, 86, 87, 88, 89, 90, 91, 95, 96, 97, 98, 99, 100, 107, 217, 289 …共53
  - `back_mic/backend/panai4/graph/inventory_35.py` 行号：5, 23, 59, 60, 61, 1026, 1029, 1079, 1083, 1084, 1085, 1088, 1135
  - `back_mic/backend/panai4/graph/inventory_v4_pre.py` 行号：2, 4, 27, 35, 36, 37, 38, 39, 40, 119, 120, 121, 122, 126, 127, 128, 135, 203, 204, 216, 480, 515, 516, 517, 518, 519, 520, 521, 523, 525 …共56
- ②测试台或 panai4 的在线服务：3 个文件 / 8 行
  - `back_mic/backend/panai4/inherit/apply_text_life_fix.py` 行号：114
  - `back_mic/backend/panai4/outline/apply_life_fix.py` 行号：159
  - `back_mic/backend/panai4/sc/stage1.py` 行号：25, 223, 224, 225, 227, 228
- ③3.5（kg_rag）：10 个文件 / 64 行
  - `back_mic/backend/kg_rag/neo4j_client.py` 行号：7, 8, 9, 24, 25, 26, 41, 42
  - `back_mic/backend/kg_rag/prompts.py` 行号：259, 261
  - `back_mic/backend/kg_rag/scripts/build_seed_concepts_1.py` 行号：13, 14, 15, 16, 17, 18, 32, 33, 127
  - `back_mic/backend/kg_rag/scripts/export_ik_dict.py` 行号：47, 48, 53, 54, 59, 60, 69, 70
  - `back_mic/backend/kg_rag/scripts/import_concepts.py` 行号：11, 12, 13, 14, 15, 16, 23, 25, 176, 177, 182, 183, 188, 189
  - `back_mic/backend/kg_rag/scripts/merge_batch_relations.py` 行号：8
  - `back_mic/backend/kg_rag/scripts/merge_seed_concepts_1_batch2.py` 行号：20, 21, 22, 23, 24, 25
  - `back_mic/backend/kg_rag/scripts/merge_seed_concepts_1_batch3.py` 行号：13, 14, 15, 16, 17, 18
  - `back_mic/backend/kg_rag/scripts/merge_seed_relations_batch.py` 行号：31, 46, 47, 50, 51
  - `back_mic/backend/kg_rag/scripts/scripture_data/import_scriptures.py` 行号：18, 20, 93, 97, 101
- ⑤其他：10 个文件 / 142 行
  - `back_mic/backend/scripts/build_seed_concepts_from_kg.py` 行号：8, 9, 10, 11, 12, 13
  - `back_qa/DEPLOY.md` 行号：101
  - `back_qa/qa/qa_service.py` 行号：640, 641, 642, 643, 644, 645
  - `back_shared/neo4j_client.py` 行号：6, 7, 8, 20, 21, 22, 30, 31, 164
  - `docs/PanAI4.0_新系统框架实施方案.md` 行号：276, 278, 284, 286, 289, 319, 320, 388
  - `docs/panai4_es/archive/es_inventory_35.md` 行号：1298, 1299
  - `docs/panai4_graph/neo4j_v4_inventory_pre.md` 行号：1, 7, 8, 10, 11, 19, 22, 71, 73, 74, 77, 78, 80, 85, 87, 88, 91, 92, 97, 98, 99, 101, 102, 304, 320, 322, 323, 437, 449, 470 …共65
  - `docs/panai4_graph/reports/35_inventory.md` 行号：5, 25, 26, 27, 28, 29, 35, 36, 37, 38, 39, 113, 114, 115, 116, 117, 120, 122
  - `docs/panai4_graph/reports/build_v4_report.md` 行号：1, 5, 6, 26, 27, 28, 29, 30, 52, 53, 54, 55, 56
  - `docs/panai4_graph/reports/build_v4_report_dry_run.md` 行号：1, 5, 6, 7, 27, 28, 29, 30, 31, 53, 54, 55, 56, 57

### B2 结论
- 会连接 neo4j-v4（`NEO4J_V4_*` / `neo4j-v4` / 7688 / 7475）的文件：
  - `back_mic/backend/panai4/graph/README.md`
  - `back_mic/backend/panai4/graph/build_v4.py`
  - `back_mic/backend/panai4/graph/inventory_35.py`
  - `back_mic/backend/panai4/graph/inventory_v4_pre.py`
  - `back_mic/backend/panai4/sc/stage1.py`
  - `docs/PanAI4.0_新系统框架实施方案.md`
  - `docs/panai4_es/archive/es_inventory_35.md`
  - `docs/panai4_graph/neo4j_v4_inventory_pre.md`
  - `docs/panai4_graph/reports/35_inventory.md`
  - `docs/panai4_graph/reports/build_v4_report.md`
  - `docs/panai4_graph/reports/build_v4_report_dry_run.md`
- 其中偏运行时/工具（排除纯建图脚本与 docs）: ['back_mic/backend/panai4/sc/stage1.py']
- `panai4/sc/stage1.py`：只 `MATCH (n:Truth_Point) RETURN n.name`，**不**读取旧 6 种关系类型。
- `build_v4.py` / `inventory_35.py`：建图与盘点；`build_v4` 会 MERGE 旧 6 种，但本轮不运行。
- 在线功能读取旧 6 种类型名的命中数：0
- **删除旧 6 种关系不会导致当前在线服务报错**：没有在线查询路径依赖 neo4j-v4 上的这些类型；kg_rag 走的是 `NEO4J_URI`（3.5）。

### B3 3.5 是否读 neo4j-v4
- kg_rag 中 NEO4J_V4/neo4j-v4/7688/7475 命中：0 → **无**；3.5 使用 `NEO4J_URI`（默认 bolt://localhost:7687）。

## C. 新 JSON 盘点（可导入资料）

### C0 目录清单
| 相对路径 | 大小 | 修改时间 | 扩展名 |
|---|---:|---|---|
| 29种关系_成立边.json | 2813293 | 2026-11-06 15:02:58 | .json |
| hymns.json | 1341790 | 2026-11-06 11:47:40 | .json |
| 图谱/【relationship】29种关系定义分类.json | 14544 | 2026-11-05 12:05:16 | .json |
| 特殊标注/【high_peak_content】从历史进展的差异看高峰时期的内涵.json | 1331384 | 2026-10-06 12:12:02 | .json |
| 特殊标注/【intrinsic_significance】2372词条内在意义分类.json | 204307 | 2026-11-06 11:26:06 | .json |
| 特殊标注/【mutuality】彼此互相.json | 12049 | 2026-10-06 12:12:03 | .json |
| 特殊标注/【organic_advance】生机关联的进展.json | 38800482 | 2026-10-06 12:11:55 | .json |
| 防火墙/【devine_argument】越进入高峰，真理越需要辨明得准确.json | 1250134 | 2026-10-05 12:25:16 | .json |
- 文件数 8；总字节 45767983
- 目录内是否有「一般」字样文件：False

### 文件：`29种关系_成立边.json`
- 范围：图谱相关
- 大小 2813293；mtime 2026-11-06 15:02:58
- UTF-8 BOM：False；解析成功：True；NaN/Infinity token：False
- 顶层：`{"structure": "list", "n": 29, "item_keys": ["relation", "name", "english", "type", "no", "group", "level", "definition", "count", "pairs"]}`
- 前 3 条（截断）：
```json
[
  {
    "relation": "REVEALS",
    "name": "启示",
    "english": "REVEALS",
    "type": "专特",
    "no": 1,
    "group": "神圣的启示",
    "level": "外在",
    "definition": "启示就是\"揭开帕子\"，启就是打开之意，示就是给人看见；启示就是神打开幔子给人看见一个东西。光与启示是相联的，得着光照就是得着启示。",
    "count": 1385,
    "pairs": [
      {
        "from": "神",
        "to": "基督的奥秘"
      },
      {
        "from": "神",
        "to": "召会的奥秘"
      },
      {
        "from": "神",
        "to": "国度的奥秘"
      },
      "…"
    ]
  },
  {
    "relation": "IN_APPOSITION_WITH / EQUIVALENT_TO",
    "name": "同位／等同",
    "english": "IN_APPOSITION_WITH / EQUIVALENT_TO",
    "type": "专特",
    "no": 2,
    "group": "神圣的启示",
    "level": "外在",
    "definition": "同位或等同，是指圣经把两个名称或两件事并列，说\"就是\"，表明它们是同一个实际；“主的灵”这辞指明那灵和主是彼此并列、同位的。这显示那灵就是主，主就是那灵，并且那…",
    "count": 1189,
    "pairs": [
      {
        "from": "那灵",
        "to": "圣灵"
      },
      {
        "from": "那灵",
        "to": "神的灵"
      },
      {
        "from": "那灵",
        "to": "基督的灵"
      },
      "…"
    ]
  },
  {
    "relation": "TYPIFIES",
    "name": "预表",
    "english": "TYPIFIES",
    "type": "专特",
    "no": 3,
    "group": "神圣的启示",
    "level": "外在",
    "definition": "预表是神用图样预先描写、表明祂新约的真理；这如同幼稚园用图示的方法教儿童一样；预表可以是一个人、一件东西、一件事迹、一种礼节。预表包括两类：",
    "count": 663,
    "pairs": [
      {
        "from": "亚当",
        "to": "基督"
      },
      {
        "from": "亚当",
        "to": "信徒"
      },
      {
        "from": "亚当",
        "to": "肢体"
      },
      "…"
    ]
  }
]
```
- 字段盘点：
| 字段 | 非空 | 空 | distinct | 长度min/med/max | >32000 |
|---|---:|---:|---:|---|---:|
| count | 29 | 0 | 29 | -/-/- | 0 |
  - 取值（≤50）：[{"value": 1385, "count": 1}, {"value": 1189, "count": 1}, {"value": 663, "count": 1}, {"value": 278, "count": 1}, {"value": 196, "count": 1}, {"value": 532, "count": 1}, {"value": 470, "count": 1}, {"value": 2155, "count": 1}, {"value": 1194, "count": 1}, {"value": 1376, "count": 1}, {"value": 1059, "count": 1}, {"value": 929, "count": 1}, {"value": 295, "count": 1}, {"value": 141, "count": 1}, {"value": 7832, "count": 1}, {"value": 3622, "count": 1}, {"value": 451, "count": 1}, {"value": 2174, "count": 1}, {"value": 904, "count": 1}, {"value": 190, "count": 1}, {"value": 226, "count": 1}, {"value": 491, "count": 1}, {"value": 720, "count": 1}, {"value": 728, "count": 1}, {"value": 1048, "count": 1}, {"value": 2742, "count": 1}, {"value": 2044, "count": 1}, {"value": 219, "count": 1}, {"value": 649, "count": 1}]
| definition | 29 | 0 | 29 | 44/87/132 | 0 |
  - 取值（≤50）：[{"value": "启示就是\"揭开帕子\"，启就是打开之意，示就是给人看见；启示就是神打开幔子给人看见一个东西。光与启示是相联的，得着光照就是…", "count": 1}, {"value": "同位或等同，是指圣经把两个名称或两件事并列，说\"就是\"，表明它们是同一个实际；“主的灵”这辞指明那灵和主是彼此并列、同位…", "count": 1}, {"value": "预表是神用图样预先描写、表明祂新约的真理；这如同幼稚园用图示的方法教儿童一样；预表可以是一个人、一件东西、一件事迹、一种…", "count": 1}, {"value": "互相内住是存在、居住于彼此里面。三一神不仅同时存在，并且互相内住；子在父里面，父在子里面。（约十四10～11。）照样，我…", "count": 1}, {"value": "父神具体化身在子里面，而子又实化为那灵。子是三一神的具体化身，而那灵是三一神的终极完成。", "count": 1}, {"value": "“经过过程”是指在神圣经纶里三一神所经过的重要步骤，借着成为肉体、人性生活、钉十字架、复活和升天，三一神就经过了过程，并…", "count": 1}, {"value": "‘成’字的动词，在希腊文里乃是指有目标的举动，意思是说，这不是轻易的举动，乃是有目标的举动，是重大的举动。所以主耶稣有两…", "count": 1}, {"value": "神的分赐是照着神计划和安排的分赐并授与；神的分赐是从神的经纶里所产生出来的，是神经纶的目标：神的分赐就是将基督那追测不尽…", "count": 1}, {"value": "“内住”这辞原文的字根与“家”这字有关。内住的意思是“居住其中”。有一个活的人位，就是包罗万有的灵，内住于我们；这灵就是…", "count": 1}, {"value": "指信徒因为与基督联结，基督所经过的一切，也成了信徒的经历：与祂同死、同埋葬、同复活、同活、同坐、同受苦、同得荣耀、同作王…", "count": 1}, {"value": "介系词“在…里”指的是范围、目前的光景与经历；如在基督里，指在基督的元素与范围里；在基督里、在灵里、在身体里、在神圣奥秘…", "count": 1}, {"value": "我们在生命里与神有神圣的联结；联结可用枝子与葡萄树的联结说明。这不仅是生命的事，也是在生命（神的生命）里的事。联结的因素…", "count": 1}, {"value": "调和乃是将两个或两个以上的东西结合在一起，使原初的元素仍然可以区别。在神的成为肉体里，神性和人性的元素调和成为一个实体，…", "count": 1}, {"value": "神在祂神圣的三一里，乃是一个合并。神圣三一的三者在祂们的所是和所作上，乃是一个合并。“合并”一辞也指明这些人位合并一起以…", "count": 1}, {"value": "经历基督，就是让基督在我们里面活着，并从我们身上活出。享受基督就是将基督接受到我们里面。享受，不是指着人在外面的一种享受…", "count": 1}, {"value": "实行是把一个目标、一个定旨作出来，完成了；指因着住(在一些事里)而习惯且持续的行(那些事)。实行真理乃是习惯的活真理，不…", "count": 1}, {"value": "建造乃是神把祂自己建造到我们里面，又把我们建造到祂里面；也就是神自己与我们调和，将神性与人性调和成为一个建造。", "count": 1}, {"value": "彰显，即给（人）知道；基督是神的丰满，神的彰显；神永远的定旨乃是要得着许多儿子，作祂团体的彰显。", "count": 1}, {"value": "基督的扩展，是借着将祂自己作为生命的种子撒在我们心里，生长并结出许多果子，而得以繁增。召会的扩展，乃是借着主生命的长大和…", "count": 1}, {"value": "“终极完成”一辞的意思是有一个过程，要达到完成或实现。新耶路撒冷乃是神新造工作的终极完成。", "count": 1}, {"value": "一物是另一物的一种。后者是总称，前者是其中一类或一个。前者具备总称的全部本质特征，另有自己的区别特征。例：燔祭是一种祭、…", "count": 1}, {"value": "一物是另一物的一部分。后者是整体，前者是其中的组成部分。部分不具备整体的全部特征，需与其他部分合在一起才构成整体。例：创…", "count": 1}, {"value": "两物在性质、方向或所属上彼此相反，互相排斥或冲突；并列放在一起时，一方使另一方更显明。例：灵与肉体相对、生命与死亡相对。", "count": 1}, {"value": "一物从另一物而出，以之为起源或根源；所出之物带有源头的成分或性质。例：生命水的河从神和羔羊的宝座流出、信徒是从神生的。", "count": 1}, {"value": "一事引起另一事；前者是原因，后者是因前者而生的结果。重在「由什么引起」：果是被因推动出来的，二者有必然的连带，不在乎有没…", "count": 1}, {"value": "一事朝着另一事而去，以之为归宿；前者是行动、过程或手段，后者是它所要达到的目的或终局。重在「为着什么、归向哪里」：目标先…", "count": 1}, {"value": "一个行动如何完成：所凭藉的途径、手段、工具，或所取的样子与状态。重在「怎样作、藉着什么作」，而不在「为什么作」或「为着什…", "count": 1}, {"value": "甲与乙在时间上有先后、同时或所属时期的关系。可以是先后，如成为肉体在复活之先；可以是同时，如重生与得救同时发生；也可以是…", "count": 1}, {"value": "甲发生或存在于乙这个实际的处所，乙是可指出的地方，如一座城、一个建筑、建筑中的一部分。例如约柜在至圣所里，五旬节那灵的浇…", "count": 1}]
| english | 29 | 0 | 29 | 2/10/35 | 0 |
  - 取值（≤50）：[{"value": "REVEALS", "count": 1}, {"value": "IN_APPOSITION_WITH / EQUIVALENT_TO", "count": 1}, {"value": "TYPIFIES", "count": 1}, {"value": "COINHERES_WITH", "count": 1}, {"value": "EMBODIED_IN / REALIZED_AS", "count": 1}, {"value": "PROCESSED_THROUGH", "count": 1}, {"value": "BECOMES", "count": 1}, {"value": "DISPENSED_INTO", "count": 1}, {"value": "INDWELLS", "count": 1}, {"value": "CO_WITH", "count": 1}, {"value": "IN", "count": 1}, {"value": "UNITED_WITH", "count": 1}, {"value": "MINGLED_WITH", "count": 1}, {"value": "INCORPORATED_WITH", "count": 1}, {"value": "EXPERIENCES / ENJOYS", "count": 1}, {"value": "PRACTICED_AS", "count": 1}, {"value": "BUILT_INTO", "count": 1}, {"value": "EXPRESSES", "count": 1}, {"value": "SPREADS", "count": 1}, {"value": "CONSUMMATED_IN", "count": 1}, {"value": "IS_A", "count": 1}, {"value": "CONTAINS", "count": 1}, {"value": "OPPOSES / CONTRASTS_WITH", "count": 1}, {"value": "OUT_OF", "count": 1}, {"value": "CAUSES", "count": 1}, {"value": "LEADS_TO", "count": 1}, {"value": "BY_MEANS_OF", "count": 1}, {"value": "BEFORE / SIMULTANEOUS_WITH / DURING", "count": 1}, {"value": "LOCATED_IN", "count": 1}]
| group | 29 | 0 | 8 | 3/8/11 | 0 |
  - 取值（≤50）：[{"value": "神圣的分赐与神人的调和", "count": 7}, {"value": "三一神的所是与经过过程", "count": 4}, {"value": "神永远经纶的目标", "count": 4}, {"value": "因果过程", "count": 4}, {"value": "神圣的启示", "count": 3}, {"value": "归属比较", "count": 3}, {"value": "经历享受与实行", "count": 2}, {"value": "时空类", "count": 2}]
| level | 29 | 0 | 4 | 2/2/5 | 0 |
  - 取值（≤50）：[{"value": "外在", "count": 13}, {"value": "最内在", "count": 7}, {"value": "内在", "count": 7}, {"value": "显出为外在", "count": 2}]
| name | 29 | 0 | 29 | 2/4/17 | 0 |
  - 取值（≤50）：[{"value": "启示", "count": 1}, {"value": "同位／等同", "count": 1}, {"value": "预表", "count": 1}, {"value": "互相内住", "count": 1}, {"value": "具体化／实化", "count": 1}, {"value": "经过过程", "count": 1}, {"value": "成为", "count": 1}, {"value": "神的分赐", "count": 1}, {"value": "内住", "count": 1}, {"value": "同…（新约的）", "count": 1}, {"value": "在灵里…", "count": 1}, {"value": "联结", "count": 1}, {"value": "调和", "count": 1}, {"value": "合并（Incorporation）", "count": 1}, {"value": "经历/享受", "count": 1}, {"value": "实行", "count": 1}, {"value": "建造（内在的）", "count": 1}, {"value": "彰显", "count": 1}, {"value": "扩展", "count": 1}, {"value": "终极完成", "count": 1}, {"value": "类属", "count": 1}, {"value": "包含", "count": 1}, {"value": "对立/对比", "count": 1}, {"value": "来源／出于", "count": 1}, {"value": "因果", "count": 1}, {"value": "结果/导向/目标", "count": 1}, {"value": "方式", "count": 1}, {"value": "时间", "count": 1}, {"value": "地点/空间", "count": 1}]
| no | 29 | 0 | 20 | -/-/- | 0 |
  - 取值（≤50）：[{"value": 1, "count": 2}, {"value": 2, "count": 2}, {"value": 3, "count": 2}, {"value": 4, "count": 2}, {"value": 5, "count": 2}, {"value": 6, "count": 2}, {"value": 7, "count": 2}, {"value": 8, "count": 2}, {"value": 9, "count": 2}, {"value": 10, "count": 1}, {"value": 11, "count": 1}, {"value": 12, "count": 1}, {"value": 13, "count": 1}, {"value": 14, "count": 1}, {"value": 15, "count": 1}, {"value": 16, "count": 1}, {"value": 17, "count": 1}, {"value": 18, "count": 1}, {"value": 19, "count": 1}, {"value": 20, "count": 1}]
| pairs | 29 | 0 | 28 | 4484/21310/236830 | 10 |
  - 取值（≤50）：[{"value": "[{\"from\": \"父\", \"to\": \"人\"}, {\"from\": \"父\", \"to\": \"信徒\"}, {\"from…", "count": 2}, {"value": "[{\"from\": \"神\", \"to\": \"基督的奥秘\"}, {\"from\": \"神\", \"to\": \"召会的奥秘\"},…", "count": 1}, {"value": "[{\"from\": \"那灵\", \"to\": \"圣灵\"}, {\"from\": \"那灵\", \"to\": \"神的灵\"}, {\"…", "count": 1}, {"value": "[{\"from\": \"亚当\", \"to\": \"基督\"}, {\"from\": \"亚当\", \"to\": \"信徒\"}, {\"f…", "count": 1}, {"value": "[{\"from\": \"父\", \"to\": \"子\"}, {\"from\": \"父\", \"to\": \"基督\"}, {\"from…", "count": 1}, {"value": "[{\"from\": \"三一神\", \"to\": \"成肉体\"}, {\"from\": \"三一神\", \"to\": \"话成肉体\"}…", "count": 1}, {"value": "[{\"from\": \"基督作为神的话\", \"to\": \"赐生命的灵\"}, {\"from\": \"基督作为神的话\", \"to…", "count": 1}, {"value": "[{\"from\": \"神\", \"to\": \"丰富\"}, {\"from\": \"神\", \"to\": \"丰盛\"}, {\"fro…", "count": 1}, {"value": "[{\"from\": \"那灵\", \"to\": \"信徒\"}, {\"from\": \"那灵\", \"to\": \"圣徒\"}, {\"f…", "count": 1}, {"value": "[{\"from\": \"信徒\", \"to\": \"钉十字架\"}, {\"from\": \"信徒\", \"to\": \"基督的十字架\"…", "count": 1}, {"value": "[{\"from\": \"信徒\", \"to\": \"神\"}, {\"from\": \"信徒\", \"to\": \"三一神\"}, {\"f…", "count": 1}, {"value": "[{\"from\": \"神\", \"to\": \"人的灵\"}, {\"from\": \"神\", \"to\": \"重生的灵\"}, {\"…", "count": 1}, {"value": "[{\"from\": \"基督的神性\", \"to\": \"基督的人性\"}, {\"from\": \"那灵\", \"to\": \"人的灵…", "count": 1}, {"value": "[{\"from\": \"三一神\", \"to\": \"信徒\"}, {\"from\": \"三一神\", \"to\": \"圣徒\"}, {…", "count": 1}, {"value": "[{\"from\": \"信徒\", \"to\": \"神\"}, {\"from\": \"信徒\", \"to\": \"父\"}, {\"fro…", "count": 1}, {"value": "[{\"from\": \"神的经纶\", \"to\": \"传扬福音\"}, {\"from\": \"神的经纶\", \"to\": \"叩门\"…", "count": 1}, {"value": "[{\"from\": \"子\", \"to\": \"父\"}, {\"from\": \"子\", \"to\": \"爱\"}, {\"from\"…", "count": 1}, {"value": "[{\"from\": \"神\", \"to\": \"人性\"}, {\"from\": \"神\", \"to\": \"人的灵\"}, {\"fr…", "count": 1}, {"value": "[{\"from\": \"三一神\", \"to\": \"终极完成的灵\"}, {\"from\": \"三一神\", \"to\": \"赐生命…", "count": 1}, {"value": "[{\"from\": \"燔祭\", \"to\": \"祭物\"}, {\"from\": \"燔祭\", \"to\": \"祭\"}, {\"fr…", "count": 1}, {"value": "[{\"from\": \"旧约\", \"to\": \"摩西五经\"}, {\"from\": \"旧约\", \"to\": \"创世记\"}, …", "count": 1}, {"value": "[{\"from\": \"神\", \"to\": \"撒但\"}, {\"from\": \"神\", \"to\": \"魔鬼\"}, {\"fro…", "count": 1}, {"value": "[{\"from\": \"神的爱\", \"to\": \"神\"}, {\"from\": \"神的爱\", \"to\": \"父\"}, {\"f…", "count": 1}, {"value": "[{\"from\": \"罪\", \"to\": \"死\"}, {\"from\": \"罪\", \"to\": \"定罪\"}, {\"from…", "count": 1}, {"value": "[{\"from\": \"重生\", \"to\": \"模成神儿子的形像\"}, {\"from\": \"重生\", \"to\": \"得荣\"…", "count": 1}, {"value": "[{\"from\": \"得救\", \"to\": \"十字架\"}, {\"from\": \"得救\", \"to\": \"血\"}, {\"f…", "count": 1}, {"value": "[{\"from\": \"成孕\", \"to\": \"童女所生\"}, {\"from\": \"成孕\", \"to\": \"成肉体\"}, …", "count": 1}, {"value": "[{\"from\": \"约柜\", \"to\": \"帐幕\"}, {\"from\": \"约柜\", \"to\": \"会幕\"}, {\"f…", "count": 1}]
| relation | 29 | 0 | 29 | 2/10/35 | 0 |
  - 取值（≤50）：[{"value": "REVEALS", "count": 1}, {"value": "IN_APPOSITION_WITH / EQUIVALENT_TO", "count": 1}, {"value": "TYPIFIES", "count": 1}, {"value": "COINHERES_WITH", "count": 1}, {"value": "EMBODIED_IN / REALIZED_AS", "count": 1}, {"value": "PROCESSED_THROUGH", "count": 1}, {"value": "BECOMES", "count": 1}, {"value": "DISPENSED_INTO", "count": 1}, {"value": "INDWELLS", "count": 1}, {"value": "CO_WITH", "count": 1}, {"value": "IN", "count": 1}, {"value": "UNITED_WITH", "count": 1}, {"value": "MINGLED_WITH", "count": 1}, {"value": "INCORPORATED_WITH", "count": 1}, {"value": "EXPERIENCES / ENJOYS", "count": 1}, {"value": "PRACTICED_AS", "count": 1}, {"value": "BUILT_INTO", "count": 1}, {"value": "EXPRESSES", "count": 1}, {"value": "SPREADS", "count": 1}, {"value": "CONSUMMATED_IN", "count": 1}, {"value": "IS_A", "count": 1}, {"value": "CONTAINS", "count": 1}, {"value": "OPPOSES / CONTRASTS_WITH", "count": 1}, {"value": "OUT_OF", "count": 1}, {"value": "CAUSES", "count": 1}, {"value": "LEADS_TO", "count": 1}, {"value": "BY_MEANS_OF", "count": 1}, {"value": "BEFORE / SIMULTANEOUS_WITH / DURING", "count": 1}, {"value": "LOCATED_IN", "count": 1}]
| type | 29 | 0 | 2 | 2/2/2 | 0 |
  - 取值（≤50）：[{"value": "专特", "count": 20}, {"value": "一般", "count": 9}]
#### C3 关系 JSON 分析
- 类型种数：**29**（预期 29）；边总数 **35902**；count 字段和=35902；pairs 长度和==总数：True
| relation | 中文名 | type | level | count | pairs |
|---|---|---|---|---:|---:|
| REVEALS | 启示 | 专特 | 外在 | 1385 | 1385 |
| IN_APPOSITION_WITH / EQUIVALENT_TO | 同位／等同 | 专特 | 外在 | 1189 | 1189 |
| TYPIFIES | 预表 | 专特 | 外在 | 663 | 663 |
| COINHERES_WITH | 互相内住 | 专特 | 最内在 | 278 | 278 |
| EMBODIED_IN / REALIZED_AS | 具体化／实化 | 专特 | 内在 | 196 | 196 |
| PROCESSED_THROUGH | 经过过程 | 专特 | 最内在 | 532 | 532 |
| BECOMES | 成为 | 专特 | 最内在 | 470 | 470 |
| DISPENSED_INTO | 神的分赐 | 专特 | 内在 | 2155 | 2155 |
| INDWELLS | 内住 | 专特 | 内在 | 1194 | 1194 |
| CO_WITH | 同…（新约的） | 专特 | 内在 | 1376 | 1376 |
| IN | 在灵里… | 专特 | 内在 | 1059 | 1059 |
| UNITED_WITH | 联结 | 专特 | 内在 | 929 | 929 |
| MINGLED_WITH | 调和 | 专特 | 最内在 | 295 | 295 |
| INCORPORATED_WITH | 合并（Incorporation） | 专特 | 最内在 | 141 | 141 |
| EXPERIENCES / ENJOYS | 经历/享受 | 专特 | 内在 | 7832 | 7832 |
| PRACTICED_AS | 实行 | 专特 | 外在 | 3622 | 3622 |
| BUILT_INTO | 建造（内在的） | 专特 | 最内在 | 451 | 451 |
| EXPRESSES | 彰显 | 专特 | 显出为外在 | 2174 | 2174 |
| SPREADS | 扩展 | 专特 | 显出为外在 | 904 | 904 |
| CONSUMMATED_IN | 终极完成 | 专特 | 最内在 | 190 | 190 |
| IS_A | 类属 | 一般 | 外在 | 226 | 226 |
| CONTAINS | 包含 | 一般 | 外在 | 491 | 491 |
| OPPOSES / CONTRASTS_WITH | 对立/对比 | 一般 | 外在 | 720 | 720 |
| OUT_OF | 来源／出于 | 一般 | 外在 | 728 | 728 |
| CAUSES | 因果 | 一般 | 外在 | 1048 | 1048 |
| LEADS_TO | 结果/导向/目标 | 一般 | 外在 | 2742 | 2742 |
| BY_MEANS_OF | 方式 | 一般 | 外在 | 2044 | 2044 |
| BEFORE / SIMULTANEOUS_WITH / DURING | 时间 | 一般 | 外在 | 219 | 219 |
| LOCATED_IN | 地点/空间 | 一般 | 外在 | 649 | 649 |
- 节点表示：pairs[].from / pairs[].to 为节点 name（中文词条名）；方向：有向：from → to；关系标注：pairs 元素仅 from/to，无关系标注字段
- 命名习惯：
  - `REVEALS` simple_ok=True slash=False space=False non_ascii=False
  - `IN_APPOSITION_WITH / EQUIVALENT_TO` simple_ok=False slash=True space=True non_ascii=False
  - `TYPIFIES` simple_ok=True slash=False space=False non_ascii=False
  - `COINHERES_WITH` simple_ok=True slash=False space=False non_ascii=False
  - `EMBODIED_IN / REALIZED_AS` simple_ok=False slash=True space=True non_ascii=False
  - `PROCESSED_THROUGH` simple_ok=True slash=False space=False non_ascii=False
  - `BECOMES` simple_ok=True slash=False space=False non_ascii=False
  - `DISPENSED_INTO` simple_ok=True slash=False space=False non_ascii=False
  - `INDWELLS` simple_ok=True slash=False space=False non_ascii=False
  - `CO_WITH` simple_ok=True slash=False space=False non_ascii=False
  - `IN` simple_ok=True slash=False space=False non_ascii=False
  - `UNITED_WITH` simple_ok=True slash=False space=False non_ascii=False
  - `MINGLED_WITH` simple_ok=True slash=False space=False non_ascii=False
  - `INCORPORATED_WITH` simple_ok=True slash=False space=False non_ascii=False
  - `EXPERIENCES / ENJOYS` simple_ok=False slash=True space=True non_ascii=False
  - `PRACTICED_AS` simple_ok=True slash=False space=False non_ascii=False
  - `BUILT_INTO` simple_ok=True slash=False space=False non_ascii=False
  - `EXPRESSES` simple_ok=True slash=False space=False non_ascii=False
  - `SPREADS` simple_ok=True slash=False space=False non_ascii=False
  - `CONSUMMATED_IN` simple_ok=True slash=False space=False non_ascii=False
  - `IS_A` simple_ok=True slash=False space=False non_ascii=False
  - `CONTAINS` simple_ok=True slash=False space=False non_ascii=False
  - `OPPOSES / CONTRASTS_WITH` simple_ok=False slash=True space=True non_ascii=False
  - `OUT_OF` simple_ok=True slash=False space=False non_ascii=False
  - `CAUSES` simple_ok=True slash=False space=False non_ascii=False
  - `LEADS_TO` simple_ok=True slash=False space=False non_ascii=False
  - `BY_MEANS_OF` simple_ok=True slash=False space=False non_ascii=False
  - `BEFORE / SIMULTANEOUS_WITH / DURING` simple_ok=False slash=True space=True non_ascii=False
  - `LOCATED_IN` simple_ok=True slash=False space=False non_ascii=False
- 与现有 10 种对照：同名精确=['CONTAINS', 'LEADS_TO', 'LOCATED_IN', 'PRACTICED_AS']；旧6重制={'EXPERIENCES': ['EXPERIENCES / ENJOYS'], 'PRACTICED_AS': ['PRACTICED_AS'], 'CONTAINS': ['CONTAINS'], 'OPPOSES': ['OPPOSES / CONTRASTS_WITH'], 'LEADS_TO': ['LEADS_TO'], 'LOCATED_IN': ['LOCATED_IN']}；新增=['REVEALS', 'IN_APPOSITION_WITH / EQUIVALENT_TO', 'TYPIFIES', 'COINHERES_WITH', 'EMBODIED_IN / REALIZED_AS', 'PROCESSED_THROUGH', 'BECOMES', 'DISPENSED_INTO', 'INDWELLS', 'CO_WITH', 'IN', 'UNITED_WITH', 'MINGLED_WITH', 'INCORPORATED_WITH', 'BUILT_INTO', 'EXPRESSES', 'SPREADS', 'CONSUMMATED_IN', 'IS_A', 'OUT_OF', 'CAUSES', 'BY_MEANS_OF', 'BEFORE / SIMULTANEOUS_WITH / DURING']；现有却不在新 JSON=['OF_BRANCH_DIRECTLY', 'OF_BRANCH_INDIRECTLY', 'BELONGS_TO_TRUNK', 'GRAFTING']；与分类四型同名冲突=[]
- 端点匹配：found=71608 missing=196 （按 name 精确；每个 from/to 各计 1 次）
- 找不到的前 50：[{"name": "晨晨复兴（晨兴）", "count": 84}, {"name": "那灵的浇灌（圣灵的浇灌）", "count": 74}, {"name": "火湖（地狱）", "count": 35}, {"name": "路得马丁", "count": 2}, {"name": "挂虑（忧虑）", "count": 1}]
- 括号内节点名出现=0；括号外节点名出现=0；合并名「外（内）」出现=194
- 找不到的端点若全是合并名/外人名，见 missing_top50；合并名清单：['产生男孩子（产生得胜者）', '晨晨复兴（晨兴）', '妇人（女人）', '挂虑（忧虑）', '火湖（地狱）', '扩大（显大）', '扩增（扩展）', '那灵的浇灌（圣灵的浇灌）']
- Trunk 名撞车：{'神的经纶': 200, '基督': 695, '那灵': 573, '神的话': 150, '三一神': 470, '新耶路撒冷': 296, '生命': 233, '管家职分': 62, '主的恢复': 98, '神的分赐': 1}；Branch 名撞车：{'神': 537, '神的经纶': 200, '神新约的经纶': 138, '基督': 695, '从天上来的异象': 89, '神建造的异象': 118, '信徒': 778, '那灵': 573, '三一神': 470, '新耶路撒冷': 296, '召会': 624, '基督的身体': 591, '得胜者': 582, '属灵的争战': 96, '召会的建造': 170, '罪': 52, '人': 123, '基督的复活': 187, '基督的十字架': 25, '基督的再来': 65, '国度': 163, '祷告': 181, '唱诗': 58, '聚会': 193, '召会生活': 129, '传扬福音': 147, '成全圣徒': 119, '初信造就': 25, '高峰的真理': 44, '神命定的路': 85, '新约的职事': 100, '祭司体系的事奉': 59, '身体的事奉': 110, '耶稣的见证': 51, '主的恢复': 98, '成为神一切的丰满': 15, '律法时代': 9, '神的福音': 1, '神的分赐': 1, '神的工作': 1, '生命的交通': 1, '神完整的救恩': 14, '生命的经历': 4, '撒但的混乱': 18, '享受基督': 61, '团体的彰显': 74, '经历基督': 61}
- 自环=0；重复三元组对数=0（多余边 0）；同类型反向对=1
- 与旧 6 种 (起点,终点) 重叠：
| 旧类型 | 新类型名 | 旧对数 | 新对数 | 相同 | 仅新 | 仅旧 |
|---|---|---:|---:|---:|---:|---:|
| EXPERIENCES | ['EXPERIENCES / ENJOYS'] | 7725 | 7832 | 230 | 7602 | 7495 |
| PRACTICED_AS | ['PRACTICED_AS'] | 7431 | 3622 | 297 | 3325 | 7134 |
| CONTAINS | ['CONTAINS'] | 5977 | 491 | 84 | 407 | 5893 |
| OPPOSES | ['OPPOSES / CONTRASTS_WITH'] | 3372 | 720 | 110 | 610 | 3262 |
| LEADS_TO | ['LEADS_TO'] | 14140 | 2742 | 262 | 2480 | 13878 |
| LOCATED_IN | ['LOCATED_IN'] | 528 | 649 | 11 | 638 | 517 |

### 文件：`hymns.json`
- 范围：ES，不属于图谱
- 大小 1341790；mtime 2026-11-06 11:47:40
- UTF-8 BOM：False；解析成功：True；NaN/Infinity token：False
- 顶层：`{"structure": "list", "n": 1299, "item_keys": ["name", "reference", "content"]}`
- 前 2 条字段示例（hymns）：
```json
[
  {
    "name": "诗歌第1首　颂赞三一神─祂的计划",
    "reference": "（英 1　西 1）",
    "content": "一　但愿荣耀归于圣父，并圣子基督，且愿荣耀归于圣灵到永古。\n 二　当我观赏广大创造─神智所制订，我灵受感，立献敬拜，并肃静。\n 三　但是我神，你是深愿：能得有众…"
  },
  {
    "name": "诗歌第2首　颂赞三一神─祂的启示",
    "reference": "（英 2）",
    "content": "一　荣耀、荣耀、荣耀、赞美、崇敬、爱戴！听哪，颂赞声浪，从永世一直澎湃！圣父、圣子、圣灵─神，已启示出来，人人都当向祂俯伏敬拜！\n 二　圣父乃是源头，荣耀、无限…"
  }
]
```

### 文件：`图谱/【relationship】29种关系定义分类.json`
- 范围：图谱相关
- 大小 14544；mtime 2026-11-05 12:05:16
- UTF-8 BOM：False；解析成功：True；NaN/Infinity token：False
- 顶层：`{"structure": "dict", "keys": ["title", "note", "type_summary", "level_summary", "relations"], "nkeys": 5}`
- 键 `title`：{"type": "str", "sample": "29种关系"}
- 键 `note`：{"type": "str", "sample": "说明：\n一、结晶读经的思维逻辑，从29种关系来看：\n结晶读经里20种专特关系与9种一般关系都有讲到，其中20种专特关系是职事信息的特点，在生命读经中都有讲到，结…"}
- 键 `type_summary`：{"type": "dict", "sample": {"专特": 20, "一般": 9}}
- 键 `level_summary`：{"type": "dict", "sample": {"外在": 13, "内在": 7, "最内在": 7, "显出为外在": 2}}
- 键 `relations`：{"type": "list", "n": 29, "item_keys": ["no", "type", "group", "name", "english", "level", "definition"]}
  - 字段统计 keys=['definition', 'english', 'group', 'level', 'name', 'no', 'type']
```json
[
  {
    "no": 1,
    "type": "专特",
    "group": "神圣的启示",
    "name": "启示",
    "english": "REVEALS",
    "level": "外在",
    "definition": "启示就是\"揭开帕子\"，启就是打开之意，示就是给人看见；启示就是神打开幔子给人看见一个东西。光与启示是相联的，得着光照就是得着启示。"
  },
  {
    "no": 2,
    "type": "专特",
    "group": "神圣的启示",
    "name": "同位／等同",
    "english": "IN_APPOSITION_WITH / EQUIVALENT_TO",
    "level": "外在",
    "definition": "同位或等同，是指圣经把两个名称或两件事并列，说\"就是\"，表明它们是同一个实际；“主的灵”这辞指明那灵和主是彼此并列、同位的。这显示那灵就是主，主就是那灵，并且那…"
  },
  {
    "no": 3,
    "type": "专特",
    "group": "神圣的启示",
    "name": "预表",
    "english": "TYPIFIES",
    "level": "外在",
    "definition": "预表是神用图样预先描写、表明祂新约的真理；这如同幼稚园用图示的方法教儿童一样；预表可以是一个人、一件东西、一件事迹、一种礼节。预表包括两类："
  }
]
```

### 文件：`特殊标注/【high_peak_content】从历史进展的差异看高峰时期的内涵.json`
- 范围：图谱相关
- 大小 1331384；mtime 2026-10-06 12:12:02
- UTF-8 BOM：False；解析成功：True；NaN/Infinity token：False
- 顶层：`{"structure": "list", "n": 87, "item_keys": ["name", "series", "stages", "content_1", "content_2", "content_3", "content_4", "content_5", "content_6"]}`
- 前 3 条（截断）：
```json
[
  {
    "name": "神的话",
    "series": "从历史进展的差异看高峰时期的内涵",
    "stages": {
      "content_1": "倪柝声弟兄职事",
      "content_2": "李常受弟兄职事第一阶段（1932-1960）",
      "content_3": "李常受弟兄职事第二阶段（1961-1973）",
      "content_4": "李常受弟兄职事第三阶段（1974-1984）",
      "content_5": "李常受弟兄职事第四阶段（1985-1990）",
      "content_6": "李常受弟兄职事高峰阶段（1991-1997）"
    },
    "content_1": [
      {
        "title": "神的话",
        "outline": "读经：创一1、3，约一1、14、18，六63，西三16，弗六17~18，提后三16，来四12，诗一一九130，徒六7，十二24，十九20，林后三6\n壹　神的话就…"
      }
    ],
    "content_2": [],
    "content_3": [
      {
        "title": "神的话",
        "outline": "读经：创一1、3，约一1、14、18，六63，西三16，弗六17~18，提后三16，来四12，诗一一九130，徒六7，十二24，十九20，林后三6\n二　神话语的…"
      }
    ],
    "content_4": [
      {
        "title": "神的话",
        "outline": "读经：创一1、3，约一1、14、18，六63，西三16，弗六17~18，提后三16，来四12，诗一一九130，徒六7，十二24，十九20，林后三6\n柒　接受神的…"
      }
    ],
    "content_5": [
      {
        "title": "神的话",
        "outline": "读经：创一1、3，约一1、14、18，六63，西三16，弗六17~18，提后三16，来四12，诗一一九130，徒六7，十二24，十九20，林后三6\n贰　我们要认…"
      }
    ],
    "content_6": [
      {
        "title": "神的话",
        "outline": "读经：创一1、3，约一1、14、18，六63，西三16，弗六17~18，提后三16，来四12，诗一一九130，徒六7，十二24，十九20，林后三6\n伍　基督—律…"
      }
    ]
  },
  {
    "name": "圣经",
    "series": "从历史进展的差异看高峰时期的内涵",
    "stages": {
      "content_1": "倪柝声弟兄职事",
      "content_2": "李常受弟兄职事第一阶段（1932-1960）",
      "content_3": "李常受弟兄职事第二阶段（1961-1973）",
      "content_4": "李常受弟兄职事第三阶段（1974-1984）",
      "content_5": "李常受弟兄职事第四阶段（1985-1990）",
      "content_6": "李常受弟兄职事高峰阶段（1991-1997）"
    },
    "content_1": [
      {
        "title": "圣经",
        "outline": "读经：启三1，四7，创一26~27，二9、16~17，太十六18，二八19，约一1、14，弗一9~10、22~23，三9，五32，西三4，启二7，二一2、9~1…"
      }
    ],
    "content_2": [
      {
        "title": "圣经",
        "outline": "读经：启三1，四7，创一26~27，二9、16~17，太十六18，二八19，约一1、14，弗一9~10、22~23，三9，五32，西三4，启二7，二一2、9~1…"
      }
    ],
    "content_3": [
      {
        "title": "圣经",
        "outline": "读经：启三1，四7，创一26~27，二9、16~17，太十六18，二八19，约一1、14，弗一9~10、22~23，三9，五32，西三4，启二7，二一2、9~1…"
      }
    ],
    "content_4": [
      {
        "title": "圣经",
        "outline": "读经：启三1，四7，创一26~27，二9、16~17，太十六18，二八19，约一1、14，弗一9~10、22~23，三9，五32，西三4，启二7，二一2、9~1…"
      }
    ],
    "content_5": [
      {
        "title": "圣经",
        "outline": "读经：启三1，四7，创一26~27，二9、16~17，太十六18，二八19，约一1、14，弗一9~10、22~23，三9，五32，西三4，启二7，二一2、9~1…"
      }
    ],
    "content_6": [
      {
        "title": "圣经",
        "outline": "读经：启三1，四7，创一26~27，二9、16~17，太十六18，二八19，约一1、14，弗一9~10、22~23，三9，五32，西三4，启二7，二一2、9~1…"
      }
    ]
  },
  {
    "name": "结晶意义",
    "series": "从历史进展的差异看高峰时期的内涵",
    "stages": {
      "content_1": "倪柝声弟兄职事",
      "content_2": "李常受弟兄职事第一阶段（1932-1960）",
      "content_3": "李常受弟兄职事第二阶段（1961-1973）",
      "content_4": "李常受弟兄职事第三阶段（1974-1984）",
      "content_5": "李常受弟兄职事第四阶段（1985-1990）",
      "content_6": "李常受弟兄职事高峰阶段（1991-1997）"
    },
    "content_1": [],
    "content_2": [],
    "content_3": [],
    "content_4": [],
    "content_5": [],
    "content_6": [
      {
        "title": "结晶意义",
        "outline": "读经：约一1、14，罗六6，八3下，林前十五45下，加五24，六14下，弗一23，四4~6，腓二7~8，来二14，启二一2，二一19~21，二二17\n壹　我们已…"
      }
    ]
  }
]
```
- 字段盘点：
| 字段 | 非空 | 空 | distinct | 长度min/med/max | >32000 |
|---|---:|---:|---:|---|---:|
| content_1 | 23 | 64 | 24 | 2/2/3614 | 0 |
  - 取值（≤50）：[{"value": "[]", "count": 64}, {"value": "[{\"outline\": \"读经：创一1、3，约一1、14、18，六63，西三16，弗六17~18，提后三16，来四12…", "count": 1}, {"value": "[{\"outline\": \"读经：启三1，四7，创一26~27，二9、16~17，太十六18，二八19，约一1、14，弗…", "count": 1}, {"value": "[{\"outline\": \"读经：创一26，但四26，太二八19~20，启十一15，十九5~6\\n壹　神的权柄是神组织宇…", "count": 1}, {"value": "[{\"outline\": \"读经：创二21，七17，可八31，徒十七31，罗十4，约五39，创十四13，书五2，腓三10…", "count": 1}, {"value": "[{\"outline\": \"读经：诗二7，罗一3~4，四25，弗二15，林后五17，徒五30，腓三10，林后四10~11…", "count": 1}, {"value": "[{\"outline\": \"读经：启十九7，罗十二1~2，太二八19~20，徒二42、46，林前十四26，弗四11~12…", "count": 1}, {"value": "[{\"outline\": \"读经：提前三15，约壹一5、7，约八12，九5，一1、4、14~17，约三21，四23~24…", "count": 1}, {"value": "[{\"outline\": \"读经：约一14、17，四24，六63，十四6、17，十六13，林前十五45，林后三17，罗八…", "count": 1}, {"value": "[{\"outline\": \"读经：西二9，林前十五45，林后三17，约一1、14，三5~6、8，七37~39，弗五18，…", "count": 1}, {"value": "[{\"outline\": \"读经：弗六17，罗五10，太三2，可十六16，罗一16~17，五10、18，徒十三23、38…", "count": 1}, {"value": "[{\"outline\": \"读经：创十五9~21，十七1、10~11，出二四3~8，申二九1，赛四二6，四九8，五四10…", "count": 1}, {"value": "[{\"outline\": \"读经：弗一5、9、11，四7、16，西一18、24，徒八14~25，十23，十九1~7，林前…", "count": 1}, {"value": "[{\"outline\": \"读经：弗一22~23，西二9，约一14~16，弗三8、19，四13，西一19，林后三18\\n…", "count": 1}, {"value": "[{\"outline\": \"读经：太十三31~32，十六18~19，西二2，三4，林前一2，十17，十五45，弗一4~1…", "count": 1}, {"value": "[{\"outline\": \"读经：约三29~30，弗五25~27，启十九7~9，二一2、9，二二17，创二21~23，西…", "count": 1}, {"value": "[{\"outline\": \"读经：启一1~2，五5~7，十二1~5，十四1~5，十五2~4，十九7~8、10、14~19…", "count": 1}, {"value": "[{\"outline\": \"读经：创二10~14，撒下六16，20～23，弗四12，腓二12，三8~14，启二二1\\n肆…", "count": 1}, {"value": "[{\"outline\": \"读经：约壹五14~15，太六9~10，约十五7，十30，西四2，但六10，雅五17，创十八2…", "count": 1}, {"value": "[{\"outline\": \"读经：太十八20，林前十四26，徒二42、46，来十25，弗四16，约四24，罗八4。\\n拾…", "count": 1}, {"value": "[{\"outline\": \"读经：太二八18~19，可十六15~16，路十四23，约十五2、5、16，徒一8，二46~4…", "count": 1}, {"value": "[{\"outline\": \"读经：创四2~8，启二7、11、17、26，三5、12、21，十二5、10~11，十九7，二…", "count": 1}, {"value": "[{\"outline\": \"读经：启二一1~3、9~11、18~23，二二1~5，来十一10，加四26，弗一23，林后五…", "count": 1}, {"value": "[{\"outline\": \"读经：太十六18，弗一23，三11，启一11，二1，三7，徒二42，彼前二5，西一18，启二…", "count": 1}]
| content_2 | 37 | 50 | 38 | 2/2/4484 | 0 |
  - 取值（≤50）：[{"value": "[]", "count": 50}, {"value": "[{\"outline\": \"读经：启三1，四7，创一26~27，二9、16~17，太十六18，二八19，约一1、14，弗…", "count": 1}, {"value": "[{\"outline\": \"读经：彼前一17，二23，四5~6、17~19，彼后二1~3、9，三3~8、10~16\\n叁…", "count": 1}, {"value": "[{\"outline\": \"读经：创一26，但四26，太二八19~20，启十一15，十九5~6\\n一　神所以要祂的儿子得…", "count": 1}, {"value": "[{\"outline\": \"读经：出二八6，利二4，罗八4~6，林前六17，太一16，加二20，腓四13，西三4、11\\…", "count": 1}, {"value": "[{\"outline\": \"读经：太二八19，林后十三14，约十四16~17，二十22，弗三16~17，罗八2、9~11…", "count": 1}, {"value": "[{\"outline\": \"读经：创二四1~67，加三16，利一3~17，来十5~10，约一1、14，十四6，太十六16…", "count": 1}, {"value": "[{\"outline\": \"读经：诗九十2，启一8，出二八2，约一14，来一3，赛四2，七14，九6，十一10，约十二2…", "count": 1}, {"value": "[{\"outline\": \"读经：创二21，七17，可八31，徒十七31，罗十4，约五39，创十四13，书五2，腓三10…", "count": 1}, {"value": "[{\"outline\": \"读经：约壹五12，启二二1~2，西二9，三4，约十四6，罗八2，腓一20~21，创二9，诗三…", "count": 1}, {"value": "[{\"outline\": \"读经：林后五17，西二13，弗二10，约壹五11，路十九1~10，徒十九18~19，约十五4…", "count": 1}, {"value": "[{\"outline\": \"读经：彼前二1~5，弗三16~17，四11~16，西二19，林前三6~7、9，罗十一17、2…", "count": 1}, {"value": "[{\"outline\": \"读经：约壹一1~3，二27，林后十三14，约十五4~5，徒二42，启二二1~2，罗八2、6，…", "count": 1}, {"value": "[{\"outline\": \"读经：启十九7，罗十二1~2，太二八19~20，徒二42、46，林前十四26，弗四11~12…", "count": 1}, {"value": "[{\"outline\": \"读经：提前三15，约壹一5、7，约八12，九5，一1、4、14~17，约三21，四23~24…", "count": 1}, {"value": "[{\"outline\": \"读经：约一14、17，四24，六63，十四6、17，十六13，林前十五45，林后三17，罗八…", "count": 1}, {"value": "[{\"outline\": \"读经：来二17，三12，十23，十一1，弗一13，西一5，约三16，提前一2，诗八九33~3…", "count": 1}, {"value": "[{\"outline\": \"读经：弗六17，罗五10，太三2，可十六16，罗一16~17，五10、18，徒十三23、38…", "count": 1}, {"value": "[{\"outline\": \"读经：创十五9~21，十七1、10~11，出二四3~8，申二九1，赛四二6，四九8，五四10…", "count": 1}, {"value": "[{\"outline\": \"读经：弗一22~23，西二9，约一14~16，弗三8、19，四13，西一19，林后三18\\n…", "count": 1}, {"value": "[{\"outline\": \"读经：太十三31~32，十六18~19，西二2，三4，林前一2，十17，十五45，弗一4~1…", "count": 1}, {"value": "[{\"outline\": \"读经：申三三18，诗四八3，六八28，徒二1~4、41，八1上，十三1上，十四23，二十17…", "count": 1}, {"value": "[{\"outline\": \"读经：弗四16，启二一2，创二八11~12、18~19，约一14，林后三18，约壹三2\\n贰…", "count": 1}, {"value": "[{\"outline\": \"读经：创二8~12，约一1、4、14，十一4~6，彼前二5，弗二22，启二一2、18~21，…", "count": 1}, {"value": "[{\"outline\": \"读经：王上五15~18，八10~11，代下七1~2，启二9，弗二21~22，结四二15~20…", "count": 1}, {"value": "[{\"outline\": \"读经：启一1~2，五5~7，十二1~5，十四1~5，十五2~4，十九7~8、10、14~19…", "count": 1}, {"value": "[{\"outline\": \"读经：徒十七26，四24，但二21、四17，罗八28，启一4、四5，提前三15，但十一32，…", "count": 1}, {"value": "[{\"outline\": \"读经：约壹五14~15，太六9~10，约十五7，十30，西四2，但六10，雅五17，创十八2…", "count": 1}, {"value": "[{\"outline\": \"读经：太十八20，林前十四26，徒二42、46，来十25，弗四16，约四24，罗八4。\\n陆…", "count": 1}, {"value": "[{\"outline\": \"读经：太二八18~19，可十六15~16，路十四23，约十五2、5、16，徒一8，二46~4…", "count": 1}, {"value": "[{\"outline\": \"读经：约九1~41，二一15~17，彼前五2~4，徒二十28~31，帖前二7~11，弗四11…", "count": 1}, {"value": "[{\"outline\": \"读经：弗四8、11~16，王上七13~15，歌一11，徒二20、27、31，林前十四1、26…", "count": 1}, {"value": "[{\"outline\": \"读经：弗六10~20，但十10~21，启十二7~11，林后十3~5，太十六18，罗十四17，…", "count": 1}, {"value": "[{\"outline\": \"读经：创四2~8，启二7、11、17、26，三5、12、21，十二5、10~11，十九7，二…", "count": 1}, {"value": "[{\"outline\": \"读经：创一1、26~28，但七14，太三2，四17，六10、33，可一15，四26，路十七2…", "count": 1}, {"value": "[{\"outline\": \"读经：启二一1~3、9~11、18~23，二二1~5，来十一10，加四26，弗一23，林后五…", "count": 1}, {"value": "[{\"outline\": \"读经：林前十五45，林后三17，西三1，林后十三5，罗八9~10，弗二22，弗三16~17，…", "count": 1}, {"value": "[{\"outline\": \"读经：太十六18，弗一23，三11，启一11，二1，三7，徒二42，彼前二5，西一18，启二…", "count": 1}]
| content_3 | 57 | 30 | 58 | 2/597/8282 | 0 |
| content_4 | 59 | 28 | 60 | 2/452/5737 | 0 |
| content_5 | 66 | 21 | 67 | 2/748/22951 | 0 |
| content_6 | 61 | 26 | 62 | 2/583/5416 | 0 |
| name | 87 | 0 | 87 | 1/4/7 | 0 |
| series | 87 | 0 | 1 | 16/16/16 | 0 |
  - 取值（≤50）：[{"value": "从历史进展的差异看高峰时期的内涵", "count": 87}]
| stages | 87 | 0 | 1 | 219/219/219 | 0 |
  - 取值（≤50）：[{"value": "{\"content_1\": \"倪柝声弟兄职事\", \"content_2\": \"李常受弟兄职事第一阶段（1932-1960…", "count": 87}]
#### C4 标注匹配
- 记录数 87；匹配 87；找不到 0
- 找不到前 50：[]
- 括号外出现：[]；括号内出现：[]
- 括号内带额外内容：[]
- 字段：['name', 'series', 'stages', 'content_1', 'content_2', 'content_3', 'content_4', 'content_5', 'content_6']；字段名备注：{"has_same_as_field": false, "has_name_field": true, "needs_backtick": [], "ascii_ok": ["name", "series", "stages", "content_1", "content_2", "content_3", "content_4", "content_5", "content_6"]}

### 文件：`特殊标注/【intrinsic_significance】2372词条内在意义分类.json`
- 范围：图谱相关
- 大小 204307；mtime 2026-11-06 11:26:06
- UTF-8 BOM：False；解析成功：True；NaN/Infinity token：False
- 顶层：`{"structure": "dict", "keys": ["categories", "words"], "nkeys": 2}`
- 键 `categories`：{"type": "list", "n": 4, "item_keys": ["name", "count", "ratio", "definition"]}
  - 字段统计 keys=['count', 'definition', 'name', 'ratio']
```json
[
  {
    "name": "外在",
    "count": 1658,
    "ratio": "69.9%",
    "definition": "外在乃是真理外在、看得见的方面，就是实际、可见的外在一面，主要在于道理。包括实行上的外在：包含神经纶中行政安排的一面，就是神的家庭行政、管家的职分，以及召会事奉…"
  },
  {
    "name": "内在",
    "count": 497,
    "ratio": "21.0%",
    "definition": "内在乃是真理内里、看不见的方面，就是奥秘、隐藏的内在生命一面，是为着经历的；就读经说，就是圣经里的灵。在这一面，神作为那灵进入我们里面，我们就被生命的灵充满；这…"
  },
  {
    "name": "最内在",
    "count": 133,
    "ratio": "5.6%",
    "definition": "最内在乃是内在的素质与基督身体的实际。内在的素质，就是一样东西最内在的部分，乃是经过过程、正在分赐的三一神作神圣的生命，浸透我们，成为我们的内在成分；基督身体的…"
  }
]
```
- 键 `words`：{"type": "list", "n": 2372, "item_keys": ["no", "name", "category"]}
  - 字段统计 keys=['category', 'name', 'no']
```json
[
  {
    "no": 1,
    "name": "阿爸",
    "category": "内在"
  },
  {
    "no": 2,
    "name": "阿拉法与俄梅嘎",
    "category": "内在"
  },
  {
    "no": 3,
    "name": "阿利路亚",
    "category": "外在"
  }
]
```
#### C4 标注匹配
- 记录数 2372；匹配 2363；找不到 9
- 找不到前 50：[{"name": "产生男孩子（产生得胜者）", "count": 1}, {"name": "晨晨复兴（晨兴）", "count": 1}, {"name": "妇人（女人）", "count": 1}, {"name": "挂虑（忧虑）", "count": 1}, {"name": "火湖（地狱）", "count": 1}, {"name": "扩大（显大）", "count": 1}, {"name": "扩增（扩展）", "count": 1}, {"name": "路得马丁", "count": 1}, {"name": "那灵的浇灌（圣灵的浇灌）", "count": 1}]
- 括号外出现：[]；括号内出现：[]
- 括号内带额外内容：[]
- 字段：['no', 'name', 'category']；字段名备注：{"has_same_as_field": false, "has_name_field": true, "needs_backtick": [], "ascii_ok": ["no", "name", "category"]}

### 文件：`特殊标注/【mutuality】彼此互相.json`
- 范围：图谱相关
- 大小 12049；mtime 2026-10-06 12:12:03
- UTF-8 BOM：False；解析成功：True；NaN/Infinity token：False
- 顶层：`{"structure": "dict", "keys": ["tag", "definition", "note", "count", "words"], "nkeys": 5}`
- 键 `tag`：{"type": "str", "sample": "彼此互相"}
- 键 `definition`：{"type": "str", "sample": "彼此互相乃是身体的特点，身体尽功用乃是彼此互相的；彼此互相乃是召会聚会的基本原则，在我们的聚会中，讲说神的话应该是彼此互相的，而不是个人的，彼此互相（而非个人）…"}
- 键 `note`：{"type": "str", "sample": "“彼此”、“互相”的希腊原文是一个字，意义一样。在中文里面，“彼此”和“互相”都能表示双向的关系，最大的差别在于词性与语法功能。“彼此”既是代词（名词）也是副词…"}
- 键 `count`：{"type": "int", "sample": 116}
- 键 `words`：{"type": "list", "n": 116, "item_keys": ["no", "name", "phrasing"]}
  - 字段统计 keys=['name', 'no', 'phrasing']
```json
[
  {
    "no": 8,
    "name": "爱",
    "phrasing": "彼此相爱"
  },
  {
    "no": 9,
    "name": "爱弟兄",
    "phrasing": "爱弟兄"
  },
  {
    "no": 11,
    "name": "爱里建造",
    "phrasing": "爱里建造/彼此建造"
  }
]
```
#### C4 标注匹配
- 记录数 116；匹配 116；找不到 0
- 找不到前 50：[]
- 括号外出现：[]；括号内出现：[]
- 括号内带额外内容：[]
- 字段：['no', 'name', 'phrasing']；字段名备注：{"has_same_as_field": false, "has_name_field": true, "needs_backtick": [], "ascii_ok": ["no", "name", "phrasing"]}

### 文件：`特殊标注/【organic_advance】生机关联的进展.json`
- 范围：图谱相关
- 大小 38800482；mtime 2026-10-06 12:11:55
- UTF-8 BOM：False；解析成功：True；NaN/Infinity token：False
- 顶层：`{"structure": "list", "n": 69, "item_keys": ["name", "series", "stages", "content_1", "content_2", "content_3", "content_4", "content_5", "content_6"]}`
- 前 3 条（截断）：
```json
[
  {
    "name": "神的话",
    "series": "1　圣经—神的话",
    "stages": {
      "content_1": "倪柝声弟兄职事",
      "content_2": "李常受弟兄职事第一阶段（1932-1960）",
      "content_3": "李常受弟兄职事第二阶段（1961-1973）",
      "content_4": "李常受弟兄职事第三阶段（1974-1984）",
      "content_5": "李常受弟兄职事第四阶段（1985-1990）",
      "content_6": "李常受弟兄职事高峰阶段（1991-1997）"
    },
    "content_1": [
      {
        "title": "圣经是最高的法庭",
        "book": "圣经是我们独一无二的标准",
        "date": "1926年4月，福州",
        "source": "",
        "outline": "读经：提后三16～17，申五32～33，启二二18～19，林前十一19，多三10，启十八4\n壹\t只有圣经有权威—提后三16～17，赛八20，申十三18：（倪柝声…"
      },
      {
        "title": "圣经是我们独一无二的标准",
        "book": "圣经是我们独一无二的标准",
        "date": "1927年1月，地点未详",
        "source": "",
        "outline": "读经：申四2，箴三十6，启二二18～19，路十一28，林后四2，诗一一一10，约叁一4，雅四4，赛八20，西二8，提后三16，徒八4，多一13～14\n壹\t圣经是…"
      },
      {
        "title": "神的应许和事实",
        "book": "什么是新约",
        "date": "1931年10月，上海",
        "source": "",
        "outline": "读经：太二六28，约一17，创四六、四九，徒十八9，六6，林前一，加三，四4，弗一17\n壹\t神永远的目的是显在新约里；“恩典和真理，都是由耶稣基督来的”所以到了…"
      },
      "…"
    ],
    "content_2": [
      {
        "title": "新约内容的特点（一）—赦免与洁净",
        "book": "什么是新约",
        "date": "1949年，上海",
        "source": "",
        "outline": "读经：来八10～12，罗五12，约壹一7、9，太二六28，来一8～9，诗三二5，箴二八13\n壹\t新约的内容是包含三大部分，这是希伯来八章十至十二节告诉我们的：（…"
      },
      {
        "title": "新约内容的特点（二A）—神的律法放在我们里面",
        "book": "什么是新约",
        "date": "1949年，上海",
        "source": "",
        "outline": "读经：约壹二29，五4、6、14、18，来八10，弗三17上，诗四4，可四28，箴四23，结三六26\n壹\t我们要说到神如何把律法放在我们里面，写在我们心上，我们…"
      },
      {
        "title": "新约内容的特点（二B）—神在生命的律里作神",
        "book": "什么是新约",
        "date": "1949年，上海",
        "source": "",
        "outline": "读经：来八10，弗五21，可十二30，弗一19～20，三20，加四19，林后三18，约壹三2\n壹\t希伯来八章十节的下一半有话说，“我要作他们的神，他们要作我的子…"
      },
      "…"
    ],
    "content_3": [
      {
        "title": "享受圣经中各类的话语",
        "book": "",
        "date": "1961年3月至9月，台北",
        "source": "",
        "outline": "读经：约一1、14，太二六26～28，路五13，罗十二11，弗一23，太十六24，帖前五17\n壹\t按着圣经的分类享受主话；圣经里有许多不同类别的话语，其中所包含…"
      },
      {
        "title": "整本圣经中神建造的异象",
        "book": "",
        "date": "1964年冬，洛杉矶",
        "source": "",
        "outline": "读经：创二10～15，二八11～22，出二五1～三八38，四十17、34，该一8，太十六18\n壹\t我们鸟瞰整本圣经时，我们看见有一件中心的事物特别突出，就是建造…"
      },
      {
        "title": "整本圣经中有关新耶路撒冷的启示",
        "book": "",
        "date": "1964年冬，洛杉矶",
        "source": "",
        "outline": "读经：约一12，弗四16，启一11，二一2、9、11～13，弗二21～22，彼前二5，弗五25\n壹\t第一，全圣经所启示神的目的，其中心思想乃是要得着一班由神建造…"
      },
      "…"
    ],
    "content_4": [
      {
        "title": "贯穿整本圣经的生命线",
        "book": "贯穿整本圣经的生命线",
        "date": "1975年春，安那翰",
        "source": "",
        "outline": "读经：创四4，26，五22，24，六9，十二7～8，二六2，24～25，三五1，9，四八3，出二五9，撒上十二23，约六57，腓一21，弗一23，西三4，启二二…"
      },
      {
        "title": "依照圣经纯正话语的三一神启示",
        "book": "依照圣经纯正话语的三一神启示",
        "date": "1975年10月，安那翰",
        "source": "",
        "outline": "读经：诗八六10，约十四16～17，提前二5，林前八4，赛九6，太二八19，约二十22，林后三17，加五16、25\n壹\t从第二世纪以来，三一神这件事始终是基督徒…"
      },
      {
        "title": "创世记的核仁",
        "book": "圣经的核仁",
        "date": "1977年4月，德国斯图嘎",
        "source": "",
        "outline": "读经：约五39，提后三16，可十二24，弗一9、17，三9～11，创一26，二六25，西一15\n壹\t圣经是一本生命的书；作为一本生命的书，圣经有一个核仁，我们认…"
      },
      "…"
    ],
    "content_5": [
      {
        "title": "新约总论内容简介",
        "book": "",
        "date": "1985年夏，安那翰",
        "source": "",
        "outline": "读经：来十7下，太一22，西一25～27，弗一9～10，三9～11，启二一2、10～11\n壹\t我们将在此专题区中，详细陈明依照圣经纯正启示之神学观；将陆续针对神…"
      },
      {
        "title": "恢复本圣经",
        "book": "",
        "date": "1986年6月，台北",
        "source": "",
        "outline": "读经：赛三四16上，弗一17，三3，提后三16，路十22，林前二10，提后二15，太五18，诗一一九160，约八32，一4，十10\n壹\t我们愿意人知道新约圣经恢…"
      },
      {
        "title": "新约的鸟瞰",
        "book": "",
        "date": "1987年，安那翰",
        "source": "",
        "outline": "引言—新约各卷主题\nA. 马太福音\t国度的福音—证明耶稣基督是君王救主。（圣经恢复本，1987年）\nB. 马可福音\t\t神的福音—证明耶稣基督是奴仆救主。（圣经恢…"
      },
      "…"
    ],
    "content_6": [
      {
        "title": "整本圣经乃是三一神的自传",
        "book": "整本圣经乃是三一神的自传",
        "date": "1992年2月至6月，安那翰",
        "source": "",
        "outline": "读经：约一1，四14，耶二13，诗九十1～2，弥五2，创一26，约十二24，罗八29\n壹\t解释神永远经纶的这整本圣经，乃是三一神的自传，见于永世的两个段落之内，…"
      },
      {
        "title": "整本圣经中关于神与人的关系完成的神圣启示（一）",
        "book": "整本圣经中关于神与人的关系完成的神圣启示",
        "date": "1992年冬，安那翰",
        "source": "",
        "outline": "读经：创一26～27，十一7～9，二二18，出三二13，出十九16～二十21，太一20\n壹\t我们需要来看整本圣经中，关于神与人的关系完成的神圣启示；圣经中关于神…"
      },
      {
        "title": "整本圣经中关于神与人的关系完成的神圣启示（二）",
        "book": "整本圣经中关于神与人的关系完成的神圣启示",
        "date": "1992年冬，安那翰",
        "source": "",
        "outline": "读经：太一20、23，徒十三33，弗二5～6，启二一2～3、9～11、18、22，二二17\n肆\t新约中神与人的关系开始于基督第一次来，终极完成于新天新地的新耶路…"
      },
      "…"
    ]
  },
  {
    "name": "圣经",
    "series": "1　圣经—神的话",
    "stages": {
      "content_1": "倪柝声弟兄职事",
      "content_2": "李常受弟兄职事第一阶段（1932-1960）",
      "content_3": "李常受弟兄职事第二阶段（1961-1973）",
      "content_4": "李常受弟兄职事第三阶段（1974-1984）",
      "content_5": "李常受弟兄职事第四阶段（1985-1990）",
      "content_6": "李常受弟兄职事高峰阶段（1991-1997）"
    },
    "content_1": [
      {
        "title": "圣经是最高的法庭",
        "book": "圣经是我们独一无二的标准",
        "date": "1926年4月，福州",
        "source": "",
        "outline": "读经：提后三16～17，申五32～33，启二二18～19，林前十一19，多三10，启十八4\n壹\t只有圣经有权威—提后三16～17，赛八20，申十三18：（倪柝声…"
      },
      {
        "title": "圣经是我们独一无二的标准",
        "book": "圣经是我们独一无二的标准",
        "date": "1927年1月，地点未详",
        "source": "",
        "outline": "读经：申四2，箴三十6，启二二18～19，路十一28，林后四2，诗一一一10，约叁一4，雅四4，赛八20，西二8，提后三16，徒八4，多一13～14\n壹\t圣经是…"
      },
      {
        "title": "神的应许和事实",
        "book": "什么是新约",
        "date": "1931年10月，上海",
        "source": "",
        "outline": "读经：太二六28，约一17，创四六、四九，徒十八9，六6，林前一，加三，四4，弗一17\n壹\t神永远的目的是显在新约里；“恩典和真理，都是由耶稣基督来的”所以到了…"
      },
      "…"
    ],
    "content_2": [
      {
        "title": "新约内容的特点（一）—赦免与洁净",
        "book": "什么是新约",
        "date": "1949年，上海",
        "source": "",
        "outline": "读经：来八10～12，罗五12，约壹一7、9，太二六28，来一8～9，诗三二5，箴二八13\n壹\t新约的内容是包含三大部分，这是希伯来八章十至十二节告诉我们的：（…"
      },
      {
        "title": "新约内容的特点（二A）—神的律法放在我们里面",
        "book": "什么是新约",
        "date": "1949年，上海",
        "source": "",
        "outline": "读经：约壹二29，五4、6、14、18，来八10，弗三17上，诗四4，可四28，箴四23，结三六26\n壹\t我们要说到神如何把律法放在我们里面，写在我们心上，我们…"
      },
      {
        "title": "新约内容的特点（二B）—神在生命的律里作神",
        "book": "什么是新约",
        "date": "1949年，上海",
        "source": "",
        "outline": "读经：来八10，弗五21，可十二30，弗一19～20，三20，加四19，林后三18，约壹三2\n壹\t希伯来八章十节的下一半有话说，“我要作他们的神，他们要作我的子…"
      },
      "…"
    ],
    "content_3": [
      {
        "title": "享受圣经中各类的话语",
        "book": "",
        "date": "1961年3月至9月，台北",
        "source": "",
        "outline": "读经：约一1、14，太二六26～28，路五13，罗十二11，弗一23，太十六24，帖前五17\n壹\t按着圣经的分类享受主话；圣经里有许多不同类别的话语，其中所包含…"
      },
      {
        "title": "整本圣经中神建造的异象",
        "book": "",
        "date": "1964年冬，洛杉矶",
        "source": "",
        "outline": "读经：创二10～15，二八11～22，出二五1～三八38，四十17、34，该一8，太十六18\n壹\t我们鸟瞰整本圣经时，我们看见有一件中心的事物特别突出，就是建造…"
      },
      {
        "title": "整本圣经中有关新耶路撒冷的启示",
        "book": "",
        "date": "1964年冬，洛杉矶",
        "source": "",
        "outline": "读经：约一12，弗四16，启一11，二一2、9、11～13，弗二21～22，彼前二5，弗五25\n壹\t第一，全圣经所启示神的目的，其中心思想乃是要得着一班由神建造…"
      },
      "…"
    ],
    "content_4": [
      {
        "title": "贯穿整本圣经的生命线",
        "book": "贯穿整本圣经的生命线",
        "date": "1975年春，安那翰",
        "source": "",
        "outline": "读经：创四4，26，五22，24，六9，十二7～8，二六2，24～25，三五1，9，四八3，出二五9，撒上十二23，约六57，腓一21，弗一23，西三4，启二二…"
      },
      {
        "title": "依照圣经纯正话语的三一神启示",
        "book": "依照圣经纯正话语的三一神启示",
        "date": "1975年10月，安那翰",
        "source": "",
        "outline": "读经：诗八六10，约十四16～17，提前二5，林前八4，赛九6，太二八19，约二十22，林后三17，加五16、25\n壹\t从第二世纪以来，三一神这件事始终是基督徒…"
      },
      {
        "title": "创世记的核仁",
        "book": "圣经的核仁",
        "date": "1977年4月，德国斯图嘎",
        "source": "",
        "outline": "读经：约五39，提后三16，可十二24，弗一9、17，三9～11，创一26，二六25，西一15\n壹\t圣经是一本生命的书；作为一本生命的书，圣经有一个核仁，我们认…"
      },
      "…"
    ],
    "content_5": [
      {
        "title": "新约总论内容简介",
        "book": "",
        "date": "1985年夏，安那翰",
        "source": "",
        "outline": "读经：来十7下，太一22，西一25～27，弗一9～10，三9～11，启二一2、10～11\n壹\t我们将在此专题区中，详细陈明依照圣经纯正启示之神学观；将陆续针对神…"
      },
      {
        "title": "恢复本圣经",
        "book": "",
        "date": "1986年6月，台北",
        "source": "",
        "outline": "读经：赛三四16上，弗一17，三3，提后三16，路十22，林前二10，提后二15，太五18，诗一一九160，约八32，一4，十10\n壹\t我们愿意人知道新约圣经恢…"
      },
      {
        "title": "新约的鸟瞰",
        "book": "",
        "date": "1987年，安那翰",
        "source": "",
        "outline": "引言—新约各卷主题\nA. 马太福音\t国度的福音—证明耶稣基督是君王救主。（圣经恢复本，1987年）\nB. 马可福音\t\t神的福音—证明耶稣基督是奴仆救主。（圣经恢…"
      },
      "…"
    ],
    "content_6": [
      {
        "title": "整本圣经乃是三一神的自传",
        "book": "整本圣经乃是三一神的自传",
        "date": "1992年2月至6月，安那翰",
        "source": "",
        "outline": "读经：约一1，四14，耶二13，诗九十1～2，弥五2，创一26，约十二24，罗八29\n壹\t解释神永远经纶的这整本圣经，乃是三一神的自传，见于永世的两个段落之内，…"
      },
      {
        "title": "整本圣经中关于神与人的关系完成的神圣启示（一）",
        "book": "整本圣经中关于神与人的关系完成的神圣启示",
        "date": "1992年冬，安那翰",
        "source": "",
        "outline": "读经：创一26～27，十一7～9，二二18，出三二13，出十九16～二十21，太一20\n壹\t我们需要来看整本圣经中，关于神与人的关系完成的神圣启示；圣经中关于神…"
      },
      {
        "title": "整本圣经中关于神与人的关系完成的神圣启示（二）",
        "book": "整本圣经中关于神与人的关系完成的神圣启示",
        "date": "1992年冬，安那翰",
        "source": "",
        "outline": "读经：太一20、23，徒十三33，弗二5～6，启二一2～3、9～11、18、22，二二17\n肆\t新约中神与人的关系开始于基督第一次来，终极完成于新天新地的新耶路…"
      },
      "…"
    ]
  },
  {
    "name": "结晶意义",
    "series": "2　圣经的结晶意义",
    "stages": {
      "content_1": "倪柝声弟兄职事",
      "content_2": "李常受弟兄职事第一阶段（1932-1960）",
      "content_3": "李常受弟兄职事第二阶段（1961-1973）",
      "content_4": "李常受弟兄职事第三阶段（1974-1984）",
      "content_5": "李常受弟兄职事第四阶段（1985-1990）",
      "content_6": "李常受弟兄职事高峰阶段（1991-1997）"
    },
    "content_1": [
      {
        "title": "结晶与结晶品",
        "book": "",
        "date": "",
        "source": "倪柝声文集第一辑第十四册，属灵人（下册），卷九，第一章",
        "outline": "读经：提前三16，二4，提后三16～17，太四4，约五39，约七17，腓二12～13，弗四23，林前六17，太七21，太二六39，罗八1～4，约十六31～33，…"
      },
      {
        "title": "基督是道路真理生命",
        "book": "",
        "date": "",
        "source": "倪柝声文集第二辑第十六册，中心的信息，基督是道路真理和生命，第一篇",
        "outline": "读经：约十四6，一4、14、17，来十19～20，西三4，太十六16，二七54，诗一一六13，徒二21，耶二九12，林前六17，西三11下，林后三6下，罗十12…"
      },
      {
        "title": "圣灵的实际",
        "book": "",
        "date": "",
        "source": "倪柝声文集第二辑第十六册，中心的信息，圣灵与实际",
        "outline": "读经：约十六13～14，十四17，十五26，六51，四24，林后三6、15，西二17，罗八28\n壹\t有一件事，是神的儿女所必须注意的，就是一切属灵的事，一切属灵…"
      },
      "…"
    ],
    "content_2": [
      {
        "title": "神人调和的二性品",
        "book": "神人调和的二性品",
        "date": "1955年9月至10月，香港",
        "source": "",
        "outline": "读经：太二1，约一1、14，七42，林前六17，约十五1、4～5，二十22，西三1～4\n壹\t神与人调和的第一步，乃是话成肉体；主耶稣成孕在马利亚腹中，并降生于伯…"
      },
      {
        "title": "弃绝天然观念，接受圣经中生命与生活的观念",
        "book": "读出圣经的本色与中心",
        "date": "1958年3月，台北",
        "source": "",
        "outline": "读经：林前二11～16，提前六16，约十四3，二十22，六63，弗四18，提前三15～16\n壹\t我们读经时所带着的观念，和所期望的事实在太多；几乎每一个读经的人…"
      },
      {
        "title": "读经要用生命读法，吸取神的肥甘",
        "book": "读出圣经的本色与中心",
        "date": "1958年3月，台北",
        "source": "",
        "outline": "读经：诗一2～3，西二7，约十五7，五39～40，八31，六63，申十七18～20，提前四6\n壹\t读经的方法，是根据读经的目的；读经的目的乃为吸取神、享受神—诗…"
      },
      "…"
    ],
    "content_3": [
      {
        "title": "使徒行传真实的意义",
        "book": "使徒行传真实的意义",
        "date": "1964年6月，纽约",
        "source": "",
        "outline": "读经：徒二1、4、14、46～47，十八2，弗一22，三16～19，四4～6，启二二1，罗十二5\n壹\t我们需要对使徒行传这卷书所记载的，有真实的眼光；主死之后，…"
      }
    ],
    "content_4": [
      {
        "title": "实际的灵引导我们进入一切的实际",
        "book": "实际的灵引导我们进入一切的实际",
        "date": "1975年春，安那翰",
        "source": "",
        "outline": "读经：约十六12～15，十四17，西二9，弗四6，西二16～17，三11，罗八16，约十七1\n壹\t约翰十六章十三节说，“只等实际的灵来了，祂要引导你们进入一切的…"
      },
      {
        "title": "看见圣经中的奥秘",
        "book": "看见圣经中的奥秘",
        "date": "1975年8月，台北",
        "source": "",
        "outline": "读经：赛九6，约一1、14、29，弗三14～17上，创二7，林前十五45下，约壹二27～28，五21，约四24，提后四22，罗八4、6\n壹\t我们需要异象，看见圣…"
      },
      {
        "title": "图样与实际",
        "book": "不住的祷告与活在灵中",
        "date": "1979年10月，台北",
        "source": "",
        "outline": "读经：约五39～40，十四16～20，十六7，腓一21上，罗八4，林前十五45下，提后四22\n壹\t神在旧约是给人图样，因此旧约满了预表与豫像—约五39～40：（…"
      },
      "…"
    ],
    "content_5": [
      {
        "title": "召会内在的素质为着召会生机的存在",
        "book": "生机建造的召会作基督的身体",
        "date": "1989年11月，安那翰",
        "source": "",
        "outline": "读经：弗一23，四3～6，约十二24，约壹一2～3，五1，约十五1、4～5，罗十二4～5\n壹\t关于召会，最重要而积极的因素是召会内在的素质—约十二24，弗四4～…"
      },
      {
        "title": "召会内在的生长为着召会生机的扩增",
        "book": "生机建造的召会作基督的身体",
        "date": "1989年11月，安那翰",
        "source": "",
        "outline": "读经：弗二15，彼前二2，林前三2、6，西二19、9，弗四11～12，约十五1、5、8，弗四16\n壹\t我们看见召会内在的素质，为着召会生机的存在，现在我们要来看…"
      },
      {
        "title": "召会内在的建造为着召会生机的功用",
        "book": "生机建造的召会作基督的身体",
        "date": "1989年11月，安那翰",
        "source": "",
        "outline": "读经：创二21～23，约六57下，彼前二2～5，罗十二4～8，林前十二28，弗一23，四16\n壹\t我们要来看召会内在的建造，为着召会生机的功用；物质的建筑是由不…"
      },
      "…"
    ],
    "content_6": [
      {
        "title": "神新约经纶中奥秘的生命之灵的律",
        "book": "神新约经纶中奥秘的生命之灵的律",
        "date": "1990年4月，台北",
        "source": "",
        "outline": "读经：西三4上，罗八2，七21、23、25下，八6下，4下，13，十二6～8，林前十二8～10，28，加二20上，五16上，25，帖前五17，弗六17～18\n壹…"
      },
      {
        "title": "新耶路撒冷—神性人性互为居所",
        "book": "神新约经纶中奥秘的生命之灵的律",
        "date": "1990年4月，台北",
        "source": "",
        "outline": "读经：撒下七12～14上，弗三17上，约十四2～3、23，十五4上，启二一1～3、10、22\n壹\t神经纶中奥秘的终极完成，就是新耶路撒冷；这是经过过程的三一神与…"
      },
      {
        "title": "圣经中神圣启示的三层",
        "book": "圣经中神圣启示的三层",
        "date": "1990年8月，旧金山",
        "source": "",
        "outline": "读经：创二7～9，约十10下，弗一9，三2、8～11，西一25，林后十三14，林前十五45下\n壹\t神的经纶乃是神要把祂自己分赐到人性里面的计划；所以在神的经纶里…"
      },
      "…"
    ]
  }
]
```
- 字段盘点：
| 字段 | 非空 | 空 | distinct | 长度min/med/max | >32000 |
|---|---:|---:|---:|---|---:|
| content_1 | 66 | 3 | 63 | 2/22881/105751 | 28 |
| content_2 | 57 | 12 | 54 | 2/14125/186927 | 14 |
| content_3 | 63 | 6 | 59 | 2/33787/261946 | 36 |
| content_4 | 65 | 4 | 61 | 2/40731/162430 | 41 |
| content_5 | 65 | 4 | 62 | 2/15473/133945 | 17 |
| content_6 | 69 | 0 | 64 | 196/28187/145404 | 29 |
| name | 69 | 0 | 69 | 1/5/7 | 0 |
| series | 69 | 0 | 61 | 4/8/13 | 0 |
| stages | 69 | 0 | 1 | 219/219/219 | 0 |
  - 取值（≤50）：[{"value": "{\"content_1\": \"倪柝声弟兄职事\", \"content_2\": \"李常受弟兄职事第一阶段（1932-1960…", "count": 69}]
#### C4 标注匹配
- 记录数 69；匹配 69；找不到 0
- 找不到前 50：[]
- 括号外出现：[]；括号内出现：[]
- 括号内带额外内容：[]
- 字段：['name', 'series', 'stages', 'content_1', 'content_2', 'content_3', 'content_4', 'content_5', 'content_6']；字段名备注：{"has_same_as_field": false, "has_name_field": true, "needs_backtick": [], "ascii_ok": ["name", "series", "stages", "content_1", "content_2", "content_3", "content_4", "content_5", "content_6"]}

### 文件：`防火墙/【devine_argument】越进入高峰，真理越需要辨明得准确.json`
- 范围：图谱相关
- 大小 1250134；mtime 2026-10-05 12:25:16
- UTF-8 BOM：False；解析成功：True；NaN/Infinity token：False
- 顶层：`{"structure": "list", "n": 189, "item_keys": ["name", "content_1"]}`
- 前 3 条（截断）：
```json
[
  {
    "name": "巴路西亚",
    "content_1": [
      {
        "title": "基督的再来",
        "description": "公开一面，基督驾云降临时，全地都要看见祂",
        "outline": "读经：太二四27、30，帖前四16~17，帖后二8，启一7，二28，十1，十二5，十四1，十九7~9，二十4、6\n壹　基督的再来乃是基督所应许的巴路西亚，意思是…"
      }
    ]
  },
  {
    "name": "被圣灵充满",
    "content_1": [
      {
        "title": "圣灵里面的充满与外面的充溢",
        "description": "素质与经纶两面并重，同时注重里外两面",
        "outline": "读经：太三16~17，路三21~22，约七38~39，徒一8，二2~4、17，罗五5，八2，弗四13，五18，加三14\n壹　新约启示那灵的两面—生命的灵和能力的…"
      }
    ]
  },
  {
    "name": "被圣灵充溢",
    "content_1": [
      {
        "title": "圣灵里面的充满与外面的充溢",
        "description": "素质与经纶两面并重，同时注重里外两面",
        "outline": "读经：太三16~17，路三21~22，约七38~39，徒一8，二2~4、17，罗五5，八2，弗四13，五18，加三14\n壹　新约启示那灵的两面—生命的灵和能力的…"
      }
    ]
  }
]
```
- 字段盘点：
| 字段 | 非空 | 空 | distinct | 长度min/med/max | >32000 |
|---|---:|---:|---:|---|---:|
| content_1 | 189 | 0 | 72 | 1319/2190/3858 | 0 |
| content_2 | 7 | 182 | 7 | 1951/2149/2816 | 0 |
  - 取值（≤50）：[{"value": null, "count": 182}, {"value": "[{\"description\": \"得赏赐是按着神的公义\", \"outline\": \"读经：弗二8~9，提后四8，林前三…", "count": 2}, {"value": "[{\"description\": \"缺宇宙一面，没有内容；缺地方一面，没有出现和实行\", \"outline\": \"读经：…", "count": 1}, {"value": "[{\"description\": \"恨任何的教，爱所有的基督徒\", \"outline\": \"读经：约一4，十10，三16…", "count": 1}, {"value": "[{\"description\": \"不可将恩典变作放纵的机会\", \"outline\": \"读经：出十九8，罗六14，七7…", "count": 1}, {"value": "[{\"description\": \"在生命和性情上，但不在神格上\", \"outline\": \"读经：约一1、14，林前十…", "count": 1}, {"value": "[{\"description\": \"职事从不控制众召会，总是服事并供应众召会\", \"outline\": \"读经：弗四12…", "count": 1}]
| content_3 | 2 | 187 | 3 | 2072/2151/2231 | 0 |
  - 取值（≤50）：[{"value": null, "count": 187}, {"value": "[{\"description\": \"得胜是基督替我们活\", \"outline\": \"读经：罗五17，八4、10、37，加…", "count": 1}, {"value": "[{\"description\": \"无分于神格\", \"outline\": \"读经：彼后一3~4，彼前一3，二2、5、9，…", "count": 1}]
| name | 189 | 0 | 189 | 1/4/9 | 0 |
#### C4 标注匹配
- 记录数 189；匹配 189；找不到 0
- 找不到前 50：[]
- 括号外出现：['产生男孩子', '那灵的浇灌']；括号内出现：['产生得胜者', '圣灵的浇灌']
- 括号内带额外内容：[{"name": "产生得胜者", "extra_keys": ["content_1"]}, {"name": "圣灵的浇灌", "extra_keys": ["content_1"]}]
- 字段：['name', 'content_1']；字段名备注：{"has_same_as_field": false, "has_name_field": true, "needs_backtick": [], "ascii_ok": ["name", "content_1"]}

### C5 一致性
```json
{
  "term_set_sizes": {
    "29种关系_成立边.json": 1270,
    "特殊标注/【high_peak_content】从历史进展的差异看高峰时期的内涵.json": 87,
    "特殊标注/【intrinsic_significance】2372词条内在意义分类.json": 2372,
    "特殊标注/【mutuality】彼此互相.json": 116,
    "特殊标注/【organic_advance】生机关联的进展.json": 69,
    "防火墙/【devine_argument】越进入高峰，真理越需要辨明得准确.json": 189
  },
  "rel_subset_of__特殊标注/【high_peak_content】从历史进展的差异看高峰时期的内涵.json": false,
  "rel_only__特殊标注/【high_peak_content】从历史进展的差异看高峰时期的内涵.json": 1211,
  "annot_only__特殊标注/【high_peak_content】从历史进展的差异看高峰时期的内涵.json": 28,
  "rel_subset_of__特殊标注/【intrinsic_significance】2372词条内在意义分类.json": true,
  "rel_only__特殊标注/【intrinsic_significance】2372词条内在意义分类.json": 0,
  "annot_only__特殊标注/【intrinsic_significance】2372词条内在意义分类.json": 1102,
  "rel_subset_of__特殊标注/【mutuality】彼此互相.json": false,
  "rel_only__特殊标注/【mutuality】彼此互相.json": 1220,
  "annot_only__特殊标注/【mutuality】彼此互相.json": 66,
  "rel_subset_of__特殊标注/【organic_advance】生机关联的进展.json": false,
  "rel_only__特殊标注/【organic_advance】生机关联的进展.json": 1222,
  "annot_only__特殊标注/【organic_advance】生机关联的进展.json": 21,
  "rel_subset_of__防火墙/【devine_argument】越进入高峰，真理越需要辨明得准确.json": false,
  "rel_only__防火墙/【devine_argument】越进入高峰，真理越需要辨明得准确.json": 1140,
  "annot_only__防火墙/【devine_argument】越进入高峰，真理越需要辨明得准确.json": 59
}
```

### C6 目录之外（不纳入导入）
- `G:\copypan\docs\panai4_graph\词条三档分类.json` exists=True note=三档分类 records={'外在': 1760, '内在': 488, '最内在': 133} keys=['外在', '内在', '最内在'] size=43661
- `G:\copypan\docs\3a_export.json` exists=True note=鸟瞰定义 content_3a records=2381 keys=['id', 'title', 'content_3a'] size=16777777
- `C:\Users\28121\Desktop\一般性标注\00neo4j_query_table_data_2026-8-25.json` exists=True note=桌面一般性标注（不在可导入资料内） records=1095 keys=['name', 'greek_terms', 'related_scriptures'] size=654926
- 与「可导入资料」重叠：`3a_export.json` 的 `content_3a` 接近「定义/鸟瞰」；`词条三档分类.json` 与 `【intrinsic_significance】…` 同属分档类信息但结构不同；桌面 `一般性标注/00neo4j_query_table_data_*.json` 含 `greek_terms`/`related_scriptures`，**未放入可导入资料**。

## D. 脚本能力

### D1
- build_v4：在 NEO4J_V4_URI 上 MERGE 节点（Truth_Point/Trunk/Branch）、分类 4 种关系、并从 3.5 只读迁移旧 6 种关系；默认不删除。
- 参数：['(默认/--apply)', '--dry-run', '--cleanup', '--cleanup --confirm']
- 读取：['docs/panai4_graph/2373个词条（已确定一一对应为concept节点）.txt', 'docs/panai4_graph/主恢复真理词典_词条主干枝子映射 (1).json', 'docs/panai4_graph/12大类与91小类的对应关系.txt', 'docs/panai4_graph/concept_mapping_35_to_40.csv', '3.5 NEO4J_URI（只读，旧 6 种 Concept→Concept）']
- 写入行为：仅 NEO4J_V4；MERGE 节点与分类关系、旧 6 种；SET same_as；--cleanup --confirm 只删清单内分类范围项
- 能否直接导入 29 种关系 JSON：**否**。缺：['无读取「可导入资料」或 29 种关系 JSON 的代码', '无写入除旧 6 种与分类 4 种以外关系类型的逻辑', '无一般/专特标注字段的 SET 逻辑（除 name/same_as）', '关系类型名含斜杠（如 EXPERIENCES / ENJOYS）时无命名规范化']
- inventory_35：盘点 3.5 Neo4j（NEO4J_URI）只读，并核对 panai4 词表；可选探测 NEO4J_V4_* 是否配置。；写入：只写 docs/panai4_graph/reports/ 报告，不写图谱
- README：说明默认 MERGE、--cleanup 两段式、清理范围不含迁移旧关系与以后新增关系。

### D2
- 按关系类型批量删除旧 6 种：**无**（`has_batch_delete_by_type_in_build=False`）。`--cleanup` 只清分类 4 种与名单外节点/`same_as`，**明确排除**迁移旧关系。
- 写死绝对路径扫描结果：未发现 G:/ 或 C:/Users/ 字面量；资料路径为仓库相对 docs/panai4_graph/。

## E. 汇总与问题清单

### 删除前后 / 导入后对比预估
| 项目 | 当前 | 删旧6后 | 再导入29种后（算术预估） |
|---|---:|---:|---:|
| 节点总数 | 2484 | 2484 | 2484（标注导入不增节点） |
| 关系总数 | 45702 | 6529 | 42431 |
| BELONGS_TO_TRUNK | 2381 | 2381 | 2381 |
| OF_BRANCH_DIRECTLY | 2381 | 2381 | 2381 |
| OF_BRANCH_INDIRECTLY | 1676 | 1676 | 1676 |
| GRAFTING | 91 | 91 | 91 |
| LEADS_TO（旧） | 14140 | 0 | 0（若重制用新类型名则不再用此名） |
| EXPERIENCES（旧） | 7725 | 0 | 0（若重制用新类型名则不再用此名） |
| PRACTICED_AS（旧） | 7431 | 0 | 0（若重制用新类型名则不再用此名） |
| CONTAINS（旧） | 5977 | 0 | 0（若重制用新类型名则不再用此名） |
| OPPOSES（旧） | 3372 | 0 | 0（若重制用新类型名则不再用此名） |
| LOCATED_IN（旧） | 528 | 0 | 0（若重制用新类型名则不再用此名） |
| 新 `REVEALS` | 0 | 0 | 1385 |
| 新 `IN_APPOSITION_WITH / EQUIVALENT_TO` | 0 | 0 | 1189 |
| 新 `TYPIFIES` | 0 | 0 | 663 |
| 新 `COINHERES_WITH` | 0 | 0 | 278 |
| 新 `EMBODIED_IN / REALIZED_AS` | 0 | 0 | 196 |
| 新 `PROCESSED_THROUGH` | 0 | 0 | 532 |
| 新 `BECOMES` | 0 | 0 | 470 |
| 新 `DISPENSED_INTO` | 0 | 0 | 2155 |
| 新 `INDWELLS` | 0 | 0 | 1194 |
| 新 `CO_WITH` | 0 | 0 | 1376 |
| 新 `IN` | 0 | 0 | 1059 |
| 新 `UNITED_WITH` | 0 | 0 | 929 |
| 新 `MINGLED_WITH` | 0 | 0 | 295 |
| 新 `INCORPORATED_WITH` | 0 | 0 | 141 |
| 新 `EXPERIENCES / ENJOYS` | 0 | 0 | 7832 |
| 新 `PRACTICED_AS` | 0 | 0 | 3622 |
| 新 `BUILT_INTO` | 0 | 0 | 451 |
| 新 `EXPRESSES` | 0 | 0 | 2174 |
| 新 `SPREADS` | 0 | 0 | 904 |
| 新 `CONSUMMATED_IN` | 0 | 0 | 190 |
| 新 `IS_A` | 0 | 0 | 226 |
| 新 `CONTAINS` | 0 | 0 | 491 |
| 新 `OPPOSES / CONTRASTS_WITH` | 0 | 0 | 720 |
| 新 `OUT_OF` | 0 | 0 | 728 |
| 新 `CAUSES` | 0 | 0 | 1048 |
| 新 `LEADS_TO` | 0 | 0 | 2742 |
| 新 `BY_MEANS_OF` | 0 | 0 | 2044 |
| 新 `BEFORE / SIMULTANEOUS_WITH / DURING` | 0 | 0 | 219 |
| 新 `LOCATED_IN` | 0 | 0 | 649 |

注意：若重制类型继续使用 `LEADS_TO` 等同名，则「删旧再导入」后该类型数量=新 JSON 计数，而不是 0；上表把「旧类型清零」与「新 JSON 类型另列」分开，避免与分类四型混淆。分类四型与 29 种 **无同名冲突**：`[]`。

### 需要主设计师决定的问题（只提问）
1. 新 JSON 里多个 `relation` 含 `/` 与空格（如 `EXPERIENCES / ENJOYS`、`IN_APPOSITION_WITH / EQUIVALENT_TO`）：导入时用哪个正式类型名？是否拆成两种关系？
2. 新关系 JSON 仍出现未拆分合并名（如 `晨晨复兴（晨兴）`），图谱已拆成两节点：导入前是否把合并名映射到括号外节点？括号内节点名若出现在 from/to，按 same_as 改挂到括号外，还是原样保留？
3. 关系端点 name 在图谱中找不到时（本轮仅 5 个名字、196 次）：跳过、报错中止、映射后导入，还是先建节点？
4. 六个重制关系与旧边重叠很少/很多时：是否允许同名覆盖？方向是否一律以新 JSON 为准？
5. 「可导入资料」中**没有**一般标注 JSON（中文名/英文名/希伯来/希腊/定义等）；是否改用 `docs/3a_export.json`、桌面 `一般性标注/00neo4j_*.json`，或等待另份 JSON？
6. 专特标注字段多为嵌套 list/dict（如 `content_1`…、`stages`）：存成 JSON 字符串标注、拆子图，还是只取摘要字段？
7. 标注字段名含中文或非 `[A-Za-z_][A-Za-z0-9_]*` 时，是否统一映射为英文蛇形名？
8. `【intrinsic_significance】` 词表 2372 条 vs 图谱 Truth_Point≈2381：差的是否就是括号拆分？导入时如何对齐？
9. 删除旧 6 种后，是否需要同步改 `build_v4.py`，避免以后 `--apply` 再次从 3.5 MERGE 回旧关系？
10. `hymns.json` 确认仅进 ES、本周图谱不动——是否还需从「可导入资料」挪出以免误导入？
11. 防火墙 JSON 中括号内节点 `产生得胜者`、`圣灵的浇灌` 也带了 `content_1`（按已定规则内容应只在括号外）；导入时丢弃、合并到括号外，还是保留？
12. 分类关系实测 6529，口令约 6526（差 3，主要在 `OF_BRANCH_INDIRECTLY=1676`）：是否需要追查，还是以实测为准？

## 验证

1. 盘点前快照：nodes=2484 rels=45702 by_type={'BELONGS_TO_TRUNK': 2381, 'CONTAINS': 5977, 'EXPERIENCES': 7725, 'GRAFTING': 91, 'LEADS_TO': 14140, 'LOCATED_IN': 528, 'OF_BRANCH_DIRECTLY': 2381, 'OF_BRANCH_INDIRECTLY': 1676, 'OPPOSES': 3372, 'PRACTICED_AS': 7431}
   盘点后快照：nodes=2484 rels=45702 by_type={'BELONGS_TO_TRUNK': 2381, 'CONTAINS': 5977, 'EXPERIENCES': 7725, 'GRAFTING': 91, 'LEADS_TO': 14140, 'LOCATED_IN': 528, 'OF_BRANCH_DIRECTLY': 2381, 'OF_BRANCH_INDIRECTLY': 1676, 'OPPOSES': 3372, 'PRACTICED_AS': 7431}
   完全相同：True
2. A2 标签和 2484 =? A9 节点 2484 → True （注：多标签节点会使标签和>节点数；本库预期单标签）
   A4 关系和 45702 =? A9 关系 45702 → True
3. A7：保留 6529 + 旧6 39173 =? 总数 45702 → True
4. SHA256：盘前文件数 10 字节 62589421；盘后 10 / 62589421；哈希表相同：True
5. 关系 JSON：类型 pairs 之和==记录边数 → True；标注字段非空≤记录数：见各文件 field_stats（脚本内已按字段统计）。
6. git status：本轮仅新增 `back_mic/backend/panai4/graph/inventory_v4_pre.py`、`docs/panai4_graph/neo4j_v4_inventory_pre.md` 与 `logs/inventory_v4_pre_*`；工作区中其余 M/?? 为既有未提交改动，非本盘点写入。详见运行日志。
   另：分类关系实测合计 6529（预期口令约 6526），差 3，见 A7；未改图谱。
7. 只读 Cypher：是；未运行 build_v4：是；未读取并打印 .env 值：是；报告/日志密钥字符串检查：{"password_in_report": false, "password_in_log": false, "compared_in_memory_only": true}

---
附录：完整代码命中表见同次运行的 `logs/inventory_v4_pre_*.json`。
