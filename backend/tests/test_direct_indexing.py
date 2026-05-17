from datetime import date
import unittest

from app.services.direct_indexing import Holding, Position, calculate_tracking_metrics, generate_rebalance_trades, normalize_holdings


class DirectIndexingTests(unittest.TestCase):
    def test_normalize_holdings_removes_exclusions_and_rescales(self) -> None:
        holdings = [
            Holding("AAPL", "Apple", 0.50, "Tech"),
            Holding("MSFT", "Microsoft", 0.30, "Tech"),
            Holding("XOM", "Exxon", 0.20, "Energy"),
        ]

        normalized = normalize_holdings(holdings, {"XOM"})

        self.assertEqual([item.symbol for item in normalized], ["AAPL", "MSFT"])
        self.assertAlmostEqual(sum(item.weight for item in normalized), 1.0)
        self.assertAlmostEqual(normalized[0].weight, 0.625)

    def test_tracking_metrics_penalize_active_share_and_cash(self) -> None:
        holdings = [Holding("AAPL", "Apple", 0.50), Holding("MSFT", "Microsoft", 0.50)]
        positions = [Position("AAPL", shares=10, price=50)]

        metrics = calculate_tracking_metrics(holdings, positions, cash=500)

        self.assertGreater(metrics.tracking_difference, 0)
        self.assertLess(metrics.tracking_score, 100)

    def test_rebalance_generates_buy_and_sell_orders(self) -> None:
        holdings = [Holding("AAPL", "Apple", 0.60), Holding("MSFT", "Microsoft", 0.40)]
        positions = [Position("AAPL", shares=20, price=50)]

        trades = generate_rebalance_trades(
            trade_date=date(2025, 6, 30),
            holdings=holdings,
            positions=positions,
            prices={"AAPL": 50, "MSFT": 100},
            portfolio_value=1_000,
        )

        self.assertTrue(any(trade.action == "SELL" and trade.symbol == "AAPL" for trade in trades))
        self.assertTrue(any(trade.action == "BUY" and trade.symbol == "MSFT" for trade in trades))


if __name__ == "__main__":
    unittest.main()

