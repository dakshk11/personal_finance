"""CBOE delayed options data service.

Uses the free CBOE CDN endpoint for 15-minute delayed option chains.

Caching strategy:
  - Daily disk cache: persisted to data/cboe_daily_cache.json.
    On startup the file is loaded into memory — restarts are instant.
    Entries are considered fresh for the whole calendar day they were fetched.
    Once midnight passes the stale file is ignored and symbols are re-fetched.
  - In-process LRU layer: _cache keeps the parsed chains so repeated calls
    within the same process never hit disk again.

Rate-limit strategy (for actual CBOE fetches):
  - Hard cap via asyncio-throttle: max 1 request/second globally
  - Exponential backoff with jitter on 429 (up to 4 retries)
  - Shared persistent httpx.AsyncClient (keep-alive, avoids TCP overhead)
"""

import asyncio
import json
import logging
import os
import random
import time
from datetime import date, datetime
from typing import Optional

import httpx
from asyncio_throttle import Throttler

from config import settings

log = logging.getLogger(__name__)

# ── Rate limiter ──────────────────────────────────────────────────────────────
_throttler = Throttler(rate_limit=1, period=1.0)

# ── Persistent async HTTP client ──────────────────────────────────────────────
_client: Optional[httpx.AsyncClient] = None

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.cboe.com/",
}

# ── Daily disk cache ──────────────────────────────────────────────────────────
_DAILY_CACHE_FILE = os.path.join(
    os.path.dirname(__file__), "..", "data", "cboe_daily_cache.json"
)

# ── In-process cache: symbol → (fetched_epoch, parsed_chain) ─────────────────
_cache: dict[str, tuple[float, list[dict]]] = {}


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(
            timeout=settings.cboe_timeout,
            headers=_HEADERS,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
        )
    return _client


# ── Disk cache helpers ────────────────────────────────────────────────────────

def load_daily_cache_from_disk() -> None:
    """Populate in-memory cache from today's disk file. Called at startup."""
    global _cache
    try:
        if not os.path.exists(_DAILY_CACHE_FILE):
            return
        with open(_DAILY_CACHE_FILE) as f:
            data = json.load(f)
        if data.get("date") != date.today().isoformat():
            log.info("CBOE daily cache is stale (dated %s) — will refetch today", data.get("date"))
            return
        chains = data.get("chains", {})
        now = time.time()
        for sym, chain in chains.items():
            _cache[sym] = (now, chain)
        log.info("CBOE daily cache loaded from disk: %d symbols", len(chains))
    except Exception as exc:
        log.debug("Could not load CBOE daily cache: %s", exc)


def _save_daily_cache_to_disk() -> None:
    """Persist current in-memory cache to the daily disk file."""
    try:
        chains = {sym: chain for sym, (_, chain) in _cache.items()}
        os.makedirs(os.path.dirname(_DAILY_CACHE_FILE), exist_ok=True)
        with open(_DAILY_CACHE_FILE, "w") as f:
            json.dump({"date": date.today().isoformat(), "chains": chains}, f)
    except Exception as exc:
        log.debug("Could not save CBOE daily cache: %s", exc)


def _is_cached_today(symbol: str) -> bool:
    """Return True if symbol has a cache entry from today (full-day freshness)."""
    cached = _cache.get(symbol)
    if not cached:
        return False
    return datetime.fromtimestamp(cached[0]).date() == date.today()


# ── Core fetch with retry ─────────────────────────────────────────────────────

async def _fetch(url: str) -> Optional[dict]:
    """Throttled GET with up to 4 retries and exponential back-off on 429."""
    for attempt in range(4):
        async with _throttler:
            try:
                resp = await _get_client().get(url)
            except Exception as exc:
                log.debug("CBOE network error %s: %s", url, exc)
                if attempt < 3:
                    await asyncio.sleep(2 ** attempt + random.random())
                continue

        if resp.status_code == 200:
            try:
                return resp.json()
            except Exception:
                return None

        if resp.status_code == 429:
            delay = min(30.0, (2 ** attempt) * 2 + random.uniform(0, 1))
            log.debug("CBOE 429 on %s – backing off %.1fs (attempt %d)", url, delay, attempt + 1)
            await asyncio.sleep(delay)
            continue

        log.debug("CBOE %s → HTTP %s", url, resp.status_code)
        return None

    log.warning("CBOE gave up after retries: %s", url)
    return None


# ── OCC symbol parser ─────────────────────────────────────────────────────────

def _parse_occ(occ: str) -> tuple[str, date, str, float]:
    """Parse CBOE OCC option symbol → (underlying, expiry, type, strike).

    CBOE emits the symbol WITHOUT padding the underlying to 6 chars, so the
    total length is variable (e.g. 'AAPL260527C00215000' = 19 chars).
    The last 15 characters are always: YYMMDD (6) + C/P (1) + strike×1000 (8).
    """
    if len(occ) < 16:
        raise ValueError(f"OCC symbol too short: {occ!r}")
    underlying = occ[:-15]
    expiry     = datetime.strptime(occ[-15:-9], "%y%m%d").date()
    opt_type   = occ[-9]
    strike     = int(occ[-8:]) / 1000.0
    return underlying, expiry, opt_type, strike


# ── Public API ────────────────────────────────────────────────────────────────

