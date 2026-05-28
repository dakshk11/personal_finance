from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
import csv
import io
import logging
import ssl
from urllib.request import urlopen

import certifi
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import DataSyncLog, HoldingSnapshot, PriceBar, SecurityMetricSnapshot
from app.services.direct_indexing import Holding, holdings_from_dicts
from app.services.index_data import INDEX_DEFINITIONS, get_index_definition
from app.services.price_math import deterministic_price

PROVIDER_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())
_logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SecurityDailySnapshot:
    symbol: str
    price: float
    forward_pe: float | None
    forward_pe_5y_avg: float | None
    forward_pe_10y_avg: float | None
    price_source: str
    valuation_source: str
    warning: str | None = None


def normalize_symbol(symbol: str) -> str:
    return symbol.upper().strip().replace("/", ".")


def _provider_symbol(symbol: str) -> str:
    return normalize_symbol(symbol).replace(".", "-")


def holdings_for_index(symbol: str, exclusions: set[str] | None = None) -> list[Holding]:
    definition = get_index_definition(symbol)
    holdings = holdings_from_dicts(definition.holdings)
    if not exclusions:
        return holdings
    normalized_exclusions = {item.upper().strip().replace("/", ".") for item in exclusions}
    return [holding for holding in holdings if holding.symbol not in normalized_exclusions]


def latest_holding_snapshot(db: Session, index_symbol: str) -> list[HoldingSnapshot]:
    rows = db.scalars(
        select(HoldingSnapshot)
        .where(HoldingSnapshot.index_symbol == index_symbol.upper())
        .order_by(HoldingSnapshot.as_of_date.desc())
    ).all()
    if not rows:
        return []
    latest_date = rows[0].as_of_date
    return [row for row in rows if row.as_of_date == latest_date]


def seed_holding_snapshots(db: Session, as_of_date: date | None = None) -> list[str]:
    as_of_date = as_of_date or date.today()
    synced: list[str] = []
    for definition in INDEX_DEFINITIONS.values():
        existing = db.scalar(
            select(HoldingSnapshot).where(
                HoldingSnapshot.index_symbol == definition.symbol,
                HoldingSnapshot.as_of_date == as_of_date,
            )
        )
        if existing:
            synced.append(definition.symbol)
            continue
        for holding in definition.holdings:
            db.add(
                HoldingSnapshot(
                    index_symbol=definition.symbol,
                    as_of_date=as_of_date,
                    symbol=str(holding["symbol"]),
                    name=str(holding["name"]),
                    sector=str(holding.get("sector") or ""),
                    weight=float(holding["weight"]),
                    source=f"{definition.provider} public holdings/fallback cache",
                    source_url=definition.source_url,
                )
            )
        synced.append(definition.symbol)
    db.commit()
    return synced


def cached_price(db: Session, symbol: str, price_date: date) -> PriceBar | None:
    return db.scalar(select(PriceBar).where(PriceBar.symbol == normalize_symbol(symbol), PriceBar.price_date == price_date))


def get_prices(db: Session, symbols: list[str], price_date: date) -> dict[str, float]:
    prices: dict[str, float] = {}
    for symbol in symbols:
        normalized = symbol.upper().strip().replace("/", ".")
        row = cached_price(db, normalized, price_date)
        if row:
            prices[normalized] = row.adjusted_close
            continue
        value = deterministic_price(normalized, price_date)
        db.add(
            PriceBar(
                symbol=normalized,
                price_date=price_date,
                close=value,
                adjusted_close=value,
                dividend=0,
                split_ratio=1,
                source="deterministic offline fallback",
            )
        )
        prices[normalized] = value
    db.commit()
    return prices


def get_latest_security_snapshots(
    db: Session,
    symbols: list[str],
    snapshot_date: date,
    allow_external: bool = True,
) -> dict[str, SecurityDailySnapshot]:
    normalized_symbols = sorted({normalize_symbol(symbol) for symbol in symbols if symbol.strip()})
    prices = _get_latest_prices(db, normalized_symbols, snapshot_date, allow_external=allow_external)
    valuation_rows = _get_security_metric_snapshots(db, normalized_symbols, snapshot_date, allow_external=allow_external)

    snapshots: dict[str, SecurityDailySnapshot] = {}
    for symbol in normalized_symbols:
        price_row = prices[symbol]
        valuation_row = valuation_rows[symbol]
        snapshots[symbol] = SecurityDailySnapshot(
            symbol=symbol,
            price=price_row.adjusted_close,
            forward_pe=valuation_row.forward_pe,
            forward_pe_5y_avg=valuation_row.forward_pe_5y_avg,
            forward_pe_10y_avg=valuation_row.forward_pe_10y_avg,
            price_source=price_row.source,
            valuation_source=valuation_row.source,
            warning=valuation_row.warning,
        )
    return snapshots


