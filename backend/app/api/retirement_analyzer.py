import json

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.entities import RetirementAnalyzerState, User
from app.schemas.common import RetirementAnalyzerStateIn, RetirementAnalyzerStateOut


router = APIRouter(prefix="/retirement-analyzer", tags=["retirement-analyzer"])


@router.get("/state", response_model=RetirementAnalyzerStateOut)
def get_retirement_analyzer_state(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RetirementAnalyzerStateOut:
    row = db.scalar(select(RetirementAnalyzerState).where(RetirementAnalyzerState.user_id == user.id))
    if not row:
        return RetirementAnalyzerStateOut()
    try:
        payload = json.loads(row.payload_json)
    except json.JSONDecodeError:
        payload = {}
    return RetirementAnalyzerStateOut(payload=payload, updated_at=row.updated_at)


@router.put("/state", response_model=RetirementAnalyzerStateOut)
def save_retirement_analyzer_state(
    payload: RetirementAnalyzerStateIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RetirementAnalyzerStateOut:
    row = db.scalar(select(RetirementAnalyzerState).where(RetirementAnalyzerState.user_id == user.id))
    serialized = json.dumps(payload.payload, separators=(",", ":"), sort_keys=True)
    if row:
        row.payload_json = serialized
    else:
        row = RetirementAnalyzerState(user_id=user.id, payload_json=serialized)
        db.add(row)
    db.commit()
    db.refresh(row)
    return RetirementAnalyzerStateOut(payload=payload.payload, updated_at=row.updated_at)
