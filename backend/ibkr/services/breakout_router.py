"""
Breakout scanner endpoints for the IBKR backend (port 8002).

GET /api/breakout/status  — cache freshness + IBKR connection state
GET /api/breakout/scan    — run breakout scan, return JSON

Data source priority per symbol:
  1. backend/ibkr/data/history/{sym}.pkl  (written by analytics_service during daily refresh)
  2. Live IBKR fetch via ib_insync        (if connected and pkl missing/stale)
  3. yfinance                             (source=yf, or explicit fallback for extras)
"""

from __future__ import annotations

import asyncio
import logging
import math
from datetime import date as _date, datetime as _datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, Query
from ib_insync import Stock

import services.ibkr_service as ibkr_svc
from data.tickers import ALL_TICKERS, SP500
from services.breakout_service import analyze
from services.breakout_indicators import sma as _sma

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/breakout", tags=["breakout"])

OHLCV_CACHE_DIR = Path(__file__).parent.parent / "data" / "history"
INTRADAY_30M_CACHE_DIR = Path(__file__).parent.parent / "data" / "history_30m"
CHART_BARS = 130
MAX_IBKR_HISTORICAL_FETCHES_PER_SCAN = 45


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_fresh(path: Path) -> bool:
    if not path.exists():
        return False
    return _datetime.fromtimestamp(path.stat().st_mtime).date() == _date.today()


