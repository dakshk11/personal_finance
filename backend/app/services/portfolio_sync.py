from __future__ import annotations

from base64 import b64encode, urlsafe_b64encode
from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac
import json
import time
from typing import Any
import urllib.parse
import urllib.request

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import PortfolioSyncCredential, PortfolioSyncProviderCredential, PortfolioSyncSnapshot, utc_now
from app.schemas.common import (
    PortfolioAnalyzerHoldingIn,
    PortfolioSyncAccountOut,
    PortfolioSyncConnectOut,
    PortfolioSyncHoldingOut,
    PortfolioSyncProviderCredentialOut,
    PortfolioSyncSectorExposureOut,
    PortfolioSyncStatusOut,
    PortfolioSyncSummaryOut,
)
from app.services.index_data import INDEX_DEFINITIONS
from app.services.market_data import normalize_symbol
from app.services.portfolio_analysis import analyze_portfolio_holdings


PROVIDER = "snaptrade"
SINGLE_POSITION_WARNING_WEIGHT = 0.10
SECTOR_WARNING_WEIGHT = 0.25
ETF_SECTORS = {
    "SPY": "Broad Market ETF",
    "QQQ": "Growth ETF",
    "SMH": "Semiconductors ETF",
    "XLE": "Energy ETF",
    "XLI": "Industrials ETF",
    "UPRO": "Leveraged Broad Market ETF",
    "TQQQ": "Leveraged Growth ETF",
    "SOXL": "Leveraged Semiconductors ETF",
}


class PortfolioSyncConfigurationError(RuntimeError):
    pass


class PortfolioSyncProviderError(RuntimeError):
    def __init__(self, message: str, status_code: int = 502) -> None:
        super().__init__(message)
        self.status_code = status_code


@dataclass(frozen=True)
class ProviderCredentials:
    client_id: str
    consumer_key: str
    source: str
    consumer_key_fingerprint: str | None = None
    updated_at: datetime | None = None


def provider_configured(db: Session | None = None, user_id: int | None = None) -> bool:
    return _provider_credentials(db, user_id) is not None


def snaptrade_user_id(user_id: int) -> str:
    return f"directindex-user-{user_id}"


def get_status(db: Session, user_id: int) -> PortfolioSyncStatusOut:
    snapshot = _snapshot_for_user(db, user_id)
    credential = _credential_for_user(db, user_id)
    provider_credentials = _provider_credentials(db, user_id)
    accounts = _json_load(snapshot.accounts_json, []) if snapshot else []
    holdings = _json_load(snapshot.holdings_json, []) if snapshot else []
    warnings = _json_load(snapshot.warnings_json, []) if snapshot else []
    if not provider_credentials:
        warnings = _unique(
            [
                "SnapTrade is not configured. Save SnapTrade credentials in Portfolio Sync setup or set SNAPTRADE_CLIENT_ID and SNAPTRADE_CONSUMER_KEY on the backend.",
                *warnings,
            ]
        )
    return PortfolioSyncStatusOut(
        provider=PROVIDER,
        configured=provider_credentials is not None,
        connected=credential is not None,
        account_count=len(accounts),
        holding_count=len(holdings),
        last_synced_at=snapshot.synced_at if snapshot else None,
        warnings=warnings,
    )


def create_connection_redirect(
    db: Session,
    user_id: int,
    *,
    client: Any | None = None,
    custom_redirect: str | None = None,
) -> PortfolioSyncConnectOut:
    provider_credentials = _provider_credentials(db, user_id)
    if not provider_credentials:
        raise PortfolioSyncConfigurationError("SnapTrade is not configured. Save SnapTrade credentials in Portfolio Sync setup or add SNAPTRADE_CLIENT_ID and SNAPTRADE_CONSUMER_KEY before connecting a brokerage.")

    credential, user_secret = _get_or_register_credential(db, user_id, client=client, provider_credentials=provider_credentials)
    snaptrade = client or _snaptrade_client(provider_credentials)
    redirect = custom_redirect or f"{get_settings().frontend_origin.rstrip('/')}/ai-advisor"
    login_body = _response_body(
        snaptrade.authentication.login_snap_trade_user(
            user_id=credential.provider_user_id,
            user_secret=user_secret,
            custom_redirect=redirect,
        )
    )
    redirect_url = _string(
        _first(
            login_body,
            (
                "redirectURI",
                "redirect_uri",
                "redirectUrl",
                "redirect_url",
                "url",
                "loginRedirectUrl",
            ),
        )
    )
    if not redirect_url:
        raise PortfolioSyncProviderError("SnapTrade did not return a brokerage connection URL.")
    return PortfolioSyncConnectOut(
        provider=PROVIDER,
        configured=True,
        connected=True,
        redirect_url=redirect_url,
        provider_user_id=credential.provider_user_id,
        warnings=[],
    )


