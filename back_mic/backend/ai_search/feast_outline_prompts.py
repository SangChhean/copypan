"""
节期纲目 Prompt 模板（晨兴信息选读、听抄稿、复合纲目）
"""

# 晨兴信息选读的纲目：根据晨兴内容生成纲目
MORNING_REVIVAL_OUTLINE = """请根据以下「晨兴信息选读」的内容，制作一份纲目。

要求：
1. 纲目层级：壹、贰、叁… → 一、二、三… → 1、2、3… → a、b、c…；每个纲目若有下级，下级至少 2 条。
2. 每条纲目（大纲、中纲）需有经节支撑，格式：纲目内容—创一1，太五3。同一书卷用顿号，不同书卷用逗号；章与节之间用全角～。
3. 纲目前写出「读经：……」，从文中提取 8～10 个经节，按书卷顺序排列。
4. 序号与纲目之间用 Tab 连接；有下级则句尾冒号，无下级则句尾句号；纲目句中句号改为分号。
5. 直接输出纲目正文，不要用 markdown 代码块或 #、*、** 等格式。
6. 篇幅控制在 A4 约 2 页内，逻辑清晰、突出主题。

【晨兴信息选读内容】
{content}"""

# 听抄稿的纲目：在原纲目基础上加入听抄稿中的重点
TRANSCRIPT_OUTLINE = """请根据以下「原纲目」和「听抄稿内容」，在原纲目的基础上，把听抄稿中的重点适度加入，生成一份完整的纲目。

要求：
1. 以原纲目的结构和层级为主，不得大幅改变原有大纲（壹贰叁…）和思路。
2. 在合适的纲目下，用听抄稿中的重点作补充或扩展，可增加小点或在中纲下加入要点；新增内容需与原有纲目风格一致。
3. 纲目格式同常规：经节—创一1，太五3；序号与纲目用 Tab；有下级冒号、无下级句号；句中句号改分号。
4. 直接输出完整纲目正文，不要用 markdown 代码块或 #、*、** 等格式。
5. 保持篇幅适中，不要过度冗长。

【原纲目】
{original_outline}

【听抄稿内容】
{transcript}"""

# 复合的纲目：以听抄稿纲目为基础，融入晨兴信息选读纲目的内容
COMPOSITE_OUTLINE = """请以以下「听抄稿的纲目」为基础，将「晨兴信息选读的纲目」中的内容适度融入，生成一份复合纲目。

要求：
1. 主体结构和层级以听抄稿的纲目为准，不得打乱其壹贰叁…及一、二、三…结构。
2. 在对应或相近的纲目下，将晨兴信息选读纲目中的要点、经节或表述融入，使内容更丰富；若某处无对应，可略过或简要补充。
3. 融合后保持格式统一：经节—创一1，太五3；序号与纲目用 Tab；有下级冒号、无下级句号；句中句号改分号。
4. 直接输出完整纲目正文，不要用 markdown 代码块或 #、*、** 等格式。
5. 篇幅以听抄稿纲目为主，适度增加，避免重复啰嗦。

【听抄稿的纲目】
{transcript_outline}

【晨兴信息选读的纲目】
{morning_revival_outline}"""


def get_morning_revival_prompt(content: str) -> str:
    return MORNING_REVIVAL_OUTLINE.replace("{content}", content)


def get_transcript_prompt(original_outline: str, transcript: str) -> str:
    return TRANSCRIPT_OUTLINE.replace("{original_outline}", original_outline).replace("{transcript}", transcript)


def get_composite_prompt(transcript_outline: str, morning_revival_outline: str) -> str:
    return COMPOSITE_OUTLINE.replace("{transcript_outline}", transcript_outline).replace(
        "{morning_revival_outline}", morning_revival_outline
    )
