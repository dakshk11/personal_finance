from __future__ import annotations

import asyncio
import json
import secrets
import ssl
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import certifi
import websockets

from app.services.market_data import fetch_yahoo_quote_snapshots, normalize_symbol


ALPACA_MAX_EQUITY_SYMBOLS = 30
ALPACA_MAX_OPTION_QUOTES = 200
ALPACA_EQUITY_REST_URL = "https://data.alpaca.markets/v2/stocks/quotes/latest"
ALPACA_EQUITY_STREAM_URL = "wss://stream.data.alpaca.markets/v2/iex"
ALPACA_OPTION_STREAM_URL = "wss://stream.data.alpaca.markets/v1beta1/opra"
QUOTE_SESSION_TTL_SECONDS = 10 * 60

_CBOE_BASE_URL = "https://cdn.cboe.com/api/global/delayed_quotes/options"
_CBOE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json",
    "Referer": "https://www.cboe.com/",
}
_OPTION_CHAIN_CACHE: dict[str, tuple[date, list[dict[str, Any]]]] = {}
_QUOTE_SESSIONS: dict[str, "AlpacaQuoteSession"] = {}
_ALPACA_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
_WHEEL_CBOE_CACHE_PATH = Path(__file__).resolve().parents[2] / "ibkr" / "data" / "cboe_daily_cache.json"


@dataclass
class AlpacaQuoteSession:
    token: str
    user_id: int
    api_key: str
    api_secret: str
    symbols: list[str]
    option_contracts: list[str]
    snapshot: dict[str, Any]
    expires_at: float


def normalize_equity_symbols(raw_symbols: list[str]) -> tuple[list[str], list[str]]:
    accepted: list[str] = []
    rejected: list[str] = []
    seen: set[str] = set()
    for raw in raw_symbols:
        symbol = normalize_symbol(str(raw).strip())
        if not symbol or len(symbol) > 12 or not symbol.replace(".", "").replace("-", "").isalnum():
            if str(raw).strip():
                rejected.append(str(raw).strip().upper())
            continue
        if symbol in seen:
            continue
        seen.add(symbol)
        if len(accepted) >= ALPACA_MAX_EQUITY_SYMBOLS:
            rejected.append(symbol)
            continue
        accepted.append(symbol)
    return accepted, rejected


async def build_recommendation_quote_snapshot(symbols: list[str]) -> dict[str, Any]:
    return await build_quote_snapshot(symbols, include_options=True)


async def build_quote_snapshot(
    symbols: list[str],
    *,
    include_options: bool = True,
    api_key: str | None = None,
    api_secret: str | None = None,
) -> dict[str, Any]:
    accepted, rejected = normalize_equity_symbols(symbols)
    if not accepted:
        raise ValueError("Add at least one valid stock symbol.")
    quotes = {item.symbol: _quote_row_from_yahoo(item) for item in fetch_yahoo_quote_snapshots(accepted)}
    if api_key and api_secret:
        alpaca_quotes = await asyncio.to_thread(_fetch_alpaca_latest_quotes, accepted, api_key, api_secret)
        for symbol, quote in alpaca_quotes.items():
            quotes.setdefault(symbol, _empty_quote_row(symbol)).update(quote)
    if not include_options:
        return {
            "symbols": accepted,
            "rejected_symbols": rejected,
            "max_symbols": ALPACA_MAX_EQUITY_SYMBOLS,
            "max_option_quotes": ALPACA_MAX_OPTION_QUOTES,
            "option_contracts": [],
            "quotes": [quotes.get(symbol, _empty_quote_row(symbol)) for symbol in accepted],
            "option_chains": {symbol: {"puts": [], "calls": []} for symbol in accepted},
        }

    chains = await _fetch_option_chains(accepted)

    option_chains: dict[str, dict[str, list[dict[str, Any]]]] = {}
    option_contracts: list[str] = []
    for symbol in accepted:
        chain = chains.get(symbol, [])
        puts = [row for row in chain if row.get("option_type") == "P"]
        calls = [row for row in chain if row.get("option_type") == "C"]
        best_put = _best_30_delta(puts, "P")
        best_call = _best_30_delta(calls, "C")
        metrics = _wheel_metrics(symbol, chain, best_put, best_call)
        quotes.setdefault(symbol, _empty_quote_row(symbol)).update(metrics)
        if best_put:
            quotes[symbol]["best_put"] = best_put
            option_contracts.append(best_put["occ_symbol"])
        if best_call:
            quotes[symbol]["best_call"] = best_call
            option_contracts.append(best_call["occ_symbol"])
        option_chains[symbol] = {"puts": puts, "calls": calls}

    if len(option_contracts) > ALPACA_MAX_OPTION_QUOTES:
        option_contracts = option_contracts[:ALPACA_MAX_OPTION_QUOTES]

    return {
        "symbols": accepted,
        "rejected_symbols": rejected,
        "max_symbols": ALPACA_MAX_EQUITY_SYMBOLS,
        "max_option_quotes": ALPACA_MAX_OPTION_QUOTES,
        "option_contracts": option_contracts,
        "quotes": [quotes[symbol] for symbol in accepted],
        "option_chains": option_chains,
    }


