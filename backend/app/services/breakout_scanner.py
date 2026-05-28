from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from contextlib import redirect_stderr, redirect_stdout
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from html.parser import HTMLParser
import io
import json
import logging
import math
import ssl
from statistics import median
import threading
import time
from typing import Any
from urllib.request import Request, urlopen

import certifi
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import BreakoutOhlcvBar, BreakoutScannerScanRun, BreakoutUniverseMember, utc_now
from app.services.index_data import INDEX_DEFINITIONS
from app.services.market_data import normalize_symbol


_logger = logging.getLogger(__name__)

SP500_SOURCE_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
SP500_SOURCE_NAME = "Wikipedia S&P 500 constituents"
SP500_FALLBACK_SOURCE = "FinanceOS SPY holdings fallback cache"
PROVIDER_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
UNIVERSE_CACHE_DAYS = 7
SCAN_HORIZONS = [5, 10, 20, 60]
DETECTORS = ["ceiling_breakout", "momentum_breakout", "near_breakout"]
MIN_PRICE = 10.0


@dataclass(frozen=True)
class BreakoutUniverseItem:
    symbol: str
    company_name: str
    sector: str
    source: str
    source_url: str


@dataclass(frozen=True)
class BreakoutBar:
    date: date
    open: float
    high: float
    low: float
    close: float
    adjusted_close: float
    volume: float
    source: str


class BreakoutUniverseError(RuntimeError):
    pass


def load_sp500_universe(db: Session, *, force_refresh: bool = False) -> dict[str, Any]:
    existing = _cached_universe_rows(db)
    if existing and not force_refresh and _universe_cache_fresh(existing):
        return _universe_out(existing, cache_status="cached", warnings=[])

    warnings: list[str] = []
    try:
        fetched = _fetch_sp500_universe()
    except Exception as exc:
        fetched = []
        warnings.append(f"Could not refresh current S&P 500 constituents: {exc}")

    if fetched:
        _replace_universe_cache(db, fetched)
        return _universe_out(_cached_universe_rows(db), cache_status="fresh", warnings=warnings)

    if existing:
        warnings.append("Using cached S&P 500 constituents because the current public source was unavailable.")
        return _universe_out(existing, cache_status="stale-cache", warnings=warnings)

    fallback = _fallback_universe()
    _replace_universe_cache(db, fallback)
    warnings.append("Using FinanceOS SPY holdings fallback because current S&P 500 constituents could not be downloaded.")
    return _universe_out(_cached_universe_rows(db), cache_status="fallback", warnings=warnings)


def run_breakout_scan(db: Session, user_id: int, payload: Any | None = None, *, force: bool = False) -> dict[str, Any]:
    config = normalize_scan_config(payload)
    market_date = date.today()
    config_hash = _config_hash(config)
    if not force:
        cached = db.scalar(
            select(BreakoutScannerScanRun)
            .where(
                BreakoutScannerScanRun.user_id == user_id,
                BreakoutScannerScanRun.market_date == market_date,
                BreakoutScannerScanRun.config_hash == config_hash,
                BreakoutScannerScanRun.status == "completed",
            )
            .order_by(BreakoutScannerScanRun.scanned_at.desc(), BreakoutScannerScanRun.id.desc())
        )
        if cached:
            result = _json_load(cached.result_json, {})
            if result:
                return result

    universe = load_sp500_universe(db)
    items = _universe_items_from_out(universe)[: config["max_symbols"]]
    start_date = market_date - timedelta(days=max(260, int(config["lookback_days"]) + 80))
    histories, history_warnings = load_ohlcv_histories(
        db,
        [item.symbol for item in items],
        start_date,
        market_date,
        force_refresh=force,
    )

    signals: list[dict[str, Any]] = []
    for item in items:
        bars = histories.get(item.symbol, [])
        setups = detect_breakout_setups(item, bars, config, include_chart=True)
        signals.extend(setups)

    signals.sort(key=lambda row: (-float(row["score"]), str(row["symbol"]), str(row["detector_type"])))
    for index, signal in enumerate(signals, start=1):
        signal["rank"] = index

    warnings = _unique(
        [
            "Educational scanner only. Breakout setups are research prompts, not trade instructions.",
            *universe.get("warnings", []),
            *history_warnings,
        ]
    )
    data_source = _data_source_label(universe, history_warnings)
    scan_run = BreakoutScannerScanRun(
        user_id=user_id,
        market_date=market_date,
        config_hash=config_hash,
        config_json=json.dumps(config, sort_keys=True),
        data_source=data_source,
        warnings_json=json.dumps(warnings),
        result_json="{}",
    )
    db.add(scan_run)
    db.flush()
    result = {
        "scan_run_id": scan_run.id,
        "scanned_at": scan_run.scanned_at,
        "market_date": market_date,
        "data_source": data_source,
        "universe_count": int(universe["count"]),
        "scanned_symbols": len(items),
        "config": config,
        "signals": signals,
        "warnings": warnings,
    }
    scan_run.result_json = json.dumps(result, default=str)
    db.add(scan_run)
    db.commit()
    return result


