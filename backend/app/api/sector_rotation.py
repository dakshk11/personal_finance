from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.entities import SectorRotationAcceptedAllocation, SectorRotationAcceptedTrade, User
from app.schemas.common import (
    SelectionHistoryRowOut,
    SectorAllocationOut,
    SectorRotationAcceptedAllocationIn,
    SectorRotationAcceptedAllocationOut,
    SectorRotationAcceptedAllocationUpdate,
    SectorRotationAcceptedTradeOut,
    SectorRotationBacktestOut,
    SectorRotationBacktestRequest,
    SectorRotationLiveOut,
    SectorRotationLiveRequest,
    SectorRotationPeriodSnapshotOut,
    SectorRotationScenarioMetricsOut,
    SectorRotationScenarioResultOut,
)
from app.services.sector_rotation_engine import CA_RATES, get_live_allocation, get_selection_history, run_backtest

router = APIRouter(prefix="/sector-rotation", tags=["sector-rotation"])


def _accepted_allocation_out(row: SectorRotationAcceptedAllocation) -> SectorRotationAcceptedAllocationOut:
    return SectorRotationAcceptedAllocationOut(
        id=row.id,
        account_type=row.account_type,
        time_frame=row.time_frame,
        weighting_method=row.weighting_method,
        cash_amount=row.cash_amount,
        as_of_year=row.as_of_year,
        rebalance_date=row.rebalance_date,
        rebalance_status=row.rebalance_status,
        rebalance_notes=row.rebalance_notes,
        notes=row.notes,
        created_at=row.created_at,
        updated_at=row.updated_at or row.created_at,
        trades=[
            SectorRotationAcceptedTradeOut(
                id=trade.id,
                ticker=trade.ticker,
                sector_name=trade.sector_name,
                target_weight=trade.target_weight,
                target_amount=trade.target_amount,
                shares=trade.shares,
                cost_basis_per_share=trade.cost_basis_per_share,
                current_price=trade.current_price,
                purchase_date=trade.purchase_date,
                market_value=trade.market_value,
                cost_basis=trade.cost_basis,
                gain_loss=trade.gain_loss,
            )
            for trade in row.trades
        ],
    )


