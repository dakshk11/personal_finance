"""
Sector rotation backtest engine.
Implements SectorSelector, TaxEngine, and BacktestRunner for all 5 scenarios.

Key design: `cumulative_value` = gross (pre-tax) compound value for all scenarios.
`post_liquidation_value` = after all taxes are accounted for.
ALGO_ANNUAL_LTCG / ALGO_QUARTERLY_STCG use Appendix B selection history returns
(authoritative), because the seed EPS data are annual averages, not the exact
Q4 FactSet signals that drove each year's rebalance decision.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from app.services.sector_rotation_data import (
    ALGO_SELECTION_HISTORY,
    ALL_SECTOR_TICKERS,
    INITIAL_NO_REBALANCE_SECTORS,
    SECTOR_NAMES,
    SPY_SECTOR_WEIGHTS_BY_YEAR,
    YEARS,
    get_annual_return,
    get_forward_eps,
    get_trailing_eps,
)


# ── Tax rates ─────────────────────────────────────────────────────────────────

@dataclass
class CaliforniaTaxRates:
    federal_ltcg: float = 0.20
    federal_stcg: float = 0.37
    california_state: float = 0.133
    niit: float = 0.038

    @property
    def ltcg_effective(self) -> float:
        return self.federal_ltcg + self.california_state + self.niit  # 0.371

    @property
    def stcg_effective(self) -> float:
        return self.federal_stcg + self.california_state + self.niit  # 0.541


CA_RATES = CaliforniaTaxRates()


# ── Sector selection ──────────────────────────────────────────────────────────

@dataclass
class SelectionConfig:
    max_sectors: int = 4
    min_sectors: int = 2
    weight_trailing: float = 0.4
    weight_forward: float = 0.6
    energy_eps_cap: float = 300.0
    max_single_sector_weight: float = 0.35
    weighting_method: str = "equal"


@dataclass
class SelectedSector:
    ticker: str
    sector_name: str
    trailing_eps: float
    forward_eps: float
    trailing_beat: float
    forward_beat: float
    score: float
    weight: float


DEFAULT_CONFIG = SelectionConfig()


def _weighting_method(value: str | None) -> str:
    return "market_weight" if value == "market_weight" else "equal"


def _selected_weights(tickers: list[str], year: int, config: SelectionConfig) -> dict[str, float]:
    if not tickers:
        return {}

    if _weighting_method(config.weighting_method) == "market_weight":
        yearly = SPY_SECTOR_WEIGHTS_BY_YEAR.get(year) or SPY_SECTOR_WEIGHTS_BY_YEAR[max(SPY_SECTOR_WEIGHTS_BY_YEAR)]
        raw = {ticker: max(0.0, yearly.get(ticker, 0.0)) for ticker in tickers}
        total = sum(raw.values())
        if total > 0:
            return {ticker: raw[ticker] / total for ticker in tickers}

    n = len(tickers)
    return {ticker: 1.0 / n for ticker in tickers}


def _weighted_sector_return(tickers: list[str], year: int, config: SelectionConfig) -> tuple[float, dict[str, float]]:
    weights = _selected_weights(tickers, year, config)
    weighted_return = sum(weights[ticker] * get_annual_return(ticker, year) for ticker in tickers)
    return weighted_return, weights


def select_sectors(year: int, config: SelectionConfig = DEFAULT_CONFIG) -> list[SelectedSector]:
    """Run the two-criteria sector selection for a given calendar year."""
    sp500_trailing = get_trailing_eps("SPY", year) or 0.0
    sp500_forward = get_forward_eps("SPY", year) or 0.0

    candidates: list[tuple[str, float, float, float]] = []
    forward_only_candidates: list[tuple[str, float, float, float]] = []

    for ticker in ALL_SECTOR_TICKERS:
        trailing = get_trailing_eps(ticker, year)
        forward = get_forward_eps(ticker, year)
        if trailing is None or forward is None:
            continue  # skip XLC before 2018

        trailing_beat = trailing - sp500_trailing
        forward_beat = forward - sp500_forward

        # Cap energy trailing EPS for scoring only, not for pass/fail
        score_trailing = min(trailing, config.energy_eps_cap) if ticker == "XLE" else trailing
        composite = (score_trailing - sp500_trailing) * config.weight_trailing + forward_beat * config.weight_forward

        passes_both = trailing > sp500_trailing and forward > sp500_forward

        if passes_both:
            candidates.append((ticker, trailing_beat, forward_beat, composite))
        elif forward > sp500_forward:
            forward_only_candidates.append((ticker, trailing_beat, forward_beat, composite))

    candidates.sort(key=lambda x: x[3], reverse=True)
    selected = candidates[: config.max_sectors]

    # Fallback to forward-only if below min_sectors
    if len(selected) < config.min_sectors:
        forward_only_candidates.sort(key=lambda x: x[3], reverse=True)
        needed = config.min_sectors - len(selected)
        selected_tickers = {t for t, *_ in selected}
        for t, tb, fb, sc in forward_only_candidates:
            if t not in selected_tickers and needed > 0:
                selected.append((t, tb, fb, sc))
                needed -= 1

    if not selected:
        return []

    selected_tickers = [t for t, *_ in selected]
    weights = _selected_weights(selected_tickers, year, config)

    result = []
    for ticker, trailing_beat, forward_beat, score in selected:
        trailing = get_trailing_eps(ticker, year) or 0.0
        forward = get_forward_eps(ticker, year) or 0.0
        result.append(SelectedSector(
            ticker=ticker,
            sector_name=SECTOR_NAMES.get(ticker, ticker),
            trailing_eps=trailing,
            forward_eps=forward,
            trailing_beat=trailing_beat,
            forward_beat=forward_beat,
            score=score,
            weight=weights[ticker],
        ))

    return result


# ── Tax engine ────────────────────────────────────────────────────────────────

def compute_taxes(
    gain: float,
    loss: float,
    carryforward: float,
    is_ltcg: bool,
    rates: CaliforniaTaxRates = CA_RATES,
) -> tuple[float, float]:
    """Return (tax_owed, updated_carryforward)."""
    net_loss_pool = loss + carryforward
    if gain <= 0:
        return 0.0, net_loss_pool + abs(gain)
    net_gain = max(0.0, gain - net_loss_pool)
    remaining_carryforward = max(0.0, net_loss_pool - gain)
    rate = rates.ltcg_effective if is_ltcg else rates.stcg_effective
    return net_gain * rate, remaining_carryforward


# ── Period snapshot ───────────────────────────────────────────────────────────

@dataclass
class PeriodSnapshot:
    year: int
    sectors_held: list[str]
    sector_weights: dict[str, float]
    period_return_pct: float
    cumulative_value: float        # gross (pre-tax) compound value
    taxes_paid_period: float
    taxes_paid_cumulative: float
    post_liquidation_value: float  # what you keep after all taxes
    embedded_tax_liability: float  # only for deferred scenarios
    loss_carryforward_balance: float
    cost_basis: float


# ── Performance metrics ───────────────────────────────────────────────────────

@dataclass
class ScenarioMetrics:
    cagr_pretax_pct: float
    cagr_posttax_pct: float
    sharpe_ratio: float
    max_drawdown_pct: float
    total_taxes_paid: float
    tax_drag_annualized_pct: float
    alpha_vs_spy_pretax_pct: float
    alpha_vs_spy_posttax_pct: float
    total_return_pct: float
    win_rate_vs_benchmark: float
    post_liquidation_value: float
    final_pretax_value: float
    best_year_return_pct: float
    worst_year_return_pct: float


@dataclass
class ScenarioResult:
    id: str
    name: str
    metrics: ScenarioMetrics
    snapshots: list[PeriodSnapshot]


def _cagr(start: float, end: float, years: int) -> float:
    if start <= 0 or end <= 0:
        return 0.0
    return ((end / start) ** (1.0 / years) - 1) * 100


def _sharpe(annual_returns: list[float], risk_free: float = 4.0) -> float:
    if len(annual_returns) < 2:
        return 0.0
    mean = sum(annual_returns) / len(annual_returns)
    variance = sum((r - mean) ** 2 for r in annual_returns) / (len(annual_returns) - 1)
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    return (mean - risk_free) / std


def _max_drawdown(values: list[float]) -> float:
    peak = values[0]
    max_dd = 0.0
    for v in values:
        if v > peak:
            peak = v
        dd = (peak - v) / peak * 100
        if dd > max_dd:
            max_dd = dd
    return max_dd


def _spy_benchmarks(starting_capital: float, rates: CaliforniaTaxRates) -> tuple[float, float]:
    """Return (spy_final_pretax, spy_final_posttax)."""
    raw = starting_capital
    for year in YEARS:
        raw *= (1 + get_annual_return("SPY", year) / 100)
    posttax = raw - max(0, raw - starting_capital) * rates.ltcg_effective
    return raw, posttax


def _compute_metrics(
    snapshots: list[PeriodSnapshot],
    starting_capital: float,
    rates: CaliforniaTaxRates,
) -> ScenarioMetrics:
    n_years = len(YEARS)
    period_returns = [s.period_return_pct for s in snapshots]
    final_pretax = snapshots[-1].cumulative_value
    final_posttax = snapshots[-1].post_liquidation_value
    total_taxes = snapshots[-1].taxes_paid_cumulative

    cagr_pre = _cagr(starting_capital, final_pretax, n_years)
    cagr_post = _cagr(starting_capital, final_posttax, n_years)

    spy_raw, spy_posttax = _spy_benchmarks(starting_capital, rates)
    spy_cagr_pre = _cagr(starting_capital, spy_raw, n_years)
    spy_cagr_post = _cagr(starting_capital, spy_posttax, n_years)

    spy_annual = [get_annual_return("SPY", y) for y in YEARS]
    win_count = sum(1 for pr, sr in zip(period_returns, spy_annual) if pr > sr)

    cumulative_values = [starting_capital] + [s.cumulative_value for s in snapshots]
    max_dd = _max_drawdown(cumulative_values)

    return ScenarioMetrics(
        cagr_pretax_pct=round(cagr_pre, 2),
        cagr_posttax_pct=round(cagr_post, 2),
        sharpe_ratio=round(_sharpe(period_returns), 3),
        max_drawdown_pct=round(max_dd, 2),
        total_taxes_paid=round(total_taxes, 2),
        tax_drag_annualized_pct=round(cagr_pre - cagr_post, 2),
        alpha_vs_spy_pretax_pct=round(cagr_pre - spy_cagr_pre, 2),
        alpha_vs_spy_posttax_pct=round(cagr_post - spy_cagr_post, 2),
        total_return_pct=round((final_pretax / starting_capital - 1) * 100, 2),
        win_rate_vs_benchmark=round(win_count / n_years * 100, 1),
        post_liquidation_value=round(final_posttax, 2),
        final_pretax_value=round(final_pretax, 2),
        best_year_return_pct=round(max(period_returns), 2),
        worst_year_return_pct=round(min(period_returns), 2),
    )


def _deferred_posttax(value: float, cost_basis: float, rates: CaliforniaTaxRates) -> tuple[float, float]:
    gain = max(0.0, value - cost_basis)
    embedded = gain * rates.ltcg_effective
    return value - embedded, embedded


# ── Scenario 1: SPY Buy-and-Hold ──────────────────────────────────────────────

def run_spy_buy_hold(starting_capital: float, rates: CaliforniaTaxRates) -> ScenarioResult:
    raw_value = starting_capital
    cost_basis = starting_capital
    snapshots: list[PeriodSnapshot] = []

    for year in YEARS:
        ret = get_annual_return("SPY", year)
        raw_value *= (1 + ret / 100)
        posttax, embedded = _deferred_posttax(raw_value, cost_basis, rates)
        snapshots.append(PeriodSnapshot(
            year=year,
            sectors_held=["SPY"],
            sector_weights={"SPY": 1.0},
            period_return_pct=round(ret, 2),
            cumulative_value=round(raw_value, 2),
            taxes_paid_period=0.0,
            taxes_paid_cumulative=0.0,
            post_liquidation_value=round(posttax, 2),
            embedded_tax_liability=round(embedded, 2),
            loss_carryforward_balance=0.0,
            cost_basis=cost_basis,
        ))

    # Assign final liquidation tax to last snapshot
    final_value = snapshots[-1].cumulative_value
    final_tax = max(0.0, final_value - cost_basis) * rates.ltcg_effective
    snapshots[-1].taxes_paid_period = round(final_tax, 2)
    snapshots[-1].taxes_paid_cumulative = round(final_tax, 2)

    metrics = _compute_metrics(snapshots, starting_capital, rates)
    return ScenarioResult(id="SPY_BUY_HOLD", name="SPY Buy-and-Hold", metrics=metrics, snapshots=snapshots)


# ── Scenario 2: Algo Annual LTCG ─────────────────────────────────────────────

def run_algo_annual_ltcg(starting_capital: float, rates: CaliforniaTaxRates, weighting_method: str = "equal") -> ScenarioResult:
    """
    Uses Appendix B historical selection returns (authoritative).
    cumulative_value = gross compound (no taxes) for charting.
    post_liquidation_value = after annual LTCG taxes.
    """
    raw_value = starting_capital     # gross, no tax
    net_value = starting_capital     # after paying LTCG each year
    carryforward = 0.0
    taxes_cumulative = 0.0
    snapshots: list[PeriodSnapshot] = []

    history = {row["year"]: row for row in ALGO_SELECTION_HISTORY}
    config = SelectionConfig(weighting_method=_weighting_method(weighting_method))

    for year in YEARS:
        row = history.get(year)
        if row:
            selected_tickers = row["sectors"]
            if config.weighting_method == "market_weight":
                algo_return, sector_weights = _weighted_sector_return(selected_tickers, year, config)
            else:
                algo_return = row["algo_return"]
                sector_weights = _selected_weights(selected_tickers, year, config)
        else:
            selected_tickers = ["SPY"]
            algo_return = get_annual_return("SPY", year)
            sector_weights = {"SPY": 1.0}

        # Track raw (gross) value
        raw_value *= (1 + algo_return / 100)

        # Track net (after-tax) value
        net_start = net_value
        net_value *= (1 + algo_return / 100)

        gain = max(0.0, net_value - net_start)
        loss = max(0.0, net_start - net_value)
        tax, carryforward = compute_taxes(gain, loss, carryforward, is_ltcg=True, rates=rates)
        net_value -= tax
        taxes_cumulative += tax

        snapshots.append(PeriodSnapshot(
            year=year,
            sectors_held=selected_tickers,
            sector_weights={t: round(w, 4) for t, w in sector_weights.items()},
            period_return_pct=round(algo_return, 2),
            cumulative_value=round(raw_value, 2),
            taxes_paid_period=round(tax, 2),
            taxes_paid_cumulative=round(taxes_cumulative, 2),
            post_liquidation_value=round(net_value, 2),
            embedded_tax_liability=0.0,
            loss_carryforward_balance=round(carryforward, 2),
            cost_basis=round(net_value, 2),
        ))

    metrics = _compute_metrics(snapshots, starting_capital, rates)
    return ScenarioResult(id="ALGO_ANNUAL_LTCG", name="Algo — Annual Rebalance (LTCG)", metrics=metrics, snapshots=snapshots)


# ── Scenario 3: Algo Quarterly STCG ──────────────────────────────────────────

def run_algo_quarterly_stcg(starting_capital: float, rates: CaliforniaTaxRates, weighting_method: str = "equal") -> ScenarioResult:
    """
    Uses Appendix B returns, applies STCG rate (54.1%) since quarterly rebalancing
    means positions are held < 12 months.
    """
    raw_value = starting_capital
    net_value = starting_capital
    carryforward = 0.0
    taxes_cumulative = 0.0
    snapshots: list[PeriodSnapshot] = []

    history = {row["year"]: row for row in ALGO_SELECTION_HISTORY}
    config = SelectionConfig(weighting_method=_weighting_method(weighting_method))

    for year in YEARS:
        row = history.get(year)
        if row:
            selected_tickers = row["sectors"]
            if config.weighting_method == "market_weight":
                algo_return, sector_weights = _weighted_sector_return(selected_tickers, year, config)
            else:
                algo_return = row["algo_return"]
                sector_weights = _selected_weights(selected_tickers, year, config)
        else:
            selected_tickers = ["SPY"]
            algo_return = get_annual_return("SPY", year)
            sector_weights = {"SPY": 1.0}

        net_start = net_value
        net_value *= (1 + algo_return / 100)
        gain = max(0.0, net_value - net_start)
        loss = max(0.0, net_start - net_value)
        tax, carryforward = compute_taxes(gain, loss, carryforward, is_ltcg=False, rates=rates)
        net_value -= tax
        taxes_cumulative += tax

        # For STCG scenario: cumulative_value = net value (taxes already paid; no deferred liability)
        snapshots.append(PeriodSnapshot(
            year=year,
            sectors_held=selected_tickers,
            sector_weights={t: round(w, 4) for t, w in sector_weights.items()},
            period_return_pct=round(algo_return, 2),
            cumulative_value=round(net_value, 2),
            taxes_paid_period=round(tax, 2),
            taxes_paid_cumulative=round(taxes_cumulative, 2),
            post_liquidation_value=round(net_value, 2),
            embedded_tax_liability=0.0,
            loss_carryforward_balance=round(carryforward, 2),
            cost_basis=round(net_value, 2),
        ))

    metrics = _compute_metrics(snapshots, starting_capital, rates)
    return ScenarioResult(id="ALGO_QUARTERLY_STCG", name="Algo — Quarterly Rebalance (STCG)", metrics=metrics, snapshots=snapshots)


# ── Scenario 4: Algo No-Rebalance ────────────────────────────────────────────

def run_algo_no_rebalance(starting_capital: float, rates: CaliforniaTaxRates, weighting_method: str = "equal") -> ScenarioResult:
    """Select sectors once (2015 initial = XLK, XLV, XLP, XLRE); drift; defer LTCG."""
    initial_sectors = INITIAL_NO_REBALANCE_SECTORS
    config = SelectionConfig(weighting_method=_weighting_method(weighting_method))
    initial_weights = _selected_weights(initial_sectors, YEARS[0], config)
    positions: dict[str, float] = {t: starting_capital * initial_weights[t] for t in initial_sectors}
    cost_basis = starting_capital
    snapshots: list[PeriodSnapshot] = []

    prev_total = starting_capital
    for year in YEARS:
        for t in positions:
            ret = get_annual_return(t, year)
            positions[t] *= (1 + ret / 100)

        total_value = sum(positions.values())
        period_ret = (total_value / prev_total - 1) * 100
        sector_weights = {t: v / total_value for t, v in positions.items()}
        posttax, embedded = _deferred_posttax(total_value, cost_basis, rates)

        snapshots.append(PeriodSnapshot(
            year=year,
            sectors_held=list(positions.keys()),
            sector_weights={t: round(w, 4) for t, w in sector_weights.items()},
            period_return_pct=round(period_ret, 2),
            cumulative_value=round(total_value, 2),
            taxes_paid_period=0.0,
            taxes_paid_cumulative=0.0,
            post_liquidation_value=round(posttax, 2),
            embedded_tax_liability=round(embedded, 2),
            loss_carryforward_balance=0.0,
            cost_basis=cost_basis,
        ))
        prev_total = total_value

    final_value = snapshots[-1].cumulative_value
    final_tax = max(0.0, final_value - cost_basis) * rates.ltcg_effective
    snapshots[-1].taxes_paid_period = round(final_tax, 2)
    snapshots[-1].taxes_paid_cumulative = round(final_tax, 2)

    metrics = _compute_metrics(snapshots, starting_capital, rates)
    return ScenarioResult(id="ALGO_NO_REBALANCE", name="Algo — Initial Selection, No Rebalance", metrics=metrics, snapshots=snapshots)


# ── Scenario 5: Equal-Weight All Sectors, No Rebalance ───────────────────────

def run_ew_no_rebalance(starting_capital: float, rates: CaliforniaTaxRates) -> ScenarioResult:
    """1/11 per sector at start; drift; defer LTCG. XLC added in 2019."""
    initial_tickers = [t for t in ALL_SECTOR_TICKERS if t != "XLC"]
    positions: dict[str, float] = {t: starting_capital / len(initial_tickers) for t in initial_tickers}
    cost_basis = starting_capital
    snapshots: list[PeriodSnapshot] = []

    prev_total = starting_capital
    for year in YEARS:
        # Add XLC in 2019 (proxy weight = 1/11 of current portfolio)
        if year == 2019 and "XLC" not in positions:
            current_total = sum(positions.values())
            xlc_alloc = current_total / 11
            scale = 1.0 - xlc_alloc / current_total
            positions = {t: v * scale for t, v in positions.items()}
            positions["XLC"] = xlc_alloc

        for t in list(positions.keys()):
            ret = get_annual_return(t, year)
            positions[t] *= (1 + ret / 100)

        total_value = sum(positions.values())
        period_ret = (total_value / prev_total - 1) * 100
        sector_weights = {t: v / total_value for t, v in positions.items()}
        posttax, embedded = _deferred_posttax(total_value, cost_basis, rates)

        snapshots.append(PeriodSnapshot(
            year=year,
            sectors_held=sorted(positions.keys()),
            sector_weights={t: round(w, 4) for t, w in sector_weights.items()},
            period_return_pct=round(period_ret, 2),
            cumulative_value=round(total_value, 2),
            taxes_paid_period=0.0,
            taxes_paid_cumulative=0.0,
            post_liquidation_value=round(posttax, 2),
            embedded_tax_liability=round(embedded, 2),
            loss_carryforward_balance=0.0,
            cost_basis=cost_basis,
        ))
        prev_total = total_value

    final_value = snapshots[-1].cumulative_value
    final_tax = max(0.0, final_value - cost_basis) * rates.ltcg_effective
    snapshots[-1].taxes_paid_period = round(final_tax, 2)
    snapshots[-1].taxes_paid_cumulative = round(final_tax, 2)

    metrics = _compute_metrics(snapshots, starting_capital, rates)
    return ScenarioResult(id="EW_NO_REBALANCE", name="Equal-Weight All Sectors (No Rebalance)", metrics=metrics, snapshots=snapshots)


# ── Main backtest runner ──────────────────────────────────────────────────────

def run_backtest(starting_capital: float = 100_000.0, weighting_method: str = "equal") -> list[ScenarioResult]:
    rates = CA_RATES
    method = _weighting_method(weighting_method)
    return [
        run_spy_buy_hold(starting_capital, rates),
        run_algo_annual_ltcg(starting_capital, rates, method),
        run_algo_quarterly_stcg(starting_capital, rates, method),
        run_algo_no_rebalance(starting_capital, rates, method),
        run_ew_no_rebalance(starting_capital, rates),
    ]


# ── Live allocation ───────────────────────────────────────────────────────────

@dataclass
class LiveAllocation:
    ticker: str
    sector_name: str
    weight: float
    dollar_amount: float
    trailing_eps_beat: float
    forward_eps_beat: float
    composite_score: float


def get_live_allocation(cash_amount: float, time_frame: str = "annual", weighting_method: str = "equal") -> tuple[list[LiveAllocation], dict, str]:
    """
    Return current sector allocation recommendation.
    Per spec timing: the February rebalance uses Q4 of the PRIOR year's data.
    So for a 2025 allocation we use 2024 EPS signals.
    """
    signal_year = YEARS[-2]   # 2024 — the signal used to build the 2025 portfolio
    latest_year = YEARS[-1]   # 2025 — the portfolio year
    config = SelectionConfig(weighting_method=_weighting_method(weighting_method))
    selected = select_sectors(signal_year, config)

    sp500_trailing = get_trailing_eps("SPY", signal_year) or 0.0
    sp500_forward = get_forward_eps("SPY", signal_year) or 0.0

    allocations = []
    live_weight_year = max(SPY_SECTOR_WEIGHTS_BY_YEAR)
    live_weights = _selected_weights([s.ticker for s in selected], live_weight_year, config)
    total_weight = sum(live_weights.values())
    for s in selected:
        source_weight = live_weights.get(s.ticker, s.weight)
        norm_weight = source_weight / total_weight if total_weight > 0 else source_weight
        allocations.append(LiveAllocation(
            ticker=s.ticker,
            sector_name=s.sector_name,
            weight=round(norm_weight, 4),
            dollar_amount=round(cash_amount * norm_weight, 2),
            trailing_eps_beat=round(s.trailing_beat, 1),
            forward_eps_beat=round(s.forward_beat, 1),
            composite_score=round(s.score, 2),
        ))

    sp500_signals = {
        "trailing_eps_growth": sp500_trailing,
        "forward_eps_growth": sp500_forward,
        "signal_year": signal_year,
        "portfolio_year": latest_year,
        "as_of_year": latest_year,
        "weighting_method": config.weighting_method,
    }

    tax_label = "37.1% LTCG" if time_frame in ("annual", "one_time") else "54.1% STCG"
    rebalance_map = {
        "annual": "annually each February",
        "quarterly": "quarterly (Feb/May/Aug/Nov)",
        "one_time": "once (no future rebalancing)",
    }
    rebalance_freq = rebalance_map.get(time_frame, "annually")
    tickers_str = ", ".join(a.ticker for a in allocations)
    weight_label = "S&P 500 sector market weights" if config.weighting_method == "market_weight" else "equal weights"
    guidance = (
        f"Signal source: {signal_year} Q4 EPS data (FactSet Earnings Insight). "
        f"Algorithm selects {tickers_str} for {latest_year}. "
        f"Weighting: {weight_label}, normalized across selected sectors. "
        f"Rebalance {rebalance_freq}. "
        f"California effective tax rate: {tax_label}. "
        f"Total allocation: ${cash_amount:,.2f} across {len(allocations)} sectors."
    )

    return allocations, sp500_signals, guidance


def get_selection_history(weighting_method: str = "equal") -> list[dict]:
    config = SelectionConfig(weighting_method=_weighting_method(weighting_method))
    rows = []
    for row in ALGO_SELECTION_HISTORY:
        selected = row["sectors"]
        if config.weighting_method == "market_weight":
            algo_return, sector_weights = _weighted_sector_return(selected, row["year"], config)
        else:
            algo_return = row["algo_return"]
            sector_weights = _selected_weights(selected, row["year"], config)
        rows.append({
            **row,
            "algo_return": round(algo_return, 2),
            "delta": round(algo_return - row["spy_return"], 2),
            "sector_weights": {ticker: round(weight, 4) for ticker, weight in sector_weights.items()},
            "weighting_method": config.weighting_method,
        })
    return rows
