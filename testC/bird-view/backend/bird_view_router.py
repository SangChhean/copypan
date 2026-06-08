import os
import json
import re
import asyncio

import anthropic
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

BIRD_VIEW_SKELETON_PROMPT = """你是一位深入熟悉倪柝声与李常受职事的资深圣经研究者。
## 输入
纲目重点：{keyword}
相关信息：
{content}

## 任务
为这份纲目构建一个逻辑骨架——即纲目大点的推进顺序与方向。
骨架的基本推进方向是：
启示（真理根基）→ 经历（主观进入）→ 应用（实际操练）→ 目标（最终带到的地步）

## 规则
1. 只输出 JSON，绝对禁止输出代码围栏、前导文字、后置说明或任何非 JSON 字符；第一个字符必须是左花括号，最后一个字符必须是右花括号
2. 骨架为 4-7 步的有序数组，每步用一句话描述该维度的内容方向

## 输出格式
{{"skeleton": [
  {{"step": "第一步：..."}},
  {{"step": "第二步：..."}},
  {{"step": "第三步：..."}},
  {{"step": "第四步：..."}},
  {{"step": "第五步：..."}}
]}}"""


BIRD_VIEW_OUTLINE_PROMPT = """## 输入
纲目重点：{keyword}
纲目骨架：
{skeleton}
相关信息：
{content}

## 任务
为这篇文章写一个鸟瞰纲目——不是深挖某一点，而是俯瞰全篇，看见文章的来龙去脉、主要论点与属灵脉络，使读者一眼掌握整篇的结构与走向。

【最高优先级原则】
逐字引用（verbatim quotes）是最核心的要求，优先级高于所有其他要求。所有纲目内容必须直接从原文提取完整句子，不可改写、总结、概括或重述。当任何要求与「逐字引用」冲突时，优先保证逐字引用。

【鸟瞰的目标】
鸟瞰纲目的目的是让人从高处看见整篇文章的结构与走向：启示从哪里来、经历如何展开、应用落在哪里、目标带到何处。每一个大点都是文章某一段主要脉络的入口，串联起来就是整篇的鸟瞰图。

【格式规范】
1. 纲目层级序号规则：
   - 第一级：壹、贰、叁、肆、伍、陆、柒、捌、玖、拾……
   - 第二级：一、二、三、四、五、六……
   - 第三级：1、2、3、4……
   - 第四级：a、b、c、d……
2. 缩进与连接规则：
   - 第一级顶格，第二级缩进一个 Tab，第三级缩进两个 Tab，第四级缩进三个 Tab
   - 序号与纲目内容之间用一个 Tab 键连接，不可用顿号、全角空格或其他符号
   - 每条纲目之间不要空行，紧密排列
3. 标点符号规则：
   - 若该纲目有下一级纲目，经节出处之后加冒号
   - 若该纲目无下一级纲目，经节出处之后加句号
   - 纲目句中若有句号，改成分号（仅指内容中间出现的句号，末尾不受此规则影响）
   - 纲目中不可使用双引号；所有单引号必须用中文状态下的单引号
4. 圣经经节格式规则：
   - 每条纲目后用—连接经节出处
   - 经节格式：创世记一章一节为「创一1」，其他书卷依次类推
   - 同一书卷多个出处合并，如「启三1，四7」，同章不同节用顿号隔开
   - 所有层级（壹、一、1、a）都需要加经节出处
   - 两个数字之间用全角～连接

【内容规范】
1. 所有纲目内容必须直接从原文提取完整句子：
   【可以做的】：
   - 从原文中选择哪些句子
   - 调整句子的排列顺序
   - 将原文中紧密相连的短句用分号拼接
   - 使用最简短的连接语（如「因此」「这样」）来组织结构
   【绝对不可以做的】：
   - 改变原文的任何用词
   - 用自己的话「换一种说法」
   - 合并多个句子的意思成一句话
   - 提炼、归纳、概括原文的意思
   - 为了「概括下级纲目」而自己总结造句
   - 添加原文中没有的解释
2. 每个大点（壹贰叁级）必须直接从原文提取完整句子，包含关键词「{keyword}」，
   不可为了「概括下级纲目」而自己总结；
   若原文无单句同时满足以上要求，可用最简短连接语拼接两个相邻原文短句，
   但两个短句均须来自原文，且拼接后须包含关键词「{keyword}」
3. 每个纲目必须是完整的阐述，不可用短句
4. 若某纲目有下一级，下一级至少需要 2 个
5. 大点的排列顺序严格以骨架步骤为准，不可自行调整
6. 纲目内容不可重复
7. 篇幅覆盖文章主要脉络，控制在 A4 纸两页以内

【输出规范】
1. 第一行：篇题，即关键词「{keyword}」，单独一行，不加任何前缀
2. 「读经：」从原文提取 8～10 个重要经节出处，按圣经书卷顺序排列，同一书卷合并
3. 纲目内容（按骨架顺序展开）
4. 用纯文本作答，不使用 Markdown 格式，将纲目写在代码块中

【最后检查清单】
生成纲目后，请确认：
✓ 第一行是篇题（关键词），之后是读经，再之后是纲目内容
✓ 每条纲目都能在原文中找到对应的原句
✓ 每个大点包含关键词「{keyword}」
✓ 所有经节格式正确
✓ 序号格式正确（壹贰叁、一二三、123、abc）
✓ 缩进与 Tab 连接正确
✓ 标点符号正确（有下级用冒号，无下级用句号）
✓ 纲目之间无空行，紧密排列
✓ 无自己总结或改写的内容
✓ 大点（壹贰叁）没有被总结或改写，每个大点能在原文中找到对应原句
✓ 无「合并多个句子意思」或「提炼归纳」的内容"""


