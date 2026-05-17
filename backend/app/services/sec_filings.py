from __future__ import annotations

import json
import re
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from xml.etree import ElementTree

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import ThirteenFFiling, ThirteenFHolding, ThirteenFWatch
from app.services.index_data import INDEX_DEFINITIONS
from app.services.market_data import get_prices


SEC_ARCHIVES_BASE = "https://www.sec.gov/Archives/edgar/data"
SEC_BROWSE_BASE = "https://www.sec.gov/cgi-bin/browse-edgar"
SEC_SUBMISSIONS_BASE = "https://data.sec.gov/submissions"


class SecFilingError(RuntimeError):
    pass


@dataclass(frozen=True)
class KnownManager:
    cik: str
    manager_name: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class FilingManagerCandidate:
    cik: str
    manager_name: str
    match_source: str
    latest_filing_date: date | None = None
    latest_report_period: date | None = None


@dataclass(frozen=True)
class FilingSearchResult:
    query: str
    candidates: list[FilingManagerCandidate]
    warning: str | None = None


@dataclass(frozen=True)
class FilingMetadata:
    manager_name: str
    cik: str
    form: str
    accession_number: str
    filing_date: date
    report_period: date | None
    primary_document_url: str
    info_table_url: str | None


@dataclass(frozen=True)
class FilingHolding:
    issuer_name: str
    title_class: str | None
    cusip: str | None
    value: float
    shares: float
    put_call: str | None
    symbol: str | None = None
    weight: float = 0


@dataclass(frozen=True)
class FilingWindow:
    report_period: date
    start_date: date
    due_date: date


@dataclass(frozen=True)
class FilingCacheResult:
    watch_id: int
    years: int
    cached_filings: int
    cached_holdings: int
    priced_holdings: int
    warnings: list[str]


@dataclass(frozen=True)
class CopycatPeriod:
    report_period: date
    filing_date: date
    start_date: date
    end_date: date
    starting_value: float
    ending_value: float
    return_pct: float
    benchmark_return_pct: float
    holdings_count: int
    priced_holdings_count: int
    top_holdings: list[FilingHolding]


@dataclass(frozen=True)
class CopycatPerformance:
    watch_id: int
    manager_name: str
    cik: str
    years: int
    starting_value: float
    ending_value: float
    total_return: float
    annualized_return: float
    benchmark_symbol: str
    benchmark_ending_value: float
    benchmark_total_return: float
    cached_filings: int
    cached_holdings: int
    priced_holdings: int
    periods: list[CopycatPeriod]
    warnings: list[str]


KNOWN_MANAGERS = (
    KnownManager("1067983", "BERKSHIRE HATHAWAY INC", ("berkshire hathaway", "warren buffett", "buffett")),
    KnownManager("1350694", "BRIDGEWATER ASSOCIATES, LP", ("bridgewater", "ray dalio", "dalio")),
    KnownManager("1037389", "RENAISSANCE TECHNOLOGIES LLC", ("renaissance technologies", "jim simons", "simons", "rentech")),
    KnownManager("1336528", "PERSHING SQUARE CAPITAL MANAGEMENT, L.P.", ("pershing square", "bill ackman", "ackman")),
    KnownManager("1423053", "CITADEL ADVISORS LLC", ("citadel", "citadel advisors", "ken griffin", "griffin")),
    KnownManager("1649339", "SCION ASSET MANAGEMENT, LLC", ("scion", "scion asset management", "michael burry", "burry")),
    KnownManager("1040273", "THIRD POINT LLC", ("third point", "daniel loeb", "loeb")),
    KnownManager("1167483", "TIGER GLOBAL MANAGEMENT LLC", ("tiger global", "chase coleman", "coleman")),
    KnownManager("1061768", "BAUPOST GROUP LLC/MA", ("baupost", "seth klarman", "klarman")),
)

