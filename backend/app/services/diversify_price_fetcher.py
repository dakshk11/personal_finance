"""Historical monthly price fetcher for the Diversification backtest.

Primary source: Alpha Vantage TIME_SERIES_MONTHLY_ADJUSTED
  - One API call per symbol returns full history (years of data)
  - Free tier: 25 calls/day, 5 calls/minute
  - With disk cache: first run costs ≤26 credits, every subsequent run costs 0
  - Endpoint: https://www.alphavantage.co/query?function=TIME_SERIES_MONTHLY_ADJUSTED
              &symbol={SYM}&apikey={KEY}

Caching:
  backend/app/services/diversify_price_cache/{SYMBOL}.json
  Refreshed once per calendar day. Cold fetch ~13s for 26 symbols (0.5s gap).
  Warm cache: < 0.01s for all 26.

Rate limiting:
  0.5s between requests = 2 req/s, well within the 5 req/min free tier limit.
  On a 429 or "limit reached" response the fetcher stops and returns what it has.
  The backtest still runs on whatever symbols were fetched successfully.
"""

from __future__ import annotations

import json
import logging
import ssl
import time
from datetime import date
from pathlib import Path
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import HTTPError

import certifi

log = logging.getLogger(__name__)

_CACHE_DIR   = Path(__file__).parent / "diversify_price_cache"
_REQUEST_GAP = 0.5    # seconds between AV requests (respects 5/min free limit)
_SSL_CTX     = ssl.create_default_context(cafile=certifi.where())
_AV_BASE     = "https://www.alphavantage.co/query"

_HEADERS = {
    "User-Agent": "FinanceOS/1.0",
    "Accept": "application/json",
}


# ── Cache helpers ─────────────────────────────────────────────────────────────

def _cache_path(symbol: str) -> Path:
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    return _CACHE_DIR / f"{symbol.upper()}.json"


def _load_cache(symbol: str) -> dict[str, float] | None:
    """Return today's cached prices, or None if stale/missing."""
    p = _cache_path(symbol)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text())
        if data.get("fetched") != date.today().isoformat():
            return None
        prices = data.get("prices")
        return prices if prices else None
    except Exception:
        return None


def _save_cache(symbol: str, prices: dict[str, float]) -> None:
    try:
        _cache_path(symbol).write_text(
            json.dumps({"fetched": date.today().isoformat(), "prices": prices})
        )
    except Exception as exc:
        log.debug("Cache write %s: %s", symbol, exc)


def cache_status() -> dict:
    """Return {symbol: fetched_date} for all cached symbols."""
    status = {}
    if _CACHE_DIR.exists():
        for p in _CACHE_DIR.glob("*.json"):
            try:
                data = json.loads(p.read_text())
                status[p.stem] = data.get("fetched", "unknown")
            except Exception:
                pass
    return status


# ── Alpha Vantage fetcher ─────────────────────────────────────────────────────

class _AvRateLimitError(Exception):
    """Raised when Alpha Vantage returns a rate-limit or credit-exhausted response."""