def list_connections(db: Session, user_id: int, *, client: Any | None = None) -> list[PortfolioSyncAccountOut]:
    credential = _credential_for_user(db, user_id)
    provider_credentials = _provider_credentials(db, user_id)
    if not provider_credentials or not credential:
        snapshot = _snapshot_for_user(db, user_id)
        return [PortfolioSyncAccountOut(**item) for item in _json_load(snapshot.accounts_json, [])] if snapshot else []

    user_secret = _decrypt_secret(credential.encrypted_user_secret)
    snaptrade = client or _snaptrade_client(provider_credentials)
    accounts = _fetch_accounts(snaptrade, credential.provider_user_id, user_secret)
    if accounts:
        return accounts
    snapshot = _snapshot_for_user(db, user_id)
    return [PortfolioSyncAccountOut(**item) for item in _json_load(snapshot.accounts_json, [])] if snapshot else []


def sync_portfolio(db: Session, user_id: int, *, client: Any | None = None) -> PortfolioSyncSummaryOut:
    provider_credentials = _provider_credentials(db, user_id)
    if not provider_credentials:
        raise PortfolioSyncConfigurationError("SnapTrade is not configured. Save SnapTrade credentials in Portfolio Sync setup or add SNAPTRADE_CLIENT_ID and SNAPTRADE_CONSUMER_KEY before syncing holdings.")

    credential = _credential_for_user(db, user_id)
    if not credential:
        raise PortfolioSyncConfigurationError("Connect a brokerage before running a portfolio sync.")

    user_secret = _decrypt_secret(credential.encrypted_user_secret)
    snaptrade = client or _snaptrade_client(provider_credentials)
    accounts = _fetch_accounts(snaptrade, credential.provider_user_id, user_secret)
    holdings_body = _fetch_holdings(snaptrade, credential.provider_user_id, user_secret, accounts)
    holdings, warnings = _normalize_holdings(holdings_body, accounts)

    if not accounts:
        accounts = _accounts_from_holdings(holdings)
    if not holdings:
        warnings.append("SnapTrade returned no holdings for connected accounts.")

    snapshot = _snapshot_for_user(db, user_id)
    now = utc_now()
    if snapshot:
        snapshot.accounts_json = _json_dump([account.model_dump() for account in accounts])
        snapshot.holdings_json = _json_dump(holdings)
        snapshot.warnings_json = _json_dump(_unique(warnings))
        snapshot.synced_at = now
    else:
        snapshot = PortfolioSyncSnapshot(
            user_id=user_id,
            provider=PROVIDER,
            accounts_json=_json_dump([account.model_dump() for account in accounts]),
            holdings_json=_json_dump(holdings),
            warnings_json=_json_dump(_unique(warnings)),
            synced_at=now,
        )
        db.add(snapshot)
    db.commit()
    db.refresh(snapshot)
    return build_summary(db, user_id, snapshot=snapshot)


def get_summary(db: Session, user_id: int) -> PortfolioSyncSummaryOut:
    return build_summary(db, user_id, snapshot=_snapshot_for_user(db, user_id))


def get_provider_credential_status(db: Session, user_id: int) -> PortfolioSyncProviderCredentialOut:
    credentials = _provider_credentials(db, user_id)
    if credentials:
        return PortfolioSyncProviderCredentialOut(
            provider=PROVIDER,
            configured=True,
            source=credentials.source,
            client_id=credentials.client_id,
            consumer_key_fingerprint=credentials.consumer_key_fingerprint,
            updated_at=credentials.updated_at,
            warnings=[],
        )
    return PortfolioSyncProviderCredentialOut(
        provider=PROVIDER,
        configured=False,
        source="none",
        warnings=[
            "Save SnapTrade credentials in Portfolio Sync setup or configure SNAPTRADE_CLIENT_ID and SNAPTRADE_CONSUMER_KEY on the backend.",
        ],
    )