COMMON_ISSUER_SYMBOLS = {
    "ACTIVISION BLIZZARD INC": "ATVI",
    "ALLY FINL INC": "ALLY",
    "ALPHABET INC CAP STK CL A": "GOOGL",
    "ALPHABET INC CAP STK CL C": "GOOG",
    "AMERICAN EXPRESS CO": "AXP",
    "APPLE INC": "AAPL",
    "BANK AMER CORP": "BAC",
    "BANK OF AMERICA CORP": "BAC",
    "BERKSHIRE HATHAWAY INC DEL CL A": "BRK.A",
    "BERKSHIRE HATHAWAY INC DEL CL B": "BRK.B",
    "CHEVRON CORP NEW": "CVX",
    "CITIGROUP INC": "C",
    "COCA COLA CO": "KO",
    "DAVITA INC": "DVA",
    "HP INC": "HPQ",
    "KRAFT HEINZ CO": "KHC",
    "LIBERTY MEDIA CORP DEL": "FWONK",
    "MASTERCARD INCORPORATED": "MA",
    "MICROSOFT CORP": "MSFT",
    "MOODYS CORP": "MCO",
    "OCCIDENTAL PETE CORP": "OXY",
    "PARAMOUNT GLOBAL": "PARA",
    "PROCTER AND GAMBLE CO": "PG",
    "SIRIUS XM HOLDINGS INC": "SIRI",
    "SNOWFLAKE INC": "SNOW",
    "VISA INC": "V",
}


def normalize_cik(cik: str | int) -> str:
    digits = re.sub(r"\D", "", str(cik))
    if not digits:
        raise SecFilingError("CIK is required")
    return digits.zfill(10)[-10:]


def cik_for_archive(cik: str | int) -> str:
    return str(int(normalize_cik(cik)))


def current_13f_filing_window(today: date | None = None) -> FilingWindow | None:
    current = today or date.today()
    report_periods = [
        date(current.year - 1, 12, 31),
        date(current.year, 3, 31),
        date(current.year, 6, 30),
        date(current.year, 9, 30),
        date(current.year, 12, 31),
    ]
    for report_period in report_periods:
        start = report_period + timedelta(days=1)
        due = report_period + timedelta(days=45)
        if start <= current <= due:
            return FilingWindow(report_period=report_period, start_date=start, due_date=due)
    return None


def next_13f_filing_window_start(today: date | None = None) -> date:
    current = today or date.today()
    report_periods: list[date] = []
    for year in range(current.year - 1, current.year + 3):
        report_periods.extend(
            [
                date(year, 3, 31),
                date(year, 6, 30),
                date(year, 9, 30),
                date(year, 12, 31),
            ]
        )
    future_starts = sorted(report_period + timedelta(days=1) for report_period in report_periods if report_period + timedelta(days=1) > current)
    return future_starts[0]


def next_13f_check_at(now: datetime | None = None, latest_report_period: date | None = None) -> datetime:
    current = now or utc_now()
    window = current_13f_filing_window(current.date())
    if window and (latest_report_period is None or latest_report_period < window.report_period):
        return current + timedelta(hours=2)
    next_start = next_13f_filing_window_start(current.date())
    return datetime.combine(next_start, time(hour=6))


def utc_now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def search_13f_managers(query: str, limit: int = 8, fetch_remote: bool = True) -> FilingSearchResult:
    cleaned = query.strip()
    if len(cleaned) < 2:
        return FilingSearchResult(query=cleaned, candidates=[], warning="Enter at least two characters.")

    candidates = _known_manager_candidates(cleaned)
    warning = None
    if fetch_remote and len(candidates) < limit:
        try:
            candidates.extend(_browse_edgar_candidates(cleaned))
        except SecFilingError as exc:
            warning = f"SEC search was unavailable; showing local manager matches. {exc}"

    return FilingSearchResult(query=cleaned, candidates=_dedupe_candidates(candidates)[:limit], warning=warning)


def resolve_13f_manager(query: str, cik: str | None = None, manager_name: str | None = None) -> FilingManagerCandidate:
    if cik:
        normalized = normalize_cik(cik)
        return FilingManagerCandidate(cik=normalized, manager_name=(manager_name or query).strip(), match_source="user")

    result = search_13f_managers(query)
    if not result.candidates:
        raise SecFilingError(f"No Form 13F manager match found for {query!r}")
    return result.candidates[0]


