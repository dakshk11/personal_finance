from __future__ import annotations

from datetime import datetime, timedelta
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
tickers_stub.ALL_TICKERS = []
sys.modules.setdefault("data", data_stub)
sys.modules.setdefault("data.tickers", tickers_stub)

services_stub = types.ModuleType("services")
sys.modules.setdefault("services", services_stub)

ibkr_service_stub = types.ModuleType("services.ibkr_service")
ibkr_service_stub.connect = lambda: False
ibkr_service_stub.is_connected = lambda: False
ibkr_service_stub.get_all_quotes = lambda: {}
ibkr_service_stub.get_ib = lambda: None
ibkr_service_stub.get_contracts = lambda: {}
sys.modules.setdefault("services.ibkr_service", ibkr_service_stub)

analytics_stub = types.ModuleType("services.analytics_service")
analytics_stub.get_all_analytics = lambda: {}
analytics_stub.get_analytics = lambda _sym: {}
analytics_stub.compute_from_bars = lambda _closes, _volumes: {}
analytics_stub.refresh = lambda *_args, **_kwargs: None
sys.modules.setdefault("services.analytics_service", analytics_stub)

cboe_stub = types.ModuleType("services.cboe_service")
cboe_stub.get_option_chain = lambda _symbol: []
cboe_stub._is_cached_today = lambda _symbol: True
cboe_stub.find_30delta_metrics = lambda _symbol: {"csp_30d": None, "cc_30d": None}
cboe_stub.get_atm_iv = lambda _symbol: None
sys.modules.setdefault("services.cboe_service", cboe_stub)

scanner_stub = types.ModuleType("services.scanner_service")
scanner_stub.run_csp_scan = lambda *args, **kwargs: []
scanner_stub.run_cc_scan = lambda *args, **kwargs: []
sys.modules.setdefault("services.scanner_service", scanner_stub)

breakout_router_stub = types.ModuleType("services.breakout_router")
try:
    from fastapi import APIRouter

    breakout_router_stub.router = APIRouter()
except Exception:
    breakout_router_stub.router = None
sys.modules.setdefault("services.breakout_router", breakout_router_stub)

import main as ibkr_main  # noqa: E402


def test_csp_requires_premium_technical_iv_and_earnings_gates() -> None:
    assert ibkr_main._derive_wheel_signals(csp_30d=5.1, cc_30d=None, iv_rank=41, rsi=65, bb_pct=75) == ["CSP"]
    assert ibkr_main._derive_wheel_signals(csp_30d=5.1, cc_30d=None, iv_rank=39, rsi=65, bb_pct=75) == []
    assert ibkr_main._derive_wheel_signals(csp_30d=5.1, cc_30d=None, iv_rank=41, rsi=66, bb_pct=75) == []
    assert ibkr_main._derive_wheel_signals(csp_30d=5.1, cc_30d=None, iv_rank=41, rsi=65, bb_pct=76) == []
    assert ibkr_main._derive_wheel_signals(
        csp_30d=5.1,
        cc_30d=None,
        iv_rank=41,
        rsi=65,
        bb_pct=75,
        earnings_date=datetime.now() + timedelta(days=7),
    ) == []


def test_cc_requires_premium_technical_iv_and_earnings_gates() -> None:
    assert ibkr_main._derive_wheel_signals(csp_30d=None, cc_30d=5.1, iv_rank=41, rsi=40, bb_pct=30) == ["CC"]
    assert ibkr_main._derive_wheel_signals(csp_30d=None, cc_30d=5.1, iv_rank=40, rsi=40, bb_pct=30) == []
    assert ibkr_main._derive_wheel_signals(csp_30d=None, cc_30d=5.1, iv_rank=41, rsi=39, bb_pct=30) == []
    assert ibkr_main._derive_wheel_signals(csp_30d=None, cc_30d=5.1, iv_rank=41, rsi=40, bb_pct=29) == []
    assert ibkr_main._derive_wheel_signals(
        csp_30d=None,
        cc_30d=5.1,
        iv_rank=41,
        rsi=40,
        bb_pct=30,
        earnings_date=datetime.now() + timedelta(days=7),
    ) == []


def test_leap_requires_oversold_band_and_thirty_day_earnings_clearance() -> None:
    assert ibkr_main._derive_wheel_signals(csp_30d=None, cc_30d=None, iv_rank=None, rsi=40, bb_pct=20) == ["LEAP"]
    assert ibkr_main._derive_wheel_signals(csp_30d=None, cc_30d=None, iv_rank=None, rsi=41, bb_pct=20) == []
    assert ibkr_main._derive_wheel_signals(csp_30d=None, cc_30d=None, iv_rank=None, rsi=40, bb_pct=21) == []
    assert ibkr_main._derive_wheel_signals(
        csp_30d=None,
        cc_30d=None,
        iv_rank=None,
        rsi=40,
        bb_pct=20,
        earnings_date=datetime.now() + timedelta(days=30),
    ) == []
