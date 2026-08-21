# line_bot.py — 按时分粮 LINE Bot
#
# 架构对照 Telegram 版 bot.py：
#   - search_api.py 完全复用，不改动（调同一个 :8020 API）
#   - 收发消息层从 python-telegram-bot 换成 line-bot-sdk（Flask webhook）
#   - Telegram 支持 parse_mode="HTML" 加粗，LINE 文字消息不支持任何 HTML/富文本，
#     所以这里的排版函数输出的是纯文本，用【】全角括号代替 <b></b> 加粗
#   - LINE 一次 reply 最多 5 条消息，所以 MAX_RESULTS 设为 4（+1 条头部说明 = 5条）
#   - 目前只做 ENABLED_CATEGORIES = {"诗歌"} 能用的范围，和 Telegram 版当前状态一致；
#     注解/经节专用的精细排版（原 bot.py 的 _parse_zhu_jie_html /
#     _parse_jing_wen_html / _format_note_block）还没有移植，
#     等以后要开放这些分类时再补，现在这些分类会走通用的纯文本兜底转换

import os
import re
import logging
from concurrent.futures import ThreadPoolExecutor
from html import unescape

import redis
from flask import Flask, request, abort
from dotenv import load_dotenv

from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import InvalidSignatureError
from linebot.v3.messaging import (
    Configuration,
    ApiClient,
    MessagingApi,
    ReplyMessageRequest,
    TextMessage,
    TemplateMessage,
    ConfirmTemplate,
    QuickReply,
    QuickReplyItem,
    MessageAction,
)
from linebot.v3.webhooks import MessageEvent, TextMessageContent, FollowEvent

from search_api import search_in_api, fetch_detail, check_api_ready

# ============ 配置 ============
load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

CHANNEL_ACCESS_TOKEN = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET")
if not CHANNEL_ACCESS_TOKEN or not CHANNEL_SECRET:
    raise RuntimeError(
        "请先在 .env 文件里设置 LINE_CHANNEL_ACCESS_TOKEN 和 LINE_CHANNEL_SECRET"
    )

configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
handler = WebhookHandler(CHANNEL_SECRET)

LOADED_COUNT = int(os.getenv("LOADED_COUNT", "12000"))

# ---- Redis：这台服务器上多个网站共用同一个 Redis 实例（db 0 + 各自 key 前缀隔离），
# 排查过没有设密码；这里额外用 db 1（现在没人用）+ 自己的 key 前缀做双重隔离 ----
REDIS_KEY_PREFIX = "linebot:anshifenliang:"
redis_client = redis.Redis(
    host="127.0.0.1",
    port=6379,
    db=1,  # 具体几号库按第 1 步查到的结果调整
    decode_responses=True,
    # password="...",  # 如果第 1 步发现需要密码，取消注释填上
)

# ---- 与 Telegram Bot 保持一致的产品规则 ----
CATEGORY_DATA = {
    "诗歌": "诗歌",
    "经节": "经节",
    "注解": "注解",
    "问答": "问答",
}
CATEGORY_BUTTONS = list(CATEGORY_DATA.keys())
ENABLED_CATEGORIES = {"诗歌"}
DEFAULT_CATEGORY = "诗歌"
CATEGORY_CLOSED_MSG = "目前暫未開放。\n\n目前僅開放【詩歌】查詢。"

# 内部分类判断用简体（要跟后端 API 的 category 参数精确匹配，不能改），
# 展示给用户看的文字用繁体，靠这个映射做转换
CATEGORY_DISPLAY = {
    "诗歌": "詩歌",
    "经节": "經節",
    "注解": "註解",
    "问答": "問答",
}

MAX_RESULTS = 4          # LINE 一次 reply 最多 5 条消息，留 1 条给头部说明
MSG_CHUNK = 4900          # LINE 单条文字消息上限约 5000 字，留一点余量


def get_user_category(user_id: str) -> str | None:
    return redis_client.get(f"{REDIS_KEY_PREFIX}category:{user_id}")


def set_user_category(user_id: str, category: str) -> None:
    # 7 天没用自动过期，避免 Redis 里无限堆积不会清理的用户数据
    redis_client.set(f"{REDIS_KEY_PREFIX}category:{user_id}", category, ex=7 * 24 * 3600)


def clear_user_category(user_id: str) -> None:
    redis_client.delete(f"{REDIS_KEY_PREFIX}category:{user_id}")


