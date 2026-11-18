# Backend — Developer Guide

## Project Setup

```bash
cd backend
uv sync               # Installs runtime deps + the default `dev` group (pytest, ruff, httpx)
```

Production installs (Docker) use `uv sync --frozen --no-dev`.

## Market Data API

The market data subsystem lives in `app/market/`. Use these imports:

```python
from app.market import PriceCache, PriceUpdate, MarketDataSource, create_market_data_source
```

### Core Types

- **`PriceUpdate`** — Immutable dataclass: `ticker`, `price`, `previous_price`, `timestamp`, `session_open`, plus properties `change`, `change_percent`, `direction` ("up"/"down"/"flat"), `session_change_percent`, and `to_dict()` (the PLAN §6 SSE per-ticker shape).

- **`PriceCache`** — Thread-safe in-memory store. Key methods:
  - `update(ticker, price, timestamp=None) -> PriceUpdate` — first write sets `session_open`
  - `get(ticker) -> PriceUpdate | None`
  - `get_price(ticker) -> float | None`
  - `get_all() -> dict[str, PriceUpdate]`
  - `remove(ticker)` — drops the ticker (and its `session_open`)
  - `version` property — monotonic counter, bumped on every update **and** remove (SSE change detection)

- **`MarketDataSource`** — Abstract interface implemented by `SimulatorDataSource` and `MassiveDataSource`. Lifecycle: `start(tickers)` -> `add_ticker()` / `remove_ticker()` -> `stop()`. Both normalise tickers (`.upper().strip()`), both are idempotent on add/remove/stop.
  - Simulator: `add_ticker` writes a price immediately.
  - Massive: snapshot mode polls every 15 s; a free plan (`NOT_AUTHORIZED`) switches to end-of-day closes, refreshed every 300 s. A new ticker gets its price on the next poll.

- **`create_market_data_source(cache)`** — Factory. Returns `MassiveDataSource` if `MASSIVE_API_KEY` is set (non-blank), otherwise `SimulatorDataSource`.

"No price yet" (`cache.get_price(t) is None`) is a normal state — trades must return `400 "No price available for X yet"`.

### SSE Streaming

```python
from app.market import create_stream_router

router = create_stream_router(price_cache)  # Fresh FastAPI APIRouter per call
# Endpoint: GET /api/stream/prices (text/event-stream)
# Sends `retry: 1000`, then one batch of all tracked tickers per cache change
# (possibly `{}`), and `: keep-alive` after 15 s of silence.
```

### Seed Data

Default tickers: AAPL, GOOGL, MSFT, AMZN, TSLA, NVDA, META, JPM, V, NFLX. Seed prices and per-ticker volatility/drift params are in `app/market/seed_prices.py`.

## Running Tests

```bash
uv run pytest -v              # All tests
uv run pytest --cov=app       # With coverage
uv run ruff check app tests   # Lint
uv run ruff format app tests  # Format
```

Massive tests use real SDK models (`TickerSnapshot.from_dict`) and `tests/market/fakes.py:FakeMassiveClient` — never `MagicMock` snapshots. No test touches the network.

## Demo

```bash
uv run market_data_demo.py   # Live terminal dashboard with simulated prices
```
