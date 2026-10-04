# -*- coding: utf-8 -*-
"""SC 页面路径与模型参数。可用环境变量覆盖数据文件路径。"""
from __future__ import annotations

import os
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[2]
_REPO = _BACKEND.parents[1]

_DEFAULT_TIERS = _REPO / "docs" / "panai4_graph" / "词条三档分类.json"
_DEFAULT_3A = _REPO / "docs" / "3a_export.json"
_DEFAULT_REF = _REPO / "docs" / "panai4_sc" / "ref"
_PROMPTS_DIR = Path(__file__).resolve().parent / "prompts"

MODEL = "claude-opus-5-5"
MAX_TOKENS = 16000
TIER_ORDER = ("最内在", "内在", "外在")

PLAIN_OLD = (
    "你的任务是仅根据用户提供的篇题/主题，直接构建并生成一条「负担说明」——"
    "没有参考摘录，负担说明的全部内容需要你依据篇题/主题、你所知道的职事信息"
    "（包括记得不准、按第二步规则标为「印象」的）与下方六阶段定义自行构建。"
)
PLAIN_NEW = (
    "你的任务是根据用户提供的篇题/主题，并参考文首的【职事参考材料】，"
    "直接构建并生成一条「负担说明」——参考材料是相关词条的职事定义，不是本篇的摘录；"
    "负担说明的内容需要你依据篇题/主题、参考材料、你所知道的职事信息"
    "（包括记得不准、按第二步规则标为「印象」的）与下方六阶段定义自行构建。"
)

# 加词条定义版默认模板 v2：在 PLAIN 替换之外，对 v0.3 再做两处精确替换
REF_V2_STEP2_OLD = "第二步：列出职事界定——分三轮进行：\n(1) 经文回想："
REF_V2_STEP2_NEW = (
    "第二步：列出职事界定——分四轮进行：\n"
    "(0) 参考材料：先逐条读文首【词条定义】，把与本题直接相关的说法列为界定；"
    "每条的「依据」写「参考材料·词条名」（可写多个词条名），不另写书名、篇名；"
    "定义原文里确有的说法，才标「原用语」。(1)(2)(3) 三轮只用来补参考材料里没有的内容。\n"
    "(1) 经文回想："
)
REF_V2_BASIS_OLD = "依据类型分三种：经文明文、职事明言、自行推论。"
REF_V2_BASIS_NEW = (
    "依据类型分四种：经文明文、职事明言、参考材料、自行推论。"
    "「参考材料」指【词条定义】里写明的说法，可作主干环，依据写词条名。"
)


def tiers_json_path() -> Path:
    raw = (os.environ.get("PANAI4_SC_TIERS_JSON") or "").strip()
    return Path(raw) if raw else _DEFAULT_TIERS


def export_3a_path() -> Path:
    raw = (os.environ.get("PANAI4_SC_3A_JSON") or "").strip()
    return Path(raw) if raw else _DEFAULT_3A


def ref_dir() -> Path:
    raw = (os.environ.get("PANAI4_SC_REF_DIR") or "").strip()
    return Path(raw) if raw else _DEFAULT_REF


def prompts_dir() -> Path:
    return _PROMPTS_DIR