@router.post("/backtest", response_model=SectorRotationBacktestOut)
def backtest(
    payload: SectorRotationBacktestRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SectorRotationBacktestOut:
    del user, db
    results = run_backtest(payload.starting_capital, payload.weighting_method)
    rates = CA_RATES

    scenario_outs = []
    for r in results:
        snaps = [
            SectorRotationPeriodSnapshotOut(
                year=s.year,
                sectors_held=s.sectors_held,
                sector_weights=s.sector_weights,
                period_return_pct=s.period_return_pct,
                cumulative_value=s.cumulative_value,
                taxes_paid_period=s.taxes_paid_period,
                taxes_paid_cumulative=s.taxes_paid_cumulative,
                post_liquidation_value=s.post_liquidation_value,
                embedded_tax_liability=s.embedded_tax_liability,
            )
            for s in r.snapshots
        ]
        m = r.metrics
        metrics_out = SectorRotationScenarioMetricsOut(
            cagr_pretax_pct=m.cagr_pretax_pct,
            cagr_posttax_pct=m.cagr_posttax_pct,
            sharpe_ratio=m.sharpe_ratio,
            max_drawdown_pct=m.max_drawdown_pct,
            total_taxes_paid=m.total_taxes_paid,
            tax_drag_annualized_pct=m.tax_drag_annualized_pct,
            alpha_vs_spy_pretax_pct=m.alpha_vs_spy_pretax_pct,
            alpha_vs_spy_posttax_pct=m.alpha_vs_spy_posttax_pct,
            total_return_pct=m.total_return_pct,
            win_rate_vs_benchmark=m.win_rate_vs_benchmark,
            post_liquidation_value=m.post_liquidation_value,
            final_pretax_value=m.final_pretax_value,
            best_year_return_pct=m.best_year_return_pct,
            worst_year_return_pct=m.worst_year_return_pct,
        )
        scenario_outs.append(SectorRotationScenarioResultOut(
            id=r.id,
            name=r.name,
            metrics=metrics_out,
            period_snapshots=snaps,
        ))

    # Build comparison table
    final_values = {r.id: r.metrics.final_pretax_value for r in results}
    posttax_values = {r.id: r.metrics.post_liquidation_value for r in results}
    winner = max(posttax_values, key=lambda k: posttax_values[k])

    algo_annual = next((r for r in results if r.id == "ALGO_ANNUAL_LTCG"), None)
    algo_quarterly = next((r for r in results if r.id == "ALGO_QUARTERLY_STCG"), None)
    spy = next((r for r in results if r.id == "SPY_BUY_HOLD"), None)

    tax_saved = round(
        (algo_annual.metrics.post_liquidation_value - algo_quarterly.metrics.post_liquidation_value)
        if algo_annual and algo_quarterly else 0, 2
    )
    alpha_posttax = round(
        (algo_annual.metrics.cagr_posttax_pct - spy.metrics.cagr_posttax_pct)
        if algo_annual and spy else 0, 2
    )

    comparison = {
        "final_pretax_values": final_values,
        "final_posttax_values": posttax_values,
        "winner": winner,
        "tax_saved_annual_vs_quarterly": tax_saved,
        "alpha_vs_spy_posttax_pct": alpha_posttax,
    }

    return SectorRotationBacktestOut(
        starting_capital=payload.starting_capital,
        weighting_method=payload.weighting_method,
        tax_rates={
            "ltcg_effective": rates.ltcg_effective,
            "stcg_effective": rates.stcg_effective,
            "federal_ltcg": rates.federal_ltcg,
            "federal_stcg": rates.federal_stcg,
            "california_state": rates.california_state,
            "niit": rates.niit,
        },
        scenarios=scenario_outs,
        comparison=comparison,
    )


@router.post("/live-allocation", response_model=SectorRotationLiveOut)
def live_allocation(
    payload: SectorRotationLiveRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SectorRotationLiveOut:
    del user, db
    allocations, sp500_signals, guidance = get_live_allocation(payload.cash_amount, payload.time_frame, payload.weighting_method)

    alloc_outs = [
        SectorAllocationOut(
            ticker=a.ticker,
            sector_name=a.sector_name,
            weight=a.weight,
            dollar_amount=a.dollar_amount,
            trailing_eps_beat=a.trailing_eps_beat,
            forward_eps_beat=a.forward_eps_beat,
            composite_score=a.composite_score,
        )
        for a in allocations
    ]

    return SectorRotationLiveOut(
        as_of_year=sp500_signals["as_of_year"],
        time_frame=payload.time_frame,
        weighting_method=payload.weighting_method,
        allocations=alloc_outs,
        sp500_signals=sp500_signals,
        rebalance_guidance=guidance,
    )


@router.get("/accepted-allocations", response_model=list[SectorRotationAcceptedAllocationOut])
def list_accepted_allocations(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SectorRotationAcceptedAllocationOut]:
    rows = db.scalars(
        select(SectorRotationAcceptedAllocation)
        .where(SectorRotationAcceptedAllocation.user_id == user.id)
        .order_by(SectorRotationAcceptedAllocation.created_at.desc(), SectorRotationAcceptedAllocation.id.desc())
    ).all()
    return [_accepted_allocation_out(row) for row in rows]


@router.post("/accepted-allocations", response_model=SectorRotationAcceptedAllocationOut, status_code=status.HTTP_201_CREATED)
def create_accepted_allocation(
    payload: SectorRotationAcceptedAllocationIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SectorRotationAcceptedAllocationOut:
    allocation = SectorRotationAcceptedAllocation(
        user_id=user.id,
        account_type=payload.account_type,
        time_frame=payload.time_frame,
        weighting_method=payload.weighting_method,
        cash_amount=payload.cash_amount,
        as_of_year=payload.as_of_year,
        rebalance_date=payload.rebalance_date or min((trade.purchase_date for trade in payload.trades), default=None),
        rebalance_status=payload.rebalance_status,
        rebalance_notes=payload.rebalance_notes,
        notes=payload.notes,
    )
    for item in payload.trades:
        market_value = round(item.shares * item.current_price, 2)
        cost_basis = round(item.shares * item.cost_basis_per_share, 2)
        allocation.trades.append(SectorRotationAcceptedTrade(
            ticker=item.ticker.upper(),
            sector_name=item.sector_name,
            target_weight=item.target_weight,
            target_amount=item.target_amount,
            shares=item.shares,
            cost_basis_per_share=item.cost_basis_per_share,
            current_price=item.current_price,
            purchase_date=item.purchase_date,
            market_value=market_value,
            cost_basis=cost_basis,
            gain_loss=round(market_value - cost_basis, 2),
        ))
    db.add(allocation)
    db.commit()
    db.refresh(allocation)
    return _accepted_allocation_out(allocation)


@router.patch("/accepted-allocations/{allocation_id}", response_model=SectorRotationAcceptedAllocationOut)
def update_accepted_allocation(
    allocation_id: int,
    payload: SectorRotationAcceptedAllocationUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SectorRotationAcceptedAllocationOut:
    allocation = db.scalar(
        select(SectorRotationAcceptedAllocation)
        .where(SectorRotationAcceptedAllocation.id == allocation_id)
        .where(SectorRotationAcceptedAllocation.user_id == user.id)
    )
    if allocation is None:
        raise HTTPException(status_code=404, detail="Accepted allocation not found")

    allocation.rebalance_date = payload.rebalance_date
    allocation.rebalance_status = payload.rebalance_status
    allocation.rebalance_notes = payload.rebalance_notes
    db.commit()
    db.refresh(allocation)
    return _accepted_allocation_out(allocation)


@router.get("/selection-history", response_model=list[SelectionHistoryRowOut])
def selection_history(
    weighting_method: str = Query("equal", pattern="^(equal|market_weight)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SelectionHistoryRowOut]:
    del user, db
    return [
        SelectionHistoryRowOut(
            year=row["year"],
            selected_sectors=row["sectors"],
            sector_weights=row["sector_weights"],
            algo_return_pct=row["algo_return"],
            spy_return_pct=row["spy_return"],
            delta_pct=row["delta"],
            key_signal=row["signal"],
            weighting_method=row["weighting_method"],
        )
        for row in get_selection_history(weighting_method)
    ]
