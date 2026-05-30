"""Wheel strategy scanner: filters CBOE option chains for CSP and CC candidates."""

from services.cboe_service import get_options_batch
from services.ibkr_service import get_all_quotes
from data.tickers import ALL_TICKERS


DEFAULT_CSP_FILTERS = {
    "dte_min": 7,
    "dte_max": 60,
    "delta_min": 0.10,
    "delta_max": 0.40,
    "min_yield": 0.5,          # % raw yield per contract
    "min_ann_yield": 10.0,     # % annualized
    "min_oi": 50,
    "min_volume": 0,
    "max_strike": None,        # no cap by default
    "min_bid": 0.05,           # ignore sub-nickel bids
    "exclude_earnings_days": 7,
}

DEFAULT_CC_FILTERS = {
    "dte_min": 7,
    "dte_max": 60,
    "delta_min": 0.10,
    "delta_max": 0.40,
    "min_yield": 0.5,
    "min_ann_yield": 8.0,
    "min_oi": 50,
    "min_volume": 0,
    "min_bid": 0.05,
}


def _apply_filters(options: list[dict], opt_type: str, filters: dict) -> list[dict]:
    out = []
    for opt in options:
        if opt["option_type"] != opt_type:
            continue
        if opt["dte"] < filters["dte_min"] or opt["dte"] > filters["dte_max"]:
            continue
        if opt["bid"] is not None and opt["bid"] < filters["min_bid"]:
            continue
        if opt["open_interest"] < filters["min_oi"]:
            continue
        if filters["min_volume"] and opt["volume"] < filters["min_volume"]:
            continue
        if opt["delta"] is None:
            continue

        delta_abs = abs(opt["delta"])
        if delta_abs < filters["delta_min"] or delta_abs > filters["delta_max"]:
            continue
        if opt["raw_yield"] is None or opt["raw_yield"] < filters["min_yield"]:
            continue
        if opt["annualized_yield"] is None or opt["annualized_yield"] < filters["min_ann_yield"]:
            continue
        out.append(opt)
    return out


async def run_csp_scan(
    symbols: list[str] | None = None,
    filters: dict | None = None,
) -> list[dict]:
    """Return top CSP (Cash-Secured Put) opportunities sorted by annualized yield."""
    if symbols is None:
        symbols = ALL_TICKERS
    if filters is None:
        filters = DEFAULT_CSP_FILTERS

    quotes = get_all_quotes()
    chains = await get_options_batch(symbols)

    results: list[dict] = []
    for sym, chain in chains.items():
        filtered = _apply_filters(chain, "P", filters)
        # Enrich with stock quote
        q = quotes.get(sym, {})
        for opt in filtered:
            opt["stock_price"] = opt.get("stock_price") or q.get("price")
            opt["change_pct"] = q.get("change_pct")
            opt["iv_rank"] = q.get("iv_rank")
        results.extend(filtered)

    results.sort(key=lambda x: x.get("annualized_yield") or 0, reverse=True)
    return results


async def run_cc_scan(
    symbols: list[str] | None = None,
    filters: dict | None = None,
) -> list[dict]:
    """Return top Covered Call opportunities sorted by annualized yield."""
    if symbols is None:
        symbols = ALL_TICKERS
    if filters is None:
        filters = DEFAULT_CC_FILTERS

    quotes = get_all_quotes()
    chains = await get_options_batch(symbols)

    results: list[dict] = []
    for sym, chain in chains.items():
        filtered = _apply_filters(chain, "C", filters)
        q = quotes.get(sym, {})
        for opt in filtered:
            opt["stock_price"] = opt.get("stock_price") or q.get("price")
            opt["change_pct"] = q.get("change_pct")
            opt["iv_rank"] = q.get("iv_rank")
            # Distance from current price to strike
            if opt["stock_price"] and opt["strike"]:
                opt["upside_pct"] = round(
                    ((opt["strike"] - opt["stock_price"]) / opt["stock_price"]) * 100, 2
                )
        results.extend(filtered)

    results.sort(key=lambda x: x.get("annualized_yield") or 0, reverse=True)
    return results