def save_provider_credentials(
    db: Session,
    user_id: int,
    *,
    client_id: str,
    consumer_key: str,
) -> PortfolioSyncProviderCredentialOut:
    normalized_client_id = client_id.strip()
    normalized_consumer_key = consumer_key.strip()
    if not normalized_client_id or not normalized_consumer_key:
        raise PortfolioSyncConfigurationError("Enter both SnapTrade client id and consumer key.")

    credential = _provider_credential_for_user(db, user_id)
    encrypted_consumer_key = _encrypt_secret(normalized_consumer_key)
    fingerprint = _secret_fingerprint(normalized_consumer_key)
    if credential:
        credential.client_id = normalized_client_id
        credential.encrypted_consumer_key = encrypted_consumer_key
        credential.consumer_key_fingerprint = fingerprint
        credential.updated_at = utc_now()
    else:
        credential = PortfolioSyncProviderCredential(
            user_id=user_id,
            provider=PROVIDER,
            client_id=normalized_client_id,
            encrypted_consumer_key=encrypted_consumer_key,
            consumer_key_fingerprint=fingerprint,
        )
        db.add(credential)

    _clear_snaptrade_user_state(db, user_id)
    db.commit()
    db.refresh(credential)
    return get_provider_credential_status(db, user_id)


def delete_provider_credentials(db: Session, user_id: int) -> PortfolioSyncProviderCredentialOut:
    credential = _provider_credential_for_user(db, user_id)
    if credential:
        db.delete(credential)
        _clear_snaptrade_user_state(db, user_id)
        db.commit()
    return get_provider_credential_status(db, user_id)


def build_summary(
    db: Session,
    user_id: int,
    *,
    snapshot: PortfolioSyncSnapshot | None,
) -> PortfolioSyncSummaryOut:
    status = get_status(db, user_id)
    if not snapshot:
        return PortfolioSyncSummaryOut(
            status=status,
            synced_at=None,
            warnings=_unique([*status.warnings, "No synced brokerage snapshot is available yet."]),
        )

    accounts = [PortfolioSyncAccountOut(**item) for item in _json_load(snapshot.accounts_json, [])]
    raw_holdings = _json_load(snapshot.holdings_json, [])
    snapshot_warnings = _json_load(snapshot.warnings_json, [])
    analyzer_holdings = [
        PortfolioAnalyzerHoldingIn(
            symbol=str(holding["symbol"]),
            shares=float(holding["shares"]),
            cost_basis_per_share=float(holding.get("cost_basis_per_share") or 0),
        )
        for holding in raw_holdings
        if _number(holding.get("shares")) > 0 and str(holding.get("symbol") or "").strip()
    ]
    analysis = analyze_portfolio_holdings(db, analyzer_holdings, min_weight_percent=0) if analyzer_holdings else None
    analysis_by_symbol = {holding.symbol: holding for holding in analysis.holdings} if analysis else {}

    enriched: list[PortfolioSyncHoldingOut] = []
    for raw in raw_holdings:
        symbol = normalize_symbol(str(raw.get("symbol") or ""))
        if not symbol:
            continue
        shares = _number(raw.get("shares"))
        cost_basis = _number(raw.get("cost_basis"))
        cost_basis_per_share = _number(raw.get("cost_basis_per_share"))
        if cost_basis <= 0 and cost_basis_per_share > 0:
            cost_basis = cost_basis_per_share * shares
        if cost_basis_per_share <= 0 and shares > 0 and cost_basis > 0:
            cost_basis_per_share = cost_basis / shares

        analyzed = analysis_by_symbol.get(symbol)
        price = analyzed.price if analyzed else _number(raw.get("price"))
        market_value = shares * price if price > 0 else _number(raw.get("market_value"))
        total_market_value = analysis.total_market_value if analysis else sum(_number(item.get("market_value")) for item in raw_holdings)
        weight = market_value / total_market_value if total_market_value > 0 else 0
        unrealized = market_value - cost_basis
        warning = raw.get("warning")
        if not warning and cost_basis <= 0:
            warning = "Cost basis missing from provider; gain/loss may be understated."
        enriched.append(
            PortfolioSyncHoldingOut(
                symbol=symbol,
                shares=round(shares, 6),
                price=round(price, 4),
                market_value=round(market_value, 2),
                weight=round(weight, 6),
                cost_basis_per_share=round(cost_basis_per_share, 4),
                cost_basis=round(cost_basis, 2),
                unrealized_gain_loss=round(unrealized, 2),
                unrealized_gain_loss_pct=round(unrealized / cost_basis, 6) if cost_basis > 0 else 0,
                account_id=_string(raw.get("account_id")) or None,
                account_name=_string(raw.get("account_name")) or "Brokerage account",
                brokerage_name=_string(raw.get("brokerage_name")) or "Connected brokerage",
                sector=_sector_for_symbol(symbol),
                data_source=analyzed.data_source if analyzed else "snaptrade holdings snapshot",
                provider_symbol_id=_string(raw.get("provider_symbol_id")) or None,
                provider_updated_at=_parse_datetime(raw.get("provider_updated_at")),
                warning=_string(warning) or None,
            )
        )

    enriched.sort(key=lambda item: item.market_value, reverse=True)
    total_market_value = round(sum(item.market_value for item in enriched), 2)
    total_cost_basis = round(sum(item.cost_basis for item in enriched), 2)
    unrealized_gain_loss = round(total_market_value - total_cost_basis, 2)
    sector_exposures = _sector_exposures(enriched, total_market_value)
    concentration_warnings = _concentration_warnings(enriched, sector_exposures)
    analysis_warnings = analysis.warnings if analysis else []

    return PortfolioSyncSummaryOut(
        status=get_status(db, user_id),
        synced_at=snapshot.synced_at,
        total_market_value=total_market_value,
        total_cost_basis=total_cost_basis,
        unrealized_gain_loss=unrealized_gain_loss,
        unrealized_gain_loss_pct=round(unrealized_gain_loss / total_cost_basis, 6) if total_cost_basis > 0 else 0,
        account_count=len(accounts),
        holding_count=len(enriched),
        accounts=accounts,
        holdings=enriched,
        top_holdings=enriched[:8],
        sector_exposures=sector_exposures,
        concentration_warnings=concentration_warnings,
        warnings=_unique([*snapshot_warnings, *analysis_warnings, *concentration_warnings]),
    )


