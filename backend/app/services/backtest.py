from dataclasses import dataclass
from datetime import date, timedelta
import statistics

from app.services.direct_indexing import Holding, Position, choose_replacements, generate_rebalance_trades, holdings_from_dicts, normalize_holdings
from app.services.direct_index_models import DEFAULT_DIRECT_INDEX_MODEL, direct_index_model_config
from app.services.index_data import get_index_definition
from app.services.price_math import deterministic_price
from app.services.tax_loss import (
    ANNUAL_TLH_TRADE_CAP,
    DEFAULT_TLH_MODE,
    PriorTrade,
    TaxLotInput,
    build_harvest_candidates,
    replacement_is_substantially_identical,
    tlh_mode_config,
    violates_wash_sale,
)


TRACKING_DRIFT_BUDGET = 0.02
TLH_YEAR_END_LOCKOUT_BUFFER_DAYS = 45
TLH_REPLACEMENT_BASKET_SIZE = 8
DEFAULT_ESTIMATED_TAX_RATE = 0.35
MIN_REBALANCE_DOLLARS = 10.0
TAX_AWARE_REBALANCE_MIN_WEIGHT = 0.0001
INDEX_TRACKING_DRIFT_BUDGETS = {
    "XLG": 0.018,
    "SPY": 0.018,
    "TOPT": 0.02,
    "QTOP": 0.018,
}


@dataclass
class SimPosition:
    symbol: str
    shares: float
    basis: float
    acquisition_date: date


@dataclass(frozen=True)
class BacktestTrade:
    trade_date: date
    action: str
    symbol: str
    shares: float
    price: float
    notional: float
    reason: str
    harvested_loss: float = 0
    realized_gain_loss: float = 0
    tracking_impact: float = 0
    wash_sale_status: str = "cleared"
    notes: str | None = None


@dataclass(frozen=True)
class BacktestResult:
    index_symbol: str
    year: int
    tlh_mode: str
    direct_index_model: str
    starting_value: float
    ending_value: float
    benchmark_value: float
    portfolio_profit: float
    portfolio_return: float
    benchmark_profit: float
    benchmark_return: float
    excess_profit: float
    tracking_difference: float
    tracking_error: float
    harvested_losses: float
    realized_gains: float
    realized_losses: float
    net_realized_gain_loss: float
    estimated_tax_rate: float
    estimated_tax_savings: float
    estimated_tax_liability: float
    estimated_net_tax_impact: float
    tax_adjusted_ending_value: float
    tax_adjusted_profit: float
    tax_adjusted_excess_profit: float
    is_profitable: bool
    is_tax_adjusted_profitable: bool
    beats_benchmark_after_tax: bool
    profitability_summary: str
    trade_count: int
    tlh_trade_count: int
    cap_used: int
    cap_remaining: int
    dropped_tlh_candidates: int
    skipped_tax_loss_value: float
    coverage_label: str
    warnings: list[str]
    trades: list[BacktestTrade]


def backtest_coverage(index_symbol: str, year: int) -> tuple[date, date, str, list[str]]:
    definition = get_index_definition(index_symbol)
    year_start = date(year, 1, 1)
    year_end = date(year, 12, 31)
    if definition.inception_date > year_end:
        label = "unavailable - pre-inception"
        warning = f"{index_symbol} launched on {definition.inception_date.isoformat()}; {year} backtest unavailable."
        return definition.inception_date, year_end, label, [warning]
    start = max(year_start, definition.inception_date)
    warnings: list[str] = []
    if start > year_start:
        label = f"partial-period from {start.isoformat()}"
        warnings.append(f"{index_symbol} launched on {definition.inception_date.isoformat()}, so {year} is partial-period only.")
    else:
        label = "full-year"
    return start, year_end, label, warnings


