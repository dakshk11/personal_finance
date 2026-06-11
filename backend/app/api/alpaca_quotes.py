from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.core.config import get_settings
from app.db.session import get_db
from app.models.entities import AIAdvisorAlpacaKey, User
from app.services.ai_advisor import AIAdvisorConfigurationError, decrypt_api_key
from app.services.alpaca_recommendation_quotes import (
    ALPACA_MAX_EQUITY_SYMBOLS,
    build_quote_snapshot,
    create_quote_session,
    pop_quote_session,
    stream_alpaca_session,
)


router = APIRouter(tags=["alpaca-quotes"])


class AlpacaRecommendationQuoteSessionIn(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=60)
    include_options: bool = True
    stream_options: bool = True


_ACTIVE_USER_WEBSOCKETS: dict[int, WebSocket] = {}


@router.post("/alpaca/recommendation-quotes/session")
async def create_recommendation_quote_session(
    payload: AlpacaRecommendationQuoteSessionIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = db.scalar(select(AIAdvisorAlpacaKey).where(AIAdvisorAlpacaKey.user_id == user.id))
    if not row:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Save an Alpaca API key and secret before opening real-time quotes.")
    try:
        api_key = decrypt_api_key(row.encrypted_api_key, get_settings().ai_advisor_key_encryption_secret)
        api_secret = decrypt_api_key(row.encrypted_api_secret, get_settings().ai_advisor_key_encryption_secret)
    except AIAdvisorConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    try:
        return await create_quote_session(
            user_id=user.id,
            api_key=api_key,
            api_secret=api_secret,
            symbols=payload.symbols,
            include_options=payload.include_options,
            stream_options=payload.stream_options,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.post("/alpaca/recommendation-quotes/snapshot")
async def pull_recommendation_quote_snapshot(
    payload: AlpacaRecommendationQuoteSessionIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict:
    row = db.scalar(select(AIAdvisorAlpacaKey).where(AIAdvisorAlpacaKey.user_id == user.id))
    if not row:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Save an Alpaca API key and secret before pulling quotes.")
    try:
        api_key = decrypt_api_key(row.encrypted_api_key, get_settings().ai_advisor_key_encryption_secret)
        api_secret = decrypt_api_key(row.encrypted_api_secret, get_settings().ai_advisor_key_encryption_secret)
    except AIAdvisorConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    try:
        snapshot = await build_quote_snapshot(
            payload.symbols,
            include_options=payload.include_options,
            api_key=api_key,
            api_secret=api_secret,
        )
        return {"session_id": "", **snapshot}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.websocket("/ws/alpaca/recommendation-quotes")
async def recommendation_quote_websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    session_id = websocket.query_params.get("session_id", "")
    session = pop_quote_session(session_id)
    if not session:
        await websocket.send_json({"type": "status", "status": "error", "message": "Quote session expired. Open real-time quotes again from the Recommendation Agent."})
        await websocket.close(code=1008)
        return
    if len(session.symbols) > ALPACA_MAX_EQUITY_SYMBOLS:
        await websocket.send_json({"type": "status", "status": "error", "message": "Alpaca equities stream supports at most 30 symbols per connection."})
        await websocket.close(code=1008)
        return
    previous = _ACTIVE_USER_WEBSOCKETS.get(session.user_id)
    if previous and previous is not websocket:
        try:
            await previous.close(code=1000, reason="A newer Alpaca quote tab became active.")
        except Exception:
            pass
    _ACTIVE_USER_WEBSOCKETS[session.user_id] = websocket
    try:
        await stream_alpaca_session(session, websocket.send_json)
    except WebSocketDisconnect:
        return
    except Exception as exc:
        try:
            await websocket.send_json({"type": "status", "status": "error", "message": str(exc) or "Alpaca quote stream closed."})
        except Exception:
            pass
    finally:
        if _ACTIVE_USER_WEBSOCKETS.get(session.user_id) is websocket:
            _ACTIVE_USER_WEBSOCKETS.pop(session.user_id, None)
