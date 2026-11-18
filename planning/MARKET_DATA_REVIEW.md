# Market Data Backend — Code Review

**Date:** 2026-11-18
**Scope:** `backend/app/market/` (9 modules), `backend/tests/market/` (6 test modules), `backend/market_data_demo.py`, backend docs. Reviewed against `PLAN.md` §6/§8/§9, `MARKET_INTERFACE.md`, `MARKET_SIMULATOR.md`, `MASSIVE_API.md` and `MARKET_DATA_DESIGN.md`.
**Commit reviewed:** `5747d1d` (`main`)
**Supersedes:** `archive/MARKET_DATA_REVIEW.md` (2026-02-10). That review's fixes are present, but its verdict missed the Massive defects below.

---

## 1. Verdict

**The simulator path works and is ready to build on. The Massive path does not work at all, and the price contract is missing two fields the plan requires.**

| Area | Status |
|---|---|
| GBM simulator, correlation, shocks | ✅ Correct (verified statistically, §4.1) |
| PriceCache / PriceUpdate core | ✅ Correct, but missing `session_open` / `session_change_percent` (PLAN §6) |
| SSE endpoint | ✅ Works end to end on uvicorn; removals are never pushed to clients |
| Massive client | ❌ **Never writes a price.** Every real snapshot is discarded. No free-tier fallback |
| Tests | ⚠️ 73/73 pass, but the Massive tests use mocks shaped like the bug, so they pass *because of* it |

`MARKET_DATA_SUMMARY.md` says "complete, tested, reviewed, all issues resolved". For Massive mode that is not true.

Must fix before the portfolio/watchlist/frontend work depends on this code: **F1, F2, F3**. Should fix soon: **F4–F9**.

---

## 2. Test and tool results

```bash
cd backend
uv run --extra dev pytest -q --cov=app --cov-report=term-missing
uv run --extra dev ruff check app tests
uv run --extra dev ruff format --check app tests
```

| Check | Result |
|---|---|
| pytest | **73 passed**, 0 failed, 2.85 s, no warnings (pytest 9.0.2, pytest-asyncio 1.3.0, Python 3.13) |
| ruff check | All checks passed |
| ruff format --check | **3 files would be reformatted**, including `tests/market/test_simulator.py` and `tests/market/test_simulator_source.py` |
| Coverage | 91% overall |

| Module | Cover | Missing |
|---|---|---|
| models.py, cache.py, factory.py, interface.py, seed_prices.py | 100% | |
| simulator.py | 98% | 149 (duplicate guard), 268–269 (loop exception log) |
| massive_client.py | 94% | 85–87, 125, but see F1: high line coverage with fake objects |
| **stream.py** | **33%** | 26–48, 62–87: the SSE endpoint and generator are untested |

Beyond the test suite, I ran these checks against real objects (reproductions are in §5):
- Massive parsing with real `massive` 2.2.0 SDK models (`TickerSnapshot.from_dict`)
- The SSE endpoint on a real uvicorn server, checked with `curl`
- GBM statistics over 20k steps, step cost, and Cholesky with 40 tickers
- Race and ordering probes on add/remove

---

## 3. Findings

Severity: **P1** = broken feature or contract violation that blocks downstream work. **P2** = incorrect behaviour that users or other agents will hit. **P3** = robustness, consistency or hygiene.

### F1 [P1] Massive mode never populates the cache

`massive_client.py:101-104`:

```python
price = snap.last_trade.price
timestamp = snap.last_trade.timestamp / 1000.0   # ← no such attribute
```

The SDK's `LastTrade` has no `.timestamp`. The JSON key `t` maps to `sip_timestamp`, which is in **nanoseconds**, not milliseconds. Every real snapshot raises `AttributeError` and the `except (AttributeError, TypeError)` skips it:

```
LOG WARNING Skipping snapshot for AAPL: 'LastTrade' object has no attribute 'timestamp'
LOG WARNING Skipping snapshot for MSFT: 'LastTrade' object has no attribute 'timestamp'
cache size after poll: 0
```

Impact: with `MASSIVE_API_KEY` set, the watchlist has no prices, every trade fails with `400 No price available`, and SSE sends nothing. Renaming the attribute alone is not enough. The code would then divide nanoseconds by 1000 and produce timestamps around the year 55,000.

**Why the tests pass:** `test_massive.py:_make_snapshot` builds a `MagicMock` and sets `last_trade.timestamp = <ms>`, so the mock has exactly the attribute the code wrongly expects. `test_timestamp_conversion` asserts the wrong unit.