def _get_or_register_credential(
    db: Session,
    user_id: int,
    *,
    client: Any | None,
    provider_credentials: ProviderCredentials,
) -> tuple[PortfolioSyncCredential, str]:
    credential = _credential_for_user(db, user_id)
    if credential:
        return credential, _decrypt_secret(credential.encrypted_user_secret)

    snaptrade = client or _snaptrade_client(provider_credentials)
    provider_user_id = snaptrade_user_id(user_id)
    try:
        body = _response_body(snaptrade.authentication.register_snap_trade_user(user_id=provider_user_id))
    except Exception as exc:
        if _is_snaptrade_user_exists_error(exc):
            # User exists on SnapTrade but local DB has no record (e.g. after a DB reset).
            # SnapTrade's delete is asynchronous — it queues the deletion and fires a
            # USER_DELETED webhook when done.  Re-registering immediately hits 1012 again.
            # Trigger the delete via a direct signed HTTP call (bypasses SDK auth quirks),
            # then ask the user to retry in a few seconds.
            _delete_snaptrade_user_direct(provider_user_id, provider_credentials)
            raise PortfolioSyncProviderError(
                "A stale SnapTrade session was found (this happens after a database reset). "
                "The old session has been queued for removal. "
                "Please wait a few seconds and click 'Connect brokerage' again.",
                status_code=409,
            )
        else:
            raise PortfolioSyncProviderError(f"SnapTrade user registration failed: {exc}") from exc
    user_secret = _string(_first(body, ("userSecret", "user_secret", "secret")))
    if not user_secret:
        raise PortfolioSyncProviderError("SnapTrade did not return a user secret.")
    credential = PortfolioSyncCredential(
        user_id=user_id,
        provider=PROVIDER,
        provider_user_id=provider_user_id,
        encrypted_user_secret=_encrypt_secret(user_secret),
        user_secret_fingerprint=_secret_fingerprint(user_secret),
    )
    db.add(credential)
    db.commit()
    db.refresh(credential)
    return credential, user_secret


