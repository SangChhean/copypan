# E:\copypan 项目架构分析报告

## 项目概览

**copypan** 是一个基于 **Elasticsearch** 的全文检索与数据展示系统，面向圣经/文献类内容的搜索、阅读与管理。后端为 **FastAPI**，前端为 **Vue**（构建后为静态资源），数据存储在 **Elasticsearch** 中。

---

## 1. 后端架构 (E:\copypan\back_mic\backend\)

### 1.1 目录结构

```
back_mic/backend/
├── main.py           # 应用入口，路由与中间件
├── es_config.py      # ES 统一配置（hosts、客户端）
├── es_init.py        # ES 索引与 mapping 定义（初始化用）
├── user/             # 用户认证与账号
├── search/           # 搜索与阅读
├── database/         # 数据管理、上传、导入
├── tools/            # 工具（如圣经书卷检索）
├── response/         # 统一异常
├── utils/            # 工具（JWT）
└── sql/              # 占位（未使用）
```

### 1.2 main.py 的作用与主要路由

**作用**：FastAPI 应用入口，注册 CORS、所有 HTTP/WebSocket 路由，以及鉴权依赖。

**核心配置**：
- **CORS**：`allow_origins` 为 `localhost:5173/3000` 等，`allow_credentials=True`，支持带 Cookie 的跨域请求。
- **鉴权**：登录后返回 JWT，并存到 Cookie `session`；受保护接口通过 `Depends(test_token)` 或 `checkAdmin(session)` 校验。

**主要路由一览**：

| 方法 | 路径 | 鉴权 | 说明 |
|------|------|------|------|
| GET | `/` | 无 | 健康检查 |
| POST | `/token` | 无 | 登录，返回 JSON + Set-Cookie(session) |
| GET | `/testToken` | Bearer/Cookie | 校验 token，返回 userinfo |
| POST | `/signup` | 无 | 注册（需邀请码） |
| POST | `/changePass` | 需登录 | 修改密码 |
| POST | `/search` | 需登录 | 主搜索（input, args） |
| ~~POST `/map`~~ | （已移除：思路搜索） |
| POST | `/cws` | 需登录 | 新约职事词典搜索 |
| POST | `/reading` | 需登录 | 按 refid 读章节 |
| POST | `/getvers` | 需登录 | 圣经书卷/经文检索 |
| POST | `/datalist` | 管理员 | 索引列表/清空索引 |
| POST | `/process` | 管理员 | 从 JSON 批量导入 ES，并推送进度 |
| POST | `/upopt` | 管理员 | 上传文件列表/操作 |
| POST | `/iv_opts` | 管理员 | 邀请码列表/操作 |
| POST | `/usr_opts` | 管理员 | 用户列表/角色/删除 |
| POST | `/upload` | 管理员 | 上传文件到 backend/database/upload |
| WS | `/ws/progress` | 无 | WebSocket 推送导入进度 |

**代码示例（登录 + 受保护搜索）**：

```python
# 登录：返回 JSON 并写 Cookie
@app.post("/token")
def login(remember: Annotated[str, Form()], form_data: OAuth2PasswordRequestForm = Depends()):
    token_body = set_token(form_data.username, form_data.password, remember)
    response = JSONResponse(content={"access_token": token_body.access_token, "token_type": token_body.token_type})
    response.set_cookie(key="session", value=token_body.access_token, path="/", max_age=30*24*3600, httponly=True, samesite="lax")
    return response

# 搜索：依赖 test_token（Header Bearer 或 Cookie session）
@app.post("/search", dependencies=[Depends(test_token)])
def search(input: str = Form(), args: str = Form()):
    result = search_fun(input, args)
    return result if result is not None else {"total": 0, "msg": []}
```

### 1.3 user/ 目录 — 用户认证模块

