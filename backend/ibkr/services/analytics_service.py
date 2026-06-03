"""Technical analytics: RSI(14), Bollinger Band %(20), and Stan Weinstein Stage Analysis.

Fetches 1 year of daily OHLCV bars for each qualified contract via
ib_insync reqHistoricalDataAsync, then computes:

  - RSI(14)      — momentum oscillator; signal when ≤ 40 (oversold)
  - BB%(20)      — position within Bollinger Bands; signal when ≤ 20% (lower band)
  - SATA score   — Stage Analysis Technical Attributes (0–10)
  - Stage (1–4)  — Stan Weinstein stage (Basing / Advancing / Topping / Declining)
  - Mansfield RS — relative strength vs SPX normalized to zero line

Stage Analysis (Stan Weinstein):
  Stage 1 – Basing:    score 3–6, 150d MA flat after decline, price oscillating around MA
  Stage 2 – Advancing: score 7–10, price above rising 150d MA, RS positive
  Stage 3 – Topping:   score 3–6, 150d MA flat after advance, erratic price action
  Stage 4 – Declining: score 0–3, price below falling 150d MA, RS negative

SATA 10 Attributes (each worth 1 point):
  [1]  Breakout/Breakdown signal
  [2]  Price > 150-day MA (30-week)
  [3]  150-day MA slope rising
  [4]  Price > 200-day MA (40-week)
  [5]  Price > 65-day MA (13-week)
  [6]  Mansfield RS > 0 (outperforming SPX on 52-week normalized basis)
  [7]  RSI(14) > 50
  [8]  Higher highs pattern (20-day high > prior 20-day high)
  [9]  Volume confirmation (avg up-day vol > avg down-day vol, 60-day window)
  [10] Low overhead resistance (price within 25% of 52-week high)
"""

import asyncio
import logging
import math
from datetime import date as _date, datetime as _datetime
from pathlib import Path
from typing import Optional

import pandas as pd
from ib_insync import Stock

log = logging.getLogger(__name__)

# OHLCV pickle cache for breakout scanner (one file per symbol, refreshed daily)
OHLCV_CACHE_DIR = Path(__file__).parent.parent / "data" / "history"

# sym → {"rsi", "bb_pct", "stage", "sata_score", "sata_attributes"}
_cache: dict[str, dict] = {}

# SPX closes (SPY ETF used as benchmark for Mansfield RS)
_spx_closes: list[float] = []

# Lock to prevent concurrent refresh() calls (e.g. from multiple reconnect-triggered tasks)
_refresh_lock: asyncio.Lock | None = None


def _get_refresh_lock() -> asyncio.Lock:
    """Return the module-level refresh lock, creating it lazily on first call.

    The Lock must be created inside a running event loop, so we can't create it
    at module import time — hence the lazy initialisation pattern.
    """
    global _refresh_lock
    if _refresh_lock is None:
        _refresh_lock = asyncio.Lock()
    return _refresh_lock


def get_analytics(symbol: str) -> dict:
    return _cache.get(symbol, {})


def get_all_analytics() -> dict:
    return dict(_cache)


def compute_from_bars(closes: list[float], volumes: list[float]) -> dict:
    """Compute the same analytics shape for an on-demand custom symbol."""
    sata_score, stage, sata_attrs = _compute_sata(closes, volumes, _spx_closes)
    mansfield = _mansfield_rs(closes, _spx_closes) if _spx_closes else None
    return {
        "rsi":             _rsi(closes),
        "bb_pct":          _bb_pct(closes),
        "stage":           stage,
        "sata_score":      sata_score,
        "sata_attributes": sata_attrs,
        "mansfield_rs":    mansfield,
        "ma150":           _last_sma(closes, 150),
        "ma200":           _last_sma(closes, 200),
    }


# ── Moving averages ───────────────────────────────────────────────────────────

def _sma(values: list[float], period: int) -> list[float]:
    """Return list of SMA values (same length as input, None-padded at start)."""
    result: list[Optional[float]] = [None] * len(values)
    for i in range(period - 1, len(values)):
        result[i] = sum(values[i - period + 1 : i + 1]) / period
    return result  # type: ignore[return-value]