def _fetch_accounts(snaptrade: Any, user_id: str, user_secret: str) -> list[PortfolioSyncAccountOut]:
    accounts: list[PortfolioSyncAccountOut] = []
    seen: set[str] = set()
    connections = getattr(snaptrade, "connections", None)
    authorizations: list[Any] = []
    if connections and hasattr(connections, "list_brokerage_authorizations"):
        body = _response_body(connections.list_brokerage_authorizations(user_id=user_id, user_secret=user_secret))
        authorizations = list(_iter_items(body, ("authorizations", "brokerage_authorizations", "data")))

    for authorization in authorizations:
        auth_data = _as_dict(authorization)
        auth_id = _string(_first(auth_data, ("id", "authorization_id", "brokerage_authorization_id")))
        if connections and auth_id and hasattr(connections, "list_brokerage_authorization_accounts"):
            body = _response_body(
                connections.list_brokerage_authorization_accounts(
                    authorization_id=auth_id,
                    user_id=user_id,
                    user_secret=user_secret,
                )
            )
            for account in _iter_items(body, ("accounts", "data")):
                merged = {**_as_dict(account), "authorization_id": auth_id}
                normalized = _normalize_account(merged, authorization=auth_data)
                if normalized.account_id in seen:
                    continue
                seen.add(normalized.account_id)
                accounts.append(normalized)
        elif auth_id:
            normalized = _normalize_account(auth_data, authorization=auth_data)
            if normalized.account_id not in seen:
                seen.add(normalized.account_id)
                accounts.append(normalized)
    if accounts:
        return accounts

    account_info = getattr(snaptrade, "account_information", None)
    if account_info and hasattr(account_info, "list_user_accounts"):
        body = _response_body(account_info.list_user_accounts(user_id=user_id, user_secret=user_secret))
        for account in _iter_items(body, ("accounts", "data")):
            normalized = _normalize_account(account)
            if normalized.account_id in seen:
                continue
            seen.add(normalized.account_id)
            accounts.append(normalized)
    return accounts


def _fetch_holdings(
    snaptrade: Any,
    user_id: str,
    user_secret: str,
    accounts: list[PortfolioSyncAccountOut],
) -> Any:
    account_info = getattr(snaptrade, "account_information", None)
    if not account_info:
        raise PortfolioSyncProviderError("SnapTrade account information client is unavailable.")
    if not hasattr(account_info, "get_user_account_positions"):
        raise PortfolioSyncProviderError("SnapTrade account positions endpoint is unavailable in the installed SDK.")
    account_bodies: list[Any] = []
    for account in accounts:
        account_id = _string(account.account_id)
        if not account_id:
            continue
        body = _response_body(
            account_info.get_user_account_positions(
                account_id=account_id,
                user_id=user_id,
                user_secret=user_secret,
            )
        )
        account_bodies.append(_positions_body_with_account_context(body, account))
    return account_bodies


def _positions_body_with_account_context(body: Any, account: PortfolioSyncAccountOut) -> dict[str, Any]:
    data = _plain(body)
    account_context = account.model_dump()
    if isinstance(data, dict):
        if not _first(data, ("account", "account_details", "brokerage_account")):
            data = {"account": account_context, **data}
        return data
    if isinstance(data, list):
        return {"account": account_context, "positions": data}
    return {"account": account_context, "positions": []}


def _normalize_account(raw: Any, authorization: dict[str, Any] | None = None) -> PortfolioSyncAccountOut:
    data = _as_dict(raw)
    auth = authorization or {}
    account_id = _string(_first(data, ("id", "account_id", "accountId", "number", "mask"))) or "connected-account"
    brokerage_name = (
        _string(
            _first(
                data,
                (
                    "brokerage_name",
                    "brokerageName",
                    "institution_name",
                    "institutionName",
                    "institution",
                    "brokerage",
                    "meta.brokerage_name",
                    "authorization.brokerage.name",
                ),
            )
        )
        or _string(_first(auth, ("brokerage_name", "brokerage.name", "institution_name", "name")))
        or "Connected brokerage"
    )
    return PortfolioSyncAccountOut(
        account_id=account_id,
        account_name=_string(_first(data, ("name", "account_name", "accountName", "nickname", "number", "mask"))) or "Brokerage account",
        brokerage_name=brokerage_name,
        authorization_id=_string(_first(data, ("authorization_id", "brokerage_authorization_id"))) or _string(_first(auth, ("id", "authorization_id"))),
        account_type=_string(_first(data, ("type", "account_type", "accountType"))) or None,
        status=_string(_first(data, ("status", "disabled", "sync_status", "syncStatus"))) or None,
        raw=_as_dict(raw),
    )