def _month_ends(start: date, end: date) -> list[date]:
    dates: list[date] = []
    current = start
    while current <= end:
        next_month = date(current.year + int(current.month == 12), 1 if current.month == 12 else current.month + 1, 1)
        month_end = min(next_month - timedelta(days=1), end)
        if month_end >= start:
            dates.append(month_end)
        current = next_month
    return dates


def _scan_dates(start: date, end: date, interval_days: int) -> list[date]:
    if interval_days >= 31:
        return _month_ends(start, end)

    dates: list[date] = []
    current = start
    while current <= end:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=interval_days)
        while current <= end and current.weekday() >= 5:
            current += timedelta(days=1)
    if dates and dates[-1] != end:
        dates.append(end)
    return dates


def _prices(symbols: list[str], price_date: date) -> dict[str, float]:
    return {symbol: deterministic_price(symbol, price_date) for symbol in symbols}


def _all_lots(positions: dict[str, list[SimPosition]]) -> list[SimPosition]:
    return [lot for lots in positions.values() for lot in lots]


def _positions_to_tracking(positions: dict[str, list[SimPosition]], prices: dict[str, float]) -> list[Position]:
    return [
        Position(symbol=symbol, shares=sum(lot.shares for lot in lots), price=prices.get(symbol, lots[0].basis))
        for symbol, lots in positions.items()
        if lots and sum(lot.shares for lot in lots) > 1e-6
    ]


def _portfolio_value(positions: dict[str, list[SimPosition]], prices: dict[str, float], cash: float) -> float:
    return sum(lot.shares * prices.get(symbol, lot.basis) for symbol, lots in positions.items() for lot in lots) + cash


def _apply_trade(positions: dict[str, list[SimPosition]], cash: float, trade: BacktestTrade) -> float:
    symbol = trade.symbol
    if trade.action == "BUY":
        positions.setdefault(symbol, []).append(
            SimPosition(
                symbol=symbol,
                shares=trade.shares,
                basis=trade.price,
                acquisition_date=trade.trade_date,
            )
        )
        return cash - trade.notional

    lots = positions.get(symbol)
    if not lots:
        return cash
    remaining_to_sell = trade.shares
    remaining_lots: list[SimPosition] = []
    for lot in sorted(lots, key=lambda item: (item.basis, item.acquisition_date), reverse=True):
        if remaining_to_sell <= 1e-9:
            remaining_lots.append(lot)
            continue
        sold_shares = min(lot.shares, remaining_to_sell)
        cash += sold_shares * trade.price
        remaining_to_sell -= sold_shares
        remaining_shares = lot.shares - sold_shares
        if remaining_shares > 1e-6:
            remaining_lots.append(
                SimPosition(
                    symbol=lot.symbol,
                    shares=remaining_shares,
                    basis=lot.basis,
                    acquisition_date=lot.acquisition_date,
                )
            )
    if remaining_lots:
        positions[symbol] = remaining_lots
    else:
        del positions[symbol]
    return cash


def _replacement_baskets(
    holdings: list[Holding],
    completion_symbol: str | None = None,
    basket_size: int = TLH_REPLACEMENT_BASKET_SIZE,
) -> dict[str, dict[str, float]]:
    if completion_symbol:
        return {holding.symbol: {completion_symbol: 1.0} for holding in holdings if holding.symbol != completion_symbol}

    baskets: dict[str, dict[str, float]] = {}
    for holding in holdings:
        peers = [peer for peer in holdings if peer.symbol != holding.symbol]
        same_sector = [peer for peer in peers if peer.sector and peer.sector == holding.sector]
        selected = sorted(same_sector or peers, key=lambda peer: peer.weight, reverse=True)[:basket_size]
        total = sum(peer.weight for peer in selected)
        if total <= 0:
            continue
        baskets[holding.symbol] = {peer.symbol: peer.weight / total for peer in selected}
    return baskets


