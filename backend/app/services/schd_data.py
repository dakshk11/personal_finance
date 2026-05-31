"""SCHD (Schwab US Dividend Equity ETF) holdings data.

Top-25 constituents by weight as of May 2026.  These cover ~65% of SCHD's NAV.
Used by the Portfolio Diversification feature to simulate TLH-funded diversification.

Source: Schwab Asset Management / stockanalysis.com, May 2026.
Sector breakdown: Energy ~19%, Consumer Staples ~18%, Health Care ~16%,
                  Financials ~18%, Industrials ~13%, Technology ~9%,
                  Communication ~6%, Consumer Discretionary ~5%.
"""

from __future__ import annotations

SCHD_TOP25: list[dict] = [
    {"symbol": "QCOM",  "name": "QUALCOMM Incorporated",         "sector": "Technology",              "weight": 0.0625},
    {"symbol": "TXN",   "name": "Texas Instruments Incorporated", "sector": "Technology",              "weight": 0.0612},
    {"symbol": "UNH",   "name": "UnitedHealth Group",             "sector": "Health Care",             "weight": 0.0513},
    {"symbol": "KO",    "name": "The Coca-Cola Company",          "sector": "Consumer Staples",        "weight": 0.0408},
    {"symbol": "MRK",   "name": "Merck & Co.",                    "sector": "Health Care",             "weight": 0.0390},
    {"symbol": "CVX",   "name": "Chevron Corporation",            "sector": "Energy",                  "weight": 0.0383},
    {"symbol": "VZ",    "name": "Verizon Communications",         "sector": "Communication",           "weight": 0.0368},
    {"symbol": "PG",    "name": "Procter & Gamble",               "sector": "Consumer Staples",        "weight": 0.0364},
    {"symbol": "COP",   "name": "ConocoPhillips",                 "sector": "Energy",                  "weight": 0.0354},
    {"symbol": "PEP",   "name": "PepsiCo Inc.",                   "sector": "Consumer Staples",        "weight": 0.0352},
    {"symbol": "AMGN",  "name": "Amgen Inc.",                     "sector": "Health Care",             "weight": 0.0346},
    {"symbol": "HD",    "name": "The Home Depot",                 "sector": "Consumer Discretionary",  "weight": 0.0336},
    {"symbol": "MO",    "name": "Altria Group",                   "sector": "Consumer Staples",        "weight": 0.0304},
    {"symbol": "ABT",   "name": "Abbott Laboratories",            "sector": "Health Care",             "weight": 0.0296},
    {"symbol": "BMY",   "name": "Bristol-Myers Squibb",           "sector": "Health Care",             "weight": 0.0294},
    {"symbol": "ACN",   "name": "Accenture plc",                  "sector": "Technology",              "weight": 0.0272},
    {"symbol": "LMT",   "name": "Lockheed Martin",                "sector": "Industrials",             "weight": 0.0270},
    {"symbol": "CMCSA", "name": "Comcast Corporation",            "sector": "Communication",           "weight": 0.0227},
    {"symbol": "BX",    "name": "Blackstone Inc.",                "sector": "Financials",              "weight": 0.0222},
    {"symbol": "ADP",   "name": "Automatic Data Processing",      "sector": "Technology",              "weight": 0.0220},
    {"symbol": "LOW",   "name": "Lowe's Companies",               "sector": "Consumer Discretionary",  "weight": 0.0200},
    {"symbol": "MMM",   "name": "3M Company",                     "sector": "Industrials",             "weight": 0.0190},
    {"symbol": "IBM",   "name": "International Business Machines","sector": "Technology",              "weight": 0.0185},
    {"symbol": "OKE",   "name": "ONEOK Inc.",                     "sector": "Energy",                  "weight": 0.0180},
    {"symbol": "EOG",   "name": "EOG Resources",                  "sector": "Energy",                  "weight": 0.0175},
]

# SCHD broad sector weights (approximate, for gap analysis vs user portfolio)
SCHD_SECTOR_WEIGHTS: dict[str, float] = {
    "Energy":               0.19,
    "Consumer Staples":     0.18,
    "Financials":           0.18,
    "Health Care":          0.16,
    "Industrials":          0.13,
    "Technology":           0.09,
    "Communication":        0.06,
    "Consumer Discretionary": 0.05,
    "Materials":            0.02,
    "Utilities":            0.02,
    "Real Estate":          0.01,
    "Other":                0.01,
}

# Sector → list of SCHD_TOP25 symbols for wash-sale replacement
_SECTOR_MAP: dict[str, list[str]] = {}
for _h in SCHD_TOP25:
    _SECTOR_MAP.setdefault(_h["sector"], []).append(_h["symbol"])


def get_schd_holdings() -> list[dict]:
    """Return all SCHD top-25 holdings."""
    return list(SCHD_TOP25)


def get_schd_symbols() -> list[str]:
    return [h["symbol"] for h in SCHD_TOP25]


def get_schd_sector_weights() -> dict[str, float]:
    return dict(SCHD_SECTOR_WEIGHTS)


def get_schd_replacement(symbol: str, exclude: set[str] | None = None) -> str | None:
    """Return a same-sector SCHD replacement for `symbol`, skipping `exclude` (wash-sale).

    Used when harvesting a loss: pick a different security in the same sector so
    we maintain sector exposure without triggering a wash-sale on the original.
    """
    sector = next((h["sector"] for h in SCHD_TOP25 if h["symbol"] == symbol), None)
    if not sector:
        return None
    candidates = [s for s in _SECTOR_MAP.get(sector, []) if s != symbol]
    if exclude:
        candidates = [s for s in candidates if s not in exclude]
    return candidates[0] if candidates else None
