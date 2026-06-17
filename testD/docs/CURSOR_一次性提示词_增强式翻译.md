# Cursor 一次性提示词：增强式翻译（工具在 testD，主工程最小漏油）

> **用法**：复制「━━━ 复制起点 ━━━」～「━━━ 复制终点 ━━━」给 Cursor Agent。  
> **架构**：**全部业务代码放在 `testD/`**；主工程只改 **3～4 处「漏油」接线**，让老师能在**服务器工具箱**打开功能。

---

## 教师说明

| 原则 | 说明 |
|------|------|
| 工具放哪 | **只在 `copypan/testD/`** 实现（service、router、页面组件） |
| 主工程改什么 | **仅** `ToolBox.vue` + 路由 + `main.py` 挂路由（+ 可选 1 行 vite alias） |
| **禁止** | 把 `enhanced_translate_*.py` 复制进 `back_mic/backend/kg_rag/`；**禁止**把 `EnhancedTranslate.vue` 复制进 `front_mic/.../toolbox/` |
| 老师验收 | 学生部署后，打开**服务器** `#/tools` → **Sotchea 测试** → **增强式翻译** |

```
┌─────────────────────────────────────────────────────────┐
│  front_mic（主前端）                                      │
│    ToolBox.vue  ──仅新增──► Sotchea 卡片 + go(...)      │
│    router/index.js ──仅新增──► 路由指向 testD 下 .vue    │
└───────────────────────────┬─────────────────────────────┘
                            │ 引用（不复制文件）
┌───────────────────────────▼─────────────────────────────┐
│  testD/（学生作业区，全部逻辑在此）                         │
│    backend/enhanced_translate_service.py                  │
│    backend/enhanced_translate_router.py                   │
│    frontend/src/components/EnhancedTranslate.vue          │
└───────────────────────────┬─────────────────────────────┘
                            │ import 主工程能力
┌───────────────────────────▼─────────────────────────────┐
│  back_mic/backend（只读复用 + 漏油挂载）                  │
│    es_config / kg_rag.retrieval / ai_search Gemini ...    │
│    main.py ──仅增加── include_router(testD.router)        │
└─────────────────────────────────────────────────────────┘
```

---

## ━━━ 复制起点 ━━━

请实现「增强式翻译」：**代码主体在 `testD/`**，主工程**最小漏油**（见下文「主工程仅允许修改的 4 处」）。必须写真实文件并自检。

---

## 一、`testD/` 目录（业务全部在此）

```text
copypan/testD/
├── README.md
├── SUBMISSION.md              # 学生填：服务器 URL、git hash、截图说明
├── TEACHER_CHECKLIST.md       # 老师线上验收表
├── WIRING.md                  # 主工程 4 处漏油说明（给老师和学生对照）
├── backend/
│   ├── __init__.py
│   ├── _bootstrap.py          # 将 back_mic/backend 加入 sys.path（包内 import 主工程用）
│   ├── enhanced_translate_service.py
│   ├── enhanced_translate_router.py
│   └── app.py                 # 可选：仅本地单独调试后端时用，上线不靠它
└── frontend/
    └── src/
        ├── components/
        │   └── EnhancedTranslate.vue
        └── ...                # 可选 testD 沙箱前端；上线走主站路由引用本组件即可
```

### 1.1 后端 API 路径（上线与主站一致）

`enhanced_translate_router.py` 使用：

```python
router = APIRouter(prefix="/api/kg_rag", tags=["kg_rag"])
```

| 路径 | 说明 |
|------|------|
| `POST /api/kg_rag/enhanced_translate` | `{ content, prompt_override? }` → `{ result, refs, error }` |
| `POST /api/kg_rag/enhanced_translate/update_prompt` | `{ prompt }` → `{ success: true }` |

主站前端已有 Vite/nginx 把 `/api` 代理到 `back_mic`，**无需**再搞 `/api/testd`。

下载仍用主工程：`POST /api/ai_search/format_outline_only`，`direction: "zh2en"`。