def _last_sma(values: list[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return sum(values[-period:]) / period


# ── RSI(14) ───────────────────────────────────────────────────────────────────

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
    return round(100 - 100 / (1 + avg_g / avg_l), 1)


# ── Bollinger Band % ──────────────────────────────────────────────────────────

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


# ── Mansfield Relative Strength ───────────────────────────────────────────────

def _mansfield_rs(stock_closes: list[float], spx_closes: list[float]) -> Optional[float]:
    """Mansfield RS oscillator normalised to zero line.

    Formula:
      ratio      = stock_close / spx_close  (daily, aligned by length)
      rs_line    = ratio (raw)
      zero_line  = 52-week SMA of ratio
      mansfield  = (ratio / zero_line - 1) * 100   →  > 0 = outperforming
    """
    n = min(len(stock_closes), len(spx_closes))
    if n < 52 * 5:          # need ~260 trading days for a meaningful 52-week SMA
        return None

    stock = stock_closes[-n:]
    spx   = spx_closes[-n:]

    ratios = [s / b for s, b in zip(stock, spx) if b and b != 0]
    if len(ratios) < 52 * 5:
        return None

    zero_line = sum(ratios[-260:]) / 260        # 52-week SMA of ratio
    if zero_line == 0:
        return None

    current_ratio = ratios[-1]
    return round((current_ratio / zero_line - 1) * 100, 2)


# ── SATA: 10 attributes ───────────────────────────────────────────────────────

def _compute_sata(
    closes: list[float],
    volumes: list[float],
    spx_closes: list[float],
) -> tuple[int, int, dict]:
    """Compute SATA score (0–10), stage (1–4), and individual attribute dict.

    Returns (sata_score, stage, attributes).
    Each attribute is True (1 point) or False (0 points).
    """
    n = len(closes)
    if n < 65:
        # Not enough data — return unknown
        return 0, 0, {}

    price = closes[-1]

    # ── Moving averages ───────────────────────────────────────────────────────
    ma65  = _last_sma(closes, 65)          # 13-week
    ma150 = _last_sma(closes, 150)         # 30-week (core Weinstein MA)
    ma200 = _last_sma(closes, 200)         # 40-week

    # MA slope: compare current MA vs 20 bars ago
    ma150_now  = _last_sma(closes,       150)
    ma150_prev = _last_sma(closes[:-20], 150) if n >= 170 else None
    ma150_rising = (ma150_now is not None and ma150_prev is not None
                    and ma150_now > ma150_prev)

    # For Stage 1 vs 3 disambiguation: was price above MA 40-80 bars ago?
    lookback_start = -min(80, n)
    lookback_end   = -min(40, n) if n > 40 else None
    if lookback_end:
        hist_closes = closes[lookback_start:lookback_end]
        hist_ma150  = _last_sma(closes[:lookback_end], 150)
        price_was_above_ma150 = (
            hist_ma150 is not None
            and len(hist_closes) > 0
            and sum(1 for c in hist_closes if c > hist_ma150) / len(hist_closes) > 0.6
        )
    else:
        price_was_above_ma150 = False

    # ── 52-week range ─────────────────────────────────────────────────────────
    year_window = closes[-260:] if n >= 260 else closes
    year_high   = max(year_window)

    # ── Volume up/down analysis (last 60 bars) ────────────────────────────────
    vol_window = min(60, len(volumes))
    up_vols, down_vols = [], []
    for i in range(1, vol_window):
        idx = -(vol_window - i)
        c_idx = idx if idx != 0 else -1
        if closes[c_idx] >= closes[c_idx - 1]:
            up_vols.append(volumes[c_idx])
        else:
            down_vols.append(volumes[c_idx])
    avg_up_vol   = sum(up_vols)   / len(up_vols)   if up_vols   else 0
    avg_down_vol = sum(down_vols) / len(down_vols) if down_vols else 0

    # ── Higher highs (20-bar comparison) ─────────────────────────────────────
    period_high_recent = max(closes[-20:])                     if n >= 20 else None
    period_high_prior  = max(closes[-40:-20]) if n >= 40 else None
    higher_highs = (period_high_recent is not None
                    and period_high_prior is not None
                    and period_high_recent > period_high_prior)

    # ── Breakout signal ───────────────────────────────────────────────────────
    # True if price crossed above 150d MA in last 5 bars, or broke prior 65d high
    breakout = False
    if ma150 and n >= 6:
        was_below = any(closes[-(i+2)] < ma150 for i in range(5) if n >= i + 3)
        now_above = price > ma150
        breakout = was_below and now_above
    if not breakout and n >= 70:
        prior_65d_high = max(closes[-70:-5])
        breakout = price > prior_65d_high

    # ── Mansfield RS ─────────────────────────────────────────────────────────
    mansfield = _mansfield_rs(closes, spx_closes) if spx_closes else None
    mansfield_positive = mansfield is not None and mansfield > 0

    # ── RSI ───────────────────────────────────────────────────────────────────
    rsi_val = _rsi(closes)
    rsi_positive = rsi_val is not None and rsi_val > 50

    # ── 10 SATA attributes (each True = 1 pt) ────────────────────────────────
    attrs = {
        "breakout":        breakout,
        "above_ma150":     ma150 is not None and price > ma150,
        "ma150_rising":    ma150_rising,
        "above_ma200":     ma200 is not None and price > ma200,
        "above_ma65":      ma65  is not None and price > ma65,
        "mansfield_pos":   mansfield_positive,
        "rsi_above_50":    rsi_positive,
        "higher_highs":    higher_highs,
        "volume_confirms": avg_up_vol > avg_down_vol,
        "no_overhead":     year_high > 0 and price >= year_high * 0.75,
    }

    sata_score = sum(1 for v in attrs.values() if v)

    # ── Stage determination ───────────────────────────────────────────────────
    stage = _determine_stage(sata_score, ma150_rising, price_was_above_ma150)

    return sata_score, stage, attrs


def _determine_stage(
    sata_score: int,
    ma150_rising: bool,
    price_was_above_ma150: bool,
) -> int:
    """Map SATA score + MA context → Weinstein Stage 1/2/3/4.

    Score 7–10 → Stage 2 (advancing)
    Score 0–3  → Stage 4 (declining)
    Score 4–6  → Stage 1 (basing, coming off decline) or Stage 3 (topping)
      - price was mostly above MA before flattening → Stage 3
      - price was mostly below MA before flattening → Stage 1
    """
    if sata_score >= 7:
        return 2
    if sata_score <= 3:
        return 4
    # Neutral zone 4–6: use prior trend direction
    return 3 if price_was_above_ma150 else 1


# ── SPX benchmark fetch ───────────────────────────────────────────────────────

async def _fetch_spx_closes(ib) -> list[float]:
    """Fetch 1 year of SPY daily closes to use as SPX benchmark for Mansfield RS."""
    try:
        spy = Stock("SPY", "SMART", "USD")
        qualified = await ib.qualifyContractsAsync(spy)
        if not qualified or not qualified[0].conId:
            log.warning("Could not qualify SPY contract for Mansfield RS")
            return []
        bars = await ib.reqHistoricalDataAsync(
            qualified[0],
            endDateTime="",
            durationStr="1 Y",
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,
        )
        closes = [bar.close for bar in bars] if bars else []
        log.info("SPY benchmark: %d daily bars fetched", len(closes))
        return closes
    except Exception as exc:
        log.warning("SPY fetch failed: %s", exc)
        return []


# ── Main refresh coroutine ────────────────────────────────────────────────────

async def refresh(ib, contracts: dict) -> None:
    """Fetch 1-year daily bars for each contract and update _cache.

    Computes RSI(14), BB%(20), SATA score, and Weinstein Stage for every symbol.
    Rate-limited to 3 concurrent requests to respect IBKR historical-data pacing.

    Protected by _refresh_lock — if called while already running (e.g. from a
    duplicate analytics task spawned by multiple IBKR reconnects), the second
    call exits immediately rather than stacking more IBKR requests.
    """
    lock = _get_refresh_lock()
    if lock.locked():
        log.warning("Analytics refresh already in progress — skipping duplicate call")
        return
    async with lock:
        await _do_refresh(ib, contracts)


async def _do_refresh(ib, contracts: dict) -> None:
    """Inner body of refresh() — always runs under _refresh_lock."""
    global _spx_closes

    # Fetch SPY benchmark first (needed for Mansfield RS)
    _spx_closes = await _fetch_spx_closes(ib)
    if not _spx_closes:
        log.warning("Mansfield RS will be skipped — SPY data unavailable")

    # IBKR pacing: max 50 historical-data requests per 30-second window
    BATCH_SIZE   = 50
    BATCH_WINDOW = 31.0   # seconds — 1s buffer over IBKR's 30s limit

    # Semaphore limits concurrent reqHistoricalDataAsync calls within a batch.
    # Combined with SNAPSHOT_BATCH=25 in ibkr_service, peak simultaneous IBKR
    # requests across all code paths stays below 35.
    sem     = asyncio.Semaphore(3)
    updated = 0

    async def _fetch_one(sym: str, contract) -> None:
        nonlocal updated
        async with sem:
            try:
                bars = await ib.reqHistoricalDataAsync(
                    contract,
                    endDateTime="",
                    durationStr="1 Y",
                    barSizeSetting="1 day",
                    whatToShow="TRADES",
                    useRTH=True,
                )
                if not bars or len(bars) < 20:
                    return

                # ── Persist full OHLCV for breakout scanner ───────────────
                try:
                    OHLCV_CACHE_DIR.mkdir(parents=True, exist_ok=True)
                    pkl_path = OHLCV_CACHE_DIR / f"{sym}.pkl"
                    needs_write = (
                        not pkl_path.exists()
                        or _datetime.fromtimestamp(pkl_path.stat().st_mtime).date() != _date.today()
                    )
                    if needs_write:
                        ohlcv_df = pd.DataFrame(
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
                        ohlcv_df.to_pickle(pkl_path)
                except Exception as _ohlcv_exc:
                    log.debug("OHLCV persist %s: %s", sym, _ohlcv_exc)
                # ─────────────────────────────────────────────────────────

                closes  = [bar.close  for bar in bars]
                volumes = [float(bar.volume) for bar in bars]

                sata_score, stage, sata_attrs = _compute_sata(closes, volumes, _spx_closes)
                mansfield = _mansfield_rs(closes, _spx_closes) if _spx_closes else None

                _cache[sym] = {
                    "rsi":             _rsi(closes),
                    "bb_pct":          _bb_pct(closes),
                    "stage":           stage,
                    "sata_score":      sata_score,
                    "sata_attributes": sata_attrs,
                    "mansfield_rs":    mansfield,
                    "ma150":           _last_sma(closes, 150),
                    "ma200":           _last_sma(closes, 200),
                }
                updated += 1
            except Exception as exc:
                log.debug("Analytics %s: %s", sym, exc)
            await asyncio.sleep(0.2)   # small per-request gap within a batch

    # ── Process in batches of 50, respecting IBKR's 50-req/30s limit ─────────
    items         = list(contracts.items())
    total_batches = (len(items) + BATCH_SIZE - 1) // BATCH_SIZE

    for batch_idx in range(total_batches):
        start = batch_idx * BATCH_SIZE
        batch = items[start : start + BATCH_SIZE]

        log.info(
            "Analytics batch %d/%d — fetching %d symbols…",
            batch_idx + 1, total_batches, len(batch),
        )
        t0 = asyncio.get_event_loop().time()

        await asyncio.gather(*[_fetch_one(s, c) for s, c in batch])

        # Enforce ≤50 requests per 30s: wait out the remainder of the window
        if batch_idx < total_batches - 1:
            elapsed   = asyncio.get_event_loop().time() - t0
            remaining = BATCH_WINDOW - elapsed
            if remaining > 0:
                log.info(
                    "Analytics pacing: batch done in %.1fs — waiting %.1fs before next batch",
                    elapsed, remaining,
                )
                await asyncio.sleep(remaining)

    log.info(
        "Analytics refreshed: RSI/BB%%/Stage computed for %d/%d symbols",
        updated, len(contracts),
    )
