# -*- coding: utf-8 -*-
"""恢复本圣经建块配置。"""

import os

SQLITE_PATH = r"G:\audio-app\Bible\assets\Bible20240820.sqlite"
DEFAULT_OUT_DIR = r"G:\PanAI4.0专用\纲目JSON"
INDEX_NAME = "panai4_bible"
BATCH = "bible"
AUTHOR = "恢复本圣经"
PARAGRAPH_TYPE = "bible"
CHUNK_ID_PREFIX = "gmbible"
IDEOGRAPHIC_SPACE = "\u3000"
CHAR_LIMIT = 1200  # ②③④ 的字数阈值（只计经文正文）
SAMPLE_SEED = 20260929

# 只用这五张表；不得碰注解、繁体、英文、介言。
TABLE_OUTLINE = "outline_all_gb_25"
TABLE_VERSE = "verse_all_final_gb_26"
TABLE_PARAGRAPH = "verse_all_paragraph_08"
TABLE_VOLUME = "volume_all_gb_22"
TABLE_TOPIC = "topic_all_gb_24"

# unit_code / related_section_code
UNIT_WHOLE = 0
UNIT_UPPER = 1
UNIT_LOWER = 2
UNIT_SUFFIX = {0: "", 1: "上", 2: "下"}

CN_DIGITS = "零一二三四五六七八九"


def to_cn_number(n: int) -> str:
    """1→一，11→十一，20→二十，119→一百一十九。"""
    if n < 0:
        raise ValueError(n)
    if n < 10:
        return CN_DIGITS[n]
    if n < 20:
        return "十" if n == 10 else "十" + CN_DIGITS[n - 10]
    if n < 100:
        tens, ones = divmod(n, 10)
        head = CN_DIGITS[tens] + "十"
        return head if ones == 0 else head + CN_DIGITS[ones]
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        head = CN_DIGITS[hundreds] + "百"
        if rest == 0:
            return head
        if rest < 10:
            return head + "零" + CN_DIGITS[rest]
        # 百后的 10～19 须写「一十…」（一百一十九，不是一百十九）
        if rest < 20:
            return head + "一十" + ("" if rest == 10 else CN_DIGITS[rest - 10])
        return head + to_cn_number(rest)
    raise ValueError("超出转换范围: {0}".format(n))


def make_key(section_code: int, segment_code: int, unit_code: int) -> int:
    return section_code * 1_000_000 + segment_code * 10 + unit_code


def default_report_path() -> str:
    here = os.path.abspath(__file__)
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(here)))))
    return os.path.join(root, "docs", "panai4_es", "bible_chunking_report.md")
