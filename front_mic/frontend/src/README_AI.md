# AI 相关前端说明

本文件曾描述已移除的独立对话页与无子路径的通用 AI 检索接口接入方式，相关内容已删除。

当前仓库中与 AI / 纲目相关的主要入口：

- **主站**：`components/Index.vue`、`components/Search.vue`
- **KG-RAG 测试台**：`components/toolbox/KgRagTest.vue`（路由 `#/kg-rag-test`，需登录）

具体请求路径与请求体以各组件内对 `/api/...` 的调用为准。

## 环境变量

- **VITE_API_BASE**：接口基础地址；留空则使用当前页面同源。前后端分离开发时可设为 `http://127.0.0.1:8000` 等。
