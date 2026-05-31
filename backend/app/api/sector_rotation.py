from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.entities import User
from app.schemas.common import (
    SelectionHistoryRowOut,
    SectorAllocationOut,
    SectorRotationBacktestOut,
    SectorRotationBacktestRequest,
    SectorRotationLiveOut,
    SectorRotationLiveRequest,
    SectorRotationPeriodSnapshotOut,
    SectorRotationScenarioMetricsOut,
    SectorRotationScenarioResultOut,
)
from app.services.sector_rotation_data import ALGO_SELECTION_HISTORY
from app.services.sector_rotation_engine import CA_RATES, get_live_allocation, run_backtest

router = APIRouter(prefix="/sector-rotation", tags=["sector-rotation"])


@router.post("/backtest", response_model=SectorRotationBacktestOut)
def backtest(
    payload: SectorRotationBacktestRequest,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SectorRotationBacktestOut:
    del user, db
    results = run_backtest(payload.starting_capital)
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
    allocations, sp500_signals, guidance = get_live_allocation(payload.cash_amount, payload.time_frame)

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
        allocations=alloc_outs,
        sp500_signals=sp500_signals,
        rebalance_guidance=guidance,
    )


@router.get("/selection-history", response_model=list[SelectionHistoryRowOut])
def selection_history(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[SelectionHistoryRowOut]:
    del user, db
    return [
        SelectionHistoryRowOut(
            year=row["year"],
            selected_sectors=row["sectors"],
            algo_return_pct=row["algo_return"],
            spy_return_pct=row["spy_return"],
            delta_pct=row["delta"],
            key_signal=row["signal"],
        )
        for row in ALGO_SELECTION_HISTORY
    ]
