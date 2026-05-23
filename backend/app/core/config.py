from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BACKEND_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "Direct Indexing Simulator"
    database_url: str = "sqlite:///./directindex.db"
    redis_url: str = "redis://localhost:6379/0"
    frontend_origin: str = "http://localhost:3000"
    session_cookie_name: str = "directindex_session"
    session_cookie_secure: bool = False
    session_ttl_seconds: int = 60 * 60 * 24 * 14
    default_portfolio_value: float = 100_000.0
    seed_test_account: bool = True
    test_account_email: str = "test@gmail.com"
    test_account_password: str = "1234"
    sec_user_agent: str = "DirectIndex local 13F research admin@example.com"
    ai_advisor_key_encryption_secret: str = ""

    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def local_cors_origins() -> list[str]:
    settings = get_settings()
    return sorted(
        {
            settings.frontend_origin.rstrip("/"),
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        }
    )
