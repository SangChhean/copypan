# -*- coding: utf-8 -*-
import anthropic
import asyncio
import os
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# ── Prompt 常量（原样复制自主站）────────────────────────────
MORNING_REVIVAL_OUTLINE = """我想为一篇文章写一个详细并深入的纲目。纲目要求如下：
1、严格要求每个纲目（大纲，中纲，小纲的每个纲目）必须从原文文章中直接提取句子来构建纲目，这是必须的，不可改写，不可使用自己总结的话，不可使用自己概括的话，不可以通过概括或重述的方式改写，所有纲目的内容必须完全从原文当中直接提取；提取的内容必须是文章的重点，紧扣篇题。
2、必须执行：每一个大纲和每一个中纲都必须加上经节的出处，每一个大纲和每一个中纲不可太短，至少有大约一行的长度。
3、大纲的思路结构和层级关系要严格按照原文思路结构和层级关系来组织，罗马大纲逻辑性强，必须提纲挈领，罗马大纲（壹，贰，叁，肆……）不超过十个。
4、纲目的层级序号严格按照原文标题的层级序号，壹的下一级是一，一的下一级是1，1的下一级是a，即一级序号为壹、贰，以此类推，二级为一、二以此类推，三级为1、2以此类推，四级为a、b以此类推。
5、每个纲目如果有下一级的纲目，下一级纲目至少需要2个。
6、请必须在每个纲目后边都加上圣经经节作支撑，用—连接，经节出处的格式是，创世记一章一节为：创一1，其他书卷依次类推。出来的纲目句末加经节的格式例如"如果我们恢复彼此互相的召会聚会，就会帮助圣徒成熟，预备主的新妇，将祂带回来，并引进祂的国度—来六1，启十九7。" 两个数字必须用全角的～连接
7、经节提取：在整个纲目最前面写出"读经：........"，从目标文章中提取 8～10 个重要的经节出处，按圣经书卷顺序排列，同一书卷内按章节顺序。同一书卷的经节用顿号隔开，不同书卷用逗号隔开。
8、纲目的序号与纲目中间必须用Tab键连接，不可用顿号、全角空格、逗号或其他的符号链接。
9、若一条纲目有下一级纲目，则这一条纲目句尾需加冒号，若这一条纲目没有下一级纲目，则这一条纲目句尾经节出处后面需加句号。
10、请记住纲目中的所有单引号必须用中文状态下的单引号，不可用英文状态下的单引号。
11、一条纲目句中若有句号，需将句号改成分号。
12、不需要生成主题，只需要生成纲目，纲目不可以重复。
13、纲目篇幅必须严格在A4纸三页之内，不得超过，不得超过。若篇幅超过三页，应优先精简中纲及小纲内容，但罗马大纲结构不可删减。
【晨兴信息选读内容】
{content}"""

