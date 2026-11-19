"""Watchlist endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field

from app import services

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


class AddTickerRequest(BaseModel):
    ticker: str = Field(min_length=1, max_length=12)


@router.get("")
async def list_watchlist() -> list[dict]:
    return services.list_watchlist()


@router.post("", status_code=201)
async def add_ticker(req: AddTickerRequest) -> dict:
    return await services.add_ticker(req.ticker)


@router.delete("/{ticker}", status_code=204)
async def remove_ticker(ticker: str) -> Response:
    await services.remove_ticker(ticker)
    return Response(status_code=204)
