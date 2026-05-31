"""Wheel Strategy Scanner — FastAPI backend.

Endpoints:
  GET  /api/status          → IBKR connection status + data source
  GET  /api/watchlist       → all watchlist stocks with quotes + metrics
  GET  /api/options/{sym}   → CBOE option chain for a symbol
  GET  /api/scanner/csp     → Cash-Secured Put scan results
  GET  /api/scanner/cc      → Covered Call scan results
  WS   /ws/quotes           → streaming quote updates (JSON lines)

Data source priority:
  1. IBKR live BBO (when TWS/Gateway is running)
  2. CBOE current_price field from delayed option chain (fallback)

Metrics pipeline (background):
  - 30Δ CSP% / 30Δ CC%  : computed from CBOE chain after pre-fill
  - RSI(14) / BB%(20)   : computed from IBKR 30-day daily bars
  - Signals (CSP/CC/LEAP): derived from the above thresholds
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any

from fastapi import FastAPI, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

import services.ibkr_service as ibkr
import services.analytics_service as analytics
from data.tickers import ALL_TICKERS
from services.cboe_service import (
    get_option_chain, _is_cached_today,
    find_30delta_metrics, get_atm_iv,
)
from services.scanner_service import run_csp_scan, run_cc_scan
from services.breakout_router import router as breakout_router

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

app = FastAPI(title="Wheel Strategy Scanner", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(breakout_router)

_ws_clients: list[WebSocket] = []

# Price fallback (CBOE delayed, when IBKR is offline)
_cboe_price_cache: dict[str, float] = {}

# Metrics cache: sym → {csp_30d, cc_30d, iv_rank, rsi, bb_pct, signals}
_metrics_cache: dict[str, dict] = {}

IBKR_RETRY_INTERVAL = 30   # seconds between reconnect attempts

# Track the analytics task to prevent duplicate concurrent refresh loops
_analytics_task: asyncio.Task | None = None


def _start_analytics_task() -> None:
    """Create a new analytics refresh task only if none is currently running.

    Prevents stacking multiple loops when IBKR reconnects repeatedly.
    """
    global _analytics_task
    if _analytics_task is not None and not _analytics_task.done():
        log.info("Analytics task already running — skipping duplicate creation")
        return
    _analytics_task = asyncio.create_task(_analytics_refresh_loop())
    log.info("Analytics refresh task started")


# ─────────────────────────────────────────────────────────────
# Lifecycle
# ─────────────────────────────────────────────────────────────

@app.on_event("startup")
async def startup():
    connected = await ibkr.connect()
    if connected:
        log.info("IBKR streaming started")
        _start_analytics_task()
    else:
        log.warning(
            "IBKR TWS not reachable on port 7496 — is TWS running with API connections enabled? "
            "Will retry every %ds. Stock prices will use CBOE fallback.",
            IBKR_RETRY_INTERVAL,
        )
    asyncio.create_task(_ibkr_reconnect_loop())
    asyncio.create_task(_cboe_metrics_loop())
    asyncio.create_task(_broadcast_loop())


@app.on_event("shutdown")
async def shutdown():
    await ibkr.disconnect()


# ─────────────────────────────────────────────────────────────
# Background tasks
# ─────────────────────────────────────────────────────────────

async def _ibkr_reconnect_loop():
    """Retry IBKR connection every IBKR_RETRY_INTERVAL s when disconnected."""
    while True:
        await asyncio.sleep(IBKR_RETRY_INTERVAL)
        if not ibkr.is_connected():
            log.info("IBKR reconnect attempt…")
            connected = await ibkr.connect()
            if connected:
                log.info("IBKR reconnected successfully")
                _start_analytics_task()   # guarded — won't duplicate if already running
            else:
                log.debug("IBKR still unavailable, will retry in %ds", IBKR_RETRY_INTERVAL)


async def _cboe_metrics_loop():
    """Pre-warm CBOE daily cache, then compute 30Δ metrics + signals for all symbols.

    Runs immediately at startup (hits disk cache if warm), then every 6 hours
    to refresh after midnight or if IBKR was offline during the initial fill.
    """
    while True:
        # ── 1. Pre-fill CBOE chain cache ──────────────────────────────────
        missing = [s for s in ALL_TICKERS if not _is_cached_today(s)]
        if missing:
            log.info(
                "CBOE pre-fill: %d symbols need fetching (%d already cached today)",
                len(missing), len(ALL_TICKERS) - len(missing),
            )
            for sym in missing:
                try:
                    chain = await get_option_chain(sym)
                    if chain:
                        price = chain[0].get("stock_price")
                        if price:
                            _cboe_price_cache[sym] = price
                except Exception:
                    pass
            log.info("CBOE pre-fill complete")
        else:
            log.info("CBOE daily cache warm — all %d symbols cached", len(ALL_TICKERS))

        # Populate price fallback from in-memory cache (includes disk-loaded entries)
        from services.cboe_service import _cache as _cboe_cache
        for sym in ALL_TICKERS:
            entry = _cboe_cache.get(sym)
            if entry and entry[1]:
                price = entry[1][0].get("stock_price")
                if price:
                    _cboe_price_cache[sym] = price

        # ── 2. Compute 30Δ metrics + signals from chain data ──────────────
        _recompute_metrics()

        await asyncio.sleep(6 * 3600)


def _seconds_until_market_close_refresh() -> float:
    """Seconds until 4:30 PM ET (30 min after NYSE close).

    If it is already past 4:30 PM ET today, returns seconds until 4:30 PM ET tomorrow.
    This ensures OHLCV data is always refreshed with the latest closing prices.
    """
    et = ZoneInfo("America/New_York")
    now = datetime.now(et)
    target = now.replace(hour=16, minute=30, second=0, microsecond=0)
    if now >= target:
        target += timedelta(days=1)
    secs = (target - now).total_seconds()
    log.info(
        "Analytics: next market-close refresh in %.0f min (at 4:30 PM ET %s)",
        secs / 60,
        target.strftime("%Y-%m-%d"),
    )
    return secs


async def _analytics_refresh_loop():
    """Fetch 1-year daily OHLCV bars from IBKR, compute all analytics, and persist to disk.

    Schedule:
      - Runs immediately when IBKR connects (populates OHLCV cache + indicators)
      - Then runs daily at 4:30 PM ET (30 min after NYSE close) to pick up latest closes
    """
    while ibkr.is_connected():
        log.info("Analytics refresh: fetching IBKR historical bars…")
        await analytics.refresh(ibkr.get_ib(), ibkr.get_contracts())
        _recompute_metrics()
        # Sleep until 4:30 PM ET (handles both "before close" and "after close" cases)
        await asyncio.sleep(_seconds_until_market_close_refresh())


def _recompute_metrics() -> None:
    """Merge 30Δ yields + RSI/BB%% + Stage → _metrics_cache and derive signals."""
    anal = analytics.get_all_analytics()
    for sym in ALL_TICKERS:
        m30    = find_30delta_metrics(sym)
        iv     = get_atm_iv(sym)
        a      = anal.get(sym, {})
        rsi    = a.get("rsi")
        bb_pct = a.get("bb_pct")

        csp_30d = m30.get("csp_30d")
        cc_30d  = m30.get("cc_30d")

        signals: list[str] = []
        if csp_30d is not None and csp_30d > 5:
            signals.append("CSP")
        if cc_30d is not None and cc_30d > 5:
            signals.append("CC")
        # LEAP: technically oversold, near lower Bollinger Band, no earnings (earnings TBD)
        if rsi is not None and bb_pct is not None and rsi <= 40 and bb_pct <= 20:
            signals.append("LEAP")

        _metrics_cache[sym] = {
            "csp_30d":  csp_30d,
            "cc_30d":   cc_30d,
            "iv_rank":  iv,
            "rsi":      rsi,
            "bb_pct":   bb_pct,
            "signals":  signals,
        }


async def _broadcast_loop():
    """Push quote updates to all connected WebSocket clients every second."""
    last_sent: dict[str, Any] = {}
    while True:
        await asyncio.sleep(1)
        quotes = _build_watchlist_rows()
        changed = {sym: q for sym, q in quotes.items() if last_sent.get(sym) != q}
        if changed and _ws_clients:
            msg = json.dumps({"type": "update", "data": changed})
            dead: list[WebSocket] = []
            for ws in _ws_clients:
                try:
                    await ws.send_text(msg)
                except Exception:
                    dead.append(ws)
            for ws in dead:
                _ws_clients.remove(ws)
        last_sent.update(changed)


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _build_watchlist_rows() -> dict[str, dict]:
    """Merge IBKR quotes + CBOE fallback + metrics into one dict per symbol."""
    ibkr_quotes = ibkr.get_all_quotes()
    rows: dict[str, dict] = {}
    for sym in ALL_TICKERS:
        q = ibkr_quotes.get(sym)
        if q and q.get("price") is not None:
            row = dict(q)
        else:
            fallback_price = _cboe_price_cache.get(sym)
            row = {
                "symbol":     sym,
                "price":      fallback_price,
                "bid":        None,
                "ask":        None,
                "last":       fallback_price,
                "close":      None,
                "change":     None,
                "change_pct": None,
                "volume":     None,
                "source":     "cboe" if fallback_price else "none",
            }

        # Merge metrics (30Δ yields, RSI, BB%, IV, signals)
        m = _metrics_cache.get(sym, {})
        row["csp_30d"]  = m.get("csp_30d")
        row["cc_30d"]   = m.get("cc_30d")
        row["iv_rank"]  = m.get("iv_rank")
        row["rsi"]      = m.get("rsi")
        row["bb_pct"]   = m.get("bb_pct")
        row["signals"]  = m.get("signals", [])

        # Stage Analysis (Weinstein) — from analytics cache
        from services.analytics_service import get_analytics as _get_anal
        anal = _get_anal(sym)
        row["stage"]           = anal.get("stage")           # 1/2/3/4 or None
        row["sata_score"]      = anal.get("sata_score")      # 0–10
        row["mansfield_rs"]    = anal.get("mansfield_rs")    # float or None
        row["ma150"]           = anal.get("ma150")           # 150-day SMA value
        row["ma200"]           = anal.get("ma200")           # 200-day SMA value
        row["sata_attributes"] = anal.get("sata_attributes", {})

        rows[sym] = row
    return rows


# ─────────────────────────────────────────────────────────────
# REST endpoints
# ─────────────────────────────────────────────────────────────

@app.get("/api/status")
def get_status():
    ibkr_on = ibkr.is_connected()
    cboe_prices = len(_cboe_price_cache)
    return {
        "ibkr_connected": ibkr_on,
        "watchlist_count": len(ALL_TICKERS),
        "quotes_cached": len(ibkr.get_all_quotes()),
        "cboe_prices_cached": cboe_prices,
        "price_source": "ibkr" if ibkr_on else ("cboe_delayed" if cboe_prices else "none"),
        "metrics_computed": len(_metrics_cache),
    }


@app.get("/api/watchlist")
def get_watchlist():
    rows = list(_build_watchlist_rows().values())
    return {"tickers": rows, "count": len(rows)}


@app.get("/api/quotes")
async def get_custom_quotes(symbols: str = Query(..., description="Comma-separated ticker symbols")):
    """Return quote + metrics data for arbitrary tickers (up to 20).

    Symbols already in the default watchlist return their full live data.
    New symbols are fetched on-demand from CBOE (daily cached after first call).
    """
    raw  = [s.strip().upper() for s in symbols.split(',') if s.strip()]
    syms = list(dict.fromkeys(raw))[:20]   # deduplicate, cap at 20

    existing = _build_watchlist_rows()
    results: list[dict] = []

    for sym in syms:
        if sym in existing:
            results.append(existing[sym])
            continue

        # New symbol — fetch from CBOE and compute metrics
        chain = await get_option_chain(sym)
        price = chain[0].get("stock_price") if chain else None
        m30   = find_30delta_metrics(sym)
        iv    = get_atm_iv(sym)

        csp, cc = m30.get("csp_30d"), m30.get("cc_30d")
        signals: list[str] = []
        if csp and csp > 5: signals.append("CSP")
        if cc  and cc  > 5: signals.append("CC")

        results.append({
            "symbol":     sym,
            "price":      price,
            "bid":        None, "ask":  None,
            "last":       price, "close": None,
            "change":     None, "change_pct": None,
            "volume":     None, "iv_rank":    iv,
            "hv30":       None, "rsi":        None,
            "bb_pct":     None, "csp_30d":    csp,
            "cc_30d":     cc,   "signals":    signals,
            "source":     "cboe" if price else "none",
        })

    return {"tickers": results, "count": len(results)}


@app.get("/api/options/{symbol}")
async def get_options(symbol: str):
    chain = await get_option_chain(symbol.upper())
    puts  = [o for o in chain if o["option_type"] == "P"]
    calls = [o for o in chain if o["option_type"] == "C"]
    return {"symbol": symbol.upper(), "puts": puts, "calls": calls, "total": len(chain)}


@app.get("/api/scanner/csp")
async def scanner_csp(
    dte_min: int         = Query(7),
    dte_max: int         = Query(60),
    delta_min: float     = Query(0.10),
    delta_max: float     = Query(0.40),
    min_ann_yield: float = Query(10.0),
    min_oi: int          = Query(50),
    limit: int           = Query(200),
):
    filters = {
        "dte_min": dte_min, "dte_max": dte_max,
        "delta_min": delta_min, "delta_max": delta_max,
        "min_yield": 0.1, "min_ann_yield": min_ann_yield,
        "min_oi": min_oi, "min_volume": 0,
        "min_bid": 0.05, "exclude_earnings_days": 7,
    }
    results = await run_csp_scan(filters=filters)
    return {"results": results[:limit], "total": len(results)}


@app.get("/api/scanner/cc")
async def scanner_cc(
    dte_min: int         = Query(7),
    dte_max: int         = Query(60),
    delta_min: float     = Query(0.10),
    delta_max: float     = Query(0.40),
    min_ann_yield: float = Query(8.0),
    min_oi: int          = Query(50),
    limit: int           = Query(200),
):
    filters = {
        "dte_min": dte_min, "dte_max": dte_max,
        "delta_min": delta_min, "delta_max": delta_max,
        "min_yield": 0.1, "min_ann_yield": min_ann_yield,
        "min_oi": min_oi, "min_volume": 0, "min_bid": 0.05,
    }
    results = await run_cc_scan(filters=filters)
    return {"results": results[:limit], "total": len(results)}


# ─────────────────────────────────────────────────────────────
# WebSocket streaming
# ─────────────────────────────────────────────────────────────

@app.websocket("/ws/quotes")
async def ws_quotes(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.append(websocket)
    try:
        snapshot = _build_watchlist_rows()
        await websocket.send_text(json.dumps({"type": "snapshot", "data": snapshot}))
        while True:
            await asyncio.sleep(60)   # keep-alive ping
    except WebSocketDisconnect:
        pass
    finally:
        if websocket in _ws_clients:
            _ws_clients.remove(websocket)
