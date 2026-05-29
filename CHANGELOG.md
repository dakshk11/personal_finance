# Changelog

All notable changes to FinanceOS are documented here.

## [Unreleased]

- Ongoing improvements to AI Studio workflows and data provider reliability.

---

## [0.6.0] — 2025-05-01

### Added
- **Breakout Scanner** — S&P 500-only ceiling breakout, momentum breakout, and near-breakout watch detectors with relative-volume, SMA trend context, and Backtest Lab forward-return distributions.
- **RSI Playbook** — Combined Wheel Strategy + Portfolio Sync universe with RSI 14 and EMA 8/21/55 action zones and click-through chart details.

---

## [0.5.0] — 2025-03-01

### Added
- **Earnings Agent** — SEC 8-K exhibit retrieval, company IR slides, Motley Fool transcript coverage, and saved per-user digest history.
- **Equity Research** — yfinance profile and five-year financials, sector peer context, simple DCF model, and saved educational research stance history.
- **FinanceOS Studio** — Unified workspace combining encrypted OpenAI key storage, AI Planner reports, Personal CFO, Portfolio Sync, Wheel Strategy, RSI Playbook, Breakout Scanner, Equity Research, and Earnings Agent.

---

## [0.4.0] — 2025-01-01

### Added
- **Portfolio Sync** — Read-only SnapTrade brokerage connection, holdings normalization, aggregate exposure, sector mix, and concentration warnings.
- **Wheel Strategy** — Daily scan for S&P 500 and Nasdaq top holdings plus core and leveraged ETFs using yfinance option chains, Black-Scholes delta, and TradeGemini-inspired review checks.

---

## [0.3.0] — 2024-10-01

### Added
- **13F Research** — SEC manager search, filing watch, holdings download, and copycat performance simulation.
- **Advisor Workspace** — Taxable account transition proposals with gain budgets, tracking constraints, active-share constraints, exclusions, and CSV export.
- **Ideas Workspace** — Self-managed investor playbooks for sector ETF TLH, asset location, retirement buckets, TIPS ladders, charitable giving, Roth windows, and rebalancing bands.

---

## [0.2.0] — 2024-07-01

### Added
- **Portfolio Analyzer** — User-entered tickers, shares, and cost basis with daily price cache, unrealized gain/loss, and forward P/E comparison against 5-year and 10-year averages.
- **Retirement Analyzer** — Tax-aware withdrawal sequencing, Roth conversion analysis, bucket planning, and Natural Retirement Spending Smile projection.

---

## [0.1.0] — 2024-04-01

### Added
- **Portfolio Dashboard** — Direct-index simulation for XLG, SPY, TOPT, and QTOP with backtests, TLH review, model comparison, and portfolio import.
- Docker Compose local stack with FastAPI backend, Next.js frontend, PostgreSQL, Redis, and Celery.
- MIT license and initial documentation.