BIRD_VIEW_SOURCE_PROMPT_MINISTRY = """
一、读取以下职事信息的所有内容：
{content}

二、读完以下鸟瞰纲目后，给每条纲目加出处。
找到职事信息内容里的出处，为此纲目添加出处。

出处规则：
1. 若某一点纲目出自生命读经，出处格式：（……生命读经，第几篇）
2. 若某一点纲目出自倪柝声文集，出处格式：（倪柝声文集书名，第几篇/第几章）
3. 若某一点纲目出自李常受文集：
   - 出现在书名部分：（李常受文集年份第X册，书名，第几章）
   - 出现在篇题部分：（李常受文集年份第X册，书名，第几章）
   【不需要写章节的题目，只写第几章】
4. 出自圣经真理题库的纲目不需要加出处，返回原文即可

最重要原则：
- 只添加出处，不可修改纲目中的任何内容
- 若找不到出处，不可删除纲目，保留原文不加出处
- 若找不到出处，直接保留原纲目文字，不做任何标注
- 若找到多个出处，选其中任意一个即可
- 大点和小点都需要加出处
- 纲目序号与纲目内容之间必须用 Tab 键连接，不可用顿号、全角空格或其他符号
- 出处添加到整条纲目的最后
- 只输出代码块，不要输出任何分析过程、推理步骤或说明文字
- 添加出处后的纲目输出在代码块中

纲目内容：
{outline}
"""

BIRD_VIEW_SOURCE_PROMPT_FEAST = """
一、读取以下节期纲目的所有内容：
{content}

二、读完以下鸟瞰纲目后，给每条纲目加出处。
找到节期纲目内容里的出处，为此纲目添加出处。

出处格式：在每条纲目后面加：（特会名称，第X篇）
【切记不要写主题，只写特会名称和篇数】

例如：
原纲目：壹　神的建造乃是神心头的愿望，也是神救恩的目标─出二五8。
找到的出处：（2000年感恩节特会，新的复兴—过神人的生活，第二篇）
添加后：壹　神的建造乃是神心头的愿望，也是神救恩的目标─出二五8。（2000年感恩节特会，第二篇）

最重要原则：
- 只添加出处，不可修改纲目中的任何内容
- 若找不到出处，不可删除纲目，保留原文不加出处
- 若找到多个出处，选其中任意一个即可
- 大点和小点都需要加出处
- 纲目序号与纲目内容之间必须用 Tab 键连接，不可用顿号、全角空格或其他符号
- 出处添加到整条纲目的最后
- 只输出代码块，不要输出任何分析过程、推理步骤或说明文字
- 添加出处后的纲目输出在代码块中

纲目内容：
{outline}
"""


