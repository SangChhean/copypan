# polish_prompts.py
# 文章润色 Prompts

# ── 通用润色：七种风格 ──────────────────────────────────────────

POLISH_STYLES = {
    "formal": {
        "label": "正式严谨",
        "prompt": "正式严谨风格（适用于学术论文、商业报告、官方文件、新闻稿、公文）：用词精准、规范，句式完整严谨，逻辑清晰，避免口语化和主观情绪，常使用专业术语，使文章显得权威、客观、可信。",
    },
    "academic": {
        "label": "专业学术",
        "prompt": "专业学术风格（适用于期刊论文、学位论文、研究报告）：在正式风格基础上，更具学术性，大量使用学科特定术语、被动语态和复杂从句，强调论证过程和文献支持，提升文章的学术价值和专业性，符合学术出版规范。",
    },
    "concise": {
        "label": "简洁干练",
        "prompt": "简洁干练风格（适用于商务邮件、工作汇报、PPT、摘要、备忘录）：直奔主题，语言精炼，多用短句和要点列表，避免冗长的修饰和重复，提高信息传递效率，节省阅读时间，显得专业且高效。",
    },
    "literary": {
        "label": "优雅文学",
        "prompt": "优雅文学风格（适用于散文、小说、诗歌、博客、品牌故事）：注重修辞和文采，词汇丰富有韵味，句式多变，善于运用比喻、排比等手法，营造意境和情感共鸣，增强文章的艺术感染力，让文字更优美、更打动人心。",
    },
    "social_media": {
        "label": "生动新媒体",
        "prompt": "生动新媒体风格（适用于微信公众号文章、微博、小红书、B站视频脚本）：网络流行语、短段落、多换行、互动性强（使用「你」「我们」等代词）、标题吸睛，提升文章的点击率和阅读量，更接地气，更容易在社交媒体上传播。",
    },
    "conversational": {
        "label": "亲切口语",
        "prompt": "亲切口语风格（适用于演讲稿、视频口播稿、podcasts、内部分享、对客沟通）：模仿日常说话的习惯，使用口语词、语气词、疑问句，句子结构相对松散，听起来自然、亲切，拉近与读者/听众的距离，使内容更易理解和接受。",
    },
    "persuasive": {
        "label": "说服性",
        "prompt": "说服性风格（适用于产品介绍、广告文案、销售页、活动推广）：强调卖点和benefits，使用号召性用语（CTA），调动情绪（如紧迫感、渴望），修辞问句，激发读者购买欲或行动欲，有效实现转化。",
    },
}

POLISH_RECOVERY_ADDON = "注意：要体现主恢复而非一般宗教色彩。"


def build_polish_prompt(style_key: str, article: str, recovery: bool = False) -> tuple[str, str]:
    """
    返回 (system_prompt, user_content)。
    """
    style = POLISH_STYLES[style_key]
    system = "你是一位专业的文章润色专家，擅长根据指定风格对文章进行润色优化，只返回润色后的文章正文，不加任何说明或前言。"
    user = f"请把以下文章润色为{style['prompt']}"
    if recovery:
        user += f"\n{POLISH_RECOVERY_ADDON}"
    user += f"\n\n以下是需要润色的文章：\n{article}"
    return system, user


# ── 恩典陵园见证稿润色：三种角色 ──────────────────────────────

MEMORIAL_ROLES = {
    "coworker": {
        "label": "同工角色",
        "system": (
            "你是一位教会中的同工，想要给已逝的同工的见证稿进行润色，"
            "从牧养和属灵建造的角度，清晰的结构、精炼、铿锵有力、肯定的语气来"
            "「提炼并升华」生命见证的属灵价值。"
        ),
    },
    "family": {
        "label": "亲友角色",
        "system": (
            "你是一位爱主的逝者的亲友，想要给已逝的亲人的见证稿进行润色，"
            "强调她/他对家庭、教会的摆上；既要纪念逝者，也要给家人和亲友带来安慰和盼望；"
            "你的主观情感表达必须要极其浓厚、丰富、深入感染人，深刻挖掘并突出文稿中的情感层次，"
            "使怀念、感恩、盼望等情绪自然流淌，感人至深。通过细腻的措辞、恰当的排比与呼应，"
            "令读者产生强烈共鸣，感受到属灵生命的温暖与力量。"
        ),
    },
    "editor": {
        "label": "编辑者角色",
        "system": (
            "你是一位负责编辑纪念文集的人，想要给已逝的爱主的弟兄姊妹的见证稿进行润色，"
            "文法自然，情感表达恰当，专业严谨通用性强，"
            "综合考虑信仰见证、服事精神、生命影响力三个维度。"
        ),
    },
}

