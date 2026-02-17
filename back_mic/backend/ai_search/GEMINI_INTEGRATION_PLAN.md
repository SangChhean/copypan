# Gemini 英文纲目接入完整计划

## 一、目标与约定（回顾）

- **Claude**：从中文库检索 → 生成**中文纲目**（现有逻辑不变）。
- **Gemini**：仅当用户点击「同时生成英文纲目」时，将**已有中文纲目**翻译成英文。
- **流程**：先展示中文纲目 → 若用户勾选「同时生成英文纲目」→ 前端调翻译接口 → 第二区块显示「正在生成英文纲目…」→ 展示英文纲目；失败则重试 1 次，仍失败则只保留中文。
- **翻译要求**：使用 `gemini_translation_instruction.py` 中的 `GEMINI_TRANSLATION_SYSTEM_INSTRUCTION`（术语表两遍，已就绪）。

---

## 二、后端

### 2.1 依赖与环境

| 步骤 | 内容 |
|------|------|
| 1 | 在 `requirements.txt` 中增加：`google-generativeai>=0.8.0`（或当前稳定版）。 |
| 2 | 在 `.env` / 部署环境增加：`GEMINI_API_KEY`（Google AI Studio 的 API Key）。可选：`GEMINI_MODEL=gemini-2.5-pro`，不配则代码里写死默认。 |

### 2.2 Gemini 客户端初始化（ai_service.py）

| 步骤 | 内容 |
|------|------|
| 1 | 读取 `GEMINI_API_KEY`、`GEMINI_MODEL`（默认 `gemini-2.5-pro`）。 |
| 2 | 若存在 `GEMINI_API_KEY`：`genai.configure(api_key=...)`；`GenerativeModel(model_name=GEMINI_MODEL, system_instruction=GEMINI_TRANSLATION_SYSTEM_INSTRUCTION)`，保存为模块级变量（如 `gemini_translation_model`），供翻译方法使用。 |
| 3 | 若未配置 key，`gemini_translation_model = None`；翻译接口被调用时返回「未配置」类错误。 |
| 4 | 从 `gemini_translation_instruction` 导入 `GEMINI_TRANSLATION_SYSTEM_INSTRUCTION`。 |

### 2.3 翻译方法（ai_service.py）

| 步骤 | 内容 |
|------|------|
| 1 | 新增方法：`translate_outline(self, chinese_outline: str) -> Dict`。 |
| 2 | 入参校验：`chinese_outline` 为空或过长（如 > 50000 字符）直接返回错误。 |
| 3 | **缓存**：缓存 key = `ai_search:translate:{hash(chinese_outline)}`（如 SHA256 前 32 字符），value = JSON `{"answer_en": "..."}`；TTL 建议 24 小时或与主搜索缓存一致。若命中则直接返回，不调 Gemini。 |
| 4 | **调用 Gemini**：`response = gemini_translation_model.generate_content(chinese_outline)`，取 `response.text` 作为 `answer_en`。 |
| 5 | **重试**：若调用抛异常（网络、限流、5xx 等），重试 1 次（相同入参）；若仍失败，返回 `{"answer_en": None, "error": "翻译失败，请稍后重试"}` 或类似，不抛异常。 |
| 6 | 成功：写入缓存，返回 `{"answer_en": "..."}`。 |
| 7 | 未配置 Gemini（`gemini_translation_model is None`）：返回 `{"answer_en": None, "error": "英文翻译服务未配置"}`。 |

### 2.4 路由（ai_router.py）

| 步骤 | 内容 |
|------|------|
| 1 | 新增请求体模型：`TranslateOutlineRequest`，字段 `chinese_outline: str`（必填，max_length=50000 或 100000）。 |
| 2 | 新增接口：`POST /api/ai_search/translate_outline`，请求体 `TranslateOutlineRequest`，返回 `{"answer_en": str | null, "error": str | null}`。 |
| 3 | 实现中调用 `ai_service.translate_outline(request.chinese_outline)`，按返回结构直接返回；若服务端异常则 500 并带简要 message。 |

### 2.5 健康检查（ai_service.py + ai_router.py）

| 步骤 | 内容 |
|------|------|
| 1 | 在 `health_check()` 返回的 `status` 字典中增加 `gemini: bool`。 |
| 2 | `gemini = bool(GEMINI_API_KEY)`（或再 ping 一次 Gemini 简单请求，可选）；不影响 `overall`（overall 仍为 ES + Claude）。 |
| 3 | 前端/运维可通过 `/api/ai_search/health` 查看 `services.gemini` 是否为 true。 |

---

## 三、前端

### 3.1 需改动的页面

- **Search.vue**：主 AI 纲目流程（search_only → generate_only），展示中文纲目后可选「同时生成英文纲目」并调翻译。
- **SearchPage.vue**：一步调用 `/api/ai_search` 的页面，同样需要「中文纲目 / 英文纲目」双区块 + 可选翻译。
- **AIChat.vue**：若也展示纲目结果，建议与上面保持一致（勾选 + 双区块 + 调翻译）；若当前仅聊天风格可暂只加「中文/英文」双区块与翻译入口。

### 3.2 Search.vue（分步流程）

