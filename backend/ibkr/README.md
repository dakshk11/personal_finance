# IBKR Research Backend

Standalone FastAPI service that powers the **Wheel Scanner**, **IBKR Breakout Scanner**, **Composite Signal Algorithm**, and **OptiTrade Lab** tabs in FinanceOS Studio.

Runs on **port 8002**, separate from the main FinanceOS backend (port 8000).

## What it does

| Layer | Detail |
|---|---|
| **IBKR live quotes** | Connects to TWS/Gateway via `ib_insync`, polls snapshot batches every 30 s |
| **IBKR historical bars** | Fetches daily historical bars for Composite Signal Algorithm, OptiTrade Lab, and cache-backed breakout scans |
| **CBOE options data** | 15-min delayed chains from the free CBOE CDN, cached daily to disk |
| **Analytics** | RSI(14), Bollinger Band %(20), breakout detectors, composite monthly trend, and OptiTrade-style levels/backtests |
| **Signals** | CSP (annualised yield > 5 %), CC (annualised yield > 5 %), LEAP (RSI ≤ 40 AND BB% ≤ 20) |
| **Scanner** | CSP and CC candidate filter with configurable DTE, delta, yield, and OI constraints |
| **WebSocket** | `/ws/quotes` streams live quote diffs to the frontend every 1 s |

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/status` | IBKR connection state, quote counts, price source |
| GET | `/api/watchlist` | Configured Nasdaq-100 + leveraged ETF universe with quotes + metrics |
| GET | `/api/quotes?symbols=AAPL,TSLA` | On-demand quotes for up to 20 custom tickers |
| GET | `/api/options/{symbol}` | Full CBOE option chain split into puts / calls |
| GET | `/api/scanner/csp` | Cash-Secured Put scan (params: dte, delta, yield, OI) |
| GET | `/api/scanner/cc` | Covered Call scan (same params) |
| GET | `/api/breakout/status` | Breakout cache freshness + IBKR connection state |
| GET | `/api/breakout/scan?source=ibkr&index=ndx100` | IBKR-backed Nasdaq-100 breakout scan |
| GET | `/api/composite-signal` | SOXL/TQQQ/UPRO composite monthly signal package |
| GET | `/api/optitrade-lab/signals` | Leveraged ETF signal package |
| GET | `/api/optitrade-lab/backtest` | Settings-aware OptiTrade Lab backtest |
| WS  | `/ws/quotes` | Snapshot + 1 s diff stream of all watchlist quotes |

## Quick start

```bash
cd backend/ibkr

# First time: create venv and install deps
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env      # edit TWS_PORT=7497 for paper trading

# Start server (always use start.sh, never --reload or direct uvicorn)
./start.sh
```

> **Why not `--reload`?** uvicorn's `--reload` mode kills workers with SIGKILL when files
> change, bypassing FastAPI's shutdown hook. ib_insync never disconnects cleanly, leaving
> orphaned processes connected to TWS. Each orphan runs its own market-data poll loop,
> and the combined subscriptions trigger IBKR error 101 ("Max number of tickers").
> `start.sh` kills any existing process on port 8002 and orphaned port-8002 uvicorn
> workers before starting — guaranteeing a single clean connection every time.

TWS must be running with socket API enabled on port 7496 (live) or 7497 (paper) for IBKR live quotes and historical-bar labs. Without TWS, the service still starts and Wheel Scanner prices fall back to CBOE 15-min delayed data automatically.

If TWS reports `client id is already in use`, a stale local worker is still connected. Run `./start.sh`; it will clean duplicate workers before starting the single expected backend process.

## Watchlist universe

Nasdaq-100 style universe from `data/tickers.py` plus leveraged ETFs such as `SOXL`, `TQQQ`, and `UPRO`.

## File layout

```
backend/ibkr/
├── main.py                  FastAPI app, endpoints, background loops
├── config.py                Pydantic settings (reads .env)
├── start.sh                 Single-instance launcher, stale-worker cleanup
├── requirements.txt         Python dependencies (includes ib_insync)
├── .env.example             Environment template
├── data/
│   ├── tickers.py           Nasdaq-100 + leveraged ETF universe (ALL_TICKERS)
│   └── cboe_daily_cache.json  Persistent daily chain cache (auto-written)
└── services/
    ├── ibkr_service.py      TWS connection, contract qualification, snapshot poll
    ├── cboe_service.py      CBOE chain fetch, parse, disk+memory cache
    ├── analytics_service.py RSI(14) and BB%(20) from IBKR daily bars
    └── scanner_service.py   CSP and CC filter logic
```
