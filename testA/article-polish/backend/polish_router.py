import asyncio
import os

import anthropic
from fastapi import APIRouter, HTTPException
from openai import OpenAI
from pydantic import BaseModel

router = APIRouter(prefix="/api/testa")


def _call_deepseek_sync(system: str, user_content: str) -> str:
    client = OpenAI(
        api_key=os.environ.get("DEEPSEEK_API_KEY"),
        base_url="https://api.deepseek.com",
    )
    response = client.chat.completions.create(
        model="deepseek-chat",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        temperature=0.7,
        max_tokens=4000,
    )
    return response.choices[0].message.content


async def call_deepseek(system: str, user_content: str) -> str:
    return await asyncio.to_thread(_call_deepseek_sync, system, user_content)


async def call_claude(system: str, user_content: str) -> str:
    def _sync():
        client = anthropic.Anthropic(
            api_key=os.environ.get("CLAUDE_API_KEY")
        )
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=system,
            messages=[{"role": "user", "content": user_content}],
        )
        return message.content[0].text

    return await asyncio.to_thread(_sync)


CHURCH_PROMPTS = {
    "zh_church": "请润色这篇召会报告：1.事实讲清楚，2.要有属灵内涵，3.保留所有数据和术语，4.加小标题、分段，5.语言更流畅感人，6.不改任何事实",
    "zh_testimony": "请润色这篇见证类文章：1.保留所有事实（日期、数字、人名、地名、术语），2.突出见证亮点和属灵意义，3.加小标题、合理分段，4.语言生动感人、有画面感",
    "en_church": "Please polish this church report: 1). Present facts clearly 2). Highlight spiritual significance and depth 3). Preserve ALL data (dates, numbers, names, places, terms) 4). Add subheadings and proper paragraphing 5). Make language flowing and touching 6). Never alter any factual information",
    "en_testimony": "Please polish this testimony article from the Lord's recovery: 1). Preserve all facts：Ensure all facts (dates, numbers, names, places, terms) are kept unchanged. 2). Highlight testimonies and spiritual significance 3). Add subheadings and proper paragraphing 4). Make language vivid, touching, and engaging",
}

CHURCH_SYSTEM_ZH = "你是一位专业的教会文章润色专家。只返回润色后的文章正文，不加任何说明、前言或解释。保持原文的核心事实和信息，按指定要求优化语言表达。"
CHURCH_SYSTEM_EN = "You are a professional editor for church publications. Return only the polished article text, without any explanation, preface, or commentary. Preserve all factual content and polish the language according to the given instructions."


STYLES = {
    "formal": "正式严谨风格。适用场景：学术论文、商业报告、官方文件、新闻稿、公文。特点：用词精准、规范，句式完整严谨，逻辑清晰，避免口语化和主观情绪，常使用专业术语。润色效果：使文章显得权威、客观、可信。",
    "academic": "专业学术风格。适用场景：期刊论文、学位论文、研究报告。特点：在正式风格基础上，更具学术性。大量使用学科特定术语、被动语态和复杂从句，强调论证过程和文献支持。润色效果：提升文章的学术价值和专业性，符合学术出版规范。",
    "concise": "简洁干练风格。适用场景：商务邮件、工作汇报、PPT、摘要、备忘录。特点：直奔主题，语言精炼，多用短句和要点列表，避免冗长的修饰和重复。润色效果：提高信息传递效率，节省阅读时间，显得专业且高效。",
    "literary": "优雅文学风格。适用场景：散文、小说、诗歌、博客、品牌故事。特点：注重修辞和文采，词汇丰富有韵味，句式多变，善于运用比喻、排比等手法，营造意境和情感共鸣。润色效果：增强文章的艺术感染力，让文字更优美、更打动人心。",
    "social": '生动新媒体风格。适用场景：微信公众号文章、微博、小红书、B站视频脚本。特点：网络流行语、短段落、多换行、互动性强（使用"你""我们"等代词）、标题吸睛。润色效果：提升文章的点击率和阅读量，更接地气，更容易在社交媒体上传播。',
    "conversational": "亲切口语风格。适用场景：演讲稿、视频口播稿、podcasts、内部分享、对客沟通。特点：模仿日常说话的习惯，使用口语词、语气词、疑问句，句子结构相对松散，听起来自然、亲切。润色效果：拉近与读者/听众的距离，使内容更易理解和接受。",
    "persuasive": "说服性风格（广告/营销）。适用场景：产品介绍、广告文案、销售页、活动推广。特点：强调卖点和benefits，使用号召性用语（CTA），调动情绪（如紧迫感、渴望），修辞问句。润色效果：激发读者购买欲或行动欲，有效实现转化。",
}
SYSTEM_PROMPT = "你是一位专业的文章润色专家。只返回润色后的文章正文，不加任何说明、前言或解释。保持原文的核心意思和段落结构，仅在语言表达上按指定风格优化。"

