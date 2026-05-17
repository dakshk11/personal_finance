from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.entities import ThirteenFWatch, User
from app.schemas.common import (
    ThirteenFCacheOut,
    ThirteenFHoldingOut,
    ThirteenFManagerCandidateOut,
    ThirteenFPerformanceOut,
    ThirteenFPerformancePeriodOut,
    ThirteenFSearchOut,
    ThirteenFSearchRequest,
    ThirteenFWatchOut,
    ThirteenFWatchRequest,
)
from app.services.sec_filings import (
    SecFilingError,
    create_or_update_13f_watch,
    download_13f_document,
    refresh_13f_watch,
    search_13f_managers,
    simulate_13f_copycat_performance,
    sync_13f_history,
    utc_now,
)


router = APIRouter(prefix="/filings", tags=["filings"])


def _watch_out(watch: ThirteenFWatch) -> ThirteenFWatchOut:
    download_url = f"/filings/13f/watches/{watch.id}/download" if watch.latest_info_table_url or watch.latest_primary_document_url else None
    return ThirteenFWatchOut(
        id=watch.id,
        query=watch.query,
        manager_name=watch.manager_name,
        cik=watch.cik,
        status=watch.status,
        latest_form=watch.latest_form,
        latest_accession_number=watch.latest_accession_number,
        latest_filing_date=watch.latest_filing_date,
        latest_report_period=watch.latest_report_period,
        latest_primary_document_url=watch.latest_primary_document_url,
        latest_info_table_url=watch.latest_info_table_url,
        last_checked_at=watch.last_checked_at,
        next_check_at=watch.next_check_at,
        last_downloaded_at=watch.last_downloaded_at,
        warning=watch.warning,
        download_url=download_url,
    )


def _candidate_out(candidate) -> ThirteenFManagerCandidateOut:
    return ThirteenFManagerCandidateOut(
        cik=candidate.cik,
        manager_name=candidate.manager_name,
        match_source=candidate.match_source,
        latest_filing_date=candidate.latest_filing_date,
        latest_report_period=candidate.latest_report_period,
    )


def _get_watch(db: Session, user: User, watch_id: int) -> ThirteenFWatch:
    watch = db.get(ThirteenFWatch, watch_id)
    if not watch or watch.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="13F watch not found")
    return watch


def _cache_out(result) -> ThirteenFCacheOut:
    return ThirteenFCacheOut(
        watch_id=result.watch_id,
        years=result.years,
        cached_filings=result.cached_filings,
        cached_holdings=result.cached_holdings,
        priced_holdings=result.priced_holdings,
        warnings=result.warnings,
    )


def _performance_out(result) -> ThirteenFPerformanceOut:
    return ThirteenFPerformanceOut(
        watch_id=result.watch_id,
        manager_name=result.manager_name,
        cik=result.cik,
        years=result.years,
        starting_value=result.starting_value,
        ending_value=result.ending_value,
        total_return=result.total_return,
        annualized_return=result.annualized_return,
        benchmark_symbol=result.benchmark_symbol,
        benchmark_ending_value=result.benchmark_ending_value,
        benchmark_total_return=result.benchmark_total_return,
        cached_filings=result.cached_filings,
        cached_holdings=result.cached_holdings,
        priced_holdings=result.priced_holdings,
        periods=[
            ThirteenFPerformancePeriodOut(
                report_period=period.report_period,
                filing_date=period.filing_date,
                start_date=period.start_date,
                end_date=period.end_date,
                starting_value=period.starting_value,
                ending_value=period.ending_value,
                return_pct=period.return_pct,
                benchmark_return_pct=period.benchmark_return_pct,
                holdings_count=period.holdings_count,
                priced_holdings_count=period.priced_holdings_count,
                top_holdings=[
                    ThirteenFHoldingOut(
                        symbol=holding.symbol,
                        issuer_name=holding.issuer_name,
                        value=holding.value,
                        shares=holding.shares,
                        weight=holding.weight,
                    )
                    for holding in period.top_holdings
                ],
            )
            for period in result.periods
        ],
        warnings=result.warnings,
    )


@router.post("/13f/search", response_model=ThirteenFSearchOut)
def search_13f(payload: ThirteenFSearchRequest, _: User = Depends(get_current_user)) -> ThirteenFSearchOut:
    result = search_13f_managers(payload.query)
    return ThirteenFSearchOut(
        query=result.query,
        candidates=[_candidate_out(candidate) for candidate in result.candidates],
        warning=result.warning,
    )


@router.get("/13f/watches", response_model=list[ThirteenFWatchOut])
def list_13f_watches(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[ThirteenFWatchOut]:
    watches = db.scalars(
        select(ThirteenFWatch)
        .where(ThirteenFWatch.user_id == user.id)
        .order_by(ThirteenFWatch.updated_at.desc(), ThirteenFWatch.created_at.desc())
    ).all()
    return [_watch_out(watch) for watch in watches]


@router.post("/13f/watches", response_model=ThirteenFWatchOut, status_code=status.HTTP_201_CREATED)
def create_13f_watch(
    payload: ThirteenFWatchRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ThirteenFWatchOut:
    try:
        watch = create_or_update_13f_watch(
            db=db,
            user_id=user.id,
            query=payload.query,
            cik=payload.cik,
            manager_name=payload.manager_name,
        )
    except SecFilingError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    return _watch_out(watch)


@router.post("/13f/watches/{watch_id}/refresh", response_model=ThirteenFWatchOut)
def refresh_13f(
    watch_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ThirteenFWatchOut:
    watch = _get_watch(db, user, watch_id)
    return _watch_out(refresh_13f_watch(db, watch))


@router.post("/13f/watches/{watch_id}/sync-history", response_model=ThirteenFCacheOut)
def sync_13f_history_endpoint(
    watch_id: int,
    years: int = 4,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ThirteenFCacheOut:
    watch = _get_watch(db, user, watch_id)
    years = max(1, min(years, 8))
    return _cache_out(sync_13f_history(db, watch, years=years))


@router.get("/13f/watches/{watch_id}/performance", response_model=ThirteenFPerformanceOut)
def get_13f_performance(
    watch_id: int,
    years: int = 4,
    starting_value: float = 100_000,
    benchmark_symbol: str = "SPY",
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ThirteenFPerformanceOut:
    watch = _get_watch(db, user, watch_id)
    years = max(1, min(years, 8))
    starting_value = max(1, starting_value)
    sync_13f_history(db, watch, years=years)
    result = simulate_13f_copycat_performance(
        db,
        watch,
        years=years,
        starting_value=starting_value,
        benchmark_symbol=benchmark_symbol,
    )
    return _performance_out(result)


@router.delete("/13f/watches/{watch_id}")
def delete_13f_watch(
    watch_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    watch = _get_watch(db, user, watch_id)
    db.delete(watch)
    db.commit()
    return {"status": "deleted"}


@router.get("/13f/watches/{watch_id}/download")
def download_13f(
    watch_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    watch = _get_watch(db, user, watch_id)
    if not watch.latest_info_table_url and not watch.latest_primary_document_url:
        watch = refresh_13f_watch(db, watch)
    document_url = watch.latest_info_table_url or watch.latest_primary_document_url
    if not document_url:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=watch.warning or "No downloadable 13F document found")

    try:
        content, content_type, filename = download_13f_document(document_url)
    except SecFilingError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    watch.last_downloaded_at = utc_now()
    db.add(watch)
    db.commit()
    safe_name = filename.replace('"', "")
    headers = {"Content-Disposition": f'attachment; filename="{watch.cik}-{safe_name}"'}
    return Response(content=content, media_type=content_type, headers=headers)
