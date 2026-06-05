# polish_router.py
# test_B 文章润色路由

from __future__ import annotations

import asyncio
import logging
import os

from fastapi import APIRouter, HTTPException
from openai import OpenAI
from pydantic import BaseModel

logger = logging.getLogger(__name__)


# ── DeepSeek 调用 ────────────────────────────────────────────────

async def call_deepseek(system: str, user_content: str) -> str:
    """轻量 DeepSeek 调用，专用于文章润色。只返回文本。"""
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DeepSeek 未配置（请设置 DEEPSEEK_API_KEY）")

    def _sync() -> str:
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
            timeout=600.0,
        )
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user_content},
            ],
            max_tokens=4000,
            temperature=0.7,
        )
        if not response.choices:
            return ""
        return (response.choices[0].message.content or "").strip()

    return await asyncio.to_thread(_sync)


# ── Prompt 定义 ──────────────────────────────────────────────────

SYSTEM_PROMPT_BASE = (
    "你是一位专业的文章润色专家。"
    "只返回润色后的文章正文，不加任何说明或前言。"
)
RECOVERY_ADDON = (
    "你熟悉倪柝声、李常受及主恢复的神学语境与用词风格。"
    "润色时若涉及属灵、信仰相关内容，措辞须体现主恢复的色彩，而非一般基督教或宗教色彩。"
)


def get_user_prompt(style: str, article: str) -> str:
    templates = {
        'formal': f'''请把以下文章润色为正式严谨风格。
要求：用词精准规范，句式完整严谨，逻辑清晰，
避免口语化和主观情绪，常使用专业术语，
使文章显得权威、客观、可信。
适用场景：学术论文、商业报告、官方文件、新闻稿、公文。

文章内容：
{article}''',

        'academic': f'''请把以下文章润色为专业学术风格。
要求：在正式风格基础上更具学术性，
大量使用学科特定术语、被动语态和复杂从句，
强调论证过程和文献支持，
提升文章的学术价值和专业性，符合学术出版规范。
适用场景：期刊论文、学位论文、研究报告。

文章内容：
{article}''',

        'concise': f'''请把以下文章润色为简洁干练风格。
要求：直奔主题，语言精炼，多用短句和要点列表，
避免冗长的修饰和重复，
提高信息传递效率，节省阅读时间，显得专业且高效。
适用场景：商务邮件、工作汇报、PPT、摘要、备忘录。

文章内容：
{article}''',

        'literary': f'''请把以下文章润色为优雅文学风格。
要求：注重修辞和文采，词汇丰富有韵味，句式多变，
善于运用比喻、排比等手法，营造意境和情感共鸣，
增强文章的艺术感染力，让文字更优美、更打动人心。
适用场景：散文、小说、诗歌、博客、品牌故事。

文章内容：
{article}''',

        'social_media': f'''请把以下文章润色为生动新媒体风格。
要求：使用网络流行语，短段落多换行，
互动性强（多用"你""我们"等代词），标题吸睛，
提升文章点击率和阅读量，更接地气，更容易在社交媒体上传播。
适用场景：微信公众号、微博、小红书、B站视频脚本。

文章内容：
{article}''',

        'conversational': f'''请把以下文章润色为亲切口语风格。
要求：模仿日常说话习惯，使用口语词、语气词、疑问句，
句子结构相对松散，听起来自然亲切，
拉近与读者/听众的距离，使内容更易理解和接受。
适用场景：演讲稿、视频口播稿、podcasts、内部分享。

文章内容：
{article}''',

        'persuasive': f'''请把以下文章润色为说服性风格。
要求：强调卖点和收益，使用号召性用语（CTA），
调动情绪（如紧迫感、渴望），善用修辞问句，
激发读者行动欲，有效实现转化。
适用场景：产品介绍、广告文案、销售页、福音单张、活动推广。

文章内容：
{article}''',
    }
    return templates[style]


