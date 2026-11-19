"""Fixtures: a fresh tmp database and a fake market source wired into app.services.state."""

from __future__ import annotations

import pytest

from app import db
from app.market import PriceCache
from app.services import state

from .fakes import DEFAULT_PRICES, FakeSource


@pytest.fixture
async def source(tmp_path, monkeypatch):
    db.init_db(str(tmp_path / "test.db"))
    cache = PriceCache()
    src = FakeSource(cache, DEFAULT_PRICES)
    monkeypatch.setattr(state, "price_cache", cache)
    monkeypatch.setattr(state, "market_source", src)
    with db.transaction() as conn:
        tickers = [r["ticker"] for r in db.list_watchlist(conn)]
    await src.start(tickers)
    return src


@pytest.fixture
def cache(source):
    return source.cache