**Fix:** follow `MARKET_DATA_DESIGN.md` §8.2 (`quote_from_snapshot`). Use `last_trade.sip_timestamp / 1e9`, falling back to `snap.updated / 1e9`. Rewrite the tests with `TickerSnapshot.from_dict({...raw JSON...})` (§13.4 of the design) so a wrong attribute name fails.

### F2 [P1] No free-tier fallback, so a free Massive key gives a dead app

The free Basic plan cannot call the snapshot endpoint (`MASSIVE_API.md` §1). It returns `403 NOT_AUTHORIZED`. The code logs it and retries forever:

```
LOG ERROR Massive poll failed: {"status":"NOT_AUTHORIZED","message":"upgrade"}
LOG ERROR Massive poll failed: {"status":"NOT_AUTHORIZED","message":"upgrade"}
cache size: 0
```

Free keys are the likely case for students, and the factory picks Massive whenever any key is set. So setting a free key makes the app strictly worse than leaving it empty.

**Fix:** on `BadResponse` containing `NOT_AUTHORIZED`, switch permanently to grouped-daily EOD prices with a slower interval (design §8.2). At minimum, log a clear message telling the user to unset `MASSIVE_API_KEY`.

### F3 [P1] `session_open` / `session_change_percent` missing (PLAN §6 contract)

`PriceUpdate.to_dict()` returns `change, change_percent, direction, previous_price, price, ticker, timestamp`. PLAN §6 (SSE payload) and §8 (`GET /api/watchlist`) also require `session_open` and `session_change_percent`, which drive the watchlist "Chg %" column. Neither `models.py` nor `cache.py` records a session open. This was raised in `REVIEW.md` P2 and is still open. The frontend and watchlist route agents will code against the PLAN shape.

**Fix:** add `session_open` to `PriceUpdate` and set it on the first cache write, carried forward on later writes; add the `session_change_percent` property and include both in `to_dict()` (design §3–§4). Update `backend/CLAUDE.md` and `MARKET_DATA_SUMMARY.md`.

### F4 [P2] Removing a ticker is never pushed to SSE clients

`PriceCache.remove()` does not bump `version`, and the stream only sends when `version` changes **and** the cache is non-empty (`stream.py:79-84`). Probes:
- `remove("AAPL")` leaves `version` unchanged, so no event is sent until the next price tick. In Massive mode that can be 15 s or more.
- When the last tracked ticker is removed, no event is ever sent (`if prices:`). The client keeps showing the ticker forever.

PLAN §11 says each event *replaces* the client's price map, so the fix is cheap: bump `version` in `remove()` when something was removed, and emit the batch even when it is `{}`.

### F5 [P2] An in-flight Massive poll resurrects a removed ticker

`_poll_once` awaits the HTTP call in a thread, then writes every returned snapshot. If `remove_ticker("AAPL")` runs during that await, the write puts AAPL back into the cache:

```
AAPL in tickers: False | AAPL in cache: True
```

The ticker is no longer polled, so its price freezes. It keeps appearing in SSE and stays valid as a trade fill price. Separately, `_fetch_snapshots` reads `self._tickers` from the worker thread while the event loop may be appending to it.

**Fix:** pass a copy of the ticker list into the thread, and after the await only write tickers still in `self._tickers` (design §8.2).

### F6 [P2] Massive skips tickers that have no `last_trade`

`last_trade` is absent on plans without trades, and the documentation notes it can be stale or missing around the daily reset. When it is absent, the snapshot is skipped (`'NoneType' object has no attribute 'price'`) even though `min.close`, `day.close` or `prev_day.close` is present. **Fix:** use the fallback chain `last_trade.price → min.close → day.close → prev_day.close`, skipping zeros (`MASSIVE_API.md` §2.1).

### F7 [P2] `create_stream_router` registers `/prices` on a shared module-level router

`stream.py:17` creates `router` at import time, and each call to `create_stream_router()` adds another route to it:

```
same router object: True | routes: ['/api/stream/prices', '/api/stream/prices']
```

The second call's cache is unreachable, because the first-registered route wins. This will bite as soon as the app tests build more than one app (`create_app()` per test). **Fix:** create the `APIRouter` inside the function. This was raised in the February review as 3.6 and is still open.

### F8 [P2] Simulator does not normalise tickers; Massive does