def _call_claude_sync(prompt: str, max_tokens: int) -> str:
    api_key = os.environ.get("CLAUDE_API_KEY")
    if not api_key:
        raise ValueError("CLAUDE_API_KEY not set")
    client = anthropic.Anthropic(api_key=api_key)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        temperature=0,
        messages=[{"role": "user", "content": prompt}],
    )
    if not message.content:
        return ""
    return message.content[0].text or ""


async def call_claude(prompt: str, max_tokens: int = 1000) -> str:
    return await asyncio.to_thread(_call_claude_sync, prompt, max_tokens)


def safe_parse_json(raw: str) -> dict:
    if not raw or not raw.strip():
        return {}
    s = raw.strip()
    if s.startswith("```"):
        lines = s.split("\n")
        s = "\n".join(lines[1:-1] if len(lines) > 2 and lines[-1].strip() == "```" else lines[1:])
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    try:
        obj = json.loads(s)
        return obj if isinstance(obj, dict) else {}
    except json.JSONDecodeError:
        return {}


def strip_code_fence(raw: str) -> str:
    if not raw or not isinstance(raw, str):
        return raw or ""
    s = raw.strip()
    lines = s.split("\n")
    fence_starts = []
    fence_ends = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("```"):
            if not fence_starts or len(fence_starts) == len(fence_ends):
                fence_starts.append(i)
            elif len(fence_starts) > len(fence_ends):
                fence_ends.append(i)
    if not fence_starts or not fence_ends:
        return raw
    last_end = fence_ends[-1]
    last_start = fence_starts[len(fence_ends) - 1]
    inner = lines[last_start + 1 : last_end]
    return "\n".join(inner).strip() if inner else raw


router = APIRouter(prefix="/api/testc/bird_view")


class SkeletonRequest(BaseModel):
    keyword: str
    type: str
    content: str


class OutlineRequest(BaseModel):
    keyword: str
    type: str
    content: str
    skeleton: str


class SourceRequest(BaseModel):
    keyword: str
    type: str
    content: str
    outline: str


@router.post("/skeleton")
async def bird_view_skeleton(req: SkeletonRequest):
    try:
        prompt = BIRD_VIEW_SKELETON_PROMPT.format(keyword=req.keyword, content=req.content)
        raw = await call_claude(prompt, max_tokens=1000)
        obj = safe_parse_json(raw)
        steps = obj.get("skeleton", []) if obj else []
        skeleton_text = "\n".join(
            f"{i + 1}. {s.get('step', '')}" for i, s in enumerate(steps)
        )
        return {
            "skeleton_json": steps,
            "skeleton_text": skeleton_text,
            "type": req.type,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/outline")
async def bird_view_outline(req: OutlineRequest):
    try:
        prompt = BIRD_VIEW_OUTLINE_PROMPT.format(
            keyword=req.keyword,
            skeleton=req.skeleton,
            content=req.content,
        )
        raw = await call_claude(prompt, max_tokens=8000)
        text = strip_code_fence(raw).strip()
        return {"outline": text, "type": req.type}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/source")
async def bird_view_source(req: SourceRequest):
    try:
        if req.type == "ministry":
            prompt = BIRD_VIEW_SOURCE_PROMPT_MINISTRY.format(
                content=req.content,
                outline=req.outline,
            )
        else:
            prompt = BIRD_VIEW_SOURCE_PROMPT_FEAST.format(
                content=req.content,
                outline=req.outline,
            )
        raw = await call_claude(prompt, max_tokens=8000)
        text = strip_code_fence(raw).strip()
        return {"outline_with_source": text, "type": req.type}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