async def create_quote_session(
    *,
    user_id: int,
    api_key: str,
    api_secret: str,
    symbols: list[str],
    include_options: bool = True,
    stream_options: bool = True,
) -> dict[str, Any]:
    _prune_sessions()
    snapshot = await build_quote_snapshot(symbols, include_options=include_options, api_key=api_key, api_secret=api_secret)
    token = secrets.token_urlsafe(24)
    session = AlpacaQuoteSession(
        token=token,
        user_id=user_id,
        api_key=api_key,
        api_secret=api_secret,
        symbols=snapshot["symbols"],
        option_contracts=snapshot["option_contracts"] if stream_options else [],
        snapshot=snapshot,
        expires_at=time.time() + QUOTE_SESSION_TTL_SECONDS,
    )
    _QUOTE_SESSIONS[token] = session
    return {"session_id": token, **snapshot}


def pop_quote_session(token: str) -> AlpacaQuoteSession | None:
    _prune_sessions()
    session = _QUOTE_SESSIONS.get(token)
    if not session or session.expires_at <= time.time():
        _QUOTE_SESSIONS.pop(token, None)
        return None
    return session


async def stream_alpaca_session(session: AlpacaQuoteSession, send_json) -> None:
    await send_json({"type": "snapshot", "data": session.snapshot})
    tasks = [
        asyncio.create_task(_stream_alpaca_quotes(session, "stock", ALPACA_EQUITY_STREAM_URL, session.symbols, send_json)),
    ]
    if session.option_contracts:
        tasks.append(asyncio.create_task(_stream_alpaca_quotes(session, "option", ALPACA_OPTION_STREAM_URL, session.option_contracts, send_json)))
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_EXCEPTION)
    for task in pending:
        task.cancel()
    for task in done:
        task.result()


def map_alpaca_stock_quote(message: dict[str, Any]) -> dict[str, Any] | None:
    if message.get("T") != "q" or not message.get("S"):
        return None
    return {
        "type": "stock_quote",
        "symbol": message.get("S"),
        "bid": _number(message.get("bp")),
        "ask": _number(message.get("ap")),
        "bid_size": _number(message.get("bs")),
        "ask_size": _number(message.get("as")),
        "timestamp": message.get("t"),
        "raw": message,
    }