def fetch_latest_13f_filing(cik: str) -> FilingMetadata:
    normalized = normalize_cik(cik)
    submissions = _fetch_json(f"{SEC_SUBMISSIONS_BASE}/CIK{normalized}.json")
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    if not isinstance(forms, list):
        raise SecFilingError("SEC submissions payload did not include recent filings")

    for index, form in enumerate(forms):
        form_text = str(form).upper()
        if not form_text.startswith("13F-HR"):
            continue
        accession_number = _array_value(recent, "accessionNumber", index)
        primary_document = _array_value(recent, "primaryDocument", index)
        filing_date = _parse_date(_array_value(recent, "filingDate", index))
        report_period = _parse_date(_array_value(recent, "reportDate", index), required=False)
        if not accession_number or not primary_document or not filing_date:
            continue
        primary_url = _archive_document_url(normalized, accession_number, primary_document)
        info_table_url = _find_information_table_url(normalized, accession_number, primary_document)
        return FilingMetadata(
            manager_name=str(submissions.get("name") or normalized),
            cik=normalized,
            form=form_text,
            accession_number=accession_number,
            filing_date=filing_date,
            report_period=report_period,
            primary_document_url=primary_url,
            info_table_url=info_table_url,
        )

    raise SecFilingError("No recent 13F-HR filing found for this manager")


def fetch_13f_filing_history(cik: str, years: int = 4, today: date | None = None) -> list[FilingMetadata]:
    normalized = normalize_cik(cik)
    current = today or date.today()
    cutoff = current - timedelta(days=365 * years + 60)
    submissions = _fetch_json(f"{SEC_SUBMISSIONS_BASE}/CIK{normalized}.json")
    recent = submissions.get("filings", {}).get("recent", {})
    forms = recent.get("form", [])
    if not isinstance(forms, list):
        raise SecFilingError("SEC submissions payload did not include recent filings")

    latest_by_period: dict[date, FilingMetadata] = {}
    for index, form in enumerate(forms):
        form_text = str(form).upper()
        if not form_text.startswith("13F-HR"):
            continue
        accession_number = _array_value(recent, "accessionNumber", index)
        primary_document = _array_value(recent, "primaryDocument", index)
        filing_date = _parse_date(_array_value(recent, "filingDate", index))
        report_period = _parse_date(_array_value(recent, "reportDate", index), required=False)
        if not accession_number or not primary_document or not filing_date or not report_period or report_period < cutoff:
            continue
        primary_url = _archive_document_url(normalized, accession_number, primary_document)
        info_table_url = _find_information_table_url(normalized, accession_number, primary_document)
        metadata = FilingMetadata(
            manager_name=str(submissions.get("name") or normalized),
            cik=normalized,
            form=form_text,
            accession_number=accession_number,
            filing_date=filing_date,
            report_period=report_period,
            primary_document_url=primary_url,
            info_table_url=info_table_url,
        )
        existing = latest_by_period.get(report_period)
        if existing is None or metadata.filing_date < existing.filing_date:
            latest_by_period[report_period] = metadata

    return sorted(latest_by_period.values(), key=lambda filing: filing.report_period or filing.filing_date)


