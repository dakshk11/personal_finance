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
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from ib_insync import Stock

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
_earnings_cache: dict[str, tuple[float, date | None]] = {}

IBKR_RETRY_INTERVAL = 30   # seconds between reconnect attempts

# Track the analytics task to prevent duplicate concurrent refresh loops
_analytics_task: asyncio.Task | None = None


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number == number else None


def _earnings_is_clear(earnings_date: Any | None, max_days: int) -> bool:
    """True when no known earnings date falls inside the exclusion window."""
    if earnings_date is None:
        return True
    if isinstance(earnings_date, datetime):
        event_date = earnings_date.date()
    elif hasattr(earnings_date, "date"):
        event_date = earnings_date.date()
    else:
        event_date = earnings_date
    try:
        days_until = (event_date - datetime.now().date()).days
    except TypeError:
        return True
    return days_until < 0 or days_until > max_days


def _coerce_earnings_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if hasattr(value, "date"):
        try:
            parsed = value.date()
            return parsed if isinstance(parsed, date) else None
        except Exception:
            return None
    if isinstance(value, (list, tuple)):
        for item in value:
            parsed = _coerce_earnings_date(item)
            if parsed is not None:
                return parsed
    return None


def _fetch_earnings_date(symbol: str) -> date | None:
    cached = _earnings_cache.get(symbol)
    if cached and time.time() - cached[0] < 6 * 3600:
        return cached[1]
    try:
        import yfinance as yf

        calendar = yf.Ticker(symbol.replace(".", "-")).get_calendar()
    except Exception:
        _earnings_cache[symbol] = (time.time(), None)
        return None

    earnings_date = None
    if isinstance(calendar, dict):
        for key in ("Earnings Date", "Earnings High", "Earnings Low"):
            parsed = _coerce_earnings_date(calendar.get(key))
            if parsed and parsed >= datetime.now().date():
                earnings_date = parsed
                break
    _earnings_cache[symbol] = (time.time(), earnings_date)
    return earnings_date


def _derive_wheel_signals(
    *,
    csp_30d: Any | None,
    cc_30d: Any | None,
    iv_rank: Any | None,
    rsi: Any | None,
    bb_pct: Any | None,
    earnings_date: Any | None = None,
) -> list[str]:
    """Apply the visible Wheel Scanner trigger rules."""
    csp = _number(csp_30d)
    cc = _number(cc_30d)
    iv = _number(iv_rank)
    rsi_value = _number(rsi)
    bb_value = _number(bb_pct)
    signals: list[str] = []

    no_earnings_7d = _earnings_is_clear(earnings_date, 7)
    no_earnings_30d = _earnings_is_clear(earnings_date, 30)

    if (
        csp is not None
        and csp > 5
        and rsi_value is not None
        and rsi_value <= 65
        and bb_value is not None
        and bb_value <= 75
        and iv is not None
        and iv > 40
        and no_earnings_7d
    ):
        signals.append("CSP")
    if (
        cc is not None
        and cc > 5
        and rsi_value is not None
        and rsi_value >= 40
        and bb_value is not None
        and bb_value >= 30
        and iv is not None
        and iv > 40
        and no_earnings_7d
    ):
        signals.append("CC")
    if (
        bb_value is not None
        and bb_value <= 20
        and rsi_value is not None
        and rsi_value <= 40
        and no_earnings_30d
    ):
        signals.append("LEAP")

    return signals


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
    asyncio.create_task(_deferred_background_task(_connect_ibkr_once("startup")))
    asyncio.create_task(_deferred_background_task(_ibkr_reconnect_loop()))
    asyncio.create_task(_deferred_background_task(_cboe_metrics_loop()))
    asyncio.create_task(_deferred_background_task(_broadcast_loop()))


@app.on_event("shutdown")
async def shutdown():
    await ibkr.disconnect()


# ─────────────────────────────────────────────────────────────
# Background tasks
# ─────────────────────────────────────────────────────────────

async def _deferred_background_task(coro):
    await asyncio.sleep(0.1)
    await coro


async def _connect_ibkr_once(reason: str) -> bool:
    connected = await ibkr.connect()
    if connected:
        log.info("IBKR streaming started (%s)", reason)
        _start_analytics_task()
        return True

    log.warning(
        "IBKR TWS not reachable on port 7496 during %s — will retry every %ds. "
        "Stock prices will use CBOE fallback until IBKR connects.",
        reason,
        IBKR_RETRY_INTERVAL,
    )
    return False


