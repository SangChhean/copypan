from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from openai import OpenAI
import asyncio
import os

STYLES = {
    'formal':        '正式严谨风格（适用于学术论文、商业报告、官方文件）',
    'academic':      '专业学术风格（适用于期刊论文、学位论文、研究报告）',
    'concise':       '简洁干练风格（适用于商务邮件、工作汇报、PPT）',
    'literary':      '优雅文学风格（适用于散文、博客、品牌故事）',
    'social_media':  '生动新媒体风格（适用于公众号、小红书、视频脚本）',
    'conversational':'亲切口语风格（适用于演讲稿、视频脚本、内部分享）',
    'persuasive':    '说服性风格（适用于福音单张、广告文案、活动推广）',
}
STYLES_LABEL = {
    'formal': '正式严谨', 'academic': '专业学术', 'concise': '简洁干练',
    'literary': '优雅文学', 'social_media': '生动新媒体',
    'conversational': '亲切口语', 'persuasive': '说服性',
}

MEMORIAL_PRINCIPLES = """
润色原则：
1. 保持庄重敬虔：维持严肃、虔诚的语气氛围
2. 忠于原文：不改变原意、结构和核心信息
3. 术语准确：保持信仰术语一致性（如「会所」、「奋力活动的神」等特定表达不变）
4. 主恢复特色：体现主恢复而非一般宗教色彩
5. 微调优化：仅对词语、句式做细微调整，提升流畅度和清晰度
6. 逻辑严密：修正语法，优化段落衔接，确保表达准确有力
只返回润色后的正文，不加任何说明。
"""

MEMORIAL_ROLES = {
    'coworker': {
        'label': '同工角色',
        'desc': '适用于：真理性强或要求精炼有力度的见证稿',
        'system': '你是一位教会中的同工，从牧养和属灵建造的角度，清晰的结构、精炼、铿锵有力、肯定的语气来「提炼并升华」生命见证的属灵价值。'
    },
    'family': {
        'label': '亲友角色',
        'desc': '适用于：要求深入富有情感表达的见证稿',
        'system': '你是一位爱主的逝者的亲友，情感表达极其浓厚、丰富、深入感染人，深刻挖掘并突出文稿中的情感层次，使怀念、感恩、盼望等情绪自然流淌，感人至深。'
    },
    'editor': {
        'label': '编辑者角色',
        'desc': '适用于：专业严谨通用性强的见证稿（如倪弟兄、李弟兄的见证）',
        'system': '你是一位负责编辑纪念文集的人，文法自然，情感表达恰当，专业严谨通用性强，综合考虑信仰见证、服事精神、生命影响力三个维度。'
    },
}


async def call_deepseek(system: str, user: str) -> str:
    api_key = os.environ.get("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DeepSeek 未配置（请设置 DEEPSEEK_API_KEY）")

    def _sync() -> str:
        client = OpenAI(
            api_key=api_key,
            base_url="https://api.deepseek.com",
            timeout=600.0,
        )
        r = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=4000,
            temperature=0.7,
        )
        if not r.choices:
            return ""
        return (getattr(r.choices[0].message, "content", None) or "").strip()

    return await asyncio.to_thread(_sync)


class PolishRequest(BaseModel):
    article: str
    style: str
    add_ministry_color: bool = False


class MemorialRequest(BaseModel):
    article: str
    role: str


router = APIRouter(prefix='/api/testc')


@router.get('/styles')
async def get_styles():
    return {
        key: {'label': STYLES_LABEL[key], 'desc': STYLES[key]}
        for key in STYLES
    }


@router.get('/roles')
async def get_roles():
    return {
        key: {'label': val['label'], 'desc': val['desc']}
        for key, val in MEMORIAL_ROLES.items()
    }


@router.post('/polish')
async def polish(request: PolishRequest):
    article = (request.article or "").strip()
    if not article:
        raise HTTPException(status_code=400, detail="文章内容不能为空")
    if request.style not in STYLES:
        raise HTTPException(status_code=400, detail=f"不支持的风格：{request.style}")

    system = "你是一位专业的文章润色专家，只返回润色后的文章正文，不加任何说明或前言。要体现主恢复而非一般宗教色彩。"
    user = f"请把以下文章润色为{STYLES[request.style]}：\n\n{article}"
    if request.add_ministry_color:
        user += "\n\n注意：要体现主恢复而非一般宗教色彩"
    try:
        result = await call_deepseek(system, user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"result": result}


@router.post('/memorial')
async def memorial(request: MemorialRequest):
    article = (request.article or "").strip()
    if not article:
        raise HTTPException(status_code=400, detail="文章内容不能为空")
    if request.role not in MEMORIAL_ROLES:
        raise HTTPException(status_code=400, detail=f"不支持的角色：{request.role}")

    role_cfg = MEMORIAL_ROLES[request.role]
    system = role_cfg["system"] + MEMORIAL_PRINCIPLES
    user = f"请润色以下见证稿：\n\n{article}"
    try:
        result = await call_deepseek(system, user)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"result": result}