| 文件 | 职责 |
|------|------|
| **token.py** | 登录签发 JWT（set_token）、校验 token（test_token）；支持从 **Authorization Bearer** 或 **Cookie session** 取 token；JWT 含 username、role、exp。 |
| **add_user.py** | 注册（signup）：校验邀请码（iv.json），写入 users.json；邀请码生成与读写（iv.json）。 |
| **changePass.py** | 修改密码：校验旧密码后更新 users.json。 |
| **users.py** | 用户列表（get_user_list）、改角色（change_role）、删用户（del_user）；供 `/usr_opts` 使用。 |
| **ivcode.py** | 邀请码列表/生成/删除/改角色；供 `/iv_opts` 使用。 |
| **users.json** | 用户存储：`{ "username": { "pass": "...", "role": "t0"|"t1"|... } }`。 |
| **iv.json** | 邀请码与默认角色：`{ "code": "role" }`。 |

**认证流程简述**：  
`POST /token` 使用 `set_token` 校验用户名密码，写 users.json，生成 JWT 并写入 Cookie；后续请求通过 `test_token`（Header 或 Cookie）解析 JWT 得到 userinfo。

### 1.4 search/ 目录 — 搜索功能模块

| 文件 | 职责 |
|------|------|
| **search.py** | 主搜索入口：解析 args（cat1-cat2-cat3-page-pageSize），调用 get_info → get_index + get_matchs，构建 ES bool should 查询（zh/text/title，含 wildcard title），分页、高亮，返回 `{ total, msg }`；打日志（参数、索引列表、完整 ES 查询 JSON）。 |
| **get_search_index.py** | 解析 args（parse_args）、根据 cat1/cat2 解析索引列表（get_index）、构建查询条件（get_match_info、get_matchs）；索引与分类映射（indies、cats）；支持 zh/text/en + title wildcard。 |
| **clear_data.py** | 将 ES 返回的 hits 转为前端格式；兼容 ES6/7 的 total 结构；单条解析失败时跳过，不中断整页。 |
| **clear_bib.py** | 单条 hit 转成前端字段（id, up, down, title, tags, source）；高亮优先用请求字段，否则从 zh/text/en/title 取。 |
| **search_map.py** | 思路工具：按 index 选择 map_* 等索引，match_phrase text，带 must_not（fwds）；返回结构化列表。 |
| **search_reading.py** | 按 refid 查 pan_reading 索引，返回阅读用文档（如章节内容）。 |

**搜索流程简述**：  
前端传 `input` + `args`（如 `a-a-a-1-10`）→ `get_info` 得到索引列表与 match 条件 → `get_matchs` 生成 bool should（zh/text/title）→ `es.search`（ignore_unavailable=True）→ `clear_data` + `clear_bib` → `{ total, msg }`。

### 1.5 其他子模块

| 目录/文件 | 职责 |
|------------|------|
| **database/datalist.py** | 获取所有 ES 索引列表（get_all_indices）、按索引清空并重建（delete_and_recreate_index）；供管理端「数据列表」使用。 |
| **database/uplaod.py** | 上传文件写入 `backend/database/upload/YYYYMMDD/`，按日期只保留当天目录（del_other_day）。 |
| **database/upopt.py** | 上传目录下的 JSON 文件列表（get_list、get_dict_filelist）；导入单文件到 ES（ins_data）；供 `/upopt`、`/process` 使用。 |
| **tools/biblecollection.py** | 圣经书卷/章节数据（Data 等），按输入返回经文或书卷信息；供 `/getvers` 使用。 |
| **response/excptions.py** | 统一 HTTP 异常：ERR_401、ERR_403。 |
| **utils/jwt_op.py** | JWT 编码/解码（HS256，固定 KEY）。 |
| **es_config.py** | ES 连接地址（ES_HOSTS）与全局客户端 `es`，供全项目引用。 |
| **es_init.py** | 定义三种 mapping 类型（read/index/map）及 all_index 列表，用于创建/重建索引（脚本或初始化）。 |

### 1.6 API 接口列表（汇总）

- **公开**：`GET /`，`POST /token`，`POST /signup`，`WS /ws/progress`  
- **需登录（test_token）**：`GET /testToken`，`POST /changePass`，`POST /search`，`POST /cws`，`POST /reading`，`POST /getvers`  
- **需管理员（checkAdmin）**：`POST /datalist`，`POST /process`，`POST /upopt`，`POST /iv_opts`，`POST /usr_opts`，`POST /upload`

