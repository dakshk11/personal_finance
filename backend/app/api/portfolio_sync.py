from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.entities import User
from app.schemas.common import (
    PortfolioSyncAccountOut,
    PortfolioSyncConnectOut,
    PortfolioSyncProviderCredentialIn,
    PortfolioSyncProviderCredentialOut,
    PortfolioSyncStatusOut,
    PortfolioSyncSummaryOut,
)
from app.services.portfolio_sync import (
    PortfolioSyncConfigurationError,
    PortfolioSyncProviderError,
    create_connection_redirect,
    delete_provider_credentials,
    get_provider_credential_status,
    get_status,
    get_summary,
    list_connections,
    save_provider_credentials,
    sync_portfolio,
)


router = APIRouter(prefix="/portfolio-sync", tags=["portfolio-sync"])


@router.get("/status", response_model=PortfolioSyncStatusOut)
def portfolio_sync_status(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PortfolioSyncStatusOut:
    return get_status(db, user.id)


@router.get("/provider-credentials", response_model=PortfolioSyncProviderCredentialOut)
def provider_credential_status(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PortfolioSyncProviderCredentialOut:
    try:
        return get_provider_credential_status(db, user.id)
    except PortfolioSyncConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.put("/provider-credentials", response_model=PortfolioSyncProviderCredentialOut)
def store_provider_credentials(
    payload: PortfolioSyncProviderCredentialIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PortfolioSyncProviderCredentialOut:
    try:
        return save_provider_credentials(
            db,
            user.id,
            client_id=payload.client_id,
            consumer_key=payload.consumer_key,
        )
    except PortfolioSyncConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/provider-credentials", response_model=PortfolioSyncProviderCredentialOut)
def remove_provider_credentials(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PortfolioSyncProviderCredentialOut:
    try:
        return delete_provider_credentials(db, user.id)
    except PortfolioSyncConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.post("/connect", response_model=PortfolioSyncConnectOut)
def connect_brokerage(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PortfolioSyncConnectOut:
    try:
        return create_connection_redirect(db, user.id)
    except PortfolioSyncConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except PortfolioSyncProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/connections", response_model=list[PortfolioSyncAccountOut])
def brokerage_connections(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[PortfolioSyncAccountOut]:
    try:
        return list_connections(db, user.id)
    except PortfolioSyncConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except PortfolioSyncProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.post("/sync", response_model=PortfolioSyncSummaryOut)
def sync_brokerage_portfolio(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PortfolioSyncSummaryOut:
    try:
        return sync_portfolio(db, user.id)
    except PortfolioSyncConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc
    except PortfolioSyncProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc


@router.get("/summary", response_model=PortfolioSyncSummaryOut)
def portfolio_sync_summary(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> PortfolioSyncSummaryOut:
    return get_summary(db, user.id)