TRANSCRIPT_OUTLINE = """以原文的纲目为主体框架，从听抄稿中提取精华内容，补充添加进原文的纲目里，形成最终的纲目，并将最终的纲目放在代码块中。纲目要求如下：
1、仔细阅读整个听抄稿，理解其结构和主题，识别独特且重要的内容，特别关注详细的解释性、紧扣主题的、扣人心弦的内容，以及与原纲目主题相关但未包含的内容。
2、了解原纲目的结构和逻辑，找出适合添加内容的位置，保证逻辑完整。
3、确保添加内容与原纲目内容内涵不重复，不会高度相似（高度相似：相似度超过80％）。
4、选择听抄稿中3～5处重要段落，保留原文的所有标点和经文引用。
5、将提取的内容插入原纲目的适当位置，不允许添加在"壹"大纲之前，且避免集中在某一处或某两处。
6、对提取的内容进行纲目序号的重新排序，排序规则为：壹的下一级是一，一的下一级是1，1的下一级是a，即一级序号为壹、贰，以此类推，二级为一、二以此类推，三级为1、2以此类推，四级为a、b以此类推。
7、确保添加内容与上下文逻辑连贯，保留所有标点和经文引用。
8、确认整合后的文档保持结构完整，检查编号是否连续、格式是否一致。
9、从听抄稿提取的内容必须完全保持原文，不得改写或概括，验证所有添加的内容都保持原文不变。
10、提取的内容不应作为独立的大纲级别（壹、贰、叁等）添加；应作为现有大纲级别下的子级内容（如一、二、三或1、2、3或a、b、c等）插入，且必须插在其内容所属的那个大纲层级的正下方，不得插入到其他大纲层级下；添加的内容应自然融入原纲目的现有结构中，确保与上下文逻辑连贯，不破坏原有结构和层次关系。
11、从听抄稿提取的内容，若每个纲目有下一级的纲目，下一级纲目至少需要提取2个。
12、原纲目中每个原有纲目点的层级结构和出现顺序绝对不能改变，也不能移动任何原有纲目点的位置，只能在原有纲目点之间或之下插入新内容，并调整序号保持连续；整合后确保纲目序号连续且没有重复。
13、整合后的纲目应保持统一的格式，纲目序号与纲目内容之间必须用Tab键连接，不可用顿号、全角空格或其他符号连接。
13.5、从听抄稿提取的每一条纲目内容必须独立成一行，不得将多条内容用逗号、分号或其他符号合并在同一行；每条内容前必须有独立的纲目序号和Tab键。
14、一条纲目句中若有句号，需将句号改成分号。
15、在最终文档中，清晰标记从听抄稿添加的内容，标记形式为：换行符号＋【听抄稿添加开始】＋换行符号＋添加的内容＋换行符号＋【听抄稿添加结束】＋换行符号。
16、用代码块格式回复。
【原纲目】
{original_outline}
【听抄稿内容】
{transcript}"""

COMPOSITE_OUTLINE = """从晨兴纲目中提取精华内容，并将其整合听抄稿纲目中，形成复合的纲目，保持听抄稿原有格式和结构，并将最终的纲目放在代码块中。纲目要求如下：
1、仔细阅读整个晨兴纲目，理解其结构和主题，识别独特且重要的内容，特别关注详细的解释性、紧扣主题的、扣人心弦的内容，以及与复合纲目主题相关但未包含的内容。
2、了解听抄稿纲目的结构和逻辑，找出适合添加内容的位置，保证逻辑完整。
3、确保添加内容与听抄稿纲目内容在字面上不完全重复（逐字相同），即使主题相似也应添加，因为晨兴纲目提供的是不同角度的阐述。
4、选择晨兴纲目中4～6处重要段落，保留原文的所有标点和经文引用。
5、将提取的内容插入听抄稿纲目的适当位置，不允许添加在"壹"大纲之前，且避免集中在某一处或某两处。
6、对提取的内容进行纲目序号的重新排序，排序规则为：壹的下一级是一，一的下一级是1，1的下一级是a，即一级序号为壹、贰，以此类推，二级为一、二以此类推，三级为1、2以此类推，四级为a、b以此类推。
7、确保添加内容与上下文逻辑连贯，保留所有标点和经文引用。
8、确保整合后的内容最后一页的篇幅超过A4纸半页（字体为小四）。
9、确认整合后的文档保持结构完整，检查编号是否连续、格式是否一致。
10、从晨兴纲目提取的内容必须完全保持原文，不得改写或概括，验证所有添加的内容都保持原文不变。
11、提取的内容不应作为独立的大纲级别（壹、贰、叁等）添加到复合纲目中，而应作为现有大纲级别下的子级内容（如一、二、三或1、2、3或a、b、c等）进行添加；添加的内容应自然地融入听抄稿纲目的现有结构中，而不是创建新的大纲层级，确保所有添加的内容都能与上下文逻辑连贯，并且不破坏原有的纲目结构和层次关系。
12、从晨兴纲目提取的内容，若每个纲目有下一级的纲目，下一级纲目至少需要提取2个。
13、听抄稿纲目中每个原有纲目点的层级结构（壹、贰、叁或一、二、三或1、2、3或a、b、c）绝对不能改变，只能调整序号以保持连续性，整合后确保纲目序号连续且没有重复的纲目序号出现。
14、整合后复合的纲目应保持统一的格式，纲目序号与纲目内容之间必须用Tab键连接，不可用顿号或其他符号连接。
15、一条纲目句中若有句号，需将句号改成分号。
16、在最终文档中，清晰标记从晨兴纲目添加的内容，标记形式为：换行符号＋【添加开始】＋换行符号＋添加的内容＋换行符号＋【添加结束】＋换行符号。
17、听抄稿纲目中原有的【听抄稿添加开始】和【听抄稿添加结束】标记必须完整保留在输出中，位置和配对不得改变；这些标记与本规则第16条的【添加开始】/【添加结束】是两套不同的标记，分别标识不同来源的内容，不得混用、替换或删除。
18、用代码块格式回复。
【听抄稿的纲目】
{transcript_outline}
【晨兴信息选读的纲目】
{morning_revival_outline}"""


