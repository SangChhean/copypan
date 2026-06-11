"""
两种圆桌场景的 Prompt 模板库（十二支派 / 神学辩论）
"""
from typing import Dict, List

FORMAT_NO_MARKDOWN = "\n\n【格式要求】请用纯文本回答，严禁使用任何Markdown格式符号，包括 **加粗**、*斜体*、# 标题、- 列表符号、`代码`等。直接输出文字内容即可。用中文输出。"


def build_scene_one_prompt(ai_name: str, topic: str) -> str:
    """场景①十二支派：历史神学研究，按时代顺序整理历代神学家观点。"""
    return f"""请对以下神学题目进行深度历史研究，用中文回答。

研究题目：{topic}

请按时代顺序，尽可能全面地整理历代神学家、神学传统对此题目的观点与论述：

一、教父时期（1—5世纪）
二、中世纪（6—15世纪）
三、宗教改革时期（16—17世纪）
四、近现代（18世纪至今）

每位神学家请说明：所属传统、核心观点、代表著作或来源。
覆盖范围须包括不同传统，不限于主流：天主教、东正教、改革宗、路德宗、循道宗、灵恩派、主的恢复等均应纳入。
引用须真实，不得捏造来源。

行文使用自然段落，不使用 Markdown 标题符号（#）或列表符号（-、*）。不要提问，直接开始回答。
""" + FORMAT_NO_MARKDOWN


def build_scene_one_conclusion_prompt(topic: str, all_responses: str) -> str:
    """场景①结论：将多AI研究结果去重合并为综合报告。"""
    return f"""以下是多个AI对同一神学题目的历史研究结果，请将其整合为一份综合性的历史神学报告，用中文输出。

研究题目：{topic}

各AI研究结果：
{all_responses}

整合要求：
- 按教父时期、中世纪、宗教改革时期、近现代四个时代组织内容
- 去除重复条目，若多个AI提到同一神学家，保留信息最完整的那份
- 补充任何AI遗漏但重要的神学家或观点，补充内容须真实可查，不得捏造神学家姓名或著作来源
- 每位神学家注明所属传统与代表著作
- 保持中立，不偏向任何神学传统
- 报告以服务辩论准备与神学研究为目标，内容须实用可查

行文使用自然段落，不使用 Markdown 标题符号（#）或列表符号（-、*）。不要提问，直接开始回答。
""" + FORMAT_NO_MARKDOWN


def _format_others_last_round(others_last_round: Dict[str, str]) -> str:
    """将 others_last_round 拼接为 [立场名称]：{内容}\\n\\n"""
    return "".join(f"[{stance}]：{content}\n\n" for stance, content in (others_last_round or {}).items())


def build_scene_two_prompt(
    ai_name: str,
    topic: str,
    stance: str,
    round_num: int,
    own_history: List[str],
    others_last_round: Dict[str, str],  # key 为立场名称
    all_stances: Dict[str, str],        # key 为立场名称
) -> str:
    """场景②神学辩论：第1轮亮明立场，第2轮正面交锋，第3轮深化论证。"""
    stances_block = "".join(f"{s}\n" for s in (all_stances or {}).values())

    base = f"""你是一位立场坚定的神学讨论者，你的立场是：{stance}。

本次辩论题目：{topic}

本次参与辩论的各方立场如下，其余均为你的辩论对手：
{stances_block}
在整个讨论过程中，你必须始终坚守自己的立场，不得软化、转换或妥协。用第一人称发言，以「我」为主语陈述观点。行文使用自然的发言语气，不使用 Markdown 标题符号（#）或列表符号（-、*）。引用观点时请注明来源（神学家姓名、著作或经文），引用须真实，不得捏造神学家姓名、著作或经文。用中文输出。
""" + FORMAT_NO_MARKDOWN

    if round_num == 1:
        return base + """

【第一轮：亮明立场】
请清晰陈述你的核心神学立场，给出至少2个主要论点，并引用相关经文或神学家的观点加以支撑。让其他参与者清楚知道你站在哪里、为什么站在那里。用中文输出。
"""

    if round_num == 2:
        own_block = f"【你在第一轮的发言】\n{own_history[0] if own_history else ''}\n\n"
        others_block = "【其他参与者在第一轮的发言】\n" + _format_others_last_round(others_last_round)
        return base + "\n" + own_block + others_block + """
【第二轮：正面交锋】
仔细阅读其他参与者的发言，点名回应至少两位参与者的具体论点，对其中威胁你立场最大的论点给予最深入的反驳。不要只是重申自己的观点，要直接针对对方说了什么来回应。用中文输出。
"""

    if round_num == 3:
        own_r1 = own_history[0] if len(own_history) > 0 else ""
        own_r2 = own_history[1] if len(own_history) > 1 else ""
        own_block = f"【你在前两轮的发言】\n第一轮：{own_r1}\n第二轮：{own_r2}\n\n"
        others_block = "【其他参与者在第二轮的发言】\n" + _format_others_last_round(others_last_round)
        return base + "\n" + own_block + others_block + """
【第三轮：深化论证】
这是最后一轮。你必须守住自己的立场，不得妥协或软化。请在前两轮的基础上，补充更深入的神学或经文依据，强化你的核心论点，同时回应对手在第二轮对你发起的反驳，不得回避，给出你最有力的陈述作为收尾。用中文输出。
"""

    return base


# ---------- 场景③ 重大讨论 ----------


def _format_round_for_prompt(round_data: Dict[str, str], participants: List[str]) -> str:
    """将一轮发言格式化为 [AI名]：内容\\n\\n"""
    return "".join(f"[{ai}]：{(round_data.get(ai) or '')}\n\n" for ai in participants)


