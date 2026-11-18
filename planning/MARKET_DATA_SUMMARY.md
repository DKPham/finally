# Market Data Backend — Summary

**Status:** Complete. All findings from `MARKET_DATA_REVIEW.md` (2026-11-18) are fixed. **146 tests pass**, with 99% coverage and no warnings. Not yet smoke-tested against a live Massive key; see "Remaining" below.

Full design: `MARKET_DATA_DESIGN.md`. Review and resolution log: `MARKET_DATA_REVIEW.md`.

## What Was Built

A market data subsystem in `backend/app/market/` (9 modules) providing live prices from either a simulator or the Massive (Polygon.io) API behind one interface.

```
MarketDataSource (ABC)
├── SimulatorDataSource  →  GBM simulator (default, no API key needed)
└── MassiveDataSource    →  Massive REST poller (when MASSIVE_API_KEY set)
                             snapshot mode ──NOT_AUTHORIZED──► end-of-day mode
        │
        ▼
   PriceCache (thread-safe, versioned; derives direction + session_open)
        │
        ├──→ SSE stream endpoint (/api/stream/prices)
        ├──→ Portfolio valuation
        └──→ Trade execution
```

| File | Purpose |
|------|---------|
| `models.py` | `PriceUpdate`: frozen dataclass (ticker, price, previous_price, timestamp, session_open). Properties: change, change_percent, direction, session_change_percent |
| `interface.py` | `MarketDataSource`: `start/stop/add_ticker/remove_ticker/get_tickers` |
| `cache.py` | `PriceCache`: thread-safe store; version bumps on update **and** remove |
| `seed_prices.py` | Seed prices, per-ticker GBM params, correlation groups, unknown-ticker price range |
| `simulator.py` | `GBMSimulator` (correlated GBM via Cholesky, shock events) + `SimulatorDataSource` |
| `massive_client.py` | `MassiveDataSource`: snapshot polling with a price fallback chain; free-tier EOD fallback |
| `factory.py` | `create_market_data_source()`: picks a source from `MASSIVE_API_KEY` |
| `stream.py` | `create_stream_router()`: SSE endpoint, version-based change detection, heartbeat |

## Key Behaviours

- **SSE payload per ticker:** `ticker, price, previous_price, timestamp, change, change_percent, direction, session_open, session_change_percent` (PLAN §6).
- **Session open** is the first price the cache records for a ticker since server start. For the simulator that is the seed price. It resets if the ticker is removed and re-added.
- **Massive snapshot mode** makes 1 request per 15 s for all tickers. Price fallback chain: `last_trade.price → min.close → day.close → prev_day.close`. Timestamps come from `sip_timestamp` (ns).
- **Massive EOD mode** (free Basic plan) uses grouped-daily closes, walking back up to 5 days and refreshing every 300 s. A newly added ticker is priced immediately from the stored table.
- **Removing a ticker** pushes an SSE batch without it; removing the last ticker pushes `{}`. A Massive poll that is already running never puts a removed ticker back.
- **Tickers are normalised** (`.upper().strip()`) by both sources.

## Usage for Downstream Code

```python
from app.market import PriceCache, create_market_data_source, create_stream_router

cache = PriceCache()
app.include_router(create_stream_router(cache))
source = create_market_data_source(cache)        # reads MASSIVE_API_KEY
await source.start(tracked_tickers)              # watchlist ∪ open positions (PLAN §6)

cache.get("AAPL")         # PriceUpdate | None
cache.get_price("AAPL")   # float | None → None means "No price available yet" (400 on trade)
cache.get_all()           # dict[str, PriceUpdate]

await source.add_ticker("PYPL")
await source.remove_ticker("GOOGL")              # only if no open position (app layer rule)
await source.stop()
```

The app-layer helper for the watchlist ∪ positions rule (`app/services/market_tracking.py`) and the lifespan wiring are specified in `MARKET_DATA_DESIGN.md` §11. They will be built together with the DB and portfolio/watchlist routes.

## Tests

```bash
cd backend && uv sync && uv run pytest --cov=app
```

| Module | Focus |
|---|---|
| `test_models.py` | Derived fields, the PLAN §6 example, key order, immutability |
| `test_cache.py` | session_open lifecycle, versioning on remove, a concurrent-writer stress test |
| `test_simulator.py` | GBM σ/μ and sector correlations measured statistically; shocks; Cholesky fallback; 40 tickers |
| `test_simulator_source.py` | Async source lifecycle, normalisation, loop resilience |
| `test_massive.py` | Real SDK models: parsing, fallback chain, EOD fallback and walk-back, races, error-log dedup |
| `test_stream.py` | SSE generator (batches, `{}`, heartbeat, disconnect) plus a real-uvicorn HTTP streaming test |
| `test_contract.py` | The same behavioural contract run against both sources |
| `test_factory.py` | Source selection from the environment |

## Remaining

- Smoke-test Massive mode once against a real key (paid, or free for the EOD path) using `MARKET_DATA_DESIGN.md` §8.4.
- Build the tracked-ticker service and lifespan wiring together with the DB and routes.

## Demo

```bash
cd backend && uv run market_data_demo.py
```
