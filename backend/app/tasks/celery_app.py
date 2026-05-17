from celery import Celery

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.services.market_data import sync_daily_data
from app.services.sec_filings import sync_due_13f_watches


settings = get_settings()
celery_app = Celery("directindex", broker=settings.redis_url, backend=settings.redis_url)
celery_app.conf.timezone = "America/Los_Angeles"
celery_app.conf.beat_schedule = {
    "sync-daily-market-data": {
        "task": "app.tasks.celery_app.sync_daily_market_data",
        "schedule": 60 * 60 * 24,
    },
    "sync-13f-filing-watches": {
        "task": "app.tasks.celery_app.sync_13f_filing_watches",
        "schedule": 60 * 60 * 2,
    }
}


@celery_app.task
def sync_daily_market_data() -> dict[str, object]:
    db = SessionLocal()
    try:
        synced, warning = sync_daily_data(db)
        return {"synced_indices": synced, "warning": warning}
    finally:
        db.close()


@celery_app.task
def sync_13f_filing_watches() -> dict[str, int]:
    db = SessionLocal()
    try:
        return sync_due_13f_watches(db)
    finally:
        db.close()
