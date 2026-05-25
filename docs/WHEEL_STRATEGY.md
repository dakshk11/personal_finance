# Wheel Strategy

The Wheel Strategy workspace lives at `/ai-advisor` under the **Wheel Strategy** tab. It is an educational research cockpit for daily cash-secured put and covered-call review. It does not place orders and does not provide investment advice.

## What It Does

- Builds a default scan universe from the de-duplicated union of:
  - S&P 500 top 30 holdings
  - Nasdaq top 30 holdings
  - Core ETFs: `QQQ`, `SPY`, `SMH`, `XLE`, and `XLI`
  - Leveraged ETFs: `UPRO`, `TQQQ`, and `SOXL`
- Runs a daily scan using cached market history and yfinance option chains when available.
- Reviews 30-45 DTE cash-secured put candidates near 0.20-0.35 absolute delta.
- Computes put delta with a Black-Scholes approximation using live implied volatility.
- Ranks candidates with a Deep Dive Summary that uses review language such as research priority, candidate, and manually verify.
- Tracks accepted put candidates through a simple wheel lifecycle:
  - 50% profit alert
  - Assignment tracking
  - Covered-call candidate alert after assignment
  - Roll review only under 14 DTE and only when a positive net credit is available

## Provider Behavior

The first-choice option provider is `yfinance`, which is already part of the backend dependency set and does not require new credentials.

The scanner can fall back to deterministic contracts if provider calls fail or no usable chain is available. Fallback data is labeled in the API and UI. Fallback data exists to keep the demo/research interface usable; it should be manually verified before any real-world decision.

## Review Logic

The signal logic is inspired by public TradeGemini education pages, including [Getting Started](https://tradegemini.com/getting-started), [Wheel](https://tradegemini.com/wheel), and [Wheel Guide](https://tradegemini.com/wheel-guide), but the implementation and UI are original to this project.

Cash-secured put review checks include:

- Premium yield versus configured minimum
- RSI below the configured entry ceiling
- Bollinger Band % below the configured extension ceiling
- Contract IV and IV-rank proxy
- No known earnings inside the configured exclusion window
- Open interest minimum
- Bid/ask spread maximum
- 30-45 DTE target window
- 0.20-0.35 absolute delta target window
- Overall account exposure cap
- Single-name exposure cap
- Sector exposure cap

Trend and red-day context are shown as review context instead of hard blockers.

## API Endpoints

Base path: `/option-strategy`

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/universe` | Returns the default Wheel Strategy universe with symbol, name, sector, group, and count. |
| `GET` | `/config` | Returns user config plus computed Wheel defaults such as universe groups, scan cadence, target delta range, IV rank minimum, and exposure caps. |
| `PUT` | `/config` | Updates compatible legacy config fields such as tickers, account value, exposure cap, DTE range, RSI settings, IV minimum, premium yield minimum, and webhook URL. |
| `POST` | `/scan?force=false` | Runs or returns the daily scan cache. Use `force=true` to bypass the daily cache. |
| `GET` | `/signals` | Returns the latest saved signal candidates. |
| `GET` | `/positions` | Returns open wheel positions. |
| `POST` | `/positions` | Records lifecycle events such as `accepted_put`, `assigned`, and `closed`. |
| `GET` | `/alerts` | Returns generated wheel alerts. |

## Signal Fields

Signal output includes the legacy fields plus:

- `sector`
- `bb_percent`
- `iv_rank`
- `earnings_date`
- `earnings_days`
- `spread_pct`
- `score`
- `deep_dive_rank`
- `deep_dive_summary`
- `if_expires_return`
- `if_assigned_basis`
- `provider`

## Config Fields

The config response includes:

- `universe_groups`
- `scan_cadence`
- `target_delta_min`
- `target_delta_max`
- `min_iv_rank`
- `bb_percent_max`
- `earnings_exclusion_days`
- `min_open_interest`
- `max_spread_pct`
- `profit_take_pct`
- `single_name_cap`
- `sector_cap`

Some of these values are currently computed defaults rather than database columns, which keeps the existing database shape stable.

## UI Notes

The Wheel Strategy tab is designed as a dense dark workbench:

- Compact top metrics
- Horizontal universe chip strip
- Deep Dive Summary panel for the top research priorities
- Signal candidate table with horizontal scrolling
- Checklist panel for candidate blockers
- Position and alert lifecycle cards
- Clear no-advice framing

The UI filters saved signals to symbols in the current Wheel universe and labels fallback/estimated scan data distinctly from live yfinance data.

## Testing

Focused tests live in `backend/tests/test_option_strategy.py`.

Run:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests/test_option_strategy.py -q
```

Full backend suite:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q
```

Frontend typecheck:

```bash
cd frontend
npm run typecheck
```

Browser QA should cover:

- `/ai-advisor` loads without login redirect
- Wheel Strategy tab renders on desktop and mobile
- Deep Dive Summary appears after signals are available
- Universe chips and candidate table scroll cleanly
- Fallback data is labeled when live option-chain data is unavailable
- No text overlap or page-wide horizontal overflow on mobile
