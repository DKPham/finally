# Team Contract — Ownership & Interfaces

PLAN.md is the spec. This file only says **who owns what** and **the Python interfaces between backend modules**, so teammates can work in parallel in the same working tree. Do not edit files you don't own: message the owner instead. If you must change an interface below, update this file and tell everyone affected.

## Ownership

| Teammate | Owns |
|---|---|
| `db-engineer` | `backend/app/db/**`, `backend/tests/db/**` |
| `backend-engineer` | `backend/app/main.py`, `backend/app/api/**` (except `chat.py`), `backend/app/services/**`, `backend/app/market/**` (the `session_open` change), `backend/pyproject.toml` + `uv.lock` (others ask before adding deps; the LLM engineer may run `uv add litellm`), `backend/tests/api/**`, `backend/tests/services/**`, `backend/tests/market/**` |
| `llm-engineer` | `backend/app/llm/**`, `backend/app/api/chat.py`, `backend/tests/llm/**` |
| `frontend-engineer` | `frontend/**` |
| `devops-engineer` | `Dockerfile`, `.dockerignore`, `scripts/**`, `.env.example`, `db/.gitkeep`, the root `.gitignore` |
| `integration-tester` | `test/**` (Playwright + `test/docker-compose.test.yml`) |

## Backend interfaces

All DB access goes through `app.db`. Use the stdlib `sqlite3`, synchronous; it is fine to call it from async routes since the queries are tiny.

### `app.db` (db-engineer)
```python
def init_db(db_path: str | None = None) -> None   # create tables, seed if users_profile empty; resolves DB_PATH env / default <project root>/db/finally.db
def get_db_path() -> str
@contextmanager
def transaction() -> Iterator[sqlite3.Connection]  # BEGIN IMMEDIATE ... COMMIT/ROLLBACK; row_factory=sqlite3.Row
# Repository functions: every one takes conn as the first arg and user_id="default" as a kwarg.
get_cash(conn) -> float;  set_cash(conn, amount) -> None
list_watchlist(conn) -> list[dict]           # {ticker, added_at}, in the order added
add_watchlist(conn, ticker) -> dict          # raises app.db.DuplicateError
remove_watchlist(conn, ticker) -> None       # raises app.db.NotFoundError
count_watchlist(conn) -> int
list_positions(conn) -> list[dict];  get_position(conn, ticker) -> dict | None   # {ticker, quantity, avg_cost, updated_at}
upsert_position(conn, ticker, quantity, avg_cost) -> None;  delete_position(conn, ticker) -> None
insert_trade(conn, ticker, side, quantity, price) -> dict   # returns the full row incl. id, executed_at
insert_snapshot(conn, total_value) -> None;  list_snapshots(conn, limit=1000) -> list[dict]   # oldest first
insert_chat_message(conn, role, content, actions: list | None) -> dict
list_chat_messages(conn, limit=50) -> list[dict]   # oldest first; actions decoded from JSON
def now_iso() -> str   # "2026-11-16T14:03:22Z"
```

### `app.services` (backend-engineer)
```python
class ServiceError(Exception):  status_code: int; detail: str    # 400/404/409, maps to HTTPException
# app.services.state: process-wide singletons set by the lifespan handler
price_cache: PriceCache; market_source: MarketDataSource
# app.services.portfolio
def get_portfolio() -> dict                    # GET /api/portfolio shape (PLAN §8)
async def execute_trade(ticker: str, side: str, quantity: float) -> dict   # {"trade": ..., "portfolio": ...}; raises ServiceError. Implements PLAN §9, incl. auto-add to watchlist
def record_snapshot() -> None
# app.services.watchlist
def list_watchlist() -> list[dict]             # GET /api/watchlist shape
async def add_ticker(ticker: str) -> dict      # raises ServiceError(409/400/422)
async def remove_ticker(ticker: str) -> None   # raises ServiceError(404); keeps the ticker in the source if a position is open
def normalize_ticker(raw: str) -> str          # uppercases + validates ^[A-Z][A-Z.]{0,5}$, raises ServiceError(422)
```
`execute_trade`, `add_ticker` and `remove_ticker` are **async** (they await `market_source.add_ticker/remove_ticker`; the simulator seeds a new ticker's price there, so a trade in a brand-new ticker can fill immediately). `get_portfolio`, `list_watchlist`, `record_snapshot` and `normalize_ticker` are sync.

### `app.llm` + `app.api.chat` (llm-engineer)
```python
router: APIRouter   # in app/api/chat.py: POST /api/chat, GET /api/chat/history
```
The chat flow calls `get_portfolio`, `list_watchlist`, `execute_trade`, `add_ticker` and `remove_ticker` from `app.services`, catching `ServiceError` into failed action results. `main.py` includes `app.api.chat.router`.

## Shared conventions
- Run backend tests with `cd backend && uv run --extra dev pytest`. Don't break other people's tests.
- `.env` exists at the project root with `OPENROUTER_API_KEY`. Never print or commit it.
- E2E and CI use `LLM_MOCK=true`.
- Frontend dev: `next dev` with rewrites to `localhost:8000`; production is the static export in `frontend/out`, copied to `/app/static` in Docker. Locally, the backend serves `../frontend/out` if `static/` is absent.
