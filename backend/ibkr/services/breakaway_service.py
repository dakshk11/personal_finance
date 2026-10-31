"""
Breakaway-style Quality Score (getbreakaway.com clone) for the Nasdaq-100.

Only the price/volume parts of Breakaway's published methodology are scored,
because the input is the daily OHLCV already cached for the breakout scanner:

  Chart checks      0…+13  14 checks in four groups; VOL and VDU are opposites
  Long-term trend  −3…+4
  Run-up            0…+2   +2 if up 100% in 12m or 60% in 6m, +1 if up 30% in 6m
  Volatility       −2…0    price-based part of "dilution, volatility, cash burn"
  Persistence       0…+2   20-session median score ≥12 → +2, ≥9 → +1 (needs 10 days)

Company size, fundamentals, news/8-K, insider, government and short-interest
inputs are not in the IBKR bar cache; they are reported as unscored.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from services.breakout_indicators import atr, ema, sma

# key, label, group, description
CHECKS: list[tuple[str, str, str, str]] = [
    ("ma_fan", "MA FAN", "Trend", "Averages stacked: 10 EMA > 21 EMA > 50 SMA > 200 SMA"),
    ("ema21", "21 EMA", "Trend", "Price holds above a rising 21-day EMA"),
    ("w_ema", "W.EMA", "Trend", "Weekly chart agrees: above a rising 10-week (50-day) EMA"),
    ("hh_hl", "HH/HL", "Trend", "Higher high and higher low than the prior 10-session swing"),
    ("near_high", "52W HI", "Trend", "Within 5% of the 52-week high"),
    ("vol", "VOL", "Volume", "Up day on 1.5x+ the 50-day average volume"),
    ("vdu", "VDU", "Volume", "Quiet rest day: under 60% of average volume on a move under 1%"),
    ("ud_vol", "U/D VOL", "Volume", "More shares traded on up days than down days over 50 sessions"),
    ("atr_sqz", "ATR SQZ", "Tight range", "10-day ATR below 75% of the 50-day ATR"),
    ("squeeze", "SQUEEZE", "Tight range", "Bollinger Bands inside Keltner Channels (price-based; no short-interest data)"),
    ("nr7", "NR7", "Tight range", "Narrowest daily range of the last seven sessions"),
    ("obv", "OBV+", "Buying", "On-balance volume above its 20-day average and higher than 10 sessions ago"),
    ("close_hi", "CLOSE HI", "Buying", "Closed in the top 25% of the day's range"),
    ("spring", "SPRING", "Buying", "Dipped under the 21 EMA in the last 5 sessions and closed back above it"),
]
CHECK_KEYS = [key for key, *_ in CHECKS]
MAX_CHECKS = 13

UNSCORED_COMPONENTS: list[tuple[str, str]] = [
    ("Company size", "−1…+2"),
    ("Profitability", "−1…+1"),
    ("Sales growth & margins", "−2…+3"),
    ("Dilution & cash burn", "−3…0"),
    ("News & 8-K filings", "−3…+3"),
    ("Insider trades (Form 4)", "−3…+3"),
    ("Government filings", "−2…+3"),
]

TIERS: list[tuple[float, str]] = [
    (20, "Exceptional"),
    (15, "Excellent"),
    (11, "Above average"),
    (6, "Average"),
    (0, "Below average"),
]


def tier(score: float | None) -> str:
    if score is None:
        return "Unscored"
    for floor, label in TIERS:
        if score >= floor:
            return label
    return "Poor"


def compute_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Vectorised checks, score components and chart overlays for every bar."""
    o, h, l, c, v = df["Open"], df["High"], df["Low"], df["Close"], df["Volume"]
    out = pd.DataFrame(index=df.index)

    e10, e21, e50 = ema(c, 10), ema(c, 21), ema(c, 50)
    s20, s50, s200 = sma(c, 20), sma(c, 50), sma(c, 200)
    avg_v = v.rolling(50).mean().shift(1)
    chg = c.pct_change()
    rng = h - l
    atr14 = atr(h, l, c, 14)
    sd20 = c.rolling(20).std()
    kc = 1.5 * atr(h, l, c, 20)
    hi52 = h.rolling(252, min_periods=200).max()
    obv = (np.sign(c.diff()).fillna(0) * v).cumsum()

    out["ma_fan"] = (e10 > e21) & (e21 > s50) & (s50 > s200)
    out["ema21"] = (c > e21) & (e21 > e21.shift(5))
    out["w_ema"] = (c > e50) & (e50 > e50.shift(5))
    h10, l10 = h.rolling(10).max(), l.rolling(10).min()
    out["hh_hl"] = (h10 > h10.shift(10)) & (l10 > l10.shift(10))
    out["near_high"] = c >= 0.95 * hi52
    out["vol"] = (chg > 0) & (v >= 1.5 * avg_v)
    out["vdu"] = (v <= 0.6 * avg_v) & (chg.abs() <= 0.01)
    up_v = v.where(chg > 0, 0).rolling(50).sum()
    dn_v = v.where(chg < 0, 0).rolling(50).sum()
    out["ud_vol"] = up_v > dn_v
    out["atr_sqz"] = atr(h, l, c, 10) < 0.75 * atr(h, l, c, 50)
    out["squeeze"] = (s20 + 2 * sd20 < s20 + kc) & (s20 - 2 * sd20 > s20 - kc)
    out["nr7"] = (rng > 0) & (rng <= rng.rolling(7).min())
    out["obv"] = (obv > obv.rolling(20).mean()) & (obv > obv.shift(10))
    out["close_hi"] = (rng > 0) & ((c - l) >= 0.75 * rng)
    dipped = (l < e21).astype(float).rolling(5).max() == 1
    out["spring"] = dipped & (c > e21) & (e21 > e21.shift(5))

    valid = s200.notna()
    out["checks"] = out[CHECK_KEYS].sum(axis=1).where(valid)

    ret_6m = c / c.shift(126) - 1
    ret_12m = c / c.shift(250) - 1
    held_above = (s50 > s200).astype(float).rolling(60).min() == 1
    trend_up = (
        (c > s200).astype(int)
        + (s200 > s200.shift(20)).astype(int)
        + held_above.astype(int)
        + (ret_12m > 0).astype(int)
    )
    trend_down = (
        np.where(ret_12m < -0.2, -2, np.where(ret_12m < 0, -1, 0))
        + ((c < s200) & (s200 < s200.shift(20))).astype(int) * -1
    )
    out["long_term"] = (trend_up + trend_down).clip(-3, 4).where(valid)
    out["run_up"] = pd.Series(
        np.where((ret_12m >= 1.0) | (ret_6m >= 0.6), 2, np.where(ret_6m >= 0.3, 1, 0)), index=df.index
    ).where(valid)
    atr_pct = atr14 / c
    out["volatility"] = pd.Series(np.where(atr_pct > 0.06, -2, np.where(atr_pct > 0.04, -1, 0)), index=df.index).where(valid)

    base = out["checks"] + out["long_term"] + out["run_up"] + out["volatility"]
    median20 = base.rolling(20, min_periods=10).median()
    out["persistence"] = pd.Series(np.where(median20 >= 12, 2, np.where(median20 >= 9, 1, 0)), index=df.index).where(valid)
    out["score"] = base + out["persistence"]

    out["trend"] = np.where(
        (c > s50) & (s50 > s200) & (s50 > s50.shift(10)),
        "Trending up",
        np.where((c < s50) & (s50 < s200), "Trending down", "Sideways"),
    )
    out["ema21_line"], out["sma50"], out["sma200"] = e21, s50, s200
    out["bb_upper"], out["bb_lower"] = s20 + 2 * sd20, s20 - 2 * sd20
    out["atr14"], out["atr_pct"] = atr14, atr_pct
    out["rel_volume"] = v / avg_v
    out["prior_high_252"] = h.shift(1).rolling(251, min_periods=200).max()
    out["ret_6m"], out["ret_12m"] = ret_6m, ret_12m
    return out


