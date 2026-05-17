from dataclasses import dataclass
from datetime import date, timedelta
import json
from math import isclose

from sqlalchemy.orm import Session

from app.models.entities import Account, ClientConstraint, ImportedHolding, ImportedTaxLot
from app.services.direct_indexing import Holding, normalize_holdings
from app.services.index_data import get_index_definition
from app.services.market_data import get_prices, holdings_for_index
from app.services.tax_loss import replacement_is_substantially_identical


ALGORITHM_VERSION = "transition-planner-v1.0"
MIN_TRADE_DOLLARS = 25.0
LEGAL_DISCLAIMER_WARNINGS = [
    "DirectIndex is educational planning software only. It is not a registered investment adviser, broker-dealer, law firm, CPA firm, tax preparer, fiduciary, custodian, or trading system.",
    "Nothing in this proposal, export, backtest, tax-loss-harvesting output, transition plan, algorithm result, or data display is tax, legal, accounting, investment, fiduciary, brokerage, or trading advice.",
    "Do not buy, sell, hold, rebalance, harvest losses, file a tax return, claim a tax benefit, or make any financial decision based only on this output. Consult a qualified attorney, CPA or tax professional, and appropriately registered investment adviser before acting.",
    "Outputs are hypothetical, model-based, and dependent on user-provided data, assumptions, cached data, and simplified rules. They may be stale, incomplete, inaccurate, unsuitable, or inconsistent with a client's full financial, legal, tax, or regulatory facts.",
    "DirectIndex does not guarantee performance, tax savings, wash-sale treatment, tracking error, active share, data accuracy, regulatory compliance, suitability, availability, or any outcome. Users and advisors are solely responsible for independent review, documentation, supervision, and final decisions.",
]


@dataclass(frozen=True)
class TransitionRecommendation:
    stage: str
    action: str
    symbol: str
    shares: float
    price: float
    notional: float
    realized_gain_loss: float
    estimated_tax_impact: float
    reason: str
    wash_sale_status: str
    notes: str


@dataclass(frozen=True)
class TransitionPlanComputation:
    input_snapshot: dict[str, object]
    recommendations: list[TransitionRecommendation]
    warnings: list[str]
    data_source_summary: str
    portfolio_value: float
    target_value: float
    realized_gains: float
    realized_losses: float
    net_realized_gain: float
    estimated_tax_impact: float
    tracking_drift: float
    active_share: float
    turnover: float
    skipped_trade_count: int


def normalize_symbol(symbol: str) -> str:
    return symbol.upper().strip().replace("/", ".")


def load_json_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return [str(item) for item in parsed] if isinstance(parsed, list) else []


def dump_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def previous_business_day(today: date | None = None) -> date:
    current = today or date.today()
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current


def latest_constraint(account: Account) -> ClientConstraint | None:
    return max(account.client.constraints, key=lambda item: item.created_at, default=None)


def _filtered_target_holdings(constraint: ClientConstraint) -> list[Holding]:
    excluded_symbols = {normalize_symbol(symbol) for symbol in load_json_list(constraint.excluded_symbols_json)}
    excluded_sectors = {sector.strip().lower() for sector in load_json_list(constraint.excluded_sectors_json)}
    holdings = [
        holding
        for holding in holdings_for_index(constraint.target_index)
        if normalize_symbol(holding.symbol) not in excluded_symbols
        and (holding.sector or "").strip().lower() not in excluded_sectors
    ]
    return normalize_holdings(holdings)


def _holding_values(account: Account, prices: dict[str, float]) -> dict[str, float]:
    values: dict[str, float] = {}
    if account.holdings:
        for holding in account.holdings:
            values[normalize_symbol(holding.symbol)] = values.get(normalize_symbol(holding.symbol), 0) + holding.market_value
        return values

    for lot in account.tax_lots:
        symbol = normalize_symbol(lot.symbol)
        values[symbol] = values.get(symbol, 0) + lot.shares * prices.get(symbol, lot.cost_basis_per_share)
    return values


