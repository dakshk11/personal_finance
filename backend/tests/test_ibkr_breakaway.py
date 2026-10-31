from __future__ import annotations

import sys
import types
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

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

from services import breakaway_router, breakaway_service  # noqa: E402


def _bars(drift: float, days: int = 260, end: date | None = None) -> pd.DataFrame:
    idx = pd.date_range(end=pd.Timestamp(end or date.today()), periods=days, freq="D")
    rng = np.random.default_rng(7)
    close = 100 * np.cumprod(1 + drift + rng.normal(0, 0.01, days))
    return pd.DataFrame(
        {"Open": close * 0.998, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": 1_000_000.0},
        index=pd.DatetimeIndex(idx, name="Date"),
    )


def test_uptrend_scores_above_downtrend() -> None:
    up = breakaway_service.compute_frame(_bars(0.003))
    down = breakaway_service.compute_frame(_bars(-0.003))
    assert up["score"].iloc[-1] > down["score"].iloc[-1]
    assert up["checks"].iloc[-1] <= breakaway_service.MAX_CHECKS
    assert not (up["vol"] & up["vdu"]).any()
    assert up["score"].iloc[:199].isna().all()


def test_tiers_match_breakaway_bands() -> None:
    assert breakaway_service.tier(20) == "Exceptional"
    assert breakaway_service.tier(15) == "Excellent"
    assert breakaway_service.tier(11) == "Above average"
    assert breakaway_service.tier(6) == "Average"
    assert breakaway_service.tier(0) == "Below average"
    assert breakaway_service.tier(-1) == "Poor"


def test_scan_uses_nasdaq100_cache_and_live_quote_without_ibkr_requests(tmp_path, monkeypatch) -> None:
    _bars(0.003).to_pickle(tmp_path / "AAA.pkl")
    _bars(-0.002).to_pickle(tmp_path / "BBB.pkl")
    _bars(0.004).to_pickle(tmp_path / "SOXL.pkl")  # leveraged ETF in ALL_TICKERS → included
    _bars(0.003).to_pickle(tmp_path / "ZZZ.pkl")  # cached but outside the universe → excluded

    async def no_ibkr_fetch(*_args, **_kwargs):
        raise AssertionError("Breakaway must not request IBKR data")

    monkeypatch.setattr(breakaway_router.breakout_router, "OHLCV_CACHE_DIR", tmp_path)
    monkeypatch.setattr(breakaway_router.breakout_router, "_fetch_from_ibkr", no_ibkr_fetch)
    monkeypatch.setattr(breakaway_router, "NASDAQ100", ["AAA", "BBB", "CCC"])
    monkeypatch.setattr(breakaway_router, "ALL_TICKERS", ["AAA", "BBB", "CCC", "SOXL"])
    monkeypatch.setattr(breakaway_router, "_bars_cache", {})
    monkeypatch.setattr(breakaway_router, "_frame_cache", {})
    monkeypatch.setattr(breakaway_router.ibkr_svc, "is_connected", lambda: False)
    monkeypatch.setattr(breakaway_router.ibkr_svc, "get_all_quotes", lambda: {"AAA": {"price": 999.0}})

    result = breakaway_router.breakaway_scan()

    symbols = [row["symbol"] for row in result["stocks"]]
    assert sorted(symbols) == ["AAA", "BBB", "SOXL"]
    assert result["universe_count"] == 4
    soxl = next(row for row in result["stocks"] if row["symbol"] == "SOXL")
    assert soxl["sector"] == "Leveraged ETFs"
    assert result["live_quotes"] == 1
    aaa = next(row for row in result["stocks"] if row["symbol"] == "AAA")
    assert aaa["price"] == 999.0 and aaa["live"] is True
    assert any("CCC" in warning for warning in result["warnings"])
    assert [row["rank"] for row in result["stocks"]] == [1, 2, 3]

    detail = breakaway_router.breakaway_stock("aaa")
    assert detail["symbol"] == "AAA"
    assert len(detail["check_details"]) == 14
    assert any(not part["scored"] for part in detail["breakdown"])
    assert detail["trade_plan"]["stop"] < detail["trade_plan"]["entry"] < detail["trade_plan"]["target"]
