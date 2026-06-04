# AI 纲目制作练习 — PanAI 2.0 设计方案

## 1. 项目概述

### 1.1 功能定位
在主站工具箱（`http://localhost/#/tools`）的「Vichhet & Chom Pei 测试」分组下，新增一个「AI纲目制作练习」入口，路由为 `/practice-kg-rag`。

用户输入纲目主题、选择纲目性质、填写负担说明，点击「生成纲目」后，后端执行 PanAI 2.0 三步流水线（检索 → Prompt 拼接 → Claude 生成），返回完整纲目文字。前端展示结果，并支持复制、下载 DOCX、下载 PDF。

### 1.2 技术栈
- 后端：FastAPI + Python，端口 8009，独立运行，不影响主站（8000）
- 前端：Vue 3 单文件组件，挂到主站路由，浅色主题，紫色按钮
- 检索：Elasticsearch，索引 `philippians-practice`
- 生成：Anthropic Claude API，模型 `claude-sonnet-4-6`
- 下载：复用主站已有接口 `POST /api/ai_search/format_outline_only`

---

## 2. 目录结构

```
D:\copypan\
├── testC\
│   └── PanAI2.0\
│       ├── __init__.py                        # 空文件，让 Python 识别为包
│       └── backend\
│           ├── __init__.py                    # 空文件
│           ├── prompts.py                     # 只放 STEP5_GENERATION_FLAT 常量
│           ├── kg_rag_router.py               # 核心业务逻辑：检索 + 生成
│           └── main.py                        # FastAPI app 入口，端口 8009
└── front_mic\
    └── frontend\
        └── src\
            ├── router\
            │   └── index.js                   # 加 /practice-kg-rag 路由
            ├── components\
            │   └── toolbox\
            │       ├── ToolBox.vue            # 加工具箱入口
            │       └── KgRagPractice.vue      # 新建前端组件（放这里，和其他工具同级）
```

> **注意：** 前端组件 `KgRagPractice.vue` 放在 `front_mic/frontend/src/components/toolbox/` 下，和 `OutlineTranslate_practice.vue` 同级，这样主站路由可以直接 import，不需要跨目录引用。

---

## 3. 后端设计

### 3.1 启动方式
在仓库根目录 `D:\copypan` 下运行：
```powershell
python -m uvicorn testC.PanAI2.0.backend.main:app --host 0.0.0.0 --port 8009 --reload
```
注意：必须在仓库根目录运行，不能进入子目录，因为 `back_shared`、`back_mic` 都需要从根目录解析路径。

### 3.2 `main.py` 设计要求

这个文件是 FastAPI 的入口，参考 `testC/zh2tw/backend/main.py` 的结构来写，但需要额外处理 sys.path：

```
职责：
1. 在最顶部把以下两个路径加入 sys.path（必须在所有 import 之前）：
   - 仓库根目录：os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
     （从 testC/PanAI2.0/backend/ 往上三级到达 D:\copypan）
   - back_mic/backend 目录：os.path.join(仓库根目录, 'back_mic', 'backend')
     （dense_search 依赖的 embedding_adapter 在这里）
2. 创建 FastAPI app，title='PanAI 2.0 Practice'
3. 加 CORS 中间件，allow_origins=['*']，必须在 include_router 之前
4. include_router(kg_rag_router.router)
5. GET /health 接口，返回 {'status': 'ok'}
6. if __name__ == '__main__': uvicorn.run，port=8009，reload=True
```

### 3.3 `prompts.py` 设计要求

只做一件事：从 `back_mic/backend/kg_rag/prompts.py` 里找到 `STEP5_GENERATION_FLAT` 这个字符串常量，完整复制到这个文件里。不做任何修改，不添加任何其他内容。

### 3.4 `kg_rag_router.py` 设计要求

这是核心文件，实现 PanAI 2.0 流水线。

#### 依赖导入
```
- from back_shared.retrieval import bm25_search, dense_search, rrf_merge, rerank
- from elasticsearch import Elasticsearch
- import anthropic
- from dotenv import load_dotenv
- from .prompts import STEP5_GENERATION_FLAT
```

#### 初始化（模块级，只执行一次）
```
- load_dotenv，路径为相对于本文件往上四级找到 back_mic/backend/.env
- ES 客户端：Elasticsearch(['http://localhost:9200'], basic_auth=('elastic', 'qwSD4AF2Dcv'))
- INDEX_NAME = 'philippians-practice'
```

