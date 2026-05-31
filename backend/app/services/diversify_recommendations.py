"""Generate current-month self-diversification trade recommendations.

Uses today's live prices (via yfinance) to find:
  1. SCHD basket holdings the user already owns that have unrealised losses
     large enough to harvest.
  2. Same-sector replacements to buy (avoiding 30-day wash-sale window).
  3. How many shares of the concentrated stock can be sold tax-free using
     the harvested losses as an offset.

This is the "Self-Diversify" phase — the user takes these trade instructions
to their own brokerage and executes them manually.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Optional

log = logging.getLogger(__name__)

_WASH_SALE_DAYS = 31


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class CurrentHolding:
    symbol: str
    shares: float
    avg_cost: float           # average cost per share
    last_sold_date: Optional[date] = None  # for wash-sale check


@dataclass
class RecommendTrade:
    action: str               # "BUY" or "SELL"
    symbol: str
    name: str
    shares: float
    estimated_price: float
    notional: float
    reason: str
    harvested_loss: Optional[float] = None   # non-None for SELL (harvest) trades


@dataclass
class DiversifyRecommendations:
    as_of_date: str
    harvest_trades: list[RecommendTrade]
    replacement_trades: list[RecommendTrade]
    concentrated_sell: Optional[RecommendTrade]
    total_harvested_loss: float
    net_tax_cost: float              # estimated taxes after harvest offset
    concentration_before_pct: float
    concentration_after_pct: float
    warnings: list[str] = field(default_factory=list)


# ── Main function ─────────────────────────────────────────────────────────────

def get_current_recommendations(
    concentrated_symbol: str,
    concentrated_shares: float,
    avg_cost_basis: float,
    current_schd_holdings: list[CurrentHolding],
    estimated_tax_rate: float = 0.35,
    harvest_threshold: float = 0.03,
) -> DiversifyRecommendations:
    """Generate this-month trade list to continue TLH-funded diversification.

    Args:
        concentrated_symbol:    Ticker of the stock to diversify away from.
        concentrated_shares:    Number of shares still held.
        avg_cost_basis:         Average cost per share.
        current_schd_holdings:  SCHD basket positions the user currently holds.
        estimated_tax_rate:     Combined marginal tax rate.
        harvest_threshold:      Min unrealised loss % to harvest (default 3%).
    """
    from app.services.schd_data import SCHD_TOP25, get_schd_replacement
    from app.services.diversify_price_fetcher import fetch_monthly_prices, get_price_at

    today_str = date.today().isoformat()
    today     = date.today()
    warnings: list[str] = []

    # ── Fetch current prices via Stooq → yfinance (same pattern as backtest) ──
    schd_symbols = [h.symbol for h in current_schd_holdings]
    all_symbols  = list(set(
        [concentrated_symbol] + schd_symbols + [x["symbol"] for x in SCHD_TOP25[:10]]
    ))

    # Fetch last 30 days as monthly — Stooq will return the most recent close
    all_prices = fetch_monthly_prices(
        symbols=all_symbols,
        start_year=today.year,
        end_year=today.year,
    )

    def _price(sym: str) -> Optional[float]:
        return get_price_at(all_prices, sym, today)

    if not _price(concentrated_symbol):
        warnings.append(
            f"Could not fetch price for {concentrated_symbol}. "
            f"Verify the ticker and try again."
        )
        return DiversifyRecommendations(
            as_of_date=today_str,
            harvest_trades=[], replacement_trades=[], concentrated_sell=None,
            total_harvested_loss=0, net_tax_cost=0,
            concentration_before_pct=1.0, concentration_after_pct=1.0,
            warnings=warnings,
        )

    # ── Identify harvestable losses ────────────────────────────────────────────
    harvest_trades:      list[RecommendTrade] = []
    replacement_trades:  list[RecommendTrade] = []
    total_harvested      = 0.0
    today                = date.today()

    name_map = {h["symbol"]: h["name"] for h in SCHD_TOP25}

    recently_sold: set[str] = set()  # track in-session to avoid double-replace

    for holding in current_schd_holdings:
        p = _price(holding.symbol)
        if not p:
            continue

        unreal_pct = (p - holding.avg_cost) / holding.avg_cost
        if unreal_pct >= -harvest_threshold:
            continue  # not enough loss

        # Wash-sale check
        if holding.last_sold_date:
            days_since = (today - holding.last_sold_date).days
            if days_since < _WASH_SALE_DAYS:
                warnings.append(
                    f"Skipping {holding.symbol}: within 30-day wash-sale window "
                    f"(last sold {holding.last_sold_date})."
                )
                continue

        loss      = (holding.avg_cost - p) * holding.shares
        notional  = p * holding.shares
        total_harvested += loss
        recently_sold.add(holding.symbol)

        harvest_trades.append(RecommendTrade(
            action="SELL",
            symbol=holding.symbol,
            name=name_map.get(holding.symbol, holding.symbol),
            shares=round(holding.shares, 4),
            estimated_price=round(p, 2),
            notional=round(notional, 2),
            reason=(
                f"Harvest ${loss:,.0f} unrealised loss "
                f"({unreal_pct*100:.1f}% below cost ${holding.avg_cost:.2f}). "
                f"Saves ~${loss*estimated_tax_rate:,.0f} in taxes."
            ),
            harvested_loss=round(loss, 2),
        ))

        # Find replacement (same sector, outside wash-sale window)
        repl = get_schd_replacement(holding.symbol, recently_sold)
        if repl:
            repl_price = _price(repl)
            if repl_price and repl_price > 0:
                repl_shares = notional / repl_price
                replacement_trades.append(RecommendTrade(
                    action="BUY",
                    symbol=repl,
                    name=name_map.get(repl, repl),
                    shares=round(repl_shares, 4),
                    estimated_price=round(repl_price, 2),
                    notional=round(notional, 2),
                    reason=(
                        f"Replace {holding.symbol} with {repl} — same sector, "
                        f"wait {_WASH_SALE_DAYS}+ days before repurchasing {holding.symbol}."
                    ),
                ))

    # ── Determine how much concentrated stock can be sold ─────────────────────
    conc_sell_trade: Optional[RecommendTrade] = None
    net_tax_cost = 0.0

    if concentrated_shares > 0 and total_harvested >= 1_000:
        conc_price = _price(concentrated_symbol)
        if conc_price and conc_price > avg_cost_basis:
            gain_per_share = conc_price - avg_cost_basis
            shares_to_sell = min(concentrated_shares, total_harvested / gain_per_share)
            shares_to_sell = max(0, shares_to_sell)
            gross_gain     = shares_to_sell * gain_per_share
            offset         = min(gross_gain, total_harvested)
            taxable_gain   = max(0.0, gross_gain - offset)
            net_tax_cost   = taxable_gain * estimated_tax_rate

            if shares_to_sell >= 0.01:
                conc_sell_trade = RecommendTrade(
                    action="SELL",
                    symbol=concentrated_symbol,
                    name=concentrated_symbol,
                    shares=round(shares_to_sell, 4),
                    estimated_price=round(conc_price, 2),
                    notional=round(shares_to_sell * conc_price, 2),
                    reason=(
                        f"Sell {shares_to_sell:.1f} shares to realise ${gross_gain:,.0f} gain. "
                        f"Offset by ${offset:,.0f} harvested losses → net taxable gain ${taxable_gain:,.0f} "
                        f"(estimated tax ${net_tax_cost:,.0f} at {estimated_tax_rate*100:.0f}%)."
                    ),
                    harvested_loss=None,
                )
        elif conc_price and conc_price <= avg_cost_basis:
            # Concentrated stock is also at a loss — harvest it directly
            loss = (avg_cost_basis - conc_price) * concentrated_shares
            harvest_trades.append(RecommendTrade(
                action="SELL",
                symbol=concentrated_symbol,
                name=concentrated_symbol,
                shares=round(concentrated_shares, 4),
                estimated_price=round(conc_price, 2),
                notional=round(concentrated_shares * conc_price, 2),
                reason=(
                    f"Concentrated stock is below cost basis — harvest ${loss:,.0f} loss "
                    f"and fully exit the position."
                ),
                harvested_loss=round(loss, 2),
            ))
            total_harvested += loss
    elif total_harvested < 1_000 and total_harvested > 0:
        warnings.append(
            f"Harvested ${total_harvested:,.0f} in losses — below the ${1_000:,.0f} threshold "
            f"to offset concentrated stock gains. Continue accumulating losses."
        )

    # ── Concentration before / after ─────────────────────────────────────────
    conc_price_now   = _price(concentrated_symbol) or avg_cost_basis
    total_port_value = concentrated_shares * conc_price_now + sum(
        h.shares * (_price(h.symbol) or h.avg_cost) for h in current_schd_holdings
    )
    conc_before_pct  = (concentrated_shares * conc_price_now / total_port_value
                        if total_port_value > 0 else 1.0)

    shares_sold      = (conc_sell_trade.shares if conc_sell_trade else 0.0)
    remaining_conc   = max(0, concentrated_shares - shares_sold)
    total_after      = remaining_conc * conc_price_now + sum(
        h.shares * (_price(h.symbol) or h.avg_cost) for h in current_schd_holdings
    )
    conc_after_pct   = (remaining_conc * conc_price_now / total_after
                        if total_after > 0 else 0.0)

    if not harvest_trades and not conc_sell_trade:
        warnings.append(
            "No positions are currently below the harvest threshold. "
            "Check back when market conditions create losses in your SCHD basket."
        )

    return DiversifyRecommendations(
        as_of_date=today_str,
        harvest_trades=harvest_trades,
        replacement_trades=replacement_trades,
        concentrated_sell=conc_sell_trade,
        total_harvested_loss=round(total_harvested, 2),
        net_tax_cost=round(net_tax_cost, 2),
        concentration_before_pct=round(conc_before_pct, 4),
        concentration_after_pct=round(conc_after_pct, 4),
        warnings=warnings,
    )