async def _ibkr_reconnect_loop():
    """Retry IBKR connection every IBKR_RETRY_INTERVAL s when disconnected."""
    while True:
        await asyncio.sleep(IBKR_RETRY_INTERVAL)
        if not ibkr.is_connected():
            log.info("IBKR reconnect attempt…")
            connected = await _connect_ibkr_once("reconnect")
            if not connected:
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
        earnings_date = _fetch_earnings_date(sym)

        signals = _derive_wheel_signals(
            csp_30d=csp_30d,
            cc_30d=cc_30d,
            iv_rank=iv,
            rsi=rsi,
            bb_pct=bb_pct,
            earnings_date=earnings_date,
        )

        _metrics_cache[sym] = {
            "csp_30d":  csp_30d,
            "cc_30d":   cc_30d,
            "iv_rank":  iv,
            "rsi":      rsi,
            "bb_pct":   bb_pct,
            "earnings_date": earnings_date.isoformat() if earnings_date else None,
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
        row["earnings_date"] = m.get("earnings_date")
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


def _pf(val) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        return None if f != f else f
    except (TypeError, ValueError):
        return None


def _pi(val) -> int | None:
    f = _pf(val)
    return int(f) if f is not None else None


def _display_volume(val: int | None) -> int | None:
    return val if val is not None and 0 <= val <= 1_000_000_000 else None


async def _build_custom_quote_row(symbol: str) -> dict:
    """Fetch one non-watchlist symbol from IBKR, then merge option metrics."""
    row: dict[str, Any] = {
        "symbol":     symbol,
        "price":      None,
        "bid":        None,
        "ask":        None,
        "last":       None,
        "close":      None,
        "change":     None,
        "change_pct": None,
        "volume":     None,
        "source":     "none",
    }

    if ibkr.is_connected():
        try:
            contract = Stock(symbol, "SMART", "USD")
            qualified = await ibkr.get_ib().qualifyContractsAsync(contract)
            if qualified and qualified[0].conId:
                contract = qualified[0]

                try:
                    tickers = await ibkr.get_ib().reqTickersAsync(contract, regulatorySnapshot=False)
                    ticker = tickers[0] if tickers else None
                    if ticker:
                        bid = _pf(ticker.bid)
                        ask = _pf(ticker.ask)
                        last = _pf(ticker.last)
                        close = _pf(ticker.close)
                        market_price = _pf(ticker.marketPrice()) if hasattr(ticker, "marketPrice") else None
                        price = ((bid + ask) / 2) if bid and ask else last or market_price or close
                        row.update({
                            "price":  price,
                            "bid":    bid,
                            "ask":    ask,
                            "last":   last,
                            "close":  close,
                            "volume": _display_volume(_pi(ticker.volume)),
                            "source": "ibkr" if price is not None else row["source"],
                        })
                except Exception as exc:
                    log.debug("IBKR snapshot %s: %s", symbol, exc)

                bars = await ibkr.get_ib().reqHistoricalDataAsync(
                    contract,
                    endDateTime="",
                    durationStr="1 Y",
                    barSizeSetting="1 day",
                    whatToShow="TRADES",
                    useRTH=True,
                )
                bars = [bar for bar in bars if _pf(bar.close) is not None]
                if bars:
                    closes = [float(bar.close) for bar in bars]
                    volumes = [float(bar.volume or 0) for bar in bars]
                    latest_close = closes[-1]
                    prior_close = closes[-2] if len(closes) >= 2 else row.get("close")
                    price = row.get("price") if row.get("price") is not None else latest_close
                    hist_volume = _display_volume(int(volumes[-1]))
                    row.update({
                        "price":  price,
                        "last":   row.get("last") if row.get("last") is not None else latest_close,
                        "close":  prior_close,
                        "volume": row.get("volume") if row.get("volume") is not None else hist_volume,
                        "source": "ibkr",
                    })
                    if price is not None and prior_close:
                        change = round(float(price) - float(prior_close), 2)
                        row["change"] = change
                        row["change_pct"] = round(change / float(prior_close) * 100, 2)

                    row.update(analytics.compute_from_bars(closes, volumes))
        except Exception as exc:
            log.debug("custom IBKR quote %s: %s", symbol, exc)

    chain = await get_option_chain(symbol)
    cboe_price = chain[0].get("stock_price") if chain else None
    if row.get("price") is None and cboe_price is not None:
        row.update({
            "price":  cboe_price,
            "last":   cboe_price,
            "source": "cboe",
        })

    m30 = find_30delta_metrics(symbol)
    iv = get_atm_iv(symbol)
    csp, cc = m30.get("csp_30d"), m30.get("cc_30d")
    earnings_date = _fetch_earnings_date(symbol)
    signals = _derive_wheel_signals(
        csp_30d=csp,
        cc_30d=cc,
        iv_rank=iv,
        rsi=row.get("rsi"),
        bb_pct=row.get("bb_pct"),
        earnings_date=earnings_date,
    )

    row.setdefault("rsi", None)
    row.setdefault("bb_pct", None)
    row.setdefault("stage", None)
    row.setdefault("sata_score", None)
    row.setdefault("mansfield_rs", None)
    row.setdefault("ma150", None)
    row.setdefault("ma200", None)
    row.setdefault("sata_attributes", {})
    row.update({
        "iv_rank": iv,
        "hv30": None,
        "csp_30d": csp,
        "cc_30d": cc,
        "earnings_date": earnings_date.isoformat() if earnings_date else None,
        "signals": signals,
    })
    return row


async def _fetch_ibkr_daily_bars(symbol: str) -> list[dict[str, Any]]:
    contract = Stock(symbol, "SMART", "USD")
    qualified = await ibkr.get_ib().qualifyContractsAsync(contract)
    if not qualified:
        raise RuntimeError("contract could not be qualified")

    bars = []
    for data_type in ("ADJUSTED_LAST", "TRADES"):
        bars = await ibkr.get_ib().reqHistoricalDataAsync(
            qualified[0],
            endDateTime="",
            durationStr="5 Y",
            barSizeSetting="1 day",
            whatToShow=data_type,
            useRTH=True,
        )
        if bars and len(bars) >= 260:
            break
    if not bars or len(bars) < 260:
        raise RuntimeError("insufficient IBKR historical bars")

    return [
        {
            "date": bar.date.date() if hasattr(bar.date, "date") else bar.date,
            "open": float(bar.open),
            "close": float(bar.close),
        }
        for bar in bars
        if bar.close and bar.close > 0
    ]


def _month_end_closes(daily_bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_month: dict[str, dict[str, Any]] = {}
    for bar in daily_bars:
        day = bar["date"]
        month_key = day.strftime("%Y-%m")
        by_month[month_key] = {
            "month": month_key,
            "date": day.isoformat(),
            "close": float(bar["close"]),
        }
    return [by_month[key] for key in sorted(by_month)]


def _rsi_monthly(closes: list[float], end: int, period: int = 6) -> float:
    gains = 0.0
    losses = 0.0
    for index in range(end - period + 1, end + 1):
        delta = closes[index] - closes[index - 1]
        if delta > 0:
            gains += delta
        else:
            losses -= delta
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - 100 / (1 + rs), 1)


def _latest_rsi_state(closes: list[float], latest_index: int) -> tuple[bool, float]:
    state = False
    latest_rsi = 0.0
    for index in range(6, latest_index + 1):
        latest_rsi = _rsi_monthly(closes, index)
        if latest_rsi > 52:
            state = True
        elif latest_rsi < 42:
            state = False
    return state, latest_rsi


def _composite_history_from_monthly(monthly: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(monthly) < 13:
        raise RuntimeError("needs at least 13 monthly closes")

    closes = [float(row["close"]) for row in monthly]
    history: list[dict[str, Any]] = []
    rsi_state = False

    for index in range(12, len(closes)):
        price = closes[index]
        sma10 = sum(closes[index - 9 : index + 1]) / 10
        sma_bullish = price >= sma10
        momentum_12m_pct = (price / closes[index - 12] - 1) * 100
        momentum_bullish = price > closes[index - 12]
        rsi6 = _rsi_monthly(closes, index)
        if rsi6 > 52:
            rsi_state = True
        elif rsi6 < 42:
            rsi_state = False
        score = int(sma_bullish) + int(momentum_bullish) + int(rsi_state)
        history.append({
            "date": monthly[index]["date"],
            "price": round(price, 2),
            "sma10": round(sma10, 2),
            "momentum_12m_pct": round(momentum_12m_pct, 2),
            "rsi6": rsi6,
            "score": score,
            "signal": "BUY" if score >= 2 else "SELL",
            "components": {
                "sma10": sma_bullish,
                "momentum12": momentum_bullish,
                "rsi6": rsi_state,
            },
        })

    return history


def _composite_signal_from_monthly(monthly: list[dict[str, Any]]) -> dict[str, Any]:
    history = _composite_history_from_monthly(monthly)
    latest = history[-1]

    return {
        "signal": latest["signal"],
        "score": latest["score"],
        "price": latest["price"],
        "as_of_date": latest["date"],
        "sma10": latest["sma10"],
        "momentum_12m_pct": latest["momentum_12m_pct"],
        "rsi6": latest["rsi6"],
        "components": latest["components"],
        "history": history[-36:],
    }


LEVERAGED_UNDERLYING_MAP = {
    "TQQQ": "QQQ",
    "SOXL": "SOXX",
    "UPRO": "SPY",
}
SP500_TOP_20_MARKET_CAP_SYMBOLS = [
    "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "AVGO", "GOOG", "META", "TSLA", "MU",
    "LLY", "BRK.B", "AMD", "JPM", "XOM", "JNJ", "V", "INTC", "WMT", "CSCO",
]
OPTITRADE_DIRECT_SYMBOLS = {symbol: symbol for symbol in SP500_TOP_20_MARKET_CAP_SYMBOLS}
OPTITRADE_UNDERLYING_MAP = {**LEVERAGED_UNDERLYING_MAP, **OPTITRADE_DIRECT_SYMBOLS}
DEFAULT_OPTITRADE_SYMBOLS = ["TQQQ", "SOXL", "UPRO", *SP500_TOP_20_MARKET_CAP_SYMBOLS]
MAX_OPTITRADE_SYMBOLS = len(DEFAULT_OPTITRADE_SYMBOLS)


async def _fetch_optitrade_daily_bars(symbol: str, duration: str = "2 Y") -> list[dict[str, Any]]:
    contract = Stock(symbol, "SMART", "USD")
    qualified = await ibkr.get_ib().qualifyContractsAsync(contract)
    if not qualified:
        raise RuntimeError("contract could not be qualified")

    bars = []
    for data_type in ("ADJUSTED_LAST", "TRADES"):
        bars = await ibkr.get_ib().reqHistoricalDataAsync(
            qualified[0],
            endDateTime="",
            durationStr=duration,
            barSizeSetting="1 day",
            whatToShow=data_type,
            useRTH=True,
        )
        if bars and len(bars) >= 120:
            break
    if not bars or len(bars) < 120:
        raise RuntimeError("insufficient IBKR historical bars")

    result = []
    for bar in bars:
        close = _pf(bar.close)
        high = _pf(bar.high)
        low = _pf(bar.low)
        open_price = _pf(bar.open)
        if close is None or high is None or low is None or open_price is None or close <= 0:
            continue
        result.append({
            "date": bar.date.date().isoformat() if hasattr(bar.date, "date") else str(bar.date),
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": float(bar.volume or 0),
        })
    if len(result) < 120:
        raise RuntimeError("insufficient clean IBKR historical bars")
    return result


def _ema(values: list[float], period: int) -> list[float | None]:
    if not values:
        return []
    alpha = 2 / (period + 1)
    result: list[float | None] = [None] * len(values)
    ema_value = values[0]
    for index, value in enumerate(values):
        ema_value = value if index == 0 else alpha * value + (1 - alpha) * ema_value
        if index >= period - 1:
            result[index] = ema_value
    return result


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _atr(bars: list[dict[str, Any]], period: int = 14) -> list[float | None]:
    true_ranges: list[float] = []
    for index, bar in enumerate(bars):
        if index == 0:
            true_ranges.append(float(bar["high"]) - float(bar["low"]))
        else:
            prev_close = float(bars[index - 1]["close"])
            true_ranges.append(max(
                float(bar["high"]) - float(bar["low"]),
                abs(float(bar["high"]) - prev_close),
                abs(float(bar["low"]) - prev_close),
            ))
    result: list[float | None] = [None] * len(bars)
    for index in range(period - 1, len(true_ranges)):
        result[index] = _avg(true_ranges[index - period + 1 : index + 1])
    return result


def _rsi_last(closes: list[float], period: int = 14) -> float:
    value = analytics.compute_from_bars(closes, [0 for _ in closes]).get("rsi")
    return float(value) if value is not None else 50.0


def _momentum_score(closes: list[float], volumes: list[float]) -> tuple[float, float, float]:
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd = ((ema12[-1] or closes[-1]) - (ema26[-1] or closes[-1])) / closes[-1] * 100
    rsi = _rsi_last(closes)
    slope20 = (closes[-1] / closes[-21] - 1) * 100 if len(closes) > 21 else 0.0
    score = 50 + (rsi - 50) * 0.55 + macd * 4 + slope20 * 1.2
    avg_volume = _avg(volumes[-21:-1]) if len(volumes) > 21 else _avg(volumes)
    volume_score = 50 if avg_volume <= 0 else max(0, min(100, volumes[-1] / avg_volume * 50))
    return round(max(0, min(100, score)), 1), round(max(0, min(100, volume_score)), 1), round(rsi, 1)


def _anti_chop_state(bars: list[dict[str, Any]], atr_value: float) -> tuple[str, bool]:
    closes = [float(bar["close"]) for bar in bars]
    latest_close = closes[-1]
    range_20 = (max(float(bar["high"]) for bar in bars[-20:]) - min(float(bar["low"]) for bar in bars[-20:])) / latest_close * 100
    atr_pct = atr_value / latest_close * 100 if latest_close else 0
    trending = range_20 >= 5.5 and atr_pct >= 1.1
    return ("Trending" if trending else "Chop filter active"), trending


def _trend_signal(bars: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [float(bar["close"]) for bar in bars]
    volumes = [float(bar["volume"]) for bar in bars]
    ema21 = _ema(closes, 21)
    ema55 = _ema(closes, 55)
    atr_values = _atr(bars)
    latest_close = closes[-1]
    latest_ema21 = ema21[-1] or latest_close
    latest_ema55 = ema55[-1] or latest_close
    atr_value = atr_values[-1] or max(latest_close * 0.025, 0.01)
    momentum, volume_score, rsi = _momentum_score(closes, volumes)
    chop_label, is_trending = _anti_chop_state(bars, atr_value)

    if latest_close > latest_ema21 > latest_ema55:
        trend_state = "BULLISH"
    elif latest_close < latest_ema21 < latest_ema55:
        trend_state = "BEARISH"
    else:
        trend_state = "NEUTRAL"

    if not is_trending:
        signal = "HOLD"
    elif trend_state == "BULLISH" and momentum >= 55:
        signal = "BUY"
    elif trend_state == "BEARISH" and momentum <= 45:
        signal = "SELL"
    else:
        signal = "HOLD"

    return {
        "signal": signal,
        "trend_state": trend_state,
        "anti_chop_state": chop_label,
        "anti_chop_pass": is_trending,
        "atr": round(atr_value, 2),
        "momentum_score": momentum,
        "volume_score": volume_score,
        "rsi": rsi,
        "ema21": latest_ema21,
        "ema55": latest_ema55,
        "ema21_series": ema21,
        "ema55_series": ema55,
    }


def _levels_for_signal(price: float, atr_value: float, signal: str, atr_multiplier: float = 2.5) -> dict[str, Any]:
    risk = max(atr_value * atr_multiplier, price * 0.03)
    direction = -1 if signal == "SELL" else 1
    stop = price - direction * risk
    take_profits = [price + direction * risk * multiple for multiple in (1, 2, 3, 4)]
    return {
        "entry": round(price, 2),
        "stop_loss": round(stop, 2),
        "take_profits": [round(value, 2) for value in take_profits],
        "risk_reward": round(abs((take_profits[1] - price) / (price - stop)), 2) if price != stop else None,
    }


def _optitrade_backtest(
    leveraged_bars: list[dict[str, Any]],
    underlying_bars: list[dict[str, Any]],
    atr_multiplier: float = 2.5,
    tp_mode: str = "multi",
    stop_model: str = "atr",
) -> dict[str, Any]:
    n = min(len(leveraged_bars), len(underlying_bars))
    leveraged = leveraged_bars[-n:]
    underlying = underlying_bars[-n:]
    atr_values = _atr(leveraged)
    trades: list[float] = []
    trade_rows: list[dict[str, Any]] = []
    equity = 1.0
    peak = 1.0
    max_drawdown = 0.0
    position_signal: str | None = None
    entry_price = 0.0
    entry_date = ""
    entry_index = 0
    stop_price = 0.0
    target_price = 0.0

    def _entry_levels(open_signal: str, open_index: int) -> tuple[float, float]:
        atr_value = float(atr_values[open_index] or 0)
        atr_risk = max(atr_value * atr_multiplier, entry_price * 0.03)
        if stop_model == "swing":
            recent = leveraged[max(0, open_index - 10): open_index + 1]
            if open_signal == "BUY":
                swing_stop = min(float(bar["low"]) for bar in recent)
                risk = entry_price - swing_stop
            else:
                swing_stop = max(float(bar["high"]) for bar in recent)
                risk = swing_stop - entry_price
            risk = risk if risk > 0 else atr_risk
        else:
            risk = atr_risk

        direction = -1 if open_signal == "SELL" else 1
        stop = entry_price - direction * risk
        target_multiple = 1 if tp_mode == "single" else 2
        target = entry_price + direction * risk * target_multiple
        return stop, target

    def _open_position(open_signal: str, open_index: int) -> None:
        nonlocal position_signal, entry_price, entry_date, entry_index, stop_price, target_price
        position_signal = open_signal
        entry_price = float(leveraged[open_index]["close"])
        entry_date = leveraged[open_index]["date"]
        entry_index = open_index
        stop_price, target_price = _entry_levels(open_signal, open_index)

    def _close_position(close_index: int, exit_price: float, reason: str) -> None:
        nonlocal equity, peak, max_drawdown, position_signal
        if not position_signal:
            return
        trade_return = (exit_price / entry_price - 1) if position_signal == "BUY" else (entry_price / exit_price - 1)
        trades.append(trade_return)
        equity *= 1 + trade_return
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - 1)
        trade_rows.append({
            "direction": position_signal,
            "entry_date": entry_date,
            "exit_date": leveraged[close_index]["date"],
            "entry_price": round(entry_price, 2),
            "exit_price": round(exit_price, 2),
            "return_pct": round(trade_return * 100, 2),
            "exit_reason": reason,
            "bars_held": max(0, close_index - entry_index),
        })
        position_signal = None

    for index in range(80, n):
        signal = _trend_signal(underlying[: index + 1])["signal"]
        price = float(leveraged[index]["close"])
        high = float(leveraged[index]["high"])
        low = float(leveraged[index]["low"])

        if position_signal:
            stop_label = "Swing stop" if stop_model == "swing" else "ATR stop"
            target_label = "TP1 single target" if tp_mode == "single" else "TP2 multi target"
            if position_signal == "BUY":
                if low <= stop_price:
                    _close_position(index, stop_price, stop_label)
                elif tp_mode in ("single", "multi") and high >= target_price:
                    _close_position(index, target_price, target_label)
            elif position_signal == "SELL":
                if high >= stop_price:
                    _close_position(index, stop_price, stop_label)
                elif tp_mode in ("single", "multi") and low <= target_price:
                    _close_position(index, target_price, target_label)

        if signal in ("BUY", "SELL") and position_signal is None:
            _open_position(signal, index)
            continue
        if position_signal and signal in ("BUY", "SELL") and signal != position_signal:
            _close_position(index, price, f"Flipped to {signal}")
            _open_position(signal, index)

    if position_signal:
        price = float(leveraged[-1]["close"])
        _close_position(n - 1, price, "Open to latest close")

    wins = [trade for trade in trades if trade > 0]
    losses = [trade for trade in trades if trade <= 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "period": "2Y daily",
        "settings": {
            "atr_multiplier": round(atr_multiplier, 2),
            "tp_mode": tp_mode,
            "stop_model": stop_model,
        },
        "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss else round(gross_profit, 2),
        "max_drawdown": round(max_drawdown * 100, 1),
        "total_trades": len(trades),
        "avg_trade": round(_avg(trades) * 100, 2) if trades else 0,
        "trades": trade_rows[-25:],
    }


def _optitrade_chart(leveraged_bars: list[dict[str, Any]], trend: dict[str, Any], levels: dict[str, Any]) -> list[dict[str, Any]]:
    closes = [float(bar["close"]) for bar in leveraged_bars]
    ema21 = _ema(closes, 21)
    ema55 = _ema(closes, 55)
    chart = []
    for index, bar in enumerate(leveraged_bars[-120:]):
        source_index = len(leveraged_bars) - 120 + index
        point = {
            "date": bar["date"],
            "close": round(float(bar["close"]), 2),
            "ema21": round(ema21[source_index], 2) if ema21[source_index] is not None else None,
            "ema55": round(ema55[source_index], 2) if ema55[source_index] is not None else None,
            "entry": levels["entry"],
            "stop_loss": levels["stop_loss"],
            "tp1": levels["take_profits"][0],
            "tp2": levels["take_profits"][1],
            "tp3": levels["take_profits"][2],
            "tp4": levels["take_profits"][3],
        }
        if index == 119 and trend["signal"] in ("BUY", "SELL"):
            point["marker"] = trend["signal"]
        chart.append(point)
    return chart


async def _build_optitrade_signal(symbol: str) -> dict[str, Any]:
    underlying = OPTITRADE_UNDERLYING_MAP.get(symbol)
    if not underlying:
        raise RuntimeError(f"{symbol} is not in the OptiTrade monitored universe")
    leveraged_bars, underlying_bars = await asyncio.gather(
        _fetch_optitrade_daily_bars(symbol),
        _fetch_optitrade_daily_bars(underlying),
    )
    trend = _trend_signal(underlying_bars)
    price = float(leveraged_bars[-1]["close"])
    leveraged_atr = _atr(leveraged_bars)[-1] or max(price * 0.025, 0.01)
    levels = _levels_for_signal(price, float(leveraged_atr), trend["signal"])

    return {
        "symbol": symbol,
        "underlying": underlying,
        "as_of_date": leveraged_bars[-1]["date"],
        "price": round(price, 2),
        "signal": trend["signal"],
        "trend_state": trend["trend_state"],
        "anti_chop_state": trend["anti_chop_state"],
        "anti_chop_pass": trend["anti_chop_pass"],
        "entry": levels["entry"],
        "stop_loss": levels["stop_loss"],
        "take_profits": levels["take_profits"],
        "risk_reward": levels["risk_reward"],
        "atr": trend["atr"],
        "momentum_score": trend["momentum_score"],
        "volume_score": trend["volume_score"],
        "rsi": trend["rsi"],
        "chart": _optitrade_chart(leveraged_bars, trend, levels),
        "backtest": _optitrade_backtest(leveraged_bars, underlying_bars),
    }


# ─────────────────────────────────────────────────────────────
# REST endpoints
# ─────────────────────────────────────────────────────────────

@app.get("/api/status")
def get_status():
    ibkr_on = ibkr.is_connected()
    ibkr_quote_count = len(ibkr.get_all_quotes())
    cboe_prices = len(_cboe_price_cache)
    return {
        "ibkr_connected": ibkr_on,
        "watchlist_count": len(ALL_TICKERS),
        "quotes_cached": ibkr_quote_count,
        "cboe_prices_cached": cboe_prices,
        "price_source": "ibkr_delayed" if ibkr_quote_count else ("cboe_delayed" if cboe_prices else "none"),
        "metrics_computed": len(_metrics_cache),
    }


@app.get("/api/watchlist")
async def get_watchlist(force_live: bool = Query(False, description="Force an immediate IBKR quote snapshot before returning rows.")):
    if force_live and ibkr.is_connected():
        await ibkr.refresh_quotes()
    rows = list(_build_watchlist_rows().values())
    return {"tickers": rows, "count": len(rows)}


@app.get("/api/composite-signal")
async def get_composite_signal():
    """Monthly composite trend signal for SOXL, TQQQ, and UPRO.

    The signal is computed on the underlying ETF proxy:
    SOXL→SOXX, TQQQ→QQQ, UPRO→SPY.
    """
    if not ibkr.is_connected():
        raise HTTPException(status_code=503, detail="IBKR is not connected.")

    pairs = [
        ("SOXL", "SOXX"),
        ("TQQQ", "QQQ"),
        ("UPRO", "SPY"),
    ]
    results = []
    warnings: list[str] = []

    for leveraged_symbol, underlying_symbol in pairs:
        try:
            daily_bars = await _fetch_ibkr_daily_bars(underlying_symbol)
            monthly = _month_end_closes(daily_bars)
            signal = _composite_signal_from_monthly(monthly)
            results.append({
                "symbol": leveraged_symbol,
                "underlying": underlying_symbol,
                "signal": signal["signal"],
                "score": signal["score"],
                "price": signal["price"],
                "as_of_date": signal["as_of_date"],
                "sma10": signal["sma10"],
                "momentum_12m_pct": signal["momentum_12m_pct"],
                "rsi6": signal["rsi6"],
                "components": signal["components"],
                "history": signal["history"],
                "month_count": len(monthly),
                "execution_note": "Evaluate at month-end close; execute at the following month's opening price.",
            })
        except Exception as exc:
            warnings.append(f"{leveraged_symbol}/{underlying_symbol}: {exc}")

    if not results:
        raise HTTPException(status_code=503, detail="No composite signal data could be loaded from IBKR.")

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "data_source": "IBKR historical daily bars rolled to month-end closes",
        "signals": results,
        "warnings": warnings,
    }


@app.get("/api/optitrade-lab/signals")
async def get_optitrade_lab_signals(symbols: str = Query(",".join(DEFAULT_OPTITRADE_SYMBOLS), description="Comma-separated OptiTrade symbols")):
    """OptiTrade-inspired signal package for leveraged ETFs.

    This is an original educational approximation using IBKR bars; it does not
    reproduce proprietary TradingView/Pine Script logic.
    """
    if not ibkr.is_connected():
        raise HTTPException(status_code=503, detail="IBKR is not connected.")

    requested = [item.strip().upper() for item in symbols.split(",") if item.strip()]
    universe = [symbol for symbol in list(dict.fromkeys(requested))[:MAX_OPTITRADE_SYMBOLS] if symbol in OPTITRADE_UNDERLYING_MAP] or DEFAULT_OPTITRADE_SYMBOLS
    results = []
    warnings: list[str] = []

    for symbol in universe:
        try:
            results.append(await _build_optitrade_signal(symbol))
        except Exception as exc:
            warnings.append(f"{symbol}: {exc}")

    if not results:
        raise HTTPException(status_code=503, detail="No OptiTrade Lab signal data could be loaded from IBKR.")

    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "data_source": "IBKR historical daily bars; original FinanceOS signal approximation",
        "signals": results,
        "warnings": warnings,
    }