def run_breakout_backtest(db: Session, user_id: int, payload: Any | None = None) -> dict[str, Any]:
    del user_id
    config = normalize_scan_config(payload)
    detector = _payload_value(payload, "detector", "ceiling_breakout")
    if detector not in DETECTORS:
        detector = "ceiling_breakout"
    years = _clamp_int(_payload_value(payload, "years", 5), 1, 10)
    config["detectors"] = [detector]
    market_date = date.today()
    start_date = market_date - timedelta(days=(years * 365) + int(config["lookback_days"]) + 120)
    universe = load_sp500_universe(db)
    items = _universe_items_from_out(universe)[: config["max_symbols"]]
    histories, history_warnings = load_ohlcv_histories(db, [item.symbol for item in items], start_date, market_date, force_refresh=False)

    returns_by_horizon: dict[int, list[float]] = {horizon: [] for horizon in SCAN_HORIZONS}
    signal_count = 0
    max_horizon = max(SCAN_HORIZONS)
    for item in items:
        bars = sorted(histories.get(item.symbol, []), key=lambda bar: bar.date)
        if len(bars) < 260 + max_horizon:
            continue
        minimum_index = max(220, min(len(bars) - max_horizon - 1, int(config["lookback_days"] * 0.45)))
        last_signal_index = -999
        for index in range(minimum_index, len(bars) - max_horizon):
            if index - last_signal_index < 10:
                continue
            setups = detect_breakout_setups(item, bars[: index + 1], config, include_chart=False)
            if not setups:
                continue
            last_signal_index = index
            signal_count += 1
            entry = _close(bars[index])
            if entry <= 0:
                continue
            for horizon in SCAN_HORIZONS:
                exit_price = _close(bars[index + horizon])
                returns_by_horizon[horizon].append(round((exit_price / entry) - 1, 6))

    horizons = [_horizon_stats(horizon, returns_by_horizon[horizon]) for horizon in SCAN_HORIZONS]
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
        "detector": detector,
        "evaluated_years": years,
        "signal_count": signal_count,
        "config": config,
        "horizons": horizons,
        "warnings": warnings,
    }


def normalize_scan_config(payload: Any | None = None) -> dict[str, Any]:
    detectors = _payload_value(payload, "detectors", DETECTORS)
    detectors = [str(item) for item in detectors if str(item) in DETECTORS] if isinstance(detectors, list) else DETECTORS
    if not detectors:
        detectors = DETECTORS
    min_relative_volume = _clamp_float(_payload_value(payload, "min_relative_volume", 1.5), 0.1, 10)
    ideal_relative_volume = max(min_relative_volume, _clamp_float(_payload_value(payload, "ideal_relative_volume", 2.0), 0.1, 20))
    return {
        "detectors": detectors,
        "lookback_days": _clamp_int(_payload_value(payload, "lookback_days", 420), 120, 1600),
        "min_relative_volume": min_relative_volume,
        "ideal_relative_volume": ideal_relative_volume,
        "min_ceiling_touches": _clamp_int(_payload_value(payload, "min_ceiling_touches", 3), 1, 12),
        "ceiling_tolerance_pct": _clamp_float(_payload_value(payload, "ceiling_tolerance_pct", 0.025), 0.001, 0.15),
        "breakout_clearance_pct": _clamp_float(_payload_value(payload, "breakout_clearance_pct", 0.01), 0, 0.2),
        "near_breakout_pct": _clamp_float(_payload_value(payload, "near_breakout_pct", 0.03), 0.001, 0.2),
        "min_avg_dollar_volume": _clamp_float(_payload_value(payload, "min_avg_dollar_volume", 25_000_000), 0, 5_000_000_000),
        "require_above_sma200": bool(_payload_value(payload, "require_above_sma200", True)),
        "max_symbols": _clamp_int(_payload_value(payload, "max_symbols", 120), 1, 505),
    }


