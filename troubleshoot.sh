#!/usr/bin/env bash
set -u

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND_DIR="${FRONTEND_DIR:-$ROOT_DIR/frontend}"
BACKEND_DIR="${BACKEND_DIR:-$ROOT_DIR/backend}"
IBKR_DIR="${IBKR_DIR:-$ROOT_DIR/backend/ibkr}"
LOG_DIR="${LOG_DIR:-$ROOT_DIR/tmp/troubleshoot}"

FRONTEND_PORT="${FRONTEND_PORT:-3000}"
BACKEND_PORT="${BACKEND_PORT:-8000}"
IBKR_PORT="${IBKR_PORT:-8002}"
HOST="${HOST:-localhost}"

FRONTEND_URL="${FRONTEND_URL:-http://$HOST:$FRONTEND_PORT/ai-advisor}"
BACKEND_URL="${BACKEND_URL:-http://127.0.0.1:$BACKEND_PORT}"
IBKR_URL="${IBKR_URL:-http://127.0.0.1:$IBKR_PORT}"
FRONTEND_ORIGIN="${FRONTEND_ORIGIN:-http://$HOST:$FRONTEND_PORT}"

FIX=1
RESTART=0
STOP_ONLY=0
RUN_TESTS=0
SKIP_IBKR=0
FOREGROUND=0
FOREGROUND_PIDS=()

RED=""
GREEN=""
YELLOW=""
BLUE=""
RESET=""
if [ -t 1 ]; then
  RED="$(printf '\033[31m')"
  GREEN="$(printf '\033[32m')"
  YELLOW="$(printf '\033[33m')"
  BLUE="$(printf '\033[34m')"
  RESET="$(printf '\033[0m')"
fi

usage() {
  cat <<EOF
Usage: ./troubleshoot.sh [options]

Checks and repairs the local FinanceOS dev stack:
  - main FastAPI backend on port $BACKEND_PORT
  - IBKR research backend on port $IBKR_PORT
  - Next frontend on port $FRONTEND_PORT
  - /ai-advisor page and frontend-to-backend API proxy

Options:
  --check-only       Only report status; do not install, start, stop, or restart.
  --restart          Stop required local services on the expected ports, then start them again.
  --foreground       Keep newly started services attached to this script until Ctrl-C.
  --stop             Stop required local services and exit.
  --run-tests        Also run focused backend tests and frontend typecheck.
  --skip-ibkr        Skip IBKR backend start/check.
  --help, -h         Show this help.

Environment overrides:
  FRONTEND_PORT=$FRONTEND_PORT BACKEND_PORT=$BACKEND_PORT IBKR_PORT=$IBKR_PORT
  FRONTEND_URL=$FRONTEND_URL BACKEND_URL=$BACKEND_URL IBKR_URL=$IBKR_URL
  FRONTEND_DIR=$FRONTEND_DIR BACKEND_DIR=$BACKEND_DIR IBKR_DIR=$IBKR_DIR LOG_DIR=$LOG_DIR
EOF
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --check-only)
      FIX=0
      shift
      ;;
    --restart)
      RESTART=1
      shift
      ;;
    --foreground)
      FOREGROUND=1
      shift
      ;;
    --stop)
      STOP_ONLY=1
      shift
      ;;
    --run-tests)
      RUN_TESTS=1
      shift
      ;;
    --skip-ibkr)
      SKIP_IBKR=1
      shift
      ;;
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "${RED}Unknown argument:${RESET} $1"
      usage
      exit 2
      ;;
  esac
done

info() { echo "${BLUE}==>${RESET} $*"; }
ok() { echo "${GREEN}OK:${RESET} $*"; }
warn() { echo "${YELLOW}WARN:${RESET} $*"; }
fail() { echo "${RED}FAIL:${RESET} $*"; }
have() { command -v "$1" >/dev/null 2>&1; }

mkdir -p "$LOG_DIR"

