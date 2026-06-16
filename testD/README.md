# testD — 增强式翻译

学生作业区：全部业务逻辑在本目录，主工程仅 4 处「漏油」接线（见 `WIRING.md`）。

## 功能

- 粘贴中文纲目 → 逐行/分句检索 ES 职事语料 → 带参考语料调用 Gemini 中翻英
- 参考语料：**直接引用**（绿 `#389e0d`）、**参考翻译**（蓝 `#1677ff`）
- 下载英文纲目 DOCX：主站 `POST /api/ai_search/format_outline_only`（`zh2en`）

## API（经主站 `back_mic` 挂载）

| 方法 | 路径 |
|------|------|
| POST | `/api/kg_rag/enhanced_translate` |
| POST | `/api/kg_rag/enhanced_translate/update_prompt` |

## 本地开发

### 方式 A（推荐，与线上一致）

1. 启动 ES / Redis（与 Pansearch 相同）
2. 配置 `back_mic/backend/.env`（含 `GEMINI_API_KEY`）
3. 主后端：`cd back_mic/backend && python main.py`（端口 8000）
4. 主前端：`cd front_mic/frontend && npm run dev`（端口 5173）
5. 登录后打开 `http://localhost:5173/#/tools` → **Sotchea 测试** → **增强式翻译**

### 方式 B（仅调试 testD 路由）

```bash
# 仓库根目录，PYTHONPATH 含 copypan
python -m uvicorn testD.backend.app:app --port 8010
```

仍需主站 8000 提供登录；API 路径与线上一致时需改请求指向 8010 或继续用方式 A。

## 目录

```text
testD/
├── backend/
│   ├── enhanced_translate_service.py
│   ├── enhanced_translate_router.py
│   ├── _bootstrap.py
│   └── app.py
├── frontend/src/components/EnhancedTranslate.vue
├── WIRING.md
├── SUBMISSION.md
└── TEACHER_CHECKLIST.md
```

## 常见问题（日志里 ES 503 / OpenRouter 401）

| 现象 | 原因 | 处理 |
|------|------|------|
| `POST .../_search [status:503]` | ES 未就绪、`kg-rag_*` 索引关闭或分片不可用 | 启动 Elasticsearch；用 `GET /_cat/indices/kg-rag*` 确认 `status=open`、`health` 非 red |
| `OpenRouter ... 401 Missing Authentication` | `.env` 未配置 `OPENROUTER_API_KEY` | 在 `back_mic/backend/.env` 填入 OpenRouter Key（向量检索用） |
| Gemini 200 但参考语料全为「无匹配」 | 上面两项导致检索被跳过 | 修好 ES + Key 后重试；仍会完成纯 Gemini 翻译 |

修复环境后**重启** `back_mic` 后端。

## `_split_body` 说明

- 正文含中文分号 `；`：拆成多个子句，分别检索与翻译，英文子句用 `; ` 连接。
- 无分号：整段作为一句处理。
- 仅行末读经后缀、无正文：不拆句，只翻译后缀（如 `—约三16：` → `—John 3:16:`）。
