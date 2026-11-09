# qa4 目录骨架建立报告

> 任务：在 `G:\copypan` 下建立 `qa4/` 独立目录骨架（仅说明与占位，不建容器、不放数据）。  
> 日期：2026-11-09。未改已跟踪文件；未改仓库根 `.gitignore`；未做 git 提交。

## 已完成内容

1. 子目录：`docs` / `infra` / `data_prep` / `backend` / `frontend` / `eval` / `tests`（各含中文 `README.md`）。
2. `qa4/README.md`：定位、与 3.0 QA / 纲目并存关系、命名约定、原则、当前状态「建设中」。
3. `qa4/.env.example`：仅变量名，值全部为空。
4. `qa4/.gitignore`：忽略 `.env`、`*.dump`、`*.jsonl`、`data/`、`graph_annotations/*.json`、`__pycache__`、`node_modules`、`dist`、日志等。
5. `qa4/docs/DATA_MANIFEST.md`：外部大数据清单（已知路径/大小；未核 SHA 写「待补」；`neo4j.dump` 已填完整 SHA256）。
6. 将 `docs/qa4_survey/qa_site_flow.md`、`docs/qa4_data/probe_local.md` **复制**入 `qa4/docs/`，SHA256 一致后**删除原件及空目录**。

## 验证

### 1. git status --short

```
?? docs/panai4_graph/export_pack.md
?? docs/panai4_graph/git_merge_conflict.md
?? docs/panai4_graph/git_merge_resolve.md
?? qa4/
```

- 出现 `?? qa4/`。
- `docs/qa4_survey/`、`docs/qa4_data/` **不再出现**。
- 其余未跟踪项（`docs/panai4_graph/*`）与任务前相同。
- 已跟踪文件无改动。

### 2. 移动报告 SHA256 对照

| 文件 | 移动前 SHA256 | 移动后路径 | 移动后 SHA256 | 一致 |
|------|---------------|------------|---------------|------|
| qa_site_flow.md | `EEF78598D42A35F98B2EA29A15B3243C233FC6B5C9DD4E3C37EDF8160E58B611` | `qa4/docs/qa_site_flow.md` | `EEF78598D42A35F98B2EA29A15B3243C233FC6B5C9DD4E3C37EDF8160E58B611` | 是 |
| probe_local.md | `144D88F2B491AABAA312AA3058544FC7D18096061A2216A36E791FD407A73222` | `qa4/docs/probe_local.md` | `144D88F2B491AABAA312AA3058544FC7D18096061A2216A36E791FD407A73222` | 是 |

### 3. git check-ignore

**应被忽略**（`git check-ignore -q` 退出码 0；`-v` 示例如下）：

```
qa4/.gitignore:2:.env	qa4/.env
qa4/.gitignore:7:*.dump	qa4/x.dump
qa4/.gitignore:12:**/data/	qa4/data/a
```

**不应被忽略**（`git check-ignore -q` 退出码 1）：

| 路径 | ignored_exit |
|------|--------------|
| qa4/README.md | 1（未忽略） |
| qa4/.env.example | 1（未忽略；`-v` 可能显示否定规则 `!.env.example`，实际仍跟踪） |

### 4. qa4/.env.example 内容（值均为空）

```
QA4_ES_HOST=
QA4_ES_PORT=
QA4_ES_USERNAME=
QA4_ES_PASSWORD=
QA4_NEO4J_URI=
QA4_NEO4J_USER=
QA4_NEO4J_PASSWORD=
```

### 5. qa4/ 完整目录树

```
qa4/
├── .env.example
├── .gitignore
├── README.md
├── backend/
│   └── README.md
├── data_prep/
│   └── README.md
├── docs/
│   ├── DATA_MANIFEST.md
│   ├── README.md
│   ├── probe_local.md
│   ├── qa_site_flow.md
│   └── skeleton_report.md
├── eval/
│   └── README.md
├── frontend/
│   └── README.md
├── infra/
│   └── README.md
└── tests/
    └── README.md
```

（上表在写入本报告前采集；含本文件 `skeleton_report.md`。）
