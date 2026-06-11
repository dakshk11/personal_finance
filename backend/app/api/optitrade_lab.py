from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import AIAdvisorAlpacaKey, User
from app.services.ai_advisor import AIAdvisorConfigurationError, decrypt_api_key
from app.services.optitrade_lab import (
    AlpacaMarketDataError,
    AlpacaRateLimitError,
    DEFAULT_OPTITRADE_SYMBOLS,
    build_alpaca_optitrade_backtest,
    build_alpaca_optitrade_signals,
)


router = APIRouter(prefix="/alpaca/optitrade-lab", tags=["alpaca-optitrade-lab"])


@router.get("/signals")
async def get_alpaca_optitrade_signals(
    symbols: str = Query(",".join(DEFAULT_OPTITRADE_SYMBOLS), description="Comma-separated OptiTrade symbols"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    api_key, api_secret = _alpaca_credentials(user, db)
    requested = [item.strip().upper() for item in symbols.split(",") if item.strip()]
    try:
        return await build_alpaca_optitrade_signals(api_key, api_secret, requested)
    except AlpacaRateLimitError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except AlpacaMarketDataError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@router.get("/backtest")
async def get_alpaca_optitrade_backtest(
    symbol: str = Query("TQQQ", description="Leveraged ETF symbol"),
    atr_multiplier: float = Query(2.5, ge=0.1, le=20),
    tp_mode: str = Query("multi", description="single, multi, or always_in"),
    stop_model: str = Query("atr", description="atr or swing"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    api_key, api_secret = _alpaca_credentials(user, db)
    try:
        return await build_alpaca_optitrade_backtest(
            api_key,
            api_secret,
            symbol,
            atr_multiplier=atr_multiplier,
            tp_mode=tp_mode,
            stop_model=stop_model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except AlpacaRateLimitError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except AlpacaMarketDataError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


def _alpaca_credentials(user: User, db: Session) -> tuple[str, str]:
    row = db.scalar(select(AIAdvisorAlpacaKey).where(AIAdvisorAlpacaKey.user_id == user.id))
    if not row:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Save an Alpaca API key and secret before using Alpaca OptiTrade Lab data.")
    try:
        return (
            decrypt_api_key(row.encrypted_api_key, get_settings().ai_advisor_key_encryption_secret),
            decrypt_api_key(row.encrypted_api_secret, get_settings().ai_advisor_key_encryption_secret),
        )
    except AIAdvisorConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
