"""
Sector rotation seed data — all historical constants for the 2015-2025 backtest.
Source: Yahoo Finance total returns + FactSet Earnings Insight historical reports.
"""

YEARS = [2015, 2016, 2017, 2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]

ALL_SECTOR_TICKERS = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLB", "XLRE", "XLU", "XLC"]

SECTOR_NAMES: dict[str, str] = {
    "XLK":  "Information Technology",
    "XLF":  "Financials",
    "XLE":  "Energy",
    "XLV":  "Health Care",
    "XLI":  "Industrials",
    "XLY":  "Consumer Discretionary",
    "XLP":  "Consumer Staples",
    "XLB":  "Materials",
    "XLRE": "Real Estate",
    "XLU":  "Utilities",
    "XLC":  "Communication Services",
    "SPY":  "S&P 500",
}

# Annual total returns (dividends reinvested), indexed 0=2015..10=2025
# None = ETF did not exist (XLC pre-Sept-2018)
ANNUAL_RETURNS: dict[str, list[float | None]] = {
    #         2015   2016   2017    2018   2019   2020   2021    2022   2023   2024   2025
    "XLK":  [ 5.9,  13.9,  38.8,  -0.3,  50.3,  43.6,  34.2, -27.7,  56.0,  21.6,  24.6],
    "XLF":  [-2.1,  22.8,  22.2, -13.0,  32.1,  -1.7,  34.9, -10.6,  12.0,  30.6,  14.9],
    "XLE":  [-21.1, 27.4,  -1.0, -18.7,  11.8, -33.7,  53.3,  64.2,  -4.8,   5.7,  -5.0],
    "XLV":  [ 6.9,  -2.7,  22.1,   6.5,  20.8,  13.4,  26.1,  -3.6,   1.5,  -0.4,   5.7],
    "XLI":  [-2.5,  18.9,  21.0, -13.3,  29.3,  11.1,  21.1,  -5.5,  18.2,  16.6,   3.0],
    "XLY":  [ 8.4,   6.0,  23.0,  -0.5,  27.9,  32.7,  24.1, -37.0,  40.9,  25.8,  -3.0],
    "XLP":  [ 6.8,   5.4,  13.2,  -8.4,  27.6,  10.6,  18.6,  -0.7,  -2.5,  12.3,   4.4],
    "XLB":  [-8.3,  16.6,  19.4, -14.7,  24.6,  20.3,  26.9, -12.3,  12.1,   3.0,  -4.7],
    "XLRE": [ 2.4,   8.4,  10.6,  -4.7,  28.1,  -4.7,  46.2, -26.2,  12.4,   5.2,   7.1],
    "XLU":  [-4.9,  16.3,  12.0,   1.4,  26.4,   0.5,  17.7,   1.6, -10.1,  23.4,  11.1],
    "XLC":  [None,  None,  None,  None,  32.7,  27.2,  21.5, -39.9,  55.6,  40.2,   8.0],
    "SPY":  [ 1.4,  12.0,  21.8,  -4.4,  31.5,  18.4,  28.7, -18.2,  26.3,  25.0,  17.7],
}

# XLC proxy for 2015-2018: 0.5 * XLK + 0.5 * XLY
def get_annual_return(ticker: str, year: int) -> float:
    idx = YEARS.index(year)
    val = ANNUAL_RETURNS[ticker][idx]
    if val is None:
        if ticker == "XLC":
            xlk = ANNUAL_RETURNS["XLK"][idx]
            xly = ANNUAL_RETURNS["XLY"][idx]
            return 0.5 * (xlk or 0) + 0.5 * (xly or 0)
        raise ValueError(f"No return data for {ticker} in {year}")
    return val


# Trailing YoY EPS growth by sector, approximate annual averages
# Note: 2021 Energy shows ~999% due to COVID base effect; capped at 300% in scoring
SECTOR_EPS_ANNUAL: dict[str, list[int | None]] = {
    #         2015   2016   2017  2018   2019   2020   2021   2022   2023   2024   2025
    "XLK":  [  12,     8,   14,   36,    10,    22,    42,     2,    18,    28,    24],
    "XLF":  [   5,    14,   20,   28,    16,   -30,    75,     8,    10,    30,    22],
    "XLE":  [ -65,   -15,  290,   82,   -24,  -150,   999,   148,   -40,    -4,    -2],
    "XLV":  [  10,    10,    8,   14,    12,    12,    28,     8,     6,    10,     8],
    "XLI":  [   2,     6,   12,   24,     8,   -32,    52,    12,    10,    14,    10],
    "XLY":  [   8,    12,   14,   20,    12,    10,    58,   -16,    22,    20,     8],
    "XLP":  [   8,     6,    8,   10,    10,     8,    18,     8,     4,     8,     6],
    "XLB":  [ -12,     8,   18,   22,    -8,   -18,    85,    10,     4,     6,     4],
    "XLRE": [  10,    12,   14,   10,    14,   -12,    22,   -10,    -8,     6,     4],
    "XLU":  [   4,     6,    4,    4,     6,     4,    18,     8,    -4,     4,     6],
    "XLC":  [None,  None, None,   20,    20,    20,    42,   -14,    26,    32,    16],
    "SPY":  [   0,     0,   12,   24,     1,   -12,    50,     5,     4,    10,    14],
}

