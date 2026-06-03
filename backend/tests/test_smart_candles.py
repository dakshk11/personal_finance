from datetime import date, timedelta
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.entities import User
from app.services import smart_candles
from app.services.breakout_scanner import BreakoutBar, BreakoutUniverseItem


class SmartCandleTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def _seed_user(self) -> tuple[object, User]:
        db = self.Session()
        user = User(email="smart-candle@example.com", password_hash="hash")
        db.add(user)
        db.commit()
        db.refresh(user)
        return db, user

    def test_blue_candle_detects_bullish_reversal(self) -> None:
        item = BreakoutUniverseItem("AAA", "AAA Inc", "Technology", "test", "test")
        config = smart_candles.normalize_smart_candle_config({"min_avg_dollar_volume": 0, "min_relative_volume": 1.1})

        signal = smart_candles.classify_latest_candle(item, _blue_bars(date.today() - timedelta(days=360)), config)

        self.assertIsNotNone(signal)
        self.assertEqual(signal["candle_color"], "blue")
        self.assertGreaterEqual(signal["score"], 70)

    def test_pink_candle_detects_distribution(self) -> None:
        item = BreakoutUniverseItem("BBB", "BBB Inc", "Industrials", "test", "test")
        config = smart_candles.normalize_smart_candle_config({"min_avg_dollar_volume": 0, "min_relative_volume": 1.1})

        signal = smart_candles.classify_latest_candle(item, _pink_bars(date.today() - timedelta(days=360)), config)

        self.assertIsNotNone(signal)
        self.assertEqual(signal["candle_color"], "pink")

    def test_red_candle_detects_breakdown(self) -> None:
        item = BreakoutUniverseItem("CCC", "CCC Inc", "Financials", "test", "test")
        config = smart_candles.normalize_smart_candle_config({"min_avg_dollar_volume": 0, "min_relative_volume": 1.1})

        signal = smart_candles.classify_latest_candle(item, _red_bars(date.today() - timedelta(days=360)), config)

        self.assertIsNotNone(signal)
        self.assertEqual(signal["candle_color"], "red")

    def test_low_volume_noisy_candle_is_neutral(self) -> None:
        item = BreakoutUniverseItem("DDD", "DDD Inc", "Utilities", "test", "test")
        config = smart_candles.normalize_smart_candle_config({"min_avg_dollar_volume": 0, "min_relative_volume": 1.3, "include_neutral": True})

        signal = smart_candles.classify_latest_candle(item, _neutral_bars(date.today() - timedelta(days=360)), config)

        self.assertIsNotNone(signal)
        self.assertEqual(signal["candle_color"], "neutral")

    def test_custom_symbols_append_without_duplicates(self) -> None:
        db, user = self._seed_user()
        universe = _universe_out()
        histories = {
            "AAA": _blue_bars(date.today() - timedelta(days=360)),
            "NVDA": _red_bars(date.today() - timedelta(days=360)),
        }

        with (
            patch("app.services.smart_candles.load_sp500_universe", return_value=universe),
            patch("app.services.smart_candles.load_ohlcv_histories", return_value=(histories, [])) as history_loader,
        ):
            result = smart_candles.run_smart_candle_scan(
                db,
                {"max_symbols": 1, "custom_symbols": ["nvda", "AAA", "nvda"], "min_avg_dollar_volume": 0, "min_relative_volume": 1.1},
            )

        self.assertEqual(history_loader.call_args.args[1], ["AAA", "NVDA"])
        self.assertEqual(result["scanned_symbols"], 2)
        self.assertEqual(result["config"]["custom_symbols"], ["NVDA", "AAA"])
        self.assertIn("NVDA", {signal["symbol"] for signal in result["signals"]})
        self.assertEqual(user.email, "smart-candle@example.com")

    def test_backtest_returns_distribution_rows(self) -> None:
        db, user = self._seed_user()
        universe = _universe_out()
        histories = {"AAA": _repeating_blue_bars(date.today() - timedelta(days=1300), trading_days=920)}

        with (
            patch("app.services.smart_candles.load_sp500_universe", return_value=universe),
            patch("app.services.smart_candles.load_ohlcv_histories", return_value=(histories, [])),
        ):
            result = smart_candles.run_smart_candle_backtest(
                db,
                {"candle_color": "blue", "years": 3, "max_symbols": 1, "min_avg_dollar_volume": 0, "min_relative_volume": 1.1},
            )

        self.assertEqual(result["candle_color"], "blue")
        self.assertEqual([row["horizon_days"] for row in result["horizons"]], [5, 10, 20, 60])
        self.assertGreater(result["signal_count"], 0)
        self.assertTrue(any(row["win_rate"] is not None for row in result["horizons"]))
        self.assertEqual(user.email, "smart-candle@example.com")


