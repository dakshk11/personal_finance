from datetime import date, timedelta
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.entities import BreakoutOhlcvBar, User
from app.services import breakout_scanner
from app.services.breakout_scanner import BreakoutBar, BreakoutUniverseItem


class BreakoutScannerTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def _seed_user(self, email: str = "breakout@example.com") -> tuple[object, User]:
        db = self.Session()
        user = User(email=email, password_hash="hash")
        db.add(user)
        db.commit()
        db.refresh(user)
        return db, user

    def test_sp500_universe_falls_back_with_clear_label(self) -> None:
        db, _ = self._seed_user()
        with patch("app.services.breakout_scanner._fetch_sp500_universe", side_effect=RuntimeError("offline")):
            universe = breakout_scanner.load_sp500_universe(db, force_refresh=True)

        self.assertEqual(universe["cache_status"], "fallback")
        self.assertGreater(universe["count"], 50)
        self.assertNotIn("QQQ", {item["symbol"] for item in universe["items"]})
        self.assertIn("fallback", " ".join(universe["warnings"]).lower())

    def test_ohlcv_cache_fetches_once_then_reuses_rows(self) -> None:
        db, _ = self._seed_user()
        start = date.today() - timedelta(days=360)
        end = date.today()
        bars = _ceiling_bars(start, trading_days=260)

        with patch("app.services.breakout_scanner._fetch_yfinance_ohlcv_batch", return_value={"AAA": bars}) as fetch:
            first, first_warnings = breakout_scanner.load_ohlcv_histories(db, ["AAA"], start, end)
            second, second_warnings = breakout_scanner.load_ohlcv_histories(db, ["AAA"], start, end)

        self.assertEqual(fetch.call_count, 1)
        self.assertIn("AAA", first)
        self.assertIn("AAA", second)
        self.assertEqual(first_warnings, [])
        self.assertEqual(second_warnings, [])
        self.assertEqual(db.scalar(select(func.count(BreakoutOhlcvBar.id))), len(bars))

    def test_detectors_find_ceiling_momentum_and_near_breakouts(self) -> None:
        item = BreakoutUniverseItem("AAA", "AAA Inc", "Technology", "test", "test")
        base_config = breakout_scanner.normalize_scan_config({"min_avg_dollar_volume": 0, "require_above_sma200": False, "min_relative_volume": 1.1})

        ceiling = breakout_scanner.detect_breakout_setups(item, _ceiling_bars(date.today() - timedelta(days=360)), base_config)
        momentum = breakout_scanner.detect_breakout_setups(item, _momentum_bars(date.today() - timedelta(days=360)), base_config)
        near = breakout_scanner.detect_breakout_setups(item, _near_breakout_bars(date.today() - timedelta(days=360)), base_config)

        self.assertIn("ceiling_breakout", {setup["detector_type"] for setup in ceiling})
        self.assertIn("momentum_breakout", {setup["detector_type"] for setup in momentum})
        self.assertIn("near_breakout", {setup["detector_type"] for setup in near})

    def test_relative_volume_and_sma_filters_block_candidate(self) -> None:
        item = BreakoutUniverseItem("AAA", "AAA Inc", "Technology", "test", "test")
        config = breakout_scanner.normalize_scan_config({"min_avg_dollar_volume": 0, "require_above_sma200": True, "min_relative_volume": 3.0})
        low_volume_bars = _ceiling_bars(date.today() - timedelta(days=360), latest_volume=900_000)

        setups = breakout_scanner.detect_breakout_setups(item, low_volume_bars, config)

        self.assertEqual(setups, [])

    def test_daily_scan_cache_force_refresh_and_user_scope(self) -> None:
        db, user = self._seed_user()
        _, second_user = self._seed_user("other-breakout@example.com")
        universe = _universe_out()
        histories = {"AAA": _ceiling_bars(date.today() - timedelta(days=360)), "BBB": _momentum_bars(date.today() - timedelta(days=360))}

        with (
            patch("app.services.breakout_scanner.load_sp500_universe", return_value=universe),
            patch("app.services.breakout_scanner.load_ohlcv_histories", return_value=(histories, [])),
        ):
            first = breakout_scanner.run_breakout_scan(db, user.id, {"max_symbols": 2, "min_avg_dollar_volume": 0, "require_above_sma200": False})
            cached = breakout_scanner.run_breakout_scan(db, user.id, {"max_symbols": 2, "min_avg_dollar_volume": 0, "require_above_sma200": False})
            forced = breakout_scanner.run_breakout_scan(db, user.id, {"max_symbols": 2, "min_avg_dollar_volume": 0, "require_above_sma200": False}, force=True)
            other = breakout_scanner.run_breakout_scan(db, second_user.id, {"max_symbols": 2, "min_avg_dollar_volume": 0, "require_above_sma200": False})

        self.assertEqual(first["scan_run_id"], cached["scan_run_id"])
        self.assertNotEqual(first["scan_run_id"], forced["scan_run_id"])
        self.assertNotEqual(first["scan_run_id"], other["scan_run_id"])
        self.assertGreaterEqual(len(first["signals"]), 1)

    def test_custom_symbols_append_to_scan_universe(self) -> None:
        db, user = self._seed_user()
        universe = _universe_out()
        histories = {
            "AAA": _ceiling_bars(date.today() - timedelta(days=360)),
            "NVDA": _momentum_bars(date.today() - timedelta(days=360)),
        }

        with (
            patch("app.services.breakout_scanner.load_sp500_universe", return_value=universe),
            patch("app.services.breakout_scanner.load_ohlcv_histories", return_value=(histories, [])) as history_loader,
        ):
            result = breakout_scanner.run_breakout_scan(
                db,
                user.id,
                {"max_symbols": 1, "custom_symbols": ["nvda", "AAA", "nvda"], "min_avg_dollar_volume": 0, "require_above_sma200": False, "min_relative_volume": 0.5},
            )

        self.assertEqual(history_loader.call_args.args[1], ["AAA", "NVDA"])
        self.assertEqual(result["scanned_symbols"], 2)
        self.assertEqual(result["config"]["custom_symbols"], ["NVDA", "AAA"])
        self.assertIn("NVDA", {signal["symbol"] for signal in result["signals"]})

    def test_backtest_returns_distribution_rows(self) -> None:
        db, user = self._seed_user()
        universe = _universe_out()
        histories = {"AAA": _momentum_bars(date.today() - timedelta(days=1300), trading_days=920)}

        with (
            patch("app.services.breakout_scanner.load_sp500_universe", return_value=universe),
            patch("app.services.breakout_scanner.load_ohlcv_histories", return_value=(histories, [])),
        ):
            result = breakout_scanner.run_breakout_backtest(
                db,
                user.id,
                {"detector": "momentum_breakout", "years": 3, "max_symbols": 1, "min_avg_dollar_volume": 0, "require_above_sma200": False, "min_relative_volume": 0.5},
            )

        self.assertEqual(result["detector"], "momentum_breakout")
        self.assertEqual([row["horizon_days"] for row in result["horizons"]], [5, 10, 20, 60])
        self.assertGreater(result["signal_count"], 0)
        self.assertTrue(any(row["win_rate"] is not None for row in result["horizons"]))