# ── Claude 调用 ────────────────────────────────────────────
async def call_claude(prompt: str, max_tokens: int = 8000) -> str:
    def _sync():
        client = anthropic.Anthropic(api_key=os.environ.get('CLAUDE_API_KEY'))
        message = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=max_tokens,
            temperature=0,
            messages=[{'role': 'user', 'content': prompt}],
        )
        return message.content[0].text or ''
    return await asyncio.to_thread(_sync)


# ── strip_code_fence ───────────────────────────────────────
def strip_code_fence(raw: str) -> str:
    text = (raw or '').strip()
    lines = text.split('\n')
    last_fence_start = -1
    for idx, line in enumerate(lines):
        if line.strip().startswith('```'):
            last_fence_start = idx
    if last_fence_start != -1:
        inner = []
        found_close = False
        for line in lines[last_fence_start + 1:]:
            if line.strip() == '```':
                found_close = True
                break
            inner.append(line)
        result = '\n'.join(inner).strip()
        if found_close and result:
            return result
        if inner:
            content_lines = []
            started = False
            for line in inner:
                stripped = line.strip()
                if not started:
                    if ('读经：' in stripped or '讀經：' in stripped or
                            re.match(r'^[壹贰叁肆伍陆柒捌玖拾]', stripped)):
                        started = True
                        content_lines.append(line)
                else:
                    content_lines.append(line)
            if content_lines:
                return '\n'.join(content_lines).strip()
    if text.startswith('```'):
        clean_lines = []
        started = False
        for line in text.split('\n'):
            stripped = line.strip()
            if stripped.startswith('```'):
                continue
            if not started:
                if ('读经：' in stripped or '讀經：' in stripped or
                        re.match(r'^[壹贰叁肆伍陆柒捌玖拾]', stripped)):
                    started = True
                    clean_lines.append(line)
            else:
                clean_lines.append(line)
        if clean_lines:
            return '\n'.join(clean_lines).strip()
    return text


# ── 请求模型 ───────────────────────────────────────────────
class MorningRevivalRequest(BaseModel):
    content: str

class TranscriptRequest(BaseModel):
    original_outline: str
    transcript: str

class CompositeRequest(BaseModel):
    morning_revival_outline: str
    transcript_outline: str


# ── 路由 ───────────────────────────────────────────────────
router = APIRouter(prefix='/api/testa/feast_outline')


@router.post('/morning_revival')
async def morning_revival(req: MorningRevivalRequest):
    if not req.content.strip():
        raise HTTPException(status_code=400, detail='晨兴信息选读内容不能为空')
    prompt = MORNING_REVIVAL_OUTLINE.format(content=req.content)
    raw = await call_claude(prompt)
    return {'outline': strip_code_fence(raw)}