def _holding_sector_map(account: Account, target_holdings: list[Holding]) -> dict[str, str]:
    sectors = {normalize_symbol(holding.symbol): holding.sector or "Unknown" for holding in target_holdings}
    for holding in account.holdings:
        sectors.setdefault(normalize_symbol(holding.symbol), holding.sector or "Unknown")
    return sectors


def _equivalent_groups(account: Account) -> list[set[str]]:
    groups: list[set[str]] = []
    for group in account.client.equivalent_groups:
        symbols = {normalize_symbol(symbol) for symbol in load_json_list(group.symbols_json)}
        if len(symbols) >= 2:
            groups.append(symbols)
    return groups


def _tracking_metrics(current_values: dict[str, float], target_values: dict[str, float], portfolio_value: float) -> tuple[float, float]:
    if portfolio_value <= 0:
        return 1.0, 1.0
    symbols = set(current_values) | set(target_values)
    active_share = sum(abs(current_values.get(symbol, 0) / portfolio_value - target_values.get(symbol, 0) / portfolio_value) for symbol in symbols) / 2
    tracking_drift = sum(abs(current_values.get(symbol, 0) - target_values.get(symbol, 0)) for symbol in symbols) / portfolio_value
    return round(tracking_drift, 6), round(active_share, 6)


def _sector_drift(current_values: dict[str, float], target_values: dict[str, float], sectors: dict[str, str], portfolio_value: float) -> dict[str, float]:
    if portfolio_value <= 0:
        return {}
    sector_current: dict[str, float] = {}
    sector_target: dict[str, float] = {}
    for symbol, value in current_values.items():
        sector = sectors.get(symbol, "Unknown")
        sector_current[sector] = sector_current.get(sector, 0) + value
    for symbol, value in target_values.items():
        sector = sectors.get(symbol, "Unknown")
        sector_target[sector] = sector_target.get(sector, 0) + value
    return {
        sector: round((sector_current.get(sector, 0) - sector_target.get(sector, 0)) / portfolio_value, 6)
        for sector in sorted(set(sector_current) | set(sector_target))
    }


def _sellable_lots(account: Account, symbol: str, price: float, objective: str) -> list[ImportedTaxLot]:
    lots = [lot for lot in account.tax_lots if normalize_symbol(lot.symbol) == symbol]
    if objective == "harvest_losses":
        return sorted(lots, key=lambda lot: (price - lot.cost_basis_per_share, lot.acquisition_date))
    if objective == "minimize_gains":
        return sorted(lots, key=lambda lot: (max(price - lot.cost_basis_per_share, 0), lot.acquisition_date))
    return sorted(lots, key=lambda lot: (price - lot.cost_basis_per_share, lot.acquisition_date))