def equal_weight_benchmark(closes: dict[str, pd.Series]) -> pd.Series:
    """Equal-weight Nasdaq-100 composite (base 100) built from the same cached closes."""
    if not closes:
        return pd.Series(dtype=float)
    returns = pd.DataFrame(closes).sort_index().pct_change(fill_method=None).mean(axis=1, skipna=True).fillna(0)
    return 100 * (1 + returns).cumprod()


def _ret(series: pd.Series, bars: int) -> float | None:
    if len(series) <= bars:
        return None
    base = float(series.iloc[-1 - bars])
    return _num(float(series.iloc[-1]) / base - 1) if base else None


def _num(value) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def summarize(symbol: str, name: str, sector: str, df: pd.DataFrame, frame: pd.DataFrame, bench: pd.Series) -> dict | None:
    """One scanner row (card) for the latest bar."""
    if len(frame) < 2 or pd.isna(frame["score"].iloc[-1]):
        return None
    last, prev = frame.iloc[-1], frame.iloc[-2]
    bar, prev_bar = df.iloc[-1], df.iloc[-2]
    close, prev_close = float(bar["Close"]), float(prev_bar["Close"])
    score = int(last["score"])
    prev_score = None if pd.isna(prev["score"]) else int(prev["score"])
    ret_3m = _ret(df["Close"], 63)
    bench_aligned = bench.reindex(df.index).ffill()
    bench_3m = _ret(bench_aligned.dropna(), 63)
    return {
        "symbol": symbol,
        "name": name,
        "sector": sector,
        "as_of": df.index[-1].strftime("%Y-%m-%d"),
        "price": round(close, 2),
        "change": round(close - prev_close, 2),
        "change_pct": _num(close / prev_close - 1),
        "score": score,
        "prev_score": prev_score,
        "fresh": prev_score is not None and prev_score != score,
        "tier": tier(score),
        "checks_firing": int(last["checks"]),
        "checks": [key for key in CHECK_KEYS if bool(last[key])],
        "trend": str(last["trend"]),
        "above_200d": bool(close > last["sma200"]) if not pd.isna(last["sma200"]) else False,
        "rel_volume": _num(last["rel_volume"]),
        "range_pct": _num((float(bar["High"]) - float(bar["Low"])) / prev_close),
        "gap_pct": _num(float(bar["Open"]) / prev_close - 1),
        "new_high": bool(float(bar["High"]) >= last["prior_high_252"]) if not pd.isna(last["prior_high_252"]) else False,
        "pct_from_high": _num(close / float(df["High"].tail(252).max()) - 1),
        "atr_pct": _num(last["atr_pct"]),
        "ret_1d": _num(close / prev_close - 1),
        "ret_1w": _ret(df["Close"], 5),
        "ret_1m": _ret(df["Close"], 21),
        "ret_3m": ret_3m,
        "ret_6m": _num(last["ret_6m"]),
        "ret_12m": _num(last["ret_12m"]),
        "strength_vs_market": None if ret_3m is None or bench_3m is None else _num(ret_3m - bench_3m),
        "sparkline": [round(float(x), 2) for x in df["Close"].tail(30)],
    }


