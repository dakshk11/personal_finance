"""Portfolio Diversification API routes.

POST /diversify/analyze        — concentration analysis (no network, pure math)
POST /diversify/backtest       — multi-year TLH backtest using yfinance
POST /diversify/recommendations — this-month self-diversify trade list (live prices)
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.entities import User
from app.schemas.common import (
    ConcentrationAnalysisOut,
    ConcentrationAnalysisRequest,
    DiversifyBacktestOut,
    DiversifyBacktestRequest,
    DiversifyRecommendationsOut,
    DiversifyRecommendationsRequest,
    DiversifyYearResultOut,
    SectorGapOut,
)
from app.services.direct_indexing import Holding, normalize_holdings
from app.services.diversification import analyze_concentration
from app.services.diversify_backtest import run_diversify_backtest
from app.services.diversify_recommendations import CurrentHolding, get_current_recommendations

router = APIRouter(prefix="/diversify", tags=["diversify"])


@router.post("/analyze", response_model=ConcentrationAnalysisOut)
def analyze(
    payload: ConcentrationAnalysisRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ConcentrationAnalysisOut:
    """Compute HHI, diversification score, and sector gaps vs SCHD."""
    del user, db

    # Convert input holdings to Holding dataclass — use shares × price as raw weight
    raw_holdings = [
        Holding(
            symbol=h.symbol,
            name=h.name or h.symbol,
            weight=h.shares * h.price,
            sector=h.sector or "Other",
        )
        for h in payload.holdings
    ]
    # Normalise weights to sum to 1
    total = sum(h.weight for h in raw_holdings)
    if total <= 0:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="Holdings must have positive share quantities and prices.")
    normalised = [Holding(h.symbol, h.name, h.weight / total, h.sector) for h in raw_holdings]

    result = analyze_concentration(normalised, payload.index_symbol)

    return ConcentrationAnalysisOut(
        hhi=result.hhi,
        diversification_score=result.diversification_score,
        top_holding=result.top_holding,
        top_holding_weight=result.top_holding_weight,
        sector_weights=result.sector_weights,
        sector_vs_index=[
            SectorGapOut(
                sector=g.sector,
                portfolio_weight=g.portfolio_weight,
                index_weight=g.index_weight,
                gap=g.gap,
            )
            for g in result.sector_vs_index
        ],
        active_share=result.active_share,
        concentration_warnings=result.concentration_warnings,
    )


@router.post("/backtest", response_model=DiversifyBacktestOut)
def backtest(
    payload: DiversifyBacktestRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DiversifyBacktestOut:
    """Run multi-year TLH-funded diversification simulation using Yahoo Finance prices."""
    del user, db

    result = run_diversify_backtest(
        concentrated_symbol=payload.concentrated_symbol.upper(),
        concentrated_shares=payload.concentrated_shares,
        avg_cost_basis=payload.avg_cost_basis,
        starting_cash=payload.starting_cash,
        years=sorted(payload.years),
        estimated_tax_rate=payload.estimated_tax_rate,
        harvest_threshold=payload.harvest_threshold,
        alpha_vantage_key=payload.alpha_vantage_key,
    )

    return DiversifyBacktestOut(
        years=[
            DiversifyYearResultOut(
                year=yr.year,
                harvested_losses=yr.harvested_losses,
                tax_savings=yr.tax_savings,
                concentration_pct=yr.concentration_pct,
                hhi=yr.hhi,
                schd_value=yr.schd_value,
                concentrated_value=yr.concentrated_value,
                trade_count=yr.trade_count,
                data_source=yr.data_source,
                warnings=yr.warnings,
            )
            for yr in result.years
        ],
        total_harvested_losses=result.total_harvested_losses,
        total_tax_savings=result.total_tax_savings,
        immediate_sell_tax_cost=result.immediate_sell_tax_cost,
        net_tlh_benefit=result.net_tlh_benefit,
        savings_vs_immediate_sell=result.savings_vs_immediate_sell,
        tlh_wins=result.tlh_wins,
        concentration_start_pct=result.concentration_start_pct,
        concentration_end_pct=result.concentration_end_pct,
        warnings=result.warnings,
    )


@router.post("/recommendations", response_model=DiversifyRecommendationsOut)
def recommendations(
    payload: DiversifyRecommendationsRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DiversifyRecommendationsOut:
    """Generate this-month trade recommendations using today's live Yahoo Finance prices."""
    del user, db

    holdings = [
        CurrentHolding(
            symbol=h.symbol.upper(),
            shares=h.shares,
            avg_cost=h.avg_cost,
            last_sold_date=h.last_sold_date,
        )
        for h in payload.current_schd_holdings
    ]

    result = get_current_recommendations(
        concentrated_symbol=payload.concentrated_symbol.upper(),
        concentrated_shares=payload.concentrated_shares,
        avg_cost_basis=payload.avg_cost_basis,
        current_schd_holdings=holdings,
        estimated_tax_rate=payload.estimated_tax_rate,
        harvest_threshold=payload.harvest_threshold,
    )

    from app.schemas.common import RecommendTradeOut

    def _trade(t) -> RecommendTradeOut:
        return RecommendTradeOut(
            action=t.action, symbol=t.symbol, name=t.name,
            shares=t.shares, estimated_price=t.estimated_price,
            notional=t.notional, reason=t.reason,
            harvested_loss=t.harvested_loss,
        )

    return DiversifyRecommendationsOut(
        as_of_date=result.as_of_date,
        harvest_trades=[_trade(t) for t in result.harvest_trades],
        replacement_trades=[_trade(t) for t in result.replacement_trades],
        concentrated_sell=_trade(result.concentrated_sell) if result.concentrated_sell else None,
        total_harvested_loss=result.total_harvested_loss,
        net_tax_cost=result.net_tax_cost,
        concentration_before_pct=result.concentration_before_pct,
        concentration_after_pct=result.concentration_after_pct,
        warnings=result.warnings,
    )
