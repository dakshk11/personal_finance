from dataclasses import dataclass, field
from datetime import date, timedelta


ANNUAL_TLH_TRADE_CAP = 1000
WASH_SALE_WINDOW_DAYS = 30
DEFAULT_TLH_MODE = "aggressive"


@dataclass(frozen=True)
class TLHModeConfig:
    mode: str
    label: str
    min_loss_percent: float
    min_loss_dollars: float
    min_harvest_loss_dollars: float
    tracking_budget_multiplier: float
    scan_interval_days: int
    warning_label: str


TLH_MODE_CONFIGS: dict[str, TLHModeConfig] = {
    "conservative": TLHModeConfig(
        mode="conservative",
        label="Conservative",
        min_loss_percent=0.08,
        min_loss_dollars=250.0,
        min_harvest_loss_dollars=100.0,
        tracking_budget_multiplier=0.35,
        scan_interval_days=31,
        warning_label="Conservative TLH mode is enabled; only larger losses are harvested and tracking drift is tightly limited.",
    ),
    "moderate": TLHModeConfig(
        mode="moderate",
        label="Moderate",
        min_loss_percent=0.05,
        min_loss_dollars=50.0,
        min_harvest_loss_dollars=50.0,
        tracking_budget_multiplier=0.65,
        scan_interval_days=14,
        warning_label="Moderate TLH mode is enabled; losses are harvested with balanced tracking-drift limits.",
    ),
    "aggressive": TLHModeConfig(
        mode="aggressive",
        label="Aggressive",
        min_loss_percent=0.02,
        min_loss_dollars=10.0,
        min_harvest_loss_dollars=25.0,
        tracking_budget_multiplier=0.65,
        scan_interval_days=7,
        warning_label="Aggressive TLH mode is enabled; replacements are not treated as tax advice.",
    ),
}


def tlh_mode_config(mode: str | None = None) -> TLHModeConfig:
    normalized = (mode or DEFAULT_TLH_MODE).lower().strip()
    return TLH_MODE_CONFIGS.get(normalized, TLH_MODE_CONFIGS[DEFAULT_TLH_MODE])


@dataclass(frozen=True)
class TaxLotInput:
    symbol: str
    acquisition_date: date
    shares: float
    cost_basis_per_share: float


@dataclass(frozen=True)
class PriorTrade:
    trade_date: date
    action: str
    symbol: str
    shares: float


@dataclass(frozen=True)
class TLHTrade:
    trade_date: date
    action: str
    symbol: str
    shares: float
    price: float
    notional: float
    harvested_loss: float
    reason: str
    wash_sale_status: str
    notes: str | None = None


@dataclass(frozen=True)
class DroppedCandidate:
    symbol: str
    estimated_loss: float
    reason: str


@dataclass(frozen=True)
class TLHResult:
    trades: list[TLHTrade] = field(default_factory=list)
    cap_used: int = 0
    cap_remaining: int = ANNUAL_TLH_TRADE_CAP
    dropped_candidates: list[DroppedCandidate] = field(default_factory=list)
    skipped_tax_loss_value: float = 0
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class HarvestCandidate:
    lot: TaxLotInput
    current_price: float
    replacement_symbol: str
    replacement_price: float
    estimated_loss: float


def normalize_symbol(symbol: str) -> str:
    return symbol.upper().strip().replace("/", ".")


def security_group(symbol: str, equivalent_groups: list[set[str]] | None = None) -> frozenset[str]:
    normalized = normalize_symbol(symbol)
    for group in equivalent_groups or []:
        normalized_group = {normalize_symbol(item) for item in group}
        if normalized in normalized_group:
            return frozenset(normalized_group)
    return frozenset({normalized})


def within_wash_window(left: date, right: date) -> bool:
    return abs((left - right).days) <= WASH_SALE_WINDOW_DAYS


def violates_wash_sale(
    sold_symbol: str,
    sale_date: date,
    prior_trades: list[PriorTrade],
    equivalent_groups: list[set[str]] | None = None,
) -> bool:
    sold_group = security_group(sold_symbol, equivalent_groups)
    for trade in prior_trades:
        if trade.action.upper() != "BUY":
            continue
        if not within_wash_window(trade.trade_date, sale_date):
            continue
        if security_group(trade.symbol, equivalent_groups) == sold_group:
            return True
    return False


def replacement_is_substantially_identical(
    sold_symbol: str,
    replacement_symbol: str,
    equivalent_groups: list[set[str]] | None = None,
) -> bool:
    return security_group(sold_symbol, equivalent_groups) == security_group(replacement_symbol, equivalent_groups)