def sync_13f_history(db: Session, watch: ThirteenFWatch, years: int = 4, today: date | None = None) -> FilingCacheResult:
    warnings: list[str] = []
    current = today or date.today()
    cutoff = current - timedelta(days=365 * years + 60)
    try:
        filings = fetch_13f_filing_history(watch.cik, years=years, today=current)
    except SecFilingError as exc:
        filings = []
        warnings.append(f"SEC history refresh failed; using existing cache if available. {exc}")

    for metadata in filings:
        filing = db.scalar(
            select(ThirteenFFiling).where(
                ThirteenFFiling.watch_id == watch.id,
                ThirteenFFiling.accession_number == metadata.accession_number,
            )
        )
        if filing is None:
            filing = ThirteenFFiling(
                watch_id=watch.id,
                manager_name=metadata.manager_name,
                cik=metadata.cik,
                form=metadata.form,
                accession_number=metadata.accession_number,
                filing_date=metadata.filing_date,
                report_period=metadata.report_period,
            )
            db.add(filing)

        filing.manager_name = metadata.manager_name
        filing.cik = metadata.cik
        filing.form = metadata.form
        filing.filing_date = metadata.filing_date
        filing.report_period = metadata.report_period
        filing.primary_document_url = metadata.primary_document_url
        filing.info_table_url = metadata.info_table_url
        filing.updated_at = utc_now()
        db.flush()

        document_url = metadata.info_table_url or metadata.primary_document_url
        if document_url and not filing.raw_info_table_xml:
            try:
                content, _, _ = download_13f_document(document_url)
                filing.raw_info_table_xml = content.decode("utf-8", errors="replace")
            except SecFilingError as exc:
                warnings.append(f"Could not cache {metadata.accession_number}: {exc}")
                continue

        if filing.raw_info_table_xml:
            try:
                holdings = parse_13f_info_table(filing.raw_info_table_xml)
            except SecFilingError as exc:
                warnings.append(f"Could not parse {metadata.accession_number}: {exc}")
                continue
            for existing in db.scalars(select(ThirteenFHolding).where(ThirteenFHolding.filing_id == filing.id)).all():
                db.delete(existing)
            filing.holdings_count = len(holdings)
            filing.priced_holdings_count = sum(1 for holding in holdings if holding.symbol and not holding.put_call)
            filing.total_value = round(sum(holding.value for holding in holdings if holding.value > 0 and not holding.put_call), 2)
            for holding in holdings:
                db.add(
                    ThirteenFHolding(
                        filing_id=filing.id,
                        symbol=holding.symbol,
                        cusip=holding.cusip,
                        issuer_name=holding.issuer_name,
                        title_class=holding.title_class,
                        value=holding.value,
                        shares=holding.shares,
                        put_call=holding.put_call,
                        weight=holding.weight,
                    )
            )
            db.add(filing)

    selected_accessions = {metadata.accession_number for metadata in filings}
    selected_periods = {metadata.report_period for metadata in filings if metadata.report_period}
    if selected_accessions:
        for existing in db.scalars(select(ThirteenFFiling).where(ThirteenFFiling.watch_id == watch.id)).all():
            duplicate_period = existing.report_period in selected_periods and existing.accession_number not in selected_accessions
            outside_window = bool(existing.report_period and existing.report_period < cutoff)
            if duplicate_period or outside_window:
                db.delete(existing)

    db.commit()
    cached_filings = db.scalars(select(ThirteenFFiling).where(ThirteenFFiling.watch_id == watch.id)).all()
    return FilingCacheResult(
        watch_id=watch.id,
        years=years,
        cached_filings=len(cached_filings),
        cached_holdings=sum(filing.holdings_count for filing in cached_filings),
        priced_holdings=sum(filing.priced_holdings_count for filing in cached_filings),
        warnings=warnings,
    )


def parse_13f_info_table(xml_text: str) -> list[FilingHolding]:
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError as exc:
        raise SecFilingError("13F information table XML is malformed") from exc

    rows = [element for element in root.iter() if _local_name(element.tag) == "infoTable"]
    holdings: list[FilingHolding] = []
    for row in rows:
        issuer = _child_text(row, "nameOfIssuer")
        if not issuer:
            continue
        title_class = _child_text(row, "titleOfClass") or None
        cusip = _child_text(row, "cusip") or None
        value = _parse_number(_child_text(row, "value")) * 1000
        shares = _parse_number(_child_text(row, "sshPrnamt"))
        put_call = (_child_text(row, "putCall") or "").upper() or None
        symbol = _normalize_symbol(_child_text(row, "ticker") or _child_text(row, "symbol")) or resolve_issuer_symbol(issuer, title_class)
        holdings.append(
            FilingHolding(
                issuer_name=issuer,
                title_class=title_class,
                cusip=cusip,
                value=round(value, 2),
                shares=shares,
                put_call=put_call,
                symbol=symbol,
            )
        )

    total_long_value = sum(holding.value for holding in holdings if holding.value > 0 and not holding.put_call)
    if total_long_value <= 0:
        return holdings
    return [
        replace(holding, weight=round(holding.value / total_long_value, 8) if holding.value > 0 and not holding.put_call else 0)
        for holding in holdings
    ]


def resolve_issuer_symbol(issuer_name: str, title_class: str | None = None) -> str | None:
    normalized = _normalize_issuer_name(" ".join(item for item in [issuer_name, title_class or ""] if item))
    issuer_only = _normalize_issuer_name(issuer_name)
    mapping = _issuer_symbol_map()
    if normalized in mapping:
        return mapping[normalized]
    if issuer_only in mapping:
        return mapping[issuer_only]
    for key, symbol in mapping.items():
        if len(key) >= 8 and (issuer_only.startswith(key) or key.startswith(issuer_only)):
            return symbol
    return None