def _normalize_holdings(raw_body: Any, accounts: list[PortfolioSyncAccountOut]) -> tuple[list[dict[str, Any]], list[str]]:
    accounts_by_id = {account.account_id: account for account in accounts}
    warnings: list[str] = []
    rows: list[dict[str, Any]] = []

    def add_holding(raw_holding: Any, account_context: dict[str, Any] | None = None) -> None:
        normalized = _normalize_holding(raw_holding, accounts_by_id, account_context or {})
        if not normalized:
            return
        if normalized.get("warning"):
            warnings.append(f"{normalized['symbol']}: {normalized['warning']}")
        rows.append(normalized)

    for item in _iter_items(raw_body, ("accounts", "holdings", "positions", "data")):
        data = _as_dict(item)
        nested = _first(data, ("holdings", "positions", "securities"))
        if isinstance(nested, list):
            account_context = _as_dict(_first(data, ("account", "brokerage_account", "account_details")) or data)
            for holding in nested:
                add_holding(holding, account_context)
            continue
        add_holding(data, None)

    return rows, _unique(warnings)


def _normalize_holding(
    raw: Any,
    accounts_by_id: dict[str, PortfolioSyncAccountOut],
    account_context: dict[str, Any],
) -> dict[str, Any] | None:
    data = _as_dict(raw)
    symbol = _holding_symbol(data)
    if not symbol:
        return None
    shares = _number(_first(data, ("shares", "quantity", "units", "position.quantity", "position.units", "balance")))
    if shares <= 0:
        return None
    market_value = _number(_first(data, ("market_value", "marketValue", "value", "current_value", "currentValue")))
    price = _number(_first(data, ("price", "last_price", "lastPrice", "market_price", "marketPrice", "trade_price", "quote.price")))
    if price <= 0 and market_value > 0:
        price = market_value / shares
    if market_value <= 0 and price > 0:
        market_value = shares * price

    cost_basis = _number(_first(data, ("cost_basis", "costBasis", "book_value", "bookValue", "total_cost", "totalCost")))
    cost_basis_per_share = _number(
        _first(
            data,
            (
                "cost_basis_per_share",
                "costBasisPerShare",
                "average_purchase_price",
                "averagePurchasePrice",
                "average_cost",
                "averageCost",
                "avg_price",
                "avgPrice",
            ),
        )
    )
    if cost_basis <= 0 and cost_basis_per_share > 0:
        cost_basis = cost_basis_per_share * shares
    if cost_basis_per_share <= 0 and cost_basis > 0:
        cost_basis_per_share = cost_basis / shares

    account_id = (
        _string(_first(data, ("account_id", "accountId", "account.id", "account.number")))
        or _string(_first(account_context, ("id", "account_id", "accountId", "number", "mask")))
        or "connected-account"
    )
    account = accounts_by_id.get(account_id)
    account_name = (
        _string(_first(data, ("account_name", "accountName", "account.name")))
        or _string(_first(account_context, ("name", "account_name", "accountName", "nickname", "number", "mask")))
        or (account.account_name if account else "")
        or "Brokerage account"
    )
    brokerage_name = (
        _string(_first(data, ("brokerage_name", "brokerageName", "account.brokerage_name", "account.institution_name")))
        or _string(_first(account_context, ("brokerage_name", "brokerageName", "institution_name", "institutionName", "brokerage")))
        or (account.brokerage_name if account else "")
        or "Connected brokerage"
    )
    warning = ""
    if cost_basis <= 0:
        warning = "Cost basis missing from provider; gain/loss may be understated."
    return {
        "symbol": symbol,
        "shares": round(shares, 6),
        "price": round(price, 4),
        "market_value": round(market_value, 2),
        "cost_basis_per_share": round(cost_basis_per_share, 4),
        "cost_basis": round(cost_basis, 2),
        "unrealized_gain_loss": round(market_value - cost_basis, 2),
        "account_id": account_id,
        "account_name": account_name,
        "brokerage_name": brokerage_name,
        "data_source": "snaptrade",
        "provider_symbol_id": _string(_first(data, ("symbol.id", "universal_symbol.id", "instrument.id", "security.id"))) or None,
        "provider_updated_at": _string(_first(data, ("updated_at", "updatedAt", "as_of_date", "asOfDate"))) or None,
        "warning": warning or None,
    }


def _holding_symbol(data: dict[str, Any]) -> str:
    direct = _first(
        data,
        (
            "symbol",
            "ticker",
            "symbol.symbol",
            "symbol.ticker",
            "symbol.raw_symbol",
            "universal_symbol.symbol",
            "universal_symbol.ticker",
            "universal_symbol.raw_symbol",
            "instrument.symbol",
            "security.symbol",
        ),
    )
    if isinstance(direct, dict):
        direct = _first(direct, ("symbol", "ticker", "raw_symbol"))
    symbol = normalize_symbol(str(direct or ""))
    return "" if symbol in {"", "CASH", "USD", "US DOLLAR"} else symbol