#### 请求体 KgRagRequest（Pydantic BaseModel）
```
- query: str                           # 纲目主题，必填
- outline_nature: str = '一般性'       # 纲目性质，默认一般性
- burden_description: str = ''         # 负担说明，可选
```

#### format_chunks 函数
把 rerank 后的 chunks 列表格式化成文字，供 Prompt 使用。每条 chunk 输出三行：
```
[chunk_id] book_title 第N篇 message_title
正文内容
---
```
具体逻辑参考 `back_mic/backend/kg_rag/kg_rag_service.py` 里的 `_format_chunks` 函数。

#### POST /query 接口流程

路由完整路径：`POST /api/practice/kg_rag/query`

```
步骤一：并发检索（用 asyncio.gather 同时跑两路，节省时间）
    bm25_results = await bm25_search(es, req.query, INDEX_NAME, top_k=30)
    dense_results = await dense_search(es, req.query, INDEX_NAME, top_k=30)

步骤二：融合排序（rrf_merge 不是 async，直接调用）
    merged = rrf_merge(bm25_results, dense_results)

步骤三：精排
    final = await rerank(merged, req.query, top_n=20)

步骤四：格式化 chunks
    chunks_text = format_chunks(final)

步骤五：构建 metadata_block
    把 outline_nature 和 burden_description 拼成多行文字。
    规则：各自非空才加入，格式如下：
        纲目性质：{outline_nature}
        负担说明：{burden_description}
    两者都空时 metadata_block = ''

步骤六：拼 Prompt
    prompt = STEP5_GENERATION_FLAT.format(
        query=req.query,
        metadata_block=metadata_block,
        chunks=chunks_text,
    )

步骤七：调 Claude API
    client = anthropic.Anthropic(api_key=os.environ['CLAUDE_API_KEY'])
    调用 claude-sonnet-4-6，max_tokens=4096
    取 response.content[0].text 作为纲目文字

步骤八：返回
    return {'answer': 纲目文字, 'chunks_used': len(final)}
```

#### 错误处理
用 try/except 包裹整个流程，出错时返回 `{'answer': None, 'error': str(e)}`

---

## 4. 前端设计

### 4.1 文件位置
`front_mic/frontend/src/components/toolbox/KgRagPractice.vue`

### 4.2 界面布局

```
┌─────────────────────────────────────────────────┐
│  ← 返回                                          │
│                                                  │
│           AI 纲目制作练习                         │
│                                                  │
│  纲目主题                                         │
│  [────────────────────────────────────────────]  │
│                                                  │
│  纲目性质                                         │
│  [一般性]  [真理启示]  [生命经历]  [应用实行]      │
│   ↑选中时紫色高亮，同一时间只能选一个               │
│                                                  │
│  负担说明（可选）                                  │
│  [────────────────────────────────────────────]  │
│  [────────────────────────────────────────────]  │
│  [────────────────────────────────────────────]  │
│                                                  │
│  [生成纲目]  ← 生成中显示「生成中…」并禁用          │
│                                                  │
│  ┌──────────────────────────────────────────┐    │
│  │ 生成结果                        [复制]   │    │
│  │                                          │    │
│  │  （纲目内容，用 <pre> 保留格式）          │    │
│  │                                          │    │
│  │  [下载 DOCX]  [下载 PDF]                │    │
│  └──────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘
```

### 4.3 样式要求
- 整体风格参考 `testC/zh2tw/frontend/src/components/ZhConvert.vue` 的浅色主题
- 背景色：`#f8f9fa`，容器最大宽度：`1100px`
- 主色调（按钮选中、生成按钮）：`#5c4db1`（紫色）
- 纲目性质按钮：未选中为灰色背景，选中为紫色背景白字
- 结果区背景白色，带边框

### 4.4 交互逻辑

```
- 纲目性质默认选中「一般性」
- 点击生成前检查主题是否为空，空则提示「请先输入纲目主题」
- 生成中：按钮文字改为「生成中…」，禁用按钮，禁用性质切换
- 生成完成：显示结果区（结果区初始隐藏）
- 复制按钮：复制纲目文字，按钮文字改为「已复制」，2秒后恢复
- 下载 DOCX / 下载 PDF：见 4.5
```

### 4.5 下载逻辑

复用主站已有接口，不需要后端新增接口。

