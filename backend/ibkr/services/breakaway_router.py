"""
Breakaway (Quality Score) endpoints for the IBKR backend — Nasdaq-100 plus
SOXL / TQQQ / UPRO (the breakout scanner's ALL_TICKERS universe).

GET /api/breakaway/scan            — ranked cards, lists, industry ranks
GET /api/breakaway/stock/{symbol}  — score breakdown, checks, chart, peers, trade plan

No IBKR requests are made here. Daily bars come from the breakout scanner's
pkl cache (data/history, refreshed by analytics_service / breakout scan) and the
live price comes from ibkr_service's existing streaming quote cache.
"""

from __future__ import annotations

from datetime import date as _date, datetime as _datetime

import pandas as pd
from fastapi import APIRouter, HTTPException

import services.ibkr_service as ibkr_svc
from data.nasdaq100_profiles import NASDAQ100_PROFILES
from data.tickers import ALL_TICKERS, NASDAQ100
from services import breakout_router
from services.breakaway_service import (
    build_lists,
    chart_points,
    check_details,
    compute_frame,
    equal_weight_benchmark,
    rank_sectors,
    score_breakdown,
    summarize,
    tier,
    trade_plan,
)

router = APIRouter(prefix="/api/breakaway", tags=["breakaway"])

# sym -> (pkl mtime, DataFrame) so repeat polls do not re-read 94 pickles
_bars_cache: dict[str, tuple[float, pd.DataFrame]] = {}
# (sym, pkl mtime, live price) -> computed frame
_frame_cache: dict[tuple, pd.DataFrame] = {}


def _cached_bars(sym: str) -> pd.DataFrame | None:
    path = breakout_router.OHLCV_CACHE_DIR / f"{sym}.pkl"
    if not path.exists():
        return None
    mtime = path.stat().st_mtime
    hit = _bars_cache.get(sym)
    if hit and hit[0] == mtime:
        return hit[1]
    df = breakout_router._load_pkl(sym, "1d")
    if df is None:
        return None
    df = df.sort_index()
    _bars_cache[sym] = (mtime, df)
    return df


def _with_live_price(df: pd.DataFrame, quote: dict | None) -> tuple[pd.DataFrame, bool]:
    """Overlay the streaming IBKR price on today's cached bar (only when that bar is today's)."""
    price = (quote or {}).get("price")
    if not price or df.index[-1].date() != _date.today():
        return df, False
    df = df.copy()
    i = df.index[-1]
    df.at[i, "Close"] = price
    df.at[i, "High"] = max(float(df.at[i, "High"]), price)
    df.at[i, "Low"] = min(float(df.at[i, "Low"]), price)
    return df, True


def _frame(sym: str, df: pd.DataFrame, live: bool) -> pd.DataFrame:
    path = breakout_router.OHLCV_CACHE_DIR / f"{sym}.pkl"
    key = (sym, path.stat().st_mtime if path.exists() else 0, float(df["Close"].iloc[-1]) if live else None)
    frame = _frame_cache.get(key)
    if frame is None:
        frame = compute_frame(df)
        for old in [k for k in _frame_cache if k[0] == sym]:
            del _frame_cache[old]
        _frame_cache[key] = frame
    return frame


def _universe() -> tuple[dict, pd.Series, list[str], int]:
    """Load every universe symbol from cache, overlay live quotes, score."""
    quotes = ibkr_svc.get_all_quotes()
    loaded: dict[str, tuple[pd.DataFrame, pd.DataFrame, bool]] = {}
    missing: list[str] = []
    live_count = 0
    for sym in ALL_TICKERS:
        bars = _cached_bars(sym)
        if bars is None or len(bars) < 200:
            missing.append(sym)
            continue
        df, live = _with_live_price(bars, quotes.get(sym))
        live_count += live
        loaded[sym] = (df, _frame(sym, df, live), live)
    # Benchmark stays Nasdaq-100 only so the 3x ETFs do not skew "the market".
    bench = equal_weight_benchmark({sym: df["Close"] for sym, (df, _, _) in loaded.items() if sym in NASDAQ100})
    return loaded, bench, missing, live_count


