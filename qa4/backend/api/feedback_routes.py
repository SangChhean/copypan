# -*- coding: utf-8 -*-
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from api.deps import get_auth, require_user

router = APIRouter(prefix="/api", tags=["feedback"])


class FeedbackRequest(BaseModel):
    request_id: str
    rating: int = Field(..., description="1 好评 / -1 差评 等")
    comment: str = ""


@router.post("/feedback")
def post_feedback(
    req: FeedbackRequest,
    request: Request,
    username: str = Depends(require_user),
):
    auth = get_auth(request)
    user = auth.get_user(username)
    fid = auth.add_feedback(
        user_id=int(user["id"]) if user else None,
        request_id=req.request_id,
        rating=req.rating,
        comment=req.comment,
    )
    return {"ok": True, "id": fid}
