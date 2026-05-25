from datetime import date, timedelta
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.entities import User
from app.services import option_strategy
from app.services.market_history import MarketHistory, MarketHistoryBar


class OptionStrategyTests(unittest.TestCase):
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
        user = User(email="wheel@example.com", password_hash="hash")
        db.add(user)
        db.commit()
        db.refresh(user)
        return db, user

    def test_scan_returns_api_ready_signal_candidates(self) -> None:
        db, user = self._seed_user()

        with (
            patch("app.services.option_strategy.get_market_history", side_effect=_mock_history),
            patch("app.services.option_strategy._fetch_yfinance_put_contracts", side_effect=_mock_contracts),
            patch("app.services.option_strategy._fetch_yfinance_earnings_date", return_value=None),
        ):
            result = option_strategy.run_scan(db, user.id)

        self.assertIsNotNone(result["scan_run_id"])
        self.assertEqual(len(result["signals"]), len(option_strategy.default_universe()))
        first = result["signals"][0]
        self.assertIn(first["status"], {"approved", "blocked"})
        self.assertEqual(first["action"], "sell_put")
        self.assertIn(first["provider"], {"yfinance", "deterministic fallback"})
        self.assertIsInstance(first["score"], float)
        self.assertIn("deep_dive_summary", first)
        self.assertIn("if_assigned_basis", first)
        self.assertGreater(first["underlying_price"], 0)
        self.assertGreater(first["collateral"], 0)
        self.assertGreaterEqual(len(first["checklist"]), 12)
        self.assertTrue(all("passed" in item for item in first["checklist"]))

        latest = option_strategy.list_signals(db, user.id)
        self.assertEqual(len(latest), len(option_strategy.default_universe()))

    def test_default_universe_and_daily_scan_cache(self) -> None:
        db, user = self._seed_user()
        universe = option_strategy.default_universe()
        symbols = {item["symbol"] for item in universe}

        self.assertTrue({"QQQ", "SPY", "SMH", "XLE", "XLI", "UPRO", "TQQQ", "SOXL", "NVDA", "AAPL"}.issubset(symbols))
        leveraged = [item for item in universe if item["symbol"] in {"UPRO", "TQQQ", "SOXL"}]
        self.assertTrue(all(item["group"] == "Leveraged ETFs" for item in leveraged))
        self.assertEqual(len(symbols), len(universe))

        with (
            patch("app.services.option_strategy.get_market_history", side_effect=_mock_history),
            patch("app.services.option_strategy._fetch_yfinance_put_contracts", side_effect=_mock_contracts),
            patch("app.services.option_strategy._fetch_yfinance_earnings_date", return_value=None),
        ):
            first = option_strategy.run_scan(db, user.id, force=False)
            cached = option_strategy.run_scan(db, user.id, force=False)
            forced = option_strategy.run_scan(db, user.id, force=True)

        self.assertEqual(first["scan_run_id"], cached["scan_run_id"])
        self.assertNotEqual(first["scan_run_id"], forced["scan_run_id"])

    def test_yfinance_put_row_parser(self) -> None:
        expiration = date.today() + timedelta(days=38)
        row = {
            "strike": 92,
            "bid": 4.8,
            "ask": 5.2,
            "lastPrice": 5,
            "impliedVolatility": 0.58,
            "openInterest": 750,
            "volume": 120,
        }

        contract = option_strategy._put_contract_from_yfinance_row(row, expiration, 38)

        self.assertIsNotNone(contract)
        assert contract is not None
        self.assertEqual(contract.provider, "yfinance")
        self.assertEqual(contract.mid, 5)
        self.assertEqual(contract.open_interest, 750)

    def test_earnings_spread_and_open_interest_filters_block_candidate(self) -> None:
        db, user = self._seed_user()
        option_strategy.update_config(db, user.id, {"account_value": 2_000_000, "min_iv": 0.30, "min_premium_yield": 0.03, "rsi_max": 100})

        with (
            patch("app.services.option_strategy.get_market_history", side_effect=_green_red_day_history),
            patch("app.services.option_strategy._fetch_yfinance_put_contracts", side_effect=_illiquid_contracts),
            patch("app.services.option_strategy._fetch_yfinance_earnings_date", return_value=date.today() + timedelta(days=3)),
        ):
            result = option_strategy.run_scan(db, user.id)

        first = result["signals"][0]
        self.assertEqual(first["status"], "blocked")
        self.assertIn("Earnings inside 7 days", first["blocked_reasons"])
        self.assertIn("DTE/delta/liquidity filter failed", first["blocked_reasons"])

    def test_scan_can_emit_approved_candidate_when_checklist_passes(self) -> None:
        db, user = self._seed_user()
        option_strategy.update_config(db, user.id, {"account_value": 2_000_000, "min_iv": 0.30, "min_premium_yield": 0.03, "rsi_max": 100})

        with (
            patch("app.services.option_strategy.get_market_history", side_effect=_green_red_day_history),
            patch("app.services.option_strategy._fetch_yfinance_put_contracts", side_effect=_mock_contracts),
            patch("app.services.option_strategy._fetch_yfinance_earnings_date", return_value=None),
        ):
            result = option_strategy.run_scan(db, user.id)

        approved = [signal for signal in result["signals"] if signal["status"] == "approved"]
        self.assertGreater(len(approved), 0)
        self.assertEqual(approved[0]["action"], "sell_put")
        self.assertTrue(all(item["passed"] for item in approved[0]["checklist"]))
        self.assertEqual(approved[0]["blocked_reasons"], [])

    def test_position_lifecycle_creates_profit_and_assignment_alerts(self) -> None:
        db, user = self._seed_user()

        with (
            patch("app.services.option_strategy.get_market_history", side_effect=_mock_history),
            patch("app.services.option_strategy._fetch_yfinance_put_contracts", side_effect=_mock_contracts),
            patch("app.services.option_strategy._fetch_yfinance_earnings_date", return_value=None),
        ):
            signal = option_strategy.run_scan(db, user.id)["signals"][0]

        position = option_strategy.record_position_event(
            db,
            user.id,
            {"event": "accepted_put", "signal_candidate_id": signal["id"], "candidate": signal},
        )

        self.assertEqual(position["status"], "put_open")
        alerts = option_strategy.list_alerts(db, user.id)
        self.assertEqual(alerts[0]["kind"], "profit_50")
        self.assertEqual(alerts[0]["symbol"], position["symbol"])
        self.assertAlmostEqual(alerts[0]["target_price"], round(signal["mid"] * 0.5, 2))

        assigned = option_strategy.record_position_event(db, user.id, {"event": "assigned", "position_id": position["id"]})

        self.assertEqual(assigned["status"], "assigned")
        alert_kinds = {alert["kind"] for alert in option_strategy.list_alerts(db, user.id)}
        self.assertIn("covered_call_candidate", alert_kinds)

    def test_roll_review_requires_under_14_dte_and_net_credit(self) -> None:
        today = date.today()
        position = {"status": "put_open", "expiration": today + timedelta(days=10), "current_price": 2.0}

        eligible = option_strategy.roll_review_candidate(position, as_of=today, next_cycle_credit=2.35)
        too_far = option_strategy.roll_review_candidate({**position, "expiration": today + timedelta(days=20)}, as_of=today, next_cycle_credit=2.35)
        debit = option_strategy.roll_review_candidate(position, as_of=today, next_cycle_credit=1.9)

        self.assertTrue(eligible["eligible"])
        self.assertEqual(eligible["net_credit"], 0.35)
        self.assertFalse(too_far["eligible"])
        self.assertFalse(debit["eligible"])


