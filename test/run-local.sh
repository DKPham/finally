#!/usr/bin/env bash
# Run the E2E suite locally.
#
#   ./run-local.sh            start a throwaway backend (LLM_MOCK, temp DB) serving frontend/out, run the suite, stop it
#   BASE_URL=http://host:port ./run-local.sh   run against an already running app instead
#
# Extra arguments are passed to `playwright test` (e.g. ./run-local.sh e2e/03-buy.spec.ts --headed).
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/.." && pwd)"
cd "$HERE"

[ -d node_modules/@playwright/test ] || npm ci
npx playwright install chromium >/dev/null 2>&1 || echo "warning: could not run playwright install (browser may already be installed)" >&2

if [ -n "${BASE_URL:-}" ]; then
  exec npx playwright test "$@"
fi

PORT="${PORT:-8000}"
export BASE_URL="http://localhost:$PORT"
[ -f "$ROOT/frontend/out/index.html" ] || { echo "frontend/out missing: run 'npm run build' in frontend/ first" >&2; exit 1; }

TMP_DB_DIR="$(mktemp -d "${TMPDIR:-/tmp}/finally-e2e.XXXXXX")"
LOG="$TMP_DB_DIR/backend.log"
(
  cd "$ROOT/backend"
  LLM_MOCK=true MASSIVE_API_KEY= OPENROUTER_API_KEY= DB_PATH="$TMP_DB_DIR/finally.db" \
    exec uv run uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
) >"$LOG" 2>&1 &
SERVER_PID=$!
cleanup() { kill "$SERVER_PID" 2>/dev/null || true; wait "$SERVER_PID" 2>/dev/null || true; echo "backend log: $LOG"; }
trap cleanup EXIT

for _ in $(seq 1 60); do
  curl -fsS "$BASE_URL/api/health" >/dev/null 2>&1 && break
  kill -0 "$SERVER_PID" 2>/dev/null || { cat "$LOG"; exit 1; }
  sleep 0.5
done
curl -fsS "$BASE_URL/api/health" >/dev/null || { echo "backend did not become healthy" >&2; cat "$LOG"; exit 1; }

npx playwright test "$@"