def build_lists(rows: list[dict], limit: int = 20) -> dict[str, list[str]]:
    def pick(filtered, key, reverse=True):
        return [r["symbol"] for r in sorted(filtered, key=lambda r: r[key] or 0, reverse=reverse)[:limit]]

    return {
        "fresh": pick([r for r in rows if r["fresh"]], "score"),
        "gainers": pick([r for r in rows if (r["change_pct"] or 0) > 0], "change_pct"),
        "losers": pick([r for r in rows if (r["change_pct"] or 0) < 0], "change_pct", reverse=False),
        "unusual_volume": pick([r for r in rows if (r["rel_volume"] or 0) >= 1.5], "rel_volume"),
        "new_highs": pick([r for r in rows if r["new_high"]], "score"),
        "most_volatile": pick(rows, "range_pct"),
        "gap_ups": pick([r for r in rows if (r["gap_pct"] or 0) >= 0.02], "gap_pct"),
        "squeeze": pick([r for r in rows if "squeeze" in r["checks"] and (r["change_pct"] or 0) > 0], "score"),
    }


def rank_sectors(rows: list[dict], min_members: int = 4) -> list[dict]:
    """Industry rank = average Quality Score of members (industries with 4+ names).

    Also sets rank / sector_rank / sector_size on each row in place.
    """
    rows.sort(key=lambda r: (-r["score"], r["symbol"]))
    for i, row in enumerate(rows, start=1):
        row["rank"] = i

    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["sector"], []).append(row)

    sectors = []
    for sector, members in groups.items():
        for i, row in enumerate(members, start=1):
            row["sector_rank"], row["sector_size"] = i, len(members)
        if len(members) < min_members:
            continue

        def avg(key):
            vals = [m[key] for m in members if m[key] is not None]
            return sum(vals) / len(vals) if vals else None

        sectors.append({
            "sector": sector,
            "members": len(members),
            "avg_score": round(avg("score"), 2),
            "pct_trending_up": sum(m["trend"] == "Trending up" for m in members) / len(members),
            "pct_above_200d": sum(m["above_200d"] for m in members) / len(members),
            "avg_ret_1d": avg("ret_1d"),
            "avg_ret_1w": avg("ret_1w"),
            "avg_ret_1m": avg("ret_1m"),
            "avg_ret_3m": avg("ret_3m"),
            "top": [{"symbol": m["symbol"], "score": m["score"]} for m in members[:3]],
        })
    sectors.sort(key=lambda s: -s["avg_score"])
    for i, sector in enumerate(sectors, start=1):
        sector["rank"] = i
    return sectors