STYLES = {
    'formal':         '正式严谨风格（适用于学术论文、商业报告、官方文件）',
    'academic':       '专业学术风格（适用于期刊论文、学位论文、研究报告）',
    'concise':        '简洁干练风格（适用于商务邮件、工作汇报、PPT）',
    'literary':       '优雅文学风格（适用于散文、博客、品牌故事）',
    'social_media':   '生动新媒体风格（适用于微信公众号、小红书、B站视频脚本）',
    'conversational': '亲切口语风格（适用于演讲稿、视频脚本、内部分享）',
    'persuasive':     '说服性风格（适用于广告文案、福音单张、活动推广）',
}


# ── 请求模型与路由 ───────────────────────────────────────────────

class PolishRequest(BaseModel):
    article: str
    styles: list[str]
    recovery_style: bool = True


router = APIRouter(prefix='/api/testb')


@router.post("/polish", summary="文章润色（多风格）")
async def polish(request: PolishRequest):
    if not request.article.strip():
        raise HTTPException(status_code=400, detail="文章内容不能为空")
    if not request.styles:
        raise HTTPException(status_code=400, detail="请至少选择一种风格")
    invalid = [s for s in request.styles if s not in STYLES]
    if invalid:
        raise HTTPException(status_code=400, detail=f"无效风格：{invalid}")

    system = SYSTEM_PROMPT_BASE
    if request.recovery_style:
        system = RECOVERY_ADDON + "\n" + SYSTEM_PROMPT_BASE

    async def _run_one(style: str):
        result = await call_deepseek(system, get_user_prompt(style, request.article))
        return style, result

    pairs = await asyncio.gather(*[_run_one(s) for s in request.styles])
    return {"results": {style: result for style, result in pairs}}


@router.post("/styles", summary="返回可用润色风格")
async def styles():
    return STYLES


# ── 恩典陵园见证稿润色 ───────────────────────────────────────────

GRAVE_SYSTEM_PROMPT = (
    "你是一位专业的见证稿润色专家，熟悉倪柝声、李常受及主恢复的神学语境与用词风格。"
    "润色时须遵守以下原则："
    "1. 保持庄重敬虔：维持严肃、虔诚的语气氛围；"
    "2. 忠于原文：不改变原意、结构和核心信息；"
    "3. 术语准确：保持信仰术语一致性（如\"会所\"、\"奋力活动的神\"等特定表达不变）；"
    "4. 主恢复特色：体现主恢复而非一般宗教色彩；"
    "5. 微调优化：仅对词语、句式做细微调整，提升流畅度和清晰度；"
    "6. 逻辑严密：修正语法，优化段落衔接，确保表达准确有力。"
    "只返回润色后的文章正文，不加任何说明或前言。"
)


def get_grave_user_prompt(role: str, article: str) -> str:
    templates = {
        'colleague': f'''请把以下见证稿润色为同工角色风格。
角色定位：你是一位教会中的同工，从牧养和属灵建造的角度润色已逝同工的见证稿。
语言风格：清晰结构、精炼、铿锵有力、肯定语气，提炼并升华生命见证的属灵价值。
适用场景：真理性强或要求精炼有力度的见证稿。

见证稿内容：
{article}''',
        'family': f'''请把以下见证稿润色为亲友角色风格。
角色定位：你是一位爱主的逝者的亲友，润色已逝亲人的见证稿，强调她/他对家庭、教会的摆上；既要纪念逝者，也要给家人和亲友带来安慰和盼望。
语言风格：主观情感表达极其浓厚、丰富、深入感染人，深刻挖掘并突出文稿中的情感层次，使怀念、感恩、盼望等情绪自然流淌，感人至深。通过细腻的措辞、恰当的排比与呼应，令读者产生强烈共鸣，感受到属灵生命的温暖与力量。
适用场景：要求深入情感表达的见证稿。

见证稿内容：
{article}''',
        'editor': f'''请把以下见证稿润色为编辑者角色风格。
角色定位：你是一位负责编辑纪念文集的人，润色已逝爱主的弟兄姊妹的见证稿，综合考虑信仰见证、服事精神、生命影响力三个维度。
语言风格：文法自然，情感表达恰当，专业严谨通用性强。
适用场景：专业严谨通用性强的见证稿，如倪弟兄、李弟兄的见证。

见证稿内容：
{article}''',
    }
    return templates[role]