def _candidate_replacements(holdings: list[Holding], exclusions: set[str], completion_symbol: str | None) -> dict[str, str]:
    if completion_symbol:
        return {holding.symbol: completion_symbol for holding in holdings if holding.symbol != completion_symbol}
    return choose_replacements(holdings, exclusions)


def _effective_holdings(holdings: list[Holding], replacement_baskets: dict[str, dict[str, float]], locked_weights: dict[str, float]) -> list[Holding]:
    weights = {holding.symbol: holding.weight for holding in holdings}
    details = {holding.symbol: holding for holding in holdings}
    for locked_symbol, locked_weight in locked_weights.items():
        basket = replacement_baskets.get(locked_symbol)
        if not basket or locked_symbol not in weights:
            continue
        shifted_weight = min(weights.get(locked_symbol, 0), locked_weight)
        weights[locked_symbol] -= shifted_weight
        for replacement, fraction in basket.items():
            weights[replacement] = weights.get(replacement, 0) + shifted_weight * fraction

    adjusted: list[Holding] = []
    for symbol, weight in weights.items():
        if weight <= 0:
            continue
        detail = details.get(symbol, Holding(symbol=symbol, name=symbol, weight=weight))
        adjusted.append(Holding(symbol=symbol, name=detail.name, sector=detail.sector, weight=weight))
    return normalize_holdings(adjusted)


def _tracking_limited_tax_lots(
    trade_date: date,
    lots: list[TaxLotInput],
    prices: dict[str, float],
    replacements: dict[str, str],
    target_weights: dict[str, float],
    locked_weights: dict[str, float],
    prior_trades: list[PriorTrade],
    tracking_budget: float,
    min_loss_percent: float,
    min_loss_dollars: float,
    min_harvest_loss_dollars: float,
) -> list[TaxLotInput]:
    current_locked_weight = sum(locked_weights.values())
    remaining_budget = max(0, tracking_budget - current_locked_weight)
    if remaining_budget <= 0:
        return []

    portfolio_value = sum(prices.get(lot.symbol, 0) * lot.shares for lot in lots)
    if portfolio_value <= 0:
        return []

    ranked_candidates: list[tuple[float, float, TaxLotInput]] = []
    candidates = build_harvest_candidates(
        lots,
        prices,
        replacements,
        min_loss_percent=min_loss_percent,
        min_loss_dollars=min_loss_dollars,
    )
    selected: list[TaxLotInput] = []
    selected_symbols: set[str] = set()
    for candidate in candidates:
        symbol = candidate.lot.symbol
        replacement = replacements.get(symbol)
        if symbol in locked_weights or not replacement:
            continue
        if violates_wash_sale(symbol, trade_date, prior_trades):
            continue
        if replacement_is_substantially_identical(symbol, replacement):
            continue
        target_weight = target_weights.get(symbol, 0)
        current_price = prices.get(symbol, 0)
        lot_value = current_price * candidate.lot.shares
        lot_weight = lot_value / portfolio_value if portfolio_value > 0 else 0
        if target_weight <= 0 or lot_weight <= 0:
            continue
        max_harvest_weight = min(tracking_budget, target_weight, lot_weight)
        harvest_weight = min(remaining_budget, max_harvest_weight)
        if harvest_weight <= 0:
            continue
        share_fraction = min(1.0, harvest_weight / lot_weight)
        harvested_shares = candidate.lot.shares * share_fraction
        partial_loss = (candidate.lot.cost_basis_per_share - current_price) * harvested_shares
        if partial_loss < min_harvest_loss_dollars:
            continue
        ranked_candidates.append(
            (
                partial_loss,
                (candidate.lot.cost_basis_per_share - current_price) / max(candidate.lot.cost_basis_per_share, 1),
                TaxLotInput(
                    symbol=symbol,
                    acquisition_date=candidate.lot.acquisition_date,
                    shares=harvested_shares,
                    cost_basis_per_share=candidate.lot.cost_basis_per_share,
                ),
            )
        )

    for _, _, tax_lot in sorted(ranked_candidates, key=lambda item: (item[0], item[1]), reverse=True):
        symbol = tax_lot.symbol
        if symbol in selected_symbols:
            continue
        current_price = prices.get(symbol, 0)
        lot_value = current_price * tax_lot.shares
        harvest_weight = lot_value / portfolio_value if portfolio_value > 0 else 0
        if harvest_weight <= 0 or harvest_weight > remaining_budget + 1e-9:
            continue
        selected.append(
            TaxLotInput(
                symbol=symbol,
                acquisition_date=tax_lot.acquisition_date,
                shares=tax_lot.shares,
                cost_basis_per_share=tax_lot.cost_basis_per_share,
            )
        )
        selected_symbols.add(symbol)
        remaining_budget -= harvest_weight
        if remaining_budget <= 0:
            break
    return selected


