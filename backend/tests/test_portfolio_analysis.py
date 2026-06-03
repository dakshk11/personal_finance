from datetime import date
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models.entities import PriceBar, SecurityMetricSnapshot
from app.schemas.common import PortfolioAnalyzerHoldingIn
from app.services.portfolio_analysis import analyze_portfolio_holdings


class PortfolioAnalysisTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)

    def test_analysis_uses_daily_cache_and_focus_threshold(self) -> None:
        db = self.Session()
        holdings = [
            PortfolioAnalyzerHoldingIn(symbol="AAPL", shares=100, cost_basis_per_share=90),
            PortfolioAnalyzerHoldingIn(symbol="MSFT", shares=50, cost_basis_per_share=260),
            PortfolioAnalyzerHoldingIn(symbol="IBM", shares=0.01, cost_basis_per_share=100),
        ]

        result = analyze_portfolio_holdings(
            db,
            holdings,
            min_weight_percent=1,
            as_of_date=date(2026, 5, 8),
            allow_external=False,
        )

        self.assertEqual(result.as_of_date, date(2026, 5, 8))
        self.assertEqual(result.hidden_holding_count, 1)
        self.assertEqual(result.analyzed_holding_count, 2)
        self.assertGreater(result.total_market_value, 0)
        self.assertTrue(all(row.forward_pe is None for row in result.holdings))
        self.assertTrue(all("deterministic" in row.data_source for row in result.holdings))
        self.assertTrue(all("unavailable" in row.data_source for row in result.holdings))
        self.assertEqual(db.scalar(select(func.count(PriceBar.id))), 3)
        self.assertEqual(db.scalar(select(func.count(SecurityMetricSnapshot.id))), 3)

        analyze_portfolio_holdings(
            db,
            holdings,
            min_weight_percent=1,
            as_of_date=date(2026, 5, 8),
            allow_external=False,
        )
        self.assertEqual(db.scalar(select(func.count(PriceBar.id))), 3)
        self.assertEqual(db.scalar(select(func.count(SecurityMetricSnapshot.id))), 3)

    def test_duplicate_symbols_are_aggregated(self) -> None:
        db = self.Session()
        result = analyze_portfolio_holdings(
            db,
            [
                PortfolioAnalyzerHoldingIn(symbol="BRK/B", shares=1, cost_basis_per_share=300),
                PortfolioAnalyzerHoldingIn(symbol="BRK.B", shares=2, cost_basis_per_share=350),
            ],
            min_weight_percent=0,
            as_of_date=date(2026, 5, 8),
            allow_external=False,
        )

        self.assertEqual(len(result.holdings), 1)
        self.assertEqual(result.holdings[0].symbol, "BRK.B")
        self.assertEqual(result.holdings[0].shares, 3)
        self.assertAlmostEqual(result.holdings[0].cost_basis_per_share, 333.3333, places=3)

    def test_external_price_replaces_cached_deterministic_fallback(self) -> None:
        db = self.Session()
        db.add(
            PriceBar(
                symbol="AAPL",
                price_date=date(2026, 5, 20),
                close=343.26,
                adjusted_close=343.26,
                dividend=0,
                split_ratio=1,
                source="deterministic offline fallback",
            )
        )
        db.commit()

        with patch("app.services.market_data._fetch_latest_prices", return_value={"AAPL": 302.25}):
            result = analyze_portfolio_holdings(
                db,
                [PortfolioAnalyzerHoldingIn(symbol="AAPL", shares=120, cost_basis_per_share=90)],
                min_weight_percent=0,
                as_of_date=date(2026, 5, 20),
                allow_external=True,
            )

        self.assertEqual(result.holdings[0].price, 302.25)
        self.assertEqual(result.holdings[0].market_value, 36270)
        row = db.scalar(select(PriceBar).where(PriceBar.symbol == "AAPL", PriceBar.price_date == date(2026, 5, 20)))
        self.assertIsNotNone(row)
        self.assertEqual(row.adjusted_close, 302.25)
        self.assertEqual(row.source, "stooq daily close cache")


if __name__ == "__main__":
    unittest.main()