# Forward NTM EPS growth estimates at start of each year
SECTOR_FORWARD_EPS: dict[str, list[int | None]] = {
    #         2015   2016   2017  2018   2019   2020   2021   2022   2023   2024   2025
    "XLK":  [  14,    10,   16,   20,    14,    18,    30,     8,    20,    16,    18],
    "XLF":  [   8,    10,   18,   22,    12,   -20,    50,     6,    -4,    12,    14],
    "XLE":  [ -40,    10,  200,   60,   -20,  -100,   300,   120,   -20,    -8,    -6],
    "XLV":  [  10,    10,    8,   12,    10,     8,    24,     6,     4,     8,     8],
    "XLI":  [   4,     8,   14,   18,     8,   -20,    40,     6,     8,    10,    10],
    "XLY":  [  10,    10,   12,   16,    10,     6,    40,    -8,    20,     8,     4],
    "XLP":  [   8,     6,    8,   10,    10,     6,    16,     6,     2,     6,     6],
    "XLB":  [   4,     8,   16,   18,    -4,   -12,    60,     4,    -4,     4,     2],
    "XLRE": [  12,    14,   12,   10,    14,    -8,    18,    -6,    -6,     4,     6],
    "XLU":  [   4,     4,    4,    6,     6,     4,    14,     6,    -4,     4,     6],
    "XLC":  [None,  None, None,   20,    22,    14,    30,    -8,    24,    20,    16],
    "SPY":  [   6,     4,   12,   14,     4,    -8,    22,     4,     6,     8,    14],
}

def get_trailing_eps(ticker: str, year: int) -> float | None:
    idx = YEARS.index(year)
    val = SECTOR_EPS_ANNUAL[ticker][idx]
    if val is None and ticker == "XLC":
        xlk = SECTOR_EPS_ANNUAL["XLK"][idx]
        xly = SECTOR_EPS_ANNUAL["XLY"][idx]
        if xlk is not None and xly is not None:
            return 0.5 * xlk + 0.5 * xly
        return None
    return float(val) if val is not None else None

def get_forward_eps(ticker: str, year: int) -> float | None:
    idx = YEARS.index(year)
    val = SECTOR_FORWARD_EPS[ticker][idx]
    if val is None and ticker == "XLC":
        xlk = SECTOR_FORWARD_EPS["XLK"][idx]
        xly = SECTOR_FORWARD_EPS["XLY"][idx]
        if xlk is not None and xly is not None:
            return 0.5 * xlk + 0.5 * xly
        return None
    return float(val) if val is not None else None


# Historical algorithm selection results (Appendix B)
ALGO_SELECTION_HISTORY: list[dict] = [
    {"year": 2015, "sectors": ["XLK", "XLV", "XLP", "XLRE"], "algo_return": 5.5,  "spy_return": 1.4,  "delta": 4.1,  "signal": "Tech/Healthcare beat flat S&P EPS"},
    {"year": 2016, "sectors": ["XLF", "XLI", "XLB", "XLU"],  "algo_return": 18.7, "spy_return": 12.0, "delta": 6.7,  "signal": "Bank/industrial Trump-reflation forward guidance"},
    {"year": 2017, "sectors": ["XLK", "XLF", "XLI", "XLB"],  "algo_return": 25.4, "spy_return": 21.8, "delta": 3.6,  "signal": "Tax reform tailwinds, all beat S&P +12% EPS"},
    {"year": 2018, "sectors": ["XLK", "XLF", "XLY", "XLI"],  "algo_return": -6.8, "spy_return": -4.4, "delta": -2.4, "signal": "Post-reform beats; valuations stretched"},
    {"year": 2019, "sectors": ["XLK", "XLC", "XLY", "XLV"],  "algo_return": 32.9, "spy_return": 31.5, "delta": 1.4,  "signal": "Tech/Comm Services forward upgrades dominate"},
    {"year": 2020, "sectors": ["XLK", "XLC", "XLV", "XLP"],  "algo_return": 23.7, "spy_return": 18.4, "delta": 5.3,  "signal": "COVID: digital demand surge + defensive beats"},
    {"year": 2021, "sectors": ["XLK", "XLF", "XLC", "XLB"],  "algo_return": 29.4, "spy_return": 28.7, "delta": 0.7,  "signal": "Recovery: Tech/Comm earnings + cyclical upgrade"},
    {"year": 2022, "sectors": ["XLE", "XLU", "XLP", "XLI"],  "algo_return": 14.9, "spy_return": -18.2,"delta": 33.1, "signal": "Energy +148% EPS; only sectors with positive forward guidance"},
    {"year": 2023, "sectors": ["XLK", "XLC", "XLY", "XLF"],  "algo_return": 41.1, "spy_return": 26.3, "delta": 14.8, "signal": "AI/Tech rebound; Energy forward guidance collapses"},
    {"year": 2024, "sectors": ["XLK", "XLF", "XLC", "XLI"],  "algo_return": 27.3, "spy_return": 25.0, "delta": 2.3,  "signal": "Continued AI earnings + Financials rate-cycle benefit"},
    {"year": 2025, "sectors": ["XLK", "XLF", "XLC", "XLV"],  "algo_return": 13.3, "spy_return": 17.7, "delta": -4.4, "signal": "Tech/Financials beat S&P +14% EPS; Healthcare added defensive"},
]

# Initial selection for ALGO_NO_REBALANCE (Q4 2014 signals)
INITIAL_NO_REBALANCE_SECTORS = ["XLK", "XLV", "XLP", "XLRE"]