def _build_tlh_trades(
    trade_date: date,
    lots: list[TaxLotInput],
    prices: dict[str, float],
    replacement_baskets: dict[str, dict[str, float]],
    annual_trade_count: int,
    annual_trade_cap: int,
    tlh_mode_label: str,
    tlh_mode_warning: str,
) -> tuple[list[BacktestTrade], int, list[str]]:
    trades: list[BacktestTrade] = []
    warnings: list[str] = []
    remaining = max(0, annual_trade_cap - annual_trade_count)

    for lot in lots:
        price = prices.get(lot.symbol)
        basket = replacement_baskets.get(lot.symbol)
        if not price or not basket:
            continue
        harvested_loss = (lot.cost_basis_per_share - price) * lot.shares
        if harvested_loss <= 0:
            continue
        required_rows = 1 + len(basket)
        if remaining < required_rows:
            warnings.append("Annual TLH trade cap reached; lower-impact harvest candidates were dropped.")
            continue

        sell_notional = lot.shares * price
        trades.append(
            BacktestTrade(
                trade_date=trade_date,
                action="SELL",
                symbol=lot.symbol,
                shares=round(lot.shares, 6),
                price=round(price, 4),
                notional=round(sell_notional, 2),
                reason="tax_loss_harvest",
                harvested_loss=round(harvested_loss, 2),
                realized_gain_loss=round(-harvested_loss, 2),
                wash_sale_status="cleared",
                notes=f"{tlh_mode_label} replacement basket used to preserve index tracking while avoiding the harvested ticker.",
            )
        )
        for replacement, fraction in basket.items():
            replacement_price = prices.get(replacement)
            if not replacement_price:
                continue
            notional = sell_notional * fraction
            trades.append(
                BacktestTrade(
                    trade_date=trade_date,
                    action="BUY",
                    symbol=replacement,
                    shares=round(notional / replacement_price, 6),
                    price=round(replacement_price, 4),
                    notional=round(notional, 2),
                    reason="tax_loss_replacement",
                    wash_sale_status="cleared",
                    notes=f"{tlh_mode_label} basket replacement for harvested {lot.symbol}.",
                )
            )
        remaining -= required_rows

    if trades:
        warnings.append(tlh_mode_warning)
    return trades, annual_trade_count + len(trades), warnings


def _sell_realized_gain_loss(positions: dict[str, list[SimPosition]], trade: object) -> float:
    if trade.action != "SELL":
        return 0
    lots = positions.get(trade.symbol)
    if not lots:
        return 0
    remaining_to_sell = trade.shares
    realized = 0.0
    for lot in sorted(lots, key=lambda item: (item.basis, item.acquisition_date), reverse=True):
        if remaining_to_sell <= 1e-9:
            break
        sold_shares = min(lot.shares, remaining_to_sell)
        realized += (trade.price - lot.basis) * sold_shares
        remaining_to_sell -= sold_shares
    return realized