| 步骤 | 内容 |
|------|------|
| 1 | 在表单区域增加**复选框**：「同时生成英文纲目」，绑定变量如 `includeEnglishOutline`。 |
| 2 | 现有「AI 回答」区块改为**第一区块**：「中文纲目」标题 + 现有 `aiAnswerFormatted` 内容 + 复制按钮（仅复制中文）。 |
| 3 | 新增**第二区块**：「英文纲目」标题。初始无内容；当 `includeEnglishOutline === true` 且已有中文纲目时：先显示「正在生成英文纲目…」局部 loading，然后调用 `POST /api/ai_search/translate_outline`，body `{ chinese_outline: aiResult.answer }`。 |
| 4 | 请求返回后：若 `answer_en` 有值，在第二区块展示（可复用与中文类似的格式化/换行）；若 `error` 有值，显示「英文纲目生成失败」或 `error` 文案；并有关闭 loading。 |
| 5 | 第二区块增加「复制英文」按钮，仅复制 `answer_en`。 |
| 6 | 翻译请求建议超时 60s；重试由后端完成，前端只根据最终返回展示成功/失败。 |

### 3.3 SearchPage.vue（一步流程）

| 步骤 | 内容 |
|------|------|
| 1 | 同样增加复选框「同时生成英文纲目」，绑定变量 `includeEnglishOutline`。 |
| 2 | 在现有「回答」下方拆成两区块：「中文纲目」与「英文纲目」。中文纲目即当前 `aiResult.answer`。 |
| 3 | 当 `includeEnglishOutline` 为 true 且 `aiResult.answer` 已有内容时：第二区块先显示「正在生成英文纲目…」，再请求 `POST /api/ai_search/translate_outline`，body `{ chinese_outline: aiResult.answer }`。 |
| 4 | 根据返回的 `answer_en` / `error` 展示英文内容或失败提示，并各加「复制」按钮。 |

### 3.4 AIChat.vue（若展示纲目）

| 步骤 | 内容 |
|------|------|
| 1 | 若当前有展示「纲目」类回答：增加「同时生成英文纲目」选项 + 中文/英文双区块 + 调用 `translate_outline`，逻辑与 Search.vue 对齐。 |
| 2 | 若为纯对话、不单独展示纲目，可暂只保证后端接口可用，前端稍后再接。 |

### 3.5 样式与体验

- 中文纲目、英文纲目**分块展示**，便于分别复制。
- 英文区块的 loading 使用**局部** loading（如该区块内 spinner + 「正在生成英文纲目…」），不整页遮罩。
- 复制按钮：中文区块复制 `answer`，英文区块复制 `answer_en`；复制成功可统一 toaster 提示。

---

## 四、实现顺序建议

1. **后端**  
   - 依赖 + 环境变量  
   - Gemini 客户端初始化 + `translate_outline`（含缓存、重试）  
   - 路由 `POST /api/ai_search/translate_outline`  
   - 健康检查增加 `gemini`

2. **自测后端**  
   - 用 curl/Postman 调 `translate_outline`，传入一段中文纲目，检查返回 `answer_en` 与缓存、重试行为。  
   - 检查 `health_check` 中 `gemini` 是否为 true/false。

3. **前端**  
   - 先改 **Search.vue**（主流程）：勾选 + 双区块 + 调用翻译 + 双复制。  
   - 再改 **SearchPage.vue**：同样勾选 + 双区块 + 翻译 + 双复制。  
   - 最后按需改 **AIChat.vue**。

4. **联调与上线**  
   - 全流程：选「同时生成英文纲目」→ 出中文 → 出英文 → 分别复制。  
   - 故意断网或错误 key 测「翻译失败」与重试 1 次的体验。  
   - 部署时确保 `GEMINI_API_KEY`、`GEMINI_MODEL` 已配置。

---

## 五、文件清单（改动/新增）

| 类型 | 文件 |
|------|------|
| 后端 | `requirements.txt`（+ google-generativeai） |
| 后端 | `ai_search/ai_service.py`（Gemini 初始化、translate_outline、health_check 增加 gemini） |
| 后端 | `ai_search/ai_router.py`（TranslateOutlineRequest、POST translate_outline、health 返回 gemini） |
| 后端 | `ai_search/gemini_translation_instruction.py`（已存在，无需改） |
| 前端 | `Search.vue`（勾选、双区块、翻译请求、双复制） |
| 前端 | `SearchPage.vue`（同上） |
| 前端 | `AIChat.vue`（按需：勾选、双区块、翻译） |
| 配置 | `.env.example` 或部署文档中补充 `GEMINI_API_KEY`、`GEMINI_MODEL` 说明 |

---

## 六、验收标准

- [ ] 不勾选「同时生成英文纲目」时，行为与现网一致，仅展示中文纲目。  
- [ ] 勾选后，中文纲目先出现，英文区块显示「正在生成英文纲目…」，再展示英文或失败提示。  
- [ ] 同一份中文纲目再次请求翻译时，命中缓存，无二次调用 Gemini。  
- [ ] Gemini 首次失败时自动重试 1 次；仍失败时仅提示错误，保留中文纲目。  
- [ ] 中文、英文区块可分别复制，且复制内容正确。  
- [ ] `/api/ai_search/health` 中能正确反映 `gemini` 是否可用。

完成以上即视为 Gemini 英文纲目接入完成。