def _accounts_from_holdings(holdings: list[dict[str, Any]]) -> list[PortfolioSyncAccountOut]:
    accounts: dict[str, PortfolioSyncAccountOut] = {}
    for holding in holdings:
        account_id = str(holding.get("account_id") or "connected-account")
        if account_id in accounts:
            continue
        accounts[account_id] = PortfolioSyncAccountOut(
            account_id=account_id,
            account_name=str(holding.get("account_name") or "Brokerage account"),
            brokerage_name=str(holding.get("brokerage_name") or "Connected brokerage"),
            status="synced",
            raw={},
        )
    return list(accounts.values())


def _sector_exposures(holdings: list[PortfolioSyncHoldingOut], total_market_value: float) -> list[PortfolioSyncSectorExposureOut]:
    grouped: dict[str, dict[str, float | int]] = {}
    for holding in holdings:
        sector = holding.sector or "Unknown"
        bucket = grouped.setdefault(sector, {"market_value": 0.0, "holding_count": 0})
        bucket["market_value"] = float(bucket["market_value"]) + holding.market_value
        bucket["holding_count"] = int(bucket["holding_count"]) + 1
    rows = [
        PortfolioSyncSectorExposureOut(
            sector=sector,
            market_value=round(float(values["market_value"]), 2),
            weight=round(float(values["market_value"]) / total_market_value, 6) if total_market_value > 0 else 0,
            holding_count=int(values["holding_count"]),
        )
        for sector, values in grouped.items()
    ]
    return sorted(rows, key=lambda row: row.market_value, reverse=True)


def _concentration_warnings(
    holdings: list[PortfolioSyncHoldingOut],
    sector_exposures: list[PortfolioSyncSectorExposureOut],
) -> list[str]:
    warnings: list[str] = []
    for holding in holdings:
        if holding.weight > SINGLE_POSITION_WARNING_WEIGHT:
            warnings.append(f"{holding.symbol} is {holding.weight:.1%} of synced market value; review single-position concentration above 10%.")
    for sector in sector_exposures:
        if sector.weight > SECTOR_WARNING_WEIGHT:
            warnings.append(f"{sector.sector} is {sector.weight:.1%} of synced market value; review sector concentration above 25%.")
    return warnings


def _credential_for_user(db: Session, user_id: int) -> PortfolioSyncCredential | None:
    return db.scalar(select(PortfolioSyncCredential).where(PortfolioSyncCredential.user_id == user_id))


def _provider_credential_for_user(db: Session, user_id: int) -> PortfolioSyncProviderCredential | None:
    return db.scalar(select(PortfolioSyncProviderCredential).where(PortfolioSyncProviderCredential.user_id == user_id))


def _snapshot_for_user(db: Session, user_id: int) -> PortfolioSyncSnapshot | None:
    return db.scalar(select(PortfolioSyncSnapshot).where(PortfolioSyncSnapshot.user_id == user_id))


def _provider_credentials(db: Session | None = None, user_id: int | None = None) -> ProviderCredentials | None:
    env_credentials = _env_provider_credentials()
    if env_credentials:
        return env_credentials
    if db is None or user_id is None:
        return None
    stored = _provider_credential_for_user(db, user_id)
    if not stored:
        return None
    return ProviderCredentials(
        client_id=stored.client_id,
        consumer_key=_decrypt_secret(stored.encrypted_consumer_key, "Stored SnapTrade consumer key"),
        source="database",
        consumer_key_fingerprint=stored.consumer_key_fingerprint,
        updated_at=stored.updated_at,
    )


def _env_provider_credentials() -> ProviderCredentials | None:
    settings = get_settings()
    client_id = settings.snaptrade_client_id.strip()
    consumer_key = settings.snaptrade_consumer_key.strip()
    if not client_id or not consumer_key:
        return None
    return ProviderCredentials(
        client_id=client_id,
        consumer_key=consumer_key,
        source="environment",
        consumer_key_fingerprint=_secret_fingerprint(consumer_key),
    )


def _clear_snaptrade_user_state(db: Session, user_id: int) -> None:
    credential = _credential_for_user(db, user_id)
    if credential:
        db.delete(credential)
    snapshot = _snapshot_for_user(db, user_id)
    if snapshot:
        db.delete(snapshot)


