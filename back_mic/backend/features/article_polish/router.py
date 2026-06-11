from fastapi import APIRouter

router = APIRouter()

from features.article_polish.polish_router import router as _polish
from features.article_polish.church_polish_router import router as _church

router.include_router(_polish)
router.include_router(_church)
