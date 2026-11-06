# neo4j-v4 导入 29 种关系报告

生成时间：2026-11-06 22:31:24；脚本：`panai4.graph.import_relations_29`。
只用 pairs 建关系；关系上无属性；类型名带反引号；未运行 build_v4.py；未打印密码。

## 摘要

1. **源**：`C:\Users\28121\Desktop\可导入资料\29种关系_成立边.json`；raw_pairs=35902；unique=35902。
2. **类型重命名**：{"IN_APPOSITION_WITH / EQUIVALENT_TO": "EQUIVALENT_TO", "EMBODIED_IN / REALIZED_AS": "EMBODIED_IN_REALIZED_AS", "EXPERIENCES / ENJOYS": "EXPERIENCES_ENJOYS", "OPPOSES / CONTRASTS_WITH": "OPPOSES_CONTRASTS_WITH", "BEFORE / SIMULTANEOUS_WITH / DURING": "SIMULTANEOUS_WITH"}
3. **端点映射**：{"路得马丁": "路德马丁", "那灵的浇灌（圣灵的浇灌）": "那灵的浇灌", "晨晨复兴（晨兴）": "晨晨复兴", "火湖（地狱）": "火湖", "挂虑（忧虑）": "挂虑"}；alias_hits={'路得马丁': 2}；composite_hits={'那灵的浇灌（圣灵的浇灌）': 74, '晨晨复兴（晨兴）': 84, '火湖（地狱）': 35, '挂虑（忧虑）': 1}。
4. **闸门**：missing=[] inner=[] fails=[] check_ok=True。
5. **自环** n=0；**重复对** n=0（MERGE 后各类型按 unique 计）。
6. **索引**：name_index=[{'name': 'truth_point_name', 'type': 'RANGE', 'state': 'ONLINE', 'properties': ['name']}] name_constraint=[{'name': 'truth_point_name', 'type': 'UNIQUENESS', 'properties': ['name']}]（未自行创建）。
7. **import**：{"aborted": false, "progress": {"REVEALS": {"expected": 1385, "actual": 1385}, "EQUIVALENT_TO": {"expected": 1189, "actual": 1189}, "TYPIFIES": {"expected": 663, "actual": 663}, "COINHERES_WITH": {"ex…。
8. **verify**：ok=True rels_total=42429 expect=42429 fails=[]。

## B1 类型映射表
- `REVEALS` → `REVEALS`；name=启示 type=专特 count=1385 pairs=1385
- `IN_APPOSITION_WITH / EQUIVALENT_TO` → `EQUIVALENT_TO`（已替换）；name=同位／等同 type=专特 count=1189 pairs=1189
- `TYPIFIES` → `TYPIFIES`；name=预表 type=专特 count=663 pairs=663
- `COINHERES_WITH` → `COINHERES_WITH`；name=互相内住 type=专特 count=278 pairs=278
- `EMBODIED_IN / REALIZED_AS` → `EMBODIED_IN_REALIZED_AS`（已替换）；name=具体化／实化 type=专特 count=196 pairs=196
- `PROCESSED_THROUGH` → `PROCESSED_THROUGH`；name=经过过程 type=专特 count=532 pairs=532
- `BECOMES` → `BECOMES`；name=成为 type=专特 count=470 pairs=470
- `DISPENSED_INTO` → `DISPENSED_INTO`；name=神的分赐 type=专特 count=2155 pairs=2155
- `INDWELLS` → `INDWELLS`；name=内住 type=专特 count=1194 pairs=1194
- `CO_WITH` → `CO_WITH`；name=同…（新约的） type=专特 count=1376 pairs=1376
- `IN` → `IN`；name=在灵里… type=专特 count=1059 pairs=1059
- `UNITED_WITH` → `UNITED_WITH`；name=联结 type=专特 count=929 pairs=929
- `MINGLED_WITH` → `MINGLED_WITH`；name=调和 type=专特 count=295 pairs=295
- `INCORPORATED_WITH` → `INCORPORATED_WITH`；name=合并（Incorporation） type=专特 count=141 pairs=141
- `EXPERIENCES / ENJOYS` → `EXPERIENCES_ENJOYS`（已替换）；name=经历/享受 type=专特 count=7832 pairs=7832
- `PRACTICED_AS` → `PRACTICED_AS`；name=实行 type=专特 count=3622 pairs=3622
- `BUILT_INTO` → `BUILT_INTO`；name=建造（内在的） type=专特 count=451 pairs=451
- `EXPRESSES` → `EXPRESSES`；name=彰显 type=专特 count=2174 pairs=2174
- `SPREADS` → `SPREADS`；name=扩展 type=专特 count=904 pairs=904
- `CONSUMMATED_IN` → `CONSUMMATED_IN`；name=终极完成 type=专特 count=190 pairs=190
- `IS_A` → `IS_A`；name=类属 type=一般 count=226 pairs=226
- `CONTAINS` → `CONTAINS`；name=包含 type=一般 count=491 pairs=491
- `OPPOSES / CONTRASTS_WITH` → `OPPOSES_CONTRASTS_WITH`（已替换）；name=对立/对比 type=一般 count=720 pairs=720
- `OUT_OF` → `OUT_OF`；name=来源／出于 type=一般 count=728 pairs=728
- `CAUSES` → `CAUSES`；name=因果 type=一般 count=1048 pairs=1048
- `LEADS_TO` → `LEADS_TO`；name=结果/导向/目标 type=一般 count=2742 pairs=2742
- `BY_MEANS_OF` → `BY_MEANS_OF`；name=方式 type=一般 count=2044 pairs=2044
- `BEFORE / SIMULTANEOUS_WITH / DURING` → `SIMULTANEOUS_WITH`（已替换）；name=时间 type=一般 count=219 pairs=219
- `LOCATED_IN` → `LOCATED_IN`；name=地点/空间 type=一般 count=649 pairs=649

## B2 统计
- expected_counts={
  "REVEALS": 1385,
  "EQUIVALENT_TO": 1189,
  "TYPIFIES": 663,
  "COINHERES_WITH": 278,
  "EMBODIED_IN_REALIZED_AS": 196,
  "PROCESSED_THROUGH": 532,
  "BECOMES": 470,
  "DISPENSED_INTO": 2155,
  "INDWELLS": 1194,
  "CO_WITH": 1376,
  "IN": 1059,
  "UNITED_WITH": 929,
  "MINGLED_WITH": 295,
  "INCORPORATED_WITH": 141,
  "EXPERIENCES_ENJOYS": 7832,
  "PRACTICED_AS": 3622,
  "BUILT_INTO": 451,
  "EXPRESSES": 2174,
  "SPREADS": 904,
  "CONSUMMATED_IN": 190,
  "IS_A": 226,
  "CONTAINS": 491,
  "OPPOSES_CONTRASTS_WITH": 720,
  "OUT_OF": 728,
  "CAUSES": 1048,
  "LEADS_TO": 2742,
  "BY_MEANS_OF": 2044,
  "SIMULTANEOUS_WITH": 219,
  "LOCATED_IN": 649
}
- self_loops=[]
- dup_pairs_head=[]
- dup_pairs_total=0

## B3 import
```json
{
  "aborted": false,
  "progress": {
    "REVEALS": {
      "expected": 1385,
      "actual": 1385
    },
    "EQUIVALENT_TO": {
      "expected": 1189,
      "actual": 1189
    },
    "TYPIFIES": {
      "expected": 663,
      "actual": 663
    },
    "COINHERES_WITH": {
      "expected": 278,
      "actual": 278
    },
    "EMBODIED_IN_REALIZED_AS": {
      "expected": 196,
      "actual": 196
    },
    "PROCESSED_THROUGH": {
      "expected": 532,
      "actual": 532
    },
    "BECOMES": {
      "expected": 470,
      "actual": 470
    },
    "DISPENSED_INTO": {
      "expected": 2155,
      "actual": 2155
    },
    "INDWELLS": {
      "expected": 1194,
      "actual": 1194
    },
    "CO_WITH": {
      "expected": 1376,
      "actual": 1376
    },
    "IN": {
      "expected": 1059,
      "actual": 1059
    },
    "UNITED_WITH": {
      "expected": 929,
      "actual": 929
    },
    "MINGLED_WITH": {
      "expected": 295,
      "actual": 295
    },
    "INCORPORATED_WITH": {
      "expected": 141,
      "actual": 141
    },
    "EXPERIENCES_ENJOYS": {
      "expected": 7832,
      "actual": 7832
    },
    "PRACTICED_AS": {
      "expected": 3622,
      "actual": 3622
    },
    "BUILT_INTO": {
      "expected": 451,
      "actual": 451
    },
    "EXPRESSES": {
      "expected": 2174,
      "actual": 2174
    },
    "SPREADS": {
      "expected": 904,
      "actual": 904
    },
    "CONSUMMATED_IN": {
      "expected": 190,
      "actual": 190
    },
    "IS_A": {
      "expected": 226,
      "actual": 226
    },
    "CONTAINS": {
      "expected": 491,
      "actual": 491
    },
    "OPPOSES_CONTRASTS_WITH": {
      "expected": 720,
      "actual": 720
    },
    "OUT_OF": {
      "expected": 728,
      "actual": 728
    },
    "CAUSES": {
      "expected": 1048,
      "actual": 1048
    },
    "LEADS_TO": {
      "expected": 2742,
      "actual": 2742
    },
    "BY_MEANS_OF": {
      "expected": 2044,
      "actual": 2044
    },
    "SIMULTANEOUS_WITH": {
      "expected": 219,
      "actual": 219
    },
    "LOCATED_IN": {
      "expected": 649,
      "actual": 649
    }
  },
  "types": 29
}
```

## B4 verify
- type_counts={
  "REVEALS": 1385,
  "EQUIVALENT_TO": 1189,
  "TYPIFIES": 663,
  "COINHERES_WITH": 278,
  "EMBODIED_IN_REALIZED_AS": 196,
  "PROCESSED_THROUGH": 532,
  "BECOMES": 470,
  "DISPENSED_INTO": 2155,
  "INDWELLS": 1194,
  "CO_WITH": 1376,
  "IN": 1059,
  "UNITED_WITH": 929,
  "MINGLED_WITH": 295,
  "INCORPORATED_WITH": 141,
  "EXPERIENCES_ENJOYS": 7832,
  "PRACTICED_AS": 3622,
  "BUILT_INTO": 451,
  "EXPRESSES": 2174,
  "SPREADS": 904,
  "CONSUMMATED_IN": 190,
  "IS_A": 226,
  "CONTAINS": 491,
  "OPPOSES_CONTRASTS_WITH": 720,
  "OUT_OF": 728,
  "CAUSES": 1048,
  "LEADS_TO": 2742,
  "BY_MEANS_OF": 2044,
  "SIMULTANEOUS_WITH": 219,
  "LOCATED_IN": 649
}
- class_types={'BELONGS_TO_TRUNK': 2380, 'OF_BRANCH_DIRECTLY': 2380, 'OF_BRANCH_INDIRECTLY': 1676, 'GRAFTING': 91}
- nodes=2483 labels={'Branch': 91, 'Trunk': 12, 'Truth_Point': 2380}
- rel_props_nonzero=0 city_n=0
- protected_compare={"devine_argument": {"before_n": 187, "now_n": 187, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}, "intrinsic_significance": {"before_n": 2372, "now_n": 2372, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}, "mutuality": {"before_n": 116, "now_n": 116, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}, "organic_advance": {"before_n": 69, "now_n": 69, "sha_mismatch": 0, "only_before": [], "only_now": [], "mismatch_names": []}}
- a_props_compare={"name_en": {"before_n": 2372, "now_n": 2372, "sha_mismatch": 0, "only_before": [], "only_now": []}, "greek_terms": {"before_n": 2257, "now_n": 2257, "sha_mismatch": 0, "only_before": [], "only_now": []}, "hebrew_terms": {"before_n": 1523, "now_n": 1523, "sha_mismatch": 0, "only_before": [], "only_now": []}, "related_scriptures": {"before_n": 2372, "now_n": 2372, "sha_mismatch": 0, "only_before": [], "only_now": []}, "definition_3a": {"before_n": 2372, "now_n": 2372, "sha_mismatch": 0, "only_before": [], "only_now": []}, "definition_3b": {"before_n": 2062, "now_n": 2062, "sha_mismatch": 0, "only_before": [], "only_now": []}}
- luther_samples=[{"type": "LOCATED_IN", "from": "路德马丁", "to": "欧洲", "present": true}, {"type": "LOCATED_IN", "from": "路德马丁", "to": "校园", "present": true}]
- samples_per_type_keys=['REVEALS', 'EQUIVALENT_TO', 'TYPIFIES', 'COINHERES_WITH', 'EMBODIED_IN_REALIZED_AS', 'PROCESSED_THROUGH', 'BECOMES', 'DISPENSED_INTO', 'INDWELLS', 'CO_WITH', 'IN', 'UNITED_WITH', 'MINGLED_WITH', 'INCORPORATED_WITH', 'EXPERIENCES_ENJOYS', 'PRACTICED_AS', 'BUILT_INTO', 'EXPRESSES', 'SPREADS', 'CONSUMMATED_IN', 'IS_A', 'CONTAINS', 'OPPOSES_CONTRASTS_WITH', 'OUT_OF', 'CAUSES', 'LEADS_TO', 'BY_MEANS_OF', 'SIMULTANEOUS_WITH', 'LOCATED_IN']
- fails=[]

## 最终验证
- 未修改 import_annotation*.py / delete_old_relations.py / .gitignore（本脚本不改）
- 未运行 build_v4.py
- 报告与日志密码检查：通过（仅变量名）
- 日志：`G:\copypan\logs\import_relations_29_verify_20261106_223119.log`