---

## 2. 前端架构 (E:\copypan\front_mic\frontend\)

### 2.1 入口与资源

- **index.html**：单页入口，`<div id="app" v-cloak></div>`，加载 `/assets/index-*.js`（Vite 构建后的主 chunk），标题为 "Pansearch"。
- **资源**：`/assets/*.js`（Vue 组件、axios、Ant Design Vue、路由等）、`/style/index.css`、`/fonts/`、`/imgs/`。

### 2.2 使用的框架和库

- **Vue 3**（从构建产物与 v-cloak、ref 等用法可推断）。
- **Vite**（script type="module"、chunk 命名方式）。
- **Ant Design Vue**（Button、Form、Input、Modal、Breadcrumb 等，见组件名与样式）。
- **Axios**：封装请求，与后端 API 通信；支持携带 Cookie/Token（与后端 CORS credentials 配合）。
- **Vue Router**（hash 模式，如 `window.location.hash`、`/login`、`/tools` 等）。

### 2.3 主要组件和页面（从构建产物推断）

| 资源/组件 | 可能对应页面/功能 |
|-----------|-------------------|
| Index-*.js | 主布局、路由、面包屑 |
| Login-*.js | 登录页 |
| Signup-*.js | 注册页 |
| ChangePass-*.js | 修改密码 |
| Forgot-*.js | 忘记密码 |
| ManaIndex-*.js | 管理端首页（用户/邀请码/数据/上传等） |
| Map-*.js | 思路工具（map 搜索） |
| Cwws-*.js | 新约职事词典搜索 |
| ShowMsg-*.js | 主搜索/结果展示 |
| BibleCo-*.js | 工具页（圣经书卷/经文） |
| Test-*.js | 测试页（WebSocket 进度） |
| checkAuth-*.js | 鉴权封装（检查 token、跳转登录） |
| axios-*.js | Axios 实例（baseURL、拦截器等） |

### 2.4 与后端的交互方式

- **登录**：`POST /token`，FormData（username, password, remember）；后端返回 JSON（access_token、token_type）并设置 Cookie `session`。前端可将 token 存 localStorage 或依赖 Cookie。
- **鉴权**：受保护接口通过 **Authorization: Bearer <token>** 或 **Cookie: session=<token>** 携带凭证；axios 需配置 `withCredentials: true` 以便带 Cookie。
- **搜索**：`POST /search`，FormData（input, args）；返回 `{ total, msg }`，msg 为结果数组。
- **其他**：map/cws/reading/getvers 等均为 POST Form；管理端接口（datalist、process、upopt、iv_opts、usr_opts、upload）同样为 POST，需管理员 session。
- **进度**：`/process` 导入时通过 WebSocket `/ws/progress` 推送 `{ progress: 0-100 }`。

---

## 3. 数据库架构（Elasticsearch）

### 3.1 索引类型与 mapping（es_init.py）

三种 mapping 类型：

**read**（阅读用，如 pan_reading）  
- refid, bread, zh, en, cells, type, toc（含 nested）

**index**（主检索用，如 bib, life, cwwn, cwwl, feasts, hymn, others, foo 及各类 _booknames/_titles/_headings 等）  
- id, text, zh（ik_max_word）, en, title（keyword）, order, type, tags, source

**map**（思路/词典类，如 map_*、cws_*）  
- id, text, msg（nested）, sn, source

### 3.2 索引列表与用途（all_index 节选）

| 索引名 | 类型 | 用途简述 |
|--------|------|----------|
| bib, foo, life, cwwn, cwwl, others, hymn, feasts | index | 主分类检索 |
| life_titles, cwwn_booknames, cwwl_headings, feasts_ot1, ... | index | 带后缀的细分检索 |
| pan_reading | read | 按 refid 阅读章节 |
| map_note, map_life, map_nee_bookname, map_lee_title, map_cont_bookname, map_feasts_title, map_hymn, ... | map | 词典类检索 |
| cws_nee, cws_lee, cws_cont, cws_life_titles, cws_nee_titles, ... | map | 新约职事词典 |

