from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.entities import User
from app.schemas.common import DataSyncOut
from app.services.market_data import sync_daily_data


router = APIRouter(prefix="/data", tags=["data"])


@router.post("/sync", response_model=DataSyncOut)
def sync_data(_: User = Depends(get_current_user), db: Session = Depends(get_db)) -> DataSyncOut:
    synced, warning = sync_daily_data(db)
    return DataSyncOut(status="completed", synced_indices=synced, warning=warning)

