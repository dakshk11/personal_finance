from dataclasses import asdict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.entities import BacktestRun, User
from app.schemas.common import (
    BacktestOut,
    BacktestRequest,
    DirectIndexModelOut,
    ModelComparisonOut,
    ModelComparisonRequest,
    ModelComparisonRow,
    TradeOut,
)
from app.services.backtest import run_backtest
from app.services.direct_index_models import EXECUTABLE_DIRECT_INDEX_MODELS, all_direct_index_models, direct_index_model_config


router = APIRouter(prefix="/backtests", tags=["backtests"])
MODEL_TRACKING_GUARDRAIL = 0.01


def _to_backtest_out(result) -> BacktestOut:
    return BacktestOut(
        index_symbol=result.index_symbol,
        year=result.year,
        tlh_mode=result.tlh_mode,
        direct_index_model=result.direct_index_model,
        starting_value=result.starting_value,
        ending_value=result.ending_value,
        benchmark_value=result.benchmark_value,
        portfolio_profit=result.portfolio_profit,
        portfolio_return=result.portfolio_return,
        benchmark_profit=result.benchmark_profit,
        benchmark_return=result.benchmark_return,
        excess_profit=result.excess_profit,
        tracking_difference=result.tracking_difference,
        tracking_error=result.tracking_error,
        harvested_losses=result.harvested_losses,
        realized_gains=result.realized_gains,
        realized_losses=result.realized_losses,
        net_realized_gain_loss=result.net_realized_gain_loss,
        estimated_tax_rate=result.estimated_tax_rate,
        estimated_tax_savings=result.estimated_tax_savings,
        estimated_tax_liability=result.estimated_tax_liability,
        estimated_net_tax_impact=result.estimated_net_tax_impact,
        tax_adjusted_ending_value=result.tax_adjusted_ending_value,
        tax_adjusted_profit=result.tax_adjusted_profit,
        tax_adjusted_excess_profit=result.tax_adjusted_excess_profit,
        is_profitable=result.is_profitable,
        is_tax_adjusted_profitable=result.is_tax_adjusted_profitable,
        beats_benchmark_after_tax=result.beats_benchmark_after_tax,
        profitability_summary=result.profitability_summary,
        trade_count=result.trade_count,
        tlh_trade_count=result.tlh_trade_count,
        cap_used=result.cap_used,
        cap_remaining=result.cap_remaining,
        dropped_tlh_candidates=result.dropped_tlh_candidates,
        skipped_tax_loss_value=result.skipped_tax_loss_value,
        coverage_label=result.coverage_label,
        warnings=result.warnings,
        trades=[TradeOut(**asdict(trade)) for trade in result.trades],
    )


