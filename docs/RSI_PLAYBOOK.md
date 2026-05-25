# RSI Playbook

RSI Playbook lives at `/ai-advisor` under the **RSI Playbook** tab. It combines the Wheel Strategy universe with the latest Portfolio Sync holdings snapshot, computes RSI and EMA context from daily market history, and maps every symbol to the requested RSI action zones.

This is educational playbook output only. It does not place trades, size positions, rebalance accounts, move money, or provide personalized investment advice.

## Rules

| RSI level | Playbook action |
| --- | --- |
| `RSI 70+` | Go to cash |
| `RSI 55-65` | Sell puts far OTM |
| `RSI 45-55` | Sell puts ATM |
| `RSI 30-45` | Buy the stock |
| `RSI 30 and below` | Buy LEAP aggressively |

`RSI 65-70` is treated as a watch gap because the requested rules do not specify that band.

## Universe

The scan source is the de-duplicated union of:

- Wheel Strategy symbols from `/option-strategy/universe`
- Latest Portfolio Sync holdings snapshot, when available

If the same symbol appears in both, the UI labels both sources.

## API

Base path: `/rsi-playbook`

| Method | Path | Behavior |
| --- | --- | --- |
| `GET` | `/scan?force=false` | Builds the combined universe, fetches/caches daily market history, computes RSI/EMA context, and returns per-symbol playbook signals with chart rows. |

Useful query parameters:

- `force`: refresh provider market history when true
- `lookback_days`: default `420`, minimum `120`, maximum `1200`
- `max_symbols`: default `90`, maximum `120`

Each signal includes:

- `symbol`, `name`, `sector`, `sources`, `group`
- `price`, `as_of_date`, `data_source`
- `rsi`, `level`, `action`, `action_tone`, `summary`
- `ema8`, `ema21`, `ema55`, `trend`, `distance_to_ema21`
- `window_return_3m`
- `portfolio_weight` when present from Portfolio Sync
- `chart` rows with date, close, EMA 8, EMA 21, EMA 55, and RSI

## Frontend

The tab presents a compact signal cockpit:

- Top metrics by action zone
- Rule strip
- Filterable per-stock summary table
- Click-through detail panel with price + EMA chart and RSI chart
- Source labels for Wheel Strategy and Portfolio Sync
- Data notes when provider history falls back or is incomplete

The chart uses the same dense dark dashboard language as Wheel Strategy and Portfolio Sync, inspired by TradeGemini-style signal workbenches without copying the site.

## Tests

Focused backend tests:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests/test_rsi_playbook.py -q
```

Full checks:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q
cd frontend && npm run typecheck
```
