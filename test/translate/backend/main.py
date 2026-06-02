from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from typing import Optional, Literal
import asyncio
import logging
from dotenv import load_dotenv

load_dotenv()

from translate_service import translate_outline, translate_outline_en2zh

logging.basicConfig(level=logging.INFO)
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class TranslateRequest(BaseModel):
    direction: Literal["zh2en", "en2zh"]
    content: str = Field(..., min_length=1, max_length=100_000)
    outline_topic: Optional[str] = Field(None, max_length=200)


@app.post("/api/translate")
async def translate(request: TranslateRequest):
    if request.direction == "zh2en":
        out = await asyncio.to_thread(
            translate_outline,
            request.content,
            request.outline_topic,
        )
        return {"result": out.get("answer_en"), "title_en": out.get("title_en"), "error": out.get("error")}
    else:
        out = await asyncio.to_thread(translate_outline_en2zh, request.content)
        return {"result": out.get("answer_zh"), "error": out.get("error")}