def _fetch_alphavantage(symbol: str, av_key: str) -> dict[str, float]:
    """Fetch monthly adjusted closes from Alpha Vantage.

    Returns {YYYY-MM-DD: adjusted_close}.
    Raises _AvRateLimitError when the daily limit is hit so the caller can stop.
    """
    url = (
        f"{_AV_BASE}?function=TIME_SERIES_MONTHLY_ADJUSTED"
        f"&symbol={symbol}&apikey={av_key}"
    )
    try:
        req = Request(url, headers=_HEADERS)
        with urlopen(req, timeout=15, context=_SSL_CTX) as resp:
            payload = json.load(resp)
    except HTTPError as exc:
        if exc.code == 429:
            raise _AvRateLimitError("Alpha Vantage HTTP 429") from exc
        log.debug("AV HTTP %s for %s", exc.code, symbol)
        return {}
    except Exception as exc:
        log.warning("AV request failed %s: %s", symbol, exc)
        return {}

    # Check for API error / rate-limit messages in the response body
    if "Note" in payload:
        # "Thank you for using Alpha Vantage! Our standard API rate limit is..."
        raise _AvRateLimitError(f"AV rate-limit note: {payload['Note'][:80]}")
    if "Information" in payload:
        raise _AvRateLimitError(f"AV limit info: {payload['Information'][:80]}")
    if "Error Message" in payload:
        log.warning("AV error for %s: %s", symbol, payload["Error Message"][:80])
        return {}

    series = payload.get("Monthly Adjusted Time Series", {})
    if not series:
        log.warning("AV returned no data for %s", symbol)
        return {}

    prices: dict[str, float] = {}
    for date_str, bar in series.items():
        adj_close = bar.get("5. adjusted close")
        if adj_close:
            try:
                prices[date_str] = round(float(adj_close), 4)
            except ValueError:
                pass

    log.debug("AV %s: %d monthly bars", symbol, len(prices))
    return prices


# ── Public API ────────────────────────────────────────────────────────────────

def fetch_monthly_prices(
    symbols: list[str],
    start_year: int,
    end_year: int,
    alpha_vantage_key: str | None = None,
) -> dict[str, dict[str, float]]:
    """Return {symbol: {YYYY-MM-DD: close}} for all symbols.

    Flow:
      1. Load from disk cache (free, instant)
      2. For cache misses: fetch from Alpha Vantage (requires api key)
      3. On rate-limit hit: stop and return what's available; log a warning

    Returns partial results if only some symbols were fetchable today.
    """
    result:   dict[str, dict[str, float]] = {}
    to_fetch: list[str] = []

    for sym in symbols:
        cached = _load_cache(sym)
        if cached is not None:
            result[sym] = cached
        else:
            to_fetch.append(sym)

    if not to_fetch:
        log.info(
            "Price cache warm: all %d symbols loaded from disk (0 API calls needed)",
            len(symbols),
        )
        return result

    log.info(
        "Price cache: %d/%d from disk, fetching %d via Alpha Vantage…",
        len(result), len(symbols), len(to_fetch),
    )

    if not alpha_vantage_key:
        log.warning(
            "No Alpha Vantage key provided — %d symbols cannot be fetched. "
            "Add your key on the Diversify page to enable the backtest.",
            len(to_fetch),
        )
        return result

    rate_limited = False
    fetched_count = 0

    for i, sym in enumerate(to_fetch):
        if i > 0:
            time.sleep(_REQUEST_GAP)

        try:
            prices = _fetch_alphavantage(sym, alpha_vantage_key)
        except _AvRateLimitError as exc:
            log.warning(
                "Alpha Vantage daily limit reached after %d symbols (%s). "
                "%d symbols remain unfetched — they will be loaded next run.",
                fetched_count, exc, len(to_fetch) - i,
            )
            rate_limited = True
            break

        if prices:
            # Filter to requested year range
            filtered = {
                d: v for d, v in prices.items()
                if start_year <= int(d[:4]) <= end_year
            }
            if filtered:
                result[sym] = filtered
                _save_cache(sym, filtered)
                fetched_count += 1
            else:
                log.debug("AV %s: no bars in %d-%d range", sym, start_year, end_year)
        else:
            log.warning("No data for %s — will retry on next run", sym)

    log.info(
        "Prices ready: %d/%d symbols have data%s",
        len(result),
        len(symbols),
        " (daily limit hit — run again tomorrow for remaining symbols)" if rate_limited else "",
    )
    return result


def get_price_at(
    prices: dict[str, dict[str, float]],
    symbol: str,
    target_date: date,
) -> Optional[float]:
    """Return the closest available monthly close at or before target_date."""
    sym_prices = prices.get(symbol)
    if not sym_prices:
        return None
    target_str = target_date.isoformat()
    candidates = {d: v for d, v in sym_prices.items() if d <= target_str}
    if not candidates:
        return None
    return candidates[max(candidates.keys())]
