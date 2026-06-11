"""IBKR TWS Socket API service via ib_insync.

Connects to TWS on port 7496 (live) / 7497 (paper trading).
Uses on-demand snapshot requests instead of persistent streaming subscriptions
to stay within the account's simultaneous market-data line limit.

Architecture:
  - ib_insync IB client in asyncio mode (connectAsync)
  - qualifyContractsAsync to resolve symbols → conIds in batches
  - reqTickersAsync in batches of SNAPSHOT_BATCH — each batch requests snapshots,
    waits for data, then releases the lines before starting the next batch.
    At most SNAPSHOT_BATCH lines are open simultaneously (default 50).
  - Background poll loop repeats every POLL_INTERVAL seconds.
"""

import asyncio
import logging
from typing import Optional

from ib_insync import IB, Stock, Ticker

from config import settings
from data.tickers import ALL_TICKERS, IBKR_SYMBOL_MAP

log = logging.getLogger(__name__)

POLL_INTERVAL   = 30   # seconds between full snapshot cycles
# Keep simultaneous IBKR market-data lines well below TWS limits.
# reqTickersAsync opens one market-data line per contract; cancel only happens
# after all data arrives, so TWS can see SNAPSHOT_BATCH lines open at once.
# With 103 symbols across 4 batches of 25, peak is 25 lines at any moment.
SNAPSHOT_BATCH  = 10   # max simultaneous market-data lines per batch
_QUALIFY_BATCH  = 10   # contracts per qualifyContractsAsync call
# Pause between snapshot batches — gives TWS time to fully process cancellations
# from the previous batch before the next one opens.
_BATCH_PAUSE    = 2.0  # seconds between snapshot batches

# ── Shared state ──────────────────────────────────────────────────────────────
_ib: IB = IB()
_quote_cache: dict[str, dict] = {}
_contracts:   dict[str, Stock] = {}   # sym -> qualified contract
_connected    = False
_poll_task: Optional[asyncio.Task] = None
_snapshot_lock: asyncio.Lock | None = None
_connect_lock: asyncio.Lock | None = None


# ── Public API ────────────────────────────────────────────────────────────────

def is_connected() -> bool:
    return _connected and _ib.isConnected()


def get_all_quotes() -> dict[str, dict]:
    return dict(_quote_cache)


def get_ib() -> IB:
    return _ib


def get_contracts() -> dict:
    return dict(_contracts)


def _get_snapshot_lock() -> asyncio.Lock:
    global _snapshot_lock
    if _snapshot_lock is None:
        _snapshot_lock = asyncio.Lock()
    return _snapshot_lock


def _get_connect_lock() -> asyncio.Lock:
    global _connect_lock
    if _connect_lock is None:
        _connect_lock = asyncio.Lock()
    return _connect_lock


async def refresh_quotes(symbols: list[str] | None = None) -> int:
    """Force an immediate IBKR snapshot refresh for selected symbols.

    Returns the number of symbols with cached quote rows after the refresh.
    """
    if not is_connected():
        return 0

    requested = [sym.strip().upper() for sym in symbols or _contracts.keys() if sym.strip()]
    requested = list(dict.fromkeys(requested))
    pairs = [(sym, _contracts[sym]) for sym in requested if sym in _contracts]
    if not pairs:
        return 0

    async with _get_snapshot_lock():
        for i in range(0, len(pairs), SNAPSHOT_BATCH):
            batch = pairs[i : i + SNAPSHOT_BATCH]
            batch_syms = [sym for sym, _ in batch]
            batch_cons = [contract for _, contract in batch]
            try:
                tickers = await _ib.reqTickersAsync(*batch_cons, regulatorySnapshot=False)
                for sym, ticker in zip(batch_syms, tickers):
                    _update_cache_from_ticker(sym, ticker)
            except Exception as exc:
                log.debug("Forced snapshot batch error: %s", exc)
            if i + SNAPSHOT_BATCH < len(pairs):
                await asyncio.sleep(_BATCH_PAUSE)

        missing = [(sym, contract) for sym, contract in pairs if sym not in _quote_cache]
        for sym, contract in missing:
            await _update_cache_from_latest_daily_bar(sym, contract)

    return sum(1 for sym, _ in pairs if sym in _quote_cache)


