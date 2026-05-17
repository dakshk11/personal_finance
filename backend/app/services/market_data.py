from datetime import UTC, date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import DataSyncLog, HoldingSnapshot, PriceBar
from app.services.direct_indexing import Holding, holdings_from_dicts
from app.services.index_data import INDEX_DEFINITIONS, get_index_definition
from app.services.price_math import deterministic_price


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
    return db.scalar(select(PriceBar).where(PriceBar.symbol == symbol, PriceBar.price_date == price_date))


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
