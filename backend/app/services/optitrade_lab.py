from __future__ import annotations

import asyncio
import json
import ssl
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import certifi

from app.core.alpaca_rate_limit import alpaca_account_rate_limiter
from app.services.ai_advisor import api_key_fingerprint


LEVERAGED_UNDERLYING_MAP = {
    "TQQQ": "QQQ",
    "SQQQ": "QQQ",
    "UPRO": "SPY",
    "SPXU": "SPY",
    "SOXL": "SOXX",
    "SOXS": "SOXX",
    "FAS": "XLF",
    "FAZ": "XLF",
    "TECL": "XLK",
    "TECS": "XLK",
}
SP500_TOP_20_MARKET_CAP_SYMBOLS = [
    "NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "AVGO", "GOOG", "META", "TSLA", "MU",
    "LLY", "BRK.B", "AMD", "JPM", "XOM", "JNJ", "V", "INTC", "WMT", "CSCO",
]
OPTITRADE_DIRECT_SYMBOLS = {symbol: symbol for symbol in SP500_TOP_20_MARKET_CAP_SYMBOLS}
OPTITRADE_UNDERLYING_MAP = {**LEVERAGED_UNDERLYING_MAP, **OPTITRADE_DIRECT_SYMBOLS}
DEFAULT_OPTITRADE_SYMBOLS = ["TQQQ", "SOXL", "UPRO", *SP500_TOP_20_MARKET_CAP_SYMBOLS]
MAX_OPTITRADE_SYMBOLS = len(DEFAULT_OPTITRADE_SYMBOLS)
ALPACA_MARKET_DATA_BASE_URL = "https://data.alpaca.markets/v2"


class AlpacaRateLimitError(RuntimeError):
    pass


class AlpacaMarketDataError(RuntimeError):
    pass


async def build_alpaca_optitrade_signals(api_key: str, api_secret: str, symbols: list[str]) -> dict[str, Any]:
    universe = _normalize_universe(symbols)
    required = list(dict.fromkeys(universe + [OPTITRADE_UNDERLYING_MAP[symbol] for symbol in universe]))
    bars_by_symbol, calls_used = await fetch_alpaca_daily_bars(api_key, api_secret, required)
    results = []
    warnings: list[str] = []
    for symbol in universe:
        try:
            results.append(_build_signal_from_bars(symbol, bars_by_symbol))
        except Exception as exc:
            warnings.append(f"{symbol}: {exc}")
    if not results:
        raise AlpacaMarketDataError("No OptiTrade Lab signal data could be loaded from Alpaca.")
    return {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "data_source": f"Alpaca Market Data historical daily bars; {calls_used} REST call(s); original FinanceOS signal approximation",
        "signals": results,
        "warnings": warnings,
        "rate_limit": {
            "limit_per_minute": alpaca_account_rate_limiter.limit,
            "remaining": alpaca_account_rate_limiter.remaining(api_key_fingerprint(api_key)),
            "pagination_note": "Each Alpaca page_token fetch counts as one request against the 200/minute account-key budget.",
        },
    }


async def build_alpaca_optitrade_backtest(
    api_key: str,
    api_secret: str,
    symbol: str,
    atr_multiplier: float = 2.5,
    tp_mode: str = "multi",
    stop_model: str = "atr",
) -> dict[str, Any]:
    symbol = symbol.strip().upper()
    underlying = OPTITRADE_UNDERLYING_MAP.get(symbol)
    if not underlying:
        raise ValueError(f"{symbol} is not in the leveraged ETF universe.")
    if tp_mode not in {"single", "multi", "always_in"}:
        raise ValueError("tp_mode must be single, multi, or always_in.")
    if stop_model not in {"atr", "swing"}:
        raise ValueError("stop_model must be atr or swing.")
    bars_by_symbol, calls_used = await fetch_alpaca_daily_bars(api_key, api_secret, [symbol, underlying])
    leveraged_bars = _bars_for(symbol, bars_by_symbol)
    underlying_bars = _bars_for(underlying, bars_by_symbol)
    return {
        "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "data_source": f"Alpaca Market Data historical daily bars; {calls_used} REST call(s); settings-aware FinanceOS backtest",
        "symbol": symbol,
        "underlying": underlying,
        "rate_limit": {
            "limit_per_minute": alpaca_account_rate_limiter.limit,
            "remaining": alpaca_account_rate_limiter.remaining(api_key_fingerprint(api_key)),
            "pagination_note": "Each Alpaca page_token fetch counts as one request against the 200/minute account-key budget.",
        },
        "backtest": _optitrade_backtest(
            leveraged_bars,
            underlying_bars,
            atr_multiplier=atr_multiplier,
            tp_mode=tp_mode,
            stop_model=stop_model,
        ),
    }


