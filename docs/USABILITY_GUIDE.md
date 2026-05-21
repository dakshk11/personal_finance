# DirectIndex Usability Guide

This guide is intended for product demos, user onboarding, and investor/customer-facing explanation. It describes the main workflows in plain language and maps each screen to the value it provides.

DirectIndex is simulation-only planning software. It does not provide tax, legal, accounting, investment, fiduciary, brokerage, or trading advice.

## Product Narrative

DirectIndex helps users and advisors answer practical planning questions before implementation:

- If I directly index an ETF or index, how much tracking drift might I accept?
- Which tax-loss harvesting model produces useful losses without creating operational noise?
- Which existing holdings have large embedded gains, high concentration, or valuation signals that deserve review?
- How should I transition a taxable legacy account without ignoring embedded gains?
- What does a retirement plan look like after state taxes, account type, Roth conversion windows, and spending changes?
- How can users understand the research and assumptions behind the model before trusting the output?

## First Impression

The landing page positions the product as a broader tax-aware portfolio, retirement, and self-managed investor planning platform and makes clear that the product is simulation-only.

<img src="screenshots/home.jpg" alt="DirectIndex landing page" width="900">

What to point out in a demo:

- The primary workflow is not generic budgeting. It is tax-aware portfolio, taxable transition, and retirement planning.
- The UI makes the simulation status visible.
- The main navigation exposes the product modules immediately: Portfolio Analyzer, Research, Retirement Analyzer, Advisor Workspace, Login, and Signup.

## Portfolio Dashboard

The portfolio dashboard is the first authenticated workspace. It is designed for repeated analysis by a user or advisor.

<img src="screenshots/dashboard.jpg" alt="Portfolio dashboard" width="900">

Primary user jobs:

- Create a simulated direct-index portfolio.
- Select the benchmark index.
- Run backtests by year, direct-indexing model, TLH mode, and tax rate.
- Compare tracking score, harvested losses, dropped candidates, and trade cap usage.
- Import holdings and tax lots for more realistic taxable-account analysis.
- Review exclusions and wash-sale-sensitive replacement logic before action.

Professional positioning:

- The dashboard is a review surface, not an execution blotter.
- Warnings stay visible so model limitations are part of the workflow.
- The app caps TLH output to keep recommendations operationally reviewable.

## Portfolio Analyzer

The portfolio analyzer is for users who already know their holdings and want a valuation, concentration, and tax-basis review without starting from a benchmark model.

<img src="screenshots/portfolio-analyzer.jpg" alt="Portfolio analyzer" width="900">

Primary user jobs:

- Enter tickers, shares, and cost basis per share, especially for holdings above 1% of the account.
- Review daily market value, account weight, total cost basis, and unrealized gain/loss.
- Compare forward P/E against 5-year and 10-year forward P/E averages.
- Identify valuation signals such as below 5-year average, below 10-year average, or at/above historical averages.
- See whether each row used Stooq close data, yfinance data, deterministic fallback data, or a mixed source such as real price with fallback valuation metrics.

Professional positioning:

- The screen works for self-managed investors who do not want to use direct indexing but still want a disciplined review process.
- Cost basis is visible because tax consequences matter when a holding is trimmed, gifted, donated, or transitioned.
- Data-source labels are intentionally exposed so users can separate real daily close data from fallback valuation estimates.

## Retirement Analyzer

The retirement analyzer is built around user-entered household, account, income, tax, and spending assumptions.

<img src="screenshots/retirement-analyzer.jpg" alt="Retirement analyzer" width="900">

Primary user jobs:

- Enter taxable, tax-deferred, Roth/HSA, and cash balances.
- Model current income as after-tax income until retirement.
- Add Social Security and pension income.
- Choose current state and retirement state tax assumptions.
- Project annual retirement spending with the Natural Retirement Spending Smile.
- Evaluate Roth conversion timing, suggested amount, tax funding, and reasoning.
- See annual spending funded by stable income, taxable, tax-deferred, Roth, cash, and any shortfall.
- Change how many detailed cash-flow rows are shown, with 36 rows as the default.
- Compare Roth conversion tax savings using the user's current effective tax rate and different conversion percentages.
- Add life events, family gifting goals, and estate-plan status to the planning context.
- Allocate reserves across cash/T-bills, bonds, and growth assets to reduce forced selling risk.

Professional positioning:

- The analyzer explains why the model makes a recommendation.
- Detailed reasoning is collapsible so the screen stays usable.
- Inputs are saved for authenticated users so the workflow can be revisited.

## Advisor Workspace

The advisor workspace supports a taxable legacy-account transition proposal.

<img src="screenshots/advisor-workspace.jpg" alt="Advisor workspace" width="900">

Primary user jobs:

- Create a client planning record.
- Import current holdings and tax lots.
- Set target index, gain budget, tracking-error limit, active-share limit, tax rate, exclusions, and household notes.
- Generate transition recommendations.
- Review tax impact, drift, active share, assumptions, and warnings.
- Export proposal recommendations to CSV.

Professional positioning:

- The workflow separates analysis from implementation.
- The user must acknowledge the legal disclaimer before generating a proposal.
- Imported data and assumptions are part of the review record.

## Research Center

The research center gives users context for the methodology and keeps assumptions visible.

<img src="screenshots/research.jpg" alt="Research page" width="900">

Primary user jobs:

- Understand how tax-loss harvesting candidates are found.
- Learn why wash-sale safeguards matter.
- Compare executable models with research-only models.
- Review the plain-English rationale behind direct indexing and TLH assumptions.

Professional positioning:

- The product does not hide behind a black box.
- Research links and model notes help users understand limitations.
- Plain-language explanations support user trust without implying advice.

## Suggested Demo Flow

1. Start at the landing page and explain the simulation-only scope.
2. Open Research to establish methodology and user trust.
3. Log in with the local demo account.
4. Open Dashboard and create or select a direct-index portfolio.
5. Run a backtest and compare TLH modes.
6. Open Portfolio Analyzer and show how entered holdings, cost basis, daily close data, unrealized gains, and valuation signals are reviewed.
7. Open Advisor Workspace and show how a taxable transition proposal is generated from imported lots and constraints.
8. Open Retirement Analyzer and show account inputs, state taxes, spending smile, Roth conversion reasoning, and the annual funding mix chart.
9. End by reiterating that outputs are planning artifacts for professional review, not trade or tax instructions.

## Usability Principles

- Keep warnings close to the output they qualify.
- Preserve user-entered retirement assumptions after login.
- Use collapsible reasoning for advanced tax and retirement details.
- Prefer clear numbers, charts, and funding sources over broad summaries.
- Expose data-source labels when price and valuation data come from different providers or fallback estimates.
- Make the distinction between simulation and implementation unavoidable.
- Keep product copy professional, specific, and conservative.

## Current Limitations

- The app is designed for local development and demonstration.
- Data can fall back to deterministic demo values when providers are unavailable or throttled.
- Portfolio Analyzer rows can mix sources, such as Stooq daily close prices with fallback forward P/E estimates.
- Tax and retirement calculations use simplified assumptions.
- Retirement analyzer output is deterministic, not a Monte Carlo engine.
- No live trading, custody, tax filing, or brokerage execution is provided.

## Local Demo Credentials

When `SEED_TEST_ACCOUNT=true`, the backend seeds:

- Email: `test@gmail.com`
- Password: `1234`

Disable this behavior before using any non-local environment.
