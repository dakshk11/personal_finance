"""Technical indicators and resistance level detection."""

import numpy as np
import pandas as pd


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return s.ewm(span=n, adjust=False).mean()


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    tr = pd.concat(
        [high - low, (high - close.shift(1)).abs(), (low - close.shift(1)).abs()],
        axis=1,
    ).max(axis=1)
    return tr.ewm(span=n, adjust=False).mean()


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    delta = close.diff()
    up = delta.clip(lower=0).ewm(com=n - 1, adjust=False).mean()
    dn = (-delta.clip(upper=0)).ewm(com=n - 1, adjust=False).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def relative_volume(vol: pd.Series, n: int = 20) -> pd.Series:
    avg = vol.rolling(n).mean()
    return vol / avg.replace(0, np.nan)


def consolidation_ratio(high: pd.Series, low: pd.Series, close: pd.Series, recent: int = 10, base: int = 30) -> float:
    """Ratio of recent ATR to base ATR. < 0.75 means price was coiling."""
    atr_vals = atr(high, low, close)
    if len(atr_vals) < base + recent:
        return 1.0
    recent_atr = atr_vals.iloc[-recent:].mean()
    base_atr = atr_vals.iloc[-(base + recent) : -recent].mean()
    if base_atr == 0 or np.isnan(base_atr):
        return 1.0
    return float(recent_atr / base_atr)


def find_pivot_highs(high: pd.Series, wing: int = 4) -> list[float]:
    """Return prices at which high is a local maximum over ±wing bars."""
    pivots = []
    arr = high.values
    for i in range(wing, len(arr) - wing):
        window = arr[i - wing : i + wing + 1]
        if arr[i] == window.max() and np.sum(window == arr[i]) == 1:
            pivots.append(float(arr[i]))
    return pivots


def find_resistance_levels(
    high: pd.Series,
    close: pd.Series,
    lookback: int = 126,
    cluster_pct: float = 0.015,
    min_tests: int = 2,
    wing: int = 4,
) -> list[tuple[float, int]]:
    """
    Find resistance zones that were tested ≥ min_tests times in the last `lookback` bars.
    Returns list of (price_level, test_count) sorted by test_count descending.

    A resistance level is a cluster of pivot highs — the stock reached that price
    multiple times but pulled back each time, making it a meaningful ceiling.
    """
    h = high.iloc[-lookback:]
    pivots = find_pivot_highs(h, wing=wing)

    if not pivots:
        return []

    clusters: list[dict] = []
    for p in sorted(pivots, reverse=True):
        placed = False
        for c in clusters:
            if abs(p - c["price"]) / c["price"] <= cluster_pct:
                c["price"] = (c["price"] * c["count"] + p) / (c["count"] + 1)
                c["count"] += 1
                placed = True
                break
        if not placed:
            clusters.append({"price": p, "count": 1})

    result = [(c["price"], c["count"]) for c in clusters if c["count"] >= min_tests]
    return sorted(result, key=lambda x: x[1], reverse=True)