def _mock_history(db: object, symbol: str, start_date: date, end_date: date, force_refresh: bool = False) -> MarketHistory:
    del db, force_refresh
    bars: list[MarketHistoryBar] = []
    current = start_date
    trading_day = 0
    price = 100 + len(symbol) * 7
    while current <= end_date:
        if current.weekday() < 5:
            price *= 1.0026
            if (end_date - current).days <= 12:
                price *= 0.986
            bars.append(MarketHistoryBar(date=current, close=round(price, 4), adjusted_close=round(price, 4), dividend=0, source="test"))
            trading_day += 1
        current += timedelta(days=1)
    return MarketHistory(
        symbol=symbol,
        name=symbol,
        benchmark=symbol,
        category="test",
        requested_start_date=start_date,
        requested_end_date=end_date,
        start_date=bars[0].date,
        end_date=bars[-1].date,
        bars=bars,
        warnings=[],
    )


def _green_red_day_history(db: object, symbol: str, start_date: date, end_date: date, force_refresh: bool = False) -> MarketHistory:
    del db, force_refresh
    bars: list[MarketHistoryBar] = []
    current = start_date
    price = 90 + len(symbol) * 4
    while current <= end_date:
        if current.weekday() < 5:
            price *= 1.0022
            if (end_date - current).days <= 3:
                price *= 0.994
            bars.append(MarketHistoryBar(date=current, close=round(price, 4), adjusted_close=round(price, 4), dividend=0, source="test"))
        current += timedelta(days=1)
    return MarketHistory(
        symbol=symbol,
        name=symbol,
        benchmark=symbol,
        category="test",
        requested_start_date=start_date,
        requested_end_date=end_date,
        start_date=bars[0].date,
        end_date=bars[-1].date,
        bars=bars,
        warnings=[],
    )


def _mock_contracts(symbol: str, latest_close: float, config: dict[str, object], today: date) -> list[option_strategy.PutContract]:
    del symbol, config
    expiration = today + timedelta(days=38)
    while expiration.weekday() != 4:
        expiration += timedelta(days=1)
    dte = (expiration - today).days
    strike = round(latest_close * 0.92, 2)
    mid = round(strike * 0.055, 2)
    return [
        option_strategy.PutContract(
            strike=strike,
            expiration=expiration,
            dte=dte,
            bid=round(mid * 0.97, 2),
            ask=round(mid * 1.03, 2),
            mid=mid,
            iv=0.58,
            open_interest=750,
            volume=120,
            provider="yfinance",
        )
    ]


def _illiquid_contracts(symbol: str, latest_close: float, config: dict[str, object], today: date) -> list[option_strategy.PutContract]:
    del symbol, config
    expiration = today + timedelta(days=38)
    while expiration.weekday() != 4:
        expiration += timedelta(days=1)
    dte = (expiration - today).days
    strike = round(latest_close * 0.92, 2)
    mid = round(strike * 0.055, 2)
    return [
        option_strategy.PutContract(
            strike=strike,
            expiration=expiration,
            dte=dte,
            bid=round(mid * 0.80, 2),
            ask=round(mid * 1.20, 2),
            mid=mid,
            iv=0.58,
            open_interest=20,
            volume=5,
            provider="yfinance",
        )
    ]


if __name__ == "__main__":
    unittest.main()
