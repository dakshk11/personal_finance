from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.schemas.common import (
    PortfolioAnalyzerHoldingIn,
    PortfolioAnalyzerHoldingOut,
    PortfolioAnalyzerOut,
)
from app.services.market_data import get_latest_security_snapshots, normalize_symbol


@dataclass
class _AggregatedHolding:
    symbol: str
    shares: float
    cost_basis: float

    @property
    def cost_basis_per_share(self) -> float:
        return self.cost_basis / self.shares if self.shares > 0 else 0


def last_business_day(today: date | None = None) -> date:
    current = today or date.today()
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def analyze_portfolio_holdings(
    db: Session,
    holdings: list[PortfolioAnalyzerHoldingIn],
    min_weight_percent: float = 1,
    as_of_date: date | None = None,
    allow_external: bool = True,
) -> PortfolioAnalyzerOut:
    analysis_date = as_of_date or last_business_day()
    aggregated = _aggregate_holdings(holdings)
    if not aggregated:
        return PortfolioAnalyzerOut(
            as_of_date=analysis_date,
            min_weight_percent=min_weight_percent,
            total_market_value=0,
            total_cost_basis=0,
            unrealized_gain_loss=0,
            unrealized_gain_loss_pct=0,
            analyzed_holding_count=0,
            hidden_holding_count=0,
            holdings=[],
            warnings=["Add at least one holding with symbol, shares, and cost basis."],
        )

    snapshots = get_latest_security_snapshots(
        db,
        [holding.symbol for holding in aggregated],
        analysis_date,
        allow_external=allow_external,
    )
    total_market_value = sum(holding.shares * snapshots[holding.symbol].price for holding in aggregated)
    total_cost_basis = sum(holding.cost_basis for holding in aggregated)
    threshold = max(0, min_weight_percent) / 100
    rows: list[PortfolioAnalyzerHoldingOut] = []
    hidden_holding_count = 0
    warnings: list[str] = [
        "Price and valuation data are cached by symbol and as-of date; repeat analysis on the same day reuses the cache.",
    ]

    for holding in aggregated:
        snapshot = snapshots[holding.symbol]
        market_value = holding.shares * snapshot.price
        weight = market_value / total_market_value if total_market_value > 0 else 0
        if weight < threshold:
            hidden_holding_count += 1
            continue
        unrealized_gain_loss = market_value - holding.cost_basis
        unrealized_gain_loss_pct = unrealized_gain_loss / holding.cost_basis if holding.cost_basis > 0 else 0
        valuation_signal, valuation_signal_label = _valuation_signal(
            snapshot.forward_pe,
            snapshot.forward_pe_5y_avg,
            snapshot.forward_pe_10y_avg,
        )
        if snapshot.warning:
            warnings.append(f"{holding.symbol}: {snapshot.warning}")
        rows.append(
            PortfolioAnalyzerHoldingOut(
                symbol=holding.symbol,
                shares=round(holding.shares, 6),
                price=round(snapshot.price, 4),
                market_value=round(market_value, 2),
                weight=round(weight, 6),
                cost_basis_per_share=round(holding.cost_basis_per_share, 4),
                cost_basis=round(holding.cost_basis, 2),
                unrealized_gain_loss=round(unrealized_gain_loss, 2),
                unrealized_gain_loss_pct=round(unrealized_gain_loss_pct, 6),
                forward_pe=snapshot.forward_pe,
                forward_pe_5y_avg=snapshot.forward_pe_5y_avg,
                forward_pe_10y_avg=snapshot.forward_pe_10y_avg,
                valuation_signal=valuation_signal,
                valuation_signal_label=valuation_signal_label,
                data_source=f"{snapshot.price_source}; {snapshot.valuation_source}",
                warning=snapshot.warning,
            )
        )

    rows.sort(key=lambda row: row.market_value, reverse=True)
    total_gain_loss = total_market_value - total_cost_basis
    if hidden_holding_count:
        warnings.append(f"{hidden_holding_count} holding(s) below {min_weight_percent:.2f}% were hidden from the focus table.")

    return PortfolioAnalyzerOut(
        as_of_date=analysis_date,
        min_weight_percent=min_weight_percent,
        total_market_value=round(total_market_value, 2),
        total_cost_basis=round(total_cost_basis, 2),
        unrealized_gain_loss=round(total_gain_loss, 2),
        unrealized_gain_loss_pct=round(total_gain_loss / total_cost_basis, 6) if total_cost_basis > 0 else 0,
        analyzed_holding_count=len(rows),
        hidden_holding_count=hidden_holding_count,
        holdings=rows,
        warnings=_unique(warnings),
    )


def _aggregate_holdings(holdings: list[PortfolioAnalyzerHoldingIn]) -> list[_AggregatedHolding]:
    grouped: dict[str, _AggregatedHolding] = {}
    for holding in holdings:
        symbol = normalize_symbol(holding.symbol)
        if not symbol or holding.shares <= 0:
            continue
        cost_basis = holding.shares * max(0, holding.cost_basis_per_share)
        current = grouped.get(symbol)
        if current:
            current.shares += holding.shares
            current.cost_basis += cost_basis
        else:
            grouped[symbol] = _AggregatedHolding(symbol=symbol, shares=holding.shares, cost_basis=cost_basis)
    return sorted(grouped.values(), key=lambda item: item.symbol)


def _valuation_signal(
    forward_pe: float | None,
    five_year_average: float | None,
    ten_year_average: float | None,
) -> tuple[str, str]:
    if not forward_pe:
        return "unknown", "Forward P/E unavailable"
    if ten_year_average and forward_pe < ten_year_average:
        return "below_10y_average", "Below 10Y avg"
    if five_year_average and forward_pe < five_year_average:
        return "below_5y_average", "Below 5Y avg"
    return "at_or_above_average", "At/above averages"


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
