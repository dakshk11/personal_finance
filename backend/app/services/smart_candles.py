from __future__ import annotations

from datetime import date, timedelta
import math
from typing import Any

from sqlalchemy.orm import Session

from app.models.entities import utc_now
from app.services.breakout_scanner import (
    BreakoutBar,
    BreakoutUniverseItem,
    SCAN_HORIZONS,
    _append_custom_universe_items,
    _average,
    _close,
    _data_source_label,
    _horizon_stats,
    _round_or_none,
    _sma,
    _trend_label,
    _universe_items_from_out,
    _window_return,
    load_ohlcv_histories,
    load_sp500_universe,
)
from app.services.market_data import normalize_symbol


COLORS = ["blue", "pink", "red", "neutral"]


def run_smart_candle_scan(db: Session, payload: Any | None = None, *, force: bool = False) -> dict[str, Any]:
    config = normalize_smart_candle_config(payload)
    market_date = date.today()
    universe = load_sp500_universe(db)
    items = _scan_items(universe, config)
    start_date = market_date - timedelta(days=max(260, int(config["lookback_days"]) + 80))
    histories, history_warnings = load_ohlcv_histories(db, [item.symbol for item in items], start_date, market_date, force_refresh=force)

    signals: list[dict[str, Any]] = []
    for item in items:
        signal = classify_latest_candle(item, histories.get(item.symbol, []), config, include_chart=True)
        if signal and (config["include_neutral"] or signal["candle_color"] != "neutral"):
            signals.append(signal)

    signals.sort(key=lambda row: (_color_sort(str(row["candle_color"])), -float(row["score"]), str(row["symbol"])))
    for index, signal in enumerate(signals, start=1):
        signal["rank"] = index

    warnings = _unique(
        [
            "FinanceOS Smart Candle Signals are educational OHLCV classifications for manual research.",
            "Signals classify recent OHLCV behavior only and are not buy or sell instructions.",
            *universe.get("warnings", []),
            *history_warnings,
        ]
    )
    return {
        "scanned_at": utc_now(),
        "market_date": market_date,
        "data_source": _data_source_label(universe, history_warnings),
        "universe_count": int(universe["count"]),
        "scanned_symbols": len(items),
        "config": config,
        "signals": signals,
        "warnings": warnings,
    }


def run_smart_candle_backtest(db: Session, payload: Any | None = None) -> dict[str, Any]:
    config = normalize_smart_candle_config(payload)
    color = str(_payload_value(payload, "candle_color", "blue")).lower()
    if color not in COLORS:
        color = "blue"
    years = _clamp_int(_payload_value(payload, "years", 5), 1, 10)
    trade_action = str(_payload_value(payload, "trade_action", "buy")).lower()
    if trade_action not in {"buy", "sell"}:
        trade_action = "buy"
    min_signal_score = _clamp_float(_payload_value(payload, "min_signal_score", 0), 0, 100)
    config["include_neutral"] = True
    config["min_signal_score"] = min_signal_score

    market_date = date.today()
    start_date = market_date - timedelta(days=(years * 365) + int(config["lookback_days"]) + 120)
    universe = load_sp500_universe(db)
    items = _scan_items(universe, config)
    histories, history_warnings = load_ohlcv_histories(db, [item.symbol for item in items], start_date, market_date, force_refresh=False)

    returns_by_horizon: dict[int, list[float]] = {horizon: [] for horizon in SCAN_HORIZONS}
    signal_count = 0
    max_horizon = max(SCAN_HORIZONS)
    for item in items:
        bars = sorted(histories.get(item.symbol, []), key=lambda bar: bar.date)
        if len(bars) < 230 + max_horizon:
            continue
        last_signal_index = -999
        for index in range(220, len(bars) - max_horizon):
            if index - last_signal_index < 5:
                continue
            signal = classify_latest_candle(item, bars[: index + 1], config, include_chart=False)
            if not signal or signal["candle_color"] != color:
                continue
            if float(signal["score"]) < min_signal_score:
                continue
            last_signal_index = index
            signal_count += 1
            entry = _close(bars[index])
            if entry <= 0:
                continue
            for horizon in SCAN_HORIZONS:
                exit_price = _close(bars[index + horizon])
                if trade_action == "sell":
                    returns_by_horizon[horizon].append(round((entry / exit_price) - 1, 6))
                else:
                    returns_by_horizon[horizon].append(round((exit_price / entry) - 1, 6))

    warnings = _unique(
        [
            "Backtests are historical research only and do not include slippage, taxes, spreads, or execution quality.",
            "Current S&P 500 membership can create survivorship bias when testing older periods.",
            "No backtest result guarantees future returns.",
            *universe.get("warnings", []),
            *history_warnings,
        ]
    )
    return {
        "candle_color": color,
        "trade_action": trade_action,
        "evaluated_years": years,
        "signal_count": signal_count,
        "config": config,
        "horizons": [_smart_horizon_stats(color, horizon, returns_by_horizon[horizon]) for horizon in SCAN_HORIZONS],
        "warnings": warnings,
    }