def _backtest_trade_from_rebalance(rebalance_trade: object, positions: dict[str, list[SimPosition]]) -> BacktestTrade:
    return BacktestTrade(
        trade_date=rebalance_trade.trade_date,
        action=rebalance_trade.action,
        symbol=rebalance_trade.symbol,
        shares=rebalance_trade.shares,
        price=rebalance_trade.price,
        notional=rebalance_trade.notional,
        reason=rebalance_trade.reason,
        realized_gain_loss=round(_sell_realized_gain_loss(positions, rebalance_trade), 2),
        tracking_impact=rebalance_trade.tracking_impact,
    )


def _profitability_summary(
    is_profitable: bool,
    is_tax_adjusted_profitable: bool,
    beats_benchmark_after_tax: bool,
    tax_adjusted_profit: float,
    tax_adjusted_excess_profit: float,
) -> str:
    if not is_profitable:
        return f"Not profitable: the simulated portfolio ended ${abs(tax_adjusted_profit):,.0f} below the starting value after estimated taxes."
    if beats_benchmark_after_tax:
        return f"Profitable and ahead of benchmark by ${tax_adjusted_excess_profit:,.0f} after estimated taxes."
    if is_tax_adjusted_profitable:
        return f"Profitable, but trails the benchmark by ${abs(tax_adjusted_excess_profit):,.0f} after estimated taxes."
    return f"Pre-tax profitable, but not profitable after estimated taxes; shortfall is ${abs(tax_adjusted_profit):,.0f}."


def _unavailable_backtest_result(
    definition_symbol: str,
    year: int,
    mode: str,
    direct_index_model: str,
    starting_value: float,
    estimated_tax_rate: float,
    coverage_label: str,
    warnings: list[str],
) -> BacktestResult:
    return BacktestResult(
        index_symbol=definition_symbol,
        year=year,
        tlh_mode=mode,
        direct_index_model=direct_index_model,
        starting_value=round(starting_value, 2),
        ending_value=round(starting_value, 2),
        benchmark_value=round(starting_value, 2),
        portfolio_profit=0,
        portfolio_return=0,
        benchmark_profit=0,
        benchmark_return=0,
        excess_profit=0,
        tracking_difference=0,
        tracking_error=0,
        harvested_losses=0,
        realized_gains=0,
        realized_losses=0,
        net_realized_gain_loss=0,
        estimated_tax_rate=round(estimated_tax_rate, 4),
        estimated_tax_savings=0,
        estimated_tax_liability=0,
        estimated_net_tax_impact=0,
        tax_adjusted_ending_value=round(starting_value, 2),
        tax_adjusted_profit=0,
        tax_adjusted_excess_profit=0,
        is_profitable=False,
        is_tax_adjusted_profitable=False,
        beats_benchmark_after_tax=False,
        profitability_summary="Backtest unavailable because the selected index had not launched yet.",
        trade_count=0,
        tlh_trade_count=0,
        cap_used=0,
        cap_remaining=ANNUAL_TLH_TRADE_CAP,
        dropped_tlh_candidates=0,
        skipped_tax_loss_value=0,
        coverage_label=coverage_label,
        warnings=warnings,
        trades=[],
    )


