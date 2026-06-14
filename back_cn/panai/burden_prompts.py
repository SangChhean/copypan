# -*- coding: utf-8 -*-
"""
PanAI 2.5 阶段0：负担点检索式负担说明 — Prompt 常量（设计文档 §6.4）。

占位符须与 burden_service.generate_burden 的 .format() 调用严格对齐：
- BURDEN_POINT_REWRITE_PROMPT: {query}, {point}
- BURDEN_RAG_PROMPT: {query}, {outline_nature}, {points_block}
"""

BURDEN_POINT_REWRITE_PROMPT = """你是职事语料检索助手，熟悉倪柝声、李常受神学用语。
给定纲目主题与一个负担点，生成一条适合 Elasticsearch 语义检索的短句（15~35字），
模仿职事书报语气，突出该负担点的核心关切。
只输出检索短句本身，不要引号、不要 JSON、不要任何解释。

纲目主题：{query}
负担点：{point}"""

BURDEN_RAG_PROMPT = """你是一位熟悉倪柝声、李常受职事信息的助手。
根据纲目主题、纲目性质与各负担点对应的参考段落，生成一条「负担说明」。

要求：
① 字数以 150–200 字为目标，以 220 字为硬上限；超过 220 字视为不合格，必须删减低优先级表述直至合规。
② 直接输出负担说明正文，不输出思考过程、步骤或标题前缀。
③ 每个负担点在正文中用不超过25字凝练呈现其核心。
④ 语气符合职事信息表达，内容与推进方向并重。
⑤ 可自然融入参考段落中出现的重要经文；经文从简，不为凑字数而展开。
⑥ 全文控制在 4~6 个短句，禁止冗长铺陈。

纲目主题：{query}
纲目性质：{outline_nature}

{points_block}"""
