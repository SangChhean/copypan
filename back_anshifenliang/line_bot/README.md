# 按时分粮 LINE Bot

在 Telegram Bot（`telegram_bot/bot.py` + `search_api.py`）基础上做的 LINE 版本。

## 文件说明

- `line_bot.py` — LINE 版收发消息层（Flask + line-bot-sdk + Redis 状态存储）
- `search_api.py` — **原样复制自 Telegram 版**，一个字没改，调同一个 `:8020` API
- `requirements.txt` — 依赖列表
- `.env.example` — 环境变量模板，复制成 `.env` 后填入真实的 LINE 密钥
- `richmenu.png` — Rich Menu 图片（两个按钮：詩歌查詢 / 轉人工客服）
- `setup_rich_menu.py` — 一次性脚本，创建 Rich Menu、上传图片、设为默认菜单

## 交互流程

1. 用户加好友 → 收到两条消息：介绍文字 + Confirm Template（两个按钮：
   🎵 詩歌查詢 / 👤 轉人工客服）
2. 点「詩歌查詢」→ 进入查询模式，之后发的文字都会被当作搜索词
3. 点「轉人工客服」（或随时输入"人工客服"四个字）→ 退出查询模式，
   Bot 不再自动回复，交由人工在 LINE Official Account Manager 的聊天
   界面手动处理
4. 没有点过「詩歌查詢」之前，用户发的任何文字 Bot 都不回复——这是
   刻意设计，让人工客服可以在不被 Bot 抢答的情况下正常接待
5. Rich Menu（输入框上方常驻菜单）是移动端的快捷入口，效果和
   Confirm Template 里的两个按钮完全一样；LINE 电脑客户端可能不显示
   Rich Menu，所以 Confirm Template 是跨平台都能用的主入口，Rich Menu
   算是移动端的锦上添花

## 状态存储：为什么用 Redis，而不是内存字典

最早的版本把"用户选了哪个分类"存在一个 Python 内存字典里，上线后
发现一个 bug：服务器上 gunicorn 用 `--workers 2` 起了两个独立进程，
内存字典不共享，同一个用户连续发的两条消息可能被分到不同进程处理，
导致"明明点过按钮，下一句却又要重新选一次"。

现在改成把状态存进服务器上现有的 Redis（`db=1`，避免和其他网站共用
的 `db=0` 冲突），所有 key 加了 `linebot:anshifenliang:` 前缀隔离，
两个 worker 进程读写的是同一份数据，不会再出现前后不一致的情况。
用户状态 7 天不活跃自动过期，不会在 Redis 里无限堆积。

## 语言：繁体 UI，但搜索结果内容不变

Bot 自己生成的所有提示文字（欢迎语、按钮、确认消息、找不到结果、
服务异常等）都是繁体中文。

但**搜索结果本身的内容**（诗歌歌词、标题等）是从 back_anshifenliang
的数据库原样读出来的，数据库目前存的是简体，这部分不受这次改动影响，
用户查到的歌词内容还是简体。分类名在内部判断逻辑里仍然用简体
（`诗歌`/`经节`/`注解`/`问答`，必须和后端 API 的 `category` 参数精确
匹配），只是展示给用户看的时候，通过 `CATEGORY_DISPLAY` 这个映射转成
繁体（比如内部还是 `诗歌`，界面上显示的是`詩歌`）。

如果以后想让搜索结果内容本身也支持繁体，需要用到
`search_api.py` 里已经写好的 `detect_query_lang()` /
`/api/is-traditional` 那套简繁检测机制，是另一个独立的工作，这次没做。

## 和 Telegram 版的关键差异

1. **纯文本为主，仅在欢迎语用了一次 Confirm Template**：LINE 文字消息
   本身不支持 HTML/富文本，`<b>标题</b>` 这种标签发过去用户会看到原始
   尖括号，所以搜索结果标题用全角括号【】代替加粗。
2. **一次最多发 5 条消息**：LINE 的 reply API 硬性限制，所以
   `MAX_RESULTS` 是 4（+1 条头部说明 = 5 条），不是 Telegram 版的 5。
3. **暂时只做了「诗歌」分类的排版**：和 Telegram Bot 现在
   `ENABLED_CATEGORIES = {"诗歌"}` 的状态一致；注解/经节专用的精细解析
   （对应 Telegram 版 `_parse_zhu_jie_html` / `_parse_jing_wen_html`）
   还没有移植，走通用纯文本兜底，够用但没有 Telegram 版精致。
4. **需要用户主动"进入"才会自动回复**：Telegram 版任何文字都会被当
   搜索词处理；LINE 版必须先点「詩歌查詢」或输入"诗歌"两个字激活，
   这是配合人工客服协同工作特意加的门槛（见上面"交互流程"）。
5. **用 Redis 而不是内存字典存状态**：见上面单独一节的说明，这个是
   LINE 版特有的坑，Telegram 版没遇到（Telegram Bot 是单进程 polling，
   不存在多 worker 不共享内存的问题）。

## 部署到伯大尼服务器

- 项目目录：`/opt/pansearch/code/back_anshifenliang/line_bot/`
- systemd 服务：`anshifenliang-linebot.service`，`gunicorn` 监听
  `127.0.0.1:8021`（`--workers 2`，因为状态已经在 Redis 里共享，多
  worker 不再是问题）
- Nginx：`linebot.educationbylevel.org` 反代到 `127.0.0.1:8021`，
  HTTPS 证书由 certbot 管理
- Redis：复用服务器上已有的 Redis 实例（`127.0.0.1:6379`），使用
  `db=1`，key 前缀 `linebot:anshifenliang:`
- **目前部署走的是手动流程**（SFTP 传文件 + md5 校验 +
  `systemctl restart`），**没有接入 `deploy.sh` 的自动重启**——因为
  服务器上那份 `deploy.sh` 和 git 仓库版本有分叉（`pkill+nohup` vs
  `systemctl restart` 的冲突），这个问题还没解决，等解决了再考虑要不
  要把 line_bot 接进自动部署流程

## 一次性初始化 Rich Menu

首次部署到新账号，或者要更新菜单样式时：

```
cd /opt/pansearch/code/back_anshifenliang/line_bot/
python3 setup_rich_menu.py
```

会自动创建 Rich Menu、上传 `richmenu.png`、设为所有用户的默认菜单。
脚本从 `.env` 读取真实 token 发请求，不会把 token 打印到任何输出。
重复运行会创建新的 Rich Menu 并覆盖默认菜单指向，旧的不会自动删除。

## 已知限制 / 后续可以做但现在没做的

- 注解/经节的精细排版（等这些分类真的要开放时再补）
- 搜索结果内容本身的简繁转换（见上面"语言"一节）
- `deploy.sh` 分叉问题解决后，把 line_bot 接入自动部署流程
- 用户状态目前只有"选了哪个分类"，没有更细的会话记忆（比如上一次
  搜索的关键词）
