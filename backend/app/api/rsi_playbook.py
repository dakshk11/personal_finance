from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.entities import User
from app.schemas.common import RSIPlaybookScanOut
from app.services.rsi_playbook import scan_rsi_playbook


router = APIRouter(prefix="/rsi-playbook", tags=["rsi-playbook"])


@router.get("/scan", response_model=RSIPlaybookScanOut)
def scan(
    force: bool = Query(default=False),
    lookback_days: int = Query(default=420, ge=120, le=1200),
    max_symbols: int = Query(default=90, ge=1, le=120),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RSIPlaybookScanOut:
    return RSIPlaybookScanOut(
        **scan_rsi_playbook(
            db,
            user.id,
            force_refresh=force,
            lookback_days=lookback_days,
            max_symbols=max_symbols,
        )
    )
