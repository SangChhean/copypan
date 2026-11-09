# qa4 — PanAI 4.0 问答独立目录

本目录是 **4.0 问答** 的独立工作区，把后端、前端、装库脚本、评估与文档收拢在一处，便于整体交接。

## 与现有系统的关系

| 系统 | 位置（参考） | 关系 |
|------|--------------|------|
| 3.0 问答（现有 QA 站） | `back_qa/`、`front_qa/` | **并存、互不影响**；本目录不改其代码与运行环境 |
| 纲目 / PanAI 主站等 | `back_mic/` 等 | **并存、互不影响**；qa4 不依赖其进程或索引前缀 |

建设过程中可只读参考现有实现；落地代码按下方原则**复制进 qa4**，而不是从业务仓直接 `import`。

## 目录说明

| 子目录 | 用途 |
|--------|------|
| `docs/` | 设计说明、摸底与骨架报告等 |
| `infra/` | 容器与部署配置（`docker-compose.neo4j.yml` / `docker-compose.es.yml` 拆分，挂载约定等） |
| `data_prep/` | 装库、核对、同步脚本（只服务 qa4 这一侧） |
| `backend/` | 4.0 问答后端 |
| `frontend/` | 4.0 问答前端（将重新设计，与主站及现有 QA 站分开） |
| `eval/` | 评估题集与评估脚本 |
| `tests/` | 测试 |

## 命名约定

| 类别 | 约定 |
|------|------|
| 容器 | `qa4-neo4j`、`qa4-es` |
| 数据卷 | `qa4_*` |
| ES 索引 | `qa4_*` |
| 环境变量 | `QA4_*`（见 `.env.example`） |

## 原则

1. **共用逻辑复制进 qa4**，不直接 `import` 现有 `back_qa` / `back_shared` / `kg_rag` 业务路径（避免交接时扯不断依赖）。
2. **大数据与密钥不进 git**：`.env`、dump、jsonl、数据目录、图谱大 JSON 等由 `.gitignore` 忽略；外部数据路径记在 `docs/DATA_MANIFEST.md`。
3. **当前状态：建设中**（仅骨架与说明，尚未建容器、未导入数据）。

## 相关文档

- `docs/DATA_MANIFEST.md` — 外部大数据清单  
- `docs/qa_site_flow.md` — 现有 3.0 QA 站全链路摸底（参考）  
- `docs/probe_local.md` — 本机 Docker / ES / Neo4j / 数据包摸底（参考）  
- `docs/skeleton_report.md` — 本骨架任务验证记录  
