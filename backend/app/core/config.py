from functools import lru_cache
from pathlib import Path
from secrets import token_urlsafe

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]
LOCAL_AI_ADVISOR_KEY_ENCRYPTION_SECRET = "directindex-local-ai-advisor-key-secret-change-me"
LOCAL_BROKER_SYNC_ENCRYPTION_SECRET = "directindex-local-broker-sync-secret-change-me"
LOCAL_RUNTIME_TEST_ACCOUNT_PASSWORD = token_urlsafe(32)


class Settings(BaseSettings):
    app_name: str = "FinanceOS"
    database_url: str = "sqlite:///./directindex.db"
    redis_url: str = "redis://localhost:6379/0"
    frontend_origin: str = "http://localhost:3000"
    session_cookie_name: str = "directindex_session"
    session_cookie_secure: bool = False
    session_ttl_seconds: int = 60 * 60 * 24 * 14
    default_portfolio_value: float = 100_000.0
    seed_test_account: bool = True
    test_account_email: str = "local-demo@financeos.local"
    test_account_password: str = ""
    sec_user_agent: str = "FinanceOS local 13F research admin@example.com"
    ai_advisor_key_encryption_secret: str = LOCAL_AI_ADVISOR_KEY_ENCRYPTION_SECRET
    snaptrade_client_id: str = ""
    snaptrade_consumer_key: str = ""
    broker_sync_encryption_secret: str = LOCAL_BROKER_SYNC_ENCRYPTION_SECRET

    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def local_test_account_password(settings: Settings) -> str:
    configured = settings.test_account_password.strip()
    return configured or LOCAL_RUNTIME_TEST_ACCOUNT_PASSWORD


def local_cors_origins() -> list[str]:
    settings = get_settings()
    return sorted(
        {
            settings.frontend_origin.rstrip("/"),
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        }
    )
