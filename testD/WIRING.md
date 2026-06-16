# 主工程漏油清单（共 4 处）

| # | 文件 | 改动 |
|---|------|------|
| ① | `front_mic/frontend/src/components/toolbox/ToolBox.vue` | 在 Piseth & Sopheap 卡片下增加 **Sotchea 测试** → `/enhanced-translate` |
| ② | `front_mic/frontend/src/router/index.js` | 路由 lazy import `testD/frontend/src/components/EnhancedTranslate.vue` |
| ③ | `back_mic/backend/main.py` | `from testD.backend.enhanced_translate_router import router` + `include_router` |
| ④ | `front_mic/frontend/vite.config.js` | alias `@testd`、`@main` |

**禁止**：向 `back_mic/backend/kg_rag/` 或 `front_mic/.../toolbox/` 复制业务文件。