def _rows(loaded: dict, bench: pd.Series) -> list[dict]:
    rows = []
    for sym, (df, frame, live) in loaded.items():
        name, sector = NASDAQ100_PROFILES.get(sym, (sym, "Other"))
        row = summarize(sym, name, sector, df, frame, bench)
        if row:
            row["live"] = live
            rows.append(row)
    return rows


@router.get("/scan")
def breakaway_scan():
    loaded, bench, missing, live_count = _universe()
    rows = _rows(loaded, bench)
    sectors = rank_sectors(rows)
    warnings = [
        "Price/volume components only. Company size, fundamentals, news/8-K, insider, government and "
        "short-interest inputs from Breakaway are not in the IBKR cache and are not scored.",
        "Educational research only — not buy or sell instructions.",
    ]
    if missing:
        warnings.append(
            f"{len(missing)} symbol(s) have no cached IBKR daily bars (or under 200 sessions): {', '.join(missing[:10])}"
            + ("…" if len(missing) > 10 else "")
            + ". Run a Breakout Scanner refresh to populate the shared cache."
        )
    tiers: dict[str, int] = {}
    for row in rows:
        tiers[row["tier"]] = tiers.get(row["tier"], 0) + 1
    bench_clean = bench.dropna()

    def bench_ret(n):
        return float(bench_clean.iloc[-1] / bench_clean.iloc[-1 - n] - 1) if len(bench_clean) > n else None

    return {
        "generated_at": _datetime.utcnow().isoformat() + "Z",
        "market_date": max((r["as_of"] for r in rows), default=None),
        "data_source": "ibkr_cache",
        "ibkr_connected": ibkr_svc.is_connected(),
        "live_quotes": live_count,
        "universe_count": len(ALL_TICKERS),
        "scored_count": len(rows),
        "market": {
            "benchmark": "Nasdaq-100 equal weight",
            "ret_1d": bench_ret(1),
            "ret_1w": bench_ret(5),
            "ret_1m": bench_ret(21),
            "ret_3m": bench_ret(63),
            "pct_trending_up": sum(r["trend"] == "Trending up" for r in rows) / len(rows) if rows else None,
            "pct_above_200d": sum(r["above_200d"] for r in rows) / len(rows) if rows else None,
            "tiers": tiers,
        },
        "stocks": rows,
        "lists": build_lists(rows),
        "sectors": sectors,
        "warnings": warnings,
    }


@router.get("/stock/{symbol}")
def breakaway_stock(symbol: str):
    sym = symbol.strip().upper()
    if sym not in ALL_TICKERS:
        raise HTTPException(status_code=404, detail=f"{sym} is not in the Breakaway universe")
    loaded, bench, _, _ = _universe()
    if sym not in loaded:
        raise HTTPException(status_code=404, detail=f"No cached IBKR daily bars for {sym}")
    rows = _rows(loaded, bench)
    rank_sectors(rows)
    row = next((r for r in rows if r["symbol"] == sym), None)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Not enough history to score {sym}")
    df, frame, _ = loaded[sym]
    history = frame["score"].dropna()
    peers = [
        {k: r[k] for k in ("symbol", "name", "score", "tier", "change_pct", "sector_rank", "trend")}
        for r in rows
        if r["sector"] == row["sector"]
    ]
    return {
        **row,
        "tier": tier(row["score"]),
        "breakdown": score_breakdown(frame),
        "check_details": check_details(frame),
        "score_history": [{"date": d.strftime("%Y-%m-%d"), "score": int(s)} for d, s in history.items()],
        "chart": chart_points(df, frame, bench),
        "peers": peers,
        "trade_plan": trade_plan(df, frame),
    }