def score_breakdown(frame: pd.DataFrame) -> list[dict]:
    last = frame.iloc[-1]
    scored = [
        ("Chart checks", int(last["checks"]), "0…+13", f"{int(last['checks'])} of {MAX_CHECKS} firing"),
        ("Long-term trend", int(last["long_term"]), "−3…+4", "200-day trend, 50/200 stack and 12-month return"),
        ("Run-up", int(last["run_up"]), "0…+2", "6- and 12-month gains"),
        ("Volatility", int(last["volatility"]), "−2…0", "ATR above 4% / 6% of price"),
        ("Persistence", int(last["persistence"]), "0…+2", "20-session median score"),
    ]
    out = [{"component": c, "points": p, "range": r, "detail": d, "scored": True} for c, p, r, d in scored]
    out += [
        {"component": c, "points": None, "range": r, "detail": "Not in IBKR price cache", "scored": False}
        for c, r in UNSCORED_COMPONENTS
    ]
    return out


def check_details(frame: pd.DataFrame, sessions: int = 60) -> list[dict]:
    last = frame.iloc[-1]
    recent = frame[frame["score"].notna()].tail(sessions)
    return [
        {
            "key": key,
            "label": label,
            "group": group,
            "description": desc,
            "fired": bool(last[key]),
            "count_60d": int(recent[key].sum()),
        }
        for key, label, group, desc in CHECKS
    ]


def trade_plan(df: pd.DataFrame, frame: pd.DataFrame) -> dict:
    price = float(df["Close"].iloc[-1])
    atr_val = float(frame["atr14"].iloc[-1])
    swing_low = float(df["Low"].tail(10).min())
    stop = max(price - 2 * atr_val, swing_low * 0.995)
    if stop >= price:
        stop = price - 2 * atr_val
    target = price + 2 * (price - stop)
    return {"entry": round(price, 2), "stop": round(stop, 2), "target": round(target, 2), "atr": round(atr_val, 2)}


def chart_points(df: pd.DataFrame, frame: pd.DataFrame, bench: pd.Series) -> list[dict]:
    bench_aligned = bench.reindex(df.index).ffill()
    rs = df["Close"] / bench_aligned
    points = []
    for idx, bar in df.iterrows():
        f = frame.loc[idx]
        points.append({
            "date": idx.strftime("%Y-%m-%d"),
            "open": _num(bar["Open"]),
            "high": _num(bar["High"]),
            "low": _num(bar["Low"]),
            "close": _num(bar["Close"]),
            "volume": _num(bar["Volume"]) or 0,
            "ema21": _num(f["ema21_line"]),
            "sma50": _num(f["sma50"]),
            "sma200": _num(f["sma200"]),
            "bb_upper": _num(f["bb_upper"]),
            "bb_lower": _num(f["bb_lower"]),
            "rs": _num(rs.loc[idx]),
            "score": _num(f["score"]),
        })
    return points