def build_scene_three_round1_prompt(topic: str) -> str:
    """场景③第一轮：各 AI 对题目/文章独立作答。"""
    return f"""请针对以下讨论题目或材料，给出你的独立回答或评价。用中文输出。

题目/材料：
{topic}

请直接陈述你的观点、分析或结论，不必引用其他参与者。行文使用自然段落，不使用 Markdown 标题符号（#）或列表符号（-、*）。不要提问，直接开始回答。
""" + FORMAT_NO_MARKDOWN


def build_scene_three_round2_prompt(
    ai_name: str,
    topic: str,
    round1_all: Dict[str, str],
    participants: List[str],
) -> str:
    """场景③第二轮：必须至少点评 2～3 个其他 AI 的观点（互相指出）。"""
    others_r1 = _format_round_for_prompt(
        {k: v for k, v in round1_all.items() if k != ai_name},
        [p for p in participants if p != ai_name],
    )
    return f"""以下是一场「重大讨论」的第一轮发言。请你在阅读后，对**至少 2～3 位其他参与者**的观点进行点评（指出亮点、补充、质疑或不同看法均可）。用中文输出。

讨论题目/材料：
{topic}

【第一轮各参与者发言】
{others_r1}

【你的任务】
请点名回应至少 2～3 位其他参与者（例如：对 Claude 的观点我认为…；GPT 提到的…值得补充…）。要针对他们具体说了什么来回应，不要泛泛而谈。行文使用自然段落，不使用 Markdown 标题符号（#）或列表符号（-、*）。不要提问，直接开始回答。
""" + FORMAT_NO_MARKDOWN


def build_scene_three_round3_prompt(
    ai_name: str,
    topic: str,
    round1_all: Dict[str, str],
    round2_all: Dict[str, str],
    participants: List[str],
) -> str:
    """场景③第三轮：根据前两轮（含第二轮互相评价），对题目本身做最终评价。"""
    r1_str = _format_round_for_prompt(round1_all, participants)
    r2_str = _format_round_for_prompt(round2_all, participants)
    return f"""以下是一场「重大讨论」的前两轮完整记录。请你在阅读后，**回到题目本身**，给出你对这道题目/材料的**最终评价**（总结你的立场、结论或建议）。不必再逐一点评他人，重点是对题目本身的收尾陈述。用中文输出。

讨论题目/材料：
{topic}

【第一轮：各参与者作答】
{r1_str}

【第二轮：互相点评】
{r2_str}

【你的任务】
请基于以上讨论，对题目/材料本身给出你的最终评价或结论。行文使用自然段落，不使用 Markdown 标题符号（#）或列表符号（-、*）。不要提问，直接开始回答。
""" + FORMAT_NO_MARKDOWN


def build_scene_four_prompt(topic: str) -> str:
    """场景④顶级模型思考：单轮深度思考与回答，无总结。"""
    return f"""请对以下题目进行深度思考，并给出你的分析与回答。用中文输出。

题目/材料：
{topic}

请充分展开思考，结构清晰，论述有据。行文使用自然段落，可使用「一、二、三、」分段；不使用 Markdown 标题符号（#）或列表符号（-、*）。不要提问，直接开始回答。
""" + FORMAT_NO_MARKDOWN


def build_scene_three_conclusion_prompt(topic: str, all_speeches_str: str) -> str:
    """场景③结论：Claude 对三轮讨论做总结。"""
    return f"""以下是一场「重大讨论」的完整三轮记录，请作为主持人，对整场讨论进行总结，用中文输出。

讨论题目/材料：
{topic}

全部发言记录：
{all_speeches_str}

请完成以下任务：
一、简要概括各轮讨论的主要观点与分歧点。
二、归纳大家对题目/材料形成的共识或仍存在的不同看法。
三、给出对读者有参考价值的结论或建议。

要求：结构清晰，保持中立；行文使用自然段落，可使用「一、二、三、」分段；不使用 Markdown 符号。不要提问，直接开始回答。
""" + FORMAT_NO_MARKDOWN


def build_conclusion_prompt(topic: str, all_stances: str, all_speeches: str) -> str:
    """结论轮：中立裁判对辩论做深度总结。"""
    return f"""以下是一场神学辩论的完整记录，请作为中立的神学评论者，对这场辩论进行深度总结，用中文输出。

辩论题目：{topic}

各方立场：
{all_stances}

全部发言记录：
{all_speeches}

请完成以下任务：

第一，梳理各方在哪些核心问题上存在共识，指出这些共识的神学基础。

第二，梳理各方在哪些核心问题上存在真正的分歧，指出每个分歧点的神学根源，并评价各方论证的强弱——哪些论点有充分的经文或神学依据，哪些论点相对薄弱或回避了关键问题。评价须基于辩论记录本身，补充引用须真实可查，不得捏造神学家姓名或著作。

第三，基于这场辩论的内容，给出对神学研究与神学辩论有实际帮助的建议：这个题目在神学研究中应当如何处理？哪些立场的洞见值得借鉴？有哪些张力是神学研究者必须正视而非回避的？

要求：
- 保持完全中立，评价论证强弱时依据逻辑与经文，不以神学传统偏好为标准
- 结构自由，不必强制分段，行文流畅自然
- 不使用 Markdown 标题符号（#）或列表符号（-、*）
- 若需分段标题，使用「一、二、三、」格式
- 不要提问，直接开始回答。
""" + FORMAT_NO_MARKDOWN