def _universe_out() -> dict[str, object]:
    return {
        "items": [
            {"symbol": "AAA", "company_name": "AAA Inc", "sector": "Technology", "source": "test", "source_url": "test"},
            {"symbol": "BBB", "company_name": "BBB Inc", "sector": "Industrials", "source": "test", "source_url": "test"},
        ],
        "count": 2,
        "source": "test",
        "source_url": "test",
        "cache_status": "fresh",
        "retrieved_at": date.today().isoformat(),
        "warnings": [],
    }


def _ceiling_bars(start: date, trading_days: int = 260, latest_volume: float = 2_800_000) -> list[BreakoutBar]:
    bars: list[BreakoutBar] = []
    current = start
    index = 0
    while len(bars) < trading_days:
        if current.weekday() < 5:
            price = min(98.8, 82 + index * 0.075)
            high = price + 0.8
            if index in {80, 125, 170, 215}:
                high = 100.2
                price = 98.7
            volume = 1_000_000
            bars.append(_bar(current, price, high, price - 1.0, volume))
            index += 1
        current += timedelta(days=1)
    latest_date = bars[-1].date + timedelta(days=1)
    while latest_date.weekday() >= 5:
        latest_date += timedelta(days=1)
    bars[-1] = _bar(latest_date, 103.4, 104.2, 101.5, latest_volume)
    return bars


def _near_breakout_bars(start: date, trading_days: int = 260) -> list[BreakoutBar]:
    bars = _ceiling_bars(start, trading_days=trading_days, latest_volume=1_250_000)
    bars[-1] = _bar(bars[-1].date, 98.9, 99.4, 97.7, 1_250_000)
    return bars


def _momentum_bars(start: date, trading_days: int = 260) -> list[BreakoutBar]:
    bars: list[BreakoutBar] = []
    current = start
    price = 42.0
    while len(bars) < trading_days:
        if current.weekday() < 5:
            price *= 1.0024
            volume = 1_000_000
            if len(bars) % 24 == 0:
                volume = 1_700_000
            bars.append(_bar(current, price, price * 1.01, price * 0.99, volume))
        current += timedelta(days=1)
    bars[-1] = _bar(bars[-1].date, bars[-2].close * 1.045, bars[-2].close * 1.055, bars[-2].close * 1.02, 2_600_000)
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


if __name__ == "__main__":
    unittest.main()