async def get_option_chain(symbol: str) -> list[dict]:
    """Return parsed option chain for *symbol*. Cached for the full trading day."""
    if _is_cached_today(symbol):
        return _cache[symbol][1]

    url     = f"{settings.cboe_base_url}/{symbol}.json"
    payload = await _fetch(url)
    if not payload:
        _cache[symbol] = (time.time(), [])
        return []

    raw_data      = payload.get("data", {})
    raw_options   = raw_data.get("options", [])
    current_price: Optional[float] = raw_data.get("current_price")
    today         = date.today()

    parsed: list[dict] = []
    for opt in raw_options:
        occ_sym: str = opt.get("option", "")
        if len(occ_sym) < 16:
            continue
        try:
            _, expiry, opt_type, strike = _parse_occ(occ_sym)
        except Exception:
            continue

        dte = (expiry - today).days
        if dte < 0:
            continue

        bid    = opt.get("bid") or 0.0
        ask    = opt.get("ask") or 0.0
        mid    = round((bid + ask) / 2, 2)
        iv     = opt.get("iv")
        delta  = opt.get("delta")
        gamma  = opt.get("gamma")
        theta  = opt.get("theta")
        vega   = opt.get("vega")
        oi     = opt.get("open_interest") or 0
        volume = opt.get("volume") or 0
        last   = opt.get("last_trade_price")

        raw_yield = ann_yield = None
        if mid > 0 and dte > 0:
            if opt_type == "P" and strike > 0:
                raw_yield = round((mid / strike) * 100, 3)
                ann_yield = round(raw_yield * (365 / dte), 2)
            elif opt_type == "C" and current_price and current_price > 0:
                raw_yield = round((mid / current_price) * 100, 3)
                ann_yield = round(raw_yield * (365 / dte), 2)

        pct_away = None
        if current_price and current_price > 0:
            pct_away = round(((strike - current_price) / current_price) * 100, 2)

        pop = round((1 - abs(delta)) * 100, 1) if delta is not None else None

        parsed.append({
            "symbol":           symbol,
            "occ_symbol":       occ_sym,
            "option_type":      opt_type,
            "expiry":           expiry.isoformat(),
            "dte":              dte,
            "strike":           strike,
            "bid":              bid,
            "ask":              ask,
            "mid":              mid,
            "last":             last,
            "iv":               round(iv * 100, 1) if iv else None,
            "delta":            round(delta, 3) if delta is not None else None,
            "gamma":            round(gamma, 4) if gamma is not None else None,
            "theta":            round(theta, 4) if theta is not None else None,
            "vega":             round(vega, 4) if vega is not None else None,
            "open_interest":    oi,
            "volume":           volume,
            "raw_yield":        raw_yield,
            "annualized_yield": ann_yield,
            "pct_away":         pct_away,
            "pop":              pop,
            "stock_price":      current_price,
            "capital_required": round(strike * 100, 2) if opt_type == "P" else None,
        })

    _cache[symbol] = (time.time(), parsed)
    _save_daily_cache_to_disk()   # persist after every new fetch
    return parsed


def find_30delta_metrics(symbol: str) -> dict:
    """From the in-memory cache, find the ~30Δ put/call nearest to 30 DTE.

    Returns {"csp_30d": annualized_yield|None, "cc_30d": annualized_yield|None}.
    Both values are the annualized premium yield expressed as a percentage.
    """
    cached = _cache.get(symbol)
    if not cached or not cached[1]:
        return {"csp_30d": None, "cc_30d": None}

    chain = cached[1]

    def _score_put(o: dict) -> float:
        dte_dist   = abs(o["dte"] - 30) / 30.0
        delta_dist = abs(abs(o["delta"]) - 0.30)
        return dte_dist + delta_dist * 2   # weight delta match more heavily

    def _score_call(o: dict) -> float:
        dte_dist   = abs(o["dte"] - 30) / 30.0
        delta_dist = abs(o["delta"] - 0.30)
        return dte_dist + delta_dist * 2

    puts  = [o for o in chain
             if o["option_type"] == "P"
             and o["delta"] is not None
             and o["annualized_yield"] is not None
             and 20 <= o["dte"] <= 50]

    calls = [o for o in chain
             if o["option_type"] == "C"
             and o["delta"] is not None
             and o["annualized_yield"] is not None
             and 20 <= o["dte"] <= 50]

    csp_30d = round(min(puts,  key=_score_put)["annualized_yield"],  2) if puts  else None
    cc_30d  = round(min(calls, key=_score_call)["annualized_yield"], 2) if calls else None

    return {"csp_30d": csp_30d, "cc_30d": cc_30d}


def get_atm_iv(symbol: str) -> Optional[float]:
    """Return the average IV of the two nearest-ATM options (proxy for IV rank)."""
    cached = _cache.get(symbol)
    if not cached or not cached[1]:
        return None
    chain = cached[1]
    # Use puts near 30 DTE with delta near 0.50 as ATM proxy
    atm = [o for o in chain
           if o["delta"] is not None
           and o["iv"] is not None
           and 20 <= o["dte"] <= 50
           and 0.40 <= abs(o["delta"]) <= 0.60]
    if not atm:
        return None
    return round(sum(o["iv"] for o in atm) / len(atm), 1)


async def get_options_batch(symbols: list[str]) -> dict[str, list[dict]]:
    """Fetch option chains for *symbols* concurrently (throttled globally)."""
    async def fetch_one(sym: str) -> tuple[str, list[dict]]:
        return sym, await get_option_chain(sym)

    tasks   = [asyncio.create_task(fetch_one(s)) for s in symbols]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    out: dict[str, list[dict]] = {}
    for r in results:
        if isinstance(r, Exception):
            log.debug("Batch fetch exception: %s", r)
            continue
        sym, chain = r
        out[sym] = chain
    return out


# Pre-load today's disk cache as soon as this module is imported
load_daily_cache_from_disk()
