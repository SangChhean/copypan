# -*- coding: utf-8 -*-
"""步骤顺序。已接通的步骤调用当前 Prompt；待设计的步骤不调用模型。"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StepSpec:
    step: str
    label: str
    # connected：调用模型。designed：跳过（待设计）。analysis：有原纲目才调用。
    kind: str


MAIN_LINE = (
    StepSpec("burden", "负担说明", "connected"),
    StepSpec("skeleton", "新生成的龙骨", "connected"),
    StepSpec("retrieval", "检索", "designed"),
    StepSpec("generation", "生成", "designed"),
    StepSpec("evaluation", "评估", "designed"),
)

ANALYSIS = (
    StepSpec("orig_skeleton", "原纲目的龙骨", "analysis"),
    StepSpec("diagnosis", "对比诊断", "analysis"),
)

ALL_STEPS = MAIN_LINE + ANALYSIS
STEP_IDS = tuple(spec.step for spec in ALL_STEPS)
STEP_LABELS = {spec.step: spec.label for spec in ALL_STEPS}

SKIP_DESIGNED = "跳过（待设计）"
SKIP_NO_OUTLINE = "跳过（无原纲目）"
SKIP_UNSELECTED = "未选择"
SKIP_BURDEN_FAILED = "负担说明失败，未执行"
SKIP_SKELETON_FAILED = "新生成的龙骨失败，未执行"
SKIP_ORIG_FAILED = "原纲目的龙骨失败，未执行"
MISSING_BURDEN = "Prompt1 输出中找不到【负担说明】"
BURDEN_MARKER = "【负担说明】"
BURDEN_TAG = "[360字左右]"

MAIN_SCOPES = ("none", "burden", "skeleton")
ANALYSIS_SCOPES = ("none", "orig_skeleton", "diagnosis")


def step_in_scope(step: str, main_scope: str, analysis_scope: str) -> bool:
    if step == "burden":
        return main_scope in {"burden", "skeleton"}
    if step == "skeleton":
        return main_scope == "skeleton"
    if step == "orig_skeleton":
        return analysis_scope in {"orig_skeleton", "diagnosis"}
    if step == "diagnosis":
        return analysis_scope == "diagnosis"
    return False


def cover_start_step(main_scope: str, analysis_scope: str, start_step: str | None) -> tuple[str, str]:
    """从某一步重跑时，把选择扩到能覆盖这一步。"""
    main, analysis = main_scope, analysis_scope
    if start_step == "burden" and main == "none":
        main = "burden"
    if start_step == "skeleton":
        main = "skeleton"
    if start_step == "orig_skeleton" and analysis == "none":
        analysis = "orig_skeleton"
    if start_step == "diagnosis":
        main = "skeleton"
        analysis = "diagnosis"
    return main, analysis


def extract_burden_body(output: str) -> str:
    """取最后一次【负担说明】之后的正文，去掉紧跟的 [360字左右] 和首尾空白。"""
    index = output.rfind(BURDEN_MARKER)
    if index < 0:
        raise ValueError(MISSING_BURDEN)
    rest = output[index + len(BURDEN_MARKER) :]
    lead = rest.lstrip(" \t\r\n")
    if lead.startswith(BURDEN_TAG):
        rest = lead[len(BURDEN_TAG) :]
    return rest.strip()


def dependency_skip(step: str, failed: set[str]) -> str | None:
    if step == "skeleton" and "burden" in failed:
        return SKIP_BURDEN_FAILED
    if step == "diagnosis" and "skeleton" in failed:
        return SKIP_SKELETON_FAILED
    if step == "diagnosis" and "orig_skeleton" in failed:
        return SKIP_ORIG_FAILED
    return None


def initial_step_status(
    spec: StepSpec,
    has_outline: bool,
    main_scope: str = "skeleton",
    analysis_scope: str = "diagnosis",
) -> tuple[str, str | None]:
    """返回 (status, output_text)。output_text 仅在跳过时有说明。"""
    if spec.kind == "designed":
        return "skipped", SKIP_DESIGNED
    if spec.kind == "analysis" and not has_outline:
        return "skipped", SKIP_NO_OUTLINE
    if not step_in_scope(spec.step, main_scope, analysis_scope):
        return "skipped", SKIP_UNSELECTED
    return "pending", None