frontend_log="$LOG_DIR/frontend-$FRONTEND_PORT.log"
backend_log="$LOG_DIR/backend-$BACKEND_PORT.log"
ibkr_log="$LOG_DIR/ibkr-$IBKR_PORT.log"
frontend_pid_file="$LOG_DIR/frontend-$FRONTEND_PORT.pid"
backend_pid_file="$LOG_DIR/backend-$BACKEND_PORT.pid"
ibkr_pid_file="$LOG_DIR/ibkr-$IBKR_PORT.pid"

http_status() {
  curl -sS -o /dev/null -w "%{http_code}" --max-time 8 "$1" 2>/dev/null || true
}

listener_pids() {
  lsof -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null || true
}

show_listener() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN 2>/dev/null || true
}

stop_port() {
  port="$1"
  label="$2"
  pids="$(listener_pids "$port")"
  if [ -z "$pids" ]; then
    ok "$label port $port is already free"
    return 0
  fi
  warn "Stopping $label on port $port (PIDs: $pids)"
  kill $pids 2>/dev/null || true
  sleep 2
  pids="$(listener_pids "$port")"
  if [ -n "$pids" ]; then
    warn "Force-stopping $label on port $port (PIDs: $pids)"
    kill -9 $pids 2>/dev/null || true
    sleep 1
  fi
  pids="$(listener_pids "$port")"
  if [ -n "$pids" ]; then
    fail "$label port $port is still occupied"
    show_listener "$port"
    return 1
  fi
  ok "$label port $port is free"
}

stop_recorded_pid() {
  pid_file="$1"
  label="$2"
  if [ ! -f "$pid_file" ]; then
    return 0
  fi
  pid="$(cat "$pid_file" 2>/dev/null || true)"
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    warn "Stopping recorded $label process $pid"
    kill "$pid" 2>/dev/null || true
    sleep 1
  fi
  rm -f "$pid_file"
}

track_foreground_pid() {
  pid="$1"
  label="$2"
  FOREGROUND_PIDS+=("$pid")
  ok "$label started in foreground supervision (PID $pid)"
}

cleanup_foreground_pids() {
  if [ "${#FOREGROUND_PIDS[@]}" -eq 0 ]; then
    return 0
  fi
  warn "Stopping foreground-supervised services"
  for pid in "${FOREGROUND_PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
}

wait_for_url() {
  url="$1"
  label="$2"
  attempts="${3:-30}"
  attempt=1
  while [ "$attempt" -le "$attempts" ]; do
    status="$(http_status "$url")"
    case "$status" in
      200|301|302|307|308)
        ok "$label is healthy at $url (HTTP $status)"
        return 0
        ;;
    esac
    sleep 1
    attempt=$((attempt + 1))
  done
  fail "$label did not become healthy at $url"
  return 1
}

require_path() {
  path="$1"
  description="$2"
  if [ ! -e "$path" ]; then
    fail "Missing $description: $path"
    exit 1
  fi
  ok "$description found"
}

install_if_missing() {
  if [ "$FIX" != "1" ]; then
    return 0
  fi

  if [ ! -d "$FRONTEND_DIR/node_modules" ]; then
    warn "frontend/node_modules is missing"
    info "Installing frontend dependencies"
    (cd "$FRONTEND_DIR" && npm install) || exit 1
  fi

  if [ ! -x "$BACKEND_DIR/.venv/bin/python" ]; then
    warn "backend/.venv is missing"
    info "Creating backend virtualenv"
    python3 -m venv "$BACKEND_DIR/.venv" || exit 1
  fi
  if [ ! -x "$BACKEND_DIR/.venv/bin/uvicorn" ]; then
    info "Installing backend dependencies"
    "$BACKEND_DIR/.venv/bin/pip" install -r "$BACKEND_DIR/requirements.txt" || exit 1
  fi

  if [ "$SKIP_IBKR" != "1" ]; then
    if [ ! -x "$IBKR_DIR/.venv/bin/python" ]; then
      warn "backend/ibkr/.venv is missing"
      info "Creating IBKR backend virtualenv"
      python3 -m venv "$IBKR_DIR/.venv" || exit 1
    fi
    if [ ! -x "$IBKR_DIR/.venv/bin/uvicorn" ]; then
      info "Installing IBKR backend dependencies"
      "$IBKR_DIR/.venv/bin/pip" install -r "$IBKR_DIR/requirements.txt" || exit 1
    fi
  fi
}