async def fetch_alpaca_daily_bars(api_key: str, api_secret: str, symbols: list[str]) -> tuple[dict[str, list[dict[str, Any]]], int]:
    if not symbols:
        return {}, 0
    key_fingerprint = api_key_fingerprint(api_key)
    next_token: str | None = None
    calls_used = 0
    out: dict[str, list[dict[str, Any]]] = {symbol: [] for symbol in symbols}
    start = (datetime.now(UTC) - timedelta(days=900)).date().isoformat()
    end = datetime.now(UTC).date().isoformat()
    while True:
        if not alpaca_account_rate_limiter.allow(key_fingerprint):
            raise AlpacaRateLimitError("Alpaca 200 requests/minute account-key limit reached. Wait a minute before retrying.")
        calls_used += 1
        payload = await asyncio.to_thread(_fetch_alpaca_bars_page, api_key, api_secret, symbols, start, end, next_token)
        for symbol, bars in (payload.get("bars") or {}).items():
            out.setdefault(symbol, []).extend(_normalize_alpaca_bars(bars))
        next_token = payload.get("next_page_token")
        if not next_token:
            break
    for symbol, bars in out.items():
        bars.sort(key=lambda row: row["date"])
        out[symbol] = _dedupe_bars(bars)
    return out, calls_used


