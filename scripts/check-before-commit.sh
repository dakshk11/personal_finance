#!/usr/bin/env bash
set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

NEXT_ENV_BACKUP=""
if [ -f frontend/next-env.d.ts ]; then
  NEXT_ENV_BACKUP="$(mktemp)"
  cp frontend/next-env.d.ts "$NEXT_ENV_BACKUP"
fi

cleanup() {
  if [ -n "$NEXT_ENV_BACKUP" ] && [ -f "$NEXT_ENV_BACKUP" ]; then
    cp "$NEXT_ENV_BACKUP" frontend/next-env.d.ts
    rm -f "$NEXT_ENV_BACKUP"
  fi
}
trap cleanup EXIT

echo "==> IBKR process sanity"
IBKR_PIDS="$(pgrep -f "uvicorn main:app.*--port 8002" 2>/dev/null || true)"
IBKR_COUNT="$(printf "%s\n" "$IBKR_PIDS" | sed '/^$/d' | wc -l | tr -d ' ')"
if [ "$IBKR_COUNT" -gt 1 ]; then
  echo "Found multiple IBKR backend workers on port 8002:"
  printf "%s\n" "$IBKR_PIDS"
  echo "Run backend/ibkr/start.sh to clean stale workers before committing."
  exit 1
fi

echo "==> Backend tests"
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests

echo "==> Frontend contract checks"
npm --prefix frontend run test:contracts

echo "==> Frontend typecheck"
npm --prefix frontend run typecheck

echo "==> Frontend production build"
npm --prefix frontend run build

echo "Every-commit regression gate passed."
