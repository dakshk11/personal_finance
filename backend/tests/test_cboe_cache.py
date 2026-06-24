from __future__ import annotations

from datetime import datetime
import importlib
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
IBKR_ROOT = ROOT / "backend" / "ibkr"
if str(IBKR_ROOT) not in sys.path:
    sys.path.insert(0, str(IBKR_ROOT))

config_stub = types.ModuleType("config")
config_stub.settings = types.SimpleNamespace(cboe_timeout=5, cboe_base_url="https://example.test")
sys.modules.setdefault("config", config_stub)

httpx_stub = types.ModuleType("httpx")


class _AsyncClient:
    def __init__(self, *_args, **_kwargs) -> None:
        self.is_closed = False


class _Limits:
    def __init__(self, *_args, **_kwargs) -> None:
        pass


httpx_stub.AsyncClient = _AsyncClient
httpx_stub.Limits = _Limits
sys.modules.setdefault("httpx", httpx_stub)

throttle_stub = types.ModuleType("asyncio_throttle")


class _Throttler:
    def __init__(self, *_args, **_kwargs) -> None:
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None


throttle_stub.Throttler = _Throttler
sys.modules.setdefault("asyncio_throttle", throttle_stub)

sys.modules.pop("services.cboe_service", None)
cboe_service = importlib.import_module("services.cboe_service")


def test_cboe_cache_is_stale_after_twenty_minutes() -> None:
    old_cache = cboe_service._cache
    try:
        cboe_service._cache = {
            "TQQQ": (
                datetime.now().timestamp() - (21 * 60),
                [{"symbol": "TQQQ", "stock_price": 80.0}],
            )
        }

        stats = cboe_service.cache_stats()

        assert cboe_service._is_cached_today("TQQQ") is False
        assert stats["cboe_cache_stale"] is True
        assert stats["cboe_cache_age_seconds"] >= 20 * 60
    finally:
        cboe_service._cache = old_cache