start_backend() {
  if [ -n "$(listener_pids "$BACKEND_PORT")" ]; then
    ok "Main backend already listening on $BACKEND_PORT"
    return 0
  fi
  if [ "$FIX" != "1" ]; then
    fail "Main backend is not listening on $BACKEND_PORT"
    return 1
  fi
  info "Starting main backend on port $BACKEND_PORT"
  if [ "$FOREGROUND" = "1" ]; then
    bash -c "cd '$ROOT_DIR' && exec env PYTHONPATH=backend '$BACKEND_DIR/.venv/bin/uvicorn' app.main:app --host 0.0.0.0 --port '$BACKEND_PORT'" >"$backend_log" 2>&1 &
  else
    nohup bash -c "cd '$ROOT_DIR' && exec env PYTHONPATH=backend '$BACKEND_DIR/.venv/bin/uvicorn' app.main:app --host 0.0.0.0 --port '$BACKEND_PORT'" >"$backend_log" 2>&1 </dev/null &
  fi
  service_pid=$!
  echo "$service_pid" >"$backend_pid_file"
  if [ "$FOREGROUND" = "1" ]; then
    track_foreground_pid "$service_pid" "Main backend"
  else
    disown "$service_pid" 2>/dev/null || true
  fi
  wait_for_url "$BACKEND_URL/health" "Main backend" 30
}

start_ibkr() {
  if [ "$SKIP_IBKR" = "1" ]; then
    warn "Skipping IBKR backend"
    return 0
  fi
  if [ -n "$(listener_pids "$IBKR_PORT")" ]; then
    ok "IBKR backend already listening on $IBKR_PORT"
    return 0
  fi
  if [ "$FIX" != "1" ]; then
    fail "IBKR backend is not listening on $IBKR_PORT"
    return 1
  fi
  info "Starting IBKR research backend on port $IBKR_PORT"
  if [ "$FOREGROUND" = "1" ]; then
    bash -c "cd '$IBKR_DIR' && exec ./start.sh" >"$ibkr_log" 2>&1 &
  else
    nohup bash -c "cd '$IBKR_DIR' && exec ./start.sh" >"$ibkr_log" 2>&1 </dev/null &
  fi
  service_pid=$!
  echo "$service_pid" >"$ibkr_pid_file"
  if [ "$FOREGROUND" = "1" ]; then
    track_foreground_pid "$service_pid" "IBKR backend"
  else
    disown "$service_pid" 2>/dev/null || true
  fi
  wait_for_url "$IBKR_URL/api/status" "IBKR backend" 30
}

start_frontend() {
  if [ -n "$(listener_pids "$FRONTEND_PORT")" ]; then
    ok "Frontend already listening on $FRONTEND_PORT"
    return 0
  fi
  if [ "$FIX" != "1" ]; then
    fail "Frontend is not listening on $FRONTEND_PORT"
    return 1
  fi
  info "Starting frontend on port $FRONTEND_PORT"
  if [ "$FOREGROUND" = "1" ]; then
    bash -c "cd '$FRONTEND_DIR' && exec env NEXT_PUBLIC_API_URL='$BACKEND_URL' NEXT_PUBLIC_IBKR_API_URL='$IBKR_URL' npm run dev -- --hostname 0.0.0.0 --port '$FRONTEND_PORT'" >"$frontend_log" 2>&1 &
  else
    nohup bash -c "cd '$FRONTEND_DIR' && exec env NEXT_PUBLIC_API_URL='$BACKEND_URL' NEXT_PUBLIC_IBKR_API_URL='$IBKR_URL' npm run dev -- --hostname 0.0.0.0 --port '$FRONTEND_PORT'" >"$frontend_log" 2>&1 </dev/null &
  fi
  service_pid=$!
  echo "$service_pid" >"$frontend_pid_file"
  if [ "$FOREGROUND" = "1" ]; then
    track_foreground_pid "$service_pid" "Frontend"
  else
    disown "$service_pid" 2>/dev/null || true
  fi
  wait_for_url "$FRONTEND_URL" "Frontend" 40
}

