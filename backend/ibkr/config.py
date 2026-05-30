from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # IBKR TWS Socket API
    tws_host: str = "127.0.0.1"
    tws_port: int = 7496        # 7496 = live TWS, 7497 = paper trading
    tws_client_id: int = 1

    # CBOE delayed options
    cboe_base_url: str = "https://cdn.cboe.com/api/global/delayed_quotes/options"
    cboe_timeout: int = 10

    # Cache TTLs
    quote_cache_ttl: int = 5       # seconds (IBKR poll interval)
    options_cache_ttl: int = 300   # 5 minutes (CBOE is already 15 min delayed)

    # CBOE fetch concurrency
    scan_batch_size: int = 5       # max concurrent CBOE fetches

    class Config:
        env_file = ".env"


settings = Settings()