### 3.3 数据关系

- **主检索**：多索引同时查询（由 args 的 cat1/cat2 决定），例如 cat1=a 时查 bib, foo, life, cwwn, cwwl, others 等；同一文档结构（id, text, zh, en, title, tags, source 等）。
- **阅读**：pan_reading 按 refid 查单文档，结构含 refid, bread, zh, en, cells, type, toc。
- **思路/词典**：map_*、cws_* 为独立索引，文档含 text、msg 等，与主检索索引无外键关系，仅通过业务（前端选 index）关联。

---

## 4. 核心功能模块

### 4.1 用户登录认证流程

1. 前端：提交用户名、密码、是否记住（remember）到 `POST /token`。  
2. 后端：`set_token` 读 users.json，校验用户名密码；通过则生成 JWT（含 username、role、exp），返回 JSON 并 `Set-Cookie: session=<JWT>`。  
3. 前端：可存 token 到 localStorage 或仅依赖 Cookie；后续请求设置 `withCredentials: true` 或 Header `Authorization: Bearer <token>`。  
4. 受保护接口：`test_token` 从 Header 或 Cookie 取 token，jwt_decode 校验并读 users.json 校验角色与过期时间，通过则注入 userinfo。

### 4.2 搜索功能实现

1. **参数**：`input`（关键词）、`args`（如 `a-a-a-1-10`：分类-子类-模式-页码-每页条数）。  
2. **解析**：`parse_args` 得到 cat1/cat2/cat3/page/pageSize；`get_index(cat1, cat2)` 得到 ES 索引列表；`get_match_info` 得到主字段（zh/en/text）与 operator；`get_matchs` 生成 bool should（zh、text、title wildcard）。  
3. **请求 ES**：`es.search(index=index_list, body={ query: { bool: { should, minimum_should_match: 1 } }, highlight: { zh, text, en, title }, from, size }, ignore_unavailable=True)`。  
4. **响应**：`clear_data` 解析 hits 与 total，`clear_bib` 逐条转成前端格式（id, up, down, title, tags, source），返回 `{ total, msg }`。

### 4.3 数据展示逻辑

- **主搜索**：前端传 input/args，后端返回 `{ total, msg }`；前端展示列表（标题、高亮片段、来源等）。  
- **阅读**：前端传 refid，`/reading` 查 pan_reading，返回整条文档用于章节展示。  
- **思路/词典**：前端选 index，传 input（及 fwds），后端查对应 map_*/cws_* 索引，返回结构化结果。  
- **管理端**：datalist 展示索引列表并可清空；upload 上传 JSON；process 选择文件批量写入 ES，并通过 WebSocket 推送进度。

---

## 5. 项目根目录其他文件

| 路径 | 说明 |
|------|------|
| **fix_red_indices.py** | 脚本：列出 red 索引，逐个 close/open，用于修复；依赖 IK 插件已安装。 |
| **import_all_data.py** | 脚本：从本地数据批量导入 ES（与 backend 的 process 或 upopt 类似）。 |
| **es_plugins/ik/** | IK 分词插件（7.17.9），供 ES 使用；需在 elasticsearch.yml 中配置 path.plugins。 |
| **es_data/** | Elasticsearch 数据目录（通常由 ES 进程使用）。 |

---

## 6. 小结

- **后端**：FastAPI + JWT（Header/Cookie）+ ES，模块按 user、search、database、tools 划分，ES 连接与索引定义集中在 es_config 与 es_init。  
- **前端**：Vue 3 + Vite + Ant Design Vue + Axios，单页应用，登录/搜索/阅读/管理/工具分多页，通过 Cookie 或 Bearer 与后端联动。  
- **数据**：ES 多索引、三种 mapping（read/index/map），主检索覆盖 zh/text/title，支持分页与高亮；用户与邀请码为 JSON 文件存储。

如需对某一模块做更细的接口级或代码级说明，可以指定模块或文件路径。
