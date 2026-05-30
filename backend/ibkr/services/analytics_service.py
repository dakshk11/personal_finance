"""Technical analytics: RSI(14) and Bollinger Band %(20) from IBKR daily bars.

Fetches 30 days of daily OHLCV bars for each qualified contract via
ib_insync reqHistoricalDataAsync, then computes:
  - RSI(14)  — momentum oscillator; signal when ≤ 40 (oversold)
  - BB%(20)  — position within Bollinger Bands; signal when ≤ 20% (lower band)

Results are cached in _cache and merged into watchlist rows by main.py.
"""

import asyncio
import logging
import math
from typing import Optional

log = logging.getLogger(__name__)

# sym → {"rsi": float|None, "bb_pct": float|None}
_cache: dict[str, dict] = {}


def get_analytics(symbol: str) -> dict:
    return _cache.get(symbol, {})


def get_all_analytics() -> dict:
    return dict(_cache)


# ── Math helpers ──────────────────────────────────────────────────────────────

def _rsi(closes: list[float], period: int = 14) -> Optional[float]:
    if len(closes) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(closes)):
        d = closes[i] - closes[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    avg_g = sum(gains[-period:]) / period
    avg_l = sum(losses[-period:]) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return round(100 - 100 / (1 + rs), 1)


def _bb_pct(closes: list[float], period: int = 20) -> Optional[float]:
    """Position within Bollinger Bands (0–100 %). ≤ 20 = near lower band."""
    if len(closes) < period:
        return None
    window = closes[-period:]
    mean = sum(window) / period
    std  = math.sqrt(sum((x - mean) ** 2 for x in window) / period)
    if std == 0:
        return 50.0
    upper = mean + 2 * std
    lower = mean - 2 * std
    pct = (closes[-1] - lower) / (upper - lower) * 100
    return round(max(0.0, min(100.0, pct)), 1)


# ── Main refresh coroutine ────────────────────────────────────────────────────

async def refresh(ib, contracts: dict) -> None:
    """Fetch 30-day daily bars for each contract and update _cache.

    Called by main.py after IBKR connects. Rate-limited to 5 concurrent
    requests so we don't exceed IBKR's historical-data pacing limits.
    """
    sem = asyncio.Semaphore(5)
    updated = 0

    async def _fetch_one(sym: str, contract) -> None:
        nonlocal updated
        async with sem:
            try:
                bars = await ib.reqHistoricalDataAsync(
                    contract,
                    endDateTime="",
                    durationStr="30 D",
                    barSizeSetting="1 day",
                    whatToShow="TRADES",
                    useRTH=True,
                )
                if not bars:
                    return
                closes = [bar.close for bar in bars]
                _cache[sym] = {
                    "rsi":    _rsi(closes),
                    "bb_pct": _bb_pct(closes),
                }
                updated += 1
            except Exception as exc:
                log.debug("Analytics %s: %s", sym, exc)
            await asyncio.sleep(0.2)   # gentle pacing

    await asyncio.gather(*[_fetch_one(s, c) for s, c in contracts.items()])
    log.info("Analytics refreshed: RSI/BB%% computed for %d/%d symbols", updated, len(contracts))