def normalize_smart_candle_config(payload: Any | None = None) -> dict[str, Any]:
    trend_filter = str(_payload_value(payload, "trend_filter", "all"))
    if trend_filter not in {"all", "above_sma200", "below_sma200"}:
        trend_filter = "all"
    return {
        "custom_symbols": _custom_symbols(_payload_value(payload, "custom_symbols", [])),
        "lookback_days": _clamp_int(_payload_value(payload, "lookback_days", 420), 120, 1600),
        "min_relative_volume": _clamp_float(_payload_value(payload, "min_relative_volume", 1.1), 0.1, 10),
        "min_avg_dollar_volume": _clamp_float(_payload_value(payload, "min_avg_dollar_volume", 25_000_000), 0, 5_000_000_000),
        "max_symbols": _clamp_int(_payload_value(payload, "max_symbols", 120), 1, 505),
        "include_neutral": bool(_payload_value(payload, "include_neutral", False)),
        "trend_filter": trend_filter,
    }


def classify_latest_candle(
    item: BreakoutUniverseItem,
    bars: list[BreakoutBar],
    config: dict[str, Any],
    *,
    include_chart: bool = True,
) -> dict[str, Any] | None:
    ordered = sorted([bar for bar in bars if _close(bar) > 0 and bar.high > 0 and bar.low > 0], key=lambda bar: bar.date)
    if len(ordered) < 90:
        return None
    context = _candle_context(ordered)
    if not context or not _passes_filters(context, config):
        return None

    color, score, components, summary = _classify_color(item, context, config)
    latest: BreakoutBar = context["latest"]
    return {
        "symbol": item.symbol,
        "company_name": item.company_name,
        "sector": item.sector,
        "candle_color": color,
        "signal_label": _signal_label(color),
        "score": round(min(100, max(0, score)), 2),
        "rank": 0,
        "price": round(_close(latest), 4),
        "as_of_date": latest.date,
        "open": round(latest.open, 4),
        "high": round(latest.high, 4),
        "low": round(latest.low, 4),
        "close": round(latest.close, 4),
        "body_pct": _round_or_none(context["body_pct"]),
        "body_to_range": _round_or_none(context["body_to_range"]),
        "close_location": _round_or_none(context["close_location"]),
        "upper_wick_pct": _round_or_none(context["upper_wick_pct"]),
        "lower_wick_pct": _round_or_none(context["lower_wick_pct"]),
        "relative_volume": _round_or_none(context["relative_volume"]),
        "avg_volume_50d": _round_or_none(context["avg_volume_50d"]),
        "avg_dollar_volume": _round_or_none(context["avg_dollar_volume"]),
        "rsi14": _round_or_none(context["rsi14"], 2),
        "return_5d": _round_or_none(context["return_5d"]),
        "return_20d": _round_or_none(context["return_20d"]),
        "sma20": _round_or_none(context["sma20"]),
        "sma40": _round_or_none(context["sma40"]),
        "sma50": _round_or_none(context["sma50"]),
        "sma200": _round_or_none(context["sma200"]),
        "trend_label": context["trend_label"],
        "summary": summary,
        "components": components,
        "data_source": latest.source,
        "warnings": [],
        "chart": _chart_points(ordered, context, color) if include_chart else [],
    }


