from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.common import HighYieldBacktestOut, HighYieldFundOut, HighYieldSignalOut, MajorIndexOut, MarketHistoryOut, MarketPriceBarOut, YahooQuoteOut, YahooQuotesOut
from app.services.market_history import (
    HighYieldFundAnalysis,
    MarketHistory,
    cache_high_yield_history,
    cache_major_index_history,
    get_high_yield_analysis,
    get_market_history,
    list_high_yield_fund_metadata,
    list_major_indexes,
)
from app.services.market_data import fetch_yahoo_quote_snapshots


router = APIRouter(prefix="/market-data", tags=["market-data"])


@router.get("/major-indexes", response_model=list[MajorIndexOut])
def major_indexes() -> list[MajorIndexOut]:
    return [
        MajorIndexOut(
            symbol=item.symbol,
            name=item.name,
            benchmark=item.benchmark,
            category=item.category,
        )
        for item in list_major_indexes()
    ]


@router.get("/high-yield-funds", response_model=list[HighYieldFundOut])
def high_yield_funds(
    start_date: date | None = None,
    end_date: date | None = None,
    force_refresh: bool = False,
    db: Session = Depends(get_db),
) -> list[HighYieldFundOut]:
    start_date = start_date or date.today() - timedelta(days=365 * 3)
    end_date = end_date or date.today()
    return [
        _high_yield_out(get_high_yield_analysis(db, item.symbol, start_date, end_date, force_refresh=force_refresh))
        for item in list_high_yield_fund_metadata()
    ]


@router.get("/history", response_model=MarketHistoryOut)
def market_history(
    symbol: str = Query(default="SPY", min_length=1, max_length=16),
    start_date: date | None = None,
    end_date: date | None = None,
    force_refresh: bool = False,
    db: Session = Depends(get_db),
) -> MarketHistoryOut:
    start_date = start_date or date.today() - timedelta(days=365 * 3)
    end_date = end_date or date.today()
    return _history_out(get_market_history(db, symbol, start_date, end_date, force_refresh=force_refresh))


@router.get("/yahoo-quotes", response_model=YahooQuotesOut)
def yahoo_quotes(symbols: str = Query(..., min_length=1, max_length=500)) -> YahooQuotesOut:
    requested = [symbol.strip() for symbol in symbols.split(",") if symbol.strip()]
    snapshots = fetch_yahoo_quote_snapshots(requested)
    return YahooQuotesOut(
        tickers=[
            YahooQuoteOut(
                symbol=row.symbol,
                price=row.price,
                last=row.price,
                close=row.close,
                source=row.source,
                warning=row.warning,
            )
            for row in snapshots
        ]
    )


@router.post("/major-indexes/cache", response_model=list[MarketHistoryOut])
def cache_major_indexes(
    start_date: date | None = None,
    end_date: date | None = None,
    force_refresh: bool = False,
    db: Session = Depends(get_db),
) -> list[MarketHistoryOut]:
    start_date = start_date or date.today() - timedelta(days=365 * 3)
    end_date = end_date or date.today()
    return [
        _history_out(history)
        for history in cache_major_index_history(db, start_date, end_date, force_refresh=force_refresh)
    ]


@router.post("/high-yield-funds/cache", response_model=list[HighYieldFundOut])
def cache_high_yield_funds(
    start_date: date | None = None,
    end_date: date | None = None,
    force_refresh: bool = False,
    db: Session = Depends(get_db),
) -> list[HighYieldFundOut]:
    start_date = start_date or date.today() - timedelta(days=365 * 3)
    end_date = end_date or date.today()
    return [
        _high_yield_out(item)
        for item in cache_high_yield_history(db, start_date, end_date, force_refresh=force_refresh)
    ]


def _high_yield_out(analysis: HighYieldFundAnalysis) -> HighYieldFundOut:
    signal = analysis.signal
    return HighYieldFundOut(
        symbol=analysis.fund.symbol,
        name=analysis.fund.name,
        issuer=analysis.fund.issuer,
        exposure=analysis.fund.exposure,
        strategy=analysis.fund.strategy,
        distribution_frequency=analysis.fund.distribution_frequency,
        source_url=analysis.fund.source_url,
        risk_note=analysis.fund.risk_note,
        data_source=analysis.data_source,
        last_price_date=analysis.last_price_date,
        cached_at=analysis.cached_at,
        warnings=analysis.warnings,
        signal=HighYieldSignalOut(
            action=signal.action,
            signal_date=signal.signal_date,
            last_close=signal.last_close,
            reason=signal.reason,
            reasons=signal.reasons,
            risk_state=signal.risk_state,
            confidence=signal.confidence,
            limited_history=signal.limited_history,
            data_points=signal.data_points,
            backtest=HighYieldBacktestOut(
                evaluated_weeks=signal.backtest.evaluated_weeks,
                buy_signals=signal.backtest.buy_signals,
                hit_rate_4w=signal.backtest.hit_rate_4w,
                average_forward_return_4w=signal.backtest.average_forward_return_4w,
                last_buy_date=signal.backtest.last_buy_date,
                recent_buy_dates=signal.backtest.recent_buy_dates,
            ),
        ),
    )


def _history_out(history: MarketHistory) -> MarketHistoryOut:
    return MarketHistoryOut(
        symbol=history.symbol,
        name=history.name,
        benchmark=history.benchmark,
        category=history.category,
        requested_start_date=history.requested_start_date,
        requested_end_date=history.requested_end_date,
        start_date=history.start_date,
        end_date=history.end_date,
        bars=[
            MarketPriceBarOut(
                date=bar.date,
                close=bar.close,
                adjusted_close=bar.adjusted_close,
                dividend=bar.dividend,
                source=bar.source,
            )
            for bar in history.bars
        ],
        warnings=history.warnings,
    )
