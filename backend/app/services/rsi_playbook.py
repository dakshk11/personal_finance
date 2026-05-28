from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import PortfolioSyncSnapshot, utc_now
from app.services.market_data import normalize_symbol
from app.services.market_history import MarketHistory, MarketHistoryBar, get_market_history
from app.services.option_strategy import default_universe


@dataclass
class RSIUniverseItem:
    symbol: str
    name: str
    sector: str
    group: str
    sources: set[str] = field(default_factory=set)
    portfolio_weight: float | None = None


def scan_rsi_playbook(
    db: Session,
    user_id: int,
    *,
    force_refresh: bool = False,
    lookback_days: int = 420,
    max_symbols: int = 90,
) -> dict[str, Any]:
    universe = _combined_universe(db, user_id)
    symbols = list(universe.values())[:max(1, max_symbols)]
    end_date = date.today()
    start_date = end_date - timedelta(days=max(120, lookback_days))
    signals: list[dict[str, Any]] = []
    warnings: list[str] = []

    for item in symbols:
        history = get_market_history(db, item.symbol, start_date, end_date, force_refresh=force_refresh)
        if not history.bars:
            warnings.append(f"{item.symbol}: provider history unavailable; RSI and chart data not shown.")
        signal = _signal_for_item(item, history)
        signals.append(signal)
        warnings.extend([f"{item.symbol}: {warning}" for warning in history.warnings[:2]])

    signals.sort(key=_signal_sort_key)
    portfolio_symbol_count = sum(1 for item in universe.values() if "Portfolio Sync" in item.sources)
    wheel_symbol_count = sum(1 for item in universe.values() if "Wheel Strategy" in item.sources)
    return {
        "scanned_at": utc_now(),
        "source_summary": "Wheel Strategy universe plus latest Portfolio Sync holdings snapshot",
        "universe_count": len(signals),
        "portfolio_symbol_count": portfolio_symbol_count,
        "wheel_symbol_count": wheel_symbol_count,
        "signals": signals,
        "warnings": _unique(warnings),
    }


def classify_rsi(rsi: float | None) -> dict[str, str]:
    if rsi is None:
        return {
            "level": "RSI unavailable",
            "action": "Wait for data",
            "action_tone": "watch",
        }
    if rsi >= 70:
        return {
            "level": "RSI 70+",
            "action": "Go to cash",
            "action_tone": "cash",
        }
    if rsi > 65:
        return {
            "level": "RSI 65-70",
            "action": "Wait / cash watch",
            "action_tone": "watch",
        }
    if rsi >= 55:
        return {
            "level": "RSI 55-65",
            "action": "Sell puts far OTM",
            "action_tone": "puts_far_otm",
        }
    if rsi >= 45:
        return {
            "level": "RSI 45-55",
            "action": "Sell puts ATM",
            "action_tone": "puts_atm",
        }
    if rsi >= 30:
        return {
            "level": "RSI 30-45",
            "action": "Buy the stock",
            "action_tone": "stock",
        }
    return {
        "level": "RSI 30 and below",
        "action": "Buy LEAP aggressively",
        "action_tone": "leap",
    }


def _signal_for_item(item: RSIUniverseItem, history: MarketHistory) -> dict[str, Any]:
    ordered = sorted([bar for bar in history.bars if _close(bar) > 0], key=lambda bar: bar.date)
    values = [_close(bar) for bar in ordered]
    ema8 = _ema(values, 8)
    ema21 = _ema(values, 21)
    ema55 = _ema(values, 55)
    rsi_values = _rsi_series(values, 14)
    latest_index = len(values) - 1
    latest_price = round(values[-1], 4) if values else 0
    latest_rsi = _round_or_none(rsi_values[latest_index]) if values else None
    classification = classify_rsi(latest_rsi)
    latest_ema8 = _round_or_none(ema8[latest_index]) if values else None
    latest_ema21 = _round_or_none(ema21[latest_index]) if values else None
    latest_ema55 = _round_or_none(ema55[latest_index]) if values else None
    trend = _trend_label(latest_price, latest_ema8, latest_ema21, latest_ema55)
    distance_to_ema21 = round((latest_price / latest_ema21) - 1, 6) if latest_price > 0 and latest_ema21 else None
    window_return_3m = _window_return(values, 63)
    chart = _chart_points(ordered, ema8, ema21, ema55, rsi_values)
    return {
        "symbol": item.symbol,
        "name": item.name,
        "sector": item.sector,
        "sources": sorted(item.sources),
        "group": item.group,
        "price": latest_price,
        "as_of_date": ordered[-1].date if ordered else None,
        "rsi": latest_rsi,
        "level": classification["level"],
        "action": classification["action"],
        "action_tone": classification["action_tone"],
        "summary": _summary(item.symbol, latest_rsi, classification["level"], classification["action"], trend),
        "trend": trend,
        "ema8": latest_ema8,
        "ema21": latest_ema21,
        "ema55": latest_ema55,
        "distance_to_ema21": distance_to_ema21,
        "window_return_3m": window_return_3m,
        "portfolio_weight": item.portfolio_weight,
        "data_source": ordered[-1].source if ordered else "No market history",
        "warnings": history.warnings,
        "chart": chart,
    }


