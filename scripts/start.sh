#!/usr/bin/env bash
# Start the FinAlly container. Usage: scripts/start.sh [--build] [--no-open]
set -euo pipefail

IMAGE="finally"
CONTAINER="finally"
PORT="${PORT:-8000}"
URL="http://localhost:${PORT}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

BUILD=0
OPEN_BROWSER=1
for arg in "$@"; do
  case "$arg" in
    --build) BUILD=1 ;;
    --no-open) OPEN_BROWSER=0 ;;
    -h|--help) echo "Usage: $0 [--build] [--no-open]"; exit 0 ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

if ! command -v docker >/dev/null 2>&1; then
  echo "Error: docker is not installed or not on PATH." >&2
  exit 1
fi

if [[ "$BUILD" -eq 1 ]] || ! docker image inspect "$IMAGE" >/dev/null 2>&1; then
  echo "Building Docker image '$IMAGE'..."
  docker build -t "$IMAGE" .
fi

# Remove any existing container (running or stopped)
if docker container inspect "$CONTAINER" >/dev/null 2>&1; then
  echo "Removing existing container '$CONTAINER'..."
  docker rm -f "$CONTAINER" >/dev/null
fi

mkdir -p "$ROOT_DIR/db"

RUN_ARGS=(-d --name "$CONTAINER" -v "$ROOT_DIR/db:/app/db" -p "${PORT}:8000")
if [[ -f "$ROOT_DIR/.env" ]]; then
  RUN_ARGS+=(--env-file "$ROOT_DIR/.env")
else
  echo "Note: no .env file found; starting without it (AI chat will be unconfigured)."
fi

docker run "${RUN_ARGS[@]}" "$IMAGE" >/dev/null

echo "FinAlly is running at $URL"

if [[ "$OPEN_BROWSER" -eq 1 ]]; then
  if command -v open >/dev/null 2>&1; then
    open "$URL" >/dev/null 2>&1 || true
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$URL" >/dev/null 2>&1 || true
  fi
fi
