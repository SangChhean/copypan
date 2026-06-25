# bot.py - 按时分粮 Bot：最多 5 条全文，按原文换行分段
import asyncio
import os
import re
import logging
from html import escape
from dotenv import load_dotenv
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes
)

from search_api import search_in_api, fetch_detail, check_api_ready

# ============ 配置 ============
load_dotenv(override=True)
TOKEN = os.getenv("BOT_TOKEN") or os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise ValueError("⚠️ 未找到 BOT_TOKEN / TELEGRAM_BOT_TOKEN，请检查 .env 或环境变量")

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

_GLYPH_FIX_MAP = {"k": "祂", "q": "痲", "F": "镕", "Z": "繸", "m": "醡"}


def _fix_glyph_corruption(text: str) -> str:
    if not text or "\ufffd" not in text:
        return text

    def repl(m: re.Match) -> str:
        return _GLYPH_FIX_MAP.get(m.group(1), m.group(0))

    return re.sub("\ufffd(.)", repl, text)


LOADED_COUNT = int(os.getenv("LOADED_COUNT", "12000"))
WEBSITE_URL = os.getenv("WEBSITE_URL", "https://chat.educationbylevel.org")

USER_CATEGORY = {}
USER_SEEN = set()

CATEGORY_DATA = {
    "📖 诗歌": "诗歌",
    "📜 经节": "经节",
    "📝 注解": "注解",
    "💡 问答": "问答",
}

CATEGORY_BUTTONS = list(CATEGORY_DATA.keys())
ENABLED_CATEGORIES = {"📖 诗歌", "📜 经节", "📝 注解", "💡 问答"}
DEFAULT_CATEGORY = "📖 诗歌"

MAX_RESULTS = 5
MSG_CHUNK = 4000


# ============ 工具函数 ============
def get_main_keyboard():
    keyboard = [
        [KeyboardButton("📖 诗歌"), KeyboardButton("📜 经节")],
        [KeyboardButton("📝 注解"), KeyboardButton("💡 问答")],
    ]
    return ReplyKeyboardMarkup(
        keyboard,
        resize_keyboard=True,
        one_time_keyboard=False,
        is_persistent=True,
    )


def _strip_inner_tags(html: str) -> str:
    html = _fix_glyph_corruption(html)
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return text


_SUPERSCRIPT_MAP = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def _to_superscript_digits(text: str) -> str:
    return text.translate(_SUPERSCRIPT_MAP)


def _html_fragment_to_telegram(fragment: str) -> str:
    """HTML 片段 → Telegram HTML，保留上标数字（Unicode）。"""
    if not fragment:
        return ""
    chunk = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    parts: list[str] = []
    pos = 0
    for m in re.finditer(r"<sup[^>]*>(.*?)</sup>", chunk, flags=re.I | re.DOTALL):
        if m.start() > pos:
            parts.append(escape(_strip_inner_tags(chunk[pos : m.start()])))
        inner = _strip_inner_tags(m.group(1)).strip()
        if inner:
            parts.append(escape(_to_superscript_digits(inner)))
        pos = m.end()
    if pos < len(chunk):
        parts.append(escape(_strip_inner_tags(chunk[pos:])))
    return "".join(parts)


def _strip_document_noise(html: str) -> str:
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", html, flags=re.I)
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", text, flags=re.I)
    text = re.sub(r"<head[^>]*>[\s\S]*?</head>", "", text, flags=re.I)
    return text


def _text_from_html_fragment(fragment: str) -> str:
    fragment = re.sub(r"<br\s*/?>", "\n", fragment, flags=re.I)
    paras = re.findall(r"<p[^>]*>(.*?)</p>", fragment, flags=re.I | re.DOTALL)
    if paras:
        return "\n\n".join(_strip_inner_tags(p).strip() for p in paras if p.strip())
    return _strip_inner_tags(fragment).strip()


def _find_div_contents(html: str, class_name: str) -> list[str]:
    results: list[str] = []
    pattern = re.compile(
        rf'<div[^>]*class="[^"]*\b{re.escape(class_name)}\b[^"]*"[^>]*>',
        re.I,
    )
    for m in pattern.finditer(html):
        start = m.end()
        depth = 1
        i = start
        while i < len(html) and depth > 0:
            open_div = html.find("<div", i)
            close_div = html.find("</div>", i)
            if close_div == -1:
                break
            if open_div != -1 and open_div < close_div:
                depth += 1
                i = open_div + 4
            else:
                depth -= 1
                if depth == 0:
                    results.append(html[start:close_div])
                i = close_div + 6
    return results


