"""
Three breakout detector types mirroring breakoutscanner.com logic:
  1. MOMENTUM_BREAKOUT  — price clears 52-week high on strong volume
  2. CEILING_BREAKOUT   — price clears a resistance zone tested ≥2× over 6 months
  3. NEAR_BREAKOUT      — within 3% of a well-tested resistance level (watch setup)

Scoring 0–100 based on: volume, trend (200 SMA), resistance quality, RSI, consolidation.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from services.breakout_indicators import sma, atr, rsi, relative_volume, consolidation_ratio, find_resistance_levels

RVOL_MIN = 1.3      # minimum RVol for breakout signal
RVOL_GOOD = 1.5
RVOL_GREAT = 2.0
NEAR_PCT = 0.025    # within 2.5% of resistance = watchlist (tighter = fewer false watches)
NEAR_RVOL_MIN = 0.8 # watches must have at least 0.8x avg volume (stock is active)
MAX_FRESH_DAYS = 2  # breakout must be at most 2 sessions old


def analyze(ticker: str, df: pd.DataFrame) -> dict | None:
    """Run all detectors. Returns best signal dict or None."""
    if len(df) < 200:
        return None

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    vol = df["Volume"]

    atr14 = atr(high, low, close)
    sma20 = sma(close, 20)
    sma50 = sma(close, 50)
    sma200 = sma(close, 200)
    rvol = relative_volume(vol)
    rsi14 = rsi(close)

    c = float(close.iloc[-1])
    h = float(high.iloc[-1])
    rv = float(rvol.iloc[-1])
    rs = float(rsi14.iloc[-1])
    s200 = float(sma200.iloc[-1])
    s50 = float(sma50.iloc[-1])
    s20 = float(sma20.iloc[-1])
    a = float(atr14.iloc[-1])

    if any(np.isnan(x) for x in [c, h, rv, rs, s200, a]):
        return None

    coil = consolidation_ratio(high, low, close)
    week52_high = float(high.iloc[-253:-1].max()) if len(df) >= 253 else float(high.iloc[:-1].max())

    signals: list[dict] = []

    # ── 1. MOMENTUM BREAKOUT (52-week high) ─────────────────────────────
    if c > week52_high and rv >= RVOL_MIN:
        score = _score_momentum(rv, c, s200, rs, coil)
        signals.append({
            "type": "MOMENTUM_BREAKOUT",
            "breakout_level": week52_high,
            "level_label": "52W High",
            "tests": None,
            "rel_vol": rv,
            "rsi": rs,
            "above_200sma": c > s200,
            "coil_ratio": coil,
            "score": score,
            "close": c,
            "sma200": s200,
            "atr": a,
        })

    # ── 2. CEILING BREAKOUT (multi-tested resistance) ────────────────────
    levels = find_resistance_levels(high, close)
    for level, tests in levels:
        # Must be above resistance
        if c <= level:
            continue
        # Must be fresh: at least one of the last MAX_FRESH_DAYS+1 prior closes was below
        prev_closes = close.iloc[-(MAX_FRESH_DAYS + 3) : -1]
        days_above = int((prev_closes > level).sum())
        if days_above > MAX_FRESH_DAYS:
            continue  # broke out too long ago
        if rv < RVOL_MIN:
            continue
        score = _score_ceiling(rv, c, s200, rs, tests, coil)
        signals.append({
            "type": "CEILING_BREAKOUT",
            "breakout_level": level,
            "level_label": f"Resistance ({tests}× tested)",
            "tests": tests,
            "rel_vol": rv,
            "rsi": rs,
            "above_200sma": c > s200,
            "coil_ratio": coil,
            "score": score,
            "close": c,
            "sma200": s200,
            "atr": a,
        })
        break  # take the best (highest test count) resistance only

    # ── 3. NEAR-BREAKOUT WATCH ───────────────────────────────────────────
    # Only flag if no active breakout found and volume is at least average
    if not [s for s in signals if s["type"] in ("MOMENTUM_BREAKOUT", "CEILING_BREAKOUT")]:
        for level, tests in levels:
            gap = (level - c) / c
            if 0 < gap <= NEAR_PCT and rv >= NEAR_RVOL_MIN:
                score = _score_near(rv, c, s200, rs, gap, tests, coil)
                signals.append({
                    "type": "NEAR_BREAKOUT",
                    "breakout_level": level,
                    "level_label": f"Watch — {gap*100:.1f}% to resistance",
                    "tests": tests,
                    "rel_vol": rv,
                    "rsi": rs,
                    "above_200sma": c > s200,
                    "coil_ratio": coil,
                    "score": score,
                    "close": c,
                    "sma200": s200,
                    "atr": a,
                })
                break

    if not signals:
        return None

    best = max(signals, key=lambda x: x["score"])
    best["ticker"] = ticker
    return best


# ── Scoring helpers ───────────────────────────────────────────────────────

def _vol_pts(rv: float, max_pts: int) -> int:
    if rv >= RVOL_GREAT:
        return max_pts
    if rv >= RVOL_GOOD:
        return int(max_pts * 0.70)
    if rv >= RVOL_MIN:
        return int(max_pts * 0.40)
    return 0


def _score_momentum(rv, close, sma200, rsi_val, coil) -> int:
    score = 0
    score += _vol_pts(rv, 30)               # volume: 30 pts
    score += 25 if close > sma200 else 0    # trend: 25 pts
    # RSI: 45–75 is the sweet spot for momentum (not overbought)
    if 45 <= rsi_val <= 75:
        score += 25
    elif 40 <= rsi_val <= 80:
        score += 15
    else:
        score += 5
    # Consolidation before breakout (coil_ratio < 0.75 = price was coiling)
    if coil < 0.65:
        score += 20
    elif coil < 0.80:
        score += 10
    return min(score, 100)


def _score_ceiling(rv, close, sma200, rsi_val, tests, coil) -> int:
    score = 0
    score += _vol_pts(rv, 30)               # volume: 30 pts
    score += 20 if close > sma200 else 0    # trend: 20 pts
    # Resistance quality: more tests = stronger level = better breakout
    score += min(tests * 6, 24)             # up to 24 pts
    # RSI: 45–65 ideal (not stretched)
    if 45 <= rsi_val <= 65:
        score += 14
    elif 35 <= rsi_val <= 70:
        score += 8
    # Consolidation
    if coil < 0.65:
        score += 12
    elif coil < 0.80:
        score += 6
    return min(score, 100)


def _score_near(rv, close, sma200, rsi_val, gap_pct, tests, coil) -> int:
    score = 0
    # Proximity to resistance
    if gap_pct <= 0.01:
        score += 30
    elif gap_pct <= 0.02:
        score += 20
    else:
        score += 10
    score += _vol_pts(rv, 20)               # volume building
    score += 20 if close > sma200 else 0    # trend
    score += min(tests * 5, 15)             # resistance quality
    if 40 <= rsi_val <= 60:
        score += 15
    elif 35 <= rsi_val <= 65:
        score += 8
    return min(score, 100)