### 1.2 `enhanced_translate_service.py` 要点

在 `_bootstrap.ensure_main_backend_path()` 之后：

```python
load_dotenv(ensure_main_backend_path() / ".env")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-pro")
GEMINI_TRANSLATION_FALLBACK_MODEL = os.getenv("GEMINI_TRANSLATION_FALLBACK_MODEL", "gemini-2.5-flash")
```

复用（**必须 await**，`_INDICES_BASE` 为 **str**）：

```python
from kg_rag.kg_rag_service import _INDICES_BASE
from kg_rag.retrieval import bm25_search, dense_search, rrf_merge, rerank
from es_config import es as es_client
from ai_search.ai_service import gemini_client, GEMINI_SEMAPHORE, _gemini_error_is_retryable
from ai_search.gemini_translation_instruction import GEMINI_TRANSLATION_SYSTEM_INSTRUCTION
from ai_search.gemini_response_utils import gemini_translation_generate_config, extract_translatable_text
```

实现：`_strip_scripture_suffix`、`_split_body`、`_exact_match`、`_retrieve_top1`、`_enrich_hit_en`、`_translate_one_line`、`enhanced_translate`（含 `refs`）、Gemini 重试/降级（同 `translate_outline`）。

### 1.3 `EnhancedTranslate.vue`（只在 testD）

- 参考只读：`front_mic/.../OutlineTranslate.vue`（不要复制进 front_mic）
- 翻译：`POST /api/kg_rag/enhanced_translate`
- 更新 Prompt：`POST /api/kg_rag/enhanced_translate/update_prompt`
- 下载：`POST /api/ai_search/format_outline_only`，`zh2en`
- 参考语料折叠区；直接引用绿 `#389e0d`、参考翻译蓝 `#1677ff`
- 顶部栏：可复制主站 `ToolsHeader` 的**最小实现**到 `testD/frontend/src/components/ToolsHeader.vue`，或用相对路径 import 主站组件（见漏油第 4 处 vite alias）

---

## 二、主工程「漏油」— 仅允许修改以下 4 处

> **除此以外**的 `back_mic/**`、`front_mic/**` 文件**不得修改**。  
> 若仓库里已有旧的 `back_mic/backend/kg_rag/enhanced_translate_*.py`，应**删除或改由 testD 提供**，避免两套实现并存。

### 漏油 ① `ToolBox.vue`（必做，老师看这个入口）

在 `Piseth & Sopheap 测试` 卡片**正下方**增加：

```vue
    <br />
    <br />
    <div class="cards">
      <a-card>
        <template #title>
          <div class="card_title">Sotchea 测试</div>
        </template>
        <a-card-grid class="card c2" @click="go('/enhanced-translate')">
          <span class="card_text">增强式翻译</span>
        </a-card-grid>
      </a-card>
    </div>
```

**只加这一块**，勿改其它工具卡片。

### 漏油 ② `front_mic/frontend/src/router/index.js`（必做）

在 `/outline-translate` 后增加路由，**组件来自 testD**（不复制到 toolbox 目录）：

```javascript
  {
    path: "/enhanced-translate",
    component: () =>
      import(
        "../../../../testD/frontend/src/components/EnhancedTranslate.vue"
      ),
    meta: { requiresAuth: true },
  },
```

路径层级以仓库实际相对深度为准；也可用漏油 ④ 的 alias：`import("@testd/components/EnhancedTranslate.vue")`。

### 漏油 ③ `back_mic/backend/main.py`（必做，服务器 API 靠它挂上）

在其它 `include_router` 附近增加（**不要**再从 `kg_rag.enhanced_translate_router` import，改从 testD）：

```python
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]  # copypan 根目录
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from testD.backend.enhanced_translate_router import router as enhanced_translate_router
# ...
app.include_router(enhanced_translate_router)
```

若已存在 `from kg_rag.enhanced_translate_router import ...`，**改为**上面 testD 的 import，并删除 `back_mic/backend/kg_rag/enhanced_translate_service.py` 与 `enhanced_translate_router.py`（若存在），避免重复。