def simulate_13f_copycat_performance(
    db: Session,
    watch: ThirteenFWatch,
    years: int = 4,
    starting_value: float = 100_000,
    benchmark_symbol: str = "SPY",
    today: date | None = None,
) -> CopycatPerformance:
    current = today or date.today()
    cutoff = current - timedelta(days=365 * years + 60)
    cached_filings = db.scalars(
        select(ThirteenFFiling)
        .where(
            ThirteenFFiling.watch_id == watch.id,
            ThirteenFFiling.report_period.is_not(None),
            ThirteenFFiling.report_period >= cutoff,
        )
        .order_by(ThirteenFFiling.report_period.asc(), ThirteenFFiling.filing_date.asc())
    ).all()
    filings_by_period: dict[date, ThirteenFFiling] = {}
    for filing in cached_filings:
        if not filing.report_period:
            continue
        existing = filings_by_period.get(filing.report_period)
        if existing is None or filing.filing_date < existing.filing_date:
            filings_by_period[filing.report_period] = filing
    filings = list(filings_by_period.values())
    warnings: list[str] = []
    if len(filings) < 1:
        return CopycatPerformance(
            watch_id=watch.id,
            manager_name=watch.manager_name,
            cik=watch.cik,
            years=years,
            starting_value=starting_value,
            ending_value=starting_value,
            total_return=0,
            annualized_return=0,
            benchmark_symbol=benchmark_symbol,
            benchmark_ending_value=starting_value,
            benchmark_total_return=0,
            cached_filings=0,
            cached_holdings=0,
            priced_holdings=0,
            periods=[],
            warnings=["No cached 13F history is available for this manager yet."],
        )

    value = starting_value
    benchmark_value = starting_value
    periods: list[CopycatPeriod] = []
    first_start: date | None = None
    last_end: date | None = None
    benchmark = benchmark_symbol.upper().strip().replace("/", ".")

    for index, filing in enumerate(filings):
        if not filing.report_period:
            continue
        start_date = _next_business_day(filing.filing_date + timedelta(days=1))
        next_start = _next_business_day(filings[index + 1].filing_date + timedelta(days=1)) if index + 1 < len(filings) else _last_business_day(current)
        end_date = _previous_business_day(next_start) if next_start > start_date else next_start
        if end_date <= start_date:
            warnings.append(f"Skipped {filing.report_period.isoformat()} because there was no holding period after the public filing date.")
            continue

        holdings = db.scalars(select(ThirteenFHolding).where(ThirteenFHolding.filing_id == filing.id)).all()
        long_holdings = [holding for holding in holdings if holding.symbol and holding.weight > 0 and not holding.put_call]
        if not long_holdings:
            warnings.append(f"Skipped {filing.report_period.isoformat()} because no long equity symbols could be resolved from the 13F filing.")
            continue

        symbols = sorted({holding.symbol for holding in long_holdings if holding.symbol} | {benchmark})
        start_prices = get_prices(db, symbols, start_date)
        end_prices = get_prices(db, symbols, end_date)
        priced_weight = 0.0
        weighted_return = 0.0
        for holding in long_holdings:
            start_price = start_prices.get(holding.symbol or "")
            end_price = end_prices.get(holding.symbol or "")
            if not start_price or start_price <= 0 or end_price is None:
                continue
            priced_weight += holding.weight
            weighted_return += holding.weight * ((end_price / start_price) - 1)
        if priced_weight <= 0:
            warnings.append(f"Skipped {filing.report_period.isoformat()} because prices were unavailable for resolved symbols.")
            continue

        period_return = weighted_return / priced_weight
        benchmark_start = start_prices.get(benchmark)
        benchmark_end = end_prices.get(benchmark)
        benchmark_return = (benchmark_end / benchmark_start - 1) if benchmark_start and benchmark_start > 0 and benchmark_end else 0
        period_starting_value = value
        value *= 1 + period_return
        benchmark_value *= 1 + benchmark_return
        top_holdings = [
            FilingHolding(
                issuer_name=holding.issuer_name,
                title_class=holding.title_class,
                cusip=holding.cusip,
                value=holding.value,
                shares=holding.shares,
                put_call=holding.put_call,
                symbol=holding.symbol,
                weight=holding.weight,
            )
            for holding in sorted(long_holdings, key=lambda item: item.weight, reverse=True)[:5]
        ]
        periods.append(
            CopycatPeriod(
                report_period=filing.report_period,
                filing_date=filing.filing_date,
                start_date=start_date,
                end_date=end_date,
                starting_value=round(period_starting_value, 2),
                ending_value=round(value, 2),
                return_pct=round(period_return, 6),
                benchmark_return_pct=round(benchmark_return, 6),
                holdings_count=len(holdings),
                priced_holdings_count=len(long_holdings),
                top_holdings=top_holdings,
            )
        )
        first_start = first_start or start_date
        last_end = end_date

    total_return = (value / starting_value) - 1 if starting_value else 0
    annualized = 0.0
    if first_start and last_end and last_end > first_start and value > 0 and starting_value > 0:
        annualized = (value / starting_value) ** (365 / max(1, (last_end - first_start).days)) - 1
    cached_holdings = sum(filing.holdings_count for filing in cached_filings)
    priced_holdings = sum(filing.priced_holdings_count for filing in cached_filings)
    return CopycatPerformance(
        watch_id=watch.id,
        manager_name=watch.manager_name,
        cik=watch.cik,
        years=years,
        starting_value=starting_value,
        ending_value=round(value, 2),
        total_return=round(total_return, 6),
        annualized_return=round(annualized, 6),
        benchmark_symbol=benchmark,
        benchmark_ending_value=round(benchmark_value, 2),
        benchmark_total_return=round((benchmark_value / starting_value) - 1 if starting_value else 0, 6),
        cached_filings=len(cached_filings),
        cached_holdings=cached_holdings,
        priced_holdings=priced_holdings,
        periods=periods,
        warnings=warnings,
    )