def _combined_universe(db: Session, user_id: int) -> dict[str, RSIUniverseItem]:
    merged: dict[str, RSIUniverseItem] = {}

    def add(symbol: str, name: str, sector: str, group: str, source: str, portfolio_weight: float | None = None) -> None:
        normalized = normalize_symbol(symbol)
        if not normalized:
            return
        current = merged.get(normalized)
        if current:
            current.sources.add(source)
            if source == "Portfolio Sync":
                current.group = "Portfolio Sync + Wheel Strategy" if "Wheel Strategy" in current.sources else "Portfolio Sync"
                current.portfolio_weight = portfolio_weight
            return
        merged[normalized] = RSIUniverseItem(
            symbol=normalized,
            name=name or f"{normalized} market history",
            sector=sector or "Unknown",
            group=group,
            sources={source},
            portfolio_weight=portfolio_weight,
        )

    for item in default_universe():
        add(
            str(item["symbol"]),
            str(item.get("name") or item["symbol"]),
            str(item.get("sector") or "Unknown"),
            str(item.get("group") or "Wheel Strategy"),
            "Wheel Strategy",
        )

    snapshot = db.scalar(select(PortfolioSyncSnapshot).where(PortfolioSyncSnapshot.user_id == user_id))
    holdings = _json_load(snapshot.holdings_json, []) if snapshot else []
    total_market_value = sum(_number(holding.get("market_value")) for holding in holdings)
    for holding in holdings:
        symbol = str(holding.get("symbol") or "")
        weight = (_number(holding.get("market_value")) / total_market_value) if total_market_value > 0 else None
        add(
            symbol,
            str(holding.get("symbol") or symbol),
            str(holding.get("sector") or "Portfolio Sync"),
            "Portfolio Sync",
            "Portfolio Sync",
            portfolio_weight=round(weight, 6) if weight is not None else None,
        )
    return merged


def _chart_points(
    bars: list[MarketHistoryBar],
    ema8: list[float | None],
    ema21: list[float | None],
    ema55: list[float | None],
    rsi_values: list[float | None],
) -> list[dict[str, Any]]:
    start = max(0, len(bars) - 252)
    rows: list[dict[str, Any]] = []
    for index in range(start, len(bars)):
        rows.append(
            {
                "date": bars[index].date,
                "close": round(_close(bars[index]), 4),
                "ema8": _round_or_none(ema8[index]),
                "ema21": _round_or_none(ema21[index]),
                "ema55": _round_or_none(ema55[index]),
                "rsi": _round_or_none(rsi_values[index]),
            }
        )
    return rows



def _ema(values: list[float], period: int) -> list[float | None]:
    if not values:
        return []
    output: list[float | None] = []
    smoothing = 2 / (period + 1)
    previous = values[0]
    for index, value in enumerate(values):
        if index == 0:
            previous = value
        else:
            previous = value * smoothing + previous * (1 - smoothing)
        output.append(previous)
    return output


def _rsi_series(values: list[float], period: int) -> list[float | None]:
    output: list[float | None] = [None] * len(values)
    if len(values) <= period:
        return output
    gains = 0.0
    losses = 0.0
    for index in range(1, period + 1):
        change = values[index] - values[index - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change
    average_gain = gains / period
    average_loss = losses / period
    output[period] = 100 if average_loss == 0 else 100 - (100 / (1 + average_gain / average_loss))
    for index in range(period + 1, len(values)):
        change = values[index] - values[index - 1]
        average_gain = ((average_gain * (period - 1)) + max(change, 0)) / period
        average_loss = ((average_loss * (period - 1)) + max(-change, 0)) / period
        output[index] = 100 if average_loss == 0 else 100 - (100 / (1 + average_gain / average_loss))
    return output


def _trend_label(price: float, ema8: float | None, ema21: float | None, ema55: float | None) -> str:
    if not ema8 or not ema21 or not ema55:
        return "Limited data"
    if price >= ema21 and ema8 >= ema21 >= ema55:
        return "Bullish EMA stack"
    if price < ema21 and ema8 < ema21 < ema55:
        return "Bearish EMA stack"
    return "Mixed EMA stack"


def _summary(symbol: str, rsi: float | None, level: str, action: str, trend: str) -> str:
    rsi_text = "unavailable" if rsi is None else f"{rsi:.1f}"
    return f"{symbol} is in {level} with RSI {rsi_text}; playbook action is {action}. EMA context: {trend}. Manually verify news, earnings, liquidity, and position sizing before acting."


def _signal_sort_key(signal: dict[str, Any]) -> tuple[int, str]:
    order = {
        "leap": 0,
        "stock": 1,
        "puts_atm": 2,
        "puts_far_otm": 3,
        "cash": 4,
        "watch": 5,
    }
    return (order.get(str(signal.get("action_tone")), 9), str(signal.get("symbol")))


def _window_return(values: list[float], period: int) -> float | None:
    if len(values) <= period or values[-period - 1] <= 0:
        return None
    return round((values[-1] / values[-period - 1]) - 1, 6)


def _close(bar: MarketHistoryBar) -> float:
    return bar.adjusted_close if bar.adjusted_close > 0 else bar.close


def _round_or_none(value: float | None) -> float | None:
    return round(value, 4) if value is not None else None


def _json_load(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _number(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