def _universe_out() -> dict[str, object]:
    return {
        "items": [
            {"symbol": "AAA", "company_name": "AAA Inc", "sector": "Technology", "source": "test", "source_url": "test"},
        ],
        "count": 1,
        "source": "test",
        "source_url": "test",
        "cache_status": "fresh",
        "retrieved_at": date.today().isoformat(),
        "warnings": [],
    }


def _base_bars(start: date, trading_days: int = 260, drift: float = 0.001, volume: float = 1_000_000) -> list[BreakoutBar]:
    bars: list[BreakoutBar] = []
    current = start
    price = 80.0
    while len(bars) < trading_days:
        if current.weekday() < 5:
            price *= 1 + drift
            bars.append(_bar(current, price, price * 1.01, price * 0.99, volume))
        current += timedelta(days=1)
    return bars


def _blue_bars(start: date, trading_days: int = 260) -> list[BreakoutBar]:
    bars = _base_bars(start, trading_days=trading_days, drift=0.0014)
    latest = _next_trading_day(bars[-1].date)
    prior = bars[-1].close
    bars[-1] = BreakoutBar(
        date=latest,
        open=round(prior * 0.982, 4),
        high=round(prior * 1.045, 4),
        low=round(prior * 0.965, 4),
        close=round(prior * 1.038, 4),
        adjusted_close=round(prior * 1.038, 4),
        volume=2_400_000,
        source="test OHLCV",
    )
    return bars


def _pink_bars(start: date, trading_days: int = 260) -> list[BreakoutBar]:
    bars = _base_bars(start, trading_days=trading_days, drift=0.0012)
    latest = _next_trading_day(bars[-1].date)
    prior = bars[-1].close
    bars[-1] = BreakoutBar(
        date=latest,
        open=round(prior * 1.015, 4),
        high=round(prior * 1.025, 4),
        low=round(prior * 0.97, 4),
        close=round(prior * 0.985, 4),
        adjusted_close=round(prior * 0.985, 4),
        volume=2_200_000,
        source="test OHLCV",
    )
    return bars


def _red_bars(start: date, trading_days: int = 260) -> list[BreakoutBar]:
    bars = _base_bars(start, trading_days=trading_days, drift=-0.0008)
    latest = _next_trading_day(bars[-1].date)
    prior = bars[-1].close
    bars[-1] = BreakoutBar(
        date=latest,
        open=round(prior * 0.985, 4),
        high=round(prior * 0.992, 4),
        low=round(prior * 0.92, 4),
        close=round(prior * 0.928, 4),
        adjusted_close=round(prior * 0.928, 4),
        volume=2_700_000,
        source="test OHLCV",
    )
    return bars


def _neutral_bars(start: date, trading_days: int = 260) -> list[BreakoutBar]:
    bars = _base_bars(start, trading_days=trading_days, drift=0.0002, volume=1_000_000)
    latest = _next_trading_day(bars[-1].date)
    prior = bars[-1].close
    bars[-1] = BreakoutBar(
        date=latest,
        open=round(prior * 0.998, 4),
        high=round(prior * 1.008, 4),
        low=round(prior * 0.992, 4),
        close=round(prior * 1.001, 4),
        adjusted_close=round(prior * 1.001, 4),
        volume=900_000,
        source="test OHLCV",
    )
    return bars


def _repeating_blue_bars(start: date, trading_days: int = 920) -> list[BreakoutBar]:
    bars = _base_bars(start, trading_days=trading_days, drift=0.0008)
    for index in range(240, len(bars), 35):
        prior = bars[index - 1].close
        bars[index] = BreakoutBar(
            date=bars[index].date,
            open=round(prior * 0.982, 4),
            high=round(prior * 1.045, 4),
            low=round(prior * 0.965, 4),
            close=round(prior * 1.038, 4),
            adjusted_close=round(prior * 1.038, 4),
            volume=2_500_000,
            source="test OHLCV",
        )
    return bars


def _bar(day: date, close: float, high: float, low: float, volume: float) -> BreakoutBar:
    return BreakoutBar(
        date=day,
        open=round((high + low) / 2, 4),
        high=round(high, 4),
        low=round(low, 4),
        close=round(close, 4),
        adjusted_close=round(close, 4),
        volume=volume,
        source="test OHLCV",
    )


def _next_trading_day(day: date) -> date:
    current = day + timedelta(days=1)
    while current.weekday() >= 5:
        current += timedelta(days=1)
    return current


if __name__ == "__main__":
    unittest.main()
