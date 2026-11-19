# Review: working tree changes since `HEAD` (`ab1fbb3`)

## Findings

1. **[P2] E2E tests use test IDs that the frontend does not render.** [`01-fresh-start.spec.ts`](../test/e2e/01-fresh-start.spec.ts#L30) and [`03-buy.spec.ts`](../test/e2e/03-buy.spec.ts#L9) query `header-cash`, while [`Header.tsx`](../frontend/src/components/Header.tsx#L48) renders `cash-balance`; the fresh-start spec also queries `header-total-value`, while the component renders `total-value`. The fresh-start and watchlist specs query `price-${ticker}`, but [`Watchlist.tsx`](../frontend/src/components/Watchlist.tsx#L102) renders `watchlist-price-${ticker}`. The watchlist spec queries `remove-${ticker}`, but the component renders `watchlist-remove-${ticker}`. These locator failures prevent the corresponding E2E flows from completing. Update the E2E selectors or the component test IDs consistently; also fix [`priceSnapshot()`](../test/e2e/helpers.ts#L86), whose `^price-` selector misses the rendered watchlist price cells.

2. **[P2] `init_db(":memory:")` initializes a different database from the one it seeds.** [`connection.py`](../backend/app/db/connection.py#L55) creates the schema using one connection, closes it, then invokes `transaction()` to seed using a second connection. SQLite creates a separate database for each `:memory:` connection, so this path fails with `no such table: users_profile`. Keep the schema and seed operations on one connection or use a shared in-memory URI with a keeper connection.

## Scope and checks

Reviewed the changed backend database, services, API, LLM and market code; frontend; Docker/scripts; and E2E setup. `git diff --check HEAD` passed. No tests were run as part of this review.