def load_ohlcv_histories(
    db: Session,
    symbols: list[str],
    start_date: date,
    end_date: date,
    *,
    force_refresh: bool = False,
) -> tuple[dict[str, list[BreakoutBar]], list[str]]:
    normalized_symbols = [normalize_symbol(symbol) for symbol in symbols if normalize_symbol(symbol)]
    histories: dict[str, list[BreakoutBar]] = {}
    missing: list[str] = []
    for symbol in normalized_symbols:
        rows = [] if force_refresh else _cached_ohlcv(db, symbol, start_date, end_date)
        if rows and _history_sufficient(rows, start_date, end_date):
            histories[symbol] = rows
        else:
            missing.append(symbol)

    warnings: list[str] = []
    if missing:
        fetched = _fetch_yfinance_ohlcv_batch(missing, start_date, end_date)
        for symbol, bars in fetched.items():
            if bars:
                _upsert_ohlcv(db, symbol, bars)
        if fetched:
            db.commit()

        still_missing: list[str] = []
        for symbol in missing:
            rows = _cached_ohlcv(db, symbol, start_date, end_date)
            if rows and _history_sufficient(rows, start_date, end_date):
                histories[symbol] = rows
            else:
                still_missing.append(symbol)

        if still_missing:
            stooq_fetched = _fetch_stooq_ohlcv_batch(still_missing, start_date, end_date)
            for symbol, bars in stooq_fetched.items():
                if bars:
                    _upsert_ohlcv(db, symbol, bars)
            if stooq_fetched:
                db.commit()
            for symbol in still_missing:
                rows = _cached_ohlcv(db, symbol, start_date, end_date)
                if rows and _history_sufficient(rows, start_date, end_date):
                    histories[symbol] = rows
                    continue
                warnings.append(f"{symbol}: Yahoo Finance v8 OHLCV unavailable; symbol skipped.")

    return histories, _unique(warnings)


def detect_breakout_setups(
    item: BreakoutUniverseItem,
    bars: list[BreakoutBar],
    config: dict[str, Any],
    *,
    include_chart: bool = True,
) -> list[dict[str, Any]]:
    ordered = sorted([bar for bar in bars if _close(bar) > 0 and bar.high > 0 and bar.low > 0], key=lambda bar: bar.date)
    if len(ordered) < 90:
        return []
    context = _market_context(ordered, config)
    if not context or not _passes_shared_filters(context, config):
        return []

    setups: list[dict[str, Any]] = []
    detectors = set(config["detectors"])
    if "ceiling_breakout" in detectors:
        ceiling = _ceiling_breakout(item, ordered, context, config, include_chart=include_chart)
        if ceiling:
            setups.append(ceiling)
    if "momentum_breakout" in detectors:
        momentum = _momentum_breakout(item, ordered, context, config, include_chart=include_chart)
        if momentum:
            setups.append(momentum)
    if "near_breakout" in detectors:
        near = _near_breakout(item, ordered, context, config, include_chart=include_chart)
        if near:
            setups.append(near)
    return setups


def _ceiling_breakout(
    item: BreakoutUniverseItem,
    bars: list[BreakoutBar],
    context: dict[str, Any],
    config: dict[str, Any],
    *,
    include_chart: bool,
) -> dict[str, Any] | None:
    resistance = context["resistance"]
    if not resistance or context["touch_count"] < config["min_ceiling_touches"]:
        return None
    if context["relative_volume"] < config["min_relative_volume"]:
        return None
    breakout_pct = (context["price"] / resistance) - 1
    if breakout_pct < config["breakout_clearance_pct"]:
        return None
    score = 42 + min(context["touch_count"], 6) * 5 + _relative_volume_points(context, config) + _trend_points(context)
    score += min(15, breakout_pct * 550)
    return _setup_out(
        item,
        context,
        detector_type="ceiling_breakout",
        setup_label="Ceiling breakout research setup",
        score=score,
        breakout_pct=breakout_pct,
        proximity_pct=max(0, (resistance - context["price"]) / resistance),
        summary=f"{item.symbol} closed above a multi-touch resistance area with {context['relative_volume']:.2f}x relative volume and {context['trend_label'].lower()} context.",
        include_chart=include_chart,
    )


def _momentum_breakout(
    item: BreakoutUniverseItem,
    bars: list[BreakoutBar],
    context: dict[str, Any],
    config: dict[str, Any],
    *,
    include_chart: bool,
) -> dict[str, Any] | None:
    values = [_close(bar) for bar in bars]
    prior_high_63 = max(values[-64:-1]) if len(values) >= 64 else max(values[:-1])
    prior_high_252 = max(values[-253:-1]) if len(values) >= 253 else max(values[:-1])
    recent_return_20 = _window_return(values, 20) or 0
    cleared_recent = context["price"] >= prior_high_63 * (1 + config["breakout_clearance_pct"] * 0.5)
    near_year_high = context["price"] >= prior_high_252 * (1 - min(config["near_breakout_pct"], 0.02))
    if not (cleared_recent or near_year_high):
        return None
    if recent_return_20 < 0.04 or context["relative_volume"] < config["min_relative_volume"]:
        return None
    score = 38 + _relative_volume_points(context, config) + _trend_points(context) + min(20, recent_return_20 * 180)
    breakout_pct = (context["price"] / max(prior_high_63, 0.01)) - 1
    return _setup_out(
        item,
        context,
        detector_type="momentum_breakout",
        setup_label="Momentum breakout research setup",
        score=score,
        breakout_pct=breakout_pct,
        proximity_pct=0,
        summary=f"{item.symbol} is pressing through recent highs with a {recent_return_20:.1%} 20-day move and {context['relative_volume']:.2f}x relative volume.",
        include_chart=include_chart,
    )


