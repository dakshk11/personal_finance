"""
Stage Desk: Weinstein stage analysis for the Nasdaq-100 (EquityDesk-style screen).

Input is the same daily OHLCV cache the Breakout Scanner and Breakaway use
(about one year of IBKR daily bars), resampled to weekly bars:

  Stage        1 Basing · 2 Advancing · 3 Topping · 4 Declining, from price vs the
               30-week SMA and that average's 4-week slope
  Weeks        consecutive weeks in the current stage
  Trend score  0…10, one point per check in TREND_CHECKS
  ATR Ext      (close − 50-day SMA) / 14-day ATR: how stretched price is
  RS           Mansfield RS vs the Nasdaq-100 equal-weight composite (30-week base,
               because the cache only holds ~52 weeks)

Earnings-call and alternative-data inputs from EquityDesk are not in the IBKR
cache and are not scored.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from services.breakout_indicators import atr, sma

STAGE_NAMES = {1: "Basing", 2: "Advancing", 3: "Topping", 4: "Declining"}
SLOPE_FLAT = 0.005  # 30-week SMA moving less than ±0.5% over 4 weeks counts as flat
EXTENDED_ATR = 4.0

# key, label, description
TREND_CHECKS: list[tuple[str, str, str]] = [
    ("stage2", "Stage 2", "Weinstein stage is Advancing"),
    ("above_ma30", "Above 30W", "Weekly close above the 30-week SMA"),
    ("ma30_rising", "30W rising", "30-week SMA higher than 4 weeks ago"),
    ("above_ma10", "Above 10W", "Weekly close above the 10-week SMA"),
    ("ma10_over_ma30", "10W > 30W", "10-week SMA above the 30-week SMA"),
    ("rs_positive", "RS > 0", "Mansfield relative strength vs Nasdaq-100 EW is positive"),
    ("rs_rising", "RS rising", "Relative strength line higher than 13 weeks ago"),
    ("near_high", "Near high", "Within 15% of the 52-week high"),
    ("accumulation", "Accumulation", "More volume on up weeks than down weeks over 10 weeks"),
    ("ret_26w", "26W up", "Positive 26-week return"),
]
MAX_SCORE = len(TREND_CHECKS)


def _num(value) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) or math.isinf(f) else f


def to_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """Daily OHLCV → Friday-ending weekly bars (the last bar may be a partial week)."""
    weekly = df.resample("W-FRI").agg(
        {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    )
    return weekly.dropna(subset=["Close"])


def classify_stages(close: pd.Series, ma30: pd.Series, slope: pd.Series) -> pd.Series:
    """Walk forward so flat-MA weeks resolve to Basing (after 4/1) or Topping (after 2/3)."""
    stages: list[float] = []
    prev: int | None = None
    for c, m, s in zip(close, ma30, slope):
        if pd.isna(m) or pd.isna(s):
            stages.append(np.nan)
            continue
        above, rising, falling = c > m, s > SLOPE_FLAT, s < -SLOPE_FLAT
        if above and rising:
            stage = 2
        elif not above and falling:
            stage = 4
        elif prev == 2 and rising:
            stage = 2  # pullback under a still-rising average
        elif prev == 4 and falling:
            stage = 4  # bear-market rally over a still-falling average
        elif prev in (2, 3):
            stage = 3
        elif prev in (4, 1):
            stage = 1
        else:
            stage = 3 if above else 1
        stages.append(stage)
        prev = stage
    return pd.Series(stages, index=close.index, dtype=float)


def weeks_in_stage(stage: pd.Series) -> pd.Series:
    run = (stage != stage.shift()).cumsum()
    return stage.groupby(run).cumcount().add(1).where(stage.notna())


def compute_weekly(df: pd.DataFrame, bench: pd.Series) -> pd.DataFrame:
    """Weekly frame with stage, weeks in stage, Mansfield RS and the trend-score checks."""
    w = to_weekly(df)
    c, v = w["Close"], w["Volume"]
    out = pd.DataFrame(index=w.index)
    out["open"], out["high"], out["low"], out["close"], out["volume"] = w["Open"], w["High"], w["Low"], c, v
    out["ma10"], out["ma30"] = sma(c, 10), sma(c, 30)
    out["slope"] = out["ma30"] / out["ma30"].shift(4) - 1
    out["stage"] = classify_stages(c, out["ma30"], out["slope"])
    out["weeks"] = weeks_in_stage(out["stage"])

    bench_w = bench.resample("W-FRI").last().reindex(w.index).ffill()
    rs = c / bench_w
    out["rs"] = rs
    out["mansfield"] = (rs / rs.rolling(30).mean() - 1) * 100

    hi52 = w["High"].cummax()  # cache holds ≤ 52 weeks, so running max = 52-week high
    chg = c.diff()
    up_v = v.where(chg > 0, 0).rolling(10).sum()
    dn_v = v.where(chg < 0, 0).rolling(10).sum()

    out["stage2"] = out["stage"] == 2
    out["above_ma30"] = c > out["ma30"]
    out["ma30_rising"] = out["slope"] > 0
    out["above_ma10"] = c > out["ma10"]
    out["ma10_over_ma30"] = out["ma10"] > out["ma30"]
    out["rs_positive"] = out["mansfield"] > 0
    out["rs_rising"] = rs > rs.shift(13)
    out["near_high"] = c >= 0.85 * hi52
    out["accumulation"] = up_v > dn_v
    out["ret_26w"] = c > c.shift(26)
    keys = [k for k, *_ in TREND_CHECKS]
    out["score"] = out[keys].sum(axis=1).where(out["stage"].notna())
    out["hi52"] = hi52
    return out


def daily_extension(df: pd.DataFrame) -> dict:
    h, l, c = df["High"], df["Low"], df["Close"]
    atr14 = atr(h, l, c, 14)
    s50 = sma(c, 50)
    last_atr, last_close = float(atr14.iloc[-1]), float(c.iloc[-1])
    return {
        "atr": _num(last_atr),
        "atr_pct": _num(last_atr / last_close) if last_close else None,
        "atr_ext": _num((last_close - float(s50.iloc[-1])) / last_atr) if last_atr else None,
        "sma50": _num(s50.iloc[-1]),
    }


def _ret(series: pd.Series, n: int) -> float | None:
    s = series.dropna()
    if len(s) <= n or not s.iloc[-1 - n]:
        return None
    return _num(s.iloc[-1] / s.iloc[-1 - n] - 1)


def stage_label(stage) -> str:
    return "N/A" if stage is None or pd.isna(stage) else f"Stage {int(stage)} · {STAGE_NAMES[int(stage)]}"


def summarize(symbol: str, name: str, sector: str, df: pd.DataFrame, weekly: pd.DataFrame, bench: pd.Series) -> dict | None:
    """One screen row for the latest bar; None until the 30-week SMA has a 4-week slope."""
    if len(weekly) < 2 or pd.isna(weekly["stage"].iloc[-1]):
        return None
    last, prev = weekly.iloc[-1], weekly.iloc[-2]
    close, prev_close = float(df["Close"].iloc[-1]), float(df["Close"].iloc[-2])
    prev_stage = None if pd.isna(prev["stage"]) else int(prev["stage"])
    prev_score = None if pd.isna(prev["score"]) else int(prev["score"])
    bench_d = bench.reindex(df.index).ffill()
    ret_13w, ret_26w = _ret(df["Close"], 63), _ret(df["Close"], 126)
    b13, b26 = _ret(bench_d, 63), _ret(bench_d, 126)
    rel_13w = None if ret_13w is None or b13 is None else ret_13w - b13
    rel_26w = None if ret_26w is None or b26 is None else ret_26w - b26
    rs_raw = None if rel_13w is None else rel_13w * 0.6 + (rel_26w if rel_26w is not None else rel_13w) * 0.4
    stage = int(last["stage"])
    return {
        "symbol": symbol,
        "name": name,
        "sector": sector,
        "as_of": df.index[-1].strftime("%Y-%m-%d"),
        "price": round(close, 2),
        "change_pct": _num(close / prev_close - 1),
        "stage": stage,
        "stage_name": STAGE_NAMES[stage],
        "prev_stage": prev_stage,
        "new_stage": prev_stage is not None and prev_stage != stage,
        "weeks": int(last["weeks"]),
        "weeks_capped": bool(weekly["stage"].notna().idxmax() == weekly.index[-int(last["weeks"])]),
        "score": int(last["score"]),
        "score_delta": None if prev_score is None else int(last["score"]) - prev_score,
        "checks": [k for k, *_ in TREND_CHECKS if bool(last[k])],
        "mansfield": _num(last["mansfield"]),
        "ma30_slope": _num(last["slope"]),
        "pct_from_ma30": _num(close / float(last["ma30"]) - 1),
        "pct_from_high": _num(close / max(float(last["hi52"]), close) - 1),
        "ret_1w": _ret(df["Close"], 5),
        "ret_13w": ret_13w,
        "ret_26w": ret_26w,
        "rel_13w": _num(rel_13w),
        "rs_raw": _num(rs_raw),
        **{k: v for k, v in daily_extension(df).items() if k != "sma50"},
    }


def _percentile(values: dict[str, float | None]) -> dict[str, int | None]:
    """1…99 percentile rank, higher value → higher percentile."""
    ranked = sorted((v, k) for k, v in values.items() if v is not None)
    n = len(ranked)
    out: dict[str, int | None] = {k: None for k in values}
    for i, (_, k) in enumerate(ranked):
        out[k] = 99 if n == 1 else int(round(1 + 98 * i / (n - 1)))
    return out


def rank_industries(rows: list[dict]) -> list[dict]:
    """Industries ranked by average 13-week return relative to the benchmark.

    Sets rs_pct (stock vs Nasdaq-100), ind_pct and ind_rank on each row in place.
    """
    for sym, pct in _percentile({r["symbol"]: r["rs_raw"] for r in rows}).items():
        next(r for r in rows if r["symbol"] == sym)["rs_pct"] = pct

    groups: dict[str, list[dict]] = {}
    for row in rows:
        groups.setdefault(row["sector"], []).append(row)

    def avg(members, key):
        vals = [m[key] for m in members if m[key] is not None]
        return sum(vals) / len(vals) if vals else None

    industries = []
    for sector, members in groups.items():
        members.sort(key=lambda r: (-(r["rs_pct"] or 0), r["symbol"]))
        stages = [m["stage"] for m in members]
        industries.append({
            "industry": sector,
            "members": len(members),
            "rel_13w": avg(members, "rel_13w"),
            "avg_score": round(avg(members, "score") or 0, 2),
            "avg_mansfield": avg(members, "mansfield"),
            "ret_1w": avg(members, "ret_1w"),
            "ret_13w": avg(members, "ret_13w"),
            "stage_counts": {str(s): stages.count(s) for s in (1, 2, 3, 4)},
            "pct_stage2": stages.count(2) / len(stages),
            "leaders": [{"symbol": m["symbol"], "stage": m["stage"], "rs_pct": m["rs_pct"]} for m in members[:4]],
        })
    pcts = _percentile({i["industry"]: i["rel_13w"] for i in industries})
    for ind in industries:
        ind["ind_pct"] = pcts[ind["industry"]]
    industries.sort(key=lambda i: -(i["ind_pct"] or 0))
    for rank, ind in enumerate(industries, start=1):
        ind["rank"] = rank
        for m in groups[ind["industry"]]:
            m["ind_pct"], m["ind_rank"] = ind["ind_pct"], rank
    return industries


def tags(row: dict) -> list[str]:
    out = []
    if row["new_stage"] and row["stage"] == 2:
        out.append("New Stage 2")
    if row["new_stage"] and row["stage"] == 4:
        out.append("New Stage 4")
    if row["pct_from_high"] is not None and row["pct_from_high"] >= -0.05:
        out.append("Near 52W high")
    if row["atr_ext"] is not None and row["atr_ext"] > EXTENDED_ATR:
        out.append("Extended")
    if row["stage"] == 2 and row["pct_from_ma30"] is not None and row["pct_from_ma30"] <= 0.05:
        out.append("Near 30W support")
    if (row.get("rs_pct") or 0) >= 90:
        out.append("RS leader")
    if "accumulation" in row["checks"]:
        out.append("Accumulation")
    return out


def stage_counts(rows: list[dict]) -> dict[str, int]:
    return {str(s): sum(r["stage"] == s for r in rows) for s in (1, 2, 3, 4)}


def check_details(weekly: pd.DataFrame) -> list[dict]:
    last = weekly.iloc[-1]
    return [{"key": k, "label": label, "description": d, "passed": bool(last[k])} for k, label, d in TREND_CHECKS]


def stage_history(weekly: pd.DataFrame) -> list[dict]:
    """Contiguous stage segments, oldest first."""
    seg: list[dict] = []
    for idx, stage in weekly["stage"].dropna().items():
        d = idx.strftime("%Y-%m-%d")
        if seg and seg[-1]["stage"] == int(stage):
            seg[-1]["end"], seg[-1]["weeks"] = d, seg[-1]["weeks"] + 1
        else:
            seg.append({"stage": int(stage), "name": STAGE_NAMES[int(stage)], "start": d, "end": d, "weeks": 1})
    return seg


def chart_points(weekly: pd.DataFrame) -> list[dict]:
    return [
        {
            "date": idx.strftime("%Y-%m-%d"),
            **{k: _num(row[k]) for k in ("open", "high", "low", "close", "volume", "ma10", "ma30", "mansfield")},
            "stage": None if pd.isna(row["stage"]) else int(row["stage"]),
        }
        for idx, row in weekly.iterrows()
    ]