`MassiveDataSource.add_ticker/remove_ticker` apply `.upper().strip()`. `SimulatorDataSource` does not:

```
after add('aapl'): ['AAPL', 'aapl']   {'AAPL': 190.0, 'aapl': 291.55}
```

A lowercase ticker becomes a separate symbol with a random price. The routes are supposed to normalise (PLAN §8), but the interface promises the same behaviour from both sources, and the chat/LLM path is an easy place to forget. Massive's `start()` doesn't normalise either. **Fix:** normalise in `start`, `add_ticker` and `remove_ticker` of both sources.

### F9 [P2] Documented test commands uninstall the test tools

`backend/README.md:25,48` says `uv sync --dev`. Dev tools are declared under `[project.optional-dependencies] dev`, not `[dependency-groups]`, so `uv sync --dev` **removes** pytest, pytest-asyncio, pytest-cov and ruff. The dry run confirms: `- pytest==9.0.2 … - ruff==0.15.0`. A plain `uv run pytest` then fails. The root `README.md:52-53` has the same problem. `backend/CLAUDE.md` correctly uses `--extra dev`.

**Fix:** move the dev tools to `[dependency-groups] dev = [...]`, which uv installs by default, or change every doc to `uv sync --extra dev` / `uv run --extra dev pytest`.

### F10 [P3] Smaller issues

| # | Location | Issue | Suggested fix |
|---|---|---|---|
| a | `cache.py:30` | `ts = timestamp or time.time()` replaces an explicit `0.0` with now | `timestamp if timestamp is not None else time.time()` |
| b | `cache.py:63` | `version` read without the lock. Safe under the GIL, inconsistent on free-threaded builds | read under the lock |
| c | `simulator.py` `add_ticker` | Before `start()` it is silently dropped; Massive keeps it | document as undefined, or queue it |
| d | `stream.py:86` | `except CancelledError` swallows cancellation inside the generator | log in `finally`, let cancellation propagate |
| e | `stream.py` | No heartbeat. In Massive mode, idle proxies may close a stream that is silent for 15 s+ | send `: keep-alive` after ~15 s of silence |
| f | `stream.py` / simulator | SSE poll and simulator tick are both 0.5 s with drifting phase, so the SSE occasionally skips a tick (one fewer sparkline point) | acceptable; or poll SSE at 0.25 s |
| g | `massive_client.py:118` | The same error is logged at ERROR every poll (every 15 s forever with a bad key) | log once, then DEBUG until it recovers |
| h | `simulator.py:173` | `np.linalg.cholesky` has no `LinAlgError` guard. Safe with current constants, fragile if groups change | fall back to independent draws |
| i | `simulator.py:143` | `SEED_PRICES.get(t, random.uniform(...))` draws a random number even for seeded tickers, perturbing seeded test runs | `SEED_PRICES.get(t) or random.uniform(...)` |
| j | tests | `ruff format` would reformat 3 files | `uv run --extra dev ruff format app tests` |
| k | `tests/conftest.py` | `event_loop_policy` fixture returns `asyncio.DefaultEventLoopPolicy()`, which is deprecated in Python 3.14 | delete the fixture; pytest-asyncio's default suffices |
| l | docs | `MARKET_DATA_SUMMARY.md` ("all issues resolved") and `backend/CLAUDE.md` (old `PriceUpdate` shape) are out of date | update after F1–F3 |

---

## 4. What is good

### 4.1 Simulator verified, not just plausible

Measured with events off, `dt = 1/252`, 20,000 steps:

| Property | Expected | Measured |
|---|---|---|
| corr AAPL/MSFT (tech) | 0.60 | 0.590 |
| corr AAPL/TSLA | 0.30 | 0.300 |
| corr JPM/V (finance) | 0.50 | 0.506 |
| corr AAPL/JPM (cross) | 0.30 | 0.298 |
| AAPL log-return σ | 0.0139 | 0.0138 |

- GBM uses the Itô-corrected exponential form, so prices are positive and unbiased. Internal prices are full precision, rounded only on output.
- `step()` with 40 tickers (the 30-ticker cap plus position-only tickers) costs **~28 µs**, against a 500 ms budget. Cholesky succeeds at 40×40.
- The engine (`GBMSimulator`) is pure and synchronous, separate from the async adapter. That is why it is so testable.

### 4.2 SSE works end to end