MEMORIAL_ROLES = {
    "coworker": "你是一位教会中的同工，想要给已逝的同工的见证稿进行润色，从牧养和属灵建造的角度，清晰的结构、精炼、铿锵有力、肯定的语气来「提炼并升华」生命见证的属灵价值。",
    "family": "你是一位爱主的逝者的亲友，想要给已逝的亲人的见证稿进行润色，强调她/他对家庭、教会的摆上；既要纪念逝者，也要给家人和亲友带来安慰和盼望；你的主观情感表达必须要极其浓厚、丰富、深入感染人，深刻挖掘并突出文稿中的情感层次，使怀念、感恩、盼望等情绪自然流淌，感人至深。通过细腻的措辞、恰当的排比与呼应，令读者产生强烈共鸣，感受到属灵生命的温暖与力量。",
    "editor": "你是一位负责编辑纪念文集的人，想要给已逝的爱主的弟兄姊妹的见证稿进行润色，文法自然，情感表达恰当，专业严谨通用性强，综合考虑信仰见证、服事精神、生命影响力三个维度。",
}

MEMORIAL_SYSTEM_PROMPT = "你是一位专业的见证稿润色专家。只返回润色后的文章正文，不加任何说明、前言或解释。润色原则：1.保持庄重敬虔：维持严肃、虔诚的语气氛围；2.忠于原文：不改变原意、结构和核心信息；3.术语准确：保持信仰术语一致性（如「会所」、「奋力活动的神」等特定表达不变）；4.主恢复特色：体现主恢复而非一般宗教色彩；5.微调优化：仅对词语、句式做细微调整，提升流畅度和清晰度；6.逻辑严密：修正语法，优化段落衔接，确保表达准确有力。"


class PolishRequest(BaseModel):
    article: str
    style: str
    recovery_tone: bool = False


@router.post("/polish")
async def polish(request: PolishRequest):
    article = (request.article or "").strip()
    if not article:
        raise HTTPException(status_code=400, detail="文章不能为空")

    style = request.style
    if style not in STYLES:
        raise HTTPException(status_code=400, detail=f"无效风格，可选：{', '.join(STYLES.keys())}")

    recovery_hint = "\n\n要体现主恢复而非一般宗教色彩。" if request.recovery_tone else ""
    user_content = f"请把以下文章润色为{STYLES[style]}：\n\n{article}{recovery_hint}"
    result = await call_deepseek(SYSTEM_PROMPT, user_content)
    return {"result": result}


@router.get("/styles")
def list_styles():
    return STYLES


class MemorialRequest(BaseModel):
    article: str
    role: str


@router.post("/memorial")
async def memorial(request: MemorialRequest):
    if not request.article.strip():
        raise HTTPException(status_code=400, detail="见证稿内容不能为空")
    if request.role not in MEMORIAL_ROLES:
        raise HTTPException(status_code=400, detail="角色不存在")
    user_content = f"{MEMORIAL_ROLES[request.role]}请润色以下见证稿：\n\n{request.article}"
    result = await call_deepseek(MEMORIAL_SYSTEM_PROMPT, user_content)
    return {"result": result}


@router.get("/memorial_roles")
async def get_memorial_roles():
    return {
        "coworker": {"label": "同工", "desc": "真理性强、精炼有力度"},
        "family": {"label": "亲友", "desc": "深入富有情感表达"},
        "editor": {"label": "编辑者", "desc": "专业严谨、通用性强"},
    }


class ChurchRequest(BaseModel):
    article: str
    mode: str


@router.post("/church")
async def church(request: ChurchRequest):
    if not request.article.strip():
        raise HTTPException(status_code=400, detail="文章内容不能为空")
    if request.mode not in CHURCH_PROMPTS:
        raise HTTPException(status_code=400, detail="模式不存在")
    system = CHURCH_SYSTEM_EN if request.mode.startswith("en_") else CHURCH_SYSTEM_ZH
    user_content = f"{CHURCH_PROMPTS[request.mode]}\n\n{request.article}"
    result = await call_claude(system, user_content)
    return {"result": result}