def _format_note_block(note_html: str) -> str:
    num_m = re.search(r'class="note-number"[^>]*>([^<]*)', note_html, re.I)
    label = _strip_inner_tags(num_m.group(1)).strip() if num_m else ""

    content_m = re.search(
        r'class="note-content"[^>]*>(.*?)</span>', note_html, re.I | re.DOTALL
    )
    if content_m:
        body = _html_fragment_to_telegram(content_m.group(1)).strip()
    else:
        multi_m = re.search(
            r'class="note-content-multi"[^>]*>(.*)', note_html, re.I | re.DOTALL
        )
        if multi_m:
            body = _text_from_html_fragment(multi_m.group(1))
            body = re.sub(
                r"<sup[^>]*>(.*?)</sup>",
                lambda m: escape(_to_superscript_digits(_strip_inner_tags(m.group(1)).strip())),
                body,
                flags=re.I | re.DOTALL,
            )
            if label and body.startswith(label.strip()):
                label = ""
        else:
            body = _strip_inner_tags(note_html).strip()
            if label and body.startswith(label):
                body = body[len(label):].strip()

    if label:
        return f"<b>{escape(label)}</b>\n{escape(body)}"
    return escape(body)


def _parse_foo_jie_single(html_text: str) -> str | None:
    html = _strip_document_noise(html_text)
    h3_m = re.search(r"<h3[^>]*>(.*?)</h3>", html, re.I | re.DOTALL)
    if not h3_m:
        return None
    body_m = re.search(r"<div[^>]*>(.*?)</div>", html, re.I | re.DOTALL)
    title = _strip_inner_tags(h3_m.group(1)).strip()
    body = _strip_inner_tags(body_m.group(1)).strip() if body_m else ""
    if not title:
        return None
    return f"<b>{escape(title)}</b>\n\n{escape(body)}" if body else f"<b>{escape(title)}</b>"


def _parse_zhu_jie_html(html_text: str) -> str | None:
    html = _strip_document_noise(html_text)
    if not re.search(r"(?:note-item|verse-content)", html, re.I):
        return None

    blocks: list[str] = []

    title_m = re.search(r'class="page-title"[^>]*>([^<]+)', html, re.I)
    if title_m:
        blocks.append(f"<b>{escape(title_m.group(1).strip())}</b>")

    for verse_html in _find_div_contents(html, "verse-content"):
        verse_inner = re.search(
            r'class="verse-text"[^>]*>(.*?)</span>', verse_html, re.I | re.DOTALL
        )
        if verse_inner:
            verse = _html_fragment_to_telegram(verse_inner.group(1)).strip()
            prefix_m = re.search(
                r'class="verse-number"[^>]*>([^<]*)', verse_html, re.I
            )
            if prefix_m:
                prefix = escape(_strip_inner_tags(prefix_m.group(1)).strip())
                verse = f"{prefix}\n{verse}" if verse else prefix
        else:
            verse = _html_fragment_to_telegram(verse_html).strip()
        if verse:
            blocks.append(verse)

    for note_html in _find_div_contents(html, "note-item"):
        note = _format_note_block(note_html)
        if note:
            blocks.append(note)

    return "\n\n".join(blocks) if blocks else None


def _parse_jing_wen_html(html_text: str) -> str | None:
    html = _strip_document_noise(html_text)
    if not re.search(r'class="(?:main-title|verse)"', html, re.I):
        return None

    blocks: list[str] = []

    title_m = re.search(r'class="main-title"[^>]*>([^<]+)', html, re.I)
    if title_m:
        blocks.append(f"<b>{escape(title_m.group(1).strip())}</b>")

    for info_html in _find_div_contents(html, "book-info"):
        text = _strip_inner_tags(info_html).strip()
        if text:
            blocks.append(escape(text))

    for theme_html in _find_div_contents(html, "theme"):
        text = _strip_inner_tags(theme_html).strip()
        if text:
            blocks.append(f"<b>{escape(text)}</b>")

    for outline_html in _find_div_contents(html, "outline"):
        text = _strip_inner_tags(outline_html).strip()
        if text:
            blocks.append(escape(text))

    for verse_html in _find_div_contents(html, "verse"):
        num_m = re.search(r'class="verse-number"[^>]*>([^<]*)', verse_html, re.I)
        text_m = re.search(
            r'class="verse-text"[^>]*>(.*?)</span>', verse_html, re.I | re.DOTALL
        )
        num = _strip_inner_tags(num_m.group(1)).strip() if num_m else ""
        text = (
            _html_fragment_to_telegram(text_m.group(1)).strip()
            if text_m
            else _html_fragment_to_telegram(verse_html).strip()
        )
        if num and text:
            blocks.append(f"<b>{escape(num)}</b> {escape(text)}")
        elif text:
            blocks.append(escape(text))

    return "\n\n".join(blocks) if blocks else None