@router.post('/transcript')
async def transcript(req: TranscriptRequest):
    if not req.original_outline.strip():
        raise HTTPException(status_code=400, detail='纲目原文不能为空')
    if not req.transcript.strip():
        raise HTTPException(status_code=400, detail='听抄稿不能为空')
    prompt = TRANSCRIPT_OUTLINE.format(
        original_outline=req.original_outline,
        transcript=req.transcript,
    )
    raw = await call_claude(prompt)
    return {'outline': strip_code_fence(raw)}


@router.post('/composite')
async def composite(req: CompositeRequest):
    if not req.morning_revival_outline.strip():
        raise HTTPException(status_code=400, detail='晨兴纲目不能为空')
    if not req.transcript_outline.strip():
        raise HTTPException(status_code=400, detail='听抄稿纲目不能为空')
    prompt = COMPOSITE_OUTLINE.format(
        transcript_outline=req.transcript_outline,
        morning_revival_outline=req.morning_revival_outline,
    )
    raw = await call_claude(prompt)
    return {'outline': strip_code_fence(raw)}


# ── 序言 Prompt ────────────────────────────────────────────
PREFACE_OUTLINE = """请将以下「听抄稿序言」内容整理成纲目格式，要求：
1、严格要求序言的每个纲目必须从原文开头部分直接提取句子来构建纲目，不可改写，不可使用自己总结的话，不可使用自己概括的话，不可以通过概括或重述的方式改写，所有纲目的内容必须完全从原文当中直接提取；提取的内容必须是文章的重点。
2、直接以"序言"为标题，不使用壹、贰等罗马序号；序言下的中纲使用一、二、三序号，中纲下的小纲使用1、2、3序号，与正文层级体系一致。
3、序言包含大纲、中纲及小纲的结构，确保有实际内容，不能只有"序言"两个字。
4、每个纲目如果有下一级的纲目，下一级纲目至少需要2个。
5、纲目序号与纲目内容之间必须用Tab键连接，不可用顿号、全角空格、逗号或其他符号连接。
6、若一条纲目有下一级纲目，则这一条纲目句尾需加冒号；若这一条纲目没有下一级纲目，则这一条纲目句尾需加句号。
7、一条纲目句中若有句号，需将句号改成分号。
8、纲目不可以有重复；若原文句子过于口语化，可在同一段落中寻找表达相同意思的书面化句子替代，若找不到替代句子，则保留原句直接提取，不可自行改写。
9、必须在序言及其下每个纲目（包括中纲、小纲）后边都加上圣经经节作支撑，用—连接，经节出处的格式是，创世记一章一节为：创一1，其他书卷依次类推。出来的纲目句末加经节的格式例如"如果我们恢复彼此互相的召会聚会，就会帮助圣徒成熟，预备主的新妇，将祂带回来，并引进祂的国度—来六1，启十九7。"两个数字必须用全角的～连接。
10、如果原来的句子中间有经节，则不需要在句末再加经节出处，保留在原位置即可。如，"我们是亚伯拉罕的真后裔（加三7），该是在地上作客的，像他一样移居并支搭帐棚（来十一9、13，彼前二11）。"
11、用代码块格式回复。
【序言格式示例】
    序言	神的生命是永远的生命，就是神自己分赐到我们里面，作我们的生命和生命的供应—约一4，十10：
        一	生命就是三一神分赐到我们里面，使我们与神有生机的联结—约一4：
            1	神的生命使我们在生命和性情上与神一样，却无分于神格—彼后一4。
            2	这生命是非受造的，是永远、神圣、属灵的生命—约壹五11～12。
        二	我们需要天天经历基督作生命树，使我们在生命里长大—启二7：
            1	生命树表征三一神在基督里作我们的生命和生命的供应—启二二2，14。
            2	我们借着吃基督作生命树，就能在神圣的生命里长大成熟—来五12～14。
【听抄稿序言内容】
{content}"""