def _clean(obj):
    """Recursively convert numpy types and NaN → JSON-safe values."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_clean(v) for v in obj]
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return None if np.isnan(obj) else float(obj)
    if isinstance(obj, np.bool_):
        return bool(obj)
    if isinstance(obj, float) and math.isnan(obj):
        return None
    return obj


def _cache_dir(interval: str) -> Path:
    return INTRADAY_30M_CACHE_DIR if interval == "30m" else OHLCV_CACHE_DIR


def _load_pkl(sym: str, interval: str = "1d") -> Optional[pd.DataFrame]:
    path = _cache_dir(interval) / f"{sym}.pkl"
    if not path.exists():
        return None
    try:
        df = pd.read_pickle(path)
        if isinstance(df, pd.DataFrame) and len(df) >= 100:
            return df
    except Exception:
        pass
    return None


async def _fetch_from_ibkr(sym: str, interval: str = "1d") -> Optional[pd.DataFrame]:
    """Fetch daily or 30-minute OHLCV for a single symbol from the live IBKR connection."""
    if not ibkr_svc.is_connected():
        return None
    contracts = ibkr_svc.get_contracts()
    contract = contracts.get(sym)
    ib = ibkr_svc.get_ib()
    try:
        if contract is None:
            qualified = await ib.qualifyContractsAsync(Stock(sym, "SMART", "USD"))
            if not qualified:
                return None
            contract = qualified[0]

        bar_size = "30 mins" if interval == "30m" else "1 day"
        duration = "30 D" if interval == "30m" else "1 Y"
        bars = await ib.reqHistoricalDataAsync(
            contract,
            endDateTime="",
            durationStr=duration,
            barSizeSetting=bar_size,
            whatToShow="TRADES",
            useRTH=True,
        )
        if not bars or len(bars) < 100:
            return None
        df = pd.DataFrame(
            {
                "Open":   [bar.open   for bar in bars],
                "High":   [bar.high   for bar in bars],
                "Low":    [bar.low    for bar in bars],
                "Close":  [bar.close  for bar in bars],
                "Volume": [float(bar.volume) for bar in bars],
            },
            index=pd.DatetimeIndex(
                [pd.Timestamp(bar.date) for bar in bars], name="Date"
            ),
        )
        # Persist for future calls
        cache_dir = _cache_dir(interval)
        cache_dir.mkdir(parents=True, exist_ok=True)
        df.to_pickle(cache_dir / f"{sym}.pkl")
        return df
    except Exception as exc:
        log.debug("IBKR fetch %s: %s", sym, exc)
        return None


def _safe_float(val) -> Optional[float]:
    try:
        f = float(val)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _format_index(idx) -> str:
    if not hasattr(idx, "strftime"):
        return str(idx)
    if getattr(idx, "hour", 0) or getattr(idx, "minute", 0):
        return idx.strftime("%Y-%m-%d %H:%M")
    return idx.strftime("%Y-%m-%d")


def _chart_frame(df: pd.DataFrame, chart_interval: str) -> pd.DataFrame:
    if chart_interval != "1h":
        return df
    if not isinstance(df.index, pd.DatetimeIndex):
        return df
    hourly = df.resample("1h").agg({
        "Open": "first",
        "High": "max",
        "Low": "min",
        "Close": "last",
        "Volume": "sum",
    })
    return hourly.dropna(subset=["Open", "High", "Low", "Close"])


def _build_chart(df: pd.DataFrame, chart_interval: str = "1d") -> list[dict]:
    """Return last CHART_BARS rows as BreakoutChartPoint list."""
    chart_df = _chart_frame(df, chart_interval)
    tail   = chart_df.tail(CHART_BARS)
    sma20  = _sma(chart_df["Close"], 20).tail(CHART_BARS).values
    sma50  = _sma(chart_df["Close"], 50).tail(CHART_BARS).values
    sma200 = _sma(chart_df["Close"], 200).tail(CHART_BARS).values

    points = []
    for i, (idx, row) in enumerate(tail.iterrows()):
        points.append({
            "date":   _format_index(idx),
            "open":   _safe_float(row["Open"]),
            "high":   _safe_float(row["High"]),
            "low":    _safe_float(row["Low"]),
            "close":  _safe_float(row["Close"]),
            "volume": int(row["Volume"]) if not math.isnan(float(row["Volume"])) else 0,
            "sma20":  _safe_float(sma20[i]),
            "sma50":  _safe_float(sma50[i]),
            "sma200": _safe_float(sma200[i]),
        })
    return points


def _signal_to_api(sig: dict, df: pd.DataFrame, rank: int, chart_interval: str = "1d") -> dict:
    """Convert breakout_service.analyze() output → BreakoutSignal-compatible dict."""
    detector_type = sig.get("type", "").lower()  # e.g. "momentum_breakout"
    close    = sig.get("close", 0.0)
    res_lvl  = sig.get("breakout_level")
    above200 = sig.get("above_200sma", False)
    rsi_val  = sig.get("rsi")
    rvol     = sig.get("rel_vol")
    tests    = sig.get("tests") or 0

    breakout_pct  = ((close - res_lvl) / res_lvl) if (res_lvl and close > res_lvl) else None
    proximity_pct = ((res_lvl - close) / close)   if (res_lvl and close <= res_lvl) else None

    vol_series  = df["Volume"].tail(50)
    avg_vol_50d = float(vol_series.mean()) if len(vol_series) >= 20 else None

    n = len(df)
    s20_val  = _safe_float(_sma(df["Close"], 20).iloc[-1])  if n >= 20  else None
    s50_val  = _safe_float(_sma(df["Close"], 50).iloc[-1])  if n >= 50  else None
    s200_val = _safe_float(_sma(df["Close"], 200).iloc[-1]) if n >= 200 else None

    as_of_date = _format_index(df.index[-1])
    trend_label = "Above 200 SMA" if above200 else "Below 200 SMA"
    rsi_str = f"RSI {rsi_val:.0f}" if rsi_val is not None else ""
    summary = f"{sig.get('level_label', '')}. {rsi_str}. {'Trend up.' if above200 else 'Below trend.'}".strip()

    return {
        "symbol":           sig["ticker"],
        "company_name":     sig["ticker"],
        "sector":           "",
        "detector_type":    detector_type,
        "setup_label":      sig.get("level_label", ""),
        "score":            float(sig.get("score", 0)),
        "rank":             rank,
        "price":            round(close, 4) if close else None,
        "as_of_date":       as_of_date,
        "resistance_level": round(res_lvl, 4) if res_lvl is not None else None,
        "breakout_pct":     round(breakout_pct, 6) if breakout_pct is not None else None,
        "proximity_pct":    round(proximity_pct, 6) if proximity_pct is not None else None,
        "touch_count":      int(tests),
        "relative_volume":  round(rvol, 4) if rvol is not None else None,
        "avg_volume_50d":   round(avg_vol_50d) if avg_vol_50d is not None else None,
        "sma20":            round(s20_val, 4)  if s20_val  is not None else None,
        "sma50":            round(s50_val, 4)  if s50_val  is not None else None,
        "sma200":           round(s200_val, 4) if s200_val is not None else None,
        "trend_label":      trend_label,
        "summary":          summary,
        "data_source":      "ibkr",
        "warnings":         [],
        "chart":            _build_chart(df, chart_interval),
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status")
def breakout_status():
    """Return cache freshness, symbol count, and IBKR connection state."""
    OHLCV_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    INTRADAY_30M_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    pkls  = list(OHLCV_CACHE_DIR.glob("*.pkl"))
    intraday_pkls = list(INTRADAY_30M_CACHE_DIR.glob("*.pkl"))
    fresh = [p for p in pkls if _is_fresh(p)]
    intraday_fresh = [p for p in intraday_pkls if _is_fresh(p)]
    return {
        "ibkr_connected": ibkr_svc.is_connected(),
        "cached_symbols": len(pkls),
        "fresh_today":    len(fresh),
        "intraday_cached_symbols": len(intraday_pkls),
        "intraday_fresh_today":    len(intraday_fresh),
        "ndx100_count":   len(ALL_TICKERS),
    }


@router.get("/scan")
async def breakout_scan(
    source: str            = Query("ibkr", enum=["ibkr", "yf"]),
    index:  str            = Query("ndx100", enum=["ndx100", "sp500", "both"]),
    interval: str          = Query("1d", enum=["1d", "30m"]),
    refresh: bool          = Query(False),
    extra:  Optional[str]  = Query(None),
):
    """
    Run breakout scan across the requested universe. Returns JSON matching BreakoutScan shape.

    source=ibkr  → load pkl cache; miss → try live IBKR; miss → skip with warning
    source=yf    → download via yfinance (1Y)
    interval=1d  → daily bars (default)
    interval=30m → 30-minute intraday detector bars with hourly chart candles
    refresh=true → refresh missing/stale IBKR cache, capped per run to avoid TWS pacing limits
    index=ndx100 → NASDAQ-100 + leveraged ETFs (default, fast with IBKR cache)
    index=sp500  → S&P 500 (slow via yfinance, pkls usually absent)
    index=both   → union of the two
    extra        → comma-separated additional tickers appended to the universe
    """
    # ── Build ticker list ──────────────────────────────────────────────────────
    if index == "ndx100":
        tickers = list(ALL_TICKERS)
    elif index == "sp500":
        tickers = list(SP500)
    else:
        tickers = list(dict.fromkeys(list(ALL_TICKERS) + list(SP500)))

    if extra:
        extras = [t.strip().upper() for t in extra.split(",") if t.strip()]
        tickers = list(dict.fromkeys(tickers + extras))

    # ── Load OHLCV data ────────────────────────────────────────────────────────
    data: dict[str, pd.DataFrame] = {}
    warnings: list[str] = []

    if source == "ibkr":
        missing: list[str] = []
        for sym in tickers:
            df = _load_pkl(sym, interval)
            cache_path = _cache_dir(interval) / f"{sym}.pkl"
            if df is not None and (not refresh or _is_fresh(cache_path)):
                data[sym] = df
            else:
                if df is not None:
                    data[sym] = df
                missing.append(sym)

        if missing:
            if ibkr_svc.is_connected():
                fetch_symbols = missing[:MAX_IBKR_HISTORICAL_FETCHES_PER_SCAN]
                deferred_symbols = missing[MAX_IBKR_HISTORICAL_FETCHES_PER_SCAN:]
                if deferred_symbols:
                    warnings.append(
                        f"IBKR refresh limited to {MAX_IBKR_HISTORICAL_FETCHES_PER_SCAN} historical requests this run "
                        f"to stay under TWS pacing limits; {len(deferred_symbols)} symbol(s) left on cached/stale data."
                    )

                # IBKR pacing: max 50 historical-data requests per 30-second window
                BATCH_SIZE   = 45
                BATCH_WINDOW = 31.0   # seconds (1s buffer over IBKR 30s limit)
                sem          = asyncio.Semaphore(3)   # max concurrent reqHistoricalDataAsync within a batch

                async def _fetch_guarded(sym: str) -> None:
                    async with sem:
                        df = await _fetch_from_ibkr(sym, interval)
                        if df is not None:
                            data[sym] = df
                        await asyncio.sleep(0.1)

                total_batches = (len(fetch_symbols) + BATCH_SIZE - 1) // BATCH_SIZE
                for batch_idx in range(total_batches):
                    start = batch_idx * BATCH_SIZE
                    batch = fetch_symbols[start : start + BATCH_SIZE]

                    log.info(
                        "Breakout IBKR fetch batch %d/%d — %d symbols…",
                        batch_idx + 1, total_batches, len(batch),
                    )
                    t0 = asyncio.get_event_loop().time()

                    await asyncio.gather(*[_fetch_guarded(s) for s in batch])

                    if batch_idx < total_batches - 1:
                        elapsed   = asyncio.get_event_loop().time() - t0
                        remaining = BATCH_WINDOW - elapsed
                        if remaining > 0:
                            log.info(
                                "Breakout pacing: %.1fs elapsed, waiting %.1fs…",
                                elapsed, remaining,
                            )
                            await asyncio.sleep(remaining)
                still_missing = [s for s in fetch_symbols if s not in data]
                if still_missing:
                    warnings.append(
                        f"{len(still_missing)} symbol(s) unavailable (not cached, IBKR fetch failed): "
                        + ", ".join(still_missing[:8])
                        + ("…" if len(still_missing) > 8 else "")
                    )
            else:
                warnings.append(
                    f"IBKR not connected; {len(missing)} symbol(s) skipped (no pkl cache). "
                    "Connect TWS and run the scan again to populate the cache, "
                    "or switch to Yahoo Finance source."
                )

    else:  # source == "yf"
        try:
            from services.yf_fetcher import download_all
            data = download_all(tickers, period="1y")
            if len(data) < len(tickers):
                warnings.append(
                    f"yfinance returned data for {len(data)}/{len(tickers)} symbols."
                )
        except Exception as exc:
            return {
                "scan_run_id":    None,
                "scanned_at":     _datetime.utcnow().isoformat() + "Z",
                "market_date":    _date.today().isoformat(),
                "data_source":    "yfinance",
                "universe_count": len(tickers),
                "scanned_symbols": 0,
                "config":         None,
                "signals":        [],
                "warnings":       [f"yfinance download failed: {exc}"],
            }

    # ── Run breakout detection ─────────────────────────────────────────────────
    raw_signals: list[tuple[dict, pd.DataFrame]] = []
    for sym, df in data.items():
        try:
            sig = analyze(sym, df)
            if sig:
                raw_signals.append((sig, df))
        except Exception as exc:
            log.debug("analyze %s: %s", sym, exc)

    raw_signals.sort(key=lambda x: x[0].get("score", 0), reverse=True)

    signals = [
        _clean(_signal_to_api(sig, df, rank=i + 1, chart_interval="1h" if interval == "30m" else "1d"))
        for i, (sig, df) in enumerate(raw_signals)
    ]

    # ── Build response ─────────────────────────────────────────────────────────
    scanned_at  = _datetime.utcnow().isoformat() + "Z"
    market_date = _date.today().isoformat()
    if data:
        last_df = next(iter(data.values()))
        if hasattr(last_df.index[-1], "strftime"):
            market_date = last_df.index[-1].strftime("%Y-%m-%d")

    data_source = "yfinance"
    if source == "ibkr":
        data_source = "ibkr_30m_cache" if interval == "30m" else "ibkr_cache"

    return {
        "scan_run_id":     None,
        "scanned_at":      scanned_at,
        "market_date":     market_date,
        "data_source":     data_source,
        "chart_interval":  "1h" if source == "ibkr" and interval == "30m" else "1d",
        "universe_count":  len(tickers),
        "scanned_symbols": len(data),
        "config":          None,
        "signals":         signals,
        "warnings":        warnings,
    }