def _fetch_alpaca_latest_quotes(symbols: list[str], api_key: str, api_secret: str) -> dict[str, dict[str, Any]]:
    if not symbols:
        return {}
    query = urlencode({"symbols": ",".join(symbols), "feed": "iex"})
    request = Request(
        f"{ALPACA_EQUITY_REST_URL}?{query}",
        headers={
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": api_secret,
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=20, context=_ALPACA_SSL_CONTEXT) as response:
            if response.status != 200:
                return {}
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code in {401, 403}:
            raise ValueError("Alpaca rejected the saved API key or secret.") from exc
        raise ValueError(f"Alpaca quote pull failed with HTTP {exc.code}.") from exc
    except URLError as exc:
        raise ValueError(f"Could not reach Alpaca quote API: {exc.reason}") from exc

    rows: dict[str, dict[str, Any]] = {}
    for symbol, item in (payload.get("quotes") or {}).items():
        if not isinstance(item, dict):
            continue
        bid = _positive_number(item.get("bp"))
        ask = _positive_number(item.get("ap"))
        row: dict[str, Any] = {
            "symbol": str(symbol).upper(),
            "bid_size": _number(item.get("bs")),
            "ask_size": _number(item.get("as")),
            "timestamp": item.get("t"),
            "source": "Alpaca REST latest quote",
            "stage": "pulled",
        }
        if bid is not None:
            row["bid"] = bid
        if ask is not None:
            row["ask"] = ask
        if bid is not None and ask is not None:
            row["price"] = round((bid + ask) / 2, 4)
        rows[str(symbol).upper()] = row
    return rows


def map_alpaca_option_quote(message: dict[str, Any]) -> dict[str, Any] | None:
    if message.get("T") != "q" or not message.get("S"):
        return None
    return {
        "type": "option_quote",
        "occ_symbol": message.get("S"),
        "bid": _number(message.get("bp")),
        "ask": _number(message.get("ap")),
        "bid_size": _number(message.get("bs")),
        "ask_size": _number(message.get("as")),
        "timestamp": message.get("t"),
        "raw": message,
    }


async def _stream_alpaca_quotes(session: AlpacaQuoteSession, stream_type: str, url: str, symbols: list[str], send_json) -> None:
    if stream_type == "option" and len(symbols) > ALPACA_MAX_OPTION_QUOTES:
        await send_json({"type": "status", "status": "error", "stream": stream_type, "message": "Alpaca option quote subscription limit is 200 contracts."})
        return
    try:
        async with websockets.connect(url, ping_interval=20, ping_timeout=20, open_timeout=20, ssl=_ALPACA_SSL_CONTEXT) as ws:
            await ws.send(_json({"action": "auth", "key": session.api_key, "secret": session.api_secret}))
            authenticated = await _wait_for_alpaca_auth(ws, stream_type, send_json)
            if not authenticated:
                return
            await ws.send(_json({"action": "subscribe", "quotes": symbols}))
            await send_json({"type": "status", "status": "subscribed", "stream": stream_type, "symbols": symbols})
            async for raw in ws:
                for message in _messages(raw):
                    if message.get("T") == "error":
                        await send_json({"type": "status", "status": "error", "stream": stream_type, "message": _alpaca_error_message(message), "code": message.get("code")})
                        continue
                    mapped = map_alpaca_stock_quote(message) if stream_type == "stock" else map_alpaca_option_quote(message)
                    if mapped:
                        await send_json(mapped)
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        await send_json({"type": "status", "status": "error", "stream": stream_type, "message": _connection_error_message(exc)})


async def _wait_for_alpaca_auth(ws, stream_type: str, send_json) -> bool:
    while True:
        raw = await asyncio.wait_for(ws.recv(), timeout=20)
        for message in _messages(raw):
            if message.get("T") == "success" and message.get("msg") == "connected":
                continue
            if message.get("T") == "success" and message.get("msg") == "authenticated":
                return True
            if message.get("T") == "error":
                await send_json({"type": "status", "status": "error", "stream": stream_type, "message": _alpaca_error_message(message), "code": message.get("code")})
                return False


async def _fetch_option_chains(symbols: list[str]) -> dict[str, list[dict[str, Any]]]:
    tasks = [_fetch_option_chain(symbol) for symbol in symbols]
    rows = await asyncio.gather(*tasks, return_exceptions=True)
    out: dict[str, list[dict[str, Any]]] = {}
    for symbol, result in zip(symbols, rows):
        out[symbol] = [] if isinstance(result, Exception) else result
    return out


async def _fetch_option_chain(symbol: str) -> list[dict[str, Any]]:
    cached = _OPTION_CHAIN_CACHE.get(symbol)
    if cached and cached[0] == date.today():
        return cached[1]
    wheel_cached = _load_wheel_cached_option_chain(symbol)
    if wheel_cached:
        _OPTION_CHAIN_CACHE[symbol] = (date.today(), wheel_cached)
        return wheel_cached
    try:
        payload = await asyncio.to_thread(_fetch_cboe_payload, symbol)
    except Exception:
        _OPTION_CHAIN_CACHE[symbol] = (date.today(), [])
        return []

    raw_data = payload.get("data", {})
    current_price = _number(raw_data.get("current_price"))
    today = date.today()
    parsed: list[dict[str, Any]] = []
    for item in raw_data.get("options", []):
        occ_symbol = str(item.get("option") or "")
        try:
            _, expiry, option_type, strike = _parse_occ(occ_symbol)
        except Exception:
            continue
        dte = (expiry - today).days
        if dte < 0:
            continue
        bid = _number(item.get("bid")) or 0.0
        ask = _number(item.get("ask")) or 0.0
        mid = round((bid + ask) / 2, 2)
        delta = _number(item.get("delta"))
        iv = _number(item.get("iv"))
        raw_yield = annualized_yield = None
        if mid > 0 and dte > 0:
            if option_type == "P" and strike > 0:
                raw_yield = round((mid / strike) * 100, 3)
                annualized_yield = round(raw_yield * (365 / dte), 2)
            elif option_type == "C" and current_price and current_price > 0:
                raw_yield = round((mid / current_price) * 100, 3)
                annualized_yield = round(raw_yield * (365 / dte), 2)
        pct_away = round(((strike - current_price) / current_price) * 100, 2) if current_price else None
        parsed.append({
            "symbol": symbol,
            "occ_symbol": occ_symbol,
            "option_type": option_type,
            "expiry": expiry.isoformat(),
            "dte": dte,
            "strike": strike,
            "bid": bid,
            "ask": ask,
            "mid": mid,
            "last": _number(item.get("last_trade_price")),
            "iv": round(iv * 100, 1) if iv else None,
            "delta": round(delta, 3) if delta is not None else None,
            "open_interest": int(_number(item.get("open_interest")) or 0),
            "volume": int(_number(item.get("volume")) or 0),
            "raw_yield": raw_yield,
            "annualized_yield": annualized_yield,
            "pct_away": pct_away,
            "pop": round((1 - abs(delta)) * 100, 1) if delta is not None else None,
            "stock_price": current_price,
            "capital_required": round(strike * 100, 2) if option_type == "P" else None,
            "upside_pct": pct_away if option_type == "C" else None,
        })
    _OPTION_CHAIN_CACHE[symbol] = (date.today(), parsed)
    return parsed


def _fetch_cboe_payload(symbol: str) -> dict[str, Any]:
    request = Request(f"{_CBOE_BASE_URL}/{symbol}.json", headers=_CBOE_HEADERS)
    with urlopen(request, timeout=20, context=_ALPACA_SSL_CONTEXT) as response:
        if response.status != 200:
            return {}
        return json.loads(response.read().decode("utf-8"))


def _load_wheel_cached_option_chain(symbol: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(_WHEEL_CBOE_CACHE_PATH.read_text())
    except Exception:
        return []
    if payload.get("date") != date.today().isoformat():
        return []
    chain = (payload.get("chains") or {}).get(symbol.upper())
    if not isinstance(chain, list):
        return []
    return [row for row in chain if isinstance(row, dict)]


def _best_30_delta(options: list[dict[str, Any]], option_type: str) -> dict[str, Any] | None:
    candidates = [
        item for item in options
        if item.get("delta") is not None and item.get("annualized_yield") is not None and 20 <= int(item.get("dte") or 0) <= 50
    ]
    if not candidates:
        return None
    target_delta = -0.30 if option_type == "P" else 0.30
    return min(candidates, key=lambda item: abs(int(item["dte"]) - 30) / 30 + abs(float(item["delta"]) - target_delta) * 2)


def _wheel_metrics(symbol: str, chain: list[dict[str, Any]], best_put: dict[str, Any] | None, best_call: dict[str, Any] | None) -> dict[str, Any]:
    iv_values = [float(row["iv"]) for row in chain if row.get("iv") is not None and 20 <= int(row.get("dte") or 0) <= 50]
    iv_rank = round(sum(iv_values) / len(iv_values), 1) if iv_values else None
    csp_30d = round(float(best_put["annualized_yield"]), 2) if best_put and best_put.get("annualized_yield") is not None else None
    cc_30d = round(float(best_call["annualized_yield"]), 2) if best_call and best_call.get("annualized_yield") is not None else None
    signals = []
    if csp_30d is not None and csp_30d >= 12:
        signals.append("CSP income")
    if cc_30d is not None and cc_30d >= 10:
        signals.append("Covered-call income")
    if iv_rank is not None and iv_rank >= 30:
        signals.append("IV premium")
    return {
        "symbol": symbol,
        "iv_rank": iv_rank,
        "hv30": None,
        "rsi": None,
        "bb_pct": None,
        "csp_30d": csp_30d,
        "cc_30d": cc_30d,
        "signals": signals,
    }


def _quote_row_from_yahoo(item) -> dict[str, Any]:
    price = _number(item.price)
    close = _number(item.close)
    change = round(price - close, 2) if price is not None and close else None
    change_pct = round((change / close) * 100, 2) if change is not None and close else None
    return {
        "symbol": item.symbol,
        "price": price,
        "bid": None,
        "ask": None,
        "bid_size": None,
        "ask_size": None,
        "last": price,
        "close": close,
        "change": change,
        "change_pct": change_pct,
        "volume": None,
        "timestamp": None,
        "update_age_ms": None,
        "iv_rank": None,
        "hv30": None,
        "rsi": None,
        "bb_pct": None,
        "csp_30d": None,
        "cc_30d": None,
        "signals": [],
        "source": item.source,
        "stage": "snapshot",
        "best_put": None,
        "best_call": None,
    }


def _empty_quote_row(symbol: str) -> dict[str, Any]:
    return _quote_row_from_yahoo(type("Quote", (), {"symbol": symbol, "price": None, "close": None, "source": "Snapshot unavailable"})())


def _parse_occ(occ: str) -> tuple[str, date, str, float]:
    if len(occ) < 16:
        raise ValueError("OCC symbol too short")
    underlying = occ[:-15]
    expiry = datetime.strptime(occ[-15:-9], "%y%m%d").date()
    option_type = occ[-9]
    strike = int(occ[-8:]) / 1000.0
    if option_type not in {"P", "C"}:
        raise ValueError("Invalid option type")
    return underlying, expiry, option_type, strike


def _prune_sessions() -> None:
    now = time.time()
    for token, session in list(_QUOTE_SESSIONS.items()):
        if session.expires_at <= now:
            _QUOTE_SESSIONS.pop(token, None)


def _messages(raw: str | bytes) -> list[dict[str, Any]]:
    try:
        payload = json.loads(raw)
    except Exception:
        return []
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return [payload] if isinstance(payload, dict) else []


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"))


def _number(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _positive_number(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and number > 0 else None


def _alpaca_error_message(message: dict[str, Any]) -> str:
    raw = str(message.get("msg") or message.get("message") or "Alpaca stream error.")
    code = message.get("code")
    if code in {401, 402, 403, 404, 405, 406, 407}:
        if "auth" in raw.lower():
            return "Alpaca rejected the saved API key or secret."
        if "symbol" in raw.lower():
            return "Alpaca rejected one or more symbols for this subscription."
        if "subscription" in raw.lower() or "permission" in raw.lower():
            return "Alpaca account does not have permission for this market-data feed."
        if "connection" in raw.lower():
            return "Alpaca connection limit reached for this account."
    return raw


def _connection_error_message(exc: Exception) -> str:
    text = str(exc).strip()
    if not text:
        return "Could not reach Alpaca streaming market data."
    return f"Could not reach Alpaca streaming market data: {text}"
