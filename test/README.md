# FinAlly E2E tests

Playwright (TypeScript) specs for the scenarios in `planning/PLAN.md` §13. The app is single-user with one database, so specs run serially in file order; `01-fresh-start` expects a freshly created database.

## In Docker (canonical)

```bash
docker compose -f test/docker-compose.test.yml up --build --abort-on-container-exit --exit-code-from playwright
docker compose -f test/docker-compose.test.yml down -v
```

Builds the app from the root `Dockerfile` with `LLM_MOCK=true` and no bind mount (throwaway DB), waits for `/api/health`, then runs the suite in `mcr.microsoft.com/playwright` against `http://finally:8000`.

## Locally

```bash
cd frontend && npm run build    # produces frontend/out
cd ../test && ./run-local.sh    # starts backend on :8000 with LLM_MOCK and a temp DB, runs the suite
BASE_URL=http://localhost:8000 ./run-local.sh   # or run against an app you started yourself
```

Reports: `npx playwright show-report`.
