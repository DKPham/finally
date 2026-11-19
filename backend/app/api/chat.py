"""Chat endpoints: POST /api/chat, GET /api/chat/history (PLAN §8, §10)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.llm import get_history, handle_chat

router = APIRouter(prefix="/api/chat", tags=["chat"])


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


@router.post("")
async def post_chat(req: ChatRequest) -> dict:
    return await handle_chat(req.message)


@router.get("/history")
async def chat_history() -> list[dict]:
    return get_history(limit=50)