def _fetch_alpaca_bars_page(
    api_key: str,
    api_secret: str,
    symbols: list[str],
    start: str,
    end: str,
    page_token: str | None,
) -> dict[str, Any]:
    params = {
        "symbols": ",".join(symbols),
        "timeframe": "1Day",
        "start": start,
        "end": end,
        "limit": "10000",
        "adjustment": "all",
        "feed": "iex",
        "sort": "asc",
    }
    if page_token:
        params["page_token"] = page_token
    request = Request(
        f"{ALPACA_MARKET_DATA_BASE_URL}/stocks/bars?{urlencode(params)}",
        headers={
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": api_secret,
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(request, timeout=30, context=ssl.create_default_context(cafile=certifi.where())) as response:
            if response.status >= 400:
                raise AlpacaMarketDataError(f"Alpaca Market Data request failed with HTTP {response.status}.")
            return json.loads(response.read().decode("utf-8"))
    except AlpacaMarketDataError:
        raise
    except Exception as exc:
        raise AlpacaMarketDataError(f"Could not reach Alpaca Market Data API: {exc}") from exc


def _normalize_alpaca_bars(raw_bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for bar in raw_bars:
        close = _float(bar.get("c"))
        high = _float(bar.get("h"))
        low = _float(bar.get("l"))
        open_price = _float(bar.get("o"))
        if close is None or high is None or low is None or open_price is None or close <= 0:
            continue
        rows.append({
            "date": str(bar.get("t", ""))[:10],
            "open": open_price,
            "high": high,
            "low": low,
            "close": close,
            "volume": _float(bar.get("v")) or 0.0,
        })
    return rows


def _dedupe_bars(bars: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_date = {bar["date"]: bar for bar in bars if bar.get("date")}
    return [by_date[key] for key in sorted(by_date)]


def _normalize_universe(symbols: list[str]) -> list[str]:
    requested = [item.strip().upper() for item in symbols if item.strip()]
    requested = list(dict.fromkeys(requested))[:MAX_OPTITRADE_SYMBOLS] or DEFAULT_OPTITRADE_SYMBOLS
    return [symbol for symbol in requested if symbol in OPTITRADE_UNDERLYING_MAP] or DEFAULT_OPTITRADE_SYMBOLS


def _bars_for(symbol: str, bars_by_symbol: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    bars = bars_by_symbol.get(symbol, [])
    if len(bars) < 120:
        raise RuntimeError(f"insufficient Alpaca historical bars for {symbol}")
    return bars


def _build_signal_from_bars(symbol: str, bars_by_symbol: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    underlying = OPTITRADE_UNDERLYING_MAP[symbol]
    leveraged_bars = _bars_for(symbol, bars_by_symbol)
    underlying_bars = _bars_for(underlying, bars_by_symbol)
    trend = _trend_signal(underlying_bars)
    price = float(leveraged_bars[-1]["close"])
    leveraged_atr = _atr(leveraged_bars)[-1] or max(price * 0.025, 0.01)
    levels = _levels_for_signal(price, float(leveraged_atr), trend["signal"])
    return {
        "symbol": symbol,
        "underlying": underlying,
        "as_of_date": leveraged_bars[-1]["date"],
        "price": round(price, 2),
        "signal": trend["signal"],
        "trend_state": trend["trend_state"],
        "anti_chop_state": trend["anti_chop_state"],
        "anti_chop_pass": trend["anti_chop_pass"],
        "entry": levels["entry"],
        "stop_loss": levels["stop_loss"],
        "take_profits": levels["take_profits"],
        "risk_reward": levels["risk_reward"],
        "atr": trend["atr"],
        "momentum_score": trend["momentum_score"],
        "volume_score": trend["volume_score"],
        "rsi": trend["rsi"],
        "chart": _optitrade_chart(leveraged_bars, trend, levels),
        "backtest": _optitrade_backtest(leveraged_bars, underlying_bars),
    }


def _ema(values: list[float], period: int) -> list[float | None]:
    if not values:
        return []
    alpha = 2 / (period + 1)
    result: list[float | None] = [None] * len(values)
    ema_value = values[0]
    for index, value in enumerate(values):
        ema_value = value if index == 0 else alpha * value + (1 - alpha) * ema_value
        if index >= period - 1:
            result[index] = ema_value
    return result


def _avg(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _atr(bars: list[dict[str, Any]], period: int = 14) -> list[float | None]:
    true_ranges = []
    for index, bar in enumerate(bars):
        if index == 0:
            true_ranges.append(float(bar["high"]) - float(bar["low"]))
        else:
            prev_close = float(bars[index - 1]["close"])
            true_ranges.append(max(float(bar["high"]) - float(bar["low"]), abs(float(bar["high"]) - prev_close), abs(float(bar["low"]) - prev_close)))
    result: list[float | None] = [None] * len(bars)
    for index in range(period - 1, len(true_ranges)):
        result[index] = _avg(true_ranges[index - period + 1 : index + 1])
    return result


def _rsi_last(closes: list[float], period: int = 14) -> float:
    if len(closes) <= period:
        return 50.0
    gains = []
    losses = []
    for index in range(len(closes) - period, len(closes)):
        delta = closes[index] - closes[index - 1]
        gains.append(max(delta, 0))
        losses.append(abs(min(delta, 0)))
    avg_loss = _avg(losses)
    if avg_loss == 0:
        return 100.0
    rs = _avg(gains) / avg_loss
    return 100 - (100 / (1 + rs))


def _momentum_score(closes: list[float], volumes: list[float]) -> tuple[float, float, float]:
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd = ((ema12[-1] or closes[-1]) - (ema26[-1] or closes[-1])) / closes[-1] * 100
    rsi = _rsi_last(closes)
    slope20 = (closes[-1] / closes[-21] - 1) * 100 if len(closes) > 21 else 0.0
    score = 50 + (rsi - 50) * 0.55 + macd * 4 + slope20 * 1.2
    avg_volume = _avg(volumes[-21:-1]) if len(volumes) > 21 else _avg(volumes)
    volume_score = 50 if avg_volume <= 0 else max(0, min(100, volumes[-1] / avg_volume * 50))
    return round(max(0, min(100, score)), 1), round(max(0, min(100, volume_score)), 1), round(rsi, 1)


def _anti_chop_state(bars: list[dict[str, Any]], atr_value: float) -> tuple[str, bool]:
    closes = [float(bar["close"]) for bar in bars]
    latest_close = closes[-1]
    range_20 = (max(float(bar["high"]) for bar in bars[-20:]) - min(float(bar["low"]) for bar in bars[-20:])) / latest_close * 100
    atr_pct = atr_value / latest_close * 100 if latest_close else 0
    trending = range_20 >= 5.5 and atr_pct >= 1.1
    return ("Trending" if trending else "Chop filter active"), trending


def _trend_signal(bars: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [float(bar["close"]) for bar in bars]
    volumes = [float(bar["volume"]) for bar in bars]
    ema21 = _ema(closes, 21)
    ema55 = _ema(closes, 55)
    atr_values = _atr(bars)
    latest_close = closes[-1]
    latest_ema21 = ema21[-1] or latest_close
    latest_ema55 = ema55[-1] or latest_close
    atr_value = atr_values[-1] or max(latest_close * 0.025, 0.01)
    momentum, volume_score, rsi = _momentum_score(closes, volumes)
    chop_label, is_trending = _anti_chop_state(bars, atr_value)
    if latest_close > latest_ema21 > latest_ema55:
        trend_state = "BULLISH"
    elif latest_close < latest_ema21 < latest_ema55:
        trend_state = "BEARISH"
    else:
        trend_state = "NEUTRAL"
    if not is_trending:
        signal = "HOLD"
    elif trend_state == "BULLISH" and momentum >= 55:
        signal = "BUY"
    elif trend_state == "BEARISH" and momentum <= 45:
        signal = "SELL"
    else:
        signal = "HOLD"
    return {
        "signal": signal,
        "trend_state": trend_state,
        "anti_chop_state": chop_label,
        "anti_chop_pass": is_trending,
        "atr": round(atr_value, 2),
        "momentum_score": momentum,
        "volume_score": volume_score,
        "rsi": rsi,
    }


def _levels_for_signal(price: float, atr_value: float, signal: str, atr_multiplier: float = 2.5) -> dict[str, Any]:
    risk = max(atr_value * atr_multiplier, price * 0.03)
    direction = -1 if signal == "SELL" else 1
    stop = price - direction * risk
    take_profits = [price + direction * risk * multiple for multiple in (1, 2, 3, 4)]
    return {
        "entry": round(price, 2),
        "stop_loss": round(stop, 2),
        "take_profits": [round(value, 2) for value in take_profits],
        "risk_reward": round(abs((take_profits[1] - price) / (price - stop)), 2) if price != stop else None,
    }


def _optitrade_backtest(
    leveraged_bars: list[dict[str, Any]],
    underlying_bars: list[dict[str, Any]],
    atr_multiplier: float = 2.5,
    tp_mode: str = "multi",
    stop_model: str = "atr",
) -> dict[str, Any]:
    n = min(len(leveraged_bars), len(underlying_bars))
    leveraged = leveraged_bars[-n:]
    underlying = underlying_bars[-n:]
    atr_values = _atr(leveraged)
    trades: list[float] = []
    trade_rows: list[dict[str, Any]] = []
    equity = peak = 1.0
    max_drawdown = 0.0
    position_signal: str | None = None
    entry_price = 0.0
    entry_date = ""
    entry_index = 0
    stop_price = 0.0
    target_price = 0.0

    def _entry_levels(open_signal: str, open_index: int) -> tuple[float, float]:
        atr_value = float(atr_values[open_index] or 0)
        atr_risk = max(atr_value * atr_multiplier, entry_price * 0.03)
        if stop_model == "swing":
            recent = leveraged[max(0, open_index - 10): open_index + 1]
            if open_signal == "BUY":
                swing_stop = min(float(bar["low"]) for bar in recent)
                risk = entry_price - swing_stop
            else:
                swing_stop = max(float(bar["high"]) for bar in recent)
                risk = swing_stop - entry_price
            risk = risk if risk > 0 else atr_risk
        else:
            risk = atr_risk
        direction = -1 if open_signal == "SELL" else 1
        stop = entry_price - direction * risk
        target = entry_price + direction * risk * (1 if tp_mode == "single" else 2)
        return stop, target

    def _open_position(open_signal: str, open_index: int) -> None:
        nonlocal position_signal, entry_price, entry_date, entry_index, stop_price, target_price
        position_signal = open_signal
        entry_price = float(leveraged[open_index]["close"])
        entry_date = leveraged[open_index]["date"]
        entry_index = open_index
        stop_price, target_price = _entry_levels(open_signal, open_index)

    def _close_position(close_index: int, exit_price: float, reason: str) -> None:
        nonlocal equity, peak, max_drawdown, position_signal
        if not position_signal:
            return
        trade_return = (exit_price / entry_price - 1) if position_signal == "BUY" else (entry_price / exit_price - 1)
        trades.append(trade_return)
        equity *= 1 + trade_return
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - 1)
        trade_rows.append({
            "direction": position_signal,
            "entry_date": entry_date,
            "exit_date": leveraged[close_index]["date"],
            "entry_price": round(entry_price, 2),
            "exit_price": round(exit_price, 2),
            "return_pct": round(trade_return * 100, 2),
            "exit_reason": reason,
            "bars_held": max(0, close_index - entry_index),
        })
        position_signal = None

    for index in range(80, n):
        signal = _trend_signal(underlying[: index + 1])["signal"]
        price = float(leveraged[index]["close"])
        high = float(leveraged[index]["high"])
        low = float(leveraged[index]["low"])
        if position_signal:
            stop_label = "Swing stop" if stop_model == "swing" else "ATR stop"
            target_label = "TP1 single target" if tp_mode == "single" else "TP2 multi target"
            if position_signal == "BUY":
                if low <= stop_price:
                    _close_position(index, stop_price, stop_label)
                elif tp_mode in ("single", "multi") and high >= target_price:
                    _close_position(index, target_price, target_label)
            elif position_signal == "SELL":
                if high >= stop_price:
                    _close_position(index, stop_price, stop_label)
                elif tp_mode in ("single", "multi") and low <= target_price:
                    _close_position(index, target_price, target_label)
        if signal in ("BUY", "SELL") and position_signal is None:
            _open_position(signal, index)
            continue
        if position_signal and signal in ("BUY", "SELL") and signal != position_signal:
            _close_position(index, price, f"Flipped to {signal}")
            _open_position(signal, index)
    if position_signal:
        _close_position(n - 1, float(leveraged[-1]["close"]), "Open to latest close")
    wins = [trade for trade in trades if trade > 0]
    losses = [trade for trade in trades if trade <= 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "period": "2Y daily",
        "settings": {"atr_multiplier": round(atr_multiplier, 2), "tp_mode": tp_mode, "stop_model": stop_model},
        "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss else round(gross_profit, 2),
        "max_drawdown": round(max_drawdown * 100, 1),
        "total_trades": len(trades),
        "avg_trade": round(_avg(trades) * 100, 2) if trades else 0,
        "trades": trade_rows[-25:],
    }


def _optitrade_chart(leveraged_bars: list[dict[str, Any]], trend: dict[str, Any], levels: dict[str, Any]) -> list[dict[str, Any]]:
    closes = [float(bar["close"]) for bar in leveraged_bars]
    ema21 = _ema(closes, 21)
    ema55 = _ema(closes, 55)
    chart = []
    start_index = max(0, len(leveraged_bars) - 120)
    for index, bar in enumerate(leveraged_bars[start_index:]):
        source_index = start_index + index
        point = {
            "date": bar["date"],
            "open": round(float(bar["open"]), 2),
            "high": round(float(bar["high"]), 2),
            "low": round(float(bar["low"]), 2),
            "close": round(float(bar["close"]), 2),
            "volume": round(float(bar.get("volume", 0.0)), 2),
            "ema21": round(ema21[source_index], 2) if ema21[source_index] is not None else None,
            "ema55": round(ema55[source_index], 2) if ema55[source_index] is not None else None,
            "entry": levels["entry"],
            "stop_loss": levels["stop_loss"],
            "tp1": levels["take_profits"][0],
            "tp2": levels["take_profits"][1],
            "tp3": levels["take_profits"][2],
            "tp4": levels["take_profits"][3],
        }
        if source_index == len(leveraged_bars) - 1 and trend["signal"] in ("BUY", "SELL"):
            point["marker"] = trend["signal"]
        chart.append(point)
    return chart


def _float(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
