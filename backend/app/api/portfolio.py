"""Portfolio endpoints: valuation, trades, history."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import services

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


class TradeRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=12)
    quantity: float = Field(gt=0, allow_inf_nan=False)
    side: Literal["buy", "sell"]


@router.get("")
async def get_portfolio() -> dict:
    return services.get_portfolio()


@router.post("/trade")
async def trade(req: TradeRequest) -> dict:
    return await services.execute_trade(req.ticker, req.side, req.quantity)


@router.get("/history")
async def history() -> list[dict]:
    return services.get_history()