On a real uvicorn server (`curl -N /api/stream/prices`):
- The headers are correct: `text/event-stream`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`.
- The stream starts with `retry: 1000`. Each event is one batch of every tracked ticker, keyed by symbol, matching PLAN §6 apart from F3.
- It sent about 2 events per second (6 in 3 s), and closed cleanly on client disconnect and on shutdown.

### 4.3 Architecture

- The strategy pattern and factory follow PLAN §6. A whitespace-only key counts as unset.
- The cache is the only thing downstream code touches, and the version counter makes change detection O(1).
- `frozen=True, slots=True` `PriceUpdate` objects, a `threading.Lock` cache, and the blocking SDK in `asyncio.to_thread` are all correct choices.
- Both loops survive exceptions, and `stop()` is idempotent in both sources.
- The simulator seeds the cache before `start()` returns, and `add_ticker` prices immediately, so new tickers are tradable at once (PLAN §9).

### 4.4 Observation (not a defect)

At real-time Δt, about **31% of ticks are unchanged at 2 dp** for low-σ names (AAPL 0.32, V 0.30). The flash animation is driven by `direction`, so a third of ticks won't flash. If the demo feels static, scale Δt (`MARKET_SIMULATOR.md` §2.2 tuning knob) rather than changing the tick rate.

---

## 5. Test gaps

| Gap | Recommendation |
|---|---|
| Massive tests use `MagicMock` snapshots (hid F1) | Build with `TickerSnapshot.from_dict` / `GroupedDailyAgg.from_dict`; inject a `FakeClient` |
| No test for `NOT_AUTHORIZED` / fallback (F2) | Fake client raising `BadResponse('{"status":"NOT_AUTHORIZED"}')` |
| `stream.py` at 33%, no SSE tests | Drive `_generate_events` with a fake `Request` (retry line, batch, no duplicate on the same version, `{}` on empty, heartbeat); one ASGI test needs `httpx` added to dev deps |
| No contract test shared by both sources | Parametrised fixture over simulator and Massive-with-fake-client: start, add (idempotent, normalised), remove (clears cache), stop twice |
| No remove-during-poll race test (F5) | Slow fake fetch; remove mid-flight; assert not in cache |
| No GBM statistical / correlation test | The measurements in §4.1 as tests with ±0.05 tolerance, seeded |
| No full-default-set Cholesky test | `GBMSimulator(list(SEED_PRICES))._cholesky.shape == (10, 10)` |

All of these are sketched in `MARKET_DATA_DESIGN.md` §13.

### Reproductions

The probes behind F1, F2, F4–F8 and F10a, using real SDK models with no network. Run each one in `backend/` with `uv run python -c '…'`, or paste it into a test:

```python
# F1 — real SDK snapshot is discarded
from massive.rest.models import TickerSnapshot
from app.market import PriceCache
from app.market.massive_client import MassiveDataSource
import asyncio
c = PriceCache(); s = MassiveDataSource("k", c); s._tickers = ["AAPL"]; s._client = object()
s._fetch_snapshots = lambda: [TickerSnapshot.from_dict(
    {"ticker": "AAPL", "lastTrade": {"p": 190.5, "t": 1731753600123456789}})]
asyncio.run(s._poll_once()); assert len(c) == 0          # bug: should be 1

# F4 — remove does not bump version
c = PriceCache(); c.update("AAPL", 1.0); v = c.version; c.remove("AAPL"); assert c.version == v

# F7 — double registration
from app.market import create_stream_router
create_stream_router(PriceCache()); r = create_stream_router(PriceCache()); assert len(r.routes) == 2

# F8 — simulator case-sensitivity
from app.market.simulator import SimulatorDataSource
async def f8():
    s = SimulatorDataSource(PriceCache(), update_interval=60); await s.start(["AAPL"])
    await s.add_ticker("aapl"); assert s.get_tickers() == ["AAPL", "aapl"]; await s.stop()
asyncio.run(f8())

