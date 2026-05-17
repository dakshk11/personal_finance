from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Holding:
    symbol: str
    name: str
    weight: float
    sector: str | None = None


@dataclass(frozen=True)
class Position:
    symbol: str
    shares: float
    price: float

    @property
    def market_value(self) -> float:
        return self.shares * self.price


@dataclass(frozen=True)
class TradeRecommendation:
    trade_date: date
    action: str
    symbol: str
    shares: float
    price: float
    notional: float
    reason: str
    tracking_impact: float = 0
    realized_gain_loss: float = 0
    harvested_loss: float = 0
    wash_sale_status: str = "cleared"
    notes: str | None = None


@dataclass(frozen=True)
class TrackingMetrics:
    tracking_score: float
    tracking_difference: float
    active_share: float
    cash_weight: float


def _normalize_symbol(symbol: str) -> str:
    return symbol.upper().strip().replace("/", ".")


def normalize_holdings(holdings: list[Holding], exclusions: set[str] | None = None) -> list[Holding]:
    normalized_exclusions = {_normalize_symbol(symbol) for symbol in exclusions or set()}
    filtered = [holding for holding in holdings if _normalize_symbol(holding.symbol) not in normalized_exclusions]
    total = sum(max(0, holding.weight) for holding in filtered)
    if total <= 0:
        raise ValueError("No index holdings remain after exclusions")
    return [
        Holding(
            symbol=_normalize_symbol(holding.symbol),
            name=holding.name,
            sector=holding.sector,
            weight=max(0, holding.weight) / total,
        )
        for holding in filtered
    ]


def holdings_from_dicts(raw_holdings: tuple[dict[str, object], ...] | list[dict[str, object]]) -> list[Holding]:
    return [
        Holding(
            symbol=str(item["symbol"]),
            name=str(item["name"]),
            sector=str(item.get("sector") or ""),
            weight=float(item["weight"]),
        )
        for item in raw_holdings
    ]


def target_allocations(
    holdings: list[Holding],
    portfolio_value: float,
    exclusions: set[str] | None = None,
) -> dict[str, float]:
    normalized = normalize_holdings(holdings, exclusions)
    return {holding.symbol: portfolio_value * holding.weight for holding in normalized}


def calculate_tracking_metrics(
    holdings: list[Holding],
    positions: list[Position],
    cash: float,
    exclusions: set[str] | None = None,
) -> TrackingMetrics:
    normalized = normalize_holdings(holdings, exclusions)
    total_value = sum(position.market_value for position in positions) + cash
    if total_value <= 0:
        return TrackingMetrics(tracking_score=0, tracking_difference=1, active_share=1, cash_weight=1)

    target_weights = {holding.symbol: holding.weight for holding in normalized}
    actual_weights = {position.symbol: position.market_value / total_value for position in positions}
    symbols = set(target_weights) | set(actual_weights)
    active_share = sum(abs(actual_weights.get(symbol, 0) - target_weights.get(symbol, 0)) for symbol in symbols) / 2
    cash_weight = cash / total_value
    tracking_difference = active_share + cash_weight
    tracking_score = max(0, min(100, 100 * (1 - tracking_difference)))
    return TrackingMetrics(
        tracking_score=round(tracking_score, 2),
        tracking_difference=round(tracking_difference, 6),
        active_share=round(active_share, 6),
        cash_weight=round(cash_weight, 6),
    )


def generate_rebalance_trades(
    trade_date: date,
    holdings: list[Holding],
    positions: list[Position],
    prices: dict[str, float],
    portfolio_value: float,
    exclusions: set[str] | None = None,
    min_trade_dollars: float = 25.0,
) -> list[TradeRecommendation]:
    targets = target_allocations(holdings, portfolio_value, exclusions)
    current = {position.symbol: position.market_value for position in positions}
    trades: list[TradeRecommendation] = []

    for symbol, target_value in sorted(targets.items()):
        price = prices.get(symbol)
        if not price or price <= 0:
            continue
        delta = target_value - current.get(symbol, 0)
        if abs(delta) < min_trade_dollars:
            continue
        action = "BUY" if delta > 0 else "SELL"
        shares = abs(delta) / price
        tracking_impact = abs(delta) / max(portfolio_value, 1)
        trades.append(
            TradeRecommendation(
                trade_date=trade_date,
                action=action,
                symbol=symbol,
                shares=round(shares, 6),
                price=round(price, 4),
                notional=round(abs(delta), 2),
                reason="rebalance",
                tracking_impact=round(tracking_impact, 6),
            )
        )

    excluded_symbols = {_normalize_symbol(symbol) for symbol in exclusions or set()}
    for position in positions:
        if position.symbol in excluded_symbols and position.market_value >= min_trade_dollars:
            trades.append(
                TradeRecommendation(
                    trade_date=trade_date,
                    action="SELL",
                    symbol=position.symbol,
                    shares=round(position.shares, 6),
                    price=round(position.price, 4),
                    notional=round(position.market_value, 2),
                    reason="excluded_symbol",
                    tracking_impact=round(position.market_value / max(portfolio_value, 1), 6),
                    notes="User exclusion forced this position out of the target portfolio.",
                )
            )
        elif position.symbol not in targets and position.market_value >= min_trade_dollars:
            trades.append(
                TradeRecommendation(
                    trade_date=trade_date,
                    action="SELL",
                    symbol=position.symbol,
                    shares=round(position.shares, 6),
                    price=round(position.price, 4),
                    notional=round(position.market_value, 2),
                    reason="non_target_rebalance",
                    tracking_impact=round(position.market_value / max(portfolio_value, 1), 6),
                    notes="Replacement or legacy position moved back toward the target portfolio.",
                )
            )
    return trades


def choose_replacements(holdings: list[Holding], exclusions: set[str] | None = None) -> dict[str, str]:
    normalized = normalize_holdings(holdings, exclusions)
    by_sector: dict[str, list[Holding]] = {}
    for holding in normalized:
        by_sector.setdefault(holding.sector or "Other", []).append(holding)

    replacements: dict[str, str] = {}
    for holding in normalized:
        peers = [peer for peer in by_sector.get(holding.sector or "Other", []) if peer.symbol != holding.symbol]
        if not peers:
            peers = [peer for peer in normalized if peer.symbol != holding.symbol]
        if peers:
            replacement = min(peers, key=lambda peer: abs(peer.weight - holding.weight))
            replacements[holding.symbol] = replacement.symbol
    return replacements