def create_or_update_13f_watch(
    db: Session,
    user_id: int,
    query: str,
    cik: str | None = None,
    manager_name: str | None = None,
) -> ThirteenFWatch:
    candidate = resolve_13f_manager(query=query, cik=cik, manager_name=manager_name)
    watch = db.scalar(select(ThirteenFWatch).where(ThirteenFWatch.user_id == user_id, ThirteenFWatch.cik == candidate.cik))
    if watch is None:
        watch = ThirteenFWatch(
            user_id=user_id,
            query=query.strip(),
            manager_name=candidate.manager_name,
            cik=candidate.cik,
            status="active",
        )
        db.add(watch)
    else:
        watch.query = query.strip()
        watch.manager_name = candidate.manager_name
        watch.status = "active"
        watch.warning = None
    db.flush()
    refresh_13f_watch(db, watch, commit=False)
    sync_13f_history(db, watch, years=4)
    db.commit()
    db.refresh(watch)
    return watch


def refresh_13f_watch(
    db: Session,
    watch: ThirteenFWatch,
    now: datetime | None = None,
    commit: bool = True,
) -> ThirteenFWatch:
    checked_at = now or utc_now()
    watch.last_checked_at = checked_at
    try:
        latest = fetch_latest_13f_filing(watch.cik)
        watch.manager_name = latest.manager_name
        watch.latest_form = latest.form
        watch.latest_accession_number = latest.accession_number
        watch.latest_filing_date = latest.filing_date
        watch.latest_report_period = latest.report_period
        watch.latest_primary_document_url = latest.primary_document_url
        watch.latest_info_table_url = latest.info_table_url
        watch.warning = None
    except SecFilingError as exc:
        watch.warning = str(exc)
    watch.next_check_at = next_13f_check_at(checked_at, watch.latest_report_period)
    watch.updated_at = checked_at
    db.add(watch)
    if commit:
        db.commit()
        db.refresh(watch)
        sync_13f_history(db, watch, years=4)
    return watch


def sync_due_13f_watches(db: Session, now: datetime | None = None) -> dict[str, int]:
    checked_at = now or utc_now()
    active_watches = db.scalars(select(ThirteenFWatch).where(ThirteenFWatch.status == "active")).all()
    refreshed = 0
    skipped = 0
    window = current_13f_filing_window(checked_at.date())

    for watch in active_watches:
        if watch.next_check_at and watch.next_check_at > checked_at:
            skipped += 1
            continue
        if not window:
            watch.next_check_at = next_13f_check_at(checked_at, watch.latest_report_period)
            watch.updated_at = checked_at
            db.add(watch)
            skipped += 1
            continue
        if watch.latest_report_period and watch.latest_report_period >= window.report_period:
            watch.next_check_at = next_13f_check_at(checked_at, watch.latest_report_period)
            watch.updated_at = checked_at
            db.add(watch)
            skipped += 1
            continue
        refresh_13f_watch(db, watch, now=checked_at, commit=False)
        sync_13f_history(db, watch, years=4)
        refreshed += 1

    db.commit()
    return {"watched": len(active_watches), "refreshed": refreshed, "skipped": skipped}


