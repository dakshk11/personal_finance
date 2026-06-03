from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.entities import User
from app.schemas.common import SmartCandleBacktestOut, SmartCandleBacktestRequest, SmartCandleScanOut, SmartCandleScanRequest
from app.services.smart_candles import run_smart_candle_backtest, run_smart_candle_scan


router = APIRouter(prefix="/smart-candles", tags=["smart-candles"])


@router.post("/scan", response_model=SmartCandleScanOut)
def scan(
    payload: SmartCandleScanRequest | None = None,
    force: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SmartCandleScanOut:
    del user
    return SmartCandleScanOut(**run_smart_candle_scan(db, payload, force=force))


@router.post("/backtest", response_model=SmartCandleBacktestOut)
def backtest(
    payload: SmartCandleBacktestRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SmartCandleBacktestOut:
    del user
    return SmartCandleBacktestOut(**run_smart_candle_backtest(db, payload))
