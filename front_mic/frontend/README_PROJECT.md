# Vue 项目初始化完成

## 已完成配置

### 1. **package.json**
- Vue 3 + Vue Router
- Vite 构建工具
- 脚本：`npm run dev`、`npm run build`、`npm run preview`

### 2. **vite.config.js**
- Vue 插件
- 路径别名：`@` → `src`
- 开发服务器：`http://localhost:5173`
- API 代理：`/api`、`/search`、`/cws`、`/reading` → `http://localhost:8000`

### 3. **index.html**
- 入口脚本改为：`<script type="module" src="/src/main.js"></script>`
- 开发模式下由 Vite 处理，生产构建时会自动替换为打包后的 JS

### 4. **依赖安装**
- `npm install` 已完成，`node_modules/` 已生成
- `.gitignore` 已创建（忽略 `node_modules/`、`dist/` 等）

### 5. **现有文件未被覆盖**
- `src/App.vue`、`src/main.js`、`src/router/index.js`
- `src/components/AIChat.vue`、`src/components/SearchPage.vue`
- `fonts/`、`imgs/`、`style/`、旧 `assets/` (构建产物)

---

## 启动项目

### 开发模式

```bash
cd e:\copypan\front_mic\frontend
npm run dev
```

访问 `http://localhost:5173`，路由：

- **`#/search`**：新搜索页（传统搜索 + AI 问答 Tab）
- **`#/search-ai`**：同上（备用路径）
- **`#/ai-assistant`**：AI 对话页

### 构建生产版

```bash
npm run build
```

生成 `dist/` 可部署到服务器。

---

## 项目结构

```
frontend/
├── index.html          # 入口 HTML（开发时指向 src/main.js）
├── package.json        # npm 配置
├── vite.config.js      # Vite 配置
├── .gitignore          # Git 忽略
├── src/
│   ├── main.js         # Vue 应用入口
│   ├── App.vue         # 根组件
│   ├── router/
│   │   └── index.js    # 路由配置（/search、/ai-assistant 等）
│   ├── components/
│   │   ├── SearchPage.vue  # 搜索页（传统 + AI Tab）
│   │   └── AIChat.vue      # AI 对话页
│   └── README_AI.md    # AI 功能说明
├── style/              # 全局样式
├── fonts/              # 字体
├── imgs/               # 图片
└── assets/             # 旧构建产物（可删除或保留作参考）
```

---

## 注意事项

1. **后端启动**：前端 API 代理到 `http://localhost:8000`，需先启动后端（`python main.py`）
2. **环境变量**（可选）：可在 `.env` 中配置 `VITE_API_BASE=http://your-server:8000`
3. **旧 `assets/` 目录**：为旧构建产物，可保留或删除（新构建会生成新的 `dist/`）
