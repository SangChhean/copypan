# AI 助手前端说明

## 已创建文件

- **src/components/AIChat.vue**：对话 UI（聊天气泡、加载动画、来源展示）
- **src/router/index.js**：路由，包含 `/ai-assistant`，使用 `AIChat` 组件
- **src/App.vue**、**src/main.js**：入口（若你已有入口，可只合并路由）

## API

- 使用 **POST /api/ai_search**，请求体：`{ question: string, max_results?: number }`
- 响应：`{ answer, sources[], cached?, tokens?, search_time?, ai_time?, total_time? }`
- 请求带 `credentials: 'include'`，与现有 cookie 登录一致

## 合并到现有项目

若项目已有 Vue Router，只需把 `/ai-assistant` 路由加进去：

```js
// 在你现有的 router 里添加
import AIChat from '@/components/AIChat.vue'

{
  path: '/ai-assistant',
  name: 'AIAssistant',
  component: AIChat,
  meta: { title: '圣经 AI 助手' }
}
```

并在导航里增加跳转：`#/ai-assistant` 或 `router.push({ name: 'AIAssistant' })`。

## 环境变量

- **VITE_API_BASE**：接口基础地址，留空则用当前域名。开发时若前后端分离，可设为 `http://localhost:8000`。

## 从零用 Vite 跑起来

若当前仓库只有构建产物、没有源码，可以用 Vite 新建入口并指向 `src`：

1. 在 `front_mic/frontend` 下执行：`npm create vite@latest . -- --template vue`（选合并或新建）
2. 或手动建 `package.json`、`vite.config.js`，entry 指向 `src/main.js`
3. 安装依赖：`npm i vue@3 vue-router@4`
4. 运行：`npm run dev`，访问 `http://localhost:5173/#/ai-assistant`
