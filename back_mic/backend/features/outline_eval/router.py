# -*- coding: utf-8 -*-
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from features.outline_eval.llm_evaluator import run_evaluation
from user.token import test_token as get_current_user

logger = logging.getLogger(__name__)

router = APIRouter()


class EvalRequest(BaseModel):
    answer: str
    query: str
    outline_nature: str
    burden_description: str = ""
    revelation: list[str] = []
    experience: list[str] = []
    practice: list[str] = []
    skeleton: list[dict[str, Any]] = []
    answer_v1: str | None = None
    eval_v1: dict[str, Any] | None = None


def _to_request_data(body: EvalRequest) -> dict[str, Any]:
    return {
        "answer": body.answer,
        "query": body.query,
        "outline_nature": body.outline_nature,
        "burden_description": body.burden_description,
        "revelation": "\n".join(body.revelation),
        "experience": "\n".join(body.experience),
        "practice": "\n".join(body.practice),
        "skeleton": body.skeleton,
    }


@router.post("/outline", summary="纲目品质评估（F1-F4 + T1-T4）")
async def evaluate_outline(
    body: EvalRequest,
    _user: dict = Depends(get_current_user),
) -> dict[str, Any]:
    """返回结构说明：
    - synthesis（新增）：高/低优先级修改建议 + overall_note
    - theology_layer 子字段：
      T1: L1-L4 + nature_fit + weak_citations
      T2: S1-S6 + weighted_score
      T3: R系/E系/P系 四维 + framework_type + structural_tension
      T4: score + sharpness_type + comment + summary
    """
    try:
        is_second_eval = body.eval_v1 is not None
        return await run_evaluation(
            _to_request_data(body),
            is_second_eval=is_second_eval,
            eval_v1=body.eval_v1,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("outline_eval 失败: %s", e, exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) from e
