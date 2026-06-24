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

ib_insync_stub = types.ModuleType("ib_insync")


class _IB:
    def isConnected(self) -> bool:
        return False


class _Stock:
    def __init__(self, *_args, **_kwargs) -> None:
        pass


class _Ticker:
    pass


ib_insync_stub.IB = _IB
ib_insync_stub.Stock = _Stock
ib_insync_stub.Ticker = _Ticker
sys.modules.setdefault("ib_insync", ib_insync_stub)

data_stub = types.ModuleType("data")
tickers_stub = types.ModuleType("data.tickers")
tickers_stub.ALL_TICKERS = ["TQQQ"]
tickers_stub.IBKR_SYMBOL_MAP = {}
sys.modules.setdefault("data", data_stub)
sys.modules.setdefault("data.tickers", tickers_stub)

sys.modules.pop("services", None)
sys.modules.pop("services.ibkr_service", None)
ibkr_service = importlib.import_module("services.ibkr_service")


def test_quote_cache_stats_marks_rows_stale_after_twenty_minutes() -> None:
    old_cache = ibkr_service._quote_cache
    try:
        ibkr_service._quote_cache = {
            "TQQQ": {
                "symbol": "TQQQ",
                "price": 80.0,
                "updated_at_epoch": datetime.now().timestamp() - (21 * 60),
            }
        }

        stats = ibkr_service.quote_cache_stats()

        assert stats["quote_cache_stale"] is True
        assert stats["quote_cache_age_seconds"] is None
        assert stats["quote_cache_stale_count"] == 1
    finally:
        ibkr_service._quote_cache = old_cache


def test_get_all_quotes_excludes_stale_rows() -> None:
    old_cache = ibkr_service._quote_cache
    now = datetime.now().timestamp()
    try:
        ibkr_service._quote_cache = {
            "OLD": {
                "symbol": "OLD",
                "price": 10.0,
                "updated_at_epoch": now - (21 * 60),
            },
            "NEW": {
                "symbol": "NEW",
                "price": 20.0,
                "updated_at_epoch": now,
            },
        }

        quotes = ibkr_service.get_all_quotes()

        assert "OLD" not in quotes
        assert quotes["NEW"]["price"] == 20.0
    finally:
        ibkr_service._quote_cache = old_cache
