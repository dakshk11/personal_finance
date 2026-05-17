from datetime import date
import unittest

from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.portfolios import _last_business_day, import_portfolio, initialize_current_portfolio, preview_trades
from app.db.session import Base
from app.models.entities import Portfolio, TaxLot, Trade, User
from app.schemas.common import (
    GenerateTradesRequest,
    PortfolioImportHoldingIn,
    PortfolioImportRequest,
    PortfolioImportTaxLotIn,
    PortfolioInitializationRequest,
)


class CurrentPortfolioTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def _seed_portfolio(self):
        db = self.Session()
        user = User(email="current@example.com", password_hash="hash")
        db.add(user)
        db.commit()
        db.refresh(user)
        portfolio = Portfolio(user_id=user.id, name="QTOP current", index_symbol="QTOP", starting_value=100_000, cash=100_000)
        db.add(portfolio)
        db.commit()
        db.refresh(portfolio)
        return db, user, portfolio

    def test_last_business_day_uses_friday_for_saturday(self) -> None:
        self.assertEqual(_last_business_day(date(2026, 5, 9)), date(2026, 5, 8))

    def test_initialize_current_is_idempotent_and_refuses_reset(self) -> None:
        db, user, portfolio = self._seed_portfolio()

        result = initialize_current_portfolio(
            portfolio.id,
            PortfolioInitializationRequest(as_of_date=date(2026, 5, 8)),
            user,
            db,
        )

        self.assertEqual(result.as_of_date, date(2026, 5, 8))
        self.assertGreater(result.seeded_positions, 0)
        self.assertLessEqual(result.invested_value, portfolio.starting_value)
        self.assertGreaterEqual(result.portfolio.cash, 0)
        self.assertEqual(db.scalar(select(func.count(TaxLot.id)).where(TaxLot.portfolio_id == portfolio.id)), result.seeded_positions)
        with self.assertRaises(HTTPException) as raised:
            initialize_current_portfolio(
                portfolio.id,
                PortfolioInitializationRequest(as_of_date=date(2026, 5, 8)),
                user,
                db,
            )
        self.assertEqual(raised.exception.status_code, 409)

    def test_trade_preview_does_not_mutate_portfolio_history(self) -> None:
        db, user, portfolio = self._seed_portfolio()
        initialize_current_portfolio(
            portfolio.id,
            PortfolioInitializationRequest(as_of_date=date(2026, 5, 8)),
            user,
            db,
        )
        before_cash = portfolio.cash
        before_lots = db.scalar(select(func.count(TaxLot.id)).where(TaxLot.portfolio_id == portfolio.id))
        before_trades = db.scalar(select(func.count(Trade.id)).where(Trade.portfolio_id == portfolio.id))

        result = preview_trades(
            portfolio.id,
            GenerateTradesRequest(as_of_date=date(2026, 5, 8), direct_index_model="risk_score"),
            user,
            db,
        )

        db.refresh(portfolio)
        self.assertEqual(portfolio.cash, before_cash)
        self.assertEqual(db.scalar(select(func.count(TaxLot.id)).where(TaxLot.portfolio_id == portfolio.id)), before_lots)
        self.assertEqual(db.scalar(select(func.count(Trade.id)).where(Trade.portfolio_id == portfolio.id)), before_trades)
        self.assertEqual(result.direct_index_model, "risk_score")
        self.assertTrue(any("Preview only" in warning for warning in result.warnings))

    def test_import_portfolio_creates_tax_lots_and_selectable_portfolio(self) -> None:
        db = self.Session()
        user = User(email="import@example.com", password_hash="hash")
        db.add(user)
        db.commit()
        db.refresh(user)

        result = import_portfolio(
            PortfolioImportRequest(
                name="Imported taxable",
                index_symbol="SPY",
                cash=250,
                holdings=[
                    PortfolioImportHoldingIn(symbol="AAPL", name="Apple", shares=10, price=180, market_value=1800),
                    PortfolioImportHoldingIn(symbol="BRK/B", name="Berkshire", shares=5, price=410, market_value=2050),
                ],
                tax_lots=[
                    PortfolioImportTaxLotIn(symbol="AAPL", acquisition_date=date(2024, 1, 3), shares=10, cost_basis_per_share=150),
                    PortfolioImportTaxLotIn(symbol="BRK/B", acquisition_date=date(2023, 6, 1), shares=5, cost_basis_per_share=300),
                ],
            ),
            user,
            db,
        )

        self.assertEqual(result.portfolio.name, "Imported taxable")
        self.assertEqual(result.portfolio.index_symbol, "SPY")
        self.assertEqual(result.portfolio.starting_value, 4100)
        self.assertEqual(result.portfolio.cash, 250)
        self.assertEqual(result.imported_positions, 2)
        self.assertEqual(result.imported_tax_lots, 2)
        self.assertEqual(db.scalar(select(func.count(TaxLot.id)).where(TaxLot.portfolio_id == result.portfolio.id)), 2)
        self.assertIsNotNone(db.scalar(select(TaxLot).where(TaxLot.portfolio_id == result.portfolio.id, TaxLot.symbol == "BRK.B")))

    def test_import_portfolio_requires_holdings_or_lots(self) -> None:
        db = self.Session()
        user = User(email="empty-import@example.com", password_hash="hash")
        db.add(user)
        db.commit()
        db.refresh(user)

        with self.assertRaises(HTTPException) as raised:
            import_portfolio(PortfolioImportRequest(), user, db)
        self.assertEqual(raised.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
