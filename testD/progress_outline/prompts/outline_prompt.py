# -*- coding: utf-8 -*-
"""四个纲目 prompt 占位（结构完整，后续填充）。"""
from __future__ import annotations

PANO_SEGMENT_PROMPT = """你是纲目整理助手。请根据以下「主恢复中神圣启示的进展」系列材料，生成分段纲目。

【输出要求】
- 输出长度约 {output_length} tokens
- 保持纲目层级清晰
- 保留关键经文与职事要点

【材料】
{content}

请生成分段纲目："""

PANO_OVERVIEW_PROMPT = """你是纲目整理助手。请根据以下「主恢复中神圣启示的进展」系列材料，生成鸟瞰纲目。

【输出要求】
- 输出长度约 {output_length} tokens
- 鸟瞰全局结构，突出主线

【材料】
{content}

请生成鸟瞰纲目："""

ENTRY_SEGMENT_PROMPT = """你是纲目整理助手。请根据以下检索到的职事材料，为词条「{term}」生成分段纲目。

【输出要求】
- 输出长度约 {output_length} tokens
- 按阶段脉络组织

【材料】
{content}

请生成分段纲目："""

ENTRY_OVERVIEW_PROMPT = """你是纲目整理助手。请根据以下检索到的职事材料，为词条「{term}」生成鸟瞰纲目。

【输出要求】
- 输出长度约 {output_length} tokens
- 鸟瞰全局，突出词条核心

【材料】
{content}

请生成鸟瞰纲目："""
