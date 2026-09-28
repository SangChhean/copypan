# 清理候选

由 `build_v4.py --cleanup` 生成。这一步没有删除任何节点、关系或标注。
`--cleanup --confirm` 只删除本文件代码块里的这些候选，不会重新计算。

- 列出时的节点数：**2484**
- 列出时的关系数：**45699**
- 候选节点：**1**
- 候选关系：**0**
- 候选 same_as：**0**

范围只包括 Truth_Point、Trunk、Branch 中不在资料名单里的节点，
以及 GRAFTING、BELONGS_TO_TRUNK、OF_BRANCH_DIRECTLY、OF_BRANCH_INDIRECTLY 中与资料不符的关系，
和与资料不符的 same_as。6 种迁移来的旧关系、其他关系类型、其他标注都不在此列。

## 节点

| 标签 | 名字 |
|---|---|
| Branch | 测试枝子 |

## 关系

（无）

## same_as

（无）

```cleanup-json
{
  "nodes": [
    {
      "label": "Branch",
      "name": "测试枝子",
      "element_id": "4:48949551-42d5-4362-b0a9-669f57309030:16"
    }
  ],
  "relationships": [],
  "same_as": []
}
```

## 确认删除

按上一份清单删除，没有重新扫描。

- 删除前节点数：**2484**
- 删除前关系数：**45699**
- 删除后节点数：**2483**
- 删除后关系数：**45699**