check_frontend_api_proxy() {
  info "Checking frontend API proxy"
  status="$(http_status "$FRONTEND_ORIGIN/api/health")"
  case "$status" in
    200)
      ok "Frontend API proxy reaches the main backend"
      return 0
      ;;
    500|502|503|504|"")
      fail "Frontend API proxy is not healthy (HTTP ${status:-none})"
      echo "This is the check that catches the blank Recommendation Agent 500 when port $BACKEND_PORT is down."
      return 1
      ;;
    *)
      fail "Frontend API proxy returned unexpected HTTP $status"
      return 1
      ;;
  esac
}

run_checks() {
  info "Running focused checks"
  (cd "$ROOT_DIR" && PYTHONPATH=backend "$BACKEND_DIR/.venv/bin/python" -m pytest backend/tests/test_recommendation_agent.py) || exit 1
  (cd "$FRONTEND_DIR" && npm run typecheck) || exit 1
}

info "Troubleshooting FinanceOS local stack"

require_path "$FRONTEND_DIR/package.json" "frontend package.json"
require_path "$BACKEND_DIR/requirements.txt" "backend requirements"
require_path "$BACKEND_DIR/app/main.py" "main backend app"
if [ "$SKIP_IBKR" != "1" ]; then
  require_path "$IBKR_DIR/start.sh" "IBKR backend launcher"
fi

have node || { fail "node is not on PATH"; exit 1; }
have npm || { fail "npm is not on PATH"; exit 1; }
have curl || { fail "curl is not on PATH"; exit 1; }
have lsof || { fail "lsof is not on PATH"; exit 1; }
ok "node $(node --version)"
ok "npm $(npm --version)"

if [ "$RESTART" = "1" ] || [ "$STOP_ONLY" = "1" ]; then
  stop_recorded_pid "$frontend_pid_file" "frontend"
  stop_recorded_pid "$backend_pid_file" "main backend"
  stop_recorded_pid "$ibkr_pid_file" "IBKR backend"
  stop_port "$FRONTEND_PORT" "frontend" || exit 1
  stop_port "$BACKEND_PORT" "main backend" || exit 1
  if [ "$SKIP_IBKR" != "1" ]; then
    stop_port "$IBKR_PORT" "IBKR backend" || exit 1
  fi
fi

if [ "$STOP_ONLY" = "1" ]; then
  ok "Stopped requested services"
  exit 0
fi

install_if_missing
start_backend || exit 1
start_ibkr || exit 1
start_frontend || exit 1

wait_for_url "$BACKEND_URL/health" "Main backend" 5 || exit 1
if [ "$SKIP_IBKR" != "1" ]; then
  wait_for_url "$IBKR_URL/api/status" "IBKR backend" 5 || exit 1
fi
wait_for_url "$FRONTEND_URL" "Frontend" 5 || exit 1
check_frontend_api_proxy || exit 1

if [ "$RUN_TESTS" = "1" ]; then
  run_checks
fi

ok "FinanceOS local stack is ready"
echo "Frontend: $FRONTEND_URL"
echo "Main backend: $BACKEND_URL"
if [ "$SKIP_IBKR" != "1" ]; then
  echo "IBKR backend: $IBKR_URL"
fi
echo "Logs: $LOG_DIR"

if [ "$FOREGROUND" = "1" ] && [ "${#FOREGROUND_PIDS[@]}" -gt 0 ]; then
  echo
  info "Foreground mode is keeping newly started services alive. Press Ctrl-C to stop them."
  trap cleanup_foreground_pids INT TERM EXIT
  wait "${FOREGROUND_PIDS[@]}"
fi