```
调用接口：POST /api/ai_search/format_outline_only
请求体：
{
    direction: 'en2zh',           // 固定值，使用中文纲目模板
    translated_text: result,      // 纲目全文（主题 + 换行 + 纲目内容）
    output_format: 'docx'         // 或 'pdf'
}
响应处理：
- DOCX：response.docx_base64 → 解码 → Blob → 触发下载，文件名为纲目主题
- PDF：response.pdf_base64 → 解码 → Blob → 触发下载，文件名为纲目主题
下载函数：参考 Search.vue 里的 doDownload 函数逻辑，直接在本组件里实现一个同样的函数
注意：下载接口在 8000 端口（主站后端），通过 nginx 转发，不需要加端口号，直接用相对路径 /api/ai_search/format_outline_only
注意：下载接口需要 Authorization header，从 localStorage.getItem('token') 读取
```

### 4.6 API 调用

```javascript
// 生成纲目
POST /api/practice/kg_rag/query
请求体：{ query, outline_nature, burden_description }
响应：{ answer: '纲目文字', chunks_used: 20 }

// 下载
POST /api/ai_search/format_outline_only
请求体：{ direction: 'en2zh', translated_text: '主题\n\n纲目内容', output_format: 'docx'|'pdf' }
响应：{ docx_base64: '...', filename: '...' } 或 { pdf_base64: '...', filename: '...' }
```

---

## 5. 主站集成

### 5.1 router/index.js
在现有路由数组末尾加一条：
```javascript
{
  path: '/practice-kg-rag',
  component: () => import('../components/toolbox/KgRagPractice.vue')
}
```

### 5.2 ToolBox.vue
在「Vichhet & Chom Pei 测试」分组里，找到「简繁互转练习」那一行，在它后面加：
```html
<a-card-grid class="card c2" @click="go('/practice-kg-rag')">
  <span class="card_text">AI纲目制作练习</span>
</a-card-grid>
```

### 5.3 nginx.conf
在现有的 `location /api/testc/` 规则**之前**新增（必须在 `/api/` 兜底规则之前，否则会被拦截）：
```nginx
location /api/practice/kg_rag/ {
    proxy_pass http://127.0.0.1:8009;
    proxy_set_header Host $host;
    proxy_set_header X-Real-IP $remote_addr;
    proxy_connect_timeout 300s;
    proxy_send_timeout 300s;
    proxy_read_timeout 300s;
}
```

---

## 6. 部署步骤

### 步骤一：启动后端
```powershell
cd D:\copypan
python -m uvicorn "testC.PanAI2.0.backend.main:app" --host 0.0.0.0 --port 8009 --reload
```
验证：浏览器访问 `http://localhost:8009/health`，返回 `{"status":"ok"}` 说明启动成功。
进一步验证：访问 `http://localhost:8009/docs`，能看到 Swagger 文档。

### 步骤二：改 nginx.conf 并 reload
```powershell
cd C:\nginx-1.24.0
.\nginx.exe -s reload
```

### 步骤三：Build 主站并部署
```powershell
cd D:\copypan\front_mic\frontend
npm run build
xcopy /E /Y dist\* C:\nginx-1.24.0\html\
```

### 步骤四：浏览器测试
访问 `http://localhost/#/tools`，找到工具箱里的「AI纲目制作练习」入口，点进去测试完整流程。

---

## 7. 注意事项

1. **nginx 规则顺序：** `/api/practice/kg_rag/` 必须放在 `/api/practice/` 和 `/api/` 之前，否则请求会被兜底规则转发到 8000 端口而不是 8009。

2. **sys.path 顺序：** `main.py` 里 sys.path 的 insert 必须在所有 import 之前，否则 `back_shared`、`embedding_adapter` 找不到。

3. **CORS 顺序：** `app.add_middleware(CORSMiddleware, ...)` 必须在 `app.include_router(...)` 之前。

4. **生成耗时：** 调 Claude 生成纲目需要 30～60 秒，前端必须有明显的加载状态，防止用户误以为卡死。

5. **下载字体：** DOCX 使用方正书宋_GBK 和方正楷体_GBK，这是主站已有的格式，用户电脑需安装这两种字体才能正确显示，否则 Word 会替换为默认字体。

6. **PanAI2.0 目录名含点：** Python 包名不能含点，所以启动命令里用引号包裹 `"testC.PanAI2.0.backend.main:app"`，或者考虑把目录名改为 `PanAI20`（去掉点），避免潜在的导入问题。

7. **rerank 降级：** 如果 JINA_API_KEY 无效或网络问题，rerank 会自动降级为 RRF 原序，不会报错，但精排质量会下降。