def download_13f_document(url: str) -> tuple[bytes, str, str]:
    if not url.startswith(f"{SEC_ARCHIVES_BASE}/"):
        raise SecFilingError("Only SEC archive documents can be downloaded")
    try:
        request = Request(url, headers=_sec_headers("application/xml,text/xml,text/html,*/*"))
        with urlopen(request, timeout=30) as response:
            content = response.read()
            content_type = response.headers.get_content_type() or "application/octet-stream"
    except (HTTPError, URLError, TimeoutError) as exc:
        raise SecFilingError(f"Could not download SEC filing document: {exc}") from exc

    filename = url.rstrip("/").rsplit("/", 1)[-1] or "13f-filing.xml"
    return content, content_type, filename


def _known_manager_candidates(query: str) -> list[FilingManagerCandidate]:
    normalized_query = _normalize_text(query)
    query_tokens = set(normalized_query.split())
    scored: list[tuple[int, FilingManagerCandidate]] = []
    for manager in KNOWN_MANAGERS:
        aliases = (_normalize_text(manager.manager_name), *(_normalize_text(alias) for alias in manager.aliases))
        score = 0
        for alias in aliases:
            alias_tokens = set(alias.split())
            if normalized_query == alias or normalized_query in alias or alias in normalized_query:
                score = max(score, 100)
            else:
                score = max(score, len(query_tokens & alias_tokens) * 10)
        if score:
            scored.append(
                (
                    score,
                    FilingManagerCandidate(
                        cik=normalize_cik(manager.cik),
                        manager_name=manager.manager_name,
                        match_source="famous-manager-list",
                    ),
                )
            )
    return [candidate for _, candidate in sorted(scored, key=lambda item: item[0], reverse=True)]


def _browse_edgar_candidates(query: str) -> list[FilingManagerCandidate]:
    url = (
        f"{SEC_BROWSE_BASE}?action=getcompany&company={quote_plus(query)}"
        "&type=13F-HR&owner=exclude&count=20&output=atom"
    )
    xml_text = _fetch_text(url)
    matches = re.findall(r"<title>\s*(?:13F-HR/A?|SC 13G/A?|[^<]*?)\s*-\s*([^<(]+?)\s*\((\d{10})\)", xml_text)
    candidates = [
        FilingManagerCandidate(cik=normalize_cik(cik), manager_name=_clean_manager_name(name), match_source="sec-edgar-search")
        for name, cik in matches
    ]
    if candidates:
        return candidates

    archive_matches = re.findall(r"/Archives/edgar/data/(\d+)/\d+/", xml_text)
    title_matches = re.findall(r"<title>\s*([^<]+?)\s*</title>", xml_text)
    fallback: list[FilingManagerCandidate] = []
    for index, cik in enumerate(archive_matches):
        name = title_matches[min(index + 1, len(title_matches) - 1)] if title_matches else query
        fallback.append(
            FilingManagerCandidate(cik=normalize_cik(cik), manager_name=_clean_manager_name(name), match_source="sec-edgar-search")
        )
    return fallback


def _dedupe_candidates(candidates: list[FilingManagerCandidate]) -> list[FilingManagerCandidate]:
    deduped: dict[str, FilingManagerCandidate] = {}
    for candidate in candidates:
        existing = deduped.get(candidate.cik)
        if existing is None or (not existing.latest_filing_date and candidate.latest_filing_date):
            deduped[candidate.cik] = candidate
    return list(deduped.values())


