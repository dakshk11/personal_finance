#!/usr/bin/env bash
# start.sh — Single-instance launcher for the IBKR research backend.
#
# Always run this instead of uvicorn directly. It:
#   1. Kills any existing process on port 8002 (including orphaned workers)
#   2. Starts uvicorn WITHOUT --reload (--reload causes orphan processes that
#      hold open IBKR market-data subscriptions and trigger error 101)
#
# Usage:
#   cd backend/ibkr && ./start.sh

set -euo pipefail
cd "$(dirname "$0")"

# ── Kill any existing ibkr backend on port 8002 ───────────────────────────────
EXISTING=$(lsof -ti :8002 2>/dev/null || true)
if [ -n "$EXISTING" ]; then
    echo "Stopping existing ibkr backend (PIDs: $EXISTING)..."
    kill $EXISTING 2>/dev/null || true
    sleep 2
    # Force-kill anything that didn't exit cleanly
    STILL=$(lsof -ti :8002 2>/dev/null || true)
    if [ -n "$STILL" ]; then
        echo "Force-killing stubborn processes (PIDs: $STILL)..."
        kill -9 $STILL 2>/dev/null || true
        sleep 1
    fi
fi

# ── Also kill orphaned uvicorn workers for this app ───────────────────────────
# Handles stale workers that are no longer listening on 8002 but still hold the
# TWS client id open, which breaks Composite/OptiTrade/Wheel IBKR endpoints.
ORPHANS=$(pgrep -f "uvicorn main:app.*--port 8002" 2>/dev/null || true)
if [ -n "$ORPHANS" ]; then
    echo "Stopping orphaned ibkr uvicorn workers (PIDs: $ORPHANS)..."
    kill $ORPHANS 2>/dev/null || true
    sleep 2
    STUBBORN=$(pgrep -f "uvicorn main:app.*--port 8002" 2>/dev/null || true)
    if [ -n "$STUBBORN" ]; then
        echo "Force-killing orphaned ibkr uvicorn workers (PIDs: $STUBBORN)..."
        kill -9 $STUBBORN 2>/dev/null || true
        sleep 1
    fi
fi

echo "Starting IBKR research backend on port 8002 (no --reload)..."
if [ -x ".venv/bin/uvicorn" ]; then
    UVICORN_BIN=".venv/bin/uvicorn"
else
    UVICORN_BIN="$(command -v uvicorn)"
fi
exec "$UVICORN_BIN" main:app --host 0.0.0.0 --port 8002
