from datetime import date, timedelta
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.entities import PriceBar
from app.services.market_history import (
    MarketHistoryBar,
    calculate_high_yield_signal,
    cache_high_yield_history,
    get_market_history,
    list_high_yield_fund_metadata,
    list_major_indexes,
)


class MarketHistoryTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def test_major_indexes_include_core_market_proxies(self) -> None:
        symbols = {item.symbol for item in list_major_indexes()}

        self.assertTrue({"SPY", "QQQ", "DIA", "IWM", "VTI"}.issubset(symbols))

    def test_high_yield_universe_includes_requested_funds(self) -> None:
        symbols = {item.symbol for item in list_high_yield_fund_metadata()}

        self.assertEqual({"QQQI", "SPYI", "CHPY", "IAUI", "OVL", "GIAX"}, symbols)

    def test_provider_history_is_cached_and_reused(self) -> None:
        db = self.Session()
        fetched = [
            MarketHistoryBar(date=date(2026, 5, 18), close=100, adjusted_close=99.5, dividend=0, source="test provider"),
            MarketHistoryBar(date=date(2026, 5, 19), close=101, adjusted_close=100.5, dividend=0.1, source="test provider"),
        ]

        with patch("app.services.market_history._fetch_provider_history", return_value=fetched) as fetch:
            result = get_market_history(db, "SPY", date(2026, 5, 18), date(2026, 5, 19))

        self.assertEqual(fetch.call_count, 1)
        self.assertEqual(result.symbol, "SPY")
        self.assertEqual(len(result.bars), 2)
        self.assertEqual(result.bars[1].dividend, 0.1)
        self.assertEqual(db.scalar(select(func.count(PriceBar.id))), 2)

        with patch("app.services.market_history._fetch_provider_history") as fetch_again:
            cached = get_market_history(db, "SPY", date(2026, 5, 18), date(2026, 5, 19))

        self.assertEqual(fetch_again.call_count, 0)
        self.assertEqual(len(cached.bars), 2)

    def test_high_yield_cache_returns_signals_for_each_fund(self) -> None:
        db = self.Session()
        fetched = _trend_with_pullback_bars(date(2025, 1, 2), 260)

        with patch("app.services.market_history._fetch_provider_history", return_value=fetched):
            result = cache_high_yield_history(db, date(2025, 1, 2), date(2025, 12, 31))

        self.assertEqual(len(result), 6)
        self.assertTrue(all(item.signal.action in {"BUY", "HOLD"} for item in result))
        self.assertTrue(all(item.signal.data_points >= 90 for item in result))

    def test_high_yield_signal_identifies_controlled_pullback(self) -> None:
        signal = calculate_high_yield_signal(_trend_with_pullback_bars(date(2025, 1, 2), 260))

        self.assertEqual(signal.action, "BUY")
        self.assertEqual(signal.risk_state, "Trend-supported pullback")
        self.assertGreater(signal.backtest.evaluated_weeks, 0)

    def test_high_yield_signal_holds_on_limited_history(self) -> None:
        signal = calculate_high_yield_signal(_trend_with_pullback_bars(date(2026, 1, 2), 40))

        self.assertEqual(signal.action, "HOLD")
        self.assertTrue(signal.limited_history)


def _trend_with_pullback_bars(start: date, count: int) -> list[MarketHistoryBar]:
    bars: list[MarketHistoryBar] = []
    current = start
    trading_day = 0
    while len(bars) < count:
        if current.weekday() < 5:
            price = 100 + trading_day * 0.18
            if count - len(bars) <= 8:
                price *= 0.94
            bars.append(
                MarketHistoryBar(
                    date=current,
                    close=round(price, 4),
                    adjusted_close=round(price, 4),
                    dividend=0,
                    source="test provider",
                )
            )
            trading_day += 1
        current += timedelta(days=1)
    return bars


if __name__ == "__main__":
    unittest.main()