def _inline_html_to_telegram(html: str) -> str:
    """段内 HTML → Telegram HTML（保留 <b>）。"""
    chunk = re.sub(
        r'<span[^>]*class="[^"]*zheng-pian-group[^"]*"[^>]*>\s*'
        r"<button[^>]*>.*?<span>\s*(\d+)\s*</span>\s*</button>\s*"
        r"([^<]+?)\s*</span>",
        lambda m: m.group(1) + m.group(2).strip(),
        html,
        flags=re.I | re.DOTALL,
    )

    parts: list[str] = []
    pos = 0
    for m in re.finditer(r"<strong>(.*?)</strong>", chunk, flags=re.I | re.DOTALL):
        if m.start() > pos:
            parts.append(escape(_strip_inner_tags(chunk[pos:m.start()])))
        parts.append(f"<b>{escape(_strip_inner_tags(m.group(1)))}</b>")
        pos = m.end()
    if pos < len(chunk):
        parts.append(escape(_strip_inner_tags(chunk[pos:])))
    return "".join(parts)


def html_to_telegram(html_text: str) -> str:
    """将 API/网站 HTML 转为 Telegram 消息：按 <p> 分段，<strong> 加粗。"""
    if not html_text or not html_text.strip():
        return escape("（暂无正文）")

    zhu_jie = _parse_zhu_jie_html(html_text)
    if zhu_jie:
        return zhu_jie

    foo_jie = _parse_foo_jie_single(html_text)
    if foo_jie:
        return foo_jie

    jing_wen = _parse_jing_wen_html(html_text)
    if jing_wen:
        return jing_wen

    text = _strip_document_noise(html_text)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    paras = re.findall(r"<p[^>]*>(.*?)</p>", text, flags=re.I | re.DOTALL)
    if paras:
        blocks = [_inline_html_to_telegram(p.strip()) for p in paras if p.strip()]
        if blocks:
            return "\n\n".join(blocks)

    return _inline_html_to_telegram(text)


def format_item_body(content: str) -> str:
    return html_to_telegram(content)


def split_html_message(text: str, max_len: int = MSG_CHUNK) -> list[str]:
    """超长时在换行处切分，避免拆断段落。"""
    if len(text) <= max_len:
        return [text]
    parts = []
    remaining = text
    while remaining:
        if len(remaining) <= max_len:
            parts.append(remaining)
            break
        cut = remaining.rfind("\n", 0, max_len)
        if cut <= 0:
            cut = max_len
        parts.append(remaining[:cut].rstrip())
        remaining = remaining[cut:].lstrip("\n")
    return parts


def build_website_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("🌐 打开网站", url=WEBSITE_URL)
    ]])


async def get_item_content(item: dict, lang: str = "zh-CN") -> str:
    source = item.get("source") or ""
    title_key = item.get("titleKey") or item.get("title") or ""
    raw_html = item.get("previewHtml") or item.get("preview") or ""
    if source and source != "catalog":
        try:
            detail = await asyncio.to_thread(fetch_detail, source, title_key, lang)
            if detail and detail.get("content"):
                raw_html = detail["content"]
        except Exception:
            logger.exception("获取全文失败 title=%r", title_key)
    return raw_html


async def send_item_full(chat, index: int, item: dict, lang: str = "zh-CN") -> None:
    """一条结果一条消息：加粗标题 + 正文。"""
    title = item.get("title") or ""
    raw_html = await get_item_content(item, lang)
    body = format_item_body(raw_html)
    header = f"<b>{index}. {escape(title)}</b>\n\n"
    full_text = header + body

    for chunk in split_html_message(full_text):
        await chat.send_message(chunk, parse_mode="HTML")


# ============ Bot 命令处理 ============
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    USER_SEEN.add(chat_id)

    await update.message.reply_text(
        f"你好 {user.first_name}! 🙏\n\n"
        f"欢迎使用「按时分粮」Bot\n"
        f"📚 已加载 {LOADED_COUNT:,} 条查经内容\n\n"
        f"💡 目前开放【诗歌】查询，直接输入关键词即可",
        reply_markup=build_website_keyboard(),
    )
    await update.message.reply_text(
        "👇 选择分类后开始查询",
        reply_markup=get_main_keyboard(),
    )


