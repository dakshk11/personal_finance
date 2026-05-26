# Breakout Scanner

Breakout Scanner lives at `/ai-advisor` under the **Breakout Scanner** tab in FinanceOS Studio. It scans S&P 500 stocks only for educational breakout research setups. It does not place trades, create alerts at brokers, assign ratings, or provide investment advice.

## Universe And Data

- Universe: current public S&P 500 constituents, cached in the backend.
- Fallback: FinanceOS SPY holdings cache when the current public S&P 500 source is unavailable, labeled in API/UI warnings.
- Price data: breakout-specific OHLCV cache keyed by symbol/date, separate from the close-only `PriceBar` cache used elsewhere.
- Provider: yfinance daily OHLCV when available; deterministic fallback history is labeled when provider data is unavailable.

## Detectors

The scanner runs three built-in detectors with adjustable parameters:

- **Ceiling Breakout**: looks for a multi-touch resistance area, then ranks stocks that close above that ceiling with relative-volume confirmation.
- **Momentum Breakout**: looks for recent-high or 52-week-high pressure with positive recent returns, relative volume, and constructive moving-average context.
- **Near-Breakout Watch**: looks for stocks still below resistance but within the configured near-breakout band, with enough touches and volume buildup for review.

Shared filters include S&P 500 membership, minimum price, minimum average dollar volume, optional SMA 200 trend filter, relative volume, resistance-touch quality, and chart context.

## API

Base path: `/breakout-scanner`

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/universe` | Returns cached S&P 500 universe metadata, source, cache status, and warnings. |
| `POST` | `/scan?force=false` | Runs the enabled detectors and returns ranked breakout setups. |
| `POST` | `/backtest` | Runs one detector against historical OHLCV and returns 5/10/20/60 trading-day distribution stats. |

Scanner config fields:

- `detectors`
- `lookback_days`
- `min_relative_volume`
- `ideal_relative_volume`
- `min_ceiling_touches`
- `ceiling_tolerance_pct`
- `breakout_clearance_pct`
- `near_breakout_pct`
- `min_avg_dollar_volume`
- `require_above_sma200`
- `max_symbols`

Scan output includes symbol, company, sector, detector type, setup label, score, rank, price, resistance level, breakout/proximity percentages, touch count, relative volume, SMA values, trend label, summary, data source, warnings, and chart points.

Backtest output includes detector, evaluated years, signal count, config snapshot, and horizon rows with win rate, average return, median return, P10, and P90.

## UI

The tab uses the same dense Studio workbench language as Wheel Strategy and RSI Playbook:

- S&P 500 universe/source metrics
- detector cards
- adjustable parameter panel
- ranked setup table
- click-through chart with close, volume, SMA 20/50/200, and resistance
- Backtest Lab cards for forward-return distributions
- educational warning labels for provider fallback and survivorship-bias limits

## Tests

Backend tests cover S&P 500 fallback labeling, OHLCV cache reuse, ceiling/momentum/near-breakout detectors, volume/SMA filters, daily scan cache and force refresh, user-scoped scan runs, and backtest distribution calculations.

Frontend checks include `npm run typecheck` and browser QA on `/ai-advisor` desktop/mobile for tab visibility, chart rendering, table scrolling, Backtest Lab rendering, and no page-wide overflow.