def _find_information_table_url(cik: str, accession_number: str, primary_document: str) -> str | None:
    index_url = _archive_document_url(cik, accession_number, "index.json")
    try:
        archive_index = _fetch_json(index_url)
    except SecFilingError:
        return None

    items = archive_index.get("directory", {}).get("item", [])
    if not isinstance(items, list):
        return None

    def item_score(item: dict[str, object]) -> int:
        name = str(item.get("name", "")).lower()
        description = str(item.get("description", "")).lower()
        file_type = str(item.get("type", "")).lower()
        if not name.endswith(".xml"):
            return 0
        if "infotable" in name or "information table" in description or "information table" in file_type:
            return 100
        if name != primary_document.lower() and not name.endswith(".xsl"):
            return 10
        return 0

    ranked = sorted(((item_score(item), item) for item in items), key=lambda item: item[0], reverse=True)
    for score, item in ranked:
        if score > 0:
            return _archive_document_url(cik, accession_number, str(item.get("name")))
    return None


def _archive_document_url(cik: str, accession_number: str, document_name: str) -> str:
    accession_path = accession_number.replace("-", "")
    return f"{SEC_ARCHIVES_BASE}/{cik_for_archive(cik)}/{accession_path}/{document_name}"


def _array_value(payload: dict[str, object], key: str, index: int) -> str:
    values = payload.get(key, [])
    if not isinstance(values, list) or index >= len(values):
        return ""
    value = values[index]
    return "" if value is None else str(value)


def _parse_date(value: str, required: bool = True) -> date | None:
    if not value:
        if required:
            raise SecFilingError("SEC filing date is missing")
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError as exc:
        if required:
            raise SecFilingError(f"SEC filing date {value!r} is invalid") from exc
        return None


def _fetch_json(url: str) -> dict[str, object]:
    text = _fetch_text(url, accept="application/json")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise SecFilingError("SEC returned malformed JSON") from exc
    if not isinstance(payload, dict):
        raise SecFilingError("SEC returned an unexpected JSON payload")
    return payload


def _fetch_text(url: str, accept: str = "application/atom+xml,application/xml,text/xml,text/html,*/*") -> str:
    try:
        request = Request(url, headers=_sec_headers(accept))
        with urlopen(request, timeout=20) as response:
            body = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
            return body.decode(charset, errors="replace")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise SecFilingError(f"SEC request failed: {exc}") from exc


def _sec_headers(accept: str) -> dict[str, str]:
    return {
        "Accept": accept,
        "User-Agent": get_settings().sec_user_agent,
    }


def _normalize_text(value: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", value.lower()).strip()


def _clean_manager_name(value: str) -> str:
    cleaned = re.sub(r"^\s*13F-HR/A?\s*-\s*", "", value, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*\(\d{10}\).*", "", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip() or value.strip()


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child_text(element: ElementTree.Element, child_name: str) -> str:
    for child in element.iter():
        if _local_name(child.tag) == child_name and child.text:
            return child.text.strip()
    return ""


def _parse_number(value: str) -> float:
    if not value:
        return 0
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return 0


def _normalize_symbol(value: str) -> str | None:
    cleaned = value.upper().strip().replace("/", ".")
    cleaned = re.sub(r"[^A-Z0-9.]+", "", cleaned)
    return cleaned or None


@lru_cache(maxsize=1)
def _issuer_symbol_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    for issuer, symbol in COMMON_ISSUER_SYMBOLS.items():
        mapping[_normalize_issuer_name(issuer)] = symbol
    for definition in INDEX_DEFINITIONS.values():
        for holding in definition.holdings:
            name = str(holding["name"])
            symbol = str(holding["symbol"])
            mapping.setdefault(_normalize_issuer_name(name), symbol)
    return mapping


def _normalize_issuer_name(value: str) -> str:
    normalized = re.sub(r"[^A-Z0-9 ]+", " ", value.upper().replace("&", " AND "))
    stop_words = {
        "ADR",
        "AND",
        "CAP",
        "CLASS",
        "CL",
        "COM",
        "COMMON",
        "CORP",
        "CORPORATION",
        "CO",
        "DEL",
        "INC",
        "INCORPORATED",
        "LTD",
        "NEW",
        "ORD",
        "PLC",
        "SHS",
        "STK",
        "STOCK",
    }
    tokens = [token for token in normalized.split() if token and token not in stop_words]
    return " ".join(tokens)


def _next_business_day(value: date) -> date:
    current = value
    while current.weekday() >= 5:
        current += timedelta(days=1)
    return current


def _previous_business_day(value: date) -> date:
    current = value
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def _last_business_day(value: date) -> date:
    return _previous_business_day(value)