async def send_search_results(
    chat,
    context: ContextTypes.DEFAULT_TYPE,
    items: list,
    query: str,
    category_name: str,
    *,
    welcome_prefix: str = "",
    lang: str = "zh-CN",
) -> None:
    display_items = items[:MAX_RESULTS]

    header = welcome_prefix + (
        f"📚 在【{category_name}】找到 {len(items)} 条结果"
    )
    if len(items) > MAX_RESULTS:
        header += f"，显示前 {MAX_RESULTS} 条"
    header += f"：「{escape(query)}」"

    await chat.send_action("typing")
    await chat.send_message(header, parse_mode="HTML")

    for idx, item in enumerate(display_items, 1):
        await send_item_full(chat, idx, item, lang)

    await chat.send_message("⬇️ 操作", reply_markup=build_website_keyboard())


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return

    user = update.effective_user
    user_input = update.message.text.strip()
    chat_id = update.effective_chat.id

    is_first_time = chat_id not in USER_SEEN
    USER_SEEN.add(chat_id)

    if user_input in CATEGORY_BUTTONS:
        if user_input not in ENABLED_CATEGORIES:
            await update.message.reply_text(
                "该分类暂未完成，敬请期待。\n\n"
                "目前仅开放【诗歌】查询。",
                reply_markup=get_main_keyboard(),
            )
            return
        category = user_input
        USER_CATEGORY[chat_id] = category
        category_name = category.split()[-1]
        await update.message.reply_text(
            f"✅ 已切换到【{category_name}】\n\n"
            f"请输入查询内容，例如：\n"
            f"• 三一神 / 神圣的经纶\n"
            f"• 诗歌第1首",
            reply_markup=get_main_keyboard(),
        )
        return

    category = USER_CATEGORY.get(chat_id) or DEFAULT_CATEGORY
    if category not in ENABLED_CATEGORIES:
        category = DEFAULT_CATEGORY
    USER_CATEGORY[chat_id] = category

    category_api = CATEGORY_DATA[category]
    category_name = category.split()[-1]

    logger.info("用户 %s (%s) 查询: [%s] %s", user.first_name, chat_id, category_name, user_input)
    await update.message.chat.send_action("typing")

    try:
        result = await asyncio.to_thread(search_in_api, user_input, category_api, MAX_RESULTS)
    except Exception as exc:
        logger.exception("搜索 API 调用失败")
        await update.message.reply_text(
            f"😔 搜索服务暂时不可用，请稍后再试。\n({exc})",
            reply_markup=get_main_keyboard(),
        )
        return

    items = result.get("items") or []
    if not result.get("found") or not items:
        await update.message.reply_text(
            f"😔 在【{category_name}】里没找到「{user_input}」\n\n"
            f"试试：\n"
            f"• 换个关键词\n"
            f"• 点底部按钮切换到其他分类",
            reply_markup=get_main_keyboard(),
        )
        return

    welcome_prefix = ""
    if is_first_time:
        welcome_prefix = (
            f"你好 {user.first_name}! 🙏 欢迎使用「按时分粮」Bot\n"
            f"📚 已加载 {LOADED_COUNT:,} 条查经内容\n"
            f"💡 点底部按钮切换分类，直接输入关键词查询\n"
            f"━━━━━━━━━━━━━━━━━━\n\n"
        )

    await send_search_results(
        update.message.chat,
        context,
        items,
        result.get("query") or user_input,
        category_name,
        welcome_prefix=welcome_prefix,
        lang=result.get("lang") or "zh-CN",
    )


async def on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(
        "Handler 异常 update=%s error=%s",
        update,
        context.error,
        exc_info=context.error,
    )


# ============ 主程序 ============
async def main():
    print("Bot starting...")
    if check_api_ready():
        print("Search API ready")
    else:
        print("WARNING: Search API not responding on :8020")

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(on_error)

    print("Bot online. Press Ctrl+C to stop.")
    await app.initialize()
    try:
        me = await app.bot.get_me()
        logger.info("Bot 身份 @%s (id=%s)", me.username, me.id)
        wh = await app.bot.get_webhook_info()
        if wh.url:
            logger.warning("检测到 webhook=%s，改为 polling 模式", wh.url)
            await app.bot.delete_webhook(drop_pending_updates=True)
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("Polling 已启动，等待消息…")
        await asyncio.Future()
    finally:
        if app.updater.running:
            await app.updater.stop()
        if app.running:
            await app.stop()
        await app.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
