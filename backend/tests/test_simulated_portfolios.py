from datetime import date
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.simulated_portfolios import create_simulated_portfolio, list_simulated_portfolios, update_simulated_portfolio_prices
from app.db.session import Base
from app.models.entities import User
from app.schemas.common import SimulatedPortfolioIn, SimulatedPortfolioPriceUpdate


def _trade(ticker: str, amount: float, price: float) -> dict:
    return {
        "ticker": ticker,
        "name": f"{ticker} fund",
        "sleeve": "income" if ticker != "VOO" else "growth",
        "category": "US Tech" if ticker != "VOO" else "Growth Sleeve",
        "yield_pct": 10.0 if ticker != "VOO" else 0,
        "target_weight": amount / 420_000,
        "target_amount": amount,
        "shares": round(amount / price, 4),
        "cost_basis_per_share": price,
        "current_price": price,
        "purchase_date": date(2026, 6, 4),
    }


class SimulatedPortfolioTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.SessionLocal = sessionmaker(bind=engine)

    def test_saves_and_lists_user_scoped_simulated_portfolio(self) -> None:
        db = self.SessionLocal()
        try:
            user = User(email="sim@example.com", password_hash="test")
            other = User(email="other-sim@example.com", password_hash="test")
            db.add_all([user, other])
            db.commit()
            db.refresh(user)
            db.refresh(other)

            tickers = ["QQQI", "GPIQ", "SPYI", "MLPI", "OVL", "IYRI", "XLVI", "CSHI", "CHPY", "VOO", "QQQ", "VUG"]
            payload = SimulatedPortfolioIn(
                cash_amount=420_000,
                trades=[_trade(ticker, 35_000, 100) for ticker in tickers],
            )

            saved = create_simulated_portfolio(payload, user, db)
            other_rows = list_simulated_portfolios(other, db)
            rows = list_simulated_portfolios(user, db)

            self.assertEqual(len(saved.trades), 12)
            self.assertEqual(saved.trades[0].ticker, "QQQI")
            self.assertAlmostEqual(saved.cost_basis, 420_000)
            self.assertAlmostEqual(saved.market_value, 420_000)
            self.assertAlmostEqual(saved.gain_loss, 0)
            self.assertEqual(len(rows), 1)
            self.assertEqual(len(other_rows), 0)
        finally:
            db.close()

    def test_price_patch_recalculates_totals(self) -> None:
        db = self.SessionLocal()
        try:
            user = User(email="sim-prices@example.com", password_hash="test")
            db.add(user)
            db.commit()
            db.refresh(user)

            saved = create_simulated_portfolio(
                SimulatedPortfolioIn(
                    cash_amount=200_000,
                    trades=[
                        _trade("QQQI", 120_000, 100),
                        _trade("VOO", 80_000, 200),
                    ],
                ),
                user,
                db,
            )

            updated = update_simulated_portfolio_prices(
                saved.id,
                SimulatedPortfolioPriceUpdate(prices=[
                    {"ticker": "QQQI", "current_price": 110},
                    {"ticker": "VOO", "current_price": 180},
                ]),
                user,
                db,
            )

            self.assertAlmostEqual(updated.market_value, 204_000)
            self.assertAlmostEqual(updated.gain_loss, 4_000)
            self.assertAlmostEqual(updated.return_pct, 2)
            qqqi = next(trade for trade in updated.trades if trade.ticker == "QQQI")
            self.assertAlmostEqual(qqqi.gain_loss, 12_000)
            self.assertAlmostEqual(qqqi.annual_income, 13_200)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
