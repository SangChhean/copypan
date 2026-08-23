# 按时分粮 LINE Bot

在 Telegram Bot（`bot.py` + `search_api.py`）基础上做的 LINE 版本。

## 文件说明

- `line_bot.py` — 新写的，LINE 版收发消息层（Flask + line-bot-sdk）
- `search_api.py` — **原样复制自 Telegram 版**，一个字没改，调同一个 `:8020` API
- `requirements.txt` — 依赖列表
- `.env.example` — 复制为 `.env` 后填真实的 LINE Channel token/secret

## 和 Telegram 版的关键差异

1. **纯文本，没有加粗**：LINE 文字消息不支持 HTML/富文本，`<b>标题</b>` 这种标签发过去用户会看到原始尖括号。所以标题用全角括号【】代替加粗。

2. **一次最多发 5 条消息**：LINE 的 reply API 硬性限制。所以 `MAX_RESULTS` 设成了 4（+1 条头部说明 = 5条），不是 Telegram 版的 5。

3. **暂时只做了「诗歌」分类的精细排版**：和 Telegram Bot 现在的 `ENABLED_CATEGORIES = {"诗歌"}` 状态一致。原 `bot.py` 里 `_parse_zhu_jie_html`（注解）、`_parse_jing_wen_html`（经文）这些专门排版函数还没有移植过来，现在这些分类的内容会走通用的纯文本转换（够用，但没有 Telegram 版那么精致）。等以后要开放这些分类时，需要把对应的解析逻辑也搬过来。

4. **没有持久化用户状态**：和 Telegram 版一样，`USER_CATEGORY` / `USER_SEEN` 都是存在内存里的 dict/set，服务重启就清空了。以后如果需要跨重启记住用户选的分类，需要换成数据库或文件存储。

5. **用 Quick Reply 代替常驻键盘**：LINE 没有和 Telegram `ReplyKeyboardMarkup` 完全对等的东西，改用 Quick Reply（消息下方的临时按钮，下一条消息后会消失）。如果想要更接近"常驻底部菜单"的效果，以后可以做 LINE 的 Rich Menu，但那个需要额外设计一张菜单图片，工作量更大，先不做。

6. **会自动请求 `/api/detail` 取全文，和 Telegram 版 `get_item_content` 一样**：`诗歌`（hymns）等分类的搜索结果本身 `previewHtml` 是空字符串（见 `lib/search_parse.js`），全文只能靠 `/api/detail` 拿。假数据测试阶段这一步是省略的（假数据自带非空 `previewHtml`），接真实 API 前必须补上，否则「诗歌」查询结果会一直显示"暂无正文"——已经在 `get_item_content`/`fetch_item_contents` 里补上，且为了不让 LINE 的 reply token 因为顺序请求多条全文而超时失效，这几次 `/api/detail` 调用是并发（线程池）发出的，不是顺序 await。

## 部署到伯大尼服务器

**不另起一套部署流程，接入现有的 `deploy.sh` + systemd 方式**（和 Telegram Bot 完全一致的模式）：

- 项目目录就是仓库里的这个目录，随 `git pull` 一起更新，不单独放到 `/var/www/...`：
  `/opt/pansearch/code/back_anshifenliang/line_bot/`
- `search_api.py` 默认连 `http://127.0.0.1:8020`（和 Telegram Bot 用的是同一个 API，不用改，除非你的 API 地址不一样）
- `.env` 放在这个目录下（`/opt/pansearch/code/back_anshifenliang/line_bot/.env`），复制 `.env.example` 后填真实值。已被仓库根目录 `.gitignore` 的 `*.env` 规则忽略，不会被提交
- 服务器上需要一个 venv（和 Telegram Bot 一样是手动建一次，deploy.sh 不负责装 Python 依赖）：
  ```bash
  cd /opt/pansearch/code/back_anshifenliang/line_bot
  python3 -m venv venv
  ./venv/bin/pip install -r requirements.txt
  ```
- systemd unit（`/etc/systemd/system/anshifenliang-linebot.service`，仿照现有 `anshifenliang-bot` 的写法，需要在服务器上手动创建一次，仓库里不提交 `.service` 文件——和 `anshifenliang-server`/`anshifenliang-bot` 的现状一致）：
  ```ini
  [Unit]
  Description=Anshifenliang LINE Bot
  After=network.target anshifenliang-server.service

  [Service]
  WorkingDirectory=/opt/pansearch/code/back_anshifenliang/line_bot
  ExecStart=/opt/pansearch/code/back_anshifenliang/line_bot/venv/bin/gunicorn --bind 127.0.0.1:8002 --workers 2 --timeout 30 line_bot:app
  Restart=always
  RestartSec=3

  [Install]
  WantedBy=multi-user.target
  ```
  （8002 端口，避开 API 的 8020 和 Telegram Bot；`--workers 2` 是因为 webhook 里每条结果都要同步调一次 `/api/detail`，单 worker 会在并发请求时排队；`--timeout` 要大于 `.env` 里的 `SEARCH_TIMEOUT`/`DETAIL_TIMEOUT`，避免 gunicorn 先把 worker 杀掉）
- 建好 unit 后执行一次 `systemctl daemon-reload && systemctl enable anshifenliang-linebot && systemctl start anshifenliang-linebot`，之后 `deploy.sh` 里的 `systemctl restart anshifenliang-linebot` 步骤就会在每次部署时自动重启它
- Nginx 反代和 certbot 那两步，把之前给你的模板里的端口和子域名对应改一下就行，比如子域名可以用 `linebot.quanbeigongying.com` 或者你喜欢的名字

### reply token 的时间限制（LINE 特有，Telegram 没有）

LINE 的 reply token 有效期很短，用完/超时就不能再用来回复。之前假数据测试时 `format_item_plain` 没有实际调 `/api/detail`，所以感觉不出耗时问题；接了真实 API 后，`handle_message` 现在会对本次展示的每条结果并发（线程池）调一次 `/api/detail` 取全文，再一起 reply。务必把 `.env` 里的 `SEARCH_TIMEOUT`/`DETAIL_TIMEOUT` 调低（示例给的是 10 秒），比 gunicorn 的 `--timeout` 小，避免单条请求卡住拖垮整个 reply。

## 测试建议

正式接入 LINE 之前，建议先本地跑一遍逻辑测试（不需要连真实的 :8020 API，也不需要真的 LINE 账号）：把 `search_api.search_in_api` 换成返回假数据的函数，模拟几种情况（有结果、无结果、切换分类、未开放分类），确认格式化输出和消息条数没问题。跑通之后再接真实的 API 和 LINE Webhook，减少上线后现场调试的次数。

## 后续可以做但现在没做的

- 「查看全文」按钮式 UI（Telegram 版没有这个功能，`bot.py` 里也已经移除了，所以 LINE 版也没做；注意这不同于自动取全文——每条结果背后自动调 `/api/detail` 取正文这件事两边都做，见上面第 6 点）
- 注解/经节的精细排版（等这些分类真的要开放时再补）
- Rich Menu 常驻菜单
- 用户状态持久化（重启不丢失分类选择）