def _near_breakout(
    item: BreakoutUniverseItem,
    bars: list[BreakoutBar],
    context: dict[str, Any],
    config: dict[str, Any],
    *,
    include_chart: bool,
) -> dict[str, Any] | None:
    del bars
    resistance = context["resistance"]
    if not resistance or context["touch_count"] < config["min_ceiling_touches"]:
        return None
    distance_below = (resistance - context["price"]) / resistance
    if distance_below < 0 or distance_below > config["near_breakout_pct"]:
        return None
    volume_floor = max(0.75, config["min_relative_volume"] * 0.6)
    if context["relative_volume"] < volume_floor:
        return None
    score = 34 + min(context["touch_count"], 6) * 4 + _trend_points(context) + _relative_volume_points(context, config) * 0.7
    score += max(0, (config["near_breakout_pct"] - distance_below) / config["near_breakout_pct"]) * 16
    return _setup_out(
        item,
        context,
        detector_type="near_breakout",
        setup_label="Near-breakout watch setup",
        score=score,
        breakout_pct=(context["price"] / resistance) - 1,
        proximity_pct=distance_below,
        summary=f"{item.symbol} is within {distance_below:.1%} of a multi-touch resistance area with volume building for manual review.",
        include_chart=include_chart,
    )


def _market_context(bars: list[BreakoutBar], config: dict[str, Any]) -> dict[str, Any] | None:
    values = [_close(bar) for bar in bars]
    volumes = [max(0, bar.volume) for bar in bars]
    if len(values) < 50:
        return None
    sma20_series = _sma(values, 20)
    sma50_series = _sma(values, 50)
    sma200_series = _sma(values, 200)
    avg_volume_50 = _average(volumes[-51:-1]) if len(volumes) > 50 else _average(volumes[-50:])
    relative_volume = (volumes[-1] / avg_volume_50) if avg_volume_50 > 0 else 0
    resistance, touch_count, first_touch = _resistance_profile(bars, config)
    price = values[-1]
    sma20 = _last_number(sma20_series)
    sma50 = _last_number(sma50_series)
    sma200 = _last_number(sma200_series)
    trend_label = _trend_label(price, sma20, sma50, sma200)
    return {
        "price": price,
        "as_of_date": bars[-1].date,
        "resistance": resistance,
        "touch_count": touch_count,
        "first_touch": first_touch,
        "relative_volume": relative_volume,
        "avg_volume_50d": avg_volume_50,
        "avg_dollar_volume": avg_volume_50 * price,
        "sma20": sma20,
        "sma50": sma50,
        "sma200": sma200,
        "sma20_series": sma20_series,
        "sma50_series": sma50_series,
        "sma200_series": sma200_series,
        "trend_label": trend_label,
        "data_source": bars[-1].source,
        "bars": bars,
    }


def _passes_shared_filters(context: dict[str, Any], config: dict[str, Any]) -> bool:
    if context["price"] < MIN_PRICE:
        return False
    if context["avg_dollar_volume"] < config["min_avg_dollar_volume"]:
        return False
    if config["require_above_sma200"] and context["sma200"] and context["price"] < context["sma200"]:
        return False
    return True