def build_harvest_candidates(
    lots: list[TaxLotInput],
    prices: dict[str, float],
    replacements: dict[str, str],
    min_loss_percent: float = 0.05,
    min_loss_dollars: float = 50.0,
) -> list[HarvestCandidate]:
    candidates: list[HarvestCandidate] = []
    for lot in lots:
        symbol = normalize_symbol(lot.symbol)
        current_price = prices.get(symbol)
        replacement_symbol = normalize_symbol(replacements.get(symbol, ""))
        replacement_price = prices.get(replacement_symbol)
        if not current_price or not replacement_symbol or not replacement_price:
            continue
        current_value = current_price * lot.shares
        basis = lot.cost_basis_per_share * lot.shares
        estimated_loss = basis - current_value
        if estimated_loss < min_loss_dollars:
            continue
        if estimated_loss / max(basis, 1) < min_loss_percent:
            continue
        candidates.append(
            HarvestCandidate(
                lot=lot,
                current_price=current_price,
                replacement_symbol=replacement_symbol,
                replacement_price=replacement_price,
                estimated_loss=estimated_loss,
            )
        )
    return sorted(candidates, key=lambda candidate: candidate.estimated_loss, reverse=True)


def generate_tax_loss_harvest_trades(
    trade_date: date,
    lots: list[TaxLotInput],
    prices: dict[str, float],
    replacements: dict[str, str],
    prior_trades: list[PriorTrade] | None = None,
    equivalent_groups: list[set[str]] | None = None,
    annual_trade_count: int = 0,
    annual_trade_cap: int = ANNUAL_TLH_TRADE_CAP,
    min_loss_percent: float | None = None,
    min_loss_dollars: float | None = None,
    tlh_mode: str = DEFAULT_TLH_MODE,
) -> TLHResult:
    mode_config = tlh_mode_config(tlh_mode)
    candidates = build_harvest_candidates(
        lots,
        prices,
        replacements,
        min_loss_percent=mode_config.min_loss_percent if min_loss_percent is None else min_loss_percent,
        min_loss_dollars=mode_config.min_loss_dollars if min_loss_dollars is None else min_loss_dollars,
    )
    trades: list[TLHTrade] = []
    dropped: list[DroppedCandidate] = []
    warnings: list[str] = []
    remaining = max(0, annual_trade_cap - annual_trade_count)

    for candidate in candidates:
        lot = candidate.lot
        symbol = normalize_symbol(lot.symbol)
        replacement = normalize_symbol(candidate.replacement_symbol)
        if violates_wash_sale(symbol, trade_date, prior_trades or [], equivalent_groups):
            dropped.append(DroppedCandidate(symbol=symbol, estimated_loss=candidate.estimated_loss, reason="wash_sale_prior_buy"))
            continue
        if replacement_is_substantially_identical(symbol, replacement, equivalent_groups):
            dropped.append(DroppedCandidate(symbol=symbol, estimated_loss=candidate.estimated_loss, reason="replacement_substantially_identical"))
            continue

        required_trade_rows = 2
        if remaining < required_trade_rows:
            dropped.append(DroppedCandidate(symbol=symbol, estimated_loss=candidate.estimated_loss, reason="annual_trade_cap"))
            continue

        sell_notional = lot.shares * candidate.current_price
        buy_shares = sell_notional / candidate.replacement_price
        notes = f"{mode_config.label} TLH replacement into {replacement}; review similarity risk before relying on tax treatment."
        trades.append(
            TLHTrade(
                trade_date=trade_date,
                action="SELL",
                symbol=symbol,
                shares=round(lot.shares, 6),
                price=round(candidate.current_price, 4),
                notional=round(sell_notional, 2),
                harvested_loss=round(candidate.estimated_loss, 2),
                reason="tax_loss_harvest",
                wash_sale_status="cleared",
                notes=notes,
            )
        )
        trades.append(
            TLHTrade(
                trade_date=trade_date,
                action="BUY",
                symbol=replacement,
                shares=round(buy_shares, 6),
                price=round(candidate.replacement_price, 4),
                notional=round(sell_notional, 2),
                harvested_loss=0,
                reason="tax_loss_replacement",
                wash_sale_status="cleared",
                notes=notes,
            )
        )
        remaining -= required_trade_rows

    skipped_loss = round(sum(item.estimated_loss for item in dropped if item.reason == "annual_trade_cap"), 2)
    if any(item.reason == "annual_trade_cap" for item in dropped):
        warnings.append("Annual TLH trade cap reached; lower-impact harvest candidates were dropped.")
    if trades:
        warnings.append(mode_config.warning_label)

    return TLHResult(
        trades=trades,
        cap_used=annual_trade_count + len(trades),
        cap_remaining=max(0, annual_trade_cap - annual_trade_count - len(trades)),
        dropped_candidates=dropped,
        skipped_tax_loss_value=skipped_loss,
        warnings=warnings,
    )


def wash_sale_lockout_until(sale_date: date) -> date:
    return sale_date + timedelta(days=WASH_SALE_WINDOW_DAYS + 1)
