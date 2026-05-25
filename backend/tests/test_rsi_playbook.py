from datetime import date, timedelta
import json
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.entities import PortfolioSyncSnapshot, User
from app.services import rsi_playbook
from app.services.market_history import MarketHistory, MarketHistoryBar


class RSIPlaybookTests(unittest.TestCase):
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
        user = User(email="rsi@example.com", password_hash="hash")
        db.add(user)
        db.commit()
        db.refresh(user)
        return db, user

    def test_rsi_classification_rules_match_playbook(self) -> None:
        self.assertEqual(rsi_playbook.classify_rsi(72)["action"], "Go to cash")
        self.assertEqual(rsi_playbook.classify_rsi(60)["action"], "Sell puts far OTM")
        self.assertEqual(rsi_playbook.classify_rsi(50)["action"], "Sell puts ATM")
        self.assertEqual(rsi_playbook.classify_rsi(38)["action"], "Buy the stock")
        self.assertEqual(rsi_playbook.classify_rsi(25)["action"], "Buy LEAP aggressively")
        self.assertEqual(rsi_playbook.classify_rsi(67)["action"], "Wait / cash watch")

    def test_combined_universe_includes_wheel_and_portfolio_sync_symbols(self) -> None:
        db, user = self._seed_user()
        db.add(
            PortfolioSyncSnapshot(
                user_id=user.id,
                provider="snaptrade",
                accounts_json="[]",
                holdings_json=json.dumps(
                    [
                        {"symbol": "AAPL", "market_value": 20_000},
                        {"symbol": "SHOP", "market_value": 5_000},
                    ]
                ),
                warnings_json="[]",
            )
        )
        db.commit()

        universe = rsi_playbook._combined_universe(db, user.id)

        self.assertIn("AAPL", universe)
        self.assertIn("SHOP", universe)
        self.assertIn("Wheel Strategy", universe["AAPL"].sources)
        self.assertIn("Portfolio Sync", universe["AAPL"].sources)
        self.assertEqual(universe["SHOP"].sources, {"Portfolio Sync"})
        self.assertAlmostEqual(universe["SHOP"].portfolio_weight or 0, 0.2)

    def test_scan_returns_chart_and_summary_for_each_symbol(self) -> None:
        db, user = self._seed_user()
        with (
            patch("app.services.rsi_playbook.default_universe", return_value=[{"symbol": "AAA", "name": "AAA Inc", "sector": "Tech", "group": "Wheel"}]),
            patch("app.services.rsi_playbook.get_market_history", side_effect=_mock_history),
        ):
            result = rsi_playbook.scan_rsi_playbook(db, user.id, max_symbols=1)

        self.assertEqual(result["universe_count"], 1)
        signal = result["signals"][0]
        self.assertEqual(signal["symbol"], "AAA")
        self.assertIn("RSI", signal["level"])
        self.assertIn("playbook action", signal["summary"])
        self.assertGreater(len(signal["chart"]), 100)
        self.assertIsNotNone(signal["ema21"])
        self.assertIsNotNone(signal["rsi"])


def _mock_history(db: object, symbol: str, start_date: date, end_date: date, force_refresh: bool = False) -> MarketHistory:
    del db, force_refresh
    bars: list[MarketHistoryBar] = []
    current = start_date
    price = 100.0
    while current <= end_date:
        if current.weekday() < 5:
            price *= 1.002
            bars.append(MarketHistoryBar(date=current, close=price, adjusted_close=price, dividend=0, source="test history"))
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


if __name__ == "__main__":
    unittest.main()
