"""
Stage Desk endpoints for the IBKR backend — Nasdaq-100 only.

GET /api/stage-desk/scan            — screen rows, stage counts, industry ranks
GET /api/stage-desk/stock/{symbol}  — trend checks, weekly chart, stage history, peers

No IBKR requests are made here. Daily bars come from the shared breakout-scanner
pkl cache and the live price from ibkr_service's streaming quote cache, through
the same helpers Breakaway uses.
"""

from __future__ import annotations

from datetime import datetime as _datetime

import pandas as pd
from fastapi import APIRouter, HTTPException

import services.ibkr_service as ibkr_svc
from data.nasdaq100_profiles import NASDAQ100_PROFILES
from data.tickers import NASDAQ100
from services.breakaway_router import _cached_bars, _with_live_price
from services.breakaway_service import equal_weight_benchmark
from services.stage_service import (
    MAX_SCORE,
    STAGE_NAMES,
    chart_points,
    check_details,
    compute_weekly,
    rank_industries,
    stage_counts,
    stage_history,
    stage_label,
    summarize,
    tags,
)

router = APIRouter(prefix="/api/stage-desk", tags=["stage-desk"])

MIN_BARS = 180  # 30-week SMA + 4-week slope needs ~34 weeks of daily bars


def _universe() -> tuple[dict[str, pd.DataFrame], pd.Series, list[str], int]:
    quotes = ibkr_svc.get_all_quotes()
    daily: dict[str, pd.DataFrame] = {}
    missing: list[str] = []
    live_count = 0
    for sym in NASDAQ100:
        bars = _cached_bars(sym)
        if bars is None or len(bars) < MIN_BARS:
            missing.append(sym)
            continue
        df, live = _with_live_price(bars, quotes.get(sym))
        live_count += live
        daily[sym] = df
    bench = equal_weight_benchmark({sym: df["Close"] for sym, df in daily.items()})
    return daily, bench, missing, live_count


def _rows(daily: dict[str, pd.DataFrame], bench: pd.Series) -> tuple[list[dict], dict[str, pd.DataFrame]]:
    rows, weeklies = [], {}
    for sym, df in daily.items():
        weekly = compute_weekly(df, bench)
        name, sector = NASDAQ100_PROFILES.get(sym, (sym, "Other"))
        row = summarize(sym, name, sector, df, weekly, bench)
        if row:
            rows.append(row)
            weeklies[sym] = weekly
    return rows, weeklies


def _scored(daily, bench):
    rows, weeklies = _rows(daily, bench)
    industries = rank_industries(rows)
    for row in rows:
        row["tags"] = tags(row)
    rows.sort(key=lambda r: (-r["score"], -(r["rs_pct"] or 0), r["symbol"]))
    return rows, weeklies, industries


def _market(bench: pd.Series) -> dict:
    bench_df = pd.DataFrame({"Open": bench, "High": bench, "Low": bench, "Close": bench, "Volume": 0.0}).dropna()
    weekly = compute_weekly(bench_df, bench)
    last = weekly.iloc[-1]
    stage = None if pd.isna(last["stage"]) else int(last["stage"])
    clean = bench.dropna()

    def ret(n):
        return float(clean.iloc[-1] / clean.iloc[-1 - n] - 1) if len(clean) > n else None

    return {
        "benchmark": "Nasdaq-100 equal weight",
        "stage": stage,
        "stage_label": stage_label(stage),
        "weeks": None if pd.isna(last["weeks"]) else int(last["weeks"]),
        "ret_1d": ret(1),
        "ret_1w": ret(5),
        "ret_1m": ret(21),
        "ret_3m": ret(63),
    }


@router.get("/scan")
def stage_desk_scan():
    daily, bench, missing, live_count = _universe()
    rows, _, industries = _scored(daily, bench)
    warnings = [
        "Technical inputs only. EquityDesk's earnings-call sentiment/performance scores and alternative data "
        "are not in the IBKR cache and are not shown.",
        "The cache holds about one year of daily bars, so Mansfield RS uses a 30-week base and weeks-in-stage "
        "is capped at the available history (marked +).",
        "Educational research only — not buy or sell instructions.",
    ]
    if missing:
        warnings.append(
            f"{len(missing)} Nasdaq-100 symbol(s) have no cached IBKR daily bars (or under {MIN_BARS} sessions): "
            + ", ".join(missing[:10]) + ("…" if len(missing) > 10 else "")
            + ". Run a Breakout Scanner refresh to populate the shared cache."
        )
    return {
        "generated_at": _datetime.utcnow().isoformat() + "Z",
        "market_date": max((r["as_of"] for r in rows), default=None),
        "ibkr_connected": ibkr_svc.is_connected(),
        "live_quotes": live_count,
        "universe_count": len(NASDAQ100),
        "scored_count": len(rows),
        "max_score": MAX_SCORE,
        "stage_names": {str(k): v for k, v in STAGE_NAMES.items()},
        "market": {**_market(bench), "stage_counts": stage_counts(rows)},
        "stocks": rows,
        "industries": industries,
        "warnings": warnings,
    }


@router.get("/stock/{symbol}")
def stage_desk_stock(symbol: str):
    sym = symbol.strip().upper()
    if sym not in NASDAQ100:
        raise HTTPException(status_code=404, detail=f"{sym} is not in the Nasdaq-100")
    daily, bench, _, _ = _universe()
    if sym not in daily:
        raise HTTPException(status_code=404, detail=f"No cached IBKR daily bars for {sym}")
    rows, weeklies, _ = _scored(daily, bench)
    row = next((r for r in rows if r["symbol"] == sym), None)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Not enough weekly history to stage {sym}")
    weekly = weeklies[sym]
    return {
        **row,
        "check_details": check_details(weekly),
        "stage_history": stage_history(weekly),
        "chart": chart_points(weekly),
        "peers": [
            {k: r[k] for k in ("symbol", "name", "stage", "weeks", "score", "rs_pct", "change_pct")}
            for r in sorted(rows, key=lambda r: -(r["rs_pct"] or 0))
            if r["sector"] == row["sector"]
        ],
    }
