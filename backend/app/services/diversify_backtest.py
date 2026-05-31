"""TLH-funded diversification backtest using real historical prices.

Data source: Stooq (primary, no rate limits) → yfinance fallback.
Results are cached to disk so repeated backtests with the same symbols are instant.
See diversify_price_fetcher.py for the fetch + cache logic.

Algorithm (simplified long-only, no leverage):
  SETUP:
    Start with the concentrated position + a SCHD basket bought with 'starting_cash'.
    SCHD basket is weighted proportionally to SCHD_TOP25 weights.

  EACH MONTH:
    1. Harvest losses: for each SCHD holding down more than harvest_threshold,
       sell it and buy a same-sector replacement (avoiding wash-sale on original).
    2. Use harvested losses to sell concentrated stock tax-free:
       sell ceil(accumulated_losses / gain_per_share) shares of concentrated stock,
       reinvest proceeds into more SCHD basket.

  YEAR-END METRICS:
    harvested_losses, tax_savings, concentration_pct, HHI, trade_count.

  COMPARISON:
    immediate_sell_tax_cost = embedded_gain × tax_rate
    net_tlh_benefit         = total_tax_savings − cumulative_tracking_cost
    tlh_wins                = net_tlh_benefit > 0
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date
from typing import Optional

log = logging.getLogger(__name__)

_MIN_OFFSET    = 1_000.0   # min accumulated loss before triggering a concentrated-stock sale
_WASH_SALE_DAYS = 31       # IRS wash-sale window


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class DiversifyYearResult:
    year: int
    harvested_losses: float
    tax_savings: float
    concentration_pct: float    # % of portfolio in the concentrated stock at year-end
    hhi: float
    schd_value: float
    concentrated_value: float
    trade_count: int
    data_source: str = "stooq/yfinance"
    warnings: list[str] = field(default_factory=list)


@dataclass
class DiversifyBacktestResult:
    years: list[DiversifyYearResult]
    total_harvested_losses: float
    total_tax_savings: float
    immediate_sell_tax_cost: float
    net_tlh_benefit: float
    savings_vs_immediate_sell: float
    tlh_wins: bool
    concentration_start_pct: float
    concentration_end_pct: float
    warnings: list[str] = field(default_factory=list)


@dataclass
class _Lot:
    symbol: str
    shares: float
    cost_per_share: float
    purchase_date: date
    is_replacement: bool = False
    original_symbol: str = ""


# ── Main backtest ─────────────────────────────────────────────────────────────

def run_diversify_backtest(
    concentrated_symbol: str,
    concentrated_shares: float,
    avg_cost_basis: float,
    starting_cash: float,
    years: list[int],
    estimated_tax_rate: float,
    harvest_threshold: float = 0.03,
    alpha_vantage_key: str | None = None,
) -> DiversifyBacktestResult:
    """Run TLH-funded diversification backtest.

    Args:
        concentrated_symbol:  Ticker of the concentrated stock (e.g. "TSLA").
        concentrated_shares:  Number of shares held at the start.
        avg_cost_basis:       Average cost per share.
        starting_cash:        Additional cash to deploy into the SCHD basket.
        years:                Calendar years to simulate (e.g. [2022, 2023, 2024]).
        estimated_tax_rate:   Combined marginal rate (e.g. 0.35).
        harvest_threshold:    Min unrealised loss % to harvest (default 3%).
    """
    from app.services.schd_data import SCHD_TOP25, get_schd_replacement
    from app.services.diversify_price_fetcher import fetch_monthly_prices, get_price_at

    warnings: list[str] = []

    # ── Fetch all historical monthly prices ───────────────────────────────────
    all_symbols = [concentrated_symbol] + [h["symbol"] for h in SCHD_TOP25]
    all_prices  = fetch_monthly_prices(
        symbols=all_symbols,
        start_year=min(years),
        end_year=max(years),
        alpha_vantage_key=alpha_vantage_key,
    )

    if concentrated_symbol not in all_prices:
        warnings.append(
            f"Could not fetch price history for {concentrated_symbol}. "
            f"Verify the ticker symbol and try again."
        )
        return _fallback_result(concentrated_symbol, concentrated_shares,
                                 avg_cost_basis, starting_cash, years,
                                 estimated_tax_rate, warnings)

    missing_schd = [h["symbol"] for h in SCHD_TOP25 if h["symbol"] not in all_prices]
    if missing_schd:
        warnings.append(
            f"Price data unavailable for {len(missing_schd)} SCHD constituents "
            f"({', '.join(missing_schd[:5])}{'…' if len(missing_schd) > 5 else ''}). "
            f"Those positions were skipped in the simulation."
        )

    def _p(sym: str, d: date) -> Optional[float]:
        return get_price_at(all_prices, sym, d)

    # ── Initialise portfolio at start of simulation ───────────────────────────
    start_year  = min(years)
    start_date  = date(start_year, 1, 1)
    conc_price_start = _p(concentrated_symbol, start_date) or avg_cost_basis

    schd_lots: list[_Lot] = []
    total_schd_weight = sum(h["weight"] for h in SCHD_TOP25)
    for h in SCHD_TOP25:
        if h["symbol"] not in all_prices:
            continue
        alloc = starting_cash * (h["weight"] / total_schd_weight)
        p     = _p(h["symbol"], start_date)
        if p and p > 0:
            schd_lots.append(_Lot(
                symbol=h["symbol"], shares=alloc / p,
                cost_per_share=p, purchase_date=start_date,
            ))

    conc_lot = _Lot(
        symbol=concentrated_symbol,
        shares=concentrated_shares,
        cost_per_share=avg_cost_basis,
        purchase_date=date(start_year - 5, 1, 1),  # assume held long-term
    )

    # ── Year-by-year simulation ───────────────────────────────────────────────
    year_results:  list[DiversifyYearResult] = []
    sold_dates:    dict[str, date]           = {}  # wash-sale tracking

    for year in sorted(years):
        year_harvested = 0.0
        annual_trades  = 0
        year_warnings: list[str] = []

        for month in range(1, 13):
            try:
                month_date = date(year, month, 28)
            except ValueError:
                continue

            if conc_lot.shares <= 0:
                break

            # ── Step 1: harvest losses in SCHD basket ─────────────────────────
            lots_to_remove: list[_Lot] = []
            lots_to_add:    list[_Lot] = []

            for lot in list(schd_lots):
                p = _p(lot.symbol, month_date)
                if not p:
                    continue
                unreal_pct = (p - lot.cost_per_share) / lot.cost_per_share
                if unreal_pct >= -harvest_threshold:
                    continue

                # Wash-sale: skip if same symbol sold within 30 days
                last_sold = sold_dates.get(lot.symbol)
                if last_sold and (month_date - last_sold).days < _WASH_SALE_DAYS:
                    continue

                loss          = (lot.cost_per_share - p) * lot.shares
                proceeds      = p * lot.shares
                year_harvested += loss
                annual_trades  += 1
                sold_dates[lot.symbol] = month_date
                lots_to_remove.append(lot)

                # Buy same-sector replacement
                exclude = {lot.symbol} | set(sold_dates.keys())
                repl    = get_schd_replacement(lot.symbol, exclude)
                if repl and _p(repl, month_date):
                    repl_price = _p(repl, month_date)
                    if repl_price and repl_price > 0:
                        lots_to_add.append(_Lot(
                            symbol=repl, shares=proceeds / repl_price,
                            cost_per_share=repl_price, purchase_date=month_date,
                            is_replacement=True, original_symbol=lot.symbol,
                        ))

            for lot in lots_to_remove:
                schd_lots.remove(lot)
            schd_lots.extend(lots_to_add)

            # ── Step 2: use losses to sell concentrated stock ─────────────────
            if conc_lot.shares > 0 and year_harvested >= _MIN_OFFSET:
                conc_price = _p(concentrated_symbol, month_date)
                if conc_price and conc_price > conc_lot.cost_per_share:
                    gain_per_share = conc_price - conc_lot.cost_per_share
                    shares_to_sell = min(conc_lot.shares, year_harvested / gain_per_share)
                    if shares_to_sell >= 0.01:
                        proceeds = shares_to_sell * conc_price
                        conc_lot = _Lot(
                            symbol=concentrated_symbol,
                            shares=conc_lot.shares - shares_to_sell,
                            cost_per_share=conc_lot.cost_per_share,
                            purchase_date=conc_lot.purchase_date,
                        )
                        annual_trades += 1
                        # Reinvest proceeds into SCHD basket (top-10 by weight)
                        top10 = [h for h in SCHD_TOP25[:10] if h["symbol"] in all_prices]
                        w10   = sum(h["weight"] for h in top10)
                        for h in top10:
                            alloc = proceeds * (h["weight"] / w10)
                            p2    = _p(h["symbol"], month_date)
                            if p2 and p2 > 0:
                                schd_lots.append(_Lot(
                                    symbol=h["symbol"], shares=alloc / p2,
                                    cost_per_share=p2, purchase_date=month_date,
                                ))

        # ── Year-end valuation ────────────────────────────────────────────────
        year_end = date(year, 12, 31)

        conc_price_end = _p(concentrated_symbol, year_end) or conc_price_start
        conc_val       = conc_lot.shares * conc_price_end

        schd_val = sum(
            lot.shares * (_p(lot.symbol, year_end) or lot.cost_per_share)
            for lot in schd_lots
        )

        total_val = conc_val + schd_val
        conc_pct  = (conc_val / total_val) if total_val > 0 else 1.0

        # HHI from current portfolio weights
        weights: dict[str, float] = {concentrated_symbol: conc_val}
        for lot in schd_lots:
            v = lot.shares * (_p(lot.symbol, year_end) or lot.cost_per_share)
            weights[lot.symbol] = weights.get(lot.symbol, 0.0) + v
        total_w = sum(weights.values())
        hhi_val = sum((v / total_w) ** 2 for v in weights.values()) if total_w > 0 else 1.0

        tax_savings = year_harvested * estimated_tax_rate

        year_results.append(DiversifyYearResult(
            year=year,
            harvested_losses=round(year_harvested, 2),
            tax_savings=round(tax_savings, 2),
            concentration_pct=round(conc_pct, 4),
            hhi=round(hhi_val, 4),
            schd_value=round(schd_val, 2),
            concentrated_value=round(conc_val, 2),
            trade_count=annual_trades,
            warnings=year_warnings,
        ))

    # ── Aggregate ─────────────────────────────────────────────────────────────
    total_harvested = sum(r.harvested_losses for r in year_results)
    total_tax_saved = sum(r.tax_savings      for r in year_results)

    conc_now          = _p(concentrated_symbol, date.today()) or conc_price_start
    embedded_gain     = max(0.0, (conc_now - avg_cost_basis) * concentrated_shares)
    immediate_cost    = embedded_gain * estimated_tax_rate

    total_port        = concentrated_shares * conc_price_start + starting_cash
    tracking_est      = total_port * 0.005 * len(years)   # ~0.5%/yr tracking cost

    net_benefit       = total_tax_saved - tracking_est
    savings_vs_sell   = net_benefit - immediate_cost

    conc_start_pct = (
        (concentrated_shares * conc_price_start)
        / (concentrated_shares * conc_price_start + starting_cash + 1e-9)
    )
    conc_end_pct = year_results[-1].concentration_pct if year_results else conc_start_pct

    return DiversifyBacktestResult(
        years=year_results,
        total_harvested_losses=round(total_harvested, 2),
        total_tax_savings=round(total_tax_saved, 2),
        immediate_sell_tax_cost=round(immediate_cost, 2),
        net_tlh_benefit=round(net_benefit, 2),
        savings_vs_immediate_sell=round(savings_vs_sell, 2),
        tlh_wins=savings_vs_sell > 0,
        concentration_start_pct=round(conc_start_pct, 4),
        concentration_end_pct=round(conc_end_pct, 4),
        warnings=warnings,
    )


# ── Fallback for complete data failures ───────────────────────────────────────

def _fallback_result(
    symbol: str, shares: float, basis: float, cash: float,
    years: list[int], tax_rate: float, warnings: list[str],
) -> DiversifyBacktestResult:
    fake = [
        DiversifyYearResult(
            year=y, harvested_losses=0, tax_savings=0,
            concentration_pct=1.0, hhi=1.0, schd_value=0,
            concentrated_value=shares * basis, trade_count=0,
            warnings=["Price data unavailable."],
        )
        for y in years
    ]
    return DiversifyBacktestResult(
        years=fake,
        total_harvested_losses=0, total_tax_savings=0,
        immediate_sell_tax_cost=0, net_tlh_benefit=0,
        savings_vs_immediate_sell=0, tlh_wins=False,
        concentration_start_pct=1.0, concentration_end_pct=1.0,
        warnings=warnings,
    )