def mark_user_seen(user_id: str) -> bool:
    """返回 True 表示这是第一次见到这个用户。"""
    key = f"{REDIS_KEY_PREFIX}seen:{user_id}"
    is_new = redis_client.set(key, "1", nx=True, ex=30 * 24 * 3600)
    return bool(is_new)


# ============ 纯文本格式化（LINE 不支持 HTML，所以不用 <b>，用【】代替） ============
# 与 Telegram 版 bot.py 对齐：源数据个别字符会以 U+FFFD 乱码形式出现，按已知映射修复。
_GLYPH_FIX_MAP = {"k": "祂", "q": "痲", "F": "镕", "Z": "繸", "m": "醡"}


def _fix_glyph_corruption(text: str) -> str:
    if not text or "�" not in text:
        return text

    def repl(m: re.Match) -> str:
        return _GLYPH_FIX_MAP.get(m.group(1), m.group(0))

    return re.sub("�(.)", repl, text)


def strip_tags_to_plain(html_text: str) -> str:
    """把 API 返回的 HTML 片段转成纯文本：<br> 换行，其余标签去掉，HTML 实体还原。"""
    if not html_text or not html_text.strip():
        return "（暫無正文）"
    text = _fix_glyph_corruption(html_text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"<p[^>]*>", "\n", text, flags=re.I)
    text = re.sub(r"</p>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    # 折叠多余空行，但保留段落间的换行
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() or "（暫無正文）"


def get_item_content(item: dict, lang: str = "zh-CN") -> str:
    """取一条结果的正文：优先请求 /api/detail 全文，取不到再退回搜索自带的预览片段。

    诗歌（hymns）等分类的搜索结果 previewHtml 本身就是空字符串，全文只能靠
    /api/detail 拿到（见 lib/search_parse.js、lib/bootstrap.js），这里必须和
    Telegram 版 bot.py 的 get_item_content 一样发起这次请求，否则诗歌结果会
    一直显示"暂无正文"。
    """
    source = item.get("source") or ""
    title_key = item.get("titleKey") or item.get("title") or ""
    raw_html = item.get("previewHtml") or item.get("preview") or ""
    if source and source != "catalog":
        try:
            detail = fetch_detail(source, title_key, lang)
            if detail and detail.get("content"):
                raw_html = detail["content"]
        except Exception:
            logger.exception("获取全文失败 title=%r", title_key)
    return raw_html


def format_item_from_content(index: int, item: dict, raw_html: str) -> str:
    """一条结果 -> 纯文本：【N. 标题】+ 正文（正文已取好，只负责排版）。"""
    title = item.get("title") or ""
    body = strip_tags_to_plain(raw_html)
    header = f"【{index}. {title}】\n\n"
    text = header + body
    if len(text) > MSG_CHUNK:
        text = text[: MSG_CHUNK - 20].rstrip() + "\n…（內容較長，已截斷）"
    return text


def fetch_item_contents(items: list[dict], lang: str) -> list[str]:
    """并发取每条结果的全文：LINE reply token 有效期很短，
    几条 /api/detail 顺序请求叠加耗时容易导致 reply 失败（Telegram 没有这个时限，
    所以 bot.py 里是顺序 await 的），这里改成线程池并发以缩短总耗时。"""
    if not items:
        return []
    with ThreadPoolExecutor(max_workers=len(items)) as executor:
        return list(executor.map(lambda it: get_item_content(it, lang), items))


def get_category_quick_reply() -> QuickReply:
    items = [
        QuickReplyItem(action=MessageAction(label=name, text=name))
        for name in CATEGORY_BUTTONS
    ]
    return QuickReply(items=items)


def reply_texts(reply_token: str, texts: list[str]) -> None:
    """一次性把最多 5 条文字消息发出去（LINE reply 的硬限制）。"""
    texts = texts[:5]
    messages = [TextMessage(text=t) for t in texts]

    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(
            ReplyMessageRequest(reply_token=reply_token, messages=messages)
        )


# ============ 事件处理 ============
@handler.add(FollowEvent)
def handle_follow(event):
    """用户加好友时触发，对应 Telegram 版的 /start。"""
    intro = (
        "🙏 各位弟兄姊妹平安！\n"
        "Line Bot 現已上線 🎉\n\n"
        "━━━━━━━━━━━━━━\n"
        "🎵 目前開放：詩歌查詢\n"
        "• 大本詩歌\n"
        "• 補充本詩歌\n"
        "• 兒童詩歌\n\n"
        "📚 後續將陸續開放：\n"
        "• 新舊約聖經經文\n"
        "• 註解\n"
        "━━━━━━━━━━━━━━\n\n"
        "💡 使用方法：\n"
        "1️⃣ 點擊下方「🎵 詩歌查詢」按鈕進入查詢模式\n"
        "2️⃣ 直接輸入關鍵詞（如：詩歌編號、歌詞片段、主題）\n"
        "3️⃣ 即問即答 ✨\n\n"
        "如需真人協助，隨時點擊「👤 轉人工客服」\n\n"
        "有任何問題歡迎私訊我們\n"
        "願主祝福大家 🌿"
    )
    confirm = TemplateMessage(
        alt_text="請選擇：詩歌查詢 或 轉人工客服",
        template=ConfirmTemplate(
            text="請選擇：",
            actions=[
                MessageAction(label="🎵 詩歌查詢", text="诗歌"),
                MessageAction(label="👤 轉人工客服", text="人工客服"),
            ],
        ),
    )
    with ApiClient(configuration) as api_client:
        line_bot_api = MessagingApi(api_client)
        line_bot_api.reply_message(
            ReplyMessageRequest(
                reply_token=event.reply_token,
                messages=[TextMessage(text=intro), confirm],
            )
        )


@handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_id = event.source.user_id
    user_input = event.message.text.strip()

    is_first_time = mark_user_seen(user_id)

    # 转人工客服（退出 Bot 查询模式）
    if user_input == "人工客服":
        clear_user_category(user_id)
        reply_texts(
            event.reply_token,
            ["👤 已為您轉接人工客服，請稍候，同工會盡快回覆您。\n\n（如需再次使用查詢功能，請點擊「🎵 詩歌查詢」）"],
        )
        return

    # 分类切换
    if user_input in CATEGORY_BUTTONS:
        if user_input not in ENABLED_CATEGORIES:
            reply_texts(event.reply_token, [CATEGORY_CLOSED_MSG])
            return
        set_user_category(user_id, user_input)
        display_name = CATEGORY_DISPLAY.get(user_input, user_input)
        reply_texts(
            event.reply_token,
            [f"✅ 已切換到【{display_name}】\n\n請輸入查詢內容，例如：\n• 奉獻\n• 詩歌第1首"],
        )
        return

    # 未激活（没点过分类按钮/没打过"诗歌"）就不当作搜索请求，留给人工客服
    current_category = get_user_category(user_id)
    if current_category is None:
        return

    category = current_category
    if category not in ENABLED_CATEGORIES:
        category = DEFAULT_CATEGORY
        set_user_category(user_id, category)
    category_api = CATEGORY_DATA[category]

    logger.info("用户 %s 查询: [%s] %s", user_id, category, user_input)

    try:
        result = search_in_api(user_input, category_api, MAX_RESULTS)
    except Exception:
        logger.exception("搜索 API 调用失败")
        reply_texts(event.reply_token, ["😔 搜尋服務暫時不可用，請稍後再試。"])
        return

    items = result.get("items") or []
    display_name = CATEGORY_DISPLAY.get(category, category)

    if not result.get("found") or not items:
        reply_texts(
            event.reply_token,
            [f"😔 在【{display_name}】裡沒找到「{user_input}」\n\n試試換個關鍵詞"],
        )
        return

    display_items = items[:MAX_RESULTS]
    header = f"📚 在【{display_name}】找到 {len(items)} 條結果"
    if len(items) > MAX_RESULTS:
        header += f"，顯示前 {MAX_RESULTS} 條"
    header += f"：「{result.get('query') or user_input}」"

    lang = result.get("lang") or "zh-CN"
    bodies = fetch_item_contents(display_items, lang)
    texts = [header] + [
        format_item_from_content(i, item, body)
        for i, (item, body) in enumerate(zip(display_items, bodies), 1)
    ]
    reply_texts(event.reply_token, texts)


# ============ Flask 路由 ============
@app.route("/webhook", methods=["POST"])
def webhook():
    signature = request.headers.get("X-Line-Signature", "")
    body = request.get_data(as_text=True)
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        abort(400)
    return "OK"


@app.route("/", methods=["GET"])
def health_check():
    api_ok = check_api_ready()
    status = "ok" if api_ok else "search API not responding"
    return f"LINE Bot (按时分粮) is running. Search API: {status}"


if __name__ == "__main__":
    if check_api_ready():
        print("Search API ready")
    else:
        print("WARNING: Search API not responding on :8020")
    # 8000 是主站 back_mic 后端的端口，这里改用 8002 与生产 systemd/gunicorn 配置一致
    dev_port = int(os.environ.get("PORT", "8002"))
    app.run(port=dev_port, debug=True)