def build_transition_plan(account: Account, constraint: ClientConstraint, db: Session, objective: str = "transition_gradually") -> TransitionPlanComputation:
    as_of_date = previous_business_day()
    target_holdings = _filtered_target_holdings(constraint)
    current_symbols = {normalize_symbol(holding.symbol) for holding in account.holdings} | {normalize_symbol(lot.symbol) for lot in account.tax_lots}
    target_symbols = {normalize_symbol(holding.symbol) for holding in target_holdings}
    prices = get_prices(db, sorted(current_symbols | target_symbols | {constraint.target_index}), as_of_date)
    for holding in account.holdings:
        prices[normalize_symbol(holding.symbol)] = holding.price
    current_values = _holding_values(account, prices)
    portfolio_value = round(sum(current_values.values()), 2)
    target_values = {normalize_symbol(holding.symbol): portfolio_value * holding.weight for holding in target_holdings}
    target_value = round(sum(target_values.values()), 2)
    tracking_drift, active_share = _tracking_metrics(current_values, target_values, portfolio_value)
    sectors = _holding_sector_map(account, target_holdings)
    equivalent_groups = _equivalent_groups(account)
    warnings = [
        *LEGAL_DISCLAIMER_WARNINGS,
        "Planning-only proposal. DirectIndex does not place trades or provide discretionary management in this workflow.",
        "Hypothetical transition output. Advisor must review client suitability, tax assumptions, account data, and execution costs before making recommendations.",
        "Using cached public holdings and deterministic fallback prices until production-grade licensed market data is configured.",
    ]
    if not constraint.outside_accounts_complete:
        warnings.append("Outside-account wash-sale data is not marked complete; household-level wash-sale risk may be understated.")
    if active_share > constraint.max_active_share:
        warnings.append("Current active share is above the client constraint; staged transition may require multiple review cycles.")
    if tracking_drift > constraint.max_tracking_error:
        warnings.append("Current tracking drift is above the client constraint; proposal prioritizes reducing drift without breaching the gain budget.")

    recommendations: list[TransitionRecommendation] = []
    realized_gains = 0.0
    realized_losses = 0.0
    net_realized_gain = 0.0
    sale_proceeds = 0.0
    skipped_trade_count = 0
    sold_loss_symbols: set[str] = set()
    adjusted_values = dict(current_values)
    sell_targets = {
        symbol: max(0.0, current_values.get(symbol, 0) - target_values.get(symbol, 0))
        for symbol in sorted(set(current_values) | set(target_values))
    }

    for symbol, target_sell_value in sorted(sell_targets.items(), key=lambda item: item[1], reverse=True):
        if target_sell_value < MIN_TRADE_DOLLARS:
            continue
        price = prices.get(symbol)
        if not price:
            skipped_trade_count += 1
            continue
        remaining_sell_value = target_sell_value
        for lot in _sellable_lots(account, symbol, price, objective):
            if remaining_sell_value < MIN_TRADE_DOLLARS:
                break
            lot_value = min(lot.shares * price, remaining_sell_value)
            shares_to_sell = lot_value / price
            gain_loss = shares_to_sell * (price - lot.cost_basis_per_share)
            if gain_loss > 0 and net_realized_gain + gain_loss > constraint.annual_gains_budget:
                remaining_budget = max(0.0, constraint.annual_gains_budget - net_realized_gain)
                if isclose(remaining_budget, 0.0, abs_tol=0.01):
                    skipped_trade_count += 1
                    continue
                shares_to_sell = min(shares_to_sell, remaining_budget / max(price - lot.cost_basis_per_share, 0.000001))
                lot_value = shares_to_sell * price
                gain_loss = shares_to_sell * (price - lot.cost_basis_per_share)
            if lot_value < MIN_TRADE_DOLLARS:
                skipped_trade_count += 1
                continue

            net_realized_gain += gain_loss
            if gain_loss >= 0:
                realized_gains += gain_loss
            else:
                realized_losses += abs(gain_loss)
                sold_loss_symbols.add(symbol)
            sale_proceeds += lot_value
            remaining_sell_value -= lot_value
            adjusted_values[symbol] = max(0.0, adjusted_values.get(symbol, 0) - lot_value)
            recommendations.append(
                TransitionRecommendation(
                    stage="initial",
                    action="SELL",
                    symbol=symbol,
                    shares=round(shares_to_sell, 6),
                    price=round(price, 4),
                    notional=round(lot_value, 2),
                    realized_gain_loss=round(gain_loss, 2),
                    estimated_tax_impact=round(max(gain_loss, 0) * constraint.estimated_tax_rate, 2),
                    reason="reduce_overweight_or_non_target",
                    wash_sale_status="loss lockout" if gain_loss < 0 else "not applicable",
                    notes="Lot selected by tax-aware transition optimizer under annual gain budget.",
                )
            )

    underweights = [
        (symbol, target_values.get(symbol, 0) - adjusted_values.get(symbol, 0))
        for symbol in sorted(target_values)
        if target_values.get(symbol, 0) - adjusted_values.get(symbol, 0) >= MIN_TRADE_DOLLARS
    ]
    for symbol, buy_value in sorted(underweights, key=lambda item: item[1], reverse=True):
        if sale_proceeds < MIN_TRADE_DOLLARS:
            break
        if any(replacement_is_substantially_identical(sold, symbol, equivalent_groups) for sold in sold_loss_symbols):
            skipped_trade_count += 1
            continue
        notional = min(buy_value, sale_proceeds)
        price = prices.get(symbol)
        if not price or notional < MIN_TRADE_DOLLARS:
            skipped_trade_count += 1
            continue
        shares = notional / price
        sale_proceeds -= notional
        adjusted_values[symbol] = adjusted_values.get(symbol, 0) + notional
        recommendations.append(
            TransitionRecommendation(
                stage="initial",
                action="BUY",
                symbol=symbol,
                shares=round(shares, 6),
                price=round(price, 4),
                notional=round(notional, 2),
                realized_gain_loss=0,
                estimated_tax_impact=0,
                reason="move_toward_target_index",
                wash_sale_status="screened",
                notes="Replacement purchase screened against advisor-provided equivalent-security groups.",
            )
        )

    post_tracking_drift, post_active_share = _tracking_metrics(adjusted_values, target_values, portfolio_value)
    trade_notional = sum(item.notional for item in recommendations)
    estimated_tax_impact = round(net_realized_gain * constraint.estimated_tax_rate, 2)
    if estimated_tax_impact < 0:
        warnings.append("Plan produces net realized losses under the provided assumptions; utilization depends on client gains and tax profile.")
    if skipped_trade_count:
        warnings.append(f"{skipped_trade_count} candidate trades were skipped by tax budget, minimum-trade, data, or wash-sale constraints.")
    if sale_proceeds >= MIN_TRADE_DOLLARS:
        warnings.append(f"{sale_proceeds:,.2f} of sale proceeds remains unallocated in this stage to respect constraints.")

    input_snapshot: dict[str, object] = {
        "algorithm_version": ALGORITHM_VERSION,
        "as_of_date": as_of_date.isoformat(),
        "account_id": account.id,
        "account_name": account.name,
        "client_id": account.client_id,
        "objective": objective,
        "target_index": constraint.target_index,
        "annual_gains_budget": constraint.annual_gains_budget,
        "max_tracking_error": constraint.max_tracking_error,
        "max_active_share": constraint.max_active_share,
        "estimated_tax_rate": constraint.estimated_tax_rate,
        "excluded_symbols": load_json_list(constraint.excluded_symbols_json),
        "excluded_sectors": load_json_list(constraint.excluded_sectors_json),
        "outside_accounts_complete": constraint.outside_accounts_complete,
        "equivalent_groups": [sorted(group) for group in equivalent_groups],
        "portfolio_value": portfolio_value,
        "pre_trade_tracking_drift": tracking_drift,
        "pre_trade_active_share": active_share,
        "post_trade_tracking_drift": post_tracking_drift,
        "post_trade_active_share": post_active_share,
        "sector_drift": _sector_drift(current_values, target_values, sectors, portfolio_value),
        "holdings_count": len(account.holdings),
        "tax_lot_count": len(account.tax_lots),
        "data_sources": ["advisor import", "cached public holdings", "deterministic offline fallback prices"],
    }
    data_source_summary = (
        f"Advisor-imported holdings/tax lots; {get_index_definition(constraint.target_index).provider} target holdings; "
        f"prices as of {as_of_date.isoformat()} from cached/fallback data."
    )
    return TransitionPlanComputation(
        input_snapshot=input_snapshot,
        recommendations=recommendations,
        warnings=warnings,
        data_source_summary=data_source_summary,
        portfolio_value=portfolio_value,
        target_value=target_value,
        realized_gains=round(realized_gains, 2),
        realized_losses=round(realized_losses, 2),
        net_realized_gain=round(net_realized_gain, 2),
        estimated_tax_impact=estimated_tax_impact,
        tracking_drift=post_tracking_drift,
        active_share=post_active_share,
        turnover=round(trade_notional / max(portfolio_value, 1), 6),
        skipped_trade_count=skipped_trade_count,
    )