async def connect() -> bool:
    """Connect to TWS, qualify contracts, start snapshot poll loop."""
    global _connected, _poll_task

    async with _get_connect_lock():
        try:
            if is_connected() and _contracts:
                return True

            if _ib.isConnected():
                _ib.disconnect()

            await _ib.connectAsync(
                settings.tws_host,
                settings.tws_port,
                clientId=settings.tws_client_id,
                readonly=True,
            )

            await _resolve_contracts()

            if not _contracts:
                log.warning("No contracts qualified — IBKR quotes unavailable")
                _ib.disconnect()
                return False

            # Use delayed IBKR market data so accounts without live subscriptions
            # still populate scanner prices through TWS.
            # 1=live, 2=frozen, 3=delayed, 4=delayed-frozen.
            _ib.reqMarketDataType(3)

            _connected = True
            if _poll_task is None or _poll_task.done():
                _poll_task = asyncio.create_task(_poll_loop())

            log.info(
                "IBKR TWS connected (port %d) · delayed market data · "
                "%d/%d contracts qualified · snapshot batch=%d interval=%ds",
                settings.tws_port, len(_contracts), len(ALL_TICKERS),
                SNAPSHOT_BATCH, POLL_INTERVAL,
            )
            return True

        except Exception as exc:
            log.warning("IBKR TWS connect error: %s", exc)
            return False


async def disconnect() -> None:
    global _connected, _poll_task
    _connected = False
    if _poll_task and not _poll_task.done():
        _poll_task.cancel()
        try:
            await _poll_task
        except asyncio.CancelledError:
            pass
    if _ib.isConnected():
        _ib.disconnect()


# ── Contract resolution ───────────────────────────────────────────────────────

async def _resolve_contracts() -> None:
    global _contracts
    _contracts = {}

    syms = list(ALL_TICKERS)
    raw  = [Stock(IBKR_SYMBOL_MAP.get(s, s), "SMART", "USD") for s in syms]

    for i in range(0, len(syms), _QUALIFY_BATCH):
        batch_syms = syms[i : i + _QUALIFY_BATCH]
        batch_raw  = raw[i : i + _QUALIFY_BATCH]
        try:
            qualified = await _ib.qualifyContractsAsync(*batch_raw)
            for sym, c in zip(batch_syms, qualified):
                if c.conId:
                    _contracts[sym] = c
        except Exception:
            # Fall back to individual qualification for failed batch
            for sym, c in zip(batch_syms, batch_raw):
                try:
                    q = await _ib.qualifyContractsAsync(c)
                    if q and q[0].conId:
                        _contracts[sym] = q[0]
                except Exception as exc:
                    log.debug("qualify %s: %s", sym, exc)
        # Pause between qualification batches so we don't flood TWS
        # at startup (each qualifyContractsAsync fires N reqContractDetails calls)
        await asyncio.sleep(1.0)

    log.info("Contracts qualified: %d/%d", len(_contracts), len(syms))


# ── Background poll loop (snapshot-based) ─────────────────────────────────────