# F10a — explicit zero timestamp replaced
assert PriceCache().update("A", 1.0, timestamp=0.0).timestamp != 0.0
```

---

## 6. Recommended order of work

1. **F1 + F6:** rewrite snapshot parsing (`quote_from_snapshot`) and the Massive tests with real SDK models.
2. **F3:** add `session_open` / `session_change_percent`; update the docs.
3. **F2:** EOD fallback for free keys.
4. **F4, F5, F7:** cache `remove()` version bump and `{}` batches; the poll race filter; router inside the factory.
5. **F8, F9:** ticker normalisation in both sources; fix the dev-dependency setup.
6. **F10** cleanups and the §5 test gaps, then re-run coverage. The target is `stream.py` ≥ 80%.

Checklist §16 of `MARKET_DATA_DESIGN.md` already maps these to code. Once items 1–4 are done, Massive mode should be smoke-tested once against a real key, paid if available and free otherwise, using the script in design §8.4.

---

## 7. Resolution (2026-11-18)

All findings are fixed. Afterwards the suite has **146 tests passing** (up from 73), and passes again under `-W error`, so there are no warnings. Nine consecutive runs gave no flaky results. `ruff check` and `ruff format --check` are clean. Coverage is **99%**: `stream.py` 100% (up from 33%), `massive_client.py` 100%, `simulator.py` 99% (only a defensive duplicate guard is uncovered).

| Finding | Fix | Tests |
|---|---|---|
| F1 | `quote_from_snapshot()` reads `last_trade.sip_timestamp` (ns), falling back to `snapshot.updated`, and converts to seconds | `test_massive.py::TestQuoteFromSnapshot` with real `TickerSnapshot.from_dict` models |
| F2 | `NOT_AUTHORIZED` switches permanently to grouped-daily EOD mode: walks back up to 5 days, refreshes every 300 s, keeps a whole-market close table so new tickers are priced at once | `TestEodFallback` (6 tests) |
| F3 | `PriceUpdate.session_open` (defaults to price) and `session_change_percent`, both in `to_dict()`; the cache sets session_open on first write and carries it forward | `test_models.py::TestSessionChange`, `test_cache.py::TestPriceCacheSession` |
| F4 | `remove()` bumps the version (only when something was removed); the stream emits `{}` batches | `test_stream.py` removal and empty-batch tests |
| F5 | Ticker list copied for the worker thread; results filtered against the current tracked set after the await | `test_removed_during_inflight_poll_is_not_resurrected`, `test_worker_thread_gets_a_copy_of_tickers` |
| F6 | Fallback chain `last_trade.price → min.close → day.close → prev_day.close`, skipping zeros | parametrised fallback test |
| F7 | `APIRouter` created inside `create_stream_router()` | `TestRouterFactory` |
| F8 | Both sources normalise and de-duplicate in `start` / `add_ticker` / `remove_ticker` | `test_contract.py` (both sources), simulator-source tests |
| F9 | Dev tools moved to `[dependency-groups] dev` (plus `httpx`), so `uv sync` / `uv run pytest` just work; docs updated; PLAN §12 Docker step now `uv sync --frozen --no-dev` | — |
| F10a | `timestamp if timestamp is not None` | `test_explicit_zero_timestamp_is_kept` |
| F10b | `version` read under the lock | concurrent-writer test |
| F10c | Simulator `add_ticker` before `start()` logs a warning; the call is a documented no-op | `test_add_before_start_is_ignored_with_warning` |
| F10d | Generator no longer swallows `CancelledError`; disconnect logged in `finally` | `test_stops_on_disconnect` |
| F10e | `: keep-alive` comment after 15 s of silence | heartbeat tests |
| F10f | Left as is (acceptable; documented) | — |
| F10g | Same error logged once at ERROR, then DEBUG; "recovered" logged at INFO | `test_repeated_error_logged_once_then_recovery` |
| F10h | `LinAlgError` falls back to independent draws | `test_non_positive_definite_falls_back_to_independent` |
| F10i | `SEED_PRICES.get(t) or random.uniform(*UNKNOWN_PRICE_RANGE)`; params copied | `test_seeded_tickers_do_not_consume_random_draws` |
| F10j | `ruff format` applied | — |
| F10k | Deprecated `event_loop_policy` fixture removed | — |
| F10l | `MARKET_DATA_SUMMARY.md`, `backend/CLAUDE.md`, `backend/README.md`, `MARKET_INTERFACE.md` §8 updated | — |

All the §5 test gaps are closed: real SDK models, a shared contract suite, SSE generator tests plus a real-uvicorn HTTP streaming test, the race test, GBM statistics and correlation tests, and a full-default-set Cholesky test.

**Not done:**
- The optional `MASSIVE_POLL_INTERVAL` setting from `MARKET_DATA_DESIGN.md` §9. It is not in PLAN §5 and the review did not require it.
- The app-layer tracking service and lifespan wiring (design §11). These belong with the DB and routes work.
- A live Massive smoke test. No API key is available in this environment.