def _candle_context(bars: list[BreakoutBar]) -> dict[str, Any] | None:
    values = [_close(bar) for bar in bars]
    volumes = [max(0, bar.volume) for bar in bars]
    latest = bars[-1]
    price = values[-1]
    day_range = max(latest.high - latest.low, 0.0001)
    body = latest.close - latest.open
    body_abs = abs(body)
    avg_volume_50 = _average(volumes[-51:-1]) if len(volumes) > 50 else _average(volumes[-50:])
    relative_volume = (volumes[-1] / avg_volume_50) if avg_volume_50 > 0 else 0
    sma20_series = _sma(values, 20)
    sma40_series = _sma(values, 40)
    sma50_series = _sma(values, 50)
    sma200_series = _sma(values, 200)
    sma20 = _last_number(sma20_series)
    sma40 = _last_number(sma40_series)
    sma50 = _last_number(sma50_series)
    sma200 = _last_number(sma200_series)
    rsi14 = _rsi(values, 14)
    return_5d = _window_return(values, 5) or 0
    return_20d = _window_return(values, 20) or 0
    return {
        "latest": latest,
        "price": price,
        "body": body,
        "body_pct": body_abs / max(latest.open, 0.0001),
        "body_to_range": body_abs / day_range,
        "close_location": (latest.close - latest.low) / day_range,
        "upper_wick_pct": max(0, latest.high - max(latest.open, latest.close)) / day_range,
        "lower_wick_pct": max(0, min(latest.open, latest.close) - latest.low) / day_range,
        "relative_volume": relative_volume,
        "avg_volume_50d": avg_volume_50,
        "avg_dollar_volume": avg_volume_50 * price,
        "rsi14": rsi14,
        "return_5d": return_5d,
        "return_20d": return_20d,
        "sma20": sma20,
        "sma40": sma40,
        "sma50": sma50,
        "sma200": sma200,
        "sma20_series": sma20_series,
        "sma40_series": sma40_series,
        "sma50_series": sma50_series,
        "sma200_series": sma200_series,
        "trend_label": _trend_label(price, sma20, sma50, sma200),
    }


def _classify_color(
    item: BreakoutUniverseItem,
    context: dict[str, Any],
    config: dict[str, Any],
) -> tuple[str, float, list[dict[str, Any]], str]:
    price = float(context["price"])
    sma20 = context["sma20"]
    sma50 = context["sma50"]
    sma200 = context["sma200"]
    rsi14 = float(context["rsi14"])
    rel_vol = float(context["relative_volume"])
    min_rel_vol = float(config["min_relative_volume"])
    bullish_body = context["body"] > 0 and context["body_to_range"] >= 0.35
    bearish_body = context["body"] < 0 and context["body_to_range"] >= 0.35
    close_high = context["close_location"] >= 0.68
    close_low = context["close_location"] <= 0.36
    volume_confirmed = rel_vol >= min_rel_vol
    above_sma20 = bool(sma20 and price >= sma20)
    above_sma50 = bool(sma50 and price >= sma50)
    above_sma200 = bool(sma200 and price >= sma200)
    below_sma50 = bool(sma50 and price < sma50)
    below_sma200 = bool(sma200 and price < sma200)
    improving = context["return_5d"] > -0.02 and context["return_20d"] > -0.08
    rebound = context["lower_wick_pct"] >= 0.25 and close_high and rsi14 < 58
    weakening = context["return_5d"] < 0 or (sma20 and price < sma20)
    breakdown = below_sma50 and (below_sma200 or context["return_20d"] <= -0.08 or rsi14 <= 42)

    blue_components = [
        _component("Bullish body", bullish_body, f"{context['body_to_range']:.0%} of range"),
        _component("Close near high", close_high, f"{context['close_location']:.0%} location"),
        _component("Volume confirmed", volume_confirmed, f"{rel_vol:.2f}x rel vol"),
        _component("Trend/reversal", (above_sma20 and above_sma50) or rebound, context["trend_label"]),
    ]
    red_components = [
        _component("Bearish body", bearish_body, f"{context['body_to_range']:.0%} of range"),
        _component("Close weak", close_low, f"{context['close_location']:.0%} location"),
        _component("Breakdown", breakdown, context["trend_label"]),
        _component("Weak RSI/return", rsi14 <= 45 or context["return_20d"] <= -0.08, f"RSI {rsi14:.1f}, 20D {context['return_20d']:.1%}"),
    ]
    pink_components = [
        _component("Weak close", close_low, f"{context['close_location']:.0%} location"),
        _component("Distribution volume", volume_confirmed, f"{rel_vol:.2f}x rel vol"),
        _component("Weakening trend", weakening, context["trend_label"]),
        _component("Not full breakdown", not breakdown, "caution before red"),
    ]

    blue_score = 38 + _passed_count(blue_components) * 12 + min(12, max(0, rel_vol - 1) * 7)
    if rebound:
        blue_score += 8
    if context["return_20d"] > 0.04:
        blue_score += 6

    red_score = 42 + _passed_count(red_components) * 12 + min(10, max(0, rel_vol - 1) * 6)
    if below_sma200:
        red_score += 8

    pink_score = 34 + _passed_count(pink_components) * 10 + min(8, max(0, rel_vol - 1) * 5)

    if _passed_count(red_components) >= 3 and breakdown:
        return "red", red_score, red_components, f"{item.symbol} printed a red risk candle: weak close, bearish structure, and {context['trend_label'].lower()}."
    if _passed_count(blue_components) >= 3 and improving:
        return "blue", blue_score, blue_components, f"{item.symbol} printed a blue smart-candle approximation: accumulation/reversal behavior with {rel_vol:.2f}x relative volume."
    if _passed_count(pink_components) >= 3:
        return "pink", pink_score, pink_components, f"{item.symbol} printed a pink caution candle: sell pressure or trend weakening without a confirmed breakdown."

    neutral_components = [
        _component("Bullish setup", _passed_count(blue_components) >= 3, "blue threshold"),
        _component("Caution setup", _passed_count(pink_components) >= 3, "pink threshold"),
        _component("Breakdown setup", _passed_count(red_components) >= 3, "red threshold"),
        _component("Volume filter", volume_confirmed, f"{rel_vol:.2f}x rel vol"),
    ]
    return "neutral", 20 + min(35, _passed_count(neutral_components) * 8), neutral_components, f"{item.symbol} has no strong smart-candle edge under the current rules."


