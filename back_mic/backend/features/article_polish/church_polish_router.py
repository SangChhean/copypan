import asyncio
import os
import anthropic
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel


async def call_claude_for_polish(system: str, user_content: str) -> str:
    def _sync():
        client = anthropic.Anthropic(api_key=os.environ.get('CLAUDE_API_KEY'))
        message = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=4000,
            system=system,
            messages=[{'role': 'user', 'content': user_content}]
        )
        return (message.content[0].text or '').strip()
    return await asyncio.to_thread(_sync)


CHURCH_PROMPTS = {
    'zh_report': {
        'label': '中文通讯类',
        'system': '你是一位专业的教会文章润色专家，只返回润色后的正文，不加任何说明。',
        'user_template': (
            '请润色这篇召会报告：\n'
            '1. 事实讲清楚\n'
            '2. 要有属灵内涵\n'
            '3. 保留所有数据和术语\n'
            '4. 加小标题、分段\n'
            '5. 语言更流畅感人\n'
            '6. 不改任何事实\n\n{article}'
        )
    },
    'zh_testimony': {
        'label': '中文见证类',
        'system': '你是一位专业的教会文章润色专家，只返回润色后的正文，不加任何说明。',
        'user_template': (
            '请润色这篇见证类文章：\n'
            '1. 保留所有事实（日期、数字、人名、地名、术语）\n'
            '2. 突出见证亮点和属灵意义\n'
            '3. 加小标题、合理分段\n'
            '4. 语言生动感人、有画面感\n\n{article}'
        )
    },
    'en_report': {
        'label': 'English Report',
        'system': 'You are a professional church article editor. Return only the polished article body without any explanation.',
        'user_template': (
            'Please polish this church report:\n'
            '1). Present facts clearly\n'
            '2). Highlight spiritual significance and depth\n'
            '3). Preserve ALL data (dates, numbers, names, places, terms)\n'
            '4). Add subheadings and proper paragraphing\n'
            '5). Make language flowing and touching\n'
            '6). Never alter any factual information\n\n{article}'
        )
    },
    'en_testimony': {
        'label': 'English Testimony',
        'system': "You are a professional church article editor from the Lord's recovery. Return only the polished article body without any explanation.",
        'user_template': (
            "Please polish this testimony article from the Lord's recovery:\n"
            '1). Preserve all facts (dates, numbers, names, places, terms)\n'
            '2). Highlight testimonies and spiritual significance\n'
            '3). Add subheadings and proper paragraphing\n'
            '4). Make language vivid, touching, and engaging\n\n{article}'
        )
    },
}


class ChurchPolishRequest(BaseModel):
    article: str
    type: str


router = APIRouter(prefix='/api/mic')


@router.get('/church-types')
async def get_church_types():
    return {k: {'label': v['label']} for k, v in CHURCH_PROMPTS.items()}


@router.post('/church-polish')
async def church_polish(request: ChurchPolishRequest):
    if not request.article.strip():
        raise HTTPException(status_code=400, detail='文章内容不能为空')
    if request.type not in CHURCH_PROMPTS:
        raise HTTPException(status_code=400, detail='无效的类型选项')
    prompt = CHURCH_PROMPTS[request.type]
    system = prompt['system']
    user = prompt['user_template'].format(article=request.article)
    result = await call_claude_for_polish(system, user)
    return {'result': result}