def _get_latest_prices(
    db: Session,
    symbols: list[str],
    price_date: date,
    allow_external: bool,
) -> dict[str, PriceBar]:
    rows: dict[str, PriceBar] = {}
    missing: list[str] = []
    refreshable_fallbacks: list[str] = []
    for symbol in symbols:
        row = cached_price(db, symbol, price_date)
        if row:
            rows[symbol] = row
            if allow_external and row.source == "deterministic offline fallback":
                refreshable_fallbacks.append(symbol)
        else:
            missing.append(symbol)

    fetch_symbols = sorted(set(missing + refreshable_fallbacks))
    fetched_prices = _fetch_latest_prices(fetch_symbols) if allow_external and fetch_symbols else {}
    for symbol in refreshable_fallbacks:
        fetched_price = fetched_prices.get(symbol)
        if fetched_price and fetched_price > 0:
            row = rows[symbol]
            row.close = fetched_price
            row.adjusted_close = fetched_price
            row.source = "stooq daily close cache"
            db.add(row)

    for symbol in missing:
        fetched_price = fetched_prices.get(symbol)
        value = fetched_price if fetched_price and fetched_price > 0 else deterministic_price(symbol, price_date)
        row = PriceBar(
            symbol=symbol,
            price_date=price_date,
            close=value,
            adjusted_close=value,
            dividend=0,
            split_ratio=1,
            source="stooq daily close cache" if fetched_price else "deterministic offline fallback",
        )
        db.add(row)
        rows[symbol] = row
    db.commit()
    return rows


def _fetch_latest_prices(symbols: list[str]) -> dict[str, float]:
    prices = _fetch_stooq_latest_prices(symbols)
    missing = [symbol for symbol in symbols if symbol not in prices]
    if missing:
        prices.update(_fetch_yfinance_latest_prices(missing))
    return prices


def _fetch_stooq_latest_prices(symbols: list[str]) -> dict[str, float]:
    prices: dict[str, float] = {}
    for symbol in symbols:
        provider_symbol = f"{_provider_symbol(symbol).lower()}.us"
        url = f"https://stooq.com/q/l/?s={provider_symbol}&f=sd2t2ohlcv&h&e=csv"
        try:
            with urlopen(url, timeout=8, context=PROVIDER_SSL_CONTEXT) as response:
                payload = response.read().decode("utf-8", errors="ignore")
            rows = list(csv.DictReader(io.StringIO(payload)))
            if not rows:
                continue
            close = rows[0].get("Close")
            if not close or close == "N/D":
                continue
            value = float(close)
            if 0 < value < 100000:
                prices[normalize_symbol(symbol)] = round(value, 4)
        except Exception as exc:
            status = getattr(exc, "code", None)
            _logger.warning("stooq spot price fetch failed | symbol=%s error=%s status=%s", symbol, type(exc).__name__, status)
            continue
    return prices


def _fetch_yfinance_latest_prices(symbols: list[str]) -> dict[str, float]:
    prices: dict[str, float] = {}
    if not symbols:
        return prices
    try:
        import yfinance as yf
    except Exception:
        return prices

    for symbol in symbols:
        try:
            history = yf.Ticker(_provider_symbol(symbol)).history(period="5d", interval="1d", auto_adjust=False)
            if history is None or history.empty or "Close" not in history:
                continue
            close = history["Close"].dropna()
            if close.empty:
                continue
            prices[symbol] = round(float(close.iloc[-1]), 4)
        except Exception:
            continue
    return prices


def _cached_security_metric(db: Session, symbol: str, metric_date: date) -> SecurityMetricSnapshot | None:
    return db.scalar(
        select(SecurityMetricSnapshot).where(
            SecurityMetricSnapshot.symbol == normalize_symbol(symbol),
            SecurityMetricSnapshot.metric_date == metric_date,
        )
    )


def _get_security_metric_snapshots(
    db: Session,
    symbols: list[str],
    metric_date: date,
    allow_external: bool,
) -> dict[str, SecurityMetricSnapshot]:
    rows: dict[str, SecurityMetricSnapshot] = {}
    missing: list[str] = []
    for symbol in symbols:
        row = _cached_security_metric(db, symbol, metric_date)
        if row:
            rows[symbol] = row
        else:
            missing.append(symbol)

    fetched_metrics = _fetch_yfinance_forward_pe(missing) if allow_external and missing else {}
    for symbol in missing:
        fetched_forward_pe = fetched_metrics.get(symbol)
        row = _build_security_metric_snapshot(db, symbol, metric_date, fetched_forward_pe)
        db.add(row)
        rows[symbol] = row
    db.commit()
    return rows


