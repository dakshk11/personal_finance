# Portfolio Sync

Portfolio Sync lives at `/ai-advisor` under the **Portfolio Sync** tab in FinanceOS Studio. It is a read-only brokerage sync workflow powered by SnapTrade. It is inspired by TradeGemini's portfolio spotlight, but implemented with FinanceOS's own data model, risk language, and Portfolio Analyzer valuation pipeline.

Portfolio Sync does not place trades, rebalance accounts, move money, or store broker login credentials. It stores only the SnapTrade provider identity, encrypted SnapTrade `userSecret`, connection/account metadata, and the latest synced holdings snapshot.

## Setup

Portfolio Sync supports two SnapTrade credential setup paths:

1. Local/browser setup: enter the SnapTrade client id and consumer key in the **Portfolio Sync** tab. The backend stores the client id plus an encrypted consumer key in the database. The plaintext consumer key is never returned after save.
2. Backend environment setup: set these variables for hosted or shared deployments:

```bash
SNAPTRADE_CLIENT_ID=
SNAPTRADE_CONSUMER_KEY=
BROKER_SYNC_ENCRYPTION_SECRET=replace-with-at-least-32-random-characters
```

Environment credentials take precedence when present. If neither environment credentials nor stored browser-entered credentials exist, `/portfolio-sync/status` returns `configured=false` and the frontend shows a setup-required state with credential input fields. It does not render fake connected accounts.

`BROKER_SYNC_ENCRYPTION_SECRET` encrypts stored SnapTrade provider consumer keys and SnapTrade user secrets before database storage. Use a long random value in every non-local environment.

Saving browser-entered provider credentials clears the existing SnapTrade `userSecret` and latest snapshot for that FinanceOS user so the next **Connect brokerage** flow uses the new app credentials. `BROKER_SYNC_ENCRYPTION_SECRET` remains backend-only and is not entered in the browser.

## Data Model

Portfolio Sync stores one SnapTrade identity per FinanceOS user:

- Optional encrypted SnapTrade app credential row for local/browser setup
- Provider user id: `directindex-user-{user.id}`
- Encrypted SnapTrade `userSecret`
- Provider/fingerprint metadata
- Latest account list snapshot
- Latest holdings snapshot
- Snapshot warnings and sync timestamp

The normalized holding shape is intentionally close to Portfolio Analyzer:

- `symbol`
- `shares`
- `cost_basis_per_share`
- `cost_basis`
- `market_value`
- `unrealized_gain_loss`
- `account_name`
- `brokerage_name`
- provider timestamp/source fields

## API

Base path: `/portfolio-sync`

| Method | Path | Behavior |
| --- | --- | --- |
| `GET` | `/status` | Returns provider configured state, connected state, account count, holding count, last sync time, and warnings. |
| `GET` | `/provider-credentials` | Returns whether SnapTrade provider credentials are configured by environment or database, plus safe metadata. |
| `PUT` | `/provider-credentials` | Stores browser-entered SnapTrade client id and encrypted consumer key, then clears stale SnapTrade user state. |
| `DELETE` | `/provider-credentials` | Removes stored provider credentials and clears SnapTrade user state for the current user. |
| `POST` | `/connect` | Registers the SnapTrade user if needed, stores the encrypted user secret, and returns a SnapTrade redirect URL. |
| `GET` | `/connections` | Lists connected brokerage accounts/authorizations when credentials and a user secret exist. |
| `POST` | `/sync` | Lists connected accounts, fetches each account's positions with SnapTrade `GET /api/v1/accounts/{accountId}/positions`, normalizes accounts and positions into holdings, persists the latest snapshot, and returns analytics. |
| `GET` | `/summary` | Returns the latest persisted holdings snapshot and analytics without calling SnapTrade. |

## Analytics

After syncing, FinanceOS reuses Portfolio Analyzer valuation logic for daily prices, weights, cost basis, and gain/loss review. The Portfolio Sync summary adds:

- Total market value
- Total cost basis
- Unrealized gain/loss
- Sector exposure using existing security/index metadata where available
- Top holdings by market value
- Missing cost-basis warnings
- Single-position concentration warnings above 10%
- Sector concentration warnings above 25%

The sync path intentionally avoids SnapTrade's deprecated aggregate `GET /api/v1/holdings` and account-specific `GET /api/v1/accounts/{accountId}/holdings` operations. It uses the finer-grained SDK method `account_information.get_user_account_positions(account_id=..., user_id=..., user_secret=...)` after account discovery.

## Frontend

The **Portfolio Sync** tab shows:

- Provider status, last sync, connected account count, and action buttons
- Setup-required state with browser-entered SnapTrade credential fields when provider credentials are missing
- Stored-credential status, fingerprint, update, and remove controls before brokerage connection
- Account cards by brokerage/account
- Market value, cost basis, gain/loss, accounts, and holdings metrics
- Compact sector mix
- Top holdings P/L
- Concentration and data-quality warnings
- Holdings table with symbol, broker/account, shares, price, value, weight, basis, P/L, and source

The manual `/portfolio` Portfolio Analyzer remains available for users who do not configure SnapTrade.

## Tests

Run the focused tests:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests/test_portfolio_sync.py -q
```

Run the full backend suite:

```bash
PYTHONPATH=backend backend/.venv/bin/python -m pytest backend/tests -q
```

Run frontend typecheck:

```bash
cd frontend
npm run typecheck
```

The Portfolio Sync tests mock SnapTrade and cover missing provider setup, encrypted browser-entered consumer-key storage, encrypted user-secret storage, redirect URL creation, stale state clearing after credential updates/deletes, multi-account holdings normalization, missing cost-basis warnings, concentration warnings, and persisted summary reads without provider calls.