GRAVE_ROLES = {
    'colleague': '同工角色（真理性强、精炼有力度的见证稿）',
    'family':    '亲友角色（深入情感表达的见证稿）',
    'editor':    '编辑者角色（专业严谨通用性强的见证稿）',
}


class GravePolishRequest(BaseModel):
    article: str
    roles: list[str]
    recovery_style: bool = True


@router.post("/grave-polish", summary="恩典陵园见证稿润色（多角色）")
async def grave_polish(request: GravePolishRequest):
    if not request.article.strip():
        raise HTTPException(status_code=400, detail="文章内容不能为空")
    if not request.roles:
        raise HTTPException(status_code=400, detail="请至少选择一个角色")
    invalid = [r for r in request.roles if r not in GRAVE_ROLES]
    if invalid:
        raise HTTPException(status_code=400, detail=f"无效角色：{invalid}")

    async def _run_one(role: str):
        result = await call_deepseek(GRAVE_SYSTEM_PROMPT, get_grave_user_prompt(role, request.article))
        return role, result

    pairs = await asyncio.gather(*[_run_one(r) for r in request.roles])
    return {"results": {role: result for role, result in pairs}}


@router.post("/grave-roles", summary="返回可用见证稿角色")
async def grave_roles():
    return GRAVE_ROLES


# ── 召会通讯及见证类润色（Claude） ───────────────────────────────

async def call_claude(user_content: str) -> str:
    """轻量 Claude 调用，专用于召会通讯及见证类润色。只返回文本。"""
    api_key = os.environ.get("CLAUDE_API_KEY")
    if not api_key:
        raise RuntimeError("Claude 未配置（请设置 CLAUDE_API_KEY）")

    def _sync() -> str:
        import anthropic

        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            messages=[{"role": "user", "content": user_content}],
        )
        if not message.content:
            return ""
        return (message.content[0].text or "").strip()

    return await asyncio.to_thread(_sync)


def get_church_user_prompt(lang: str, article_type: str, article: str) -> str:
    templates = {
        ('zh', 'report'): f'''请润色这篇召会报告：
1. 事实讲清楚
2. 要有属灵内涵
3. 保留所有数据和术语
4. 加小标题、分段
5. 语言更流畅感人
6. 不改任何事实

文章内容：
{article}''',
        ('zh', 'testimony'): f'''请润色这篇见证类文章：
1. 保留所有事实（日期、数字、人名、地名、术语）
2. 突出见证亮点和属灵意义
3. 加小标题、合理分段
4. 语言生动感人、有画面感

文章内容：
{article}''',
        ('en', 'report'): f'''Please polish this church report:
1). Present facts clearly
2). Highlight spiritual significance and depth
3). Preserve ALL data (dates, numbers, names, places, terms)
4). Add subheadings and proper paragraphing
5). Make language flowing and touching
6). Never alter any factual information

Article content:
{article}''',
        ('en', 'testimony'): f'''Please polish this testimony article from the Lord's recovery:
1). Preserve all facts: Ensure all facts (dates, numbers, names, places, terms) are kept unchanged.
2). Highlight testimonies and spiritual significance
3). Add subheadings and proper paragraphing
4). Make language vivid, touching, and engaging

Article content:
{article}''',
    }
    return templates[(lang, article_type)]


class ChurchPolishRequest(BaseModel):
    article: str
    lang: str  # 'zh' 或 'en'
    article_type: str  # 'report' 或 'testimony'


@router.post("/church-polish", summary="召会通讯及见证类润色（Claude）")
async def church_polish(request: ChurchPolishRequest):
    if not request.article.strip():
        raise HTTPException(status_code=400, detail="文章内容不能为空")
    if request.lang not in ("zh", "en"):
        raise HTTPException(status_code=400, detail="lang 必须为 zh 或 en")
    if request.article_type not in ("report", "testimony"):
        raise HTTPException(status_code=400, detail="article_type 必须为 report 或 testimony")

    result = await call_claude(
        get_church_user_prompt(request.lang, request.article_type, request.article)
    )
    return {"result": result}
