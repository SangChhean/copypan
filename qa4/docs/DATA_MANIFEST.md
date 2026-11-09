# 外部大数据清单（DATA_MANIFEST）

> 大数据与密钥不进 git。本表记录**仓库外**（或被 `.gitignore` 忽略）的数据包位置与核验信息。  
> SHA256 已用本机 `Get-FileHash -Algorithm SHA256` 核对（2026-11-09）。

| 名称 | 路径 | 大小（字节） | SHA256 | 说明 |
|------|------|--------------|--------|------|
| neo4j.dump | `G:\PanAI4.0专用\图谱上线\neo4j.dump` | 10,507,204 | `B5B0C10C657E0FF03309A6D21603DC11B3152D66037F499EAD266948721089C4` | PanAI 4.0 图谱 dump；与本机 `neo4j-v4` 基线一致 |
| PanAI4.0_ES数据包_20261107.zip | `G:\PanAI4.0专用\数据包\PanAI4.0_ES数据包_20261107.zip` | 2,764,415,696 | `A61457CDBFAF33EA34F082A0014A0DB6673CAF0CDEC509EAD6B2A4A59C8FD21B` | ES 十索引导入包（含 `es/import_to_local_es.py`） |
| PanAI4.0_图谱数据包_20261107.zip | `G:\PanAI4.0专用\数据包\PanAI4.0_图谱数据包_20261107.zip` | 29,298,212 | `4803ADB9E8EDECCA06F4DA7F76066BCD2A473F5C67AC7BBA4E1A5B6C27ACAAA9` | 图谱 dump + 两份 graph_annotations JSON + load 脚本 |
| organic_advance.json（源） | `G:\copypan\back_mic\backend\panai4\data\graph_annotations\organic_advance.json` | 38,800,482 | `63A2320504C535E5B54D6AC8B33E0F76CAFDFA5D330EDFE9CCBBAA15ABFB8178` | 图谱外置大 JSON（业务仓源） |
| truth_dictionary_3a3b.json（源） | `G:\copypan\back_mic\backend\panai4\data\graph_annotations\truth_dictionary_3a3b.json` | 31,627,640 | `98721FD096CBDB1E10080089D22FEDBA3A7973EB0F2C7B2F9BC14B66F3E7DAC1` | 图谱外置大 JSON（业务仓源） |
| organic_advance.json（qa4 副本） | `qa4/data/graph_annotations/organic_advance.json` | 38,800,482 | 同源（复制后 SHA 一致） | 供 qa4 交接使用；被 gitignore |
| truth_dictionary_3a3b.json（qa4 副本） | `qa4/data/graph_annotations/truth_dictionary_3a3b.json` | 31,627,640 | 同源（复制后 SHA 一致） | 供 qa4 交接使用；被 gitignore |

补充说明：

- 索引源数据与向量目录根：`G:\PanAI4.0专用\索引数据\`（十个 `panai4_*` 子目录）；总体积大，细节见 `probe_local.md`。装入 qa4 后索引名约定为 `qa4_*`。
- 本机现有 ES 容器仍使用 `panai4_*`；qa4 独立 ES 容器建立前勿混淆。

## qa4-es 内容核对

将仓库外 `panai4_*`（`elasticsearch8` / `docker-cluster`，`127.0.0.1:9200`）与 `qa4_*`（`qa4-es` / cluster `qa4`，`127.0.0.1:9202`，镜像 `8.19.0-ik`）做只读对照后的固化结论见：

- 报告：[`qa4/docs/es_equivalence_report.md`](es_equivalence_report.md)
- 最终全量验证：`G:\PanAI4.0专用\logs\qa4_verify_20261109_154127.json`（及同名 `.log` / `.md`）
- hymns kNN 收尾（判据修改后）：`G:\PanAI4.0专用\logs\qa4_verify_20261109_161710.json`
- 诊断原始产物：`G:\PanAI4.0专用\logs\qa4_verify_diag_20261109_151150.json`（及同名 `.log` / `.md`）
- 历史全量（判据修订前）：`G:\PanAI4.0专用\logs\qa4_verify_20261109_151505.json`

要点（细节与数字以报告及 JSON 为准）：content 以去掉顶层 null 键后相等为准；BM25 仅 `text_life` / `outline_12490` 有分数相对偏差且未计 FAIL；hymns kNN 两例为重复向量并列（无害），161710 PASS；除该 knn 判据外无其他放宽。