async def _poll_loop() -> None:
    """Fetch market-data snapshots in batches, then sleep POLL_INTERVAL."""
    global _connected

    syms = list(_contracts.keys())
    cons = list(_contracts.values())
    total_batches = (len(cons) + SNAPSHOT_BATCH - 1) // SNAPSHOT_BATCH

    log.info(
        "IBKR poll loop started — %d contracts, %d batches of %d, interval %ds",
        len(cons), total_batches, SNAPSHOT_BATCH, POLL_INTERVAL,
    )

    while _connected:
        try:
            if not _ib.isConnected():
                log.warning("IBKR TWS connection lost")
                _connected = False
                break

            for i in range(0, len(cons), SNAPSHOT_BATCH):
                if not _connected:
                    break

                batch_syms = syms[i : i + SNAPSHOT_BATCH]
                batch_cons = cons[i : i + SNAPSHOT_BATCH]
                batch_num  = i // SNAPSHOT_BATCH + 1

                try:
                    tickers = await _ib.reqTickersAsync(
                        *batch_cons, regulatorySnapshot=False
                    )
                    for sym, ticker in zip(batch_syms, tickers):
                        _update_cache_from_ticker(sym, ticker)
                    log.debug(
                        "Snapshot batch %d/%d complete (%d symbols, max %d simultaneous)",
                        batch_num, total_batches, len(batch_syms), SNAPSHOT_BATCH,
                    )
                except Exception as exc:
                    log.debug("Snapshot batch %d error: %s", batch_num, exc)

                # Pause between batches: gives TWS time to fully process
                # cancellations from the previous batch before new lines open.
                if i + SNAPSHOT_BATCH < len(cons):
                    await asyncio.sleep(_BATCH_PAUSE)

            await asyncio.sleep(POLL_INTERVAL)

        except asyncio.CancelledError:
            break
        except Exception as exc:
            log.warning("IBKR poll error: %s", exc)
            _connected = False
            break

    log.info("IBKR poll loop stopped")


def _update_cache_from_ticker(sym: str, ticker: Ticker) -> None:
    bid   = _pf(ticker.bid)
    ask   = _pf(ticker.ask)
    last  = _pf(ticker.last)
    close = _pf(ticker.close)
    market_price = _pf(ticker.marketPrice()) if hasattr(ticker, "marketPrice") else None

    price = ((bid + ask) / 2) if (bid and ask) else last or market_price or close

    # Skip if no price data arrived yet (ib_insync uses NaN as uninitialised sentinel).
    if price is None:
        return

    change = change_pct = None
    if price and close:
        change     = round(price - close, 2)
        change_pct = round((change / close) * 100, 2)

    _quote_cache[sym] = {
        "symbol":     sym,
        "price":      price,
        "bid":        bid,
        "ask":        ask,
        "last":       last,
        "close":      close,
        "change":     change,
        "change_pct": change_pct,
        "volume":     _pi(ticker.volume),
        "iv_rank":    None,
        "hv30":       None,
        "source":     "ibkr",
    }


async def _update_cache_from_latest_daily_bar(sym: str, contract: Stock) -> None:
    """Use IBKR daily bars when live snapshot fields are unavailable."""
    try:
        bars = await _ib.reqHistoricalDataAsync(
            contract,
            endDateTime="",
            durationStr="1 M",
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,
        )
    except Exception as exc:
        log.debug("Historical quote fallback %s: %s", sym, exc)
        return

    clean = [bar for bar in bars if _pf(bar.close) is not None]
    if not clean:
        return

    latest = clean[-1]
    previous = clean[-2] if len(clean) >= 2 else None
    price = _pf(latest.close)
    prior_close = _pf(previous.close) if previous else None
    if price is None:
        return

    change = change_pct = None
    if prior_close:
        change = round(price - prior_close, 2)
        change_pct = round((change / prior_close) * 100, 2)

    _quote_cache[sym] = {
        "symbol":     sym,
        "price":      price,
        "bid":        None,
        "ask":        None,
        "last":       price,
        "close":      prior_close,
        "change":     change,
        "change_pct": change_pct,
        "volume":     _pi(latest.volume),
        "iv_rank":    None,
        "hv30":       None,
        "source":     "ibkr_historical",
    }


# ── Value parsers ─────────────────────────────────────────────────────────────

def _pf(val) -> Optional[float]:
    """Convert ib_insync float field (may be NaN sentinel) to float or None."""
    if val is None:
        return None
    try:
        f = float(val)
        return None if f != f else f  # f != f is True only for NaN
    except (ValueError, TypeError):
        return None


def _pi(val) -> Optional[int]:
    f = _pf(val)
    return int(f) if f is not None else None
