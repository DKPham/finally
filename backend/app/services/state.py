"""Process-wide singletons, set by the FastAPI lifespan handler (or by tests).

Always access them as attributes of this module (``state.price_cache``) so that
reassignment is seen everywhere.
"""

from __future__ import annotations

from app.market import MarketDataSource, PriceCache

price_cache: PriceCache = PriceCache()
market_source: MarketDataSource | None = None
