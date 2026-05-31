#!/usr/bin/env bash
# start.sh — Single-instance launcher for the IBKR Wheel Scanner backend.
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

# ── Also kill any orphaned uvicorn workers for this app ───────────────────────
# (Handles the case where a previous --reload left an orphan with PPID=1)
pkill -f "uvicorn main:app.*8002" 2>/dev/null || true

echo "Starting IBKR Wheel Scanner backend on port 8002 (no --reload)..."
exec .venv/bin/uvicorn main:app --host 0.0.0.0 --port 8002
