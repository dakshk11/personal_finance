from __future__ import annotations

import asyncio
from datetime import date, timedelta
import sys
import types
from pathlib import Path
from unittest.mock import AsyncMock

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

from services import breakout_router  # noqa: E402


def test_ibkr_scan_uses_cached_ndx100_data_without_live_connection(tmp_path, monkeypatch) -> None:
    _write_cache(tmp_path, "AAA")
    live_fetch = AsyncMock()
    monkeypatch.setattr(breakout_router, "OHLCV_CACHE_DIR", tmp_path)
    monkeypatch.setattr(breakout_router, "ALL_TICKERS", ["AAA"])
    monkeypatch.setattr(breakout_router.ibkr_svc, "is_connected", lambda: False)
    monkeypatch.setattr(breakout_router, "_fetch_from_ibkr", live_fetch)
    monkeypatch.setattr(breakout_router, "analyze", _fake_analyze)

    result = asyncio.run(breakout_router.breakout_scan(source="ibkr", index="ndx100", extra=None))

    assert result["data_source"] == "ibkr_cache"
    assert result["universe_count"] == 1
    assert result["scanned_symbols"] == 1
    assert len(result["signals"]) == 1
    assert result["warnings"] == []
    live_fetch.assert_not_called()

    signal = result["signals"][0]
    assert signal["symbol"] == "AAA"
    assert signal["detector_type"] == "near_breakout"
    assert signal["chart"]
    assert {"date", "open", "high", "low", "close", "volume", "sma20", "sma50", "sma200"} <= set(signal["chart"][-1])


def test_ibkr_scan_appends_extra_symbols_without_duplicates(tmp_path, monkeypatch) -> None:
    _write_cache(tmp_path, "AAA")
    _write_cache(tmp_path, "ZZZ")
    monkeypatch.setattr(breakout_router, "OHLCV_CACHE_DIR", tmp_path)
    monkeypatch.setattr(breakout_router, "ALL_TICKERS", ["AAA"])
    monkeypatch.setattr(breakout_router.ibkr_svc, "is_connected", lambda: False)
    monkeypatch.setattr(breakout_router, "analyze", _fake_analyze)

    result = asyncio.run(breakout_router.breakout_scan(source="ibkr", index="ndx100", extra="aaa, ZZZ, AAA"))

    assert result["universe_count"] == 2
    assert result["scanned_symbols"] == 2
    assert {signal["symbol"] for signal in result["signals"]} == {"AAA", "ZZZ"}


def test_ibkr_scan_supports_30m_intraday_cache(tmp_path, monkeypatch) -> None:
    _write_cache(tmp_path, "AAA", rows=220, intraday=True)
    monkeypatch.setattr(breakout_router, "INTRADAY_30M_CACHE_DIR", tmp_path)
    monkeypatch.setattr(breakout_router, "ALL_TICKERS", ["AAA"])
    monkeypatch.setattr(breakout_router.ibkr_svc, "is_connected", lambda: False)
    monkeypatch.setattr(breakout_router, "analyze", _fake_analyze)

    result = asyncio.run(breakout_router.breakout_scan(source="ibkr", index="ndx100", interval="30m", extra=None))

    assert result["data_source"] == "ibkr_30m_cache"
    assert result["chart_interval"] == "1h"
    assert result["universe_count"] == 1
    assert result["scanned_symbols"] == 1
    assert len(result["signals"]) == 1
    assert " " in result["signals"][0]["as_of_date"]
    assert " " in result["signals"][0]["chart"][-1]["date"]
    assert result["signals"][0]["chart"][-1]["date"].endswith(":00")


def test_ibkr_refresh_caps_live_historical_fetches(tmp_path, monkeypatch) -> None:
    live_fetch = AsyncMock(return_value=None)
    monkeypatch.setattr(breakout_router, "INTRADAY_30M_CACHE_DIR", tmp_path)
    monkeypatch.setattr(breakout_router, "ALL_TICKERS", ["AAA", "BBB", "CCC", "DDD", "EEE"])
    monkeypatch.setattr(breakout_router, "MAX_IBKR_HISTORICAL_FETCHES_PER_SCAN", 3)
    monkeypatch.setattr(breakout_router.ibkr_svc, "is_connected", lambda: True)
    monkeypatch.setattr(breakout_router, "_fetch_from_ibkr", live_fetch)
    monkeypatch.setattr(breakout_router, "analyze", _fake_analyze)

    result = asyncio.run(breakout_router.breakout_scan(source="ibkr", index="ndx100", interval="30m", refresh=True, extra=None))

    assert live_fetch.await_count == 3
    assert result["scanned_symbols"] == 0
    assert any("IBKR refresh limited to 3 historical requests" in warning for warning in result["warnings"])


def test_ibkr_scan_missing_cache_disconnected_keeps_response_shape(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(breakout_router, "OHLCV_CACHE_DIR", tmp_path)
    monkeypatch.setattr(breakout_router, "ALL_TICKERS", ["MISS"])
    monkeypatch.setattr(breakout_router.ibkr_svc, "is_connected", lambda: False)
    monkeypatch.setattr(breakout_router, "analyze", _fake_analyze)

    result = asyncio.run(breakout_router.breakout_scan(source="ibkr", index="ndx100", extra=None))

    assert result["data_source"] == "ibkr_cache"
    assert result["universe_count"] == 1
    assert result["scanned_symbols"] == 0
    assert result["signals"] == []
    assert result["warnings"]
    assert "IBKR not connected" in result["warnings"][0]


def _write_cache(directory: Path, symbol: str, rows: int = 220, intraday: bool = False) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    _ohlcv_frame(rows=rows, intraday=intraday).to_pickle(directory / f"{symbol}.pkl")


def _ohlcv_frame(rows: int = 220, intraday: bool = False) -> pd.DataFrame:
    if intraday:
        dates = pd.date_range("2025-01-02 09:30", periods=rows, freq="30min")
        return _frame_for_dates(dates)

    current = date(2025, 1, 2)
    dates = []
    while len(dates) < rows:
        if current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)

    return _frame_for_dates(pd.DatetimeIndex(dates, name="Date"))


def _frame_for_dates(dates: pd.DatetimeIndex) -> pd.DataFrame:
    data = []
    for index, _day in enumerate(dates):
        base = 100 + index * 0.2
        data.append(
            {
                "Open": round(base, 4),
                "High": round(base + 1.8, 4),
                "Low": round(base - 1.2, 4),
                "Close": round(base + 0.7, 4),
                "Volume": 1_000_000 + index * 1_000,
            }
        )
    if dates.name != "Date":
        dates = pd.DatetimeIndex(dates, name="Date")
    return pd.DataFrame(data, index=dates)


def _fake_analyze(symbol: str, df: pd.DataFrame) -> dict[str, object]:
    close = float(df["Close"].iloc[-1])
    return {
        "ticker": symbol,
        "type": "NEAR_BREAKOUT",
        "close": close,
        "breakout_level": round(close * 1.02, 4),
        "above_200sma": True,
        "rsi": 58.0,
        "rel_vol": 1.6,
        "tests": 4,
        "score": 77,
        "level_label": "Watch setup",
    }