@app.get("/api/optitrade-lab/backtest")
async def get_optitrade_lab_backtest(
    symbol: str = Query("TQQQ", description="Leveraged ETF symbol"),
    atr_multiplier: float = Query(2.5, ge=0.1, le=20),
    tp_mode: str = Query("multi", description="single, multi, or always_in"),
    stop_model: str = Query("atr", description="atr or swing"),
):
    """Settings-aware OptiTrade Lab backtest for one leveraged ETF."""
    if not ibkr.is_connected():
        raise HTTPException(status_code=503, detail="IBKR is not connected.")

    symbol = symbol.strip().upper()
    underlying = OPTITRADE_UNDERLYING_MAP.get(symbol)
    if not underlying:
        raise HTTPException(status_code=400, detail=f"{symbol} is not in the OptiTrade monitored universe.")

    if tp_mode not in {"single", "multi", "always_in"}:
        raise HTTPException(status_code=400, detail="tp_mode must be single, multi, or always_in.")
    if stop_model not in {"atr", "swing"}:
        raise HTTPException(status_code=400, detail="stop_model must be atr or swing.")

    leveraged_bars, underlying_bars = await asyncio.gather(
        _fetch_optitrade_daily_bars(symbol),
        _fetch_optitrade_daily_bars(underlying),
    )
    return {
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "data_source": "IBKR historical daily bars; settings-aware FinanceOS backtest",
        "symbol": symbol,
        "underlying": underlying,
        "backtest": _optitrade_backtest(
            leveraged_bars,
            underlying_bars,
            atr_multiplier=atr_multiplier,
            tp_mode=tp_mode,
            stop_model=stop_model,
        ),
    }


@app.get("/api/quotes")
async def get_custom_quotes(
    symbols: str = Query(..., description="Comma-separated ticker symbols"),
    force_live: bool = Query(False, description="Force an immediate IBKR quote snapshot before returning rows."),
):
    """Return quote + metrics data for arbitrary tickers (up to 20).

    Symbols already in the default watchlist return their full live data.
    New symbols are fetched on-demand from IBKR, with CBOE option metrics merged in.
    """
    raw  = [s.strip().upper() for s in symbols.split(',') if s.strip()]
    syms = list(dict.fromkeys(raw))[:20]   # deduplicate, cap at 20

    if force_live and ibkr.is_connected():
        await ibkr.refresh_quotes(syms)

    existing = _build_watchlist_rows()
    results: list[dict] = []

    for sym in syms:
        if sym in existing and not (force_live and existing[sym].get("source") != "ibkr"):
            results.append(existing[sym])
            continue

        results.append(await _build_custom_quote_row(sym))

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
