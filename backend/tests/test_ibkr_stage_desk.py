from __future__ import annotations

import sys
import types
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

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

from services import breakaway_router, stage_router, stage_service  # noqa: E402


def _bars(drift: float, days: int = 320, end: date | None = None) -> pd.DataFrame:
    idx = pd.date_range(end=pd.Timestamp(end or date.today()), periods=days, freq="D")
    rng = np.random.default_rng(7)
    close = 100 * np.cumprod(1 + drift + rng.normal(0, 0.01, days))
    return pd.DataFrame(
        {"Open": close * 0.998, "High": close * 1.01, "Low": close * 0.99, "Close": close, "Volume": 1_000_000.0},
        index=pd.DatetimeIndex(idx, name="Date"),
    )


def test_classify_stages_walks_through_the_cycle() -> None:
    close = pd.Series([110, 112, 105, 95, 90, 92, 101], dtype=float)
    ma30 = pd.Series([100, 101, 104, 100, 96, 95, 95], dtype=float)
    slope = pd.Series([0.02, 0.02, 0.0, -0.02, -0.03, 0.0, 0.0])
    assert stage_service.classify_stages(close, ma30, slope).tolist() == [2, 2, 3, 4, 4, 1, 1]


def test_weeks_in_stage_counts_runs() -> None:
    stage = pd.Series([np.nan, 1, 1, 2, 2, 2, 3], dtype=float)
    assert stage_service.weeks_in_stage(stage).tolist()[1:] == [1, 2, 1, 2, 3, 1]


@pytest.mark.parametrize("drift,stage", [(0.003, 2), (-0.003, 4)])
def test_trend_stages_and_scores(drift: float, stage: int) -> None:
    bench = _bars(0.0)["Close"]
    weekly = stage_service.compute_weekly(_bars(drift), bench)
    assert weekly["stage"].iloc[-1] == stage
    assert 0 <= weekly["score"].iloc[-1] <= stage_service.MAX_SCORE


def test_scan_is_nasdaq100_only_and_uses_cache_and_live_quote(tmp_path, monkeypatch) -> None:
    _bars(0.003).to_pickle(tmp_path / "AAA.pkl")
    _bars(-0.002).to_pickle(tmp_path / "BBB.pkl")
    _bars(0.004).to_pickle(tmp_path / "SOXL.pkl")  # leveraged ETF → excluded from Stage Desk

    async def no_ibkr_fetch(*_args, **_kwargs):
        raise AssertionError("Stage Desk must not request IBKR data")

    monkeypatch.setattr(breakaway_router.breakout_router, "OHLCV_CACHE_DIR", tmp_path)
    monkeypatch.setattr(breakaway_router.breakout_router, "_fetch_from_ibkr", no_ibkr_fetch)
    monkeypatch.setattr(breakaway_router, "_bars_cache", {})
    monkeypatch.setattr(stage_router, "NASDAQ100", ["AAA", "BBB", "CCC"])
    monkeypatch.setattr(stage_router.ibkr_svc, "is_connected", lambda: False)
    monkeypatch.setattr(stage_router.ibkr_svc, "get_all_quotes", lambda: {"AAA": {"price": 999.0}})

    result = stage_router.stage_desk_scan()

    assert sorted(r["symbol"] for r in result["stocks"]) == ["AAA", "BBB"]
    assert result["universe_count"] == 3 and result["live_quotes"] == 1
    aaa = next(r for r in result["stocks"] if r["symbol"] == "AAA")
    assert aaa["price"] == 999.0 and aaa["stage"] == 2
    assert all(r["ind_pct"] is not None and r["rs_pct"] is not None for r in result["stocks"])
    assert any("CCC" in w for w in result["warnings"])

    detail = stage_router.stage_desk_stock("aaa")
    assert len(detail["check_details"]) == stage_service.MAX_SCORE
    assert detail["stage_history"][-1]["stage"] == detail["stage"]
    with pytest.raises(stage_router.HTTPException):
        stage_router.stage_desk_stock("SOXL")