def _passes_filters(context: dict[str, Any], config: dict[str, Any]) -> bool:
    if context["avg_dollar_volume"] < config["min_avg_dollar_volume"]:
        return False
    sma200 = context["sma200"]
    if config["trend_filter"] == "above_sma200" and sma200 and context["price"] < sma200:
        return False
    if config["trend_filter"] == "below_sma200" and sma200 and context["price"] >= sma200:
        return False
    return True


def _chart_points(bars: list[BreakoutBar], context: dict[str, Any], latest_color: str) -> list[dict[str, Any]]:
    start = max(0, len(bars) - 130)
    rows: list[dict[str, Any]] = []
    for index in range(start, len(bars)):
        rows.append(
            {
                "date": bars[index].date,
                "open": round(bars[index].open, 4),
                "high": round(bars[index].high, 4),
                "low": round(bars[index].low, 4),
                "close": round(bars[index].close, 4),
                "volume": round(max(0, bars[index].volume), 2),
                "sma20": _round_or_none(context["sma20_series"][index]),
                "sma40": _round_or_none(context["sma40_series"][index]),
                "sma50": _round_or_none(context["sma50_series"][index]),
                "sma200": _round_or_none(context["sma200_series"][index]),
                "candle_color": latest_color if index == len(bars) - 1 else None,
            }
        )
    return rows


def _scan_items(universe: dict[str, Any], config: dict[str, Any]) -> list[BreakoutUniverseItem]:
    return _append_custom_universe_items(_universe_items_from_out(universe)[: config["max_symbols"]], config["custom_symbols"])


def _smart_horizon_stats(color: str, horizon: int, values: list[float]) -> dict[str, Any]:
    stats = _horizon_stats(horizon, values)
    return {"candle_color": color, **stats}


def _custom_symbols(value: Any) -> list[str]:
    raw_symbols = value if isinstance(value, list) else []
    normalized: list[str] = []
    for raw in raw_symbols:
        symbol = normalize_symbol(str(raw))
        if not symbol or len(symbol) > 12:
            continue
        if symbol not in normalized:
            normalized.append(symbol)
    return normalized[:25]


def _rsi(values: list[float], period: int) -> float:
    if len(values) <= period:
        return 50.0
    changes = [values[index] - values[index - 1] for index in range(len(values) - period, len(values))]
    gains = [max(0, change) for change in changes]
    losses = [abs(min(0, change)) for change in changes]
    avg_gain = _average(gains)
    avg_loss = _average(losses)
    if avg_loss == 0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def _last_number(values: list[float | None]) -> float | None:
    for value in reversed(values):
        if isinstance(value, (int, float)) and math.isfinite(value):
            return float(value)
    return None


def _signal_label(color: str) -> str:
    return {
        "blue": "Blue accumulation / reversal",
        "pink": "Pink caution / distribution",
        "red": "Red breakdown risk",
        "neutral": "Neutral / no strong edge",
    }.get(color, "Neutral / no strong edge")


def _color_sort(color: str) -> int:
    return {"blue": 0, "pink": 1, "red": 2, "neutral": 3}.get(color, 4)


def _component(label: str, passed: bool, value: str) -> dict[str, Any]:
    return {"label": label, "passed": bool(passed), "value": value}


def _passed_count(components: list[dict[str, Any]]) -> int:
    return sum(1 for component in components if component["passed"])


def _unique(values: list[str]) -> list[str]:
    output: list[str] = []
    for value in values:
        if value and value not in output:
            output.append(value)
    return output


def _clamp_int(value: Any, low: int, high: int) -> int:
    try:
        return max(low, min(high, int(value)))
    except Exception:
        return low


def _clamp_float(value: Any, low: float, high: float) -> float:
    try:
        number = float(value)
    except Exception:
        return low
    if not math.isfinite(number):
        return low
    return max(low, min(high, number))


def _payload_value(payload: Any | None, key: str, default: Any) -> Any:
    if payload is None:
        return default
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)
