from datetime import date
import unittest

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.api.sector_rotation import create_accepted_allocation, list_accepted_allocations, update_accepted_allocation
from app.db.session import Base
from app.models.entities import User
from app.schemas.common import SectorRotationAcceptedAllocationIn, SectorRotationAcceptedAllocationUpdate
from app.services.sector_rotation_engine import get_live_allocation, get_selection_history, run_backtest


class SectorRotationWeightingTests(unittest.TestCase):
    def test_equal_weight_preserves_existing_annual_return(self) -> None:
        result = run_backtest(100_000, "equal")
        annual = next(row for row in result if row.id == "ALGO_ANNUAL_LTCG")
        first = annual.snapshots[0]

        self.assertEqual(first.sectors_held, ["XLK", "XLV", "XLP", "XLRE"])
        self.assertAlmostEqual(first.period_return_pct, 5.5)
        self.assertAlmostEqual(sum(first.sector_weights.values()), 1.0)
        self.assertTrue(all(weight == 0.25 for weight in first.sector_weights.values()))

    def test_market_weight_normalizes_selected_sector_weights(self) -> None:
        result = run_backtest(100_000, "market_weight")
        annual = next(row for row in result if row.id == "ALGO_ANNUAL_LTCG")
        first = annual.snapshots[0]

        self.assertAlmostEqual(sum(first.sector_weights.values()), 1.0, delta=0.001)
        self.assertNotEqual(first.sector_weights["XLK"], first.sector_weights["XLRE"])
        self.assertNotEqual(first.period_return_pct, 5.5)

    def test_live_allocation_market_weight_amounts_sum_to_cash(self) -> None:
        allocations, signals, guidance = get_live_allocation(100_000, "annual", "market_weight")

        self.assertEqual(signals["weighting_method"], "market_weight")
        self.assertAlmostEqual(sum(row.weight for row in allocations), 1.0, places=4)
        self.assertAlmostEqual(sum(row.dollar_amount for row in allocations), 100_000, delta=1)
        self.assertIn("S&P 500 sector market weights", guidance)

    def test_selection_history_returns_weights_for_each_mode(self) -> None:
        equal = get_selection_history("equal")[0]
        market = get_selection_history("market_weight")[0]

        self.assertEqual(equal["weighting_method"], "equal")
        self.assertEqual(market["weighting_method"], "market_weight")
        self.assertAlmostEqual(sum(equal["sector_weights"].values()), 1.0)
        self.assertAlmostEqual(sum(market["sector_weights"].values()), 1.0, delta=0.001)
        self.assertNotEqual(equal["algo_return"], market["algo_return"])


class SectorRotationAcceptedAllocationTests(unittest.TestCase):
    def setUp(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        self.SessionLocal = sessionmaker(bind=engine)

    def test_saves_accepted_allocation_with_multiple_trades(self) -> None:
        db = self.SessionLocal()
        try:
            user = User(email="sector-test@example.com", password_hash="test")
            db.add(user)
            db.commit()
            db.refresh(user)

            payload = SectorRotationAcceptedAllocationIn(
                account_type="tax_deferred",
                time_frame="annual",
                weighting_method="market_weight",
                cash_amount=100_000,
                as_of_year=2026,
                trades=[
                    {
                        "ticker": "xlk",
                        "sector_name": "Technology",
                        "target_weight": 0.6,
                        "target_amount": 60_000,
                        "shares": 19,
                        "cost_basis_per_share": 174,
                        "current_price": 174,
                        "purchase_date": date(2026, 6, 2),
                    },
                    {
                        "ticker": "XLF",
                        "sector_name": "Financials",
                        "target_weight": 0.4,
                        "target_amount": 40_000,
                        "shares": 10,
                        "cost_basis_per_share": 50,
                        "current_price": 55,
                        "purchase_date": date(2026, 6, 2),
                    },
                ],
            )

            saved = create_accepted_allocation(payload, user, db)
            rows = list_accepted_allocations(user, db)

            self.assertEqual(saved.weighting_method, "market_weight")
            self.assertEqual(len(saved.trades), 2)
            self.assertEqual(saved.trades[0].ticker, "XLK")
            self.assertAlmostEqual(saved.trades[0].market_value, 3306)
            self.assertAlmostEqual(saved.trades[0].cost_basis, 3306)
            self.assertAlmostEqual(saved.trades[0].gain_loss, 0)
            self.assertEqual(len(rows), 1)
            self.assertEqual(len(rows[0].trades), 2)
            self.assertAlmostEqual(rows[0].trades[1].gain_loss, 50)

            updated = update_accepted_allocation(
                saved.id,
                SectorRotationAcceptedAllocationUpdate(
                    rebalance_date=date(2026, 6, 3),
                    rebalance_status="partial",
                    rebalance_notes="Bought XLK, changed XLF size.",
                ),
                user,
                db,
            )

            self.assertEqual(updated.rebalance_date, date(2026, 6, 3))
            self.assertEqual(updated.rebalance_status, "partial")
            self.assertEqual(updated.rebalance_notes, "Bought XLK, changed XLF size.")
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
