from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.entities import User
from app.schemas.common import BreakoutBacktestOut, BreakoutScanOut, BreakoutScannerBacktestRequest, BreakoutScannerConfigIn, BreakoutUniverseOut
from app.services.breakout_scanner import load_sp500_universe, run_breakout_backtest, run_breakout_scan


router = APIRouter(prefix="/breakout-scanner", tags=["breakout-scanner"])


@router.get("/universe", response_model=BreakoutUniverseOut)
def universe(
    force: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BreakoutUniverseOut:
    del user
    return BreakoutUniverseOut(**load_sp500_universe(db, force_refresh=force))


@router.post("/scan", response_model=BreakoutScanOut)
def scan(
    payload: BreakoutScannerConfigIn | None = None,
    force: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BreakoutScanOut:
    return BreakoutScanOut(**run_breakout_scan(db, user.id, payload, force=force))


@router.post("/backtest", response_model=BreakoutBacktestOut)
def backtest(
    payload: BreakoutScannerBacktestRequest | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BreakoutBacktestOut:
    return BreakoutBacktestOut(**run_breakout_backtest(db, user.id, payload))