@router.post("", response_model=BacktestOut)
def create_backtest(payload: BacktestRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> BacktestOut:
    result = run_backtest(
        payload.index_symbol,
        payload.year,
        payload.starting_value,
        payload.exclusions,
        payload.estimated_tax_rate,
        payload.tlh_mode,
        payload.direct_index_model,
    )
    db.add(
        BacktestRun(
            user_id=user.id,
            index_symbol=result.index_symbol,
            year=result.year,
            starting_value=result.starting_value,
            ending_value=result.ending_value,
            benchmark_value=result.benchmark_value,
            tracking_difference=result.tracking_difference,
            tracking_error=result.tracking_error,
            harvested_losses=result.harvested_losses,
            trade_count=result.trade_count,
            tlh_trade_count=result.tlh_trade_count,
            dropped_tlh_candidates=result.dropped_tlh_candidates,
            coverage_label=result.coverage_label,
            warnings="\n".join(result.warnings) if result.warnings else None,
        )
    )
    db.commit()
    return _to_backtest_out(result)


def _recommended_model(rows: list[ModelComparisonRow], index_symbol: str) -> tuple[str | None, str | None, str]:
    available_rows = [row for row in rows if row.available]
    if not available_rows:
        return None, None, f"No executable model has available {index_symbol.upper()} history for the selected years."

    grouped: dict[str, list[ModelComparisonRow]] = {}
    for row in available_rows:
        grouped.setdefault(row.direct_index_model, []).append(row)

    guardrail_groups = {
        model_id: model_rows
        for model_id, model_rows in grouped.items()
        if all(abs(row.tracking_difference) <= MODEL_TRACKING_GUARDRAIL and row.tracking_error <= MODEL_TRACKING_GUARDRAIL for row in model_rows)
    }
    candidate_groups = guardrail_groups or grouped

    def score(item: tuple[str, list[ModelComparisonRow]]) -> tuple[float, float, float, int, int]:
        model_id, model_rows = item
        model = direct_index_model_config(model_id)
        tax_adjusted_profit = sum(row.tax_adjusted_profit for row in model_rows)
        harvested_losses = sum(row.harvested_losses for row in model_rows)
        tracking_risk = max(max(abs(row.tracking_difference), row.tracking_error) for row in model_rows)
        trade_count = sum(row.trade_count for row in model_rows)
        return (tax_adjusted_profit, harvested_losses, -tracking_risk, -trade_count, -model.rank)

    best_model_id, best_rows = max(candidate_groups.items(), key=score)
    best_model = direct_index_model_config(best_model_id)
    years = ", ".join(str(year) for year in sorted({row.year for row in best_rows}))
    total_profit = sum(row.tax_adjusted_profit for row in best_rows)
    max_tracking = max(max(abs(row.tracking_difference), row.tracking_error) for row in best_rows)
    guardrail_text = "inside" if guardrail_groups else "closest to"
    recommendation = (
        f"Use {best_model.label} as the current-year default. It had the highest aggregate tax-adjusted profit "
        f"for {index_symbol.upper()} across {years} among models {guardrail_text} the 1% tracking guardrail "
        f"(${total_profit:,.2f} aggregate tax-adjusted profit; max tracking measure {max_tracking:.2%})."
    )
    return best_model.id, best_model.label, recommendation


@router.post("/model-comparison", response_model=ModelComparisonOut)
def compare_models(payload: ModelComparisonRequest, _: User = Depends(get_current_user)) -> ModelComparisonOut:
    rows: list[ModelComparisonRow] = []
    years = sorted(set(payload.years))
    for model_id in EXECUTABLE_DIRECT_INDEX_MODELS:
        model = direct_index_model_config(model_id)
        for year in years:
            result = run_backtest(
                payload.index_symbol,
                year,
                payload.starting_value,
                payload.exclusions,
                payload.estimated_tax_rate,
                payload.tlh_mode,
                model_id,
            )
            rows.append(
                ModelComparisonRow(
                    direct_index_model=model.id,
                    model_label=model.label,
                    year=year,
                    available=not result.coverage_label.startswith("unavailable"),
                    coverage_label=result.coverage_label,
                    harvested_losses=result.harvested_losses,
                    tracking_difference=result.tracking_difference,
                    tracking_error=result.tracking_error,
                    trade_count=result.trade_count,
                    cap_used=result.cap_used,
                    cap_remaining=result.cap_remaining,
                    tax_adjusted_profit=result.tax_adjusted_profit,
                    warnings=result.warnings,
                )
            )

    recommended_model, recommended_model_label, recommendation = _recommended_model(rows, payload.index_symbol)
    models = [
        DirectIndexModelOut(
            id=model.id,
            label=model.label,
            rank=model.rank,
            executable=model.executable,
            summary=model.summary,
            best_for=model.best_for,
            source_support=model.source_support,
        )
        for model in all_direct_index_models()
    ]
    return ModelComparisonOut(
        index_symbol=payload.index_symbol.upper(),
        models=models,
        rows=rows,
        recommended_model=recommended_model,
        recommended_model_label=recommended_model_label,
        recommendation=recommendation,
    )