### 漏油 ④ `front_mic/frontend/vite.config.js`（推荐，非必须）

在 `resolve.alias` 增加一行，便于 testD 组件 import 主站工具：

```javascript
'@testd': resolve(__dirname, '../../testD/frontend/src'),
'@main': resolve(__dirname, 'src'),
```

则 `EnhancedTranslate.vue` 可写：

```javascript
import ToolsHeader from '@main/components/toolbox/ToolsHeader.vue'
import { toastSuccess, toastError, toastWarning } from '@main/utils/Dialog'
```

**仅增加 alias**，勿改其它构建配置。

---

## 三、部署与老师验收（必做）

### 3.1 构建与部署

```bash
cd front_mic/frontend && npm run build
# 服务器：git pull + build + 重启 back_mic uvicorn（同项目 deploy.sh）
```

服务器**只跑主后端 + 主前端 dist**，不单独部署 testD 的 8007/5174。

### 3.2 学生填写 `testD/SUBMISSION.md`

必填：**服务器 URL**（`https://域名/#/tools`）、git commit、测试纲目两行（含分号 / 含经文）。

### 3.3 老师 `testD/TEACHER_CHECKLIST.md`

| # | 验收项 |
|---|--------|
| 1 | 服务器登录后打开 **工具箱**，见 **Sotchea 测试** |
| 2 | 进入 **增强式翻译**，非 404 |
| 3 | 翻译成功，Network 为 **`/api/kg_rag/enhanced_translate`** 且 200 |
| 4 | 参考语料展开，绿/蓝标签正确 |
| 5 | 仓库有完整 **`testD/`**，主工程仅上述 4 处漏油 diff 可控 |

### 3.4 `testD/WIRING.md`

Cursor 生成简短文档，列出 4 处漏油的文件路径与改动摘要，方便老师 code review。

---

## 四、本地开发两种方式（写入 testD/README.md）

**方式 A（推荐，与线上一致）**

1. 完成 testD 代码 + 4 处漏油  
2. `uvicorn main:app --port 8000` + `cd front_mic/frontend && npm run dev`  
3. 打开 `http://localhost:5173/#/tools` → Sotchea → 增强式翻译  

**方式 B（仅调试 testD 后端逻辑）**

- `testD/backend/app.py` + `_bootstrap`，端口 8007  
- 仍需要主后端 8000 提供登录与 ES  

---

## 五、完成后自检（Agent 必须报告）

1. 列出 **`testD/`** 下所有新建文件。  
2. 列出主工程**仅** 4 处漏油文件的 diff 摘要。  
3. 确认**没有** `front_mic/.../toolbox/EnhancedTranslate.vue`（应在 testD）。  
4. 确认**没有**（或已删除）`back_mic/backend/kg_rag/enhanced_translate_*.py` 重复实现。  
5. `npm run build` 成功；`python -c "from testD.backend.enhanced_translate_service import enhanced_translate"` 在 `PYTHONPATH=仓库根` 下成功。  
6. 说明 `_split_body` 对分号行、经文行的处理。

---

## 常见错误

| 现象 | 原因 |
|------|------|
| 老师看不到 Sotchea | 未改 `ToolBox.vue` 或未部署新 dist |
| 404 页面 | 漏油 ② 路径错或组件不在 testD |
| API 404 | 漏油 ③ 未 include_router 或 `PYTHONPATH` 未含仓库根 |
| 仍有两套 backend | kg_rag 里旧文件未删，与 testD 并存 |
| build 找不到 testD 组件 | 相对 import 层级错；用 alias 修复 |

---

## ━━━ 复制终点 ━━━

---

## 给学生的话

1. **工具在 testD**，主工程只「接一根线」——**可以**，且污染最小。  
2. 交作业 = **testD 完整代码** + **4 处漏油** + **服务器能打开工具箱里的 Sotchea**。  
3. 详细逻辑见 `docs/CURSOR_增强式翻译完整实现指令.md`；**接线方式以本文为准**。
