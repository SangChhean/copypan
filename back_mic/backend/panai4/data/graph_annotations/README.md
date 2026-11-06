# organic_advance.json

## 这是什么

「生机关联的进展」（organic advance）专特标注的**内容文件**，共 **69** 个词条。

每条含：`name`、`series`、`stages`、`content_1` … `content_6`；每个 content 项含 `title`、`book`、`date`、`source`、`outline`（职事原文）。

## 来源

- 桌面源路径：`C:\Users\28121\Desktop\可导入资料\特殊标注\【organic_advance】生机关联的进展.json`
- 大小：38800482 字节
- SHA256：`63a2320504c535e5b54d6ac8b33e0f76cafdfa5d330edfe9ccbbaa15abfb8178`
- 复制日期：2026-11-06 22:11:04

## 与图谱的关系

图谱里 `Truth_Point` 节点的标注 `organic_advance = true` **只表示**：该词条在本文件里有内容。

内容本身**不在**图谱里；检索时按词条名 `name` 到本文件取。

这是例外：其他专特标注的内容都在图谱节点里。

## 部署

服务器上需在同一相对路径放一份（相对仓库根）：

`back_mic/backend/panai4/data/graph_annotations/organic_advance.json`

读取时用相对于仓库根的路径，不要写死盘符。

本文件体积大，**不进 git**，需要单独备份与部署。

词条改名或删除后，要核对本文件里的 `name` 与图谱是否一致。

---

# truth_dictionary_3a3b.json

## 这是什么

「真理词典」3a/3b **正文**内容文件，共 **2372** 个词条。

每条含：`id`、`title`、`content_3a`、`content_3b`。

## 来源

- 桌面源路径：`C:\Users\28121\Desktop\可导入资料\真理词典：3a和3b.json`
- 大小：31627640 字节
- SHA256：`98721fd096cbdb1e10080089d22fedba3a7973eb0f2c7b2f9bc14b66f3e7dac1`
- 复制日期：2026-11-06 22:30:42

## 与图谱的关系

图谱 **不存** 正文。`Truth_Point` 上仅有布尔标注：
- `definition_3a = true`（全部有 3a 正文的词条）
- `definition_3b = true`（仅 `content_3b` 非空的词条；空则不写该标注）

检索正文时按词条名到本文件取（JSON 的 `title` 对应源名；括号词在源里为整体名如「妇人（女人）」，图谱节点为括号外名）。

服务器上需在同一相对路径放一份：`back_mic/backend/panai4/data/graph_annotations/truth_dictionary_3a3b.json`。

本文件体积大，**不进 git**，需单独备份与部署。