def _snaptrade_client(credentials: ProviderCredentials | None = None) -> Any:
    try:
        from snaptrade_client import SnapTrade
    except Exception as exc:
        raise PortfolioSyncConfigurationError("Install snaptrade-python-sdk==11.0.190 to enable brokerage sync.") from exc
    provider_credentials = credentials or _env_provider_credentials()
    if not provider_credentials:
        raise PortfolioSyncConfigurationError("SnapTrade is not configured. Save SnapTrade credentials in Portfolio Sync setup or add backend environment credentials.")
    return SnapTrade(client_id=provider_credentials.client_id, consumer_key=provider_credentials.consumer_key)


def _delete_snaptrade_user_direct(user_id: str, provider_credentials: ProviderCredentials) -> None:
    """Delete a SnapTrade user via a direct signed HTTP request.

    The SDK's delete_snap_trade_user has auth-parameter ordering issues that produce
    a 401/1083 on some SDK versions.  This replicates SnapTrade's exact signing scheme
    (same logic as snaptrade_client/request_after_hook.py) without the SDK middleware.
    """
    timestamp = int(time.time())
    query = urllib.parse.urlencode({
        "userId": user_id,
        "clientId": provider_credentials.client_id,
        "timestamp": timestamp,
    })
    path = "/snapTrade/deleteUser"
    sig_object = {"content": None, "path": f"/api/v1{path}", "query": query}
    sig_content = json.dumps(sig_object, separators=(",", ":"), sort_keys=True)
    sig_digest = hmac.new(
        provider_credentials.consumer_key.encode(),
        sig_content.encode(),
        hashlib.sha256,
    ).digest()
    signature = b64encode(sig_digest).decode()

    url = f"https://api.snaptrade.com/api/v1{path}?{query}"
    req = urllib.request.Request(url, method="DELETE")
    req.add_header("Signature", signature)
    try:
        with urllib.request.urlopen(req, timeout=10):
            pass
    except Exception:
        # Best-effort: if the delete fails (e.g. user already gone), silently continue.
        pass


def _is_snaptrade_user_exists_error(exc: Exception) -> bool:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        return str(body.get("code", "")) == "1012"
    if isinstance(body, str):
        return "1012" in body
    return False


def _encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("utf-8")


def _decrypt_secret(ciphertext: str, description: str = "Stored SnapTrade user secret") -> str:
    try:
        return _fernet().decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise PortfolioSyncConfigurationError(f"{description} could not be decrypted.") from exc


def _secret_fingerprint(value: str) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()
    return f"sha256:{digest[:16]}"


def _fernet() -> Fernet:
    secret = get_settings().broker_sync_encryption_secret.strip()
    if len(secret) < 32:
        raise PortfolioSyncConfigurationError("Broker sync encryption secret must be at least 32 characters.")
    key = urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def _sector_for_symbol(symbol: str) -> str:
    normalized = normalize_symbol(symbol)
    if normalized in ETF_SECTORS:
        return ETF_SECTORS[normalized]
    for definition in INDEX_DEFINITIONS.values():
        for holding in definition.holdings:
            if normalize_symbol(str(holding["symbol"])) == normalized:
                return str(holding.get("sector") or "Unknown")
    return "Unknown"


def _response_body(response: Any) -> Any:
    return _plain(getattr(response, "body", response))


def _iter_items(value: Any, keys: tuple[str, ...]) -> list[Any]:
    plain = _plain(value)
    if isinstance(plain, list):
        return plain
    if isinstance(plain, dict):
        for key in keys:
            candidate = plain.get(key)
            if isinstance(candidate, list):
                return candidate
        return [plain]
    return []


def _plain(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _plain(to_dict())
    if hasattr(value, "__dict__"):
        return {key: _plain(item) for key, item in vars(value).items() if not key.startswith("_")}
    return value


def _as_dict(value: Any) -> dict[str, Any]:
    plain = _plain(value)
    return plain if isinstance(plain, dict) else {}


def _first(source: Any, paths: tuple[str, ...]) -> Any:
    data = _plain(source)
    for path in paths:
        current = data
        found = True
        for key in path.split("."):
            if isinstance(current, dict) and key in current:
                current = current[key]
            else:
                found = False
                break
        if found and current not in (None, ""):
            return current
    return None


def _number(value: Any) -> float:
    try:
        if value in (None, ""):
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _string(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value).strip()


def _json_dump(value: Any) -> str:
    return json.dumps(value, default=str)


def _json_load(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    text = _string(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
