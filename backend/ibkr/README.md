# IBKR Wheel Scanner — Backend

Standalone FastAPI service that powers the **Wheel Scanner** tab in FinanceOS Studio.

Runs on **port 8002**, separate from the main FinanceOS backend (port 8000).

## What it does

| Layer | Detail |
|---|---|
| **IBKR live quotes** | Connects to TWS/Gateway via `ib_insync`, polls snapshot batches every 30 s |
| **CBOE options data** | 15-min delayed chains from the free CBOE CDN, cached daily to disk |
| **Analytics** | RSI(14) and Bollinger Band %(20) from 30-day IBKR daily bars |
| **Signals** | CSP (annualised yield > 5 %), CC (annualised yield > 5 %), LEAP (RSI ≤ 40 AND BB% ≤ 20) |
| **Scanner** | CSP and CC candidate filter with configurable DTE, delta, yield, and OI constraints |
| **WebSocket** | `/ws/quotes` streams live quote diffs to the frontend every 1 s |

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/status` | IBKR connection state, quote counts, price source |
| GET | `/api/watchlist` | All 107 symbols with quotes + metrics |
| GET | `/api/quotes?symbols=AAPL,TSLA` | On-demand quotes for up to 20 custom tickers |
| GET | `/api/options/{symbol}` | Full CBOE option chain split into puts / calls |
| GET | `/api/scanner/csp` | Cash-Secured Put scan (params: dte, delta, yield, OI) |
| GET | `/api/scanner/cc` | Covered Call scan (same params) |
| WS  | `/ws/quotes` | Snapshot + 1 s diff stream of all watchlist quotes |

## Quick start

```bash
cd backend/ibkr

# First time: create venv and install deps
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Copy env (edit TWS_PORT=7497 for paper trading)
cp .env.example .env

# Start server
uvicorn main:app --host 0.0.0.0 --port 8002 --reload
```

TWS must be running with socket API enabled on port 7496 (live) or 7497 (paper).  
Without TWS, prices fall back to CBOE 15-min delayed data automatically.

## Watchlist universe

107 symbols: full Nasdaq-100 + `SOXL`, `TQQQ`, `UPRO`.

## File layout

```
backend/ibkr/
├── main.py                  FastAPI app, endpoints, background loops
├── config.py                Pydantic settings (reads .env)
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