def run_backtest(
    index_symbol: str,
    year: int,
    starting_value: float = 100_000,
    exclusions: list[str] | None = None,
    estimated_tax_rate: float = DEFAULT_ESTIMATED_TAX_RATE,
    tlh_mode: str = DEFAULT_TLH_MODE,
    direct_index_model: str = DEFAULT_DIRECT_INDEX_MODEL,
) -> BacktestResult:
    estimated_tax_rate = max(0, min(0.60, estimated_tax_rate))
    mode_config = tlh_mode_config(tlh_mode)
    model_config = direct_index_model_config(direct_index_model)
    definition = get_index_definition(index_symbol)
    start, end, coverage_label, warnings = backtest_coverage(index_symbol, year)
    if start > end:
        return _unavailable_backtest_result(
            definition.symbol,
            year,
            mode_config.mode,
            model_config.id,
            starting_value,
            estimated_tax_rate,
            coverage_label,
            warnings,
        )
    normalized_exclusions = {symbol.upper().strip().replace("/", ".") for symbol in exclusions or []}
    holdings = normalize_holdings(holdings_from_dicts(definition.holdings), normalized_exclusions)
    symbols = [holding.symbol for holding in holdings]
    completion_symbol = definition.symbol if model_config.replacement_strategy == "completion_etf" else None
    replacements = _candidate_replacements(holdings, normalized_exclusions, completion_symbol)
    replacement_baskets = _replacement_baskets(holdings, completion_symbol=completion_symbol)
    target_weights = {holding.symbol: holding.weight for holding in holdings}
    tracking_budget = (
        INDEX_TRACKING_DRIFT_BUDGETS.get(definition.symbol, TRACKING_DRIFT_BUDGET)
        * mode_config.tracking_budget_multiplier
        * model_config.tracking_budget_multiplier
    )
    scan_interval_days = model_config.scan_interval_days or mode_config.scan_interval_days
    min_loss_percent = model_config.min_loss_percent if model_config.min_loss_percent is not None else mode_config.min_loss_percent
    min_loss_dollars = model_config.min_loss_dollars if model_config.min_loss_dollars is not None else mode_config.min_loss_dollars
    min_harvest_loss_dollars = (
        model_config.min_harvest_loss_dollars
        if model_config.min_harvest_loss_dollars is not None
        else mode_config.min_harvest_loss_dollars
    )

    positions: dict[str, list[SimPosition]] = {}
    trades: list[BacktestTrade] = []
    prior_trades: list[PriorTrade] = []
    tlh_trade_count = 0
    dropped_tlh_candidates = 0
    skipped_tax_loss_value = 0.0
    harvested_losses = 0.0
    period_tracking_differences: list[float] = []
    cash = 0.0
    wash_lockouts: dict[str, tuple[date, float]] = {}
    benchmark_value = starting_value
    previous_portfolio_value = starting_value
    monthly_rebalance_dates = set(_month_ends(start, end))

    start_prices = _prices(symbols, start)
    previous_benchmark_prices = start_prices
    for holding in holdings:
        target_value = starting_value * holding.weight
        price = start_prices[holding.symbol]
        shares = target_value / price
        positions[holding.symbol] = [SimPosition(symbol=holding.symbol, shares=shares, basis=price, acquisition_date=start)]
        trades.append(
            BacktestTrade(
                trade_date=start,
                action="BUY",
                symbol=holding.symbol,
                shares=round(shares, 6),
                price=price,
                notional=round(target_value, 2),
                reason="initial_index_purchase",
            )
        )
        prior_trades.append(PriorTrade(trade_date=start, action="BUY", symbol=holding.symbol, shares=shares))

    scan_dates = set(_scan_dates(start, end, scan_interval_days))
    simulation_dates = sorted(scan_dates | monthly_rebalance_dates)
    for rebalance_date in simulation_dates:
        is_valuation_date = rebalance_date in monthly_rebalance_dates
        active_symbols = sorted(set(symbols) | set(positions) | set(replacements.values()) | {definition.symbol})
        prices = _prices(active_symbols, rebalance_date)
        period_return = sum(
            holding.weight * ((prices[holding.symbol] / previous_benchmark_prices[holding.symbol]) - 1)
            for holding in holdings
        )
        projected_benchmark_value = benchmark_value * (1 + period_return)
        prices[definition.symbol] = projected_benchmark_value
        wash_lockouts = {symbol: lockout for symbol, lockout in wash_lockouts.items() if lockout[0] > rebalance_date}
        locked_weights = {symbol: weight for symbol, (_, weight) in wash_lockouts.items()}
        portfolio_value_before_tlh = _portfolio_value(positions, prices, cash)
        if is_valuation_date:
            benchmark_value = projected_benchmark_value
            previous_benchmark_prices = {symbol: prices[symbol] for symbol in symbols}
            portfolio_period_return = (portfolio_value_before_tlh / max(previous_portfolio_value, 1)) - 1
            period_tracking_differences.append(portfolio_period_return - period_return)

        lots = [
            TaxLotInput(
                symbol=position.symbol,
                acquisition_date=position.acquisition_date,
                shares=position.shares,
                cost_basis_per_share=position.basis,
            )
            for position in _all_lots(positions)
        ]
        if rebalance_date <= end - timedelta(days=TLH_YEAR_END_LOCKOUT_BUFFER_DAYS):
            tlh_lots = _tracking_limited_tax_lots(
                trade_date=rebalance_date,
                lots=lots,
                prices=prices,
                replacements=replacements,
                target_weights=target_weights,
                locked_weights=locked_weights,
                prior_trades=prior_trades,
                tracking_budget=tracking_budget,
                min_loss_percent=min_loss_percent,
                min_loss_dollars=min_loss_dollars,
                min_harvest_loss_dollars=min_harvest_loss_dollars,
            )
        else:
            tlh_lots = []
        tlh_trades, tlh_trade_count, tlh_warnings = _build_tlh_trades(
            trade_date=rebalance_date,
            lots=tlh_lots,
            prices=prices,
            replacement_baskets=replacement_baskets,
            annual_trade_count=tlh_trade_count,
            annual_trade_cap=ANNUAL_TLH_TRADE_CAP,
            tlh_mode_label=mode_config.label,
            tlh_mode_warning=mode_config.warning_label,
        )
        for warning in tlh_warnings:
            if warning not in warnings:
                warnings.append(warning)

        for backtest_trade in tlh_trades:
            trades.append(backtest_trade)
            cash = _apply_trade(positions, cash, backtest_trade)
            prior_trades.append(PriorTrade(trade_date=backtest_trade.trade_date, action=backtest_trade.action, symbol=backtest_trade.symbol, shares=backtest_trade.shares))
            if backtest_trade.action == "SELL":
                harvested_losses += backtest_trade.harvested_loss
                lockout_weight = backtest_trade.notional / max(portfolio_value_before_tlh, 1)
                existing_until, existing_weight = wash_lockouts.get(backtest_trade.symbol, (backtest_trade.trade_date + timedelta(days=31), 0))
                wash_lockouts[backtest_trade.symbol] = (
                    max(existing_until, backtest_trade.trade_date + timedelta(days=31)),
                    min(target_weights.get(backtest_trade.symbol, 0), existing_weight + lockout_weight),
                )

        if is_valuation_date:
            locked_weights = {symbol: weight for symbol, (until, weight) in wash_lockouts.items() if until > rebalance_date}
            effective_holdings = _effective_holdings(holdings, replacement_baskets, locked_weights)
            current_positions = _positions_to_tracking(positions, prices)
            portfolio_value = _portfolio_value(positions, prices, cash)
            rebalance_trades = generate_rebalance_trades(
                trade_date=rebalance_date,
                holdings=effective_holdings,
                positions=current_positions,
                prices=prices,
                portfolio_value=portfolio_value,
                exclusions=normalized_exclusions,
                min_trade_dollars=max(MIN_REBALANCE_DOLLARS, portfolio_value * TAX_AWARE_REBALANCE_MIN_WEIGHT),
            )
            for rebalance_trade in sorted(rebalance_trades, key=lambda trade: 0 if trade.action == "SELL" else 1):
                backtest_trade = _backtest_trade_from_rebalance(rebalance_trade, positions)
                trades.append(backtest_trade)
                cash = _apply_trade(positions, cash, backtest_trade)
                prior_trades.append(PriorTrade(trade_date=backtest_trade.trade_date, action=backtest_trade.action, symbol=backtest_trade.symbol, shares=backtest_trade.shares))

        if is_valuation_date:
            previous_portfolio_value = _portfolio_value(positions, prices, cash)

    end_prices = _prices(sorted(set(symbols) | set(positions) | {definition.symbol}), end)
    end_prices[definition.symbol] = benchmark_value
    ending_value = _portfolio_value(positions, end_prices, cash)
    tracking_difference = (ending_value - benchmark_value) / max(benchmark_value, 1)
    tracking_error = statistics.pstdev(period_tracking_differences) if len(period_tracking_differences) > 1 else 0
    portfolio_profit = ending_value - starting_value
    benchmark_profit = benchmark_value - starting_value
    excess_profit = ending_value - benchmark_value
    realized_gains = sum(max(0, trade.realized_gain_loss) for trade in trades)
    realized_losses = -sum(min(0, trade.realized_gain_loss) for trade in trades)
    net_realized_gain_loss = realized_gains - realized_losses
    estimated_tax_savings = max(0, -net_realized_gain_loss) * estimated_tax_rate
    estimated_tax_liability = max(0, net_realized_gain_loss) * estimated_tax_rate
    estimated_net_tax_impact = estimated_tax_savings - estimated_tax_liability
    tax_adjusted_ending_value = ending_value + estimated_net_tax_impact
    tax_adjusted_profit = tax_adjusted_ending_value - starting_value
    tax_adjusted_excess_profit = tax_adjusted_ending_value - benchmark_value
    is_profitable = portfolio_profit > 0
    is_tax_adjusted_profitable = tax_adjusted_profit > 0
    beats_benchmark_after_tax = tax_adjusted_excess_profit > 0

    return BacktestResult(
        index_symbol=definition.symbol,
        year=year,
        tlh_mode=mode_config.mode,
        direct_index_model=model_config.id,
        starting_value=round(starting_value, 2),
        ending_value=round(ending_value, 2),
        benchmark_value=round(benchmark_value, 2),
        portfolio_profit=round(portfolio_profit, 2),
        portfolio_return=round(portfolio_profit / max(starting_value, 1), 6),
        benchmark_profit=round(benchmark_profit, 2),
        benchmark_return=round(benchmark_profit / max(starting_value, 1), 6),
        excess_profit=round(excess_profit, 2),
        tracking_difference=round(tracking_difference, 6),
        tracking_error=round(tracking_error, 6),
        harvested_losses=round(harvested_losses, 2),
        realized_gains=round(realized_gains, 2),
        realized_losses=round(realized_losses, 2),
        net_realized_gain_loss=round(net_realized_gain_loss, 2),
        estimated_tax_rate=round(estimated_tax_rate, 4),
        estimated_tax_savings=round(estimated_tax_savings, 2),
        estimated_tax_liability=round(estimated_tax_liability, 2),
        estimated_net_tax_impact=round(estimated_net_tax_impact, 2),
        tax_adjusted_ending_value=round(tax_adjusted_ending_value, 2),
        tax_adjusted_profit=round(tax_adjusted_profit, 2),
        tax_adjusted_excess_profit=round(tax_adjusted_excess_profit, 2),
        is_profitable=is_profitable,
        is_tax_adjusted_profitable=is_tax_adjusted_profitable,
        beats_benchmark_after_tax=beats_benchmark_after_tax,
        profitability_summary=_profitability_summary(
            is_profitable,
            is_tax_adjusted_profitable,
            beats_benchmark_after_tax,
            tax_adjusted_profit,
            tax_adjusted_excess_profit,
        ),
        trade_count=len(trades),
        tlh_trade_count=tlh_trade_count,
        cap_used=tlh_trade_count,
        cap_remaining=max(0, ANNUAL_TLH_TRADE_CAP - tlh_trade_count),
        dropped_tlh_candidates=dropped_tlh_candidates,
        skipped_tax_loss_value=round(skipped_tax_loss_value, 2),
        coverage_label=coverage_label,
        warnings=warnings,
        trades=trades[-250:],
    )
