from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.entities import User
from app.schemas.common import (
    OptionStrategyAlertEventOut,
    OptionStrategyConfigOut,
    OptionStrategyConfigUpdate,
    OptionStrategyPositionEventIn,
    OptionStrategyScanResultOut,
    OptionStrategySignalCandidateOut,
    OptionStrategyUniverseOut,
    OptionStrategyWheelPositionOut,
)
from app.services import option_strategy


router = APIRouter(prefix="/option-strategy", tags=["option-strategy"])


@router.get("/universe", response_model=OptionStrategyUniverseOut)
def get_universe(
    user: User = Depends(get_current_user),
) -> OptionStrategyUniverseOut:
    del user
    items = option_strategy.default_universe()
    groups = sorted({item["group"] for item in items})
    return OptionStrategyUniverseOut(items=items, groups=groups, count=len(items))


@router.get("/config", response_model=OptionStrategyConfigOut)
def get_config(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OptionStrategyConfigOut:
    return OptionStrategyConfigOut(**option_strategy.get_config(db, user.id))


@router.put("/config", response_model=OptionStrategyConfigOut)
def update_config(
    payload: OptionStrategyConfigUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OptionStrategyConfigOut:
    return OptionStrategyConfigOut(**option_strategy.update_config(db, user.id, payload.model_dump(exclude_unset=True)))


@router.post("/scan", response_model=OptionStrategyScanResultOut)
def run_scan(
    force: bool = Query(default=False),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OptionStrategyScanResultOut:
    return OptionStrategyScanResultOut(**option_strategy.run_scan(db, user.id, force=force))


@router.get("/signals", response_model=list[OptionStrategySignalCandidateOut])
def list_signals(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[OptionStrategySignalCandidateOut]:
    return [OptionStrategySignalCandidateOut(**item) for item in option_strategy.list_signals(db, user.id)]


@router.post("/positions", response_model=OptionStrategyWheelPositionOut)
def record_position_event(
    payload: OptionStrategyPositionEventIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OptionStrategyWheelPositionOut:
    try:
        position = option_strategy.record_position_event(db, user.id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return OptionStrategyWheelPositionOut(**position)


@router.get("/positions", response_model=list[OptionStrategyWheelPositionOut])
def list_positions(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[OptionStrategyWheelPositionOut]:
    return [OptionStrategyWheelPositionOut(**item) for item in option_strategy.list_positions(db, user.id)]


@router.get("/alerts", response_model=list[OptionStrategyAlertEventOut])
def list_alerts(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[OptionStrategyAlertEventOut]:
    return [OptionStrategyAlertEventOut(**item) for item in option_strategy.list_alerts(db, user.id)]