def _fetch_yfinance_forward_pe(symbols: list[str]) -> dict[str, float]:
    metrics: dict[str, float] = {}
    if not symbols:
        return metrics
    try:
        import yfinance as yf
    except Exception:
        return metrics

    for symbol in symbols:
        try:
            info = yf.Ticker(_provider_symbol(symbol)).get_info()
            forward_pe = info.get("forwardPE") if isinstance(info, dict) else None
            if isinstance(forward_pe, (int, float)) and 0 < forward_pe < 300:
                metrics[symbol] = round(float(forward_pe), 2)
        except Exception:
            continue
    return metrics


def _build_security_metric_snapshot(db: Session, symbol: str, metric_date: date, fetched_forward_pe: float | None) -> SecurityMetricSnapshot:
    normalized = normalize_symbol(symbol)
    if fetched_forward_pe and fetched_forward_pe > 0:
        forward_pe: float | None = fetched_forward_pe
        source = "yfinance forward PE daily cache"
        warning: str | None = "5Y and 10Y forward P/E averages are estimated until enough local valuation history is cached."
    else:
        forward_pe = None
        source = "unavailable"
        warning = "Live forward P/E data unavailable; valuation metrics not shown."

    cached_5y_average = _historical_forward_pe_average(db, normalized, metric_date, 5)
    cached_10y_average = _historical_forward_pe_average(db, normalized, metric_date, 10)
    if forward_pe is not None and cached_5y_average is not None and cached_10y_average is not None:
        warning = None
    return SecurityMetricSnapshot(
        symbol=normalized,
        metric_date=metric_date,
        forward_pe=round(forward_pe, 2) if forward_pe is not None else None,
        forward_pe_5y_avg=round(cached_5y_average, 2) if cached_5y_average is not None else None,
        forward_pe_10y_avg=round(cached_10y_average, 2) if cached_10y_average is not None else None,
        source=source,
        warning=warning,
    )


def _historical_forward_pe_average(db: Session, symbol: str, metric_date: date, years: int) -> float | None:
    start = metric_date - timedelta(days=365 * years)
    rows = db.scalars(
        select(SecurityMetricSnapshot.forward_pe).where(
            SecurityMetricSnapshot.symbol == symbol,
            SecurityMetricSnapshot.metric_date >= start,
            SecurityMetricSnapshot.metric_date < metric_date,
            SecurityMetricSnapshot.forward_pe.is_not(None),
        )
    ).all()
    minimum_observations = 30 if years <= 5 else 60
    if len(rows) < minimum_observations:
        return None
    return sum(float(row) for row in rows) / len(rows)


def _deterministic_forward_pe(symbol: str) -> float:
    seed = sum((index + 3) * ord(char) for index, char in enumerate(symbol))
    return round(11 + (seed % 2600) / 100, 2)


def _symbol_adjustment(symbol: str, horizon_years: int) -> float:
    seed = sum((index + horizon_years) * ord(char) for index, char in enumerate(symbol))
    return ((seed % 900) - 250) / 1000


def _business_days(start: date, end: date) -> list[date]:
    days: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            days.append(current)
        current += timedelta(days=1)
    return days


def sync_price_history(db: Session, symbols: list[str], start: date, end: date) -> int:
    inserted = 0
    for price_date in _business_days(start, end):
        for symbol in symbols:
            normalized = symbol.upper().strip().replace("/", ".")
            if cached_price(db, normalized, price_date):
                continue
            value = deterministic_price(normalized, price_date)
            db.add(
                PriceBar(
                    symbol=normalized,
                    price_date=price_date,
                    close=value,
                    adjusted_close=value,
                    dividend=0,
                    split_ratio=1,
                    source="deterministic offline fallback",
                )
            )
            inserted += 1
    db.commit()
    return inserted


def sync_daily_data(db: Session) -> tuple[list[str], str | None]:
    started_at = datetime.now(UTC).replace(tzinfo=None)
    log = DataSyncLog(
        dataset="daily_market_data",
        source="free provider adapter with deterministic fallback",
        status="running",
        started_at=started_at,
    )
    db.add(log)
    db.commit()

    synced = seed_holding_snapshots(db)
    symbols = sorted({str(holding["symbol"]) for definition in INDEX_DEFINITIONS.values() for holding in definition.holdings})
    today = date.today()
    start = today - timedelta(days=10)
    sync_price_history(db, symbols, start, today)

    warning = "Using cached public holdings and deterministic fallback prices when free providers are unavailable."
    log.status = "completed"
    log.completed_at = datetime.now(UTC).replace(tzinfo=None)
    log.warning = warning
    db.add(log)
    db.commit()
    return synced, warning