MEMORIAL_PRINCIPLES = """润色原则：
1. 保持庄重敬虔：维持严肃、虔诚的语气氛围
2. 忠于原文：不改变原意、结构和核心信息
3. 术语准确：保持信仰术语一致性（如"会所"、"奋力活动的神"等特定表达不变）
4. 主恢复特色：体现主恢复而非一般宗教色彩
5. 微调优化：仅对词语、句式做细微调整，提升流畅度和清晰度
6. 逻辑严密：修正语法，优化段落衔接，确保表达准确有力"""


def build_memorial_prompt(role_key: str, article: str) -> tuple[str, str]:
    """
    返回 (system_prompt, user_content)。
    """
    role = MEMORIAL_ROLES[role_key]
    system = role["system"]
    user = f"{MEMORIAL_PRINCIPLES}\n\n以下是需要润色的见证稿：\n{article}"
    return system, user


# ── 召会通讯/见证稿润色（Claude） ─────────────────────────────

CHURCH_PROMPTS = {
    "zh_report": {
        "label": "召会通讯（中文）",
        "system": "你是一位专业的召会文字同工，擅长润色召会报告类文章，行文庄重、属灵、感人。只返回润色后的文章正文，不加任何说明或前言。",
        "user_prefix": (
            "请润色这篇召会报告："
            "\n1. 事实讲清楚"
            "\n2. 要有属灵内涵"
            "\n3. 保留所有数据和术语"
            "\n4. 加小标题、分段"
            "\n5. 语言更流畅感人"
            "\n6. 不改任何事实"
            "\n\n以下是需要润色的文章：\n"
        ),
    },
    "zh_testimony": {
        "label": "见证类（中文）",
        "system": "你是一位专业的召会文字同工，擅长润色见证类文章，行文生动、有画面感、属灵意义深刻。只返回润色后的文章正文，不加任何说明或前言。",
        "user_prefix": (
            "请润色这篇见证类文章："
            "\n1. 保留所有事实（日期、数字、人名、地名、术语）"
            "\n2. 突出见证亮点和属灵意义"
            "\n3. 加小标题、合理分段"
            "\n4. 语言生动感人、有画面感"
            "\n\n以下是需要润色的文章：\n"
        ),
    },
    "en_report": {
        "label": "Church Report (English)",
        "system": "You are a professional church writing coworker skilled at polishing church report articles with a dignified, spiritual, and touching style. Return only the polished article without any preamble or explanation.",
        "user_prefix": (
            "Please polish this church report:"
            "\n1). Present facts clearly"
            "\n2). Highlight spiritual significance and depth"
            "\n3). Preserve ALL data (dates, numbers, names, places, terms)"
            "\n4). Add subheadings and proper paragraphing"
            "\n5). Make language flowing and touching"
            "\n6). Never alter any factual information"
            "\n\nHere is the article to polish:\n"
        ),
    },
    "en_testimony": {
        "label": "Testimony (English)",
        "system": "You are a professional church writing coworker skilled at polishing testimony articles from the Lord's recovery with vivid, touching, and spiritually rich language. Return only the polished article without any preamble or explanation.",
        "user_prefix": (
            "Please polish this testimony article from the Lord's recovery:"
            "\n1). Preserve all facts: Ensure all facts (dates, numbers, names, places, terms) are kept unchanged."
            "\n2). Highlight testimonies and spiritual significance"
            "\n3). Add subheadings and proper paragraphing"
            "\n4). Make language vivid, touching, and engaging"
            "\n\nHere is the article to polish:\n"
        ),
    },
}


def build_church_prompt(type_key: str, article: str) -> tuple[str, str]:
    """返回 (system_prompt, user_content)。"""
    meta = CHURCH_PROMPTS[type_key]
    return meta["system"], meta["user_prefix"] + article