# ── 添言 Prompt ────────────────────────────────────────────
ADDENDUM_OUTLINE = """请将以下「听抄稿添言」内容整理成纲目格式，要求：
1、严格要求添言的每个纲目必须从原文开头部分直接提取句子来构建纲目，不可改写，不可使用自己总结的话，不可使用自己概括的话，不可以通过概括或重述的方式改写，所有纲目的内容必须完全从原文当中直接提取；提取的内容必须是文章的重点。
2、直接以"添言"为标题，不使用壹、贰等罗马序号；添言下的中纲使用一、二、三序号，中纲下的小纲使用1、2、3序号，与正文层级体系一致。
3、添言包含大纲、中纲及小纲的结构，确保有实际内容，不能只有"添言"两个字。
4、每个纲目如果有下一级的纲目，下一级纲目至少需要2个。
5、纲目序号与纲目内容之间必须用Tab键连接，不可用顿号、全角空格、逗号或其他符号连接。
6、若一条纲目有下一级纲目，则这一条纲目句尾需加冒号；若这一条纲目没有下一级纲目，则这一条纲目句尾需加句号。
7、一条纲目句中若有句号，需将句号改成分号。
8、纲目不可以有重复；若原文句子过于口语化，可在同一段落中寻找表达相同意思的书面化句子替代，若找不到替代句子，则保留原句直接提取，不可自行改写。
9、必须在添言及其下每个纲目（包括中纲、小纲）后边都加上圣经经节作支撑，用—连接，经节出处的格式是，创世记一章一节为：创一1，其他书卷依次类推。出来的纲目句末加经节的格式例如"如果我们恢复彼此互相的召会聚会，就会帮助圣徒成熟，预备主的新妇，将祂带回来，并引进祂的国度—来六1，启十九7。"两个数字必须用全角的～连接。
10、如果原来的句子中间有经节，则不需要在句末再加经节出处，保留在原位置即可。如，"我们是亚伯拉罕的真后裔（加三7），该是在地上作客的，像他一样移居并支搭帐棚（来十一9、13，彼前二11）。"
11、用代码块格式回复。
【添言格式示例】
    添言	神的生命是永远的生命，就是神自己分赐到我们里面，作我们的生命和生命的供应—约一4，十10：
        一	生命就是三一神分赐到我们里面，使我们与神有生机的联结—约一4：
            1	神的生命使我们在生命和性情上与神一样，却无分于神格—彼后一4。
            2	这生命是非受造的，是永远、神圣、属灵的生命—约壹五11～12。
        二	我们需要天天经历基督作生命树，使我们在生命里长大—启二7：
            1	生命树表征三一神在基督里作我们的生命和生命的供应—启二二2，14。
            2	我们借着吃基督作生命树，就能在神圣的生命里长大成熟—来五12～14。
【听抄稿添言内容】
{content}"""


# ── 请求模型 ───────────────────────────────────────────────
class PrefaceRequest(BaseModel):
    content: str

class AddendumRequest(BaseModel):
    content: str


# ── 路由 ───────────────────────────────────────────────────
@router.post('/preface')
async def preface(req: PrefaceRequest):
    if not req.content.strip():
        raise HTTPException(status_code=400, detail='序言内容不能为空')
    prompt = PREFACE_OUTLINE.format(content=req.content)
    raw = await call_claude(prompt)
    return {'outline': strip_code_fence(raw)}


@router.post('/addendum')
async def addendum(req: AddendumRequest):
    if not req.content.strip():
        raise HTTPException(status_code=400, detail='添言内容不能为空')
    prompt = ADDENDUM_OUTLINE.format(content=req.content)
    raw = await call_claude(prompt)
    return {'outline': strip_code_fence(raw)}