def _resistance_profile(bars: list[BreakoutBar], config: dict[str, Any]) -> tuple[float | None, int, date | None]:
    if len(bars) < 45:
        return None, 0, None
    lookback_count = min(len(bars) - 1, max(60, int(config["lookback_days"] * 5 / 7)))
    window = bars[-lookback_count - 1 : -1]
    highs = sorted([bar.high for bar in window if bar.high > 0])
    if not highs:
        return None, 0, None
    top_n = max(int(config["min_ceiling_touches"]), min(20, max(4, len(highs) // 10)))
    candidate = median(highs[-top_n:])
    tolerance = float(config["ceiling_tolerance_pct"])
    touches = [bar for bar in window if candidate > 0 and abs(bar.high - candidate) / candidate <= tolerance]
    if len(touches) < int(config["min_ceiling_touches"]):
        candidate = _percentile(highs, 0.95)
        touches = [bar for bar in window if candidate > 0 and abs(bar.high - candidate) / candidate <= tolerance]
    return round(candidate, 4), len(touches), touches[0].date if touches else None


def _setup_out(
    item: BreakoutUniverseItem,
    context: dict[str, Any],
    *,
    detector_type: str,
    setup_label: str,
    score: float,
    breakout_pct: float | None,
    proximity_pct: float | None,
    summary: str,
    include_chart: bool,
) -> dict[str, Any]:
    return {
        "symbol": item.symbol,
        "company_name": item.company_name,
        "sector": item.sector,
        "detector_type": detector_type,
        "setup_label": setup_label,
        "score": round(min(100, max(0, score)), 2),
        "rank": 0,
        "price": round(context["price"], 4),
        "as_of_date": context["as_of_date"],
        "resistance_level": _round_or_none(context["resistance"]),
        "breakout_pct": _round_or_none(breakout_pct),
        "proximity_pct": _round_or_none(proximity_pct),
        "touch_count": int(context["touch_count"]),
        "relative_volume": _round_or_none(context["relative_volume"]),
        "avg_volume_50d": _round_or_none(context["avg_volume_50d"]),
        "sma20": _round_or_none(context["sma20"]),
        "sma50": _round_or_none(context["sma50"]),
        "sma200": _round_or_none(context["sma200"]),
        "trend_label": context["trend_label"],
        "summary": summary,
        "data_source": context["data_source"],
        "warnings": [],
        "chart": _chart_points(context) if include_chart else [],
    }


def _chart_points(context: dict[str, Any]) -> list[dict[str, Any]]:
    bars: list[BreakoutBar] = context["bars"]
    start = max(0, len(bars) - 130)
    rows: list[dict[str, Any]] = []
    for index in range(start, len(bars)):
        rows.append(
            {
                "date": bars[index].date,
                "close": round(_close(bars[index]), 4),
                "volume": round(max(0, bars[index].volume), 2),
                "sma20": _round_or_none(context["sma20_series"][index]),
                "sma50": _round_or_none(context["sma50_series"][index]),
                "sma200": _round_or_none(context["sma200_series"][index]),
                "resistance": _round_or_none(context["resistance"]),
            }
        )
    return rows


def _fetch_sp500_universe() -> list[BreakoutUniverseItem]:
    request = Request(SP500_SOURCE_URL, headers={"User-Agent": "FinanceOS educational scanner contact local"})
    with urlopen(request, timeout=12, context=PROVIDER_SSL_CONTEXT) as response:
        html = response.read().decode("utf-8", errors="ignore")
    parser = _SP500TableParser()
    parser.feed(html)
    items = parser.items()
    if len(items) < 400:
        raise BreakoutUniverseError("public S&P 500 table did not contain enough symbols")
    return items


class _SP500TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._in_table = False
        self._done = False
        self._in_cell = False
        self._current_cell: list[str] = []
        self._current_row: list[str] = []
        self.rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._done:
            return
        attr_map = {key: value or "" for key, value in attrs}
        if tag == "table" and not self._in_table and "wikitable" in attr_map.get("class", ""):
            self._in_table = True
            return
        if self._in_table and tag == "tr":
            self._current_row = []
        if self._in_table and tag in {"td", "th"}:
            self._in_cell = True
            self._current_cell = []

    def handle_endtag(self, tag: str) -> None:
        if self._done:
            return
        if self._in_table and tag in {"td", "th"} and self._in_cell:
            self._current_row.append(_clean_cell("".join(self._current_cell)))
            self._in_cell = False
        if self._in_table and tag == "tr" and self._current_row:
            self.rows.append(self._current_row)
        if self._in_table and tag == "table":
            self._in_table = False
            self._done = True

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._current_cell.append(data)

    def items(self) -> list[BreakoutUniverseItem]:
        if not self.rows:
            return []
        header = [cell.lower() for cell in self.rows[0]]
        try:
            symbol_index = header.index("symbol")
            name_index = header.index("security")
            sector_index = header.index("gics sector")
        except ValueError:
            return []
        items: list[BreakoutUniverseItem] = []
        seen: set[str] = set()
        for row in self.rows[1:]:
            if len(row) <= max(symbol_index, name_index, sector_index):
                continue
            symbol = normalize_symbol(row[symbol_index])
            if not symbol or symbol in seen:
                continue
            seen.add(symbol)
            items.append(
                BreakoutUniverseItem(
                    symbol=symbol,
                    company_name=row[name_index] or symbol,
                    sector=row[sector_index] or "Unknown",
                    source=SP500_SOURCE_NAME,
                    source_url=SP500_SOURCE_URL,
                )
            )
        return items


def _fallback_universe() -> list[BreakoutUniverseItem]:
    items: list[BreakoutUniverseItem] = []
    for holding in INDEX_DEFINITIONS["SPY"].holdings:
        items.append(
            BreakoutUniverseItem(
                symbol=normalize_symbol(str(holding["symbol"])),
                company_name=str(holding.get("name") or holding["symbol"]),
                sector=str(holding.get("sector") or "Unknown"),
                source=SP500_FALLBACK_SOURCE,
                source_url=INDEX_DEFINITIONS["SPY"].source_url,
            )
        )
    return items


def _fetch_yfinance_ohlcv_batch(symbols: list[str], start_date: date, end_date: date) -> dict[str, list[BreakoutBar]]:
    try:
        import yfinance as yf
    except Exception:
        return {}

    output: dict[str, list[BreakoutBar]] = {}
    empty_chunk_failures = 0
    for chunk_start in range(0, len(symbols), 40):
        chunk = symbols[chunk_start : chunk_start + 40]
        provider_map = {symbol: symbol.replace(".", "-") for symbol in chunk}
        try:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                frame = yf.download(
                    " ".join(provider_map.values()),
                    start=start_date.isoformat(),
                    end=(end_date + timedelta(days=1)).isoformat(),
                    interval="1d",
                    auto_adjust=False,
                    group_by="ticker",
                    progress=False,
                    threads=True,
                )
        except Exception:
            empty_chunk_failures += 1
            if empty_chunk_failures >= 1:
                break
            continue
        chunk_had_bars = False
        for symbol, provider_symbol in provider_map.items():
            bars = _bars_from_yfinance_frame(symbol, provider_symbol, frame)
            if bars:
                output[symbol] = bars
                chunk_had_bars = True
        if chunk_had_bars:
            empty_chunk_failures = 0
        else:
            empty_chunk_failures += 1
            if empty_chunk_failures >= 1:
                break
    return output


def _bars_from_yfinance_frame(symbol: str, provider_symbol: str, frame: Any) -> list[BreakoutBar]:
    if frame is None or getattr(frame, "empty", True):
        return []
    try:
        columns = frame.columns
        if getattr(columns, "nlevels", 1) > 1:
            level0 = list(columns.get_level_values(0))
            level1 = list(columns.get_level_values(1))
            if provider_symbol in level0:
                data = frame[provider_symbol]
            elif provider_symbol in level1:
                data = frame.xs(provider_symbol, axis=1, level=1)
            else:
                return []
        else:
            data = frame
        bars: list[BreakoutBar] = []
        for index, row in data.iterrows():
            close = _number(row.get("Close"))
            adjusted_close = _number(row.get("Adj Close")) or close
            high = _number(row.get("High"))
            low = _number(row.get("Low"))
            open_price = _number(row.get("Open"))
            volume = _number(row.get("Volume"))
            if close <= 0 or high <= 0 or low <= 0:
                continue
            price_date = index.date() if hasattr(index, "date") else date.fromisoformat(str(index)[:10])
            bars.append(
                BreakoutBar(
                    date=price_date,
                    open=round(open_price or close, 4),
                    high=round(high, 4),
                    low=round(low, 4),
                    close=round(close, 4),
                    adjusted_close=round(adjusted_close or close, 4),
                    volume=round(max(0, volume), 2),
                    source="yfinance OHLCV cache",
                )
            )
        return bars
    except Exception:
        return []


def _fetch_stooq_ohlcv_batch(symbols: list[str], start_date: date, end_date: date) -> dict[str, list[BreakoutBar]]:
    """Fallback fetcher using Yahoo Finance v8 chart API with parallel requests."""
    period1 = int(datetime.combine(start_date, datetime.min.time()).timestamp())
    period2 = int(datetime.combine(end_date + timedelta(days=1), datetime.min.time()).timestamp())
    output: dict[str, list[BreakoutBar]] = {}

    _rate_lock = threading.Lock()
    _rate_last: list[float] = [0.0]

    def _fetch_one(symbol: str) -> tuple[str, list[BreakoutBar]]:
        with _rate_lock:
            wait = 0.05 - (time.monotonic() - _rate_last[0])
            if wait > 0:
                time.sleep(wait)
            _rate_last[0] = time.monotonic()
        yf_symbol = symbol.replace(".", "-")
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{yf_symbol}?period1={period1}&period2={period2}&interval=1d"
        try:
            request = Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                    "Accept": "application/json",
                },
            )
            with urlopen(request, timeout=12, context=PROVIDER_SSL_CONTEXT) as response:
                payload = json.loads(response.read().decode("utf-8", errors="ignore"))
            return symbol, _bars_from_yfinance_v8(symbol, payload)
        except Exception as exc:
            status = getattr(exc, "code", None)
            _logger.warning("Yahoo v8 OHLCV fetch failed | symbol=%s error=%s status=%s", symbol, type(exc).__name__, status)
            return symbol, []

    with ThreadPoolExecutor(max_workers=15) as pool:
        futures = {pool.submit(_fetch_one, symbol): symbol for symbol in symbols}
        for future in as_completed(futures):
            try:
                symbol, bars = future.result()
                if bars:
                    output[symbol] = bars
            except Exception:
                pass
    return output


def _bars_from_yfinance_v8(symbol: str, payload: Any) -> list[BreakoutBar]:
    del symbol
    try:
        result = (payload.get("chart") or {}).get("result") or []
        if not result:
            return []
        result = result[0]
        timestamps = result.get("timestamp") or []
        quote = ((result.get("indicators") or {}).get("quote") or [{}])[0]
        adjclose_list = (((result.get("indicators") or {}).get("adjclose") or [{}])[0]).get("adjclose") or []
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []
        bars: list[BreakoutBar] = []
        for i, ts in enumerate(timestamps):
            close = _number(closes[i] if i < len(closes) else None)
            high = _number(highs[i] if i < len(highs) else None)
            low = _number(lows[i] if i < len(lows) else None)
            if close <= 0 or high <= 0 or low <= 0:
                continue
            open_price = _number(opens[i] if i < len(opens) else None)
            volume = _number(volumes[i] if i < len(volumes) else None)
            adjusted_close = _number(adjclose_list[i] if i < len(adjclose_list) else None) or close
            price_date = datetime.fromtimestamp(ts, tz=timezone.utc).date()
            bars.append(
                BreakoutBar(
                    date=price_date,
                    open=round(open_price or close, 4),
                    high=round(high, 4),
                    low=round(low, 4),
                    close=round(close, 4),
                    adjusted_close=round(adjusted_close, 4),
                    volume=round(max(0, volume), 2),
                    source="Yahoo Finance v8 OHLCV",
                )
            )
        return bars
    except Exception:
        return []


def _upsert_ohlcv(db: Session, symbol: str, bars: list[BreakoutBar]) -> None:
    for bar in bars:
        row = db.scalar(select(BreakoutOhlcvBar).where(BreakoutOhlcvBar.symbol == symbol, BreakoutOhlcvBar.price_date == bar.date))
        if row is None:
            row = BreakoutOhlcvBar(
                symbol=symbol,
                price_date=bar.date,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                adjusted_close=bar.adjusted_close,
                volume=bar.volume,
                source=bar.source,
            )
        else:
            row.open = bar.open
            row.high = bar.high
            row.low = bar.low
            row.close = bar.close
            row.adjusted_close = bar.adjusted_close
            row.volume = bar.volume
            row.source = bar.source
            row.retrieved_at = utc_now()
        db.add(row)


def _cached_ohlcv(db: Session, symbol: str, start_date: date, end_date: date) -> list[BreakoutBar]:
    rows = db.scalars(
        select(BreakoutOhlcvBar)
        .where(
            BreakoutOhlcvBar.symbol == normalize_symbol(symbol),
            BreakoutOhlcvBar.price_date >= start_date,
            BreakoutOhlcvBar.price_date <= end_date,
        )
        .order_by(BreakoutOhlcvBar.price_date)
    ).all()
    return [
        BreakoutBar(
            date=row.price_date,
            open=row.open,
            high=row.high,
            low=row.low,
            close=row.close,
            adjusted_close=row.adjusted_close,
            volume=row.volume,
            source=row.source,
        )
        for row in rows
    ]




def _replace_universe_cache(db: Session, items: list[BreakoutUniverseItem]) -> None:
    now = utc_now()
    seen: set[str] = set()
    for item in items:
        if item.symbol in seen:
            continue
        seen.add(item.symbol)
        row = db.scalar(select(BreakoutUniverseMember).where(BreakoutUniverseMember.symbol == item.symbol))
        if row is None:
            row = BreakoutUniverseMember(
                symbol=item.symbol,
                company_name=item.company_name,
                sector=item.sector,
                source=item.source,
                source_url=item.source_url,
                retrieved_at=now,
            )
        else:
            row.company_name = item.company_name
            row.sector = item.sector
            row.source = item.source
            row.source_url = item.source_url
            row.retrieved_at = now
        db.add(row)
    db.commit()


def _cached_universe_rows(db: Session) -> list[BreakoutUniverseMember]:
    return db.scalars(select(BreakoutUniverseMember).order_by(BreakoutUniverseMember.symbol)).all()


def _universe_cache_fresh(rows: list[BreakoutUniverseMember]) -> bool:
    latest = max((row.retrieved_at for row in rows), default=None)
    if latest is None:
        return False
    return latest >= utc_now() - timedelta(days=UNIVERSE_CACHE_DAYS)


def _universe_out(rows: list[BreakoutUniverseMember], *, cache_status: str, warnings: list[str]) -> dict[str, Any]:
    source = rows[0].source if rows else SP500_SOURCE_NAME
    source_url = rows[0].source_url if rows else SP500_SOURCE_URL
    retrieved_at = max((row.retrieved_at for row in rows), default=None)
    return {
        "items": [
            {
                "symbol": row.symbol,
                "company_name": row.company_name,
                "sector": row.sector,
                "source": row.source,
                "source_url": row.source_url,
            }
            for row in rows
        ],
        "count": len(rows),
        "source": source,
        "source_url": source_url,
        "cache_status": cache_status,
        "retrieved_at": retrieved_at,
        "warnings": warnings,
    }


def _universe_items_from_out(universe: dict[str, Any]) -> list[BreakoutUniverseItem]:
    return [
        BreakoutUniverseItem(
            symbol=str(item["symbol"]),
            company_name=str(item.get("company_name") or item["symbol"]),
            sector=str(item.get("sector") or "Unknown"),
            source=str(item.get("source") or universe.get("source") or SP500_SOURCE_NAME),
            source_url=str(item.get("source_url") or universe.get("source_url") or SP500_SOURCE_URL),
        )
        for item in universe.get("items", [])
    ]


def _data_source_label(universe: dict[str, Any], history_warnings: list[str]) -> str:
    if universe.get("cache_status") == "fallback" or history_warnings:
        return "S&P 500 universe + yfinance/Yahoo Finance v8 OHLCV cache with labeled fallbacks"
    return "S&P 500 universe + yfinance/Yahoo Finance v8 OHLCV cache"


def _history_sufficient(rows: list[BreakoutBar], start_date: date, end_date: date) -> bool:
    if len(rows) < 80:
        return False
    return rows[0].date <= start_date + timedelta(days=21) and rows[-1].date >= end_date - timedelta(days=10)


def _horizon_stats(horizon: int, values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "horizon_days": horizon,
            "signal_count": 0,
            "win_rate": None,
            "average_return": None,
            "median_return": None,
            "p10_return": None,
            "p90_return": None,
        }
    ordered = sorted(values)
    return {
        "horizon_days": horizon,
        "signal_count": len(values),
        "win_rate": round(sum(1 for value in values if value > 0) / len(values), 6),
        "average_return": round(sum(values) / len(values), 6),
        "median_return": round(median(values), 6),
        "p10_return": round(_percentile(ordered, 0.10), 6),
        "p90_return": round(_percentile(ordered, 0.90), 6),
    }


def _config_hash(config: dict[str, Any]) -> str:
    return sha256(json.dumps(config, sort_keys=True).encode("utf-8")).hexdigest()[:24]


def _relative_volume_points(context: dict[str, Any], config: dict[str, Any]) -> float:
    ideal = max(float(config["ideal_relative_volume"]), 0.1)
    return min(18, max(0, context["relative_volume"] / ideal) * 18)


def _trend_points(context: dict[str, Any]) -> float:
    label = context["trend_label"]
    if label == "Strong uptrend":
        return 16
    if label == "Constructive trend":
        return 10
    if label == "Mixed trend":
        return 4
    return 0


def _trend_label(price: float, sma20: float | None, sma50: float | None, sma200: float | None) -> str:
    if not sma20 or not sma50:
        return "Limited trend data"
    if sma200 and price >= sma20 >= sma50 >= sma200:
        return "Strong uptrend"
    if price >= sma20 and sma20 >= sma50:
        return "Constructive trend"
    if sma200 and price < sma200:
        return "Below SMA 200"
    return "Mixed trend"


def _sma(values: list[float], period: int) -> list[float | None]:
    output: list[float | None] = []
    rolling = 0.0
    for index, value in enumerate(values):
        rolling += value
        if index >= period:
            rolling -= values[index - period]
        if index >= period - 1:
            output.append(rolling / period)
        else:
            output.append(None)
    return output


def _window_return(values: list[float], period: int) -> float | None:
    if len(values) <= period or values[-period - 1] <= 0:
        return None
    return (values[-1] / values[-period - 1]) - 1


def _close(bar: BreakoutBar) -> float:
    return bar.adjusted_close if bar.adjusted_close > 0 else bar.close


def _average(values: list[float]) -> float:
    clean = [value for value in values if isinstance(value, (int, float)) and value >= 0]
    return sum(clean) / len(clean) if clean else 0.0


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = (len(ordered) - 1) * percentile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] * (upper - index) + ordered[upper] * (index - lower)


def _last_number(values: list[float | None]) -> float | None:
    for value in reversed(values):
        if isinstance(value, (int, float)) and math.isfinite(value):
            return float(value)
    return None


def _round_or_none(value: Any, digits: int = 6) -> float | None:
    if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
        return None
    return round(float(value), digits)


def _number(value: Any) -> float:
    try:
        if value is None:
            return 0.0
        number = float(value)
        if not math.isfinite(number):
            return 0.0
        return number
    except Exception:
        return 0.0


def _payload_value(payload: Any | None, key: str, default: Any) -> Any:
    if payload is None:
        return default
    if isinstance(payload, dict):
        return payload.get(key, default)
    return getattr(payload, key, default)


def _clamp_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        return min(maximum, max(minimum, int(value)))
    except Exception:
        return minimum


def _clamp_float(value: Any, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
        if not math.isfinite(number):
            return minimum
        return min(maximum, max(minimum, number))
    except Exception:
        return minimum


def _json_load(payload: str | None, fallback: Any) -> Any:
    if not payload:
        return fallback
    try:
        return json.loads(payload)
    except Exception:
        return fallback


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        output.append(value)
    return output


def _clean_cell(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").replace("\n", " ").split()).strip()
